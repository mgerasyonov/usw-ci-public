from __future__ import annotations

OWNER_GATED = {"NEED_DECISION", "READY_FOR_AUDITION", "BLOCKED"}

class AutoResumeError(ValueError):
    pass
