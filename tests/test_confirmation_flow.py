import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END

from backend.resume_agent import (
    AgentState,
    build_local_edit_candidate,
    direct_edit_node,
    entry_router,
    is_explicit_resume_change_request,
    route_after_conversation,
    skill_runtime,
)


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

        with (
            patch("backend.resume_agent.conversation_llm") as llm,
            patch("backend.resume_agent.skill_runtime.invoke", wraps=skill_runtime.invoke) as invoke,
        ):
            result = await direct_edit_node(state)
        llm.ainvoke.assert_not_called()
        invoke.assert_awaited_once()
        self.assertEqual(invoke.await_args.args[0], "resume-edit")

        self.assertIsNone(result["proposal_error"])
        self.assertIsNotNone(result["pending_confirmation"])
        labels = [change["label"] for change in result["pending_confirmation"]["changes"]]
        self.assertIn("基础信息 · 姓名", labels)
        self.assertIn("基础信息 · 目标岗位", labels)
        self.assertIn("教育经历 1 · GPA", labels)
        self.assertEqual(result["resume_data"]["basics"]["name"], "原姓名")

    async def test_local_field_assignment_preserves_whole_field_bold(self):
        before = resume_payload("**原姓名**", with_education=True)
        state = AgentState(
            messages=[HumanMessage(content="将姓名改为新姓名。")],
            resume_data=before,
            jd_data={},
            user_id=7,
            task_id="task-1",
        )

        candidate = build_local_edit_candidate(state)

        self.assertEqual(candidate["basics"]["name"], "**新姓名**")

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

    def test_conversation_without_tool_call_ends_without_second_model_path(self):
        state = AgentState(
            messages=[
                HumanMessage(content="把目标岗位改成后端开发"),
                AIMessage(content="收到", tool_calls=[]),
            ],
            resume_data=resume_payload("测试用户"),
        )
        self.assertEqual(route_after_conversation(state), END)

if __name__ == "__main__":
    unittest.main()
