# Profile: the universal profile

This is the default profile for any product. It keeps the methodology intact while you
elicit the domain specifics this skill doesn't hard-code. The goal: end up with the same
five pillars (memory, sub-agents, skills, eval loop, stop conditions), fitted to whatever
this product actually is. If you set the skill up for the same kind of product
repeatedly, capture its specifics as a new file alongside this one under
`references/profiles/` and reuse it.

## First, characterize the domain (ask the user)

You can't write good success criteria for a product you don't understand. Ask 2–4
focused questions:
1. **What does the product do, and who is it for?** (one or two sentences)
2. **What does a good cycle output look like?** What would make the user say "yes, ship
   that"? Push for something measurable.
3. **What's the most expensive mistake the system could make?** (This defines the
   approval checkpoints and the risk gate.)
4. **What external systems does it touch?** (APIs, data sources, side-effecting actions —
   these become tools and checkpoints.)

If the repo already encodes answers (README, configs, code), mine those first and confirm
rather than asking cold.

## Map the answers onto the scaffold

- **Success criteria (CLAUDE.md §3):** turn "good output" into numbers/booleans a gate
  can check. If the output is subjective (writing, design), define a rubric the Reviewer
  role applies and treat the quality gate as a rubric score threshold.
- **Sub-agent team (`references/roles.md`):** keep the shape — one Orchestrator, several
  specialists matched to the product's real subtasks, one safety/risk gate (whatever
  "dangerous" means here), one Reviewer/quality gate. Rename freely; e.g. a content
  product might have Research, Draft, Edit, Fact-check (the safety gate), Reviewer.
- **Skills (`.orbit/skills/`):** package this product's recurring know-how. Ask "what
  do we explain or re-derive every time?" — that's a skill. Aim for 4–6 high-value ones.
- **Tools & hooks (`hooks-and-tools.md`):** wrap each external system as a least-privilege
  tool; add hooks to validate outputs and to gate any side-effecting action.

## Stop conditions still apply — fit them to the domain

The hard limits (iterations, token/cost budget, runtime) are universal; copy them as-is.
The eval gates and approval checkpoints are domain-specific:
- **Eval gates:** whatever "the output is good enough to count as progress" means here.
  At minimum a quality gate (Reviewer) and, if there's any notion of dangerous output, a
  safety gate.
- **Approval checkpoints:** the answer to "most expensive mistake" question. Anything
  irreversible, outward-facing, or costly routes through a human. The default posture for
  any side-effecting action you're unsure about is `human`, not `auto`.

## The universal safety rule

Regardless of domain: **the loop never takes an irreversible, financial, or outward-facing
action on its own.** It proposes; a human approves. When in doubt about whether an action
qualifies, gate it. A loop that can only read, compute, and write to its own state files
is safe to run unattended; the moment it can email a customer, charge a card, deploy, or
delete data, those specific actions need a human at the gate.

## First run recommendation

Same philosophy as every profile: start small and prove the brakes. Pick the smallest
useful unit of work, `max_iterations: 2`, tight budgets, short runtime, every uncertain
checkpoint set to `human`. Success = "produce one validated output that passes the quality
gate." Watch the first run end to end and confirm it stops on its own before you ever
leave it unattended. Confidence in the stop conditions comes before any autonomy.
