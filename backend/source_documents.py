"""Metadata helpers for uploaded resume source documents."""

from __future__ import annotations

import hashlib
from io import BytesIO
import os
from pathlib import Path
import uuid


ALLOWED_SOURCE_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/jpg"}
SOURCE_EXTENSION = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
}


def source_document_root() -> Path:
    configured = os.getenv("SOURCE_DOCUMENT_DIR", "").strip()
    root = Path(configured) if configured else Path(__file__).resolve().parents[1] / "data" / "source_documents"
    return root.resolve()


def _safe_storage_path(storage_key: str) -> Path:
    root = source_document_root()
    candidate = (root / storage_key).resolve()
    if root != candidate and root not in candidate.parents:
        raise ValueError("原稿存储路径无效")
    return candidate


def persist_source_document(db, user_id: int, content: bytes, content_type: str, filename: str):
    """Atomically persist one parsed source file and its pending metadata."""
    if content_type not in ALLOWED_SOURCE_TYPES:
        raise ValueError("只支持 PDF、PNG 或 JPG 原稿")
    if not content:
        raise ValueError("原稿文件为空")
    from .database import SourceDocument

    document_id = str(uuid.uuid4())
    extension = SOURCE_EXTENSION[content_type]
    storage_key = f"{user_id}/{document_id}{extension}"
    path = _safe_storage_path(storage_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(content)
    temporary.replace(path)
    document = SourceDocument(
        id=document_id,
        user_id=user_id,
        storage_key=storage_key,
        original_filename=(Path(filename or f"resume{extension}").name[:255] or f"resume{extension}"),
        mime_type="image/jpeg" if content_type == "image/jpg" else content_type,
        file_size=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        status="pending",
    )
    try:
        db.add(document)
        db.commit()
        db.refresh(document)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return document


def source_document_path(storage_key: str) -> Path:
    path = _safe_storage_path(storage_key)
    if not path.is_file():
        raise FileNotFoundError("原稿文件不存在")
    return path


def remove_source_document_file(storage_key: str) -> None:
    try:
        path = _safe_storage_path(storage_key)
        path.unlink(missing_ok=True)
        parent = path.parent
        root = source_document_root()
        if parent != root and parent.exists() and not any(parent.iterdir()):
            parent.rmdir()
    except (OSError, ValueError):
        # Metadata cleanup must not fail just because an already-orphaned file
        # cannot be removed at this moment.
        return


def detect_source_page_count(content: bytes, content_type: str) -> int:
    """Return the real PDF page count; image uploads are a single source page."""
    if content_type != "application/pdf":
        return 1
    if not content:
        raise ValueError("PDF 文件为空")

    from pypdf import PdfReader

    reader = PdfReader(BytesIO(content), strict=False)
    page_count = len(reader.pages)
    if page_count < 1:
        raise ValueError("PDF 中没有可读取的页面")
    return page_count
