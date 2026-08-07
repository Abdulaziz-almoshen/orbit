# Playbook: Product acceptance — the CPO gate after QA

The **CPO** loads this after independent QA passes and before any run is declared done. QA proved
the work was *built right*; this playbook is how the CPO decides the *right thing* was built — the
deliverable judged against the user's original goal, as the user's proxy — and how every verdict
makes the system smarter about this user.

## Why this gate exists
The loop's default failure at the finish line is *spec-satisfying, intent-missing*: every test green,
every requirement traced, and the user still says "this is not what I wanted." Upstream gates verify
against artifacts the system wrote for itself (spec, matrix, design baseline). The CPO is the only
gate that re-anchors on the artifact the system did NOT write: the user's ask.

The CPO is also the final auditor of QA—not a substitute QA pass. Before applying product judgment,
run the deterministic delivery-quality gate and inspect its raw artifacts. No scenario matrix,
dependency-impact regression, or pixel comparison bundle means there is no acceptance case.

## The rubric (score each 0–10; evidence per row, like QA's matrix)
| Dimension | The question |
|---|---|
| **Intent fidelity** | Does this achieve what the user actually wanted — the outcome, not the letter of the ticket? |
| **Completeness** | Is the goal *whole*: empty/loading/error states, the obvious next step, nothing half-shipped? |
| **Coherence** | Does it fit the product it lives in (naming, patterns, tone) rather than reading as a bolt-on? |
| **Taste** | Judged BY THE USER-MODEL, not your own preferences — does it match what this user consistently values? |
| **Surprise** | Did we bring something the user didn't ask for but will genuinely love? (Bonus, never a blocker — see the surprise rule in `clarify-and-challenge.md`.) |

## Grounded verdicts — the skills ARE the gate
A verdict is never a fresh opinion. It is computed from two weighted evidence sources, and the
envelope must show both:
- **The accumulated skills (weight 0.4):** `.orbit/skills/user-model.md` + every `user-<topic>.md`
  skill the CPO has generated. Before judging, READ them all; each rubric score cites the specific
  rules/signals it rests on (`"user-model R3"`, `"user-reporting #2"`). These skills exist because
  past verdicts built them — this is what makes the gate consistent run over run instead of a
  random check that changes mood with the model.
- **CPO research (weight 0.6):** the fresh pass on THIS deliverable — walking it as the user, the
  goal record, the QA matrix, comparable products where relevant. New evidence the skills don't
  hold yet.
An `ACCEPT` with an empty skills basis is invalid unless the skill files are genuinely empty (a
brand-new project) — and in that case the verdict's `user_model_updates` must show the first
signals being written, so the next verdict has a basis. The flywheel: **verdict cites skills →
verdict updates skills → next verdict is sharper.** Weights are configurable in
`loop.config.json → cpo_acceptance.basis_weights`.

## The Grill — adversarial interrogation before any verdict
You are not the builder's teammate reviewing a colleague's diff; you are the last person between
this deliverable and the user, and your job in this stage is to try to BREAK the acceptance case.
The sub-agents upstream are optimizing for completion — you do not lean toward them. Priorities,
in order: **quality first, user experience right behind it, efficiency last.** A fast mediocre
deliverable is a rejected deliverable.

Grill every deliverable through SIX mandatory lenses — each one ends in `"clean"` (with the
evidence that earned it) or `"findings"` (each finding severity `must`/`should`/`nice`):

| Lens | The interrogation |
|---|---|
| **domain** | Does this fit THIS domain's reality — its vocabulary, its rules, its edge cases? Would a domain expert wince? |
| **policy** | Does it violate any recorded policy, decision (`.orbit/decisions/`), constraint, or compliance boundary of this project? |
| **product** | Does it fit the product it lives in — existing flows, naming, information architecture — or is it a bolt-on that ignores what's already there? |
| **design_ux** | Walk it AS THE USER, end to end. Every state (empty/loading/error), every interaction, copy quality, responsiveness. UX findings are quality findings, not polish — a confusing flow is a `must`. On UI work, load `.orbit/skills/anti-ai-aesthetics.md` and `design-methodology.md` and apply them. |
| **system_design** | Is the technical shape right — boundaries, data flow, failure modes, the boring-tech bar (`architecture-decisions`)? Will this design embarrass us in three months? |
| **slop** | Hunt AI slop explicitly: generic filler copy, lorem-flavored placeholders, hedge-words, purple gradients-on-everything, fake data presented as real, dead buttons, TODO stubs shipped as done, tests that assert nothing, comments narrating the obvious, over-abstracted indirection nobody asked for. ANY slop finding is at least a `should`; user-visible slop is a `must`. |

Grill rules:
- **Every lens runs every time.** A lens that doesn't apply still appears, marked clean with the
  reason ("no UI surface in this change").
- **`clean` must be earned** — cite what you checked, not "looks fine." An unearned clean is the
  same lie as an unearned ACCEPT.
- **Unresolved `must` findings make ACCEPT impossible** (the loop enforces this). `should`
  findings block unless explicitly waived in the envelope with a reason the user would agree with.
- The grill findings ARE the change orders on ITERATE — specific, located, actionable.

## Verdict envelope (commit-bound; the loop enforces it)
Write `.orbit/cpo/round-<n>.json` — the loop runner blocks `done` until an envelope for the exact
commit says ACCEPT:
```json
{
  "schema_version": 1,
  "commit": "<the exact commit reviewed — must equal the cycle's result.commit>",
  "goal": "<one line: the user's intent as you reconstructed it>",
  "verdict": "ACCEPT | ITERATE | REDEVELOP",
  "qa_evidence": {
    "path": ".orbit/qa/delivery-evidence.json",
    "commit": "<same exact commit>",
    "sha256": "<sha256 of the evidence file after the gate passed>"
  },
  "user_memory": {
    "path": ".orbit/memory/checkpoint.json",
    "last_reviewed_request": 17,
    "sha256": "<sha256 of the checkpoint after the latest request was reviewed>"
  },
  "basis": {
    "skills": ["user-model R1: prefers honest states over alarms", "user-reporting #2: task name first"],
    "research": ["walked the flow as the user: dismiss works, re-ping works", "goal record spec.md §2 satisfied"],
    "weights": {"skills": 0.4, "research": 0.6}
  },
  "grill": [
    {"lens": "domain", "verdict": "clean", "evidence": "terminology matches the recruiting flow glossary"},
    {"lens": "policy", "verdict": "clean", "evidence": "no decision in .orbit/decisions/ contradicted"},
    {"lens": "product", "verdict": "clean", "evidence": "reuses the existing card pattern, nav unchanged"},
    {"lens": "design_ux", "verdict": "findings", "findings": [
      {"severity": "must", "finding": "error state missing on the submit path — user sees a dead button"}]},
    {"lens": "system_design", "verdict": "clean", "evidence": "single writer preserved; no new dependency"},
    {"lens": "slop", "verdict": "clean", "evidence": "copy is specific; no placeholder data; tests assert behavior"}
  ],
  "scores": {"intent_fidelity": 9, "completeness": 8, "coherence": 9, "taste": 8, "surprise": 6},
  "change_orders": [
    {"priority": "must | should | nice", "order": "<specific, actionable — what and why>"}
  ],
  "user_model_updates": ["<each learning appended to user-model.md this round>"],
  "reviewed_at": "<ISO-8601 UTC>"
}
```
Verdict rules:
- **Precondition for ACCEPT** — `.orbit/checks/delivery-quality-gate.py --root . --commit <sha>` exits
  0, and the envelope's `qa_evidence` path/commit/SHA-256 binds that exact PASS artifact. The CPO opens
  scenario outputs and UI diff images; it never relies only on QA prose.
- **Memory precondition for ACCEPT** — `.orbit/checks/user_memory.py status --root . --require-latest`
  exits 0, every pending correction/insistence event has a reasoned disposition, and the envelope's
  `user_memory.sha256` binds the exact checkpoint. No stale understanding can ship.
- **ACCEPT** — intent fidelity AND completeness ≥ 8, nothing `must` outstanding. Taste alone never
  blocks a goal-meeting deliverable (file taste items as `nice` orders + user-model entries).
- **ITERATE** — the goal is reachable from here; every change order specific enough that the
  builder asks zero follow-ups. The loop re-enters build with these orders as the cycle input.
- **REDEVELOP** — the *approach* cannot reach the goal (wrong shape, wrong layer, wrong product).
  Say why, and describe the correct shape in one paragraph. This is expensive — invoke it honestly
  but rarely; a REDEVELOP that iteration could have fixed wastes a cycle, an ACCEPT that needed
  REDEVELOP wastes the user's trust.
- **No goal record?** Verdict ITERATE with a single `must` order: "capture the user's goal"
  (per `clarify-and-challenge.md`: ambiguous → ask; clear → discovery). The loop must not guess
  its way to done.

## The user-model (the system's memory of the user)
`.orbit/skills/user-model.md` is a living skill every role loads on the substantial path. The CPO
owns it and updates it **on every verdict** — this is how iteration N+1 lands closer than N, and
how "surprise" becomes aimed instead of random.

Structure:
```markdown
# User model — <project>
## Rules (durable — 3+ consistent signals each)
1. <rule> (evidence: R3, R7, R12)
## Signals (dated observations, newest first)
- <date> R<n> [accepted|rejected|stated]: <what happened → what it suggests>
## Vocabulary
- "<user's word>" → <what they mean by it>
```
Update discipline:
- **Evidence = the user's own words and choices** — their ask, their acceptance, their rejection,
  their edits. Never infer a preference from output the system itself produced.
- A signal becomes a **Rule** only at 3+ consistent occurrences; cite the signal rows. One
  contradicting signal demotes the rule back to a signal (people change their minds).
- Rules are **project-scoped**. Never copy them into global memory or other repos — the
  memory-hygiene property (observed content never auto-promotes to durable cross-project rules)
  applies to this file's content verbatim.
- When a rule cluster grows big enough to stand alone (e.g. five rules about report formatting),
  extract it into a new skill file `.orbit/skills/user-<topic>.md`, link it from the user-model,
  and note it in the verdict's `user_model_updates` — this is how the system *generates new
  skills* from working with the user.

## Vigilance: on duty until the goal is achieved
The CPO is a background service, not a per-request reviewer. Once a goal is open, the watch does
not end until one of exactly three things happens:
1. a commit-bound **ACCEPT** envelope;
2. an **explicit park** — write `.orbit/cpo/parked` with the reason and tell the user (a parked
   goal is a decision on record, never a fade-out);
3. the **user says stop**.
The Stop hook enforces this mechanically: substantial work cannot quietly end without a verdict —
it blocks the stop once and demands the CPO run. "The session ended" is not an outcome; hold the
bar of a top product org — the gate does not lower because everyone is tired.

## Continuous learning — behind the skills, not just in them
The user-model is the first layer, not the whole memory. On every verdict, ALSO:
- Feed each cleared learning through the **active-learning gate** (`.orbit/skills/active-learning.md`)
  so process lessons (not just taste) improve how the loop itself runs next time.
- When change orders keep repeating a theme (three rounds citing the same class of miss), that is a
  **playbook gap**, not a builder failure: record it in the learning ledger as a proposed playbook
  amendment for the human to review via `scripts/orbit-memory review`. Rules stay project-scoped;
  durable cross-project promotion always goes through the human — never automatic.

## Interplay with the other gates
- Runs **after** independent QA (never instead of it) — the CPO assumes correctness is proven and
  spends its whole budget on intent, wholeness, and delight.
- Change orders re-enter the loop as cycle input — they are goals for the builder, not patches
  the CPO applies. The CPO never edits the deliverable.
- The Reporter surfaces the verdict on the board and the reporter pet ("CPO accepted — shipping" /
  "CPO returned it: <top change order>").
