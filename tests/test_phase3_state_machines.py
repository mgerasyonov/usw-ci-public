import unittest

from finalizer_state_core import FinalizerStateError, evaluate_finalization
from auto_resume_core import AutoResumeError, decide_resume
from gui_component_schema import GuiComponentSchemaError, validate_component_contract


class FinalizerStateTests(unittest.TestCase):
    def request(self):
        return {
            "schema": "usw.public.finalizer_eval",
            "version": 1,
            "expected_state_revision": 7,
            "expected_ownership_state": "ACTIVE",
        }

    def state(self, status="WORKING", result="PASS", revision=7):
        return {
            "state_revision": revision,
            "execution_status": status,
            "last_result": {"classification": result},
        }

    def test_finalizer_eligible(self):
        out = evaluate_finalization(
            request=self.request(),
            task_state=self.state(),
            ownership_status="ACTIVE",
        )
        self.assertEqual(out["classification"], "READY_TO_FINALIZE")

    def test_finalizer_owner_gate_rejected(self):
        out = evaluate_finalization(
            request=self.request(),
            task_state=self.state(status="NEED_DECISION"),
            ownership_status="ACTIVE",
        )
        self.assertEqual(out["status"], "REJECTED")
        self.assertTrue(out["owner_gate"])

    def test_finalizer_pending_rejected(self):
        out = evaluate_finalization(
            request=self.request(),
            task_state=self.state(status="WAITING_REMOTE", result="PENDING"),
            ownership_status="ACTIVE",
        )
        self.assertEqual(out["classification"], "QUALIFICATION_AMBIGUOUS")

    def test_finalizer_stale_revision_rejected(self):
        out = evaluate_finalization(
            request=self.request(),
            task_state=self.state(revision=8),
            ownership_status="ACTIVE",
        )
        self.assertEqual(out["classification"], "STALE_REVISION")


class AutoResumeTests(unittest.TestCase):
    def state(self, status="WAITING_REMOTE", revision=8, run_id="run-8"):
        return {
            "execution_status": status,
            "state_revision": revision,
            "last_remote_builder_run_id": run_id,
        }

    def observation(self, seq=8, revision=8, run_id="run-8", result="PASS"):
        return {
            "source": "synthetic",
            "run_id": run_id,
            "sequence": seq,
            "state_revision": revision,
            "classification": result,
        }

    def test_owner_gate_never_restarts(self):
        for status in ("NEED_DECISION", "READY_FOR_AUDITION", "BLOCKED"):
            out = decide_resume(
                task_state=self.state(status=status),
                observation=self.observation(),
            )
            self.assertEqual(out["decision"], "NO_AUTO_RESTART")

    def test_duplicate_is_ignored(self):
        obs = self.observation()
        first = decide_resume(task_state=self.state(), observation=obs)
        second = decide_resume(
            task_state=self.state(),
            observation=obs,
            overlay={"last_identity": first["identity"], "last_sequence": 8},
        )
        self.assertEqual(second["decision"], "DUPLICATE_IGNORED")

    def test_older_sequence_is_stale(self):
        out = decide_resume(
            task_state=self.state(),
            observation=self.observation(seq=7, revision=7, run_id="run-7"),
            overlay={"last_sequence": 8},
        )
        self.assertEqual(out["decision"], "STALE_IGNORED")

    def test_fresh_result_resumes(self):
        out = decide_resume(
            task_state=self.state(),
            observation=self.observation(),
        )
        self.assertEqual(out["decision"], "APPLY_AND_RESUME")
        self.assertEqual(out["next_execution_status"], "WORKING")


class GuiSchemaTests(unittest.TestCase):
    def valid_component(self):
        return {
            "component_id": "KnobMedium",
            "semantic_name": "Medium Knob",
            "family": "ContinuousControls",
            "status": "IMPLEMENTATION_READY",
            "size_classes": ["M"],
            "supported_roles": ["parameter"],
            "binding_class": ["PARAM_CONTINUOUS"],
            "interaction_states": ["default", "hover", "active", "disabled"],
            "rendering_layers": [
                {"class": "VECTOR_STATIC"},
                {"class": "VECTOR_DYNAMIC"},
                {"class": "TEXT_RUNTIME"},
            ],
            "logical_bounds": {"width": 64, "height": 64},
            "resize_policy": "scale_with_component",
            "motion_update_class": ["PARAMETER_DRIVEN"],
            "assets": [],
            "runtime_adapter": "qualified-generic-runtime-control",
            "qa_fixtures": ["min", "mid", "max", "disabled"],
            "known_limits": [],
        }

    def test_component_contract_passes(self):
        out = validate_component_contract(self.valid_component())
        self.assertEqual(out["status"], "PASS")

    def test_component_contract_rejects_unknown_binding(self):
        item = self.valid_component()
        item["binding_class"] = ["UNKNOWN_BINDING"]
        with self.assertRaises(GuiComponentSchemaError):
            validate_component_contract(item)

    def test_component_contract_requires_runtime_adapter(self):
        item = self.valid_component()
        item["runtime_adapter"] = ""
        with self.assertRaises(GuiComponentSchemaError):
            validate_component_contract(item)


if __name__ == "__main__":
    unittest.main()
