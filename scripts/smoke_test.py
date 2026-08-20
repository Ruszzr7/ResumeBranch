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
        ProjectTask,
        Resume,
        ResumeProject,
        SessionLocal,
        User,
    )

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if user:
            db.query(ProjectTask).filter(ProjectTask.user_id == user.id).delete()
            db.query(ResumeProject).filter(ResumeProject.user_id == user.id).delete()
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
    project_response = client.post(
        f"{API_URL}/projects",
        json={"title": "Smoke Resume Project"},
        headers=headers,
    )
    require(project_response, 200, "create resume project")
    project = project_response.json()
    base_headers = {**headers, "X-Task-ID": project["base_task_id"]}

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
        headers=base_headers,
    )
    require(saved, 200, "save resume")

    loaded = client.post(f"{API_URL}/load_resume", headers=base_headers)
    require(loaded, 200, "load resume")
    if loaded.json().get("basics", {}).get("name") != "Local Smoke Test":
        raise RuntimeError("resume did not round-trip through the configured database")

    task_response = client.post(
        f"{API_URL}/projects/{project['id']}/tasks",
        json={"title": "Local Test JD"},
        headers=headers,
    )
    require(task_response, 200, "create JD task")
    task_headers = {**headers, "X-Task-ID": task_response.json()["id"]}
    cloned = client.post(f"{API_URL}/load_resume", headers=task_headers)
    require(cloned, 200, "clone base resume into JD task")
    if cloned.json().get("basics", {}).get("name") != "Local Smoke Test":
        raise RuntimeError("JD task did not inherit the project's base resume")

    blank_task_response = client.post(
        f"{API_URL}/projects/{project['id']}/tasks",
        json={"title": "Blank JD", "copy_base_resume": False},
        headers=headers,
    )
    require(blank_task_response, 200, "create blank JD task")
    blank_task_headers = {
        **headers,
        "X-Task-ID": blank_task_response.json()["id"],
    }
    blank_resume = client.post(f"{API_URL}/load_resume", headers=blank_task_headers)
    require(blank_resume, 200, "load blank JD task")
    if blank_resume.json().get("basics", {}).get("name"):
        raise RuntimeError("blank JD task unexpectedly inherited the base resume")

    exported_pdf = client.post(
        f"{API_URL}/export_pdf",
        json={"lang": "zh", "style": {}},
        headers=task_headers,
    )
    require(exported_pdf, 200, "export PDF")
    if not exported_pdf.content.startswith(b"%PDF"):
        raise RuntimeError("exported content is not a PDF")

    saved_jd = client.post(
        f"{API_URL}/save_jd",
        json={"jd_data": {"company": "Local Test", "position": "Engineer"}},
        headers=task_headers,
    )
    require(saved_jd, 200, "save JD")
    loaded_jd = client.post(f"{API_URL}/load_jd", headers=task_headers)
    require(loaded_jd, 200, "load JD")
    if loaded_jd.json().get("company") != "Local Test":
        raise RuntimeError("JD did not round-trip through the configured database")

    llm_response = client.post(
        f"{API_URL}/chat",
        data={
            "message": "Reply briefly that the smoke test connection works.",
            "session_id": "smoke-test",
        },
        headers=task_headers,
    )
    if os.getenv("LLM_API_KEY", "").strip():
        require(llm_response, 200, "configured LLM")
        if '"type": "end"' not in llm_response.text:
            raise RuntimeError("configured LLM response did not complete its SSE stream")
    else:
        require(llm_response, 503, "disabled LLM guard")


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
    if not admin_login.json().get("user", {}).get("is_admin"):
        raise RuntimeError("configured administrator does not have server-side admin permission")
    admin_headers = {
        "Authorization": f"Bearer {admin_login.json()['access_token']}"
    }

    invite = client.post(
        f"{API_URL}/auth/invite-codes",
        json={"count": 1},
        headers=admin_headers,
    )
    require(invite, 200, "create invite")
    invite_payload = invite.json()
    invite_code = (
        invite_payload[0]["code"]
        if isinstance(invite_payload, list)
        else invite_payload["code"]
    )

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
                settings = client.get(f"{API_URL}/settings/llm")
                require(settings, 200, "read local LLM settings")
                settings_data = settings.json()
                if "api_key" in settings_data:
                    raise RuntimeError("LLM settings endpoint exposed the API key")
                save_settings = client.put(
                    f"{API_URL}/settings/llm",
                    json={
                        "provider": settings_data.get("provider", "moonshot"),
                        "model": settings_data.get("model", ""),
                        "base_url": settings_data.get("base_url", ""),
                        "api_key": None,
                    },
                )
                require(save_settings, 200, "save local LLM settings")
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
