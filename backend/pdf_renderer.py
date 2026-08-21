"""Render resume HTML to PDF with the Chromium engine used by the preview."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


LOGGER = logging.getLogger(__name__)
PDF_BROWSER_ENV = "RESUME_PDF_BROWSER"
PDF_NO_SANDBOX_ENV = "RESUME_PDF_NO_SANDBOX"


def find_pdf_browser() -> str | None:
    """Return a usable Chromium-family browser path, if one is available."""
    configured = str(os.environ.get(PDF_BROWSER_ENV, "") or "").strip().strip('"')
    if configured:
        configured_path = Path(configured).expanduser()
        if configured_path.is_file():
            return str(configured_path.resolve())
        LOGGER.warning("Ignoring missing %s path: %s", PDF_BROWSER_ENV, configured)

    for command in (
        "chrome",
        "chrome.exe",
        "msedge",
        "msedge.exe",
        "chromium",
        "chromium.exe",
        "chromium-browser",
        "google-chrome",
        "google-chrome-stable",
    ):
        resolved = shutil.which(command)
        if resolved:
            return str(Path(resolved).resolve())

    candidates: list[Path] = []
    if os.name == "nt":
        for root_name in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            root = os.environ.get(root_name)
            if not root:
                continue
            root_path = Path(root)
            candidates.extend((
                root_path / "Google" / "Chrome" / "Application" / "chrome.exe",
                root_path / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            ))
    else:
        candidates.extend((
            Path("/usr/bin/google-chrome"),
            Path("/usr/bin/google-chrome-stable"),
            Path("/usr/bin/chromium"),
            Path("/usr/bin/chromium-browser"),
        ))

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate.resolve())
    return None


def render_html_with_chromium(
    html_content: str,
    *,
    browser_path: str | None = None,
    timeout_seconds: int = 30,
) -> bytes:
    """Print HTML to PDF with Chromium and fail clearly when it is unavailable."""
    executable = browser_path or find_pdf_browser()
    if not executable:
        raise RuntimeError(
            "未找到可用的 Chromium 浏览器。请安装 Chrome、Edge 或 Chromium，"
            f"也可以通过 {PDF_BROWSER_ENV} 指定浏览器可执行文件。"
        )

    with tempfile.TemporaryDirectory(prefix="resume-pdf-") as temp_dir:
        temp_root = Path(temp_dir)
        html_path = temp_root / "resume.html"
        pdf_path = temp_root / "resume.pdf"
        profile_path = temp_root / "browser-profile"
        html_path.write_text(html_content, encoding="utf-8")

        command = [
            executable,
            "--headless=new",
            "--disable-gpu",
            "--disable-extensions",
            "--disable-background-networking",
            "--no-first-run",
            "--no-default-browser-check",
            "--no-pdf-header-footer",
            "--allow-file-access-from-files",
            f"--user-data-dir={profile_path}",
            f"--print-to-pdf={pdf_path}",
            "--timeout=5000",
            html_path.as_uri(),
        ]
        if os.environ.get(PDF_NO_SANDBOX_ENV, "").strip().lower() in {
            "1", "true", "yes", "on"
        }:
            command.insert(1, "--no-sandbox")
        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            completed = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=timeout_seconds,
                creationflags=creation_flags,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError(f"Chromium PDF 生成失败：{exc}") from exc

        if completed.returncode != 0 or not pdf_path.is_file():
            detail = completed.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                "Chromium PDF 生成失败"
                f"（退出码 {completed.returncode}）：{detail[-1000:] or '未生成 PDF 文件'}"
            )

        pdf_bytes = pdf_path.read_bytes()
        if not pdf_bytes.startswith(b"%PDF-"):
            raise RuntimeError("Chromium 返回了无效的 PDF 文件")
        return pdf_bytes
