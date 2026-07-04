#!/usr/bin/env python3
"""
Tests the Orbit RUN CONTRACT — the operating-model promise that a task runs through a VISIBLE board
(role-tagged checklist + current owner + .orbit/tasks.json + .orbit/activity.jsonl), NOT the native
`Workflow(...)` background runner. This is Orbit's core product ("watch the team work"), so it's
guarded on two levels:

  A. Every run-contract surface (the /orbit-run command, the Orchestrator role, the router's injected
     TASK context, and the CLAUDE.md template's §10) must (1) name TaskCreate/TaskUpdate +
     .orbit/tasks.json + .orbit/activity.jsonl, (2) explicitly BAN the native Workflow(...) runner for
     task execution, and (3) say make-the-board-visible-FIRST.
  B. The Stop hook (orbit-stop-check.py) fails loudly (blocks once) when a routed task did real work
     but never made the board visible — and stays silent/fail-open otherwise. The scaffolder places
     and wires it.

Run: python3 tests/test_run_contract.py   (exit 0 = pass)
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STOP_HOOK = os.path.join(ROOT, "assets", "checks", "orbit-stop-check.py")


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def _has_ban(text):
    """The file forbids the native Workflow runner for task execution."""
    low = text.lower()
    if "workflow(" not in low:
        return False
    return any(w in low for w in ("do not", "don't", "never", "bypass", "black-box", "black box"))


# --- A. run-contract surfaces --------------------------------------------------------------------
SURFACES = {
    "commands/orbit-run.md": _read("commands", "orbit-run.md"),
    "assets/claude-agents/orchestrator.md": _read("assets", "claude-agents", "orchestrator.md"),
    "references/claude-md-template.md": _read("references", "claude-md-template.md"),
    "assets/checks/route.py": _read("assets", "checks", "route.py"),
}
_REQUIRED = ["TaskCreate", "TaskUpdate", ".orbit/tasks.json", ".orbit/activity.jsonl"]


def _run_stop(payload, cwd, project_dir=None):
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
    if project_dir:
        env["CLAUDE_PROJECT_DIR"] = project_dir
    p = subprocess.run([sys.executable, STOP_HOOK],
                       input=json.dumps(payload) if isinstance(payload, dict) else payload,
                       capture_output=True, text=True, cwd=cwd, timeout=10, env=env)
    return p.returncode, p.stdout.strip()


def _decision(out):
    return json.loads(out).get("decision") if out else None


def _scaffold_run_activity(orbit, route=True, work=0, board=False):
    os.makedirs(orbit, exist_ok=True)
    lines = []
    if route:
        lines.append({"schema": 2, "phase": "route", "status": "start", "role": "dispatcher", "msg": "routing: task"})
    for i in range(work):
        lines.append({"schema": 2, "phase": "build", "status": "edit", "role": "builder", "msg": f"edit f{i}"})
    with open(os.path.join(orbit, "activity.jsonl"), "w") as f:
        for l in lines:
            f.write(json.dumps(l) + "\n")
    t0 = time.time()
    if route:
        m = os.path.join(orbit, ".last-task-route")
        open(m, "w").write("t")
        os.utime(m, (t0, t0))
    if board:
        tj = os.path.join(orbit, "tasks.json")
        open(tj, "w").write("[]")
        os.utime(tj, (t0 + 5, t0 + 5))


def main():
    fails = []

    # A. every surface names the board files, bans Workflow, and (for the two run docs) says board-first
    for name, text in SURFACES.items():
        for tok in _REQUIRED:
            if tok not in text:
                fails.append(f"[A] {name} does not mention {tok!r}")
        if not _has_ban(text):
            fails.append(f"[A] {name} does not explicitly ban the native Workflow(...) runner")
    for name in ("commands/orbit-run.md", "assets/claude-agents/orchestrator.md"):
        if "FIRST" not in SURFACES[name]:
            fails.append(f"[A] {name} does not say make the board visible FIRST (before spawning specialists)")

    # B1. Stop hook: the GAP (task routed, real work, no board) → block loudly
    with tempfile.TemporaryDirectory() as d:
        orbit = os.path.join(d, ".orbit")
        _scaffold_run_activity(orbit, route=True, work=5, board=False)
        rc, out = _run_stop({"cwd": d}, d)
        if _decision(out) != "block":
            fails.append(f"[B] observability gap should BLOCK, got {out!r}")
        else:
            reason = json.loads(out)["reason"]
            if "observability" not in reason.lower() or "workflow" not in reason.lower():
                fails.append("[B] block reason must name the observability gap + the Workflow ban")

    # B2. board present → silent; B3. trivial work → silent; B4. no route → silent
    for label, kw in (("board-present", dict(work=5, board=True)),
                      ("trivial-work", dict(work=1, board=False)),
                      ("no-route", dict(route=False, work=3))):
        with tempfile.TemporaryDirectory() as d:
            _scaffold_run_activity(os.path.join(d, ".orbit"), **kw)
            rc, out = _run_stop({"cwd": d}, d)
            if _decision(out) is not None:
                fails.append(f"[B] {label} should be silent, got {out!r}")

    # B5. loop guard: stop_hook_active → silent
    with tempfile.TemporaryDirectory() as d:
        _scaffold_run_activity(os.path.join(d, ".orbit"), work=5, board=False)
        rc, out = _run_stop({"cwd": d, "stop_hook_active": True}, d)
        if _decision(out) is not None:
            fails.append(f"[B] stop_hook_active should be silent (no loop), got {out!r}")

    # B6. fail-open on malformed input
    with tempfile.TemporaryDirectory() as d:
        rc, out = _run_stop("not json", d)
        if rc != 0 or out:
            fails.append(f"[B] malformed input must fail open, got rc={rc} out={out!r}")

    # C. the scaffolder PLACES and WIRES the Stop hook
    sc = importlib.util.spec_from_file_location("scaffold_rc", os.path.join(ROOT, "scripts", "scaffold.py"))
    scaffold = importlib.util.module_from_spec(sc)
    sys.modules["scaffold_rc"] = scaffold
    sc.loader.exec_module(scaffold)
    if not any("orbit-stop-check.py" in dst for _, dst, *_ in scaffold.FILE_PLAN):
        fails.append("[C] scaffold.FILE_PLAN does not place orbit-stop-check.py")
    if "orbit-stop-check.py" not in getattr(scaffold, "STOP_CHECK_CMD", ""):
        fails.append("[C] scaffold.STOP_CHECK_CMD does not reference orbit-stop-check.py")
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["git", "init", "-q", d], check=True)
        subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "scaffold.py"),
                        "--surfaces", "web", "--install-hooks", "--target", d],
                       capture_output=True, text=True, check=True)
        if not os.path.isfile(os.path.join(d, ".orbit", "checks", "orbit-stop-check.py")):
            fails.append("[C] scaffolded repo did not place .orbit/checks/orbit-stop-check.py")
        settings = json.loads(_readfile(os.path.join(d, ".claude", "settings.json")))
        if "orbit-stop-check.py" not in json.dumps(settings.get("hooks", {}).get("Stop", [])):
            fails.append("[C] scaffolded settings.json did not wire the Stop → orbit-stop-check hook")

    if fails:
        print(f"FAIL: run-contract {len(fails)} case(s):")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("PASS: run-contract (Workflow ban on all surfaces + board-first + Stop observability hook "
          "gap/silent/fail-open + scaffold wires it)")


def _readfile(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


if __name__ == "__main__":
    main()
