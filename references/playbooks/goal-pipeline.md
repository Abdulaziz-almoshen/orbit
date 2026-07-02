# Playbook: The goal pipeline — one goal in, a whole polished product out

The **Planner** and **Orchestrator** load this when the user sends a **goal** (a product outcome, not a
task): "build the initiative module", "make a booking prototype". The contract: the system decomposes,
builds, verifies, and **polishes to completion** — interrupting the human exactly **twice** — and what
comes back is a working product, clean and lean, not scaffolding. (For a single task, the normal loop
applies; this playbook is the goal-sized lane.)

## The artifact chain (each phase writes a file the next consumes)
1. **Spec** — after discovery/negotiation, the Planner writes `spec.md`: user stories + **numbered
   requirements** with **EARS acceptance criteria** ("WHEN <condition> THE SYSTEM SHALL <behavior>").
   Every criterion measurable — these become the QA Engineer's matrix rows. *Human gate #1: the user
   approves the spec (one message, the negotiation already happened).*
2. **Plan** — the technical shape (stack per the ADR/boring-tech rules, data model, the top-3
   architecture characteristics), then
3. **Stories** — `tasks.md`: the backlog **organized by user story**, each story a self-contained work
   order (full context + its acceptance criteria embedded — the engineer asks zero follow-ups), with
   explicit **blocks/blocked-by** edges so the backlog is a DAG.

## Slice rule: every story is a tracer bullet
A story is valid **only if** it's a thin **vertical slice** — cuts through all layers (data → API → UI),
is independently runnable/demoable, and **closes with a locking end-to-end check**. Horizontal layers
("all the models, then all the APIs…") are forbidden: no feedback until layer 3, bugs pile at the seams.
**Story #1 is always the walking skeleton** — the thinnest end-to-end path, proving the stack before
breadth. This is why every checkpoint is a *working product*, not parts.

## The completion loop (run until green, then polish)
The Orchestrator drives waves until the backlog is empty:
```
while unblocked stories remain:
    dispatch every unblocked story (parallel waves — one engineer per story where independent)
    per story: build → backpressure-verify (tests/type/lint MUST pass) → Reviewer (diff) → mark done
gap-analysis: "what does spec.md require that the build doesn't do yet?" → new stories if any
QA Engineer: full requirements-traceability pass (every ID → verdict; pixel pass vs approved design)
POLISH PASS (mandatory, once all green): one lean-ness/coherence iteration — dead code out, states
    complete (empty/loading/error), copy consistent, cross-page consistency — the "surprise" lives here
```
"Done" = **every acceptance criterion objectively green + the polish pass ran** — never "the agent
feels finished." A story failing backpressure twice → struggle detection: stop, diagnose, escalate if stuck.

## Autonomy with meaningful gates (the decision taxonomy)
Classify every decision mid-run; don't stop for what you can decide:
- **Mechanical** (one right answer — naming, file placement, an obvious lib): decide silently, log it.
- **Taste** (reasonable people differ — layout variant, copy tone, minor scope): decide with your
  recommendation, **batch into ONE end-of-run approval** alongside the demo. *Human gate #2.*
- **User-challenge** (the evidence says the user's stated direction should change) and **one-way doors**
  (schema, auth model, anything hard to undo): **never auto-decide** — stop and ask, with the evidence.
Principles when deciding: completeness over shortcut · smallest diff that's actually right · boring
tech by default · explicit over clever · bias to action. **Auto-deciding replaces the user's judgment,
never the analysis** — and every decision gets a line in the audit trail (STATE.md / an ADR if architectural).

## Keep it lean (the "clean" in clean-and-lean)
The spec's **out-of-scope list** is binding; a "Delay: not yet" list beats speculative features. No new
dependency without clearing the boring-tech bar (see `architecture-decisions`). The polish pass removes
what the run added but the spec never asked for.

## Live visibility
The team board shows the story DAG burning down (`✓ story-3 · ▸ story-4 (wave 2) · ○ story-5`), each
story in its engineer's color, with the team voice narrating waves. The Reporter's close is the demo:
what was built, the requirement scorecard, what was decided (the taste batch), what's deferred.
