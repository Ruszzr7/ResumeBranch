import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from PIL import Image

from backend.resume_agent import (
    _attach_visual_resume_parts,
    conversation_node,
    should_render_resume_pdf_images,
)
from backend.main import _parse_render_style
from backend.skills.render_resume_pdf_images import render_resume_pdf_images
from langchain_core.messages import HumanMessage


class ResumeVisualSkillTests(unittest.TestCase):
    def test_visual_trigger_is_on_demand(self):
        self.assertTrue(should_render_resume_pdf_images("请看看当前简历页面的排版", "main"))
        self.assertTrue(should_render_resume_pdf_images("请开始排版建议", "layout"))
        self.assertFalse(should_render_resume_pdf_images("请把项目简介改得更简洁", "main"))

    def test_image_parts_are_attached_only_to_latest_human_turn(self):
        parts = [{"type": "image_url", "image_url": {"url": "data:image/png;base64,PNG"}}]
        messages = [HumanMessage(content="之前"), HumanMessage(content="现在")]
        attached = _attach_visual_resume_parts(messages, parts)
        self.assertEqual(messages[-1].content, "现在")
        self.assertEqual(attached[-1].content[0]["text"], "现在")
        self.assertEqual(attached[-1].content[-1], parts[0])
        self.assertIn("PDF 第 1 页", attached[-1].content[-2]["text"])

    def test_skill_renders_at_most_two_in_memory_png_pages(self):
        image = Image.new("RGB", (4, 4), "white")
        render_style = {
            "pageMode": "auto",
            "sourcePageCount": 1,
            "pageBreakBefore": "project_experience:0",
        }
        with (
            patch("backend.pdf_generator.generate_pdf", return_value=b"%PDF") as generate_pdf,
            patch("pdf2image.convert_from_bytes", return_value=[image, image.copy(), image.copy()]) as convert,
        ):
            parts = render_resume_pdf_images(
                {"basics": {}}, {}, render_style=render_style, max_pages=2,
            )
        convert.assert_called_once()
        self.assertEqual(generate_pdf.call_args.kwargs["style"], render_style)
        self.assertEqual(len(parts), 2)
        self.assertTrue(parts[0]["image_url"]["url"].startswith("data:image/png;base64,"))

    def test_render_style_parser_accepts_only_renderer_fields(self):
        parsed = _parse_render_style({
            "marginTop": "8.5",
            "pageBreakBefore": "project_experience:0",
            "unknown": "must be discarded",
            "fontSize": "not-a-number",
        })
        self.assertEqual(parsed["marginTop"], 8.5)
        self.assertEqual(parsed["pageBreakBefore"], "project_experience:0")
        self.assertNotIn("unknown", parsed)
        self.assertNotIn("fontSize", parsed)

    def test_normal_conversation_attaches_visual_context_only_when_requested(self):
        model = SimpleNamespace(
            bind_tools=MagicMock(return_value=SimpleNamespace(
                ainvoke=AsyncMock(return_value=SimpleNamespace(content="已查看页面")),
            )),
            ainvoke=AsyncMock(return_value=SimpleNamespace(content="普通回答")),
        )
        from backend.resume_agent import AgentState
        from backend.layout_config import default_layout_config

        visual_state = AgentState(
            messages=[HumanMessage(content="请看看当前页面排版")],
            resume_data={"basics": {"name": "张三"}},
            layout_data=default_layout_config(),
            photo="data:image/png;base64,PHOTO",
            render_style={"pageMode": "auto", "pageBreakBefore": "project_experience:0"},
        )
        with (
            patch("backend.resume_agent.conversation_llm", model),
            patch("backend.resume_agent.render_resume_pdf_images", return_value=[
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,PNG"}}
            ]) as render,
        ):
            import asyncio
            result = asyncio.run(conversation_node(visual_state))
        render.assert_called_once()
        self.assertEqual(render.call_args.kwargs.get("photo"), "data:image/png;base64,PHOTO")
        self.assertEqual(
            render.call_args.kwargs.get("render_style"),
            {"pageMode": "auto", "pageBreakBefore": "project_experience:0"},
        )
        sent = model.bind_tools.return_value.ainvoke.await_args.args[0]
        self.assertTrue(any(isinstance(item, list) for item in [sent[-1].content]))
        self.assertEqual(result["messages"][-1].content, "已查看页面")

    def test_visual_render_failure_falls_back_to_text_without_request_error(self):
        model = SimpleNamespace(
            bind_tools=MagicMock(return_value=SimpleNamespace(
                ainvoke=AsyncMock(return_value=SimpleNamespace(content="已使用文字上下文回答")),
            )),
        )
        from backend.resume_agent import AgentState

        visual_state = AgentState(
            messages=[HumanMessage(content="请看看当前页面排版")],
            resume_data={"basics": {"name": "张三"}},
        )
        with (
            patch("backend.resume_agent.conversation_llm", model),
            patch(
                "backend.resume_agent.render_resume_pdf_images",
                side_effect=FileNotFoundError("Poppler unavailable"),
            ),
        ):
            import asyncio
            result = asyncio.run(conversation_node(visual_state))
        self.assertEqual(result["messages"][-1].content, "已使用文字上下文回答")


if __name__ == "__main__":
    unittest.main()
