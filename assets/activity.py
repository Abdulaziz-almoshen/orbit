#!/usr/bin/env python3
"""
Orbit observability — the "who's talking" event stream, the live checklist, and the run snapshot.

Both the loop and individual roles (and the hook collector, bin/orbit-hook) call into this so the
activity thread, task list, and run summary stay current. Everything here is best-effort and never
raises into the caller — if the disk is read-only or a field is missing, it degrades to a no-op.

Writes (all under $ORBIT_DIR, default .orbit/):
  activity.jsonl   append-only thread — one schema-2 JSON event per line (who · phase · what · cost)
  tasks.json       the checklist (id, title, owner, status)
  run.json         a compact, atomically-written snapshot for fast rendering (phase, active role,
                   done/total, elapsed, totals, confidence, blocked question) — see snapshot()

Event schema (v2), all fields optional except ts/role:
  {schema, ts, run_id, cycle, role, phase, status, task_id, msg,
   tokens, cost_usd, confidence_delta, proof:{kind,status,detail}, files:[...]}
Schema-1 events (no `schema`, `who` instead of `role`) still render — the dashboard is defensive.

Render the live view with the bundled `orbit-status` script (a second terminal pane), or mirror
tasks.json into Claude Code's TaskCreate/TaskUpdate for the native pinned checklist.
"""
from __future__ import annotations
import json
import os
import time
import uuid
from pathlib import Path

SCHEMA = 2
ORBIT_DIR = Path(os.environ.get("ORBIT_DIR", ".orbit"))
ACTIVITY = ORBIT_DIR / "activity.jsonl"
TASKS = ORBIT_DIR / "tasks.json"
RUN = ORBIT_DIR / "run.json"

PHASES = ("plan", "act", "evaluate", "update", "decide", "read", "route", "build", "verify",
          "safety", "report")
STATUSES = ("start", "info", "done", "blocked", "failed")
TASK_STATES = ("pending", "in_progress", "done", "skipped")

# Lifecycle phase ordering per mode — used only to render a phase strip; see assets/lifecycle.py.
LIFECYCLES = {
    "feature":  ["discover", "plan", "build", "verify", "safety", "report"],
    "bug":      ["reproduce", "diagnose", "fix", "regression", "report"],
    "design":   ["taste", "prototype", "select", "implement", "pixel-qa"],
    "refactor": ["map", "change", "compatibility", "tests", "review"],
    "data":     ["validate", "transform", "compare", "safety", "report"],
}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def _write_atomic(path: Path, data) -> None:
    """Write JSON via a temp file + os.replace so a reader never sees a half-written snapshot."""
    try:
        ORBIT_DIR.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        os.replace(tmp, path)
    except Exception:
        pass


# --------------------------------------------------------------------------- run lifecycle
def current_run_id() -> str:
    """The active run's id — from run.json, or a fresh one persisted if none exists yet."""
    run = _read_json(RUN, {})
    rid = run.get("run_id")
    if rid:
        return rid
    return new_run().get("run_id", "")


def new_run(mode: str = "", goal: str = "", run_id: str | None = None) -> dict:
    """Start a fresh run: new run_id + a zeroed snapshot. Called by the loop / a SessionStart hook /
    orbit-run at the start of a run. Returns the snapshot dict."""
    snap = {
        "schema": SCHEMA,
        "run_id": run_id or uuid.uuid4().hex,
        "mode": mode or "",
        "goal": goal or "",
        "started_ts": _now(),
        "last_ts": _now(),
        "cycle": 0,
        "phase": "",
        "active_role": "",
        "active_task": "",
        "tokens": 0,
        "cost_usd": 0.0,
        "confidence": 0,
        "blocked_question": None,
    }
    _write_atomic(RUN, snap)
    return snap


def set_mode(mode: str) -> None:
    """Record the detected lifecycle mode (feature/bug/design/refactor/data) on the snapshot."""
    snap = _read_json(RUN, {})
    if not snap:
        snap = new_run(mode=mode)
    else:
        snap["mode"] = mode
        _write_atomic(RUN, snap)


def _tasks_progress():
    tasks = _read_json(TASKS, [])
    if not isinstance(tasks, list):
        return 0, 0
    done = sum(1 for t in tasks if isinstance(t, dict) and t.get("status") == "done")
    return done, len(tasks)


def _update_snapshot(ev: dict) -> None:
    """Fold one event into run.json (O(1), running accumulators — never rescans the log)."""
    snap = _read_json(RUN, {})
    if not snap or "run_id" not in snap:
        snap = new_run()
    snap["schema"] = SCHEMA
    snap["last_ts"] = ev.get("ts", _now())
    if ev.get("cycle") is not None:
        snap["cycle"] = ev.get("cycle")
    if ev.get("phase"):
        snap["phase"] = ev["phase"]
    role, status = ev.get("role", ""), ev.get("status", "")
    if role and status in ("start", "info"):
        snap["active_role"] = role
    if ev.get("task_id") and status in ("start", "info"):
        snap["active_task"] = ev["task_id"]
    try:
        snap["tokens"] = int(snap.get("tokens", 0)) + int(ev.get("tokens", 0) or 0)
    except Exception:
        pass
    try:
        snap["cost_usd"] = round(float(snap.get("cost_usd", 0.0)) + float(ev.get("cost_usd", 0.0) or 0.0), 6)
    except Exception:
        pass
    try:
        cd = int(ev.get("confidence_delta", 0) or 0)
        snap["confidence"] = max(0, min(100, int(snap.get("confidence", 0)) + cd))
    except Exception:
        pass
    if status == "blocked" and ev.get("msg"):
        snap["blocked_question"] = ev["msg"]
    elif status in ("done", "start") and role != "human":
        snap["blocked_question"] = snap.get("blocked_question")  # cleared explicitly via clear_block()
    done, total = _tasks_progress()
    snap["tasks_done"], snap["tasks_total"] = done, total
    _write_atomic(RUN, snap)


def clear_block() -> None:
    snap = _read_json(RUN, {})
    if snap:
        snap["blocked_question"] = None
        _write_atomic(RUN, snap)


# --------------------------------------------------------------------------- events + tasks
def emit(role: str, phase: str = "", status: str = "info", msg: str = "",
         cycle=None, task_id=None, tokens=None, cost_usd=None,
         confidence_delta=None, proof=None, files=None) -> None:
    """Record one 'who said what' event (schema 2) AND echo it inline as `[role] (phase) msg`,
    then fold it into the run.json snapshot. Extra fields are optional and only stored when given.

    role:   which agent is speaking — 'orchestrator', 'builder', 'safety', 'reviewer', …
    phase:  where in the cycle/lifecycle we are (one of PHASES, loosely)
    status: start / info / done / blocked / failed
    tokens / cost_usd:  this step's spend (folded into the run totals)
    confidence_delta:   +/- points to move delivery confidence (see assets/confidence.py)
    proof:  {"kind": "test|lint|review|...", "status": "pass|fail", "detail": "..."}
    files:  paths this event touched
    """
    try:
        ORBIT_DIR.mkdir(parents=True, exist_ok=True)
        ev = {"schema": SCHEMA, "ts": _now(), "run_id": current_run_id(),
              "role": role, "phase": phase, "status": status, "msg": msg}
        if cycle is not None:
            ev["cycle"] = cycle
        if task_id is not None:
            ev["task_id"] = task_id
        if tokens is not None:
            ev["tokens"] = tokens
        if cost_usd is not None:
            ev["cost_usd"] = cost_usd
        if confidence_delta is not None:
            ev["confidence_delta"] = confidence_delta
        if proof is not None:
            ev["proof"] = proof
        if files is not None:
            ev["files"] = files
        with ACTIVITY.open("a") as f:
            f.write(json.dumps(ev) + "\n")
        _update_snapshot(ev)
        tag = f"[{role}]" + (f" ({phase})" if phase else "")
        print(f"{tag} {msg}".rstrip(), flush=True)
    except Exception:
        pass


def set_tasks(tasks) -> None:
    """Replace the whole checklist. tasks: list of {id, title, owner, status}."""
    try:
        ORBIT_DIR.mkdir(parents=True, exist_ok=True)
        TASKS.write_text(json.dumps(list(tasks), indent=2))
        _update_snapshot({"ts": _now()})            # refresh done/total on the snapshot
    except Exception:
        pass


def update_task(task_id: str, status: str, owner: str | None = None) -> None:
    """Move one task to a new status (pending|in_progress|done|skipped)."""
    try:
        tasks = _read_json(TASKS, [])
        for t in tasks:
            if isinstance(t, dict) and t.get("id") == task_id:
                t["status"] = status
                if owner:
                    t["owner"] = owner
                break
        TASKS.write_text(json.dumps(tasks, indent=2))
        _update_snapshot({"ts": _now()})
    except Exception:
        pass
