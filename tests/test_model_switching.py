#!/usr/bin/env python3
"""
Model switching policy (v0.39.x): Orbit runs cheap by default and escalates to an Opus Advisor
only on demand. This guards the exact failure mode where a big model becomes an always-on worker.

Run: python3 tests/test_model_switching.py   (exit 0 = pass)
"""
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def main():
    fails = []
    cfg = json.loads(_read("assets", "loop.config.json"))
    mp = cfg.get("model_policy", {})
    ex = mp.get("executor", {})
    ad = mp.get("advisor", {})
    if ex.get("model") != "sonnet" or ex.get("display") != "Sonnet 5":
        fails.append("[config] executor lane must be sonnet / Sonnet 5")
    if ad.get("model") != "opus" or ad.get("display") != "Opus 4.8":
        fails.append("[config] advisor lane must be opus / Opus 4.8")
    if ad.get("runs") != "on_demand" or ad.get("max_calls_per_cycle") != 1:
        fails.append("[config] advisor must be on-demand and capped to one call per cycle")
    if ad.get("requires_reason") is not True or ad.get("output_word_limit", 9999) > 500:
        fails.append("[config] advisor must require a reason and a compact output limit")
    for trigger in ("architecture_fork", "safety_or_compliance_uncertainty",
                    "repeated_gate_failure", "expensive_if_wrong_decision"):
        if trigger not in ad.get("allowed_triggers", []):
            fails.append(f"[config] advisor allowed_triggers missing {trigger}")

    advisor = _read("assets", "claude-agents", "advisor.md")
    if not re.search(r"(?m)^model:\s*opus\s*$", advisor):
        fails.append("[agent] advisor.md must pin model: opus")
    front = advisor.split("---", 2)[1]
    if any(tool in front for tool in ("Write", "Edit", "Bash", "MultiEdit")):
        fails.append("[agent] advisor must stay read-only (no Write/Edit/Bash tools)")
    low_advisor = advisor.lower()
    for tok in ("on demand", "advises", "never edits", "400 words"):
        if tok not in low_advisor:
            fails.append(f"[agent] advisor.md missing {tok!r}")

    surfaces = {
        "route.py": _read("assets", "checks", "route.py"),
        "orchestrator.md": _read("assets", "claude-agents", "orchestrator.md"),
        "loop-tiers.md": _read("references", "playbooks", "loop-tiers.md"),
        "claude-md-template.md": _read("references", "claude-md-template.md"),
        "roles.md": _read("references", "roles.md"),
        "README.md": _read("README.md"),
    }
    for name, text in surfaces.items():
        low = text.lower()
        if "advisor" not in low or "opus 4.8" not in low:
            fails.append(f"[docs] {name} must name the Opus 4.8 Advisor")
        if "on demand" not in low and "on-demand" not in low:
            fails.append(f"[docs] {name} must keep the Advisor on-demand")
        if "ordinary" in low and "executor" not in low:
            fails.append(f"[docs] {name} mentions ordinary work without the Executor lane")

    ralph = _read("assets", "ralph_loop.sh")
    if "model_policy" not in ralph or "--model" not in ralph or "CLAUDE_MODEL_ARGS" not in ralph:
        fails.append("[runner] ralph_loop.sh must read model_policy and pass --model for executor")
    loop_py = _read("assets", "loop.py")
    if "def model_lane" not in loop_py or "model_policy" not in loop_py:
        fails.append("[runner] loop.py must expose model_lane for portable adapters")

    sc = importlib.util.spec_from_file_location("scaffold_ms", os.path.join(ROOT, "scripts", "scaffold.py"))
    scaffold = importlib.util.module_from_spec(sc)
    sys.modules["scaffold_ms"] = scaffold
    sc.loader.exec_module(scaffold)
    if "advisor" not in scaffold.ROLES_CORE:
        fails.append("[scaffold] advisor must be part of the universal spine catalog")
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["git", "init", "-q", d], check=True)
        subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "scaffold.py"),
                        "--surfaces", "api", "--target", d], capture_output=True, text=True, check=True)
        for rel in (".claude/agents/advisor.md", ".orbit/roles/advisor.md"):
            if not os.path.isfile(os.path.join(d, rel)):
                fails.append(f"[scaffold] scaffold did not provision {rel}")

    if fails:
        print(f"FAIL: model-switching {len(fails)} case(s):")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("PASS: model-switching (Sonnet executor + Opus Advisor on demand + scaffold/runner/docs)")


if __name__ == "__main__":
    main()
