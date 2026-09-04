import base64
import unittest
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from PIL import Image
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from backend.layout_config import default_layout_config
from backend.main import _parse_render_style
from backend.resume_agent import (
    AgentState,
    _attach_visual_resume_parts,
    conversation_node,
    resume_snapshot_tool,
    should_force_initial_visual_snapshot,
    tool_node,
    graph,
)
from backend.skill_runtime import skill_runtime

_resume_snapshot_module = skill_runtime.get("resume-snapshot").module
DEFAULT_DPI = _resume_snapshot_module.DEFAULT_DPI
ResumeVisualSnapshot = _resume_snapshot_module.ResumeVisualSnapshot
render_resume_pdf_images = _resume_snapshot_module.render_resume_pdf_images
render_resume_pdf_snapshot = _resume_snapshot_module.render_resume_pdf_snapshot


def snapshot(*, revision="revision-1"):
    return ResumeVisualSnapshot(
        parts=[{"type": "image_url", "image_url": {"url": "data:image/png;base64,PNG"}}],
        revision=revision,
        page_sizes=((900, 1273),),
        page_bytes=(12345,),
    )


class ResumeVisualSkillTests(unittest.IsolatedAsyncioTestCase):
    def test_only_initial_layout_turn_is_forced(self):
        initial = AgentState(
            messages=[HumanMessage(content="开始排版建议")],
            context_type="layout",
            context_metadata={},
        )
        follow_up = AgentState(
            messages=[AIMessage(content="1. 调整间距"), HumanMessage(content="执行第一点")],
            context_type="layout",
            context_metadata={"initial_analysis_completed": True},
        )
        self.assertTrue(should_force_initial_visual_snapshot(initial))
        self.assertFalse(should_force_initial_visual_snapshot(follow_up))

        legacy_follow_up = AgentState(
            messages=[AIMessage(content="1. 调整间距"), HumanMessage(content="继续")],
            context_type="layout",
            context_metadata={"latest_recommendations": "1. 调整间距"},
        )
        self.assertFalse(should_force_initial_visual_snapshot(legacy_follow_up))

        explicit_command = AgentState(
            messages=[HumanMessage(content="检查排版")],
            context_type="layout",
            context_metadata={"initial_analysis_completed": True},
            assistant_command="layout",
        )
        self.assertTrue(should_force_initial_visual_snapshot(explicit_command))

    def test_image_parts_are_attached_only_to_latest_human_turn(self):
        parts = [{"type": "image_url", "image_url": {"url": "data:image/png;base64,PNG"}}]
        messages = [HumanMessage(content="之前"), HumanMessage(content="现在")]
        attached = _attach_visual_resume_parts(messages, parts)
        self.assertEqual(messages[-1].content, "现在")
        self.assertEqual(attached[-1].content[0]["text"], "现在")
        self.assertEqual(attached[-1].content[-1], parts[0])
        self.assertIn("PDF 第 1 页", attached[-1].content[-2]["text"])

    def test_skill_uses_lower_resolution_color_png_and_at_most_two_pages(self):
        image = Image.new("RGB", (1200, 1700), (10, 120, 230))
        render_style = {
            "pageMode": "auto",
            "sourcePageCount": 1,
            "pageBreakBefore": "project_experience:0",
        }
        with (
            patch("backend.pdf_generator.generate_pdf", return_value=b"%PDF") as generate_pdf,
            patch("pdf2image.convert_from_bytes", return_value=[image, image.copy(), image.copy()]) as convert,
        ):
            result = render_resume_pdf_snapshot(
                {"basics": {}}, {}, render_style=render_style, max_pages=2,
            )
        self.assertEqual(convert.call_args.kwargs["dpi"], DEFAULT_DPI)
        self.assertEqual(DEFAULT_DPI, 96)
        self.assertEqual(generate_pdf.call_args.kwargs["style"], render_style)
        self.assertEqual(len(result.parts), 2)
        self.assertLessEqual(max(result.page_sizes[0]), 1400)
        encoded = result.parts[0]["image_url"]["url"].split(",", 1)[1]
        decoded = Image.open(BytesIO(base64.b64decode(encoded)))
        self.assertEqual(decoded.mode, "RGB")
        self.assertEqual(decoded.getpixel((0, 0)), (10, 120, 230))

    def test_compatibility_wrapper_returns_image_parts(self):
        image = Image.new("RGB", (4, 4), "white")
        with (
            patch("backend.pdf_generator.generate_pdf", return_value=b"%PDF"),
            patch("pdf2image.convert_from_bytes", return_value=[image]),
        ):
            parts = render_resume_pdf_images({"basics": {}}, {})
        self.assertEqual(len(parts), 1)
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

    async def test_initial_layout_turn_forces_one_ephemeral_snapshot(self):
        bound = SimpleNamespace(
            ainvoke=AsyncMock(return_value=AIMessage(content="1. 调整模块间距")),
        )
        model = SimpleNamespace(bind_tools=MagicMock(return_value=bound))
        state = AgentState(
            messages=[HumanMessage(content="开始排版建议")],
            resume_data={"basics": {"name": "张三"}},
            layout_data=default_layout_config(),
            context_type="layout",
            context_metadata={},
        )
        with (
            patch("backend.resume_agent.conversation_llm", model),
            patch("resumebranch_agent_skill_resume_snapshot.render_resume_pdf_snapshot", return_value=snapshot()) as render,
        ):
            result = await conversation_node(state)
        render.assert_called_once()
        exposed = {item.name for item in model.bind_tools.call_args.args[0]}
        self.assertEqual(
            exposed,
            {"activate_agent_skill"},
        )
        sent = bound.ainvoke.await_args.args[0]
        self.assertTrue(any(
            isinstance(message.content, list)
            and any(isinstance(part, dict) and part.get("type") == "image_url" for part in message.content)
            for message in sent
        ))
        self.assertEqual(result["visual_snapshot_parts"], [])
        self.assertEqual(result["visual_snapshot_calls"], 1)
        self.assertTrue(result["context_metadata_updates"]["initial_analysis_completed"])

    async def test_layout_follow_up_does_not_automatically_render(self):
        bound = SimpleNamespace(ainvoke=AsyncMock(return_value=AIMessage(content="继续讨论")))
        model = SimpleNamespace(bind_tools=MagicMock(return_value=bound))
        state = AgentState(
            messages=[AIMessage(content="1. 调整间距"), HumanMessage(content="执行第一点")],
            resume_data={"basics": {"name": "张三"}},
            layout_data=default_layout_config(),
            context_type="layout",
            context_metadata={"initial_analysis_completed": True},
        )
        with (
            patch("backend.resume_agent.conversation_llm", model),
            patch("resumebranch_agent_skill_resume_snapshot.render_resume_pdf_snapshot") as render,
        ):
            await conversation_node(state)
        render.assert_not_called()
        bound_tools = model.bind_tools.call_args.args[0]
        self.assertEqual(
            {value.name for value in bound_tools},
            {"activate_agent_skill"},
        )

    async def test_model_visual_tool_renders_once_and_returns_ephemeral_parts(self):
        state = AgentState(
            messages=[
                HumanMessage(content="请查看页面后回答"),
                AIMessage(content="", tool_calls=[{
                    "name": "resume_snapshot",
                    "args": {"reason": "需要判断分页"},
                    "id": "visual-1",
                }]),
            ],
            resume_data={"basics": {"name": "张三"}},
            layout_data=default_layout_config(),
        )
        with patch("resumebranch_agent_skill_resume_snapshot.render_resume_pdf_snapshot", return_value=snapshot()) as render:
            result = await tool_node(state)
        render.assert_called_once()
        self.assertEqual(result["visual_snapshot_calls"], 1)
        self.assertEqual(len(result["visual_snapshot_parts"]), 1)
        self.assertIsInstance(result["messages"][-1], ToolMessage)
        self.assertEqual(result["messages"][-1].name, "resume_snapshot")

    async def test_graph_returns_to_model_after_visual_tool(self):
        responses = [
            AIMessage(content="", tool_calls=[{
                "name": "resume_snapshot",
                "args": {"reason": "查看分页"},
                "id": "visual-loop-1",
            }]),
            AIMessage(content="已根据当前快照完成判断"),
        ]
        bound = SimpleNamespace(ainvoke=AsyncMock(side_effect=responses))
        model = SimpleNamespace(bind_tools=MagicMock(return_value=bound))
        state = AgentState(
            messages=[HumanMessage(content="请查看当前页面后再回答")],
            resume_data={"basics": {"name": "张三"}},
            layout_data=default_layout_config(),
        )
        with (
            patch("backend.resume_agent.conversation_llm", model),
            patch("resumebranch_agent_skill_resume_snapshot.render_resume_pdf_snapshot", return_value=snapshot()) as render,
        ):
            result = await graph.ainvoke(state)
        render.assert_called_once()
        self.assertEqual(bound.ainvoke.await_count, 2)
        self.assertEqual(result["messages"][-1].content, "已根据当前快照完成判断")
        self.assertEqual(result["visual_snapshot_parts"], [])

    async def test_layout_follow_up_can_call_edit_without_reuploading_snapshot(self):
        response = AIMessage(content="", tool_calls=[{
            "name": "resume_edit",
            "args": {
                "resume_operations": [],
                "layout_operations": [{
                    "op": "set",
                    "path": "global.moduleMargin",
                    "value": 0.6,
                    "expected": 0.5,
                }],
            },
            "id": "layout-edit-1",
        }])
        bound = SimpleNamespace(ainvoke=AsyncMock(return_value=response))
        model = SimpleNamespace(bind_tools=MagicMock(return_value=bound))
        state = AgentState(
            messages=[
                AIMessage(content="1. 将模块间距调整为 0.6。"),
                HumanMessage(content="执行第一点"),
            ],
            resume_data={"basics": {"name": "张三"}},
            layout_data=default_layout_config(),
            context_type="layout",
            context_metadata={
                "initial_analysis_completed": True,
                "latest_recommendations": "1. 将模块间距调整为 0.6。",
            },
            user_id=1,
            task_id="task-1",
        )
        with (
            patch("backend.resume_agent.conversation_llm", model),
            patch("resumebranch_agent_skill_resume_snapshot.render_resume_pdf_snapshot") as render,
        ):
            result = await graph.ainvoke(state)
        render.assert_not_called()
        self.assertIsNotNone(result["pending_confirmation"])
        self.assertEqual(
            result["pending_confirmation"]["layout_candidate"]["global"]["moduleMargin"],
            0.6,
        )

    async def test_model_cannot_render_twice_in_one_turn(self):
        state = AgentState(
            messages=[AIMessage(content="", tool_calls=[{
                "name": "resume_snapshot", "args": {}, "id": "visual-2",
            }])],
            visual_snapshot_calls=1,
        )
        with patch("resumebranch_agent_skill_resume_snapshot.render_resume_pdf_snapshot") as render:
            result = await tool_node(state)
        render.assert_not_called()
        self.assertIn("本轮已经提供过", result["messages"][-1].content)

    async def test_visual_evidence_is_resolved_before_simultaneous_edit(self):
        state = AgentState(
            messages=[AIMessage(content="", tool_calls=[
                {
                    "name": "resume_edit",
                    "args": {
                        "resume_operations": [{
                            "op": "set", "path": "basics.name", "value": "新姓名",
                        }],
                        "layout_operations": [],
                    },
                    "id": "edit-visual-1",
                },
                {
                    "name": "resume_snapshot",
                    "args": {"reason": "先确认视觉效果"},
                    "id": "visual-edit-1",
                },
            ])],
            resume_data={"basics": {"name": "旧姓名"}},
            layout_data=default_layout_config(),
        )
        with patch("resumebranch_agent_skill_resume_snapshot.render_resume_pdf_snapshot", return_value=snapshot()):
            result = await tool_node(state)
        self.assertIsNone(result["pending_confirmation"])
        self.assertEqual(result["resume_data"]["basics"]["name"], "旧姓名")
        self.assertTrue(result["visual_snapshot_parts"])
        deferred = [
            message.content for message in result["messages"]
            if isinstance(message, ToolMessage) and message.name == "resume_edit"
        ]
        self.assertTrue(any("尚未生成修改预览" in value for value in deferred))

    async def test_visual_failure_does_not_fall_back_to_fake_layout_analysis(self):
        model = SimpleNamespace(ainvoke=AsyncMock(), bind_tools=MagicMock())
        state = AgentState(
            messages=[HumanMessage(content="开始排版建议")],
            resume_data={"basics": {"name": "张三"}},
            layout_data=default_layout_config(),
            context_type="layout",
            context_metadata={},
        )
        with (
            patch("backend.resume_agent.conversation_llm", model),
            patch("resumebranch_agent_skill_resume_snapshot.render_resume_pdf_snapshot", side_effect=FileNotFoundError("Poppler")),
        ):
            result = await conversation_node(state)
        model.ainvoke.assert_not_called()
        self.assertIn("快照生成失败", result["messages"][-1].content)
        self.assertEqual(result["context_metadata_updates"]["last_visual_error"], "FileNotFoundError")


if __name__ == "__main__":
    unittest.main()
