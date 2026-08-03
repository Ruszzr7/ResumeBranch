"""Metadata helpers for uploaded resume source documents."""

from __future__ import annotations

from io import BytesIO


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
