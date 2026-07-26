"""Repeatable local smoke test for frontend, API, auth, MySQL, and disabled LLM."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import httpx
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

API_URL = "http://127.0.0.1:8000"
FRONTEND_URL = "http://127.0.0.1:5173"


def require(response: httpx.Response, expected: int, label: str) -> None:
    if response.status_code != expected:
        raise RuntimeError(
            f"{label}: expected HTTP {expected}, got {response.status_code}: "
            f"{response.text[:300]}"
        )
    print(f"PASS {label}: HTTP {response.status_code}")


def cleanup_test_data(email: str, invite_code: str | None) -> None:
    from backend.database import (
        Conversation,
        InviteCode,
        JobDescription,
        Resume,
        SessionLocal,
        User,
    )

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if user:
            db.query(Conversation).filter(Conversation.user_id == user.id).delete()
            db.query(JobDescription).filter(JobDescription.user_id == user.id).delete()
            db.query(Resume).filter(Resume.user_id == user.id).delete()
            db.delete(user)
        if invite_code:
            db.query(InviteCode).filter(InviteCode.code == invite_code).delete()
        db.commit()
    finally:
        db.close()


def main() -> None:
    admin_email = os.getenv("ADMIN_EMAIL", "")
    admin_password = os.getenv("ADMIN_PASSWORD", "")
    if not admin_email or not admin_password:
        raise RuntimeError("ADMIN_EMAIL/ADMIN_PASSWORD are not configured")

    test_email = f"smoke-{uuid.uuid4().hex}@local.test"
    test_password = uuid.uuid4().hex
    invite_code = None

    try:
        with httpx.Client(timeout=20.0) as client:
            require(client.get(FRONTEND_URL), 200, "frontend")
            health = client.post(f"{API_URL}/health")
            require(health, 200, "health")
            if health.json().get("status") != "ok":
                raise RuntimeError("health response did not report status=ok")

            admin_login = client.post(
                f"{API_URL}/auth/login",
                data={"username": admin_email, "password": admin_password},
            )
            require(admin_login, 200, "admin login")
            admin_headers = {
                "Authorization": f"Bearer {admin_login.json()['access_token']}"
            }

            invite = client.post(
                f"{API_URL}/auth/invite-codes",
                json={"count": 1},
                headers=admin_headers,
            )
            require(invite, 200, "create invite")
            invite_code = invite.json()["code"]

            register = client.post(
                f"{API_URL}/auth/register",
                json={
                    "email": test_email,
                    "password": test_password,
                    "invite_code": invite_code,
                },
            )
            require(register, 200, "register")
            user_headers = {
                "Authorization": f"Bearer {register.json()['access_token']}"
            }

            me = client.get(f"{API_URL}/auth/me", headers=user_headers)
            require(me, 200, "current user")
            if me.json().get("email") != test_email:
                raise RuntimeError("authenticated user did not match test user")

            resume_data = {
                "basics": {
                    "name": "Local Smoke Test",
                    "email": test_email,
                    "target_position": "Backend Engineer",
                },
                "education": [],
                "work_experience": [],
                "project_experience": [],
                "others": {"skills": ["Python", "MySQL"]},
                "self_evaluation": [],
            }
            saved = client.post(
                f"{API_URL}/save_resume",
                json={"resume_data": resume_data},
                headers=user_headers,
            )
            require(saved, 200, "save resume")

            loaded = client.post(f"{API_URL}/load_resume", headers=user_headers)
            require(loaded, 200, "load resume")
            if loaded.json().get("basics", {}).get("name") != "Local Smoke Test":
                raise RuntimeError("resume did not round-trip through MySQL")

            exported_pdf = client.post(
                f"{API_URL}/export_pdf",
                json={"lang": "zh", "style": {}},
                headers=user_headers,
            )
            require(exported_pdf, 200, "export PDF")
            if not exported_pdf.content.startswith(b"%PDF"):
                raise RuntimeError("exported content is not a PDF")

            saved_jd = client.post(
                f"{API_URL}/save_jd",
                json={"jd_data": {"company": "Local Test", "position": "Engineer"}},
                headers=user_headers,
            )
            require(saved_jd, 200, "save JD")
            loaded_jd = client.post(f"{API_URL}/load_jd", headers=user_headers)
            require(loaded_jd, 200, "load JD")
            if loaded_jd.json().get("company") != "Local Test":
                raise RuntimeError("JD did not round-trip through MySQL")

            llm_disabled = client.post(
                f"{API_URL}/chat",
                data={"message": "hello", "session_id": "smoke-test"},
                headers=user_headers,
            )
            require(llm_disabled, 503, "disabled LLM guard")
    finally:
        cleanup_test_data(test_email, invite_code)

    print("SMOKE_TEST_OK")


if __name__ == "__main__":
    main()
