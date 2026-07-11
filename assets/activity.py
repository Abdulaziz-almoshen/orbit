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

# Activity is TELEMETRY, not memory — the append-only log must never grow into token debt (a subagent
# that reads a 400KB log burns ~100k tokens). Cap it: keep the last KEEP_EVENTS live, archive the rest.
MAX_ACTIVITY_BYTES = int(os.environ.get("ORBIT_ACTIVITY_MAX_BYTES", 256 * 1024))
KEEP_EVENTS = int(os.environ.get("ORBIT_ACTIVITY_KEEP", 500))


def _rotate_activity() -> None:
    """Cap activity.jsonl: keep the last KEEP_EVENTS events live, append older ones to a dated archive
    under .orbit/archive/activity/. Only runs when the file crosses MAX_ACTIVITY_BYTES (checked via a
    cheap stat), so it's near-free per emit and self-limiting. Fails open — telemetry never breaks the run."""
    try:
        if not ACTIVITY.exists() or ACTIVITY.stat().st_size <= MAX_ACTIVITY_BYTES:
            return
        lines = [ln for ln in ACTIVITY.read_text().splitlines() if ln.strip()]
        if len(lines) <= KEEP_EVENTS:
            return
        old, keep = lines[:-KEEP_EVENTS], lines[-KEEP_EVENTS:]
        arc_dir = ORBIT_DIR / "archive" / "activity"
        arc_dir.mkdir(parents=True, exist_ok=True)
        arc = arc_dir / f"activity-{time.strftime('%Y-%m-%d', time.gmtime())}.jsonl"
        with arc.open("a") as f:
            f.write("\n".join(old) + "\n")
        tmp = ACTIVITY.with_name("activity.jsonl.tmp")
        tmp.write_text("\n".join(keep) + "\n")
        tmp.replace(ACTIVITY)                          # atomic swap — no reader ever sees a half-file
    except Exception:
        pass
TASKS = ORBIT_DIR / "tasks.json"
RUN = ORBIT_DIR / "run.json"
AGENTS = ORBIT_DIR / "agents.json"

# Known roles → (human display name, one-line responsibility). Used to build the team board so a
# queued agent reads like a person with a job, not a slug. Unknown roles get a title-cased name.
ROLE_INFO = {
    "dispatcher": ("Dispatcher", "routes the request (task vs question)"),
    "orchestrator": ("Orchestrator", "plans + conducts the loop, owns state"),
    "product-discovery": ("Product Discovery", "de-risks the bet before building"),
    "market-researcher": ("Market Researcher", "what exists, reuse-vs-build, the gap"),
    "planner": ("Planner", "slices the work + sets the proof bar"),
    "builder": ("Builder", "produces the core output"),
    "frontend-engineer": ("Frontend Engineer", "builds the web UI"),
    "backend-engineer": ("Backend Engineer", "builds the API / services"),
    "mobile-developer": ("Mobile Developer", "builds the mobile app"),
    "data-engineer": ("Data Engineer", "data pipelines / ETL / ML"),
    "cli-engineer": ("CLI Engineer", "builds the command-line tool"),
    "designer": ("Designer", "distinctive, on-brand UI from picked prototypes"),
    "reviewer": ("Reviewer", "checks correctness + regressions, proves the diff"),
    "qa-engineer": ("QA Engineer", "validates the product vs the requirements (RTM)"),
    "safety-gate": ("Safety", "confirms no unsafe/outward action without approval"),
    "reporter": ("Reporter", "summarizes proof + remaining risk"),
    "human": ("You", "decisions the loop pauses for"),
    "subagent": ("Sub-agent", "a spawned worker"),
}

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


# --------------------------------------------------------------------------- the team roster
def role_display(role: str) -> str:
    info = ROLE_INFO.get(role)
    return info[0] if info else (role or "").replace("-", " ").replace("_", " ").title()


def role_responsibility(role: str) -> str:
    info = ROLE_INFO.get(role)
    return info[1] if info else ""


def _blank_agent(role: str) -> dict:
    return {"display": role_display(role), "responsibility": role_responsibility(role),
            "task": "", "status": "idle", "started_at": None, "last_event_at": None,
            "mission": "", "last_message": ""}


def agent_update(role: str, status: str = None, task: str = None, message: str = None) -> None:
    """Fold one signal into .orbit/agents.json — the live team roster the dashboard/status line read.
    status: active | queued | done | blocked | failed | idle. `started_at` is stamped the moment a
    role goes active (so the board can show 'active 4m 52s'). Fail-safe; never raises."""
    if not role or role == "?":
        return
    try:
        agents = _read_json(AGENTS, {})
        if not isinstance(agents, dict):
            agents = {}
        a = agents.get(role) or _blank_agent(role)
        a.setdefault("display", role_display(role))
        a.setdefault("responsibility", role_responsibility(role))
        now = _now()
        if status == "active" and (a.get("status") != "active" or not a.get("started_at")):
            a["started_at"] = now                 # (re)entering active — or active-without-a-clock — starts it
            a["mission"] = ""                     # a fresh stint gets a fresh mission line
        if status:
            a["status"] = status
        if task:
            a["task"] = task
        if message:
            if a.get("status") == "active" and not a.get("mission"):
                a["mission"] = message            # the first substantive line of this stint = the mission
            a["last_message"] = message
        a["last_event_at"] = now
        agents[role] = a
        _write_atomic(AGENTS, agents)
    except Exception:
        pass


def set_team(assignments) -> None:
    """Declare the run's team + plan up front (the orchestrator calls this before dispatching, so the
    dashboard can show WHO IS QUEUED and their job — a real standup, not just who's already talking).
    assignments: ordered list of {role, task?, status? (default 'queued'), responsibility?}. Order is
    preserved as 'seq' so the board can render the queue + derive each agent's 'next'."""
    try:
        agents = _read_json(AGENTS, {})
        if not isinstance(agents, dict):
            agents = {}
        for i, item in enumerate(assignments or []):
            if not isinstance(item, dict) or not item.get("role"):
                continue
            role = item["role"]
            a = agents.get(role) or _blank_agent(role)
            a["display"] = a.get("display") or role_display(role)
            a["responsibility"] = item.get("responsibility") or a.get("responsibility") or role_responsibility(role)
            a["status"] = item.get("status") or (a.get("status") if a.get("status") != "idle" else "queued")
            if item.get("task"):
                a["task"] = item["task"]
            a["seq"] = i
            agents[role] = a
        _write_atomic(AGENTS, agents)
    except Exception:
        pass


# emit() status → the roster status the board shows.
_EMIT_TO_AGENT = {"start": "active", "info": "active", "done": "done",
                  "blocked": "blocked", "failed": "failed"}


# --------------------------------------------------------------------------- decision cards
PENDING = ORBIT_DIR / "pending-question.json"


def ask(title: str, why: str = "", recommended: str = "", options=None) -> None:
    """Record a decision card (the headless equivalent of AskUserQuestion) to
    .orbit/pending-question.json, pin it on run.json, and log a blocked event. `options` is a list
    of {"id", "label", "tradeoff"}. On the interactive path, use the AskUserQuestion tool instead —
    this is what makes a pending decision visible in orbit-status when there's no chat to ask in."""
    card = {
        "schema": SCHEMA,
        "ts": _now(),
        "run_id": current_run_id(),
        "title": title or "Decision needed",
        "why": why or "",
        "recommended": recommended or "",
        "options": [o for o in (options or []) if isinstance(o, dict)],
    }
    _write_atomic(PENDING, card)
    emit("human", "decide", "blocked", f"decision needed: {card['title']}")
    snap = _read_json(RUN, {})                    # set the CLEAN title last (emit set it to the msg)
    if not snap:
        snap = new_run()
    snap["blocked_question"] = card["title"]
    _write_atomic(RUN, snap)


def resolve_question(answer: str = "") -> None:
    """Clear a pending decision card once it's answered (unblocks the run)."""
    try:
        if PENDING.exists():
            PENDING.unlink()
    except Exception:
        pass
    clear_block()
    if answer:
        emit("human", "decide", "info", f"decision: {answer}")


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
        _rotate_activity()                             # keep the live log bounded (telemetry ≠ memory)
        _update_snapshot(ev)
        # keep the team roster live off the same signal (so orbit-hook's emits feed it for free)
        if role and role != "?":
            agent_update(role, status=_EMIT_TO_AGENT.get(status), task=task_id, message=msg or None)
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
