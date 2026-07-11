---
description: Run a task through the Orbit loop (read→plan→act→evaluate→update→decide) instead of free-editing.
argument-hint: <the task, e.g. "add a logout button" or "port the dashboard screen">
---

Route this **task** through the Orbit loop — do not free-edit the codebase directly.

Task: $ARGUMENTS

1. **READ** — read `CLAUDE.md` and `.orbit/STATE.md`. If there is no `.orbit/` system in this
   repo yet, tell the user to run `/orbit` first to set it up, then stop.
2. **QUEUE** — append the task to `.orbit/STATE.md`'s task queue with a clear done-gate.
3. **Board FIRST, then RUN the cycle** via the sub-agent roster in `.claude/agents/`:
   Dispatcher (confirm it's a task, not a question) → the specialists it needs → QA-Engineer
   (validate against the acceptance criteria / RTM) → Reviewer (quality gate) → Safety (veto) →
   Reporter.
   **Your FIRST action — before spawning any specialist — is to make the board visible:** call
   `.orbit/activity.py` `set_team([...])` to declare who's active + who's queued, `set_tasks([...])`
   to write the checklist, and build the native list with `TaskCreate` — all up front, so the user
   sees the plan and who owns each step *immediately*, not after the work is done. Open with a
   one-line assignment. Only then dispatch roles with the **Task tool**.
   **Before a long sub-agent wait, print the inline board** (`scripts/orbit-status --team`) — never
   leave the user on only "waiting for background agent."
   **Show the checklist two ways (do both):**
   (a) **write `.orbit/tasks.json`** via `.orbit/activity.py` `set_tasks`/`update_task` —
   the guaranteed-visible path that feeds `orbit-status`; (b) **also build the native checklist
   with `TaskCreate`/`TaskUpdate`** (the `Task*` tools — NOT `TodoWrite`, which is off by
   default), role-tagged (`[data] …`, `[safety] …`), **driven by you, the main orchestrator**
   (a subagent's task calls don't surface). Update items to `in_progress`/`completed` as roles
   finish. Don't just narrate `[role]` lines and skip the files.

   > **Do NOT run an Orbit task through the native `Workflow(...)` background runner.** It executes a
   > black-box job (`Running in background · /workflows to monitor`) that bypasses Orbit's entire
   > operating model: the role-tagged checklist, the visible current owner, `.orbit/tasks.json`, and
   > `.orbit/activity.jsonl`. Orbit's promise is *watch the team work* — a task is not "running
   > through Orbit" unless the user can see **who owns each step and what's done / in progress**. Use
   > the **Task tool** for sub-agents (each emits `start`/`done` via `.orbit/activity.py`) and drive
   > the checklist yourself. (`Workflow(...)` is fine for *developing Orbit itself*; it is banned as
   > the *run path for a scaffolded repo's tasks*.)
4. **COUNTERFACTUAL PREFLIGHT** for T2+ work, before implementation: use `.orbit/skills/counterfactual-regret.md`
   and `.orbit/counterfactual.py` to attack the riskiest assumption with one cheap falsification probe.
   Record `Assumption -> Probe -> Evidence -> Decision`. A failed probe must route back to its typed
   phase (`discovery`, `plan`, `build`, or `review`) and update the checklist before continuing.
5. **EVALUATE** against `CLAUDE.md` §3 and the gates in `.orbit/loop.config.json`. Honor the
   stop conditions (§8) and approval checkpoints — **propose, never auto-perform**, anything
   irreversible, financial, or outward-facing.
6. **REPAIR ITERATIVELY** when Reviewer, QA, or Safety finds a failure: create a structured
   `repair-<id>.json` packet per `.orbit/skills/iterative-repair.md`, assign a targeted fix, retest
   the original failure plus a regression check, and backtrack to the right phase. Stop after two
   attempts on the same failure and escalate; never repeat the same blind repair.
7. **UPDATE + REPORT** — fold results into `.orbit/STATE.md` (snapshot, queue, cycle log) and
   give a short, decision-ready summary of what changed.

Follow the routing rule in `CLAUDE.md` §10. Open with `[orchestrator] routing: $ARGUMENTS`.
For a quick one-cycle interactive run, keep it tight; for larger/unattended work, point the
user at `scripts/ralph_loop.sh` (dev) or a durable engine (see `references/durable-execution.md`).
