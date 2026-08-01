"""Helpers for passing uploaded resume files to multimodal model APIs."""

from __future__ import annotations

import base64


def build_file_message_part(
    content: bytes,
    content_type: str,
    *,
    normalize_image_type: bool = False,
) -> dict:
    """Return the original upload as an OpenAI-compatible data URL part.

    PDF files intentionally remain ``application/pdf``.  The production
    version of the product used the model's native PDF understanding, so this
    helper must not rasterize pages or alter the original bytes.
    """
    if content_type == "application/pdf":
        mime_type = "application/pdf"
    elif content_type.startswith("image/"):
        if normalize_image_type:
            mime_type = content_type if content_type in {"image/png", "image/webp"} else "image/jpeg"
        else:
            mime_type = content_type
    else:
        raise ValueError("只支持图片或PDF文件")

    encoded = base64.b64encode(content).decode("utf-8")
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
    }
