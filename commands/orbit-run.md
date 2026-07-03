---
description: Run a task through the Orbit loop (read→plan→act→evaluate→update→decide) instead of free-editing.
argument-hint: <the task, e.g. "add a logout button" or "port the dashboard screen">
---

Route this **task** through the Orbit loop — do not free-edit the codebase directly.

Task: $ARGUMENTS

1. **READ** — read `CLAUDE.md` and `.orbit/STATE.md`. If there is no `.orbit/` system in this
   repo yet, tell the user to run `/orbit` first to set it up, then stop.
2. **QUEUE** — append the task to `.orbit/STATE.md`'s task queue with a clear done-gate.
3. **RUN the cycle** via the sub-agent roster in `.claude/agents/`: Dispatcher (confirm it's a
   task, not a question) → the specialists it needs → QA-Engineer (validate against the
   acceptance criteria / RTM) → Reviewer (quality gate) → Safety (veto) → Reporter. Dispatch
   roles with the Task tool. **Show the checklist two ways (do both):**
   (a) **write `.orbit/tasks.json`** via `.orbit/activity.py` `set_tasks`/`update_task` —
   the guaranteed-visible path that feeds `orbit-status`; (b) **also build the native checklist
   with `TaskCreate`/`TaskUpdate`** (the `Task*` tools — NOT `TodoWrite`, which is off by
   default), role-tagged (`[data] …`, `[safety] …`), **driven by you, the main orchestrator**
   (a subagent's task calls don't surface). Don't just narrate `[role]` lines and skip the files.
4. **EVALUATE** against `CLAUDE.md` §3 and the gates in `.orbit/loop.config.json`. Honor the
   stop conditions (§8) and approval checkpoints — **propose, never auto-perform**, anything
   irreversible, financial, or outward-facing.
5. **UPDATE + REPORT** — fold results into `.orbit/STATE.md` (snapshot, queue, cycle log) and
   give a short, decision-ready summary of what changed.

Follow the routing rule in `CLAUDE.md` §10. Open with `[orchestrator] routing: $ARGUMENTS`.
For a quick one-cycle interactive run, keep it tight; for larger/unattended work, point the
user at `scripts/ralph_loop.sh` (dev) or a durable engine (see `references/durable-execution.md`).
