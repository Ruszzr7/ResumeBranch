import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from backend.layout_config import default_layout_config
from backend.resume_agent import (
    AgentState,
    build_local_layout_candidate,
    direct_edit_node,
    entry_router,
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
            "gpa": "3.5", "gpa_scale": "4.0", "ranking": "", "average_score": "", "theses": [],
        }],
        "work_experience": [], "project_experience": [],
        "others": {"skills": [], "certificates": [], "languages": []},
        "self_evaluation": [],
    }


class LayoutConversationTests(unittest.IsolatedAsyncioTestCase):
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

    async def test_mixed_content_and_layout_request_uses_one_local_preview(self):
        state = AgentState(
            messages=[HumanMessage(content="把姓名改为张伟，学校标签不要黑底")],
            resume_data=resume_payload(), layout_data=default_layout_config(),
            user_id=7, task_id="task-1",
        )
        self.assertEqual(entry_router(state), "direct_edit")
        result = await direct_edit_node(state)
        self.assertEqual(result["pending_confirmation"]["resume_candidate"]["basics"]["name"], "张伟")
        kinds = [item.get("kind", "content") for item in result["pending_confirmation"]["changes"]]
        self.assertIn("content", kinds)
        self.assertIn("layout", kinds)

    async def test_complex_combined_request_uses_exactly_one_model_call(self):
        state = AgentState(
            messages=[HumanMessage(content="重新组织项目经历描述，并将它放到教育经历前面")],
            resume_data=resume_payload(), layout_data=default_layout_config(),
            user_id=7, task_id="task-1",
        )
        resume_after = resume_payload()
        resume_after["project_experience"] = [{
            "project_name": "项目A", "role": "开发", "date_range": [], "details": ["完成接口优化"]
        }]
        layout_after = default_layout_config()
        order = layout_after["global"]["sectionOrder"]
        order.remove("project_experience")
        order.insert(0, "project_experience")
        response = {"resume_data": resume_after, "layout_config": layout_after}
        fake_llm = SimpleNamespace(ainvoke=AsyncMock(return_value=AIMessage(content=json.dumps(response, ensure_ascii=False))))
        with patch("backend.resume_agent.conversation_llm", fake_llm):
            result = await proposal_generator_node(state)
        fake_llm.ainvoke.assert_awaited_once()
        ids = [item["id"] for item in result["pending_confirmation"]["changes"]]
        self.assertIn("layout-global", ids)
        self.assertTrue(any(not value.startswith("layout-") for value in ids))

    async def test_selecting_layout_group_persists_only_that_group(self):
        before_layout = default_layout_config()
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
