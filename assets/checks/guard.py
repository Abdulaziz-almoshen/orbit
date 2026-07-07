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
    wrapped force-push is still caught. Substitution detection is QUOTE-AWARE, matching bash: a bare
    `(` inside a quoted string is a literal character (a JS/SQL/regex argument like
    `browse js "(()=>{…})()"`), NOT a subshell — only `$( … )` and backticks expand inside `"…"`,
    and nothing expands inside `'…'`. This stops quoted code arguments from being misread as shell,
  • recognizes home-relative sensitive paths (`~/.ssh`, `$HOME/.aws`, …), not just absolute ones,
  • RESOLVES a `$VAR` command name when the variable was assigned a static literal in the SAME
    command (`B=/path/tool; $B goto …` → the real tool → allowed; `RM="rm -rf"; $RM /` → the real
    command → denied). This kills the common false positive (assign-a-path-then-reuse-it) AND
    catches danger hidden the same way — both used to only "ask",
  • FAILS CLOSED to "ask" when a command's identity is genuinely un-inspectable (its name is a
    variable with no resolvable literal assignment, or a downloader is piped straight into a shell).
THREAT MODEL, stated honestly: this catches an agent's *mistakes* — a genuinely dangerous command
generated in a normal, non-adversarial form — and asks/blocks on it. It is NOT a sandbox and does
NOT defend against a determined adversary deliberately obfuscating a payload to evade a static
parser: that is undecidable in general (short of *being* bash), so the hook FAILS OPEN by design
(a parse it can't resolve → allow, never brick the shell). THREE adversarial red-team passes hardened
it against 25 specific evasions and over-blocks — quote-aware substitution scanning, ANSI-C `$'…'`
(parser AND tokenizer), the bash-5.3 `${ cmd; }` funsub (incl. inside `"…"`), argument-position
variable resolution (all candidates, worst wins), quote/comment-aware heredoc detection (bodies are
inert stdin data; a quoted `<<X` is not a heredoc), word-boundary `#`-comment handling (so
`fix#42 && …` isn't truncated), `);`-tokenizer splits, a `dd`/redirect raw-device fail-safe — and it
no longer over-blocks common benign work (heredoc file-writes, comments, `./build` cleanups, quoted
code arguments). Residual gaps are exotic obfuscations outside the mistake threat model. Wrapper-flag
stripping is a KNOWN-flag list, not a full grammar; variable resolution covers same-command LITERAL
assignments only (a value from `$( … )`, another variable, or the environment stays un-resolvable and
keeps its "ask"); multi-level indirection, runtime aliases, and base64|sh remain out of scope.
Depth-in-defense, not a wall.

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
_VARREF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)")  # $VAR / ${VAR}
_ANSI_C = re.compile(r"\$'(?:\\.|[^'\\])*'")               # ANSI-C $'…' span (honors backslash escapes)
_DELIM = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.\-]*")       # a heredoc delimiter word (bash-ish)
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
        while s.startswith("./"):                            # `./build` is the cwd prefix, NOT a dotfile
            s = s[2:]
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


def _redirect_to_device(t):
    # shell output redirection onto a raw block device (`> /dev/sda`) destroys it exactly like
    # `dd of=…` — same blast radius, and the more common accidental form (image-flashing).
    for i, tok in enumerate(t):
        if tok in (">", ">>") and i + 1 < len(t) and re.match(r"/dev/(sd|nvme|disk|hd|mmcblk)", t[i + 1]):
            return True
        if re.match(r">>?/dev/(sd|nvme|disk|hd|mmcblk)", tok):   # glued `>/dev/sda`
            return True
    return False


def _mkfs(t):
    return bool(t) and (t[0].startswith("mkfs") or t[0] in ("fdisk", "parted"))


def _ambiguous_git_force(t):
    # a git command with a force flag but no visible `push` subcommand, whose intent is hidden in
    # a shell variable — we can't confirm it's safe, so pause.
    return is_git(t) and ("--force" in t or "-f" in t) and "push" not in t and any("$" in x for x in t)


def _ambiguous_dd(t):
    # a `dd` whose output target is an unresolved variable / substitution / `/dev/$VAR` — we can't
    # confirm it isn't a raw disk device, so pause (mirrors _ambiguous_git_force for dd).
    return bool(t) and t[0] == "dd" and any(a.startswith("of=") and "$" in a for a in t)


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
    ("deny", "redirecting output onto a raw disk device (`> /dev/sd…`) destroys the disk.",
     _redirect_to_device),
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
    ("ask",  "a `dd` whose output device is hidden in a variable/substitution — confirm it's not a raw disk.",
     _ambiguous_dd),
    ("ask",  "this command's name is an unresolved shell variable — I can't verify what it runs; confirm it's safe.",
     _var_command),
]

# Declarative project rules, layered on top of the built-in RULES by the TRUSTED runner (bin/orbit-guard)
# from a repo's .orbit/security/rules.json. Empty for the standalone project-local guard.py, so its
# behaviour is byte-identical. Project rules can only ADD caution (escalate via _max) — they can never
# downgrade a built-in deny or introduce an 'allow' (see compile_rules + _eval_argv).
EXTRA_RULES = []


def compile_rules(rules):
    """Compile DECLARATIVE project rules (pure data, never code) into (decision, reason, predicate)
    tuples. Honors only 'ask'/'deny' — a repo can add caution but can NOT weaken the built-in wall.
    Match keys (ANDed within a rule), tested against the fully-resolved argv `t`:
      • argv_contains: [str, …]  → every token must be present in the argv
      • argv_regex:   "…"        → regex search over the joined argv (input-capped; safe-compiled)
    Unknown/invalid rules are skipped; at most 200 rules are honored (a runaway-file backstop)."""
    out = []
    for r in (rules if isinstance(rules, list) else [])[:200]:
        try:
            if not isinstance(r, dict) or r.get("decision") not in ("ask", "deny"):
                continue
            decision = r["decision"]
            reason = str(r.get("reason") or "repo policy rule")[:300]   # cap a project-supplied string
            m = r.get("match") or {}
            conds = []
            contains = m.get("argv_contains")
            if isinstance(contains, list) and contains:
                need = [str(x) for x in contains]
                conds.append(lambda t, need=need: all(x in t for x in need))
            rx = m.get("argv_regex")
            if isinstance(rx, str) and rx:
                try:
                    cre = re.compile(rx)
                    conds.append(lambda t, cre=cre: bool(cre.search(" ".join(t)[:4096])))
                except re.error:
                    pass
            if not conds:
                continue
            out.append((decision, reason, lambda t, conds=conds: all(c(t) for c in conds)))
        except Exception:
            continue
    return out


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


def _strip_comment(line):
    """Remove a bash comment — from an unquoted `#` at a word boundary (start of line or after
    whitespace) to end of line. Quote-aware, so `fix#42`, `issue#7`, `'a#b'` keep their `#`. We do
    this ourselves because shlex's built-in `commenters='#'` strips `#` even mid-word, which dropped
    a chained `git commit -m fix#42 && git push --force` down to just `git commit -m fix`."""
    i, n = 0, len(line)
    while i < n:
        c = line[i]
        if c == "\\":
            i += 2
            continue
        if c == "'" or c == '"':
            i = _skip_quote(line, i)
            continue
        if c == "#" and (i == 0 or line[i - 1] in " \t"):
            return line[:i]
        i += 1
    return line


def _tokenize(line):
    """Tokenize one line, keeping shell operators (&&, ||, ;, |, &) as separate tokens. Compound
    punctuation runs (');', ')&&', …) are re-split so no separator hides behind a ')' or '('.
    ANSI-C `$'…'` spans are neutralized to `''` FIRST — raw shlex isn't ANSI-C aware and would raise
    on `$'\\''`, which used to make the whole line drop silently (a `$'\\''; rm -rf /` bypass).
    Comments are stripped word-boundary-aware (not shlex's mid-word `#`)."""
    line = _strip_comment(_ANSI_C.sub("''", line))
    lex = shlex.shlex(line, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    lex.commenters = ""                                    # we handle `#` ourselves (word-boundary)
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


def _skip_quote(cmd, i):
    """`cmd[i]` is a quote char. Return the index just past the matching close quote.
    A plain `'…'` is fully literal; a `$'…'` (ANSI-C) honors backslash escapes, so `\\'` does NOT
    close it; `"…"` honors a backslash escape. An UNTERMINATED quote returns i+1 — the quote char is
    treated as a literal and scanning continues. Never swallow to end-of-string: a stray apostrophe
    (in a heredoc body, a `#` comment, `don't`/`let's`) must NOT hide a real `$( … )` that follows."""
    n = len(cmd)
    if cmd[i] == "'":
        ansi_c = i > 0 and cmd[i - 1] == "$"                # $'…' → backslash escapes apply
        j = i + 1
        while j < n:
            if ansi_c and cmd[j] == "\\":
                j += 2
                continue
            if cmd[j] == "'":
                return j + 1
            j += 1
        return i + 1                                        # unterminated → treat the quote as literal
    j = i + 1                                               # double quote
    while j < n:
        if cmd[j] == "\\":
            j += 2
            continue
        if cmd[j] == '"':
            return j + 1
        j += 1
    return i + 1                                            # unterminated → treat the quote as literal


def _grab_balanced(cmd, start):
    """`start` is just past an opening `(`. Return (inner, end): the balanced content up to the
    matching `)`, and the index just past it. Quote-aware — a `(`/`)` inside a quoted span does NOT
    count toward depth (so `$(echo ")")` closes correctly)."""
    depth, j, n = 1, start, len(cmd)
    while j < n and depth:
        ch = cmd[j]
        if ch in "'\"":
            j = _skip_quote(cmd, j)
            continue
        if ch == "\\":
            j += 2
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        j += 1
    return cmd[start:j - 1], j


def _grab_brace(cmd, start):
    """`start` is just past an opening `{`. Return (inner, end): brace-balanced content up to the
    matching `}`, and the index just past it. Quote-aware."""
    depth, j, n = 1, start, len(cmd)
    while j < n and depth:
        ch = cmd[j]
        if ch in "'\"":
            j = _skip_quote(cmd, j)
            continue
        if ch == "\\":
            j += 2
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        j += 1
    return cmd[start:j - 1], j


def _inner_commands(cmd):
    """Yield command strings hidden in REAL shell substitutions/subshells — `$( … )`, backticks,
    *unquoted* `( … )` / `<( … )` / `>( … )`, and the bash-5.3 command funsub `${ cmd; }` / `${|cmd;}`.
    Quote-aware, matching bash's own rules:
      • inside single quotes NOTHING expands;
      • inside double quotes ONLY `$( … )` and backticks expand — a bare `(` there is a literal
        character (JS/SQL/regex/etc. passed as a string argument), NOT a subshell.
    This is what stops a quoted code argument like `browse js "(()=>{ … })()"` from being misread as
    shell and asked about, while still catching a real `"$(rm -rf /)"` hidden inside double quotes."""
    subs, i, n = [], 0, len(cmd)
    while i < n:
        c = cmd[i]
        if c == "\\":                                       # escaped char → literal
            i += 2
            continue
        if c == "#" and (i == 0 or cmd[i - 1] in " \t\n"):  # a `#` comment (word boundary) → EOL
            nl = cmd.find("\n", i)                          # bash doesn't expand $( … ) in a comment
            i = nl if nl != -1 else n
            continue
        if c == "$" and i + 2 < n and cmd[i + 1] == "{" and cmd[i + 2] in " \t\n|":
            inner, i = _grab_brace(cmd, i + 2)              # bash-5.3 funsub `${ cmd; }` / `${|cmd;}`
            subs.append(inner.lstrip("| \t\n").rstrip(" \t\n;"))
            continue
        if c == "'":                                        # single-quoted span → no expansion
            i = _skip_quote(cmd, i)
            continue
        if c == '"':                                        # double-quoted span → $( ), ` `, ${ funsub}
            i += 1
            while i < n and cmd[i] != '"':
                if cmd[i] == "\\":
                    i += 2
                    continue
                if cmd[i] == "$" and i + 2 < n and cmd[i + 1] == "{" and cmd[i + 2] in " \t\n|":
                    inner, i = _grab_brace(cmd, i + 2)      # funsub expands inside "…" too
                    subs.append(inner.lstrip("| \t\n").rstrip(" \t\n;"))
                    continue
                if cmd[i] == "$" and i + 1 < n and cmd[i + 1] == "(":
                    inner, i = _grab_balanced(cmd, i + 2)
                    subs.append(inner)
                    continue
                if cmd[i] == "`":
                    k = cmd.find("`", i + 1)
                    if k == -1:
                        i = n
                        break
                    subs.append(cmd[i + 1:k])
                    i = k + 1
                    continue
                i += 1
            i += 1                                          # step past the closing "
            continue
        if c == "`":                                        # unquoted backtick substitution
            k = cmd.find("`", i + 1)
            if k != -1:
                subs.append(cmd[i + 1:k])
                i = k + 1
                continue
            i += 1
            continue
        if c == "(":                                        # unquoted ( subshell ) / $( ) / <( ) / >( )
            inner, i = _grab_balanced(cmd, i + 1)
            subs.append(inner)
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
    """Build {VAR: [candidate literal values]} for variables ASSIGNED a static literal in THIS
    command, so a later `$VAR` — as the command NAME *or* as an ARGUMENT — is resolved instead of
    slipping past. Common safe idiom:
        B=/path/to/tool; $B goto …   → resolve $B → /path/to/tool  (not dangerous → allow)
    and the danger hidden the same way is caught in every position:
        RM="rm -rf"; $RM /           → $RM → rm -rf                 (→ deny)
        DEV=/dev/sda; dd … of=$DEV   → of=$DEV → of=/dev/sda        (→ deny)
        F=--force; git push $F       → $F → --force                (→ deny)
    ONLY FLAT literal values are recorded — a value with `$`/`` ` ``/`$(` (another var or a command
    substitution) OR a shell control operator (`;`, `|`, `&`, `<`, `>`, `(`, `)`, newline) makes the
    whole var un-resolvable (dropped): we must never resolve it to a partial/benign guess. The
    operator check stops `X="foo; rm -rf /"; $X` from resolving to a benign `foo` with the `rm`
    smuggled in as args. A var reassigned to DIFFERENT literals keeps ALL candidates — bash is
    last-write-wins but the guard can't know positions, so the evaluator tries every candidate and
    takes the WORST verdict (`RM=echo; RM="rm -rf"; $RM /` must still deny, not downgrade to ask)."""
    m, bad = {}, set()
    for seg in segs:
        for tok in seg:
            mo = _ASSIGN_FULL.match(tok)
            if not mo:
                continue
            name, val = mo.group(1), mo.group(2)
            if "$" in val or "`" in val or any(c in _UNSAFE_VAL for c in val):
                bad.add(name)                     # not a flat literal — the whole var is unresolvable
                continue
            m.setdefault(name, [])
            if val not in m[name]:
                m[name].append(val)
    for name in bad:
        m.pop(name, None)
    return m


def _var_name(tok):
    """The variable name if `tok` is exactly a `$VAR` / `${VAR}` reference, else None."""
    if tok.startswith("${") and tok.endswith("}"):
        return tok[2:-1] or None
    if tok.startswith("$") and len(tok) > 1 and tok[1:].isidentifier():
        return tok[1:]
    return None


def _sub_token(tok, choice):
    """Substitute `$VAR`/`${VAR}` in one token using {name: value}. A whole-token ref expands via
    shlex (so `--force` / `rm -rf` become real argv tokens); an embedded ref (e.g. `of=$DEV`) is
    string-spliced. Returns the list of resulting tokens."""
    nm = _var_name(tok)
    if nm is not None and nm in choice:
        try:
            parts = shlex.split(choice[nm])
        except Exception:
            parts = None
        return parts if parts else [choice[nm]]
    if "$" not in tok:
        return [tok]
    return [_VARREF.sub(lambda mo: choice.get(mo.group(1) or mo.group(2), mo.group(0)), tok)]


def _resolved_variants(t, var_map):
    """Candidate argv lists for a segment with its resolvable `$VAR`s substituted. Single-value vars
    are always substituted; a multi-value var yields one variant per candidate so `evaluate` can take
    the WORST. Bounded to a handful of variants. A segment with no resolvable var → itself, unchanged
    (so a genuinely un-inspectable `$X` command name still reaches the `_var_command` 'ask')."""
    refs = []
    for tok in t:
        for mo in _VARREF.finditer(tok):
            nm = mo.group(1) or mo.group(2)
            if nm in var_map and nm not in refs:
                refs.append(nm)
    if not refs:
        return [t]
    base = {nm: var_map[nm][0] for nm in refs}

    def build(choice):
        out = []
        for tok in t:
            out.extend(_sub_token(tok, choice))
        return out

    variants = [build(base)]
    for nm in refs:
        for v in var_map[nm][1:]:
            ch = dict(base)
            ch[nm] = v
            variants.append(build(ch))
    return variants[:12]


def _heredoc_delims(line):
    """Heredoc introducers on a line, QUOTE- and COMMENT-aware → [(name, unquoted, dash)]. A `<<`
    inside quotes or after an unquoted `#` is NOT a heredoc (so `grep '<<X'`, `echo "a<<Y"`, and
    `ls # <<Z` are not misread — that misread swallowed the *next* real command as fake body). Only a
    genuine, confidently-detected heredoc strips a body: a false negative is a safe over-ask, a false
    positive is an unsafe bypass, so this leans conservative."""
    out, i, n = [], 0, len(line)
    while i < n:
        c = line[i]
        if c == "\\":
            i += 2
            continue
        if c == "'" or c == '"':
            i = _skip_quote(line, i)
            continue
        if c == "#" and (i == 0 or line[i - 1] in " \t"):
            break                                           # comment to EOL — no heredoc past here
        if line[i:i + 2] == "<<" and line[i:i + 3] != "<<<":
            j = i + 2
            dash = j < n and line[j] == "-"
            if dash:
                j += 1
            while j < n and line[j] in " \t":
                j += 1
            q = ""
            if j < n and line[j] in "'\"\\":
                q = line[j]
                j += 1
            mo = _DELIM.match(line, j)
            if mo:
                out.append((mo.group(0), q == "", dash))
                j = mo.end()
                if q in ("'", '"') and j < n and line[j] == q:
                    j += 1
            i = j
            continue
        i += 1
    return out


def _split_heredocs(cmd):
    """Split heredocs out of a command → (code, unquoted_bodies):
      • `code` is the command with every heredoc BODY and its closing delimiter removed. Body lines
        are stdin DATA, never commands — `_segments` must not tokenize them as argv, or a benign
        `cat <<'EOF' … rm -rf / … EOF` file-write gets wrongly blocked.
      • `unquoted_bodies` collects only the bodies whose delimiter was UNQUOTED (`<<EOF`, not
        `<<'EOF'` / `<<\\EOF`): there bash DOES run `$( … )`/backticks at setup, so they still need
        substitution-scanning (a real `<<EOF … $(rm -rf /) … EOF` must still be caught).
    The closing delimiter must match EXACTLY (for `<<-`, only leading TABS are stripped) — bash does
    not accept a trailing-space `EOF `. No heredoc → (cmd, "")."""
    if "<<" not in cmd:
        return cmd, ""
    lines = cmd.split("\n")
    code, bodies, i = [], [], 0
    while i < len(lines):
        code.append(lines[i])
        delims = _heredoc_delims(lines[i])
        i += 1
        for name, unquoted, dash in delims:
            body = []
            while i < len(lines):
                probe = lines[i].lstrip("\t") if dash else lines[i]
                if probe == name:
                    break
                body.append(lines[i])
                i += 1
            if i < len(lines):                             # consume the exact closing delimiter line
                i += 1
            if unquoted:
                bodies.append("\n".join(body))
    return "\n".join(code), "\n".join(bodies)


def evaluate(cmd, _depth=0):
    """Return the most severe (decision, reason) triggered by any segment, or None to allow."""
    if _depth > 6 or not cmd:
        return None
    cmd = cmd.replace("\\\n", "")                           # bash line-continuation joins with NO space
    best = None
    code, hbodies = _split_heredocs(cmd)                    # heredoc bodies are stdin data, not argv

    # 1. recurse into hidden sub-commands (subshells / substitutions / backticks) in the code, PLUS
    #    unquoted-heredoc bodies (where `$( … )`/backticks run at setup); quoted bodies are inert.
    for inner in _inner_commands(code):
        best = _max(best, evaluate(inner, _depth + 1))
    for inner in _inner_commands(hbodies):
        best = _max(best, evaluate(inner, _depth + 1))

    segs = _segments(code)                                  # NOT the heredoc body lines
    var_map = _resolve_map(segs)               # {VAR: [candidates]} assigned in this same command

    # 2. cross-segment: a downloader piped straight into a shell = unreviewed remote code. Resolve a
    #    `$VAR` command name first, so `C=curl; $C … | sh` and `curl … | $S`(S=sh) don't hide it.
    def _first_names(s):
        st = _strip_wrappers(list(s))
        if not st:
            return [""]
        nm = _var_name(st[0])
        if nm and nm in var_map:
            outs = []
            for v in var_map[nm]:
                try:
                    outs.append((shlex.split(v) or [v])[0])
                except Exception:
                    outs.append(v)
            return outs or [st[0]]
        return [st[0]]
    name_sets = [_first_names(s) for s in segs]
    has_dl = any(any(n in ("curl", "wget", "fetch") for n in ns) for ns in name_sets)
    has_sh = any(any(n in _SHELLS for n in ns) for ns in name_sets)
    if has_dl and has_sh:
        best = _max(best, ("ask", "piping a downloaded script straight into a shell (curl|sh) runs "
                                  "unreviewed remote code — confirm the source."))

    # 3. per-segment argv rules, WITH same-command variable resolution in the command-name AND
    #    argument positions. A multi-valued var is tried in every candidate; we keep the worst.
    #    An un-resolvable `$VAR` passes through unchanged → the `_var_command` rule still asks.
    for seg in segs:
        base = _strip_wrappers(list(seg))
        if not base:
            continue
        for variant in _resolved_variants(base, var_map):
            t = _strip_wrappers(variant)               # a value may itself begin with sudo/env/…
            best = _max(best, _eval_argv(t, _depth))
    return best


def _eval_argv(t, depth):
    """The verdict for ONE fully-resolved argv — recursing into `sh -c "…"` / `eval …`, else running
    the RULES. Returns (decision, reason) or None."""
    if not t:
        return None
    sc = _shell_c_arg(t)
    if sc is not None:                                      # sh -c "…" / bash -lc "…"
        return evaluate(sc, depth + 1)
    if t[0] == "eval":                                     # eval <string> → evaluate the string
        return evaluate(" ".join(t[1:]), depth + 1)
    best = None
    for decision, reason, pred in RULES:                   # built-in wall: deny-first ordered → first match wins
        try:
            if pred(t):
                best = (decision, reason)
                break
        except Exception:
            continue
    for decision, reason, pred in EXTRA_RULES:             # declarative project rules: escalate-only via _max
        try:
            if pred(t):
                best = _max(best, (decision, reason))       # a repo can raise ask→deny, never lower a built-in deny
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
