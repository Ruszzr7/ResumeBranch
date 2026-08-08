"""Protocol adapters shared by chat and document parsing roles."""

from __future__ import annotations

import base64
import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

import httpx
from langchain_openai import ChatOpenAI


ADAPTERS = {
    "openai_chat": "OpenAI Chat Completions",
    "openai_responses": "OpenAI Responses",
    "gemini_native": "Gemini Native",
}


@dataclass(frozen=True)
class GatewayConfig:
    role: str
    base_url: str
    model: str
    api_key: str
    adapter: str = "auto"

    def resolved_adapter(self) -> str:
        return detect_adapter(self.base_url, self.model, self.adapter)


def model_family(model: str) -> str:
    value = model.strip().lower()
    if "gemini" in value:
        return "gemini"
    if value.startswith(("gpt-", "o1", "o3", "o4")):
        return "openai"
    if "claude" in value:
        return "anthropic"
    if "kimi" in value or value.startswith("k3"):
        return "kimi"
    if "deepseek" in value:
        return "deepseek"
    return "unknown"


def temperature_supported(model: str) -> bool:
    """Whether an OpenAI-compatible model accepts an explicit temperature."""
    value = model.strip().lower()
    return not (
        value.startswith(("gpt-5", "o1", "o3", "o4"))
        or "reasoner" in value
        or "thinking" in value
    )


def resolve_temperature(model: str, requested: float | None) -> float | None:
    """Apply model constraints while preserving role-specific defaults."""
    if requested is None:
        return None
    if model_family(model) == "kimi":
        return 1.0
    return requested if temperature_supported(model) else None


def detect_adapter(base_url: str, model: str = "", requested: str = "auto") -> str:
    if requested and requested != "auto":
        if requested not in ADAPTERS:
            raise ValueError("不支持的接入协议")
        return requested
    parsed = urlsplit(base_url.strip())
    host = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/").lower()
    if host == "generativelanguage.googleapis.com" and "/openai" not in path:
        return "gemini_native"
    if path.endswith("/responses"):
        return "openai_responses"
    return "openai_chat"


def validate_gateway_config(config: GatewayConfig) -> None:
    if config.role not in {"chat", "parser"}:
        raise ValueError("配置角色必须是 chat 或 parser")
    if not config.model.strip():
        raise ValueError("模型不能为空")
    parsed = urlsplit(config.base_url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("URL 必须是有效的 http:// 或 https:// 地址")
    if config.adapter not in {"auto", *ADAPTERS}:
        raise ValueError("不支持的接入协议")


def openai_endpoint(base_url: str, suffix: str) -> str:
    parsed = urlsplit(base_url.strip())
    path = parsed.path.rstrip("/")
    for known in ("/chat/completions", "/responses", "/models"):
        if path.endswith(known):
            path = path[: -len(known)]
            break
    return urlunsplit((parsed.scheme, parsed.netloc, f"{path}{suffix}", "", ""))


def gemini_endpoint(base_url: str, model: str) -> str:
    """Build a Gemini native endpoint from official or relay-style base URLs."""
    parsed = urlsplit(base_url.strip())
    path = parsed.path.rstrip("/")
    for known in ("/chat/completions", "/responses", "/models", "/openai"):
        if path.lower().endswith(known):
            path = path[: -len(known)].rstrip("/")
            break
    # A relay may expose OpenAI compatibility at /v1 while exposing Gemini's
    # native protocol at /v1beta on the same host (for example Apilio).
    if path.lower().endswith("/v1"):
        path = path[:-3].rstrip("/") + "/v1beta"
    elif not path.lower().endswith("/v1beta"):
        path = path + "/v1beta"
    return urlunsplit((
        parsed.scheme,
        parsed.netloc,
        f"{path}/models/{quote(model, safe='')}:generateContent",
        "",
        "",
    ))


def _gateway_error(response: httpx.Response, operation: str) -> ValueError:
    status = response.status_code
    detail = ""
    try:
        payload = response.json()
        error = payload.get("error", payload) if isinstance(payload, dict) else payload
        if isinstance(error, dict):
            detail = str(error.get("message") or error.get("detail") or error.get("code") or "")
        else:
            detail = str(error)
    except Exception:
        detail = response.text
    detail = re.sub(r"\s+", " ", detail).strip()[:240]
    if status in {401, 403}:
        message = f"{operation}被 API 拒绝（HTTP {status}），请检查密钥权限、模型权限或中转站限制"
    elif status == 413:
        message = f"{operation}文件超过 API 请求大小限制"
    elif status == 429:
        message = f"{operation}触发 API 频率或额度限制，请稍后重试"
    elif status >= 500:
        message = f"{operation}的上游服务暂时不可用（HTTP {status}）"
    else:
        message = f"{operation}失败（HTTP {status}）"
    if detail:
        message += f"：{detail}"
    return ValueError(message)


async def _post_json_with_retry(
    client: httpx.AsyncClient,
    endpoint: str,
    *,
    operation: str,
    attempts: int = 2,
    **kwargs: Any,
) -> httpx.Response:
    response: httpx.Response | None = None
    for attempt in range(attempts):
        response = await client.post(endpoint, **kwargs)
        if response.status_code < 400:
            return response
        if response.status_code not in {403, 429, 500, 502, 503, 504} or attempt + 1 >= attempts:
            raise _gateway_error(response, operation)
        await asyncio.sleep(0.6 * (attempt + 1))
    raise _gateway_error(response, operation)  # pragma: no cover


def create_chat_model(
    config: GatewayConfig,
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> ChatOpenAI:
    validate_gateway_config(config)
    if config.resolved_adapter() != "openai_chat":
        raise ValueError("当前对话运行时仅支持 OpenAI Chat Completions 协议")
    kwargs: dict[str, Any] = {
        "api_key": config.api_key or "local-llm-disabled",
        "base_url": config.base_url,
        "model": config.model,
        "max_retries": 3,
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    effective_temperature = resolve_temperature(config.model, temperature)
    if effective_temperature is not None:
        kwargs["temperature"] = effective_temperature
    return ChatOpenAI(**kwargs)


async def test_chat_connection(config: GatewayConfig, *, timeout: float = 25.0) -> dict[str, Any]:
    adapter = config.resolved_adapter()
    if adapter != "openai_chat":
        raise ValueError("该协议尚不能用于项目对话，请使用 OpenAI Chat 兼容地址")
    endpoint = openai_endpoint(config.base_url, "/chat/completions")
    test_temperature = resolve_temperature(config.model, 0.0)
    structured_payload = {
        "model": config.model,
        "messages": [{"role": "user", "content": '只输出 JSON 对象：{"ok":true}'}],
        "max_tokens": 2048,
        "response_format": {"type": "json_object"},
    }
    stream_payload = {
        "model": config.model,
        "messages": [{"role": "user", "content": "只回复 OK"}],
        "max_tokens": 1024,
        "stream": True,
    }
    if test_temperature is not None:
        structured_payload["temperature"] = test_temperature
        stream_payload["temperature"] = test_temperature
    headers = {"Authorization": f"Bearer {config.api_key}"}
    async with asyncio.timeout(timeout):
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
            structured_response = await client.post(
                endpoint, headers=headers, json=structured_payload
            )
            if structured_response.status_code == 400:
                if "only 1 is allowed" in structured_response.text.lower():
                    structured_payload["temperature"] = 1
                    stream_payload["temperature"] = 1
                structured_payload.pop("response_format", None)
                structured_response = await client.post(
                    endpoint, headers=headers, json=structured_payload
                )
            if structured_response.status_code >= 400:
                raise _gateway_error(structured_response, "对话连接测试")
            structured_data = structured_response.json()
            structured_text = message_text(
                (((structured_data.get("choices") or [{}])[0].get("message") or {}).get("content"))
            )

            stream_parts: list[str] = []
            async with client.stream("POST", endpoint, headers=headers, json=stream_payload) as streamed:
                if streamed.status_code >= 400:
                    await streamed.aread()
                    raise _gateway_error(streamed, "流式输出测试")
                async for line in streamed.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    value = line[5:].strip()
                    if not value or value == "[DONE]":
                        continue
                    try:
                        event = json.loads(value)
                        delta = (((event.get("choices") or [{}])[0].get("delta") or {}).get("content"))
                        if isinstance(delta, str):
                            stream_parts.append(delta)
                    except json.JSONDecodeError:
                        continue

    text = structured_text.strip()
    stream_text = "".join(stream_parts).strip()
    try:
        structured = parse_json_output(text).get("ok") is True
    except ValueError:
        structured = False
    return {
        "success": bool(text and stream_text and structured),
        "connected": bool(text or stream_text),
        "adapter": adapter,
        "model_family": model_family(config.model),
        "checks": {
            "connected": bool(text or stream_text),
            "chat": bool(text),
            "stream": bool(stream_text),
            "structured_output": structured,
        },
    }


def _data_url(content: bytes, mime_type: str) -> str:
    return f"data:{mime_type};base64,{base64.b64encode(content).decode('ascii')}"


def message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for part in content:
            if isinstance(part, str):
                texts.append(part)
            elif isinstance(part, dict):
                value = part.get("text") or part.get("content")
                if isinstance(value, str):
                    texts.append(value)
        return "\n".join(texts)
    return str(content or "")


async def invoke_document(
    config: GatewayConfig,
    *,
    content: bytes,
    mime_type: str,
    filename: str,
    prompt: str,
    timeout: float = 60.0,
) -> str:
    """Invoke one configured document protocol and return plain model text."""
    validate_gateway_config(config)
    adapter = config.resolved_adapter()
    if adapter == "openai_chat":
        if mime_type == "application/pdf":
            raise ValueError(
                "OpenAI Chat 兼容协议没有标准的 PDF 文件输入；请使用 Gemini Native 或 OpenAI Responses 解析协议"
            )
        endpoint = openai_endpoint(config.base_url, "/chat/completions")
        payload = {
            "model": config.model,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": _data_url(content, mime_type)}},
            ]}],
            "temperature": 0,
            # Reasoning models may consume most of this budget before emitting JSON.
            "max_tokens": 8192,
            "response_format": {"type": "json_object"},
        }
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                endpoint,
                headers={"Authorization": f"Bearer {config.api_key}"},
                json=payload,
            )
            # Some OpenAI-compatible relays do not implement response_format. Keep
            # the same protocol and retry once without that optional hint.
            if response.status_code == 400:
                payload.pop("response_format", None)
                response = await client.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {config.api_key}"},
                    json=payload,
                )
            if response.status_code >= 400:
                # A single retry is useful for relays that intermittently return
                # 403/5xx while rotating an upstream multimodal route.
                response = await _post_json_with_retry(
                    client,
                    endpoint,
                    operation="文档解析",
                    headers={"Authorization": f"Bearer {config.api_key}"},
                    json=payload,
                )
            data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise ValueError("解析 API 没有返回可用结果")
        choice = choices[0]
        if choice.get("finish_reason") in {"length", "max_tokens"}:
            raise ValueError("解析模型输出被截断，请换用输出上限更高的模型后重试")
        return message_text((choice.get("message") or {}).get("content"))
    if adapter == "openai_responses":
        endpoint = openai_endpoint(config.base_url, "/responses")
        if mime_type == "application/pdf":
            file_part = {
                "type": "input_file", "filename": filename,
                "file_data": _data_url(content, mime_type),
            }
        else:
            file_part = {"type": "input_image", "image_url": _data_url(content, mime_type)}
        payload = {
            "model": config.model,
            "input": [{"role": "user", "content": [file_part, {"type": "input_text", "text": prompt}]}],
        }
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                endpoint,
                headers={"Authorization": f"Bearer {config.api_key}"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        if isinstance(data.get("output_text"), str):
            return data["output_text"]
        texts = []
        for item in data.get("output", []):
            for part in item.get("content", []):
                if isinstance(part.get("text"), str):
                    texts.append(part["text"])
        return "\n".join(texts)
    if adapter == "gemini_native":
        endpoint = gemini_endpoint(config.base_url, config.model)
        payload = {
            "contents": [{"role": "user", "parts": [
                {"inline_data": {"mime_type": mime_type, "data": base64.b64encode(content).decode("ascii")}},
                {"text": prompt},
            ]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0,
                "maxOutputTokens": 16384,
            },
        }
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await _post_json_with_retry(
                client,
                endpoint,
                operation="Gemini 原生文档解析",
                params={"key": config.api_key},
                json=payload,
            )
            data = response.json()
        return "".join(
            part.get("text", "")
            for candidate in data.get("candidates", [])
            for part in candidate.get("content", {}).get("parts", [])
        )
    raise ValueError("当前协议不支持文档解析")


def parse_json_output(content: str) -> dict[str, Any]:
    cleaned = content.strip()
    cleaned = re.sub(r"^```json\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"^```\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        # Tolerate a short textual prefix/suffix while still requiring one valid
        # JSON object. This does not guess or repair resume content.
        start = cleaned.find("{")
        if start < 0:
            raise ValueError("解析模型没有返回 JSON 对象") from exc
        try:
            parsed, _ = json.JSONDecoder().raw_decode(cleaned[start:])
        except json.JSONDecodeError as inner:
            if cleaned.count("{") > cleaned.count("}") or cleaned.count("[") > cleaned.count("]"):
                raise ValueError("解析模型返回的 JSON 不完整，请重试或更换解析模型") from inner
            raise ValueError(f"解析模型返回了无效 JSON（第 {inner.lineno} 行）") from inner
    if not isinstance(parsed, dict):
        raise ValueError("模型没有返回 JSON 对象")
    return parsed
