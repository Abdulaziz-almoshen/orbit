# STATE.md template

`.orbit/STATE.md` is the system's working memory — the scratchpad it reads at the start
of a cycle and rewrites at the end. It changes constantly, which is exactly why it's
separate from `CLAUDE.md`: durable facts stay stable in CLAUDE.md, churn lives here.

Design rules:
- **One owner writes it per cycle** (the Orchestrator). Specialists report results *to*
  the Orchestrator, which folds them in. This avoids write races when roles run parallel.
- **Append to the log, overwrite the snapshot.** The "Current snapshot" section is
  replaced each cycle; the "Decision log" and "Cycle log" only grow (newest on top).
- Keep entries terse and factual. This is a state machine's memory, not prose.

Copy the structure below to `.orbit/STATE.md` and seed it from the audit.

---

```markdown
# Working State — <Product Name>

_Last updated: <UTC timestamp> by <role/cycle id>_

## Run goal
(The single objective of the current run, in one sentence. The loop's "done" is when
this is met. Example: "Produce one validated output for <unit of work> that passes the
quality and safety gates, fully explained.")

## Current snapshot  (overwrite every cycle)
- Iteration: <n> of <max>
- Budget: <tokens/cost used> of <cap>
- Phase: <plan | act | evaluate | update | decide>
- Active role(s): <who is working>
- Last cycle result: <one line — pass/fail of eval gate, key metric>
- Blockers / awaiting human: <none | description + what's needed>

## Task queue  (overwrite every cycle; ordered)
- [ ] <next action> — owner: <role> — gate: <what must be true to call it done>
- [ ] <...>
- [x] <completed this run> — result: <one line>

## Open questions / assumptions
- <thing we assumed because it was ambiguous; flag for human if it matters>

## Decision log  (append-only, newest first)
- <timestamp> — <decision> — because <reason> — by <role/human>

## Cycle log  (append-only, newest first; one line per cycle)
- <timestamp> iter <n>: <action taken> → <eval result> → <decision>

## Handoffs  (overwrite; current in-flight handoffs between roles)
- <from-role> → <to-role>: <artifact/location> — <what's needed back>
```

---

## How the loop uses this file

- **READ:** load `CLAUDE.md` then `STATE.md`. The snapshot + task queue tell the
  Orchestrator where things stand without any conversation history — this is what makes
  fresh-context cycles work.
- **UPDATE:** at cycle end, the Orchestrator overwrites the snapshot, task queue, and
  handoffs; appends one line to the cycle log; appends any new decisions.
- **DECIDE:** if the run goal is met → done. If a blocker needs a human → pause and
  surface it. If a hard cap tripped → stop. Otherwise → continue with the top queue item.

Keep this file the ground truth of "where are we right now." If an agent is ever unsure
what to do next, the answer is here.
