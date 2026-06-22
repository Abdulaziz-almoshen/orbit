# The methodology (the "why")

This skill operationalizes the approach Daisy Hollman described in "Beyond the basics
with Claude Code." The talk is short on slides and long on one idea, so internalize the
idea rather than memorizing steps.

## The core shift

> "You're not supposed to prompt Claude. You're supposed to build a system that prompts
> itself."

A prompt is a single turn. It works once, then the context is gone and you type it
again. That doesn't scale and it doesn't improve. A *system* is different: it keeps its
own notes, breaks work into pieces, runs the pieces, checks the results against a bar it
set for itself, writes down what it learned, and chooses what to do next — and it can do
that a hundred times while you sleep, getting a little further each cycle.

Everything this skill installs exists to make that real, and to make it **safe**.

## The five pillars

1. **Persistent memory.** The system's intelligence lives in files, not in a context
   window. `CLAUDE.md` is the stable source of truth read at the start of every cycle;
   `STATE.md` is the scratchpad written at the end of every cycle. Because state is on
   disk, a fresh agent with zero conversation history can pick up exactly where the last
   one stopped. This is what makes the "Ralph loop" (fresh context each iteration)
   possible — and fresh context is a feature, not a limitation: it prevents context rot
   and keeps each cycle sharp.

2. **Decomposition into specialized sub-agents.** One agent asked to do everything does
   everything mediocrely and blows its context. A *team* — each role with a narrow remit,
   its own instructions, and its own context budget — does each thing well and in
   parallel. The Orchestrator plans and delegates; specialists execute; a Reviewer gates.
   This mirrors a real SDLC org chart on purpose. **Fan out, don't queue:** independent
   work — and independent *deliberation* (generating approaches, scanning risks, inferring
   from the repo) — runs concurrently, then converges. Parallel is both faster *and* sharper
   than a serial chain, because you get several perspectives at once instead of one.

   **Fast by default.** Effort scales to the task, automatically — no mode, no command. A
   small, clear, reversible task is just *done* (reason internally, act, self-check); the full
   team + parallel deliberation is reserved for substantial, ambiguous, or irreversible work.
   The system spends its thinking where the stakes are, so the common case stays quick and the
   hard case stays smart. Surface decisions, not transcripts.

3. **Skills as packaged knowledge.** Recurring domain expertise — the know-how the team
   would otherwise re-derive or re-paste into a prompt every run — shouldn't live in
   prose. Package it once as a skill a role loads on demand. Skills keep CLAUDE.md lean and
   make the system's knowledge auditable and improvable.

4. **The evaluation loop.** "Act" without "evaluate" is just motion. Every cycle the
   system measures its output against explicit success criteria (a quality bar, input
   validity, safety checks) and only proceeds when it clears the bar. Evaluation is what
   turns iteration into improvement instead of drift.

5. **Stop conditions and human gates.** Daisy stressed this hard, because an autonomous
   loop with a credit card and no brakes is a way to wake up to a large bill or a real-
   world mistake. Every loop has hard caps (iterations, cost, runtime), eval gates that
   block bad work from compounding, an explicit "done," and human-approval checkpoints in
   front of anything irreversible or outward-facing. **The loop proposes; a human
   disposes** on the actions that matter.

## The loop shape

```
            ┌─────────────────────────────────────────────┐
            │                                             │
            ▼                                             │
   ┌──────────────┐   ┌────────┐   ┌─────────┐   ┌──────────────┐   ┌──────────┐
   │ READ state   │──▶│ PLAN   │──▶│ ACT     │──▶│ EVALUATE     │──▶│ UPDATE   │
   │ CLAUDE.md +  │   │ next   │   │ via sub-│   │ vs success   │   │ state +  │
   │ STATE.md     │   │ action │   │ agents  │   │ criteria/    │   │ memory   │
   └──────────────┘   └────────┘   └─────────┘   │ eval gates   │   └────┬─────┘
                                                  └──────────────┘        │
                                                                          ▼
                                                                   ┌────────────┐
                                                                   │ DECIDE     │
                                                                   │ continue / │
                                                                   │ spawn /    │
                                                                   │ STOP       │
                                                                   └────────────┘
```

DECIDE checks the stop conditions on every pass. Hitting any hard cap, failing a gate
that can't be recovered, or reaching an explicit "done" ends the run cleanly and leaves
the state file ready for the next human (or scheduled) kickoff.

## What "good" looks like when you're done

- A new agent with no memory can read `CLAUDE.md` + `STATE.md` and know exactly what the
  product is, what's been done, what's next, and what bar to clear.
- No single agent is responsible for everything; work fans out to named roles.
- Domain knowledge is in skills, not smeared through prose.
- The loop physically cannot run unbounded or take an irreversible action alone.
- Running production on the user's own orchestrator (e.g. Gemini) needs none of the Claude
  Code adapter — the core is portable.

Keep this file's spirit in mind through every phase: you are building the machine that
does the work, not doing the work.
