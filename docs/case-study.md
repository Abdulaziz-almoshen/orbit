# Case study: governing a messy little app with Orbit

**What this is:** a captured, reproducible walkthrough of the *harness* Orbit stands up on a real
repo — with **real command output**, not a mock-up. Every block below is copy-pasted from an actual
run (Orbit v0.23.1, macOS, `python3`). The commands to reproduce it are at the bottom.

**What this is *not* (yet):** a transcript of a fully autonomous, multi-hour product build. That
requires a live model driving the loop, and we won't paste a synthetic one and call it real —
honesty is the whole point of Orbit. What you see here is the part that is **deterministic and
verifiable today**: the governed skeleton, and the brakes proving they actually bind. The live
end-to-end build is the next artifact; it's marked clearly as pending in [Maturity](../README.md#maturity).

---

## The repo we governed

A throwaway task tracker — one messy file, no memory, no tests, and a `wipe()` that nukes the DB
with no guard. Exactly the kind of thing people point an agent at and then nervously watch:

```python
# app.py — a throwaway task tracker. No memory, no tests, can wipe the DB.
def wipe(): json.dump([], open(DB,"w"))   # <- destructive, no guard
```

Plus a tiny `index.html` with a design token (`--brand:#2b6cb0`) so there's a UI surface to detect.

## One command → a governed harness

```
$ python3 scripts/scaffold.py --surfaces web,cli --install-hooks --target <repo>

Specialists for this project (from surfaces ['web', 'cli']): cli-engineer, frontend-engineer + designer
Created:
  + .orbit/loop.config.json          + .orbit/checks/guard.py   (safety wall)
  + .orbit/loop.py                    + .orbit/checks/route.py   (router)
  + .orbit/activity.py                + .orbit/checks/learn.py
  + scripts/ralph_loop.sh             + .orbit/qa/snapshot.py    (pixel-diff)
  + scripts/orbit-status              + .orbit/qa/extract-tokens.py
  + .orbit/skills/  (13 playbooks)    + .orbit/skills/design-styles/ (67 styles)
  + .claude/agents/  (12 roles)       + .orbit/roles/ (same, model-agnostic)
Installed Orbit's always-on hooks:
  + .claude/settings.json → hooks.PreToolUse[matcher=Bash] → guard.py
  + .claude/settings.json → hooks.UserPromptSubmit → route.py
```

**115 files** land deterministically. The *only* thing left to hand-author is the project-specific
part — `CLAUDE.md` (the plan + rules) and the one domain skill. The structure is a script, not an
essay.

## The team it provisioned — fitted to the surfaces, not a fixed template

The repo had a web surface and a CLI surface, so Orbit stood up **one engineer per surface** plus
the universal spine (12 agents total):

```
dispatcher  orchestrator  product-discovery  market-researcher  planner
reviewer    qa-engineer   reporter           safety-gate                     ← universal spine
frontend-engineer   cli-engineer   designer                                  ← per detected surface
```

A backend-only repo gets `backend-engineer` and **no** designer; a data repo gets `data-engineer`.
The roster is derived from the code, not pasted in.

## The brakes that actually bind

This is the part that separates "a folder of prompts" from a governed system. Both are real hook
I/O — the exact JSON Claude Code sends, and the exact decision the hook returns.

### The safety wall (`PreToolUse` → `guard.py`)

```
git push --force origin main       -> deny        (catastrophic: history rewrite)
cd src && git push --force         -> deny        (guard splits on && — no bypass)
git commit -m ok                   -> allow (no output)
```

The middle line is the one that matters: a naive matcher only sees `cd src`. Orbit's guard splits
the command into segments and inspects each, so wrapping the dangerous call behind `cd … &&` doesn't
sneak it past. The decision is returned in the envelope current Claude Code actually enforces
(`hookSpecificOutput.permissionDecision`) — the model never gets a vote.

### The router (`UserPromptSubmit` → `route.py`)

```
"add a wipe-confirmation prompt to app.py"  -> TASK       (routes through the loop)
"is the task list persisted?"               -> QUESTION   (answered directly, no ceremony)
"why did the last run stop?"                -> QUESTION
"yes"                                        -> no injection (an ack — nothing to route)
```

Deterministic, every message, before the model responds. It's a keyword matcher (honest about that:
it injects the *default lane*, which the Dispatcher can override with a one-line reason), but it
means the task/question split isn't left to the model's mood.

### The hard limits (`loop.config.json`)

```json
{ "max_iterations": 3,
  "token_budget": { "per_cycle": 60000, "per_run": 250000 },
  "cost_budget_usd": { "per_run": 5.0 },
  "max_runtime_seconds": 1800 }
approval_checkpoints: { "move_money": "FORBIDDEN", "deploy": "human",
                        "delete_data": "human", "spend_over_usd": 1.0 }
```

The `ralph_loop.sh` runner meters real cost + tokens from `claude -p --output-format json` and stops
when a budget is hit; `delete_data: human` is exactly the gate that would make that unguarded
`wipe()` pause for a human instead of running.

## The QA executors — helpers, honest about their limits

On the web surface, Orbit provisioned `.orbit/qa/`. The pixel-diff is pure-python (no browser):

```
$ snapshot.py diff build.ppm approved.ppm --threshold 0.01
FAIL: 1/16 pixels differ = 6.2500% (threshold 1.0000%)   → diff.ppm
```

The screenshot / computed-token tools use Playwright *if installed*, and otherwise **say so and exit
cleanly** instead of crashing the cycle:

```
$ extract-tokens.py file://…/index.html --compare index.html
extract-tokens needs Playwright (not bundled).
  pip install playwright && playwright install chromium
Or read computed styles with your browser tool …
```

Helpers, not a bundled browser — the QA role falls back to a browser MCP, gstack `/browse`, or a
manual capture.

## What's proven here — and what isn't

| Claim | Status in this case study |
|---|---|
| Scaffolds a fitted, governed skeleton in one command | ✅ **shown** (115 files, surface-derived team) |
| Safety wall blocks catastrophic git — no `cd &&` bypass | ✅ **shown** (real hook I/O) |
| Router classifies every message deterministically | ✅ **shown** (real hook I/O) |
| Hard iteration/token/cost/approval limits are configured + metered | ✅ **shown** (config) / ⚙️ metering unit-tested |
| QA pixel-diff works with no browser; tools degrade gracefully | ✅ **shown** |
| A full autonomous product build, start to finish, unattended | ⏳ **pending** — needs a live model run; not faked here |

The behavioral claims above are also locked in by an automated suite (8 test files: guard schema +
`cd &&` cases, router accuracy, budget persistence, migration safety, the coherence gate). See
[`docs/evals.md`](evals.md) for the eval harness.

## Reproduce it yourself

```bash
# 1. a messy demo repo
mkdir demo && cd demo && git init
printf 'def wipe(): open("db","w").close()\n' > app.py && git add -A && git commit -m init

# 2. stand up the harness (from an Orbit checkout)
python3 /path/to/orbit/scripts/scaffold.py --surfaces web,cli --install-hooks --target .

# 3. watch the brakes bind
echo '{"tool_name":"Bash","tool_input":{"command":"cd src && git push --force"}}' | python3 .orbit/checks/guard.py
echo '{"prompt":"is it persisted?"}' | python3 .orbit/checks/route.py
```
