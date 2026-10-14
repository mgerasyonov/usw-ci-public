import unittest

from public_core import (
    PublicCoreError,
    canonical_dedup_material,
    classify_work,
    compute_dedup_key,
    deterministic_launch_identity,
    validate_task_state,
    evaluate_finalizer_state,
    decide_auto_resume,
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


class Phase3StateTests(unittest.TestCase):
    def test_finalizer_eligible(self):
        out = evaluate_finalizer_state(
            request={
                "schema": "usw.public.finalizer_eval",
                "version": 1,
                "expected_state_revision": 3,
                "expected_ownership_state": "ACTIVE",
            },
            task_state={
                "state_revision": 3,
                "execution_status": "WORKING",
                "last_result": {"classification": "PASS"},
            },
            ownership_status="ACTIVE",
        )
        self.assertEqual(out["classification"], "READY_TO_FINALIZE")

    def test_finalizer_owner_gate(self):
        out = evaluate_finalizer_state(
            request={
                "schema": "usw.public.finalizer_eval",
                "version": 1,
                "expected_state_revision": 3,
                "expected_ownership_state": "ACTIVE",
            },
            task_state={
                "state_revision": 3,
                "execution_status": "NEED_DECISION",
                "last_result": {"classification": "PASS"},
            },
            ownership_status="ACTIVE",
        )
        self.assertTrue(out["owner_gate"])

    def test_auto_resume_duplicate_and_stale(self):
        state = {
            "execution_status": "WAITING_REMOTE",
            "state_revision": 5,
            "last_remote_builder_run_id": "r5",
        }
        obs = {
            "source": "synthetic",
            "run_id": "r5",
            "sequence": 5,
            "state_revision": 5,
            "classification": "PASS",
        }
        first = decide_auto_resume(task_state=state, observation=obs)
        dup = decide_auto_resume(
            task_state=state,
            observation=obs,
            overlay={"last_identity": first["identity"], "last_sequence": 5},
        )
        self.assertEqual(dup["decision"], "DUPLICATE_IGNORED")

        stale = decide_auto_resume(
            task_state=state,
            observation={**obs, "run_id": "r4", "sequence": 4, "state_revision": 4},
            overlay={"last_sequence": 5},
        )
        self.assertEqual(stale["decision"], "STALE_IGNORED")

    def test_auto_resume_owner_gate(self):
        out = decide_auto_resume(
            task_state={
                "execution_status": "READY_FOR_AUDITION",
                "state_revision": 5,
                "last_remote_builder_run_id": "r5",
            },
            observation={
                "source": "synthetic",
                "run_id": "r5",
                "sequence": 5,
                "state_revision": 5,
                "classification": "PASS",
            },
        )
        self.assertEqual(out["decision"], "NO_AUTO_RESTART")


if __name__ == "__main__":
    unittest.main()
