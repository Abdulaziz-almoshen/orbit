#!/usr/bin/env python3
"""
verify-hooks.py — detect drift between a product repo's installed .orbit/checks/*.py hooks and
what THIS Orbit install currently ships.

Why this exists: Orbit's hooks (guard.py, route.py, learn.py, design-gate.py) are wired into
.claude/settings.json as `$CLAUDE_PROJECT_DIR/.orbit/checks/<name>.py` — i.e. they live INSIDE
the product repo, tracked like any other file. That means anyone with commit access to that repo
(a teammate, a merged PR) can modify the safety guard itself, and Claude Code will silently run
the modified version next time. This is not unique to Orbit — it's inherent to Claude Code's
project-local hook model — but Orbit should give you a way to NOTICE it, not just hope.

This is a DETECTION tool, not a prevention mechanism. It does not stop a hostile change from
being merged; it tells you, after the fact, that an installed hook no longer matches what Orbit
itself currently ships — which could be a deliberate customization (see the RULES comment block
in guard.py) or could be tampering. Either way, you should look at the diff before trusting it.

Usage:
  python3 scripts/verify-hooks.py --target /path/to/product-repo

Exit codes: 0 = every present hook matches; 1 = at least one hook differs (review the diff).
Never crashes on a missing/unreadable file — reports it and continues.
"""
import argparse
import hashlib
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
ASSETS_CHECKS = SKILL_ROOT / "assets" / "checks"

HOOK_FILES = ["guard.py", "route.py", "learn.py", "design-gate.py"]


def _sha(path: Path):
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser(description="Verify a product repo's installed hooks against this Orbit's shipped versions")
    ap.add_argument("--target", default=".", type=Path, help="the product repo to check")
    args = ap.parse_args()
    target = args.target.resolve()

    print(f"Verifying .orbit/checks/*.py in {target} against {SKILL_ROOT} (this Orbit install)…\n")
    drift = 0
    for name in HOOK_FILES:
        shipped = ASSETS_CHECKS / name
        installed = target / ".orbit" / "checks" / name
        shipped_hash = _sha(shipped)
        installed_hash = _sha(installed)

        if not installed.exists():
            # design-gate.py is only placed on UI repos — absent there is normal, not drift.
            if name == "design-gate.py" and shipped_hash is not None:
                print(f"  -  {name}: not installed here (expected on non-UI repos)")
                continue
            print(f"  !  {name}: MISSING at {installed}")
            drift += 1
            continue
        if installed_hash is None:
            print(f"  !  {name}: present but unreadable at {installed}")
            drift += 1
            continue
        if shipped_hash is None:
            print(f"  ?  {name}: this Orbit install doesn't ship it — can't compare")
            continue
        if installed_hash == shipped_hash:
            print(f"  ✓  {name}: matches what this Orbit install ships")
        else:
            print(f"  ⚠️  {name}: DIFFERS from what this Orbit install ships.")
            print(f"      This may be a deliberate customization (e.g. RULES you added to "
                 f"guard.py) — or it may not be. Review the diff before trusting it:")
            print(f"        diff {shipped} {installed}")
            drift += 1

    print()
    if drift:
        print(f"⚠️  {drift} hook(s) differ from what this Orbit install ships — reviewed above.")
        sys.exit(1)
    print("✓ every installed hook matches this Orbit install's shipped version.")


if __name__ == "__main__":
    main()
