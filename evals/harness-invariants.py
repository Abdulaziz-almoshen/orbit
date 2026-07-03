#!/usr/bin/env python3
"""
harness-invariants.py — the DETERMINISTIC half of the eval: does `/orbit` (via scaffold.py)
actually produce the governed structure it promises, and do the brakes bind?

This does NOT grade model-authored output quality (CLAUDE.md prose, the domain skill, whether the
build is any good) — that needs a live model run + a judge, and is the manual A/B in run-eval.sh.
What it checks is the part that must be true every time, and can be verified with no model:

  1. the universal spine of roles is provisioned (incl. BOTH gates: safety + reviewer, + QA)
  2. loop.config.json carries real hard limits (iterations, token, cost, runtime)
  3. approval_checkpoints exist with a FORBIDDEN and a human gate
  4. both hooks are wired into .claude/settings.json
  5. the safety wall actually DENYs a force-push (correct envelope), and allows a normal commit
  6. the router injects a lane for a task and for a question

Usage:  harness-invariants.py --files <dir> [--surfaces web,cli]
Exit code = number of failed invariants (0 = all pass).
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPINE = {"dispatcher", "orchestrator", "planner", "reviewer", "qa-engineer",
         "reporter", "safety-gate", "product-discovery", "market-researcher"}


def _hook(path, payload):
    r = subprocess.run([sys.executable, path], input=json.dumps(payload),
                       capture_output=True, text=True)
    out = r.stdout.strip()
    return json.loads(out) if out else None


def check(files_dir, surfaces):
    results = []       # (ok, label)

    with tempfile.TemporaryDirectory() as d:
        # seed the repo with the eval's files so surface detection has something real to see
        if files_dir and os.path.isdir(files_dir):
            for fn in os.listdir(files_dir):
                src = os.path.join(files_dir, fn)
                if os.path.isfile(src):
                    with open(src, "rb") as a, open(os.path.join(d, fn), "wb") as b:
                        b.write(a.read())

        cmd = [sys.executable, os.path.join(ROOT, "scripts", "scaffold.py"),
               "--install-hooks", "--target", d]
        if surfaces:
            cmd += ["--surfaces", surfaces]
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode != 0:
            return [(False, f"scaffold failed: {p.stderr.strip()[:200]}")]

        # 1. spine roles
        agents = {f[:-3] for f in os.listdir(os.path.join(d, ".claude/agents")) if f.endswith(".md")}
        missing = SPINE - agents
        results.append((not missing, f"spine roles provisioned (both gates present)"
                        + (f" — MISSING {sorted(missing)}" if missing else "")))

        # 2. hard limits
        cfg = json.load(open(os.path.join(d, ".orbit/loop.config.json")))
        hl = cfg.get("hard_limits", {})
        has_limits = all(k in hl for k in ("max_iterations", "token_budget", "cost_budget_usd", "max_runtime_seconds"))
        results.append((has_limits, "hard limits present (iterations/token/cost/runtime)"))

        # 3. approval checkpoints
        ck = cfg.get("approval_checkpoints", {})
        has_gates = "FORBIDDEN" in ck.values() and "human" in ck.values()
        results.append((has_gates, "approval_checkpoints have a FORBIDDEN + a human gate"))

        # 4. hooks wired
        st = json.load(open(os.path.join(d, ".claude/settings.json")))
        blob = json.dumps(st.get("hooks", {}))
        wired = "guard.py" in blob and "route.py" in blob
        results.append((wired, "both hooks wired into .claude/settings.json"))

        # 5. safety wall binds (correct envelope)
        guard = os.path.join(d, ".orbit/checks/guard.py")
        deny = _hook(guard, {"tool_name": "Bash", "tool_input": {"command": "cd x && git push --force"}})
        allow = _hook(guard, {"tool_name": "Bash", "tool_input": {"command": "git commit -m ok"}})
        deny_ok = bool(deny) and deny.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"
        allow_ok = allow is None
        results.append((deny_ok and allow_ok, "safety wall DENYs force-push (cd&& too), allows normal commit"))

        # 6. router injects lanes
        route = os.path.join(d, ".orbit/checks/route.py")
        t = _hook(route, {"prompt": "add a confirmation prompt to app.py"})
        q = _hook(route, {"prompt": "is the data persisted?"})
        t_ok = bool(t) and "TASK" in t.get("hookSpecificOutput", {}).get("additionalContext", "")
        q_ok = bool(q) and "QUESTION" in q.get("hookSpecificOutput", {}).get("additionalContext", "")
        results.append((t_ok and q_ok, "router injects a TASK lane and a QUESTION lane"))

    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", help="dir of eval seed files to drop into the scratch repo")
    ap.add_argument("--surfaces", default="", help="comma-separated surfaces to pass to scaffold")
    args = ap.parse_args()

    results = check(args.files, args.surfaces)
    failed = 0
    for ok, label in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")
        if not ok:
            failed += 1
    sys.exit(failed)


if __name__ == "__main__":
    main()
