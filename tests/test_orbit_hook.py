#!/usr/bin/env python3
"""
Tests bin/orbit-hook — the telemetry collector wired to Claude Code hook events. Verifies it maps
each event to a sanitized activity event, mirrors the native TaskCreate/TaskUpdate checklist into
tasks.json, filters noisy PostToolUse tools, redacts control chars, and FAILS OPEN (unknown event /
un-scaffolded repo / malformed input → no-op, no crash, never writes outside a scaffolded .orbit/).

Run: python3 tests/test_orbit_hook.py   (exit 0 = pass)
"""
import importlib.util
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


def _scaffold_hook_cmd():
    spec = importlib.util.spec_from_file_location("scaffold_oh", os.path.join(ROOT, "scripts", "scaffold.py"))
    m = importlib.util.module_from_spec(spec)
    sys.modules["scaffold_oh"] = m
    spec.loader.exec_module(m)
    return m.ORBIT_HOOK_CMD


def _install_resolution():
    """The wired ORBIT_HOOK_CMD must resolve orbit-hook for BOTH the skills-dir clone AND the
    marketplace plugin cache (~/.claude/plugins/cache/<mkt>/orbit/<ver>/bin), and no-op (exit 0)
    when Orbit isn't installed anywhere."""
    fails = []
    cmd = _scaffold_hook_cmd()

    def place(binroot):
        os.makedirs(os.path.join(binroot, "bin"))
        os.makedirs(os.path.join(binroot, "assets"))
        for src, dst in ((HOOK, "bin/orbit-hook"), (os.path.join(ROOT, "assets", "activity.py"), "assets/activity.py")):
            with open(src, "rb") as a, open(os.path.join(binroot, dst), "wb") as b:
                b.write(a.read())

    def run_cmd(fake_home, repo):
        env = {**os.environ, "HOME": fake_home, "CLAUDE_CONFIG_DIR": os.path.join(fake_home, ".claude")}
        env.pop("CLAUDE_PLUGIN_ROOT", None)
        payload = json.dumps({"hook_event_name": "SubagentStart", "agent_type": "builder", "cwd": repo})
        return subprocess.run(cmd, shell=True, input=payload, capture_output=True, text=True, env=env, timeout=10)

    # marketplace plugin-cache layout ONLY (no skills-dir)
    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as repo:
        place(os.path.join(home, ".claude", "plugins", "cache", "orbit", "orbit", "0.26.2"))
        os.makedirs(os.path.join(repo, ".orbit"))
        r = run_cmd(home, repo)
        if r.returncode != 0 or not os.path.exists(os.path.join(repo, ".orbit", "activity.jsonl")):
            fails.append(f"resolver missed the marketplace plugin-cache install: rc={r.returncode} err={r.stderr[:150]!r}")

    # skills-dir clone layout
    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as repo:
        place(os.path.join(home, ".claude", "skills", "orbit"))
        os.makedirs(os.path.join(repo, ".orbit"))
        r = run_cmd(home, repo)
        if not os.path.exists(os.path.join(repo, ".orbit", "activity.jsonl")):
            fails.append("resolver missed the skills-dir clone install")

    # neither → clean no-op (exit 0, no write, no error)
    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as repo:
        os.makedirs(os.path.join(home, ".claude"))
        os.makedirs(os.path.join(repo, ".orbit"))
        r = run_cmd(home, repo)
        if r.returncode != 0:
            fails.append(f"resolver should exit 0 when Orbit isn't installed, got {r.returncode}")
        if os.path.exists(os.path.join(repo, ".orbit", "activity.jsonl")):
            fails.append("resolver wrote telemetry with no Orbit install present")
    return fails


def main():
    fails = []
    fails += _install_resolution()
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
        fire({"hook_event_name": "PermissionRequest", "tool_name": "Bash",
              "tool_input": {"command": "npm test"}, "session_id": "session-abc123", "cwd": d}, d)
        fire({"hook_event_name": "Notification",
              "message": "Claude is \x1b[31mwaiting\x1b[0m for your input",
              "title": "Input needed", "notification_type": "elicitation_dialog",
              "session_id": "session-abc123", "cwd": d}, d)

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
        attention = json.loads(open(os.path.join(d, ".orbit", "attention.json")).read())
        if (attention.get("session_id") != "session-abc123" or
                attention.get("message") != "Allow Bash: npm test" or
                attention.get("question_available") is not True):
            fails.append(f"exact permission request must survive its generic companion notification: {attention}")

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
