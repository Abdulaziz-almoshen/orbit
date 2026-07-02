# Playbook: Architecture decisions — the CTO hat (direction decided once, never relitigated)

The **Planner** and the **Orchestrator's plan-review** load this on the substantial lane. A CTO is a
*hat, not a headcount*: the ability to set technical direction with named trade-offs, record it, and
hold the line — so the product stays coherent and lean across every cycle and session.

## When a decision is architectural (open an ADR, not a chat)
Signals: choosing between frameworks/stores/services · a schema or auth model · a service/module
boundary · an integration pattern · anything **hard to undo** (one-way door) · reversing a prior call.
Trivia (naming, file placement) is not architectural — decide and move.

## The ADR — `.orbit/decisions/NNN-<slug>.md` (append-only)
```
# NNN. <decision title>                      Status: proposed | accepted | superseded-by-NNN
## Context        — the problem + the constraints (team, timeline, existing stack)
## Decision drivers — the named forces (from the top-3 characteristics below)
## Options        — 2–3, each scored: Complexity · Cost · Scalability · Team familiarity · Maturity/licensing · Migration
## Decision       — the call + first-principles why (not "it's standard")
## Consequences   — honest, including the negative ones
## Confirmation   — HOW adherence will be verified (a check the Reviewer/QA can run)
```
Rules: one decision per record · **supersede, never rewrite** (the history is the point) · rejected
options stay with their "why not" · readable in 2 minutes · never fabricate a rationale — if you don't
know, ask. Keep an index in `.orbit/decisions/README.md`. Genuine forks get the full form; routine
calls get the short form (Context/Decision/Consequences). Depth scales to stakes.

## The standing rules (what makes direction *lean*)
- **Boring technology by default.** The detected stack is the "adopt" ring. A NEW framework/DB/service
  costs an **innovation token** (a project gets ~3) and must clear a written bar: what does the current
  stack fail to do · the migration story · the 3am-operations story. No answer → no new tech.
- **Top-3 architecture characteristics.** On a goal-sized ask, name at most 3 "-ilities" that actually
  matter here (with one-line justifications, logged to STATE.md). Every decision brief must state its
  impact on those 3 — and each becomes a **fitness function** the Reviewer/QA runs every cycle
  (e.g. "p95 route < 200ms in the smoke run", "no cross-surface imports", "bundle < X KB").
- **The user's stack is law** unless the evidence says otherwise — then it's a user-challenge
  (escalate with the evidence), never a silent migration.

## How it runs in the loop
- **Plan phase (goal lane):** a C4-lite snapshot of the current architecture (containers + tech +
  dependencies, from the detected surfaces) → the characteristics worksheet → decisions as ADRs.
- **Every cycle:** the Orchestrator **loads accepted ADRs as constraints** (like the learning ledger) —
  the loop never re-decides settled direction; a re-opened decision requires a superseding ADR.
- **The Reviewer enforces:** an architectural change in the diff with **no corresponding ADR is a
  finding**; each ADR's Confirmation check runs as part of the gate.
- **Active learning ties in:** an architectural learning routes here (an ADR), not to CLAUDE.md prose.
