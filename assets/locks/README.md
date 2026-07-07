# `.orbit/locks/` — the single-writer lock

A repo can have **many readers but only one writer at a time**. This directory holds that lock.

- **`active-writer.json`** — the live lock (absent = no active writer). Written atomically.
- **`events.jsonl`** — append-only audit trail: `acquired` / `heartbeat` / `released` / `broke` / `blocked`.
- Lock transitions are also mirrored into `.orbit/activity.jsonl` so the live dashboard shows them.

## Who is a "writer"?

One **Claude Code session** (`session_id`). Task-tool **sub-agents share the parent's `session_id`**, so
an orchestrator and its whole team count as the *same* writer and never block each other. A genuinely
separate session — a second interactive window, or a headless `claude -p` loop — gets a *different*
`session_id` and is correctly treated as a **foreign writer** (serialized behind the lock).

## `active-writer.json` schema

```json
{
  "lock_version": 1,
  "repo": "/abs/path/to/repo",
  "owner_kind": "interactive|background|agent|unknown",
  "session_id": "stable-session-id",
  "owner_id": "stable-session-id",
  "transcript_id": "sha256(transcript_path)[:16]",
  "task": "F1-S4 housing report",
  "branch": "master",
  "git_head": "ae08fdc",
  "started_at": "2026-07-07T10:15:00Z",
  "heartbeat_at": "2026-07-07T10:19:20Z",
  "ttl_seconds": 1800
}
```

A lock with no `heartbeat_at` within `ttl_seconds` is **stale** (recoverable). Because the enforcement
hook refreshes the heartbeat on every write by the owning session, a live session's lock never goes
stale; an abandoned one does after ~30 min.

## Enforcement (automatic)

`orbit-lock-hook` runs as a `PreToolUse` hook for `Edit` / `Write` / `MultiEdit` / `Bash`:

| Situation | Decision |
|---|---|
| read-only tool / command | allow |
| write + no lock | auto-acquire, allow |
| write + you own the lock | heartbeat, allow |
| write + a **foreign** session owns it | **deny** (with a `break` recovery line) |
| write to `.orbit/STATE.md` under a foreign lock | **deny** (always — the memory spine) |
| corrupt lock file + write | **deny** (fail closed for writes; reads stay open) |

The hook **fails open** on any infrastructure error (a bug never bricks the repo), and can be disabled
entirely with `ORBIT_LOCK_DISABLE=1`.

## Recovering a stuck/stale lock (manual, logged)

```bash
scripts/orbit-lock status                                   # who owns it, and is it stale?
scripts/orbit-lock break --reason "stale abandoned session" # clear it — reason is required and audited
```

Breaking a lock is a deliberate operator act: it requires `--reason` and is appended to `events.jsonl`.
