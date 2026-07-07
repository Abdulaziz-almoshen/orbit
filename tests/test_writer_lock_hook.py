#!/usr/bin/env python3
"""
Single-writer lock — the PreToolUse enforcement BINARY, end-to-end (v0.30.0). Pipes real hook payloads
through bin/orbit-lock-hook and asserts the allow/deny envelope, the safety valves (fail-open, kill
switch, non-orbit repo), and that a write auto-acquires the lock file.

Run: python3 tests/test_writer_lock_hook.py   (exit 0 = pass)
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "bin" / "orbit-lock-hook"
fails = []


def _mk(d):
    (Path(d) / ".orbit" / "locks").mkdir(parents=True, exist_ok=True)
    return Path(d)


def run_hook(payload, env=None):
    """→ ('allow', '') if the hook emitted nothing, else ('deny', reason)."""
    r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload) if isinstance(payload, dict) else payload,
                       capture_output=True, text=True, env={**os.environ, **(env or {})})
    out = r.stdout.strip()
    if not out:
        return ("allow", "")
    try:
        d = json.loads(out)["hookSpecificOutput"]
        return (d["permissionDecision"], d.get("permissionDecisionReason", ""))
    except Exception:
        return ("MALFORMED_OUTPUT", out)


def pay(sid, cwd, tool, ti):
    return {"session_id": sid, "cwd": str(cwd), "tool_name": tool, "tool_input": ti,
            "hook_event_name": "PreToolUse"}


def ck(cond, msg):
    if not cond:
        fails.append(msg)


def test_enforcement():
    with tempfile.TemporaryDirectory() as d:
        t = _mk(d)
        # 1) no lock + A Edit → allow AND the lock file is now owned by A
        dec, _ = run_hook(pay("A", t, "Edit", {"file_path": str(t / "foo.py")}))
        ck(dec == "allow", f"no-lock A Edit → {dec}")
        lock = json.loads((t / ".orbit/locks/active-writer.json").read_text())
        ck(lock.get("owner_id") == "A", f"auto-acquire should own the lock as A, got {lock.get('owner_id')}")
        # 2) A again → allow (heartbeat)
        ck(run_hook(pay("A", t, "Edit", {"file_path": "x"}))[0] == "allow", "A second write → allow")
        # 3) foreign B Edit → deny
        dec, reason = run_hook(pay("B", t, "Edit", {"file_path": "x"}))
        ck(dec == "deny" and "writer-lock" in reason, f"foreign B Edit → {dec} {reason!r}")
        # 4) foreign B git status → allow; git commit → deny
        ck(run_hook(pay("B", t, "Bash", {"command": "git status"}))[0] == "allow", "B git status → allow")
        ck(run_hook(pay("B", t, "Bash", {"command": "git commit -m x"}))[0] == "deny", "B git commit → deny")
        # 5) foreign B Write STATE.md → deny, reason names STATE.md
        dec, reason = run_hook(pay("B", t, "Write", {"file_path": str(t / ".orbit/STATE.md")}))
        ck(dec == "deny" and "STATE.md" in reason, f"B STATE.md → {dec} {reason!r}")


def test_safety_valves():
    with tempfile.TemporaryDirectory() as d:
        t = _mk(d)
        # foreign lock in place
        subprocess.run([sys.executable, str(ROOT / "bin" / "orbit-lock"), "acquire", "--target", str(t)],
                       capture_output=True, text=True, env={**os.environ, "TERM_SESSION_ID": "OWNER"})
        # kill switch → allow even for a foreign writer
        ck(run_hook(pay("B", t, "Edit", {"file_path": "x"}), env={"ORBIT_LOCK_DISABLE": "1"})[0] == "allow",
           "ORBIT_LOCK_DISABLE=1 must allow")
        # garbage payload → fail open
        ck(run_hook("not json at all")[0] == "allow", "garbage payload → fail open (allow)")
        # payload missing tool_name → allow
        ck(run_hook({"cwd": str(t), "session_id": "B"})[0] == "allow", "no tool_name → allow")
        # non-orbit cwd → allow (not ours to police)
        with tempfile.TemporaryDirectory() as d2:
            ck(run_hook(pay("B", d2, "Edit", {"file_path": "x"}))[0] == "allow", "non-orbit repo → allow")
        # malformed lock: write denied, read allowed
        (t / ".orbit/locks/active-writer.json").write_text("{ broken")
        ck(run_hook(pay("B", t, "Edit", {"file_path": "x"}))[0] == "deny", "malformed lock + write → deny")
        ck(run_hook(pay("B", t, "Bash", {"command": "cat x"}))[0] == "allow", "malformed lock + read → allow")


def test_no_double_writer_race():
    """Adversarial: many DISTINCT sessions auto-acquire at once. The O_EXCL close must leave EXACTLY one
    owner in the lock file (no two sessions both become the writer)."""
    import threading
    with tempfile.TemporaryDirectory() as d:
        t = _mk(d)
        def hit(i):
            run_hook(pay(f"S{i}", t, "Edit", {"file_path": "f"}))
        threads = [threading.Thread(target=hit, args=(i,)) for i in range(12)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        owners = set()
        lock = json.loads((t / ".orbit/locks/active-writer.json").read_text())
        owners.add(lock.get("owner_id"))
        ck(len(owners) == 1 and lock.get("owner_id"), f"exactly one writer must win the race; lock={lock.get('owner_id')}")


def main():
    if not os.access(HOOK, os.X_OK):
        print("FAIL: bin/orbit-lock-hook missing or not executable")
        sys.exit(1)
    for fn in (test_enforcement, test_safety_valves, test_no_double_writer_race):
        try:
            fn()
        except Exception as e:
            fails.append(f"[{fn.__name__}] raised {type(e).__name__}: {e}")
    if fails:
        print(f"FAIL: writer-lock-hook {len(fails)} case(s):")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("PASS: writer-lock-hook (allow/deny end-to-end · auto-acquire · kill switch · fail-open · "
          "non-orbit · malformed closed-for-writes-open-for-reads)")


if __name__ == "__main__":
    main()
