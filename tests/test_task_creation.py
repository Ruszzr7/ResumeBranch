import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base, ProjectTask, ResumeProject, create_resume_task, save_user_resume


class TaskCreationTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.target_project = ResumeProject(id="target", user_id=1, title="目标主简历")
        self.source_project = ResumeProject(id="source", user_id=1, title="其他主简历")
        self.source_task = ProjectTask(
            id="source-task", project_id="source", user_id=1, title="英文版本",
            is_base=False, session_id="source-task",
            resume_data={"basics": {"name": "候选人"}}, photo="photo-data",
            source_page_count=2, source_document_id="source-document",
            jd_data={"position": "旧岗位"}, messages=[{"content": "旧对话"}],
        )
        self.db.add_all([self.target_project, self.source_project, self.source_task])
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_cross_project_copy_is_independent_and_uses_new_jd(self):
        task = create_resume_task(
            self.db, 1, "target", "新岗位", copy_base_resume=False,
            source_task_id="source-task", jd_data={"position": "新岗位"},
        )
        self.assertEqual(task.resume_data["basics"]["name"], "候选人")
        self.assertEqual(task.photo, "photo-data")
        self.assertEqual(task.source_page_count, 2)
        self.assertEqual(task.source_document_id, "source-document")
        self.assertEqual(task.jd_data["position"], "新岗位")
        self.assertEqual(task.messages, [])
        self.assertNotEqual(task.session_id, self.source_task.session_id)

        task.resume_data = {"basics": {"name": "独立副本"}}
        self.db.commit()
        self.db.refresh(self.source_task)
        self.assertEqual(self.source_task.resume_data["basics"]["name"], "候选人")

    def test_cannot_copy_another_users_resume(self):
        foreign = ProjectTask(
            id="foreign", project_id="source", user_id=2, title="他人简历",
            is_base=True, session_id="foreign", resume_data={"basics": {"name": "他人"}},
        )
        self.db.add(foreign)
        self.db.commit()
        task = create_resume_task(
            self.db, 1, "target", "非法复制", copy_base_resume=False,
            source_task_id="foreign",
        )
        self.assertIsNone(task)

    def test_blank_version_contains_no_source_data(self):
        task = create_resume_task(
            self.db, 1, "target", "空白", copy_base_resume=False,
            source_task_id=None, jd_data={},
        )
        self.assertEqual(task.resume_data, {})
        self.assertEqual(task.photo, "")
        self.assertEqual(task.source_page_count, 1)
        self.assertIsNone(task.source_document_id)

    def test_explicit_empty_photo_removes_existing_photo_but_omitted_photo_is_preserved(self):
        self.db.info["task_id"] = self.source_task.id

        save_user_resume(
            self.db,
            1,
            {"basics": {"name": "候选人", "photo": ""}},
        )
        self.db.refresh(self.source_task)
        self.assertEqual(self.source_task.photo, "")

        self.source_task.photo = "photo-data"
        self.db.commit()
        save_user_resume(self.db, 1, {"basics": {"name": "候选人"}})
        self.db.refresh(self.source_task)
        self.assertEqual(self.source_task.photo, "photo-data")


if __name__ == "__main__":
    unittest.main()
