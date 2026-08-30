import unittest

from backend.main import _sanitize_streaming_user_visible_text, _sanitize_user_visible_text


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

    def test_layout_identifiers_use_existing_chinese_labels(self):
        rendered = _sanitize_user_visible_text(
            "当前是 `compact`，可切换为 `three-column`，不要展示 global.titleStyle。"
        )
        self.assertNotIn("compact", rendered)
        self.assertNotIn("three-column", rendered)
        self.assertNotIn("global.titleStyle", rendered)
        self.assertIn("紧凑", rendered)
        self.assertIn("三列", rendered)
        self.assertIn("模块标题样式", rendered)

    def test_retired_layout_identifiers_remain_localizable_without_becoming_capabilities(self):
        rendered = _sanitize_user_visible_text(
            "`basics.preset` 曾使用 `centered`。"
        )
        self.assertEqual(rendered, "基本信息布局 曾使用 居中式。")

    def test_streaming_boundary_withholds_partial_internal_identifiers(self):
        self.assertEqual(
            _sanitize_streaming_user_visible_text("当前是 `comp"),
            "当前是 ",
        )
        self.assertEqual(
            _sanitize_streaming_user_visible_text("当前是 `compact`"),
            "当前是 紧凑",
        )
        self.assertEqual(
            _sanitize_streaming_user_visible_text("调用 request_resume"),
            "调用 ",
        )
        self.assertEqual(
            _sanitize_streaming_user_visible_text("调用 request_resume_edit"),
            "调用 系统能力",
        )


if __name__ == "__main__":
    unittest.main()
