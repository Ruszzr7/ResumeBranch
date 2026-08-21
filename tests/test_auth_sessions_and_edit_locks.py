import unittest
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import (
    AuthSession,
    Base,
    ProjectTask,
    ResumeEditLock,
    ResumeProject,
    acquire_resume_edit_lock,
    auth_session_is_active,
    get_resume_edit_state,
    mark_resume_edit_awaiting_confirmation,
    release_resume_edit_lock,
    rotate_auth_session,
)


class AuthSessionAndEditLockTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.db.add(ResumeProject(id="project-1", user_id=1, title="简历"))
        self.db.add(ProjectTask(
            id="task-1", project_id="project-1", user_id=1,
            title="基础简历", is_base=True, session_id="main-1",
        ))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_rotating_login_invalidates_the_previous_server_session(self):
        first = rotate_auth_session(self.db, 1)
        self.assertTrue(auth_session_is_active(self.db, 1, first))

        second = rotate_auth_session(self.db, 1)
        self.assertNotEqual(first, second)
        self.assertFalse(auth_session_is_active(self.db, 1, first))
        self.assertTrue(auth_session_is_active(self.db, 1, second))
        self.assertEqual(self.db.query(AuthSession).filter_by(user_id=1).count(), 1)

    def test_task_lock_is_atomic_and_released_by_owner(self):
        first = acquire_resume_edit_lock(self.db, 1, "task-1", "main-1", "request-1")
        self.assertIsNotNone(first)

        other_db = self.Session()
        try:
            blocked = acquire_resume_edit_lock(other_db, 1, "task-1", "command-1", "request-2")
            self.assertIsNone(blocked)
        finally:
            other_db.close()

        self.assertTrue(mark_resume_edit_awaiting_confirmation(
            self.db, 1, "task-1", "main-1", "request-1"
        ))
        self.assertEqual(get_resume_edit_state(self.db, 1, "task-1")["status"], "awaiting_confirmation")
        self.assertTrue(release_resume_edit_lock(
            self.db, 1, "task-1", owner_session_id="main-1", request_id="request-1"
        ))
        self.assertIsNone(get_resume_edit_state(self.db, 1, "task-1"))

    def test_abandoned_generation_can_be_recovered(self):
        acquire_resume_edit_lock(self.db, 1, "task-1", "main-1", "request-1")
        row = self.db.query(ResumeEditLock).filter_by(task_id="task-1").one()
        row.updated_at = datetime.utcnow() - timedelta(minutes=10)
        self.db.commit()

        recovered = acquire_resume_edit_lock(
            self.db, 1, "task-1", "command-1", "request-2"
        )
        self.assertIsNotNone(recovered)
        self.assertEqual(recovered.owner_session_id, "command-1")


if __name__ == "__main__":
    unittest.main()
