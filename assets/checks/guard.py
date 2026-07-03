#!/usr/bin/env python3
"""
Orbit safety guard — a PreToolUse hook that BINDS regardless of the agent's choice.

Claude Code runs this BEFORE a Bash tool call; if it returns a "deny" decision the command
never executes — the model gets no say. That's the difference between a guarantee and a
suggestion: prose in CLAUDE.md is advisory and can be silently skipped; this hook binds.

It is installed by default when /orbit sets up a repo (announced, with a one-line removal via
orbit-uninstall). Remove it anytime.

Protocol (Claude Code ≥ 2.1): read the PreToolUse JSON on stdin; print NOTHING to allow, or
    {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                            "permissionDecision": "deny"|"ask",
                            "permissionDecisionReason": "..."}}
to block ("deny") or pause for a human ("ask"). We match the parsed ARGV of EACH command
segment (splitting `cd x && git push --force`, stripping `sudo`/`env`, recursing into
`sh -c "..."`) — never a substring. Fail OPEN: any error allows the command, because a guard
must never brick your shell.
"""
import hashlib
import json
import shlex
import sys

_OPERATORS = {"&&", "||", ";", "|", "&"}
_WRAPPERS = {"sudo", "nohup", "command", "builtin", "exec", "time", "doas"}
_SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}


def is_git(t):
    return bool(t) and t[0] == "git"


def _push(t):
    return is_git(t) and "push" in t


def _dry_run(t):
    return "--dry-run" in t or "-n" in t


def _force_with_lease(t):
    return any(x == "--force-with-lease" or x.startswith("--force-with-lease=") for x in t)


def _hard_force(t):
    if "--force" in t or "-f" in t:
        return True
    try:
        pi = t.index("push")
    except ValueError:
        return False
    return any(x.startswith("+") and len(x) > 1 for x in t[pi + 1:])  # +refspec = a forced push


# --- customize for YOUR repo -------------------------------------------------------------
# Each rule: (decision, reason, predicate(argv_tokens) -> bool). "deny" = never allowed;
# "ask" = pause for human approval. Matched per command segment; first match (deny beats ask).
RULES = [
    ("deny", "force-push rewrites shared history and is not allowed. Open a normal PR instead.",
     lambda t: _push(t) and _hard_force(t) and not _force_with_lease(t) and not _dry_run(t)),
    ("ask",  "force-with-lease is a human-approval checkpoint here — confirm before pushing.",
     lambda t: _push(t) and _force_with_lease(t) and not _dry_run(t)),
    ("ask",  "git push is a human-approval checkpoint here — confirm before pushing.",
     lambda t: _push(t) and not _dry_run(t)),
    ("ask",  "merging into the default branch is a human-approval checkpoint.",
     lambda t: is_git(t) and t[1:2] == ["merge"]
        and any(b in t for b in ("master", "main", "origin/master", "origin/main"))),
    # Add your repo's own FORBIDDEN / ASK actions here, e.g.:
    #   ("deny", "the DB schema is frozen.", lambda t: (not is_git(t)) and "migrate" in t),
    #   ("ask",  "deploys need a human.",    lambda t: t[:1] == ["deploy"]),
]
# -----------------------------------------------------------------------------------------

_SEVERITY = {"deny": 2, "ask": 1}


def _strip_wrappers(t):
    while t:
        if t[0] in _WRAPPERS:
            t = t[1:]
            continue
        if t[0] == "env":
            t = t[1:]
            while t and "=" in t[0] and not t[0].startswith("-"):
                t = t[1:]
            continue
        break
    return t


def _tokenize(line):
    """Tokenize one line, keeping shell operators (&&, ||, ;, |, &) as separate tokens."""
    lex = shlex.shlex(line, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    return list(lex)


def _segments(cmd):
    """Split a command string into argv lists, one per shell segment (&&, ||, ;, |, & and newlines)."""
    out = []
    for line in cmd.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            toks = _tokenize(line)
        except Exception:
            try:
                out.append(shlex.split(line))
            except Exception:
                pass
            continue
        cur = []
        for tk in toks:
            if tk in _OPERATORS:
                if cur:
                    out.append(cur)
                cur = []
            else:
                cur.append(tk)
        if cur:
            out.append(cur)
    return out


def evaluate(cmd, _depth=0):
    """Return the most severe (decision, reason) triggered by any segment, or None to allow."""
    if _depth > 4:
        return None
    best = None
    for seg in _segments(cmd):
        t = _strip_wrappers(list(seg))
        if not t:
            continue
        if t[0] in _SHELLS and "-c" in t:                 # sh -c "..." → evaluate the payload
            i = t.index("-c")
            if i + 1 < len(t):
                sub = evaluate(t[i + 1], _depth + 1)
                if sub and (best is None or _SEVERITY[sub[0]] > _SEVERITY[best[0]]):
                    best = sub
            continue
        for decision, reason, pred in RULES:
            try:
                if pred(t):
                    if best is None or _SEVERITY[decision] > _SEVERITY[best[0]]:
                        best = (decision, reason)
                    break
            except Exception:
                continue
    return best


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict) or data.get("tool_name") != "Bash":
            return  # allow (print nothing)
        cmd = (data.get("tool_input") or {}).get("command", "") or ""
        hit = evaluate(cmd)
        if hit:
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": hit[0],
                "permissionDecisionReason": f"[orbit] {hit[1]}",
            }}))
    except Exception:
        return  # fail OPEN — a guard must never brick the shell


if __name__ == "__main__":
    main()
