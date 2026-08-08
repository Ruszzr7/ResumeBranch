"""Provider-native file extraction helpers.

Kimi's documented PDF workflow is not a multimodal ``image_url`` request. It
uploads the file with ``purpose=file-extract``, retrieves normalized content,
then places that content in the chat context.
"""

from __future__ import annotations

from pathlib import PurePath
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

import httpx


def is_kimi_file_api_url(base_url: str) -> bool:
    """Return whether this is Kimi's official metered API, not Kimi Code."""
    host = (urlsplit(base_url.strip()).hostname or "").lower()
    return host == "api.moonshot.cn" or host.endswith(".api.moonshot.cn")


def build_files_url(base_url: str) -> str:
    parsed = urlsplit(base_url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("URL 必须是有效的 http:// 或 https:// 地址")
    path = parsed.path.rstrip("/")
    for suffix in ("/chat/completions", "/responses", "/models"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
            break
    if not path.endswith("/files"):
        path = f"{path}/files"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


async def extract_kimi_file_content(
    content: bytes,
    *,
    filename: str,
    content_type: str,
    api_key: str,
    base_url: str,
    client: httpx.AsyncClient | None = None,
) -> str:
    """Upload a file to Kimi, retrieve extracted content, and clean it up."""
    if not api_key.strip():
        raise ValueError("Kimi 文件解析需要 API Key")
    files_url = build_files_url(base_url)
    headers = {"Authorization": f"Bearer {api_key.strip()}"}
    safe_name = PurePath(filename or "resume.pdf").name
    owns_client = client is None
    requester = client or httpx.AsyncClient(
        timeout=httpx.Timeout(60.0),
        follow_redirects=True,
    )
    file_id = ""
    try:
        upload = await requester.post(
            files_url,
            headers=headers,
            data={"purpose": "file-extract"},
            files={"file": (safe_name, content, content_type)},
        )
        upload.raise_for_status()
        payload: Any = upload.json()
        file_id = str(payload.get("id", "")) if isinstance(payload, dict) else ""
        if not file_id:
            raise ValueError("Kimi 文件上传成功，但接口未返回 file_id")

        content_response = await requester.get(
            f"{files_url}/{quote(file_id, safe='')}/content",
            headers=headers,
        )
        content_response.raise_for_status()
        extracted = content_response.text
        if not extracted.strip():
            raise ValueError("Kimi 文件抽取结果为空")
        return extracted
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        raise ValueError(f"Kimi 文件接口调用失败（HTTP {status}）") from exc
    except httpx.RequestError as exc:
        raise ValueError("无法连接 Kimi 文件接口") from exc
    finally:
        if file_id:
            try:
                await requester.delete(
                    f"{files_url}/{quote(file_id, safe='')}",
                    headers=headers,
                    timeout=5.0,
                )
            except httpx.HTTPError:
                pass
        if owns_client:
            await requester.aclose()
