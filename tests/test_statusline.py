#!/usr/bin/env python3
"""
Tests the Claude Code status surface and its scaffold wiring: a compact run line and a state-driven,
one-way Claude-to-Codex QA parcel; malformed input never crashes.

Run: python3 tests/test_statusline.py   (exit 0 = pass)
"""
import json
import os
import subprocess
import sys
import tempfile
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SL = os.path.join(ROOT, "assets", "orbit-statusline.py")
SCAFFOLD = os.path.join(ROOT, "scripts", "scaffold.py")


def render(claude, run, tasks=None, agents=None):
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, ".orbit"))
        json.dump(run, open(os.path.join(d, ".orbit", "run.json"), "w"))
        if tasks is not None:
            json.dump(tasks, open(os.path.join(d, ".orbit", "tasks.json"), "w"))
        if agents is not None:
            json.dump(agents, open(os.path.join(d, ".orbit", "agents.json"), "w"))
        c = dict(claude); c["cwd"] = d
        r = subprocess.run([sys.executable, SL], input=json.dumps(c),
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip(), r.returncode


def main():
    fails = []
    scaffold_source = open(SCAFFOLD).read()
    if ('"scripts/orbit-statusline"' not in scaffold_source or
            "812c44c72001f4460b825a9bdb8bcc6a0059719e58f0ae74c863cca30d499cb3" not in scaffold_source):
        fails.append("existing 0.62 projects cannot safely migrate the shipped static handoff")
    full = {"context_window": {"used_percentage": 38, "total_input_tokens": 10000,
                               "current_usage": {"cache_read_input_tokens": 6100}},
            "cost": {"total_cost_usd": 0.42}, "model": {"display_name": "Opus"}}
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    run = {"phase": "build", "active_role": "builder", "active_task": "Implement checkout",
           "tasks_done": 5, "tasks_total": 9, "confidence": 76,
           "last_ts": now, "blocked_question": None}

    line, rc = render(full, run)
    for needle in ("BUILD", "Implement checkout", "builder", "5/9", "$0.42"):
        if needle not in line:
            fails.append(f"full status line missing '{needle}': {line!r}")
    for noise in ("ctx", "cache", "conf", "\n"):
        if noise in line:
            fails.append(f"stable status line contains noisy/multiline '{noise}': {line!r}")

    blocked_run = dict(run); blocked_run["blocked_question"] = "Choose path"
    bl, _ = render(full, blocked_run)
    if "⚠ INPUT" not in bl or "builder" not in bl.lower() or "Implement checkout" not in bl:
        fails.append(f"blocked run hid the board owner/task: {bl!r}")

    # A missing active_task must fall back to the first unfinished native-board item.
    fallback_run = dict(run); fallback_run["active_task"] = ""; fallback_run["active_role"] = "orchestrator"
    fb, _ = render(full, fallback_run, [
        {"id": "U8", "title": "QA evidence", "owner": "qa-engineer", "status": "done"},
        {"id": "U9", "title": "CPO verdict", "owner": "cpo", "status": "pending"},
    ])
    if "U9 CPO verdict" not in fb or "cpo" not in fb.lower():
        fails.append(f"status line did not recover the next unfinished board task: {fb!r}")

    stale_run = dict(run); stale_run["last_ts"] = "2020-01-01T00:00:00Z"
    stale, _ = render(full, stale_run)
    if "STALLED" not in stale:
        fails.append(f"status line hid a stalled LLM task: {stale!r}")

    # QA is a truthful handoff: actors stay fixed; the parcel moves once from real state timing.
    with tempfile.TemporaryDirectory() as d:
        orbit = os.path.join(d, ".orbit"); os.makedirs(orbit)
        subprocess.run(["git", "init", "-q"], cwd=d, check=True)
        subprocess.run(["git", "config", "user.email", "orbit@example.test"], cwd=d, check=True)
        subprocess.run(["git", "config", "user.name", "Orbit"], cwd=d, check=True)
        open(os.path.join(d, "x"), "w").write("x\n")
        subprocess.run(["git", "add", "x"], cwd=d, check=True)
        subprocess.run(["git", "commit", "-qm", "x"], cwd=d, check=True)
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=d, text=True).strip()
        json.dump(run, open(os.path.join(orbit, "run.json"), "w"))
        json.dump({"independent_qa": {"enabled": True, "provider": {"mode": "both", "adapters": {
                      "codex": {"model": "gpt-5.6-sol"}, "claude": {}}}}},
                  open(os.path.join(orbit, "loop.config.json"), "w"))
        control = os.path.join(d, ".git", "orbit-independent-qa"); os.makedirs(control)
        json.dump({"schema_version": 1, "status": "reviewing", "target_commit": head,
                   "providers": {"codex": {"status": "reviewing"}, "claude": {"status": "queued"}}},
                  open(os.path.join(control, "current.json"), "w"))
        payload = {**full, "cwd": d, "session_id": "session-qa-123",
                   "model": {"display_name": "Opus 4.8"}}
        qa_render = subprocess.run([sys.executable, SL], input=json.dumps(payload),
                                   env={**os.environ, "TERM_PROGRAM": "iTerm.app",
                                        "TERM_SESSION_ID": "term-window-42"},
                                   capture_output=True, text=True, timeout=10)
        rendered = qa_render.stdout.strip()
        lines = rendered.splitlines()
        if len(lines) != 2 or "Claude" not in lines[1] or "Codex QA" not in lines[1]:
            fails.append(f"QA must render one explicit Claude/Codex handoff row: {rendered!r}")
        if "📦" not in rendered or "REVIEW" not in rendered or "5.6 Sol" not in rendered:
            fails.append(f"reviewing must show a Claude-to-Codex code/content review: {rendered!r}")
        def at_age(age):
            stamp = time.time() - age
            os.utime(os.path.join(control, "current.json"), (stamp, stamp))
            return subprocess.run([sys.executable, SL], input=json.dumps(payload),
                                  env={**os.environ, "TERM_PROGRAM": "iTerm.app",
                                       "TERM_SESSION_ID": "term-window-42"},
                                  capture_output=True, text=True, timeout=10).stdout.strip()
        review_frames = [at_age(age).splitlines()[-1] for age in (.1, 2.2, 8)]
        parcel_positions = [frame.find("📦") for frame in review_frames]
        if not parcel_positions[0] < parcel_positions[1] < parcel_positions[2]:
            fails.append(f"review parcel did not move once toward Codex: {review_frames}")
        if any(frame.find("Claude") != review_frames[0].find("Claude") or
               frame.find("Codex QA") != review_frames[0].find("Codex QA") for frame in review_frames):
            fails.append(f"actors moved while parcel animated: {review_frames}")
        states = {
            "changes_required": ("FEEDBACK", "←"),
            "pass": ("PASS",),
            "blocked": ("BLOCKED",),
        }
        for state, expected in states.items():
            json.dump({"schema_version": 1, "status": state, "target_commit": head,
                       "providers": {"codex": {"status": state}, "claude": {"status": "queued"}}},
                      open(os.path.join(control, "current.json"), "w"))
            transition = subprocess.run([sys.executable, SL], input=json.dumps(payload),
                                        env={**os.environ, "TERM_PROGRAM": "iTerm.app",
                                             "TERM_SESSION_ID": "term-window-42"},
                                        capture_output=True, text=True, timeout=10).stdout.strip()
            handoff = transition.splitlines()[-1]
            if not all(mark in handoff for mark in expected):
                fails.append(f"{state} handoff is unclear: {handoff!r}")
            if handoff.find("Claude") >= handoff.find("Codex QA"):
                fails.append(f"{state} moved Claude/Codex positions: {handoff!r}")
            if "5.6 Sol" not in handoff:
                fails.append(f"{state} hid Orbit's selected OpenAI model: {handoff!r}")
        json.dump({"schema_version": 1, "status": "changes_required", "target_commit": head,
                   "providers": {"codex": {"status": "changes_required"}}},
                  open(os.path.join(control, "current.json"), "w"))
        feedback_frames = [at_age(age).splitlines()[-1] for age in (.1, 2.2, 8)]
        feedback_positions = [frame.find("📦") for frame in feedback_frames]
        if not feedback_positions[0] > feedback_positions[1] > feedback_positions[2]:
            fails.append(f"feedback parcel did not return once to Claude: {feedback_frames}")
        sessions = json.load(open(os.path.join(orbit, "sessions.json")))
        if sessions.get("session-qa-123", {}).get("model") != "Opus 4.8":
            fails.append(f"statusline did not record session/model identity: {sessions}")
        identity = sessions.get("session-qa-123", {})
        if (identity.get("terminal_program"), identity.get("terminal_session"),
                identity.get("terminal_bundle")) != ("iTerm.app", "term-window-42", "com.googlecode.iterm2"):
            fails.append(f"statusline did not record actionable terminal identity: {identity}")

    # missing Claude fields → those segments drop, orbit segments still render, no crash
    partial, rc = render({}, run)
    if rc != 0 or "BUILD" not in partial or "ctx" in partial or "$" in partial:
        fails.append(f"missing-claude-fields case wrong: rc={rc} line={partial!r}")

    # empty everything → empty line, exit 0 (never crashes the status bar)
    empty, rc = render({}, {})
    if rc != 0:
        fails.append(f"empty case should exit 0, got {rc}")

    # garbage stdin → exit 0, no traceback
    r = subprocess.run([sys.executable, SL], input="not json{", capture_output=True, text=True, timeout=10)
    if r.returncode != 0 or "Traceback" in r.stderr:
        fails.append(f"garbage stdin should fail safe: rc={r.returncode} err={r.stderr[:120]!r}")

    # --- scaffold wiring: adds statusLine when absent, never overwrites an existing one --------
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["git", "init", "-q", d], check=True)
        subprocess.run([sys.executable, SCAFFOLD, "--surfaces", "api", "--install-hooks",
                        "--target", d], capture_output=True, check=True)
        st = json.load(open(os.path.join(d, ".claude", "settings.json")))
        if "orbit-statusline" not in json.dumps(st.get("statusLine", {})):
            fails.append("scaffold did not wire the Orbit status line on a fresh repo")
        if not os.path.exists(os.path.join(d, "scripts", "orbit-statusline")):
            fails.append("scaffold did not place scripts/orbit-statusline")

    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["git", "init", "-q", d], check=True)
        os.makedirs(os.path.join(d, ".claude"))
        mine = {"statusLine": {"type": "command", "command": "my-own-statusline"}}
        json.dump(mine, open(os.path.join(d, ".claude", "settings.json"), "w"))
        subprocess.run([sys.executable, SCAFFOLD, "--surfaces", "api", "--install-hooks",
                        "--target", d], capture_output=True, check=True)
        st = json.load(open(os.path.join(d, ".claude", "settings.json")))
        if st.get("statusLine", {}).get("command") != "my-own-statusline":
            fails.append("scaffold OVERWROTE the user's existing status line (must not)")

    if fails:
        print("FAIL: statusline")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("PASS: statusline (persistent task board · stall visibility · truthful QA parcel · fail-safe)")


if __name__ == "__main__":
    main()
