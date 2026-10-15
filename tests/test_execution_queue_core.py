import copy
import unittest

import execution_queue_core as core


def request(request_id, *, at, status="READY", gate="SATISFIED", priority=100, key="k"):
    return {
        "request_id": request_id,
        "created_at": at,
        "status": status,
        "priority": priority,
        "supersedence_key": key,
        "owner_gate": {"status": gate},
    }


class ExecutionQueueCoreTests(unittest.TestCase):
    def test_owner_gate_blocks_ready_selection(self):
        reqs = {"x": request("x", at="1", status="DEFERRED_OWNER_GATE", gate="WAITING")}
        self.assertIsNone(core.select_ready(reqs))

    def test_newer_same_key_supersedes_older(self):
        reqs = {
            "old": request("old", at="1"),
            "new": request("new", at="2"),
        }
        self.assertEqual(core.select_ready(reqs)["request_id"], "new")
        self.assertEqual(reqs["old"]["status"], "SUPERSEDED")

    def test_running_is_not_retroactively_superseded(self):
        reqs = {
            "running": request("running", at="1", status="RUNNING"),
            "new": request("new", at="2"),
        }
        self.assertEqual(core.select_ready(reqs)["request_id"], "new")
        self.assertEqual(reqs["running"]["status"], "RUNNING")

    def test_priority_wins_across_different_keys(self):
        reqs = {
            "low": request("low", at="1", priority=10, key="a"),
            "high": request("high", at="2", priority=200, key="b"),
        }
        self.assertEqual(core.select_ready(reqs)["request_id"], "high")

    def test_running_to_pass(self):
        reqs = {"x": request("x", at="1")}
        core.mark_running(reqs, "x", "77")
        self.assertEqual(reqs["x"]["status"], "RUNNING")
        core.mark_result(reqs, "x", "PASS", "77")
        self.assertEqual(reqs["x"]["status"], "PASS")
        self.assertEqual(reqs["x"]["result"]["run_id"], "77")

    def test_result_conflict_fails_closed(self):
        reqs = {"x": request("x", at="1")}
        core.mark_result(reqs, "x", "PASS", "77")
        with self.assertRaises(core.QueueStateError):
            core.mark_result(reqs, "x", "FAIL", "78")


if __name__ == "__main__":
    unittest.main(verbosity=2)
