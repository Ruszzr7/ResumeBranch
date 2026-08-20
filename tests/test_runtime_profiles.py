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
                AGENT_CHECKPOINTER_ENABLED="false",
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
                db.close()

                with TestClient(app) as client:
                    login = client.post(
                        "/auth/login",
                        data={"username": "ADMIN@example.com", "password": "admin-password"},
                    )
                    assert login.status_code == 200, login.text
                    assert login.json()["user"]["is_admin"] is True
                    admin_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

                    invite = client.post(
                        "/auth/invite-codes", json={"count": 1}, headers=admin_headers
                    )
                    assert invite.status_code == 200, invite.text
                    code = invite.json()["code"]
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
                    assert client.get(
                        "/auth/invite-codes", headers=user_headers
                    ).status_code == 403

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
                """,
                APP_MODE="multi_user",
                HOST="0.0.0.0",
                JWT_SECRET_KEY="test-secret-that-is-longer-than-thirty-two-characters",
                DATABASE_URL=f"sqlite:///{(root / 'multi.db').as_posix()}",
                AGENT_CHECKPOINTER_ENABLED="false",
                LLM_API_KEY="",
                LLM_PROFILE_PATH=str(root / "llm_profiles.json"),
            )
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
