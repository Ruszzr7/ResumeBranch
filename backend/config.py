"""Application mode and local-user configuration."""

import os


SUPPORTED_APP_MODES = {"local", "multi_user"}
APP_MODE = os.getenv("APP_MODE", "multi_user").strip().lower()
LOCAL_USER_EMAIL = os.getenv("LOCAL_USER_EMAIL", "local@localhost").strip().lower()

if APP_MODE not in SUPPORTED_APP_MODES:
    supported = ", ".join(sorted(SUPPORTED_APP_MODES))
    raise RuntimeError(f"APP_MODE must be one of: {supported}")

if not LOCAL_USER_EMAIL:
    raise RuntimeError("LOCAL_USER_EMAIL cannot be empty")


def is_local_mode() -> bool:
    """Return whether authentication-free local mode is enabled."""
    return APP_MODE == "local"
