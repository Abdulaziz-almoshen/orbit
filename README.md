<p align="center">
  <img src="assets/orbit-readme-header.png" alt="Orbit — governed agentic delivery" width="100%">
</p>

<div align="center">

# Orbit

### A Claude Code plugin that turns a repo into a governed agentic loop.

You give it a goal. It sizes the work, dispatches a small team of subagents through
hard quality gates, keeps a live board in your terminal, and refuses to call the
work done until the gates have evidence.

![version](https://img.shields.io/badge/version-0.67.1-2b6cb0)
![license](https://img.shields.io/badge/license-MIT-2f855a)
![Claude Code](https://img.shields.io/badge/Claude%20Code-plugin-6b46c1)

</div>

## How a goal runs

1. **Route** — a deterministic hook classifies every message (task / question) and sizes a gear, T0–T4.
2. **Evidence** — intake builds a bounded repository packet (≤1 hop, ≤12 files, ~4k tokens), not a whole-codebase prompt.
3. **Deliver** — the gear's mandatory roles run as real subagents on a visible board; a token ledger meters each dispatch.
4. **Prove** — Safety, Review, and QA return verdicts with evidence; a CPO subagent compares the deliverable to your original goal.
5. **Ship** — the Stop hook blocks the finish until required owners ran, QA evidence exists, and the CPO wrote a commit-bound ACCEPT.

## The gear decides the team

| Gear | Fires on | Mandatory roles |
|---|---|---|
| T0 | questions, trivial patches | none — direct answer |
| T1 | small, clear, reversible | Planner · Builder · Reviewer · QA · Reporter |
| T2 | normal product work | T1 + Safety + CPO |
| T3 | broad or uncertain work | T2 + Discovery + BA + Market Research |
| T4 | production / irreversible | T3 + checkpoints + human gates |

UI work adds a Designer. Each gear carries a token budget (T1 25k → T4 240k hard ceiling);
on pressure the loop trims packets, downgrades models, or pauses with a checkpoint — it
never silently drops a quality gate. Everyday work runs on the Sonnet 5 Executor; the
Opus 4.8 Advisor is on-demand only, for expensive forks and repeated gate failures.

## What is mechanically enforced vs. what isn't

**Enforced by hooks and scripts** (works regardless of model mood): message routing, the
gear-scaled role contract, per-goal token ledgers with pre-dispatch reservations, the
destructive-command wall, QA scenario/viewport evidence checks, the CPO/Stop finish gate,
and the live status board.

**Model judgment** (not enforceable): the *quality* of plans, reviews, and verdicts. Orbit
can force a reviewer to run and to cite evidence; it cannot force the review to be smart.

## Install

Pick one:

```bash
git clone --single-branch --depth 1 https://github.com/Abdulaziz-almoshen/orbit.git ~/.claude/skills/orbit
cd ~/.claude/skills/orbit && ./setup
```

```bash
curl -fsSL https://raw.githubusercontent.com/Abdulaziz-almoshen/orbit/main/install.sh | bash
```

Then, in a product repo:

```text
/orbit
```

The scaffolder detects surfaces, provisions roles/playbooks/hooks, and never overwrites your
customized files. It also **never writes sandbox or permission restrictions** — your capability
envelope stays yours (v0.62–0.67.0 briefly violated this; 0.67.1 removed it and migrates it away).

## Daily use

| Command | Purpose |
|---|---|
| `/orbit:orbit-run <goal>` | Run a goal through the loop |
| `scripts/orbit-status --follow` | Watch owners, gates, budget |
| `scripts/orbit-dashboard --port 8765` | Read-only local web board |
| `scripts/orbit-context doctor` | Context-bloat stoplight (compact / digest to fix) |
| `scripts/orbit-budget status` | Inspect the per-goal token ledger |
| `orbit-doctor --fix` | Repair managed scaffold drift |
| `/orbit-upgrade` | Update the plugin, then heal projects |

The terminal board is ≤4 lines: goal + gear + cost · what's running now (the question itself,
in red, when Orbit is blocked on you) · one role-state strip · the Claude→Codex QA relay.

## Optional: independent QA

With `independent_qa` enabled and export approved, a second provider (Codex or a fresh Claude)
reviews the exact committed snapshot and returns a verdict. Off by default; nothing leaves your
machine until you approve it.

## Honest limits

- **The Claude Code path is the product.** The portable runner (`loop.py`) still has a stub
  `dispatch()`; wiring another orchestrator is yours to do.
- **Token numbers are estimates** (bytes ÷ 4), used as stoplights and ledgers — not billing truth.
- **The watchdog observer** rides an experimental, remotely-gated Claude capability. When it's
  unavailable, the deterministic gates still bind; the tripwire doesn't.
- **Repository evidence is bounded, not omniscient.** Python gets real AST extraction; other
  languages get conservative, confidence-labeled extraction. Validate against your own repos.
- **Gates guarantee process, not brilliance.** A forced review with citations is still only as
  good as the model writing it.
- Dev channel is checksum-verifiable (`python3 bin/orbit-verify --root .`) but **unsigned**.

## Repository

```text
bin/         trusted hooks and CLIs      assets/      scaffolded engines, checks, roles
references/  playbooks and templates     scripts/     deterministic install + migration
tests/       57 contract test files      → bash tests/run.sh
```

History in [CHANGELOG.md](CHANGELOG.md). License: MIT.
