from __future__ import annotations

import hashlib
import json
import unicodedata

EXECUTION_STATES = {
    "WORKING", "WAITING_REMOTE", "NEED_DECISION", "BLOCKED",
    "READY_FOR_AUDITION", "ACCEPTED", "CLOSED",
}
RESULT_CLASSIFICATIONS = {"NONE", "PENDING", "PASS", "FAIL"}


class PublicCoreError(ValueError):
    pass


def normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    value = unicodedata.normalize("NFKC", str(value)).strip().lower()
    return " ".join(value.split())


def canonical_dedup_material(*, project: str, role: str, product: str | None,
                             subsystem: str, route: str, scope_key: str) -> dict:
    material = {
        "responsible_project": normalize_text(project),
        "responsible_role": normalize_text(role),
        "target_product": normalize_text(product),
        "target_subsystem": normalize_text(subsystem),
        "route": normalize_text(route),
        "scope_key": normalize_text(scope_key),
    }
    if not material["responsible_project"] or not material["responsible_role"]:
        raise PublicCoreError("responsible project and role are required")
    if not material["target_product"] and not material["target_subsystem"]:
        raise PublicCoreError("at least one target is required")
    if not material["route"] or not material["scope_key"]:
        raise PublicCoreError("route and scope_key are required")
    return material


def compute_dedup_key(material: dict) -> str:
    payload = json.dumps(
        material, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def validate_task_state(state: dict) -> None:
    if state.get("schema") != "usw.task_state" or state.get("version") != 1:
        raise PublicCoreError("schema/version mismatch")
    if state.get("execution_status") not in EXECUTION_STATES:
        raise PublicCoreError("invalid execution status")
    result = state.get("last_result") or {}
    if result.get("classification") not in RESULT_CLASSIFICATIONS:
        raise PublicCoreError("invalid result classification")
    if not isinstance(state.get("state_revision"), int) or state["state_revision"] < 1:
        raise PublicCoreError("invalid state revision")
    if not isinstance(state.get("events"), list) or not state["events"]:
        raise PublicCoreError("events missing")


def deterministic_launch_identity(request_id: str, task_id: str,
                                  task_state_revision: int,
                                  lease_generation: int) -> tuple[str, str, str]:
    if task_state_revision < 1 or lease_generation < 1:
        raise PublicCoreError("revision/generation must be positive")
    material = {
        "request_id": request_id,
        "task_id": task_id,
        "task_state_revision": task_state_revision,
        "lease_generation": lease_generation,
    }
    encoded = json.dumps(
        material, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    return (
        f"exec-{digest[:24]}",
        f"sha256:{digest}",
        f"usw-run-{digest[:48]}",
    )


def classify_work(*, execution_status: str, lease_age_seconds: int | None,
                  lease_timeout_seconds: int,
                  remote_status: str | None = None) -> str:
    if execution_status == "NEED_DECISION":
        return "NEED_OWNER_DECISION"
    if execution_status == "BLOCKED":
        return "EXTERNAL_BLOCKED"
    if execution_status in {"READY_FOR_AUDITION", "ACCEPTED", "CLOSED"}:
        return "TERMINAL_OR_OWNER_GATE"
    if execution_status == "WAITING_REMOTE" and remote_status in {"queued", "in_progress"}:
        return "WAITING_EXTERNAL"
    if lease_age_seconds is None:
        return "STALE_WORKER"
    if lease_age_seconds <= lease_timeout_seconds:
        return "HEALTHY"
    if execution_status == "WAITING_REMOTE" and remote_status == "completed":
        return "RESUME_NEEDED"
    return "STALE_WORKER"


OWNER_GATED_EXECUTION_STATES = {"NEED_DECISION", "READY_FOR_AUDITION", "BLOCKED"}


def evaluate_finalizer_state(*, request: dict, task_state: dict, ownership_status: str) -> dict:
    if request.get("schema") != "usw.public.finalizer_eval" or request.get("version") != 1:
        raise PublicCoreError("finalizer request schema/version mismatch")

    expected_revision = request.get("expected_state_revision")
    if not isinstance(expected_revision, int) or expected_revision < 1:
        raise PublicCoreError("invalid expected state revision")

    expected_owner = request.get("expected_ownership_state", "ACTIVE")
    if ownership_status != expected_owner:
        return {"status": "REJECTED", "classification": "STALE_OWNERSHIP"}

    if task_state.get("state_revision") != expected_revision:
        return {"status": "REJECTED", "classification": "STALE_REVISION"}

    execution_status = task_state.get("execution_status")
    result_class = (task_state.get("last_result") or {}).get("classification")

    if execution_status in OWNER_GATED_EXECUTION_STATES:
        return {
            "status": "REJECTED",
            "classification": execution_status,
            "owner_gate": True,
        }

    if execution_status == "WAITING_REMOTE" or result_class == "PENDING":
        return {"status": "REJECTED", "classification": "QUALIFICATION_AMBIGUOUS"}

    if result_class == "FAIL":
        return {"status": "REJECTED", "classification": "QUALIFICATION_FAIL"}

    if result_class not in {"PASS", "NONE"}:
        return {"status": "REJECTED", "classification": "RESULT_STATE_INVALID"}

    return {
        "status": "ELIGIBLE",
        "classification": "READY_TO_FINALIZE",
        "next_stage": "READY_TO_FINALIZE",
        "expected_revision": expected_revision,
    }


def _resume_identity(observation: dict) -> str:
    return "|".join([
        str(observation.get("source", "")),
        str(observation.get("run_id", "")),
        str(observation.get("sequence", "")),
        str(observation.get("classification", "")),
    ])


def decide_auto_resume(*, task_state: dict, observation: dict, overlay: dict | None = None) -> dict:
    overlay = overlay or {}

    status = task_state.get("execution_status")
    if status in OWNER_GATED_EXECUTION_STATES:
        return {"decision": "NO_AUTO_RESTART", "reason": status, "owner_gate": True}

    classification = observation.get("classification")
    if classification not in {"PASS", "FAIL"}:
        raise PublicCoreError("invalid observation classification")

    seq = observation.get("sequence")
    if not isinstance(seq, int) or seq < 0:
        raise PublicCoreError("invalid observation sequence")

    identity = _resume_identity(observation)
    if overlay.get("last_identity") == identity:
        return {"decision": "DUPLICATE_IGNORED", "identity": identity}

    last_seq = overlay.get("last_sequence")
    if isinstance(last_seq, int) and seq < last_seq:
        return {"decision": "STALE_IGNORED", "identity": identity}

    observed_revision = observation.get("state_revision")
    current_revision = task_state.get("state_revision")
    if (
        isinstance(observed_revision, int)
        and isinstance(current_revision, int)
        and observed_revision < current_revision
        and observation.get("run_id") != task_state.get("last_remote_builder_run_id")
    ):
        return {
            "decision": "STALE_IGNORED",
            "identity": identity,
            "reason": "OLDER_REVISION",
        }

    return {
        "decision": "APPLY_AND_RESUME",
        "identity": identity,
        "classification": classification,
        "run_id": observation.get("run_id"),
        "sequence": seq,
        "next_execution_status": "WORKING",
    }


PUBLIC_JOB_SAFETY = {
    "private_repo": False,
    "external_auth": False,
    "private_artifacts": False,
    "proprietary_data": False,
    "logs_public": True,
}

PUBLIC_JOB_WORKLOADS = {
    "FINALIZER_STATE_EVAL",
    "AUTO_RESUME_DECISION",
    "GUI_COMPONENT_VALIDATE",
}


def validate_public_job_request(req: dict) -> None:
    required = {"schema", "version", "request_id", "workload", "public_safety", "payload"}
    if req.get("schema") != "usw.public_job_request" or req.get("version") != 1:
        raise PublicCoreError("public job schema/version mismatch")
    if set(req) != required:
        raise PublicCoreError("public job fields mismatch")
    if not isinstance(req.get("request_id"), str) or not req["request_id"] or len(req["request_id"]) > 96:
        raise PublicCoreError("public job request id invalid")
    if req.get("workload") not in PUBLIC_JOB_WORKLOADS:
        raise PublicCoreError("public job workload not allowed")
    if req.get("public_safety") != PUBLIC_JOB_SAFETY:
        raise PublicCoreError("public safety facts are not explicit PASS")
    if not isinstance(req.get("payload"), dict):
        raise PublicCoreError("public job payload invalid")
