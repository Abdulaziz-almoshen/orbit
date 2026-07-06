---
name: orbit-upgrade
description: >-
  Upgrade the installed orbit plugin to the latest version from GitHub and show
  what changed. Use when the user says "upgrade orbit", "update agentic loop",
  "get the latest orbit", or when the /orbit preamble reports
  UPGRADE_AVAILABLE. Speech-to-text aliases: "update agent loop", "upgrade the agent loop".
allowed-tools:
  - Bash
  - Read
  - Write
  - AskUserQuestion
---

# /orbit-upgrade

Upgrade the orbit plugin and show what's new. This updates the **plugin/scaffolder**
only — it never touches the `CLAUDE.md`, roles, or loop files a previous run already
scaffolded into a product repo (those are that project's files).

## Inline upgrade flow

This section is referenced by the `/orbit` preamble when it detects
`UPGRADE_AVAILABLE <old> <new>`. Run the steps in order.

### Step 0: locate the install

```bash
# Resolve the plugin root (holds VERSION, bin/, CHANGELOG.md, skills/).
CANDIDATES="
${CLAUDE_PLUGIN_ROOT:-}
$HOME/.claude/plugins/cache/orbit/orbit
$HOME/.claude/skills/orbit
.claude/skills/orbit
"
INSTALL_DIR=""
for _c in $CANDIDATES; do
  [ -n "$_c" ] && [ -f "$_c/VERSION" ] && { INSTALL_DIR="$(cd "$_c" && pwd -P)"; break; }
done
# Fallback: search the plugin cache for our VERSION-bearing root.
if [ -z "$INSTALL_DIR" ]; then
  INSTALL_DIR="$(find "$HOME/.claude/plugins/cache" -maxdepth 3 -type f -name VERSION 2>/dev/null \
    | while read -r v; do d="$(dirname "$v")"; [ -d "$d/skills/orbit" ] && echo "$d" && break; done)"
fi
[ -z "$INSTALL_DIR" ] && { echo "ERROR: orbit install not found"; exit 1; }
echo "INSTALL_DIR=$INSTALL_DIR"
echo "IS_GIT=$([ -d "$INSTALL_DIR/.git" ] && echo yes || echo no)"
```

### Step 1: ask once, then honor the choice (consent-once, opt-out default)

The posture is **auto-upgrade recommended**, but a user should get **one** say in it — not silent
auto-updates forever, and not a prompt on every release. So: the **first** time an upgrade is offered
and `auto_upgrade` is unset, **ask once**; persist the answer; honor it silently ever after.

```bash
STATE_DIR="${ORBIT_HOME:-$HOME/.orbit}"; mkdir -p "$STATE_DIR" 2>/dev/null || true
_auto="$(grep -E '^auto_upgrade=' "$STATE_DIR/config" 2>/dev/null | tail -1 | cut -d= -f2-)"
[ "${ORBIT_AUTO_UPGRADE:-}" = "1" ] && _auto="true"
[ "${ORBIT_AUTO_UPGRADE:-}" = "0" ] && _auto="false"
echo "AUTO_UPGRADE=${_auto:-unset}"
```

**If `AUTO_UPGRADE=unset` (first upgrade, no choice recorded yet):** ask **once** with the
`AskUserQuestion` tool — *"Keep Orbit auto-updated?"* with the **Recommended** option first:
- **Yes, auto-update (Recommended)** — stay current hands-off; each upgrade is announced, never silent.
- **No, ask me each time** — I'll tell you when a version is available and wait for `/orbit-upgrade`.

Then **persist the choice** with `_set auto_upgrade true|false` (below) and proceed by the matching
branch. This is the *only* time you ask; every later upgrade honors the saved value silently.

**If `AUTO_UPGRADE=true`:** skip the question. Say "⬆️ Auto-upgrading orbit v{old} → v{new}…" and go
to Step 2. (Announced + shows what's new in Step 5 — auto, never silent. Opt out anytime with
`auto_upgrade=false`.)

**If `AUTO_UPGRADE=false` (opted out):** don't upgrade and don't nag — just one line: "orbit
**v{new}** is available (you're on v{old}). Run `/orbit-upgrade` when you want it." Then continue
the original skill.

To write a config key (create the file if missing):
```bash
_set() { mkdir -p "$STATE_DIR"; touch "$STATE_DIR/config"; grep -v -E "^$1=" "$STATE_DIR/config" > "$STATE_DIR/config.tmp" 2>/dev/null || true; echo "$1=$2" >> "$STATE_DIR/config.tmp"; mv "$STATE_DIR/config.tmp" "$STATE_DIR/config"; }
# usage: _set auto_upgrade true   |   _set update_check false
```

### Step 2: save the old version

```bash
OLD_VERSION="$(tr -d '[:space:]' < "$INSTALL_DIR/VERSION" 2>/dev/null || echo unknown)"
echo "OLD_VERSION=$OLD_VERSION"
```

### Step 3: upgrade

**Git install (`IS_GIT=yes`) — the normal case:**
```bash
cd "$INSTALL_DIR"
_STASH="$(git stash 2>&1)"
git fetch origin
_BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)"
git reset --hard "origin/$_BRANCH"
echo "$_STASH" | grep -q "Saved working directory" && echo "NOTE: local changes were stashed — run 'git stash pop' in $INSTALL_DIR to restore."
_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
echo "Now at commit $_SHA on $_BRANCH — this is a floating-branch install, not a signed release;
this is the checkable record of exactly what code is now running."
```

**Skills-dir install (`IS_GIT=no` and `$INSTALL_DIR/.install-method` says `method=skills-dir`, or `$INSTALL_DIR` is under `~/.claude/skills/`) — the default install:** re-run the installer, which re-downloads the latest and overwrites in place (no restart needed):
```bash
_BR="$(grep -E '^branch=' "$INSTALL_DIR/.install-method" 2>/dev/null | cut -d= -f2-)"; _BR="${_BR:-main}"
ORBIT_BRANCH="$_BR" bash -c 'curl -fsSL "https://raw.githubusercontent.com/Abdulaziz-almoshen/orbit/'"$_BR"'/install.sh" | bash'
```

**Plugin-cache install (`IS_GIT=no` and `$INSTALL_DIR` is under `~/.claude/plugins/`):** prefer the platform updater — tell the user to run `/plugin update orbit@orbit` (or `/plugin marketplace update orbit`), since Claude Code owns that cache. Do not git-clone over a managed cache.

### Step 4: mark + clear caches

```bash
echo "$OLD_VERSION" > "$STATE_DIR/just-upgraded-from"
rm -f "$STATE_DIR/last-update-check" "$STATE_DIR/update-snoozed" 2>/dev/null || true
NEW_VERSION="$(tr -d '[:space:]' < "$INSTALL_DIR/VERSION" 2>/dev/null || echo unknown)"
echo "Upgraded $OLD_VERSION -> $NEW_VERSION"
```

### Step 5: show what's new

Read `$INSTALL_DIR/CHANGELOG.md`. Summarize the entries between `OLD_VERSION` and the new
version as 3–6 user-facing bullets (skip internal refactors). Format:

```
orbit v{new} — upgraded from v{old}! (commit {sha})

What's new:
- …

⚠️ This upgraded the PLUGIN only — your already-scaffolded projects still run their OLD local
scaffold (that's a separate freshness). To see if a project is behind, run
`scripts/scaffold.py --check-drift --target <repo>`; to refresh it, re-run /orbit inside it
(it adds missing files/hooks + re-stamps the version, and hash-gates — never clobbers — a
customized guard.py).
```

Include `{sha}` (from Step 3's `$_SHA`, when the install is a git checkout) — it's the concrete,
checkable record of what's now running, since this is a floating-branch install, not a signed
release.

### Step 6: continue

Resume whatever the user originally invoked. If this was triggered from the `/orbit`
preamble, go back into that workflow. The upgrade is done.

---

## Standalone usage (`/orbit-upgrade` invoked directly)

1. Force a fresh check (bypass the 24h throttle):
   ```bash
   for _p in "${CLAUDE_PLUGIN_ROOT:-}/bin/orbit-update-check" \
             "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills/orbit/bin/orbit-update-check" \
             "$HOME/.claude/skills/orbit/bin/orbit-update-check"; do
     [ -x "$_p" ] && { "$_p" --force; break; }
   done
   ```
2. If it prints `UPGRADE_AVAILABLE <old> <new>` → run Steps 0–6 above.
3. If it prints nothing → run Step 0 to find `INSTALL_DIR`, read `VERSION`, and tell the
   user "You're already on the latest version (v{version})."
