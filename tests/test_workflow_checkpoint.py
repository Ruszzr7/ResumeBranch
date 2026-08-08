import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from backend.harness.workflow import (
    WORKFLOW_STATE_KEYS,
    WorkflowCheckpointManager,
    build_workflow_thread_id,
    workflow_config,
)


class WorkflowCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "workflow.sqlite"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_state_survives_manager_restart_and_pause_resume(self):
        manager = WorkflowCheckpointManager(self.path)
        state = manager.record_turn_sync(
            7,
            "task-1",
            session_id="task-1",
            request_id="request-1",
            interaction_mode="coaching",
        )
        self.assertEqual(state["turn_count"], 1)
        manager.update_state_sync(
            7,
            "task-1",
            phase="evidence_collection",
            focus_section="work_experience",
            current_question="你在这个项目中具体负责什么？",
        )
        manager.pause_sync(7, "task-1")
        manager.close_sync()

        restarted = WorkflowCheckpointManager(self.path)
        recovered = restarted.load_state_sync(7, "task-1")
        self.assertEqual(recovered["interaction_mode"], "coaching")
        self.assertEqual(recovered["status"], "paused")
        self.assertEqual(recovered["phase"], "evidence_collection")
        self.assertEqual(recovered["focus_section"], "work_experience")
        self.assertEqual(recovered["turn_count"], 1)
        resumed = restarted.resume_sync(7, "task-1")
        self.assertEqual(resumed["status"], "active")
        restarted.close_sync()

    def test_user_and_task_thread_ids_are_strictly_isolated(self):
        manager = WorkflowCheckpointManager(self.path)
        manager.record_turn_sync(
            7, "task-1", session_id="task-1", request_id="r1",
            interaction_mode="coaching",
        )
        manager.record_turn_sync(
            7, "task-2", session_id="task-2", request_id="r2",
            interaction_mode="jd_review",
        )
        manager.record_turn_sync(
            8, "task-1", session_id="task-1", request_id="r3",
            interaction_mode="chat",
        )

        self.assertEqual(manager.load_state_sync(7, "task-1")["interaction_mode"], "coaching")
        self.assertEqual(manager.load_state_sync(7, "task-2")["interaction_mode"], "jd_review")
        self.assertEqual(manager.load_state_sync(8, "task-1")["interaction_mode"], "chat")
        self.assertNotEqual(
            build_workflow_thread_id(7, "task-1"),
            build_workflow_thread_id(8, "task-1"),
        )
        manager.close_sync()

    def test_checkpoint_rejects_business_payloads(self):
        manager = WorkflowCheckpointManager(self.path)
        manager.record_turn_sync(
            7, "task-1", session_id="task-1", request_id="r1",
        )

        with self.assertRaises(ValueError):
            manager.update_state_sync(7, "task-1", resume_data={"basics": {}})
        with self.assertRaises(ValueError):
            manager.update_state_sync(7, "task-1", pending_confirmation={"id": "secret"})

        checkpoint = manager._saver.get_tuple(workflow_config(7, "task-1")).checkpoint
        channel_values = checkpoint["channel_values"]
        self.assertTrue(set(channel_values).issubset(WORKFLOW_STATE_KEYS))
        for forbidden in ("resume_data", "jd_data", "messages", "pending_confirmation", "photo"):
            self.assertNotIn(forbidden, channel_values)
        manager.close_sync()

    def test_delete_thread_removes_recoverable_state(self):
        manager = WorkflowCheckpointManager(self.path)
        manager.record_turn_sync(
            7, "task-1", session_id="task-1", request_id="r1",
        )
        manager.delete_thread_sync(7, "task-1")
        self.assertEqual(manager.load_state_sync(7, "task-1"), {})
        manager.close_sync()

    def test_duplicate_request_id_is_idempotent(self):
        manager = WorkflowCheckpointManager(self.path)
        first = manager.record_turn_sync(
            7, "task-1", session_id="task-1", request_id="same-request",
            interaction_mode="coaching",
        )
        second = manager.record_turn_sync(
            7, "task-1", session_id="task-1", request_id="same-request",
            interaction_mode="coaching",
        )
        self.assertEqual(first["turn_count"], 1)
        self.assertEqual(second["turn_count"], 1)
        manager.close_sync()

    def test_retention_cleanup_deletes_only_stale_control_threads(self):
        manager = WorkflowCheckpointManager(self.path)
        manager.record_turn_sync(
            7, "task-1", session_id="task-1", request_id="r1",
            interaction_mode="coaching",
        )
        deleted = manager.cleanup_stale_sync(retention_days=0)
        self.assertEqual(deleted, 1)
        self.assertEqual(manager.load_state_sync(7, "task-1"), {})
        manager.close_sync()

    def test_concurrent_distinct_requests_do_not_lose_turns(self):
        manager = WorkflowCheckpointManager(self.path)

        def record(index):
            return manager.record_turn_sync(
                7, "task-1", session_id="task-1", request_id=f"r-{index}",
                interaction_mode="coaching" if index == 0 else None,
            )

        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(record, range(8)))
        self.assertEqual(manager.load_state_sync(7, "task-1")["turn_count"], 8)
        manager.close_sync()


if __name__ == "__main__":
    unittest.main()
