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
import json
import shutil
import time
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
ASSETS = SKILL_ROOT / "assets"

# (source in assets, destination relative to target repo root, chmod)
FILE_PLAN = [
    ("loop.config.json", ".orbit/loop.config.json", None),
    ("loop.py",          ".orbit/loop.py",          0o755),
    ("activity.py",      ".orbit/activity.py",      None),
    ("ralph_loop.sh",    "scripts/ralph_loop.sh",     0o755),
    ("orbit-status",     "scripts/orbit-status",      0o755),
    ("checks/guard.py",  ".orbit/checks/guard.py",    0o755),  # placed, NOT wired (see skill Phase 6a)
    ("claude-agents/safety-gate.md", ".claude/agents/safety-gate.md", None),
]

DIRS = [
    ".orbit", ".orbit/roles", ".orbit/skills",
    ".orbit/artifacts", ".orbit/checks", ".claude/agents", "scripts",
]


HOOK_CMD = 'python3 "$CLAUDE_PROJECT_DIR/.orbit/checks/guard.py"'


def install_hooks(target: Path) -> None:
    """Wire .orbit/checks/guard.py as a PreToolUse(Bash) hook in .claude/settings.json.

    Default-on + announced (skill Phase 6a): backs up settings.json first, merges the hook
    idempotently (never double-adds), prints the exact JSON + the one-line removal. The hook
    is the only layer that actually binds; this makes Orbit's safety real out of the box.
    Remove anytime with `orbit-uninstall`."""
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
    pre = hooks.setdefault("PreToolUse", [])
    # idempotent: skip if an orbit guard hook is already wired
    already = any(".orbit/" in json.dumps(e) for e in pre)
    entry = {"matcher": "Bash", "hooks": [{"type": "command", "command": HOOK_CMD}]}
    if not already:
        pre.append(entry)
        tmp = settings.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(settings)
        print("Installed always-on safety hook (announced, not silent):")
        print("  + .claude/settings.json  →  hooks.PreToolUse[matcher=Bash]:")
        print("      " + json.dumps(entry))
        if backed_up:
            print("  (your previous settings.json was backed up alongside it)")
    else:
        print("Safety hook already wired in .claude/settings.json — left as-is.")
    print("  Remove anytime:  orbit-uninstall   (or delete that hook block)")


def main():
    ap = argparse.ArgumentParser(description="Scaffold the orbit skeleton")
    ap.add_argument("--target", default=".", type=Path, help="target repo root")
    ap.add_argument("--install-hooks", action="store_true",
                    help="also wire the always-on safety hook into .claude/settings.json")
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
    if args.install_hooks:
        print()
        install_hooks(target)
    else:
        print(
            "\nSafety guard: .orbit/checks/guard.py is PLACED but NOT wired (re-run with\n"
            "--install-hooks to wire it, or let the skill do it by default in Phase 6a).\n"
            "It does nothing until it's registered as a PreToolUse hook in .claude/settings.json."
        )
    print(
        "\nTo undo everything later: run `orbit-uninstall` from this repo (lists, asks, then\n"
        "removes .orbit/, scripts/ralph_loop.sh, scripts/orbit-status, and any Orbit hooks;\n"
        "leaves your CLAUDE.md alone)."
    )


if __name__ == "__main__":
    main()
