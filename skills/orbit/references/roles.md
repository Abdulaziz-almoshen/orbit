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
| **Orchestrator / PM** | Plan, decompose, delegate, control the loop, own STATE.md, check stop conditions. | CLAUDE.md, STATE.md | STATE.md |
| **Input / Research Specialist** | Gather, clean, and validate the inputs the work needs; guarantee they're complete and fresh before anyone uses them. | external sources, input-validation skill | validated inputs + a quality report |
| **Builder / Executor** | Produce the core output of the product from the validated inputs. | validated inputs, the domain skill | candidate output + rationale |
| **Analyst** | Derive, transform, or evaluate as the domain requires; add context the Builder needs. | inputs, prior outputs | analysis notes |
| **Safety / Compliance** | Check the output is safe, permitted, and free of unreviewed side effects; block anything forbidden. **Veto power.** | candidate output, safety-rules skill | approved-or-rejected output + reason |
| **Reviewer / Evaluator** | Quality gate before "done": check the output against §3 success criteria; catch errors/regressions. **Gate power.** | all outputs, success criteria | pass/fail + reasons |
| **Reporter** | Turn results into clear, decision-ready outputs/explanations. | everything above, output-formatting skill | reports, summaries |

Two roles hold special power and must always exist: **Safety/Compliance** can veto any
action (it is the safety gate), and **Reviewer/Evaluator** decides whether a cycle's
output is good enough to count as progress (it is the quality gate). The Orchestrator may
delegate freely but cannot overrule either gate without a human.

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

## Done / handoff criteria
- (what must be true before this role hands off; which role gets it next)

## Limits & safety
- (context/scope boundaries; what it must NOT do; when it must escalate to a human)
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

- Parallelize only independent work (e.g. two independent analyses of the same input, or
  the same analysis across many independent items). Anything with a data dependency runs
  in sequence.
- Give each spawned role only the context it needs (the relevant STATE.md slice + input
  paths), not the whole history — that's the point of decomposition.
- Collect all parallel results, then do a single STATE.md update. One writer, one write.
