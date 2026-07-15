#!/usr/bin/env python3
"""
Tests assets/orbit-statusline.py (the one-line Claude Code status line) and its scaffold wiring:
fuses Claude status JSON + .orbit/run.json, drops missing segments, labels cache reuse honestly,
surfaces a blocked run, and NEVER crashes; the scaffolder wires it only if the user has none.

Run: python3 tests/test_statusline.py   (exit 0 = pass)
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SL = os.path.join(ROOT, "assets", "orbit-statusline.py")
SCAFFOLD = os.path.join(ROOT, "scripts", "scaffold.py")


def render(claude, run):
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, ".orbit"))
        json.dump(run, open(os.path.join(d, ".orbit", "run.json"), "w"))
        c = dict(claude); c["cwd"] = d
        r = subprocess.run([sys.executable, SL], input=json.dumps(c),
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip(), r.returncode


def main():
    fails = []
    scaffold_source = open(SCAFFOLD).read()
    if ('"scripts/orbit-statusline"' not in scaffold_source or
            "7f4b512f83674863fef70d465ee6a483d78191e21382ef6f34a5c5236b914c49" not in scaffold_source):
        fails.append("existing <=0.44 projects cannot safely migrate the shipped one-line reporter")
    full = {"context_window": {"used_percentage": 38, "total_input_tokens": 10000,
                               "current_usage": {"cache_read_input_tokens": 6100}},
            "cost": {"total_cost_usd": 0.42}, "model": {"display_name": "Opus"}}
    run = {"phase": "build", "active_role": "builder", "tasks_done": 5, "tasks_total": 9,
           "confidence": 76, "last_ts": "2020-01-01T00:00:00Z", "blocked_question": None}

    line, rc = render(full, run)
    for needle in ("build", "builder", "5/9", "ctx 38%", "$0.42", "cache 61%", "conf 76%"):
        if needle not in line:
            fails.append(f"full status line missing '{needle}': {line!r}")

    blocked_run = dict(run); blocked_run["blocked_question"] = "Choose path"
    bl, _ = render(full, blocked_run)
    if "needs input" not in bl:
        fails.append(f"blocked run should show 'needs input': {bl!r}")

    # Multi-line QA scene belongs directly below Claude Code's activity panel and names real providers.
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
        json.dump({"independent_qa": {"enabled": True, "provider": {"mode": "both"}}},
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
        for needle in ("Builder", "Codex: reviewing", "Claude QA: queued"):
            if needle not in qa_render.stdout:
                fails.append(f"terminal QA scene missing '{needle}': {qa_render.stdout!r}")
        if "📦" not in qa_render.stdout and "💬" not in qa_render.stdout:
            fails.append(f"terminal QA scene missing animated handoff/comment marker: {qa_render.stdout!r}")
        sessions = json.load(open(os.path.join(orbit, "sessions.json")))
        if sessions.get("session-qa-123", {}).get("model") != "Opus 4.8":
            fails.append(f"statusline did not record session/model identity: {sessions}")
        identity = sessions.get("session-qa-123", {})
        if (identity.get("terminal_program"), identity.get("terminal_session"),
                identity.get("terminal_bundle")) != ("iTerm.app", "term-window-42", "com.googlecode.iterm2"):
            fails.append(f"statusline did not record actionable terminal identity: {identity}")

    # missing Claude fields → those segments drop, orbit segments still render, no crash
    partial, rc = render({}, run)
    if rc != 0 or "build" not in partial or "ctx" in partial or "$" in partial:
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
    print("PASS: statusline (fuses claude+run, honest cache label, blocked surface, fail-safe, non-overwrite wiring)")


if __name__ == "__main__":
    main()
