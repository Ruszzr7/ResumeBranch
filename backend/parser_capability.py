"""Fast, deterministic document capability verification."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from .llm_gateway import GatewayConfig, invoke_document, model_family, parse_json_output


ASSET_DIR = Path(__file__).with_name("assets")
EXPECTED = {
    "name": "LIN YANZHEN",
    "phone": "13800001234",
    "email": "parser-check@example.com",
    "school": "QINGLAN UNIVERSITY",
}

CAPABILITY_PROMPT = '''Read this one-page synthetic resume. Return JSON only:
{"name":"","phone":"","email":"","school":"","visual_code":"","columns":0,"avatar_present":false}
Preserve exact text. columns is the visible column count. avatar_present describes whether a portrait/avatar is visible.'''


def _evaluate(payload: dict[str, Any], *, code: str) -> dict[str, bool]:
    content = all(
        str(payload.get(key, "")).strip().casefold() == value.casefold()
        for key, value in EXPECTED.items()
    )
    return {
        "content": content,
        "visual_code": str(payload.get("visual_code", "")).strip().upper() == code,
        "layout": payload.get("columns") == 2,
        "avatar": payload.get("avatar_present") is True,
    }


async def _verify_candidate(config: GatewayConfig) -> dict[str, Any]:
    pdf_bytes = (ASSET_DIR / "parser_fixture.pdf").read_bytes()
    image_bytes = (ASSET_DIR / "parser_fixture.png").read_bytes()

    async def run(content: bytes, mime: str, filename: str, code: str):
        raw = ""
        try:
            raw = await invoke_document(
                config, content=content, mime_type=mime, filename=filename,
                prompt=CAPABILITY_PROMPT, timeout=20,
            )
            payload = parse_json_output(raw)
            return {"ok": True, "payload": payload, **_evaluate(payload, code=code)}
        except Exception as exc:
            return {
                "ok": False, "error": type(exc).__name__,
                "error_message": str(exc).strip()[:240],
                "raw_preview": raw[:400] if raw else "",
                "content": False, "visual_code": False, "layout": False, "avatar": False,
            }

    # Run sequentially: two concurrent base64 multimodal requests caused false
    # 403/rate-limit failures on otherwise working relay routes.
    image = await run(image_bytes, "image/png", "parser_fixture.png", "IMG-4827")
    pdf = await run(pdf_bytes, "application/pdf", "parser_fixture.pdf", "PDF-7319")
    adapter = config.resolved_adapter()
    checks = {
        "connected": bool(pdf["ok"] or image["ok"]),
        "image": bool(image["ok"] and image["content"] and image["visual_code"]),
        "pdf": bool(pdf["ok"] and pdf["content"]),
        "pdf_vision": bool(pdf["ok"] and pdf["visual_code"]),
        # Only these protocols have a defined first-class PDF file input. An
        # application/pdf data URL inside Chat Completions is non-standard and
        # must not be advertised as native PDF support.
        "native_pdf": adapter in {"gemini_native", "openai_responses"},
        "layout": bool(pdf["layout"] and image["layout"]),
        "avatar": bool(pdf["avatar"] and image["avatar"]),
        "structured_output": bool(pdf["ok"] and image["ok"]),
    }
    return {
        "success": all(checks.values()),
        "adapter": adapter,
        "model_family": model_family(config.model),
        "checks": checks,
        "details": {"pdf": pdf, "image": image},
    }


async def verify_parser_capabilities(config: GatewayConfig) -> dict[str, Any]:
    """Probe the highest-fidelity protocol and return the selected adapter."""
    candidates: list[GatewayConfig] = []
    if config.adapter == "auto" and model_family(config.model) == "gemini":
        # Gemini relays often expose both /v1/chat/completions and the native
        # /v1beta generateContent route. Probe native first because it has a
        # defined inline PDF format and materially better document fidelity.
        candidates.append(GatewayConfig(
            role=config.role,
            base_url=config.base_url,
            model=config.model,
            api_key=config.api_key,
            adapter="gemini_native",
        ))
    candidates.append(GatewayConfig(
        role=config.role,
        base_url=config.base_url,
        model=config.model,
        api_key=config.api_key,
        adapter=config.resolved_adapter(),
    ))

    attempts = []
    results = []
    seen = set()
    for candidate in candidates:
        adapter = candidate.resolved_adapter()
        if adapter in seen:
            continue
        seen.add(adapter)
        result = await _verify_candidate(candidate)
        results.append(result)
        attempts.append({
            "adapter": adapter,
            "success": result["success"],
            "checks": result["checks"],
        })
        if result["success"]:
            result["attempts"] = attempts
            result["message"] = "PDF 与图片解析能力验证通过"
            return result

    # Return the most informative attempt rather than blindly returning the
    # last fallback. Prefer more passed checks, with native PDF as a tiebreaker.
    best = max(
        results,
        key=lambda item: (sum(bool(v) for v in item["checks"].values()), bool(item["checks"].get("native_pdf"))),
    )
    errors = []
    for section in ("image", "pdf"):
        message = best.get("details", {}).get(section, {}).get("error_message", "")
        if message and message not in errors:
            errors.append(message)
    if not best["checks"].get("native_pdf"):
        errors.append("当前地址只通过了 OpenAI Chat 兼容调用，没有可验证的原生 PDF 文件通道")
    best["attempts"] = attempts
    best["message"] = "；".join(errors) or "接口响应正常，但没有通过全部解析能力检查"
    return best
