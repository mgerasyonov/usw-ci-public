from __future__ import annotations

OWNER_GATED = {"NEED_DECISION", "READY_FOR_AUDITION", "BLOCKED"}

class AutoResumeError(ValueError):
    pass

def _identity(observation: dict) -> str:
    return "|".join([
        str(observation.get("source", "")),
        str(observation.get("run_id", "")),
        str(observation.get("sequence", "")),
        str(observation.get("classification", "")),
    ])


def decide_resume(*, task_state: dict, observation: dict, overlay: dict | None = None) -> dict:
    overlay = overlay or {}
    status = task_state.get("execution_status")
    if status in OWNER_GATED:
        return {"decision": "NO_AUTO_RESTART", "reason": status}

    classification = observation.get("classification")
    if classification not in {"PASS", "FAIL"}:
        raise AutoResumeError("CLASSIFICATION_INVALID")

    seq = observation.get("sequence")
    if not isinstance(seq, int) or seq < 0:
        raise AutoResumeError("SEQUENCE_INVALID")

    identity = _identity(observation)
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
        return {"decision": "STALE_IGNORED", "identity": identity, "reason": "OLDER_REVISION"}

    return {
        "decision": "APPLY_AND_RESUME",
        "identity": identity,
        "classification": classification,
        "run_id": observation.get("run_id"),
        "sequence": seq,
        "next_execution_status": "WORKING",
    }
