#!/usr/bin/env bash
#
# install.sh — install Orbit as a Claude Code *user skill* (no restart needed).
#
# Claude Code watches ~/.claude/skills/ and discovers skills live, mid-session — so unlike a
# marketplace plugin (resolved only at startup), this install is usable the moment it finishes.
# This is the same mechanism gstack uses.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/Abdulaziz-almoshen/orbit/main/install.sh | bash
#   ./install.sh                      # from a local clone
#   ORBIT_BRANCH=dev ./install.sh     # install a specific branch
#
set -euo pipefail

SLUG="Abdulaziz-almoshen/orbit"
BRANCH="${ORBIT_BRANCH:-main}"
SKILLS_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills"

say() { printf '%s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# --- resolve the source tree: a local checkout, or download the tarball ---------------------
SRC=""
CLEANUP=""
_self_dir=""
case "${BASH_SOURCE[0]:-}" in
  ""|bash|sh) ;;                                   # piped (curl | bash): no script file on disk
  *) _self_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd -P || true)" ;;
esac

if [ -n "${ORBIT_SRC:-}" ] && [ -f "${ORBIT_SRC%/}/skills/orbit/SKILL.md" ]; then
  SRC="${ORBIT_SRC%/}"
elif [ -n "$_self_dir" ] && [ -f "$_self_dir/skills/orbit/SKILL.md" ]; then
  SRC="$_self_dir"                                 # running from a clone
else
  command -v curl >/dev/null 2>&1 || die "curl is required to download Orbit"
  command -v tar  >/dev/null 2>&1 || die "tar is required to download Orbit"
  TMP="$(mktemp -d)"; CLEANUP="$TMP"
  say "Downloading Orbit ($BRANCH)…"
  curl -fsSL "https://github.com/$SLUG/archive/refs/heads/$BRANCH.tar.gz" | tar -xz -C "$TMP" \
    || die "download failed (check the branch name / network)"
  SRC="$(find "$TMP" -maxdepth 1 -type d -name 'orbit-*' | head -1)"
  [ -n "$SRC" ] && [ -f "$SRC/skills/orbit/SKILL.md" ] || die "downloaded archive looks wrong"
fi

VER="$(tr -d '[:space:]' < "$SRC/VERSION" 2>/dev/null || echo unknown)"

# --- install into the user skills dir -------------------------------------------------------
mkdir -p "$SKILLS_DIR" || die "cannot create $SKILLS_DIR"

install_skill() {                                  # $1 = subdir under skills/
  local name="$1" dst="$SKILLS_DIR/$1"
  rm -rf "$dst"; mkdir -p "$dst"
  cp -R "$SRC/skills/$name/." "$dst/"
}
install_skill orbit
install_skill orbit-upgrade

# bin/, VERSION, CHANGELOG, commands live *inside* the orbit skill dir so the preamble and the
# update-checker (which resolve relative to bin/) find them. evals/ is dev-only — drop it.
mkdir -p "$SKILLS_DIR/orbit/bin"
cp -R "$SRC/bin/." "$SKILLS_DIR/orbit/bin/"
chmod +x "$SKILLS_DIR/orbit/bin/"* 2>/dev/null || true
cp "$SRC/VERSION" "$SKILLS_DIR/orbit/VERSION"
[ -f "$SRC/CHANGELOG.md" ] && cp "$SRC/CHANGELOG.md" "$SKILLS_DIR/orbit/CHANGELOG.md"
[ -d "$SRC/commands" ] && { mkdir -p "$SKILLS_DIR/orbit/commands"; cp -R "$SRC/commands/." "$SKILLS_DIR/orbit/commands/"; }
rm -rf "$SKILLS_DIR/orbit/evals" 2>/dev/null || true

# marker so /orbit-upgrade knows this is a skills-dir install and re-runs this installer
printf 'method=skills-dir\nslug=%s\nbranch=%s\n' "$SLUG" "$BRANCH" > "$SKILLS_DIR/orbit/.install-method"

[ -n "$CLEANUP" ] && rm -rf "$CLEANUP"

# --- report ---------------------------------------------------------------------------------
say ""
say "✅ Orbit v$VER installed as a user skill → $SKILLS_DIR/orbit"
say ""
say "   Run /orbit in any repo. No restart needed — Claude Code discovers skills live."
say "   Update later with /orbit-upgrade. Remove with: rm -rf \"$SKILLS_DIR/orbit\" \"$SKILLS_DIR/orbit-upgrade\""

# If a marketplace copy is also installed, the two /orbit skills can collide — flag it.
_pi="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/plugins/installed_plugins.json"
if [ -f "$_pi" ] && grep -q '"orbit@orbit"' "$_pi" 2>/dev/null; then
  say ""
  say "   NOTE: you also have the marketplace plugin installed. To avoid a duplicate /orbit,"
  say "   remove it: claude plugin uninstall orbit@orbit && claude plugin marketplace remove orbit"
fi
