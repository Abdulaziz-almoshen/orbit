---
name: orbit
description: >-
  Transform any product repository into a production-grade, self-prompting agentic
  loop system following Daisy Hollman's "build a system that prompts itself"
  methodology. Audits the current project, then scaffolds persistent memory
  (CLAUDE.md + STATE files), a specialized sub-agent team, domain skills, a
  read→act→evaluate→update→decide loop, and HARD stop conditions (iteration/cost/
  runtime caps, eval gates, human-approval checkpoints). Produces a model-agnostic
  core PLUS a Claude Code adapter, so the loop can run on your own orchestrator
  (e.g. Gemini) or via headless `claude -p`. Domain-agnostic: it characterizes
  whatever product it runs in and fits the system to it. Use this skill whenever the
  user wants to set up, upgrade, or "productionize" an autonomous agent / agentic
  loop / self-prompting system, build an orchestrator, add a sub-agent team or
  persistent memory, or mentions Daisy Hollman, "a system that prompts itself",
  "Ralph loop", agentic SDLC roles, or stop conditions for a runaway agent.
---

# Orbit — install a self-prompting system into a repo

## Preamble — run this first (update check)

Before doing anything else, check whether a newer version of this plugin is available, the
same way gstack does. Run:

```bash
_UPD=""
for _p in "${CLAUDE_PLUGIN_ROOT:-}/bin/orbit-update-check" \
          "$HOME/.claude/skills/orbit/bin/orbit-update-check" \
          ".claude/skills/orbit/bin/orbit-update-check"; do
  if [ -x "$_p" ]; then _UPD="$("$_p" 2>/dev/null || true)"; break; fi
done
[ -n "$_UPD" ] && echo "$_UPD" || true
```

Then:
- If the output is `UPGRADE_AVAILABLE <old> <new>`: read `skills/orbit-upgrade/SKILL.md`
  and follow its **Inline upgrade flow** (auto-upgrade if configured, otherwise ask with the
  4 options, or snooze). When that finishes, **continue this skill** from the next section.
- If the output is `JUST_UPGRADED <from> <to>`: say "Running orbit v{to} (just updated!)"
  and continue.
- If there's no output (up to date, throttled, snoozed, or offline): continue silently.

The check is throttled to once per 24h and never blocks — if the script isn't found or the
network is down, it prints nothing and you proceed normally. This preamble is the only
"phone-home"; the rest of the skill is local.

## The one idea everything serves

> "You're not supposed to prompt Claude. You're supposed to build a system that prompts
> itself." — Daisy Hollman

A single human-written prompt is a dead end: it runs once and the context evaporates.
A *system* persists its own state, decomposes its own work, checks its own results,
and decides its own next move — and it does this safely, inside hard limits, with a
human at the gates that matter. Your job when this skill runs is to turn the repo in
front of you into exactly that system.

You are **not** running the loop yourself right now. You are **building the harness**
that will run it. Resist the urge to start "doing the work" of the product. Instead,
lay down the artifacts that let the system do that work repeatedly, on its own, without
you re-typing the prompt each time.

Read `references/methodology.md` once before you start — it distills the principles
so the rest of this skill makes sense.

## What you produce (hybrid output)

Two layers, written into the target repo:

**A. Model-agnostic core** — works with any orchestrator (their own model layer, a cron
job, a CI step):
- `CLAUDE.md` — the single source of truth, read at the start of every cycle.
- `.orbit/STATE.md` — mutable working state (task queue, decisions, blockers) the
  loop writes after every cycle. Kept separate from CLAUDE.md so frequent writes
  don't churn the stable doc.
- `.orbit/roles/*.md` — sub-agent role specs, written so *any* model can adopt them.
- `.orbit/skills/*.md` — domain skills (reusable knowledge the roles load).
- `.orbit/loop.config.json` — the portable contract: stop conditions, eval gates,
  approval checkpoints, budgets.
- `.orbit/loop.py` — a reference runner implementing read→act→evaluate→update→decide
  against `loop.config.json`. Model-agnostic; the dispatch function is a seam you wire
  to the user's orchestrator (e.g. Gemini, or any model/runtime).

**B. Claude Code adapter** — so the same system runs natively here:
- `.claude/agents/*.md` — the roles as Claude Code subagents.
- `.claude/settings.json` hooks — automated validation/notification on key events.
- `scripts/ralph_loop.sh` — an external "Ralph loop" that drives headless `claude -p`
  with **fresh context each cycle**, enforcing the same hard limits.

Bundled templates live in `assets/`; copy and adapt them rather than inventing from
scratch. The deterministic skeleton (directories + static files) can be laid down with
`scripts/scaffold.py`; the bespoke, audit-driven files (CLAUDE.md, STATE.md, roles,
skills) you author yourself.

## Operating procedure

Work in small, verifiable steps. After each phase, briefly tell the user what landed
and what's next. For any non-trivial architectural change, propose the plan before
writing — don't silently restructure their orchestration.

### Phase 0 — Orient and characterize the domain

1. Confirm the working directory and whether it's an existing product or greenfield.
2. **Characterize the domain.** You can't fit a good system to a product you don't
   understand. Read `references/profiles/generic.md` — it's the universal profile and it
   tells you what to elicit. Mine the repo (README, configs, code) for answers first,
   then ask the user only what you couldn't infer:
   - What does the product do, and who is it for?
   - What does a good cycle output look like — ideally something measurable?
   - What's the most expensive mistake the system could make? (this defines the safety
     gate and the human-approval checkpoints)
   - What external systems does it touch? (these become tools and checkpoints)
   If you set this skill up for the same kind of product repeatedly, capture its specifics
   as a new file under `references/profiles/` and reuse it.
3. Detect the stack (language, package manager, how the orchestrator and any external
   APIs are currently called). You'll need this to wire the loop.

### Phase 1 — Audit the current state

Explore the project structure, the existing orchestration code, how external systems and
the model are invoked, and any current state handling. Then summarize for the user:
- **Current architecture** — the real one, in 5–10 bullets.
- **What works well** — keep these; treat reliable integrations as fixed tools.
- **Gaps vs. the methodology** — specifically: persistent memory, sub-agent
  decomposition, packaged skills, and (most important) stop conditions. Be concrete
  about what's missing, not generic.

For a greenfield repo, say so plainly and scaffold fresh from the templates.

### Phase 2 — CLAUDE.md (highest priority)

Create or heavily update `CLAUDE.md` in the repo root from `references/claude-md-template.md`.
This is the file the whole system reads first. Required sections are listed in the
template. Keep it focused and *updatable* — it is memory, not a manual. Push detailed,
rarely-changing rules into skills and hooks; keep CLAUDE.md to overview, current state
pointer, success criteria, conventions, the agent roster, skills index, **stop
conditions**, and the loop shape. If a `CLAUDE.md` already exists, merge — preserve the
user's content, don't clobber it.

Also create `.orbit/STATE.md` from `references/state-template.md` and seed it with the
open tasks you discovered in the audit.

### Phase 3 — Define the sub-agent team

Don't build one big agent. Decompose into specialized roles, following
`references/roles.md`. Keep the *shape* — one planner, several executors, one safety
gate, one quality gate — and rename/scope the roles to the product's real subtasks:
Orchestrator/PM, the specialists this domain needs, Safety/Compliance, Quality
Reviewer/Evaluator, Reporter.

For each role, write a model-agnostic spec to `.orbit/roles/<role>.md` **and** a Claude
Code subagent to `.claude/agents/<role>.md` (the adapter — same responsibilities, Claude
Code frontmatter). Document in CLAUDE.md and in `references/roles.md`'s handoff section
how roles hand off work and how they read/write shared state (`STATE.md`), so the
orchestrator can fan out parallel work without agents stepping on each other.

### Phase 4 — Create domain skills

Package 4–6 high-value, reusable skills into `.orbit/skills/`, drawn from what this
product re-derives or re-explains every run. Ask "what knowledge do we keep re-pasting
into prompts?" — that's a skill. Each skill is knowledge a role loads on demand — keep
them focused. Reference every skill in CLAUDE.md's Skills Index so roles know when to
reach for them.

### Phase 5 — The self-prompting loop + stop conditions

Lay down the loop from `references/loop-design.md`:
1. Copy `assets/loop.config.json` → `.orbit/loop.config.json` and fill in real
   thresholds with the user (caps, eval gates, approval checkpoints).
2. Copy `assets/loop.py` → `.orbit/loop.py` and wire its `dispatch()` seam to their
   orchestrator. Keep it model-agnostic.
3. Copy `assets/ralph_loop.sh` → `scripts/ralph_loop.sh` for the Claude Code path.

The loop is **read → plan → act → evaluate → update → decide**. The non-negotiable part
is the stop conditions — Daisy stressed these to avoid runaway cost and damage. Every
loop ships with, at minimum: a max-iterations cap, a token/cost budget per cycle and per
run, a max-runtime wall clock, eval gates that block progress unless inputs/quality/safety
checks pass, an explicit done signal, and human-approval checkpoints for any high-impact
or outward-facing action. **The system never takes an irreversible, financial, or
outward-facing action on its own — it proposes; a human disposes.** This is baked into
the config and the Safety role; see `references/loop-design.md`.

### Phase 6 — Tools and hooks

Wire integration per `references/hooks-and-tools.md`:
- Keep existing integrations as reliable, well-typed tools; don't reinvent them.
- Add hooks (`.claude/settings.json` for the Claude Code path; event handlers in
  `loop.py` for the portable path) that auto-run validation on key events — e.g. an
  input-validation check after a fetch, a quality gate after an output is produced, a
  notification on key milestones. Hooks are how you enforce rules without bloating
  CLAUDE.md.
- Prefer shelling out to existing, trusted CLIs over rebuilding them.

### Phase 7 — Report and recommend the first run

When the scaffolding is in place, deliver:
1. The new/updated `CLAUDE.md` (show it).
2. The list of sub-agents and skills created (names + one-line purpose each).
3. The loop implementation (the config + the runner, with the dispatch seam called out).
4. A recommended **first autonomous loop to run** and the **exact stop conditions** to
   use for it — start tiny and safe (the smallest useful unit of work, dry-run mode, max
   3 iterations, hard token budget, every checkpoint set to human).
5. Immediate gaps and recommended improvements to the existing orchestration.

Then update `.orbit/STATE.md` and `CLAUDE.md` to reflect what was built — close the
loop on your own work, the same way the system will.

## Guardrails for you, the builder

- **Stop conditions are not optional.** A loop without hard caps is a defect. If the
  user waves them off, install conservative defaults anyway and tell them where to relax.
- **Never wire auto-execution of irreversible or outward-facing actions.** Moving money,
  sending outbound messages, deploys, deleting data — these route through a human-approval
  checkpoint. The loop proposes; a human disposes.
- **Don't clobber existing files.** Merge CLAUDE.md; back up anything you rewrite.
- **Keep CLAUDE.md lean.** When you're tempted to add a long rule, ask whether it
  belongs in a skill or a hook instead.
- **Stay model-agnostic in the core.** The Claude Code adapter is a convenience layer,
  not the foundation. The user runs production on their own orchestrator.

## Reference map

- `references/methodology.md` — the principles and the "why". Read first.
- `references/claude-md-template.md` — CLAUDE.md template + required sections.
- `references/state-template.md` — STATE.md working-memory template.
- `references/roles.md` — the sub-agent team, specs, and handoff protocol.
- `references/loop-design.md` — loop structure, stop conditions, Ralph loop, the
  config contract.
- `references/hooks-and-tools.md` — hook events, tool wiring, CLI-first guidance.
- `references/profiles/generic.md` — the universal profile: how to characterize any
  product and fit the system to it. Add your own profiles here for repeated setups.
- `assets/` — copyable `loop.config.json`, `loop.py`, `ralph_loop.sh`, example subagent.
- `scripts/scaffold.py` — lays down the deterministic skeleton.
