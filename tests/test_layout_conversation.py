import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from backend.layout_config import default_layout_config
from backend.resume_agent import (
    AgentState,
    build_local_layout_candidate,
    conversation_node,
    direct_edit_node,
    entry_router,
    is_resume_coaching_request,
    make_pending_confirmation,
    proposal_generator_node,
    tool_node,
)


def resume_payload(name="测试用户"):
    return {
        "basics": {"name": name, "gender": "", "phone": "", "email": "", "target_position": ""},
        "education": [{
            "school_name": "测试大学", "major": "计算机", "degree": "本科",
            "date_range": ["2020", "2024"], "school_tags": ["211"],
            "gpa": "3.5", "gpa_scale": "4.0", "ranking": "", "theses": [],
        }],
        "work_experience": [], "project_experience": [],
        "others": {"skills": [], "certificates": [], "languages": []},
        "self_evaluation": [],
    }


class LayoutConversationTests(unittest.IsolatedAsyncioTestCase):
    def test_review_and_interview_requests_stay_in_conversation_mode(self):
        review_requests = [
            "请分析这份简历有哪些不足，并推荐如何修改和完善",
            "请先全面诊断我的简历，先不要修改",
            "请以面试官身份开始拷打我的项目经历",
            "结合 JD 分析匹配度并给出优化建议",
            "请分析当前简历排版并给出建议，本轮只分析，不修改简历",
        ]
        for request in review_requests:
            with self.subTest(request=request):
                state = AgentState(
                    messages=[HumanMessage(content=request)],
                    resume_data=resume_payload(), layout_data=default_layout_config(),
                )
                self.assertTrue(is_resume_coaching_request(request))
                self.assertEqual(entry_router(state), "conversation_llm")

    def test_explicit_apply_request_still_uses_edit_pipeline(self):
        request = "请直接优化项目经历并应用到简历"
        state = AgentState(
            messages=[HumanMessage(content=request)],
            resume_data=resume_payload(), layout_data=default_layout_config(),
        )
        self.assertFalse(is_resume_coaching_request(request))
        self.assertEqual(entry_router(state), "conversation_llm")

    async def test_coaching_turn_does_not_expose_save_tool(self):
        bound = SimpleNamespace(
            ainvoke=AsyncMock(return_value=AIMessage(content="诊断结果")),
        )
        fake_llm = SimpleNamespace(
            bind_tools=MagicMock(return_value=bound),
        )
        state = AgentState(
            messages=[HumanMessage(content="请全面诊断简历并给出修改建议")],
            resume_data=resume_payload(), layout_data=default_layout_config(),
        )
        with patch("backend.resume_agent.conversation_llm", fake_llm):
            result = await conversation_node(state)
        exposed = fake_llm.bind_tools.call_args.args[0]
        self.assertEqual([item.name for item in exposed], ["render_resume_pdf_images"])
        bound.ainvoke.assert_awaited_once()
        system_prompt = bound.ainvoke.await_args.args[0][0].content
        self.assertIn("本轮模式：只读诊断与简历教练", system_prompt)
        self.assertEqual(result["messages"][-1].content, "诊断结果")

    async def test_mixed_mission_apply_and_consultation_still_exposes_edit_skill(self):
        bound = SimpleNamespace(
            ainvoke=AsyncMock(return_value=AIMessage(content="已处理明确修改，并继续回答咨询。")),
        )
        fake_llm = SimpleNamespace(bind_tools=MagicMock(return_value=bound))
        state = AgentState(
            messages=[
                AIMessage(content="1. 调整模块间距。"),
                HumanMessage(content="执行第一点，另外工作经历还有什么优化建议吗？"),
            ],
            resume_data=resume_payload(),
            layout_data=default_layout_config(),
            context_type="layout",
            context_metadata={"initial_analysis_completed": True},
        )
        with patch("backend.resume_agent.conversation_llm", fake_llm):
            await conversation_node(state)
        exposed = {item.name for item in fake_llm.bind_tools.call_args.args[0]}
        self.assertEqual(exposed, {"render_resume_pdf_images", "request_resume_edit"})

    async def test_common_layout_request_is_local_and_previews_without_llm(self):
        state = AgentState(
            messages=[HumanMessage(content="学校后面的211不要黑底，专业和GPA放到学校右边")],
            resume_data=resume_payload(), layout_data=default_layout_config(),
            user_id=7, task_id="task-1",
        )
        self.assertEqual(entry_router(state), "direct_edit")
        candidate = build_local_layout_candidate(state)
        self.assertEqual(candidate["education"]["schoolTagStyle"], "text")
        self.assertEqual(candidate["education"]["preset"], "three-column")

        with patch("backend.resume_agent.conversation_llm") as llm:
            result = await direct_edit_node(state)
        llm.ainvoke.assert_not_called()
        pending = result["pending_confirmation"]
        self.assertEqual([item["id"] for item in pending["changes"]], ["layout-education"])
        self.assertEqual(pending["resume_candidate"]["basics"]["name"], "测试用户")
        self.assertEqual(pending["layout_candidate"]["education"]["preset"], "three-column")

    async def test_complete_default_layout_request_is_local_and_uses_current_defaults(self):
        current_layout = default_layout_config()
        current_layout["education"]["preset"] = "classic"
        state = AgentState(
            messages=[HumanMessage(content="请恢复默认排版。")],
            resume_data=resume_payload(), layout_data=current_layout,
            user_id=7, task_id="task-1",
        )
        self.assertEqual(entry_router(state), "direct_edit")
        with patch("backend.resume_agent.conversation_llm") as llm:
            result = await direct_edit_node(state)
        llm.ainvoke.assert_not_called()
        candidate = result["pending_confirmation"]["layout_candidate"]
        self.assertEqual(candidate["basics"]["preset"], "left-aligned")
        self.assertEqual(candidate["education"]["preset"], "compact")
        self.assertEqual(candidate["work_experience"]["preset"], "compact")

    async def test_mixed_content_and_layout_request_uses_one_local_preview(self):
        layout = default_layout_config()
        layout["education"]["schoolTagStyle"] = "outline"
        state = AgentState(
            messages=[HumanMessage(content="把姓名改为张伟，学校标签不要黑底")],
            resume_data=resume_payload(), layout_data=layout,
            user_id=7, task_id="task-1",
        )
        self.assertEqual(entry_router(state), "direct_edit")
        result = await direct_edit_node(state)
        self.assertEqual(result["pending_confirmation"]["resume_candidate"]["basics"]["name"], "张伟")
        kinds = [item.get("kind", "content") for item in result["pending_confirmation"]["changes"]]
        self.assertIn("content", kinds)
        self.assertIn("layout", kinds)

    async def test_complex_combined_request_uses_exactly_one_model_call(self):
        layout = default_layout_config()
        project_index = layout["global"]["sectionOrder"].index("project_experience")
        state = AgentState(
            messages=[HumanMessage(content="重新组织项目经历描述，并将它放到教育经历前面")],
            resume_data=resume_payload(), layout_data=layout,
            user_id=7, task_id="task-1",
            context_metadata={
                "resume_operations": [{
                    "op": "append", "path": "project_experience",
                    "value": {"project_name": "项目A", "role": "开发", "date_range": [], "details": ["完成接口优化"]},
                }],
                "layout_operations": [{
                    "op": "move", "path": "global.sectionOrder",
                    "from_index": project_index, "to_index": 0,
                }],
            },
        )
        with patch("backend.resume_agent.conversation_llm") as fake_llm:
            result = await proposal_generator_node(state)
        fake_llm.ainvoke.assert_not_called()
        ids = [item["id"] for item in result["pending_confirmation"]["changes"]]
        self.assertIn("layout-global", ids)
        self.assertTrue(any(not value.startswith("layout-") for value in ids))

    async def test_structured_model_cannot_bypass_modal_only_font_sizes(self):
        before_layout = default_layout_config()
        state = AgentState(
            messages=[HumanMessage(content="重新组织项目经历描述并应用")],
            resume_data=resume_payload(), layout_data=before_layout,
            user_id=7, task_id="task-1",
            context_metadata={
                "resume_operations": [{
                    "op": "append", "path": "project_experience",
                    "value": {"project_name": "项目A", "role": "开发", "date_range": [], "details": ["完成接口优化"]},
                }],
                "layout_operations": [{"op": "set", "path": "global.fontSize", "value": 11.5}],
            },
        )
        with patch("backend.resume_agent.conversation_llm") as fake_llm:
            result = await proposal_generator_node(state)
        fake_llm.ainvoke.assert_not_called()
        self.assertIsNone(result["pending_confirmation"])
        self.assertIn("无法安全生成", result["proposal_error"])

    async def test_selecting_layout_group_persists_only_that_group(self):
        before_layout = default_layout_config()
        before_layout["education"]["schoolTagStyle"] = "outline"
        after_layout = default_layout_config()
        after_layout["education"]["schoolTagStyle"] = "text"
        before_resume = resume_payload()
        proposal_state = AgentState(
            resume_data=before_resume, layout_data=before_layout, user_id=7, task_id="task-1"
        )
        pending = make_pending_confirmation(proposal_state, before_resume, after_layout)
        confirm_state = AgentState(
            messages=[HumanMessage(content=f'[CONFIRM_REPLY:{pending["confirm_id"]}:confirm_selected:layout-education]')],
            resume_data=before_resume, layout_data=before_layout, pending_confirmation=pending,
            user_id=7, task_id="task-1",
        )
        fake_db = SimpleNamespace(close=lambda: None)
        with (
            patch("backend.tools.update_resume", return_value="简历已成功保存"),
            patch("backend.database.SessionLocal", return_value=fake_db),
            patch("backend.database.save_task_layout_config", return_value=after_layout) as save_layout,
            patch("backend.resume_agent.record_assistant_revision") as record_revision,
        ):
            result = await tool_node(confirm_state)
        save_layout.assert_called_once()
        record_revision.assert_called_once()
        self.assertEqual(result["layout_data"]["education"]["schoolTagStyle"], "text")
        self.assertTrue(result["just_saved"])


if __name__ == "__main__":
    unittest.main()
