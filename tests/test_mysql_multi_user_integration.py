"""Opt-in integration coverage for the real MySQL multi-user profile."""

from __future__ import annotations

import os
from pathlib import Path
import unittest
import uuid

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(
    os.getenv("RUN_MYSQL_INTEGRATION") == "1",
    "set RUN_MYSQL_INTEGRATION=1 to use the configured MySQL test database",
)
class MySQLMultiUserIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        load_dotenv(ROOT / ".env")
        from backend.database import database_backend

        if database_backend != "mysql":
            raise unittest.SkipTest("configured DATABASE_URL is not MySQL")

    def test_admin_registration_and_user_isolation(self):
        from fastapi.testclient import TestClient
        from backend.auth import get_password_hash
        from backend.database import (
            InviteCode,
            SessionLocal,
            User,
            create_user,
            delete_resume_project,
            list_resume_projects,
        )
        from backend.main import app

        marker = uuid.uuid4().hex
        admin_email = f"integration-admin-{marker}@example.test"
        user_email = f"integration-user-{marker}@example.test"
        password = f"test-{marker}"
        invite_code = None
        admin_headers = {}
        user_headers = {}

        db = SessionLocal()
        try:
            create_user(
                db,
                admin_email,
                get_password_hash(password),
                "integration-admin",
                is_admin=True,
            )
        finally:
            db.close()

        try:
            with TestClient(app) as client:
                admin_login = client.post(
                    "/auth/login",
                    data={"username": admin_email.upper(), "password": password},
                )
                self.assertEqual(admin_login.status_code, 200, admin_login.text)
                self.assertTrue(admin_login.json()["user"]["is_admin"])
                admin_headers = {
                    "Authorization": f"Bearer {admin_login.json()['access_token']}"
                }

                invite = client.post(
                    "/auth/invite-codes", json={"count": 1}, headers=admin_headers
                )
                self.assertEqual(invite.status_code, 200, invite.text)
                invite_code = invite.json()["code"]

                registration = client.post(
                    "/auth/register",
                    json={
                        "email": user_email.upper(),
                        "password": password,
                        "invite_code": invite_code,
                    },
                )
                self.assertEqual(registration.status_code, 200, registration.text)
                self.assertFalse(registration.json()["user"]["is_admin"])
                user_headers = {
                    "Authorization": f"Bearer {registration.json()['access_token']}"
                }
                self.assertEqual(
                    client.get("/auth/invite-codes", headers=user_headers).status_code,
                    403,
                )

                admin_title = f"admin-{marker}"
                user_title = f"user-{marker}"
                self.assertEqual(
                    client.post(
                        "/projects", json={"title": admin_title}, headers=admin_headers
                    ).status_code,
                    200,
                )
                self.assertEqual(
                    client.post(
                        "/projects", json={"title": user_title}, headers=user_headers
                    ).status_code,
                    200,
                )
                admin_titles = {
                    item["title"] for item in client.get("/projects", headers=admin_headers).json()
                }
                user_titles = {
                    item["title"] for item in client.get("/projects", headers=user_headers).json()
                }
                self.assertIn(admin_title, admin_titles)
                self.assertNotIn(user_title, admin_titles)
                self.assertIn(user_title, user_titles)
                self.assertNotIn(admin_title, user_titles)
        finally:
            db = SessionLocal()
            try:
                users = db.query(User).filter(User.email.in_([admin_email, user_email])).all()
                for user in users:
                    for project in list_resume_projects(db, user.id):
                        if marker in str(project.title or ""):
                            delete_resume_project(db, user.id, project.id)
                db.query(User).filter(User.email.in_([admin_email, user_email])).delete(
                    synchronize_session=False
                )
                if invite_code:
                    db.query(InviteCode).filter(InviteCode.code == invite_code).delete()
                db.commit()
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
