# Playbook: Planning & decision briefs (the Orchestrator/Planner loads this)

Good planning is what makes the loop build the *right* thing, scalably — not just execute the
literal ask. This packages the planning rigor every Orchestrator should apply.

## Decision briefs — how to frame a real fork
When the plan hits a genuine choice (not a trivial one), don't bury it or guess. Frame it:

```
D<N> — <one-line question>
Stakes (plain English): what breaks / what the user feels if we pick wrong.
Options:
  A) <option>  — Completeness: X/10   (10 = full coverage, 7 = happy-path, 3 = shortcut)
  B) <option>  — Completeness: Y/10
Recommendation: <A or B> because <first-principles reason, not "it's standard">.
Net: the one thing you're actually trading off.
```
Use `Completeness: X/10` only when options differ in *coverage*; if they differ in *kind*,
say so and skip the score. Log settled decisions to `STATE.md` → `## Decisions` so a re-run
doesn't relitigate them.

## Two lenses, every plan
- **CEO lens (scope & value):** Is this the *simplest valuable* thing? Or is there a coherent
  *bigger* version worth proposing? Tie every choice to an observable outcome ("users wait
  N ms / hit a white screen / can now do X"), not "there may be issues." Challenge the ask
  if a smaller or larger scope serves the user better.
- **Eng lens (durability):** **Blast radius** — worst case, and how many systems/teams does
  it ripple to? Scalability, stability, failure modes, and *reversibility* (a reversible
  choice is cheaper to get wrong). Prefer the tightest feedback loop for the domain.

## Boil the ocean (completeness)
AI makes completeness cheap, so the complete thing is usually the goal: recommend full
coverage — tests, edge cases, error paths — not the demo path. The only thing out of scope is
genuinely unrelated work (a rewrite, a multi-quarter migration); flag *that* as separate
scope, never as an excuse to cut corners on the task at hand.

## Plan-review before building
Between **plan** and **act**, the Orchestrator (or a human) reviews the plan through both
lenses above. A plan that can't name its proof (how it'll know it worked) or its blast radius
isn't ready. Roles state the **Completeness** of what they hand off.

## Escalation beats guessing
If a decision is ambiguous, high-impact, or hinges on uncertain domain facts, **stop and ask**
— record it as an Open Question (`STATE.md` → `## Open Questions`) and return the cycle as
`DONE_WITH_CONCERNS`, not `DONE`. Inventing an answer to a one-way-door decision is the
expensive mistake.
