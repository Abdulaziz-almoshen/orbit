# Observability — "who's talking" + the live checklist

A loop you can't watch is a loop you don't trust. Orbit makes every cycle legible: at any
moment you can see **which agent is talking, what stage it's in, what it just did, and the
checklist crossing itself off**. This is the difference between staring at a black box and
watching a team work.

The design is one principle: **one event stream, multiple renderers.** The loop and every
role emit structured events to a single place; you render them however your environment
allows. Don't scatter ad-hoc prints — emit events, then render.

## The two data files (written by `activity.py`)

- **`.orbit/activity.jsonl`** — append-only thread, one event per line:
  ```json
  {"ts":"2026-06-18T20:01:04Z","cycle":1,"role":"data","phase":"act","status":"start","msg":"validating inputs","task_id":"t2"}
  ```
  `role` = who's talking. `phase` ∈ plan·act·evaluate·update·decide·read. `status` ∈
  start·done·blocked·info. `msg` = the human-readable line.
- **`.orbit/tasks.json`** — the checklist:
  ```json
  [{"id":"t2","title":"validate inputs","owner":"data","status":"in_progress"}]
  ```
  `status` ∈ pending·in_progress·done·skipped. `owner` = the role responsible — this is how
  the checklist also shows *who* owns each step.

`activity.py` (scaffolded to `.orbit/activity.py`) gives three best-effort calls:
`emit(role, phase, status, msg, cycle, task_id)`, `set_tasks(tasks)`,
`update_task(id, status)`. They never raise into the caller.

## Renderer 0 — inline in chat (universal: the desktop-app & web path)

The pinned task list and the terminal dashboard below are **surface-specific** — they show in the
Claude Code IDE/CLI. In the **Claude desktop app and claude.ai web** there is no pinned panel and no
terminal, so the *only* thing the user sees is what the model prints. So **every cycle, render a
compact "team board" inline** in the reply — this is the one renderer that works everywhere:

```
🛰 Orbit · cycle 2
✓ 🟣 planner — planned the change
✓ 🟢 frontend-engineer — built the form
▸ 🟡 reviewer — proving it (running tests)…
○ 🔴 safety · ○ ⚪ reporter
```

Emoji role colors match `orbit-status`: 🔵 dispatcher · 🟣 planner · 🟢 engineer · 🟪 designer ·
🟡 reviewer · 🔴 safety · ⚪ reporter. Keep it short (live "who's talking," not a log). It reads from
the same `.orbit/tasks.json` + `.orbit/activity.jsonl` as the other renderers, so it's always in sync.

## Renderer 1 — Claude Code native (the pinned task checklist)

When the loop runs **inside Claude Code**, build the checklist with the built-in
**`TaskCreate` / `TaskUpdate` / `TaskList`** tools (`TaskCreate` to add an item, `TaskUpdate`
to flip it `in_progress`→`completed`). That gives you the pinned, auto-crossed-off list in
the terminal/IDE — the exact behavior you see in VS Code.

> **Important (this is the bug that hid the checklist):** these tools **replaced
> `TodoWrite`**, which is **disabled by default** in current Claude Code (≥ v2.1.142). Use
> the `Task*` tools, not `TodoWrite`. Two more rules that make it actually show:
> - **Drive it from the MAIN orchestrator, not a subagent.** A subagent's `Task*` calls run
>   in its own isolated context and **do not surface** in the user's view — only its final
>   text returns. So the top-level agent owns the checklist; role subagents report back and
>   the orchestrator updates the list on their behalf.
> - **The native checklist is best-effort** — it only appears if the model actually calls
>   the tool. So **always also write `.orbit/tasks.json`** (via `activity.set_tasks` /
>   `update_task`). That feeds `orbit-status` and is the **guaranteed-visible** fallback if
>   the task tools aren't called or aren't enabled.

Two conventions make it show *who*:

1. **Prefix every todo with its owning role**, so the pinned list reads as a cast list:
   ```
   [orchestrator] plan cycle 1
   [data] validate inputs
   [analyst] derive candidate output
   [safety] gate the output        (veto)
   [reviewer] check vs success criteria
   [reporter] write the result
   ```
   Mark each `in_progress` when its role starts and `completed` when it finishes — TaskCreate/TaskUpdate
   strikes it through live.
2. **Every role announces itself in one line** when it acts: `[data] fetched 412 rows, validating…`
   → the transcript thread itself becomes the "who's talking" log. Keep the role tag first
   so it's scannable. The Orchestrator narrates handoffs: `[orchestrator] → safety: gate AAPL signal`.

Keep TaskCreate/TaskUpdate and `tasks.json` in sync — same ids, same owners. The Orchestrator owns both
(one writer), the same way it owns STATE.md.

## Renderer 2 — anywhere (the `orbit-status` dashboard)

Your production loop runs on your own orchestrator (e.g. Gemini), where there's no
TaskCreate/TaskUpdate. So Orbit ships a portable dashboard. Run it in a second terminal pane:

```bash
scripts/orbit-status --follow      # redraws ~1/s — a pinned live dashboard
scripts/orbit-status               # one-shot snapshot
scripts/orbit-status --tail 40     # last N thread lines
```

It reads `tasks.json` + `activity.jsonl` and renders: the **checklist** (✓ done / ▸ active /
○ pending, each tagged with its owner), a **Now** line (the current speaker + phase + msg),
and a color-coded **thread** of who said what. Roles are color-coded so you track speakers
at a glance. Stdlib only — nothing to install.

## How the loop wires it in

- `loop.py` calls `emit()` at each phase boundary (READ/PLAN/ACT/EVALUATE/UPDATE/DECIDE) and
  around every `dispatch(role, …)` (`start` before, `done`/`blocked` after), and
  `set_tasks()` / `update_task()` as the plan and its progress change.
- Each **role**, in its spec (`references/roles.md`), is told to emit a `start` when it picks
  up work and a `done`/`blocked` when it hands off, and to prefix its report with `[role]`.
- A **human checkpoint** emits `role:"human", status:"blocked", msg:"awaiting approval: …"`
  so the dashboard makes it obvious the loop is paused on *you*.

## Why this shape

- **One source of truth.** The same events drive TaskCreate/TaskUpdate, the dashboard, and STATE.md's
  snapshot — they can't drift.
- **Renderer-agnostic.** Today TaskCreate/TaskUpdate + `orbit-status`; tomorrow a web view or an IDE
  panel reads the same `activity.jsonl`. No loop changes needed.
- **Cheap and safe.** Append-only JSONL, best-effort writes, zero deps. If observability
  breaks, the loop doesn't.

The goal: a developer glancing at the screen always knows **who is doing what, right now**,
and how much of the plan is done — live, not after the fact.
