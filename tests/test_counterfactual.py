#!/usr/bin/env python3
"""Counterfactual Regret Gate contract: bounded packets, safe routes, and provisioning."""
import importlib.util
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main():
    fails = []
    cfg = json.load(open(os.path.join(ROOT, "assets", "loop.config.json")))
    cf = cfg.get("counterfactual", {})
    for key in ("enabled", "minimum_gear", "max_hypotheses", "max_probe_words", "max_packet_bytes",
                "failure_routes"):
        if key not in cf:
            fails.append(f"[config] missing counterfactual.{key}")
    gate = load("counterfactual", "assets/counterfactual.py")
    packet = {
        "schema": 1, "cycle": 2, "decision": "use reply speed",
        "assumption": "reply speed predicts readiness",
        "hypotheses": [{"failure": "slow serious users", "signal": "won leads reply later",
                        "probe": "compare won/lost reply delays"}],
        "selected_probe": "compare won/lost reply delays",
        "outcome": "pending", "backtrack": "none",
    }
    if gate.validate(packet, cfg):
        fails.append("[valid] a compact pending packet must validate")
    for outcome in ("pass", "fail", "inconclusive"):
        p = dict(packet, outcome=outcome)
        if gate.validate(p, cfg):
            fails.append(f"[state] {outcome} packet must validate")
    too_many = dict(packet, hypotheses=[packet["hypotheses"][0]] * 4)
    if not gate.validate(too_many, cfg):
        fails.append("[limit] more than max_hypotheses must fail")
    if gate.route_failure("wrong_assumption", cfg) != "discovery":
        fails.append("[route] wrong assumption must return to discovery")
    if gate.route_failure("architecture_risk", cfg) != "plan":
        fails.append("[route] architecture risk must return to plan")
    if gate.route_failure("unknown_failure", cfg) != "discovery":
        fails.append("[route] unknown failure must fail safe to discovery")

    scaffold = load("scaffold_counterfactual", "scripts/scaffold.py")
    if not any(src == "counterfactual.py" and dst == ".orbit/counterfactual.py"
               for src, dst, _ in scaffold.FILE_PLAN):
        fails.append("[scaffold] counterfactual validator is not provisioned")
    if "counterfactual-regret.md" not in scaffold.PLAYBOOKS_ALWAYS:
        fails.append("[scaffold] counterfactual playbook is not provisioned")
    orch = open(os.path.join(ROOT, "assets", "claude-agents", "orchestrator.md")).read().lower()
    if "counterfactual regret gate" not in orch or "typed phase" not in orch:
        fails.append("[orchestrator] must require the gate and typed backtracking")
    ralph = open(os.path.join(ROOT, "assets", "ralph_loop.sh")).read().lower()
    if "counterfactual" not in ralph or "falsification probe" not in ralph:
        fails.append("[ralph] must require the preflight before ACT")
    run_cmd = open(os.path.join(ROOT, "commands", "orbit-run.md")).read().lower()
    if "counterfactual preflight" not in run_cmd or ".orbit/counterfactual.py" not in run_cmd:
        fails.append("[orbit-run] must expose the preflight and validator")

    if fails:
        print(f"FAIL: counterfactual {len(fails)} case(s):")
        for f in fails:
            print("  -", f)
        raise SystemExit(1)
    print("PASS: counterfactual (bounded packet + safe routing + scaffold/orchestrator contract)")


if __name__ == "__main__":
    main()
