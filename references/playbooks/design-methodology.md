# Playbook: Design methodology (the Designer role loads this)

A reusable skill provisioned to the **Designer** role when `/orbit` sets up a frontend/UI
product. It's self-contained — the substance lives here, the role just loads it.

## Stance
Design like a studio that gives each client a distinctive visual identity that couldn't be
mistaken for anyone else's. Every choice is deliberate, opinionated, and grounded in the
**subject's own world** — its materials, instruments, artifacts, vernacular. Templated
defaults are the enemy of that.

## The style palette (67 ready-made styles)
You have a catalog of **67 selectable style token-systems** in `design-styles.md` (full specs in
`design-styles/<name>.md`) — minimal, brutalist, glassmorphism, editorial, luxury, retro, neon,
and more. These are the *menu*; this methodology is the *how*. The user picks the style from real
prototypes (gates below); you then apply it with the rigor here (grounding, signature, anti-AI
checklist, quality floor) so it's distinctive, not a templated drop-in.

## First, determine impact — heavy or trivial? (every design-related request)
Before touching a style or building a component, classify the request. This is what keeps the
prototype gate scoped to work that deserves it, and keeps the fast lane (CLAUDE.md §10) fast:

**HEAVY — changes the user experience** (a prototype gate fires, below):
- A new or redesigned component, module, screen, or flow.
- A change to layout, visual hierarchy, typography, the color system, spacing rhythm, or an
  interaction/motion pattern.
- Introducing a UI surface that has no approved style yet (the *first* design request in this repo).

**TRIVIAL — no gate, just do it** (fast lane, §10):
- A copy/text fix or a same-layout content swap.
- A single token tweak already sanctioned by `DESIGN.md`.
- An appearance-*restoring* bug fix (bringing a component back to its approved design).
- A `className`/prop swap or a zero-pixel refactor.
- Anything small · clear · reversible.

On TRIVIAL, proceed directly — no prototypes, no `AskUserQuestion` — and drop a
**`.orbit/design/TRIVIAL`** marker (see Handoff below), so later checks can see a design decision
was made without mistaking it for a HEAVY approval. On HEAVY, run whichever gate applies below.

## Two gates — the one-time style pick, and the recurring component gate
These serve different moments in a product's life, and only one runs per HEAVY request.

### A. The style-prototype gate — once per product, not per component
Run this **only** the first time this repo needs a design (no `DESIGN.md` / no chosen style yet),
or when the user explicitly asks to re-pick the whole product's look:
1. **Shortlist 2–5 styles** from `design-styles.md` that genuinely fit the brief — use the families
   to narrow (e.g. a fintech dashboard → `clean` / `corporate` / `sleek`; a kids' app → `doodle` /
   `colorful` / `friendly`; a launch page → `bold` / `editorial` / `cosmic`). Show the relevant few,
   never all 67.
2. **Build a standalone HTML prototype of each** — one self-contained `.html` file per style (inline
   CSS, **the same component with real content from the brief** so they're directly comparable),
   using that style's tokens from `design-styles/<name>.md`. Write them to
   `.orbit/artifacts/<cycle>/previews/<style>.html`.
3. **Open them for the user** to compare side by side (`open` each file, or serve the folder), with a
   one-line pitch per style ("Brutalist — raw, high-contrast, unmissable"; "Clean — calm, trustworthy").
4. **The user picks one — via `AskUserQuestion`.** One option per style (its one-line pitch as the
   description, **your best fit for the brief first, labeled "(Recommended)"**) plus an
   "Other / remix" escape. Never a prose question — the selection must be one click.

This sets the product's visual language for everything after it (see Handoff — `DESIGN.md`).

### B. The component prototype gate — every subsequent HEAVY component/redesign
Once a style is chosen (gate A already ran), a new HEAVY component does **not** re-pick the style —
it generates variations *within* it:
1. **Build 2–5 HTML prototypes of this component** — different layouts, compositions, or
   interaction patterns for *this* brief, all using the *already-approved* style's tokens from
   `DESIGN.md`. Write them to `.orbit/artifacts/<cycle>/previews/<variant>.html`.
2. **Open them for the user** the same way (`open` each file, or serve the folder), with a one-line
   pitch per variant.
3. **The user picks one — via `AskUserQuestion`.** One option per variant, your recommendation
   first labeled "(Recommended)", plus an "Other / remix" escape.

**This gate is mandatory on the HEAVY branch — not on every design-related request.** TRIVIAL work
skips it by design; the fast lane stays fast. (The Reviewer/QA enforce it *conditionally*, only
when `impact_level: HEAVY` — see `roles.md` and `qa-validation.md`.)

## The two-pass process — plan before you code, critique twice
1. **Start from the chosen style** (the prototype the user picked) and explore the subject's world to
   adapt it — don't discard their choice, *ground* it.
2. **Plan a token system** (below) in writing — no code yet.
3. **Critique the plan against the brief** (the hard gate — see below).
4. **Build** to the plan.
5. **Self-critique while building**, and before finishing, **remove one accessory** that
   doesn't serve the brief.

## The token system (write this first)
- **Color** — 4–6 *named* hex values, grounded in the subject. (`--ink`, `--signal`, … not
  "blue/gray".)
- **Type** — a characterful display face used with restraint + a complementary body face +
  a utility face for captions/data. Pair deliberately *for this brief*; set a clear type
  scale with intentional weights/widths. Typography carries the personality.
- **Layout** — ASCII wireframes + a sentence of prose per section.
- **Signature** — the **one** memorable element. Spend boldness here; keep everything else
  quiet and disciplined.

## Principles
- **Hero is a thesis** — open with the most characteristic thing in the subject's world.
  Reject the templated big-number + label + stat + gradient unless it's genuinely best.
- **Structure encodes information** — use numbered markers (01/02/03) only if order truly
  carries meaning. Every structural device must encode something true.
- **Motion serves the subject** — orchestrate one meaningful moment, don't scatter effects
  (scattered animation reads as AI-generated).
- **Match complexity to the vision** — maximalist needs elaborate execution; minimal needs
  precision in spacing, type, and detail. Elegance is executing the chosen vision *well*.
- **Copy with intent** — active voice, written from the user's side of the screen, one job
  per element, consistent action names. Words make understanding easier; treat them like
  spacing and color.

## The plan-critique gate (before any code)
Test each choice: work through a *similar* brief and confirm you don't arrive at the same
answer. If any part reads like a default, revise it. Only start building once the plan is
distinctive and coherent. (See `anti-ai-aesthetics.md` for the specific defaults to reject.)

## Quality floor (built in, not announced)
Responsive down to mobile; visible keyboard focus; `prefers-reduced-motion` respected. Mind
CSS specificity (type- vs element-based selectors can cancel each other on padding/margins).

## Handoff — the design is a FILE contract, not a suggestion
The user's pick from whichever gate ran (or the triage call, on TRIVIAL) becomes **artifacts every
later step must consume**. Two distinct records, so a HEAVY approval is never confused with a
TRIVIAL pass-through:

1. **On HEAVY — `design/approved.json`** (the repo root; canonical, single location — every role
   reads and writes this one path, never a per-cycle copy) — the pick, in one record:
   ```json
   { "component": "checkout-summary", "impact_level": "HEAVY",
     "impact_rationale": "new layout + interaction pattern",
     "variants_shown": 3, "chosen": "variant-b",
     "previews": [".orbit/artifacts/12/previews/variant-b.html"], "cycle": 12 }
   ```
   `variants_shown` is always 2–5 here. Engineers **must detect and read this before any UI code.**
   A **legacy record with no `impact_level`** (written before this gate existed) is not an error —
   treat it as **pass-with-warning**, never an auto-fail.
2. **On TRIVIAL — `.orbit/design/TRIVIAL`** — a one-line marker (which component, why trivial, the
   cycle), dropped instead of `approved.json`. It records that triage happened without implying a
   prototype pick ever occurred. Its mere presence is proof enough for this cycle.
3. **`DESIGN.md`** (repo root) — the extracted token system as the *persistent design authority*:
   named hex values, type roles + scale, spacing scale, radius, the signature element, and a
   **Decisions Log** line per change. Every future design/UI run reads DESIGN.md first; its tokens
   **override** anything a new generation would invent. (This is what keeps the product visually
   coherent across sessions — and it's where active learning writes design learnings.)
4. **`.orbit/artifacts/<cycle>/design-plan.md`** — the per-cycle plan (tokens + layout + signature +
   rationale, naming the chosen style/variant) for the Builder.

**Fidelity rule:** when an approved prototype exists, **pixel-match it** — source-of-truth fidelity
beats code elegance (`width: 312px` matching the mockup beats a cleaner grid class that doesn't).
Real content only, never lorem ipsum.

**The verification triangle** closes the loop: approved prototype (the *target*) → Builder builds *to*
it → the **QA Engineer** machine-verifies build-vs-target (token assertions from computed styles +
screenshot diffs at 375/768/1440 — see `qa-validation.md`). Orbit ships thin helpers for this in
`.orbit/qa/` (`extract-tokens.py --compare DESIGN.md`, `snapshot.py screenshot|diff`) — **helpers,
not a bundled browser**: they use Playwright if installed and otherwise fall back to a browser MCP /
gstack `/browse` / a manual capture (they exit cleanly, never crash the cycle). The Reviewer's
**Design Distinctiveness** gate still applies (see `roles.md`), **conditionally** — it fires when
`impact_level: HEAVY`. A HEAVY UI change with no `approved.json` behind it is a finding; TRIVIAL
work is exempt (its own triage record is enough).
