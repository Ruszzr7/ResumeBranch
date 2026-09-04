import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import (
    Base,
    ProjectTask,
    ResumeProject,
    create_resume_task,
    rename_resume_project,
    rename_resume_task,
    switch_base_resume_task,
    save_user_resume,
)
from backend.resume_schema import validate_resume_data


class TaskCreationTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.target_project = ResumeProject(id="target", user_id=1, title="目标主简历")
        self.source_project = ResumeProject(id="source", user_id=1, title="其他主简历")
        self.base_task = ProjectTask(
            id="base-task", project_id="target", user_id=1, title="基础简历",
            is_base=True, session_id="base-task",
            resume_data={"basics": {"name": "旧基础内容"}}, photo="old-photo",
        )
        self.source_task = ProjectTask(
            id="source-task", project_id="source", user_id=1, title="英文版本",
            is_base=False, session_id="source-task",
            resume_data={"basics": {"name": "候选人"}}, photo="photo-data",
            source_page_count=2, source_document_id="source-document",
            jd_data={"position": "旧岗位"}, messages=[{"content": "旧对话"}],
        )
        self.db.add_all([self.target_project, self.source_project, self.base_task, self.source_task])
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
        self.assertEqual(task.resume_data, validate_resume_data({}))
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

    def test_project_and_task_titles_can_be_renamed(self):
        project = rename_resume_project(self.db, 1, "target", "新的主简历")
        task = rename_resume_task(self.db, 1, "base-task", "长期基础版")

        self.assertEqual(project.title, "新的主简历")
        self.assertEqual(task.title, "长期基础版")
        self.db.refresh(self.target_project)
        self.db.refresh(self.base_task)
        self.assertEqual(self.target_project.title, "新的主简历")
        self.assertEqual(self.base_task.title, "长期基础版")

    def test_version_can_switch_into_base_role_without_copying_or_deleting_data(self):
        version_task = ProjectTask(
            id="target-version", project_id="target", user_id=1, title="目标岗位版本",
            is_base=False, session_id="target-version",
            resume_data={
            "basics": {"name": "版本候选人"},
            "project_experience": [{"project_name": "版本项目"}],
            },
            photo="photo-data", source_page_count=2, source_document_id="source-document",
            layout_config={"page": {"margin_top_mm": 18}},
            jd_data={"position": "版本岗位"}, messages=[{"content": "版本对话"}],
        )
        self.db.add(version_task)
        self.db.commit()

        result, base_task, former_base_task = switch_base_resume_task(self.db, 1, "target-version")

        self.assertEqual(result, "ok")
        self.assertIs(base_task, version_task)
        self.assertIs(former_base_task, self.base_task)
        self.assertTrue(base_task.is_base)
        self.assertFalse(former_base_task.is_base)
        self.assertEqual(former_base_task.title, "版本简历")
        self.assertEqual(base_task.resume_data, version_task.resume_data)
        self.assertEqual(base_task.photo, "photo-data")
        self.assertEqual(base_task.source_page_count, 2)
        self.assertEqual(base_task.source_document_id, "source-document")
        self.assertEqual(base_task.layout_config, version_task.layout_config)
        self.assertEqual(base_task.jd_data, {"position": "版本岗位"})
        self.assertEqual(base_task.messages, [{"content": "版本对话"}])
        self.assertEqual(former_base_task.resume_data["basics"]["name"], "旧基础内容")
        self.assertEqual(former_base_task.photo, "old-photo")
        self.db.refresh(self.target_project)
        self.assertEqual(self.target_project.base_resume_data["basics"]["name"], "版本候选人")

    def test_setting_existing_base_is_a_noop(self):
        result, base_task, former_base_task = switch_base_resume_task(self.db, 1, "base-task")
        self.assertEqual(result, "ok")
        self.assertEqual(base_task.id, "base-task")
        self.assertIsNone(former_base_task)


if __name__ == "__main__":
    unittest.main()
