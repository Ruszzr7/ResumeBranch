import json
import unittest
from unittest.mock import patch

from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.graph import END

from backend.resume_agent import AgentState, entry_router, tool_node, tool_node_router


def resume_payload(name="测试用户"):
    return {
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


class ConfirmationFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_confirm_routes_to_tool_node_and_saves_current_task_once(self):
        state = confirmation_state()
        self.assertEqual(entry_router(state), "tool_node")

        with patch("backend.tools.update_resume", return_value="简历已成功保存") as update:
            result = await tool_node(state)

        update.assert_called_once()
        self.assertEqual(update.call_args.kwargs["user_id"], 7)
        self.assertEqual(update.call_args.kwargs["task_id"], "task-1")
        self.assertEqual(result["resume_data"]["basics"]["name"], "新姓名")
        self.assertIsNone(result["pending_confirmation"])
        self.assertTrue(result["just_saved"])

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


if __name__ == "__main__":
    unittest.main()
