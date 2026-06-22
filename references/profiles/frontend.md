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
  `references/playbooks/design-methodology.md` and `references/playbooks/anti-ai-aesthetics.md`.
  (This is the "provide skills to the sub-agent" pattern — the role loads them on demand.)
- Give the Reviewer the **Design Distinctiveness** gate (the ported/built UI must not read
  like a default, and must match the design source of truth if one exists).
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
