#!/usr/bin/env python3
"""
Tests for assets/checks/guard.py — the PreToolUse safety hook.

Verifies (a) the decision logic across ~24 commands and (b) that the OUTPUT VALIDATES against
the schema Claude Code actually reads: hookSpecificOutput.{hookEventName=PreToolUse,
permissionDecision in {deny,ask}, permissionDecisionReason}.

Manual smoke (not automatable here): wire guard.py as a PreToolUse[Bash] hook in a temp repo's
.claude/settings.json, then `claude -p "run: git push --force"` and confirm the block appears.

Run: python3 tests/test_guard.py   (exit 0 = pass)
"""
import json
import os
import subprocess
import sys

GUARD = os.path.join(os.path.dirname(__file__), "..", "assets", "checks", "guard.py")


def run(stdin_text):
    p = subprocess.run([sys.executable, GUARD], input=stdin_text,
                       capture_output=True, text=True, timeout=10)
    return p.returncode, p.stdout.strip()


def decision_of(out):
    """None if allow (empty output); else the permissionDecision from the correct envelope."""
    if not out:
        return None
    obj = json.loads(out)                                  # must be valid JSON
    hso = obj["hookSpecificOutput"]                        # must use the correct envelope
    assert hso["hookEventName"] == "PreToolUse", hso
    assert hso["permissionDecision"] in ("deny", "ask"), hso
    assert hso.get("permissionDecisionReason"), "reason required"
    assert "permissionDecision" not in obj, "must NOT be top-level (Claude Code ignores that)"
    return hso["permissionDecision"]


def bash(cmd):
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}})


CASES = [
    # command                                            expected decision (None = allow)
    ("git push --force origin main",                     "deny"),
    ("git push -f",                                      "deny"),
    ("git push origin +main",                            "deny"),
    ("cd /repo && git push --force",                     "deny"),      # segment split
    ("cd x; git push --force origin main",               "deny"),      # ; split
    ('sh -c "git push -f"',                              "deny"),      # sh -c recursion
    ('bash -c "cd /r && git push --force"',              "deny"),
    ("sudo git push --force",                            "deny"),      # wrapper strip
    ("env FOO=1 git push --force",                       "deny"),      # env wrapper
    ("git push --force-with-lease",                      "ask"),       # safe variant → ask, not deny
    ("git push --force-with-lease=main",                 "ask"),
    ("git push",                                         "ask"),
    ("git push origin main",                             "ask"),
    ("cd app && git push origin main",                   "ask"),
    ("git merge main",                                   "ask"),
    ("git merge origin/main",                            "ask"),
    ("git push --force --dry-run",                       None),        # dry-run doesn't push
    ("git push --dry-run",                               None),
    ("git status",                                       None),
    ("git log --oneline",                                None),
    ("git commit -m 'wip'",                              None),
    ("echo 'git push --force is dangerous'",             None),        # mention in a string ≠ action
    ("ls -la && cat README.md",                          None),
    ("git merge feature-branch",                         None),        # not the default branch
]

ROBUSTNESS = [
    # (raw stdin, must-not-crash, expected decision)  — fail-open on all of these
    (bash("git status"),                                 None),
    ("[]",                                               None),        # valid JSON, not an object
    ("not json at all",                                  None),        # unparseable → allow
    ("",                                                 None),        # empty stdin → allow
    (json.dumps({"tool_name": "Read"}),                  None),        # non-Bash → allow
    (bash("git push $(printf origin)"),                  "ask"),       # still a push (no literal force flag) → ask, safe
]


def main():
    failures = []
    for cmd, expected in CASES:
        rc, out = run(bash(cmd))
        if rc != 0:
            failures.append(f"nonzero exit {rc} for: {cmd}")
            continue
        try:
            got = decision_of(out)
        except Exception as e:
            failures.append(f"bad output schema for {cmd!r}: {e} | out={out!r}")
            continue
        if got != expected:
            failures.append(f"MISROUTE {cmd!r}: expected {expected}, got {got}")

    for stdin_text, expected in ROBUSTNESS:
        try:
            rc, out = run(stdin_text)
        except Exception as e:
            failures.append(f"CRASH on robustness input {stdin_text!r}: {e}")
            continue
        if rc != 0:
            failures.append(f"nonzero exit on robustness input {stdin_text!r}")
            continue
        got = decision_of(out) if out else None
        if got != expected:
            failures.append(f"robustness {stdin_text!r}: expected {expected}, got {got}")

    total = len(CASES) + len(ROBUSTNESS)
    if failures:
        print(f"FAIL: guard {len(failures)}/{total} cases failed:")
        for f in failures:
            print("  -", f)
        sys.exit(1)
    print(f"PASS: guard {total}/{total} cases (decisions + schema + fail-open)")


if __name__ == "__main__":
    main()
