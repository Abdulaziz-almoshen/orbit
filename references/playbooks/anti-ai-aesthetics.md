# Playbook: Anti-AI-aesthetics checklist (the Designer's "don't" list)

The fastest way to look generated is to fall into one of the default looks every AI reaches
for. The Designer runs this check during the **plan-critique gate** (before coding) and
again before finishing. Match any cluster → revise, unless the brief *genuinely* calls for it.

## The three default clusters to reject
1. **Warm-cream editorial** — `#F4F1EA`-ish cream background + a serif + a terracotta/rust
   accent. The "tasteful startup memo" default.
2. **Dark neon** — near-black background + acid-green or vermilion accent, high-contrast
   "hacker/AI" look.
3. **Broadsheet** — newspaper/editorial grid + hairline rules + zero border-radius +
   all-caps tracked labels. The "we read a type blog" default.

If your token system lands on one of these *by reflex* rather than because the subject
demands it, you defaulted — start over from the subject's world.

## Other AI tells
- **Scattered motion** — fade/slide on everything. One orchestrated moment beats ten.
- **Templated hero** — big number + label + 3 stats + gradient, regardless of subject.
- **Decoration that encodes nothing** — dividers, badges, icons that aren't carrying
  information. Cut anything that doesn't serve the brief.
- **Generic copy** — "Seamlessly streamline your workflow." Write from the user's side, in
  the subject's vocabulary.
- **Symmetry-by-default** — everything centered and evenly spaced because it's safe.

## Anti-slop bans (folded in from TasteSkill — the fast, mechanical tells)
Beyond the three clusters above, these are the specific patterns that read as generated. The
Designer audits them in the **taste preflight** (`taste-preflight.md`) and the QA Engineer scans the
*rendered* UI for them. A match is a finding unless the brief genuinely demands it and you say why.

- **Em-dashes in shipped UI copy** — the single most-flagged LLM tell. Ban them in the *product's*
  headlines, body, labels, and quotes; rewrite with commas, colons, or full stops.
  **Scope:** this applies **only to end-user-facing copy the product renders** — *not* to Orbit's own
  internal docs, playbooks, or reports (which keep their house style, em-dashes included).
- **Fake dashboards / div-drawn fake screenshots** standing in for real UI or real imagery.
- **Default purple / mesh-gradient centered hero + glow**; the beige-brass-espresso "luxury" palette
  reused across projects; Inter or a "premium" serif (Fraunces / Instrument Serif) chosen by reflex.
- **Three identical generic feature cards** in a row; **generic cards** that encode nothing.
- **Fake version labels** and fake-precise specs with no source data.
- **Decorative scroll cues** ("scroll to explore") and **decorative dots / dividers / badges** that
  carry no information.
- **Generic names** ("John Doe", "Acme Co") and **empty marketing copy** ("Seamlessly streamline your
  workflow"); filler verbs ("Elevate", "Unleash", "Seamless").
- **Structural red flags:** a hero that doesn't fit one viewport; desktop nav wrapping to two lines;
  CTA text wrapping to multiple lines; eyebrow labels on every section (cap ~1 per 3).

## The test
For each major choice ask: *"Would a different brief have produced the same choice?"* If yes,
it's a default, not a decision. Replace it with something that could only belong to *this*
subject.
