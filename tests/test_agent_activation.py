#!/usr/bin/env python3
"""
Agent activation policy (v0.55): substantial work has mandatory stage owners, run sequentially by
default. Approval widens concurrency; it never turns required capabilities into optional lenses.

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
    if cm.get("activation_model") != "mandatory_stage_owners":
        fails.append("[config] activation_model must be mandatory_stage_owners")
    if cm.get("max_concurrent_subagents_without_approval") != 1:
        fails.append("[config] default concurrency must be one")
    if cm.get("fanout_requires_approval") is not True:
        fails.append("[config] fanout_requires_approval must be true")
    if cm.get("packet_file_limit") != 8:
        fails.append("[config] packet_file_limit must be 8")
    if cm.get("packet_output_word_limit") != 500:
        fails.append("[config] packet_output_word_limit must be 500")

    contract = cfg.get("capability_enforcement", {})
    if contract.get("enabled") is not True or contract.get("mode") != "strict":
        fails.append("[config] strict capability enforcement must ship enabled")
    for role in ("product-discovery", "business-analyst", "market-researcher", "planner",
                 "safety-gate", "reviewer", "qa-engineer", "cpo", "reporter"):
        if role not in contract.get("required_for_substantial", []):
            fails.append(f"[config] required_for_substantial missing {role}")
    if "designer" not in contract.get("required_for_ui", []):
        fails.append("[config] UI work must require Designer")

    surfaces = {
        "route.py": _read("assets", "checks", "route.py"),
        "orchestrator.md": _read("assets", "claude-agents", "orchestrator.md"),
        "loop-tiers.md": _read("references", "playbooks", "loop-tiers.md"),
        "claude-md-template.md": _read("references", "claude-md-template.md"),
        "roles.md": _read("references", "roles.md"),
    }
    for name, text in surfaces.items():
        low = text.lower()
        if "mandatory" not in low and "required" not in low:
            fails.append(f"[docs] {name} must describe mandatory stage ownership")
        if "sequential" not in low and "one active" not in low:
            fails.append(f"[docs] {name} must preserve single-worker default concurrency")
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
    print("PASS: agent-activation (mandatory stage owners + sequential default + tiny packets + board semantics)")


if __name__ == "__main__":
    main()
