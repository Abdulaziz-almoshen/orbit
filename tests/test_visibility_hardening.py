#!/usr/bin/env python3
"""
Regression tests for three reproduced P1s in the visibility system:
  1. Subdirectory: orbit-hook + orbit-statusline must find the repo-root .orbit/ when Claude works
     inside a subdir (packages/app), not miss it.
  2. Run isolation: the dashboard must scope proof/confidence to the CURRENT run_id — an old run's
     'test pass' can't inflate a fresh run's confidence.
  3. Secret leak: a key pasted into a prompt / tool arg / notification must be [redacted] before it
     lands in activity.jsonl (route.py + orbit-hook) or is displayed (orbit-status).

Run: python3 tests/test_visibility_hardening.py   (exit 0 = pass)
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ROUTE = os.path.join(ROOT, "assets", "checks", "route.py")
HOOK = os.path.join(ROOT, "bin", "orbit-hook")
SL = os.path.join(ROOT, "assets", "orbit-statusline.py")
STATUS = os.path.join(ROOT, "assets", "orbit-status")
ASSETS = os.path.join(ROOT, "assets")

SECRETS = [
    "sk-proj-AbC123dEf456GHI789jklMNO",
    "ghp_ABCdef1234567890123456789012345678",
    "AKIA1234567890ABCDEF",
    "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.abcDEF123456",
]


def main():
    fails = []

    # --- 1. subdirectory resolution --------------------------------------------------
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, ".orbit"))
        os.makedirs(os.path.join(d, "packages", "app"))
        sub = os.path.join(d, "packages", "app")
        subprocess.run([sys.executable, HOOK],
                       input=json.dumps({"hook_event_name": "SubagentStart", "agent_type": "builder", "cwd": sub}),
                       capture_output=True, text=True, timeout=10)
        if not os.path.exists(os.path.join(d, ".orbit", "activity.jsonl")):
            fails.append("orbit-hook from a subdir did not record to the repo-root .orbit/")
        # statusline from a subdir finds root run.json
        json.dump({"run_id": "r1", "phase": "build", "tasks_done": 2, "tasks_total": 5},
                  open(os.path.join(d, ".orbit", "run.json"), "w"))
        r = subprocess.run([sys.executable, SL], input=json.dumps({"cwd": sub, "context_window": {"used_percentage": 38}}),
                           capture_output=True, text=True, timeout=10)
        if "2/5" not in r.stdout:
            fails.append(f"statusline from a subdir did not find root run.json: {r.stdout!r}")

    # --- 2. run isolation ------------------------------------------------------------
    with tempfile.TemporaryDirectory() as d:
        orbit = os.path.join(d, ".orbit")
        os.makedirs(orbit)
        for mod in ("confidence.py", "lifecycle.py"):
            with open(os.path.join(ASSETS, mod), "rb") as a, open(os.path.join(orbit, mod), "wb") as b:
                b.write(a.read())
        json.dump({"run_id": "NEW", "phase": "build", "tasks_total": 3}, open(os.path.join(orbit, "run.json"), "w"))
        with open(os.path.join(orbit, "activity.jsonl"), "w") as f:
            f.write(json.dumps({"run_id": "OLD", "role": "reviewer", "status": "done",
                                "msg": "old run", "proof": {"kind": "test", "status": "pass"}}) + "\n")
            f.write(json.dumps({"run_id": "NEW", "role": "builder", "status": "start", "msg": "building"}) + "\n")
        j = subprocess.run([sys.executable, STATUS, "--json"], capture_output=True, text=True,
                           env={**os.environ, "ORBIT_DIR": orbit, "NO_COLOR": "1"}, timeout=10)
        conf = json.loads(j.stdout)["run"]["confidence"]
        if conf != 50:
            fails.append(f"run isolation broken: fresh run shows confidence {conf} (old proof leaked; want 50)")

    # --- 3. secret redaction ---------------------------------------------------------
    # route.py: a secret in a prompt never lands in activity.jsonl
    for secret in SECRETS:
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, ".orbit"))
            json.dump({"run_id": "r1"}, open(os.path.join(d, ".orbit", "run.json"), "w"))
            subprocess.run([sys.executable, ROUTE],
                           input=json.dumps({"prompt": f"deploy with {secret} now", "cwd": d}),
                           capture_output=True, text=True, timeout=10)
            log = open(os.path.join(d, ".orbit", "activity.jsonl")).read()
            if secret in log:
                fails.append(f"route.py leaked a secret into activity.jsonl: {secret[:12]}…")
            if "[redacted]" not in log:
                fails.append(f"route.py did not redact the secret {secret[:12]}…")
    # orbit-hook: a secret in a notification never lands in activity.jsonl
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, ".orbit"))
        subprocess.run([sys.executable, HOOK],
                       input=json.dumps({"hook_event_name": "Notification",
                                         "message": f"paste {SECRETS[1]} here", "cwd": d}),
                       capture_output=True, text=True, timeout=10)
        log = open(os.path.join(d, ".orbit", "activity.jsonl")).read()
        if SECRETS[1] in log:
            fails.append("orbit-hook leaked a secret from a Notification")
    # benign text with no secret is unchanged (no over-redaction of normal prompts)
    spec = importlib.util.spec_from_file_location("r", ROUTE)
    r = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(r)
    if r._redact("add a logout button to the settings page") != "add a logout button to the settings page":
        fails.append("secret scrub over-redacted a benign prompt")

    if fails:
        print("FAIL: visibility-hardening")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("PASS: visibility-hardening (subdir resolution + run isolation + secret redaction)")


if __name__ == "__main__":
    main()
