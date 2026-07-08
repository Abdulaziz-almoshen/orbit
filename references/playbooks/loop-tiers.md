# Playbook: Orbit Gearbox — size the loop before you move (the Orchestrator loads this)

The loop chooses the right **gear** before it does any work. Not every request deserves the same
machinery: a question needs no loop; a broad, ambiguous, compliance-heavy initiative needs a whole
research-and-critique fleet. **The prime directive: pick the SMALLEST gear that can still PROVE the
result** — escalate only on a real trigger, de-escalate the moment the uncertainty collapses. (This is
the market consensus — route first, add complexity only when it improves the outcome; dynamic
orchestrator-workers for broad tasks; guardrails that scale with autonomy.)

Every non-trivial run **declares its gear out loud first** (the *Gear Card*, below) — that legibility
is the point: the user sees Orbit's operating mode *before* it moves.

## The five gears

| Gear | Fires when | Loop shape | Agents | Guardrails scale up | Reuses (already in Orbit) |
|---|---|---|---|---|---|
| **T0 · Direct** | question · explanation · trivial patch | answer / patch directly; a one-line STATE note if useful | 0 (main loop) | read-only-ish; nothing to gate | the `route.py` QUESTION lane |
| **T1 · Quick** | small · clear · reversible · low-stakes | **Plan → Do → Verify** — one owner, one proof bar, self-check | 1 | guard hook + self-check | the fast lane (§10) |
| **T2 · Standard** | a real product/dev change · ~1 workstream | Main agent plans/builds; optional single Reviewer/QA on the board | 0–1 unless approved | Safety veto → Reviewer/QA only when needed · proof per requirement · context doctor first | the substantial lane, but **Lite by default** |
| **T3 · Deep** | (≥3 distinct surfaces **or** high research need) **and** (high ambiguity **or** compliance/security risk) | **Map → Research → Plan → Critique → Synthesize → Build** | dynamic, sized to breadth, capped (≤4 by default) | + adversarial **Critique gate** · fan-out + token caps · **context doctor + always confirm before fan-out** · role-scoped tools per worker | discovery **made dynamic** (Product-Discovery/Market-Researcher roles) + plan-review's lenses **as the critics** (Reviewer/Safety); its Build phase hands to T2 (which uses goal-pipeline only if the plan is goal-sized) |
| **T4 · Mission** | spans multiple repos · multiple days · a production migration · money/customer-facing at scale | T3 **wrapped in durable state** — checkpoints, resumable runs, a human-approval gate per irreversible step, an external artifact bundle | dynamic, across sessions | + **mandatory human gates** · durable audit log · tool minimization · artifact bundle for review | the portable `loop.py` runner + `durable-execution.md` + approval checkpoints |

Every gear runs through Orbit's **visible board** — `set_team` + `.orbit/tasks.json` + `.orbit/activity.jsonl`,
sub-agents dispatched with the **Task tool**. **Never** the native `Workflow(...)` background runner
(it bypasses the board — see the run contract). The gear decides *how much* machinery; the board is
always on.

**Cost mode is Lite by default.** Before T2/T3/T4, run `scripts/orbit-context doctor` when available.
If it returns FAIL, compact or ask before continuing. Without explicit approval: max **one** sub-agent,
no red-team fleet, no background workflow, no repeated long status narration. Intelligence should come
from sharper selection, not more agents.
That means one sub-agent maximum by default.

## Model switching — Executor + Advisor
Orbit runs as a two-lane loop:

| Lane | Model | When it runs | Job |
|---|---|---|---|
| **Executor** | `Sonnet 5` (`model_policy.executor.model = sonnet`) | every turn / normal loop work | plan, build, verify, update memory |
| **Advisor** | `Opus 4.8` (`model_policy.advisor.model = opus`) | on demand only | one compact recommendation on a costly decision |

The Advisor is **not** the default reviewer and not a hidden fleet. Use it only for: architecture forks,
safety/compliance uncertainty, repeated gate failure, a decision that is expensive to get wrong, or an
explicit user request for deep judgment. One Advisor call per cycle by default; log the `advisor_reason`,
put `advisor` on the visible board while it is active, send a tiny packet, and keep the answer under the
configured word limit. If you would ask the Advisor twice, stop and ask the user to approve the wider
budget first.

## Agent Activation — catalog, not payroll
Orbit can provision many specialists. That is inventory, not an instruction to wake them. The default
run has one owner: the main agent. Use role **lenses** internally before spawning role **workers**.

| Trigger | Default activation |
|---|---|
| Question / explanation | 0 sub-agents |
| Small clear reversible change | 0 sub-agents |
| Risky code with a concrete proof gap | 1 Reviewer or QA Engineer |
| HEAVY UI decision | 1 Designer or Reviewer, depending on the gap |
| Deploy / payment / privacy / destructive operation | 1 Safety gate |
| External uncertainty that changes the decision | 1 Market Researcher or Product Discovery worker |
| 2+ independent unknowns / broad strategy | Ask before 2-4 agents |

Any spawned worker gets a **tiny specialist packet**:
- exact question / verdict needed;
- 3-8 relevant files or artifact paths max;
- constraints and approval gates;
- expected output limit, normally <=500 words;
- no full `.orbit/activity.jsonl`, no full `STATE.md`, no open-ended repo tour.
- Plain rule: no full STATE and no full activity context in a sub-agent packet.

The visible board should show active owner(s) and blockers. It may show dormant specialists as
`available`, but it must not queue the whole catalog to make the run feel bigger.

## The sizing router — a scorecard, not vibes
Score the request on seven axes, then let the **highest risk-trigger win** (a *sum* is unsafe — it lets
low-risk axes dilute a high-stakes one). Axes:

- **Ambiguity** — is the "what" and "how" clear, or does it need discovery? *(modulator)*
- **Blast radius** — how many surfaces / how much could it break? *(risk floor)*
- **# of surfaces** — distinct sub-questions / features / areas touched. *(breadth discriminator)*
- **Research need** — external unknowns (regulation, API limits, feasibility, "does X exist?"). *(breadth discriminator)*
- **Compliance / security risk** — data · security · money · regulated actions. *(risk floor)*
- **Reversibility** — how hard to undo. *(risk floor)*
- **Runtime / cost** — minutes vs days · one repo vs many · a production migration. *(mission discriminator)*

The decision procedure (run it at kickoff; bias downward):

```
question / explanation / trivial patch?                                  → T0 Direct
multi-repo | multi-day | production migration | money-at-scale?           → T4 Mission
(#surfaces ≥ 3 OR research = high) AND (ambiguity = high OR compliance = high) → T3 Deep
a real change, single workstream?                                        → T2 Standard
else (small · clear · reversible · low-stakes)                           → T1 Quick

FLOOR (non-negotiable): any HIGH on {blast radius, compliance/security, reversibility}
⇒ gear ≥ T2, AND that step may NOT be auto-performed — it goes through a human gate.
```

The gear is a **declared starting posture, not a cage**: any role may **escalate** ("this is bigger than
sized — landmine: X") or **de-escalate** ("Map/Research resolved the unknowns — dropping to T2") mid-run
with a one-line reason, logged as a `[gear]` line in STATE.md. A one-word user override always wins
("quick" / "go deep"). `route.py` injects only a **soft hint** (breadth/research/mission keywords) — it's
a keyword matcher and never sets the gear itself.

## The Gear Card — declare the mode before moving
Open every T2+ run (and announce T1) with a Gear Card: `emit` it to `.orbit/activity.jsonl` (phase
`gear`) and render it as the board header. This is the surprise factor — Orbit explaining itself:

```
🎛  Gear: T3 Deep
    Why:    5 independent feature asks · unknown regulation/API constraints · PDPL compliance risk
    Budget: 12 agents · ~45 min · 380k-token cap
    Plan:   Map → Research → Plan → Critique → Synthesize → Build
    Exit:   plan-of-record + a proof bar per slice
```

`Why` names the *triggers* that chose the gear; `Budget` is the cap it will run under; `Exit` is the
proof that ends the run. On **T3/T4, always confirm** the budget with the user (one `AskUserQuestion`)
before spawning the fleet — an expensive fan-out is a human decision.

## Guardrails scale with autonomy (OWASP LLM06 — Excessive Agency)
More agents / more tools / more reach ⇒ **more control**, never less:

- **Role-scoped tools per worker.** Every worker is dispatched *as an existing role*, so it inherits
  that role's `tools:` frontmatter — not full access. A Research worker (Product-Discovery /
  Market-Researcher) gets read + web + `Write` *for its own brief only*, never `Bash`; a critic
  (Reviewer / Safety) runs read-mostly and **never writes the plan** — only the Synthesizer does. The
  Gearbox *leans on* Orbit's per-role scoping; it does not hand every worker broad tools.
- **Approval for high-impact actions.** Anything irreversible / outward-facing / money / regulated is
  *proposed*, never auto-performed — a human gate. Mandatory and audited on T4.
- **Cost + fan-out caps.** T3 runs under `loop.config.json` → `context_budget`, `cost_mode`, and
  `gears.deep` (agent cap, token budget, concurrency). Exceed the cap → **bucket related sub-questions
  under one worker and LOG the merge** — never silently drop coverage.
- **Everything logged + monitored.** The board (`tasks.json` + `activity.jsonl`) *is* the audit trail;
  T4 keeps a durable one across sessions.

## The Deep loop (T3) — dynamic fan-out that stays productive
Six phases; agents sized to the request's real structure, capped:

These are **existing roles run in a phased fan-out — no new role types are introduced.** All of it
runs on the visible board (set_team the approved active/queued workers, not the whole catalog) and only
after the user approves the budget:

1. **Map** — the **Product-Discovery** role (read-only) run once per codebase *surface* (data model ·
   UI/nav · integration seams). Answers "what actually exists?" before anyone plans.
2. **Research** — the **Market/Competitive-Researcher** role, **one worker per genuine unknown** (one
   per client ask / regulation / feasibility question). Read + web (+ its own brief). Timeboxed, cited.
   *Each worker must be justified as distinct; overlapping questions are merged and the merge is logged
   to `activity.jsonl`.* (< 3 genuine unknowns ⇒ this was a T2, not a T3.)
3. **Plan** — the **Planner** role, one per **feature cluster**: placement, UX, exact data-model
   changes, thin implementation slices with a proof bar each, the gates that apply.
4. **Critique** — **only after a draft plan exists** (barrier: the critics need the whole draft). The
   critics are **your existing gate roles wearing a critique-the-plan hat — not new roles**: the
   **Reviewer** (Scalability — holds at the stated scale bar? blast radius, hot paths), the
   **Safety/Compliance** gate (§8 + domain rules like PDPL — nothing irreversible/outward/regulated
   auto-performed), and on UI work the **Reviewer's Design-Distinctiveness lens** (UX-coherence /
   sequencing — one console, not five bolt-ons; quick-wins first). Each is prompted to find the blocker
   (the red-team discipline). Per-feature verdicts: **pass / concerns / blocker** with evidence. A
   **blocker holds that feature** out of the plan-of-record until resolved or escalated.
5. **Synthesize** — the **Planner** (or the Orchestrator) — the **same role that already owns the plan;
   there is no separate "Synthesizer" role.** It converges the critic-passed slices into a *single
   plan-of-record* — sequenced quick-wins-first, a proof bar + gates + owner decisions per slice.
   **Not a pile of reports.** This is what the user approves.
6. **Build** — hand the plan-of-record to the **T2 Standard** loop (Builder → Reviewer → QA/Safety). If
   the plan is *goal-sized*, T2 runs `goal-pipeline.md` inside this phase; otherwise it's a normal build.

Fan-out sizing:
`agents = Map(surfaces, ≤map_max) + Research(unknowns, ≤research_max) + Plan(clusters, ≤plan_max) + critics`,
clamped by `gears.deep.agent_max`. Within a phase, run in parallel (bounded by `concurrency`); pipeline
where safe, but **barrier before Critique** (it needs the whole draft). Announce the sized budget in the
Gear Card and **confirm before spawning**.

## The Mission loop (T4) — durable, resumable, human-gated
When work spans repos / days / a production migration / money at scale, run T3's shape **on the durable
engine**: the portable `loop.py` runner (checkpointing, resume, budget) or a durable orchestrator (see
`durable-execution.md`), with:
- **Checkpoints + resume** — a crash or a day's break resumes from the last finished step, no re-burn.
- **A human-approval gate at every irreversible / outward / money step** — mandatory, audited. This is
  the **existing** mechanism, not a new one: the Orchestrator routes each such step through
  `loop.config.json` → `approval_checkpoints` (`move_money` FORBIDDEN, `external_message`/`deploy`/
  `delete_data` `human`, `spend_over_usd`) via the **Safety gate**, pausing with an `AskUserQuestion`
  before it proceeds. `loop.py` enforces the same checkpoints for the headless path.
- **An external artifact bundle** — spec, plan-of-record, critic verdicts, proof — a reviewable package,
  not just chat.
- The same visible board, persisted across sessions.

## The one-line summary
T0 answers, T1 does, T2 builds-with-a-team, T3 investigates-then-builds, T4 runs-a-durable-mission —
each announced as a Gear Card, each on the visible board, each with guardrails matched to its reach.
**Smallest gear that still proves the result.**
