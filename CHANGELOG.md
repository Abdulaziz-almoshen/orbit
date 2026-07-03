# Changelog

All notable changes to the `orbit` skill are documented here. `VERSION` is the single source of
truth — the update checker compares it against GitHub.

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
