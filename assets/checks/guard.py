#!/usr/bin/env python3
"""
Orbit safety guard — a PreToolUse hook that BINDS regardless of the agent's choice.

Claude Code runs this BEFORE a Bash tool call; if it returns a "deny" decision the command
never executes — the model gets no say. That's the difference between a guarantee and a
suggestion: prose in CLAUDE.md is advisory and can be silently skipped; this hook binds.

Protocol (Claude Code ≥ 2.1): read the PreToolUse JSON on stdin; print NOTHING to allow, or
    {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                            "permissionDecision": "deny"|"ask",
                            "permissionDecisionReason": "..."}}
to block ("deny") or pause for a human ("ask"). Confirmed against the current hooks reference
(hookSpecificOutput.permissionDecision + permissionDecisionReason; the old top-level shape is
ignored). Fail OPEN: any error allows the command, because a guard must never brick your shell.

WHAT IT CATCHES — and its honest threat model. This guard is built to stop the *obvious and
accidental* dangerous command a fallible agent might emit, and the *common ways intent gets
hidden* — it does NOT claim to defeat a determined obfuscator (nothing at the shell layer can:
one can always write a script file, `python -c "os.system(...)"`, or fetch+run). So it:
  • parses EACH command segment's argv (splitting `&&`/`||`/`;`/`|`/`&` and newlines),
  • collapses `\\`-newline line-continuations first,
  • strips leading env-assignments (`X=1 …`), `sudo`/`env`/`nohup`/`xargs`/… **including their own
    flags** (`sudo -E`, `env -i`, `xargs -I{}` no longer leave a flag sitting where the real
    command name belongs), and subshell/brace wrappers (`( … )`, `{ …; }`), and recurses into
    `sh -c "…"` (incl. `-lc`/`-xc`), `eval …`, and command-substitutions `$( … )` / backticks so a
    wrapped force-push is still caught,
  • recognizes home-relative sensitive paths (`~/.ssh`, `$HOME/.aws`, …), not just absolute ones,
  • RESOLVES a `$VAR` command name when the variable was assigned a static literal in the SAME
    command (`B=/path/tool; $B goto …` → the real tool → allowed; `RM="rm -rf"; $RM /` → the real
    command → denied). This kills the common false positive (assign-a-path-then-reuse-it) AND
    catches danger hidden the same way — both used to only "ask",
  • FAILS CLOSED to "ask" when a command's identity is genuinely un-inspectable (its name is a
    variable with no resolvable literal assignment, or a downloader is piped straight into a shell).
Residual limit, stated honestly: wrapper-flag stripping is a KNOWN-flag list (`sudo`/`env`/`xargs`'s
documented value-taking flags), not a full grammar. Variable resolution covers same-command LITERAL
assignments only — a value from `$( … )`, another variable, or the environment stays un-resolvable
and keeps its "ask" (fail-safe: never *allow* on a value we can't determine). Runtime aliases and
base64|sh remain out of scope.

Customize the RULES block for YOUR repo (deploys, migrations, data deletes, secret branches).
"""
import json
import re
import shlex
import sys

_OPERATORS = {"&&", "||", ";", "|", "&"}
_WRAPPERS = {"sudo", "nohup", "command", "builtin", "exec", "time", "doas", "xargs"}
_SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
_GROUPS = {"(", ")", "{", "}"}
_PUNCT = set("();<>|&")                                      # shlex(punctuation_chars=True)'s set
_ATOMIC2 = ("&&", "||", ">>", "<<", ">&", "<&", "|&", "&>")  # 2-char ops to keep whole when re-splitting
_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")            # NAME=value env-assignment prefix
_ASSIGN_FULL = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")  # capture NAME + literal value
_UNSAFE_VAL = set(";|&<>()\n")                              # control operators that void flat resolution
_COMBINED_C = re.compile(r"^-[a-z]*c$")                       # -c, -lc, -xc … (shell command flag)

# Known VALUE-taking flags for the wrappers we strip — so `sudo -u root git push --force` or
# `xargs -I{} sh -c "..."` don't leave a flag/value token sitting where the real command name
# should be (which silently defeats every downstream check). Anything else starting with "-"
# is treated as flag-only and dropped whole — best-effort, same philosophy as the rest of this
# file: narrow the common cases, never crash, never worse than before.
_WRAPPER_VALUE_FLAGS = {
    "sudo": {"-u", "-g", "-p", "-r", "-h", "-C", "-U", "--user", "--group", "--prompt",
             "--role", "--type", "--close-from", "--host"},
    "env":  {"-u", "-C", "-S", "-P", "--unset", "--chdir", "--split-string"},
    "xargs": {"-I", "-L", "-l", "-n", "-P", "-s", "-a", "-E", "-d",
              "--delimiter", "--max-lines", "--max-args", "--max-procs", "--max-chars",
              "--arg-file", "--eof-str", "--replace"},
}


# --- predicates over a segment's argv tokens ---------------------------------------------
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


def _short_flags(t):
    """Union of clustered short flags, e.g. `-rf` -> {'r','f'} (long flags handled separately)."""
    out = set()
    for x in t:
        if x.startswith("-") and not x.startswith("--") and len(x) > 1:
            out.update(x[1:])
    return out


def _rm_rf(t):
    if not (t and t[0] == "rm"):
        return False
    sf, longs = _short_flags(t), set(t)
    rec = "r" in sf or "R" in sf or "--recursive" in longs
    force = "f" in sf or "--force" in longs
    return rec and force


_CATASTROPHIC = {"/", "/*", "~", "~/", "$HOME", "$HOME/", "*", ".", "./", "..", "../"}
_HOME_PREFIXES = ("~/", "$HOME/")


def _rm_targets(t):
    return [x for x in t[1:] if not x.startswith("-")]


def _home_subpath(x):
    """The part after `~/` or `$HOME/`, or None if x doesn't start with either."""
    for p in _HOME_PREFIXES:
        if x.startswith(p):
            return x[len(p):]
    return None


def _rm_catastrophic(t):
    if not _rm_rf(t):
        return False
    tg = _rm_targets(t)
    if not tg:                                               # `rm -rf` with targets from stdin/glob
        return False                                        # -> handled as "sensitive" (ask), not deny
    for x in tg:
        s = x.rstrip("/")
        if x in _CATASTROPHIC or s in ("", "/", "~", "$HOME", "*", ".", ".."):
            return True
        if x.startswith("/") and x.strip("/").count("/") == 0:   # a top-level system dir: /etc, /usr…
            return True
    return False


def _rm_sensitive(t):
    if not _rm_rf(t):
        return False
    tg = _rm_targets(t)
    if not tg:
        return True                                         # target-less recursive-force delete → ask
    for x in tg:
        s = x.rstrip("/")
        if s.startswith(".") or ".git" in x or ".orbit" in x or x.startswith("/") or x.startswith("$"):
            return True
        sub = _home_subpath(x)                               # ~/.ssh, ~/.aws, $HOME/.gnupg, …
        if sub is not None and (sub == "" or sub.startswith(".")):
            return True
    return False


def _reset_hard(t):
    return is_git(t) and "reset" in t and "--hard" in t


def _git_clean(t):
    return is_git(t) and "clean" in t and ("f" in _short_flags(t) or "--force" in t)


def _to_device(t):
    return any(re.match(r"of=/dev/(sd|nvme|disk|hd|mmcblk)", x) for x in t)


def _mkfs(t):
    return bool(t) and (t[0].startswith("mkfs") or t[0] in ("fdisk", "parted"))


def _ambiguous_git_force(t):
    # a git command with a force flag but no visible `push` subcommand, whose intent is hidden in
    # a shell variable — we can't confirm it's safe, so pause.
    return is_git(t) and ("--force" in t or "-f" in t) and "push" not in t and any("$" in x for x in t)


def _var_command(t):
    # the command's NAME is an unresolved shell variable ($X / ${X}) — un-inspectable → ask.
    return bool(t) and (t[0].startswith("$") or t[0].startswith("${"))


# --- RULES: (decision, reason, predicate). Ordered DENY-first; first match per segment wins. ---
# Customize for YOUR repo — e.g. deploys, frozen migrations, data deletes, secret-branch pushes:
#   ("deny", "the DB schema is frozen — no migrations.", lambda t: is_git(t) is False and "migrate" in t),
#   ("ask",  "deploys are a human checkpoint.",          lambda t: t[:1] == ["deploy"]),
RULES = [
    ("deny", "force-push rewrites shared history and is not allowed. Open a normal PR instead.",
     lambda t: _push(t) and _hard_force(t) and not _force_with_lease(t) and not _dry_run(t)),
    ("deny", "`git push --mirror` can force-overwrite and delete every remote ref — not allowed.",
     lambda t: _push(t) and "--mirror" in t and not _dry_run(t)),
    ("deny", "`rm -rf` on a root/home/system path is catastrophic and irreversible.",
     _rm_catastrophic),
    ("deny", "writing with `dd` to a raw disk device destroys the disk.",
     _to_device),
    ("deny", "`mkfs`/`fdisk`/`parted` reformats a disk — never run this from an agent loop.",
     _mkfs),
    ("ask",  "force-with-lease is a human-approval checkpoint here — confirm before pushing.",
     lambda t: _push(t) and _force_with_lease(t) and not _dry_run(t)),
    ("ask",  "deleting a remote branch (`push --delete` / `push :branch`) — confirm the target.",
     lambda t: _push(t) and not _dry_run(t)
        and ("--delete" in t or "-d" in t or any(x.startswith(":") and len(x) > 1 for x in t))),
    ("ask",  "git push is a human-approval checkpoint here — confirm before pushing.",
     lambda t: _push(t) and not _dry_run(t)),
    ("ask",  "merging into the default branch is a human-approval checkpoint.",
     lambda t: is_git(t) and t[1:2] == ["merge"]
        and any(b in t for b in ("master", "main", "origin/master", "origin/main"))),
    ("ask",  "`git reset --hard` discards uncommitted work irreversibly — confirm.",
     _reset_hard),
    ("ask",  "`git clean -f` deletes untracked/ignored files irreversibly — confirm.",
     _git_clean),
    ("ask",  "a recursive, forced `rm` of a hidden/absolute/.git/.orbit path is irreversible — confirm.",
     _rm_sensitive),
    ("ask",  "a git command with a force flag whose intent is hidden in a variable — confirm it's not a force-push.",
     _ambiguous_git_force),
    ("ask",  "this command's name is an unresolved shell variable — I can't verify what it runs; confirm it's safe.",
     _var_command),
]

_SEVERITY = {"deny": 2, "ask": 1}


def _max(a, b):
    if b is None:
        return a
    if a is None:
        return b
    return a if _SEVERITY[a[0]] >= _SEVERITY[b[0]] else b


def _strip_flags(t, value_flags):
    """Consume a run of dash-flags at the front of t. A flag in value_flags eats its value too —
    as a separate token (`-u root`), inline-short (`-I{}`), inline-long (`--user=root`), or as
    the LAST option in a bundled short cluster (`-Eu` = -E, then -u; getopt convention allows a
    value-taking short option only in the last position of a bundle, so its value is the next
    token). Anything else starting with `-` is assumed flag-only and dropped whole (best-effort —
    an unrecognized value-flag can still misparse, but that's strictly better than not trying)."""
    short_value_flags = {vf for vf in value_flags if not vf.startswith("--") and len(vf) == 2}
    while t and t[0].startswith("-"):
        tok = t[0]
        if tok in value_flags:                              # exact match: value is the NEXT token
            t = t[1:]
            if t:
                t = t[1:]
            continue
        if any(tok.startswith(vf + "=") for vf in value_flags if vf.startswith("--")):
            t = t[1:]                                        # --user=root (value inline)
            continue
        if any(tok.startswith(vf) and len(tok) > len(vf) for vf in value_flags if not vf.startswith("--")):
            t = t[1:]                                        # -I{} / -uroot (value inline)
            continue
        if re.match(r"^-[A-Za-z]{2,}$", tok) and f"-{tok[-1]}" in short_value_flags:
            t = t[1:]                                        # -Eu -> -E flag-only, -u takes a value
            if t:
                t = t[1:]
            continue
        t = t[1:]                                            # flag-only (known or not) — drop it
    return t


def _strip_wrappers(t):
    """Peel leading env-assignments, sudo/env/xargs/… wrappers (INCLUDING the wrapper's own
    flags, so `sudo -E`, `env -i`, `xargs -I{}` don't leave a flag sitting where the real
    command name belongs), and subshell/brace punctuation."""
    while t:
        tok = t[0]
        if tok in _GROUPS:                                  # ( … ) or { …; } group punctuation
            t = t[1:]
            continue
        if _ASSIGN.match(tok):                              # X=1 git …  (env-assignment prefix)
            t = t[1:]
            continue
        if tok == "env":
            t = t[1:]
            while t and _ASSIGN.match(t[0]) and not t[0].startswith("-"):
                t = t[1:]                                    # env FOO=1 BAR=2 cmd
            t = _strip_flags(t, _WRAPPER_VALUE_FLAGS["env"])  # env -i / -u NAME / -C dir …
            continue
        if tok in _WRAPPERS:
            t = t[1:]
            t = _strip_flags(t, _WRAPPER_VALUE_FLAGS.get(tok, set()))
            continue
        break
    return t


def _split_punct(tok):
    """Re-split a run of shell punctuation into individual operator/group tokens.
    shlex(punctuation_chars=True) returns a *run* of punctuation as ONE token, so ');' (a subshell
    close glued to a ';') would hide the ';' command-separator from segment-splitting — and
    `X=$(…); rm -rf /` would slip past the rules. Two-char operators and redirections (`&&`, `>&`,
    `&>`, …) are kept whole so `2>&1` isn't misread as a background `&`."""
    out, i, n = [], 0, len(tok)
    while i < n:
        if tok[i:i + 2] in _ATOMIC2:
            out.append(tok[i:i + 2])
            i += 2
        else:
            out.append(tok[i])
            i += 1
    return out


def _tokenize(line):
    """Tokenize one line, keeping shell operators (&&, ||, ;, |, &) as separate tokens. Compound
    punctuation runs (');', ')&&', …) are re-split so no separator hides behind a ')' or '('."""
    lex = shlex.shlex(line, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    out = []
    for tok in lex:
        if len(tok) > 1 and all(c in _PUNCT for c in tok):
            out.extend(_split_punct(tok))
        else:
            out.append(tok)
    return out


def _segments(cmd):
    """Split a command string into argv lists, one per shell segment (&&, ||, ;, |, & + newlines)."""
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


def _inner_commands(cmd):
    """Yield command strings hidden inside `( … )`, `$( … )`, `` `…` ``. Single-quoted regions are
    skipped (bash does no expansion there), so a quoted example isn't a false positive."""
    subs, i, n = [], 0, len(cmd)
    while i < n:
        c = cmd[i]
        if c == "'":                                        # skip single-quoted span (no expansion)
            j = cmd.find("'", i + 1)
            i = (j + 1) if j != -1 else n
            continue
        if c == "`":
            j = cmd.find("`", i + 1)
            if j != -1:
                subs.append(cmd[i + 1:j])
                i = j + 1
                continue
        if c == "(":                                        # ( subshell ), $( ), <( ), >( )
            depth, j = 1, i + 1
            while j < n and depth:
                if cmd[j] == "(":
                    depth += 1
                elif cmd[j] == ")":
                    depth -= 1
                j += 1
            subs.append(cmd[i + 1:j - 1])
            i = j
            continue
        i += 1
    return subs


def _shell_c_arg(t):
    """If argv is a shell invoked with -c/-lc/-xc …, return the command string it runs, else None."""
    if not t or t[0] not in _SHELLS:
        return None
    for i in range(1, len(t)):
        if t[i] == "-c" or _COMBINED_C.match(t[i]):
            return t[i + 1] if i + 1 < len(t) else None
    return None


def _resolve_map(segs):
    """Build {VAR: literal-value} for variables ASSIGNED with a static literal in THIS command, so
    a later `$VAR` command name can be resolved instead of just asked about. Common safe idiom:
        B=/path/to/tool; $B goto …   → resolve $B → /path/to/tool  (not dangerous → allow)
    But it also catches danger hidden the same way:
        RM="rm -rf"; $RM /           → resolve $RM → rm -rf         (→ deny)
    ONLY a FLAT literal value is recorded — a value with `$`/`` ` ``/`$(` (another var or a command
    substitution) OR with a shell control operator (`;`, `|`, `&`, `<`, `>`, `(`, `)`, newline) is
    un-resolvable and stays out of the map (that `$VAR` keeps its 'ask'). The operator check matters:
    without it, `X="foo; rm -rf /"; $X` would resolve to a *benign* command `foo` with the `rm`
    smuggled in as args — turning a fail-safe 'ask' into a silent allow. A var reassigned to a
    DIFFERENT literal is treated as ambiguous and dropped (fail toward asking)."""
    m, ambiguous = {}, set()
    for seg in segs:
        for tok in seg:
            mo = _ASSIGN_FULL.match(tok)
            if not mo:
                continue
            name, val = mo.group(1), mo.group(2)
            if "$" in val or "`" in val or any(c in _UNSAFE_VAL for c in val):
                ambiguous.add(name)               # not a flat literal command — can't safely resolve
                continue
            if name in m and m[name] != val:      # reassigned differently — ambiguous
                ambiguous.add(name)
            m[name] = val
    for name in ambiguous:
        m.pop(name, None)
    return m


def _var_name(tok):
    """The variable name in a `$VAR` / `${VAR}` command token, or None."""
    if tok.startswith("${") and tok.endswith("}"):
        return tok[2:-1] or None
    if tok.startswith("$") and len(tok) > 1:
        return tok[1:]
    return None


def evaluate(cmd, _depth=0):
    """Return the most severe (decision, reason) triggered by any segment, or None to allow."""
    if _depth > 6 or not cmd:
        return None
    cmd = cmd.replace("\\\n", "")                           # bash line-continuation joins with NO space
    best = None

    # 1. recurse into hidden sub-commands (subshells / substitutions / backticks)
    for inner in _inner_commands(cmd):
        best = _max(best, evaluate(inner, _depth + 1))

    segs = _segments(cmd)
    var_map = _resolve_map(segs)               # {VAR: literal} assigned in this same command

    # 2. cross-segment: a downloader piped straight into a shell = unreviewed remote code
    names = []
    for s in segs:
        st = _strip_wrappers(list(s))
        names.append(st[0] if st else "")
    if any(n in ("curl", "wget", "fetch") for n in names) and any(n in _SHELLS for n in names):
        best = _max(best, ("ask", "piping a downloaded script straight into a shell (curl|sh) runs "
                                  "unreviewed remote code — confirm the source."))

    # 3. per-segment argv rules (recursing into sh -c / eval)
    for seg in segs:
        t = _strip_wrappers(list(seg))
        if not t:
            continue
        # Resolve a `$VAR` command name from a same-command literal assignment, then RE-STRIP (the
        # value may itself begin with sudo/env/…). RM="rm -rf"; $RM /  →  [rm,-rf,/] → the RULES
        # see the real command. Un-resolvable vars stay `$VAR` → _var_command still asks.
        name = _var_name(t[0])
        if name and name in var_map:
            try:
                t = _strip_wrappers(shlex.split(var_map[name]) + t[1:])
            except Exception:
                pass
            if not t:
                continue
        sc = _shell_c_arg(t)
        if sc is not None:                                  # sh -c "…" / bash -lc "…"
            best = _max(best, evaluate(sc, _depth + 1))
            continue
        if t[0] == "eval":                                  # eval <string> → evaluate the string
            best = _max(best, evaluate(" ".join(t[1:]), _depth + 1))
            continue
        for decision, reason, pred in RULES:
            try:
                if pred(t):
                    best = _max(best, (decision, reason))
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
