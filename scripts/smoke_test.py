"""Repeatable smoke test for local and multi-user application modes."""

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


def exercise_business_endpoints(
    client: httpx.Client, headers: dict[str, str], test_email: str
) -> None:
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
        headers=headers,
    )
    require(saved, 200, "save resume")

    loaded = client.post(f"{API_URL}/load_resume", headers=headers)
    require(loaded, 200, "load resume")
    if loaded.json().get("basics", {}).get("name") != "Local Smoke Test":
        raise RuntimeError("resume did not round-trip through MySQL")

    exported_pdf = client.post(
        f"{API_URL}/export_pdf",
        json={"lang": "zh", "style": {}},
        headers=headers,
    )
    require(exported_pdf, 200, "export PDF")
    if not exported_pdf.content.startswith(b"%PDF"):
        raise RuntimeError("exported content is not a PDF")

    saved_jd = client.post(
        f"{API_URL}/save_jd",
        json={"jd_data": {"company": "Local Test", "position": "Engineer"}},
        headers=headers,
    )
    require(saved_jd, 200, "save JD")
    loaded_jd = client.post(f"{API_URL}/load_jd", headers=headers)
    require(loaded_jd, 200, "load JD")
    if loaded_jd.json().get("company") != "Local Test":
        raise RuntimeError("JD did not round-trip through MySQL")

    llm_disabled = client.post(
        f"{API_URL}/chat",
        data={"message": "hello", "session_id": "smoke-test"},
        headers=headers,
    )
    require(llm_disabled, 503, "disabled LLM guard")


def authenticate_multi_user(
    client: httpx.Client, test_email: str, test_password: str
) -> tuple[dict[str, str], str]:
    admin_email = os.getenv("ADMIN_EMAIL", "")
    admin_password = os.getenv("ADMIN_PASSWORD", "")
    if not admin_email or not admin_password:
        raise RuntimeError("ADMIN_EMAIL/ADMIN_PASSWORD are not configured")

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
    return (
        {"Authorization": f"Bearer {register.json()['access_token']}"},
        invite_code,
    )


def verify_local_auth_is_disabled(client: httpx.Client) -> None:
    require(
        client.post(
            f"{API_URL}/auth/login",
            data={"username": "nobody@local.test", "password": "unused"},
        ),
        404,
        "local login disabled",
    )
    require(
        client.post(
            f"{API_URL}/auth/register",
            json={
                "email": "nobody@local.test",
                "password": "unused-password",
                "invite_code": "unused",
            },
        ),
        404,
        "local registration disabled",
    )
    require(
        client.get(f"{API_URL}/auth/invite-codes"),
        404,
        "local invite management disabled",
    )


def main() -> None:
    generated_email = f"smoke-{uuid.uuid4().hex}@local.test"
    test_email = generated_email
    test_password = uuid.uuid4().hex
    invite_code: str | None = None
    cleanup_email: str | None = generated_email

    try:
        with httpx.Client(timeout=20.0) as client:
            require(client.get(FRONTEND_URL), 200, "frontend")
            app_config = client.get(f"{API_URL}/app/config")
            require(app_config, 200, "app config")
            app_mode = app_config.json().get("app_mode")
            if app_mode not in {"local", "multi_user"}:
                raise RuntimeError(f"unexpected app mode: {app_mode!r}")

            health = client.post(f"{API_URL}/health")
            require(health, 200, "health")
            if health.json().get("status") != "ok":
                raise RuntimeError("health response did not report status=ok")
            if health.json().get("app_mode") != app_mode:
                raise RuntimeError("health and app config report different modes")

            if app_mode == "local":
                test_email = app_config.json().get("local_user_email", "")
                cleanup_email = None
                if not (
                    test_email.startswith("smoke-")
                    and test_email.endswith("@local.test")
                ):
                    raise RuntimeError(
                        "Local-mode smoke tests write and delete data. Start the "
                        "backend with a temporary smoke-*@local.test "
                        "LOCAL_USER_EMAIL."
                    )
                cleanup_email = test_email
                user_headers: dict[str, str] = {}
                verify_local_auth_is_disabled(client)
            else:
                user_headers, invite_code = authenticate_multi_user(
                    client, test_email, test_password
                )

            me = client.get(f"{API_URL}/auth/me", headers=user_headers)
            require(me, 200, "current user")
            if me.json().get("email") != test_email:
                raise RuntimeError("authenticated user did not match test user")
            exercise_business_endpoints(client, user_headers, test_email)
    finally:
        if cleanup_email:
            cleanup_test_data(cleanup_email, invite_code)

    print("SMOKE_TEST_OK")


if __name__ == "__main__":
    main()
