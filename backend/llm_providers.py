"""LLM provider registry and machine-local profile persistence.

All providers below expose an OpenAI-compatible Chat Completions endpoint, so
the agent can keep using ``ChatOpenAI``. Credentials are stored in ``data/``
(the persisted Docker volume) and are never returned to the browser.
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any


PROVIDERS: dict[str, dict[str, Any]] = {
    "kimi_api": {
        "label": "Kimi 开放平台（按量 API）",
        "base_url": "https://api.moonshot.cn/v1",
        "models": ["kimi-k3", "kimi-k2.6"],
        "default_model": "kimi-k3",
        "temperature": {"supported": False, "default": None},
        "note": "适合产品集成，按 API 用量计费。",
        "docs_url": "https://www.kimi.com/help/kimi-api/api-overview",
    },
    "kimi_coding": {
        "label": "Kimi Code（会员订阅）",
        "base_url": "https://api.kimi.com/coding/v1",
        "models": ["k3", "k3-256k", "kimi-for-coding", "kimi-for-coding-highspeed"],
        "default_model": "kimi-for-coding",
        "temperature": {"supported": False, "default": None},
        "note": "使用 Kimi Code 会员 Key；与开放平台 Key/额度不互通。",
        "docs_url": "https://www.kimi.com/code/docs/",
    },
    "deepseek": {
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "models": ["deepseek-v4-flash", "deepseek-v4-pro"],
        "default_model": "deepseek-v4-flash",
        "temperature": {"supported": True, "default": 1.0, "min": 0.0, "max": 2.0, "step": 0.1},
        "note": "思考模式会忽略 temperature；旧版 deepseek-chat/reasoner 已退役。",
        "docs_url": "https://api-docs.deepseek.com/",
    },
    "glm": {
        "label": "智谱 GLM",
        "base_url": "https://open.bigmodel.cn/api/paas/v4/",
        "models": ["glm-5.2", "glm-5.1", "glm-5-turbo", "glm-4.7-flash"],
        "default_model": "glm-5.2",
        "temperature": {"supported": True, "default": 0.6, "min": 0.01, "max": 1.0, "step": 0.05},
        "note": "OpenAI 兼容接口要求 temperature 大于 0 且不超过 1。",
        "docs_url": "https://docs.bigmodel.cn/cn/guide/develop/openai/introduction",
    },
    "minimax": {
        "label": "MiniMax",
        "base_url": "https://api.minimaxi.com/v1",
        "models": ["MiniMax-M2.7", "MiniMax-M2.7-highspeed", "MiniMax-M2.5", "MiniMax-M2.5-highspeed"],
        "default_model": "MiniMax-M2.7",
        "temperature": {"supported": True, "default": 1.0, "min": 0.0, "max": 2.0, "step": 0.1},
        "note": "支持按量 API Key；Token Plan Key 需使用对应订阅额度。",
        "docs_url": "https://platform.minimaxi.com/docs/api-reference/api-overview",
    },
    "gemini": {
        "label": "Google Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "models": ["gemini-3.6-flash", "gemini-3.6-pro"],
        "default_model": "gemini-3.6-flash",
        "temperature": {"supported": True, "default": 0.2, "min": 0.0, "max": 2.0, "step": 0.1},
        "note": "使用 Google AI Studio API Key 和 Gemini OpenAI 兼容端点。",
        "docs_url": "https://ai.google.dev/gemini-api/docs/openai",
    },
    "openai": {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "models": ["gpt-5.2", "gpt-5-mini", "gpt-4.1"],
        "default_model": "gpt-5.2",
        "temperature": {"supported": True, "default": 0.2, "min": 0.0, "max": 2.0, "step": 0.1},
        "note": "部分推理模型不接受 temperature，选择后系统会自动省略。",
        "docs_url": "https://platform.openai.com/docs/api-reference/chat",
    },
}

PROFILE_PATH = Path(__file__).resolve().parents[1] / "data" / "llm_profiles.json"


def _temperature_supported(provider: str, model: str) -> bool:
    model_key = model.lower()
    if provider in {"kimi_api", "kimi_coding"}:
        return False
    if provider == "deepseek" and ("reasoner" in model_key or "thinking" in model_key):
        return False
    if provider == "openai" and model_key.startswith(("gpt-5", "o1", "o3", "o4")):
        return False
    return bool(PROVIDERS.get(provider, {}).get("temperature", {}).get("supported", True))


def public_registry() -> list[dict[str, Any]]:
    result = []
    for provider_id, definition in PROVIDERS.items():
        item = deepcopy(definition)
        # Models and endpoints change frequently. Only stable provider
        # metadata is sent to the UI; users enter current values themselves.
        item.pop("models", None)
        item.pop("default_model", None)
        item.pop("base_url", None)
        item["id"] = provider_id
        result.append(item)
    return result


def load_profiles() -> dict[str, Any]:
    payload: dict[str, Any] = {"active_provider": "", "profiles": {}}
    if PROFILE_PATH.exists():
        try:
            loaded = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                payload.update(loaded)
        except (OSError, json.JSONDecodeError):
            pass

    legacy_provider = os.getenv("LLM_PROVIDER", "kimi_api").strip() or "kimi_api"
    aliases = {"moonshot": "kimi_api", "openai-compatible": "openai"}
    legacy_provider = aliases.get(legacy_provider, legacy_provider)
    if legacy_provider not in PROVIDERS:
        legacy_provider = "kimi_api"
    payload["active_provider"] = payload.get("active_provider") or legacy_provider
    profiles = payload.setdefault("profiles", {})
    if legacy_provider not in profiles:
        profiles[legacy_provider] = {
            "model": os.getenv("LLM_MODEL", "").strip(),
            "base_url": os.getenv("BASE_URL", "").strip(),
            "api_key": os.getenv("LLM_API_KEY", "").strip(),
            "temperature": PROVIDERS[legacy_provider]["temperature"].get("default"),
        }

    # Earlier local settings used the generic "moonshot" provider for both
    # products. Move a coding subscription endpoint to its correct profile so
    # the provider label, key quota and URL cannot be confused.
    active_provider = payload.get("active_provider")
    active_stored = profiles.get(active_provider, {})
    active_url = str(active_stored.get("base_url", "")).lower()
    if active_provider == "kimi_api" and "api.kimi.com/coding" in active_url:
        profiles["kimi_coding"] = {**active_stored, **profiles.get("kimi_coding", {})}
        profiles.pop("kimi_api", None)
        payload["active_provider"] = "kimi_coding"
    return payload


def save_profile(provider: str, profile: dict[str, Any]) -> dict[str, Any]:
    if provider not in PROVIDERS:
        raise ValueError("不支持的模型服务商")
    payload = load_profiles()
    current = payload.setdefault("profiles", {}).get(provider, {})
    merged = {**current, **profile}
    if not profile.get("api_key"):
        merged["api_key"] = current.get("api_key", "")
    payload["profiles"][provider] = merged
    payload["active_provider"] = provider
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROFILE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def active_profile() -> tuple[str, dict[str, Any]]:
    payload = load_profiles()
    provider = payload.get("active_provider", "kimi_api")
    if provider not in PROVIDERS:
        provider = "kimi_api"
    definition = PROVIDERS[provider]
    stored = payload.get("profiles", {}).get(provider, {})
    profile = {
        "api_key": stored.get("api_key", ""),
        "model": stored.get("model") or definition["default_model"],
        "base_url": stored.get("base_url") or definition["base_url"],
        "temperature": stored.get("temperature", definition["temperature"].get("default")),
    }
    return provider, profile


def serialize_settings() -> dict[str, Any]:
    payload = load_profiles()
    profiles: dict[str, Any] = {}
    for provider_id, definition in PROVIDERS.items():
        stored = payload.get("profiles", {}).get(provider_id, {})
        key = stored.get("api_key", "")
        profiles[provider_id] = {
            "model": stored.get("model", ""),
            "base_url": stored.get("base_url", ""),
            "temperature": stored.get("temperature", definition["temperature"].get("default")),
            "temperature_supported": _temperature_supported(provider_id, stored.get("model", "")),
            "configured": bool(key),
            "api_key_hint": f"••••{key[-4:]}" if key else "",
        }
    return {"active_provider": payload.get("active_provider", "kimi_api"), "providers": public_registry(), "profiles": profiles}


def validate_profile(provider: str, model: str, base_url: str, temperature: float | None) -> None:
    if provider not in PROVIDERS:
        raise ValueError("不支持的模型服务商")
    if not model.strip() or not base_url.strip():
        raise ValueError("模型和 Base URL 不能为空")
    if not base_url.startswith(("http://", "https://")):
        raise ValueError("Base URL 必须以 http:// 或 https:// 开头")
    spec = PROVIDERS[provider]["temperature"]
    if temperature is not None and _temperature_supported(provider, model):
        minimum, maximum = spec.get("min", 0.0), spec.get("max", 2.0)
        if not minimum <= temperature <= maximum:
            raise ValueError(f"temperature 必须在 {minimum} 到 {maximum} 之间")


def temperature_supported(provider: str, model: str) -> bool:
    return _temperature_supported(provider, model)
