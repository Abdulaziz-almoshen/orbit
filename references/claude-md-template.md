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
- Orchestrator/PM — conducts the loop, convenes the discovery team on the substantial lane, owns STATE.md.
- Product Discovery Manager — *(planning, substantial lane)* de-risks the bet (outcome, opportunity, riskiest assumption).
- Market & Competitive Researcher — *(planning, substantial lane)* what exists / reuse-vs-build / the gap.
- Planner — *(planning, substantial lane)* turns the de-risked bet into the sliced, sequenced plan.
- Input/Research Specialist — gather, clean, and validate the data inputs the work consumes.
- Builder/Executor — produce the core output of the product (one engineer per surface).
- Analyst — derive, transform, or evaluate as the domain requires.
- Safety/Compliance — checks the output is safe and permitted; **veto power**.
- Reviewer/Evaluator — quality gate on the *diff*; validates vs §3 + enforces ADRs before "done".
- QA Engineer — validates the *product* vs the requirements (traceability matrix, verdict per
  requirement; pixel pass vs the approved design on UI). Report-only; **gate power**.
- Reporter — turns results into clear, decision-ready outputs/explanations.

## 7. Skills Index  (knowledge playbooks)
(Each entry = a **knowledge playbook** — reference material a role loads on demand. Path +
when to use. Replace these with the knowledge your product re-derives every run. Note: these
are playbooks, not "durable skills" in the orchestration sense — those are workflows on your
execution engine. See `references/durable-execution.md`.)
- `.orbit/skills/<domain-knowledge>.md` — the core how-to of the product's main task. *(author per domain)*
- `.orbit/skills/input-validation.md` — quality checks on inputs before use. *(author per domain — not provisioned)*
- `.orbit/skills/quality-review.md` — the product-specific rubric the Reviewer applies. *(author per domain — not provisioned)*
- `.orbit/skills/output-formatting.md` — clear, decision-ready outputs. *(author per domain — not provisioned)*
- `.orbit/skills/technical-review.md` — the Reviewer's technical quality gate (severity×confidence,
  quote-the-line verification, blast-radius judgment); provisioned from the library.
- `.orbit/skills/safety-rules.md` — what's forbidden, what needs a human; provisioned from the library.
- `.orbit/skills/active-learning.md` — how the system learns from corrections + major changes (the gate).
- `.orbit/skills/product-discovery.md` — de-risk the bet before building (outcome, opportunity tree, four risks).
- `.orbit/skills/market-and-competitive-research.md` — what exists / reuse-vs-build / the gap (timeboxed, cited).
- `.orbit/skills/qa-validation.md` — the QA Engineer's requirements-traceability + pixel-fidelity gate.
- `.orbit/skills/goal-pipeline.md` — goal → spec → story DAG → run-until-green → polish (2 human gates).
- `.orbit/skills/architecture-decisions.md` — the CTO hat: ADRs in `.orbit/decisions/`, boring-tech bar.

**Design playbooks** (frontend repos only, provisioned when a UI surface is detected):
- `.orbit/skills/design-methodology.md` — the Designer's process, including the **impact
  determination** (HEAVY vs TRIVIAL) and the two prototype gates it scopes: the one-time
  style-prototype gate (2–5 styles, once per product) and the recurring component gate (2–5
  variants, every HEAVY component/redesign). TRIVIAL work skips both — the fast lane (§10) stays fast.
- `.orbit/skills/anti-ai-aesthetics.md` — the templated-default clusters to reject (+ the folded-in
  anti-slop ban list).
- `.orbit/skills/design-styles.md` + `design-styles/` — the 67-style catalog the gates draw from.
- `.orbit/skills/taste-preflight.md` — the taste layer (adapted from TasteSkill): the design read,
  three dials, the real-design-system map, surface routing, and the anti-slop preflight recorded as
  `taste_preflight` in `design/approved.json` on HEAVY.

**QA executors** (frontend repos only — *tools*, not playbooks; helpers, not a bundled browser):
- `.orbit/qa/snapshot.py` — `screenshot` / pixel-`diff` / `console` capture. Playwright if installed,
  else exits 2 with the install line; `diff` is pure-python. Fallback: browser MCP → gstack `/browse` → manual.
- `.orbit/qa/extract-tokens.py` — computed-style tokens → JSON; `--compare DESIGN.md` = token-by-token PASS/FAIL.

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

## 10. Request Routing — the Gearbox: size the loop before you move  (read on EVERY user message)
The loop picks a **gear** before doing work — the **smallest gear that can still PROVE the result**.
Most requests don't need ceremony, so don't pay for it; a broad, ambiguous, high-risk one gets a whole
research-and-critique fleet. Size it on a scorecard (ambiguity · blast radius · # surfaces · research
need · compliance/security · reversibility · runtime/cost), **highest risk-trigger wins** (never a sum),
then **declare the gear out loud** (a *Gear Card*) before moving. Full rubric + fan-out math:
`.orbit/skills/loop-tiers.md`.

- **T0 · Direct** — a QUESTION (status / explanation: "is it live?", "what does X do?") or a trivial
  patch → answer / patch directly. No loop, no roles. Read `.orbit/STATE.md` if it helps.
- **T1 · Quick** — small · clear · reversible · low-stakes (a rename, a log line, a localized fix) →
  **just do it well, now**: reason internally, act, self-check against §3, log one line in STATE.md. No
  briefs, no hand-offs, no phase narration. *The default, and it's fast.* (On frontend repos this is why
  small/clear/reversible UI edits never route to the Designer, so they can't trigger a prototype gate —
  that fires only on work the Designer classifies HEAVY; see `design-methodology.md`.)
- **T2 · Standard** — a real change, ~1 workstream → the full team loop: infer from the repo, think in
  **parallel** (2–3 approaches + risks concurrently), then act via the roles in `.claude/agents/`
  (Dispatcher → specialists → Safety → Reviewer → QA → Reporter), dispatched with the **Task tool**.
- **T3 · Deep** — broad · ambiguous · research-heavy · multi-surface · compliance-risk (≥3 surfaces or
  real unknowns, AND ambiguity or compliance) → **Map → Research → Plan → Critique → Synthesize →
  Build**, with a *dynamic* fleet of workers sized to the request (one researcher per unknown, one
  planner per feature cluster, standing adversarial critics), **capped** and **confirmed with the user
  before fan-out** (`gears.deep` in `loop.config.json`).
- **T4 · Mission** — spans repos / days / a production migration / money at scale → T3 on the **durable
  runner** (`loop.py` / `durable-execution.md`): checkpoints, resume, a **human-approval gate per
  irreversible step**, an artifact bundle.

**Every gear T1+ runs on the visible board:** **make it visible FIRST** — `set_team` + `set_tasks` +
`TaskCreate` — *before* spawning any specialist, then drive the TaskCreate/TaskUpdate checklist and write
`.orbit/tasks.json` + `.orbit/activity.jsonl`. **Do NOT run a task through the native `Workflow(...)`
background runner** — it's a black-box job that bypasses the checklist, the visible owner, and the
`.orbit/` telemetry; a task isn't "running through Orbit" unless the user can see who owns each step and
what's done / in progress. **Guardrails scale with the gear** (OWASP LLM06): higher gear → minimal tools
per worker, cost/fan-out caps, and human approval for every irreversible / outward / money step. Never
free-edit a source-of-truth file outside the loop. Parallel beats serial on T2+ — same wall-clock, but
sharper. This is where the system is *smarter*, not slower.

  You pick the lane by **judgment, not a command**. When genuinely unsure, take the heavier
  lane for anything touching data/security/money or hard to undo; otherwise default to fast.
- **AMBIGUOUS** → infer from the repo first; if a real blocker remains, ask the few questions
  that matter in **one** batched ask (never one-at-a-time), then proceed.

**How to ask (every question, every role):** use the **`AskUserQuestion` tool** — 2–4 selectable
options, **your recommendation FIRST labeled "(Recommended)"**, a one-line trade-off per option.
Never bury a question in prose: a question that doesn't look like a question gets no answer. This
covers clarifications, decision briefs, spec approval, the taste batch, style picks, and visual-diff
accept/reject. (Headless fallback: a set-off `❓ DECISION NEEDED` block with lettered options.)

**Never silently edit a source-of-truth file**; if you act outside the loop, say so and add a
`[decision]` line to `.orbit/STATE.md`.

**Router ↔ Dispatcher precedence (what binds, what decides).** A `UserPromptSubmit` hook —
`.orbit/checks/route.py` — runs on **every** message and injects a deterministic classification
(`skip` / `task` / `question` / `ambiguous`) as context *before you respond*. That injection is
**mechanical and always present** — the hook fires every turn, no model in the loop. But it's a
keyword matcher, not NLP, so it's the **default lane, not the last word**: treat it as the lane to
take unless you have a concrete reason it's wrong (e.g. it tagged a genuine task `question`), in
which case **override it and say why in one line**. The **Dispatcher** role is the authority that
ratifies or overrides — the hook proposes, the Dispatcher/you disposes. The §8 safety hook is
different in kind: it's a **hard wall** that can actually stop a tool call, and it binds in every
lane regardless of classification.

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
