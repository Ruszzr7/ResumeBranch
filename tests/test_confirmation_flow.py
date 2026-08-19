import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph import END

from backend.resume_agent import (
    AgentState,
    build_local_edit_candidate,
    direct_edit_node,
    entry_router,
    is_explicit_resume_change_request,
    proposal_generator_node,
    route_after_conversation,
    tool_node,
    tool_node_router,
)
from backend.resume_changes import build_resume_changes, resume_digest
from backend.layout_config import default_layout_config


def resume_payload(name="测试用户", *, with_education=False):
    payload = {
        "basics": {
            "name": name,
            "gender": "",
            "phone": "",
            "email": "",
            "target_position": "",
        },
        "education": [],
        "work_experience": [],
        "project_experience": [],
        "others": {"skills": [], "certificates": [], "languages": []},
        "self_evaluation": [],
    }
    if with_education:
        payload["education"] = [{
            "school_name": "测试大学",
            "major": "计算机科学",
            "degree": "本科",
            "date_range": ["2020.09", "2024.06"],
            "school_tags": [],
            "gpa": "3.5",
            "gpa_scale": "4.0",
            "ranking": "",
            "theses": [],
        }]
    return payload


def confirmation_state(value="confirm", *, pending_task_id="task-1", state_task_id="task-1"):
    confirm_id = "confirm-1"
    return AgentState(
        messages=[HumanMessage(content=f"[CONFIRM_REPLY:{confirm_id}:{value}]")],
        resume_data=resume_payload("原姓名"),
        jd_data={},
        pending_confirmation={
            "confirm_id": confirm_id,
            "tool_name": "save_resume_tool",
            "tool_args": {
                "content": json.dumps(resume_payload("新姓名"), ensure_ascii=False),
                "task_id": pending_task_id,
            },
            "status": "pending",
        },
        user_id=7,
        task_id=state_task_id,
    )


def selective_confirmation_state(selected_id="change-1"):
    before = resume_payload("原姓名")
    before["basics"]["target_position"] = "开发"
    after = resume_payload("新姓名")
    after["basics"]["target_position"] = "后端开发"
    changes = build_resume_changes(before, after)
    return AgentState(
        messages=[HumanMessage(content=f"[CONFIRM_REPLY:confirm-2:confirm_selected:{selected_id}]")],
        resume_data=before,
        jd_data={},
        pending_confirmation={
            "confirm_id": "confirm-2",
            "tool_name": "save_resume_tool",
            "tool_args": {"content": json.dumps(after, ensure_ascii=False), "task_id": "task-1"},
            "changes": changes,
            "base_hash": resume_digest(before),
            "status": "pending",
        },
        user_id=7,
        task_id="task-1",
    )


class ConfirmationFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_clear_field_assignments_use_local_preview_without_llm(self):
        before = resume_payload("原姓名", with_education=True)
        state = AgentState(
            messages=[HumanMessage(content="将姓名改为张伟，将 GPA 改为 3.8/4.0，将目标岗位改为后端开发。")],
            resume_data=before,
            jd_data={},
            user_id=7,
            task_id="task-1",
        )
        self.assertEqual(entry_router(state), "direct_edit")
        candidate = build_local_edit_candidate(state)
        self.assertEqual(candidate["basics"]["name"], "张伟")
        self.assertEqual(candidate["basics"]["target_position"], "后端开发")
        self.assertEqual(candidate["education"][0]["gpa"], "3.8")
        self.assertEqual(candidate["education"][0]["gpa_scale"], "4.0")

        with patch("backend.resume_agent.conversation_llm") as llm:
            result = await direct_edit_node(state)
        llm.ainvoke.assert_not_called()

        self.assertIsNone(result["proposal_error"])
        self.assertIsNotNone(result["pending_confirmation"])
        labels = [change["label"] for change in result["pending_confirmation"]["changes"]]
        self.assertIn("基础信息 · 姓名", labels)
        self.assertIn("基础信息 · 目标岗位", labels)
        self.assertIn("教育经历 1 · GPA", labels)
        self.assertEqual(result["resume_data"]["basics"]["name"], "原姓名")

    async def test_legacy_proposal_node_does_not_call_a_second_model(self):
        state = AgentState(
            messages=[HumanMessage(content="优化项目经历的描述，使其更突出后端性能提升")],
            resume_data=resume_payload("原姓名"),
            jd_data={},
            user_id=7,
            task_id="task-1",
        )
        self.assertEqual(entry_router(state), "conversation_llm")
        with patch("backend.resume_agent.conversation_llm") as fake_llm:
            result = await proposal_generator_node(state)
        fake_llm.ainvoke.assert_not_called()
        self.assertIsNone(result["pending_confirmation"])
        self.assertIn("无法安全生成", result["proposal_error"])

    async def test_legacy_proposal_node_can_execute_structured_operations(self):
        state = AgentState(
            messages=[HumanMessage(content="执行已确认的修改")],
            resume_data=resume_payload("原姓名"), jd_data={}, user_id=7, task_id="task-1",
            context_metadata={
                "resume_operations": [{"op": "set", "path": "basics.name", "value": "新姓名"}],
                "layout_operations": [],
            },
        )
        with patch("backend.resume_agent.conversation_llm") as fake_llm:
            result = await proposal_generator_node(state)
        fake_llm.ainvoke.assert_not_called()
        self.assertIsNone(result["proposal_error"])
        self.assertIsNotNone(result["pending_confirmation"])

    async def test_same_local_value_finishes_without_confirmation(self):
        state = AgentState(
            messages=[HumanMessage(content="把姓名改为张伟")],
            resume_data=resume_payload("张伟"), jd_data={}, user_id=7, task_id="task-1",
        )
        self.assertEqual(entry_router(state), "direct_edit")
        result = await direct_edit_node(state)
        self.assertIsNone(result["pending_confirmation"])
        self.assertIn("已经符合", result["messages"][-1].content)

    async def test_inline_bold_uses_deterministic_preview_without_llm(self):
        before = resume_payload("测试用户")
        before["work_experience"] = [{
            "company_name": "示例科技",
            "job_title": "后端实习生",
            "job_type": "实习",
            "date_range": ["2025.01", "2025.06"],
            "details": [],
            "content_blocks": [{
                "type": "bullet_list", "label": "", "label_bold": True,
                "text": "", "items": ["将接口延迟降低35%"],
            }],
        }]
        state = AgentState(
            messages=[HumanMessage(content="把实习经历中的“接口延迟降低35%”加粗")],
            resume_data=before, jd_data={}, user_id=7, task_id="task-1",
        )

        self.assertEqual(entry_router(state), "direct_edit")
        with patch("backend.resume_agent.conversation_llm") as llm:
            result = await direct_edit_node(state)
        llm.ainvoke.assert_not_called()
        self.assertIsNotNone(result["pending_confirmation"])
        candidate = result["pending_confirmation"]["resume_candidate"]
        self.assertEqual(
            candidate["work_experience"][0]["content_blocks"][0]["items"][0],
            "将**接口延迟降低35%**",
        )
        self.assertEqual(result["resume_data"]["work_experience"][0]["content_blocks"][0]["items"][0], "将接口延迟降低35%")
        self.assertIn("接受前不会保存", result["messages"][-1].content)

    async def test_inline_bold_ambiguity_fails_closed_without_llm_or_confirmation(self):
        before = resume_payload("测试用户")
        before["honors"] = ["持续学习奖"]
        before["self_evaluation"] = ["保持持续学习"]
        state = AgentState(
            messages=[HumanMessage(content="把“持续学习”加粗")],
            resume_data=before, jd_data={}, user_id=7, task_id="task-1",
        )

        with patch("backend.resume_agent.conversation_llm") as llm:
            result = await direct_edit_node(state)
        llm.ainvoke.assert_not_called()
        self.assertIsNone(result["pending_confirmation"])
        self.assertIn("找到 2 处", result["messages"][-1].content)
        self.assertEqual(result["resume_data"]["honors"], ["持续学习奖"])
        self.assertEqual(result["resume_data"]["self_evaluation"], ["保持持续学习"])

    async def test_inline_bold_requires_an_exact_quoted_target(self):
        state = AgentState(
            messages=[HumanMessage(content="把实习经历中的性能提升加粗")],
            resume_data=resume_payload("测试用户"), jd_data={}, user_id=7, task_id="task-1",
        )
        result = await direct_edit_node(state)
        self.assertIsNone(result["pending_confirmation"])
        self.assertIn("请用引号", result["messages"][-1].content)

    async def test_inline_unbold_removes_only_the_selected_run(self):
        before = resume_payload("测试用户")
        before["self_evaluation"] = ["保持**持续学习**和复盘"]
        state = AgentState(
            messages=[HumanMessage(content="把自我评价中的“持续学习”改为普通字重")],
            resume_data=before, jd_data={}, user_id=7, task_id="task-1",
        )
        result = await direct_edit_node(state)
        candidate = result["pending_confirmation"]["resume_candidate"]
        self.assertEqual(candidate["self_evaluation"], ["保持持续学习和复盘"])
        self.assertEqual(result["resume_data"]["self_evaluation"], ["保持**持续学习**和复盘"])

    async def test_font_size_chat_change_redirects_to_modal_without_candidate(self):
        state = AgentState(
            messages=[HumanMessage(content="把正文字号调整为10.5磅")],
            resume_data=resume_payload("测试用户"), jd_data={}, user_id=7, task_id="task-1",
        )
        self.assertEqual(entry_router(state), "direct_edit")
        with patch("backend.resume_agent.conversation_llm") as llm:
            result = await direct_edit_node(state)
        llm.ainvoke.assert_not_called()
        self.assertIsNone(result["pending_confirmation"])
        self.assertIn("设置各部分字号", result["messages"][-1].content)

    async def test_scoped_school_replacement_uses_local_preview_without_touching_honors(self):
        before = resume_payload("测试用户", with_education=True)
        before["honors"] = ["测试大学研究生奖学金"]
        state = AgentState(
            messages=[HumanMessage(content="请修改教育经历：将测试大学调整为中山大学。")],
            resume_data=before, jd_data={}, user_id=7, task_id="task-1",
        )

        self.assertEqual(entry_router(state), "direct_edit")
        candidate = build_local_edit_candidate(state)
        self.assertEqual(candidate["education"][0]["school_name"], "中山大学")
        self.assertEqual(candidate["honors"], ["测试大学研究生奖学金"])
        with patch("backend.resume_agent.conversation_llm") as llm:
            result = await direct_edit_node(state)
        llm.ainvoke.assert_not_called()
        self.assertIsNotNone(result["pending_confirmation"])

    async def test_already_applied_school_replacement_finishes_without_model_or_confirmation(self):
        before = resume_payload("测试用户", with_education=True)
        before["education"][0]["school_name"] = "中山大学"
        state = AgentState(
            messages=[HumanMessage(content="请修改教育经历：将测试大学调整为中山大学。")],
            resume_data=before, jd_data={}, user_id=7, task_id="task-1",
        )

        self.assertEqual(entry_router(state), "direct_edit")
        with patch("backend.resume_agent.conversation_llm") as llm:
            result = await direct_edit_node(state)
        llm.ainvoke.assert_not_called()
        self.assertIsNone(result["pending_confirmation"])
        self.assertIn("已经符合", result["messages"][-1].content)

    def test_ambiguous_gpa_or_percentage_stays_on_structured_path(self):
        state = AgentState(
            messages=[HumanMessage(content="把本科的GPA修改为前10%")],
            resume_data=resume_payload("测试用户", with_education=True),
        )
        self.assertEqual(entry_router(state), "conversation_llm")

    def test_style_and_conversation_requests_do_not_trigger_data_fallback(self):
        self.assertFalse(is_explicit_resume_change_request("字体颜色改成白色"))
        self.assertFalse(is_explicit_resume_change_request("你建议我怎么优化简历？"))
        self.assertTrue(is_explicit_resume_change_request("把目标岗位改成后端开发"))

    async def test_confirm_routes_to_tool_node_and_saves_current_task_once(self):
        state = confirmation_state()
        self.assertEqual(entry_router(state), "tool_node")

        with (
            patch("backend.tools.update_resume", return_value="简历已成功保存") as update,
            patch("backend.resume_agent.record_assistant_revision") as record_revision,
        ):
            result = await tool_node(state)

        update.assert_called_once()
        self.assertEqual(update.call_args.kwargs["user_id"], 7)
        self.assertEqual(update.call_args.kwargs["task_id"], "task-1")
        self.assertEqual(result["resume_data"]["basics"]["name"], "新姓名")
        self.assertIsNone(result["pending_confirmation"])
        self.assertTrue(result["just_saved"])
        self.assertEqual(tool_node_router(AgentState(**result)), END)
        record_revision.assert_called_once()

    async def test_cancel_does_not_write_and_ends_without_another_llm_call(self):
        state = confirmation_state("cancel")

        with patch("backend.tools.update_resume") as update:
            result = await tool_node(state)

        update.assert_not_called()
        self.assertIsNone(result["pending_confirmation"])
        self.assertFalse(result["just_saved"])
        self.assertEqual(result["resume_data"]["basics"]["name"], "原姓名")
        self.assertIsInstance(result["messages"][-1], ToolMessage)
        self.assertEqual(result["messages"][-1].content, "已取消保存")
        self.assertEqual(tool_node_router(AgentState(**result)), END)

    async def test_confirmation_cannot_cross_task_boundaries(self):
        state = confirmation_state(pending_task_id="task-2", state_task_id="task-1")

        with patch("backend.tools.update_resume") as update:
            result = await tool_node(state)

        update.assert_not_called()
        self.assertFalse(result["just_saved"])
        self.assertIn("不属于当前简历任务", result["messages"][-1].content)

    async def test_selective_confirmation_applies_only_selected_change(self):
        state = selective_confirmation_state("change-1")
        with (
            patch("backend.tools.update_resume", return_value="简历已成功保存") as update,
            patch("backend.resume_agent.record_assistant_revision") as record_revision,
        ):
            result = await tool_node(state)

        saved = update.call_args.args[0]
        self.assertEqual(saved["basics"]["name"], "新姓名")
        self.assertEqual(saved["basics"]["target_position"], "开发")
        self.assertTrue(result["messages"][-1].content.startswith("已应用 1 项修改"))
        self.assertIn("基础信息 · 姓名：原姓名 → 新姓名", result["messages"][-1].content)
        record_revision.assert_called_once()

    def test_confirmation_result_cannot_reenter_preview_generator(self):
        state = AgentState(
            messages=[
                HumanMessage(content="把姓名改为张伟"),
                AIMessage(content="请确认"),
                HumanMessage(content="[CONFIRM_REPLY:confirm-1:confirm_all]"),
                ToolMessage(content="已应用 1 项修改", tool_call_id="confirm", name="confirmation_handler"),
                AIMessage(content="修改已生效"),
            ],
            resume_data=resume_payload("张伟"),
        )
        self.assertEqual(route_after_conversation(state), END)

    def test_conversation_without_tool_call_ends_without_second_model_path(self):
        state = AgentState(
            messages=[
                HumanMessage(content="把目标岗位改成后端开发"),
                AIMessage(content="收到", tool_calls=[]),
            ],
            resume_data=resume_payload("测试用户"),
        )
        self.assertEqual(route_after_conversation(state), END)

    async def test_stale_preview_cannot_overwrite_newer_resume(self):
        state = selective_confirmation_state("change-1")
        state.resume_data["basics"]["phone"] = "13800000000"
        with patch("backend.tools.update_resume") as update:
            result = await tool_node(state)
        update.assert_not_called()
        self.assertFalse(result["just_saved"])
        self.assertIn("发生其他修改", result["messages"][-1].content)

    async def test_content_only_confirmation_survives_unrelated_layout_autosave(self):
        state = selective_confirmation_state("change-1")
        base_layout = default_layout_config()
        state.pending_confirmation["base_layout"] = base_layout
        state.pending_confirmation["tool_args"]["layout_content"] = json.dumps(base_layout, ensure_ascii=False)
        state.layout_data = default_layout_config()
        state.layout_data["global"]["moduleMargin"] = 0.8

        with (
            patch("backend.tools.update_resume", return_value="简历已成功保存") as update,
            patch("backend.resume_agent.record_assistant_revision"),
        ):
            result = await tool_node(state)

        update.assert_called_once()
        self.assertTrue(result["just_saved"])


if __name__ == "__main__":
    unittest.main()
