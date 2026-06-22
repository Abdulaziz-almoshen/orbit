# Tools and hooks

The loop's intelligence is in the methodology; its reliability is in how it touches the
outside world. Two principles: treat proven integrations as fixed tools, and enforce
rules with hooks instead of bloating CLAUDE.md.

## Tools: keep what works, wrap it cleanly

- **Don't reinvent reliable integrations.** If an external API or service already works,
  treat it as a tool with a stable contract: typed inputs, typed outputs, errors
  surfaced not swallowed. Roles call the tool; they don't re-implement HTTP.
- **Prefer shelling out to trusted CLIs.** If a job is already a one-liner in an existing
  CLI (a data exporter, a validator, `gh`, etc.), call it rather than rebuilding it
  in-process. Less code, fewer bugs, more reuse.
- **MCP-style thinking for wiring.** Even if you're not literally using MCP, model each
  external capability as a named tool with a clear schema and least-privilege access. A
  role gets only the tools it needs. This keeps the blast radius small and makes the
  system auditable: you can see exactly what each role can touch.
- **One module per integration.** Keep each external API, the model/orchestrator call, and
  any side-effecting interface in their own modules with their own tests. The loop wires
  them together; it doesn't tangle them.

## Hooks: enforce rules on events, not in prose

A rule buried in CLAUDE.md is a suggestion. A rule wired as a hook is enforced. Hooks are
how you keep the persistent memory lean while still guaranteeing behavior.

### Useful hook events for an agentic product
- **After inputs are fetched/loaded** → run the input-validation skill's checks; fail the
  cycle's input gate automatically if completeness/staleness/schema problems are found.
- **After an output is produced** → trigger the quality gate; block "done" until the
  Reviewer's bar is met.
- **On a key milestone** → run the safety checks and emit a notification (to a human
  channel) summarizing what was produced — never an auto-action, just a heads-up.
- **Before any checkpointed action** (financial/outbound/deploy/delete/spend) → hard-stop
  and require human approval. This is the last line of defense behind the config.
- **On run end** → snapshot STATE.md and emit a one-line run summary (iterations, budget
  used, gates passed/failed, outcome).

### Claude Code path — `.claude/settings.json`
Wire hooks in `.claude/settings.json` using Claude Code's hook events (e.g. PostToolUse,
Stop). A hook is a small command the harness runs automatically on the event; use them to
shell out to a validation script or a notifier. Keep hook commands fast and idempotent —
they run often. Example shapes (consult current Claude Code hook docs for exact event
names and schema before writing — don't guess the schema):

```jsonc
{
  "hooks": {
    // run input validation after the fetch/load tool runs
    "PostToolUse": [
      { "matcher": "fetch_inputs",
        "hooks": [{ "type": "command",
                    "command": "python .orbit/checks/validate_inputs.py" }] }
    ],
    // summarize the run when the agent stops
    "Stop": [
      { "hooks": [{ "type": "command",
                    "command": "python .orbit/checks/run_summary.py" }] }
    ]
  }
}
```

If you're unsure of the exact hook event names or matcher syntax for the installed
version, check the Claude Code hooks documentation (the `claude-code-guide` agent can
confirm) rather than inventing fields — a malformed hook silently does nothing.

### Portable path — event handlers in `loop.py`
For the orchestrator-run path (e.g. Gemini), the same events are method calls on the loop:
`on_inputs_loaded()`, `on_output_produced()`, `on_milestone()`, `before_checkpoint()`,
`on_run_end()`. The reference `loop.py` stubs these so you wire validation and
notification in one place, independent of any harness. Same rules, no Claude Code needed.

## The division of labor

- **CLAUDE.md** — what the system *is* and the bar it holds (read every cycle, kept lean).
- **Skills** — *how* to do recurring domain work (loaded on demand).
- **Hooks** — *guarantees* that fire on events (enforcement, not suggestion).
- **Config** — the *limits* the loop runs inside (the safety contract).

When you're tempted to add a long "always remember to…" rule to CLAUDE.md, ask which of
the other three it really belongs in. Usually it's a hook or a skill.

## Enforcement vs. suggestion (the rule that actually matters)

A rule in CLAUDE.md, a role spec, or `loop.py` is **advisory**: it only takes effect if the
agent chooses to honor it, and a normal request goes to normal Claude — which can edit a file
or run a command with none of it firing. A **`PreToolUse` hook is binding**: Claude Code runs
it *before* the tool, and if it returns a deny decision the tool never executes — the agent
gets no say. If a safety rule is non-negotiable, it must be a hook; otherwise you've shipped a
suggestion and called it a guarantee.

A `PreToolUse` hook is a small program: it reads the tool call as JSON on **stdin** and prints
a decision on **stdout** — `{}` to allow, or `{"permissionDecision":"deny"|"ask","message":"…"}`
to block (`deny`) or pause for the human (`ask`). State (e.g. a frozen boundary) lives in an
external file read on every call, so the rule binds across turns and fresh contexts. Register
it in `.claude/settings.json` under `hooks.PreToolUse` with a matcher (e.g. `Bash`). Confirm
the exact field names against current Claude Code hook docs before shipping — a malformed hook
silently does nothing. `.orbit/checks/guard.py` is a working template (left unwired until the
user consents — see SKILL.md Phase 6a).

## Guardrail best practices

- **Match the action, not the string.** Parse the command with `shlex.split()` and match the
  parsed argv (e.g. `tokens[0]=="git" and "push" in tokens`). Substring matching on the raw
  command is the classic footgun — it blocks `git push --dry-run`, a command that merely
  mentions "git push" in a string, and even your own test command.
- **`deny` vs `ask`.** Reserve `deny` for truly irreversible/forbidden actions; use `ask` for
  reversible-but-risky ones so normal work isn't over-blocked.
- **Fail open.** On any parse error, allow — a guard must never brick the user's shell.
- **Be findable.** Install hooks only with consent, print the exact JSON added, and ship a
  one-line removal (`orbit-uninstall`). A guard the user can't turn off is its own hazard.
