from __future__ import annotations

TERMINAL = {"PASS", "FAIL", "CANCELLED", "SUPERSEDED"}


class QueueStateError(RuntimeError):
    pass


def reconcile_supersedence(requests: dict[str, dict]) -> None:
    groups: dict[str, list[dict]] = {}
    for req in requests.values():
        if req.get("status") not in {"READY", "DEFERRED_OWNER_GATE"}:
            continue
        key = str(req.get("supersedence_key") or "")
        if not key:
            raise QueueStateError("SUPERSEDENCE_KEY_MISSING")
        groups.setdefault(key, []).append(req)

    for group in groups.values():
        if len(group) < 2:
            continue
        group.sort(key=lambda r: (str(r.get("created_at") or ""), str(r["request_id"])))
        keep = group[-1]["request_id"]
        for req in group[:-1]:
            req["status"] = "SUPERSEDED"
            req["result"] = {"classification": "SUPERSEDED", "superseded_by": keep}


def select_ready(requests: dict[str, dict]) -> dict | None:
    reconcile_supersedence(requests)
    ready = []
    for req in requests.values():
        gate = req.get("owner_gate") or {"status": "SATISFIED"}
        if req.get("status") == "READY" and gate.get("status") == "SATISFIED":
            ready.append(req)
    ready.sort(key=lambda r: (-int(r.get("priority", 0)), str(r.get("created_at") or ""), str(r["request_id"])))
    return ready[0] if ready else None


def mark_running(requests: dict[str, dict], request_id: str, run_id: str) -> None:
    req = requests.get(request_id)
    if req is None:
        raise QueueStateError("REQUEST_NOT_FOUND")
    if req.get("status") == "RUNNING":
        return
    if req.get("status") != "READY":
        raise QueueStateError("REQUEST_NOT_RUNNABLE")
    gate = req.get("owner_gate") or {"status": "SATISFIED"}
    if gate.get("status") != "SATISFIED":
        raise QueueStateError("OWNER_GATE_NOT_SATISFIED")
    req["status"] = "RUNNING"
    req["result"] = {"classification": "RUNNING", "run_id": str(run_id)}


def mark_result(requests: dict[str, dict], request_id: str, result: str, run_id: str) -> None:
    if result not in {"PASS", "FAIL"}:
        raise QueueStateError("RESULT_INVALID")
    req = requests.get(request_id)
    if req is None:
        raise QueueStateError("REQUEST_NOT_FOUND")
    if req.get("status") in {"PASS", "FAIL"}:
        if req["status"] != result:
            raise QueueStateError("RESULT_CONFLICT")
        return
    if req.get("status") not in {"READY", "RUNNING"}:
        raise QueueStateError("REQUEST_NOT_RESULTABLE")
    req["status"] = result
    req["result"] = {"classification": result, "run_id": str(run_id)}
