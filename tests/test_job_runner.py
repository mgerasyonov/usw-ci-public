import unittest

from job_runner import JobRunnerError, run_request


PUBLIC_SAFETY = {
    "private_repo": False,
    "external_auth": False,
    "private_artifacts": False,
    "proprietary_data": False,
    "logs_public": True,
}


class JobRunnerTests(unittest.TestCase):
    def base(self, workload, payload):
        return {
            "schema": "usw.public_job_request",
            "version": 1,
            "request_id": "req-1",
            "workload": workload,
            "public_safety": dict(PUBLIC_SAFETY),
            "payload": payload,
        }

    def test_finalizer_job(self):
        req = self.base("FINALIZER_STATE_EVAL", {
            "request": {
                "schema": "usw.public.finalizer_eval",
                "version": 1,
                "expected_state_revision": 3,
                "expected_ownership_state": "ACTIVE",
            },
            "task_state": {
                "state_revision": 3,
                "execution_status": "WORKING",
                "last_result": {"classification": "PASS"},
            },
            "ownership_status": "ACTIVE",
        })
        out = run_request(req)
        self.assertEqual(out["status"], "PASS")
        self.assertEqual(out["output"]["classification"], "READY_TO_FINALIZE")

    def test_auto_resume_job(self):
        req = self.base("AUTO_RESUME_DECISION", {
            "task_state": {
                "state_revision": 4,
                "execution_status": "WAITING_REMOTE",
                "last_remote_builder_run_id": "run-4",
            },
            "observation": {
                "source": "synthetic",
                "run_id": "run-4",
                "sequence": 4,
                "state_revision": 4,
                "classification": "PASS",
            },
            "overlay": {},
        })
        out = run_request(req)
        self.assertEqual(out["output"]["decision"], "APPLY_AND_RESUME")

    def test_gui_component_job(self):
        req = self.base("GUI_COMPONENT_VALIDATE", {
            "component": {
                "component_id": "Meter",
                "semantic_name": "Meter",
                "family": "Metering",
                "status": "IMPLEMENTATION_READY",
                "size_classes": ["M"],
                "supported_roles": ["telemetry"],
                "binding_class": ["TELEMETRY_SCALAR"],
                "interaction_states": ["default"],
                "rendering_layers": [{"class": "TELEMETRY_RENDERED"}],
                "logical_bounds": {"width": 32, "height": 180},
                "resize_policy": "height_scales",
                "motion_update_class": ["METER_TELEMETRY"],
                "assets": [],
                "runtime_adapter": "qualified-meter-adapter",
                "qa_fixtures": ["silence", "nominal", "peak"],
                "known_limits": [],
            }
        })
        out = run_request(req)
        self.assertEqual(out["output"]["status"], "PASS")

    def test_safety_must_be_exact(self):
        req = self.base("GUI_COMPONENT_VALIDATE", {"component": {}})
        req["public_safety"]["private_repo"] = True
        with self.assertRaises(JobRunnerError):
            run_request(req)

    def test_unknown_workload_fails(self):
        req = self.base("UNKNOWN", {})
        with self.assertRaises(JobRunnerError):
            run_request(req)


if __name__ == "__main__":
    unittest.main()
