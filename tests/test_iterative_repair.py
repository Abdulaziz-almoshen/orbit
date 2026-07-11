#!/usr/bin/env python3
"""Iterative repair contract: evidence packets, bounded attempts, and provisioning."""
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
    iteration = cfg.get("iteration", {})
    for key in ("enabled", "max_repair_attempts", "repair_reserve_usd", "max_failure_packet_bytes",
                "repeat_failure_action"):
        if key not in iteration:
            fails.append(f"[config] missing iteration.{key}")
    repair = load("repair", "assets/repair.py")
    packet = {
        "schema": 1, "id": "REV-004", "cycle": 2, "attempt": 1,
        "source": "reviewer", "severity": "P1", "criterion": "AC-3",
        "evidence": "tests/test_booking.py:81 reproduces duplicate booking",
        "failure": "duplicate booking is accepted",
        "root_cause": "uniqueness check runs after the write",
        "required_change": "validate the booking key before persistence",
        "verification": ["pytest tests/test_booking.py -q", "repeat the duplicate request"],
        "owner": "builder", "max_attempts": 2, "status": "queued",
    }
    if repair.validate(packet, cfg):
        fails.append("[valid] a complete repair packet must validate")
    if repair.next_action(packet, cfg) != "repair":
        fails.append("[state] queued first attempt must route to repair")
    if repair.next_action(dict(packet, attempt=2), cfg) != "repair":
        fails.append("[state] second attempt is still allowed, once")
    if repair.next_action(dict(packet, attempt=3), cfg) != "escalate":
        fails.append("[state] repeated failure must escalate")
    if repair.next_action(dict(packet, status="passed"), cfg) != "retest-regression":
        fails.append("[state] passed repair must require regression retest")
    missing = dict(packet)
    del missing["evidence"]
    if not repair.validate(missing, cfg):
        fails.append("[safety] evidence-less repair packet must fail")

    scaffold = load("scaffold_repair", "scripts/scaffold.py")
    if not any(src == "repair.py" and dst == ".orbit/repair.py" for src, dst, _ in scaffold.FILE_PLAN):
        fails.append("[scaffold] repair validator is not provisioned")
    if "iterative-repair.md" not in scaffold.PLAYBOOKS_ALWAYS:
        fails.append("[scaffold] repair playbook is not provisioned")
    orch = open(os.path.join(ROOT, "assets", "claude-agents", "orchestrator.md")).read().lower()
    if "repair-<id>.json" not in orch or "same failure" not in orch:
        fails.append("[orchestrator] must require packets and repeated-failure escalation")

    if fails:
        print(f"FAIL: iterative-repair {len(fails)} case(s):")
        for f in fails:
            print("  -", f)
        raise SystemExit(1)
    print("PASS: iterative-repair (evidence packet + bounded attempts + regression retest + provisioning)")


if __name__ == "__main__":
    main()
