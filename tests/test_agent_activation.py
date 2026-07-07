#!/usr/bin/env python3
"""
Agent activation policy (v0.38.x): Orbit may ship many specialists, but they are a catalog,
not payroll. The default run is one owner, zero/one sub-agent, tiny packets, approval before fanout.

Run: python3 tests/test_agent_activation.py   (exit 0 = pass)
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def main():
    fails = []
    cfg = json.loads(_read("assets", "loop.config.json"))
    cm = cfg.get("cost_mode", {})
    if cm.get("activation_model") != "catalog_not_payroll":
        fails.append("[config] cost_mode.activation_model must be catalog_not_payroll")
    if cm.get("max_subagents_without_approval") != 1:
        fails.append("[config] max_subagents_without_approval must be 1")
    if cm.get("fanout_requires_approval") is not True:
        fails.append("[config] fanout_requires_approval must be true")
    if cm.get("packet_file_limit") != 8:
        fails.append("[config] packet_file_limit must be 8")
    if cm.get("packet_output_word_limit") != 500:
        fails.append("[config] packet_output_word_limit must be 500")

    surfaces = {
        "route.py": _read("assets", "checks", "route.py"),
        "orchestrator.md": _read("assets", "claude-agents", "orchestrator.md"),
        "loop-tiers.md": _read("references", "playbooks", "loop-tiers.md"),
        "claude-md-template.md": _read("references", "claude-md-template.md"),
        "roles.md": _read("references", "roles.md"),
    }
    for name, text in surfaces.items():
        low = text.lower()
        if "catalog" not in low or "payroll" not in low:
            fails.append(f"[docs] {name} must say agents are catalog, not payroll")
        if "one sub-agent" not in low and "1 sub-agent" not in low and "zero or one" not in low:
            fails.append(f"[docs] {name} must preserve the one-subagent default")
        if "approval" not in low:
            fails.append(f"[docs] {name} must require approval before wider fanout")

    packet_sources = ("orchestrator.md", "loop-tiers.md", "claude-md-template.md", "roles.md")
    for name in packet_sources:
        low = surfaces[name].lower()
        if "3-8" not in low or "500" not in low or "full state" not in low or "activity" not in low:
            fails.append(f"[packet] {name} must define tiny packets and ban full state/activity context")

    skill = _read("SKILL.md").lower()
    if "available:" not in skill or "not running" not in skill:
        fails.append("[board] SKILL.md board example must show dormant specialists as available, not queued")
    if "who's active plus any approved queued worker" not in skill:
        fails.append("[board] SKILL.md must not tell the model to queue the whole catalog")

    if fails:
        print(f"FAIL: agent-activation {len(fails)} case(s):")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("PASS: agent-activation (catalog-not-payroll + one-subagent default + tiny packets + board semantics)")


if __name__ == "__main__":
    main()
