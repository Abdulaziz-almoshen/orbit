# Playbook: Design methodology (the Designer role loads this)

A reusable skill provisioned to the **Designer** role when `/orbit` sets up a frontend/UI
product. It's self-contained — the substance lives here, the role just loads it.

## Stance
Design like a studio that gives each client a distinctive visual identity that couldn't be
mistaken for anyone else's. Every choice is deliberate, opinionated, and grounded in the
**subject's own world** — its materials, instruments, artifacts, vernacular. Templated
defaults are the enemy of that.

## The two-pass process — plan before you code, critique twice
1. **Brainstorm / explore** the subject's world for the visual language.
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

## Handoff
Produce `.orbit/artifacts/<cycle>/design-plan.md` — the token system (color, type, layout,
signature) + the rationale — and hand it to the Builder to implement. The Reviewer checks it
against the **Design Distinctiveness** gate (see `roles.md`).
