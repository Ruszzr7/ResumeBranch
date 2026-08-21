"""Launch the backend with the native Windows multi-user MySQL profile."""

from __future__ import annotations

import os
from pathlib import Path
import runpy
import sys
from urllib.parse import quote_plus

from dotenv import dotenv_values


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env.multi_user"


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} must be configured in {ENV_FILE.name}")
    return value


def _map_container_path(name: str) -> None:
    """Map legacy /app paths from the Compose profile to this checkout."""
    value = os.environ.get(name, "").strip()
    if value == "/app":
        os.environ[name] = str(PROJECT_ROOT)
    elif value.startswith("/app/"):
        os.environ[name] = str(PROJECT_ROOT / value.removeprefix("/app/"))


if not ENV_FILE.exists():
    raise RuntimeError(f"Missing {ENV_FILE}. Copy .env.multi_user.example first.")

for key, value in dotenv_values(ENV_FILE).items():
    if value is not None:
        os.environ[key] = value

os.environ["APP_MODE"] = "multi_user"
os.environ["HOST"] = "127.0.0.1"

if not os.environ.get("DATABASE_URL", "").strip():
    mysql_user = quote_plus(_required("MYSQL_USER"))
    mysql_password = quote_plus(_required("MYSQL_PASSWORD"))
    mysql_database = quote_plus(_required("MYSQL_DATABASE"))
    mysql_host = os.environ.get("MYSQL_HOST", "127.0.0.1").strip() or "127.0.0.1"
    mysql_port = os.environ.get("MYSQL_PORT", "3306").strip() or "3306"
    if not mysql_port.isdigit():
        raise RuntimeError("MYSQL_PORT must be a number")
    os.environ["DATABASE_URL"] = (
        f"mysql+pymysql://{mysql_user}:{mysql_password}"
        f"@{mysql_host}:{mysql_port}/{mysql_database}?charset=utf8mb4"
    )

for path_setting in (
    "LLM_PROFILE_PATH",
    "SOURCE_DOCUMENT_DIR",
    "AGENT_CHECKPOINT_DB_PATH",
    "LOCAL_EXPORT_DIR",
):
    _map_container_path(path_setting)

os.chdir(PROJECT_ROOT)
sys.path.insert(0, str(PROJECT_ROOT))

if "--check" in sys.argv:
    from sqlalchemy import create_engine, text

    try:
        check_engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
        with check_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        check_engine.dispose()
    except Exception as exc:
        raise SystemExit(f"MySQL connection check failed: {exc}") from None
    print("MySQL connection check passed.")
    raise SystemExit(0)

runpy.run_module("backend.main", run_name="__main__")
