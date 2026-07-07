#!/usr/bin/env python3
"""
orbit_lock_lib — the single-writer-lock core, shared by the trusted binaries `orbit-lock` (CLI) and
`orbit-lock-hook` (PreToolUse enforcement). Kept in ONE place so the CLI and the hook can never drift.

Model: a repo can have many READERS but only one WRITER at a time. "Writer" = one Claude Code session
(its `session_id`). Because Task-tool sub-agents share the parent's `session_id`, an orchestrator and
its whole sub-agent team count as the SAME writer (they never block each other); a genuinely separate
session — a second interactive window, or a headless `claude -p` loop — gets a different `session_id`
and is correctly treated as a foreign writer.

Lock file:  <repo>/.orbit/locks/active-writer.json   (written atomically: temp + os.replace)
Audit log:  <repo>/.orbit/locks/events.jsonl          (append-only: acquired/heartbeat/released/broke/blocked)
Dashboard:  <repo>/.orbit/activity.jsonl              (lock transitions mirrored into the live stream)

FAIL POLICY (two tiers, deliberately):
  • Hook/CLI INFRASTRUCTURE failure (unreadable payload, exception, missing files) → the CALLER fails
    OPEN (allow). A bug must never brick a repo — this mirrors Orbit's fail-open guard.
  • A successfully-READ lock that is foreign / stale / malformed, on a WRITE → deny, but ALWAYS with an
    `orbit-lock break --reason …` recovery line. Reads are never denied. This is the "protect the
    memory spine" behaviour, and it can't silently brick because the recovery path is always printed.
"""
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

LOCK_VERSION = 1
DEFAULT_TTL = 1800  # seconds; a lock with no heartbeat for this long is "stale" (recoverable via break)


# ─────────────────────────────── paths ───────────────────────────────
def locks_dir(target: Path) -> Path:
    return Path(target) / ".orbit" / "locks"


def lock_path(target: Path) -> Path:
    return locks_dir(target) / "active-writer.json"


def events_path(target: Path) -> Path:
    return locks_dir(target) / "events.jsonl"


def activity_path(target: Path) -> Path:
    return Path(target) / ".orbit" / "activity.jsonl"


# ─────────────────────────────── time ───────────────────────────────
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(s: str) -> datetime:
    return datetime.strptime((s or "").strip().replace("Z", ""), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)


# ─────────────────────────────── identity ───────────────────────────────
def resolve_identity(payload: dict = None) -> dict:
    """Who am I? Order (per spec): hook payload session_id → transcript hash → ORBIT_SESSION_ID →
    CLAUDE_SESSION_ID → TERM_SESSION_ID → fallback unknown:<cwd-hash>. Never PID-only (hooks are
    short-lived). The fallback can collide for two bare terminals in the same cwd with no TERM_SESSION_ID
    — acceptable: the enforcement path (hooks) always has a real session_id."""
    payload = payload or {}
    sid = (payload.get("session_id")
           or os.environ.get("ORBIT_SESSION_ID")
           or os.environ.get("CLAUDE_SESSION_ID")
           or os.environ.get("TERM_SESSION_ID"))
    tpath = payload.get("transcript_path") or ""
    tid = hashlib.sha256(tpath.encode()).hexdigest()[:16] if tpath else ""
    if not sid:
        cwd = payload.get("cwd") or os.getcwd()
        sid = "unknown:" + hashlib.sha256(cwd.encode()).hexdigest()[:12]
    kind = (payload.get("_owner_kind") or os.environ.get("ORBIT_OWNER_KIND") or "unknown")
    return {"owner_id": str(sid), "owner_kind": kind, "session_id": str(sid), "transcript_id": tid}


# ─────────────────────────────── lock io ───────────────────────────────
def read_lock(target: Path):
    """Return (state, data): state ∈ 'none' | 'ok' | 'malformed'. Never raises."""
    p = lock_path(target)
    if not p.exists():
        return ("none", None)
    try:
        data = json.loads(p.read_text())
        if not isinstance(data, dict) or "owner_id" not in data:
            return ("malformed", None)
        return ("ok", data)
    except Exception:
        return ("malformed", None)


def write_lock_atomic(target: Path, data: dict) -> None:
    p = lock_path(target)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, p)  # atomic on POSIX — a crash never leaves a half-written lock


def acquire_exclusive(target: Path, data: dict) -> bool:
    """Atomically create the lock ONLY if it does not exist (O_CREAT|O_EXCL). Returns True if WE got
    it, False if another session created it first — in which case the caller must re-read and re-decide.
    Closes the auto-acquire TOCTOU: two sessions that both saw 'no lock' can't both become the writer."""
    p = lock_path(target)
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(p), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        return False
    try:
        os.write(fd, (json.dumps(data, indent=2, sort_keys=True) + "\n").encode())
    finally:
        os.close(fd)
    return True


def remove_lock(target: Path) -> None:
    try:
        lock_path(target).unlink()
    except FileNotFoundError:
        pass


def is_stale(data: dict, now: datetime) -> bool:
    try:
        hb = _parse_iso(data.get("heartbeat_at") or data.get("started_at"))
        ttl = int(data.get("ttl_seconds") or DEFAULT_TTL)
        return (now - hb).total_seconds() > ttl
    except Exception:
        return True  # unparseable heartbeat within an otherwise-valid lock → treat as stale (recoverable)


def new_lock(target: Path, identity: dict, task: str, now: datetime) -> dict:
    return {
        "lock_version": LOCK_VERSION,
        "repo": str(Path(target).resolve()),
        "owner_kind": identity.get("owner_kind", "unknown"),
        "session_id": identity["session_id"],
        "owner_id": identity["owner_id"],
        "transcript_id": identity.get("transcript_id", ""),
        "task": task or "",
        "branch": _git(target, "rev-parse", "--abbrev-ref", "HEAD"),
        "git_head": _git(target, "rev-parse", "--short", "HEAD"),
        "started_at": iso(now),
        "heartbeat_at": iso(now),
        "ttl_seconds": DEFAULT_TTL,
    }


def _git(target: Path, *args) -> str:
    try:
        import subprocess
        r = subprocess.run(["git", "-C", str(target), *args], capture_output=True, text=True, timeout=3)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


# ─────────────────────────────── logging ───────────────────────────────
def _append_jsonl(p: Path, obj: dict) -> None:
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a") as f:
            f.write(json.dumps(obj) + "\n")
    except Exception:
        pass  # audit logging must never break enforcement


def log_event(target: Path, action: str, identity: dict, now: datetime, **extra) -> None:
    ev = {"ts": iso(now), "action": action, "owner_id": identity.get("owner_id"),
          "owner_kind": identity.get("owner_kind"), "session_id": identity.get("session_id")}
    ev.update(extra)
    _append_jsonl(events_path(target), ev)


def log_activity(target: Path, status: str, msg: str) -> None:
    _append_jsonl(activity_path(target),
                  {"who": "orbit-lock", "phase": "lock", "status": status, "msg": msg})


# ─────────────────────────────── write-intent classification ───────────────────────────────
WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
_WRITE_BIN = {"rm", "mv", "cp", "touch", "mkdir", "rmdir", "chmod", "chown", "ln", "dd", "truncate",
              "tee", "install", "unlink", "shred"}
_WRITE_GIT = {"add", "commit", "push", "merge", "rebase", "reset", "checkout", "switch", "pull",
              "stash", "cherry-pick", "revert", "tag", "am", "apply", "restore", "rm", "mv", "clean"}
_READ_GIT = {"status", "diff", "log", "show", "branch", "remote", "config", "blame", "rev-parse",
             "describe", "ls-files", "ls-tree", "shortlog", "reflog", "cat-file"}
_READ_BIN = {"ls", "pwd", "find", "wc", "head", "tail", "cat", "grep", "rg", "less", "more", "file",
             "stat", "du", "df", "which", "type", "env", "printenv", "date", "whoami", "echo", "true",
             "sed", "awk", "jq",  # read UNLESS writing in place (-i) — the _REDIR pass catches `sed -i`
             "pytest", "test", "jest", "vitest", "tox", "ruff", "mypy", "flake8", "eslint", "tsc"}
# A file-write redirect: `>`/`>>` (optionally fd-prefixed) followed by a filename — but NOT `>&`/`2>&1`
# (fd duplication, not a file write). Catches the no-space form `x>f` that a naive `\s>` misses.
_REDIR = re.compile(r">>?(?!&)\s*[\w./~$*-]|(?:^|\|)\s*tee\b|\bsed\b[^|;&]*\s-i\b|\bperl\b[^|;&]*\s-i\b")


def _bash_first_words(cmd: str):
    """Yield the leading command word of each top-level segment (best-effort; skips env-assign & sudo).
    Split on ; newline | && || — but NOT a bare `&`, or `2>&1` would be shredded into a phantom `1`."""
    for seg in re.split(r"\|\||&&|[;\n|]", cmd):
        toks = seg.strip().split()
        i = 0
        while i < len(toks) and ("=" in toks[i] and not toks[i].startswith("-")):  # FOO=bar prefix
            i += 1
        if i < len(toks) and toks[i] in ("sudo", "command", "env", "nohup", "time"):
            i += 1
            while i < len(toks) and toks[i].startswith("-"):
                i += 1
        if i < len(toks):
            rest = toks[i + 1:]
            yield toks[i], (rest[0] if rest else "")


def classify_bash(cmd: str) -> str:
    """→ 'write' | 'read' | 'unknown'. A coarse OPERATIONAL wall, honestly not a sandbox: arbitrary
    `python -c` / eval can still write, so unknown commands are treated conservatively by the caller
    (allowed with no lock, denied under a FOREIGN lock)."""
    cmd = cmd or ""
    if _REDIR.search(cmd):
        return "write"
    saw_unknown = False
    for head, sub in _bash_first_words(cmd):
        base = head.split("/")[-1]
        if base == "git":
            if sub in _WRITE_GIT:
                return "write"
            if sub in _READ_GIT:
                continue
            saw_unknown = True
        elif base in _WRITE_BIN:
            return "write"
        elif base in ("python", "python3", "manage.py") and ("migrate" in cmd or "makemigrations" in cmd or "flush" in cmd):
            return "write"
        elif base == "docker" and ("up" in cmd or "down" in cmd or "restart" in cmd):
            return "write"
        elif base in _READ_BIN:
            continue
        else:
            saw_unknown = True
    return "unknown" if saw_unknown else "read"


def classify_write_intent(tool_name: str, tool_input: dict) -> str:
    if tool_name in WRITE_TOOLS:
        return "write"
    if tool_name != "Bash":
        return "read"  # Read / Grep / Glob / WebFetch / … — never a write
    return classify_bash((tool_input or {}).get("command", "") or "")


def _touches_state(tool_name: str, tool_input: dict) -> bool:
    ti = tool_input or {}
    if tool_name in WRITE_TOOLS:
        fp = str(ti.get("file_path") or ti.get("notebook_path") or "")
        return fp.endswith("STATE.md") and (".orbit" in fp or "STATE.md" == os.path.basename(fp))
    if tool_name == "Bash":
        cmd = ti.get("command", "") or ""
        return "STATE.md" in cmd
    return False


# ─────────────────────────────── the decision ───────────────────────────────
def _break_line(cmd="orbit-lock break --reason '<why>'"):
    return f"recover explicitly with: {cmd}"


def evaluate(target: Path, tool_name: str, tool_input: dict, identity: dict, now: datetime) -> dict:
    """PURE decision (no writes): {decision: allow|deny, action: acquire|heartbeat|none, reason}.
    The hook performs `action` (acquire/heartbeat mutate the lock) and emits `decision`."""
    intent = classify_write_intent(tool_name, tool_input)
    if intent == "read":
        return {"decision": "allow", "action": "none", "reason": "read-only"}

    state, data = read_lock(target)

    if state == "none":
        if intent == "write":
            return {"decision": "allow", "action": "acquire", "reason": "no writer lock — auto-acquired"}
        return {"decision": "allow", "action": "none", "reason": "no lock; ambiguous command not acquiring"}

    if state == "malformed":
        # reads already returned above; a write against a corrupt lock fails CLOSED, but recoverably
        return {"decision": "deny", "action": "none",
                "reason": "the writer lock file is corrupt — " + _break_line("orbit-lock break --reason 'corrupt lock'")}

    # state == ok
    if data.get("owner_id") == identity["owner_id"]:
        return {"decision": "allow", "action": "heartbeat", "reason": "you hold the writer lock"}

    # a FOREIGN session holds it
    stale = is_stale(data, now)
    who = f"{data.get('owner_kind', '?')} session {str(data.get('session_id', '?'))[:8]}"
    if _touches_state(tool_name, tool_input):
        return {"decision": "deny", "action": "none",
                "reason": f".orbit/STATE.md is the memory spine and another writer ({who}) holds this repo — "
                          f"never written under a foreign lock. " + _break_line()}
    base = f"another session ({who}) holds the writer lock; this session is read-only"
    if stale:
        return {"decision": "deny", "action": "none",
                "reason": base + " (that lock is STALE) — " + _break_line("orbit-lock break --reason 'stale abandoned session'")}
    return {"decision": "deny", "action": "none", "reason": base + " until it releases — or " + _break_line()}
