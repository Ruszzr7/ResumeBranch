"""Isolated regression tests for local and multi-user runtime profiles."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RuntimeProfileTests(unittest.TestCase):
    def run_python(self, source: str, **environment: str) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env.update(environment)
        env["PYTHONIOENCODING"] = "utf-8"
        return subprocess.run(
            [sys.executable, "-c", textwrap.dedent(source)],
            cwd=ROOT,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=30,
            check=False,
        )

    def test_local_profile_needs_no_jwt_secret(self):
        result = self.run_python(
            """
            from backend.config import APP_MODE, CORS_ALLOW_ORIGINS
            assert APP_MODE == "local"
            assert "http://127.0.0.1:5173" in CORS_ALLOW_ORIGINS
            """,
            APP_MODE="local",
            HOST="127.0.0.1",
            JWT_SECRET_KEY="",
            CORS_ALLOW_ORIGINS="",
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_multi_user_profile_rejects_missing_jwt_secret(self):
        result = self.run_python(
            "from backend.config import APP_MODE",
            APP_MODE="multi_user",
            HOST="0.0.0.0",
            JWT_SECRET_KEY="",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires JWT_SECRET_KEY", result.stderr)

    def test_sqlite_persists_and_invite_registration_is_atomic(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            database_path = Path(temporary_dir) / "nested" / "profile.db"
            database_url = f"sqlite:///{database_path.as_posix()}"
            source = """
                from backend.auth import get_password_hash
                from backend.database import (
                    InviteCode, SessionLocal, User, engine, init_db,
                    register_user_with_invite,
                )

                init_db()
                db = SessionLocal()
                db.add(InviteCode(code="PROFILE01"))
                db.commit()
                user = register_user_with_invite(
                    db, "User@Example.com", get_password_hash("password-123"), "PROFILE01"
                )
                user_id = user.id
                db.close()
                engine.dispose()

                db = SessionLocal()
                saved = db.query(User).filter(User.id == user_id).one()
                invite = db.query(InviteCode).filter(InviteCode.code == "PROFILE01").one()
                assert saved.email == "user@example.com"
                assert invite.is_used is True
                try:
                    register_user_with_invite(
                        db, "second@example.com", get_password_hash("password-456"), "PROFILE01"
                    )
                except ValueError:
                    pass
                else:
                    raise AssertionError("a consumed invite was accepted")
                assert db.query(User).filter(User.email == "second@example.com").count() == 0
                db.close()
            """
            result = self.run_python(
                source,
                APP_MODE="local",
                HOST="127.0.0.1",
                JWT_SECRET_KEY="",
                DATABASE_URL=database_url,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(database_path.exists())

    def test_local_api_disables_accounts_and_keeps_collision_safe_exports(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            result = self.run_python(
                """
                from fastapi.testclient import TestClient
                import os
                from pathlib import Path
                from unittest.mock import patch
                from backend.main import app, _persist_local_export, _resume_export_filename

                with TestClient(app) as client:
                    config = client.get("/app/config")
                    assert config.status_code == 200
                    assert config.json()["app_mode"] == "local"
                    assert config.json()["database_backend"] == "sqlite"
                    assert client.post(
                        "/auth/login", data={"username": "x@example.com", "password": "unused"}
                    ).status_code == 404
                    current = client.get("/auth/me")
                    assert current.status_code == 200
                    assert current.json()["email"] == "local@localhost"
                    with patch("backend.main._open_local_export_directory") as open_directory:
                        opened = client.post("/local/exports/open")
                    assert opened.status_code == 200, opened.text
                    export_directory = Path(os.environ["LOCAL_EXPORT_DIR"]).resolve()
                    assert Path(opened.json()["path"]) == export_directory
                    open_directory.assert_called_once_with(export_directory)

                filename = _resume_export_filename(
                    {"basics": {"name": "候选人"}}, "pdf", "后端/AI 简历", "岗位:一", None
                )
                assert filename.startswith("后端_AI 简历_岗位_一_")
                first = _persist_local_export(b"first", filename)
                second = _persist_local_export(b"second", filename)
                assert first.exists() and second.exists()
                assert second.stem.endswith("_01")
                assert first.read_bytes() == b"first"
                assert second.read_bytes() == b"second"
                """,
                APP_MODE="local",
                HOST="127.0.0.1",
                JWT_SECRET_KEY="",
                DATABASE_URL=f"sqlite:///{(root / 'local.db').as_posix()}",
                LOCAL_EXPORT_DIR=str(root / "exports"),
                LLM_API_KEY="",
                LLM_PROFILE_PATH=str(root / "llm_profiles.json"),
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_multi_user_api_enforces_admin_and_user_isolation(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            result = self.run_python(
                """
                from fastapi.testclient import TestClient
                from backend.auth import get_password_hash
                from backend.database import SessionLocal, create_user
                from backend.main import app

                db = SessionLocal()
                create_user(
                    db,
                    "admin@example.com",
                    get_password_hash("admin-password"),
                    "admin",
                    is_admin=True,
                )
                create_user(
                    db,
                    "Ruszzr",
                    get_password_hash("admin-alias-password"),
                    "admin",
                    is_admin=True,
                )
                create_user(
                    db,
                    "legacy-user",
                    get_password_hash("legacy-user-password"),
                    "legacy",
                    is_admin=False,
                )
                db.close()

                with TestClient(app) as client:
                    login = client.post(
                        "/auth/login",
                        data={"username": "ADMIN@example.com", "password": "admin-password"},
                    )
                    assert login.status_code == 200, login.text
                    assert login.json()["user"]["is_admin"] is True
                    admin_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

                    admin_alias_login = client.post(
                        "/auth/login",
                        data={"username": "RUSZZR", "password": "admin-alias-password"},
                    )
                    assert admin_alias_login.status_code == 200, admin_alias_login.text
                    assert admin_alias_login.json()["user"]["is_admin"] is True
                    ordinary_alias_login = client.post(
                        "/auth/login",
                        data={"username": "legacy-user", "password": "legacy-user-password"},
                    )
                    assert ordinary_alias_login.status_code == 401

                    invite = client.post(
                        "/auth/invite-codes", json={"count": 1}, headers=admin_headers
                    )
                    assert invite.status_code == 200, invite.text
                    code = invite.json()["code"]
                    invalid_registration = client.post(
                        "/auth/register",
                        json={
                            "email": "ordinary-user",
                            "password": "user-password",
                            "invite_code": code,
                        },
                    )
                    assert invalid_registration.status_code == 400
                    assert "邮箱格式" in invalid_registration.text
                    registration = client.post(
                        "/auth/register",
                        json={
                            "email": "USER@example.com",
                            "password": "user-password",
                            "invite_code": code,
                        },
                    )
                    assert registration.status_code == 200, registration.text
                    assert registration.json()["user"]["email"] == "user@example.com"
                    assert registration.json()["user"]["is_admin"] is False
                    user_headers = {
                        "Authorization": f"Bearer {registration.json()['access_token']}"
                    }
                    second_login = client.post(
                        "/auth/login",
                        data={"username": "user@example.com", "password": "user-password"},
                    )
                    assert second_login.status_code == 200, second_login.text
                    assert client.get("/auth/me", headers=user_headers).status_code == 401
                    user_headers = {
                        "Authorization": f"Bearer {second_login.json()['access_token']}"
                    }
                    assert client.get(
                        "/auth/invite-codes", headers=user_headers
                    ).status_code == 403
                    assert client.post(
                        "/local/exports/open", headers=user_headers
                    ).status_code == 404
                    assert client.get(
                        "/settings/llm", headers=user_headers
                    ).status_code == 403
                    admin_settings = client.get(
                        "/settings/llm", headers=admin_headers
                    )
                    assert admin_settings.status_code == 200, admin_settings.text
                    assert "configs" in admin_settings.json()

                    admin_project = client.post(
                        "/projects", json={"title": "管理员简历"}, headers=admin_headers
                    )
                    user_project = client.post(
                        "/projects", json={"title": "用户简历"}, headers=user_headers
                    )
                    assert admin_project.status_code == 200, admin_project.text
                    assert user_project.status_code == 200, user_project.text
                    admin_titles = {
                        item["title"] for item in client.get("/projects", headers=admin_headers).json()
                    }
                    user_titles = {
                        item["title"] for item in client.get("/projects", headers=user_headers).json()
                    }
                    assert "管理员简历" in admin_titles and "用户简历" not in admin_titles
                    assert "用户简历" in user_titles and "管理员简历" not in user_titles
                    assert client.post("/auth/logout", headers=user_headers).status_code == 200
                    assert client.get("/auth/me", headers=user_headers).status_code == 401
                """,
                APP_MODE="multi_user",
                HOST="0.0.0.0",
                JWT_SECRET_KEY="test-secret-that-is-longer-than-thirty-two-characters",
                DATABASE_URL=f"sqlite:///{(root / 'multi.db').as_posix()}",
                LLM_API_KEY="",
                LLM_PROFILE_PATH=str(root / "llm_profiles.json"),
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_pdf_and_agent_dependencies_match_the_runtime_contract(self):
        requirements = (ROOT / "backend" / "requirements.txt").read_text(encoding="utf-8").lower()
        lock = (ROOT / "backend" / "requirements.lock.txt").read_text(encoding="utf-8").lower()
        dockerfile = (ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8").lower()

        self.assertNotIn("weasyprint", requirements)
        self.assertNotIn("weasyprint", lock)
        self.assertIn("chromium", dockerfile)
        self.assertIn("resume_pdf_no_sandbox=true", dockerfile)
        self.assertIn("poppler-utils", dockerfile)
        self.assertIn("requirements.lock.txt", dockerfile)
        self.assertNotIn("-r backend/requirements.txt", dockerfile)
        self.assertNotIn("langchain-tavily", requirements)
        self.assertNotIn("langchain-tavily", lock)
        self.assertNotRegex(lock, r"(?m)^langchain==")

    def test_docker_multi_user_profile_isolated_from_local_runtime_data(self):
        compose = (ROOT / "docker-compose.multi-user.yml").read_text(encoding="utf-8")
        dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
        docker_env = (ROOT / ".env.docker.example").read_text(encoding="utf-8")
        workflow = (ROOT / ".github" / "workflows" / "docker-multi-user.yml").read_text(
            encoding="utf-8"
        )
        nginx = (ROOT / "frontend" / "nginx.conf").read_text(encoding="utf-8")

        self.assertIn("${MULTI_USER_ENV_FILE:-.env.docker}", compose)
        self.assertIn("APP_MODE: multi_user", compose)
        self.assertIn(
            "DATABASE_URL: mysql+pymysql://${MYSQL_USER}:${MYSQL_PASSWORD}@mysql:3306/${MYSQL_DATABASE}?charset=utf8mb4",
            compose,
        )
        self.assertIn('"8080:80"', compose)
        self.assertNotIn('"3306:3306"', compose)
        self.assertNotIn('"8000:8000"', compose)
        self.assertNotIn("container_name:", compose)
        self.assertIn(".env*", dockerignore)
        self.assertIn("data/", dockerignore)
        self.assertIn("output/", dockerignore)
        self.assertIn("MYSQL_ROOT_PASSWORD=", docker_env)
        self.assertIn("docker compose", workflow)
        self.assertIn("/auth/login", workflow)
        self.assertIn("/auth/register", workflow)
        self.assertIn('skill_runtime.invoke("resume-snapshot"', workflow)
        self.assertIn("pdftoppm -v", workflow)
        self.assertIn("location ^~ /tasks/", nginx)
        self.assertIn("settings/llm(?:/.*)?", nginx)
        self.assertIn("proxy_buffering off", nginx)
        self.assertIn('"${compose[@]}" down', workflow)
        self.assertIn("down -v --remove-orphans", workflow)

    def test_windows_launchers_keep_frontend_shared_and_backend_profile_specific(self):
        scripts = ROOT / "scripts"
        start_local = (scripts / "start_local.cmd").read_text(encoding="utf-8")
        start_multi = (scripts / "start_multi_user.cmd").read_text(encoding="utf-8")
        backend = (scripts / "start_backend_local.cmd").read_text(encoding="utf-8")
        multi_runner = (scripts / "run_multi_user_backend.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("start_frontend.cmd", start_local)
        self.assertIn("start_frontend.cmd", start_multi)
        self.assertIn("start_mysql.cmd", start_multi)
        self.assertIn("start_backend_multi_user.cmd\" --restart", start_multi)
        self.assertIn('set "RESTART=1"', backend)
        self.assertIn("EXPECTED_APP_MODE=local", backend)
        self.assertIn("EXPECTED_APP_MODE=multi_user", backend)
        self.assertIn("EXPECTED_DATABASE=sqlite", backend)
        self.assertIn("EXPECTED_DATABASE=mysql", backend)
        self.assertIn('ENV_FILE = PROJECT_ROOT / ".env.multi_user"', multi_runner)
        self.assertIn('os.environ["APP_MODE"] = "multi_user"', multi_runner)
        self.assertIn('os.environ["HOST"] = "127.0.0.1"', multi_runner)
        self.assertIn("quote_plus(_required(\"MYSQL_PASSWORD\"))", multi_runner)
        self.assertIn('if "--check" in sys.argv:', multi_runner)
        self.assertIn("Checking MySQL application credentials", backend)
        self.assertLess(
            backend.index("Checking MySQL application credentials"),
            backend.index('if "%RESTART%"=="1"'),
        )


if __name__ == "__main__":
    unittest.main()
