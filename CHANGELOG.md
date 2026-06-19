# Changelog

All notable changes to the `orbit` plugin are documented here. The version here
must match `VERSION` and `.claude-plugin/plugin.json` — the update checker compares them.

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
