#!/usr/bin/env python3
"""
Scaffold the deterministic skeleton of the orbit system into a target repo.

This lays down the mechanical, identical-every-time part in ONE run — so /orbit setup is a
script (seconds), not the model authoring ~20 files by hand (minutes). It creates the dirs and
drops in: the engine files (loop.config.json, loop.py, activity.py, ralph_loop.sh, orbit-status,
guard.py), the reusable skill-library playbooks, the working-state file, and the full standard
sub-agent team (both the Claude Code adapters in .claude/agents/ and the model-agnostic specs in
.orbit/roles/).

It deliberately does NOT write the ONE genuinely bespoke file -- CLAUDE.md -- which the agent
authors per-repo from references/claude-md-template.md after characterizing the project. That's
the same split mature tools use (deterministic scaffold via CLI/templates; the LLM writes only
the project-specific spec).

Safety: never overwrites. If a target file exists it's left untouched and reported, so your
existing files are never clobbered.

Usage:
  python scaffold.py --target /path/to/repo      # default target: current directory
  python scaffold.py --frontend                  # also stand up the Designer + design playbooks
  python scaffold.py --install-hooks             # also wire the PreToolUse safety hook
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import time
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
ASSETS = SKILL_ROOT / "assets"
REFERENCES = SKILL_ROOT / "references"
PLAYBOOKS = REFERENCES / "playbooks"
AGENTS = ASSETS / "claude-agents"

# Engine files: (source in assets, destination relative to target repo root, chmod)
FILE_PLAN = [
    ("loop.config.json", ".orbit/loop.config.json", None),
    ("loop.py",          ".orbit/loop.py",          0o755),
    ("activity.py",      ".orbit/activity.py",      None),
    ("ralph_loop.sh",    "scripts/ralph_loop.sh",     0o755),
    ("orbit-status",     "scripts/orbit-status",      0o755),
    ("checks/guard.py",  ".orbit/checks/guard.py",    0o755),  # placed, NOT wired (see skill Phase 6a)
    ("checks/route.py",  ".orbit/checks/route.py",    0o755),  # the UserPromptSubmit router (Phase 6a)
]

# Reusable skill-library playbooks copied into .orbit/skills/ (the provisioning step).
PLAYBOOKS_ALWAYS = ["clarify-and-challenge.md", "planning-and-decision-briefs.md", "technical-review.md"]
PLAYBOOKS_FRONTEND = ["design-methodology.md", "anti-ai-aesthetics.md"]

# Standard sub-agent team. Each is copied verbatim to .claude/agents/<role>.md (the adapter) and,
# frontmatter-stripped, to .orbit/roles/<role>.md (the model-agnostic spec).
ROLES_ALWAYS = ["dispatcher", "orchestrator", "builder", "reviewer", "reporter", "safety-gate"]
ROLES_FRONTEND = ["designer"]

DIRS = [
    ".orbit", ".orbit/roles", ".orbit/skills",
    ".orbit/artifacts", ".orbit/checks", ".claude/agents", "scripts",
]

GUARD_CMD = 'python3 "$CLAUDE_PROJECT_DIR/.orbit/checks/guard.py"'
ROUTE_CMD = 'python3 "$CLAUDE_PROJECT_DIR/.orbit/checks/route.py"'


def _strip_frontmatter(text: str) -> str:
    """Remove a leading YAML frontmatter block (--- ... ---) for the portable role spec."""
    return re.sub(r"\A---\n.*?\n---\n+", "", text, count=1, flags=re.DOTALL)


def _place(src: Path, dst: Path, created, skipped, mode=None, transform=None):
    """Copy src→dst, never overwriting; optionally transform the text first."""
    rel = dst
    if not src.exists():
        skipped.append(f"{rel}  (MISSING SOURCE {src.name})")
        return
    if dst.exists():
        skipped.append(f"{rel}  (exists -- left untouched)")
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if transform:
        dst.write_text(transform(src.read_text()))
    else:
        shutil.copy2(src, dst)
    if mode:
        dst.chmod(mode)
    created.append(str(rel))


def install_hooks(target: Path) -> None:
    """Wire Orbit's two always-on hooks into .claude/settings.json (default-on + announced):

      • PreToolUse(Bash) → guard.py  — the binding safety wall (deny/ask on dangerous commands).
      • UserPromptSubmit → route.py  — the deterministic router: the SYSTEM classifies every message
        (task → loop, question → direct) and injects the decision, so Orbit controls the project.

    Backs up settings.json first, merges each hook idempotently (never double-adds), prints what it
    added + the one-line removal. Remove anytime with `orbit-uninstall`."""
    settings = target / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    backed_up = settings.exists()
    if backed_up:
        try:
            data = json.loads(settings.read_text())
        except Exception:
            data = {}
        settings.with_suffix(f".json.bak.{int(time.time())}").write_text(settings.read_text())

    hooks = data.setdefault("hooks", {})
    added = []

    pre = hooks.setdefault("PreToolUse", [])
    if not any("guard.py" in json.dumps(e) for e in pre):
        pre.append({"matcher": "Bash", "hooks": [{"type": "command", "command": GUARD_CMD}]})
        added.append("PreToolUse[matcher=Bash] → guard.py   (safety: deny/ask on dangerous commands)")

    ups = hooks.setdefault("UserPromptSubmit", [])
    if not any("route.py" in json.dumps(e) for e in ups):
        ups.append({"hooks": [{"type": "command", "command": ROUTE_CMD}]})
        added.append("UserPromptSubmit → route.py            (routing: classify task vs question)")

    if added:
        tmp = settings.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(settings)
        print("Installed Orbit's always-on hooks (announced, not silent):")
        for a in added:
            print("  + .claude/settings.json  →  hooks." + a)
        if backed_up:
            print("  (your previous settings.json was backed up alongside it)")
    else:
        print("Orbit hooks already wired in .claude/settings.json — left as-is.")
    print("  Remove anytime:  orbit-uninstall   (or delete those hook blocks)")


def main():
    ap = argparse.ArgumentParser(description="Scaffold the orbit skeleton")
    ap.add_argument("--target", default=".", type=Path, help="target repo root")
    ap.add_argument("--frontend", action="store_true",
                    help="also stand up the Designer role + design playbooks (frontend/UI repos)")
    ap.add_argument("--install-hooks", action="store_true",
                    help="also wire the always-on safety hook into .claude/settings.json")
    args = ap.parse_args()
    target = args.target.resolve()

    if not target.is_dir():
        raise SystemExit(f"target is not a directory: {target}")

    created, skipped = [], []

    for d in DIRS:
        (target / d).mkdir(parents=True, exist_ok=True)

    # 1. engine files
    for src_rel, dst_rel, mode in FILE_PLAN:
        _place(ASSETS / src_rel, target / dst_rel, created, skipped, mode)

    # 2. working-state file (from the reference template)
    _place(REFERENCES / "state-template.md", target / ".orbit/STATE.md", created, skipped)

    # 3. skill-library playbooks -> .orbit/skills/
    playbooks = PLAYBOOKS_ALWAYS + (PLAYBOOKS_FRONTEND if args.frontend else [])
    for pb in playbooks:
        _place(PLAYBOOKS / pb, target / ".orbit/skills" / pb, created, skipped)

    # 4. the standard team -> .claude/agents/ (adapter, verbatim) + .orbit/roles/ (spec, no frontmatter)
    roles = ROLES_ALWAYS + (ROLES_FRONTEND if args.frontend else [])
    for role in roles:
        src = AGENTS / f"{role}.md"
        _place(src, target / ".claude/agents" / f"{role}.md", created, skipped)
        _place(src, target / ".orbit/roles" / f"{role}.md", created, skipped, transform=_strip_frontmatter)

    print("Scaffolded orbit skeleton into:", target,
          "(frontend profile)" if args.frontend else "")
    print("\nCreated:")
    for c in created or ["(nothing new)"]:
        print("  +", c)
    if skipped:
        print("\nSkipped (already present or missing source):")
        for s in skipped:
            print("  -", s)

    print(
        "\nThe skeleton is down. The ONLY thing left to author by hand is the project-specific part:\n"
        "  * CLAUDE.md  -> from references/claude-md-template.md: fill the project name, what it is,\n"
        "                  §3 success criteria, §8 stop conditions, and §10 routing. (This is the one\n"
        "                  file the model writes — everything above was deterministic.)\n"
        "  * .orbit/skills/<domain>.md  -> the product's core domain how-to (one skill).\n"
        "  * tailor role NAMES/scope only if the domain needs it; the default team works as-is.\n"
        "  * wire loop.py dispatch() to your orchestrator; tune loop.config.json thresholds."
    )
    if args.install_hooks:
        print()
        install_hooks(target)
    else:
        print(
            "\nSafety guard: .orbit/checks/guard.py is PLACED but NOT wired (re-run with\n"
            "--install-hooks to wire it, or let the skill do it by default in Phase 6a)."
        )
    print(
        "\nTo undo everything later: run `orbit-uninstall` from this repo (lists, asks, then\n"
        "removes .orbit/, scripts/ralph_loop.sh, scripts/orbit-status, and any Orbit hooks;\n"
        "leaves your CLAUDE.md alone)."
    )


if __name__ == "__main__":
    main()
