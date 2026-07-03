#!/usr/bin/env python3
"""
Tests the router → activity → dashboard chain doesn't crash (regression for the v0.22.1 bug
where route.py logged {ts:int, who:...} and orbit-status did ts[11:19] → TypeError on the first
routed message). Also feeds a legacy-schema line to prove the dashboard is defensive.

Run: python3 tests/test_observability.py   (exit 0 = pass)
"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.join(os.path.dirname(__file__), "..")
ROUTE = os.path.join(ROOT, "assets", "checks", "route.py")
STATUS = os.path.join(ROOT, "assets", "orbit-status")


def main():
    fails = []
    with tempfile.TemporaryDirectory() as d:
        orbit = os.path.join(d, ".orbit")
        os.makedirs(orbit)

        # 1. route.py logs a routing event (run with cwd=temp so it writes .orbit/activity.jsonl)
        stdin = json.dumps({"prompt": "add a logout button", "cwd": d})
        subprocess.run([sys.executable, ROUTE], input=stdin, capture_output=True, text=True, cwd=d, timeout=10)

        act = os.path.join(orbit, "activity.jsonl")
        if not os.path.exists(act):
            fails.append("route.py did not write .orbit/activity.jsonl")
        else:
            row = json.loads(open(act).read().splitlines()[-1])
            if not isinstance(row.get("ts"), str) or "role" not in row:
                fails.append(f"route.py wrote the wrong schema: {row}")

        # 2. a well-formed current event + a legacy (int ts, 'who') event + a garbage line
        with open(act, "a") as f:
            f.write(json.dumps({"ts": "2026-07-03T20:14:02Z", "role": "reviewer", "phase": "act", "status": "done", "msg": "tests green"}) + "\n")
            f.write(json.dumps({"ts": 1782149890, "who": "orchestrator", "phase": "plan", "status": "start", "msg": "legacy event"}) + "\n")
            f.write("this is not json\n")

        # 3. the dashboard must render without crashing and include both actors
        p = subprocess.run([sys.executable, STATUS, "--tail", "10"],
                           capture_output=True, text=True, cwd=d,
                           env={**os.environ, "ORBIT_DIR": orbit}, timeout=10)
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
    print("PASS: observability (router schema + defensive dashboard, legacy + garbage tolerated)")


if __name__ == "__main__":
    main()
