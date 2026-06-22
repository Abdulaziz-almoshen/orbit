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

command -v git >/dev/null 2>&1 || { echo "ERROR: git is required" >&2; exit 1; }
mkdir -p "$(dirname "$DEST")"

if [ -d "$DEST/.git" ]; then
  echo "Orbit already installed at $DEST — updating (git pull)…"
  git -C "$DEST" fetch --quiet origin "$BRANCH"
  git -C "$DEST" reset --hard "origin/$BRANCH"
else
  [ -e "$DEST" ] && rm -rf "$DEST"
  echo "Cloning Orbit → $DEST …"
  git clone --single-branch --depth 1 --branch "$BRANCH" "https://github.com/$SLUG.git" "$DEST"
fi

cd "$DEST" && ./setup
