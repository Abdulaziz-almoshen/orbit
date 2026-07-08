# Loop design, stop conditions, and the config contract

The loop is where "a system that prompts itself" becomes literal. This file specifies
the cycle, the stop conditions that keep it safe, the portable config that encodes them,
and the two ways to run it (portable runner vs. Ralph loop).

## The cycle: read → plan → act → evaluate → update → decide

1. **READ** — load `CLAUDE.md` then `.orbit/STATE.md`. A fresh agent now knows the
   product, the bar, what's done, and what's next — with no conversation history.
2. **PLAN** — pick the top task from STATE.md's queue. For anything non-trivial, write
   the plan before acting (the human can be asked to approve big plans).
3. **ACT** — the Orchestrator delegates to the right specialist role(s), parallel where
   independent. Roles write artifacts to known paths and report back.
4. **EVALUATE** — measure the output against the success criteria (CLAUDE.md §3) via the
   eval gates. Run Safety (veto) and Reviewer (quality) gates. Failing a gate is normal —
   it routes to a fix task, it doesn't crash the loop.
5. **UPDATE** — the Orchestrator folds results into STATE.md: overwrite snapshot/queue,
   append to decision + cycle logs. Update CLAUDE.md only if a durable fact changed.
6. **DECIDE** — check stop conditions. Then: run goal met → **done**; blocker needs a
   human → **pause and surface**; hard cap tripped → **stop**; otherwise → **continue**
   to the next READ.

The DECIDE step is the brake. It runs every cycle and it is the only place the loop is
allowed to keep going.

## Stop conditions — the non-negotiable part

Daisy stressed these because an unattended loop with API credits and side effects is how
you get a surprise bill or a real-world mistake. Three categories, all enforced by
`loop.config.json`:

### 1. Hard limits (cheap, absolute — check before every cycle)
- `max_iterations` — total cycles per run.
- `token_budget.per_cycle` / `token_budget.per_run` — abort the cycle / the run on breach.
- `cost_budget_usd.per_run` — dollar ceiling; abort on breach.
- `max_runtime_seconds` — wall-clock ceiling for the whole run.

These need no judgment. The runner checks them mechanically and stops the moment one
trips. They are the backstop that holds even if every other check is misconfigured.

### 2. Eval gates (proceed only if all pass)
Defined per domain; each is a boolean check the runner can evaluate:
- **Input gate** — the inputs the cycle needs are present, well-formed, and fresh within
  tolerance; passes the input-validation skill.
- **Quality gate** — the cycle's output meets the success criteria (e.g. a Reviewer rubric
  score ≥ threshold, or a concrete domain metric above its bar), as judged by the Reviewer
  role.
- **Safety gate** — Safety/Compliance approves (no forbidden action, no unreviewed side
  effect, output permitted). Safety holds a **veto**: a failed safety gate can never be
  overridden by the loop.

A failed gate does not necessarily stop the run — it blocks *progress* and routes a fix
task into the queue. But a gate that fails repeatedly (`gate_failure_streak`) trips a
hard stop, because a loop that can't pass its own bar is thrashing and burning money.

### 3. Human-approval checkpoints (the loop pauses and waits)
Any action that is irreversible, financial, outward-facing, or spends money routes
through a human:
- moving money or any financial action (**forbidden outright by default**, not merely
  gated — see below),
- sending external messages/notifications to third parties,
- deploys / infra changes, deleting or overwriting data,
- spend above a configured threshold.

At a checkpoint the loop writes the proposed action + rationale to STATE.md, surfaces it,
and **stops the cycle**. A human resumes it. The loop proposes; a human disposes.

### Side-effect safety (hard rule, not a setting)
**Dry-run / sandbox by default. The system never takes an irreversible, financial, or
outward-facing action on its own.** It may *propose* such an action — with its rationale —
for a human to approve, and it may act freely in a sandbox explicitly flagged as such.
Enabling a real side effect must be a deliberate human change to the config *and* gated by
an approval checkpoint — there is no "autonomous irreversible action" mode in this
scaffold, by design. Moving money is `FORBIDDEN` by default: the system does not perform
financial actions on a user's behalf.

## The config contract — `loop.config.json`

The config is the single, portable encoding of everything above. Both runners read it; it
is the contract between the methodology and the machine. See `assets/loop.config.json`
for the template with inline comments. Shape:

```json
{
  "run_goal": "one sentence; mirrors STATE.md run goal",
  "hard_limits": {
    "max_iterations": 2,
    "token_budget": { "per_cycle": 20000, "per_run": 80000 },
    "cost_budget_usd": { "per_cycle": 0.35, "per_run": 1.25 },
    "max_runtime_seconds": 900,
    "gate_failure_streak": 2
  },
  "eval_gates": {
    "input":   { "require_complete": true, "max_staleness_seconds": 3600 },
    "quality": { "min_reviewer_score": 8, "max_score": 10 },
    "safety":  { "require_safety_approval": true, "forbid_unreviewed_side_effects": true }
  },
  "approval_checkpoints": {
    "move_money": "FORBIDDEN",
    "external_message": "human",
    "deploy": "human",
    "delete_data": "human",
    "spend_over_usd": 1.0
  },
  "done_when": "STATE.md run_goal satisfied and Reviewer gate passed",
  "dispatch": { "orchestrator": "your-orchestrator", "model": "<model-id>" }
}
```

`approval_checkpoints` values: `auto` (loop may do it), `human` (pause for approval),
`FORBIDDEN` (never, full stop). Numeric thresholds (`spend_over_usd`) mean "above this →
human."

## Two runners, one contract

### Portable runner — `.orbit/loop.py`
Implements the cycle against `loop.config.json`. Model-agnostic: the only model-specific
part is `dispatch(role, task)`, a clearly marked seam you wire to the user's orchestrator
(e.g. Gemini, or any model/runtime). Use this for production runs on their own stack, in
cron, or in CI. It keeps a running token/cost tally and checks hard limits before every cycle.

### Ralph loop — `scripts/ralph_loop.sh`
A thin external shell loop that drives headless `claude -p` once per iteration, each time
with **fresh context**, relying entirely on `CLAUDE.md` + `STATE.md` for continuity. This
is the "Ralph loop" idea: instead of one long-running agent whose context rots, you
restart a clean agent each cycle and let the files carry the memory. It enforces the same
`max_iterations` / runtime caps in bash and bails on any non-zero exit or a stop sentinel
the agent writes to STATE.md. Use it for autonomous runs inside the Claude Code ecosystem.

Both honor the same `loop.config.json`. Pick the runner per where you're executing; the
contract — and the safety — is identical.

### Durability — survive a restart, don't start over

A process will die (deploy, OOM, crash). A loop that re-runs from scratch on restart
re-fetches data, re-calls the model (re-burning tokens), and can double-fire side effects.
So the loop checkpoints **steps**: `loop.py`'s `Steps` memo records each completed step's
output to `.orbit/steps.jsonl`; a fresh run starts clean, `loop.py --resume` skips completed
steps and continues. Wrap the things you don't want repeated — fetches, model calls, side
effects (so resume doesn't double-send). `ralph_loop.sh` is the **dev** runner and is *not*
durable (a crash restarts the cycle); for unattended production, run on a durable engine
(Inngest / Temporal / Vercel Workflow) where checkpointing, retries, `onFailure`, triggers,
and concurrency are native. See `references/durable-execution.md` and the reference template
`assets/runners/inngest-loop.ts`. **Don't build your own engine — integrate one.**

### Concurrency — one run per key

Set `concurrency.singleton_key` in `loop.config.json` so at most one run happens per key
(per ticker / service / conversation / screen) — a scheduled run can't stomp a running one.
A durable engine enforces this natively; the portable runner uses a lockfile.

## Recommending the first run

Start small and boring on purpose. A good first loop:
- the smallest useful unit of work, dry-run / sandbox only,
- `max_iterations: 2`, tight `per_run` token + dollar budget, `max_runtime_seconds` short,
- every checkpoint that could matter set to `human`,
- success = "produce one validated output that passes the quality and safety gates,"
- and you watch the first run end-to-end before you ever leave it unattended.

The goal of the first run is to prove the *harness* works and stops correctly — not to
ship output. Confidence in the brakes comes before autonomy.
