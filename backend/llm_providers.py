"""Role-based LLM settings with migration from the earlier provider registry."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .llm_gateway import (
    ADAPTERS,
    GatewayConfig,
    detect_adapter,
    model_family,
    resolve_temperature,
    temperature_supported as gateway_temperature_supported,
    validate_gateway_config,
)


ROLES = ("chat", "parser")
PROFILE_PATH = Path(os.getenv(
    "LLM_PROFILE_PATH",
    str(Path(__file__).resolve().parents[1] / "data" / "llm_profiles.json"),
))

# Kept as an empty compatibility registry for older imports. Vendor identity no
# longer controls runtime behavior.
PROVIDERS: dict[str, dict[str, Any]] = {}


def _blank() -> dict[str, Any]:
    return {
        "base_url": "", "model": "", "api_key": "", "adapter": "auto",
        "verified": False, "capabilities": {}, "verified_at": None,
    }


def _migrate(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("version") == 2 and isinstance(payload.get("configs"), dict):
        result = {"version": 2, "configs": {role: {**_blank(), **payload["configs"].get(role, {})} for role in ROLES}}
        return result
    profiles = payload.get("profiles", {}) if isinstance(payload.get("profiles"), dict) else {}
    active = payload.get("active_provider", "")
    legacy = profiles.get(active, {}) if active else {}
    if not legacy and profiles:
        legacy = next(iter(profiles.values()))
    if not legacy:
        legacy = {
            "base_url": os.getenv("BASE_URL", ""),
            "model": os.getenv("LLM_MODEL", ""),
            "api_key": os.getenv("LLM_API_KEY", ""),
        }
    chat = {**_blank(), **legacy}
    chat["adapter"] = detect_adapter(chat.get("base_url", ""), chat.get("model", "")) if chat.get("base_url") else "auto"
    return {"version": 2, "configs": {"chat": chat, "parser": _blank()}}


def load_profiles() -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if PROFILE_PATH.exists():
        try:
            loaded = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                payload = loaded
        except (OSError, json.JSONDecodeError):
            pass
    return _migrate(payload)


def get_role_config(role: str, *, include_key: bool = True) -> dict[str, Any]:
    if role not in ROLES:
        raise ValueError("配置角色必须是 chat 或 parser")
    config = {**_blank(), **load_profiles()["configs"].get(role, {})}
    if not include_key:
        config.pop("api_key", None)
    return config


def save_role_config(role: str, profile: dict[str, Any]) -> dict[str, Any]:
    current = load_profiles()
    existing = current["configs"].get(role, _blank())
    merged = {**existing, **profile}
    if not profile.get("api_key"):
        merged["api_key"] = existing.get("api_key", "")
    merged["verified"] = bool(profile.get("verified", False))
    current["configs"][role] = merged
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROFILE_PATH.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return current


def gateway_config(role: str, *, api_key_override: str | None = None, **overrides: Any) -> GatewayConfig:
    stored = get_role_config(role)
    stored.update({key: value for key, value in overrides.items() if value is not None})
    key = api_key_override if api_key_override is not None else stored.get("api_key", "")
    return GatewayConfig(
        role=role,
        base_url=str(stored.get("base_url", "")),
        model=str(stored.get("model", "")),
        api_key=str(key or ""),
        adapter=str(stored.get("adapter", "auto") or "auto"),
    )


def serialize_settings() -> dict[str, Any]:
    result: dict[str, Any] = {"configs": {}, "adapters": [{"id": key, "label": value} for key, value in ADAPTERS.items()]}
    for role in ROLES:
        stored = get_role_config(role)
        key = stored.get("api_key", "")
        result["configs"][role] = {
            "base_url": stored.get("base_url", ""),
            "model": stored.get("model", ""),
            "adapter": stored.get("adapter", "auto"),
            "resolved_adapter": detect_adapter(stored.get("base_url", ""), stored.get("model", ""), stored.get("adapter", "auto")) if stored.get("base_url") else "",
            "model_family": model_family(stored.get("model", "")),
            "configured": bool(key and stored.get("base_url") and stored.get("model")),
            "api_key_hint": f"••••{key[-4:]}" if key else "",
            "verified": bool(stored.get("verified")),
            "capabilities": stored.get("capabilities", {}),
            "verified_at": stored.get("verified_at"),
        }
    return result


def validate_role_config(role: str, model: str, base_url: str, adapter: str = "auto") -> None:
    validate_gateway_config(GatewayConfig(role, base_url, model, "", adapter))


# Compatibility helpers used by the existing conversation runtime and tests.
def active_profile(role: str = "chat") -> tuple[str, dict[str, Any]]:
    stored = get_role_config(role)
    adapter = detect_adapter(stored.get("base_url", ""), stored.get("model", ""), stored.get("adapter", "auto")) if stored.get("base_url") else "openai_chat"
    return adapter, {
        "api_key": stored.get("api_key", ""), "model": stored.get("model", ""),
        "base_url": stored.get("base_url", ""), "temperature": None,
    }


def temperature_supported(provider: str, model: str) -> bool:
    return gateway_temperature_supported(model)


def role_temperature(provider: str, model: str, requested: float | None) -> float | None:
    return resolve_temperature(model, requested)


def public_registry() -> list[dict[str, Any]]:
    return []


def validate_profile(provider: str, model: str, base_url: str, temperature: float | None = None) -> None:
    validate_role_config("chat", model, base_url, provider if provider in ADAPTERS else "auto")


def save_profile(provider: str, profile: dict[str, Any]) -> dict[str, Any]:
    profile = {**profile, "adapter": provider if provider in ADAPTERS else "auto"}
    return save_role_config("chat", profile)
