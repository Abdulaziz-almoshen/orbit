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
| **Orchestrator / PM** | Plan, decompose, delegate, control the loop, own STATE.md, check stop conditions. Frames real forks as **decision briefs** and runs a **plan-review** (CEO + eng lenses) before building. Loads `planning-and-decision-briefs`. | CLAUDE.md, STATE.md | STATE.md, decision briefs |
| **Input / Research Specialist** | Gather, clean, and validate the inputs the work needs; guarantee they're complete and fresh before anyone uses them. | external sources, input-validation skill | validated inputs + a quality report |
| **Builder / Executor** | Produce the core output of the product from the validated inputs. (On a frontend repo, implements the Designer's Design Plan.) | validated inputs, the domain skill, design-plan | candidate output + rationale |
| **Designer** *(frontend repos only — see `profiles/frontend.md`)* | Turn a UI brief into a distinctive, production-grade **Design Plan** (tokens + layout + signature), grounded in the product's world, never a templated default. Loads `design-methodology` + `anti-ai-aesthetics`. | the brief, design source of truth | a Design Plan for the Builder |
| **Analyst** | Derive, transform, or evaluate as the domain requires; add context the Builder needs. | inputs, prior outputs | analysis notes |
| **Safety / Compliance** | Check the output is safe, permitted, and free of unreviewed side effects; block anything forbidden. **Veto power.** | candidate output, safety-rules skill | approved-or-rejected output + reason |
| **Reviewer / Evaluator** | Quality gate before "done": check the output against §3 success criteria and **prove** it (run tests/validators, not eyeball); catch errors/regressions across correctness, security, concurrency, migrations, performance, tests, API-contract, maintainability. Loads `technical-review` (severity×confidence gate, **quote-the-line** verification, blast-radius judgment). On UI work, also apply the **Design Distinctiveness** gate. **Gate power.** | all outputs, success criteria, the diff | pass/fail + evidence-backed findings |
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
| `design-methodology.md`, `anti-ai-aesthetics.md` | **Designer** | frontend/UI repos (`profiles/frontend.md`) |
| `planning-and-decision-briefs.md` | **Orchestrator** | always |
| `clarify-and-challenge.md` | **Dispatcher / Orchestrator** | always (the task path) |
| `technical-review.md` | **Reviewer / Evaluator** | always (any code/technical repo) |

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
4. **Gates are sequential even when work is parallel.** Input → (Builder ∥ Analyst
   in parallel) → Safety (veto) → Reviewer (gate) → Reporter. The two gates
   (Safety, Reviewer) are choke points by design; nothing reaches "done" without passing
   both.
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
- Parallelize only independent work (two independent analyses of the same input, or the same
  analysis across many independent items). Anything with a data dependency runs in sequence.
- Give each spawned role only the context it needs (the relevant STATE.md slice + input
  paths), not the whole history — that's the point of decomposition.
- **Load only the playbooks the lane needs.** Don't pull planning + clarify + design playbooks
  for a one-line fix — lazy-load by task. Less context = faster reasoning, no loss of rigor.
- Reason internally and **surface the decision, not the transcript** — narration is latency the
  user feels; judgment is the value.
- Collect all parallel results, then do a single STATE.md update. One writer, one write.
