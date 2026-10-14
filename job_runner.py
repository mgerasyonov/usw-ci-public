from __future__ import annotations

import argparse
import json
from pathlib import Path

class JobRunnerError(ValueError):
    pass

from finalizer_state_core import evaluate_finalization
from auto_resume_core import decide_resume
from gui_component_schema import validate_component_contract

ALLOWED_WORKLOADS = {
    "FINALIZER_STATE_EVAL",
    "AUTO_RESUME_DECISION",
    "GUI_COMPONENT_VALIDATE",
}

REQUIRED_SAFETY = {
    "private_repo": False,
    "external_auth": False,
    "private_artifacts": False,
    "proprietary_data": False,
    "logs_public": True,
}


def validate_request(req: dict) -> None:
    if req.get("schema") != "usw.public_job_request" or req.get("version") != 1:
        raise JobRunnerError("REQUEST_SCHEMA_INVALID")
    required = {"schema", "version", "request_id", "workload", "public_safety", "payload"}
    if set(req) != required:
        raise JobRunnerError("REQUEST_FIELDS_INVALID")
    if not isinstance(req["request_id"], str) or not req["request_id"] or len(req["request_id"]) > 96:
        raise JobRunnerError("REQUEST_ID_INVALID")
    if req["workload"] not in ALLOWED_WORKLOADS:
        raise JobRunnerError("WORKLOAD_NOT_ALLOWED")
    if req["public_safety"] != REQUIRED_SAFETY:
        raise JobRunnerError("PUBLIC_SAFETY_NOT_EXPLICITLY_PASS")
    if not isinstance(req["payload"], dict):
        raise JobRunnerError("PAYLOAD_INVALID")


def run_request(req: dict) -> dict:
    validate_request(req)
    workload = req["workload"]
    payload = req["payload"]

    if workload == "FINALIZER_STATE_EVAL":
        expected = {"request", "task_state", "ownership_status"}
        if set(payload) != expected:
            raise JobRunnerError("FINALIZER_PAYLOAD_FIELDS_INVALID")
        output = evaluate_finalization(
            request=payload["request"],
            task_state=payload["task_state"],
            ownership_status=payload["ownership_status"],
        )
    elif workload == "AUTO_RESUME_DECISION":
        expected = {"task_state", "observation", "overlay"}
        if set(payload) != expected:
            raise JobRunnerError("AUTO_RESUME_PAYLOAD_FIELDS_INVALID")
        output = decide_resume(
            task_state=payload["task_state"],
            observation=payload["observation"],
            overlay=payload["overlay"],
        )
    else:
        if set(payload) != {"component"}:
            raise JobRunnerError("GUI_COMPONENT_PAYLOAD_FIELDS_INVALID")
        output = validate_component_contract(payload["component"])

    return {
        "schema": "usw.public_job_result",
        "version": 1,
        "request_id": req["request_id"],
        "workload": workload,
        "status": "PASS",
        "output": output,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    request_path = Path(args.request)
    out_path = Path(args.out)

    try:
        req = json.loads(request_path.read_text(encoding="utf-8"))
        result = run_request(req)
        rc = 0
    except Exception as exc:
        result = {
            "schema": "usw.public_job_result",
            "version": 1,
            "status": "FAIL",
            "error": f"{exc.__class__.__name__}:{exc}",
        }
        rc = 2

    out_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, sort_keys=True))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
