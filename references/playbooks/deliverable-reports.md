# Playbook: Deliverable reports (the Reporter loads this)

The final message a run produces is the product the user actually reads. It must answer, in this
order, without a file dump: **what changed · proof · confidence · risks · files touched · next**.
Lead with the outcome; never claim a gate passed when it didn't. Pull the real numbers from
`.orbit/run.json` (confidence, cost, tokens) and the Reviewer/QA verdicts — don't estimate them.

## The universal spine (every report has these)
- **What changed** — 1–3 sentences, plain language, outcome first ("Settings now save per-device").
- **Proof** — the concrete evidence, not "should work": the test output (0 failures), the QA
  verdict/RTM score, the reviewer pass, the screenshot-diff result. Cite it.
- **Confidence** — the number + reason from `confidence.py` / `run.json` ("76%: tests + review
  pass; safety pending"). If it's below ~75, say why in the same breath.
- **Risks** — what could bite: an unresolved blocker, a large blast radius, a waived requirement,
  a `CONCERNS` verdict. Name them; don't bury them.
- **Files touched** — the surfaces changed (grouped, not a raw diff).
- **Next recommended action** — the single most useful next step (run it, review it, ship it,
  answer the pending decision).

End with the unambiguous status: **DONE** / **DONE_WITH_CONCERNS (…)** / **BLOCKED (…)**.

## Templates by lifecycle mode (match the mode in `run.json`)

### Feature
```
✅ <Feature> — <one-line outcome>
Proof: <tests: N pass> · <QA: score/verdict> · <reviewer: pass>
Confidence: <N%>: <reason>
Risks: <none | the 1–2 that matter>
Files: <grouped surfaces>
Next: <the one action>
Status: DONE | DONE_WITH_CONCERNS(…) | BLOCKED(…)
```

### Bug fix
```
🐛 Fixed: <symptom> — root cause: <the actual cause, not the symptom>
Proof: a regression test that reproduces-then-passes (<test name>) · <suite: N pass>
Confidence: <N%>: <reason>
Risks: <regression surface / anything still unverified>
Files: <the fix + the new test>
Next: <verify in the failing scenario / ship>
Status: DONE | DONE_WITH_CONCERNS(…) | BLOCKED(…)
```

### Design
```
🎨 <Screen/component> — <the chosen direction, grounded in the product>
Proof: user picked <variant> from <N> prototypes · pixel pass <score> vs the approved design ·
       tokens match DESIGN.md
Confidence: <N%>: <reason>
Risks: <accessibility / responsive gaps / un-approved deltas>
Files: <the built UI + DESIGN.md updates>
Next: <the decision batch, if any / ship>
Status: DONE | DONE_WITH_CONCERNS(…) | BLOCKED(…)
```

### Refactor
```
♻️ Refactored: <what> — behavior unchanged (that IS the deliverable)
Proof: the SAME tests pass before and after (<suite: N pass>) · no API/contract change (or: the
       intended one, migrated) · reviewer pass
Confidence: <N%>: <reason>
Risks: <blast radius / compatibility / anything the tests don't cover>
Files: <the moved/renamed surfaces>
Next: <follow-up cleanup / ship>
Status: DONE | DONE_WITH_CONCERNS(…) | BLOCKED(…)
```

## Honesty rules (non-negotiable)
- A **CONCERNS** or a failing gate → the status is NOT `DONE`. Say `DONE_WITH_CONCERNS` or `BLOCKED`.
- "requirements met" needs the line-by-line RTM, not a green test suite alone (see `qa-validation`).
- If there's a pending decision (`.orbit/pending-question.json`), the report ends by surfacing it,
  not by implying the work is finished.
