# Changelog

All notable changes to the `orbit` plugin are documented here. The version here
must match `VERSION` and `.claude-plugin/plugin.json` — the update checker compares them.

## 0.7.1

Docs: surface the Designer and Planning powers in the README. v0.7.0 shipped the capabilities
but the README didn't name them as headline value — now it does.

- **New "✨ Two powers people love" section** in the README, showcasing the **Planning power**
  (clarify-first/infer-first, challenge weak assumptions, decision briefs + CEO/eng plan-review,
  escalate-don't-guess) and the conditional **Designer** (Design Plan + token system + two-pass
  plan→critique→build, rejects the 3 default AI aesthetics, Design Distinctiveness gate), each
  pointing at the playbooks it loads from the skill library.
- **Two new "Why you'll care" rows** — "plans like a senior" and "a real Designer, not slop".
- **"The team" paragraph** now names the **Dispatcher** (clarify & challenge) and the
  **Designer** (frontend repos). Framing kept honest: these are advisory/prompt-driven, like routing.


## 0.7.0

A reusable role-skill library + a conditional Designer + planning rigor + a beginner-exciting README.

- **Skill library** (`references/playbooks/`): reusable playbooks provisioned to sub-agents when
  they're created — `design-methodology` + `anti-ai-aesthetics` (Designer), `planning-and-decision-briefs`
  (Orchestrator), `clarify-and-challenge` (Dispatcher/Orchestrator). Grows over time; documented in
  `roles.md` → "Skill library".
- **Designer sub-agent (conditional)**: a new role + `profiles/frontend.md` that stands it up only on
  frontend/UI repos. Embeds the frontend-design methodology (two-pass plan→critique→build, named token
  system, hero-is-thesis, one signature, anti-AI-aesthetic checklist, quality floor) — self-contained,
  no external-skill dependency. Produces a Design Plan for the Builder; Reviewer gains a Design
  Distinctiveness gate.
- **Planning rigor + clarify/challenge**: Orchestrator frames forks as decision briefs (stakes,
  Completeness X/10, recommendation, Net) and runs a CEO+eng plan-review; Dispatcher clarifies and
  challenges the ask (infer-first, surface premises, forcing questions, propose 2-3 approaches) instead
  of executing literally — "be smarter than the prompt." Advisory (prompt-driven), like routing.
- **README glow-up**: a beginner-facing "Why you'll care" before/after table and a punchier value prop.


## 0.6.1

Fixes the live checklist not appearing. Root cause (confirmed against Claude Code docs):
Orbit's observability targeted **`TodoWrite`, which is disabled by default** in current
Claude Code (≥ v2.1.142) — so the agent correctly reported it "isn't available," fell back
to prose, and (since it also never wrote `.orbit/tasks.json`) left nothing for `orbit-status`
to render either. No checklist, from either path.

- **Migrated observability from `TodoWrite` → the current `TaskCreate` / `TaskUpdate` /
  `TaskList` tools** across SKILL.md, observability.md, the CLAUDE.md template, roles.md,
  the `/orbit-run` command, README, and `activity.py`.
- **Belt-and-suspenders, stated as a hard rule:** every cycle **always writes
  `.orbit/tasks.json` + `.orbit/activity.jsonl`** (the guaranteed-visible path that feeds
  `orbit-status`) *and* builds the native `Task*` checklist. A run that only narrates `[role]`
  lines and skips the files is called out as the failure to avoid.
- **Drive the checklist from the MAIN orchestrator** — a subagent's `Task*` calls run in
  isolated context and don't surface to the user; documented explicitly.
- Honest framing kept: the native checklist is best-effort (model must call the tool); the
  file-fed `orbit-status` (or running the loop runner, which emits deterministically) is the
  guaranteed-visible fallback.

## 0.6.0

The safety hook is now **default-on (announced), not opt-in** — so Orbit's safety is real
out of the box. A floor you have to opt into is a floor most people skip.

- **`/orbit` installs the `PreToolUse` safety hook by default** as part of setup — no
  question — and **announces exactly what it added** (the deny/ask lists) plus the one-line
  removal (`orbit-uninstall`). Never silent; the original footgun was silence + no off-switch,
  not the install itself. Skipped only if `.orbit/setup.json` records a prior removal.
- **`scaffold.py --install-hooks`** — deterministic wiring: backs up `.claude/settings.json`,
  merges the `PreToolUse(Bash)` guard idempotently (never double-adds), prints the JSON.
- The hook still **fails open** and only **denies the catastrophic** (force-push, secrets-
  branch push, schema migration) while **asking** on normal pushes — so default-on won't
  disrupt workflows. README/Phase 6a reworded: the hook is the one binding layer; routing +
  roles remain advisory.

## 0.5.1

Docs accuracy fix. Verified against Claude Code plugin docs that plugin slash commands are
**namespaced**: the new command is invoked as **`/orbit:orbit-run`**, not `/orbit-run`.
Corrected the references in CLAUDE.md §10, SKILL.md, and the README. (Claude Code lists
commands under "Skills" in `plugin details` because commands and skills have converged —
`commands/orbit-run.md` is the correct location.)

## 0.5.0

Orbit becomes a task router with a smooth, self-answering install. Grounded in a deep study
of gstack + Claude Code routing primitives + agent frameworks. Honest framing: no tool can
*force* a workflow to run on a message (gstack's routing is advisory too) — so this is
gstack-parity reliable-advisory routing; the only hard wall remains the safety hook.

- **Task vs. question routing.** New `CLAUDE.md` §10 "Request Routing" (written on every
  `/orbit` run): a *task* (build/fix/change) routes through the loop; a *question* is answered
  directly; ambiguous → ask one. This is the "system prompts itself" behavior.
- **`/orbit:orbit-run <task>` command.** The plugin's first `commands/` — a deterministic, user-
  invoked target to send a task through the loop. Plus a **Dispatcher/Router** role.
- **Smooth, infer-first install.** Phase 0 rewritten: infer the domain from the repo and ask
  **0 questions** on an existing repo, **1** only on greenfield; headless → safe defaults,
  never hang; choices persist in `.orbit/setup.json` so re-runs don't re-ask. (`/plugin`
  install was already zero-prompt.)
- **Library pedagogy adopted.** The 5-part mental model (**trigger → action → proof → memory
  → stop**) up front; a first-class **`proof`** field in `loop.config.json` and a
  **Proof/Verification** section in every role spec.
- **Honesty pass.** README + Phase 7 state plainly what binds (the safety hook) vs. what's
  advisory (routing); stale version badge fixed (0.2.0 → 0.5.0).

## 0.4.0

Durable execution — the loop / skill / orchestrator model. Orbit owns the design + safety +
onboarding layers; it now scaffolds *onto* a durable engine instead of pretending a shell
`while True` is production.

- **Step checkpointing + `--resume` in `loop.py`.** A `Steps` memo records each completed
  step's output to `.orbit/steps.jsonl`; on restart, completed steps are skipped — no
  re-fetch, no re-charged model call, no double side effect. Survives a crash instead of
  starting over.
- **Triggers + concurrency in `loop.config.json`.** New `trigger` (manual/cron/event) and
  `concurrency.singleton_key` (one run per key — fixes the orphaned-background-loop class of
  bug). New `paths.checkpoints`.
- **Durable-backend reference runner.** `assets/runners/inngest-loop.ts` maps the loop onto
  Inngest's `step.run`/`step.invoke`/retries/`onFailure`/concurrency (reference template,
  grounded in inngest/utah + Inngest docs). `ralph_loop.sh` is now labeled the **dev** runner.
- **Vocabulary fix.** Orbit's `.orbit/skills/*.md` are **knowledge playbooks**, not "durable
  skills" (workflows on the engine) — clarified in the glossary, CLAUDE.md template, README.
- **New guide `references/durable-execution.md`** — three layers, why durability is the
  foundation, two runners, concurrency, step-level traces as the trust layer, and the
  orchestration-aware self-extending agent as the north star.

## 0.3.0

Real enforcement + beginner mode. Grounded in how gstack actually binds safety (real
`PreToolUse` hooks, not prose).

- **Binding safety hooks (Hybrid C).** Ships `.orbit/checks/guard.py` — a `PreToolUse` hook
  that Claude Code evaluates *before* a tool runs and can `deny`, so the non-negotiables hold
  even outside the loop. It is **placed but unwired**; `/orbit` Phase 6a installs it only with
  explicit consent, backs up `.claude/settings.json`, and prints the exact JSON + one-line
  removal. Argv-matched (not substring), fail-open. Fixes the "agent silently bypasses its own
  gates" trust trap.
- **`orbit-uninstall`.** A real undo: lists, confirms, removes the Orbit scaffold and strips
  only Orbit-tagged hooks (with backup); never touches your CLAUDE.md.
- **One live view per environment.** Claude Code uses the native pinned TodoWrite checklist
  automatically (no command, no second terminal); `orbit-status --follow` is reserved for the
  headless path (with "Ctrl-C to stop").
- **Beginner onboarding.** Plain-language preface + 5-line glossary; Phase 7 now ends with a
  "what I installed / the 3 files that matter / works-today-vs-wire-later / spend / how-to-undo"
  summary and a status line. `loop.py`'s `dispatch()` is labeled a stub.
- **Honesty pass.** README safety section now distinguishes what binds (in-loop caps + the
  opt-in hook) from what's advisory (normal chat). New `hooks-and-tools.md` section:
  "Enforcement vs. suggestion" + guardrail best practices.

## 0.2.0

Observability — see who's talking and watch the checklist live.

- **"Who's talking" event stream:** every role and the loop emit structured events
  (`who · phase · what`) to `.orbit/activity.jsonl`, plus a checklist in `.orbit/tasks.json`,
  via the new `.orbit/activity.py` helper.
- **Live dashboard:** `scripts/orbit-status --follow` renders a pinned terminal view —
  current speaker, phase, and the checklist crossing itself off (✓/▸/○), color-coded by role.
  Works anywhere (including your own orchestrator).
- **Native Claude Code checklist:** mirror `.orbit/tasks.json` into TodoWrite with
  role-prefixed items (`[data] validate inputs`) for the pinned, auto-crossed-off list;
  each role announces itself `[role] …` so the transcript shows who's speaking.
- `loop.py` now emits at every phase and around each dispatch; `scaffold.py` lays down
  `activity.py` + `orbit-status`. New guide: `references/observability.md`.

## 0.1.0

Initial release.

- `/orbit` skill: audits any product repo and scaffolds the full self-prompting
  system — `CLAUDE.md` persistent memory, `.orbit/STATE.md` working state, a specialized
  sub-agent team, domain skills, the read→act→evaluate→update→decide loop, and hard stop
  conditions.
- Hybrid output: a model-agnostic core (`loop.py`, `loop.config.json`, role specs, skills)
  plus a Claude Code adapter (`.claude/agents`, hooks, `ralph_loop.sh`).
- Domain-agnostic: characterizes whatever product it runs in via the universal profile.
- Self-update: a preamble update-check on every invocation, plus `/orbit-upgrade`
  (git-based pull-and-continue, with auto-upgrade config and snooze).
