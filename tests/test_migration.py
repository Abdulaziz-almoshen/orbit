#!/usr/bin/env python3
"""
Tests scaffold.py's hook migration across versions:
  1. a known-old (<0.23.0 dead-shape) guard.py is REPLACED with the current one + backup + announce;
  2. a 0.23.0 guard.py (correct shape but narrow/bypassable) also UPGRADES to the hardened current;
  3. a locally-MODIFIED old guard is NOT clobbered (warned instead);
  4. an ALREADY-CURRENT guard is left untouched (no backup, no churn).

Run: python3 tests/test_migration.py   (exit 0 = pass)
"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCAFFOLD = os.path.join(ROOT, "scripts", "scaffold.py")


def blob_at(commit, relpath):
    r = subprocess.run(["git", "-C", ROOT, "show", f"{commit}:{relpath}"], capture_output=True)
    return r.stdout if r.returncode == 0 and r.stdout else None


def oldest_blob(relpath):
    commits = subprocess.run(["git", "-C", ROOT, "log", "--all", "--format=%H", "--", relpath],
                             capture_output=True, text=True).stdout.split()
    for c in reversed(commits):
        b = blob_at(c, relpath)
        if b:
            return b
    return None


def scaffold(target):
    return subprocess.run([sys.executable, SCAFFOLD, "--target", target, "--surfaces", "api"],
                          capture_output=True, text=True, timeout=60)


def _plant(d, blob):
    checks = os.path.join(d, ".orbit", "checks")
    os.makedirs(checks)
    open(os.path.join(checks, "guard.py"), "wb").write(blob)
    return checks


def main():
    fails = []
    old_guard = oldest_blob("assets/checks/guard.py")            # <0.23.0 dead-shape
    v0230_guard = blob_at("2849ddb", "assets/checks/guard.py")  # 0.23.0 (correct shape, bypassable)
    current_guard = open(os.path.join(ROOT, "assets", "checks", "guard.py"), "rb").read()
    if not old_guard or b'"permissionDecision": decision' not in old_guard:
        print("SKIP: could not fetch a known-old guard.py from git history"); return

    # Case 1: byte-identical <0.23.0 dead guard → migrated + backed up + announced
    with tempfile.TemporaryDirectory() as d:
        checks = _plant(d, old_guard)
        out = scaffold(d).stdout
        after = open(os.path.join(checks, "guard.py"), "rb").read()
        if b"_inner_commands" not in after:                     # a v0.23.1-only construct
            fails.append("clean <0.23.0 guard was NOT upgraded to the hardened guard")
        if not any(f.startswith("guard.py.bak.") for f in os.listdir(checks)):
            fails.append("no backup of the old guard.py was written")
        if "UPDATED" not in out:
            fails.append("migration was not announced in the scaffold output")

    # Case 2: a 0.23.0 guard (correct shape, but bypassable) also upgrades to the hardened current
    if v0230_guard and v0230_guard != current_guard:
        with tempfile.TemporaryDirectory() as d:
            checks = _plant(d, v0230_guard)
            scaffold(d)
            after = open(os.path.join(checks, "guard.py"), "rb").read()
            if after != current_guard:
                fails.append("0.23.0 guard was NOT upgraded to the hardened 0.23.1 guard")
            if not any(f.startswith("guard.py.bak.") for f in os.listdir(checks)):
                fails.append("no backup written when upgrading the 0.23.0 guard")

    # Case 3: locally-modified old guard → NOT clobbered, warned
    with tempfile.TemporaryDirectory() as d:
        checks = _plant(d, old_guard + b"\n# my custom rule\n")
        out = scaffold(d).stdout
        after = open(os.path.join(checks, "guard.py"), "rb").read()
        if b"_inner_commands" in after:
            fails.append("locally-modified guard.py was clobbered (must not be)")
        if b"# my custom rule" not in after:
            fails.append("locally-modified guard.py lost the user's edit")
        if "locally modified" not in out:
            fails.append("no warning for the locally-modified old guard.py")

    # Case 4: an ALREADY-CURRENT guard is left untouched (no backup)
    with tempfile.TemporaryDirectory() as d:
        checks = _plant(d, current_guard)
        scaffold(d)
        if any(f.startswith("guard.py.bak.") for f in os.listdir(checks)):
            fails.append("an already-current guard.py was needlessly backed up/rewritten")

    if fails:
        print("FAIL: migration")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("PASS: migration (old + 0.23.0 upgraded w/ backup; modified warned+preserved; current untouched)")


if __name__ == "__main__":
    main()
