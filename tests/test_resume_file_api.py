import json
import unittest
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, patch

from starlette.datastructures import Headers, UploadFile

from backend import main
from backend.llm_gateway import GatewayConfig


RESUME = {
    "basics": {"name": "张三", "gender": "", "phone": "13800138000", "email": "a@example.com", "target_position": "开发工程师"},
    "education": [{"school_name": "测试大学", "major": "计算机", "degree": "本科", "date_range": ["2020.09", "2024.06"], "school_tags": [], "gpa": "", "gpa_scale": "", "ranking": "", "average_score": "", "theses": []}],
    "work_experience": [], "project_experience": [],
    "others": {"skills": ["Python"], "certificates": [], "languages": []},
    "self_evaluation": [],
}


def upload(mime="application/pdf"):
    return UploadFile(
        file=BytesIO(b"%PDF-test" if mime == "application/pdf" else b"image"),
        filename="resume.pdf" if mime == "application/pdf" else "resume.png",
        headers=Headers({"content-type": mime}),
    )


class ResumeFileApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_import_requires_parser_configuration(self):
        with patch("backend.main.get_role_config", return_value={}):
            response = await main.parse_and_save_resume_endpoint(
                file=upload(), db=SimpleNamespace(), current_user=SimpleNamespace(id=7)
            )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(json.loads(response.body)["error_code"], "parser_not_configured")

    async def test_import_requires_verified_parser(self):
        profile = {"api_key": "key", "base_url": "https://relay/v1", "model": "gemini", "verified": False}
        with patch("backend.main.get_role_config", return_value=profile):
            response = await main.parse_and_save_resume_endpoint(
                file=upload(), db=SimpleNamespace(), current_user=SimpleNamespace(id=7)
            )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(json.loads(response.body)["error_code"], "parser_not_verified")

    async def test_verified_parser_returns_draft_without_saving(self):
        profile = {"api_key": "key", "base_url": "https://relay/v1", "model": "gemini", "verified": True}
        with (
            patch("backend.main.get_role_config", return_value=profile),
            patch("backend.main.gateway_config", return_value=GatewayConfig("parser", "https://relay/v1", "gemini", "key", "gemini_native")),
            patch("backend.main.invoke_document", AsyncMock(return_value=json.dumps(RESUME, ensure_ascii=False))),
            patch("backend.main.set_parsing_status"),
            patch("backend.source_documents.detect_source_page_count", return_value=1),
            patch("backend.main.delete_unreferenced_source_documents", return_value=[]),
            patch("backend.main.persist_source_document", return_value=SimpleNamespace(id="source-1", status="pending")),
            patch("backend.main.save_user_resume") as save_resume,
        ):
            response = await main.parse_and_save_resume_endpoint(
                file=upload(), draft_only=True, db=SimpleNamespace(), current_user=SimpleNamespace(id=7)
            )
        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["draft"])
        self.assertEqual(payload["source_document_token"], "source-1")
        save_resume.assert_not_called()

    async def test_verified_parser_can_preserve_legacy_immediate_save(self):
        profile = {"api_key": "key", "base_url": "https://relay/v1", "model": "gemini", "verified": True}
        with (
            patch("backend.main.get_role_config", return_value=profile),
            patch("backend.main.gateway_config", return_value=GatewayConfig("parser", "https://relay/v1", "gemini", "key", "gemini_native")),
            patch("backend.main.invoke_document", AsyncMock(return_value=json.dumps(RESUME, ensure_ascii=False))),
            patch("backend.main.set_parsing_status"),
            patch("backend.main.set_source_page_count"),
            patch("backend.source_documents.detect_source_page_count", return_value=1),
            patch("backend.main.persist_source_document", return_value=SimpleNamespace(id="source-1", status="pending")),
            patch("backend.main.attach_source_document", return_value=SimpleNamespace(id="source-1", status="ready")),
            patch("backend.main.delete_unreferenced_source_documents", return_value=[]),
            patch("backend.main.save_user_resume") as save_resume,
        ):
            response = await main.parse_and_save_resume_endpoint(
                file=upload(), draft_only=False, db=SimpleNamespace(), current_user=SimpleNamespace(id=7)
            )
        self.assertEqual(response.status_code, 200)
        save_resume.assert_called_once_with(ANY, 7, ANY)

    async def test_confirm_import_validates_and_saves_draft(self):
        request = main.ConfirmResumeImportRequest(resume_data=RESUME, source_page_count=2)
        with (
            patch("backend.main.save_user_resume") as save_resume,
            patch("backend.main.set_source_page_count"),
            patch("backend.main.set_parsing_status"),
        ):
            response = await main.confirm_resume_import_endpoint(
                request=request, db=SimpleNamespace(), current_user=SimpleNamespace(id=7)
            )
        self.assertTrue(response["success"])
        self.assertEqual(response["source_page_count"], 2)
        save_resume.assert_called_once_with(ANY, 7, ANY)


    async def test_image_and_pdf_share_lossless_schema_prompt(self):
        profile = {"api_key": "key", "base_url": "https://relay/v1beta", "model": "gemini", "verified": True}
        parsed = dict(RESUME)
        parsed.update({
            "research_interests": ["机器人控制"],
            "honors": ["一等奖学金"],
            "custom_sections": [{"title": "校园经历", "items": ["学生会"]}],
        })
        invoke = AsyncMock(return_value=json.dumps(parsed, ensure_ascii=False))
        with (
            patch("backend.main.get_role_config", return_value=profile),
            patch("backend.main.gateway_config", return_value=GatewayConfig("parser", "https://relay/v1beta", "gemini", "key", "gemini_native")),
            patch("backend.main.invoke_document", invoke),
            patch("backend.main.set_parsing_status"),
            patch("backend.source_documents.detect_source_page_count", return_value=1),
            patch("backend.main.delete_unreferenced_source_documents", return_value=[]),
            patch("backend.main.persist_source_document", return_value=SimpleNamespace(id="source-1", status="pending")),
        ):
            response = await main.parse_and_save_resume_endpoint(
                file=upload("image/png"), draft_only=True, db=SimpleNamespace(), current_user=SimpleNamespace(id=7)
            )

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["resume_data"]["research_interests"], ["机器人控制"])
        self.assertEqual(invoke.call_args.kwargs["mime_type"], "image/png")
        prompt = invoke.call_args.kwargs["prompt"]
        for field in ("birth_date", "research_interests", "honors", "custom_sections"):
            self.assertIn(field, prompt)
        self.assertIn("禁止把原简历一个栏目拆成多个新栏目", prompt)
        self.assertIn("CET-4/CET-6", prompt)


if __name__ == "__main__":
    unittest.main()
