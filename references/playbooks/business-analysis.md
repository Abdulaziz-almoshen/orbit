# Business analysis — the requirements contract

Use this playbook on every T2/T3/T4 task after Product Discovery and before Planner or Designer.
Its output is the shared contract for implementation, Reviewer, QA, and CPO. It is not optional
prose and it is not a restatement of the request.

## Required artifact

Write `.orbit/artifacts/<cycle>/business-analysis.md` with:

1. **Goal and actors** — original user outcome, primary/secondary actors, and what success changes.
2. **Current → future workflow** — numbered happy path plus alternate and failure paths.
3. **Business rules** — stable `BR-*` IDs, precedence, permissions, timing, limits, and exceptions.
4. **Functional requirements** — stable `FR-*` IDs, each atomic and implementation-independent.
5. **Non-functional requirements** — `NFR-*` IDs for security, accessibility, performance,
   reliability, privacy, localization, observability, and compatibility where applicable.
6. **Data dictionary** — entities/fields, source of truth, allowed states, validation, retention,
   and migrations touched.
7. **EARS acceptance criteria** — observable `Given/When/Then` or EARS statements for every ID.
8. **Traceability baseline** — `goal → evidence → requirement → criterion → planned proof`.
9. **Assumptions and decisions** — fact / repo-derived inference / assumption labels; owner and
   deadline for anything unresolved.
10. **Out of scope** — what this run intentionally does not promise.

## Gate

`READY` only when every material behavior has an owner, rule, acceptance criterion, and proof path.
Return `BLOCKED` when an unresolved choice changes money, permissions, persisted data, outward-facing
behavior, compliance, or the user's core workflow. Do not let Planner or Builder silently decide it.

Announce `[business-analyst] …`; emit `start`/`done`/`blocked` through `.orbit/activity.py`.
