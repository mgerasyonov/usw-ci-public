import unittest

from public_core import (
    PublicCoreError,
    canonical_dedup_material,
    classify_work,
    compute_dedup_key,
    deterministic_launch_identity,
    validate_task_state,
)


class PublicCoreTests(unittest.TestCase):
    def test_dedup_is_normalized_and_deterministic(self):
        a = canonical_dedup_material(
            project="  Design  ", role="Agent", product=None,
            subsystem="GUI", route="Public Safe", scope_key=" Core  Tests "
        )
        b = canonical_dedup_material(
            project="design", role="agent", product=None,
            subsystem="gui", route="public safe", scope_key="core tests"
        )
        self.assertEqual(compute_dedup_key(a), compute_dedup_key(b))

    def test_dedup_requires_target(self):
        with self.assertRaises(PublicCoreError):
            canonical_dedup_material(
                project="p", role="r", product=None,
                subsystem="", route="x", scope_key="y"
            )

    def test_task_state_validation(self):
        state = {
            "schema": "usw.task_state",
            "version": 1,
            "state_revision": 1,
            "execution_status": "WORKING",
            "last_result": {"classification": "NONE"},
            "events": [{"sequence": 1}],
        }
        validate_task_state(state)
        state["execution_status"] = "INVALID"
        with self.assertRaises(PublicCoreError):
            validate_task_state(state)

    def test_launch_identity_is_stable_and_fenced(self):
        a = deterministic_launch_identity("req-1", "task-1", 4, 2)
        b = deterministic_launch_identity("req-1", "task-1", 4, 2)
        c = deterministic_launch_identity("req-1", "task-1", 4, 3)
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    def test_watchdog_classification(self):
        self.assertEqual(classify_work(
            execution_status="WORKING",
            lease_age_seconds=10,
            lease_timeout_seconds=30
        ), "HEALTHY")
        self.assertEqual(classify_work(
            execution_status="WORKING",
            lease_age_seconds=120,
            lease_timeout_seconds=30
        ), "STALE_WORKER")
        self.assertEqual(classify_work(
            execution_status="NEED_DECISION",
            lease_age_seconds=120,
            lease_timeout_seconds=30
        ), "NEED_OWNER_DECISION")
        self.assertEqual(classify_work(
            execution_status="WAITING_REMOTE",
            lease_age_seconds=120,
            lease_timeout_seconds=30,
            remote_status="in_progress"
        ), "WAITING_EXTERNAL")
        self.assertEqual(classify_work(
            execution_status="WAITING_REMOTE",
            lease_age_seconds=120,
            lease_timeout_seconds=30,
            remote_status="completed"
        ), "RESUME_NEEDED")


if __name__ == "__main__":
    unittest.main()
