<p align="center">
  <img src="assets/orbit-readme-header.png" alt="Orbit — governed agentic delivery" width="100%">
</p>

<div align="center">

# Orbit

### Give it the goal. Get back a proven commit.

Orbit maps the repository, selects the smallest qualified team, watches the work, tests the full
impact, repairs failures, and commits only after the goal is proven.

![version](https://img.shields.io/badge/version-0.66.0-2b6cb0)
![license](https://img.shields.io/badge/license-MIT-2f855a)
![Claude Code](https://img.shields.io/badge/Claude%20Code-plugin-6b46c1)
![tests](https://img.shields.io/badge/tests-all%20passing-10a877)

</div>

## One goal, one governed delivery

<picture>
  <img src="assets/orbit-loop-observer.svg" alt="User intent becomes a bounded repository-impact packet, enters a gear-selected expert loop watched by one Claude observer, passes protected quality gates, and exits as a proven commit." width="100%">
</picture>

| 1 · Understand | 2 · Select | 3 · Deliver | 4 · Prove | 5 · Ship |
|---|---|---|---|---|
| Map intent to repository evidence | Choose the smallest expert graph | Design and build autonomously | Safety → Review → QA → CPO | Commit the exact proven snapshot |

## What Orbit changes

- **No whole-codebase prompts.** A local, zero-LLM index maps topology, symbols, calls, APIs,
  events, schemas, tests, ownership, and Git co-change. Agents receive a one-hop evidence packet,
  not the repository.
- **No ceremonial agent swarm.** Gear determines the mandatory roles. Irrelevant roles are pruned;
  required roles must actually run.
- **No “tests passed” shortcut.** QA covers six scenario types, direct and transitive dependencies,
  and relevant regression journeys. UI work adds three-viewport pixel evidence.
- **No rubber-stamped finish.** A CPO compares the exact deliverable with the original goal. Missing
  evidence or a rejected verdict returns the work to repair.
- **No silent drift.** One propagated Claude watchdog observes the complete role tree and reports
  shallow discovery, scope drift, stalled work, weakened tests, or unsupported completion.
- **No unmetered fan-out.** Root and agent usage share hard token/call ceilings. T5/T100 labels clamp
  to T4; closeout budget remains protected. If measured work outgrows the intake forecast, Orbit
  automatically reconsiders one gear at a time without resetting spend, changing the goal, or asking.

## What is mechanically enforced

| Control | Binding behavior |
|---|---|
| Live board | The terminal always shows the active or next unfinished task, owning LLM, elapsed/stalled time, and checklist progress; the native task list remains the source of truth. |
| Task budget | Every text goal gets a deterministic route-bound T1–T4 ledger automatically. Cached history is charged only as the per-goal delta; optional communication is pruned first, while 15% capacity and Agent-call admission remain protected for Safety, Review, QA, CPO, and Report. |
| Repository evidence | Intake builds a ≤1-hop, ≤12-file, ~4,000-token packet. Orbit-generated drift is repaired automatically before Agent launch; an unrecoverable or >12 KB handoff is denied without asking the user. |
| Capability graph | T1 requires Plan/Review/QA/Report; T2 adds Safety/CPO; T3/T4 add Discovery/BA/Market; UI adds Designer. |
| Autonomy | Independent LLM tasks may run in the background with reservations held until measurable completion. Routine local work auto-runs inside [Claude's OS sandbox](https://code.claude.com/docs/en/sandboxing), while Orbit's trusted destructive-command wall remains binding. |
| Safety | Catastrophic or uninspectable commands are denied; irreversible/external-authority actions remain human decisions. Orbit never emits a routine `ask`. |
| QA | Happy, alternate, negative, boundary, authorization, and failure/recovery scenarios plus dependency regression are required. |
| UI proof | Baseline, actual, and computed diff at 375×812, 768×1024, and 1440×900, with accessibility and console checks. |
| Delivery | Stop blocks missing owners, stale user memory, failed QA evidence, or missing commit-bound CPO acceptance. |
| Updates | Every scaffold and safe auto-heal installs missing managed components and refreshes repository intelligence without overwriting custom project files. |

## The gear decides the team

| Gear | Use | Required quality spine |
|---|---|---|
| T0 · Direct | No project work | Direct answer |
| T1 · Quick | Small, low-risk change | Planner → Builder → Reviewer → QA → Reporter |
| T2 · Standard | Normal product work | T1 + Safety + CPO |
| T3 · Deep | Broad or uncertain work | T2 + Discovery + BA + Market Research |
| T4 · Mission | Production/migration/irreversible risk | T3 + durable checkpoints and human gates |

UI work always adds the Designer. Orbit runs required owners sequentially in Lite mode and widens
only when evidence and the configured budget justify it.

Sonnet 5 is the everyday Executor; the Opus 4.8 Advisor is on-demand only for expensive forks,
safety uncertainty, or repeated gate failure.

## Install

Choose one path—do not install both.

```bash
git clone --single-branch --depth 1 https://github.com/Abdulaziz-almoshen/orbit.git \
  ~/.claude/skills/orbit
cd ~/.claude/skills/orbit && ./setup
```

Or:

```bash
curl -fsSL https://raw.githubusercontent.com/Abdulaziz-almoshen/orbit/main/install.sh | bash
```

Then open a product repository and run:

```text
/orbit
```

Orbit detects the project surfaces, provisions the relevant roles and playbooks, enables the hooks,
builds the repository index, and preserves existing custom files.

## Daily commands

| Command | Purpose |
|---|---|
| `/orbit:orbit-run <goal>` | Deliver a goal through the governed loop. |
| `scripts/orbit-status --follow` | Watch owner, phase, gates, confidence, and budget. |
| `scripts/orbit-dashboard --port 8765` | Open the read-only local board. |
| `scripts/orbit-intel query --goal "…"` | Inspect the bounded repository-impact packet. |
| `scripts/orbit-memory review` | Review captured user corrections before promotion. |
| `scripts/orbit-worktree create --task <slug>` | Isolate an independent worker. |
| `orbit-doctor --fix` | Diagnose and safely repair managed scaffold drift. |
| `/orbit-upgrade` | Update Orbit and safely heal installed projects. |

## Live supervision

```text
Goal → repository evidence → gear-selected team → Safety → Review → QA → CPO → Commit
                    └────────── Watchdog observes the descendant tree ──────────┘
```

The observer is a drift tripwire, not a worker or security boundary. Healthy work is silent. Orbit
enables `CLAUDE_CODE_EXPERIMENTAL_OBSERVER_AGENTS=1`, attaches one watchdog to the root Orchestrator,
and propagates it to descendants. Anthropic still remotely gates this experimental Claude capability;
when it is unavailable, the deterministic Safety, QA, CPO, budget, and Stop gates continue to bind.

When Codex QA is enabled, `📦` crosses from Claude to the real OpenAI reviewer and returns only with
feedback. Orbit routes T1 → Luna/low, T2 → Terra/medium, and T3/T4 → Sol/high; security, auth, money,
privacy, compliance, or dangerous migrations force Sol. Failed review promotes the next attempt.

## Frontend standard

Frontend projects add a mandatory Designer, the canonical [TasteSkill](https://www.tasteskill.dev/)
method where appropriate, a 67-style design catalog, prototype-before-build discipline, and pixel
verification on every UI delivery. Marketing-page art direction never overrides functional product
UX, accessibility, the project design system, or the user's source of truth.

## Honest boundaries

- Repository packet size is mechanically enforced; semantic relevance is not perfect. Python uses
  real AST symbols/calls, while other languages currently use conservative confidence-labeled
  extraction.
- Business language may not match code vocabulary on the first retrieval. Orbit must run one silent,
  targeted internal query—not ask the user and not widen to the full repository.
- Sandboxed local work is non-interactive. Commands needing new network or host authority may still
  need one explicit authorization; Orbit never converts routine implementation into repeated approvals.
- Role execution is enforceable; expert judgment quality remains model-governed. Validate Recall@K
  against your enterprise task corpus before treating the index as a complete impact oracle.
- The architecture applies the sparse spatial/temporal communication principle from
  [AgentPrune, ICLR 2025](https://proceedings.iclr.cc/paper_files/paper/2025/file/bbc461518c59a2a8d64e70e2c38c4a0e-Paper-Conference.pdf);
  it never prunes the goal, Safety, Review, QA, CPO, or proof.

## Repository

```text
bin/                  trusted hooks and commands
assets/               scaffolded engines, checks, roles, and visual assets
references/           playbooks and project templates
scripts/scaffold.py   deterministic install and migration
tests/                safety, quality, budget, lifecycle, and retrieval contracts
```

```bash
bash tests/run.sh
python3 scripts/check-coherence.py
python3 bin/orbit-verify --root .
```

The development channel is checksum-verifiable but unsigned. See [CHANGELOG.md](CHANGELOG.md) for
release history and [references/playbooks/repository-intelligence.md](references/playbooks/repository-intelligence.md)
for the evidence-retrieval contract.

## License

MIT
