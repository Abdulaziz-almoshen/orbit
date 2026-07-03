#!/usr/bin/env python3
"""
Tests the manager-visible team board: activity.set_team() declares queued agents + responsibilities;
emit() keeps the active agent's roster live (mission, last signal, started_at); orbit-status --team
renders Working-now / Queued; the status line surfaces the active agent by name; orbit-hook drives
the roster from SubagentStart/Stop and attributes tool edits to whoever's active (no phantom
'builder'). All fail-safe.

Run: python3 tests/test_team_board.py   (exit 0 = pass)
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STATUS = os.path.join(ROOT, "assets", "orbit-status")
SL = os.path.join(ROOT, "assets", "orbit-statusline.py")
HOOK = os.path.join(ROOT, "bin", "orbit-hook")
ASSETS = os.path.join(ROOT, "assets")


def _load_activity(orbit_dir):
    os.environ["ORBIT_DIR"] = orbit_dir
    spec = importlib.util.spec_from_file_location("activity_tb", os.path.join(ASSETS, "activity.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _provision(orbit):
    for mod in ("confidence.py", "lifecycle.py"):
        with open(os.path.join(ASSETS, mod), "rb") as a, open(os.path.join(orbit, mod), "wb") as b:
            b.write(a.read())


def main():
    fails = []
    with tempfile.TemporaryDirectory() as d:
        orbit = os.path.join(d, ".orbit")
        os.makedirs(orbit)
        _provision(orbit)
        a = _load_activity(orbit)
        a.new_run(mode="feature", goal="worker lifecycle spine")
        a.set_team([{"role": "frontend-engineer", "task": "F-S1", "status": "active"},
                    {"role": "reviewer"}, {"role": "safety-gate"}, {"role": "reporter"}])
        a.set_tasks([{"id": f"s{i}", "title": f"slice {i}", "owner": "", "status": "pending"}
                     for i in range(5)])
        a.emit("frontend-engineer", "build", "start", "Building worker lifecycle spine", task_id="F-S1")
        a.emit("frontend-engineer", "build", "info", "edited lifecycle schema + wiring UI copy")

        agents = json.loads(open(os.path.join(orbit, "agents.json")).read())
        fe = agents.get("frontend-engineer", {})
        if fe.get("status") != "active" or fe.get("display") != "Frontend Engineer":
            fails.append(f"active agent roster wrong: {fe}")
        if fe.get("mission") != "Building worker lifecycle spine":
            fails.append(f"mission (first stint message) wrong: {fe.get('mission')!r}")
        if fe.get("last_message") != "edited lifecycle schema + wiring UI copy":
            fails.append(f"last_message wrong: {fe.get('last_message')!r}")
        if not fe.get("started_at"):
            fails.append("active agent has no started_at clock")
        for q in ("reviewer", "safety-gate", "reporter"):
            if agents.get(q, {}).get("status") != "queued" or not agents[q].get("responsibility"):
                fails.append(f"queued agent {q} not declared with responsibility: {agents.get(q)}")

        # dashboard --team renders the standup board
        env = {**os.environ, "ORBIT_DIR": orbit, "NO_COLOR": "1"}
        board = subprocess.run([sys.executable, STATUS, "--team"], capture_output=True, text=True,
                               env=env, timeout=10).stdout
        for needle in ("Working now", "Frontend Engineer", "active", "Building worker lifecycle spine",
                       "Last signal:", "Next: Reviewer", "Queued", "Safety", "Reporter"):
            if needle not in board:
                fails.append(f"--team board missing '{needle}'")

        # --json includes the roster
        js = subprocess.run([sys.executable, STATUS, "--json"], capture_output=True, text=True,
                            env=env, timeout=10).stdout
        if "frontend-engineer" not in js or '"agents"' not in js:
            fails.append("--json missing the agents roster")

        # status line surfaces the active agent by name
        claude = {"cwd": d, "context_window": {"used_percentage": 38}}
        line = subprocess.run([sys.executable, SL], input=json.dumps(claude), capture_output=True,
                              text=True, timeout=10).stdout.strip()
        if "F-S1" not in line or "Frontend Engineer" not in line or "0/" not in line:
            fails.append(f"status line missing active agent / slice: {line!r}")

    # --- orbit-hook drives the roster + attributes edits to the active agent ----------
    with tempfile.TemporaryDirectory() as d:
        orbit = os.path.join(d, ".orbit")
        os.makedirs(orbit)

        def fire(p):
            subprocess.run([sys.executable, HOOK], input=json.dumps(p), capture_output=True,
                           text=True, cwd=d, timeout=10)
        fire({"hook_event_name": "SubagentStart", "agent_type": "frontend-engineer", "cwd": d})
        fire({"hook_event_name": "PostToolUse", "tool_name": "Edit",
              "tool_input": {"file_path": "src/Settings.tsx"}, "cwd": d})
        agents = json.loads(open(os.path.join(orbit, "agents.json")).read())
        if "builder" in agents:
            fails.append("PostToolUse created a phantom 'builder' instead of attributing to the active agent")
        fe = agents.get("frontend-engineer", {})
        if fe.get("status") != "active" or "Settings.tsx" not in (fe.get("last_message") or ""):
            fails.append(f"orbit-hook did not attribute the edit to the active agent: {fe}")
        fire({"hook_event_name": "SubagentStop", "agent_type": "frontend-engineer", "cwd": d})
        agents = json.loads(open(os.path.join(orbit, "agents.json")).read())
        if agents["frontend-engineer"].get("status") != "done":
            fails.append("SubagentStop did not mark the agent done")

    # --- fail-safe: garbage agents.json never crashes the dashboard/statusline --------
    with tempfile.TemporaryDirectory() as d:
        orbit = os.path.join(d, ".orbit")
        os.makedirs(orbit)
        open(os.path.join(orbit, "agents.json"), "w").write("{ not json")
        env = {**os.environ, "ORBIT_DIR": orbit, "NO_COLOR": "1"}
        for args in ([], ["--team"], ["--json"], ["--compact"]):
            r = subprocess.run([sys.executable, STATUS, *args], capture_output=True, text=True,
                               env=env, timeout=10)
            if r.returncode != 0:
                fails.append(f"garbage agents.json crashed {args}: {r.stderr[:150]}")

    if fails:
        print("FAIL: team-board")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("PASS: team-board (roster + set_team + mission/last-signal, --team board, statusline agent, "
          "orbit-hook attribution, fail-safe)")


if __name__ == "__main__":
    main()
