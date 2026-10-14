from __future__ import annotations

OWNER_GATED = {"NEED_DECISION", "READY_FOR_AUDITION", "BLOCKED"}


class FinalizerStateError(ValueError):
    pass


def evaluate_finalization(*, request: dict, task_state: dict, ownership_status: str) -> dict:
    if request.get("schema") != "usw.public.finalizer_eval" or request.get("version") != 1:
        raise FinalizerStateError("REQUEST_SCHEMA_INVALID")

    expected_revision = request.get("expected_state_revision")
    if not isinstance(expected_revision, int) or expected_revision < 1:
        raise FinalizerStateError("EXPECTED_REVISION_INVALID")

    if ownership_status != request.get("expected_ownership_state", "ACTIVE"):
        return {"status": "REJECTED", "classification": "STALE_OWNERSHIP"}

    revision = task_state.get("state_revision")
    if revision != expected_revision:
        return {"status": "REJECTED", "classification": "STALE_REVISION"}

    execution_status = task_state.get("execution_status")
    result_class = (task_state.get("last_result") or {}).get("classification")

    if execution_status in OWNER_GATED:
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
        "expected_revision": revision,
    }
