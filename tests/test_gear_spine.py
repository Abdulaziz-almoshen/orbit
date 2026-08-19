#!/usr/bin/env python3
"""Regression tests for the gear-scaled capability spine in the Stop hook.

Before v0.60.0 the mandatory spine was gear-independent: a T1 one-file change was held to the same
eleven-role contract as a T3 initiative. These tests pin the new behavior AND the safety property
that makes it safe — an undeclared gear still gets the full spine, so skipping the Gear Card is
never the cheap path.
"""
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "assets" / "checks" / "orbit-stop-check.py"

T1_ROLES = ["planner", "reviewer", "qa-engineer", "reporter"]
T3_ROLES = ["product-discovery", "business-analyst", "market-researcher", "planner",
            "safety-gate", "reviewer", "qa-engineer", "cpo", "reporter"]


def _events(gear=None, done_roles=()):
    """A minimal post-route activity log: a route, a gear card, work, then completions."""
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    out = [{"schema": 2, "ts": ts, "role": "orchestrator", "phase": "route", "status": "start"}]
    if gear:
        out.append({"schema": 2, "ts": ts, "role": "orchestrator", "phase": "gear",
                    "status": "done", "gear": gear, "msg": f"Gear: {gear} declared"})
    for i in range(4):                                   # clear the work_event_threshold
        out.append({"schema": 2, "ts": ts, "role": "builder", "phase": "build",
                    "status": "done", "msg": f"edit {i}"})
    for role in done_roles:
        out.append({"schema": 2, "ts": ts, "role": role, "phase": "evaluate", "status": "done"})
    return out


def _project(td: Path, gear=None, done_roles=()):
    orbit = td / ".orbit"
    orbit.mkdir(parents=True)
    # Isolate the capability contract: the memory / delivery / CPO gates are exercised by their own
    # tests and would otherwise fire first and mask what this file is pinning.
    cfg = json.loads((ROOT / "assets/loop.config.json").read_text())
    for block in ("user_memory", "delivery_quality", "cpo_acceptance"):
        cfg.setdefault(block, {})["enabled"] = False
    (orbit / "loop.config.json").write_text(json.dumps(cfg, indent=2))
    with (orbit / "activity.jsonl").open("w") as f:
        for e in _events(gear, done_roles):
            f.write(json.dumps(e) + "\n")
    (orbit / ".last-task-route").write_text("x")
    # A visible board, so only the capability contract can be the thing that blocks.
    (orbit / "tasks.json").write_text("[]")
    time.sleep(0.01)
    (orbit / "tasks.json").write_text("[]")
    return orbit


def _run(td: Path):
    r = subprocess.run([sys.executable, str(HOOK)], text=True, capture_output=True,
                       input=json.dumps({"cwd": str(td)}))
    if not r.stdout.strip():
        return None
    try:
        return json.loads(r.stdout)
    except Exception:
        return None


def main() -> int:
    failures = []

    # --- T1 declared + the four T1 owners done → the run may finish -----------------------
    with tempfile.TemporaryDirectory() as td:
        _project(Path(td), gear="T1", done_roles=T1_ROLES)
        out = _run(Path(td))
        if out and out.get("decision") == "block":
            failures.append(f"T1 with its own spine complete must not block: {out.get('reason','')[:160]}")

    # --- the same run WITHOUT a declared gear falls back to the full spine ----------------
    with tempfile.TemporaryDirectory() as td:
        _project(Path(td), gear=None, done_roles=T1_ROLES)
        out = _run(Path(td))
        if not (out and out.get("decision") == "block"):
            failures.append("an undeclared gear must fall back to the full spine")
        elif "no Gear Card" not in out.get("reason", ""):
            failures.append("the block should tell the user to declare a gear")

    # --- T3 declared but only the T1 owners ran → blocked --------------------------------
    with tempfile.TemporaryDirectory() as td:
        _project(Path(td), gear="T3", done_roles=T1_ROLES)
        out = _run(Path(td))
        if not (out and out.get("decision") == "block"):
            failures.append("T3 with only the T1 spine must block")
        elif "product-discovery" not in out.get("reason", ""):
            failures.append("the T3 block should name the missing discovery stages")

    # --- T3 declared with the full spine → allowed ---------------------------------------
    with tempfile.TemporaryDirectory() as td:
        _project(Path(td), gear="T3", done_roles=T3_ROLES)
        out = _run(Path(td))
        if out and out.get("decision") == "block" and "CAPABILITY" in out.get("reason", ""):
            failures.append(f"T3 with a complete spine must not block on capability: "
                            f"{out.get('reason','')[:160]}")

    # --- mid-run escalation raises the bar: the LAST gear event wins ---------------------
    with tempfile.TemporaryDirectory() as td:
        orbit = _project(Path(td), gear="T1", done_roles=T1_ROLES)
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with (orbit / "activity.jsonl").open("a") as f:
            f.write(json.dumps({"schema": 2, "ts": ts, "role": "orchestrator", "phase": "gear",
                                "status": "done", "gear": "T3",
                                "msg": "escalating to T3 — landmine found"}) + "\n")
        out = _run(Path(td))
        if not (out and out.get("decision") == "block"):
            failures.append("escalating T1 → T3 mid-run must raise the mandatory set")

    # --- T0 declared → nothing mandatory --------------------------------------------------
    with tempfile.TemporaryDirectory() as td:
        _project(Path(td), gear="T0", done_roles=[])
        out = _run(Path(td))
        if out and out.get("decision") == "block" and "CAPABILITY" in out.get("reason", ""):
            failures.append("T0 must have no mandatory spine")

    if failures:
        print("FAIL: gear-scaled spine")
        for f in failures:
            print("  -", f)
        return 1
    print("PASS: gear-scaled spine (T1/T3 sets, undeclared→full, escalation raises, T0 free)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
