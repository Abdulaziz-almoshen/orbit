#!/usr/bin/env python3
"""
Tests for assets/checks/design-gate.py — the PreToolUse design-gate hook (Phase 2).

Verifies (a) it only acts on Edit/Write/MultiEdit against a UI-production file, (b) it asks
exactly once per cycle when no design-decision record exists, (c) a TRIVIAL marker or a HEAVY
approved.json *carrying a taste_preflight record* allows silently — while a HEAVY approval with
NO taste_preflight asks (the taste gate), a legacy approval with no impact_level allows
(pass-with-warning), and an unparseable approval fails safe to allow, (d) it never touches .orbit/ previews, docs,
config, backend, or test files, (e) it fails open on any malformed/unexpected input, and
(f) the OUTPUT VALIDATES against the same hookSpecificOutput schema as guard.py — and it
NEVER returns "deny".

Run: python3 tests/test_design_gate.py   (exit 0 = pass)
"""
import json
import os
import subprocess
import sys
import tempfile

GATE = os.path.join(os.path.dirname(__file__), "..", "assets", "checks", "design-gate.py")


def run(stdin_text):
    p = subprocess.run([sys.executable, GATE], input=stdin_text,
                       capture_output=True, text=True, timeout=10)
    return p.returncode, p.stdout.strip()


def decision_of(out):
    """None if allow (empty output); else the permissionDecision from the correct envelope."""
    if not out:
        return None
    obj = json.loads(out)                                  # must be valid JSON
    hso = obj["hookSpecificOutput"]                         # must use the correct envelope
    assert hso["hookEventName"] == "PreToolUse", hso
    assert hso["permissionDecision"] == "ask", f"design-gate must NEVER deny, got {hso}"
    assert hso.get("permissionDecisionReason"), "reason required"
    assert "permissionDecision" not in obj, "must NOT be top-level"
    return hso["permissionDecision"]


def edit(tool, file_path, cwd):
    return json.dumps({"tool_name": tool, "tool_input": {"file_path": file_path}, "cwd": cwd})


def main():
    failures = []

    # --- 1. no design record anywhere -> ask on a UI production file --------------------
    with tempfile.TemporaryDirectory() as d:
        rc, out = run(edit("Edit", os.path.join(d, "src", "Button.tsx"), d))
        try:
            got = decision_of(out)
        except Exception as e:
            failures.append(f"bad output for no-record case: {e} | out={out!r}")
        else:
            if got != "ask":
                failures.append(f"no design record: expected ask, got {got}")

    # --- 2. a HEAVY approved.json WITH a taste_preflight record -> allow -----------------
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "design"))
        with open(os.path.join(d, "design", "approved.json"), "w") as f:
            json.dump({"component": "x", "impact_level": "HEAVY", "cycle": 1,
                       "taste_preflight": {"design_read": "…", "dials": {"variance": 4},
                                           "design_system": "shadcn", "surface": "app",
                                           "checklist_passed": True}}, f)
        rc, out = run(edit("Write", os.path.join(d, "src", "Card.tsx"), d))
        if decision_of(out) is not None:
            failures.append(f"HEAVY approved.json with taste_preflight but still asked: {out!r}")

    # --- 2a. a HEAVY approved.json with NO taste_preflight -> ask (the taste gate) --------
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "design"))
        with open(os.path.join(d, "design", "approved.json"), "w") as f:
            json.dump({"component": "x", "impact_level": "HEAVY", "cycle": 1}, f)
        rc, out = run(edit("Write", os.path.join(d, "src", "Card.tsx"), d))
        got = decision_of(out)
        if got != "ask":
            failures.append(f"HEAVY approval with no taste_preflight should ask, got {got}: {out!r}")
        elif "taste_preflight" not in json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"]:
            failures.append(f"the no-preflight ask should name taste_preflight: {out!r}")

    # --- 2c. a LEGACY approval (no impact_level) -> allow (pass-with-warning preserved) ---
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "design"))
        with open(os.path.join(d, "design", "approved.json"), "w") as f:
            json.dump({"component": "x", "chosen": "variant-b"}, f)   # predates impact_level
        rc, out = run(edit("Write", os.path.join(d, "src", "Card.tsx"), d))
        if decision_of(out) is not None:
            failures.append(f"legacy approval (no impact_level) should allow, asked: {out!r}")

    # --- 2d. an UNPARSEABLE approval -> allow (fail-safe, never fabricate a finding) ------
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "design"))
        with open(os.path.join(d, "design", "approved.json"), "w") as f:
            f.write("{ this is not valid json ")
        rc, out = run(edit("Write", os.path.join(d, "src", "Card.tsx"), d))
        if decision_of(out) is not None:
            failures.append(f"unparseable approval should fail safe to allow, asked: {out!r}")

    # --- 2b. editing a UI file in a SUBDIR finds the root design record (no over-ask) ----
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, ".orbit", "design"))
        os.makedirs(os.path.join(d, "packages", "app", "src"))
        open(os.path.join(d, ".orbit", "design", "TRIVIAL"), "w").write("triage: trivial\n")
        sub = os.path.join(d, "packages", "app")           # cwd is the subdir, .orbit is at root
        rc, out = run(edit("Edit", os.path.join(sub, "src", "Btn.tsx"), sub))
        if decision_of(out) is not None:
            failures.append(f"subdir edit missed the root design record (over-asked): {out!r}")

    # --- 3. a TRIVIAL marker exists -> allow ---------------------------------------------
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, ".orbit", "design"))
        with open(os.path.join(d, ".orbit", "design", "TRIVIAL"), "w") as f:
            f.write("component: Button\nreason: copy fix\n")
        rc, out = run(edit("Edit", os.path.join(d, "src", "Button.tsx"), d))
        if decision_of(out) is not None:
            failures.append(f"TRIVIAL marker present but still asked: {out!r}")

    # --- 4. an .orbit/ preview edit is never gated ---------------------------------------
    with tempfile.TemporaryDirectory() as d:
        rc, out = run(edit("Write", os.path.join(d, ".orbit", "artifacts", "3", "previews",
                                                 "variant-a.html"), d))
        if decision_of(out) is not None:
            failures.append(f".orbit/ preview file was gated: {out!r}")

    # --- 5. doc / config / backend / test files are never gated --------------------------
    with tempfile.TemporaryDirectory() as d:
        for p in ("README.md", "config.yaml", "package.json", "server/api.py",
                 "src/components/Button.test.tsx", "tests/Button.spec.jsx"):
            rc, out = run(edit("Edit", os.path.join(d, p), d))
            if decision_of(out) is not None:
                failures.append(f"non-UI-production file was gated: {p} -> {out!r}")

    # --- 6. ask fires at most ONCE per cycle (second edit same cycle -> silent) ----------
    with tempfile.TemporaryDirectory() as d:
        rc1, out1 = run(edit("Edit", os.path.join(d, "src", "A.tsx"), d))
        got1 = decision_of(out1)
        rc2, out2 = run(edit("Edit", os.path.join(d, "src", "B.tsx"), d))
        got2 = decision_of(out2)
        if got1 != "ask":
            failures.append(f"first unguarded UI edit should ask, got {got1}")
        if got2 is not None:
            failures.append(f"second unguarded UI edit same cycle should be silent, got {got2}")

    # --- 7. a NEW cycle re-arms the ask (STATE.md Iteration bump) ------------------------
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, ".orbit"))
        state = os.path.join(d, ".orbit", "STATE.md")
        with open(state, "w") as f:
            f.write("## Current snapshot\n- Iteration: 1 of 10\n")
        rc, out = run(edit("Edit", os.path.join(d, "src", "A.tsx"), d))
        if decision_of(out) != "ask":
            failures.append("cycle 1: expected ask on first unguarded edit")
        with open(state, "w") as f:
            f.write("## Current snapshot\n- Iteration: 2 of 10\n")
        rc, out = run(edit("Edit", os.path.join(d, "src", "B.tsx"), d))
        if decision_of(out) != "ask":
            failures.append("cycle 2 (new iteration): expected the ask to re-arm, got silence")

    # --- 7b. no "cwd" in the payload -> falls back to the process's actual cwd, no crash ---
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "design"))
        with open(os.path.join(d, "design", "approved.json"), "w") as f:
            json.dump({"component": "x", "impact_level": "HEAVY", "cycle": 1,
                       "taste_preflight": {"checklist_passed": True}}, f)
        payload = json.dumps({"tool_name": "Write", "tool_input": {"file_path": "src/Card.tsx"}})
        p = subprocess.run([sys.executable, GATE], input=payload, capture_output=True, text=True,
                          timeout=10, cwd=d)
        if p.returncode != 0:
            failures.append(f"no-cwd-in-payload case exited nonzero: {p.stderr!r}")
        elif decision_of(p.stdout.strip()) is not None:
            failures.append(f"no-cwd-in-payload should fall back to the process cwd and allow "
                            f"(approved.json is there): {p.stdout!r}")

    # --- 8. fail-open on malformed / unexpected input ------------------------------------
    ROBUSTNESS = [
        "not json at all",
        "",
        "[]",
        json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}}),   # not Edit/Write
        json.dumps({"tool_name": "Edit", "tool_input": {}}),                  # missing file_path
    ]
    for stdin_text in ROBUSTNESS:
        try:
            rc, out = run(stdin_text)
        except Exception as e:
            failures.append(f"CRASH on robustness input {stdin_text!r}: {e}")
            continue
        if rc != 0:
            failures.append(f"nonzero exit on robustness input {stdin_text!r}")
            continue
        if out:
            try:
                got = decision_of(out)
            except Exception as e:
                failures.append(f"bad schema on robustness input {stdin_text!r}: {e}")
                continue
            if got is not None:
                failures.append(f"robustness input should fail open (allow), got {got}: {stdin_text!r}")

    if failures:
        print(f"FAIL: design-gate {len(failures)} case(s) failed:")
        for f in failures:
            print("  -", f)
        sys.exit(1)
    print("PASS: design-gate (ask-only, once per cycle, record-aware, fail-open)")


if __name__ == "__main__":
    main()
