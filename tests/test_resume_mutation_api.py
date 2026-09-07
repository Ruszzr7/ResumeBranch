from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend import main
from backend.auth import ensure_local_user
from backend.database import (
    Base,
    Conversation,
    ProjectTask,
    ResumeProject,
    ResumeRevision,
    acquire_resume_edit_lock,
    get_resume_task,
    release_resume_edit_lock,
)
from backend.layout_config import default_layout_config
from backend.resume_schema import ensure_resume_identity, validate_resume_data


def resume_payload(name: str = "A") -> dict:
    return ensure_resume_identity(validate_resume_data({
        "basics": {
            "name": name,
            "phone": "13800138000",
            "email": "candidate@example.com",
            "target_position": "后端工程师",
        },
        "education": [],
        "work_experience": [],
        "project_experience": [],
        "others": {"skills": ["Python"], "certificates": [], "languages": []},
        "self_evaluation": [],
    }))


class ResumeMutationApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "resume-mutation.sqlite3"
        self.engine = create_engine(
            f"sqlite:///{db_path.as_posix()}",
            connect_args={"check_same_thread": False, "timeout": 30},
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)

        db = self.Session()
        try:
            user = ensure_local_user(db)
            self.user_id = user.id
            initial_resume = resume_payload()
            initial_layout = default_layout_config()
            db.add(ResumeProject(
                id="project-1",
                user_id=self.user_id,
                title="并发测试简历",
                base_resume_data=deepcopy(initial_resume),
            ))
            db.add(ProjectTask(
                id="task-1",
                project_id="project-1",
                user_id=self.user_id,
                title="主简历",
                is_base=True,
                session_id="task-1",
                resume_data=deepcopy(initial_resume),
                layout_config=deepcopy(initial_layout),
            ))
            db.commit()
        finally:
            db.close()

        def override_get_db():
            request_db = self.Session()
            try:
                yield request_db
            finally:
                request_db.close()

        self.previous_overrides = dict(main.app.dependency_overrides)
        main.app.dependency_overrides[main.get_db] = override_get_db
        self.local_mode_patch = patch("backend.auth.is_local_mode", return_value=True)
        self.local_mode_patch.start()
        self.client_a = TestClient(main.app)
        self.client_b = TestClient(main.app)
        self.headers = {"X-Task-ID": "task-1"}

    def tearDown(self):
        self.client_a.close()
        self.client_b.close()
        self.local_mode_patch.stop()
        main.app.dependency_overrides.clear()
        main.app.dependency_overrides.update(self.previous_overrides)
        self.engine.dispose()
        self.temp_dir.cleanup()

    def load_resume(self, client: TestClient | None = None) -> tuple[dict, dict]:
        response = (client or self.client_a).post("/load_resume", headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        version = payload.pop("state_version")
        payload.pop("parsing_status", None)
        return payload, version

    def stored_task(self):
        db = self.Session()
        try:
            task = get_resume_task(db, self.user_id, "task-1")
            return {
                "resume_data": deepcopy(task.resume_data),
                "layout_config": deepcopy(task.layout_config),
                "state_sequence": task.state_sequence,
                "revisions": db.query(ResumeRevision).filter_by(task_id="task-1").count(),
            }
        finally:
            db.close()

    def test_two_clients_editing_same_content_version_yield_one_success_and_one_conflict(self):
        current, version = self.load_resume()
        payload_b = deepcopy(current)
        payload_c = deepcopy(current)
        payload_b["basics"]["name"] = "B"
        payload_c["basics"]["name"] = "C"
        barrier = threading.Barrier(2)

        def save(client, resume_data):
            barrier.wait(timeout=5)
            return client.post(
                "/save_resume",
                headers=self.headers,
                json={"resume_data": resume_data, "base_version": version},
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = [
                executor.submit(save, self.client_a, payload_b),
                executor.submit(save, self.client_b, payload_c),
            ]
            results = [future.result(timeout=15) for future in responses]

        self.assertEqual(sorted(response.status_code for response in results), [200, 409])
        stored = self.stored_task()
        self.assertIn(stored["resume_data"]["basics"]["name"], {"B", "C"})
        self.assertEqual(stored["state_sequence"], 1)
        self.assertEqual(stored["revisions"], 1)

    def test_two_clients_editing_same_layout_version_yield_one_success_and_one_conflict(self):
        _, version = self.load_resume()
        layout_a = default_layout_config()
        layout_b = default_layout_config()
        layout_a["global"]["fontSize"] = 10.5
        layout_b["global"]["fontSize"] = 11.0
        barrier = threading.Barrier(2)

        def save(client, layout):
            barrier.wait(timeout=5)
            return client.put(
                "/tasks/task-1/layout",
                headers=self.headers,
                json={"layout_config": layout, "base_version": version},
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = [
                executor.submit(save, self.client_a, layout_a),
                executor.submit(save, self.client_b, layout_b),
            ]
            results = [future.result(timeout=15) for future in responses]

        self.assertEqual(sorted(response.status_code for response in results), [200, 409])
        stored = self.stored_task()
        self.assertIn(stored["layout_config"]["global"]["fontSize"], {10.5, 11.0})
        self.assertEqual(stored["state_sequence"], 1)
        self.assertEqual(stored["revisions"], 1)

    def test_stale_cross_domain_versions_merge_content_and_layout(self):
        current, version = self.load_resume()
        changed_resume = deepcopy(current)
        changed_resume["basics"]["name"] = "B"
        content_response = self.client_a.post(
            "/save_resume",
            headers=self.headers,
            json={"resume_data": changed_resume, "base_version": version},
        )
        self.assertEqual(content_response.status_code, 200, content_response.text)

        changed_layout = default_layout_config()
        changed_layout["global"]["fontSize"] = 10.5
        layout_response = self.client_b.put(
            "/tasks/task-1/layout",
            headers=self.headers,
            json={"layout_config": changed_layout, "base_version": version},
        )
        self.assertEqual(layout_response.status_code, 200, layout_response.text)

        stored = self.stored_task()
        self.assertEqual(stored["resume_data"]["basics"]["name"], "B")
        self.assertEqual(stored["layout_config"]["global"]["fontSize"], 10.5)
        self.assertEqual(stored["state_sequence"], 2)
        self.assertEqual(stored["revisions"], 2)

    def test_ai_edit_lock_blocks_manual_save_without_creating_revision(self):
        current, version = self.load_resume()
        changed = deepcopy(current)
        changed["basics"]["name"] = "B"
        db = self.Session()
        try:
            self.assertIsNotNone(acquire_resume_edit_lock(
                db, self.user_id, "task-1", "ai-session", "ai-request"
            ))
        finally:
            db.close()

        try:
            response = self.client_a.post(
                "/save_resume",
                headers=self.headers,
                json={"resume_data": changed, "base_version": version},
            )
            self.assertEqual(response.status_code, 409, response.text)
            stored = self.stored_task()
            self.assertEqual(stored["resume_data"]["basics"]["name"], "A")
            self.assertEqual(stored["state_sequence"], 0)
            self.assertEqual(stored["revisions"], 0)
        finally:
            db = self.Session()
            try:
                release_resume_edit_lock(
                    db, self.user_id, "task-1",
                    owner_session_id="ai-session", request_id="ai-request",
                )
            finally:
                db.close()

    def test_old_revision_cannot_undo_a_later_manual_edit(self):
        current, version = self.load_resume()
        changed_b = deepcopy(current)
        changed_b["basics"]["name"] = "B"
        first = self.client_a.post(
            "/save_resume",
            headers=self.headers,
            json={"resume_data": changed_b, "base_version": version},
        )
        self.assertEqual(first.status_code, 200, first.text)

        current_b, version_b = self.load_resume(self.client_b)
        changed_c = deepcopy(current_b)
        changed_c["basics"]["name"] = "C"
        second = self.client_b.post(
            "/save_resume",
            headers=self.headers,
            json={"resume_data": changed_c, "base_version": version_b},
        )
        self.assertEqual(second.status_code, 200, second.text)

        undo = self.client_a.post(
            "/tasks/task-1/undo",
            headers=self.headers,
            json={
                "revision_id": first.json()["revision_id"],
                "base_version": second.json()["state_version"],
            },
        )
        self.assertEqual(undo.status_code, 409, undo.text)
        stored = self.stored_task()
        self.assertEqual(stored["resume_data"]["basics"]["name"], "C")
        self.assertEqual(stored["state_sequence"], 2)
        self.assertEqual(stored["revisions"], 2)

    def test_resume_workspace_endpoints_reject_missing_task_context(self):
        requests = (
            lambda: self.client_a.post("/load_resume"),
            lambda: self.client_a.post("/save_resume", json={"resume_data": resume_payload()}),
            lambda: self.client_a.post("/load_jd", json={}),
            lambda: self.client_a.post("/save_jd", json={"jd_data": {"position": "后端工程师"}}),
            lambda: self.client_a.post("/load_conversation", json={"session_id": "task-1"}),
            lambda: self.client_a.post("/save_conversation", json={"session_id": "task-1", "messages": []}),
            lambda: self.client_a.post("/api/chat/first_message", json={"user_type": "custom", "custom_identity": "开发者"}),
            lambda: self.client_a.post("/api/chat/save_ai_message", json={"message": "欢迎"}),
            lambda: self.client_a.post("/translate_resume", json={}),
            lambda: self.client_a.post("/restore_resume_translation", json={}),
            lambda: self.client_a.post(
                "/api/resume/parse_and_save",
                files={"file": ("resume.pdf", b"%PDF-test", "application/pdf")},
            ),
            lambda: self.client_a.post("/api/resume/confirm_import", json={"resume_data": {}}),
            lambda: self.client_a.delete("/api/resume/import_drafts/draft-1"),
            lambda: self.client_a.get("/api/resume/parsing_status"),
            lambda: self.client_a.post("/export_pdf", json={}),
            lambda: self.client_a.post("/export_docx", json={}),
            lambda: self.client_a.post("/api/chat/first_message_from_resume", json={}),
        )
        for request in requests:
            with self.subTest(request=request):
                response = request()
                self.assertEqual(response.status_code, 400, response.text)

        stored = self.stored_task()
        self.assertEqual(stored["state_sequence"], 0)
        self.assertEqual(stored["revisions"], 0)
        db = self.Session()
        try:
            self.assertEqual(db.query(Conversation).count(), 0)
        finally:
            db.close()

    def test_invalid_task_header_returns_not_found_before_resume_write(self):
        response = self.client_a.post(
            "/save_resume",
            headers={"X-Task-ID": "missing-task"},
            json={"resume_data": resume_payload("B")},
        )
        self.assertEqual(response.status_code, 404, response.text)
        stored = self.stored_task()
        self.assertEqual(stored["resume_data"]["basics"]["name"], "A")
        self.assertEqual(stored["state_sequence"], 0)
        self.assertEqual(stored["revisions"], 0)

    def test_invalid_task_header_rejects_jd_and_conversation_endpoints(self):
        invalid_headers = {"X-Task-ID": "missing-task"}
        requests = (
            lambda: self.client_a.post("/load_jd", headers=invalid_headers, json={}),
            lambda: self.client_a.post("/save_jd", headers=invalid_headers, json={"jd_data": {}}),
            lambda: self.client_a.post("/load_conversation", headers=invalid_headers, json={"session_id": "x"}),
            lambda: self.client_a.post("/save_conversation", headers=invalid_headers, json={"session_id": "x", "messages": []}),
        )
        for request in requests:
            with self.subTest(request=request):
                response = request()
                self.assertEqual(response.status_code, 404, response.text)

        db = self.Session()
        try:
            self.assertEqual(db.query(Conversation).count(), 0)
        finally:
            db.close()

    def test_ai_message_without_session_uses_the_task_main_session(self):
        response = self.client_a.post(
            "/api/chat/save_ai_message",
            headers=self.headers,
            json={"message": "主会话欢迎语"},
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["session_id"], "task-1")
        db = self.Session()
        try:
            task = get_resume_task(db, self.user_id, "task-1")
            self.assertEqual(task.messages, [{"type": "ai", "content": "主会话欢迎语"}])
            self.assertEqual(task.compressed_context, [{"type": "ai", "content": "主会话欢迎语"}])
            self.assertEqual(db.query(Conversation).count(), 0)
        finally:
            db.close()

    def test_translation_rejects_a_stale_content_version(self):
        current, version = self.load_resume()
        changed_b = deepcopy(current)
        changed_b["basics"]["name"] = "B"
        saved = self.client_a.post(
            "/save_resume",
            headers=self.headers,
            json={"resume_data": changed_b, "base_version": version},
        )
        self.assertEqual(saved.status_code, 200, saved.text)

        translated = deepcopy(changed_b)
        translated["basics"]["name"] = "Translated B"
        service_result = {
            "resume_data": translated,
            "cache_hits": 0,
            "new_translations": 1,
            "total_translatable": 1,
        }
        with patch(
            "backend.resume_translation.translate_resume",
            AsyncMock(return_value=service_result),
        ):
            response = self.client_b.post(
                "/translate_resume",
                headers=self.headers,
                json={"base_version": version},
            )

        self.assertEqual(response.status_code, 409, response.text)
        stored = self.stored_task()
        self.assertEqual(stored["resume_data"]["basics"]["name"], "B")
        self.assertEqual(stored["state_sequence"], 1)
        self.assertEqual(stored["revisions"], 1)

    def test_import_confirmation_rejects_a_stale_content_version(self):
        current, version = self.load_resume()
        changed_b = deepcopy(current)
        changed_b["basics"]["name"] = "B"
        saved = self.client_a.post(
            "/save_resume",
            headers=self.headers,
            json={"resume_data": changed_b, "base_version": version},
        )
        self.assertEqual(saved.status_code, 200, saved.text)

        imported = resume_payload("Imported C")
        response = self.client_b.post(
            "/api/resume/confirm_import",
            headers=self.headers,
            json={
                "resume_data": imported,
                "source_page_count": 1,
                "base_version": version,
            },
        )

        self.assertEqual(response.status_code, 409, response.text)
        stored = self.stored_task()
        self.assertEqual(stored["resume_data"]["basics"]["name"], "B")
        self.assertEqual(stored["state_sequence"], 1)
        self.assertEqual(stored["revisions"], 1)


if __name__ == "__main__":
    unittest.main()
