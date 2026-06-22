# Durable execution — what runs the loop

Most agent talk is about what the loop *does* (reasoning, tools, context). The harder
question is what *runs* it. A loop that can't survive a restart isn't a loop — it's a
`while True` that starts over on every crash, re-fetching data, re-calling the model
(re-burning tokens), and re-firing side effects (the duplicate-Slack-message problem).

Orbit is strong at the **design** layer (memory, roles, gates, safety, onboarding) but it
is **not** an execution engine. This file says how to put a real one underneath it.

## The three layers

1. **Loop** — a trigger (cron, event, or human) plus a decision-maker. Cron is the
   heartbeat; the model is the decision in the middle; **steps** are the durable execution
   that checkpoints progress.
2. **Skill (durable workflow)** — a multi-step, retryable, composable unit of work. **Note
   the vocabulary:** the article's "skill" is a *durable workflow*. Orbit's
   `.orbit/skills/*.md` are **knowledge playbooks** — reference material a role loads, not
   workflows. Two different things; don't conflate them. Where this file says "durable
   skill" it means a workflow/function on the engine; where Orbit says "skill" it means a
   playbook.
3. **Orchestrator** — the engine that schedules triggers, executes steps, retries, enforces
   concurrency, stores run history, and hot-deploys new functions. Invisible when it works;
   foundational always.

LLM + tools live *inside* the loop. So: **an agent is loops + durable skills + orchestration**,
not just "LLM + tools." Swap the model freely; the architecture and the skill library persist.

## Why durability is the foundation, not a feature

A process **will** die — deploy, OOM, spot reclaim, a 30-minute provider outage. The fix
isn't "better error handling," it's an execution model where:
- **each step is checkpointed** — on restart, completed steps are skipped, not re-run;
- **each decision is persisted** — the model isn't re-asked (and re-charged) for choices it
  already made;
- **side effects are idempotent** — a resumed run doesn't double-send or double-spawn;
- **retries are per-step** — if step 3 of 5 fails transiently, retry step 3, not 1–2;
- **failures have a hook** — when retries are exhausted, an `onFailure` path notifies a
  human and preserves the triggering event so the next run can pick it up.

Checkpointing is also a **cost** control: re-running a loop from zero re-pays for every LLM
call. Multiply across many agents and it's real money.

## Two runners — pick by where you are

Orbit ships both; be honest about which is which:

- **`scripts/ralph_loop.sh` — the DEV runner.** A fresh `claude -p` per cycle, memory in
  the files. Great for developing and watching a loop interactively. It is **not durable**:
  a crash mid-cycle restarts the cycle. Don't run unattended production on it.
- **A durable engine — the PRODUCTION runner.** Run the loop on Inngest / Temporal /
  Vercel Workflow. You get step checkpointing, retries, `onFailure`, cron/event triggers,
  concurrency, hot-deploy, and step-level run history for free. Orbit's `loop.py` `dispatch()`
  is the seam; `assets/runners/inngest-loop.ts` is a reference template. **Don't build your
  own engine** — that's years of work and it's exactly what these tools exist for.

The portable `loop.py` adds a thin durability layer (the `Steps` checkpoint memo + `--resume`)
so the *portable* path also survives a restart — but a real engine is the production answer.

## Concurrency — one run per key

A scheduled loop must not stomp a running one (the orphaned-background-loop bug). Use a
**singleton per key**: at most one run per ticker / service / conversation / screen. On an
engine this is a native control (e.g. `concurrency: [{ limit: 1, key: "event.data.service" }]`,
as utah does per conversation); in the portable runner it's a lockfile keyed by
`concurrency.singleton_key` in `loop.config.json`. Queue the second run; don't race.

## Observability is the trust layer

When the thing that wrote the code isn't a human, "see what happened at 3am" is not a
nice-to-have. Every checkpoint is observable by construction: each `step.run()` records its
inputs, output, duration, retries, and status. Orbit's `activity.jsonl` is the portable
version of this (the `Steps` memo writes a per-step record); on an engine, use its run
history. Either way: every step, every decision, every retry — auditable after the fact.

## North star — the orchestration-aware, self-extending agent

The advanced pattern (Inngest's `utah`, https://github.com/inngest/utah): the agent has the
orchestration SDK as a tool. It **writes new durable skills**, a sidecar **registers them
without a restart**, and a **weekly cron review loop** reads run history, judges performance
(did the alerts correlate with real outages? false positives?), and proposes changes. The
agent is ephemeral; its output — the durable skill library — persists across model swaps.
That's "the moat is the loop" made concrete: institutional knowledge encoded as executable,
durable infrastructure.

This is a direction, not a Phase-1 deliverable, and it only works on a real engine. Orbit's
role/playbook/gate model is the design half; a durable orchestrator is the execution half.
Build the design now; graduate to the engine when you go to production.
