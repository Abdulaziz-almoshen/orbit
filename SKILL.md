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

## Preamble — STEP 0, run this BEFORE anything else (update check)

This is your **first action** the moment `/orbit` loads — before you read the repo, plan, respond,
or run any other phase. **Do not skip it. Do not batch it after other work.** Run exactly this one
block (it finds `orbit-preamble` whether Orbit is a user skill or a marketplace plugin, and falls
back to an inline resolver if that script is missing):

```bash
for _p in "${CLAUDE_PLUGIN_ROOT:-}/bin/orbit-preamble" \
          "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills/orbit/bin/orbit-preamble" \
          "$HOME/.claude/skills/orbit/bin/orbit-preamble" \
          ".claude/skills/orbit/bin/orbit-preamble"; do
  [ -x "$_p" ] && { "$_p"; exit 0; }
done
# fallback: older install without orbit-preamble — resolve orbit-update-check inline
_UPD=""; _DIR=""; _CC="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
for _p in "${CLAUDE_PLUGIN_ROOT:-}/bin/orbit-update-check" \
          "$_CC/skills/orbit/bin/orbit-update-check" \
          "$HOME/.claude/skills/orbit/bin/orbit-update-check" \
          ".claude/skills/orbit/bin/orbit-update-check"; do
  if [ -x "$_p" ]; then _UPD="$("$_p" 2>/dev/null || true)"; _DIR="$(dirname "$(dirname "$_p")")"; break; fi
done
_VER="$(tr -d '[:space:]' < "${_DIR:-.}/VERSION" 2>/dev/null || echo '?')"
echo "${_UPD:-orbit v$_VER (up to date / not re-checked within 24h)}"
```

Then act on the line it printed — and **always say one line back so the user can see the check ran**:
- `UPGRADE_AVAILABLE <old> <new>` → read `orbit-upgrade/SKILL.md` and follow its **Inline upgrade
  flow**. The default posture is auto-upgrade, but on the **first** upgrade with no saved choice it
  **asks once** (`auto_upgrade` consent) and then honors that silently forever after. When done,
  **continue this skill** from the next section.
- `JUST_UPGRADED <from> <to>` → say "Running orbit v{to} (just updated!)" and continue.
- `orbit v<x> …` (the fallback line) → say "Running orbit v{x}." once, then continue.

The script checks the latest **VERSION on GitHub** (`git fetch` if the install is a git clone, else
a `curl` to raw GitHub), is throttled to **once / 24h**, and **never blocks** — offline / throttled /
snoozed just yields the version line. Be honest in your one-liner: a fallback line means "running
v{x}", not a guaranteed fresh check. This preamble is the only "phone-home"; the rest is local.

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

## In plain language (tell the user this up front)

Most people who run `/orbit` are not experts in agent frameworks. Before the jargon, say
the gist in one breath and name the few files that matter:

> "I'm going to set this repo up to do repeatable work by itself, safely. Three files
> matter: **CLAUDE.md** (the plan + the rules), **.orbit/STATE.md** (live progress), and
> **.orbit/loop.config.json** (the limits — how many steps, how much it can spend, what it
> may never do). Everything else is detail you can ignore until you need it. Nothing runs
> on its own and nothing risky happens without you — and you can undo all of it."

**The shape of every loop (one line):** *trigger → action → proof → memory → stop.* What
kicks it off, what it does, the **proof** it actually worked, what it remembers, and when it
halts. If a loop is missing its "proof" or its "stop," it isn't done. Keep this in mind for
every loop you set up.

Five terms you'll use — gloss each the first time, in one line:
- **loop** — one pass of: read state → do a small step → check it → write down what happened → decide whether to continue or stop.
- **role / sub-agent** — a specialist with one job (gather inputs, build, check safety, review quality). Keeps each step focused.
- **gate** — a check the output must pass to count as progress (a quality bar; a safety OK).
- **stop condition** — a hard brake: max steps, max spend, max time, or a forbidden action.
- **step / checkpoint** — one recorded unit of work. Checkpointing it means a crash resumes from the last completed step instead of redoing (and re-paying for) everything.
- **dispatch** — the one function in `loop.py` you'd wire to your own model (e.g. Gemini) to run the loop *off* Claude. Until you do, it's a stub.

Note on the word **"skill"**: Orbit's `.orbit/skills/*.md` are **knowledge playbooks** — reference
material a role loads. That's different from the industry's "durable skill" (a retryable
*workflow* on an orchestrator). Orbit installs the playbooks; the durable workflows live on
the execution engine. See `references/durable-execution.md`.

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
  to the user's orchestrator (e.g. Gemini, or any model/runtime). It checkpoints steps
  (`.orbit/steps.jsonl`) so `loop.py --resume` survives a restart. `ralph_loop.sh` is the
  **dev** runner; for durable production, run on an engine — see
  `references/durable-execution.md` + the template `assets/runners/inngest-loop.ts`.
- `.orbit/activity.py` + `scripts/orbit-status` — the **observability layer**: every role
  emits "who's talking" events to `.orbit/activity.jsonl` and a checklist to
  `.orbit/tasks.json`, and `orbit-status --follow` renders a live dashboard (current
  speaker + phase + the checklist crossing itself off). See `references/observability.md`.

**B. Claude Code adapter** — so the same system runs natively here:
- `.claude/agents/*.md` — the roles as Claude Code subagents.
- `.claude/settings.json` hooks — automated validation/notification on key events.
- `scripts/ralph_loop.sh` — an external "Ralph loop" that drives headless `claude -p`
  with **fresh context each cycle**, enforcing the same hard limits.
- **Native live checklist via TaskCreate/TaskUpdate** — inside Claude Code, mirror `.orbit/tasks.json`
  into the built-in TaskCreate/TaskUpdate tool (each item prefixed with its owning role, e.g.
  `[data] validate inputs`) so you get the pinned, auto-crossed-off list; each role
  announces itself `[role] …` so the transcript shows who's talking.

Bundled templates live in `assets/`; copy and adapt them rather than inventing from
scratch. The deterministic skeleton (directories + static files) can be laid down with
`scripts/scaffold.py`; the bespoke, audit-driven files (CLAUDE.md, STATE.md, roles,
skills) you author yourself.

## Operating procedure

Work in small, verifiable steps. After each phase, briefly tell the user what landed
and what's next. For any non-trivial architectural change, propose the plan before
writing — don't silently restructure their orchestration.

**Fast path — the skeleton is a script, not an essay.** Almost everything Orbit installs is
*identical every time*, so a single `scaffold.py` run writes it (Phase 2) — you do **not**
hand-author it file-by-file. Your only real work is the *project-specific* parts: characterizing
the repo, authoring `CLAUDE.md`, and writing the one domain skill. **Do not read Orbit's reference
docs to "build" the scaffold** — the script owns the structure. The only references you may need
are `profiles/generic.md` (to infer the domain) and `claude-md-template.md` (to write CLAUDE.md);
skip `methodology`/`roles`/`loop-design`/`observability`/`durable-execution` unless you're
customizing that exact piece. This is what keeps setup **under a minute instead of ten** — and it
matches how mature tools (gstack, spec-kit, BMAD) scaffold: a deterministic script for the
skeleton, the model only for the project-specific spec.

### Phase 0 — Orient and characterize the domain (infer first; ask only what you can't)

Setup must feel like gstack: smooth, near-zero questions. **Inference is the default; asking
is the fallback.** Interrogating the user with four questions is a failure mode.

1. **If `.orbit/setup.json` exists**, read it and reuse those answers — don't re-ask on a
   re-run. (Write it at the end of setup: the domain characterization + any choices.)
2. **Mine the repo and INFER** product, goal, "most expensive mistake," and integrations
   from README, package manifests (package.json, *.csproj, requirements.txt…), config, and
   code. Read `references/profiles/generic.md` for what to look for.
   - **Detect the distinct technical SURFACES — this determines the team, deterministically.** Look
     for: a **web frontend** (React/Vue/Svelte/Next/Tailwind, `.tsx`/views), a **mobile app** (React
     Native/Expo, Swift/iOS, Kotlin/Android, Flutter), a **backend/api** (server framework, routes,
     DB), a **data** layer (pipelines/ETL/notebooks), a **cli**. A repo can have several at once.
     **Pass exactly what you find to `scaffold.py --surfaces <list>`** (Phase 2) — it provisions one
     engineer per surface (`frontend-engineer`/`mobile-developer`/`backend-engineer`/`data-engineer`)
     and the **Designer only if a UI surface (web/mobile)** is present. This is what makes the roster
     fit the project rather than a fixed template. (No surface detected → a single generic `builder`.)
3. **Then decide:**
   - **Existing product, enough inferred** → ask **nothing**. State your inferred
     characterization in one short paragraph "I read the repo as: <…> — correct me if wrong"
     and proceed. The user corrects only if needed.
   - **Greenfield / EMPTY repo** (nothing to read) → ask the **one** product question ("what are
     you building / what's a good outcome"), batched into a **single** AskUserQuestion. Then
     **derive the surfaces from the answer + the stack they pick** and pass them to `--surfaces` —
     the team comes from *intent*, not the (empty) code. E.g. "a recipe app for iPhone with a sync
     backend" → `--surfaces mobile,api` → `mobile-developer` + `backend-engineer` (+ Designer for the
     mobile UI). "An internal dashboard" → `--surfaces web,api`. Don't ask plumbing questions; infer
     the surfaces from the product answer.
   - **Non-interactive / headless / no answer / truly unknown** → scaffold with **empty `--surfaces`**
     (a single generic `builder`, no Designer) and proceed — never hang. The user can re-run `/orbit`
     with the real surfaces once the product is known; it won't overwrite.
4. Detect the stack (language, package manager, how the orchestrator and any external APIs
   are called) — purely by reading; this is never a question.

The bar: a typical existing repo gets **0 questions**; a blank greenfield repo gets **1**.
If you set Orbit up for the same kind of product repeatedly, capture it as a new file under
`references/profiles/` and reuse it.

### Phase 1 — Audit the current state

Explore the project structure, the existing orchestration code, how external systems and
the model are invoked, and any current state handling. Then summarize for the user:
- **Current architecture** — the real one, in 5–10 bullets.
- **What works well** — keep these; treat reliable integrations as fixed tools.
- **Gaps vs. the methodology** — specifically: persistent memory, sub-agent
  decomposition, packaged skills, and (most important) stop conditions. Be concrete
  about what's missing, not generic.

For a greenfield repo, say so plainly and scaffold fresh from the templates.

### Phase 2 — Lay the deterministic skeleton (ONE command — don't hand-build it)

Run the scaffolder. It writes the whole identical-every-time skeleton in one shot — the engine
(`loop.config.json`, `loop.py`, `activity.py`, `ralph_loop.sh`, `orbit-status`, `guard.py`, `route.py`),
`.orbit/STATE.md`, the skill-library playbooks into `.orbit/skills/`, and the **full standard
team** to both `.claude/agents/*.md` (adapters) and `.orbit/roles/*.md` (specs):

```bash
# resolve Orbit's root whether it's a marketplace plugin or a skills-dir clone:
ORBIT="${CLAUDE_PLUGIN_ROOT:-${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills/orbit}"
python3 "$ORBIT/scripts/scaffold.py" --target . --surfaces <detected> [--install-hooks]
```

- **`--surfaces`** is the key flag — pass the surfaces **you detected in Phase 0** (comma-separated:
  `web`, `mobile`, `api`/`backend`, `data`, `cli`). The scaffolder then provisions the **team that fits
  this project, deterministically**: **one engineer per surface** (`frontend-engineer`,
  `mobile-developer`, `backend-engineer`, `data-engineer`) **and the Designer + design playbooks only if
  there's a UI surface** (web/mobile). A backend API repo → `--surfaces api` → a `backend-engineer`, no
  designer. A web+mobile+API product → `--surfaces web,mobile,api` → three engineers + designer. No
  surfaces detected → a single generic `builder`. (Empty `--surfaces` is allowed; `--frontend` still
  works as an alias for `--surfaces web`.)
- Add **`--install-hooks`** to wire the safety hooks now (or leave it for Phase 6a).
- It **never overwrites** — existing files are left untouched and reported, so a re-run is safe.
  The **one exception is a security migration**: a repo scaffolded before 0.23.0 has a `guard.py`
  whose blocks Claude Code silently ignored and a `route.py` that crashed the dashboard — the
  scaffolder replaces those *known-old* files (backing each up + announcing it), and only *warns*
  (never clobbers) if you'd edited them. Tell the user plainly when this fires.

This replaces hand-authoring ~20 files. The **universal spine** (dispatcher, orchestrator,
product-discovery, market-researcher, planner, reviewer, qa-engineer, reporter, safety-gate) is the same every
project; the **specialists vary by the code** (the per-surface engineers + the conditional Designer).
Everything is in place and working — **don't re-author any of it.**

### Phase 3 — Author CLAUDE.md (the one bespoke file)

This is the single file the model writes by hand — the project-specific spec the whole system
reads first. Create or merge `CLAUDE.md` in the repo root from `references/claude-md-template.md`.
Keep it focused and *updatable* — it's memory, not a manual: overview, current-state pointer,
**§3 success criteria**, conventions, the agent roster (the scaffolded team), skills index,
**§8 stop conditions**, the loop shape, and **§10 Request Routing**. If a `CLAUDE.md` already
exists, **merge — preserve the user's content, don't clobber it.**

**Always write §10 "Request Routing"** — it's what makes Orbit a task router (fast by default:
small/clear/reversible → just do it; substantial/ambiguous/irreversible → the full loop) rather
than a one-shot installer. (Advisory — the model follows it; the only hard wall is the §8 safety
hook. Say so in the summary.)

The scaffolder already wrote `.orbit/STATE.md` — seed it with the open tasks from your audit. At
the end of setup, write `.orbit/setup.json` (the inferred characterization + any choices) so a
re-run doesn't re-ask.

### Phase 4 — Customize the team to THIS project (don't recreate)

The standard team + library playbooks are already in place from Phase 2. Make them *fit the
project* — quickly, not from scratch:

- **Engineers are already provisioned per surface (deterministically, from `--surfaces`).** The
  scaffolder wrote one engineer per detected surface (`frontend-engineer` / `mobile-developer` /
  `backend-engineer` / `data-engineer`) and the Designer iff a UI surface — so the roster already fits
  the project, not a template. Your only job: **verify they match the repo** (add one if a surface was
  missed; you forgot a `--surfaces` value → just re-run with it, it won't overwrite) and **point each
  engineer at its domain skill**. They run in **parallel** — the Planner fans work out to them.
- **Keep only what the project needs; scale to size.** The Designer exists *iff* there's a UI
  surface (a web/mobile `--surfaces`). A tiny prototype stays lean (dispatcher, planner, one engineer,
  reviewer, safety, reporter); a bigger system earns the full bench (an engineer per surface, plus
  an Input/Research or Analyst role when the work genuinely needs one). Don't provision roles a
  one-person prototype won't use — match the team to the product, not a fixed template.
- **The discovery team** (Product Discovery Manager · Market & Competitive Researcher · Planner) is
  scaffolded as part of the standard roster, but it's **convened only on the substantial planning
  lane** — the Orchestrator spins it up for new/ambiguous/value-uncertain work and **folds it back
  into itself** on a small/medium task. So it costs nothing on routine work but is there when a real
  bet needs de-risking. On a tiny throwaway prototype you may drop the trio and let the Orchestrator
  plan directly.
- **Write the domain skills** — the core how-to this product re-derives every run ("what do we keep
  re-pasting into prompts?"). Start with the **one** that matters most; add others only for a
  genuinely distinct body of knowledge, and **author them concurrently** (fan out, don't write them
  one after another) so setup stays fast. Index each in CLAUDE.md's §7.

Record the final roster (each agent's project-specific name + what it's for + which skill it loads) —
Phase 7 introduces them to the user.

### Phase 5 — Tune the loop config (already placed)

The scaffolder placed `loop.config.json`, `loop.py`, and `ralph_loop.sh`. Your job is only to
**fill real thresholds** in `.orbit/loop.config.json` with the user (caps, eval gates, approval
checkpoints) and wire `loop.py`'s `dispatch()` seam to their orchestrator.

The loop is **read → plan → act → evaluate → update → decide**. The non-negotiable part is the
stop conditions — Daisy stressed these to avoid runaway cost and damage. Every loop ships with, at
minimum: a max-iterations cap, a token/cost budget per cycle and per run, a max-runtime wall
clock, eval gates that block progress unless inputs/quality/safety checks pass, an explicit done
signal, and human-approval checkpoints for any high-impact or outward-facing action. **The system
never takes an irreversible, financial, or outward-facing action on its own — it proposes; a human
disposes.** This is baked into the config and the Safety role; see `references/loop-design.md` only
if you're changing the loop's shape.

### Phase 6 — Tools and hooks

Wire integration per `references/hooks-and-tools.md`:
- Keep existing integrations as reliable, well-typed tools; don't reinvent them.
- Add hooks (`.claude/settings.json` for the Claude Code path; event handlers in
  `loop.py` for the portable path) that auto-run validation on key events — e.g. an
  input-validation check after a fetch, a quality gate after an output is produced, a
  notification on key milestones. Hooks are how you enforce rules without bloating
  CLAUDE.md.
- Prefer shelling out to existing, trusted CLIs over rebuilding them.

### Phase 6a — Install the always-on hooks (the binding layer + the router)

The most important phase, and the one most setups skip. Hooks are the only Orbit layer that runs
**regardless of what the model decides** — Claude Code runs them itself. Orbit installs **two**, by
default, as part of setup:

- **`PreToolUse` → `.orbit/checks/guard.py`** — the **safety wall.** Runs before a tool call; if it
  returns `deny`, the tool never executes. This is the line between a guarantee and a suggestion.
- **`UserPromptSubmit` → `.orbit/checks/route.py`** — the **router.** Runs on **every user message**
  before the model responds. *The system* classifies it (task → loop, question → answer) and injects
  that decision as a live instruction. This is what makes Orbit **control the project** — routing is
  no longer a passive §10 rule the model may ignore; the classification is the system's, and the
  directive is forced into context every turn. (See `references/hooks-and-tools.md` → "Enforcement vs
  suggestion.")

Install **both by default — no question — but never silently.** A floor the user opts into is a
floor most users skip. Wire them as part of setup and **announce exactly what you did.** (The
original footgun wasn't "installed without a prompt" — it was "installed *silently* with no findable
off-switch." Announce + easy removal fixes that.)

1. `.orbit/checks/guard.py` ships hardened defaults that already `deny` force-push / `push --mirror`
   / `rm -rf` of a root-or-system path / disk wipes and `ask` before a plain push / `reset --hard` /
   `clean -f` / `curl | sh` (and sees through subshells, `sh -lc`, env-prefixes, substitutions). **Add
   this repo's own rules** to the `RULES` block — `deny` its irreversible/forbidden actions (a
   secret-branch push, a frozen-schema migration), `ask` its reversible-but-risky ones (a deploy).
   Parse argv precisely; don't loosen the defaults. `route.py` works out of the box; tune its verb
   lists only if the domain has unusual phrasing.
2. **Wire both by default** — run `python3 "$ORBIT/scripts/scaffold.py" --target . --install-hooks`
   (with `ORBIT` resolved as in Phase 2; or, in the same `scaffold.py` run from Phase 2, just pass
   `--install-hooks` then). It backs up `.claude/settings.json`, merges each hook idempotently, and
   prints the exact JSON.
3. **Announce them, plainly:** "Installed two always-on hooks — a **safety wall** (denies <deny
   list>, asks before <ask list>) and a **router** (classifies every message → task routes through
   the loop, question is answered directly). Active on your **next message/command — no restart
   needed**. Remove anytime with `orbit-uninstall`."
4. If `.orbit/setup.json` records that the user previously removed a hook, **don't re-add silently** —
   mention it and let them decide.

This is what makes "Orbit controls the project" true rather than aspirational. **Honest scope:** the
guard *binds* (it can stop a tool); the router *decides and injects* deterministically every turn (the
system, not the model) — but the model still **executes** the loop, because a hook can't run the
sub-agent team itself. So routing went from "advisory text" to "system-decided + force-injected each
message," which is the real fix for triggering — short of the model literally being unable to ignore
it. Both hooks **fail open** (a bug never bricks the shell or blocks a prompt).

### Phase 6.5 — Make the loop watchable (observability)

A loop you can't watch is a loop nobody trusts. The scaffolder already placed the observability
layer (`.orbit/activity.py` + `scripts/orbit-status`) — you *use* it. The pinned task list and the
terminal dashboard are **surface-specific** (they show in the Claude Code IDE/CLI). In the **Claude
desktop app and claude.ai web**, there's no pinned panel and no terminal — so the only thing the
user sees is **what you print in chat.** Therefore **do THREE things every cycle:**

1. **ALWAYS write `.orbit/tasks.json` + `.orbit/activity.jsonl`** (via `.orbit/activity.py`'s
   `set_tasks` / `update_task` / `emit`). The data floor — never depends on a UI being present.
2. **ALWAYS render the "team board" inline in your reply** — this is the **universally visible**
   path (desktop app, web, terminal, IDE — anywhere, because it's just text). A compact markdown
   block with emoji role colors matching the dashboard, refreshed each cycle:
   ```
   🛰 Orbit · cycle 2
   ✓ 🟣 planner — planned the change
   ✓ 🟢 frontend-engineer — built the form
   ▸ 🟡 reviewer — proving it (running tests)…
   ○ 🔴 safety · ○ ⚪ reporter
   ```
   (🔵 dispatcher · 🟣 planner · 🔭 discovery · 📊 market · 🟢 engineer · 🟪 designer · 🟡 reviewer · 🧪 qa · 🔴 safety · ⚪ reporter — same
   colors as `orbit-status`.) **The board also carries the team's voice** — a one-line "why this task
   matters" at kickoff, a progress-aware "your team's heads-down — N of M done, almost there" during
   the pause, and an earned close on completion. Mandatory; warm and genuine, tone calibrated to the
   task (serious for governance/security/money), varied, never filler. See `observability.md` →
   "The team voice." Keep it short — live "who's talking" + encouragement, not a log dump.
3. **Also build the native `TaskCreate` / `TaskUpdate` checklist** — the pinned on-screen list in
   the Claude Code IDE/CLI. **`Task*`, NOT `TodoWrite`** (off by default ≥ v2.1.142). Drive it from
   the MAIN orchestrator. Best-effort and surface-specific — that's why steps 1–2 are the floor.

Per surface: **IDE/CLI** → the pinned native list (step 3) + the inline board; **desktop app / web**
→ the inline board (step 2) is what's visible; **headless / own-orchestrator** → `scripts/orbit-status
--follow` (Ctrl-C to stop) off the step-1 files. Each role announces itself: `emit` a `start` on
pickup and `done`/`blocked` on handoff, and open its report with `[role] …`.

### Phase 7 — Report, in plain language, and recommend the first run

End every `/orbit` run with a short, beginner-readable summary — not a file dump:

1. **What I installed** — a few grouped bullets (memory, team, loop, safety).
2. **The 3 files that matter** — `CLAUDE.md` (plan + rules), `.orbit/STATE.md` (progress),
   `.orbit/loop.config.json` (limits). "The rest is detail you can ignore until you need it."
3. **Works today vs. wire later** — be honest: `loop.py`'s `dispatch()` is a **stub** that
   raises until you connect your own model; the Claude Code path works now via the
   subagents. Don't let scaffolding read as a finished product.
4. **Limits + the first run** — in plain words: "a run can use up to ~$X and N steps, then it
   stops itself; anything risky waits for you." Then name the **first loop** and its exact stop
   conditions — start tiny and safe (smallest unit of work, dry-run, max 3 iterations, every
   checkpoint human).
5. **How routing & safety work — what binds vs. what's advisory** (don't oversell): a **router
   hook** classifies **every** message deterministically (task → loop, question → direct) and
   injects that as the **default lane** before I respond — mechanical, every turn, no model in the
   loop. But it's a keyword matcher, so I still *execute* the loop and can override a clear
   misclassification with a stated reason. The **safety hook** is different: a hard wall that can
   actually **stop** a tool call, in every lane. `loop.py`'s `dispatch()` is a stub until wired.
   Both always-on hooks (router + safety) are: `<on / off>`. **To undo:** run `orbit-uninstall`
   from this repo (or `~/.claude/skills/orbit/bin/orbit-uninstall` if it isn't on your PATH) — it
   removes everything Orbit added and leaves your CLAUDE.md alone.
6. **A status line** — `DONE` / `DONE_WITH_CONCERNS (…)` / `BLOCKED (…)` so the true state
   is unambiguous.

Nothing here needs a restart: the scaffolded files are read live, and the safety hook arms on
the next command. The user can start working immediately.

Then, internally, update `.orbit/STATE.md` and `CLAUDE.md` to reflect what was built — close the
loop on your own work, the same way the system will.

### The closing — "meet your team" (make it warm and motivating)

This is the **last thing the user sees**, and it should feel like a capable team reporting for duty —
not a file manifest. Introduce **only the roles you actually stood up for this project**, by their
project-specific names, each with the skill that backs it and its **live-view color** (so the intro
matches the dashboard they'll watch). Use the real colors:

- 🔵 **Dispatcher** *(cyan)* — reads every message first; routes tasks into the loop, answers questions directly.
- 🟣 **Orchestrator / Planner** *(magenta)* — conducts the loop; the Planner turns the de-risked bet into the sliced, sequenced plan. *Skills: planning-and-decision-briefs, clarify-and-challenge.*
- 🔭 **Product Discovery Manager** *(blue — on substantial work)* — frames the outcome + the user's job, kills the four risks, names the riskiest assumption. *Skill: product-discovery.*
- 📊 **Market & Competitive Researcher** *(cyan — on substantial work)* — what exists, reuse-vs-build, where the gap is. *Skill: market-and-competitive-research.*
- 🟢 **&lt;Frontend / Backend / Data&gt; Engineer** *(green)* — builds the work. *Skill: &lt;the domain skill&gt;.*
- 🟪 **Designer** *(violet — frontend only)* — distinctive, on-brand UI, not templated slop. *Skills: design-methodology, anti-ai-aesthetics.*
- 🟡 **Reviewer** *(yellow)* — proves the *diff* (runs tests, quotes the line, enforces ADRs) before it counts. *Skill: technical-review.*
- 🧪 **QA Engineer** *(bright yellow)* — validates the *product* against the requirements, story by story; pixel-checks the UI vs your approved design. *Skill: qa-validation.*
- 🔴 **Safety** *(red)* — can veto or stop a dangerous action. The hard wall.
- ⚪ **Reporter** *(grey)* — turns results into clear, decision-ready updates.

Close with a genuine, encouraging line in your own words — e.g. *"Your team's assembled, and every
one of them comes with the skills to do this right. I'm ready — what's the first task?"* Then, when
they send it, the **router** picks the lane, the **Planner** opens with a quick negotiation to kill
the rabbit holes, and the **live checklist** shows each teammate (in their color) working it down to
done. Make the user feel they just hired a team, and it's eager to start.

## Guardrails for you, the builder

- **Stop conditions are not optional.** A loop without hard caps is a defect. If the
  user waves them off, install conservative defaults anyway and tell them where to relax.
- **Fast by default; smart where it counts.** Depth scales to the task, automatically — no
  mode, no extra command. A small, clear, reversible task is just done; the full team and
  *parallel* deliberation are reserved for substantial, ambiguous, or irreversible work
  (CLAUDE.md §10). When the system does deliberate, it fans out (approaches ∥ risks ∥ infer)
  instead of a slow serial chain, and surfaces the decision, not a transcript. Don't build a
  system that runs six phases of ceremony on a one-line fix — that's the latency users feel.
- **Every question to the user is an `AskUserQuestion`.** Selectable options, recommendation
  FIRST labeled "(Recommended)", one-line trade-off per option, batched when there are several —
  never a question buried in prose (it doesn't look like a question and goes unanswered). This is
  the rule for setup AND for the system you scaffold (it's in the CLAUDE.md template §10 and
  `clarify-and-challenge.md` → "HOW to ask").
- **Never wire auto-execution of irreversible or outward-facing actions.** Moving money,
  sending outbound messages, deploys, deleting data — these route through a human-approval
  checkpoint. The loop proposes; a human disposes.
- **Don't clobber existing files.** Merge CLAUDE.md; back up anything you rewrite.
- **Keep CLAUDE.md lean.** When you're tempted to add a long rule, ask whether it
  belongs in a skill or a hook instead.
- **Stay model-agnostic in the core.** The Claude Code adapter is a convenience layer,
  not the foundation. The user runs production on their own orchestrator.
- **Don't bypass silently.** Most everyday requests are fine to handle directly — the full
  role/gate ceremony is for deliberate loop runs, not every chat. But if a loop is active or
  a request touches a guarded action, say so out loud and, if you act outside the loop, write
  a one-line `[decision]` note in `.orbit/STATE.md` saying what you did and why. The thing
  that actually protects the work is the Phase 6a hook — not your memory to route through the
  gates. Never imply the gates ran when they didn't.

## Reference map

- `references/methodology.md` — the principles and the "why". Read if you're new to the approach or
  customizing a piece — **not** required to run the scaffold (the script owns the structure).
- `references/claude-md-template.md` — CLAUDE.md template + required sections.
- `references/state-template.md` — STATE.md working-memory template.
- `references/roles.md` — the sub-agent team, specs, and handoff protocol.
- `references/loop-design.md` — loop structure, stop conditions, Ralph loop, the
  config contract.
- `references/hooks-and-tools.md` — hook events, tool wiring, CLI-first guidance.
- `references/observability.md` — the "who's talking" event stream + live checklist
  (TaskCreate/TaskUpdate + the `orbit-status` dashboard).
- `references/durable-execution.md` — what *runs* the loop: the loop/skill/orchestrator
  model, step checkpointing, concurrency, and when to graduate to a durable engine.
- `references/profiles/generic.md` — the universal profile: how to characterize any
  product. `references/profiles/frontend.md` — the frontend/UI profile that activates the
  **Designer**. Add your own profiles here for repeated setups.
- `references/playbooks/` — the reusable **role-skill library** provisioned to sub-agents:
  `design-methodology.md` + `anti-ai-aesthetics.md` + `design-styles.md` (Designer),
  `planning-and-decision-briefs.md` (Orchestrator), `clarify-and-challenge.md` (Dispatcher/Orchestrator),
  `technical-review.md` (Reviewer — the technical quality gate), `qa-validation.md` (QA Engineer —
  requirements-traceability + pixel fidelity), `active-learning.md` (the Orchestrator's silent
  learn-gate in the UPDATE phase), `product-discovery.md` + `market-and-competitive-research.md`
  (the planning-phase **discovery team**), `goal-pipeline.md` (goal → story DAG → run-until-green →
  polish), `architecture-decisions.md` (the CTO hat — ADRs, boring-tech, fitness functions).
  Grow this over time.
- `assets/` — copyable `loop.config.json`, `loop.py`, `activity.py`, `ralph_loop.sh`,
  `orbit-status`, `checks/guard.py` (safety) + `checks/route.py` (router), `runners/inngest-loop.ts`,
  example subagents (incl. designer, reviewer, safety-gate).
- `scripts/scaffold.py` — lays down the deterministic skeleton.
- `commands/orbit-run.md` — the `/orbit:orbit-run <task>` slash command: explicitly send a task
  through the loop. (Auto-routing is the CLAUDE.md §10 rule; this is the manual target.)
