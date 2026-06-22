#!/usr/bin/env python3
"""
Orbit safety guard — a PreToolUse hook that BINDS regardless of the agent's choice.

This is the enforcement layer the agent cannot talk its way around. Claude Code runs this
BEFORE a Bash tool call; if it returns a "deny" decision, the command never executes — the
model gets no say. That's the difference between a guarantee and a suggestion: prose in
CLAUDE.md is advisory and can be silently skipped (see BEGINNER-MODE.md); this hook is
binding. (Pattern mirrors gstack's check-freeze.sh / check-careful.sh.)

It is DISABLED until you wire it into .claude/settings.json. The /orbit skill asks before
doing that, prints the exact JSON it adds, and shows the one-line removal. Don't wire it
silently — a guard the user can't find the off-switch for is its own footgun.

Protocol: read the PreToolUse JSON on stdin; print `{}` to allow, or
`{"permissionDecision":"deny"|"ask","message":"..."}` to block ("deny") or pause for a
human ("ask"). Match the parsed ARGV via shlex — NEVER a substring — so `git push --dry-run`
or a command that merely mentions "git push" inside a string is not falsely blocked. Fail
OPEN: any parse error allows the command, because a guard must never brick your shell.
"""
import json
import shlex
import sys


def is_git(t):
    return bool(t) and t[0] == "git"


# --- customize for YOUR repo -------------------------------------------------------------
# Each rule: (decision, reason, predicate(argv_tokens) -> bool).
#   "deny" = never allowed (truly irreversible/forbidden).
#   "ask"  = pause for human approval (reversible-but-risky).
# Match the ACTION precisely on tokens, not the raw string. Order matters: first match wins.
RULES = [
    ("deny", "force-push rewrites shared history and is not allowed. Open a normal PR instead.",
     lambda t: is_git(t) and "push" in t and any(f in t for f in ("--force", "-f", "--force-with-lease"))),
    ("ask",  "git push is a human-approval checkpoint here — confirm before pushing.",
     lambda t: is_git(t) and "push" in t),
    ("ask",  "merging into the default branch is a human-approval checkpoint.",
     lambda t: is_git(t) and t[1:2] == ["merge"] and any(b in t for b in ("master", "main", "origin/master", "origin/main"))),
    # Add your repo's own FORBIDDEN / ASK actions here, e.g.:
    #   ("deny", "the DB schema is frozen.", lambda t: is_git(t) is False and "migrate" in t),
    #   ("ask",  "deploys need a human.",    lambda t: t[:1] == ["deploy"]),
]
# -----------------------------------------------------------------------------------------


def allow():
    print("{}")
    sys.exit(0)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        allow()  # fail-open: never brick the shell on a parse error
    if data.get("tool_name") != "Bash":
        allow()
    cmd = (data.get("tool_input") or {}).get("command", "")
    try:
        tokens = shlex.split(cmd)
    except Exception:
        allow()  # unparseable command -> don't block
    for decision, reason, pred in RULES:
        try:
            if pred(tokens):
                print(json.dumps({"permissionDecision": decision, "message": f"[orbit] {reason}"}))
                sys.exit(0)
        except Exception:
            continue
    allow()


if __name__ == "__main__":
    main()
