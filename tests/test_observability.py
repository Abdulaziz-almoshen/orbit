#!/usr/bin/env python3
"""
Tests the telemetry chain: route.py + activity.py write schema-2 events, maintain the atomic
run.json snapshot, redact prompts (no control chars / no raw prompt), and the orbit-status
dashboard renders legacy + garbage lines without crashing (regression for the v0.22.1 bug where
route.py logged {ts:int, who:...} and orbit-status did ts[11:19] → TypeError).

Run: python3 tests/test_observability.py   (exit 0 = pass)
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ROUTE = os.path.join(ROOT, "assets", "checks", "route.py")
STATUS = os.path.join(ROOT, "assets", "orbit-status")


def _load_activity(orbit_dir):
    """Import assets/activity.py bound to a temp ORBIT_DIR."""
    os.environ["ORBIT_DIR"] = orbit_dir
    spec = importlib.util.spec_from_file_location("activity_t", os.path.join(ROOT, "assets", "activity.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    fails = []
    with tempfile.TemporaryDirectory() as d:
        orbit = os.path.join(d, ".orbit")
        os.makedirs(orbit)

        # --- 1. activity.py: schema-2 events + atomic run.json snapshot ---------------
        a = _load_activity(orbit)
        a.new_run(mode="feature", goal="build settings")
        a.set_tasks([{"id": "t1", "title": "classify", "owner": "dispatcher", "status": "done"},
                     {"id": "t2", "title": "build", "owner": "builder", "status": "in_progress"}])
        a.emit("builder", "build", "start", "editing form", cycle=2, task_id="t2",
               tokens=1000, cost_usd=0.04, confidence_delta=15,
               proof={"kind": "test", "status": "pass", "detail": "pytest"}, files=["src/x.ts"])
        run = json.loads(open(os.path.join(orbit, "run.json")).read())
        if run.get("schema") != 2 or not run.get("run_id"):
            fails.append(f"run.json missing schema/run_id: {run}")
        for k, want in (("mode", "feature"), ("phase", "build"), ("active_role", "builder"),
                        ("tasks_done", 1), ("tasks_total", 2), ("tokens", 1000), ("confidence", 15)):
            if run.get(k) != want:
                fails.append(f"run.json[{k}] = {run.get(k)!r}, expected {want!r}")
        if os.path.exists(os.path.join(orbit, "run.json.tmp")):
            fails.append("run.json.tmp left behind (non-atomic write)")
        ev = json.loads(open(os.path.join(orbit, "activity.jsonl")).read().splitlines()[-1])
        if ev.get("schema") != 2 or "proof" not in ev or "files" not in ev or ev.get("tokens") != 1000:
            fails.append(f"activity event not schema-2 w/ extended fields: {ev}")

    with tempfile.TemporaryDirectory() as d:
        orbit = os.path.join(d, ".orbit")
        os.makedirs(orbit)
        json.dump({"run_id": "rid1"}, open(os.path.join(orbit, "run.json"), "w"))

        # --- 2. route.py: redaction (no control chars, no raw prompt), schema-2 --------
        nasty = "add a \x1b[31mRED\x1b[0m logout button\nwith tabs " + "z" * 200
        subprocess.run([sys.executable, ROUTE], input=json.dumps({"prompt": nasty, "cwd": d}),
                       capture_output=True, text=True, cwd=d, timeout=10)
        act = os.path.join(orbit, "activity.jsonl")
        if not os.path.exists(act):
            fails.append("route.py did not write .orbit/activity.jsonl for a task")
        else:
            row = json.loads(open(act).read().splitlines()[-1])
            msg = row.get("msg", "")
            if row.get("schema") != 2 or row.get("role") != "dispatcher":
                fails.append(f"route.py wrote wrong schema/role: {row}")
            if row.get("run_id") != "rid1":
                fails.append(f"route.py did not tie the event to the run: {row.get('run_id')}")
            if any(c in msg for c in ("\x1b", "\n", "\t")):
                fails.append(f"route.py msg still contains control chars: {msg!r}")
            if "z" * 200 in msg or len(msg) > 120:
                fails.append(f"route.py logged the raw/uncapped prompt: {msg!r}")

        # --- 3. dashboard renders current + legacy + garbage without crashing ----------
        with open(act, "a") as f:
            f.write(json.dumps({"schema": 2, "ts": "2026-07-03T20:14:02Z", "role": "reviewer",
                                "phase": "verify", "status": "done", "msg": "tests green"}) + "\n")
            f.write(json.dumps({"ts": 1782149890, "who": "orchestrator", "phase": "plan",
                                "status": "start", "msg": "legacy event"}) + "\n")
            f.write("this is not json\n")
        p = subprocess.run([sys.executable, STATUS, "--tail", "10"], capture_output=True, text=True,
                           cwd=d, env={**os.environ, "ORBIT_DIR": orbit}, timeout=10)
        if p.returncode != 0:
            fails.append(f"orbit-status crashed (exit {p.returncode}): {p.stderr.strip()[:300]}")
        else:
            for needle in ("reviewer", "orchestrator", "dispatcher"):
                if needle not in p.stdout:
                    fails.append(f"orbit-status output missing '{needle}'")

    if fails:
        print("FAIL: observability")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("PASS: observability (schema-2 events + atomic run.json + prompt redaction + defensive render)")


if __name__ == "__main__":
    main()
