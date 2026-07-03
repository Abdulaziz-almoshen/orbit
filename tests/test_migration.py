#!/usr/bin/env python3
"""
Tests scaffold.py's hook migration: an existing repo with a known-old (broken) guard.py/route.py
gets it REPLACED with the fixed version + a backup + an announcement; a locally-MODIFIED old file
is NOT clobbered (warned instead). Regression for the v0.22.1 critical guard-protocol defect.

Run: python3 tests/test_migration.py   (exit 0 = pass)
"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCAFFOLD = os.path.join(ROOT, "scripts", "scaffold.py")


def oldest_blob(relpath):
    commits = subprocess.run(["git", "-C", ROOT, "log", "--all", "--format=%H", "--", relpath],
                             capture_output=True, text=True).stdout.split()
    for c in reversed(commits):  # oldest first
        blob = subprocess.run(["git", "-C", ROOT, "show", f"{c}:{relpath}"], capture_output=True).stdout
        if blob:
            return blob
    return None


def scaffold(target):
    return subprocess.run([sys.executable, SCAFFOLD, "--target", target, "--surfaces", "api"],
                          capture_output=True, text=True, timeout=60)


def main():
    fails = []
    old_guard = oldest_blob("assets/checks/guard.py")
    old_route = oldest_blob("assets/checks/route.py")
    if not old_guard or b'"permissionDecision": decision' not in old_guard:
        print("SKIP: could not fetch a known-old guard.py from git history"); return

    # Case 1: byte-identical old files → migrated + backed up
    with tempfile.TemporaryDirectory() as d:
        checks = os.path.join(d, ".orbit", "checks"); os.makedirs(checks)
        open(os.path.join(checks, "guard.py"), "wb").write(old_guard)
        if old_route:
            open(os.path.join(checks, "route.py"), "wb").write(old_route)
        out = scaffold(d).stdout
        guard_after = open(os.path.join(checks, "guard.py"), "rb").read()
        if b"hookSpecificOutput" not in guard_after:
            fails.append("clean-old guard.py was NOT migrated to the fixed protocol")
        if not any(f.startswith("guard.py.bak.") for f in os.listdir(checks)):
            fails.append("no backup of the old guard.py was written")
        if "FIXED" not in out:
            fails.append("migration was not announced in the scaffold output")

    # Case 2: locally-modified old guard → NOT clobbered, warned
    with tempfile.TemporaryDirectory() as d:
        checks = os.path.join(d, ".orbit", "checks"); os.makedirs(checks)
        open(os.path.join(checks, "guard.py"), "wb").write(old_guard + b"\n# my custom rule\n")
        out = scaffold(d).stdout
        guard_after = open(os.path.join(checks, "guard.py"), "rb").read()
        if b"hookSpecificOutput" in guard_after:
            fails.append("locally-modified guard.py was clobbered (must not be)")
        if b"# my custom rule" not in guard_after:
            fails.append("locally-modified guard.py lost the user's edit")
        if "locally modified" not in out:
            fails.append("no warning for the locally-modified old guard.py")

    if fails:
        print("FAIL: migration")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("PASS: migration (clean-old replaced+backed-up+announced; user-modified warned+preserved)")


if __name__ == "__main__":
    main()
