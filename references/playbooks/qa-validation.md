# Playbook: QA validation — prove the product against the requirements, one by one

The **QA Engineer** loads this. Its job is different from the Reviewer's (who reviews the *diff* for
technical defects): QA validates the *product* against the *requirements* — user story by user story,
acceptance criterion by criterion, and on UI work pixel-by-pixel against the approved design. Nothing
reaches CPO until **every requirement, user scenario, related dependency path, and UI pixel comparison
has machine-validated evidence bound to the exact commit**.

## Posture: report-only, evidence-first
- **Never fix.** Find and document; engineers fix; you re-verify. Don't read source to "understand" —
  test as a user. (Separation of duties keeps the verdict honest.)
- **Repro is everything.** Every failure carries evidence — a screenshot, a command output, a diff.
  Retry once before documenting (a fluke is not a finding). Check the console after every interaction —
  invisible JS errors are still bugs.
- **Depth over breadth:** 5 well-evidenced findings beat 20 vague ones.

## The spine: the Requirements Traceability Matrix (RTM)
The Planner emits numbered requirements with **EARS-style acceptance criteria**
("WHEN <condition> THE SYSTEM SHALL <observable behavior>") — that is your test oracle. Build the
matrix; it IS the report:

| ID | Requirement / user story | Criterion (EARS) | Method | Verdict | Evidence |
|----|--------------------------|------------------|--------|---------|----------|
| R-3 | Doctor accepts AI suggestion | WHEN the doctor clicks Accept THE SYSTEM SHALL issue the leave in <15s | browser | PASS | shot-R3.png |

- **Method** per row: browser check · API probe · visual diff · code/config inspection — functional and
  pixel rows coexist in one matrix.
- **Coverage is computed, not felt:** "R-7: no test" is itself a blocking finding.
- Derive cases per criterion with **boundary + equivalence** heuristics (empty, max, invalid class,
  double-submit, logged-out) — not just the happy path. An unanswerable criterion is a red card →
  escalate to the Planner, don't guess.

## The verdict gate: PASS / CONCERNS / FAIL / WAIVED
Per requirement and rolled up for the run. **CONCERNS** ships with named caveats; **WAIVED** requires
an explicit human decision; any **FAIL** on a P0 requirement = the run is not done. Score the run:
P0 = 40pts (any failure → 0), P1 = 30 prorated, P2 = 15 prorated, visual fidelity = 15. **< 85 = not done.**

## The scenario matrix (functional QA is a journey, not a checklist)

For every changed capability, execute complete scenarios through the real interface/API. The matrix
must include all six kinds: **happy · alternate · negative · boundary · authorization · failure/recovery**.
Each case records `persona`, Given/preconditions, When/steps, Then/expected, actual observed result,
verdict, and a durable screenshot/output/trace artifact. Include state transitions, retries,
double-submit/idempotency where relevant, logged-out/forbidden behavior, downstream effects, and the
next action a real user takes. A row that only clicks the newly changed control is not an end-to-end
scenario and cannot pass.

## Dependency-impact regression (test the system around the change)

Read the diff and construct the impact graph before choosing commands:
`changed units → imports/callers/consumers → transitive dependents → related user journeys`.
Record all four layers in delivery evidence. Run focused tests, integration/contract checks, and the
relevant wider suite for those dependents. Capture command, exit code, and complete output artifact.
Do not declare coverage complete if only the edited module or requested scope was tested. A previously
passing related flow that regresses is P0, even when the new acceptance criterion passes.

## The pixel pass (UI work — the design is a contract, not a suggestion)
**Runs on every UI delivery.** HEAVY and TRIVIAL determine design ceremony, not whether pixels are
tested. Every changed route/screen needs an approved target or pre-change baseline plus actual screenshots and
diff images at 375x812, 768x1024, and 1440x900. Any missing baseline, actual, diff, or route×viewport pair is a blocker. A legacy
approval may remain usable only after QA captures an explicit baseline for this commit. **Also require
the `taste_preflight` record:** a HEAVY
`approved.json` with **no `taste_preflight`** block (design read + dials + design-system + surface +
`checklist_passed`) is a finding — the taste gate was skipped, not judged unneeded. On HEAVY, the
Designer's **approved prototype** (`design/approved.json` + `DESIGN.md` tokens) is the golden baseline:
1. **Token assertions:** extract the *rendered* design system via computed styles (fonts, palette, type
   scale, spacing, touch-target boxes) and assert token-by-token against DESIGN.md — numeric checks
   (body ≥16px, WCAG AA 4.5:1, 44px targets, spacing on the 4/8px scale), not vibes.
2. **Screenshot diff:** render build and prototype at the same viewports (375/768/1440), mask dynamic
   regions, diff at ~1% threshold; emit the diff image as evidence and a multi-axis fidelity score.

**How to run the pixel pass — the executor, and its fallbacks.** Orbit ships thin **helpers, not a
bundled browser**, in `.orbit/qa/` (frontend repos only):
- `.orbit/qa/extract-tokens.py <url> --compare DESIGN.md` → token-by-token PASS/FAIL for step 1.
- `.orbit/qa/snapshot.py screenshot <url> --out build.png --viewport 375x812` then
  `.orbit/qa/snapshot.py diff build.png approved.png --threshold 0.01 --out diff.png` → step 2.

These need **Playwright** (`pip install playwright && playwright install chromium`); the `diff`
subcommand is pure-python and needs nothing. When Playwright isn't installed, prefer this fallback
chain, in order: **(1)** an installed browser MCP tool → **(2)** gstack `/browse` if present →
**(3)** a manual screenshot + `snapshot.py diff`. The helpers exit 2 with the install line (never a
traceback), so a missing browser degrades the check — it never crashes the cycle.

**The visual gate is required, then the delivery-quality gate binds its evidence.** Run
`.orbit/qa/visual-gate.py` before
you score fidelity: `python3 .orbit/qa/visual-gate.py --root . --screenshot build.png --mobile
build-mobile.png --contract DESIGN.tokens.json` (exit 1 = BLOCKED). It enforces the non-negotiables that
"the process ran" can't paper over: **HEAVY UI with no screenshot at all → BLOCK** (you cannot pass HEAVY
UI on prose — produce evidence), a **blank canvas → BLOCK**, **mobile horizontal overflow → BLOCK**, and
**sub-AA body contrast → BLOCK** (pure math from the token contract, no browser needed); token drift is a
WARN (BLOCK with `--strict-tokens`). It degrades honestly — dimensions + contrast need no dependencies,
and it never *silent-passes*: if evidence can't be produced it blocks. Then populate every viewport in
`.orbit/qa/delivery-evidence.json`; the deterministic delivery gate checks paths, ratios, token verdict,
accessibility, console errors, and exact-commit binding before CPO.
3. **Intentional change?** The approved design target decides whether a delta is intended. The Designer
   selects and records the baseline; QA never silently advances it to make a failing build pass.
4. Quick structural checks per page: trunk test (what site/page/sections/where-am-I), states
   (empty/loading/error/overflow), responsive at 3 viewports, keyboard focus visible.
5. **Anti-slop scan (the AI-tell pass).** Scan the *rendered* UI against the ban list in
   `taste-preflight.md`/`anti-ai-aesthetics.md` — em-dashes in shipped copy, fake dashboards or
   div-drawn fake screenshots, default purple/mesh gradients, three identical generic cards, the
   beige-luxury palette, fake version labels, decorative scroll cues/dots, generic names ("John Doe"),
   empty marketing copy ("Seamlessly streamline your workflow"). A confirmed match on HEAVY UI is a
   finding (severity by prominence), with the screenshot as evidence — not a matter of taste.

## Execution discipline
- **Reconnaissance-then-action:** navigate, wait for idle, inspect the real DOM, derive real selectors —
  never assume them. One scripted check per acceptance criterion where possible.
- Keep a **baseline per requirement ID** across cycles: report Resolved / Persistent / New, and the
  trend (IMPROVING/DEGRADING). Regressions against previously-PASS rows are P0.
- Multi-role products: run per-role auth contexts (the logged-out row is always present).

## The exit gate (Iron Law)
No completion claims without fresh evidence in the report: "tests pass" requires the 0-failure output;
**"requirements met" requires the line-by-line matrix** — a green test suite alone is NOT sufficient.
Red-flag words in your own draft ("should", "probably", "seems to") mean you haven't verified.

Write `.orbit/qa/delivery-evidence.json` from `.orbit/qa/delivery-evidence.template.json`, then run:
`python3 .orbit/checks/delivery-quality-gate.py --root . --commit <exact-sha>`. Only exit 0 opens CPO.

## Report
Lead with the roll-up: `QA: N requirements — P pass, C concerns, F fail (score X/100)` → the matrix →
"Top 3 things to fix" → per-finding blocks (severity · repro steps · evidence) → the visual-fidelity
section → verdict: **DONE (with evidence) / DONE_WITH_CONCERNS (…) / BLOCKED (…)**. Announce
`[qa-engineer] …`; emit start/done/blocked via `.orbit/activity.py`.
