#!/usr/bin/env python3
"""
Orbit observability — the "who's talking" event stream + the live checklist.

Both the loop and individual roles call into this so the activity thread and the task
list stay current. Everything here is best-effort and never raises into the caller — if
the disk is read-only or a field is missing, it degrades to a no-op.

Writes (all under $ORBIT_DIR, default .orbit/):
  activity.jsonl   append-only thread, one JSON event per line (who · phase · what)
  tasks.json       the checklist (id, title, owner, status)

Render the live view with the bundled `orbit-status` script (a second terminal pane), or
mirror tasks.json into Claude Code's TaskCreate/TaskUpdate for the native pinned checklist.
"""
from __future__ import annotations
import json
import os
import time
from pathlib import Path

ORBIT_DIR = Path(os.environ.get("ORBIT_DIR", ".orbit"))
ACTIVITY = ORBIT_DIR / "activity.jsonl"
TASKS = ORBIT_DIR / "tasks.json"

PHASES = ("plan", "act", "evaluate", "update", "decide", "read")
STATUSES = ("start", "done", "blocked", "info")
TASK_STATES = ("pending", "in_progress", "done", "skipped")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def emit(role: str, phase: str = "", status: str = "info", msg: str = "",
         cycle=None, task_id=None) -> None:
    """Record one 'who said what' event AND echo it inline as `[role] (phase) msg`.

    role:   which agent is speaking — 'orchestrator', 'data', 'safety', 'reviewer', …
    phase:  one of PHASES (where in the cycle we are)
    status: one of STATUSES (start / done / blocked / info)
    """
    try:
        ORBIT_DIR.mkdir(parents=True, exist_ok=True)
        ev = {"ts": _now(), "role": role, "phase": phase, "status": status, "msg": msg}
        if cycle is not None:
            ev["cycle"] = cycle
        if task_id is not None:
            ev["task_id"] = task_id
        with ACTIVITY.open("a") as f:
            f.write(json.dumps(ev) + "\n")
        tag = f"[{role}]" + (f" ({phase})" if phase else "")
        print(f"{tag} {msg}".rstrip(), flush=True)
    except Exception:
        pass


def set_tasks(tasks) -> None:
    """Replace the whole checklist. tasks: list of {id, title, owner, status}."""
    try:
        ORBIT_DIR.mkdir(parents=True, exist_ok=True)
        TASKS.write_text(json.dumps(list(tasks), indent=2))
    except Exception:
        pass


def update_task(task_id: str, status: str, owner: str | None = None) -> None:
    """Move one task to a new status (pending|in_progress|done|skipped)."""
    try:
        tasks = json.loads(TASKS.read_text()) if TASKS.exists() else []
        for t in tasks:
            if t.get("id") == task_id:
                t["status"] = status
                if owner:
                    t["owner"] = owner
                break
        TASKS.write_text(json.dumps(tasks, indent=2))
    except Exception:
        pass
