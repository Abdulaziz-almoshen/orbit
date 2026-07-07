#!/usr/bin/env python3
"""
Single-writer lock — scaffold wiring + surface integration (v0.30.0). Verifies /orbit wires the lock
hook exactly once (two matchers), provisions the project files, that orbit-status shows the owner, and
that the doctor reports lock-hook drift when it isn't wired.

Run: python3 tests/test_writer_lock_scaffold.py   (exit 0 = pass)
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAFFOLD = ROOT / "scripts" / "scaffold.py"
fails = []


def ck(cond, msg):
    if not cond:
        fails.append(msg)


def _scaffold(t, *extra):
    subprocess.run([sys.executable, str(SCAFFOLD), "--target", str(t), "--surfaces", "api", *extra],
                   capture_output=True, text=True)


def _lock_entries(settings):
    pre = json.loads(settings.read_text()).get("hooks", {}).get("PreToolUse", [])
    return [e for e in pre if "orbit-lock-hook" in json.dumps(e)]


def test_files_and_wiring():
    with tempfile.TemporaryDirectory() as d:
        t = Path(d)
        _scaffold(t, "--install-hooks")
        # project files
        ck((t / ".orbit/locks/.gitkeep").exists(), "scaffold creates .orbit/locks/.gitkeep")
        ck(os.access(t / "scripts/orbit-lock", os.X_OK), "scaffold provisions executable scripts/orbit-lock")
        # wiring: exactly two matchers (Edit|Write|MultiEdit + Bash), wired from the TRUSTED install
        entries = _lock_entries(t / ".claude/settings.json")
        matchers = sorted(e.get("matcher", "") for e in entries)
        ck(matchers == ["Bash", "Edit|Write|MultiEdit"], f"lock hook matchers = {matchers}")
        ck(all("orbit-lock-hook" in json.dumps(e) and "$CLAUDE_PROJECT_DIR/.orbit" not in json.dumps(e)
                for e in entries), "lock hook is resolved from the trusted install, not the project copy")
        # idempotent: a second --install-hooks re-run does NOT double-add
        _scaffold(t, "--install-hooks")
        ck(len(_lock_entries(t / ".claude/settings.json")) == 2, "re-run must not double-wire the lock hook")


def test_orbit_status_shows_owner():
    with tempfile.TemporaryDirectory() as d:
        t = Path(d)
        _scaffold(t)
        subprocess.run([sys.executable, str(ROOT / "bin" / "orbit-lock"), "acquire", "--target", str(t),
                        "--owner", "interactive", "--task", "F1 report"],
                       capture_output=True, text=True, env={**os.environ, "TERM_SESSION_ID": "OWNER"})
        r = subprocess.run([sys.executable, str(t / "scripts" / "orbit-status")],
                           capture_output=True, text=True, cwd=str(t), env={**os.environ, "ORBIT_DIR": ".orbit"})
        ck("Writer lock" in r.stdout and "interactive" in r.stdout,
           f"orbit-status must show the writer-lock owner; got:\n{r.stdout[:400]}")


def test_doctor_reports_lock_drift():
    with tempfile.TemporaryDirectory() as d:
        t = Path(d)
        _scaffold(t)  # NO --install-hooks → the lock hook is unwired → drift should mention it
        r = subprocess.run([sys.executable, str(SCAFFOLD), "--check-drift", "--target", str(t)],
                           capture_output=True, text=True)
        ck("writer lock" in r.stdout, f"doctor should list unwired 'writer lock' hook drift; got:\n{r.stdout[:400]}")


def main():
    for fn in (test_files_and_wiring, test_orbit_status_shows_owner, test_doctor_reports_lock_drift):
        try:
            fn()
        except Exception as e:
            fails.append(f"[{fn.__name__}] raised {type(e).__name__}: {e}")
    if fails:
        print(f"FAIL: writer-lock-scaffold {len(fails)} case(s):")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("PASS: writer-lock-scaffold (files provisioned · hook wired once, two matchers, trusted · "
          "orbit-status shows owner · doctor reports lock drift)")


if __name__ == "__main__":
    main()
