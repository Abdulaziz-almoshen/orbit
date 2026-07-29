#!/usr/bin/env python3
"""Strict role contract: substantial work cannot stop after silently skipping Orbit capabilities."""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "assets/checks/orbit-stop-check.py"
REQUIRED = [
    "product-discovery", "business-analyst", "market-researcher", "planner",
    "safety-gate", "reviewer", "qa-engineer", "cpo", "reporter",
]


def fixture(root: Path, completed=(), ui=False):
    orbit = root / ".orbit"
    orbit.mkdir()
    (root / ".claude/agents").mkdir(parents=True)
    if ui:
        (root / ".claude/agents/designer.md").write_text("designer")
    (orbit / "loop.config.json").write_text(json.dumps({
        "capability_enforcement": {
            "enabled": True, "mode": "strict", "work_event_threshold": 3,
            "required_for_substantial": REQUIRED, "required_for_ui": ["designer"],
        },
        "cpo_acceptance": {"enabled": False},
    }))
    events = [{"phase": "route", "status": "start", "role": "dispatcher"}]
    events += [{"phase": "build", "status": "info", "role": "builder"} for _ in range(3)]
    events += [{"phase": "act", "status": "done", "role": role} for role in completed]
    (orbit / "activity.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
    now = time.time()
    (orbit / ".last-task-route").write_text("route")
    os.utime(orbit / ".last-task-route", (now, now))
    (orbit / "tasks.json").write_text("[]")
    os.utime(orbit / "tasks.json", (now + 2, now + 2))


def run(root: Path):
    p = subprocess.run([sys.executable, str(HOOK)], input=json.dumps({"cwd": str(root)}),
                       text=True, capture_output=True, timeout=10)
    return json.loads(p.stdout) if p.stdout.strip() else {}


def main():
    failures = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        fixture(root, completed=["reviewer"])
        result = run(root)
        if result.get("decision") != "block":
            failures.append("missing mandatory roles did not block Stop")
        reason = result.get("reason", "")
        for role in ("business-analyst", "qa-engineer", "cpo"):
            if role not in reason:
                failures.append(f"block reason did not name {role}")

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        fixture(root, completed=REQUIRED)
        if run(root).get("decision"):
            failures.append("complete non-UI role contract did not release Stop")

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        fixture(root, completed=REQUIRED, ui=True)
        result = run(root)
        if result.get("decision") != "block" or "designer" not in result.get("reason", ""):
            failures.append("UI project did not require Designer")

    if failures:
        print("FAIL: capability-enforcement")
        for failure in failures:
            print("  -", failure)
        return 1
    print("PASS: capability-enforcement (real role completions · BA · QA/CPO · UI Designer)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
