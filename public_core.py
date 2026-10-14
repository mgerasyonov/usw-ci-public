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
