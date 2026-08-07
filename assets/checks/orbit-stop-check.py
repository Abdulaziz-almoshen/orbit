#!/usr/bin/env python3
"""
orbit-stop-check.py — Orbit's Stop hook: the observability backstop.

When the main agent finishes a turn, this checks whether a routed TASK actually ran through Orbit's
visible operating model. It catches a task that did real work but produced NO board —
no `.orbit/tasks.json` checklist, no `set_team` roster — i.e. it was run as a black box (e.g. via the
native `Workflow(...)` background runner) instead of the role-tagged checklist Orbit promises. That
silently breaks the "watch the team work" contract, so it FAILS LOUDLY: it records an
observability-gap event and blocks the stop ONCE, telling the model to make the board visible.

In strict mode it also blocks a substantial run that skipped mandatory specialist owners. A role
must have a post-route `status:done` event; mentioning a role, listing it as available, or privately
using it as a mental "lens" does not count.

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
import importlib.util
import os
import sys
import time
from pathlib import Path

_WORK_MIN = 3   # shipped fallback; strict projects may set capability_enforcement.work_event_threshold


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


def _ui_project(orbit):
    """Use scaffolded surface metadata first; Designer presence is the old-project fallback."""
    try:
        setup = json.loads((orbit / "setup.json").read_text())
        surfaces = {str(s).lower() for s in setup.get("surfaces", [])}
        if surfaces & {"web", "frontend", "ui", "mobile", "ios", "android"}:
            return True
    except Exception:
        pass
    return (orbit.parent / ".claude" / "agents" / "designer.md").is_file()


def _delivery_quality_vigilance(orbit, route_mt):
    """Block every stop until the QA evidence itself passes; a `qa-engineer done` event is not proof."""
    try:
        config_path = orbit / "loop.config.json"
        if not config_path.is_file():
            return                                           # legacy/minimal test scaffold: no contract
        cfg = json.loads(config_path.read_text())
        contract = cfg.get("delivery_quality") or {}
        if contract.get("enabled") is not True:
            return
        gate_path = orbit / "checks" / "delivery-quality-gate.py"
        spec = importlib.util.spec_from_file_location("orbit_delivery_quality", gate_path)
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)
        evidence = orbit.parent / str(contract.get(
            "evidence_path", ".orbit/qa/delivery-evidence.json"))
        result = gate.evaluate(orbit.parent, evidence_path=evidence, ui_project=_ui_project(orbit),
                               contract=contract)
        if result.get("passed") and _mtime(evidence) > route_mt:
            return
        errors = list(result.get("errors") or [])
        if _mtime(evidence) <= route_mt:
            errors.insert(0, "delivery evidence is missing or stale for this routed task")
        try:
            with (orbit / "activity.jsonl").open("a") as f:
                f.write(json.dumps({
                    "schema": 2, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "role": "qa-engineer", "phase": "evaluate", "status": "blocked",
                    "msg": "delivery-quality evidence blocked: " + " · ".join(errors[:3]),
                }) + "\n")
        except Exception:
            pass
        print(json.dumps({"decision": "block", "reason": (
            "[orbit] DELIVERY QUALITY GATE — QA role completion is not enough. Before CPO, write a "
            "fresh .orbit/qa/delivery-evidence.json bound to the exact commit and make the validator "
            "pass. Required: executable happy/alternate/negative/boundary/authorization/failure-"
            "recovery scenarios with artifacts; changed units plus direct/transitive dependents and "
            "related user flows with successful regression command output; and, for UI, baseline/"
            "actual/diff pixel comparisons at 375x812, 768x1024, and 1440x900, matching tokens, "
            "accessibility PASS, and zero console errors. Current blockers: " + " · ".join(errors[:4])
        )}))
        sys.exit(0)
    except SystemExit:
        raise
    except Exception as exc:
        # A configured quality gate must not disappear silently because its validator is broken.
        print(json.dumps({"decision": "block", "reason":
                          f"[orbit] DELIVERY QUALITY GATE ERROR — repair the validator before release: {exc}"}))
        sys.exit(0)


def _user_memory_vigilance(orbit, route_mt):
    """A deliverable cannot outrun the latest user correction or an overdue memory review."""
    if not (orbit / "loop.config.json").is_file():
        return                                               # legacy/minimal scaffold: contract absent
    try:
        cfg = json.loads((orbit / "loop.config.json").read_text())
        contract = cfg.get("user_memory") or {}
        if contract.get("enabled") is not True or contract.get("require_review_before_delivery") is not True:
            return
        helper = orbit / "checks" / "user_memory.py"
        spec = importlib.util.spec_from_file_location("orbit_user_memory_stop", helper)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        result = module.status(orbit, int(contract.get("max_requests_between_reviews", 5)),
                               require_latest=True)
        if result.get("passed"):
            return
        pending = ", ".join(result.get("pending_event_ids") or []) or "none"
        print(json.dumps({"decision": "block", "reason": (
            "[orbit] USER MEMORY GATE — delivery cannot proceed until Orbit reviews what the user "
            "most recently taught or corrected. Pending important events: " + pending + ". Requests "
            "since review: " + str(result.get("requests_since_review", 0)) + ". Read "
            ".orbit/skills/user-model.md and .orbit/skills/user-memory-architecture.md, then run "
            ".orbit/checks/user_memory.py review with promote/dismiss for each pending event, or "
            "checkpoint when there is no durable new signal. Never invent a preference. Re-run "
            "status --require-latest before QA/CPO."
        )}))
        sys.exit(0)
    except SystemExit:
        raise
    except Exception as exc:
        print(json.dumps({"decision": "block", "reason":
                          f"[orbit] USER MEMORY GATE ERROR — repair the checkpoint before delivery: {exc}"}))
        sys.exit(0)


def _capability_enforcement(orbit, route_mt, post_route, work):
    """Require real, completed stage owners on substantial work in a strict project."""
    try:
        cfg = json.loads((orbit / "loop.config.json").read_text())
        contract = cfg.get("capability_enforcement") or {}
        if contract.get("enabled") is not True or str(contract.get("mode", "")).lower() != "strict":
            return
        if len(work) < int(contract.get("work_event_threshold", _WORK_MIN)):
            return
        required = list(contract.get("required_for_substantial") or [])
        if _ui_project(orbit):
            required += list(contract.get("required_for_ui") or [])
        required = list(dict.fromkeys(str(role) for role in required if str(role).strip()))
        completed = {
            str(event.get("role")) for event in post_route
            if isinstance(event, dict) and event.get("status") == "done"
        }
        missing = [role for role in required if role not in completed]
        if not missing:
            return
        warned = orbit / ".capability-stop-warned"
        if warned.exists() and warned.read_text().strip() == repr(route_mt):
            return
        try:
            warned.write_text(repr(route_mt))
            with (orbit / "activity.jsonl").open("a") as f:
                f.write(json.dumps({
                    "schema": 2,
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "role": "orchestrator",
                    "phase": "evaluate",
                    "status": "blocked",
                    "msg": "mandatory capability stages missing: " + ", ".join(missing),
                }) + "\n")
        except Exception:
            pass
        print(json.dumps({"decision": "block", "reason": (
            "[orbit] STRICT CAPABILITY CONTRACT — this run cannot finish because mandatory stage "
            "owners were skipped: " + ", ".join(missing) + ". Dispatch each named role as an actual "
            "specialist and let it complete with evidence. A role mentioned in prose, silently used "
            "as a lens, or merely listed as available does NOT count. Discovery frames the bet; "
            "Business Analysis writes testable requirements; Market Research checks prior art; "
            "Planner sets the proof bar; Designer is mandatory for UI; Safety, Reviewer, and QA "
            "return verdicts; CPO writes its commit-bound verdict; Reporter closes with proof. "
            "Keep the visible board updated while these stages run."
        )}))
        sys.exit(0)
    except SystemExit:
        raise
    except Exception:
        return                                              # malformed local state never bricks Claude


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
    post_route = events[r + 1:]
    work = [e for e in post_route
            if isinstance(e, dict) and e.get("phase") not in ("route", "observability")]
    try:
        cfg = json.loads((orbit / "loop.config.json").read_text())
        work_min = int((cfg.get("capability_enforcement") or {}).get(
            "work_event_threshold", _WORK_MIN))
    except Exception:
        work_min = _WORK_MIN
    if len(work) < work_min:
        return                                              # not enough real work to warrant a board

    # Strict capability ownership is independent of presentation. Check it even when the board is
    # absent so the hook's single continuation demands the complete repair, not only a checklist.
    _capability_enforcement(orbit, route_mt, post_route, work)

    # (3) was the board updated after the route?
    if _mtime(orbit / "tasks.json") > route_mt or _mtime(orbit / "agents.json") > route_mt:
        _user_memory_vigilance(orbit, route_mt)              # latest user intent before release proof
        _delivery_quality_vigilance(orbit, route_mt)         # evidence before CPO, not role theater
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
