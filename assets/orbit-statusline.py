#!/usr/bin/env python3
"""
orbit-statusline — the one-line Claude Code status line for an Orbit run.

Claude Code runs this every couple of seconds with its status-line JSON on stdin. We fuse that
(context %, cost, cache reuse, model) with the project's .orbit/run.json (phase, active role,
task progress, confidence, blocked state) into a single compact line, e.g.:

  🛰 build · builder · 5/9 · ctx 38% · $0.42 · cache 61% · conf 76%
  🛰 ⚠ needs input · build · 5/9 · ctx 38% · $0.42            (when a decision is pending)

Design rules: FAST (runs on a 2s refresh) and FAIL-SAFE — any missing/renamed field just drops
that one segment; a total failure prints an empty line, never a traceback. Cache reuse is labeled
honestly ("cache") — it's cache_read / total_input, NOT a fabricated "tokens saved".

Install: `.claude/settings.json` → {"statusLine": {"type":"command",
"command":"python3 \"$CLAUDE_PROJECT_DIR/scripts/orbit-statusline\"", "refreshInterval": 2}}.
Orbit wires this only if you don't already have a status line (never overwrites yours).
"""
import json
import os
import sys
import time
from pathlib import Path


def _get(d, *path, default=None):
    """Safe nested get: _get(data, 'context_window', 'used_percentage')."""
    cur = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def _find_orbit(start):
    """Nearest .orbit/ from `start` upward, so the status line still finds the repo-root scaffold
    when Claude is working in a subdir. None if none found."""
    try:
        cur = Path(start).resolve()
    except Exception:
        return None
    for p in [cur, *cur.parents]:
        if (p / ".orbit").is_dir():
            return p / ".orbit"
    return None


def _age_seconds(iso_ts):
    """Seconds since an ISO 'YYYY-MM-DDTHH:MM:SSZ', or None if unparseable."""
    try:
        t = time.strptime(str(iso_ts), "%Y-%m-%dT%H:%M:%SZ")
        return max(0, int(time.time() - time.mktime(t) + time.timezone))
    except Exception:
        return None


def _active_agent(agents: dict):
    """The agent working now (first with status active/blocked), or None."""
    if not isinstance(agents, dict):
        return None
    cands = [dict(v, role=k) for k, v in agents.items()
             if isinstance(v, dict) and v.get("status") in ("active", "blocked")]
    cands.sort(key=lambda x: (x.get("seq", 99), x.get("role", "")))
    return cands[0] if cands else None


def _dur(secs):
    if secs is None:
        return ""
    return f"{secs}s" if secs < 60 else f"{secs // 60}m{secs % 60}s" if secs < 3600 else f"{secs // 3600}h"


def build_line(claude: dict, run: dict, agents: dict = None, lock_seg: str = "") -> str:
    seg = []
    if lock_seg:
        seg.append(lock_seg)                       # 🔒 read-only — another session holds the writer lock
    blocked = run.get("blocked_question")
    if blocked:
        seg.append("⚠ needs input")

    # slice/task first, then the human-readable active agent + how long it's been at it
    slice_ = run.get("active_task")
    ag = _active_agent(agents or {})
    if slice_ or (ag and ag.get("task")):
        seg.append(str(slice_ or ag.get("task")))
    if ag and not blocked:
        name = ag.get("display") or ag.get("role") or "agent"
        el = _dur(_age_seconds(ag.get("started_at")))
        seg.append(f"{name}{(' ' + el) if el else ''}")
    elif run.get("active_role") and not blocked:
        seg.append(str(run["active_role"]))
    elif run.get("phase") or run.get("mode"):
        seg.append(str(run.get("phase") or run.get("mode")))

    total = run.get("tasks_total")
    if isinstance(total, int) and total > 0:
        seg.append(f"{run.get('tasks_done', 0)}/{total}")

    # quiet: surface it once it's meaningful (the run may be waiting on the active agent)
    age = _age_seconds(run.get("last_ts"))
    if age is not None and age >= 60:
        seg.append(f"quiet {_dur(age)}")

    ctx = _get(claude, "context_window", "used_percentage")
    if isinstance(ctx, (int, float)):
        seg.append(f"ctx {int(ctx)}%")

    cost = _get(claude, "cost", "total_cost_usd")
    if isinstance(cost, (int, float)):
        seg.append(f"${cost:.2f}")

    # cache reuse = cache_read / total_input (honest label — not "tokens saved")
    cur = _get(claude, "context_window", "current_usage", default={})
    total_in = _get(claude, "context_window", "total_input_tokens")
    cache_read = cur.get("cache_read_input_tokens") if isinstance(cur, dict) else None
    if isinstance(total_in, (int, float)) and total_in and isinstance(cache_read, (int, float)):
        seg.append(f"cache {int(100 * cache_read / total_in)}%")

    conf = run.get("confidence")
    if isinstance(conf, (int, float)):
        seg.append(f"conf {int(conf)}%")

    return "🛰 " + " · ".join(seg) if seg else ""


def main():
    try:
        claude = json.load(sys.stdin)
        if not isinstance(claude, dict):
            claude = {}
    except Exception:
        claude = {}
    # Prefer the ORIGINAL project dir (repo root) over cwd, then walk up — so a subdir still finds it.
    orbit = None
    for cand in (_get(claude, "workspace", "project_dir"), claude.get("cwd"),
                 _get(claude, "workspace", "current_dir"), os.environ.get("CLAUDE_PROJECT_DIR"), "."):
        if cand:
            orbit = _find_orbit(cand)
            if orbit:
                break
    try:
        run = json.loads((orbit / "run.json").read_text()) if orbit else {}
        if not isinstance(run, dict):
            run = {}
    except Exception:
        run = {}
    try:
        agents = json.loads((orbit / "agents.json").read_text()) if orbit else {}
        if not isinstance(agents, dict):
            agents = {}
    except Exception:
        agents = {}
    lock_seg = ""
    try:                                                    # 🔒 only when ANOTHER session holds the lock
        lk = json.loads((orbit / "locks" / "active-writer.json").read_text()) if orbit else {}
        me = (claude.get("session_id") or os.environ.get("ORBIT_SESSION_ID")
              or os.environ.get("CLAUDE_SESSION_ID") or os.environ.get("TERM_SESSION_ID"))
        if isinstance(lk, dict) and lk.get("owner_id") and lk.get("owner_id") != me:
            lock_seg = "🔒 read-only"
    except Exception:
        lock_seg = ""
    try:
        print(build_line(claude, run, agents, lock_seg))
    except Exception:
        print("")                                           # never crash the status line


if __name__ == "__main__":
    main()
