import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import (
    Base,
    ProjectTask,
    ResumeProject,
    ResumeRevision,
    delete_resume_project,
    record_resume_revision,
    save_conversation_context,
    undo_latest_resume_revision,
)


class ResumeRevisionTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.project = ResumeProject(id="project-1", user_id=1, title="测试")
        self.task = ProjectTask(
            id="task-1", project_id="project-1", user_id=1, title="基础简历",
            is_base=True, session_id="task-1", resume_data={"basics": {"name": "新姓名"}},
        )
        self.db.add_all([self.project, self.task])
        self.db.commit()
        self.db.info["task_id"] = "task-1"

    def tearDown(self):
        self.db.close()

    def test_undo_restores_task_and_base_project(self):
        self.task.pending_confirmation = {"confirm_id": "stale-confirm"}
        self.task.compressed_context = [
            {"type": "ai", "content": "修改已生效"},
        ]
        self.db.commit()
        record_resume_revision(
            self.db, 1, "task-1",
            {"basics": {"name": "原姓名"}},
            {"basics": {"name": "新姓名"}},
            ["change-1"],
        )
        status, restored, restored_layout, revision_id = undo_latest_resume_revision(self.db, 1, "task-1")
        self.assertEqual(status, "undone")
        self.assertEqual(restored["basics"]["name"], "原姓名")
        self.assertEqual(restored_layout["education"]["schoolTagStyle"], "text")
        self.db.refresh(self.task)
        self.db.refresh(self.project)
        self.assertEqual(self.task.resume_data["basics"]["name"], "原姓名")
        self.assertEqual(self.project.base_resume_data["basics"]["name"], "原姓名")
        self.assertIsNone(self.task.pending_confirmation)
        self.assertEqual(self.task.compressed_context, [
            {"type": "ai", "content": "修改已生效"},
        ])
        self.assertIsNotNone(revision_id)

    def test_saving_none_explicitly_clears_pending_confirmation(self):
        self.task.pending_confirmation = {"confirm_id": "stale-confirm"}
        self.db.commit()
        save_conversation_context(
            self.db,
            1,
            "task-1",
            [{"type": "human", "content": "新的普通请求"}],
            None,
        )
        self.db.refresh(self.task)
        self.assertIsNone(self.task.pending_confirmation)

    def test_undo_refuses_to_overwrite_later_edit(self):
        record_resume_revision(
            self.db, 1, "task-1",
            {"basics": {"name": "原姓名"}},
            {"basics": {"name": "新姓名"}},
            ["change-1"],
        )
        self.task.resume_data = {"basics": {"name": "用户后来手工修改"}}
        self.db.commit()
        status, restored, restored_layout, revision_id = undo_latest_resume_revision(self.db, 1, "task-1")
        self.assertEqual(status, "conflict")
        self.assertIsNone(restored)
        self.assertIsNone(restored_layout)
        self.assertIsNone(revision_id)

    def test_undo_restores_layout_snapshot(self):
        before_layout = {"education": {"schoolTagStyle": "text"}}
        after_layout = {"education": {"schoolTagStyle": "outline"}}
        self.task.layout_config = after_layout
        self.db.commit()
        record_resume_revision(
            self.db, 1, "task-1",
            {"basics": {"name": "新姓名"}},
            {"basics": {"name": "新姓名"}},
            ["layout-education"],
            before_layout=before_layout,
            after_layout=after_layout,
        )
        status, _, restored_layout, revision_id = undo_latest_resume_revision(self.db, 1, "task-1")
        self.assertEqual(status, "undone")
        self.assertEqual(restored_layout["education"]["schoolTagStyle"], "text")
        self.assertIsNotNone(revision_id)

    def test_deleting_project_removes_revision_snapshots(self):
        record_resume_revision(
            self.db, 1, "task-1",
            {"basics": {"name": "原姓名"}},
            {"basics": {"name": "新姓名"}},
            ["change-1"],
        )
        self.assertTrue(delete_resume_project(self.db, 1, "project-1"))
        self.assertEqual(self.db.query(ResumeRevision).count(), 0)


if __name__ == "__main__":
    unittest.main()
