#!/usr/bin/env python3
"""Hard pre-CPO delivery evidence: scenarios, dependency regression, and computed pixel diffs."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GATE = ROOT / "assets" / "checks" / "delivery-quality-gate.py"
spec = importlib.util.spec_from_file_location("delivery_quality_gate", GATE)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
fails = []


def ck(value, message):
    if not value:
        fails.append(message)


def ppm(path, changed=False):
    pixels = bytearray()
    for y in range(12):
        for x in range(12):
            v = (x * 17 + y * 29) % 255
            if changed and x == 4 and y == 5:
                v = 255 - v
            pixels += bytes((v, (v * 2) % 255, (v * 3) % 255))
    path.write_bytes(b"P6\n12 12\n255\n" + pixels)


def fixture(root):
    evidence_dir = root / ".orbit" / "artifacts" / "1" / "qa"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    cases = []
    for i, kind in enumerate(gate.DEFAULT_SCENARIOS, 1):
        proof = evidence_dir / f"SC-{i}.txt"
        proof.write_text(f"observed {kind} scenario")
        cases.append({"id": f"SC-{i}", "kind": kind, "persona": "recruiter",
                      "preconditions": "Given an authenticated recruiter and seeded vacancy",
                      "steps": "When the recruiter completes the workflow",
                      "expected": "Then the state and downstream list update",
                      "actual": "The state and downstream list updated", "verdict": "PASS",
                      "evidence": str(proof.relative_to(root))})
    reg = evidence_dir / "regression.txt"; reg.write_text("42 tests passed")
    comparisons = []
    for vp in gate.DEFAULT_VIEWPORTS:
        baseline = evidence_dir / f"baseline-{vp}.ppm"
        actual = evidence_dir / f"actual-{vp}.ppm"
        diff = evidence_dir / f"diff-{vp}.ppm"
        ppm(baseline); ppm(actual); ppm(diff)
        comparisons.append({"route": "/jobs", "viewport": vp,
                            "baseline": str(baseline.relative_to(root)),
                            "actual": str(actual.relative_to(root)),
                            "diff": str(diff.relative_to(root)),
                            "mismatch_ratio": 0.0, "verdict": "PASS"})
    return {"schema_version": 1, "commit": "abc123", "verdict": "PASS",
            "scenarios": {"coverage_complete": True, "cases": cases},
            "dependency_regression": {
                "changed_units": ["job-form"], "direct_dependents": ["job-service"],
                "transitive_dependents": ["job-list"], "related_user_flows": ["edit and reopen job"],
                "commands": [{"command": "npm test -- jobs", "exit_code": 0, "verdict": "PASS",
                              "evidence": str(reg.relative_to(root))}],
                "coverage_complete": True, "verdict": "PASS"},
            "visual": {"applicable": True, "changed_routes": ["/jobs"], "comparisons": comparisons,
                       "tokens_verdict": "PASS", "accessibility_verdict": "PASS",
                       "console_errors": [], "verdict": "PASS"}}


def main():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        evidence = fixture(root)
        path = root / ".orbit" / "qa" / "delivery-evidence.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(evidence))
        result = gate.evaluate(root, path, expected_commit="abc123", ui_project=True, contract={"enabled": True})
        ck(result["passed"], f"complete evidence must pass: {result['errors']}")

        missing = json.loads(path.read_text()); missing["scenarios"]["cases"].pop()
        path.write_text(json.dumps(missing))
        result = gate.evaluate(root, path, "abc123", True, {"enabled": True})
        ck(not result["passed"] and any("failure_recovery" in e for e in result["errors"]),
           "missing required scenario kind must block")

        broken = fixture(root); broken["dependency_regression"]["commands"][0]["exit_code"] = 1
        path.write_text(json.dumps(broken))
        result = gate.evaluate(root, path, "abc123", True, {"enabled": True})
        ck(not result["passed"] and any("command failed" in e for e in result["errors"]),
           "failed related regression command must block")

        pixels = fixture(root)
        actual = root / pixels["visual"]["comparisons"][0]["actual"]
        ppm(actual, changed=True)  # manifest lies (ratio 0); computed diff must catch it at strict 0
        path.write_text(json.dumps(pixels))
        result = gate.evaluate(root, path, "abc123", True,
                               {"enabled": True, "max_pixel_mismatch_ratio": 0.0})
        ck(not result["passed"] and any("computed pixel diff failed" in e for e in result["errors"]),
           "pixel comparison must be computed, not trusted from manifest prose")

        exact = fixture(root); path.write_text(json.dumps(exact))
        result = gate.evaluate(root, path, "different", True, {"enabled": True})
        ck(not result["passed"] and any("does not match" in e for e in result["errors"]),
           "evidence must bind the exact delivered commit")

    with tempfile.TemporaryDirectory() as d:
        root = Path(d); orbit = root / ".orbit"
        (orbit / "checks").mkdir(parents=True); (orbit / "qa").mkdir()
        shutil.copy2(GATE, orbit / "checks" / "delivery-quality-gate.py")
        shutil.copy2(ROOT / "assets" / "qa" / "snapshot.py", orbit / "qa" / "snapshot.py")
        (orbit / "loop.config.json").write_text(json.dumps({
            "delivery_quality": {"enabled": True}, "cpo_acceptance": {"enabled": False},
            "capability_enforcement": {"enabled": False, "work_event_threshold": 3}}))
        (orbit / "setup.json").write_text(json.dumps({"surfaces": ["web"]}))
        (orbit / ".last-task-route").write_text("x")
        events = [{"phase": "route", "status": "start"}] + [
            {"phase": "act", "status": "done", "role": "builder"} for _ in range(3)]
        (orbit / "activity.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n")
        time.sleep(0.02); (orbit / "tasks.json").write_text("[]")
        hook = ROOT / "assets" / "checks" / "orbit-stop-check.py"
        proc = subprocess.run([sys.executable, str(hook)], input=json.dumps({"cwd": str(root)}),
                              text=True, capture_output=True,
                              env={**os.environ, "CLAUDE_PROJECT_DIR": str(root)})
        out = json.loads(proc.stdout) if proc.stdout.strip() else {}
        ck(out.get("decision") == "block" and "DELIVERY QUALITY GATE" in out.get("reason", ""),
           "Stop hook must block missing delivery evidence before CPO")
        evidence = fixture(root); path = orbit / "qa" / "delivery-evidence.json"
        time.sleep(0.02); path.write_text(json.dumps(evidence))
        proc = subprocess.run([sys.executable, str(hook)], input=json.dumps({"cwd": str(root)}),
                              text=True, capture_output=True,
                              env={**os.environ, "CLAUDE_PROJECT_DIR": str(root)})
        ck(not proc.stdout.strip(), f"valid evidence should release the pre-CPO Stop gate: {proc.stdout}")

    with tempfile.TemporaryDirectory() as d:
        root = Path(d); orbit = root / ".orbit"; orbit.mkdir()
        (orbit / "loop.config.json").write_text(json.dumps({
            "cpo_acceptance": {"enabled": True}, "paths": {}, "independent_qa": {}}))
        subprocess.run([sys.executable, str(ROOT / "scripts" / "scaffold.py"), "--target", str(root)],
                       text=True, capture_output=True, check=True,
                       env={**os.environ, "ORBIT_HOME": str(root / "home")})
        migrated = json.loads((orbit / "loop.config.json").read_text())
        ck(migrated.get("delivery_quality", {}).get("enabled") is True,
           "safe update must enable the delivery-quality contract in existing Orbit projects")
        ck(migrated.get("cpo_acceptance", {}).get("require_delivery_evidence") is True,
           "safe update must bind CPO to delivery evidence")
        ck((orbit / "checks" / "delivery-quality-gate.py").is_file(),
           "safe update must install the delivery-quality validator")

    if fails:
        print(f"FAIL: delivery-quality-gate {len(fails)} case(s):")
        for failure in fails:
            print("  -", failure)
        raise SystemExit(1)
    print("PASS: delivery-quality-gate (six scenarios · dependency graph · computed 3-viewport pixels · exact commit · Stop enforcement)")


if __name__ == "__main__":
    main()
