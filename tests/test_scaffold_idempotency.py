#!/usr/bin/env python3
"""
Tests scaffold idempotency: running scaffold.py twice into the same repo must not change any
file the first run produced (no duplication, no clobber, no re-write) — re-running /orbit is
safe. Also asserts the second run reports everything as skipped, not created.

Run: python3 tests/test_scaffold_idempotency.py   (exit 0 = pass)
"""
import hashlib
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCAFFOLD = os.path.join(ROOT, "scripts", "scaffold.py")


def _snapshot(d):
    out = {}
    for base, _, files in os.walk(d):
        for fn in files:
            p = os.path.join(base, fn)
            out[os.path.relpath(p, d)] = hashlib.sha256(open(p, "rb").read()).hexdigest()
    return out


def main():
    fails = []
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["git", "init", "-q", d], check=True)
        r1 = subprocess.run([sys.executable, SCAFFOLD, "--surfaces", "web,api", "--install-hooks",
                             "--target", d], capture_output=True, text=True, check=True)
        snap1 = _snapshot(d)

        r2 = subprocess.run([sys.executable, SCAFFOLD, "--surfaces", "web,api", "--install-hooks",
                             "--target", d], capture_output=True, text=True, check=True)
        snap2 = _snapshot(d)

        # nothing changed content
        changed = [k for k in snap1 if k in snap2 and snap1[k] != snap2[k]]
        if changed:
            fails.append(f"second scaffold changed {len(changed)} file(s): {changed[:5]}")
        # no files vanished
        vanished = [k for k in snap1 if k not in snap2]
        if vanished:
            fails.append(f"second scaffold removed files: {vanished[:5]}")
        # second run created nothing new (idempotent) and did NOT re-announce installs as fresh
        if "Created:" in r2.stdout:
            new_lines = r2.stdout.split("Created:", 1)[1].split("Skipped", 1)[0]
            if new_lines.strip() and "(nothing new)" not in new_lines:
                fails.append("second scaffold reported freshly-created files (not idempotent)")
        if "already wired" not in r2.stdout:
            fails.append("second scaffold re-installed hooks instead of detecting them (not idempotent)")

    if fails:
        print("FAIL: scaffold idempotency")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("PASS: scaffold idempotency (re-running /orbit changes nothing, double-adds nothing)")


if __name__ == "__main__":
    main()
