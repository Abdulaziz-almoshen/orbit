# Credits & third-party attribution

Orbit is MIT-licensed. It builds on the following open-source work — gratefully credited here, and
where required by their licenses (retained notices + a note of changes).

## Design styles — `references/playbooks/design-styles/`
- **Source:** [bergside/awesome-design-skills](https://github.com/bergside/awesome-design-skills)
- **License:** MIT — © 2026 Bergside (full text:
  `references/playbooks/design-styles/LICENSE-awesome-design-skills.txt`)
- **What we use & changes:** the 67 per-style `DESIGN.md` token specs are bundled **verbatim** as
  Orbit's selectable style palette. The catalog index (`design-styles.md`) and the mandatory
  style-prototype selection gate (in `design-methodology.md`) are Orbit's own additions on top.

## Design methodology — `references/playbooks/design-methodology.md`
- **Source:** Anthropic's `frontend-design` skill (claude-plugins-official)
- **License:** Apache-2.0
- **What we use & changes:** the methodology (studio stance, hero-is-thesis, the named token
  system, "remove one accessory", quality floor) is **adapted and restructured** into Orbit's own
  playbook and combined with the style palette + selection gate above. Not a verbatim copy.

## Technical-review methodology — `references/playbooks/technical-review.md`
- **Inspiration:** the review / QA / eng-review skills in
  [gstack](https://github.com/garrytan/gstack) (MIT — © 2026 Garry Tan)
- **What we use & changes:** the *methodology* (severity×confidence gate, quote-the-line
  verification, prove-don't-assume, engineering-judgment lenses) is **distilled and rewritten,
  vendor-neutral** — no files copied.

## Planning / discovery methodology — `references/playbooks/product-discovery.md` + `market-and-competitive-research.md`
- **Concepts (public frameworks, adapted — no code copied):** Marty Cagan / SVPG (the four big
  risks; discovery vs delivery), Teresa Torres (opportunity solution tree, assumption mapping,
  riskiest-assumption test), Jobs-To-Be-Done, April Dunford (positioning sequence), and the
  multi-agent **planning-team relay** pattern (Analyst → PM → Architect → PO) from
  [BMAD-METHOD](https://github.com/bmad-code-org/BMAD-METHOD) (MIT) and GitHub spec-kit.

## Methodology
- Orbit's core "build a system that prompts itself" loop is based on **Daisy Hollman's** talk
  "Beyond the basics with Claude Code."
