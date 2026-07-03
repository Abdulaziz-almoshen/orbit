#!/usr/bin/env python3
"""
Tests assets/checks/route.py classify() against ~65 realistic prompts.

Bar: ≥ 95% of the table classified as expected, AND zero task→question misroutes (the dangerous
direction — a task silently skipping the loop). Regression for the v0.22.1 audit findings:
"can you fix the bug" → question, "yes"/"go ahead" → forced clarifying question, "run the tests" → ambiguous.

Run: python3 tests/test_router.py   (exit 0 = pass)
"""
import importlib.util
import os
import sys

spec = importlib.util.spec_from_file_location(
    "route", os.path.join(os.path.dirname(__file__), "..", "assets", "checks", "route.py"))
route = importlib.util.module_from_spec(spec)
spec.loader.exec_module(route)
classify = route.classify

# (prompt, expected class)  — class ∈ {task, question, skip, ambiguous}
CASES = [
    # polite imperatives — the audit's worst failures (were → question, skipping the loop)
    ("can you add a logout button", "task"),
    ("could you fix the login bug?", "task"),
    ("can you refactor the auth module", "task"),
    ("would you add dark mode please", "task"),
    ("please can you deploy to staging", "task"),
    ("can you write a test for this", "task"),
    ("will you bump the version", "task"),
    # acks / confirmations — were → ambiguous → forced question
    ("yes", "skip"), ("yep", "skip"), ("no", "skip"), ("ok", "skip"), ("okay", "skip"),
    ("sure", "skip"), ("go ahead", "skip"), ("proceed", "skip"), ("continue", "skip"),
    ("do it", "skip"), ("option 2", "skip"), ("option B", "skip"), ("thanks", "skip"),
    ("lgtm", "skip"), ("ship it", "skip"), ("sounds good", "skip"), ("perfect", "skip"),
    ("a", "skip"), ("2", "skip"),
    # operational commands — were → ambiguous
    ("run the tests", "task"), ("commit and push", "task"), ("revert the last commit", "task"),
    ("bump the version", "task"), ("install the dependencies", "task"), ("deploy to prod", "task"),
    ("run the build", "task"), ("format the code", "task"), ("lint everything", "task"),
    ("upgrade the deps", "task"), ("migrate the database", "task"), ("tag a release", "task"),
    # plain imperative tasks
    ("add dark mode", "task"), ("fix the login bug", "task"), ("build a settings page", "task"),
    ("refactor the parser", "task"), ("rename this component", "task"), ("delete the old file", "task"),
    ("implement search", "task"), ("write the readme", "task"),
    # genuine questions — must stay questions
    ("how do I add a new screen?", "question"), ("what does the dispatcher do", "question"),
    ("why is the build failing?", "question"), ("is it deployed?", "question"),
    ("what's the current version", "question"), ("how does routing work", "question"),
    ("explain the loop", "question"), ("describe the architecture", "question"),
    ("can you explain how the router works", "question"), ("what are the roles", "question"),
    ("which model is this", "question"), ("should I use postgres or sqlite?", "question"),
    # negations / deferrals — don't interject
    ("don't build the export yet", "skip"), ("do not push this", "skip"),
    ("no need to add tests", "skip"), ("hold off on the deploy", "skip"), ("stop", "skip"),
    # genuinely ambiguous — soft directive, model decides (never forced question)
    ("the dashboard feels slow", "ambiguous"), ("the users are complaining about the checkout", "ambiguous"),
    ("something is off with the layout on mobile", "ambiguous"),
    # slash commands / empty
    ("/orbit", "skip"), ("/orbit-upgrade", "skip"), ("", "skip"),
]


def main():
    wrong, dangerous = [], []
    for prompt, expected in CASES:
        got = classify(prompt)
        if got != expected:
            wrong.append((prompt, expected, got))
            if expected == "task" and got == "question":     # task silently skips the loop
                dangerous.append((prompt, got))

    total = len(CASES)
    passed = total - len(wrong)
    pct = 100 * passed / total
    print(f"router: {passed}/{total} = {pct:.1f}%")
    if wrong:
        print("  misroutes:")
        for p, e, g in wrong:
            flag = "  ⚠ DANGEROUS" if (e == "task" and g == "question") else ""
            print(f"    {p!r}: expected {e}, got {g}{flag}")

    ok = pct >= 95.0 and len(dangerous) == 0
    if not ok:
        if dangerous:
            print(f"FAIL: {len(dangerous)} task→question misroute(s) (a task silently skips the loop) — must be 0")
        if pct < 95.0:
            print(f"FAIL: {pct:.1f}% < 95% bar")
        sys.exit(1)
    print("PASS: router ≥95% and zero task→question misroutes")


if __name__ == "__main__":
    main()
