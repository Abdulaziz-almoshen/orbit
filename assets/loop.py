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
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# Observability: emit "who's talking" events + drive the live checklist. activity.py sits
# next to this file (both scaffolded into .orbit/). If it's missing, degrade to no-ops so
# the loop still runs — observability never breaks the loop.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from activity import emit, set_tasks, update_task  # noqa: F401
except Exception:
    def emit(*a, **k): pass
    def set_tasks(*a, **k): pass
    def update_task(*a, **k): pass


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


class Steps:
    """Durable step memo (portable-path durability).

    Each named step runs AT MOST ONCE: its result is checkpointed to disk, so a restart
    (crash, deploy, OOM) resumes from the last completed step instead of re-running — and
    re-paying for — fetches, LLM calls, and side effects. This is what turns a `while True`
    into something that survives a restart. It mirrors a durable orchestrator's `step.run()`
    semantics for the portable path; for production, run the loop on a real engine
    (Inngest/Temporal/Workflow) instead of this file — see references/durable-execution.md.

    Wrap exactly the things you don't want to repeat on resume: external fetches, model
    calls, and side effects (so a restart doesn't double-send). Don't wrap "read current
    state" — you want that fresh each cycle. Step outputs must be JSON-serializable."""

    def __init__(self, path: Path):
        self.path = path
        self.done: dict = {}
        self.last_budget: dict | None = None
        if path.exists():
            for line in path.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue  # a truncated final line (crash/OOM mid-append) is uncheckpointed — skip it
                if "__budget__" in r:                 # a budget checkpoint (see save_budget)
                    self.last_budget = r["__budget__"]
                elif "name" in r:
                    self.done[r["name"]] = r

    def save_budget(self, budget, cycle: int):
        """Persist the running spend so --resume doesn't reset the per-run budget to zero."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(json.dumps({"__budget__": {
                "tokens": budget.tokens, "cost_usd": budget.cost_usd, "cycle": cycle}}) + "\n")

    def run(self, name: str, fn):
        if name in self.done:                       # already completed on an earlier run —
            return self.done[name]["output"]        # skip and return the checkpointed result
        t0 = time.time()
        output = fn()
        rec = {"name": name, "output": output, "status": "done",
               "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "duration_ms": int((time.time() - t0) * 1000)}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:              # append = the checkpoint (trace too)
            f.write(json.dumps(rec) + "\n")
        self.done[name] = rec
        emit("step", "", "done", f"{name} ({rec['duration_ms']}ms)")
        return output


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


# The stable per-cycle step contract. Durability + observability both key off these names: the ACT and
# EVALUATE steps are checkpointed (see Steps), so a crash resumes at the next step, not the last one.
STEP_CONTRACT = ("read", "plan", "act", "evaluate", "update", "decide")


class Idempotency:
    """Business-key idempotency for SIDE EFFECTS (deploy, external message, payment). A key fires AT MOST
    ONCE — across resumes AND separate runs — unless explicitly forced. This is stronger than the per-run
    step memo (Steps), which is keyed on a cycle-scoped step NAME: use a STABLE BUSINESS key here, e.g.
    'deploy:v1.2.3' or 'notify:invoice-4471', so the effect can't repeat even in a brand-new run.

    Adapter usage inside dispatch():  idem.run('deploy:v1.2.3', lambda: really_deploy())"""

    def __init__(self, path: Path):
        self.path = path
        self.used = _read_json(path, {}) if path.exists() else {}

    def seen(self, key: str) -> bool:
        return key in self.used

    def run(self, key: str, fn, force: bool = False):
        if key in self.used and not force:
            return self.used[key].get("output")     # already performed → do NOT repeat the side effect
        out = fn()
        try:
            json.dumps(out)
            stored = out
        except (TypeError, ValueError):
            stored = str(out)
        self.used[key] = {"at": _now(), "output": stored, "forced": bool(force and key in self.used)}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.used, indent=2))
        return out


class Approvals:
    """Durable human-approval waits. When the loop needs a human for a gated action it records a PENDING
    request and STOPS; a human grants it out-of-band (`loop.py --approve <action>`); on --resume the loop
    finds the grant and proceeds PAST the checkpoint instead of pausing on the same gate forever. Grants
    are per (action, cycle) so each occurrence needs its own approval — a later cycle re-asks."""

    def __init__(self, root: Path):
        self.root = root
        self.pending = root / "pending.json"
        self.granted = root / "granted.jsonl"

    def _grants(self) -> set:
        out = set()
        if self.granted.exists():
            for ln in self.granted.read_text().splitlines():
                try:
                    out.add(json.loads(ln)["key"])
                except Exception:
                    pass
        return out

    def is_granted(self, action: str, cycle: int) -> bool:
        return f"{action}:{cycle}" in self._grants()

    def request(self, action: str, cycle: int) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.pending.write_text(json.dumps(
            {"action": action, "cycle": cycle, "key": f"{action}:{cycle}", "requested_at": _now()}, indent=2))

    def grant(self, action: str = "", cycle: int | None = None) -> str:
        """Grant the CURRENT pending request (action/cycle inferred) or a specific action:cycle pair."""
        self.root.mkdir(parents=True, exist_ok=True)
        if cycle is None and self.pending.exists():
            p = _read_json(self.pending, {})
            action = action or p.get("action", "")
            cycle = p.get("cycle", 1)
        key = f"{action}:{cycle if cycle is not None else 1}"
        with self.granted.open("a") as f:
            f.write(json.dumps({"key": key, "at": _now()}) + "\n")
        return key


# ------------------------------------------------------------------------ the seams
def dispatch(role: str, task: dict, context: str, cfg: dict) -> dict:
    """MODEL SEAM. Build the role's prompt from .orbit/roles/<role>.md + the relevant
    STATE.md slice + input artifact paths, call your orchestrator, return a structured
    result: {"ok": bool, "summary": str, "artifacts": [paths], "tokens": int,
             "cost_usd": float, "needs_human": str|None}.

    Wire this to Gemini (or anything). Keep token/cost accounting accurate so hard limits
    actually bite. The Claude Code adapter swaps this for a native subagent call."""
    # [STUB] Not wired. This raises until you connect your orchestrator. Until then the
    # portable runner does nothing — the Claude Code path (subagents) is what works today.
    raise NotImplementedError("Wire dispatch() to your orchestrator (e.g. Gemini).")


def model_lane(role: str, cfg: dict) -> dict:
    """Return the configured model lane for a role. The portable runner is model-agnostic, but
    adapters should use this to keep the cheap Executor / on-demand Advisor split consistent."""
    policy = cfg.get("model_policy", {}) or {}
    if role == "advisor":
        return policy.get("advisor", policy.get("executor", {}))
    return policy.get("executor", {})


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


def evaluate_independent_qa(cycle_output: dict, cfg: dict) -> dict:
    """Run the opt-in, separately configured reviewer against an exact commit."""
    qa = cfg.get("independent_qa", {}) or {}
    if qa.get("enabled") is not True:
        return {"passed": True, "status": "disabled", "reason": "independent QA is opt-in"}
    request = cycle_output.get("independent_qa_request")
    commit = cycle_output.get("commit")
    if not request or not commit:
        return {"passed": False, "status": "missing_input",
                "reason": "enabled independent QA requires result.commit and result.independent_qa_request"}
    runner = Path(cfg.get("paths", {}).get("independent_qa_runner", "scripts/orbit-independent-qa"))
    command = [sys.executable, str(runner), "review", "--request", str(request), "--commit", str(commit)]
    proc = subprocess.run(command, text=True, capture_output=True)
    raw = proc.stdout if proc.stdout.strip() else proc.stderr
    try:
        status = json.loads(raw)
    except Exception:
        status = {"passed": False, "status": "error", "reason": raw[-2000:] or "review runner failed"}
    status["passed"] = bool(proc.returncode == 0 and status.get("passed"))
    return status


def evaluate_cpo_acceptance(cycle_output: dict, cfg: dict) -> dict:
    """The CPO gate AFTER QA: the run is not done until a commit-bound verdict envelope in
    .orbit/cpo/ says ACCEPT. QA proves the work was built right; the CPO verdict is the recorded
    judgment that the RIGHT thing was built (deliverable vs the user's goal). The CPO subagent
    writes the envelope (see .orbit/skills/product-acceptance.md); this gate only enforces it."""
    cpo = cfg.get("cpo_acceptance", {}) or {}
    if cpo.get("enabled") is not True:
        return {"passed": True, "status": "disabled", "reason": "CPO acceptance is not enabled"}
    commit = cycle_output.get("commit")
    if not commit:
        return {"passed": False, "status": "missing_input",
                "reason": "enabled CPO acceptance requires result.commit (verdicts are commit-bound)"}
    vdir = Path(cfg.get("paths", {}).get("cpo_verdicts", ".orbit/cpo"))
    rounds = sorted(vdir.glob("round-*.json"), key=lambda p: p.stat().st_mtime) if vdir.is_dir() else []
    if not rounds:
        return {"passed": False, "status": "pending",
                "reason": "CPO acceptance pending — dispatch the cpo subagent to judge the "
                          "deliverable against the user's goal and write .orbit/cpo/round-<n>.json"}
    try:
        verdict = json.loads(rounds[-1].read_text())
    except Exception:
        return {"passed": False, "status": "error",
                "reason": f"unreadable CPO verdict envelope: {rounds[-1].name}"}
    if str(verdict.get("commit", "")) != str(commit):
        return {"passed": False, "status": "stale",
                "reason": f"newest CPO verdict is for commit {str(verdict.get('commit'))[:8]!r}, "
                          f"not the cycle's {str(commit)[:8]!r} — re-run the cpo subagent"}
    v = str(verdict.get("verdict", "")).upper()
    if v == "ACCEPT":
        # A grounded gate, not a mood: ACCEPT must cite the accumulated skills it rests on —
        # or, on a brand-new project with empty skills, show the first signals being written.
        basis = verdict.get("basis") if isinstance(verdict.get("basis"), dict) else {}
        cited = [s for s in (basis.get("skills") or []) if str(s).strip()]
        seeded = [s for s in (verdict.get("user_model_updates") or []) if str(s).strip()]
        if not cited and not seeded:
            return {"passed": False, "status": "ungrounded",
                    "reason": "ACCEPT without basis — the verdict must cite the skills it rests on "
                              "(basis.skills), or on a fresh project record its first user-model "
                              "updates. Re-run the cpo subagent per .orbit/skills/product-acceptance.md"}
        return {"passed": True, "status": "accepted", "verdict": v,
                "reason": f"CPO accepted commit {str(commit)[:8]} against the goal "
                          f"({len(cited)} skill citation(s))"}
    orders = verdict.get("change_orders") or []
    top = next((o.get("order", "") for o in orders if isinstance(o, dict)), "")
    return {"passed": False, "status": v.lower() or "rejected", "verdict": v,
            "reason": f"CPO returned the deliverable ({v or 'no verdict'})"
                      + (f" — top change order: {top}" if top else "")}


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
    return "gates[" + ",".join(k for k in ("input", "quality", "safety", "independent_qa", "cpo") if ev.get(k)) + "]"


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
    threshold. Default-deny: an unknown action is treated as needing a human.

    NOTE: this is APPLICATION-level enforcement — it only fires when the loop calls it, so
    it covers the portable/Gemini path. It does NOT bind a direct tool call made outside the
    loop. On the Claude Code path, install the always-on PreToolUse hook (.orbit/checks/guard.py,
    skill Phase 6a) so the non-negotiables hold even when no loop is running."""
    rule = cfg["approval_checkpoints"].get(action, "human")
    if rule == "FORBIDDEN":
        raise PermissionError(f"Action '{action}' is FORBIDDEN by config and must never run.")
    if rule == "auto":
        return False
    if isinstance(rule, (int, float)):
        return amount_usd > rule
    return True  # "human" or unknown -> require approval


# ------------------------------------------------------------------------- the loop
def run(cfg: dict, resume: bool = False):
    budget = Budget()
    cycle = 1
    fail_streak = 0

    # Durable checkpoints: a fresh run starts clean; --resume keeps the prior checkpoints so
    # completed steps are skipped (no re-fetch, no re-charged model calls, no double side
    # effects). On a production engine this is the orchestrator's job; here it's a file.
    ckpt = Path(cfg["paths"].get("checkpoints", ".orbit/steps.jsonl"))
    if not resume and ckpt.exists():
        ckpt.unlink()
    steps = Steps(ckpt)
    resumed = set(steps.done)                        # steps already completed BEFORE this run
    _orbit = ckpt.parent                             # durable approval waits + side-effect idempotency
    approvals = Approvals(_orbit / "approvals")
    idem = Idempotency(_orbit / "idempotency.json")
    if resume and steps.last_budget:                 # restore spend + cycle so per-run caps + the
        budget.tokens = steps.last_budget.get("tokens", 0)     # iteration counter survive a restart
        budget.cost_usd = steps.last_budget.get("cost_usd", 0.0)
        cycle = int(steps.last_budget.get("cycle", 1))          # don't reset to 1 (would re-count)

    while True:
        # DECIDE (pre-check): does any hard limit say stop before we even start?
        reason = hard_stop_reason(cfg, budget, cycle, fail_streak)
        if reason:
            emit("orchestrator", "decide", "blocked", f"STOP — {reason}", cycle=cycle)
            on_run_end({"cfg": cfg, "budget": budget, "reason": reason})
            return

        # READ — a fresh agent learns where things stand from the files alone.
        emit("orchestrator", "read", "start", "reading CLAUDE.md + STATE.md", cycle=cycle)
        claude_md, state = read_state(cfg)
        context = claude_md + "\n\n" + state

        # PLAN + ACT: the orchestrator decides the next action and delegates. A real impl
        # plans a task list (set_tasks) and dispatches each item to its owning role,
        # emitting start/done around every dispatch so the live view shows who's talking.
        emit("orchestrator", "plan", "info", "planning next action", cycle=cycle)
        task = {"goal": cfg.get("run_goal", ""), "model_lane": model_lane("orchestrator", cfg)}
        emit("orchestrator", "act", "start", "delegating to specialist(s)", cycle=cycle)
        # Checkpointed: on resume, a completed act is NOT re-dispatched (no re-charged model
        # call, no duplicate side effect) — its result is read back from the checkpoint.
        act_name = f"c{cycle}:act"
        result = steps.run(act_name, lambda: dispatch("orchestrator", task, context, cfg))
        emit("orchestrator", "act", "done", result.get("summary", "(no summary)"), cycle=cycle)
        if act_name not in resumed:                  # only meter a FRESH dispatch — a cycle restored
            spent = int(result.get("tokens", 0) or 0)   # from the checkpoint is already in the
            budget.tokens += spent                      # restored budget, so re-adding double-counts
            budget.cost_usd += float(result.get("cost_usd", 0.0) or 0.0)
            steps.save_budget(budget, cycle)         # persist spend so --resume can't reset caps to zero
            # per-CYCLE budget: a single cycle blowing its cap is a runaway signal — stop the loop.
            per_cycle = cfg["hard_limits"].get("token_budget", {}).get("per_cycle", 0)
            if per_cycle and spent >= per_cycle:
                reason = f"cycle {cycle} exceeded per-cycle token budget ({per_cycle}) — used {spent}"
                emit("orchestrator", "decide", "blocked", f"STOP — {reason}", cycle=cycle)
                on_run_end({"cfg": cfg, "budget": budget, "reason": reason})
                return

        # Approval enforcement: a tagged side-effect action is gated by config. FORBIDDEN never
        # runs (loop stops); "human"/threshold pauses for approval. This is the point that makes
        # loop.config.json's approval_checkpoints actually bind on the runner path.
        action_tag = result.get("action")
        if action_tag:
            try:
                gated = needs_human(action_tag, cfg, result.get("cost_usd", 0.0))
            except PermissionError as e:
                emit("safety", "evaluate", "blocked", str(e), cycle=cycle)
                on_run_end({"cfg": cfg, "budget": budget, "reason": f"FORBIDDEN: {action_tag}"})
                return
            if gated and not approvals.is_granted(action_tag, cycle):
                approvals.request(action_tag, cycle)     # DURABLE wait: record the request and stop
                emit("human", "decide", "blocked",
                     f"awaiting approval: {action_tag} — grant with "
                     f"`python .orbit/loop.py --approve {action_tag}` then --resume", cycle=cycle)
                on_run_end({"cfg": cfg, "budget": budget, "reason": "awaiting human"})
                return
            if gated:                                    # granted (on --resume) → proceed AT MOST ONCE
                idem.run(f"{action_tag}:c{cycle}", lambda: {"approved": action_tag, "cycle": cycle})
                emit("human", "decide", "done", f"approval granted: {action_tag}", cycle=cycle)

        # Human checkpoint mid-cycle if the orchestrator proposed a gated action (durable wait too).
        _nh = result.get("needs_human")
        if _nh:
            if not approvals.is_granted(_nh, cycle):
                approvals.request(_nh, cycle)
                emit("human", "decide", "blocked",
                     f"awaiting approval: {_nh} — grant with "
                     f"`python .orbit/loop.py --approve {_nh}` then --resume", cycle=cycle)
                on_run_end({"cfg": cfg, "budget": budget, "reason": "awaiting human"})
                return  # resume is a fresh invocation after the human grants
            emit("human", "decide", "done", f"approval granted: {_nh}", cycle=cycle)

        # EVALUATE — Safety (veto) + Reviewer (quality) gates (also checkpointed).
        emit("reviewer", "evaluate", "start", "checking gates", cycle=cycle)
        ev = steps.run(f"c{cycle}:evaluate", lambda: evaluate_gates(result, cfg))
        passed = ev["input"] and ev["quality"] and ev["safety"]
        goal_met = _goal_met(result, cfg)
        if passed and goal_met:
            emit("independent-qa", "evaluate", "start", "reviewing exact committed snapshot", cycle=cycle)
            qa_status = steps.run(f"c{cycle}:independent-qa", lambda: evaluate_independent_qa(result, cfg))
            ev["independent_qa"] = bool(qa_status.get("passed"))
            ev.setdefault("reasons", {})["independent_qa"] = qa_status.get("reason", qa_status.get("status", ""))
            passed = passed and ev["independent_qa"]
            emit("independent-qa", "evaluate", "done" if ev["independent_qa"] else "blocked",
                 ev["reasons"]["independent_qa"], cycle=cycle)
            if passed:  # CPO acceptance runs strictly AFTER QA passes — goal fidelity, not correctness
                emit("cpo", "evaluate", "start", "judging deliverable against the user's goal", cycle=cycle)
                cpo_status = steps.run(f"c{cycle}:cpo", lambda: evaluate_cpo_acceptance(result, cfg))
                ev["cpo"] = bool(cpo_status.get("passed"))
                ev.setdefault("reasons", {})["cpo"] = cpo_status.get("reason", cpo_status.get("status", ""))
                passed = passed and ev["cpo"]
                emit("cpo", "evaluate", "done" if ev["cpo"] else "blocked",
                     ev["reasons"]["cpo"], cycle=cycle)
        fail_streak = 0 if passed else fail_streak + 1
        emit("reviewer", "evaluate", "done" if passed else "blocked", _g(ev), cycle=cycle)

        # UPDATE
        decision = "done" if (passed and goal_met) else \
                   "continue" if passed else "fix-and-retry"
        update_state(cfg, cycle, result.get("summary", "(no summary)"), ev, decision)
        emit("orchestrator", "update", "done", f"decision: {decision}", cycle=cycle)

        # DECIDE (post): explicit done?
        if decision == "done":
            emit("orchestrator", "decide", "done", "run goal met + quality gate passed",
                 cycle=cycle)
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
    ap.add_argument("--resume", action="store_true",
                    help="resume from the last checkpoint instead of starting a fresh run")
    ap.add_argument("--approve", metavar="ACTION", default="",
                    help="grant the pending human-approval checkpoint for ACTION, then re-run with --resume")
    args = ap.parse_args()
    try:
        cfg = load_config(args.config)
    except FileNotFoundError:
        sys.exit(f"config not found: {args.config}")
    if args.approve:
        _orbit = Path(cfg["paths"].get("checkpoints", ".orbit/steps.jsonl")).parent
        key = Approvals(_orbit / "approvals").grant(args.approve)
        print(f"approved: {key} — now re-run with --resume to proceed past the checkpoint")
        return
    run(cfg, resume=args.resume)


if __name__ == "__main__":
    main()
