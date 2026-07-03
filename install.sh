#!/usr/bin/env bash
#
# install.sh — curl-friendly wrapper around the gstack-style clone install.
#
#   curl -fsSL https://raw.githubusercontent.com/Abdulaziz-almoshen/orbit/main/install.sh | bash
#
# Equivalent to the canonical command:
#   git clone --single-branch --depth 1 https://github.com/Abdulaziz-almoshen/orbit.git \
#       ~/.claude/skills/orbit && cd ~/.claude/skills/orbit && ./setup
#
# It clones Orbit into ~/.claude/skills/orbit (the skill dir IS the git checkout, so updates are a
# fast `git pull` via /orbit-upgrade — no restart, Claude Code discovers it live). Re-runnable.
#
set -euo pipefail

SLUG="Abdulaziz-almoshen/orbit"
BRANCH="${ORBIT_BRANCH:-main}"
DEST="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills/orbit"
FORCE="${ORBIT_FORCE:-0}"
[ "${1:-}" = "--force" ] && FORCE=1

command -v git >/dev/null 2>&1 || { echo "ERROR: git is required" >&2; exit 1; }
mkdir -p "$(dirname "$DEST")"

if [ -d "$DEST/.git" ]; then
  echo "Orbit already installed at $DEST — updating to origin/$BRANCH…"
  # explicit refspec so switching ORBIT_BRANCH works even against a --single-branch clone
  git -C "$DEST" fetch --quiet origin "+refs/heads/$BRANCH:refs/remotes/origin/$BRANCH"
  git -C "$DEST" reset --hard "origin/$BRANCH"
elif [ -e "$DEST" ]; then
  # a non-git file/dir is squatting the destination — never rm -rf it silently
  if [ "$FORCE" = 1 ]; then
    echo "Removing existing (non-git) $DEST (--force)…"
    rm -rf "$DEST"
  elif [ -t 0 ]; then
    printf '%s already exists and is not an Orbit checkout. Delete it and install? [y/N] ' "$DEST"
    read -r ans
    case "$ans" in [yY]*) rm -rf "$DEST" ;; *) echo "Aborted."; exit 1 ;; esac
  else
    echo "ERROR: $DEST already exists and is not an Orbit checkout." >&2
    echo "       Re-run with --force (or ORBIT_FORCE=1) to overwrite it, or remove it yourself." >&2
    exit 1
  fi
  echo "Cloning Orbit → $DEST …"
  git clone --single-branch --depth 1 --branch "$BRANCH" "https://github.com/$SLUG.git" "$DEST"
else
  echo "Cloning Orbit → $DEST …"
  git clone --single-branch --depth 1 --branch "$BRANCH" "https://github.com/$SLUG.git" "$DEST"
fi

cd "$DEST" && ./setup
