import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import (
    AgentMemoryState,
    Base,
    MemoryVersionConflict,
    ProjectTask,
    ResumeProject,
    delete_conversation_context,
    get_agent_memory_state,
    save_agent_memory_state,
    update_agent_memory_round_outcome,
)
from backend.harness.memory import (
    build_conversation_round,
    normalize_memory_summary,
    serialize_memory_summary,
)


class AgentMemoryStateTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.project = ResumeProject(id="project-1", user_id=1, title="测试")
        self.task = ProjectTask(
            id="task-1",
            project_id="project-1",
            user_id=1,
            title="基础简历",
            is_base=True,
            session_id="task-1",
            compressed_context=[],
        )
        self.db.add_all([self.project, self.task])
        self.db.commit()
        self.db.info["task_id"] = "task-1"

    def tearDown(self):
        self.db.close()

    def test_legacy_flat_context_is_not_loaded_into_round_memory(self):
        self.task.compressed_context = [
            {"type": "systemmessage", "content": "历史摘要"},
            {"type": "human", "content": "最近问题"},
            {"type": "ai", "content": "最近回答"},
        ]
        self.db.commit()

        state = get_agent_memory_state(self.db, 1, "task-1")

        self.assertEqual(state["summary"], "")
        self.assertEqual(state["recent_rounds"], [])
        self.assertEqual(state["version"], 0)
        self.assertEqual(self.db.query(AgentMemoryState).count(), 0)

    def test_legacy_agent_memory_discards_its_stale_summary(self):
        self.db.add(AgentMemoryState(
            scope_id="task:task-1",
            user_id=1,
            task_id="task-1",
            session_id="task-1",
            summary="撤回前仍需修改学校",
            recent_messages=[
                {"type": "human", "content": "将本科改为中山大学"},
                {"type": "ai", "content": "已生成修改预览"},
            ],
            version=3,
        ))
        self.db.commit()

        state = get_agent_memory_state(self.db, 1, "task-1")

        self.assertEqual(state["summary"], "")
        self.assertEqual(state["recent_rounds"], [])
        self.assertEqual(state["version"], 3)

    def test_unversioned_summary_is_ignored_while_structured_rounds_remain(self):
        round_data = build_conversation_round(
            "round-1", input_type="chat", input_content="最近问题",
        )
        self.db.add(AgentMemoryState(
            scope_id="task:task-1",
            user_id=1,
            task_id="task-1",
            session_id="task-1",
            summary="山东大学和中山大学存在冲突",
            recent_messages=[round_data],
            version=3,
        ))
        self.db.commit()

        state = get_agent_memory_state(self.db, 1, "task-1")

        self.assertEqual(normalize_memory_summary(state["summary"])["events"], [])
        self.assertEqual([item["round_id"] for item in state["recent_rounds"]], ["round-1"])

    def test_optimistic_version_rejects_stale_overwrite(self):
        first_version = save_agent_memory_state(
            self.db,
            1,
            "task-1",
            "第一版",
            [build_conversation_round("round-1", input_type="chat", input_content="first")],
            0,
        )
        self.assertEqual(first_version, 1)

        with self.assertRaises(MemoryVersionConflict):
            save_agent_memory_state(
                self.db,
                1,
                "task-1",
                "过期版本",
                [build_conversation_round("round-2", input_type="chat", input_content="stale")],
                0,
            )

        state = get_agent_memory_state(self.db, 1, "task-1")
        self.assertEqual(normalize_memory_summary(state["summary"])["events"], [])
        self.assertEqual(state["version"], 1)

        second_version = save_agent_memory_state(
            self.db,
            1,
            "task-1",
            "第二版",
            [build_conversation_round("round-2", input_type="chat", input_content="second")],
            1,
        )
        self.assertEqual(second_version, 2)

    def test_deleting_context_removes_layered_and_legacy_memory(self):
        self.task.compressed_context = [{"type": "human", "content": "legacy"}]
        self.db.commit()
        save_agent_memory_state(
            self.db,
            1,
            "task-1",
            "summary",
            [build_conversation_round("round-1", input_type="chat", input_content="recent")],
            0,
        )

        delete_conversation_context(self.db, 1, "task-1")

        self.db.refresh(self.task)
        self.assertEqual(self.task.compressed_context, [])
        self.assertEqual(self.db.query(AgentMemoryState).count(), 0)

    def test_confirm_and_undo_update_the_originating_round(self):
        round_data = build_conversation_round(
            "request-1",
            input_type="chat",
            input_content="把姓名改为张三",
            status="preview_pending",
            outcome_type="resume_edit",
            outcome={"confirm_id": "confirm-1", "changes": [{"id": "change-1"}]},
        )
        save_agent_memory_state(self.db, 1, "task-1", "", [round_data], 0)

        self.assertTrue(update_agent_memory_round_outcome(
            self.db, 1, "task-1",
            round_id="request-1",
            status="saved",
            outcome_updates={"revision_id": "revision-1", "selected_change_ids": ["change-1"]},
        ))
        self.assertTrue(update_agent_memory_round_outcome(
            self.db, 1, None,
            task_id="task-1",
            revision_id="revision-1",
            status="undone",
        ))

        state = get_agent_memory_state(self.db, 1, "task-1")
        self.assertEqual(len(state["recent_rounds"]), 1)
        self.assertEqual(state["recent_rounds"][0]["outcome"]["status"], "undone")

    def test_undo_updates_an_evicted_edit_event_by_revision_id(self):
        summary = serialize_memory_summary({
            "format": "conversation_summary_v2",
            "events": [{
                "round_id": "request-1",
                "type": "resume_edit",
                "request": "把姓名改为张三",
                "changes": ["基本信息 · 姓名：李四 → 张三"],
                "status": "saved",
                "revision_id": "revision-1",
            }],
        })
        save_agent_memory_state(self.db, 1, "task-1", summary, [], 0)

        self.assertTrue(update_agent_memory_round_outcome(
            self.db, 1, None,
            task_id="task-1",
            revision_id="revision-1",
            status="undone",
        ))

        state = get_agent_memory_state(self.db, 1, "task-1")
        payload = normalize_memory_summary(state["summary"])
        self.assertEqual(payload["events"][0]["status"], "undone")


if __name__ == "__main__":
    unittest.main()
