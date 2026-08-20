"""On-demand visual inspection of the current rendered resume.

This capability deliberately has no persistence side effects.  It renders the
same PDF source used by the export endpoint, rasterizes at most two pages in
memory, and returns OpenAI-compatible image message parts for a vision-capable
conversation model.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import sys
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any


DEFAULT_MAX_PAGES = 2
DEFAULT_DPI = 96
DEFAULT_MAX_LONG_EDGE = 1400
DEFAULT_MAX_TOTAL_BYTES = 800 * 1024
MIN_SCALE = 84 / DEFAULT_DPI


@dataclass(frozen=True)
class ResumeVisualSnapshot:
    """Ephemeral model input plus non-sensitive diagnostics."""

    parts: list[dict[str, Any]]
    revision: str
    page_sizes: tuple[tuple[int, int], ...]
    page_bytes: tuple[int, ...]

    @property
    def total_bytes(self) -> int:
        return sum(self.page_bytes)


def _find_poppler_bin() -> str | None:
    """Resolve a Poppler directory containing real pdfinfo/pdftoppm binaries.

    The local desktop runtime exposes Poppler through ``.cmd`` shims.  The
    backend can be started by a detached process whose PATH does not contain
    those shims, so resolution also checks the runtime cache and the Python
    executable's nearby dependency tree without requiring a machine-specific
    absolute path.
    """
    configured = str(os.environ.get("POPPLER_PATH", "") or "").strip()
    candidates: list[Path] = [Path(configured)] if configured else []
    for command in ("pdfinfo", "pdftoppm"):
        resolved = shutil.which(command)
        if not resolved:
            continue
        path = Path(resolved)
        candidates.append(path.parent)
        # The bundled Windows runtime exposes .cmd shims one level above the
        # native Poppler binaries; resolve that layout without hard-coding a
        # workspace path.
        if path.suffix.lower() in {".cmd", ".bat"} and len(path.parents) >= 3:
            candidates.append(path.parents[2] / "native" / "poppler" / "Library" / "bin")
            candidates.append(path.parents[2] / "native" / "poppler" / "bin")

    # When the detached backend does not inherit the desktop runtime PATH,
    # locate the same bundled runtime relative to the current user or Python
    # executable.  These are narrow, deterministic paths rather than a broad
    # recursive filesystem scan.
    runtime_roots = {
        Path.home() / ".cache" / "codex-runtimes",
        Path(sys.executable).resolve().parent.parent / ".cache" / "codex-runtimes",
    }
    for runtime_root in runtime_roots:
        if not runtime_root.is_dir():
            continue
        for runtime_dir in runtime_root.iterdir():
            candidates.extend([
                runtime_dir / "dependencies" / "native" / "poppler" / "Library" / "bin",
                runtime_dir / "dependencies" / "native" / "poppler" / "bin",
            ])

    for candidate in candidates:
        if not candidate:
            continue
        candidate = candidate.expanduser()
        if (candidate / "pdfinfo.exe").is_file() and (candidate / "pdftoppm.exe").is_file():
            return str(candidate)
        if os.name != "nt" and (candidate / "pdfinfo").is_file() and (candidate / "pdftoppm").is_file():
            return str(candidate)
    return None


def _encode_png(image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _resize_pages(images: list, scale: float) -> list:
    if scale >= 0.999:
        return [image.copy() for image in images]
    from PIL import Image

    resampling = getattr(Image, "Resampling", Image).LANCZOS
    return [
        image.resize(
            (
                max(1, round(image.width * scale)),
                max(1, round(image.height * scale)),
            ),
            resampling,
        )
        for image in images
    ]


def _snapshot_revision(
    resume_data: dict,
    layout_config: dict | None,
    photo: str | None,
    render_style: dict | None,
) -> str:
    payload = {
        "resume_data": resume_data or {},
        "layout_config": layout_config or {},
        "photo": photo or "",
        "render_style": render_style or {},
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _pdf_pages_to_snapshot(
    pdf_bytes: bytes,
    *,
    max_pages: int,
    dpi: int,
    revision: str,
    max_long_edge: int = DEFAULT_MAX_LONG_EDGE,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
) -> ResumeVisualSnapshot:
    """Rasterize PDF bytes without creating a user-visible file."""
    if not pdf_bytes:
        return ResumeVisualSnapshot([], revision, (), ())

    try:
        from pdf2image import convert_from_bytes
    except ImportError as exc:  # pragma: no cover - exercised only in minimal deployments
        raise RuntimeError("当前运行环境缺少 PDF 图片渲染依赖，请安装 pdf2image") from exc

    images = convert_from_bytes(
        pdf_bytes,
        dpi=max(72, int(dpi)),
        first_page=1,
        last_page=max(1, int(max_pages)),
        fmt="png",
        thread_count=1,
        poppler_path=_find_poppler_bin(),
    )
    source_images = images[: max(1, int(max_pages))]
    if not source_images:
        return ResumeVisualSnapshot([], revision, (), ())

    longest_edge = max(max(image.size) for image in source_images)
    initial_scale = min(1.0, max(1, int(max_long_edge)) / longest_edge)
    scale = initial_scale
    encoded_pages: list[bytes] = []
    output_images: list = []
    while True:
        for image in output_images:
            image.close()
        output_images = _resize_pages(source_images, scale)
        encoded_pages = [_encode_png(image) for image in output_images]
        total_bytes = sum(len(value) for value in encoded_pages)
        if total_bytes <= max(1, int(max_total_bytes)) or scale <= MIN_SCALE + 1e-6:
            break
        target_scale = scale * ((max_total_bytes / total_bytes) ** 0.5) * 0.96
        scale = max(MIN_SCALE, min(scale * 0.92, target_scale))

    parts: list[dict[str, Any]] = []
    for png_bytes in encoded_pages:
        encoded = base64.b64encode(png_bytes).decode("ascii")
        parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{encoded}"},
        })

    page_sizes = tuple(image.size for image in output_images)
    page_bytes = tuple(len(value) for value in encoded_pages)
    for image in output_images:
        image.close()
    for image in images:
        image.close()
    return ResumeVisualSnapshot(parts, revision, page_sizes, page_bytes)


def render_resume_pdf_snapshot(
    resume_data: dict,
    layout_config: dict | None = None,
    *,
    photo: str | None = None,
    render_style: dict | None = None,
    max_pages: int = DEFAULT_MAX_PAGES,
    dpi: int = DEFAULT_DPI,
    max_long_edge: int = DEFAULT_MAX_LONG_EDGE,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
) -> ResumeVisualSnapshot:
    """Render the canonical PDF into a bounded, color PNG snapshot."""
    from ..pdf_generator import generate_pdf

    page_limit = max(1, min(int(max_pages or DEFAULT_MAX_PAGES), DEFAULT_MAX_PAGES))
    revision = _snapshot_revision(resume_data, layout_config, photo, render_style)
    pdf_bytes = generate_pdf(
        resume_data or {},
        style=render_style,
        photo=photo,
        layout_config=layout_config,
    )
    return _pdf_pages_to_snapshot(
        pdf_bytes,
        max_pages=page_limit,
        dpi=dpi,
        revision=revision,
        max_long_edge=max_long_edge,
        max_total_bytes=max_total_bytes,
    )


def render_resume_pdf_images(
    resume_data: dict,
    layout_config: dict | None = None,
    *,
    photo: str | None = None,
    render_style: dict | None = None,
    max_pages: int = DEFAULT_MAX_PAGES,
    dpi: int = DEFAULT_DPI,
) -> list[dict[str, Any]]:
    """Render the current resume PDF and return at most ``max_pages`` PNG parts.

    The function is intentionally synchronous because the PDF renderer and
    rasterizer are blocking libraries.  Callers in the async agent should use
    ``asyncio.to_thread``.  No files, database rows, messages, or logs are
    created by this skill.
    """
    return render_resume_pdf_snapshot(
        resume_data,
        layout_config,
        photo=photo,
        render_style=render_style,
        max_pages=max_pages,
        dpi=dpi,
    ).parts


__all__ = [
    "DEFAULT_DPI",
    "DEFAULT_MAX_LONG_EDGE",
    "DEFAULT_MAX_TOTAL_BYTES",
    "ResumeVisualSnapshot",
    "render_resume_pdf_images",
    "render_resume_pdf_snapshot",
]
