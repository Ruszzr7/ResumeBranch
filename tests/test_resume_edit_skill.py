import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from backend.layout_config import default_layout_config
from backend.resume_agent import AgentState, entry_router, is_mission_resume_edit_request, tool_node
from backend.skills.resume_edit import (
    ResumeEditOperationError,
    ResumeEditRequest,
    run_resume_edit,
)


def resume_payload():
    return {
        "basics": {"name": "旧姓名", "target_position": "后端开发"},
        "education": [],
        "project_experience": [{
            "project_name": "项目 A",
            "role": "开发",
            "date_range": [],
            "content_blocks": [{
                "type": "bullet_list",
                "semantic_role": "generic",
                "label": "",
                "label_bold": False,
                "text": "",
                "items": ["第一条", "第二条", "第三条"],
            }],
        }],
    }


class ResumeEditSkillTests(unittest.IsolatedAsyncioTestCase):
    def test_mission_follow_up_uses_the_edit_router(self):
        self.assertTrue(is_mission_resume_edit_request("执行第 1 点", "layout"))
        self.assertFalse(is_mission_resume_edit_request("分析第 1 点", "layout"))
        state = AgentState(messages=[HumanMessage(content="执行第 1 点")], context_type="layout")
        self.assertEqual(entry_router(state), "conversation_llm")

    async def test_structured_content_operation_is_deterministic_and_does_not_call_llm(self):
        llm = SimpleNamespace(ainvoke=AsyncMock())
        result = await run_resume_edit(
            ResumeEditRequest(
                resume_data=resume_payload(),
                layout_config=default_layout_config(),
                resume_operations=({
                    "op": "set", "path": "basics.name", "value": "新姓名", "expected": "旧姓名",
                },),
            ),
            llm,
        )
        self.assertEqual(result.resume_data["basics"]["name"], "新姓名")
        llm.ainvoke.assert_not_awaited()

    async def test_list_operations_support_move_insert_and_remove(self):
        result = await run_resume_edit(
            ResumeEditRequest(
                resume_data=resume_payload(),
                layout_config=default_layout_config(),
                resume_operations=(
                    {"op": "move", "path": "project_experience[0].content_blocks[0].items", "from_index": 0, "to_index": 2},
                    {"op": "insert", "path": "project_experience[0].content_blocks[0].items", "index": 1, "value": "新增"},
                    {"op": "remove", "path": "project_experience[0].content_blocks[0].items", "index": 2, "expected": "第三条"},
                ),
            )
        )
        self.assertEqual(
            result.resume_data["project_experience"][0]["content_blocks"][0]["items"],
            ["第二条", "新增", "第一条"],
        )

    async def test_layout_operation_is_supported_but_font_sizes_are_rejected(self):
        result = await run_resume_edit(
            ResumeEditRequest(
                resume_data=resume_payload(),
                layout_config=default_layout_config(),
                layout_operations=({"op": "set", "path": "global.moduleMargin", "value": 0.7},),
            )
        )
        self.assertEqual(result.layout_config["global"]["moduleMargin"], 0.7)
        with self.assertRaises(ResumeEditOperationError):
            await run_resume_edit(
                ResumeEditRequest(
                    resume_data=resume_payload(),
                    layout_config=default_layout_config(),
                    layout_operations=({"op": "set", "path": "global.fontSize", "value": 12},),
                )
            )

    async def test_raw_instruction_fails_closed_without_model_retry(self):
        llm = SimpleNamespace(ainvoke=AsyncMock())
        with self.assertRaises(ResumeEditOperationError):
            await run_resume_edit(
                ResumeEditRequest(
                    request_text="执行第 1 点",
                    resume_data=resume_payload(),
                    layout_config=default_layout_config(),
                ),
                llm,
            )
        llm.ainvoke.assert_not_awaited()

    async def test_structured_tool_call_creates_existing_confirmation_preview(self):
        state = AgentState(
            messages=[
                HumanMessage(content="把姓名改为新姓名"),
                AIMessage(content="", tool_calls=[{
                    "name": "request_resume_edit",
                    "args": {
                        "resume_operations": [{
                            "op": "set", "path": "basics.name", "value": "新姓名", "expected": "旧姓名",
                        }],
                        "layout_operations": [],
                    },
                    "id": "edit-1",
                }]),
            ],
            resume_data=resume_payload(),
            layout_data=default_layout_config(),
            user_id=1,
            task_id="task-1",
        )
        with patch("backend.resume_agent.conversation_llm") as llm:
            result = await tool_node(state)
        self.assertIsNotNone(result["pending_confirmation"])
        self.assertEqual(
            result["pending_confirmation"]["resume_candidate"]["basics"]["name"],
            "新姓名",
        )
        llm.ainvoke.assert_not_called()


if __name__ == "__main__":
    unittest.main()
