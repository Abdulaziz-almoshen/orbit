#!/usr/bin/env python3
"""
Tests that loop.config.json and the two enforcers (ralph_loop.sh + loop.py) agree — no limit is
"documented but inert", and no enforcer reads a key the config doesn't ship:

  1. every hard_limits key in the shipped config is one the code actually enforces (no inert knob),
     and every REQUIRED enforced key is present (nothing enforced-but-missing → silent default);
  2. every `read_cfg ['hard_limits'][...]` path in ralph_loop.sh resolves in the shipped config;
  3. loop.py hard_stop_reason() runs against the shipped config without a KeyError (its required
     keys all exist).

This is the check that would have caught `token_budget.per_cycle` shipping while nothing read it.

Run: python3 tests/test_config_consistency.py   (exit 0 = pass)
"""
import importlib.util
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "assets", "loop.config.json")
RALPH = os.path.join(ROOT, "assets", "ralph_loop.sh")

# The hard_limits the code enforces. (top-level key -> required sub-keys, or None for a leaf.)
ENFORCED = {
    "max_iterations": None,
    "max_runtime_seconds": None,
    "gate_failure_streak": None,
    "token_budget": {"per_run", "per_cycle"},          # both enforced (runner + loop.py)
    "cost_budget_usd": {"per_run", "per_cycle"},        # both enforced by the runner
}


def main():
    fails = []
    cfg = json.load(open(CONFIG))
    hl = cfg.get("hard_limits", {})

    # 1a. no inert knob: every shipped hard_limits key is enforced
    for k in hl:
        if k not in ENFORCED:
            fails.append(f"[1] hard_limits ships '{k}' but no enforcer reads it (inert config knob)")
    # 1b. every required enforced key is present
    for k, subs in ENFORCED.items():
        if k not in hl:
            fails.append(f"[1] hard_limits is missing enforced key '{k}' (would silently default)")
            continue
        for s in (subs or set()):
            if not isinstance(hl[k], dict) or s not in hl[k]:
                fails.append(f"[1] hard_limits['{k}'] is missing required sub-key '{s}'")

    # 2. every hard_limits path ralph_loop.sh reads must resolve in the shipped config
    ralph = open(RALPH).read()
    for top, sub in re.findall(r"\['hard_limits'\]\['([^']+)'\](?:\['([^']+)'\])?", ralph):
        node = hl.get(top)
        if node is None:
            fails.append(f"[2] ralph_loop.sh reads hard_limits['{top}'] — absent from the config")
        elif sub and (not isinstance(node, dict) or sub not in node):
            fails.append(f"[2] ralph_loop.sh reads hard_limits['{top}']['{sub}'] — absent from the config")

    # 3. loop.py hard_stop_reason must not KeyError on the shipped config
    spec = importlib.util.spec_from_file_location("loop", os.path.join(ROOT, "assets", "loop.py"))
    loop = importlib.util.module_from_spec(spec)
    sys.modules["loop"] = loop
    spec.loader.exec_module(loop)
    full = json.load(open(CONFIG))
    full.setdefault("paths", {}).setdefault("stop_sentinel", os.path.join(ROOT, "does-not-exist"))
    try:
        loop.hard_stop_reason(full, loop.Budget(), cycle=1, fail_streak=0)
    except KeyError as e:
        fails.append(f"[3] loop.py hard_stop_reason KeyError on shipped config: {e} (config/code drift)")

    if fails:
        print("FAIL: config consistency")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("PASS: config consistency (no inert knobs; runner + loop.py read only keys the config ships)")


if __name__ == "__main__":
    main()
