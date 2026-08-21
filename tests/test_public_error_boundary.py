import unittest

from backend.main import _sanitize_user_visible_text


class PublicErrorBoundaryTests(unittest.TestCase):
    def test_internal_protocol_identifiers_are_not_user_visible(self):
        rendered = _sanitize_user_visible_text(
            "request_resume_edit 处理 layout_config 失败，ValueError: invalid session_id"
        )
        self.assertNotIn("request_resume_edit", rendered)
        self.assertNotIn("layout_config", rendered)
        self.assertNotIn("session_id", rendered)
        self.assertNotIn("ValueError", rendered)

    def test_legitimate_resume_english_is_preserved(self):
        text = "使用 LangGraph、FastAPI 和 MySQL 构建 AI 应用"
        self.assertEqual(_sanitize_user_visible_text(text), text)


if __name__ == "__main__":
    unittest.main()
