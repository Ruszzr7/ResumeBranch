import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import (
    AgentMemoryState,
    AgentSkillState,
    Base,
    Conversation,
    ConversationContext,
    ProjectTask,
    ResumeEditLock,
    ResumeProject,
    ResumeRevision,
    close_conversation_context,
    create_or_resume_conversation_context,
    ensure_main_context,
    append_context_event,
    get_agent_memory_state,
    get_agent_skill_state,
    get_conversation,
    get_conversation_context,
    delete_resume_project,
    list_conversation_contexts,
    reset_main_conversation_context,
    save_agent_memory_state,
    save_agent_skill_state,
    save_conversation,
    save_conversation_context,
    update_conversation_context_metadata,
)


class ConversationContextTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.db.add_all([
            ResumeProject(id="project-1", user_id=1, title="测试"),
            ProjectTask(
                id="task-1", project_id="project-1", user_id=1,
                title="基础简历", is_base=True, session_id="task-1",
            ),
        ])
        self.db.commit()
        self.db.info["task_id"] = "task-1"

    def tearDown(self):
        self.db.close()

    def test_active_command_contexts_are_singleton_and_data_isolated(self):
        main = ensure_main_context(self.db, 1, "task-1")
        layout = create_or_resume_conversation_context(self.db, 1, "task-1", "layout")
        resumed = create_or_resume_conversation_context(self.db, 1, "task-1", "layout")
        self.assertEqual(layout.id, resumed.id)

        save_conversation(self.db, 1, layout.session_id, [{"type": "human", "content": "排版"}])
        save_conversation(self.db, 1, main.session_id, [{"type": "human", "content": "主对话"}])
        self.assertEqual(get_conversation(self.db, 1, layout.session_id)[0]["content"], "排版")
        self.assertEqual(get_conversation(self.db, 1, main.session_id)[0]["content"], "主对话")

        save_agent_memory_state(self.db, 1, layout.session_id, "排版摘要", [], 0)
        self.assertEqual(
            get_agent_memory_state(self.db, 1, layout.session_id)["scope_id"],
            f"task:task-1:context:{layout.session_id}",
        )
        self.assertEqual(get_agent_memory_state(self.db, 1, main.session_id)["scope_id"], "task:task-1")

    def test_conversation_storage_requires_an_active_task(self):
        self.db.info.pop("task_id", None)
        with self.assertRaisesRegex(ValueError, "请先选择一个简历任务"):
            save_conversation(self.db, 1, "orphan", [{"type": "human", "content": "孤立消息"}])
        with self.assertRaisesRegex(ValueError, "请先选择一个简历任务"):
            get_conversation(self.db, 1, "orphan")
        with self.assertRaisesRegex(ValueError, "请先选择一个简历任务"):
            save_conversation_context(self.db, 1, "orphan", [])
        with self.assertRaisesRegex(ValueError, "请先选择一个简历任务"):
            get_conversation_context(self.db, 1, "orphan")
        self.assertEqual(self.db.query(Conversation).count(), 0)

    def test_closing_mission_clears_memory_but_keeps_audit_record(self):
        context = create_or_resume_conversation_context(self.db, 1, "task-1", "coaching")
        append_context_event(self.db, 1, "task-1", context, "started")
        save_conversation(self.db, 1, context.session_id, [{"type": "human", "content": "事实"}])
        save_agent_memory_state(self.db, 1, context.session_id, "摘要", [], 0)
        closed = close_conversation_context(self.db, 1, context.id)
        event = append_context_event(self.db, 1, "task-1", context, "closed")
        self.assertEqual(closed.status, "closed")
        self.assertEqual(event["action"], "closed")
        self.assertEqual(event["status"], "closed")
        task = self.db.query(ProjectTask).filter(ProjectTask.id == "task-1").one()
        self.assertEqual(len(task.messages), 1)
        self.assertEqual(task.messages[0]["content"], f"已结束“{context.title}”任务。")
        self.assertEqual(self.db.query(AgentMemoryState).count(), 0)
        self.assertEqual(get_conversation(self.db, 1, context.session_id), [])
        self.assertEqual(
            [item.status for item in list_conversation_contexts(self.db, 1, "task-1") if item.id == context.id],
            ["closed"],
        )

    def test_mission_lifecycle_marker_is_small_context_metadata(self):
        context = create_or_resume_conversation_context(self.db, 1, "task-1", "layout")
        updated = update_conversation_context_metadata(
            self.db,
            1,
            context.session_id,
            {"initial_analysis_completed": True},
        )
        self.assertTrue(updated.metadata_json["initial_analysis_completed"])
        self.assertNotIn("messages", updated.metadata_json)

    def test_reset_main_context_clears_chat_state_only(self):
        main = ensure_main_context(self.db, 1, "task-1")
        task = self.db.query(ProjectTask).filter(ProjectTask.id == "task-1").one()
        task.resume_data = {"basics": {"name": "张三"}}
        task.jd_data = {"position": "后端开发"}
        task.layout_config = {"version": 10}
        task.messages = [{"role": "user", "content": "历史消息"}]
        task.compressed_context = [{"type": "human", "content": "近期消息"}]
        task.pending_confirmation = {"confirm_id": "confirm-1"}
        main.metadata_json = {"initial_analysis_completed": True}
        self.db.add_all([
            ResumeEditLock(
                task_id="task-1", user_id=1, owner_session_id=main.session_id,
                request_id="request-1", status="awaiting_confirmation",
            ),
            ResumeRevision(
                id="revision-1", task_id="task-1", user_id=1,
                before_data={"basics": {"name": "旧姓名"}},
                after_data={"basics": {"name": "张三"}},
            ),
        ])
        self.db.commit()
        save_agent_memory_state(self.db, 1, main.session_id, "摘要", [], 0)
        save_agent_skill_state(
            self.db, 1, main.session_id, "resume-coach", {"active": True}, 0
        )

        reset = reset_main_conversation_context(self.db, 1, "task-1", main.id)

        self.assertEqual(reset.id, main.id)
        self.db.refresh(task)
        self.assertEqual(task.messages, [])
        self.assertEqual(task.compressed_context, [])
        self.assertIsNone(task.pending_confirmation)
        self.assertEqual(task.resume_data, {"basics": {"name": "张三"}})
        self.assertEqual(task.jd_data, {"position": "后端开发"})
        self.assertEqual(task.layout_config, {"version": 10})
        self.assertEqual(reset.metadata_json, {})
        self.assertEqual(self.db.query(AgentMemoryState).count(), 0)
        self.assertEqual(self.db.query(AgentSkillState).count(), 0)
        self.assertEqual(self.db.query(ResumeEditLock).count(), 0)
        self.assertEqual(self.db.query(ResumeRevision).count(), 1)

    def test_reset_rejects_mission_context(self):
        context = create_or_resume_conversation_context(self.db, 1, "task-1", "layout")
        with self.assertRaisesRegex(ValueError, "只能重置主对话"):
            reset_main_conversation_context(self.db, 1, "task-1", context.id)

    def test_project_delete_removes_mission_storage(self):
        context = create_or_resume_conversation_context(self.db, 1, "task-1", "layout")
        self.db.add(Conversation(user_id=1, session_id=context.session_id, messages=[{"content": "排版"}]))
        save_agent_memory_state(self.db, 1, context.session_id, "摘要", [], 0)
        save_agent_skill_state(
            self.db, 1, context.session_id, "resume-coach",
            {"active": True, "issues": {}}, 0,
        )
        self.db.commit()

        self.assertTrue(delete_resume_project(self.db, 1, "project-1"))
        self.assertEqual(self.db.query(ConversationContext).count(), 0)
        self.assertEqual(self.db.query(Conversation).count(), 0)
        self.assertEqual(self.db.query(AgentMemoryState).count(), 0)
        self.assertEqual(self.db.query(AgentSkillState).count(), 0)

    def test_coach_state_is_private_and_versioned(self):
        context = create_or_resume_conversation_context(self.db, 1, "task-1", "coaching")
        version = save_agent_skill_state(
            self.db, 1, context.session_id, "resume-coach",
            {"active": True, "issues": {"issue-1": {"evidence": ["A"]}}}, 0,
        )
        stored = get_agent_skill_state(self.db, 1, context.session_id, "resume-coach")
        self.assertEqual(version, 1)
        self.assertEqual(stored["version"], 1)
        self.assertTrue(stored["state"]["active"])
        self.assertNotIn("coach_state", get_agent_memory_state(self.db, 1, context.session_id))


if __name__ == "__main__":
    unittest.main()
