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
