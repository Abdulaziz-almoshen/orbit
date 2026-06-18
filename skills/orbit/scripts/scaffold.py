#!/usr/bin/env python3
"""
Scaffold the deterministic skeleton of the orbit system into a target repo.

This handles the mechanical, identical-every-time part: create the .orbit/ and
.claude/agents/ directories and drop in the static assets (loop.config.json, loop.py,
ralph_loop.sh). It deliberately does NOT write the bespoke, audit-driven files
(CLAUDE.md, STATE.md, role specs, skills) -- those are authored per-repo by the agent
running the skill, from the templates in references/.

Safety: never overwrites. If a target file exists, it is left untouched and reported, so
your existing CLAUDE.md / config is never clobbered.

Usage:
  python scaffold.py --target /path/to/repo      # default target: current directory
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
ASSETS = SKILL_ROOT / "assets"

# (source in assets, destination relative to target repo root, chmod)
FILE_PLAN = [
    ("loop.config.json", ".orbit/loop.config.json", None),
    ("loop.py",          ".orbit/loop.py",          0o755),
    ("ralph_loop.sh",    "scripts/ralph_loop.sh",     0o755),
    ("claude-agents/safety-gate.md", ".claude/agents/safety-gate.md", None),
]

DIRS = [
    ".orbit", ".orbit/roles", ".orbit/skills",
    ".orbit/artifacts", ".orbit/checks", ".claude/agents", "scripts",
]


def main():
    ap = argparse.ArgumentParser(description="Scaffold the orbit skeleton")
    ap.add_argument("--target", default=".", type=Path, help="target repo root")
    args = ap.parse_args()
    target = args.target.resolve()

    if not target.is_dir():
        raise SystemExit(f"target is not a directory: {target}")

    created, skipped = [], []

    for d in DIRS:
        (target / d).mkdir(parents=True, exist_ok=True)

    for src_rel, dst_rel, mode in FILE_PLAN:
        src = ASSETS / src_rel
        dst = target / dst_rel
        if not src.exists():
            skipped.append(f"{dst_rel}  (MISSING SOURCE {src_rel})")
            continue
        if dst.exists():
            skipped.append(f"{dst_rel}  (exists -- left untouched)")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        if mode:
            dst.chmod(mode)
        created.append(dst_rel)

    print("Scaffolded orbit skeleton into:", target)
    print("\nCreated:")
    for c in created or ["(nothing new)"]:
        print("  +", c)
    if skipped:
        print("\nSkipped (already present or missing source):")
        for s in skipped:
            print("  -", s)

    print(
        "\nNext (authored by hand, per the skill's references/):\n"
        "  * CLAUDE.md            -> references/claude-md-template.md\n"
        "  * .orbit/STATE.md    -> references/state-template.md\n"
        "  * .orbit/roles/*.md  -> references/roles.md (+ .claude/agents/*.md adapters)\n"
        "  * .orbit/skills/*.md -> the active profile in references/profiles/\n"
        "  * wire loop.py dispatch() to your orchestrator; fill loop.config.json thresholds"
    )


if __name__ == "__main__":
    main()
