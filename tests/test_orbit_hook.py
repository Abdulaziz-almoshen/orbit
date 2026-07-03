#!/usr/bin/env python3
"""
Tests bin/orbit-hook — the telemetry collector wired to Claude Code hook events. Verifies it maps
each event to a sanitized activity event, mirrors the native TaskCreate/TaskUpdate checklist into
tasks.json, filters noisy PostToolUse tools, redacts control chars, and FAILS OPEN (unknown event /
un-scaffolded repo / malformed input → no-op, no crash, never writes outside a scaffolded .orbit/).

Run: python3 tests/test_orbit_hook.py   (exit 0 = pass)
"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
HOOK = os.path.join(ROOT, "bin", "orbit-hook")


def fire(payload, cwd):
    return subprocess.run([sys.executable, HOOK],
                          input=payload if isinstance(payload, str) else json.dumps(payload),
                          capture_output=True, text=True, cwd=cwd, timeout=10)


def main():
    fails = []
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, ".orbit"))
        act = os.path.join(d, ".orbit", "activity.jsonl")
        tasks_p = os.path.join(d, ".orbit", "tasks.json")

        fire({"hook_event_name": "SubagentStart", "agent_type": "builder", "cwd": d}, d)
        fire({"hook_event_name": "SubagentStop", "agent_type": "builder", "cwd": d}, d)
        fire({"hook_event_name": "TaskCreated", "task_id": "T1",
              "task": {"content": "build UI"}, "cwd": d}, d)
        fire({"hook_event_name": "TaskCompleted", "task_id": "T1", "cwd": d}, d)
        fire({"hook_event_name": "PostToolUse", "tool_name": "Edit",
              "tool_input": {"file_path": "src/A.tsx"}, "cwd": d}, d)
        fire({"hook_event_name": "PostToolUse", "tool_name": "Read",
              "tool_input": {"file_path": "README.md"}, "cwd": d}, d)   # must be skipped
        fire({"hook_event_name": "PostToolUseFailure", "tool_name": "Bash", "cwd": d}, d)
        fire({"hook_event_name": "Notification",
              "message": "Claude is \x1b[31mwaiting\x1b[0m for your input", "cwd": d}, d)

        events = [json.loads(l) for l in open(act).read().splitlines()]
        roles_status = [(e["role"], e["status"], e["msg"]) for e in events]

        if not any(r == "builder" and s == "start" for r, s, _ in roles_status):
            fails.append("SubagentStart not recorded")
        if not any(r == "builder" and s == "done" for r, s, _ in roles_status):
            fails.append("SubagentStop not recorded")
        if not any("A.tsx" in m for _, _, m in roles_status):
            fails.append("PostToolUse(Edit) not recorded with the file path")
        if any("README.md" in m for _, _, m in roles_status):
            fails.append("PostToolUse(Read) should be filtered out (too noisy)")
        if not any(s == "failed" for _, s, _ in roles_status):
            fails.append("PostToolUseFailure not recorded as failed")
        # redaction: the notification's ANSI escapes must be gone
        notif = [m for r, s, m in roles_status if r == "human"]
        if not notif or "\x1b" in notif[0]:
            fails.append(f"Notification not recorded/redacted: {notif}")
        if notif and "blocked" not in [s for r, s, _ in roles_status if r == "human"]:
            fails.append("a 'waiting for input' notification should be status=blocked")

        # native checklist mirrored into tasks.json
        tasks = json.loads(open(tasks_p).read())
        t1 = next((t for t in tasks if t["id"] == "T1"), None)
        if not t1 or t1["status"] != "done":
            fails.append(f"TaskCreated/Completed did not mirror into tasks.json: {tasks}")

        # run.json reflects it (blocked question set by the notification)
        run = json.loads(open(os.path.join(d, ".orbit", "run.json")).read())
        if not run.get("blocked_question"):
            fails.append("run.json blocked_question not set by the notification")

    # --- fail-open: unknown event, un-scaffolded repo, garbage input ------------------
    with tempfile.TemporaryDirectory() as d:
        r = fire({"hook_event_name": "Stop", "cwd": d}, d)          # no .orbit/ → no-op
        if r.returncode != 0:
            fails.append(f"un-scaffolded repo should exit 0: {r.returncode}")
        if os.path.exists(os.path.join(d, ".orbit")):
            fails.append("orbit-hook created .orbit/ in an un-scaffolded repo (must not)")
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, ".orbit"))
        for bad in ("not json", "", "[]", json.dumps({"hook_event_name": "MadeUpEvent", "cwd": d})):
            r = fire(bad, d)
            if r.returncode != 0:
                fails.append(f"malformed/unknown input should fail open: {bad!r} → {r.returncode}")
        # nothing should have been written for those
        if os.path.exists(os.path.join(d, ".orbit", "activity.jsonl")):
            fails.append("orbit-hook wrote an event for malformed/unknown input")

    if fails:
        print("FAIL: orbit-hook")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("PASS: orbit-hook (event mapping + native-task mirror + noise filter + redaction + fail-open)")


if __name__ == "__main__":
    main()
