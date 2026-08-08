"""Best-effort model discovery for OpenAI-compatible API roots."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx


def build_models_url(base_url: str) -> str:
    raw = base_url.strip()
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("URL 必须是有效的 http:// 或 https:// 地址")

    path = parsed.path.rstrip("/")
    for suffix in ("/chat/completions", "/responses"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
            break
    if not path.endswith("/models"):
        path = f"{path}/models"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def extract_model_ids(payload: Any) -> list[str]:
    if isinstance(payload, dict):
        candidates = payload.get("data", payload.get("models", []))
    elif isinstance(payload, list):
        candidates = payload
    else:
        candidates = []

    model_ids: set[str] = set()
    for item in candidates if isinstance(candidates, list) else []:
        if isinstance(item, str):
            value = item
        elif isinstance(item, dict):
            value = item.get("id") or item.get("model") or item.get("name")
        else:
            value = None
        if isinstance(value, str) and value.strip():
            model_ids.add(value.strip())
    return sorted(model_ids, key=str.casefold)


async def discover_models(
    base_url: str,
    api_key: str = "",
    *,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    models_url = build_models_url(base_url)
    headers = {"Accept": "application/json"}
    if api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"

    owns_client = client is None
    requester = client or httpx.AsyncClient(timeout=httpx.Timeout(12.0), follow_redirects=True)
    try:
        response = await requester.get(models_url, headers=headers)
        if response.status_code in {401, 403}:
            return {
                "success": False,
                "models": [],
                "message": "该地址查询模型需要有效的 API Key，请填写 Key 后重试。",
            }
        if response.status_code >= 400:
            return {
                "success": False,
                "models": [],
                "message": "该接口未开放模型列表，或需要有效的 API Key；仍可手动填写模型。",
            }
        try:
            payload = response.json()
        except ValueError:
            payload = None
        models = extract_model_ids(payload)
        if not models:
            return {
                "success": False,
                "models": [],
                "message": "接口未返回可识别的模型列表，请手动填写模型。",
            }
        return {"success": True, "models": models, "message": f"已获取 {len(models)} 个可用模型"}
    except httpx.RequestError:
        return {
            "success": False,
            "models": [],
            "message": "无法连接模型列表接口，请检查 URL。",
        }
    finally:
        if owns_client:
            await requester.aclose()
