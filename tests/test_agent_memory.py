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

    def test_legacy_context_is_loaded_without_eager_migration(self):
        self.task.compressed_context = [
            {"type": "systemmessage", "content": "历史摘要"},
            {"type": "human", "content": "最近问题"},
            {"type": "ai", "content": "最近回答"},
        ]
        self.db.commit()

        state = get_agent_memory_state(self.db, 1, "task-1")

        self.assertEqual(state["summary"], "历史摘要")
        self.assertEqual(
            [message["content"] for message in state["recent_messages"]],
            ["最近问题", "最近回答"],
        )
        self.assertEqual(state["version"], 0)
        self.assertEqual(self.db.query(AgentMemoryState).count(), 0)

    def test_optimistic_version_rejects_stale_overwrite(self):
        first_version = save_agent_memory_state(
            self.db,
            1,
            "task-1",
            "第一版",
            [{"type": "human", "content": "first"}],
            0,
        )
        self.assertEqual(first_version, 1)

        with self.assertRaises(MemoryVersionConflict):
            save_agent_memory_state(
                self.db,
                1,
                "task-1",
                "过期版本",
                [{"type": "human", "content": "stale"}],
                0,
            )

        state = get_agent_memory_state(self.db, 1, "task-1")
        self.assertEqual(state["summary"], "第一版")
        self.assertEqual(state["version"], 1)

        second_version = save_agent_memory_state(
            self.db,
            1,
            "task-1",
            "第二版",
            [{"type": "human", "content": "second"}],
            1,
        )
        self.assertEqual(second_version, 2)

    def test_interview_memory_is_persisted_with_the_same_optimistic_version(self):
        facts = {
            "schema_version": 1,
            "verified_facts": [{
                "claim": "转化率提升20%",
                "source_quote": "转化率提升20%",
                "source_type": "user_message",
            }],
        }
        version = save_agent_memory_state(
            self.db, 1, "task-1", "", [], 0, interview_memory=facts,
        )

        state = get_agent_memory_state(self.db, 1, "task-1")
        self.assertEqual(version, 1)
        self.assertEqual(state["interview_memory"]["verified_facts"][0]["claim"], "转化率提升20%")

    def test_deleting_context_removes_layered_and_legacy_memory(self):
        self.task.compressed_context = [{"type": "human", "content": "legacy"}]
        self.db.commit()
        save_agent_memory_state(
            self.db,
            1,
            "task-1",
            "summary",
            [{"type": "human", "content": "recent"}],
            0,
        )

        delete_conversation_context(self.db, 1, "task-1")

        self.db.refresh(self.task)
        self.assertEqual(self.task.compressed_context, [])
        self.assertEqual(self.db.query(AgentMemoryState).count(), 0)


if __name__ == "__main__":
    unittest.main()
