<p align="center">
  <img src="assets/orbit-readme-header.png" alt="Orbit - self-prompting agentic workflows" width="100%">
</p>

<div align="center">

# Orbit

### Stop prompting your agent. Build a system that prompts itself.

#### Give Orbit the goal. It selects the smallest expert graph that can prove it, watches the whole run, and commits the result.

Orbit turns a product repository into a durable, observable agentic loop: it remembers the work,
plans the next move, delegates focused tasks, **watches the full role tree live for drift**, checks the
result, repairs failures, and returns a proven local commit—interrupting only for true blockers.

![version](https://img.shields.io/badge/version-0.61.0-2b6cb0)
![license](https://img.shields.io/badge/license-MIT-2f855a)
![Claude Code](https://img.shields.io/badge/Claude%20Code-plugin-6b46c1)
![observable](https://img.shields.io/badge/observable-live%20dashboard-e8590c)
![live observer](https://img.shields.io/badge/live%20observer-full%20role%20tree-e8590c)

</div>

## Why Orbit

Most agent sessions forget context, repeat failed work, and leave you watching a black box. Orbit
gives the work a durable operating system:

- **User memory that binds delivery:** every real request advances a machine checkpoint; strong
  corrections and “always/never/must/remember” signals enter an append-only event ledger immediately.
  Orbit reviews memory at least every five requests and again after the latest request before shipping.
  Pending or stale memory blocks CPO/Stop; a no-new-signal checkpoint is valid, invented preferences are not.
- **Plan and progress:** every run has a visible checklist, owner, phase, gate, and next action.
- **Enforced capabilities without ceremonial fan-out:** Orbit chooses a protected role graph by gear.
  T1 proves with Planner/Reviewer/QA/Reporter; T2 adds Safety/CPO; T3/T4 add Discovery/BA/Market;
  UI adds Design. Every required owner is machine-gated, but irrelevant roles are pruned.
- **Iterative quality:** failures become evidence-backed repair packets and return to the loop.
- **Scenario-complete QA:** every delivery executes happy, alternate, negative, boundary,
  authorization, and failure/recovery journeys with observed artifacts—not only ticket assertions.
- **Dependency regression:** QA maps changed units to direct and transitive dependents plus related
  user flows, then captures focused, integration, and relevant wider-suite command results.
- **Pixel evidence on every UI delivery:** every changed route/screen requires baseline, actual, and
  computed diff images at 375×812, 768×1024, and 1440×900, together with token fidelity, accessibility, responsiveness, and
  zero console errors. “Trivial” changes reduce design ceremony, not visual QA.
- **TasteSkill-powered Designer:** frontend installs vendor the complete canonical TasteSkill v2
  framework into the Designer, with its MIT license. Landing pages, portfolios, editorial work, and
  redesigns get the full anti-slop/art-direction method; dashboards and multi-step product UI retain
  Orbit's functional design rules instead of inheriting inappropriate marketing-page recipes.
- **Machine-gated before CPO:** `.orbit/checks/delivery-quality-gate.py` validates the exact-commit
  evidence bundle. A `qa-engineer done` event or green narrow test is not sufficient.
- **Independent QA:** an opt-in second provider reviews an exact commit against an armed acceptance
  manifest; code or manifest changes invalidate the approval.
- **CPO acceptance:** after QA proves the work was built right, a CPO role judges whether the *right
  thing* was built — the deliverable against your original goal. The run cannot finish without a
  commit-bound `ACCEPT`; `ITERATE`/`REDEVELOP` verdicts return the work with change orders, and every
  verdict grows a per-project user-model (`.orbit/skills/user-model.md`) so each iteration lands
  closer to what you actually want.
- **Reviewer choice:** install-time detection offers Codex, isolated Claude QA, or both. Missing providers
  block instead of silently weakening the gate; the choice never grants project export consent, and
  Arabic/RTL QA follows the project, not the provider.
- **Adversarial thinking:** a cheap counterfactual probe challenges risky assumptions before build.
- **Model discipline:** Sonnet handles normal work; the Opus 4.8 Advisor is invoked on demand for
  expensive decisions.
- **Trusted resource kernel:** root-turn usage is reconciled from Claude's transcript; every Agent
  call is reserved before launch and charged from actual usage after return. T0–T4 have hard ceilings, T5/T100 clamp to T4, ten percent is protected
  for closeout, and budget exhaustion returns a resumable checkpoint—never an unmetered retry.
- **Parallel work:** independent workers use isolated Git worktrees instead of fighting over one checkout.
- **One full-loop Claude observer:** a single watchdog is attached to the root orchestrator with
  descendant propagation, so it sees Discovery through delivery without paying for a duplicate
  observer beside every role. Its state is visible as `armed`, `watching`, `intervention`, or `clean`.
- **Autonomous delivery:** reversible product and engineering decisions are Orbit's job. It asks only
  for missing access, human authority over irreversible/external actions, or an expensive product fork
  that evidence cannot resolve. Green work is returned as a scoped local commit with proof.
- **Non-interactive Bash safety:** routine commands—including normal push/merge—proceed without a
  hook prompt. Catastrophic commands are hard-denied; risky or uninspectable commands are denied
  rather than pausing for confirmation. The `PreToolUse:Bash` hook never emits `ask`.
- **Always-on routing:** a deterministic hook classifies every message before the model sees it.
  In the default `always` mode each real request engages the loop and every reply opens with a
  visible `⏣ orbit` lane marker — you always see Orbit take the request. Acks and "don't…"
  messages stay silent; set `router.mode: "smart"` for conservative routing.

## The loop

<picture>
  <img src="assets/orbit-loop-observer.svg" alt="The Orbit loop: one goal flows through every enforced specialist while a real Claude watchdog surrounds and observes the full role tree; green work ends in a proven commit." width="100%">
</picture>

> **New in Orbit 0.61:** AgentPrune's spatial-temporal graph insight is now an enforceable resource
> kernel. One root observer watches the descendant tree; gear selects the smallest protected role DAG;
> Agent hooks reserve and charge actual tokens; compaction carries a bounded goal/evidence checkpoint;
> every tier is capped. Quality gates and the user's goal are protected from pruning.

> **New in Orbit 0.57:** QA is evidence-enforced before CPO. The gate chain is now
> Safety → Reviewer → QA Engineer → **Delivery Quality** (scenario matrix + dependency regression +
> three-viewport computed pixel diffs) → Independent QA (opt-in) → **CPO acceptance** → done. CPO must
> rerun the gate, inspect raw evidence, and bind its ACCEPT to the evidence file's exact SHA-256.

> **New in Orbit 0.58:** user memory is an enforced architecture, not an optional note. The router
> records requests and important corrections into `.orbit/memory/`; the five-request review clock is
> mechanical, every delivery requires a review after the latest request, and CPO ACCEPT binds the exact
> memory checkpoint SHA-256 alongside QA evidence.

> **New in Orbit 0.50:** the **CPO** closed the goal-fidelity gap. Every
> earlier gate verifies the build against artifacts the system wrote for itself; the CPO is the
> user's proxy — it re-anchors on the goal you actually stated, returns the deliverable
> (`ITERATE`/`REDEVELOP`) when the goal isn't served, and records what it learns about your
> taste in a per-project user-model that every later run inherits.

> **Enforcement means the declared gear is binding.** Required owners must produce completion
> evidence; irrelevant owners do not run. Missing evidence blocks Stop. A role name in prose is not
> evidence, and a larger gear never creates an uncapped budget.

Three controls make the loop meaningfully safer and iterative:

1. **Counterfactual preflight:** identify the riskiest assumption, run the cheapest useful probe,
   and backtrack to discovery or planning when evidence disagrees.
2. **One propagated observer:** inspect discovery quality, analysis, planning, implementation, every gate,
   and reporting for drift, stalled/repetitive work, rubber-stamping, or unsupported proof. Healthy
   work produces no advisory, but its watcher state remains visible.
3. **Bounded repair:** capture the failure, owner, root cause, required change, and regression test;
   repair it and return to the original gate. Repeated failure escalates to Advisor or a human.

### Why the observer matters

| Without live observation | With Orbit 0.56 |
|---|---|
| Weak discovery or a wrong approach may travel through the loop. | The watchdog can flag generic ideas, missing evidence, or delivery drift at the role where it begins. |
| The worker must remember every constraint while optimizing for completion. | A separate Haiku observer has one narrow job: notice compounding mistakes. |
| Test weakening may only appear in the finished diff. | Attempts to skip, weaken, delete, or reverse-engineer tests can be challenged immediately. |
| More code and tokens accumulate before repair begins. | One early advisory can avoid an expensive downstream repair cycle. |

The expected steady state is silence. The observer is a **drift tripwire**, not another worker and
not a security boundary; Safety, Reviewer, QA, approval checkpoints, and hard limits still decide
whether the result may proceed.

## Install

Choose one installation path. Do not install both the clone and marketplace plugin.

```bash
git clone --single-branch --depth 1 https://github.com/Abdulaziz-almoshen/orbit.git \
  ~/.claude/skills/orbit
cd ~/.claude/skills/orbit && ./setup
```

Or:

```bash
curl -fsSL https://raw.githubusercontent.com/Abdulaziz-almoshen/orbit/main/install.sh | bash
```

Then open a product repository and run `/orbit`. The preamble checks for updates and quietly repairs
safe scaffold drift: it adds missing Orbit-owned files, preserves custom files and disabled hooks,
and skips projects under an active writer lock.

## Command map

| Command | Purpose |
|---|---|
| `/orbit` | Scaffold a project or merge safe template updates. |
| `/orbit:orbit-run <task>` | Force a task through the governed loop. |
| `scripts/orbit-status --follow` | Follow agents, checklist, gates, budget, and confidence. |
| `scripts/orbit-dashboard --once` | Print the redacted status snapshot; `--port N` serves a read-only board. |
| `scripts/orbit-pet start` | Show the always-on-top macOS pet that narrates tasks, questions, QA, commits, and deployment. |
| `scaffold.py --enable-reporter` | One-time trusted-project activation: hooks, terminal QA scene, local board, and macOS pet. |
| `scripts/orbit-qa-hook install` | Opt in to automatic post-commit QA and the exact-commit pre-push gate after project approval. |
| `orbit-doctor` | Inspect scaffold drift; `--fix` applies only safe managed-hook refreshes. |
| `scripts/orbit-lock status` | Inspect the current checkout lease. |
| `scripts/orbit-lock takeover --reason "..."` | Atomically break, acquire, and verify a handoff. |
| `scripts/orbit-worktree create --task <slug>` | Create an isolated worker branch and checkout. |
| `scripts/orbit-worktree finish <worktree>` | Submit changed files, tests, summary, and budget to the merge queue. |
| `scripts/orbit-memory review` | Review the learning ledger before promoting anything durable. |
| `/orbit-upgrade` | Upgrade the installed plugin. |

## Parallel work

The coordinator owns the plan, integration branch, `STATE.md`, and final QA. Workers write in separate
branches:

```text
Coordinator: plan -> integrate -> verify
     |-- orbit/task-a  -> worker + private worktree
     `-- orbit/task-b  -> worker + private worktree
```

Each worker receives a bounded token/USD reservation and returns a completion packet. The shared
registry lives in Git's common directory; each worktree has its own local Orbit lease. This means
parallel sessions are normal without allowing two sessions to edit the same checkout.

```bash
scripts/orbit-worktree create --task concierge-fix
scripts/orbit-worktree status
scripts/orbit-worktree finish ../project-orbit-concierge-fix \
  --summary "Implemented and tested the concierge fix" \
  --tests "pytest -q"
```

The coordinator reviews the packet, resolves conflicts, runs integration QA, and merges. Orbit does
not silently merge worker branches.

## Live visibility

Orbit is designed to be watched without reading a wall of model prose:

```text
Orbit  |  Build  |  3/8 complete  |  1 active  |  budget $0.42/$1.25

> frontend-engineer  building the requested slice
  reviewer            queued: checks regressions
  safety-gate         queued: confirms approval boundaries
```

In Claude Code, the native checklist is the primary surface. In headless or portable runs, use
`scripts/orbit-status --follow` or the read-only dashboard.

## Observer agents: real, full-loop, and visible (experimental Claude capability)

Orbit's Claude Code adapter pairs the root Orchestrator with one descendant-propagating
`.claude/agents/watchdog.md`:

```text
Goal → Orchestrator → gear-selected expert DAG → Safety → Review → QA → CPO → Report
          │                     descendant read-only activity digest                    │
          └──────────────────────▶ Watchdog (Haiku) ────────────────────────────────────┘

No finding = no message. The worker continues uninterrupted.
```

The watcher sees Claude Code's truncated, read-only activity digest and stays silent unless a short
advisory can prevent shallow discovery, stalled work, scope drift, weakened tests, rubber-stamped
gates, or unsupported proof. It cannot edit,
block the worker, or grant user authority, and it does not replace the final Reviewer or QA gates.

Every scaffold and auto-heal enables the project experiment, installs a missing watchdog, restores
required hooks, and migrates old duplicate child-watchdog blocks without replacing customized role
bodies. Explicit env values and alternate custom observers are preserved. To enable it manually:

```bash
CLAUDE_CODE_EXPERIMENTAL_OBSERVER_AGENTS=1 claude
```

This Claude capability remains undocumented, experimental, and remotely gated; Orbit cannot honestly
guarantee that Anthropic's server enables it. Orbit does guarantee the project setting, agent
root frontmatter, descendant propagation, update repair, visible `observer.json` state, and
regression tests. When Claude withholds the capability, roles continue and the final gates still bind.

## What binds

| Capability | Guarantee |
|---|---|
| Safety wall | Trusted Bash guard is non-interactive: routine commands allow, catastrophic commands deny, and no `ask` confirmation is ever emitted. |
| Writer lease | One writer per checkout; reads remain available. `takeover` verifies the new owner before writes resume. |
| Worktree isolation | Separate workers can write concurrently in separate Git worktrees. |
| Runtime and budget caps | The trusted Agent hook enforces per-session token/call ceilings on native Claude sessions; `ralph_loop.sh` and `loop.py` retain iteration, runtime, token, and dollar limits. |
| Checkpointing | Durable runner state persists budget and progress across resume. |
| Telemetry | Hooks observe and redact activity; they fail open and never block work. |
| Capability completion | Strict Stop contract blocks substantial work when a mandatory role has no completed post-route event; UI projects additionally require Designer. |

Role activation is mechanically checked; the quality of discovery, analysis, design, and review
judgment remains model-governed. Advisor invocation and the portable runner's model `dispatch()` seam
also remain model-governed. The
Claude Code path is the complete default path; wire `dispatch()` before using `loop.py` with another
orchestrator.

## Model and cost policy

Orbit Lite is the default:

- gear-required stage owners run sequentially, one at a time;
- maximum two isolated workers by default;
- focused packets instead of full repository history and telemetry;
- the Sonnet Executor lane for ordinary work;
- one Opus Advisor call for an architectural fork, safety uncertainty, or repeated gate failure;
- explicit per-cycle and per-run token, dollar, runtime, and context limits.

The configured graph—not reassurance—controls concurrency and required owners. The goal is complete
accountability without uncontrolled fan-out.

## Frontend projects

UI repositories receive a mandatory Designer stage, a 67-style design catalog,
prototype-before-build guidance, and visual QA helpers. A substantial UI run cannot stop without a
completed Designer event. The design gate also records the chosen direction and asks when a UI
change has no design decision on record; visual judgment itself remains human/model work.

## Self-update

```text
/orbit-upgrade
```

The installer reports the resolved commit and version. Project scaffolds are separate snapshots; the
automatic preamble refreshes only safe Orbit-owned drift and never overwrites custom project files.

For a manual install refresh:

```bash
cd ~/.claude/skills/orbit
git fetch origin
git reset --hard origin/main
./setup
```

## Repository layout

```text
bin/                  trusted commands and hooks
assets/               scaffolded engines, checks, agents, and wrappers
references/           playbooks, role specs, and templates
scripts/scaffold.py   deterministic project provisioning and migration
tests/                regression, safety, budget, and lifecycle tests
```

## Development

```bash
bash tests/run.sh
python3 scripts/check-coherence.py
python3 bin/orbit-verify --root .
```

Before a release, bump `VERSION`, add a `CHANGELOG.md` entry, regenerate `checksums.txt`, and run the
full suite. The current channel is an unsigned development channel; checksum verification detects
modification but is not a cryptographic signature.

## License

MIT
