import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage

from backend import main
from backend.layout_config import default_layout_config


def resume_payload():
    return {
        "basics": {
            "name": "测试用户", "gender": "", "phone": "", "email": "",
            "target_position": "后端开发",
        },
        "education": [], "work_experience": [], "project_experience": [],
        "others": {"skills": [], "certificates": [], "languages": []},
        "self_evaluation": [],
    }


def decode_sse(chunks):
    raw = "".join(chunk.decode() if isinstance(chunk, bytes) else chunk for chunk in chunks)
    return [
        json.loads(block[6:]) for block in raw.split("\n\n") if block.startswith("data: ")
    ]


class FakeInterviewGraph:
    async def astream_events(self, initial_state, config=None, version=None):
        assert initial_state["interaction_mode"] == "coaching"
        assert initial_state["interaction_action"] == "start"
        memory = {
            "schema_version": 1,
            "mode": "coaching",
            "verified_facts": [],
            "latest_suggestion": None,
        }
        yield {"event": "on_chain_start", "name": "interview_coach", "data": {}}
        yield {
            "event": "on_chain_end",
            "name": "interview_coach",
            "data": {"output": {
                "messages": list(initial_state["messages"]) + [AIMessage(content="诊断完成。\n\n你负责的核心动作是什么？")],
                "resume_data": initial_state["resume_data"],
                "layout_data": initial_state["layout_data"],
                "pending_confirmation": None,
                "interview_memory": memory,
                "workflow_updates": {
                    "interaction_mode": "coaching",
                    "status": "active",
                    "phase": "questioning",
                    "focus_section": "work_experience",
                    "current_question": "你负责的核心动作是什么？",
                    "last_node": "interview_coach",
                },
            }},
        }


class InterviewApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_interview_mode_emits_recoverable_workflow_state(self):
        db = SimpleNamespace(info={"task_id": "task-1"})
        user = SimpleNamespace(id=7)
        manager = SimpleNamespace(
            load_state=AsyncMock(return_value={}),
            record_turn=AsyncMock(return_value={
                "interaction_mode": "coaching", "status": "active", "phase": "idle",
                "turn_count": 1,
            }),
            update_state=AsyncMock(return_value={
                "interaction_mode": "coaching", "status": "active",
                "phase": "questioning", "focus_section": "work_experience",
                "current_question": "你负责的核心动作是什么？", "turn_count": 1,
            }),
        )
        with (
            patch("backend.main.require_llm_configured"),
            patch("backend.main.graph", FakeInterviewGraph()),
            patch("backend.main.get_workflow_checkpoint_manager", return_value=manager),
            patch("backend.main.get_user_resume", return_value=resume_payload()),
            patch("backend.main.get_user_jd", return_value={}),
            patch("backend.main.get_task_layout_config", return_value=default_layout_config()),
            patch("backend.database.clear_pending_confirmation"),
            patch("backend.database.get_pending_confirmation", return_value=None),
            patch("backend.database.get_agent_memory_state", return_value={
                "summary": "", "recent_messages": [], "version": 0, "interview_memory": {},
            }),
            patch("backend.database.save_agent_memory_state", return_value=1) as save_memory,
            patch("backend.database.save_conversation_context"),
        ):
            response = await main.chat_endpoint(
                message="开始严格拷打",
                files=[],
                session_id="task-1",
                request_id="interview-1",
                interaction_mode="coaching",
                interaction_action="start",
                current_user=user,
                db=db,
            )
            chunks = [chunk async for chunk in response.body_iterator]
            await asyncio.sleep(0)

        events = decode_sse(chunks)
        self.assertEqual(
            [event["type"] for event in events],
            ["progress", "workflow_state", "final", "end"],
        )
        self.assertEqual(events[1]["state"]["phase"], "questioning")
        self.assertEqual(events[1]["state"]["focus_section"], "work_experience")
        self.assertEqual(events[2]["content"], "诊断完成。\n\n你负责的核心动作是什么？")
        manager.record_turn.assert_awaited_once_with(
            7, "task-1", session_id="task-1", request_id="interview-1",
            interaction_mode="coaching",
        )
        self.assertEqual(save_memory.call_args.kwargs["interview_memory"]["mode"], "coaching")

    async def test_invalid_structured_mode_fails_before_graph_execution(self):
        with patch("backend.main.require_llm_configured"):
            response = await main.chat_endpoint(
                message="开始",
                files=[],
                session_id="task-1",
                request_id="invalid-1",
                interaction_mode="unsafe-mode",
                interaction_action="start",
                current_user=SimpleNamespace(id=7),
                db=SimpleNamespace(info={"task_id": "task-1"}),
            )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
