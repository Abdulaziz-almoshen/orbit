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

### Step 1: auto-upgrade, or ask

```bash
STATE_DIR="${ORBIT_HOME:-$HOME/.orbit}"; mkdir -p "$STATE_DIR" 2>/dev/null || true
_auto=""
[ "${ORBIT_AUTO_UPGRADE:-}" = "1" ] && _auto="true"
[ -z "$_auto" ] && _auto="$(grep -E '^auto_upgrade=' "$STATE_DIR/config" 2>/dev/null | tail -1 | cut -d= -f2-)"
echo "AUTO_UPGRADE=$_auto"
```

**If `AUTO_UPGRADE=true`:** skip the question. Say "Auto-upgrading orbit v{old} → v{new}…" and go to Step 2.

**Otherwise**, ask with AskUserQuestion — "orbit **v{new}** is available (you're on v{old}). Upgrade now?" — four options:

- **Yes, upgrade now** → Step 2.
- **Always keep me up to date** → write `auto_upgrade=true` to `$STATE_DIR/config`, say "Auto-upgrade enabled.", then Step 2.
- **Not now** → write an escalating snooze (1st = 24h, 2nd = 48h, 3rd+ = 1 week) and continue the original skill without upgrading:
  ```bash
  _SNOOZE="$STATE_DIR/update-snoozed"; _REMOTE="{new}"; _LVL=0
  if [ -f "$_SNOOZE" ] && [ "$(awk '{print $1}' "$_SNOOZE")" = "$_REMOTE" ]; then
    _LVL="$(awk '{print $2}' "$_SNOOZE")"; case "$_LVL" in *[!0-9]*) _LVL=0 ;; esac
  fi
  _LVL=$(( _LVL + 1 )); [ "$_LVL" -gt 3 ] && _LVL=3
  echo "$_REMOTE $_LVL $(date +%s)" > "$_SNOOZE"
  ```
  Tell the user the next reminder window (24h / 48h / 1 week). Tip: set `auto_upgrade=true` in `$STATE_DIR/config` for hands-off upgrades.
- **Never ask again** → write `update_check=false` to `$STATE_DIR/config`; say it can be re-enabled by removing that line. Continue the original skill.

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
```

**Non-git install (`IS_GIT=no`, e.g. a plugin cache copy):** prefer the platform updater — tell the user to run `/plugin update orbit@orbit` (or `/plugin marketplace update orbit`), since Claude Code owns that cache. Do not git-clone over a managed cache.

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
orbit v{new} — upgraded from v{old}!

What's new:
- …

Then re-run /orbit if you want existing projects to pick up template improvements
(it merges; it won't clobber your scaffolded files).
```

### Step 6: continue

Resume whatever the user originally invoked. If this was triggered from the `/orbit`
preamble, go back into that workflow. The upgrade is done.

---

## Standalone usage (`/orbit-upgrade` invoked directly)

1. Force a fresh check (bypass the 24h throttle):
   ```bash
   for _p in "${CLAUDE_PLUGIN_ROOT:-}/bin/orbit-update-check" \
             "$HOME/.claude/skills/orbit/bin/orbit-update-check"; do
     [ -x "$_p" ] && { "$_p" --force; break; }
   done
   ```
2. If it prints `UPGRADE_AVAILABLE <old> <new>` → run Steps 0–6 above.
3. If it prints nothing → run Step 0 to find `INSTALL_DIR`, read `VERSION`, and tell the
   user "You're already on the latest version (v{version})."
