#!/usr/bin/env python3
"""
Single-writer lock — core library + CLI behaviour (v0.30.0). Many readers, one writer.
Covers the decision table (orbit_lock_lib.evaluate), the write-intent classifier, staleness, identity
resolution, and the orbit-lock CLI lifecycle. The hook binary and scaffold wiring have their own files.

Run: python3 tests/test_writer_lock.py   (exit 0 = pass)
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
fails = []


def _load_lib():
    spec = importlib.util.spec_from_file_location("orbit_lock_lib", ROOT / "bin" / "orbit_lock_lib.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["orbit_lock_lib"] = m
    spec.loader.exec_module(m)
    return m


L = _load_lib()


def _mk(d):
    (Path(d) / ".orbit" / "locks").mkdir(parents=True, exist_ok=True)
    return Path(d)


def _ident(sid, kind="interactive"):
    return {"owner_id": sid, "owner_kind": kind, "session_id": sid, "transcript_id": ""}


def ck(cond, msg):
    if not cond:
        fails.append(msg)


def test_decision_table():
    now = L.now_utc()
    with tempfile.TemporaryDirectory() as d:
        t = _mk(d)
        # 1) no lock + Edit → allow + acquire
        dec = L.evaluate(t, "Edit", {"file_path": "x.py"}, _ident("A"), now)
        ck(dec["decision"] == "allow" and dec["action"] == "acquire", f"1 no-lock+Edit → {dec}")
        # set up: A owns a fresh lock
        L.write_lock_atomic(t, L.new_lock(t, _ident("A"), "task", now))
        # 2) same session + Edit → allow + heartbeat
        dec = L.evaluate(t, "Edit", {"file_path": "x"}, _ident("A"), now)
        ck(dec["decision"] == "allow" and dec["action"] == "heartbeat", f"2 same-session+Edit → {dec}")
        # 3) foreign + Edit → deny
        dec = L.evaluate(t, "Edit", {"file_path": "x"}, _ident("B"), now)
        ck(dec["decision"] == "deny", f"3 foreign+Edit → {dec}")
        # 4) foreign + STATE.md Write → deny, and the reason names STATE.md
        dec = L.evaluate(t, "Write", {"file_path": str(t / ".orbit/STATE.md")}, _ident("B"), now)
        ck(dec["decision"] == "deny" and "STATE.md" in dec["reason"], f"4 foreign+STATE.md → {dec}")
        # 7) foreign + git status → allow (read)
        dec = L.evaluate(t, "Bash", {"command": "git status"}, _ident("B"), now)
        ck(dec["decision"] == "allow", f"7 foreign+git status → {dec}")
        # 8) foreign + git commit → deny
        dec = L.evaluate(t, "Bash", {"command": "git commit -m x"}, _ident("B"), now)
        ck(dec["decision"] == "deny", f"8 foreign+git commit → {dec}")
        dec = L.evaluate(t, "Bash", {"command": "scripts/orbit-lock break --reason 'stale abandoned session'"}, _ident("B"), now)
        ck(dec["decision"] == "allow", f"foreign+orbit-lock break → {dec}")
        dec = L.evaluate(t, "Bash", {"command": "scripts/orbit-lock release --force"}, _ident("B"), now)
        ck(dec["decision"] == "deny", f"foreign+release --force must stay blocked → {dec}")
        # 5) stale foreign lock + Edit → deny WITH a break instruction
        stale = L.new_lock(t, _ident("A"), "", now)
        stale["heartbeat_at"] = "2000-01-01T00:00:00Z"
        L.write_lock_atomic(t, stale)
        dec = L.evaluate(t, "Edit", {"file_path": "x"}, _ident("B"), now)
        ck(dec["decision"] == "deny" and "break" in dec["reason"] and "STALE" in dec["reason"],
           f"5 stale+Edit → {dec}")
        # 11) malformed lock: write → deny (closed), read → allow (open)
        (t / ".orbit/locks/active-writer.json").write_text("{ not json")
        ck(L.evaluate(t, "Edit", {"file_path": "x"}, _ident("B"), now)["decision"] == "deny",
           "11 malformed+write should deny (fail closed)")
        ck(L.evaluate(t, "Bash", {"command": "cat x"}, _ident("B"), now)["decision"] == "allow",
           "11 malformed+read should allow (fail open)")
        ck(L.evaluate(t, "Bash", {"command": "cd /tmp && scripts/orbit-lock break --reason 'corrupt lock'"}, _ident("B"), now)["decision"] == "allow",
           "malformed+cd then orbit-lock break must allow")
        ck(L.evaluate(t, "Bash", {"command": "scripts/orbit-lock break"}, _ident("B"), now)["decision"] == "deny",
           "orbit-lock break without reason must stay blocked")


def test_classifier():
    W = [("git commit -m x", "write"), ("git push", "write"), ("rm -rf build", "write"),
         ("mv a b", "write"), ("sed -i 's/a/b/' f", "write"), ("echo hi > f.txt", "write"),
         ("python manage.py migrate", "write"), ("cat foo", "read"), ("git status", "read"),
         ("git diff HEAD", "read"), ("ls -la", "read"), ("rg pattern", "read"),
         ("pytest -q", "read"), ("python weird_script.py", "unknown"),
         # adversarial (v0.30.0 red-team): no-space redirects must NOT slip through as reads,
         # `2>&1` must not be shredded into a phantom write, `sed -i` writes but `sed -n` reads.
         ("echo x>f", "write"), ("echo x>>f", "write"), ("ls 2>&1", "read"),
         ("sed -n 1p f", "read"), ("awk '{print}' f", "read")]
    for cmd, want in W:
        got = L.classify_bash(cmd)
        ck(got == want, f"classify_bash({cmd!r}) = {got}, want {want}")
    ck(L.classify_write_intent("Edit", {}) == "write", "Edit tool is write")
    ck(L.classify_write_intent("Write", {}) == "write", "Write tool is write")
    ck(L.classify_write_intent("Read", {}) == "read", "Read tool is read")
    ck(L.classify_write_intent("Grep", {}) == "read", "Grep tool is read")


def test_staleness_and_identity():
    now = L.now_utc()
    with tempfile.TemporaryDirectory() as d:
        t = _mk(d)
        fresh = L.new_lock(t, _ident("A"), "", now)
        ck(not L.is_stale(fresh, now), "fresh lock is not stale")
        ck(L.is_stale(dict(fresh, heartbeat_at="2000-01-01T00:00:00Z"), now), "old heartbeat is stale")
        ck(L.is_stale(dict(fresh, heartbeat_at="garbage"), now), "unparseable heartbeat treated stale")
    ck(L.resolve_identity({"session_id": "S"})["owner_id"] == "S", "payload session_id wins")
    saved = {k: os.environ.get(k) for k in ("TERM_SESSION_ID", "ORBIT_SESSION_ID", "CLAUDE_SESSION_ID")}
    for k in saved:
        os.environ.pop(k, None)
    os.environ["ORBIT_SESSION_ID"] = "ENV"
    ck(L.resolve_identity({})["owner_id"] == "ENV", "ORBIT_SESSION_ID fallback")
    ck(L.resolve_identity({"cwd": "/x"})["owner_id"].startswith("unknown:") is False, "env beats cwd fallback")
    os.environ.pop("ORBIT_SESSION_ID")
    ck(L.resolve_identity({"cwd": "/x"})["owner_id"].startswith("unknown:"), "cwd-hash last-resort fallback")
    for k, v in saved.items():
        if v is not None:
            os.environ[k] = v


def _cli(target, *args, env=None):
    return subprocess.run([sys.executable, str(ROOT / "bin" / "orbit-lock"), *args, "--target", str(target)],
                          capture_output=True, text=True, env={**os.environ, **(env or {})})


def test_cli_lifecycle():
    with tempfile.TemporaryDirectory() as d:
        t = _mk(d)
        r = _cli(t, "status", env={"TERM_SESSION_ID": "A"})
        ck(r.returncode == 0 and "FREE" in r.stdout, f"status(free) → {r.returncode} {r.stdout!r}")
        r = _cli(t, "acquire", "--owner", "interactive", env={"TERM_SESSION_ID": "A"})
        ck(r.returncode == 0 and "ACQUIRED" in r.stdout, f"acquire(A) → {r.returncode} {r.stdout!r}")
        r = _cli(t, "acquire", "--owner", "background", env={"TERM_SESSION_ID": "B"})
        ck(r.returncode == 3, f"foreign acquire(B) must be REFUSED (rc3), got {r.returncode}")
        r = _cli(t, "heartbeat", env={"TERM_SESSION_ID": "A"})
        ck(r.returncode == 0, f"heartbeat(A) → {r.returncode}")
        r = _cli(t, "break", env={"TERM_SESSION_ID": "B"})  # no --reason
        ck(r.returncode == 2, f"break WITHOUT --reason must fail (rc2), got {r.returncode}")
        r = _cli(t, "break", "--reason", "took over", env={"TERM_SESSION_ID": "B"})
        ck(r.returncode == 0 and "BROKEN" in r.stdout, f"break --reason → {r.returncode} {r.stdout!r}")
        # audit trail written
        ev = (t / ".orbit/locks/events.jsonl")
        ck(ev.exists() and "broke" in ev.read_text() and "took over" in ev.read_text(),
           "events.jsonl records the break with its reason")
        r = _cli(t, "takeover", "--task", "handoff", "--reason", "approved handoff",
                 env={"TERM_SESSION_ID": "C"})
        ck(r.returncode == 0 and "TAKEOVER VERIFIED" in r.stdout,
           f"takeover must acquire and verify in one operation → {r.returncode} {r.stdout!r}")
        owner = json.loads((t / ".orbit/locks/active-writer.json").read_text()).get("owner_id")
        ck(owner == "C", f"takeover must leave the new owner in the lock, got {owner!r}")


def main():
    for fn in (test_decision_table, test_classifier, test_staleness_and_identity, test_cli_lifecycle):
        try:
            fn()
        except Exception as e:
            fails.append(f"[{fn.__name__}] raised {type(e).__name__}: {e}")
    if fails:
        print(f"FAIL: writer-lock {len(fails)} case(s):")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("PASS: writer-lock (decision table · classifier · staleness · identity · CLI lifecycle + audit)")


if __name__ == "__main__":
    main()
