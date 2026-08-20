"""Runtime profile and security-sensitive application configuration."""

import os

from dotenv import load_dotenv


load_dotenv()


SUPPORTED_APP_MODES = {"local", "multi_user"}
APP_MODE = os.getenv("APP_MODE", "local").strip().lower()
LOCAL_USER_EMAIL = os.getenv("LOCAL_USER_EMAIL", "local@localhost").strip().lower()
SERVER_HOST = os.getenv("HOST", "127.0.0.1").strip()
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "").strip()
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", str(60 * 24))
)


def _configured_cors_origins() -> list[str]:
    raw = os.getenv("CORS_ALLOW_ORIGINS", "").strip()
    if raw:
        return [origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()]
    if APP_MODE == "local":
        return ["http://127.0.0.1:5173", "http://localhost:5173"]
    # The multi-user Docker profile is same-origin behind Nginx, so CORS is
    # disabled unless an operator explicitly allows additional frontends.
    return []


CORS_ALLOW_ORIGINS = _configured_cors_origins()

if APP_MODE not in SUPPORTED_APP_MODES:
    supported = ", ".join(sorted(SUPPORTED_APP_MODES))
    raise RuntimeError(f"APP_MODE must be one of: {supported}")

if not LOCAL_USER_EMAIL:
    raise RuntimeError("LOCAL_USER_EMAIL cannot be empty")

if JWT_ACCESS_TOKEN_EXPIRE_MINUTES <= 0:
    raise RuntimeError("JWT_ACCESS_TOKEN_EXPIRE_MINUTES must be positive")

if APP_MODE == "local" and SERVER_HOST not in {"127.0.0.1", "localhost", "::1"}:
    raise RuntimeError("Local mode must bind HOST to 127.0.0.1, localhost, or ::1")

if APP_MODE == "multi_user":
    insecure_secrets = {
        "",
        "your-super-secret-key-change-this-in-production",
        "replace-with-a-long-random-secret",
        "replace-with-at-least-32-random-characters",
    }
    if JWT_SECRET_KEY in insecure_secrets or len(JWT_SECRET_KEY) < 32:
        raise RuntimeError(
            "multi_user mode requires JWT_SECRET_KEY with at least 32 characters"
        )


def is_local_mode() -> bool:
    """Return whether authentication-free local mode is enabled."""
    return APP_MODE == "local"
