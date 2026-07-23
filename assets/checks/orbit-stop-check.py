#!/usr/bin/env python3
"""
orbit-stop-check.py — Orbit's Stop hook: the observability backstop.

When the main agent finishes a turn, this checks whether a routed TASK actually ran through Orbit's
visible operating model. The failure it catches: a task that did real work but produced NO board —
no `.orbit/tasks.json` checklist, no `set_team` roster — i.e. it was run as a black box (e.g. via the
native `Workflow(...)` background runner) instead of the role-tagged checklist Orbit promises. That
silently breaks the "watch the team work" contract, so it FAILS LOUDLY: it records an
observability-gap event and blocks the stop ONCE, telling the model to make the board visible.

Signal (all three, or it stays silent):
  1. a TASK was routed this turn      — route.py logged a `phase:route status:start` event and
                                         touched `.orbit/.last-task-route`;
  2. real work happened               — >= _WORK_MIN activity events were logged AFTER that route
                                         (edits / sub-agents; a trivial no-op or an answered question
                                         logs nothing, so it never fires there);
  3. the board was never updated      — neither `.orbit/tasks.json` nor `.orbit/agents.json` was
                                         written after the route.

CONSERVATIVE + FAIL-OPEN by design (a false block is worse than a missed nudge — the guard-hardening
lesson): it only fires on *substantial* work with a *completely absent* board, blocks at most once per
route (Claude Code's `stop_hook_active` + a per-route `.stop-warned` marker), and ANY error → exit 0
(allow the stop). It never blocks a turn that did no work.

Protocol: read the Stop-event JSON on stdin; print nothing to allow the stop, or
    {"decision": "block", "reason": "…"}
to make the agent continue and produce the board.
"""
import json
import os
import sys
import time
from pathlib import Path

_WORK_MIN = 3   # >= this many post-route activity events ⇒ "real work happened this turn"


def _find_orbit(start):
    proj = os.environ.get("CLAUDE_PROJECT_DIR")
    if proj and (Path(proj) / ".orbit").is_dir():
        return Path(proj) / ".orbit"
    try:
        cur = Path(start).resolve()
    except Exception:
        return None
    for p in [cur, *cur.parents]:
        if (p / ".orbit").is_dir():
            return p / ".orbit"
    return None


def _mtime(p):
    try:
        return p.stat().st_mtime
    except Exception:
        return 0.0


def _cpo_vigilance(orbit, route_mt):
    """The CPO stays on duty until the goal is achieved: when a routed task did substantial work and
    the board is visible, but no commit-bound CPO ACCEPT was recorded after the route, block the stop
    ONCE to demand a verdict (or an explicit park). The system must not quietly go to sleep with an
    open goal — 'done' is the CPO's word, not the model's feeling. Fail-open + once per route; the
    escape hatches are honest: an ACCEPT envelope, `.orbit/cpo/parked`, or disabling cpo_acceptance."""
    try:
        cfg = json.loads((orbit / "loop.config.json").read_text())
        if (cfg.get("cpo_acceptance") or {}).get("enabled") is not True:
            return
        if (orbit / "cpo" / "parked").exists():             # user explicitly parked the goal
            return
        warned = orbit / ".cpo-stop-warned"
        if warned.exists() and warned.read_text().strip() == repr(route_mt):
            return                                          # one vigilance nudge per routed task
        vdir = orbit / "cpo"
        rounds = sorted(vdir.glob("round-*.json"), key=lambda p: p.stat().st_mtime) if vdir.is_dir() else []
        if rounds and _mtime(rounds[-1]) > route_mt:
            v = json.loads(rounds[-1].read_text())
            if str(v.get("verdict", "")).upper() == "ACCEPT":
                return                                      # the CPO signed off after this route
        try:
            warned.write_text(repr(route_mt))
        except Exception:
            pass
        with (orbit / "activity.jsonl").open("a") as f:
            f.write(json.dumps({
                "schema": 2, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "role": "cpo", "phase": "evaluate", "status": "blocked",
                "msg": "CPO vigilance: substantial work stopped without a CPO verdict — "
                       "the goal is not accepted yet.",
            }) + "\n")
        print(json.dumps({"decision": "block", "reason": (
            "[orbit] CPO ON DUTY — the goal is not accepted yet. Substantial work ran this turn but "
            "no commit-bound ACCEPT exists in .orbit/cpo/. The system stays awake until the goal is "
            "achieved: dispatch the cpo subagent NOW to judge the deliverable against the user's "
            "original goal (rubric: .orbit/skills/product-acceptance.md) and write "
            ".orbit/cpo/round-<n>.json. If the verdict is ITERATE/REDEVELOP, continue the loop on its "
            "change orders. Only an ACCEPT envelope, an explicit park (write .orbit/cpo/parked with "
            "the reason and tell the user), or the user saying stop ends the watch."
        )}))
        sys.exit(0)
    except SystemExit:
        raise
    except Exception:
        return                                              # fail open — never break a stop on error


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return                                              # fail open
    if not isinstance(data, dict) or data.get("stop_hook_active"):
        return                                              # already continued once → don't loop
    orbit = _find_orbit(data.get("cwd") or ".")
    if orbit is None:
        return                                              # not a scaffolded repo → nothing to do

    route_mt = _mtime(orbit / ".last-task-route")
    if not route_mt:
        return                                              # no task routed → nothing to enforce

    warned = orbit / ".stop-warned"                         # already nudged for THIS route?
    try:
        if warned.read_text().strip() == repr(route_mt):
            return
    except Exception:
        pass

    # (2) real work logged after the route?
    try:
        events = [json.loads(l) for l in (orbit / "activity.jsonl").read_text(errors="ignore").splitlines()
                  if l.strip()]
    except Exception:
        return
    r = -1
    for i, e in enumerate(events):
        if isinstance(e, dict) and e.get("phase") == "route" and e.get("status") == "start":
            r = i
    if r < 0:
        return
    work = [e for e in events[r + 1:]
            if isinstance(e, dict) and e.get("phase") not in ("route", "observability")]
    if len(work) < _WORK_MIN:
        return                                              # not enough real work to warrant a board

    # (3) was the board updated after the route?
    if _mtime(orbit / "tasks.json") > route_mt or _mtime(orbit / "agents.json") > route_mt:
        _cpo_vigilance(orbit, route_mt)                     # board OK — but is the CPO satisfied?
        return                                              # the board WAS made visible → all good

    # GAP: substantial work, no board. Record it + block once.
    try:
        with (orbit / "activity.jsonl").open("a") as f:
            f.write(json.dumps({
                "schema": 2, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "role": "dispatcher", "phase": "observability", "status": "blocked",
                "msg": "observability gap: a task did work with no visible checklist "
                       "(no .orbit/tasks.json / set_team). Drive TaskCreate/TaskUpdate; "
                       "do NOT use the native Workflow() runner.",
            }) + "\n")
    except Exception:
        pass
    try:
        warned.write_text(repr(route_mt))
    except Exception:
        pass
    print(json.dumps({"decision": "block", "reason": (
        "[orbit] observability missing: this task did real work but never made the board visible — "
        "no .orbit/tasks.json checklist and no set_team roster were written after routing. Make it "
        "visible NOW so the user can see who owns each step: call .orbit/activity.py set_team + "
        "set_tasks and build the role-tagged TaskCreate/TaskUpdate checklist. Do NOT run Orbit tasks "
        "through the native Workflow(...) background runner — it bypasses Orbit's operating model."
    )}))


if __name__ == "__main__":
    main()
