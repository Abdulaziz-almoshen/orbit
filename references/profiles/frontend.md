# Profile: Frontend / UI product (activates the Designer)

Use this profile **in addition to** `generic.md` when the repo is a frontend/UI product —
i.e. when `/orbit` should stand up a **Designer** sub-agent. Not every product needs one;
this is conditional.

## Detect a frontend/UI repo (infer, don't ask)
Signals to grep for: `package.json` deps like `react`/`vue`/`svelte`/`next`/`astro`/`tailwind`;
`.tsx`/`.jsx`/`.vue`/`.svelte`/`.cshtml`/`.html` view files; a `components/`, `pages/`,
`views/`, or `app/` dir; CSS/SCSS/`styled`; a design file (`design-concept.html`, Figma export,
a tokens file). If these are present, activate the Designer. If it's a pure backend/CLI/data
job, don't.

## Stand up the Designer
- Add the **Designer** role (see `references/roles.md`) to this repo's roster, as a spec in
  `.orbit/roles/designer.md` + an adapter in `.claude/agents/designer.md`.
- **Provision its skills** — copy the design playbooks into `.orbit/skills/`:
  `design-methodology.md`, `anti-ai-aesthetics.md`, `design-styles.md`, **and the whole
  `design-styles/` directory (the 67-style catalog)**. The scaffolder does this automatically with
  `--frontend`. (This is the "provide skills to the sub-agent" pattern — the role loads them on demand.)
- **Determine impact first, every design-related request.** HEAVY (a new/redesigned component,
  module, screen, or flow; a layout/hierarchy/typography/color/spacing/interaction change; no
  approved style yet) fires a prototype gate; TRIVIAL (copy fix, sanctioned token tweak,
  appearance-restoring bug fix, className/prop swap, zero-pixel refactor) skips it — fast lane
  stays fast (see `design-methodology.md`).
- **The mandatory prototype gate — HEAVY work only.** No style chosen yet → the Designer shortlists
  2–5 styles from `design-styles.md`, builds a **standalone HTML prototype of each**, opens them for
  the user, and lets the user **pick one** (sets the product's look, once). A style already exists →
  the Designer builds **2–5 HTML prototypes of the component itself**, within that style, opens
  them, and lets the user pick the variant. Either way: before any production build, non-negotiable
  on HEAVY, skipped entirely on TRIVIAL (see `design-methodology.md`).
- Give the Reviewer the **Design Distinctiveness** gate, **conditional on `impact_level: HEAVY`**
  (the ported/built UI must not read like a default, must match the design source of truth if one
  exists, **and a style/variant must have been selected from prototypes** — a HEAVY UI change with
  no recorded pick doesn't pass; TRIVIAL work is exempt and a legacy record with no `impact_level`
  is a pass-with-warning, not an auto-fail).
- If the repo has a **design source of truth** (e.g. `design-concept.html`, a tokens file),
  name it in CLAUDE.md §4 and treat it as the fidelity reference + a human-approval checkpoint
  for direct edits.

## Designer ↔ Builder handoff
Designer produces a `design-plan.md` artifact (color/type/layout/signature + rationale);
the Builder implements it; the Reviewer scores fidelity + distinctiveness before "done".

## First run for a frontend product
Smallest useful unit — one screen/component — dry-run/preview only, the Designer plans the
token system and the Builder implements it additively, gates run, you review. Don't redesign
the whole app in one cycle.
