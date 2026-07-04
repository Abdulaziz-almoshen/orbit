# Playbook: Taste preflight — the read, the dials, the anti-slop gate (the Designer loads this)

Adapted from **TasteSkill** (Leonxlnx, MIT — see `CREDITS.md`); adapted, not copied. TasteSkill's one
job is to stop AI-generated UI from *looking* generated. Orbit already owns the operating model — the
HEAVY/TRIVIAL triage, the prototype gate, the `DESIGN.md` + `design/approved.json` contract, and the
QA verification triangle. This playbook adds the **taste layer** on top of that: a one-line design
*read*, three explicit *dials*, a real-design-system *map*, surface-aware *scope*, and a **hard
preflight checklist** that runs before the Designer hands to the Builder and gates HEAVY UI at review.
It **extends** `anti-ai-aesthetics.md` (the ban list) — it does not replace it.

## When it runs
- The Designer runs the preflight on **HEAVY** UI work — as part of, or immediately after, whichever
  prototype gate fired — and records the outcome in `design/approved.json` under `taste_preflight`
  (see *The record*).
- **TRIVIAL** work skips it: the fast lane stays fast and the `.orbit/design/TRIVIAL` marker is proof
  enough.
- **Scope by surface** (§5) decides how much of the full preflight actually applies.

## 1. The design read (state it before choosing a style)
Before shortlisting styles, declare **one line**:

> Reading this as: **[page kind]** for **[audience]**, with a **[vibe]** language, leaning toward
> **[system / aesthetic]**.

This forces an explicit interpretation of the brief instead of a silent default. Signals to read:
page kind, audience, vibe words, references, brand assets, and the *quiet* constraints (perf budget,
existing tokens, target platform). If the read genuinely diverges from the brief, ask **exactly one**
clarifying question — otherwise state the read and proceed with confidence.

## 2. Three dials (set them explicitly, 1–10 — they drive every layout / motion / spacing call)
- **`DESIGN_VARIANCE`** (1–10): symmetry ↔ asymmetry. Low = centered, clean, safe; high = asymmetric,
  editorial, unexpected.
- **`MOTION_INTENSITY`** (1–10): static ↔ choreographed. Low = hover states only; high = scroll-driven,
  magnetic, orchestrated.
- **`VISUAL_DENSITY`** (1–10): airy ↔ cockpit-packed. Low = gallery / marketing; high = dense dashboard.

No silent defaults: name the three numbers in the Design Plan and let them *justify* the composition.
The surface (§5) sets the sane starting range; a value far from that range needs a reason.

## 3. Design-system map (reach for a real system when the brief aligns — don't reinvent)
Distinct from the 67-style aesthetic catalog in `design-styles.md`: those are **looks**; these are
**conventions** — components, spacing scales, interaction and accessibility patterns you inherit
wholesale when the product *is* that kind of product.

| System | Reach for it when the product is… |
|---|---|
| **Material** | broad consumer / Android-adjacent |
| **Fluent** | Microsoft / Windows enterprise |
| **Carbon** | IBM-style data-dense enterprise |
| **Polaris** | commerce / merchant admin (Shopify-shaped) |
| **Atlassian** | productivity / issue-and-doc tools |
| **Primer** | developer tools (GitHub-shaped) |
| **GOV.UK / USWDS** | government, accessibility-first, plain-language |
| **Bootstrap** | fast, conventional, get-it-shipped web |
| **Radix / shadcn** | composable React primitives you skin yourself |
| **Tailwind** | a utility baseline under any of the above |

Pick **at most one** as the convention backbone; the chosen aesthetic style then *skins* it. On a
dashboard/admin surface this map is the **primary** tool — conventions matter more than a novel look.
`"none — bespoke"` is a valid, deliberate choice for expressive marketing/portfolio work; record it as
a decision, not an omission.

## 4. Anti-slop bans (audit against the canonical list — **`anti-ai-aesthetics.md`**)
The full, maintained ban list lives in `anti-ai-aesthetics.md` (the three default clusters + the
folded-in TasteSkill tells) — that file is the single source of truth; don't restate it here. Audit
against it **before building and again before finishing**; a match means revise, unless the brief
*genuinely* demands it and you note why. The two tells worth naming inline, because they gate this
playbook's checklist:

- **Em-dashes in shipped UI copy** — the single most-flagged LLM tell. Ban them in the *product's*
  headlines, body, labels, and quotes (rewrite with commas, colons, or full stops).
  **Scope:** this applies **only to end-user-facing copy the product renders** — *not* to Orbit's own
  internal docs, playbooks, or reports (which keep their house style).
- **Fakery** — fake dashboards / div-drawn fake screenshots, fake version labels, generic names, and
  empty marketing copy read as generated on sight. (See `anti-ai-aesthetics.md` for the rest: palette /
  type reflexes, layout tells, content tells, structural red flags.)

## 5. Scope by surface (how much of the preflight applies)
The **§6 quality defaults and the §4 ban list apply on every surface** — they are the floor, never
surface-optional. What *changes* by surface is the emphasis: dial ranges, whether to reach for a
design system, and which landing-page flourishes are appropriate.
- **Landing / marketing / portfolio** → the **full** preflight, with room to be expressive: the read,
  dials skewed toward low density, an *optional* design system, hero photography, and the whole ban
  list. This is TasteSkill's home turf.
- **SaaS / app / dashboard / admin** → the **design-system map (§3)** is the primary tool and the
  **ban list (§4)** still holds; set `VISUAL_DENSITY` high and lean on Orbit's product-UI QA (the RTM +
  pixel pass in `qa-validation.md`). Skip only the *landing-page flourishes* — hero photography, a
  dark-by-reflex palette — unless the brief asks. Here, conventions beat novelty. (The §6 defaults —
  colour-mode strategy, motivated motion, a11y — still apply.)
- **Mobile / native** → **platform guidelines first** (Apple HIG / Android Material) — they own
  navigation, touch targets, and system patterns. Use TasteSkill only for visual *polish* (palette,
  type, motion restraint); never to override a platform convention. The §6 a11y and motion defaults
  still apply, expressed the platform's way.

## 6. Quality defaults (every surface — the floor, not landing-only)
- **Motion is motivated:** every animation justifies itself in one sentence (hierarchy · feedback ·
  state · storytelling). No scatter. Clean up listeners; avoid raw `window` scroll handlers.
- **Images over empty divs:** real or seeded-placeholder imagery in explicit slots — never a div-drawn
  fake UI standing in for a screenshot.
- **Colour-mode strategy declared up front** (light, dark, or dual) and checked in whatever modes
  ship. Adapt to the product — don't force dark by reflex.
- **Accessibility is not optional:** WCAG AA 4.5:1 text contrast, labelled controls, visible keyboard
  focus, `prefers-reduced-motion` honoured. (Mirrors the methodology's quality floor.)

## 7. Redesign audit (when changing an existing UI)
Audit **before** redrawing: extract the current brand tokens, map the existing information
architecture, and split **preserve** (SEO, accessibility wins, established copy voice, working IA)
from **modernise**. No silent IA shifts — a navigation or hierarchy change is itself a HEAVY decision
that goes through the prototype gate.

## The record (what the Designer writes, what QA / Reviewer check)
On **HEAVY**, the Designer records the preflight *inside* `design/approved.json` so later gates verify
it mechanically rather than by vibe:

```json
"taste_preflight": {
  "design_read": "Reading this as: a pricing page for indie founders, with a confident-utilitarian language, leaning toward Linear/shadcn.",
  "dials": { "variance": 4, "motion": 3, "density": 6 },
  "design_system": "shadcn",
  "surface": "app",
  "checklist_passed": true
}
```

`design_system` is a name from §3 or `"none"` (bespoke) — deliberate either way. `surface` is one of
`landing` · `app` · `mobile`. QA (`qa-validation.md`) and the Reviewer's Design-Distinctiveness gate
treat a **HEAVY** `approved.json` with **no `taste_preflight`** as a finding — the taste gate was
*skipped*, not judged unnecessary. TRIVIAL work is exempt. The `design-gate.py` hook also asks on a
HEAVY UI edit whose approval carries no `taste_preflight`.

## The hard preflight checklist (run mechanically before handing to the Builder — every box)
- [ ] **Design read** stated (one line).
- [ ] **Three dials** set (variance / motion / density), justified by the surface.
- [ ] **Design system** chosen from §3, or `"none — bespoke"` deliberately.
- [ ] **Anti-slop ban list (§4 + `anti-ai-aesthetics.md`)** audited — zero matches, or a
      brief-justified exception noted.
- [ ] **No em-dashes** in shipped UI copy.
- [ ] **Colour-mode strategy** declared; **a11y floor** met (contrast · focus · reduced-motion · labels).
- [ ] On a **redesign**: brand tokens extracted, IA mapped, preserve-vs-modernise split written.
- [ ] **`taste_preflight` recorded** in `design/approved.json`.
