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
- **The mandatory style-prototype gate.** On every new component/module/screen, the Designer must
  shortlist 2–4 styles from `design-styles.md`, build a **standalone HTML prototype of each**, open
  them for the user, and let the user **pick one** before any production build. The user chooses the
  look from real prototypes — this is non-negotiable for design work (see `design-methodology.md`).
- Give the Reviewer the **Design Distinctiveness** gate (the ported/built UI must not read like a
  default, must match the design source of truth if one exists, **and a style must have been
  selected from prototypes** — a UI change with no recorded style choice doesn't pass).
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
