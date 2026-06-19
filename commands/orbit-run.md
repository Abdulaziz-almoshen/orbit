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
   task, not a question) → the specialists it needs → Safety (veto) → Reviewer (quality gate)
   → Reporter. Use the Task tool to dispatch roles, and drive a TodoWrite checklist with
   role-tagged items (`[data] …`, `[safety] …`) so the user sees who's working.
4. **EVALUATE** against `CLAUDE.md` §3 and the gates in `.orbit/loop.config.json`. Honor the
   stop conditions (§8) and approval checkpoints — **propose, never auto-perform**, anything
   irreversible, financial, or outward-facing.
5. **UPDATE + REPORT** — fold results into `.orbit/STATE.md` (snapshot, queue, cycle log) and
   give a short, decision-ready summary of what changed.

Follow the routing rule in `CLAUDE.md` §10. Open with `[orchestrator] routing: $ARGUMENTS`.
For a quick one-cycle interactive run, keep it tight; for larger/unattended work, point the
user at `scripts/ralph_loop.sh` (dev) or a durable engine (see `references/durable-execution.md`).
