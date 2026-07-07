# Changelog

All notable changes to the `orbit` skill are documented here. `VERSION` is the single source of
truth — the update checker compares it against GitHub.

## 0.29.0

**Project freshness gets a first-class doctor + safe managed-hook patching — and a real clobber bug is
fixed.** (Train A of the trust/durability/visibility roadmap — completing the freshness engine started
in 0.28.1 rather than rebuilding it.)

- **`orbit-doctor`** (new `bin/`) — a read-only health check for a scaffolded project: scaffold drift
  (version · missing files/hooks · role/prose drift · preserved custom guard) **plus** a safe-refresh
  plan for the managed hooks, in one command. `orbit-doctor --fix` applies only the safe changes. It
  runs against the *installed* plugin (a project-local copy would go stale), and it's literal-executable
  so it never trips the guard. `/orbit`'s re-run path and `/orbit-upgrade` both point at it now.
- **`scaffold.py --plan-refresh`** (read-only) previews exactly what a safe managed-hook refresh would
  do — which hooks (`guard`·`route`·`orbit-stop-check`·`learn`) would **auto-upgrade** (unmodified since
  we placed them), be **added** (missing), or stay **customized** — and prints a **unified-diff patch
  suggestion** for each customized hook so you can hand-merge. **`--apply-safe-refresh`** writes only the
  safe ones (add + upgrade, backups kept) and **never touches a customized hook**. One shared classifier
  (`_classify_managed`) now backs both these modes and the full-scaffold migration.
- **Bugfix (the important one): a customized guard is no longer clobbered on the *second* refresh.**
  `_write_manifest` used to record the hash of whatever was on disk — including a *customized* guard —
  which "laundered" the customization into looking unmodified, so the next `/orbit` re-run (or refresh)
  auto-upgraded and **overwrote** it. This was a latent break of the "never clobber the customized guard"
  invariant, live since 0.28.1. The manifest now records **only shipped hashes**; a customized file keeps
  the hash of what *we* last placed, so it reads as customized forever. Pinned by two regression tests
  (`repeated_refresh_preserves_customization`, `repeated_full_scaffold_preserves_customization`).

New `tests/test_scaffold_refresh.py` (6 cases). Full suite (26 files) + coherence + `claude plugin
validate` green.

## 0.28.3

**The `/orbit` preamble now runs with zero PreToolUse prompts — the executable is always literal.**
0.28.2 stopped the guard prompt by wrapping the resolved path in `bash "$_p"`, but that still puts a
variable in command-adjacent position and force-feeds the shebang. The cleaner fix (a P1 *trust* bug —
Orbit must not ask you to trust Orbit before it has started): resolve the install directory as a `cd`
argument and run a **literal** `./orbit-preamble` / `./orbit-update-check`. So no `$VAR` ever sits in
command position, the script's own shebang is respected, and the guard has nothing to ask about. Same
rewrite in `/orbit-upgrade`'s forced check. **The guard is untouched** — it still asks on a real
`"$X"` command and denies dangerous substitutions. `tests/test_generated_commands.py` now evaluates the
**exact** Step 0 and forced-check blocks *extracted from the skill files* through `guard.evaluate(...)`
and asserts `None` (so the test can't drift from what ships), plus the guard's ask/deny behaviour.
Acceptance bar met in full; suite (25 files) + coherence + `claude plugin validate` green.

## 0.28.2

**Orbit's own `/orbit` preamble stops tripping Orbit's own guard.** The Step 0 update-check preamble
resolved a binary across candidate paths with `for _p in …; do "$_p"; done` — but `"$_p"` is a bare
`$VAR` *command name*, exactly what the guard's fail-safe asks about (it can't resolve a for-loop
variable). So every `/orbit` run prompted *"this command's name is an unresolved shell variable —
confirm it's safe."* — a self-inflicted false positive. Fixed the *generator*, not the guard (the
guard is correct to be cautious here, and it's been hardened over three red-team rounds): the preamble
now invokes the resolved path through an interpreter — `bash "$_p"` — so the command name is `bash`
and `$_p` is just an argument. Same fix in the `/orbit-upgrade` standalone check. New
`tests/test_generated_commands.py` asserts Orbit emits no bare-`$var` command and that the guard still
(correctly) asks on the bare form — the regression is on the generator, not a guard weakening. Full
suite (25 files) + coherence + `claude plugin validate` green.

## 0.28.1

**Scaffold freshness — kill the silent version lie.** The bug class: `/orbit-upgrade` can truthfully
say "Orbit is current" while a scaffolded project still runs an **old local scaffold** — `plugin`
freshness ≠ `project-scaffold` freshness. Root cause: `.orbit/setup.json`'s `orbit_version` was written
*once, by the model* and never bumped, so it drifted (a real project sat at `0.21.0` while missing the
Stop hook and the Gearbox). Fixed at the source:

- **Deterministic version stamp.** The scaffolder now writes `.orbit/setup.json`'s `orbit_version` +
  `scaffold_schema` on every run — so a re-run finally moves `0.21.0 → current`. Idempotency is
  preserved: `last_migrated_from`/`last_migrated_at` are written **only when the version actually
  changes**, never a fresh timestamp on a no-op re-run (no git noise), and the model-written keys
  (domain characterization + choices) are preserved.
- **A read-only drift report** — `scaffold.py --check-drift` (surfaced by the `/orbit` preamble on a
  re-run, and referenced by `/orbit-upgrade`): reports *plugin current · scaffold metadata old/missing ·
  missing files · hook drift · role/template drift (advisory) · stale prose (advisory) · custom guard
  preserved*. So a project can't silently run a stale scaffold while the plugin reports "current."
- **Broadened, manifest-based migration.** A `.orbit/.scaffold-manifest.json` records the sha of each
  managed check the scaffolder placed. On a re-run, a managed hook (`guard.py`, `route.py`, `learn.py`,
  `orbit-stop-check.py`) that is **byte-identical to what we placed** (unmodified) is carried forward
  with a backup; a **customized** one (e.g. a guard with your own §8 deploy rules) is **warned about and
  never overwritten**. No more maintaining hardcoded historical-hash lists.

New `tests/test_scaffold_freshness.py`; the idempotency and migration invariants still pass; full suite
(24 files) + coherence + `claude plugin validate` green. (A project like the earlier stale one refreshes
by re-running `/orbit` in it — the local projects themselves were left untouched.)

## 0.28.0

**Orbit Gearbox — the loop sizes itself before it moves.** Not every request deserves the same
machinery. Orbit already leaned this way (a fast lane vs a substantial lane vs the goal pipeline), but
the ladder was *implicit* and its top rung couldn't scale its fan-out to the request. The Gearbox makes
it explicit, market-aligned (route-first · dynamic orchestrator-workers · guardrails-scale-with-autonomy,
OWASP LLM06), and — the point — **legible**: Orbit declares its operating mode before doing the work.

Five gears, chosen by a **scorecard** (ambiguity · blast radius · # surfaces · research need ·
compliance/security · reversibility · runtime/cost), *highest risk-trigger wins* (never a sum), biased
toward the **smallest gear that can still prove the result**:

- **T0 Direct** — question / explanation / trivial patch → answer or patch, no loop.
- **T1 Quick** — small · clear · reversible → Plan → Do → Verify, one owner.
- **T2 Standard** — a real change → the team loop on the visible board.
- **T3 Deep** — broad · ambiguous · research-heavy · multi-surface → **Map → Research → Plan → Critique
  → Synthesize → Build**, with a *dynamic* fleet of **existing roles** sized to the request (Map =
  Product-Discovery per surface, Research = Market-Researcher per unknown, Plan = Planner per feature
  cluster, **Critique = the Reviewer/Safety/design roles wearing an adversarial "critique the plan" hat**
  after a draft exists, **Synthesize = the Planner** converging to one plan-of-record — *no new role
  types are introduced*). Capped (`gears.deep`: 16 agents / 400k tokens) and **always confirmed with the
  user before fan-out**.
- **T4 Mission** — multi-repo · multi-day · production migration · money at scale → T3 on the durable
  runner (`loop.py` / `durable-execution.md`): checkpoints, resume, a human-approval gate per irreversible
  step, an artifact bundle.

Every gear opens with a **Gear Card** (`Gear / Why / Budget / Exit`, emitted to `activity.jsonl` +
rendered on the board) — the "surprise factor": Orbit explaining *why* it sized the request the way it
did. **Guardrails scale with the gear** (OWASP LLM06): higher gear → minimal tools per worker (reusing
Orbit's per-role `tools:` scoping), cost/fan-out caps, and a human gate on every irreversible/outward/money
step. And it all runs on the **visible board** — `set_team` + `.orbit/tasks.json` + `.orbit/activity.jsonl`,
Task-tool sub-agents — **never** the native `Workflow(...)` runner (the v0.27.2 contract holds).

**It's not new machinery — it unifies what Orbit already had:** T1 = the fast lane, T2 = the substantial
lane + discovery team, T3 = the discovery team *made dynamic* + plan-review's lenses *as critics* +
goal-pipeline, T4 = the durable `loop.py` path. Wired into §10, the Orchestrator role, `route.py` (a soft
gear hint on breadth/research/mission signals + "size the gear first" in the injected context),
`loop.config.json` (the `gears` block), `roles.md`, and `SKILL.md`; provisioned as `loop-tiers.md`. New
`tests/test_loop_tiers.py`; full suite (23 files) + coherence + `claude plugin validate` green; the whole
feature run through a 5-lens adversarial review.

## 0.27.2

**The run contract now forbids the black-box runner — and enforces it.** Orbit's core promise is
*watch the team work*: a task runs through a visible, role-tagged checklist with a current owner and
`.orbit/tasks.json` + `.orbit/activity.jsonl`, driven by the main orchestrator. The gap this closes:
nothing in the contract said *not* to use Claude's native `Workflow(...)` background runner — which
executes an opaque job (`Running in background · /workflows to monitor`) that bypasses the entire
board. That silently reduces Orbit to "a fancy prompt."

- **The ban is now explicit on every run-contract surface** — `commands/orbit-run.md`, the
  Orchestrator role, the router's injected TASK context (`route.py`), the CLAUDE.md template §10, and
  `SKILL.md`'s observability phase all state: **do NOT run an Orbit task through `Workflow(...)`**; use
  the **Task tool** for sub-agents and drive the checklist yourself. (It stays fine for developing
  Orbit itself.)
- **Board FIRST.** The orchestrator now makes the board visible — `set_team` + `set_tasks` +
  `TaskCreate` — as its *first* action, before spawning any specialist, so the user sees who owns each
  step immediately, not after the work is done.
- **Enforced by a new Stop hook** — `.orbit/checks/orbit-stop-check.py`. When a routed task did real
  work but wrote **no board** (no `.orbit/tasks.json`, no `set_team`), it **fails loudly**: records an
  observability-gap event and blocks the stop once, telling the model to make the board visible.
  Conservative + fail-open by design (the guard-hardening lesson): it fires only on *substantial* work
  with a *completely absent* board, blocks at most once per route (`stop_hook_active` + a per-route
  marker), stays silent on trivial/no-work turns and answered questions, and any error → allow. The
  router (`route.py`) drops a `.last-task-route` anchor so the hook can tell a task ran; `orbit-uninstall`
  strips the hook like the others.
- New `tests/test_run_contract.py` (the Workflow ban on all surfaces + board-first + the Stop hook's
  gap/silent/fail-open behavior + the scaffolder placing and wiring it). Live acceptance: a real
  route → black-box run **blocks**, a run that wrote the board **stays silent**. Full suite (22 files)
  + coherence + `claude plugin validate` green.

## 0.27.1

**Guard: fixes the reported `$B` browse false-positive, then two adversarial red-team passes harden it
against 16 evasions — and remove the over-blocks that hardening exposed.** The trigger was a real
annoyance: gstack's `browse` emits `B=/…/browse; $B js "(()=>{…})()"`, and the guard was parsing the
*quoted JavaScript argument* as if it were shell (a bare `(` inside quotes read as a subshell), so it
asked on every call.

- **The browse fix.** `_inner_commands` is now **quote-aware** — a bare `(` inside single/double
  quotes is a literal character (a JS/SQL/regex argument), while a real `$( … )` / backtick — even
  inside double quotes — is still caught.
- **Three red-team rounds, 25 confirmed fixes.** Rather than ship on faith, an adversarial
  multi-agent pass — then a second on the hardened result, then a third targeting regressions from
  the second — hunted for commands bash executes catastrophically but the guard allowed, *and* benign
  commands it wrongly blocked. Fixed:
  - **Parser:** ANSI-C `$'…'` (both the trailing-`$()` swallow and the tokenizer-drop `$'\''; rm -rf /`);
    a stray apostrophe (in `don't`, a `#` comment, a heredoc body) no longer hides a later `$( … )`;
    the bash-5.3 command funsub `${ cmd; }` / `${|cmd;}` is recognized, including inside double quotes;
    `#` comments are stripped word-boundary-aware, so `git commit -m fix#42 && git push --force` no
    longer drops its tail.
  - **Variable resolution:** `$VAR` / `${VAR}` resolves in **argument** position too (`of=$DEV`,
    `git push $F`, `rm -rf $D`), every candidate of a reassigned var is tried (worst wins), the
    curl|sh detector resolves var names, and `dd`/redirect gained raw-device fail-safes (`> /dev/sda`).
  - **Heredocs done right:** a heredoc BODY is inert stdin **data**, never a command, so a benign
    `cat <<'EOF' … rm -rf / … EOF` file-write isn't blocked — but detection is **quote/comment-aware**
    (a `<<X` inside quotes or a comment is *not* a heredoc, closing a regression the first heredoc
    pass introduced), the delimiter charset and exact close-match are correct, and an **unquoted**
    heredoc body still gets its `$( … )` scanned.
  - **Over-blocks removed:** `#` comments aren't parsed as commands; `rm -rf ./build` (the cwd prefix,
    not a dotfile) is allowed; heredoc file-writes with dangerous-looking body lines are allowed.
- **Honest boundary.** The guard's threat model is *catching an agent's mistakes*, not defeating a
  determined adversary — it fails **open** by design (spelled out in the module header). Three rounds
  closed the common and many adversarial forms and removed the false positives that hurt real work;
  residual gaps are exotic obfuscations outside that model. `tests/test_guard.py` grows to **123
  cases**; full suite + coherence + `claude plugin validate` green. (This reaches existing scaffolded
  repos only when they re-run `/orbit` — each repo has its own `.orbit/checks/guard.py` and migration
  is warn-only.)

## 0.27.0

**The Designer gets a taste layer — TasteSkill, folded into Orbit's workflow.** Orbit already owned
the operating model (HEAVY/TRIVIAL triage, the prototype gate, the `design/approved.json` + `DESIGN.md`
contract, the QA verification triangle). What it lacked was a mechanical guard against UI that *looks*
generated. This release adapts **[TasteSkill](https://github.com/Leonxlnx/taste-skill)** (MIT, Leonxlnx —
credited in `CREDITS.md`) into that workflow as a new playbook, `taste-preflight.md`:

- **The design *read*** — one line before choosing a style ("Reading this as: a pricing page for indie
  founders, leaning toward Linear/shadcn"), so the brief is interpreted explicitly, not defaulted.
- **Three dials, set explicitly** (1–10): `DESIGN_VARIANCE` (symmetry↔asymmetry), `MOTION_INTENSITY`
  (static↔choreographed), `VISUAL_DENSITY` (airy↔cockpit). They drive every layout/motion/spacing call.
- **A real-design-system map** — Material · Fluent · Carbon · Polaris · Atlassian · Primer · GOV.UK/USWDS ·
  Bootstrap · Radix/shadcn · Tailwind — *conventions* to inherit, distinct from the 67 aesthetic styles.
- **Surface-conditional scope** — landing/marketing gets the full preflight; app/dashboard leans on the
  system-map + Orbit's product-UI QA at high density; mobile defers to platform guidelines first.
- **An anti-slop ban list** folded into `anti-ai-aesthetics.md` (the canonical source): fake dashboards,
  default purple gradients, generic cards, beige-luxury palette, fake version labels, decorative scroll
  cues/dots, generic names, empty marketing copy — and em-dashes **in shipped UI copy only** (Orbit's own
  internal docs keep their house style; a deliberate adaptation, not a copy).
- **A recorded contract + real gates.** The Designer writes a `taste_preflight` block into
  `design/approved.json` on HEAVY (read + dials + design-system + surface + `checklist_passed`). QA and the
  Reviewer's Design-Distinctiveness gate treat a HEAVY approval with **no `taste_preflight`** as a finding,
  and the `design-gate.py` hook asks on a HEAVY UI edit whose approval lacks it — while a legacy or
  unparseable approval stays pass-with-warning (fail-safe). TRIVIAL work is exempt; the fast lane stays fast.

The Designer now loads four design skills (`design-methodology` + `anti-ai-aesthetics` + `design-styles` +
`taste-preflight`); `taste-preflight.md` is provisioned into `.orbit/skills/` on UI repos only. New
`tests/test_taste_preflight.py` (UI-only provisioning, the 67-style catalog, HEAVY-only recording, the
QA/Reviewer gates, the scoped em-dash ban) + extended `test_design_gate.py`. The whole merge was put
through a six-lens adversarial verification pass; the confirmed findings (ban-list de-duplication, surface
vs universal-defaults clarity, one missed doc reference, and stronger test assertions) are fixed here. Full
suite (21 files) + coherence + `claude plugin validate` green.

*Note:* the `0.7.1`-vs-richer-release confusion some external notes referenced was stale — this repo already
shipped the full 67-style catalog; 0.27.0 builds straight on it.

## 0.26.3

**Guard now resolves a `$VAR` command name — killing a false positive AND closing a real bypass.**
Two fixes to `assets/checks/guard.py`, both about a command whose *name* is a shell variable:

- **False positive (the reported annoyance).** The safe idiom `B=/path/to/tool; $B goto …` (as
  emitted by gstack's browse) made the guard *ask* every time, because it saw the command name as an
  un-inspectable `$B`. The guard now builds a `{VAR: value}` map from **flat literal assignments in
  the same command** and resolves `$B` to the real tool → benign → **allowed, no prompt**. Only flat
  literals resolve: a value with `$`/`` ` ``/`$(` (another var or a substitution) **or** a shell
  control operator (`;`, `|`, `&`, `<`, `>`, `(`, `)`) is left un-resolvable and keeps its *ask* —
  so `X="foo; rm -rf /"; $X` can't smuggle a hidden command in as args. A var reassigned to a
  different literal is treated as ambiguous and also stays *ask*.
- **The symmetric bypass.** The very same shape used to *hide* danger — `RM="rm -rf"; $RM /` or
  `G="git push --force"; $G origin main` — previously only asked (documented as "self-obfuscation out
  of scope"). It now resolves to the real command and **denies**.
- **A deny-bypass in the tokenizer, found while testing this.** `shlex(punctuation_chars=True)`
  returns a *run* of punctuation as one token, so `);` glued a subshell-close to a `;` and hid the
  separator — `X=$(echo hi); rm -rf /` split into a single segment and slipped past the rules as an
  **allow**. `_tokenize` now re-splits compound punctuation (keeping `&&`, `>&`, `&>`, … whole so
  `2>&1` isn't misread as a background `&`), so the `;` is seen and `rm -rf /` denies.

Fail-open and the deny-first precedence are unchanged. `tests/test_guard.py` grows to 78 cases
(6 new regressions covering both directions of resolution, the smuggling defense, and the `);` split).

## 0.26.2

**Marketplace install is now a first-class path for telemetry.** The telemetry hook is wired from
the trusted Orbit install (so editing a product repo can't alter the collector) — but 0.26.1 wired
a single skills-dir path, so a **marketplace/plugin install** silently got no telemetry. A
project-level hook can't see `$CLAUDE_PLUGIN_ROOT` (verified against the docs), so `orbit-hook` is
now wired as a runtime **resolver** that finds the collector across both layouts: the skills-dir
clone (`${CLAUDE_CONFIG_DIR:-~/.claude}/skills/orbit`) and the marketplace plugin cache
(`~/.claude/plugins/cache/<marketplace>/orbit/<version>/bin`, confirmed on disk). It `exec`s the
first match with stdin intact, and exits cleanly (0, no telemetry) if Orbit isn't found anywhere —
still fail-open. `orbit-uninstall` strips it, re-scaffold stays idempotent, and
`tests/test_orbit_hook.py` now covers all three resolution cases (skills-dir / plugin-cache / none).

## 0.26.1

**Hardening — three reproduced P1s in the visibility system, fixed.**

- **⚠️ Secret leak (privacy):** a key pasted into a prompt (`sk-proj-…`, `ghp_…`, `AKIA…`, a JWT,
  `token: …`) landed verbatim in `.orbit/activity.jsonl` — the redaction only stripped control
  chars. `_redact` (route.py + orbit-hook) now scrubs known secret shapes + labeled key/value pairs
  to `[redacted]` *before* logging, and the dashboard scrubs again at render (defense in depth).
  Benign prompts are unchanged.
- **Subdirectory:** working inside e.g. `packages/app`, the hooks looked for `.orbit/` in the cwd
  and missed the repo-root scaffold (no telemetry; the status line showed only `ctx%`). `orbit-hook`,
  `route.py`, `orbit-statusline`, and `design-gate.py` now resolve the nearest `.orbit/` by walking
  up from the cwd / the edited file (the status line prefers Claude's `workspace.project_dir`).
- **Run isolation:** the dashboard pulled proof events from the whole log regardless of run, so a
  fresh run could show `65%: test pass` from a *prior* run's proof. `orbit-status` now scopes events
  to the current `run_id`; a fresh run with a stale passing-test proof correctly reads a neutral 50%.

New `tests/test_visibility_hardening.py` + a subdir case in `test_design_gate.py`; 21 test files +
the coherence gate all green.

## 0.26.0

**A manager-visible team board.** 0.25.0 made the telemetry real, but the on-screen view was still
checklist-shaped. This turns it team-shaped: who's working now, who's queued, and what the active
one is doing — the standup a manager actually wants to see.

- **`.orbit/agents.json`** — a live team roster (display name, one-line responsibility, task,
  status, `started_at`, `last_event_at`, mission, last message), maintained in `activity.py`.
  `emit()` folds every signal into it (so `orbit-hook` feeds it for free), and a new
  **`set_team([...])`** lets the orchestrator declare the plan up front, so the board shows who's
  **queued** and their job — not just whoever's already talking. Known spine roles carry human names
  + responsibilities.
- **`orbit-status`** grew a **Working now / Queued** team board *above* the checklist: each active
  agent shows its human name, a live `active 4m 52s` clock, its task, mission, last signal, and who's
  up next; queued agents show their job. Escalating quiet tiers — `quiet 1m` → `long step` →
  `possibly stuck` (60/180/300s). New **`--team`** mode renders just the board (for printing inline);
  `--json` now includes the roster.
- **`orbit-statusline`** surfaces the active agent by human name + elapsed + quiet:
  `🛰 F-S1 · Frontend Engineer 4m52s · 3/9 · quiet 72s · ctx 38%`.
- **`orbit-hook`** drives the roster from SubagentStart/Stop and attributes a tool edit to whoever's
  *active* (from `run.json`) instead of a phantom "builder".
- **Guidance**: the orchestrator declares the team (`set_team`) before dispatching and prints the
  inline board (`orbit-status --team`) before a long sub-agent wait — the user is never left on only
  "waiting for background agent." Sub-agents emit a standup-style status (no chain-of-thought).
- New `tests/test_team_board.py`; 19 test files + coherence all green; fully fail-safe (a garbage
  `agents.json` never crashes any view).

## 0.25.0

**Long runs now feel alive, measurable, and trustworthy.** A full run-visibility system: what's
happening, who's active, how far along, what it's spending, how confident it is, and any decision
it's waiting on — fed **mechanically** by a hook collector on Claude Code's real run events, so it
stays live even when a role forgets to narrate. (Every hook event and status-line field was
verified against the current Claude Code docs before building.)

- **Schema-2 telemetry + an atomic `run.json` snapshot.** Events carry run_id + optional
  tokens/cost/confidence_delta/proof/files; `.orbit/run.json` is a compact, atomically-written
  (temp + os.replace) summary — phase, active role, done/total, elapsed, budget totals, confidence,
  blocked question — maintained by O(1) accumulators. Backward-compatible with schema-1 events.
- **`bin/orbit-hook` — a telemetry collector** wired to SubagentStart/Stop, TaskCreated/Completed
  (it mirrors the *native* Claude Code checklist into `.orbit/tasks.json`, so done/total is real),
  PostToolUse (file edits only), PostToolUseFailure, PostToolBatch, Stop, Notification. Observe-only
  (never blocks a tool, never returns a permission decision), never logs a raw prompt, fails open.
  Wired from the **trusted install path** — not copied into the repo — so editing the product repo
  can't alter the collector (addresses the project-local-hook trust boundary).
- **A one-line status line** (`orbit-statusline.py`) fusing Claude's status JSON (context %, cost,
  cache reuse — honestly labeled, not "tokens saved" — model) with `run.json`. Wired only if you
  don't already have a status line; never overwrites yours.
- **A rich `orbit-status` dashboard**: lifecycle phase strip (mode-aware), progress bar, active
  roles, budget, evidence-based confidence with a reason, and stall detection (30s / 90s). New
  modes: `--compact`, `--json`, `--no-ansi` (honors `NO_COLOR`).
- **Evidence-based confidence** (`confidence.py`): +tests/lint/review/safety/QA pass, −failing
  test / blocker / large unreviewed diff / safety concern, off a neutral 50 — with a plain reason,
  never a fabricated 100.
- **Lifecycle modes** (`lifecycle.py`): feature / bug / design / refactor / data, detected from the
  task so the dashboard shows the right phase strip instead of "Discover → Plan → Build" for a
  one-line fix.
- **Decision cards** (the headless equivalent of AskUserQuestion): `activity.ask()` writes
  `.orbit/pending-question.json` (title, why, options, recommended); the dashboard pins it and the
  status line shows `⚠ needs input`; `activity.resolve_question()` clears it. (Interactive path
  still uses the AskUserQuestion tool.)
- **Deliverable-report templates** (`deliverable-reports.md`, loaded by the Reporter): the report
  spine (what changed · proof · confidence · risks · files · next) per lifecycle mode, pulling REAL
  numbers, with honesty rules (a CONCERNS/failing gate is never "DONE").
- **Privacy**: `route.py` no longer logs the raw prompt — it stores a redacted, control-and-ANSI-
  stripped summary (no terminal injection into the live view). An adversarial review confirmed the
  system's invariants (fail-open, no-raw-prompts, observe-only, atomic writes, trusted-install
  import) hold; two low-severity defense-in-depth items (OSC-sequence stripping, render-time
  sanitization) were fixed.
- **Tests**: +6 suites (observability schema-2, orbit-hook, statusline, dashboard, confidence+
  lifecycle, decision cards) — 18 files + the coherence gate, all green. `orbit-uninstall` removes
  every new hook/status-line surface; the status-line/telemetry rows are in the honest binds table.

## 0.24.1

**⚠️ Security — the guard's flagged-wrapper and home-path parsing had real gaps.** An independent
review confirmed four live bypasses: `sudo -E git push --force`, `env -i git push --force`,
`echo x | xargs -I{} sh -c "git push --force"`, and `rm -rf ~/.ssh` all returned empty (allow)
output. Root cause: `_strip_wrappers` only stripped the wrapper's *name* (`sudo`, `env`, `xargs`),
not the wrapper's *own flags* — so `-E`/`-i`/`-I{}` were left sitting where the real command name
should be, and every downstream `is_git()`/`_push()` check silently failed. Separately, the
catastrophic/sensitive `rm` checks only recognized absolute paths, not home-relative ones like
`~/.ssh`. Both are fixed: wrapper-flag stripping now handles known value-taking flags (as a
separate token, inline, or bundled in a getopt-style short cluster like `-Eu`) for `sudo`/`env`/
`xargs`, and `~/`/`$HOME/`-relative dotfile/dotdir paths are now recognized as sensitive. Guard
tests: 59 → **72 cases**, one per closed gap plus the realistic variants around it.

Also from that review:

- **Docs now match reality.** README claimed "8 automated test files" (actually 12 at release
  time, now 13); Self-update said "auto-upgrade is on by default" with no mention of the
  first-time consent-once ask that's actually implemented, and repeatedly called the update
  mechanism "a `git pull`" when it's `git fetch` + `git reset --hard` (local edits are stashed,
  not merged — a real difference if you've hand-modified the installed copy). All three fixed to
  describe the actual, current behavior. `orbit-uninstall`'s "everything is removable" claim is
  corrected to name what's actually left for manual review (`.claude/agents/*.md`, `CLAUDE.md`) —
  the script itself already documented this; only the README oversold it.
- **The hero moved the "works now vs. stub" disclosure up.** "It runs on your own orchestrator"
  read as a day-one claim for the portable `loop.py` path, whose `dispatch()` is a stub. The hero
  line is softened and a callout right after the intro states the Claude Code path works today
  while the portable path needs one wire-up — instead of that disclosure living only deep in the
  Safety table.
- **A compact command map**, added right after Install: `/orbit`, `/orbit:orbit-run`,
  `scripts/orbit-status --follow`, `orbit-uninstall`, `/orbit-upgrade` in one table instead of
  scattered across the doc.
- **The project-local hook trust boundary, named honestly.** `.claude/settings.json` points hooks
  at files tracked inside the product repo — anyone with commit access can modify `guard.py`
  itself. This is inherent to Claude Code's project-local hook model, not fixed here, but now:
  documented plainly with concrete mitigation advice (CODEOWNERS on `.orbit/checks/` +
  `.claude/settings.json`), and a new **`scripts/verify-hooks.py --target <repo>`** that hashes a
  repo's installed hooks against what your current Orbit install ships and flags drift —
  detection, not prevention, and labeled as such.
- **Resolved-commit visibility.** `install.sh`, `./setup`, and `/orbit-upgrade` now print the
  resolved commit SHA after every install/upgrade — a concrete, checkable record of what's
  running, since installs track a mutable branch, not a signed release. Signed tags + checksum
  verification would be stronger and are named as a real next step, not claimed as done.
- New `tests/test_verify_hooks.py`. Suite is now 13 files + the coherence gate, all green;
  `claude plugin validate` passes.

## 0.24.0

**Prototype-before-develop, scoped to the work that deserves it.** The Designer's style-prototype
gate previously fired on "any new component… every time," with no way to tell a genuine redesign
from a copy fix, and always re-picked the product's whole look even for a single component in an
already-styled product. Neither matched how a good design process actually works. This release
adds an impact determination and splits the gate in two:

- **HEAVY vs TRIVIAL, decided first, every design request.** HEAVY (a new/redesigned component,
  module, screen, or flow; a layout/hierarchy/typography/color/spacing/interaction change; no
  approved style yet) fires a prototype gate; TRIVIAL (a copy fix, a sanctioned token tweak, an
  appearance-restoring bug fix, a className/prop swap, a zero-pixel refactor) skips it entirely —
  the fast lane (CLAUDE.md §10) stays fast, structurally: small/clear/reversible UI edits never
  route to the Designer at all.
- **Two gates for two different moments.** Gate A — the one-time **style-prototype pick** (2–5 of
  the 67 catalog styles, once per product, sets `DESIGN.md`) — is now clearly distinct from gate B,
  the new **recurring component gate**: 2–5 HTML variants of *this* component, built within the
  already-approved style, every time a HEAVY component is designed or redesigned. Both are opened
  in the browser and picked via `AskUserQuestion`, same as before — no new tooling.
- **Real teeth downstream, honestly scoped.** The Reviewer's Design Distinctiveness gate and the
  QA Engineer's pixel pass are now **conditional on `impact_level: HEAVY`** in `design/approved.json`
  — TRIVIAL work (which drops a separate `.orbit/design/TRIVIAL` marker) is exempt, and a visibly
  HEAVY change with *neither* record present is itself a finding, not a silent pass. A legacy
  `approved.json` with no `impact_level` is a pass-with-warning, never an auto-fail.
- **A coarse mechanical backstop for the silent skip.** New `.orbit/checks/design-gate.py`
  (`PreToolUse[Edit|Write|MultiEdit]`, UI repos only): Claude Code only exposes the file path being
  edited, not its content, so this hook can't judge heavy-vs-trivial or verify real prototypes were
  built — what it *can* catch is a UI production file edited with **no design-decision record at
  all**. Asks once per cycle, never denies, fails open, ignores `.orbit/` previews and non-UI files.
  Honestly labeled in the README's binds table as a **coarse traceability backstop**, not a
  per-change heavy-redesign blocker.
- **Tests.** New `tests/test_design_gate.py` (9 cases: unguarded-edit asks, either record allows,
  `.orbit/`/doc/backend/test files are never gated, ask-once-then-silent within a cycle, re-arms on
  a new cycle, fails open); `check-coherence.py` gained invariant **[F]** — every placed check/hook
  script's source file exists and every `*_CMD` constant references a file that's actually placed.
  Suite is now 13 files, all green.

## 0.23.1

**⚠️ Security — the safety guard is now hard to slip past, and it grew real teeth.** 0.23.0 fixed
the guard's *output shape* (blocks finally registered), but an independent adversarial review found
its *coverage* was still narrow and several one-token tricks walked right through: a subshell
`(git push --force)`, a brace group `{ …; }`, a `\`-newline continuation, `$( … )`/backticks, an
env-assignment prefix (`GIT_SSH_COMMAND=x git push --force`), and `bash -lc "…"` all evaded the
force-push deny — and it caught **zero** non-git destructive commands. This release rewrites the
matcher to see through all of those (it collapses line-continuations, strips env-assignment/subshell/
brace/`sudo`/`env` wrappers, and recurses into `sh -lc`, `eval`, and command-substitutions), and
ships **default non-git teeth**: it denies `rm -rf` of a root/home/system path, `push --mirror`, and
disk wipes (`dd`/`mkfs` to a device), and asks before `reset --hard`, `clean -f`, `rm -rf` of a
hidden/`.git`/`.orbit`/absolute path, and `curl | sh`. When a command's identity is genuinely
un-inspectable (its name is a shell variable), it **asks** rather than silently allowing. The guard
test suite went from 30 to **59 cases**, one per closed bypass. **Honest threat model, stated in the
README:** it stops obvious/accidental danger and common obfuscation — it does *not* claim to defeat
deliberate self-obfuscation (a script file, `python -c`, runtime aliases); nothing at the shell layer
can. **Re-run `/orbit`** to upgrade an existing repo's guard (the migration now carries 0.23.0 hooks
forward too, with a backup; a locally-customized guard is warned about, never overwritten).

Also, honesty and enforcement caught up to the claims:

- **The binds table no longer over-claims.** The old table said the guard "blocks secrets-branch
  push" (there was no such rule) and the hero said it "physically blocks… your DB" (it didn't). Both
  are rewritten to describe exactly what the default guard does, with a one-line pointer to add your
  own deploy/migration/secret-branch rules.
- **The runner enforces every configured limit.** `ralph_loop.sh` now also enforces the **per-cycle**
  token/cost budgets and the **gate-failure streak** (from `GATE_FAILED` lines the agent writes), not
  just per-run + iterations + runtime. `loop.py` enforces the per-cycle token budget too.
- **`loop.py --resume` no longer corrupts its own budget.** It restored spend and then re-added each
  memoized cycle's tokens (100→200) and reset the cycle counter to 1; both are fixed — a restored
  cycle is never re-metered, and the counter continues where it left off.
- **No more dead provisioning or inert config.** `active-learning.md` was copied into every repo but
  no role loaded it — now the Orchestrator does. `token_budget.per_cycle` was shipped but unread —
  now enforced. `check-coherence.py` is bidirectional (catches provisioned-but-never-loaded), and a
  new `test_config_consistency.py` fails if the config ships a knob no runner reads.
- **More tests.** New `test_uninstall.py`, `test_scaffold_idempotency.py`, and
  `test_config_consistency.py`; the suite is now 12 files, all run by `tests/run.sh` + CI.

## 0.23.0

**⚠️ Security/correctness fix — the safety guard now actually binds.** Earlier versions' `guard.py`
emitted its deny/ask decision in a JSON shape that current Claude Code **silently ignores**
(`{"permissionDecision": …}` at the top level instead of inside `hookSpecificOutput`). The effect:
the safety wall's blocks were **not enforced** — a `git push --force` the guard "denied" could still
run. This release ships the correct envelope, verified against the schema Claude Code actually reads,
with a 30-case test suite. It also closes a guard **bypass** where wrapping a dangerous command
behind `cd x && …` slipped past the matcher (the guard now splits on `&&`/`||`/`;`/`|` and inspects
each segment, including `sh -c` recursion). **If you scaffolded a project before 0.23.0, re-run
`/orbit`** — the migration detects the old, unmodified hooks and replaces them (with a `.bak` backup
and an announcement); a locally-modified hook is never overwritten — you get a warning + manual
diff instructions instead.

Everything else in this release is about making the pitch **true** rather than overclaimed:

- **The dead brakes now work.** `loop.py` enforces `approval_checkpoints` before tagged side-effects
  (FORBIDDEN raises; a `human` gate awaits), persists its budget across `--resume`, and survives a
  truncated checkpoint line. `ralph_loop.sh` meters real cost + tokens from
  `claude -p --output-format json` and stops when a budget is hit (falls back to iteration/runtime
  caps, and says so, if the JSON is unreadable — never crashes the loop).
- **Honest framing everywhere.** README carries a **binds / advisory / stub** table for every claim;
  the router is described (and now *injects itself*) as the **default lane the model can override**,
  not "the system's call, not the model's"; `dispatch()` is labeled a stub, not a feature.
- **Coherence, enforced.** New `scripts/check-coherence.py` fails CI on phantom skills or roster
  drift; shipped the real `safety-rules.md` playbook the safety gate was loading from thin air;
  `ROLES_CORE` is the single source of truth for the roster.
- **UX.** Install block on the README's first screen + a "pick ONE install path" warning; the
  settings-hook installer now **aborts** instead of clobbering an unparseable `settings.json`;
  `install.sh` won't `rm -rf` a non-git dir without `--force`/consent; `setup` no longer leaves stray
  symlinks and puts `orbit-uninstall` on your PATH; the first auto-upgrade asks **once** for consent.
- **QA executors, not sermons.** New `.orbit/qa/snapshot.py` (screenshot / pixel-diff / console) and
  `extract-tokens.py` (computed-style token check) — helpers, not a bundled browser: Playwright if
  installed, graceful degradation (exit 2, never a traceback) otherwise; the pixel-diff is pure-python.
- **Evidence.** `docs/case-study.md` (a real, reproducible harness walkthrough) and `docs/evals.md` +
  `evals/run-eval.sh` (harness invariants passing 3/3, plus an honest, un-faked task-quality A/B
  table). A README **Maturity** section states the young-project reality plainly.
- **Router accuracy** held at 69/69 on the test set with zero task→question misroutes; acks
  (`"yes"`, `"go ahead"`) correctly inject nothing.

## 0.22.1

Questions to the user must LOOK like questions. Field feedback: a clarifying question rendered as
prose (options crammed in parentheses) was scrolled past and timed out unanswered.

- **Every ask is now an `AskUserQuestion`** — 2–4 selectable options, the **recommendation FIRST
  labeled "(Recommended)"**, a one-line trade-off per option, several questions batched into one call.
  Canonical rule in `clarify-and-challenge.md` → "HOW to ask" + the scaffolded CLAUDE.md §10; wired
  into every ask-point: the router's ambiguous + surprise directives (route.py), decision briefs
  (presented AS the question, options selectable), goal-pipeline's two gates + user-challenges, the
  discovery one-way-door escalation, QA's visual-diff accept/reject, and the Designer's style pick
  (one option per style + "Other / remix"). Headless fallback: a set-off `❓ DECISION NEEDED` block.

## 0.22.0

Four capabilities from a market study of ~30 skills (gstack files read line-by-line + spec-kit, BMAD,
superpowers, Pocock, Ralph, ADR practice): a professional QA Engineer, a goal→whole-product pipeline,
the design-as-contract embedding, and the CTO hat. Active learning verified intact end-to-end and
extended to route design learnings → DESIGN.md and architectural learnings → ADRs.

- **QA Engineer (new core sub-agent) + `qa-validation` playbook** — validates the *product* against
  the *requirements*, requirement by requirement: a Requirements Traceability Matrix (every ID → test →
  verdict → evidence; PASS/CONCERNS/FAIL/WAIVED; any P0 fail or score <85 = not done), EARS acceptance
  criteria as the oracle, boundary/equivalence case derivation, report-only posture (never fixes),
  gstack-grade evidence discipline (screenshot per issue, retry-once, console per interaction), and a
  **pixel pass**: computed-style token assertions vs DESIGN.md + screenshot diffs vs the approved
  prototype at 3 viewports. Gate order is now Safety → Reviewer (diff) → QA (product) → Reporter.
- **`goal-pipeline` playbook** — send a goal, receive a whole polished product: spec (numbered
  requirements + EARS criteria, human gate #1) → story DAG of vertical tracer-bullet slices (each
  independently demoable, walking skeleton first) → parallel wave dispatch → backpressure-verify →
  run until every criterion is green → gap analysis → **mandatory polish pass**. Autonomy via the
  Mechanical/Taste/User-Challenge decision taxonomy: exactly 2 human stops per goal.
- **Design is a file contract** — the style-prototype winner becomes `design/approved.json` +
  **`DESIGN.md`** (persistent token authority future runs must read; fidelity rule: pixel-match the
  approved mockup) and the **verification triangle**: prototype = target → build to it → QA
  machine-verifies against it. A UI change with no approved.json behind it is a finding.
- **`architecture-decisions` playbook (the CTO hat)** — ADRs in `.orbit/decisions/` (append-only,
  supersede-never-rewrite, option matrix, a Confirmation check per decision), Choose-Boring-Technology
  innovation tokens, top-3 architecture characteristics → fitness functions the gates run; the
  Orchestrator loads accepted ADRs as constraints every cycle (settled direction never relitigated);
  the Reviewer flags architectural changes without an ADR.
- Wired end-to-end: scaffolder (ROLES_CORE + playbooks + `.orbit/decisions/`), roles.md, CLAUDE.md
  template, planner/orchestrator/reviewer/designer adapters, board colors (🧪 qa), CREDITS.md.

## 0.21.0

Listable in the Claude plugin directory — without losing the no-restart clone install. Per the docs,
Claude Code v2.1.142+ auto-discovers a root `SKILL.md` as a single-skill plugin, so adding two
manifests (no files moved) makes the *same* repo installable BOTH ways and submittable to the
official directory.

- Added `.claude-plugin/plugin.json` + `.claude-plugin/marketplace.json` (`source: "./"`).
  `claude plugin validate` passes. The root `SKILL.md` (with its `name:` frontmatter) is the plugin's
  single skill — no `skills/` subdir, no duplication.
- **Two install paths now:** (1) clone into `~/.claude/skills/orbit` + `./setup` — **no restart**,
  unchanged; (2) `/plugin marketplace add Abdulaziz-almoshen/orbit` → `/plugin install orbit@orbit` —
  one-time restart, and discoverable in the directory.
- `scaffold.py` path in SKILL.md now resolves `$CLAUDE_PLUGIN_ROOT` (plugin) **or**
  `~/.claude/skills/orbit` (clone), so setup works for both.
- Maintenance: keep `VERSION`, `plugin.json`, and `marketplace.json` (×2) in sync on each bump.

## 0.20.0

The goal gets genuinely **negotiated** before building — the gstack office-hours feel, done honestly.
A substantial goal now triggers the planning team's expert review FIRST, and the rule is calibrated:
**speak up only when you genuinely have something — then you MUST; if the goal's sound, proceed**
(no manufactured friction). Fixes "it doesn't negotiate or challenge the goal."

- **Router directive rewritten** (`route.py` TASK injection): on a substantial goal, run the planning
  team's expert pass before building — understand intent, bring discovery + prior-art/market +
  technical judgment to bear, and **if that reveals a wrong premise / a better or more scalable
  approach / a real risk / a reuse-over-build / a missing requirement, you MUST surface it with
  evidence (the "surprise: be smarter than the ask")**. If sound, say so in one line and proceed.
  Small/clear → just do it.
- **The surprise rule** added to `clarify-and-challenge.md` and `product-discovery.md`: the bar to
  speak up = "would a sharp senior engineer + PM who know this codebase genuinely flag this?" — if
  yes you must (with evidence), if no proceed. Never rubber-stamp a goal you can improve; never grill
  for ceremony. This reconciles "fast by default" (small tasks) with real negotiation (goals).

## 0.19.1

Empty / greenfield repo handling for the surface-driven team. On a repo with no code, surface
detection finds nothing — so Phase 0 now: asks the one product question, **derives the surfaces from
the answer + chosen stack**, and passes them to `--surfaces` (e.g. "a recipe app for iPhone with a sync
backend" → `mobile,api` → mobile-developer + backend-engineer + Designer). The team comes from *intent*,
not the empty code. Only when intent is truly unknown (headless / no answer) does it fall back to a
single generic `builder` (no Designer), which a later `/orbit` re-run upgrades non-destructively.

## 0.19.0

The team is now **provisioned from the project's code**, deterministically — not a fixed template +
a hopeful rename. Closes the gap that two different projects got the same agents.

- **`scaffold.py --surfaces <web,mobile,api,data,cli>`**: Phase 0 detects the repo's technical
  surfaces and passes them in; the scaffolder writes **one engineer per surface**
  (`frontend-engineer` / `mobile-developer` / `backend-engineer` / `data-engineer`, generated from the
  builder template with the name/title/scope substituted) and the **Designer + design playbooks +
  67-style catalog only when a UI surface (web/mobile) is present**. A backend API repo → just a
  `backend-engineer`, no designer; web+mobile+api → three engineers + designer; unknown stack → a
  single generic `builder`. `--frontend` kept as an alias for `--surfaces web`.
- **Universal spine vs project specialists** made explicit: the spine (dispatcher, orchestrator,
  product-discovery, market-researcher, planner, reviewer, reporter, safety-gate) is the same every
  project (those are needed everywhere); the **specialists vary by the code** (the per-surface engineers
  + the conditional Designer). The old Phase-4 "rename the generic builder" model step is gone — it's
  deterministic now.
- Wired through Phase 0 (detect → `--surfaces`), Phase 2 (the scaffold command), and Phase 4 (verify,
  don't recreate). Verified across api / web,api / web,mobile,api / data / none.

## 0.18.0

The planning phase becomes a real **discovery team**. Grounded in a study of product discovery
(Cagan's four risks, Torres's opportunity solution tree, JTBD), market/competitive research
(don't-reinvent prior-art, Dunford positioning), and multi-agent planning (BMAD's Analyst/PM/Architect
relay, spec-kit, plan-and-execute). The single Orchestrator/PM box is split into a relay.

- **Three new advisor sub-agents**, convened by the Orchestrator on the **substantial planning lane**
  (skipped on the fast lane; folded back into the Orchestrator on small/medium work):
  - **Product Discovery Manager** (`product-discovery`) — de-risks the *bet*: outcome + the user's job
    (JTBD), opportunity-solution tree, the four big risks, the riskiest assumption + its cheapest test.
    → `discovery-brief.md`.
  - **Market & Competitive Researcher** (`market-researcher`) — what exists / what they'd use instead /
    where the gap is, a **reuse-vs-build verdict**, graded feature matrix, Dunford positioning. Runs in
    **parallel** with discovery, timeboxed + cited. → `market-brief.md`.
  - **Planner** (`planner`) — turns the de-risked bet into the plan of record (thin vertical slices,
    sequenced by dependency + risk, proof bar per slice); reuses the decision-brief format. → `plan.md`.
- **Two new playbooks** (`product-discovery.md`, `market-and-competitive-research.md`) + the Planner
  reuses `planning-and-decision-briefs.md`. The Orchestrator stays the conductor + sole STATE.md writer
  and runs plan-review as the closing critic gate.
- Wired through roles.md (roster + relay + skill-library), the Orchestrator adapter, scaffolder
  (ROLES_ALWAYS + PLAYBOOKS_ALWAYS), CLAUDE.md template (§6/§7), SKILL.md (Phase 4 + reference map +
  "meet your team" + board legend), and `orbit-status` colors (🔭 discovery, 📊 market).
- **Proportional by design** (the anti-BMAD-bloat guard): full relay only for new/ambiguous work; lite
  artifacts; parallel not serial; reuse over reinvent. Attribution in CREDITS.md.

## 0.17.1

Auto-upgrade is now the **default** — installs stay current hands-off.

- `/orbit-upgrade` Step 1 defaults `auto_upgrade=true`: when the preamble finds a newer version it
  pulls it (`git pull`), **announces** it + shows what's new, and continues — no prompt. Opt out with
  `auto_upgrade=false` in `~/.orbit/config` (then `/orbit` just notifies and waits for a manual
  `/orbit-upgrade`). Preamble + README updated; also fixed a stale `skills/orbit-upgrade` path left
  over from the v0.12 root restructure.

## 0.17.0

Active learning — the system gets sharper as you use it. Grounded in a market study of how the best
tools do it (gstack /learn, Claude Code auto-memory, mem0/Letta/Zep, Cursor/Windsurf/Cline, Generative
Agents/Reflexion/spec-kit). **Posture: silent + automatic, no confirmation** (user's choice).

- **Append-only ledger** `.orbit/checks/learn.py` (record/recall) → `.orbit/learnings.jsonl` — the
  anti-thrash backbone every tool converged on: latest-wins dedup by key, confidence decay for
  unverified entries (user-stated never decays), an injection-text refusal, and trust-by-source. The
  ledger is the source of truth; markdown (CLAUDE.md/skills/decisions) is a *promoted view*, not
  rewritten every turn.
- **The gate** (`references/playbooks/active-learning.md`, provisioned always): event-triggered (a
  user correction / a verified outcome / an end-of-major-change checkpoint — never every message,
  default no-op); two-stage (salience ≥ 7 with anchor examples + recurring/verified/non-obvious/
  broadly-applicable/reason-carrying); **route-by-kind** to the right home (convention→CLAUDE.md,
  technique→a skill incl. the defaults, methodology→a playbook, dated choice→STATE.md decision log);
  dedup ADD/UPDATE/NOOP (NOOP default, paraphrases collapse).
- **Safety that needs no prompt:** a **user-origin gate** — a standing rule is only promoted from the
  user's *own* message, never tool/web/PR text (the defense that makes silent writes safe; Windsurf's
  no-review auto-memory got prompt-injection-exploited). Everything is git-revertible.
- **Silent but visible:** no confirmation, but a quiet `📝 Learned: … → <file>` on write and
  `📝 Applying what you taught me: …` when a past learning changes behavior — the "I'm improving the
  system" payoff. Wired into the loop's UPDATE phase via the CLAUDE.md template, methodology, roles,
  and the scaffolder.

## 0.16.0

The team gets a voice — the wait behind the scenes is never empty anymore.

- **Motivational team voice on the live board (mandatory).** Every cycle's inline "team board" now
  carries three genuine beats: (1) a one-line **"why this task matters"** at kickoff (what it unlocks,
  pulled from §3 success criteria), (2) a progress-aware **"your team's heads-down — N of M done,
  almost there, sit tight"** during the pause while sub-agents work, and (3) an **earned close** on
  completion (who did what + the impact, then "what's next?").
- **Guardrails:** tone calibrates to the task (upbeat for a playful feature; warm-but-serious for
  governance/security/money/medical — never confetti on something sensitive), lines vary cycle to
  cycle, stay short and honest (no claimed-but-unreal progress). Documented in `observability.md` →
  "The team voice"; enforced via SKILL.md Phase 6.5.

## 0.15.0

The Designer now offers **67 real styles** and **lets the user pick from openable HTML prototypes** —
mandatory on every design request.

- **67-style palette folded into the Designer** (not bolted on): bundled
  `references/playbooks/design-styles/` (67 token-systems — minimal, brutalism, glassmorphism,
  editorial, luxury, retro, neon, …) + an auto-generated catalog `design-styles.md` (families + a
  full table with each style's vibe + colors). Adapted from **bergside/awesome-design-skills** (MIT,
  attributed in `CREDITS.md` + the bundled LICENSE). It's integrated with `design-methodology.md`
  (the *how*), not separated.
- **Mandatory style-prototype selection gate.** On any new component/module/screen the Designer must
  shortlist 2–4 fitting styles, build a **standalone HTML prototype of each** (same component, real
  content) under `.orbit/artifacts/<cycle>/previews/`, **open them for the user**, and the user
  **picks one** before any production build. Wired through `design-methodology.md`, the Designer
  role/adapter, `profiles/frontend.md`, and the **Reviewer** (a UI change with no recorded style
  selection doesn't pass).
- **Scaffolder** (`--frontend`) now provisions the whole catalog (`design-styles.md` + the 67-style
  `design-styles/` dir) into `.orbit/skills/`; backend/CLI/data repos don't get it.
- **`CREDITS.md`** added — proper attribution for awesome-design-skills (MIT), the frontend-design
  methodology (Apache-2.0), and the gstack-inspired technical-review (distilled, MIT).

## 0.14.0

A technical team sized to the project, and a live view that shows in the desktop/web app too.

- **One engineer per surface.** Phase 0 now detects the distinct technical surfaces (web frontend,
  mobile app, backend/API, data) and Phase 4 stands up **one engineer per surface** —
  `frontend-engineer` + `mobile-developer` + `backend-engineer` as needed, each with its own skill,
  running in parallel under the Planner. A single-surface prototype still gets one; a multi-surface
  product gets the full bench. (Was: a single generic builder + "one extra specialist.")
- **Visible everywhere — the desktop-app fix.** The pinned checklist (IDE) and `orbit-status`
  (terminal) are surface-specific; in the **Claude desktop app / claude.ai web** there's no panel or
  terminal. So the loop now **always renders a compact "team board" inline in chat each cycle** (emoji
  role colors matching the dashboard) — the one renderer that works on every surface. Documented as
  Renderer 0 in `observability.md`; Phase 6.5 now does three things (data files + inline board +
  native list).

## 0.13.0

The "meet your team" closing + per-project team tailoring — setup now ends like a capable team
reporting for duty, with agents named to the stack.

- **"Meet your team" closing message (Phase 7):** setup now ends by introducing *only the roles it
  actually stood up*, by their project-specific names, each with its skill and its **live-view color**
  (cyan dispatcher, magenta planner, green engineer, violet designer, yellow reviewer, red safety,
  grey reporter) — then an encouraging "I'm ready, what's the first task?" Warm, not a file manifest.
- **Per-project tailoring (Phase 4):** the generic *builder* is renamed to the stack —
  `frontend-engineer` / `backend-engineer` / `data-engineer`; roles the project doesn't need are
  dropped (no Designer on a backend/CLI/data repo); team scales to project size. Domain skills are
  authored **concurrently** to keep setup fast.
- **Dashboard colors:** added `dispatcher` (cyan) and `designer` (violet) to `orbit-status` so the
  team intro matches the live checklist exactly.

## 0.12.0

True gstack-style install: clone into the skills dir + `./setup`, with `git pull` updates.

- **The repo is now the skill dir.** Moved `SKILL.md` + `references/`, `assets/`, `scripts/`,
  `evals/`, and `orbit-upgrade/` to the repo **root** (history preserved via `git mv`), so the
  canonical install is exactly gstack's:
  `git clone --single-branch --depth 1 …/orbit.git ~/.claude/skills/orbit && cd ~/.claude/skills/orbit && ./setup`.
- **New `./setup`** entrypoint — chmods the helpers and symlinks the `orbit-upgrade` sub-skill to
  the top level so `/orbit-upgrade` resolves. **`install.sh` is now a thin curl wrapper** that does
  the same clone + `./setup`.
- **Updates are `git pull`** — the install dir is a real git checkout, so `/orbit-upgrade` does a
  fast incremental fetch/reset (no re-download), exactly like gstack.
- **Dropped the marketplace plugin** (`.claude-plugin/`) — a root-level skill can't also be a
  marketplace plugin, and the marketplace path was what caused the restart problem. One model now:
  clone → live discovery → no restart.
- Fixed the internal `scaffold.py` path refs (now `~/.claude/skills/orbit/scripts/scaffold.py`).

## 0.11.0

Orbit now **controls the project** — a deterministic router decides routing, not the model. This
is the real fix for "nothing triggers Orbit when I just talk to Claude."

- **New `UserPromptSubmit` hook (`route.py`)** — the system's first actor on **every** message,
  before the model responds. It classifies the prompt *in code* (task verbs → TASK, interrogatives →
  QUESTION, else AMBIGUOUS) and injects the routing decision as a live instruction: a task routes
  through the loop, a question is answered directly. The call is the **system's, not Claude's**, and
  it's present every turn — routing is no longer a passive §10 rule the model may ignore. Best-effort
  emits the decision to `.orbit/activity.jsonl` so the system "acts first" visibly. Fails open; never
  blocks a prompt.
- **`scaffold.py --install-hooks` now wires BOTH hooks** (idempotent, backed up, announced): the
  router (`UserPromptSubmit` → route.py) and the safety wall (`PreToolUse` → guard.py).
- **Honest reframe across SKILL.md / CLAUDE.md template / README:** routing is now *system-decided +
  force-injected every message* (a real control layer), while the model still *executes* the loop (a
  hook can't run the sub-agents). "Orbit controls the project" is now true at the decision layer, not
  aspirational. `orbit-uninstall` already strips both hooks.

## 0.10.1

Tighten the update check (it was advisory, silent, and easy to skip).

- **Mandatory + first:** the preamble is now "STEP 0 — run BEFORE anything else, do not skip,"
  so the model reliably runs it the moment `/orbit` loads.
- **Observable:** it now **always prints one line** (the running version, or the upgrade offer) —
  silence can no longer hide a skipped or throttled check. The wording is honest: a fallback line
  says "running v{x}", not a guaranteed fresh re-check.
- **Robust paths:** resolves the install via `CLAUDE_CONFIG_DIR` too, so it finds the skills-dir
  install (no `.git` → it checks the latest VERSION on GitHub via curl) and the marketplace plugin.
- Clarified it checks **GitHub** (git fetch if a clone, else curl raw), throttled once/24h, never
  blocks offline. Still prompt-driven (a skill can't force a run) — hard enforcement would need a
  session hook; this is the right level short of that.


## 0.10.0

Install drops from ~10 minutes to under a minute. Field feedback: a fresh `/orbit` took ~10 min
because the model read ~14 reference docs and hand-authored ~20 scaffold files one at a time.
Research confirmed every comparable tool (gstack, spec-kit, BMAD) lays its skeleton down with a
deterministic script and uses the LLM only for the project-specific spec — Orbit was the anomaly.

- **`scaffold.py` now lays down the ENTIRE deterministic skeleton in one run:** the engine files
  (as before) **plus** `.orbit/STATE.md`, the skill-library playbooks copied into `.orbit/skills/`,
  and the full standard team written to both `.claude/agents/*.md` (adapters, verbatim) and
  `.orbit/roles/*.md` (specs, frontmatter-stripped). New `--frontend` flag stands up the Designer +
  design playbooks; `--install-hooks` unchanged. Never overwrites; idempotent.
- **Four new bundled role adapters** (`dispatcher`, `orchestrator`, `builder`, `reporter`) join the
  existing `reviewer`, `safety-gate`, `designer` — so the scaffolder ships a complete working team.
- **SKILL.md reworked around the fast path:** a new "the skeleton is a script, not an essay"
  principle; Phase 2 is now a single `scaffold.py` run; Phases 3–5 shrink to "author the ONE bespoke
  file (CLAUDE.md) + the one domain skill + tune thresholds — don't recreate what the script wrote."
  Explicit instruction NOT to read the reference docs to build the scaffold. This is what removes the
  ~14 sequential reads + ~20 hand-authored files.
- Result: setup = one deterministic script + a couple of targeted edits, matching how gstack /
  spec-kit / BMAD scaffold. The intelligence stays where it belongs — characterizing the repo and
  writing the domain-specific CLAUDE.md.


## 0.9.0

A real **technical-review** playbook for the Reviewer — the sub-agent responsible for technical
quality. Distilled the transferable methodology from a mature pre-landing-review + QA + eng/DX
review toolkit into one self-contained, vendor-neutral playbook (no external dependency).

- **New playbook `technical-review.md`** (`references/playbooks/`), provisioned to the **Reviewer**
  on any code/technical repo. It encodes: the **severity × confidence gate** with a **quote-the-line**
  verification rule (you must cite `file:line` or the finding is unverified — kills the false-positive
  class); the full inspection surface (correctness/enum-completeness, security, concurrency, data
  migrations, tests, performance, API contract, maintainability, with security + migrations always
  run); **prove-don't-assume** verification (run the tests, "code that *handles* a deliverable is not
  the deliverable"); engineering-judgment lenses (blast radius, reversibility, boring-by-default,
  essential-vs-accidental complexity, a **complexity tripwire** that escalates instead of proceeding);
  auto-fix-vs-ask; the output format + cycle verdict; and an anti-nitpick / anti-rubber-stamp list.
- **New Reviewer sub-agent adapter** `assets/claude-agents/reviewer.md` (loads the playbook; reviews,
  never lands; gate power).
- Wired through `roles.md` (Reviewer row + skill-library table), SKILL.md (Phase 3 provisioning +
  reference map), and the scaffolded CLAUDE.md skills index (§7). Advisory like the other roles —
  the binding wall remains the PreToolUse safety hook.


## 0.8.0

Fast by default + no-restart install. Two pieces of field feedback drove this: "the thinking
takes too long" and "installing forces me to close the session and start a new one."

- **No-restart install (like gstack).** New `install.sh` installs Orbit as a Claude Code
  **user skill** in `~/.claude/skills/` (one line: `curl … | bash`). Claude Code watches that
  folder and discovers skills **live**, so `/orbit` works immediately — no restart. The
  marketplace plugin stays as an alternative (it's the path that needs a restart, since
  marketplace plugins resolve at startup). Verified against the docs: the PreToolUse safety
  hook also reloads live (fires on the next command), so *nothing* in setup needs a restart —
  messaging in SKILL.md Phase 6a/7 and the README updated to say so.
- **`/orbit-upgrade` covers the new install:** a skills-dir install self-updates by re-running
  the installer (re-fetch + overwrite, no restart); the plugin-cache path still defers to
  `/plugin update`. `orbit-uninstall` now prints how to remove either install shape.
- **Fast by default (no new command, no "fast mode", no lost rigor).** Routing (`§10`) gained a
  proportional rule: a **small · clear · reversible** task is just *done* (reason internally,
  act, self-check) while **substantial · ambiguous · irreversible** work runs the full loop —
  the model picks the lane by judgment, not a command. The deliberation that *does* run now
  goes **in parallel** (infer ∥ approaches ∥ risks), which is both faster and *smarter* (more
  perspectives at once) than the old serial plan→brief→review chain. Clarify-and-challenge no
  longer pings one question at a time — it infers first and batches the few that matter into
  one message. Updated across `§10`, `clarify-and-challenge`, `planning-and-decision-briefs`,
  `methodology`, `roles`, and SKILL.md. The intelligence (clarify, challenge, decision briefs,
  Designer) is unchanged or sharper — it just stops taxing trivial work.


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
