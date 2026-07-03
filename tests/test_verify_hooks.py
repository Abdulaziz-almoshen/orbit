#!/usr/bin/env python3
"""
Tests scripts/verify-hooks.py: it detects a matching hook, a MODIFIED hook (drift/possible
tampering), and a MISSING hook — and never crashes on an empty/partial .orbit/checks/.

Run: python3 tests/test_verify_hooks.py   (exit 0 = pass)
"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERIFY = os.path.join(ROOT, "scripts", "verify-hooks.py")
CHECKS_SRC = os.path.join(ROOT, "assets", "checks")
GUARD_SRC = os.path.join(CHECKS_SRC, "guard.py")
NON_UI_HOOKS = ["guard.py", "route.py", "learn.py"]        # design-gate.py is UI-only


def run(target):
    return subprocess.run([sys.executable, VERIFY, "--target", target],
                          capture_output=True, text=True, timeout=15)


def _plant_all(checks_dir):
    for name in NON_UI_HOOKS:
        with open(os.path.join(CHECKS_SRC, name), "rb") as a, \
             open(os.path.join(checks_dir, name), "wb") as b:
            b.write(a.read())


def main():
    fails = []

    # 1. exact copies of every shipped non-UI hook -> a clean match, exit 0
    with tempfile.TemporaryDirectory() as d:
        checks = os.path.join(d, ".orbit", "checks")
        os.makedirs(checks)
        _plant_all(checks)
        p = run(d)
        if p.returncode != 0:
            fails.append(f"identical hooks should exit 0: rc={p.returncode} out={p.stdout!r}")
        if "guard.py: matches what this Orbit install ships" not in p.stdout:
            fails.append(f"guard.py should report a match: {p.stdout!r}")

    # 2. a modified guard.py (rest untouched) -> reported as differing, nonzero exit
    with tempfile.TemporaryDirectory() as d:
        checks = os.path.join(d, ".orbit", "checks")
        os.makedirs(checks)
        _plant_all(checks)
        with open(os.path.join(checks, "guard.py"), "ab") as f:
            f.write(b"\n# a locally-added rule\n")
        p = run(d)
        if p.returncode == 0 or "DIFFERS" not in p.stdout:
            fails.append(f"modified guard.py should be flagged as differing: rc={p.returncode} "
                         f"out={p.stdout!r}")

    # 3. a totally empty repo (no .orbit/checks/ at all) -> reports MISSING, never crashes
    with tempfile.TemporaryDirectory() as d:
        p = run(d)
        if p.returncode == 0:
            fails.append("an empty repo (no hooks at all) should NOT report success")
        if "MISSING" not in p.stdout:
            fails.append(f"an empty repo should report MISSING hooks: {p.stdout!r}")

    if fails:
        print("FAIL: verify-hooks")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("PASS: verify-hooks (matches identical, flags modified, reports missing, never crashes)")


if __name__ == "__main__":
    main()
