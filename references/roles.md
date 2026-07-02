# The sub-agent team

One agent doing everything blows its context and does each thing mediocrely. A team of
narrow specialists, coordinated by an Orchestrator and gated by a Reviewer, does each
thing well and in parallel. This file defines the standard roster, the spec format, the
handoff protocol, and how to render each role for both output layers.

Adapt names and scope to the product — but keep the *shape*: one planner, several
executors, one safety gate, one quality gate. The roster below is a domain-neutral
default; rename and re-scope each role to the real subtasks of the product you're in.

## Roster (standard, SDLC-style)

| Role | Remit | Reads | Writes |
|------|-------|-------|--------|
| **Dispatcher / Router** | Classify each request: **question** → answer directly (no loop); **task** → first **clarify & challenge** (infer from the repo, surface premises, ask only the gap), then hand to the Orchestrator to route through the loop (CLAUDE.md §10). Loads `clarify-and-challenge`. No edit tools. | the user request, CLAUDE.md §10 | a routing decision + clarified intent |
| **Orchestrator / PM** | **Conducts** the loop: on the substantial lane, convenes the **discovery team** (below) in the PLAN phase, runs **plan-review** (CEO + eng lenses), owns STATE.md (sole writer), checks stop conditions. Folds the team's artifacts into the plan; doesn't do the discovery itself. Loads `planning-and-decision-briefs`. | CLAUDE.md, STATE.md, the team's briefs | STATE.md, ratified plan |
| **Product Discovery Manager** *(planning phase, substantial lane)* | De-risk the *bet* before building: frame the **outcome** + the user's **job**, map opportunities from evidence, kill the four risks (value/usability/feasibility/viability), name the **riskiest assumption + cheapest test**. Extends clarify-and-challenge with evidence. Loads `product-discovery`. | clarified intent, repo/analytics, market brief | `discovery-brief.md` |
| **Market & Competitive Researcher** *(planning phase, substantial lane)* | What already exists, what the user would use instead, where the gap is — a **reuse-vs-build verdict**, graded feature matrix, positioning. Timeboxed, cited. Runs in **parallel** with discovery. Loads `market-and-competitive-research`. Distinct from Input/Research below. | the JTBD/intent, the web, deps | `market-brief.md` |
| **Planner** *(planning phase, substantial lane)* | Turn the validated, de-risked bet into the **plan of record** — thin vertical slices, sequenced by dependency + risk, a proof bar per slice, hand-off specs. Emits **decision briefs** in the standard format up to the Orchestrator. Loads `planning-and-decision-briefs`. | discovery + market briefs, §3 criteria | `plan.md` + decision briefs |
| **Input / Research Specialist** | Gather, clean, and validate the **data inputs** the work consumes; guarantee they're complete and fresh. (Supply-side data — *not* the demand-side Market Researcher above.) | external sources, input-validation skill | validated inputs + a quality report |
| **Builder / Executor** | Produce the core output of the product from the validated inputs. (On a frontend repo, implements the Designer's Design Plan.) | validated inputs, the domain skill, design-plan | candidate output + rationale |
| **Designer** *(frontend repos only — see `profiles/frontend.md`)* | On any UI request, **first** run the mandatory **style-prototype gate**: shortlist 2–4 of the 67 styles, build a standalone HTML prototype of each, open them, let the user **pick** — then turn the chosen style into a distinctive, production-grade **Design Plan** (tokens + layout + signature) grounded in the product's world. Loads `design-methodology` + `design-styles` (the 67-style catalog) + `anti-ai-aesthetics`. | the brief, design source of truth | HTML prototypes → a Design Plan for the Builder |
| **Analyst** | Derive, transform, or evaluate as the domain requires; add context the Builder needs. | inputs, prior outputs | analysis notes |
| **Safety / Compliance** | Check the output is safe, permitted, and free of unreviewed side effects; block anything forbidden. **Veto power.** | candidate output, safety-rules skill | approved-or-rejected output + reason |
| **Reviewer / Evaluator** | Quality gate before "done": check the output against §3 success criteria and **prove** it (run tests/validators, not eyeball); catch errors/regressions across correctness, security, concurrency, migrations, performance, tests, API-contract, maintainability. Loads `technical-review` (severity×confidence gate, **quote-the-line** verification, blast-radius judgment). On UI work, also apply the **Design Distinctiveness** gate — *and confirm the mandatory style-prototype selection happened* (a UI change with no user-picked style + previews doesn't pass). **Enforces ADRs**: an architectural change in the diff with no corresponding ADR in `.orbit/decisions/` is a finding, and each accepted ADR's Confirmation check runs as part of the gate. **Gate power.** (Reviews the *diff*; the QA Engineer validates the *product* — both must pass.) | all outputs, success criteria, the diff, `.orbit/decisions/` | pass/fail + evidence-backed findings |
| **QA Engineer** | Validate the **product against the requirements** — requirement by requirement, user story by user story; on UI work, pixel-by-pixel vs the approved design. Builds a **Requirements Traceability Matrix** (every ID → test → verdict → evidence; PASS/CONCERNS/FAIL/WAIVED). **Report-only** (never fixes). Loads `qa-validation`. **Gate power** — a P0 FAIL or score <85 means not done. | the Planner's requirements/EARS criteria, the running app, `design/approved.json` + `DESIGN.md` | the RTM report + verdict |
| **Reporter** | Turn results into clear, decision-ready outputs/explanations. | everything above, output-formatting skill | reports, summaries |

Two roles hold special power and must always exist: **Safety/Compliance** can veto any
action (it is the safety gate), and **Reviewer/Evaluator** decides whether a cycle's
output is good enough to count as progress (it is the quality gate). The Orchestrator may
delegate freely but cannot overrule either gate without a human.

## Skill library — provision skills to a role when you create it

Orbit ships a growing library of reusable role **playbooks** in `references/playbooks/`. A
playbook is packaged know-how a role loads on demand — *not* baked into the role spec, so the
same playbook can serve many products and the library grows over time. When `/orbit` creates a
sub-agent, it **provisions the relevant playbooks** by copying them into the repo's
`.orbit/skills/` and pointing the role at them. Current library:

| Playbook | Provisioned to | When |
|----------|----------------|------|
| `design-methodology.md`, `anti-ai-aesthetics.md`, `design-styles.md` + `design-styles/` (67 styles) | **Designer** | frontend/UI repos (`profiles/frontend.md`) |
| `planning-and-decision-briefs.md` | **Orchestrator** + **Planner** | always |
| `clarify-and-challenge.md` | **Dispatcher / Orchestrator** | always (the task path) |
| `product-discovery.md` | **Product Discovery Manager** | always (convened on the substantial lane) |
| `market-and-competitive-research.md` | **Market & Competitive Researcher** | always (convened on the substantial lane) |
| `technical-review.md` | **Reviewer / Evaluator** | always (any code/technical repo) |
| `active-learning.md` | **Orchestrator** (the loop's UPDATE phase) | always — silently learns from corrections + major changes |
| `qa-validation.md` | **QA Engineer** | always — the requirements-traceability + pixel-fidelity gate |
| `goal-pipeline.md` | **Planner + Orchestrator** | goal-sized asks — spec → story DAG → run-until-green → polish pass, 2 human gates |
| `architecture-decisions.md` | **Planner / Orchestrator plan-review** (the CTO hat) | substantial lane — ADRs in `.orbit/decisions/`, boring-tech bar, fitness functions |

Add new playbooks here as the system grows (e.g. data-validation, backtesting, fact-checking
for other domains). A role's spec just says "load `<playbook>`"; the substance lives once, in
the library.

## Role spec format (model-agnostic)

Write each role to `.orbit/roles/<role>.md` in this shape so any model can adopt it:

```markdown
# Role: <Name>

## Mission
(1–2 sentences. The single thing this role is responsible for.)

## Inputs
- (what it reads: STATE.md fields, datasets, prior role outputs, which skills to load)

## Procedure
1. (concrete steps; reference the skill(s) that carry the how-to)
2. ...

## Outputs
- (exact artifacts + where they go; what it reports back to the Orchestrator)

## Proof / verification
- (the CONCRETE evidence this role's output is correct — a command that exits 0, a metric
  over a threshold, a checklist all-true, a rubric score. "Looks done" is not proof. Maps to
  `loop.config.json` → `proof`.)

## Done / handoff criteria
- (what must be true before this role hands off; which role gets it next)

## Limits & safety
- (context/scope boundaries; what it must NOT do; when it must escalate to a human)

## Announce yourself (observability)
- Emit a `start` event when you pick up work and `done`/`blocked` when you hand off, via
  `.orbit/activity.py`'s `emit(role, phase, status, msg)`; open your report with `[role] …`.
  This is how the live view (TaskCreate/TaskUpdate + `orbit-status`) shows who's talking. See
  `observability.md`.
```

## Claude Code adapter (subagents)

For the Claude Code path, render each role to `.claude/agents/<role>.md` with the
subagent frontmatter Claude Code expects, and a body that mirrors the role spec:

```markdown
---
name: <role-slug>
description: <when the Orchestrator should delegate to this role — be specific so it
  triggers reliably>
tools: <only the tools this role needs — least privilege>
---

<the role's mission, procedure, outputs, and limits — same content as the role spec,
phrased as instructions to the subagent>
```

Keep the two in sync: the `.orbit/roles/` spec is the source of truth; the
`.claude/agents/` file is its Claude Code embodiment. See `assets/claude-agents/` for a
worked example.

## Handoff protocol

Parallel roles must not corrupt shared state. The rules:

1. **Only the Orchestrator writes STATE.md.** Specialists return results to the
   Orchestrator (as their final message / a file in a known location); the Orchestrator
   folds them into STATE.md at cycle end. This serializes writes even when execution is
   parallel.
2. **Artifacts go to known paths, not into prose.** A role that produces a dataset, a
   draft, or any sizeable output writes it to a predictable location (e.g.
   `.orbit/artifacts/<cycle>/<role>-<thing>`) and references the path in its report.
   The next role reads the path. This keeps large data out of context windows.
3. **Handoffs are explicit.** The producing role records the handoff in its report:
   "produced `<path>`; <next-role> should <do what>; need back: <what>." The Orchestrator
   mirrors current in-flight handoffs in STATE.md's Handoffs section.
4. **Gates are sequential even when work is parallel.** Input → (Engineers ∥ Analyst
   in parallel) → Safety (veto) → Reviewer (the diff) → **QA Engineer (the product vs the
   requirements)** → Reporter. The three gates (Safety, Reviewer, QA) are choke points by
   design; nothing reaches "done" without passing all of them.
5. **Escalation beats guessing.** If a role hits an ambiguous, high-impact decision, it
   stops and records an Open Question in its report rather than improvising. The
   Orchestrator decides whether to pause for a human (see stop conditions).

## Fan-out guidance for the Orchestrator

- **Size the loop to the task first (fast by default).** A small, clear, reversible task gets
  no fan-out at all — do it directly, self-check, log one line. Spin up the team only for
  substantial, ambiguous, or irreversible work. Most tasks are the former; that's what keeps
  the system quick (CLAUDE.md §10).
- **Deliberate in parallel, not serially.** When work *is* substantial, fan out the *thinking*
  too — infer-from-repo ∥ generate 2–3 approaches ∥ scan risks — then synthesize. Same
  wall-clock as one pass, more perspectives = a sharper call. A serial plan→brief→review chain
  is the slow path; avoid it.
- **The planning relay (substantial lane only).** Convene the **discovery team** in the PLAN phase:
  **Product Discovery Manager ∥ Market & Competitive Researcher** run *concurrently* (independent
  inputs) → both feed the **Planner** (which has a data dependency, so it runs after) → the Planner
  hands `plan.md` + decision briefs back to you → you run **plan-review** and fold it into STATE.md →
  build. **Skip the team on the fast lane** (small/clear/reversible — Builder just does it); on a
  **medium** task, wear the hats yourself instead of spinning up all three. Depth scales to stakes;
  never run a 3-agent discovery sprint on a one-line fix. You stay the sole STATE.md writer.
- Parallelize only independent work (two independent analyses of the same input, or the same
  analysis across many independent items). Anything with a data dependency runs in sequence.
- Give each spawned role only the context it needs (the relevant STATE.md slice + input
  paths), not the whole history — that's the point of decomposition.
- **Load only the playbooks the lane needs.** Don't pull planning + clarify + design playbooks
  for a one-line fix — lazy-load by task. Less context = faster reasoning, no loss of rigor.
- Reason internally and **surface the decision, not the transcript** — narration is latency the
  user feels; judgment is the value.
- Collect all parallel results, then do a single STATE.md update. One writer, one write.
