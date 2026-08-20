#!/usr/bin/env python3
"""Regression tests for the per-goal token budget allocator."""
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    path = ROOT / "assets/checks/token_budget.py"
    spec = importlib.util.spec_from_file_location("orbit_token_budget", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["orbit_token_budget"] = mod
    spec.loader.exec_module(mod)
    return mod


def _project(td: Path) -> Path:
    orbit = td / ".orbit"
    orbit.mkdir(parents=True)
    (orbit / "loop.config.json").write_text(
        (ROOT / "assets/loop.config.json").read_text())
    return orbit


def main() -> int:
    tb = _load()
    failures = []
    with tempfile.TemporaryDirectory() as td:
        orbit = _project(Path(td))

        # --- gear scaling: a smaller gear gets a smaller pot -------------------------------
        t1 = tb.plan(orbit, "T1", ["planner", "reviewer", "qa-engineer", "reporter"], "small fix")
        t3 = tb.plan(orbit, "T3", ["planner", "builder", "reviewer"], "big initiative")
        if not (t1["total"] == 25000 and t3["total"] == 140000):
            failures.append(f"per_gear totals wrong: T1={t1['total']} T3={t3['total']}")

        # --- renormalization: the running roles split the whole spendable pot ---------------
        tb.plan(orbit, "T1", ["planner", "reviewer", "qa-engineer", "reporter"], "small fix")
        led = tb.load(orbit)
        spendable = led["total"] - led["reserve"]
        allocated = sum(led["allocations"].values())
        if abs(allocated - spendable) > 5:                 # rounding slack only
            failures.append(f"allocations {allocated} do not fill spendable {spendable}")
        if led["reserve"] != 3750:
            failures.append(f"reserve should be 15% of 25000 = 3750, got {led['reserve']}")

        # --- every label is governed; arbitrary high labels saturate at hard T4 --------------
        t4 = tb.plan(orbit, "T4", ["planner", "builder"], "mission")
        if t4["total"] != 240000 or tb.plan(orbit, "T100", ["planner"], "mission")["gear"] != "T4":
            failures.append("T4/T100 must share the 240k hard ceiling")
        if tb.check(orbit, "planner", 10**9)["decision"] != "deny":
            failures.append("the hard global ceiling must deny an impossible dispatch")

        # --- the degrade ladder escalates with the size of the overrun ---------------------
        tb.plan(orbit, "T1", ["planner", "reviewer", "qa-engineer", "reporter"], "small fix")
        led = tb.load(orbit)
        left = tb.remaining(led, "reporter")
        rungs = {
            "small": tb.check(orbit, "reporter", left + 10)["action"],
            "medium": tb.check(orbit, "reporter", int(left * 2.5))["action"],
            "huge": tb.check(orbit, "reporter", left * 100)["action"],
        }
        if rungs["small"] != "trim_packet":
            failures.append(f"a small overrun should trim, got {rungs['small']}")
        if rungs["medium"] != "downgrade_model":
            failures.append(f"a medium overrun should downgrade, got {rungs['medium']}")
        if rungs["huge"] not in ("budget_pause_with_checkpoint", "budget_pause"):
            failures.append(f"a huge overrun should pause with a checkpoint, got {rungs['huge']}")
        if tb.check(orbit, "planner", 100)["decision"] != "allow":
            failures.append("a dispatch that fits must be allowed")

        # --- spend drains the reserve only for the overrun portion -------------------------
        alloc = tb.load(orbit)["allocations"]["planner"]
        tb.spend(orbit, "planner", alloc + 500)
        led = tb.load(orbit)
        if led["reserve_used"] != 500:
            failures.append(f"reserve_used should be exactly the overrun 500, got {led['reserve_used']}")

        # --- a waiver is recorded where the CPO gate can see it ----------------------------
        tb.record_degrade(orbit, "reporter", "waive_role_with_record", "out of budget")
        led = tb.load(orbit)
        if "reporter" not in led.get("waived", []):
            failures.append("a waived role must land in `waived` for the CPO gate")
        if not led.get("degrades"):
            failures.append("degrades must be logged")

        # --- the countdown stays silent until warn_at, then speaks ------------------------
        tb.plan(orbit, "T2", ["planner", "builder", "reviewer"], "standard")
        quiet = tb.packet_note(tb.load(orbit), "builder")
        if quiet:
            failures.append("packet_note must be silent below warn_at (premature wrap-up risk)")
        alloc = tb.load(orbit)["allocations"]["builder"]
        tb.spend(orbit, "builder", int(alloc * 0.8))
        loud = tb.packet_note(tb.load(orbit), "builder")
        if "TOKEN BUDGET" not in loud:
            failures.append("packet_note must surface the countdown past warn_at")

        # --- an unknown role still gets a share rather than zero ---------------------------
        tb.plan(orbit, "T2", ["planner", "some-custom-role"], "custom")
        if not tb.load(orbit)["allocations"].get("some-custom-role"):
            failures.append("an unlisted role must still receive a default allocation")

        # --- no ledger → deny, never run unmetered -----------------------------------------
        with tempfile.TemporaryDirectory() as td2:
            empty = Path(td2) / ".orbit"
            empty.mkdir()
            if tb.check(empty, "planner", 999999)["decision"] != "deny":
                failures.append("a missing ledger must fail closed")

        # --- estimator is monotonic and non-zero ------------------------------------------
        if not (tb.estimate_tokens("x" * 400) > tb.estimate_tokens("x" * 100) > 0):
            failures.append("estimate_tokens must grow with input")

        # --- goal sizing happens before execution and explicit ceilings remain governed ----
        sized = {
            "small": tb.size_goal("fix the button copy")["gear"],
            "deep": tb.size_goal("implement frontend and backend provisioning architecture across every dependency")["gear"],
            "mission": tb.size_goal("production migration across repos with billing and compliance")["gear"],
            "explicit": tb.size_goal("run this as T100")["gear"],
        }
        if sized != {"small": "T1", "deep": "T3", "mission": "T4", "explicit": "T4"}:
            failures.append(f"deterministic goal preflight sized incorrectly: {sized}")

        # --- measured pressure can raise the envelope, never reset it or cross T4 ------------
        ledger = tb.plan(orbit, "T1", ["planner", "reviewer", "qa-engineer", "reporter"],
                         "finish the immutable goal")
        ledger["session_id"] = "session-1"; ledger["agent_calls"] = 4
        tb._write(orbit, ledger)
        original_hash = ledger["goal_hash"]
        expanded = tb.reconsider(orbit, "planner", 7000, "agent-call ceiling", require_call_slot=True)
        after = tb.load(orbit)
        if expanded.get("decision") != "allow" or after.get("gear") != "T2":
            failures.append(f"T1 pressure did not auto-expand exactly to T2: {expanded}")
        if after.get("goal_hash") != original_hash or after.get("session_id") != "session-1":
            failures.append("automatic reconsideration reset the goal or session")
        if not after.get("reconsiderations") or after["reconsiderations"][-1].get("goal_preserved") is not True:
            failures.append("automatic reconsideration was not auditable as goal-preserving")

        tb.plan(orbit, "T4", ["planner"], "hard-ceiling goal")
        stopped = tb.reconsider(orbit, "planner", 10**9, "impossible estimate")
        if stopped.get("decision") != "deny" or stopped.get("gear") != "T4":
            failures.append("T4 must remain the absolute automatic-reconsideration ceiling")

    if failures:
        print("FAIL: token budget")
        for f in failures:
            print("  -", f)
        return 1
    print("PASS: token budget (intake sizing · automatic reconsideration · hard T4 · reserve · countdown)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
