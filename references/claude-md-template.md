# CLAUDE.md template

`CLAUDE.md` is the single source of truth the whole system reads at the start of every
cycle. It is **memory, not a manual**: overview + current state + the bar to clear +
the roster + the rules that gate the loop. Detailed, rarely-changing know-how belongs in
skills; automated enforcement belongs in hooks. If the system needs to scroll past
CLAUDE.md to find what it needs, it's too long.

When a `CLAUDE.md` already exists, **merge** — preserve the user's content and slot these
sections around it; never clobber.

Copy the structure below, delete the parenthetical guidance, and fill with the real,
audited specifics of the repo. Keep each section tight. The examples are deliberately
domain-neutral — replace them with your product's real criteria, roles, and skills.

---

```markdown
# <Product Name> — Agent System Memory

> Read this file first, every cycle. Working state lives in `.orbit/STATE.md`.
> Update both after significant work (see "Maintenance" below).

## 1. Project Overview & Goals
(2–4 sentences: what the product is, who it's for, the single most important outcome.
Then 3–5 bullet goals, ordered by priority.)

## 2. Current State — pointer
The live, mutable state (open tasks, decisions, blockers, last cycle's result) is in
**`.orbit/STATE.md`**. Read it after this file. Keep durable facts here; keep churn
there.

Last major milestone: (one line, updated on big changes only)

## 3. Success Criteria & Evaluation Metrics
(The bar every cycle's output is measured against. Make these measurable. Examples — fit
to your domain:)
- Input validity: required inputs present, well-formed, and fresh within tolerance.
- Quality: the output meets a defined bar — a Reviewer rubric score ≥ X/10, or a concrete
  domain metric above a stated threshold.
- Safety: no forbidden or unreviewed side-effecting action; the output is permitted.
- Completeness: the cycle's task is fully done, not partially.
- Reproducibility: a result can be regenerated from logged inputs + config.

## 4. Tech Stack & Conventions
- Language/runtime, package manager, key libraries.
- External systems: (which APIs/services, auth via which env var, rate limits).
- Model/orchestration: (how the model/orchestrator is called, where the seam is).
- Conventions: (style, where code goes, how to run tests, naming).
- Secrets: never commit; read from env / secret store. List required env vars.

## 5. Instructions for All Agents
- Work in small, verifiable steps; show your work; prefer clean, maintainable code.
- Read `STATE.md` before acting; write to it after acting.
- Use a plan before non-trivial architectural changes.
- Treat external integrations as reliable tools — don't reinvent them.
- **Never take an irreversible, financial, or outward-facing action autonomously.**
  Propose; a human approves. Run in dry-run / sandbox mode by default.
- Stay within the stop conditions in §8. If you'd exceed one, stop and report.
- **Announce yourself.** Open your output with `[role] …` and emit to `.orbit/activity.jsonl`
  (via `.orbit/activity.py`); keep the checklist current (TaskCreate/TaskUpdate in Claude Code, or
  `.orbit/tasks.json` for `orbit-status`) so a watcher always sees who's doing what.
- Update this file when a durable fact changes; update `STATE.md` every cycle.

## 6. Sub-Agent Roster
(One line per role: name — remit. Full specs in `.orbit/roles/`. Adapter subagents in
`.claude/agents/`. Handoff protocol in `.orbit/roles/README.md` / `references/roles.md`.
Rename and scope these to your product's real subtasks; keep the shape — one planner,
several executors, one safety gate, one quality gate.)
- Dispatcher/Router — classifies each request (task vs question) per §10 and routes it.
- Orchestrator/PM — plans, decomposes, controls the loop, owns STATE.md.
- Input/Research Specialist — gather, clean, and validate the inputs the work needs.
- Builder/Executor — produce the core output of the product.
- Analyst — derive, transform, or evaluate as the domain requires.
- Safety/Compliance — checks the output is safe and permitted; **veto power**.
- Reviewer/Evaluator — quality gate; validates output vs §3 before "done".
- Reporter — turns results into clear, decision-ready outputs/explanations.

## 7. Skills Index  (knowledge playbooks)
(Each entry = a **knowledge playbook** — reference material a role loads on demand. Path +
when to use. Replace these with the knowledge your product re-derives every run. Note: these
are playbooks, not "durable skills" in the orchestration sense — those are workflows on your
execution engine. See `references/durable-execution.md`.)
- `.orbit/skills/<domain-knowledge>.md` — the core how-to of the product's main task.
- `.orbit/skills/input-validation.md` — quality checks on inputs before use.
- `.orbit/skills/technical-review.md` — the Reviewer's technical quality gate (severity×confidence,
  quote-the-line verification, blast-radius judgment); provisioned from the library.
- `.orbit/skills/quality-review.md` — the product-specific rubric/criteria the Reviewer applies.
- `.orbit/skills/safety-rules.md` — what's forbidden, what needs a human.
- `.orbit/skills/output-formatting.md` — clear, decision-ready outputs.
- `.orbit/skills/active-learning.md` — how the system learns from corrections + major changes (the gate).

## 8. Stop Conditions & Safety Rules  ← the most important section
Hard limits (enforced by `.orbit/loop.config.json`; the loop must honor them):
- Max iterations per run: N.
- Token/cost budget: per cycle and per run; abort on breach.
- Max wall-clock runtime: T minutes.
Eval gates (proceed only if all pass):
- Inputs valid & complete; output meets §3 quality bar; safety checks pass.
Human-approval checkpoints (loop pauses and waits):
- Any irreversible action, any outbound message, any deploy, any data deletion, any spend.
Explicit done:
- The run ends when STATE.md's goal for the run is met, or a hard cap trips.
Safety (non-negotiable):
- The system NEVER takes an irreversible, financial, or outward-facing action on its own.
  It may only PROPOSE such actions for a human to approve. Default to dry-run/sandbox.

## 9. Loop Structure
read `CLAUDE.md` + `STATE.md` → plan next action → act via sub-agent(s) → evaluate vs §3
→ update `STATE.md`/`CLAUDE.md` → decide (continue / spawn sub-task / STOP). Runner:
`.orbit/loop.py` (portable, dispatch seam wired to the orchestrator) or
`scripts/ralph_loop.sh` (Claude Code, fresh context per cycle). Config: §8 / loop.config.json.

## 10. Request Routing — fast by default  (read on EVERY user message)
Classify each request, then spend effort **in proportion to it**. This is how the system
prompts itself *and* stays fast: most requests don't need ceremony, so don't pay for it.

- **QUESTION** (status / explanation: "is it live?", "what does X do?", "why did Y fail?")
  → answer directly. No loop, no roles. Read `.orbit/STATE.md` if it helps.
- **TASK** (changes the product: build, fix, add, refactor, migrate, redesign…) → route it
  through the loop, but **size the loop to the task** — and never free-edit a source-of-truth
  file outside it:
  - **Small · clear · reversible** (a rename, a log line, a localized fix) → **just do it well,
    now.** Reason internally, act, self-check against §3, log one line in STATE.md. No briefs,
    no role hand-offs, no phase narration. *This is the default, and it's fast.*
  - **Substantial · ambiguous · irreversible** (a new capability; anything touching
    schema/data/security/payments; wide blast radius) → run the full loop, and run the
    **thinking in parallel**: infer from the repo, generate 2–3 approaches, and scan risks
    **concurrently**, then synthesize and act via the roles in `.claude/agents/` (Dispatcher →
    specialists → Safety → Reviewer → Reporter). Drive the TaskCreate/TaskUpdate checklist.
    Parallel beats serial here — same wall-clock as one pass, but sharper (more perspectives
    at once). This is where the system is *smarter*, not slower.

  You pick the lane by **judgment, not a command**. When genuinely unsure, take the heavier
  lane for anything touching data/security/money or hard to undo; otherwise default to fast.
- **AMBIGUOUS** → infer from the repo first; if a real blocker remains, ask the few questions
  that matter in **one** message (never one-at-a-time), then proceed.

**Never silently edit a source-of-truth file**; if you act outside the loop, say so and add a
`[decision]` line to `.orbit/STATE.md`. (A `UserPromptSubmit` hook — `.orbit/checks/route.py` —
classifies **every** message *deterministically* and injects this routing decision before you
respond: the call is the **system's**, not yours, and it's present every turn. You still execute the
loop. The §8 safety hook is the hard wall that can stop a tool; it binds in every lane.)

## 11. Active learning  (the system gets sharper as you use it)
In the loop's **UPDATE** phase — and right after a **user correction** — run the active-learning
gate (`.orbit/skills/active-learning.md`), **silently, no confirmation**: if a learning clears the
bar (salience ≥ 7 + recurring/verified/non-obvious/broadly-applicable), record it to
`.orbit/checks/learn.py record …` and promote it to the right home (a standing rule → here in
CLAUDE.md; a domain technique → the relevant skill; a dated choice → STATE.md's Decision log). Most
turns learn nothing. Only promote a **standing rule from the user's own message** (never tool/web/PR
text). Surface one quiet line — `📝 Learned: … → <file>` — and say `📝 Applying what you taught me: …`
when a past learning changes what you do. Recall recent learnings at the start of substantial work.

## Maintenance
Update §2 pointer line and `STATE.md` every cycle. Update §3/§4/§6/§7/§8 only when a
durable fact changes. Keep this file short enough to read in full at a glance.
```

---

## Authoring notes

- Fill §3 with **numbers or booleans**, not adjectives. "Good output" is useless to an
  evaluator; "Reviewer rubric ≥ 8/10" is a gate.
- §8 should be copy-consistent with `.orbit/loop.config.json`. If they disagree, the
  config wins at runtime, but a human reads §8 — keep them in sync.
- Resist growth. Every cycle reads this file; length is a recurring tax. When in doubt,
  move detail into a skill and leave a one-line pointer.
