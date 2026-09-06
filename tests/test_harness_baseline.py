import asyncio
import json
import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage, ToolMessage

from backend import main
from backend.database import MemoryVersionConflict
from backend.harness.context import UNVERIFIED_EXECUTION_STATUS, filter_messages_for_llm
from backend.harness.persistence import sanitize_messages_for_persistence, serialize_context_messages
from backend.layout_config import default_layout_config
from backend.resume_agent import AgentState, conversation_node, make_pending_confirmation


def resume_payload(name="测试用户"):
    return {
        "basics": {
            "name": name,
            "gender": "",
            "phone": "",
            "email": "",
            "target_position": "后端开发",
        },
        "education": [],
        "work_experience": [],
        "project_experience": [],
        "others": {"skills": [], "certificates": [], "languages": []},
        "self_evaluation": [],
    }


def decode_sse(chunks):
    events = []
    raw = "".join(
        chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk
        for chunk in chunks
    )
    for block in raw.split("\n\n"):
        if block.startswith("data: "):
            events.append(json.loads(block[6:]))
    return events


class FakeConversationGraph:
    def __init__(self):
        self.last_config = None

    async def astream_events(self, initial_state, config=None, version=None):
        self.last_config = config
        yield {"event": "on_chain_start", "name": "conversation_llm", "data": {}}
        yield {
            "event": "on_chat_model_stream",
            "name": "fake_model",
            "data": {"chunk": AIMessageChunk(content="你")},
        }
        yield {
            "event": "on_chat_model_stream",
            "name": "fake_model",
            "data": {"chunk": AIMessageChunk(content="好")},
        }
        yield {
            "event": "on_chain_end",
            "name": "conversation_llm",
            "data": {
                "output": {
                    "messages": list(initial_state["messages"]) + [AIMessage(content="你好")],
                    "pending_confirmation": None,
                }
            },
        }


class FakeConfirmationGraph:
    def __init__(self, pending):
        self.pending = pending

    async def astream_events(self, initial_state, config=None, version=None):
        yield {"event": "on_chain_start", "name": "direct_edit", "data": {}}
        yield {
            "event": "on_chain_end",
            "name": "direct_edit",
            "data": {
                "output": {
                    "messages": list(initial_state["messages"]) + [
                        AIMessage(content="修改预览已生成")
                    ],
                    "pending_confirmation": self.pending,
                }
            },
        }


class FakeUnverifiedEditGraph:
    async def astream_events(self, initial_state, config=None, version=None):
        yield {"event": "on_chain_start", "name": "conversation_llm", "data": {}}
        yield {
            "event": "on_chat_model_stream",
            "name": "fake_model",
            "data": {"chunk": AIMessageChunk(content="已根据你的要求生成修改预览")},
        }
        yield {
            "event": "on_chain_end",
            "name": "conversation_llm",
            "data": {
                "output": {
                    "messages": list(initial_state["messages"]) + [AIMessage(
                        content="当前尚未生成修改候选。"
                    )],
                    "pending_confirmation": None,
                }
            },
        }


class FakeSkillProgressGraph:
    def __init__(self, tool_name):
        self.tool_name = tool_name

    async def astream_events(self, initial_state, config=None, version=None):
        yield {
            "event": "on_chain_start",
            "name": "tool_node",
            "data": {
                "input": {
                    "messages": [AIMessage(content="", tool_calls=[{
                        "name": self.tool_name,
                        "args": {},
                        "id": f"{self.tool_name}-progress-1",
                        "type": "tool_call",
                    }])],
                },
            },
        }
        yield {
            "event": "on_chain_end",
            "name": "tool_node",
            "data": {
                "output": {
                    "messages": list(initial_state["messages"]) + [AIMessage(content="已完成")],
                    "pending_confirmation": None,
                },
            },
        }


class HarnessBaselineTests(unittest.IsolatedAsyncioTestCase):
    def test_stream_progress_uses_the_actual_skill_tool(self):
        snapshot_event = {
            "data": {
                "input": {
                    "messages": [AIMessage(content="", tool_calls=[{
                        "name": "resume_snapshot",
                        "args": {"reason": "查看字号层级"},
                        "id": "snapshot-progress-1",
                        "type": "tool_call",
                    }])],
                },
            },
        }
        edit_event = {
            "data": {
                "input": {
                    "messages": [AIMessage(content="", tool_calls=[{
                        "name": "resume_edit",
                        "args": {"resume_operations": [], "layout_operations": []},
                        "id": "edit-progress-1",
                        "type": "tool_call",
                    }])],
                },
            },
        }
        loader_event = {
            "data": {
                "input": {
                    "messages": [AIMessage(content="", tool_calls=[{
                        "name": "load_agent_skill",
                        "args": {"name": "resume-edit"},
                        "id": "loader-progress-1",
                        "type": "tool_call",
                    }])],
                },
            },
        }
        coach_event = {
            "data": {
                "input": {
                    "messages": [AIMessage(content="", tool_calls=[{
                        "name": "resume_coach",
                        "args": {"operation": "update"},
                        "id": "coach-progress-1",
                        "type": "tool_call",
                    }])],
                },
            },
        }
        self.assertEqual(main._stream_tool_names(snapshot_event), {"resume_snapshot"})
        self.assertEqual(main._stream_tool_names(edit_event), {"resume_edit"})
        self.assertEqual(main._stream_tool_names(loader_event), {"load_agent_skill"})
        self.assertEqual(main._stream_tool_names(coach_event), {"resume_coach"})

    async def test_empty_tool_assistant_is_never_sent_or_persisted(self):
        messages = [
            HumanMessage(content="请查看当前简历"),
            AIMessage(content="", tool_calls=[{
                "name": "resume_snapshot",
                "args": {"reason": "查看分页"},
                "id": "visual-empty-1",
                "type": "tool_call",
            }]),
            ToolMessage(
                content="已生成当前简历快照",
                tool_call_id="visual-empty-1",
                name="resume_snapshot",
            ),
            AIMessage(content=""),
            AIMessage(content=[]),
            AIMessage(content=[{"type": "text", "text": ""}]),
        ]

        llm_messages = filter_messages_for_llm(messages, just_saved=False)
        self.assertFalse(any(
            isinstance(message, AIMessage) and not str(message.content or "").strip()
            for message in llm_messages
        ))
        self.assertIn("已生成当前简历快照", llm_messages[-1].content)

        durable = sanitize_messages_for_persistence(messages)
        serialized = serialize_context_messages(durable)
        self.assertEqual(serialized, [{
            **HumanMessage(content="请查看当前简历").model_dump(),
            "type": "human",
        }])

    def test_live_tool_protocol_is_preserved_after_latest_user_message(self):
        messages = [
            HumanMessage(content="将姓名改为新姓名"),
            AIMessage(content="", tool_calls=[{
                "name": "load_agent_skill",
                "args": {"name": "resume-edit"},
                "id": "load-edit-1",
                "type": "tool_call",
            }]),
            ToolMessage(
                content="【Agent Skill：resume-edit】\n完整说明",
                tool_call_id="load-edit-1",
                name="load_agent_skill",
            ),
        ]

        filtered = filter_messages_for_llm(
            messages,
            just_saved=False,
            preserve_tool_protocol=True,
        )

        self.assertEqual(filtered, messages)
        self.assertEqual(filtered[1].tool_calls[0]["name"], "load_agent_skill")
        self.assertIsInstance(filtered[2], ToolMessage)

    async def test_http_conversation_sanitizer_drops_stream_and_legacy_empty_assistant(self):
        messages = main.sanitize_conversation_message_dicts([
            {"role": "user", "content": "当前问题"},
            {"role": "assistant", "content": "", "streaming": True},
            {"type": "ai", "content": ""},
            {"role": "assistant", "content": "正常回复"},
        ])
        self.assertEqual(
            [(item.get("role") or item.get("type"), item.get("content")) for item in messages],
            [("user", "当前问题"), ("assistant", "正常回复")],
        )

    async def test_conversation_context_order_and_filtering_contract(self):
        bound_model = SimpleNamespace(
            ainvoke=AsyncMock(return_value=AIMessage(content="本轮回答"))
        )
        fake_llm = SimpleNamespace(
            bind_tools=MagicMock(return_value=bound_model)
        )
        current_resume = resume_payload("数据库姓名")
        current_resume["basics"]["photo"] = "data:image/png;base64,SECRET_IMAGE"
        state = AgentState(
            messages=[
                SystemMessage(content="历史压缩摘要"),
                HumanMessage(content="历史问题"),
                AIMessage(
                    content="历史工具建议",
                    tool_calls=[{
                        "name": "resume_edit",
                        "args": {"content": "{}"},
                        "id": "call-1",
                        "type": "tool_call",
                    }],
                ),
                ToolMessage(
                    content="内部工具结果",
                    tool_call_id="call-1",
                    name="resume_edit",
                ),
                HumanMessage(content="当前问题"),
            ],
            resume_data=current_resume,
            jd_data={"company": "示例公司", "position": "后端开发"},
            user_id=7,
            task_id="task-1",
        )

        with patch("backend.resume_agent.conversation_llm", fake_llm):
            await conversation_node(state)

        fake_llm.bind_tools.assert_called_once()
        sent_messages = bound_model.ainvoke.await_args.args[0]
        self.assertIsInstance(sent_messages[0], SystemMessage)
        self.assertIn("数据库姓名", sent_messages[0].content)
        self.assertIn("示例公司", sent_messages[0].content)
        self.assertIn("当前数据库的唯一事实来源", sent_messages[0].content)
        self.assertNotIn("SECRET_IMAGE", sent_messages[0].content)

        sent_contents = [message.content for message in sent_messages[1:]]
        self.assertEqual(
            sent_contents,
            ["历史压缩摘要", "历史问题", "历史工具建议", "当前问题"],
        )
        self.assertFalse(sent_messages[3].tool_calls)
        self.assertFalse(any(isinstance(message, ToolMessage) for message in sent_messages))

    async def test_explicit_edit_without_tool_call_is_not_retried(self):
        bound_model = SimpleNamespace(
            ainvoke=AsyncMock(return_value=AIMessage(content="请补充希望修改成什么内容。"))
        )
        fake_llm = SimpleNamespace(bind_tools=MagicMock(return_value=bound_model))
        state = AgentState(
            messages=[HumanMessage(content="把姓名改为新姓名")],
            resume_data=resume_payload("旧姓名"),
        )
        with patch("backend.resume_agent.conversation_llm", fake_llm):
            await conversation_node(state)
        bound_model.ainvoke.assert_awaited_once()

    def test_pending_confirmation_payload_contract(self):
        before = resume_payload("原姓名")
        after = resume_payload("新姓名")
        state = AgentState(
            resume_data=before,
            layout_data=default_layout_config(),
            user_id=7,
            task_id="task-1",
        )
        pending = make_pending_confirmation(state, after, default_layout_config())

        self.assertEqual(set(pending), {
            "confirm_id", "content", "options", "task_id",
            "base_version", "resume_candidate", "layout_candidate",
            "changes", "status",
        })
        self.assertEqual(pending["task_id"], "task-1")
        self.assertEqual(pending["status"], "pending")
        self.assertEqual(
            [option["value"] for option in pending["options"]],
            ["confirm", "cancel"],
        )
        self.assertEqual(pending["resume_candidate"]["basics"]["name"], "新姓名")
        self.assertTrue(pending["changes"])

    async def test_chat_sse_event_contract_for_normal_conversation(self):
        db = SimpleNamespace(info={"task_id": "task-1"})
        user = SimpleNamespace(id=7)
        fake_graph = FakeConversationGraph()

        with (
            patch("backend.main.require_llm_configured"),
            patch("backend.main.graph", fake_graph),
            patch("backend.main.get_user_resume", return_value=resume_payload()),
            patch("backend.main.get_user_jd", return_value={}),
            patch("backend.main.get_task_layout_config", return_value=default_layout_config()),
            patch("backend.database.clear_pending_confirmation"),
            patch("backend.database.get_agent_memory_state", return_value={
                "summary": "", "recent_rounds": [], "version": 0,
            }),
            patch("backend.database.get_conversation_context", return_value=[]),
            patch("backend.database.get_pending_confirmation", return_value=None),
            patch("backend.database.find_task_pending_confirmation", return_value=None),
            patch("backend.database.save_agent_memory_state", return_value=1),
            patch("backend.database.save_conversation_context"),
        ):
            response = await main.chat_endpoint(
                message="你好",
                files=[],
                session_id="task-1",
                request_id="request-1",
                current_user=user,
                db=db,
            )
            chunks = [chunk async for chunk in response.body_iterator]
            await asyncio.sleep(0)

        events = decode_sse(chunks)
        self.assertEqual(
            [event["type"] for event in events],
            ["stream", "stream", "final", "end"],
        )
        self.assertEqual([events[0]["content"], events[1]["content"]], ["你", "你好"])
        self.assertEqual(set(events[2]), {
            "type", "content", "session_id", "request_id",
            "layout_config",
        })
        self.assertEqual(events[2]["content"], "你好")
        self.assertEqual(events[2]["session_id"], "task-1")
        self.assertEqual(events[2]["request_id"], "request-1")
        self.assertEqual(set(events[3]), {
            "type", "session_id", "request_id",
            "layout_config",
        })
        self.assertEqual(
            fake_graph.last_config["configurable"]["thread_id"],
            "user:7:task:task-1:session:task-1",
        )

    async def test_chat_discards_buffered_answer_when_resume_changes_mid_turn(self):
        db = SimpleNamespace(info={"task_id": "task-1"}, query=MagicMock())
        user = SimpleNamespace(id=7)
        initial_resume = resume_payload("修改前")
        changed_resume = resume_payload("人工修改后")
        initial_task = SimpleNamespace(
            session_id="task-1", state_sequence=1, layout_config=default_layout_config()
        )
        changed_task = SimpleNamespace(
            session_id="task-1", state_sequence=2, layout_config=default_layout_config()
        )
        fresh_db = SimpleNamespace(info={}, close=MagicMock())
        task_calls = {"count": 0}

        def current_task(*_args, **_kwargs):
            task_calls["count"] += 1
            return changed_task if task_calls["count"] > 2 else initial_task

        with (
            patch("backend.main.require_llm_configured"),
            patch("backend.main.graph", FakeConversationGraph()),
            patch("backend.main.get_context_by_session", return_value=SimpleNamespace(
                status="active", context_type="main", metadata_json={}
            )),
            patch("backend.main.get_resume_task", side_effect=current_task),
            patch("backend.main.get_user_resume", side_effect=[initial_resume, changed_resume]),
            patch("backend.main.get_user_jd", return_value={}),
            patch("backend.main.get_user_photo", return_value=""),
            patch("backend.main.get_task_layout_config", return_value=default_layout_config()),
            patch("backend.database.SessionLocal", return_value=fresh_db),
            patch("backend.database.clear_pending_confirmation"),
            patch("backend.database.get_pending_confirmation", return_value=None),
            patch("backend.database.get_agent_memory_state", return_value={
                "summary": "", "recent_rounds": [], "version": 0,
            }),
            patch("backend.main.get_agent_skill_state", return_value={"state": {}, "version": 0}),
            patch("backend.main.persist_turn_state", new_callable=AsyncMock),
        ):
            response = await main.chat_endpoint(
                message="请分析当前简历",
                files=[],
                session_id="task-1",
                request_id="request-stale-answer",
                current_user=user,
                db=db,
            )
            events = decode_sse([chunk async for chunk in response.body_iterator])

        self.assertEqual([event["type"] for event in events], ["final", "end"])
        self.assertIn("本轮回答期间简历已发生其他修改", events[0]["content"])

    async def test_chat_progress_reports_the_actual_non_edit_skill_stage(self):
        progress_cases = {
            "load_agent_skill": "loading_skill",
            "resume_snapshot": "snapshot",
            "resume_coach": "coaching",
        }
        for tool_name, expected_phase in progress_cases.items():
            db = SimpleNamespace(info={"task_id": "task-1"})
            user = SimpleNamespace(id=7)
            with (
                patch("backend.main.require_llm_configured"),
                patch("backend.main.graph", FakeSkillProgressGraph(tool_name)),
                patch("backend.main.get_user_resume", return_value=resume_payload()),
                patch("backend.main.get_user_jd", return_value={}),
                patch("backend.main.get_task_layout_config", return_value=default_layout_config()),
                patch("backend.database.clear_pending_confirmation"),
                patch("backend.database.get_agent_memory_state", return_value={
                    "summary": "", "recent_rounds": [], "version": 0,
                }),
                patch("backend.database.get_conversation_context", return_value=[]),
                patch("backend.database.get_pending_confirmation", return_value=None),
                patch("backend.database.find_task_pending_confirmation", return_value=None),
                patch("backend.database.save_agent_memory_state", return_value=1),
                patch("backend.database.save_conversation_context"),
            ):
                response = await main.chat_endpoint(
                    message="你好",
                    files=[],
                    session_id="task-1",
                    request_id=f"request-{tool_name}",
                    current_user=user,
                    db=db,
                )
                events = decode_sse([chunk async for chunk in response.body_iterator])

            self.assertEqual(events[0]["type"], "progress")
            self.assertEqual(events[0]["phase"], expected_phase)
            self.assertEqual([event["type"] for event in events[-2:]], ["final", "end"])

    async def test_chat_sse_event_contract_for_confirmation_preview(self):
        before = resume_payload("原姓名")
        after = resume_payload("新姓名")
        pending = make_pending_confirmation(
            AgentState(
                resume_data=before,
                layout_data=default_layout_config(),
                user_id=7,
                task_id="task-1",
            ),
            after,
            default_layout_config(),
        )
        db = SimpleNamespace(info={"task_id": "task-1"})
        user = SimpleNamespace(id=7)

        with (
            patch("backend.main.require_llm_configured"),
            patch("backend.main.graph", FakeConfirmationGraph(pending)),
            patch("backend.main.get_user_resume", return_value=before),
            patch("backend.main.get_user_jd", return_value={}),
            patch("backend.main.get_task_layout_config", return_value=default_layout_config()),
            patch("backend.database.clear_pending_confirmation"),
            patch("backend.database.get_agent_memory_state", return_value={
                "summary": "", "recent_rounds": [], "version": 0,
            }),
            patch("backend.database.get_conversation_context", return_value=[]),
            patch("backend.database.get_pending_confirmation", return_value=None),
            patch("backend.database.find_task_pending_confirmation", return_value=None),
            patch("backend.database.save_agent_memory_state", return_value=1),
            patch("backend.database.save_conversation_context"),
        ):
            response = await main.chat_endpoint(
                message="把姓名改成新姓名",
                files=[],
                session_id="task-1",
                request_id="request-confirm",
                current_user=user,
                db=db,
            )
            chunks = [chunk async for chunk in response.body_iterator]
            await asyncio.sleep(0)

        events = decode_sse(chunks)
        self.assertEqual(
            [event["type"] for event in events],
            ["progress", "progress", "progress", "stream", "confirm", "final", "end"],
        )
        self.assertEqual(events[3]["content"], "修改预览已生成")
        self.assertEqual(
            [events[index]["phase"] for index in (0, 1, 2)],
            ["building_preview", "validating", "ready"],
        )
        self.assertEqual(set(events[4]), {
            "type", "request_id", "id", "content", "options", "changes",
            "resume_candidate", "layout_candidate", "confirm_id", "session_id",
        })
        self.assertEqual(events[4]["confirm_id"], pending["confirm_id"])
        self.assertEqual(events[4]["resume_candidate"]["basics"]["name"], "新姓名")
        self.assertEqual(events[5]["content"], "修改预览已生成")

    async def test_explicit_edit_never_exposes_unverified_model_stream(self):
        db = SimpleNamespace(info={"task_id": "task-1"})
        user = SimpleNamespace(id=7)

        with (
            patch("backend.main.require_llm_configured"),
            patch("backend.main.graph", FakeUnverifiedEditGraph()),
            patch("backend.main.get_user_resume", return_value=resume_payload()),
            patch("backend.main.get_user_jd", return_value={}),
            patch("backend.main.get_task_layout_config", return_value=default_layout_config()),
            patch("backend.database.clear_pending_confirmation"),
            patch("backend.database.get_agent_memory_state", return_value={
                "summary": "", "recent_rounds": [], "version": 0,
            }),
            patch("backend.database.get_conversation_context", return_value=[]),
            patch("backend.database.get_pending_confirmation", return_value=None),
            patch("backend.database.find_task_pending_confirmation", return_value=None),
            patch("backend.database.save_agent_memory_state", return_value=1),
            patch("backend.database.save_conversation_context"),
        ):
            response = await main.chat_endpoint(
                message="将本科的暨南大学改为中山大学",
                files=[],
                session_id="task-1",
                request_id="request-unverified-edit",
                current_user=user,
                db=db,
            )
            chunks = [chunk async for chunk in response.body_iterator]

        events = decode_sse(chunks)
        self.assertEqual([event["type"] for event in events], ["final", "end"])
        self.assertEqual(events[0]["content"], UNVERIFIED_EXECUTION_STATUS)

    async def test_contextual_edit_never_exposes_unverified_model_stream(self):
        db = SimpleNamespace(info={"task_id": "task-1"})
        user = SimpleNamespace(id=7)

        with (
            patch("backend.main.require_llm_configured"),
            patch("backend.main.graph", FakeUnverifiedEditGraph()),
            patch("backend.main.get_user_resume", return_value=resume_payload()),
            patch("backend.main.get_user_jd", return_value={}),
            patch("backend.main.get_task_layout_config", return_value=default_layout_config()),
            patch("backend.database.clear_pending_confirmation"),
            patch("backend.database.get_agent_memory_state", return_value={
                "summary": "", "recent_rounds": [], "version": 0,
            }),
            patch("backend.database.get_conversation_context", return_value=[]),
            patch("backend.database.get_pending_confirmation", return_value=None),
            patch("backend.database.find_task_pending_confirmation", return_value=None),
            patch("backend.database.save_agent_memory_state", return_value=1),
            patch("backend.database.save_conversation_context"),
        ):
            response = await main.chat_endpoint(
                message="按你认为合理的顺序调整",
                files=[],
                session_id="task-1",
                request_id="request-contextual-unverified-edit",
                current_user=user,
                db=db,
            )
            chunks = [chunk async for chunk in response.body_iterator]

        events = decode_sse(chunks)
        self.assertEqual([event["type"] for event in events], ["final", "end"])
        self.assertEqual(events[0]["content"], UNVERIFIED_EXECUTION_STATUS)

    async def test_chat_reports_persistence_conflict_before_final_and_end(self):
        db = SimpleNamespace(info={"task_id": "task-1"})
        user = SimpleNamespace(id=7)

        with (
            patch("backend.main.require_llm_configured"),
            patch("backend.main.graph", FakeConversationGraph()),
            patch("backend.main.get_user_resume", return_value=resume_payload()),
            patch("backend.main.get_user_jd", return_value={}),
            patch("backend.main.get_task_layout_config", return_value=default_layout_config()),
            patch("backend.database.clear_pending_confirmation"),
            patch("backend.database.get_agent_memory_state", return_value={
                "summary": "", "recent_rounds": [], "version": 3,
            }),
            patch("backend.database.get_pending_confirmation", return_value=None),
            patch(
                "backend.database.save_agent_memory_state",
                side_effect=MemoryVersionConflict("记忆状态版本已变化"),
            ),
            patch("backend.database.save_conversation_context") as save_legacy,
        ):
            response = await main.chat_endpoint(
                message="你好",
                files=[],
                session_id="task-1",
                request_id="request-conflict",
                current_user=user,
                db=db,
            )
            chunks = [chunk async for chunk in response.body_iterator]

        events = decode_sse(chunks)
        event_types = [event["type"] for event in events]
        self.assertEqual(
            event_types,
            ["stream", "stream", "persistence_error", "final", "end"],
        )
        self.assertTrue(events[2]["retryable"])
        self.assertEqual(events[2]["request_id"], "request-conflict")
        save_legacy.assert_not_called()

    async def test_confirm_and_undo_endpoint_success_contracts(self):
        before = resume_payload("原姓名")
        after = resume_payload("新姓名")
        pending = make_pending_confirmation(
            AgentState(
                resume_data=before,
                layout_data=default_layout_config(),
                user_id=7,
                task_id="task-1",
            ),
            after,
            default_layout_config(),
        )
        db = SimpleNamespace(info={"task_id": "task-1"})
        user = SimpleNamespace(id=7)

        with (
            patch("backend.database.get_pending_confirmation", return_value=pending),
            patch("backend.database.clear_pending_confirmation") as clear_pending,
            patch("backend.database.record_resume_revision") as record_revision,
            patch("backend.database.update_conversation_context_metadata"),
            patch("backend.tools.update_resume", return_value="简历已成功保存"),
            patch("backend.main.release_resume_edit_lock"),
            patch("backend.main.get_resume_task", return_value=SimpleNamespace(
                resume_data=before,
                layout_config=default_layout_config(),
            )),
        ):
            response = await main.confirm_endpoint(
                confirm_id=pending["confirm_id"],
                action="confirm",
                session_id="task-1",
                current_user=user,
                db=db,
            )

        confirm_payload = json.loads(response.body)
        self.assertEqual(set(confirm_payload), {
            "success", "message", "action", "revision_id", "resume_data", "layout_config", "selected_change_ids",
        })
        self.assertTrue(confirm_payload["success"])
        self.assertEqual(confirm_payload["action"], "saved")
        self.assertEqual(confirm_payload["resume_data"]["basics"]["name"], "新姓名")
        clear_pending.assert_called_once_with(db, 7, "task-1")
        record_revision.assert_called_once()

        layout = default_layout_config()
        with patch(
            "backend.main.undo_latest_resume_revision",
            return_value=("undone", before, layout),
        ):
            undo_payload = await main.undo_task_resume_change(
                "task-1", db=db, current_user=user
            )
        self.assertEqual(set(undo_payload), {
            "success", "message", "resume_data", "layout_config",
        })
        self.assertTrue(undo_payload["success"])
        self.assertEqual(undo_payload["message"], "已撤回本次修改")
        self.assertEqual(undo_payload["resume_data"], before)
        self.assertEqual(undo_payload["layout_config"], layout)

    async def test_confirm_endpoint_applies_only_selected_content_change(self):
        before = resume_payload("原姓名")
        before["basics"]["target_position"] = "开发"
        after = resume_payload("新姓名")
        after["basics"]["target_position"] = "后端开发"
        pending = make_pending_confirmation(
            AgentState(
                resume_data=before,
                layout_data=default_layout_config(),
                user_id=7,
                task_id="task-1",
            ),
            after,
            default_layout_config(),
        )
        selected_id = next(
            change["id"]
            for change in pending["changes"]
            if change.get("path") == ["basics", "name"]
        )
        db = SimpleNamespace(info={"task_id": "task-1"})
        user = SimpleNamespace(id=7)

        with (
            patch("backend.database.get_pending_confirmation", return_value=pending),
            patch("backend.database.clear_pending_confirmation"),
            patch("backend.database.record_resume_revision"),
            patch("backend.database.update_conversation_context_metadata"),
            patch("backend.tools.update_resume", return_value="简历已成功保存") as update,
            patch("backend.main.release_resume_edit_lock"),
            patch("backend.main.get_resume_task", return_value=SimpleNamespace(
                resume_data=before,
                layout_config=default_layout_config(),
            )),
        ):
            response = await main.confirm_endpoint(
                confirm_id=pending["confirm_id"],
                action="confirm_selected",
                session_id="task-1",
                selected_change_ids=selected_id,
                current_user=user,
                db=db,
            )

        payload = json.loads(response.body)
        saved_resume = update.call_args.args[0]
        self.assertTrue(payload["success"])
        self.assertEqual(payload["selected_change_ids"], [selected_id])
        self.assertEqual(saved_resume["basics"]["name"], "新姓名")
        self.assertEqual(saved_resume["basics"]["target_position"], "开发")

    async def test_direct_replace_builds_one_literal_preview_without_llm(self):
        before = resume_payload("广东工业大学")
        task = SimpleNamespace(
            session_id="task-1",
            resume_data=before,
            layout_config=default_layout_config(),
        )
        db = SimpleNamespace(info={"task_id": "task-1"})
        user = SimpleNamespace(id=7)
        request = main.DirectReplaceRequest(
            session_id="task-1",
            scope="basics",
            original_text="广东工业大学",
            target_text="暨南大学",
        )

        with (
            patch("backend.main.get_resume_task", return_value=task),
            patch("backend.database.find_task_pending_confirmation", return_value=None),
            patch("backend.database.get_conversation_context", return_value=[]),
            patch("backend.database.save_conversation_context") as save_pending,
        ):
            payload = await main.direct_replace_preview(
                "task-1", request, db=db, current_user=user
            )

        self.assertTrue(payload["success"])
        self.assertEqual(payload["resume_candidate"]["basics"]["name"], "暨南大学")
        self.assertEqual(len(payload["changes"]), 1)
        save_pending.assert_called_once()

    async def test_direct_replace_duplicate_matches_are_selectable(self):
        before = resume_payload()
        before["education"] = [
            {"school_name": "广东工业大学", "degree": "本科"},
            {"school_name": "广东工业大学", "degree": "硕士"},
        ]
        task = SimpleNamespace(
            session_id="task-1",
            resume_data=before,
            layout_config=default_layout_config(),
        )
        db = SimpleNamespace(info={"task_id": "task-1"})
        user = SimpleNamespace(id=7)
        request = main.DirectReplaceRequest(
            session_id="task-1",
            scope="education",
            original_text="广东工业大学",
            target_text="暨南大学",
        )

        with (
            patch("backend.main.get_resume_task", return_value=task),
            patch("backend.database.find_task_pending_confirmation", return_value=None),
            patch("backend.database.get_conversation_context", return_value=[]),
            patch("backend.database.save_conversation_context") as save_pending,
        ):
            payload = await main.direct_replace_preview(
                "task-1", request, db=db, current_user=user
            )

        self.assertTrue(payload["success"])
        self.assertEqual(len(payload["changes"]), 2)
        self.assertIn("找到 2 处相同内容", payload["content"])
        pending = save_pending.call_args.args[4]
        selected_id = next(
            change["id"]
            for change in pending["changes"]
            if change["path"] == ["education", 0, "school_name"]
        )

        with (
            patch("backend.database.get_pending_confirmation", return_value=pending),
            patch("backend.database.clear_pending_confirmation"),
            patch("backend.database.record_resume_revision"),
            patch("backend.database.update_conversation_context_metadata"),
            patch("backend.tools.update_resume", return_value="简历已成功保存") as update,
            patch("backend.main.release_resume_edit_lock"),
            patch("backend.main.get_resume_task", return_value=task),
        ):
            response = await main.confirm_endpoint(
                confirm_id=pending["confirm_id"],
                action="confirm_selected",
                session_id="task-1",
                selected_change_ids=selected_id,
                current_user=user,
                db=db,
            )

        self.assertTrue(json.loads(response.body)["success"])
        saved_resume = update.call_args.args[0]
        self.assertEqual(saved_resume["education"][0]["school_name"], "暨南大学")
        self.assertEqual(saved_resume["education"][1]["school_name"], "广东工业大学")

    async def test_direct_replace_repeated_text_in_one_field_stays_grouped(self):
        before = resume_payload()
        before["self_evaluation"] = ["持续学习、持续复盘"]
        task = SimpleNamespace(
            session_id="task-1",
            resume_data=before,
            layout_config=default_layout_config(),
        )
        db = SimpleNamespace(info={"task_id": "task-1"})
        user = SimpleNamespace(id=7)
        request = main.DirectReplaceRequest(
            session_id="task-1",
            scope="self_evaluation",
            original_text="持续",
            target_text="主动",
        )

        with (
            patch("backend.main.get_resume_task", return_value=task),
            patch("backend.database.find_task_pending_confirmation", return_value=None),
            patch("backend.database.get_conversation_context", return_value=[]),
            patch("backend.database.save_conversation_context"),
        ):
            payload = await main.direct_replace_preview(
                "task-1", request, db=db, current_user=user
            )

        self.assertTrue(payload["success"])
        self.assertEqual(len(payload["changes"]), 1)
        self.assertIn("均位于同一字段", payload["content"])
        self.assertEqual(payload["resume_candidate"]["self_evaluation"], ["主动学习、主动复盘"])

    def test_direct_replace_scopes_are_precise_and_include_contextual_sections(self):
        current = {
            "education": [],
            "education_supplement": ["补充"],
            "others": {
                "skills": ["Python"],
                "certificates": ["CET-6"],
                "languages": ["英语"],
                "field_labels": {"certificates": "证书", "languages": "语言"},
            },
            "custom_sections": [
                {"title": "开源实践", "items": ["项目 A"]},
                {"title": "校园活动", "items": ["活动 B"]},
            ],
        }
        self.assertEqual(
            main._direct_replace_scope_paths("education", current),
            (("education",), ("education_supplement",)),
        )
        self.assertEqual(
            main._direct_replace_scope_paths("skills", current),
            (("others", "skills"),),
        )
        self.assertEqual(
            main._direct_replace_scope_paths("custom_sections:1", current),
            (("custom_sections", 1),),
        )

    def test_direct_replace_path_helpers_only_change_the_selected_subtree(self):
        current = {
            "others": {"skills": ["Python"], "certificates": ["Python 证书"]},
        }
        path = ("others", "skills")
        replaced, count = main._replace_unique_resume_text(
            main._direct_replace_path_value(current, path), "Python", "Go",
        )
        candidate = main._set_direct_replace_path(deepcopy(current), path, replaced)
        self.assertEqual(count, 1)
        self.assertEqual(candidate["others"]["skills"], ["Go"])
        self.assertEqual(candidate["others"]["certificates"], ["Python 证书"])


if __name__ == "__main__":
    unittest.main()
