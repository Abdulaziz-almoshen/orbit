#!/usr/bin/env python3
"""
Tests the Orbit GEARBOX — the loop sizes itself into a gear (T0 Direct · T1 Quick · T2 Standard ·
T3 Deep · T4 Mission) before doing work, declares a Gear Card, and scales its guardrails with the gear.

Guards:
  A. loop-tiers.md is the canonical spec — names all five gears, the scorecard axes, the Gear Card,
     the T3 phases (Map→Research→Plan→Critique→Synthesize→Build) + critic lenses, the prime directive
     + risk floors, always-confirm on T3+, the OWASP "minimal tools per worker" guardrail, and it keeps
     the v0.27.2 board contract (visible board, never native Workflow).
  B. Every surface points at the Gearbox: §10, the Orchestrator role, and route.py's injected TASK
     context all name the gears + "declare the gear"; the Orchestrator loads loop-tiers.md.
  C. route.py's gear_hint fires on breadth/research (→T3) and mission (→T4) signals, and stays silent
     on a plain task.
  D. loop.config.json ships the gears budget block (T3 caps incl. confirm_before_fanout; T4 durability).
  E. The scaffolder provisions loop-tiers.md into .orbit/skills/.

Run: python3 tests/test_loop_tiers.py   (exit 0 = pass)
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def main():
    fails = []

    # --- A. the canonical Gearbox spec -----------------------------------------------------------
    gb = _read("references", "playbooks", "loop-tiers.md")
    gl = gb.lower()
    for gear in ("t0", "t1", "t2", "t3", "t4", "direct", "quick", "standard", "deep", "mission"):
        if gear not in gl:
            fails.append(f"[A] loop-tiers.md never names gear token {gear!r}")
    for phase in ("map", "research", "plan", "critique", "synthesize", "build"):
        if phase not in gl:
            fails.append(f"[A] loop-tiers.md missing Deep phase {phase!r}")
    for lens in ("scalab", "complian", "ux"):
        if lens not in gl:
            fails.append(f"[A] loop-tiers.md missing critic lens {lens!r}")
    for axis in ("ambiguity", "blast radius", "surfaces", "research", "reversib", "runtime"):
        if axis not in gl:
            fails.append(f"[A] loop-tiers.md scorecard missing axis {axis!r}")
    if "gear card" not in gl:
        fails.append("[A] loop-tiers.md never defines the Gear Card")
    if "smallest gear" not in gl:
        fails.append("[A] loop-tiers.md missing the prime directive (smallest gear that proves the result)")
    if "floor" not in gl:
        fails.append("[A] loop-tiers.md missing the risk-floor rule")
    if "tools per worker" not in gl and "role-scoped tool" not in gl:
        fails.append("[A] loop-tiers.md missing the OWASP per-worker tool-scoping guardrail")
    if "confirm" not in gl:
        fails.append("[A] loop-tiers.md missing the always-confirm-before-fan-out rule")
    # the critique barrier + merge-logging + Gear-Card emission are load-bearing rules
    if "after a draft" not in gl and "barrier before critique" not in gl:
        fails.append("[A] loop-tiers.md missing the 'critique only after a draft' / barrier rule")
    if "merge" not in gl or "log" not in gl:
        fails.append("[A] loop-tiers.md missing the Research merge-and-log rule")
    if "activity.jsonl" not in gl or "gear card" not in gl:
        fails.append("[A] loop-tiers.md must say the Gear Card is emitted to activity.jsonl")
    # critics + synthesizer must REUSE existing roles, not invent new role types
    if "no new role" not in gl and "no separate" not in gl:
        fails.append("[A] loop-tiers.md must state the critics/synthesizer are existing roles (no new role types)")
    if "reviewer" not in gl or "safety" not in gl:
        fails.append("[A] loop-tiers.md must map the critics onto the Reviewer/Safety roles")
    # keeps the v0.27.2 board contract (no regression) — proximity-aware, not two loose substrings
    import re as _re
    if not _re.search(r"(never|not|do not|don't|bypass)[^.\n]{0,80}workflow\(|workflow\([^.\n]{0,80}(bypass|black.?box|never)", gl):
        fails.append("[A] loop-tiers.md must keep the Workflow ban (a negation near the Workflow( mention)")
    for tok in (".orbit/tasks.json", ".orbit/activity.jsonl"):
        if tok.lower() not in gl:
            fails.append(f"[A] loop-tiers.md must keep {tok} in the board contract")
    for tok in (".orbit/tasks.json", ".orbit/activity.jsonl"):
        if tok.lower() not in gl:
            fails.append(f"[A] loop-tiers.md must keep {tok} in the board contract")

    # --- B. every surface points at the Gearbox --------------------------------------------------
    surfaces = {
        "references/claude-md-template.md": _read("references", "claude-md-template.md"),
        "assets/claude-agents/orchestrator.md": _read("assets", "claude-agents", "orchestrator.md"),
        "assets/checks/route.py": _read("assets", "checks", "route.py"),
    }
    for name, text in surfaces.items():
        low = text.lower()
        if not all(g in low for g in ("t0", "t1", "t2", "t3", "t4")):
            fails.append(f"[B] {name} does not name all five gears T0–T4")
        if "gear" not in low:
            fails.append(f"[B] {name} never mentions the gear / Gearbox")
    orch = surfaces["assets/claude-agents/orchestrator.md"]
    ol = orch.lower()
    if ".orbit/skills/loop-tiers.md" not in orch:
        fails.append("[B] orchestrator.md does not LOAD .orbit/skills/loop-tiers.md")
    if "gear card" not in ol:
        fails.append("[B] orchestrator.md does not declare the Gear Card")
    # the operationalization the review flagged: caps read, board+Task tool on T3, human-gate, reuse
    if "gears.deep" not in ol:
        fails.append("[B] orchestrator.md does not read the gears.deep caps for the T3 fan-out")
    if "approval_checkpoints" not in ol:
        fails.append("[B] orchestrator.md does not operationalize the human gate (approval_checkpoints)")
    if "task tool" not in ol and "task-tool" not in ol:
        fails.append("[B] orchestrator.md does not bind the T3 fan-out to the Task tool / board")
    if not ("no new role" in ol and "reviewer" in ol and "safety" in ol):
        fails.append("[B] orchestrator.md must reuse existing roles for critics (Reviewer/Safety), no new role types")

    # --- C. route.py gear_hint behaviour ---------------------------------------------------------
    spec = importlib.util.spec_from_file_location("route_gb", os.path.join(ROOT, "assets", "checks", "route.py"))
    route = importlib.util.module_from_spec(spec)
    sys.modules["route_gb"] = route
    spec.loader.exec_module(route)
    checks = [
        ("add a logout button to the navbar", None),                                  # plain → silent
        ("1. housing report 2. iqama expiry 3. translation 4. email 5. reviews", "T3"),  # breadth → T3
        ("research the PDPL compliance and API access feasibility", "T3"),             # research → T3
        ("migrate the billing system to production across repos", "T4"),               # mission → T4
    ]
    for prompt, want in checks:
        h = route.gear_hint(prompt)
        got = "T4" if "T4" in h else ("T3" if "T3" in h else None)
        if got != want:
            fails.append(f"[C] gear_hint({prompt[:30]!r}) → {got}, want {want}")
    if "size the gear" not in route.TASK_CTX.lower():
        fails.append("[C] route.py TASK_CTX does not tell the model to size the gear first")

    # --- D. loop.config.json gears block ---------------------------------------------------------
    cfg = json.loads(_read("assets", "loop.config.json"))
    gears = cfg.get("gears", {})
    deep = gears.get("deep", {})
    for k in ("agent_max", "map_max", "research_max", "plan_max", "critics", "concurrency",
              "token_budget", "confirm_before_fanout"):
        if k not in deep:
            fails.append(f"[D] loop.config.json gears.deep missing {k!r}")
    if deep.get("confirm_before_fanout") is not True:
        fails.append("[D] gears.deep.confirm_before_fanout must be true (always confirm on T3)")
    if deep.get("agent_max") != 16:
        fails.append(f"[D] gears.deep.agent_max should be 16, got {deep.get('agent_max')}")
    for k in ("map_max", "research_max", "plan_max", "critics", "concurrency"):
        if not isinstance(deep.get(k), int) or deep.get(k) < 1:
            fails.append(f"[D] gears.deep.{k} must be a positive integer, got {deep.get(k)!r}")
    if not isinstance(deep.get("token_budget"), int) or deep.get("token_budget") < 1000:
        fails.append(f"[D] gears.deep.token_budget must be a real token cap, got {deep.get('token_budget')!r}")
    mission = gears.get("mission", {})
    for k in ("durable", "resumable", "human_gate_per_irreversible_step", "artifact_bundle"):
        if mission.get(k) is not True:
            fails.append(f"[D] gears.mission.{k} must be true (T4 durability/audit)")

    # --- E. scaffolder provisions loop-tiers.md --------------------------------------------------
    sc = importlib.util.spec_from_file_location("scaffold_gb", os.path.join(ROOT, "scripts", "scaffold.py"))
    scaffold = importlib.util.module_from_spec(sc)
    sys.modules["scaffold_gb"] = scaffold
    sc.loader.exec_module(scaffold)
    if "loop-tiers.md" not in scaffold.PLAYBOOKS_ALWAYS:
        fails.append("[E] scaffold PLAYBOOKS_ALWAYS does not include loop-tiers.md")
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["git", "init", "-q", d], check=True)
        subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "scaffold.py"),
                        "--surfaces", "api", "--target", d], capture_output=True, text=True, check=True)
        if not os.path.isfile(os.path.join(d, ".orbit", "skills", "loop-tiers.md")):
            fails.append("[E] scaffolded repo did not provision .orbit/skills/loop-tiers.md")

    if fails:
        print(f"FAIL: loop-tiers {len(fails)} case(s):")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("PASS: loop-tiers (Gearbox spec + all surfaces + gear hints + config caps + provisioning)")


if __name__ == "__main__":
    main()
