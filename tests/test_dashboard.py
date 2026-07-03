#!/usr/bin/env python3
"""
Tests assets/orbit-status (the rich dashboard): the --compact/--json/--no-ansi modes, the
lifecycle strip + progress + confidence sections, stall detection, and full defensiveness — a
garbage run.json, a missing run.json, or a bad event line must never crash any mode.

Run: python3 tests/test_dashboard.py   (exit 0 = pass)
"""
import json
import os
import subprocess
import sys
import tempfile
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STATUS = os.path.join(ROOT, "assets", "orbit-status")
ASSETS = os.path.join(ROOT, "assets")


def run(orbit_dir, *args):
    env = {**os.environ, "ORBIT_DIR": orbit_dir, "NO_COLOR": "1"}
    return subprocess.run([sys.executable, STATUS, *args], capture_output=True, text=True,
                          env=env, timeout=10)


def _seed(d, run_json, tasks, events):
    o = os.path.join(d, ".orbit")
    os.makedirs(o, exist_ok=True)
    for mod in ("confidence.py", "lifecycle.py"):                # provision so features engage
        with open(os.path.join(ASSETS, mod), "rb") as a, open(os.path.join(o, mod), "wb") as b:
            b.write(a.read())
    if run_json is not None:
        with open(os.path.join(o, "run.json"), "w") as f:
            f.write(run_json if isinstance(run_json, str) else json.dumps(run_json))
    json.dump(tasks, open(os.path.join(o, "tasks.json"), "w"))
    with open(os.path.join(o, "activity.jsonl"), "w") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")
    return o


def main():
    fails = []
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    run_json = {"schema": 2, "run_id": "r1", "mode": "feature", "phase": "build",
                "active_role": "builder", "started_ts": now, "last_ts": now, "cycle": 2,
                "tasks_done": 5, "tasks_total": 9, "tokens": 41000, "cost_usd": 0.42,
                "blocked_question": None}
    tasks = [{"id": "t1", "title": "classify", "owner": "dispatcher", "status": "done"},
             {"id": "t2", "title": "build UI", "owner": "builder", "status": "in_progress"}]
    events = [{"schema": 2, "ts": now, "role": "reviewer", "phase": "verify", "status": "done",
               "msg": "tests green", "proof": {"kind": "test", "status": "pass"}},
              {"schema": 2, "ts": now, "role": "builder", "phase": "build", "status": "start",
               "msg": "editing form"}]

    with tempfile.TemporaryDirectory() as d:
        o = _seed(d, run_json, tasks, events)

        full = run(o)
        for needle in ("Lifecycle", "[Build]", "Progress", "5/9", "Budget", "$0.42",
                       "Confidence", "65%", "editing form"):
            if needle not in full.stdout:
                fails.append(f"full dashboard missing '{needle}'")
        if full.returncode != 0:
            fails.append(f"full mode nonzero exit: {full.stderr[:200]}")

        comp = run(o, "--compact")
        if comp.returncode != 0 or "5/9" not in comp.stdout or "conf 65%" not in comp.stdout:
            fails.append(f"--compact wrong: {comp.stdout!r}")

        js = run(o, "--json")
        try:
            obj = json.loads(js.stdout)
            if obj["run"]["confidence"] != 65 or obj["run"]["tasks_total"] != 9:
                fails.append(f"--json wrong values: {obj['run']}")
        except Exception as e:
            fails.append(f"--json did not produce valid JSON: {e} | {js.stdout[:200]!r}")

        # no ANSI escapes when NO_COLOR
        if "\x1b" in full.stdout:
            fails.append("NO_COLOR output still contains ANSI escapes")

    # --- stall detection: an old last event → 'possibly stalled' -----------------------
    with tempfile.TemporaryDirectory() as d:
        old = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 200))
        rj = dict(run_json); rj["last_ts"] = old
        o = _seed(d, rj, tasks, [{"schema": 2, "ts": old, "role": "builder", "status": "start", "msg": "x"}])
        out = run(o).stdout
        if "stalled" not in out:
            fails.append(f"stall detection missing for a 200s-old event: {out[-200:]!r}")

    # --- blocked run surfaces 'Needs input' --------------------------------------------
    with tempfile.TemporaryDirectory() as d:
        rj = dict(run_json); rj["blocked_question"] = "Choose the path"
        o = _seed(d, rj, tasks, events)
        if "Needs input" not in run(o).stdout:
            fails.append("blocked run did not surface 'Needs input'")

    # --- defensive: garbage run.json, missing run.json, bad event line -----------------
    with tempfile.TemporaryDirectory() as d:
        o = _seed(d, "{ this is not json", tasks, events)
        with open(os.path.join(o, "activity.jsonl"), "a") as f:
            f.write("not a json line\n")
        for args in ([], ["--compact"], ["--json"]):
            r = run(o, *args)
            if r.returncode != 0:
                fails.append(f"garbage run.json crashed mode {args}: {r.stderr[:200]}")
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, ".orbit"))                   # no run.json / tasks / activity
        for args in ([], ["--compact"], ["--json"]):
            r = run(os.path.join(d, ".orbit"), *args)
            if r.returncode != 0:
                fails.append(f"empty .orbit crashed mode {args}: {r.stderr[:200]}")

    if fails:
        print("FAIL: dashboard")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("PASS: dashboard (compact/json/no-ansi modes, lifecycle+progress+confidence, stall, fully defensive)")


if __name__ == "__main__":
    main()
