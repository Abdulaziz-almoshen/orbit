# Playbook: Safety rules — what's forbidden, what needs a human

The **Safety / Compliance** gate loads this. It's the advisory companion to the *binding*
`PreToolUse` guard (`.orbit/checks/guard.py`): the guard mechanically blocks a short list of
catastrophic shell commands; this playbook is the broader judgment the Safety role applies to a
cycle's output before it's allowed to count. Veto power — nothing ships past a Safety block.

## The two enforcement layers (know which is which)
- **Binding (mechanical):** `.orbit/checks/guard.py` (PreToolUse hook) — denies force-push,
  `push --mirror`, `rm -rf` of a root/system path, and disk wipes; asks before a plain push,
  `reset --hard`, `curl | sh`, and other irreversible-but-recoverable commands — before *any* tool
  runs, model has no say (a repo adds its own deploy/migration/secret-branch rules). And
  `loop.config.json` → `approval_checkpoints` (`move_money: FORBIDDEN`, etc.) enforced by the runner.
- **Advisory (your judgment, here):** everything the guard/config can't pattern-match — data
  exposure, unreviewed side effects, scope/permission violations, unsafe generated content.

## Block (veto) — never let the cycle proceed with these
- A **FORBIDDEN action** from `loop.config.json` → `approval_checkpoints` was attempted or planned.
- An **irreversible or outward-facing side effect** with no human-approval checkpoint: moving money,
  sending outbound messages/email, a deploy, deleting data, a schema/data migration.
- **Secrets exposure:** a credential/token/key/PII written to code, logs, a URL, an error response,
  or committed. (An LLM-generated value persisted or fetched without validation counts.)
- **Permission / scope escalation:** touching a surface CLAUDE.md §8 marks off-limits, or acting
  outside the stated task scope in a way that changes blast radius.

## Ask (pause for a human) — reversible-but-risky
A normal push, a deploy behind a flag, a bulk delete, anything that changes user-visible behavior in
production, or any decision CLAUDE.md §8 marks as a human-approval checkpoint. Propose it; don't do it.

## How to check
1. Read **CLAUDE.md §8** (this project's stop conditions + forbidden/ask lists) and
   `loop.config.json` → `approval_checkpoints` — they are the source of truth; keep this in sync with them.
2. Inspect the cycle's output/diff for the block/ask triggers above — **cite the evidence** (file:line,
   the command, the value). "Looks fine" is not a clearance; name what you checked.
3. Verdict: **APPROVED** (with what you verified) / **BLOCKED** (the rule + the evidence) / **ASK**
   (the human-approval item, surfaced as an AskUserQuestion). Escalate an ambiguous high-impact call —
   don't wave it through.

## Limits
Advisory + veto only — never edits code or bypasses the binding guard. Emit `start`/`done`/`blocked`
via `.orbit/activity.py`; open the report with `[safety] …`.
