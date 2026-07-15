#!/usr/bin/env python3
"""
Tests loop.py durability + approval enforcement (honesty-pass claims 4.2 / 4.7):
 - Steps() survives a truncated final checkpoint line (crash/OOM mid-append) instead of crashing.
 - Budget checkpoints persist and reload, so --resume doesn't reset per-run caps to zero.
 - needs_human() actually enforces the config: FORBIDDEN raises, "human" gates, "auto" allows.

Run: python3 tests/test_loop.py   (exit 0 = pass)
"""
import importlib.util
import json
import os
import sys
import tempfile

spec = importlib.util.spec_from_file_location(
    "loop", os.path.join(os.path.dirname(__file__), "..", "assets", "loop.py"))
loop = importlib.util.module_from_spec(spec)
sys.modules["loop"] = loop            # dataclass in loop.py needs the module registered first
spec.loader.exec_module(loop)


def main():
    fails = []

    # 1. Steps tolerates a truncated final line
    with tempfile.TemporaryDirectory() as d:
        p = loop.Path(os.path.join(d, "steps.jsonl"))
        p.write_text(
            json.dumps({"name": "c1:act", "output": {"ok": True}, "status": "done"}) + "\n"
            + '{"name": "c2:act", "output": {"ok"' )  # truncated last line (no newline)
        try:
            s = loop.Steps(p)
        except Exception as e:
            fails.append(f"Steps crashed on truncated line: {e}")
        else:
            if "c1:act" not in s.done:
                fails.append("Steps dropped the valid checkpoint")
            if "c2:act" in s.done:
                fails.append("Steps kept the truncated (uncheckpointed) step")

    # 2. Budget persists + reloads
    with tempfile.TemporaryDirectory() as d:
        p = loop.Path(os.path.join(d, "steps.jsonl"))
        s = loop.Steps(p)
        b = loop.Budget()
        b.tokens, b.cost_usd = 12345, 0.42
        s.save_budget(b, cycle=3)
        s2 = loop.Steps(p)  # simulate a restart
        if not s2.last_budget or s2.last_budget.get("tokens") != 12345:
            fails.append(f"budget did not persist/reload: {s2.last_budget}")

    # 3. needs_human enforces config
    cfg = {"approval_checkpoints": {"move_money": "FORBIDDEN", "deploy": "human",
                                    "write_file": "auto", "spend": 5}}
    try:
        loop.needs_human("move_money", cfg)
        fails.append("FORBIDDEN action did not raise")
    except PermissionError:
        pass
    if loop.needs_human("deploy", cfg) is not True:
        fails.append("'human' action should require approval")
    if loop.needs_human("write_file", cfg) is not False:
        fails.append("'auto' action should not require approval")
    if loop.needs_human("spend", cfg, amount_usd=10) is not True:
        fails.append("threshold gate should fire above the amount")
    if loop.needs_human("spend", cfg, amount_usd=1) is not False:
        fails.append("threshold gate should pass below the amount")
    if loop.needs_human("unknown_action", cfg) is not True:
        fails.append("unknown action should default to requiring a human")

    # 3b. Independent QA is a first-class lifecycle gate, opt-in and fail-closed when enabled.
    if not loop.evaluate_independent_qa({}, {}).get("passed"):
        fails.append("disabled independent QA should be a no-op")
    missing = loop.evaluate_independent_qa({}, {"independent_qa": {"enabled": True}})
    if missing.get("passed") or missing.get("status") != "missing_input":
        fails.append(f"enabled independent QA did not fail closed on missing commit/request: {missing}")
    with tempfile.TemporaryDirectory() as d:
        runner = os.path.join(d, "orbit-independent-qa")
        with open(runner, "w") as f:
            f.write("import json\nprint(json.dumps({'passed': True, 'status': 'pass', 'reason': 'approved'}))\n")
        result = loop.evaluate_independent_qa(
            {"commit": "abc", "independent_qa_request": "request.json"},
            {"independent_qa": {"enabled": True}, "paths": {"independent_qa_runner": runner}})
        if not result.get("passed"):
            fails.append(f"independent QA lifecycle adapter did not pass provider result: {result}")

    # 4. --resume must NOT double-count budget, and must continue the cycle counter (not reset to 1)
    with tempfile.TemporaryDirectory() as d:
        ckpt = os.path.join(d, "steps.jsonl")
        cfg = {
            "hard_limits": {"max_iterations": 2, "token_budget": {"per_run": 10_000_000, "per_cycle": 0},
                            "cost_budget_usd": {"per_run": 1e9}, "max_runtime_seconds": 1e9,
                            "gate_failure_streak": 99},
            "paths": {"stop_sentinel": os.path.join(d, "STOP"), "state": os.path.join(d, "STATE.md"),
                      "claude_md": os.path.join(d, "CLAUDE.md"), "checkpoints": ckpt},
            "approval_checkpoints": {}, "eval_gates": {}, "run_goal": "x",
        }
        loop.dispatch = lambda *a, **k: {"summary": "ok", "tokens": 100, "cost_usd": 1.0}
        loop.evaluate_gates = lambda *a, **k: {"input": True, "quality": True, "safety": True, "reasons": {}}
        loop.run(cfg, resume=False)                       # runs 2 cycles → 200 tokens
        after_first = loop.Steps(loop.Path(ckpt)).last_budget
        if not after_first or after_first.get("tokens") != 200:
            fails.append(f"first run should spend 200 tokens over 2 cycles, got {after_first}")
        loop.run(cfg, resume=True)                          # must NOT re-add the cached cycles
        after_resume = loop.Steps(loop.Path(ckpt)).last_budget
        if after_resume and after_resume.get("tokens") != 200:
            fails.append(f"--resume double-counted budget: expected 200, got {after_resume.get('tokens')}")

    if fails:
        print("FAIL: loop")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("PASS: loop (truncated-line resilience + budget persistence + approval enforcement + "
          "resume no-double-count)")


if __name__ == "__main__":
    main()
