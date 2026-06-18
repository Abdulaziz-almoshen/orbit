#!/usr/bin/env python3
"""
Reference self-prompting loop runner (model-agnostic).

Implements Daisy Hollman's read -> plan -> act -> evaluate -> update -> decide cycle
against loop.config.json. The ONLY model-specific code is dispatch(): wire it to your
orchestrator (e.g. Gemini). Everything else -- state, budgets, gates, stop conditions --
is portable and enforces the safety contract regardless of model.

This is a skeleton to adapt, not a finished product. The control flow, budget tracking,
gate checks, and stop conditions are real; the role execution (dispatch) and the concrete
gate evaluators are stubs marked TODO for you to wire to your code.

Usage:  python .orbit/loop.py --config .orbit/loop.config.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path


# --------------------------------------------------------------------------- config
def load_config(path: Path) -> dict:
    cfg = json.loads(path.read_text())
    return {k: v for k, v in cfg.items() if not k.startswith("_")}


@dataclass
class Budget:
    """Running tally of the run's spend, checked against hard_limits before each cycle."""
    tokens: int = 0
    cost_usd: float = 0.0
    started_at: float = field(default_factory=time.time)

    def runtime_s(self) -> float:
        return time.time() - self.started_at


# ------------------------------------------------------------------------ the seams
def dispatch(role: str, task: dict, context: str, cfg: dict) -> dict:
    """MODEL SEAM. Build the role's prompt from .orbit/roles/<role>.md + the relevant
    STATE.md slice + input artifact paths, call your orchestrator, return a structured
    result: {"ok": bool, "summary": str, "artifacts": [paths], "tokens": int,
             "cost_usd": float, "needs_human": str|None}.

    Wire this to Gemini (or anything). Keep token/cost accounting accurate so hard limits
    actually bite. The Claude Code adapter swaps this for a native subagent call."""
    raise NotImplementedError("Wire dispatch() to your orchestrator (Gemini).")


def evaluate_gates(cycle_output: dict, cfg: dict) -> dict:
    """Evaluate the eval gates against this cycle's output. Return
    {"input": bool, "quality": bool, "safety": bool, "reasons": {gate: str}}.
    Safety is a veto: a False safety gate can never be overridden by the loop.
    TODO: implement each check using your input-validation / quality / safety code."""
    gates = cfg.get("eval_gates", {})
    # Stubs -- replace with real checks. Default to False so an unimplemented gate fails
    # safe (blocks progress) rather than waving work through.
    return {"input": False, "quality": False, "safety": False,
            "reasons": {"input": "TODO", "quality": "TODO", "safety": "TODO"},
            "_gates_spec": gates}


# ------------------------------------------------------------------- event handlers
# Same events as the Claude Code hooks, in one portable place. Wire validation/notify.
def on_inputs_loaded(ctx):    ...  # run input-validation checks; fail input gate on problems
def on_output_produced(ctx):  ...  # trigger the quality gate
def on_milestone(ctx):        ...  # run safety checks; notify a human channel (never act)
def on_run_end(ctx):          ...  # snapshot STATE.md; emit one-line run summary


# ---------------------------------------------------------------------- state files
def read_state(cfg: dict) -> tuple[str, str]:
    """READ: the two memory files. A fresh process now knows everything it needs."""
    p = cfg["paths"]
    claude_md = Path(p["claude_md"]).read_text() if Path(p["claude_md"]).exists() else ""
    state = Path(p["state"]).read_text() if Path(p["state"]).exists() else ""
    return claude_md, state


def update_state(cfg: dict, cycle: int, action: str, eval_result: dict, decision: str):
    """UPDATE: append to the cycle log. (A real impl also overwrites the snapshot/queue;
    keep ONE writer -- the orchestrator -- to avoid races when roles run in parallel.)"""
    state_path = Path(cfg["paths"]["state"])
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    line = f"- {stamp} iter {cycle}: {action} -> {_g(eval_result)} -> {decision}\n"
    # Minimal append; adapt to your STATE.md structure (see references/state-template.md).
    with state_path.open("a") as f:
        f.write(line)


def _g(ev: dict) -> str:
    return "gates[" + ",".join(k for k in ("input", "quality", "safety") if ev.get(k)) + "]"


# ----------------------------------------------------------------- stop conditions
def hard_stop_reason(cfg: dict, budget: Budget, cycle: int, fail_streak: int) -> str | None:
    """The brake. Checked before every cycle. Returns a reason string to stop, or None."""
    hl = cfg["hard_limits"]
    if Path(cfg["paths"]["stop_sentinel"]).exists():
        return "stop sentinel present"
    if cycle > hl["max_iterations"]:
        return f"max_iterations ({hl['max_iterations']}) reached"
    if budget.tokens >= hl["token_budget"]["per_run"]:
        return f"per-run token budget ({hl['token_budget']['per_run']}) reached"
    if budget.cost_usd >= hl["cost_budget_usd"]["per_run"]:
        return f"per-run cost budget (${hl['cost_budget_usd']['per_run']}) reached"
    if budget.runtime_s() >= hl["max_runtime_seconds"]:
        return f"max_runtime ({hl['max_runtime_seconds']}s) reached"
    if fail_streak >= hl["gate_failure_streak"]:
        return f"gate failed {fail_streak} cycles in a row (thrashing)"
    return None


def needs_human(action: str, cfg: dict, amount_usd: float = 0.0) -> bool:
    """Approval checkpoint. FORBIDDEN actions never run; 'human' pauses; numbers gate by
    threshold. Default-deny: an unknown action is treated as needing a human."""
    rule = cfg["approval_checkpoints"].get(action, "human")
    if rule == "FORBIDDEN":
        raise PermissionError(f"Action '{action}' is FORBIDDEN by config and must never run.")
    if rule == "auto":
        return False
    if isinstance(rule, (int, float)):
        return amount_usd > rule
    return True  # "human" or unknown -> require approval


# ------------------------------------------------------------------------- the loop
def run(cfg: dict):
    budget = Budget()
    cycle = 1
    fail_streak = 0

    while True:
        # DECIDE (pre-check): does any hard limit say stop before we even start?
        reason = hard_stop_reason(cfg, budget, cycle, fail_streak)
        if reason:
            print(f"[STOP] {reason}")
            on_run_end({"cfg": cfg, "budget": budget, "reason": reason})
            return

        # READ
        claude_md, state = read_state(cfg)
        context = claude_md + "\n\n" + state

        # PLAN + ACT: the orchestrator decides the next action and delegates.
        # In a real impl the orchestrator role returns the plan; here we model one step.
        task = {"goal": cfg.get("run_goal", "")}
        result = dispatch("orchestrator", task, context, cfg)
        budget.tokens += result.get("tokens", 0)
        budget.cost_usd += result.get("cost_usd", 0.0)

        # Human checkpoint mid-cycle if the orchestrator proposed a gated action.
        if result.get("needs_human"):
            print(f"[PAUSE] human approval needed: {result['needs_human']}")
            on_run_end({"cfg": cfg, "budget": budget, "reason": "awaiting human"})
            return  # resume is a fresh invocation after the human acts

        # EVALUATE
        ev = evaluate_gates(result, cfg)
        passed = ev["input"] and ev["quality"] and ev["safety"]
        fail_streak = 0 if passed else fail_streak + 1

        # UPDATE
        decision = "done" if (passed and _goal_met(result, cfg)) else \
                   "continue" if passed else "fix-and-retry"
        update_state(cfg, cycle, result.get("summary", "(no summary)"), ev, decision)

        # DECIDE (post): explicit done?
        if decision == "done":
            print("[DONE] run goal met and quality gate passed.")
            on_run_end({"cfg": cfg, "budget": budget, "reason": "done"})
            return

        cycle += 1


def _goal_met(result: dict, cfg: dict) -> bool:
    """TODO: real check that STATE.md run_goal is satisfied. Conservative default: not yet."""
    return False


# ------------------------------------------------------------------------------ cli
def main():
    ap = argparse.ArgumentParser(description="Self-prompting loop runner")
    ap.add_argument("--config", default=".orbit/loop.config.json", type=Path)
    args = ap.parse_args()
    try:
        cfg = load_config(args.config)
    except FileNotFoundError:
        sys.exit(f"config not found: {args.config}")
    run(cfg)


if __name__ == "__main__":
    main()
