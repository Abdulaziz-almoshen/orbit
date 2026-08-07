#!/usr/bin/env python3
"""Orbit delivery-quality gate: scenario, dependency-regression, and pixel evidence before CPO.

The QA role writes `.orbit/qa/delivery-evidence.json`. This validator treats role completion as
insufficient: every required scenario must have observed proof, related dependencies must be mapped
and regression-tested, and UI work must include pixel comparisons at every configured viewport.
Stdlib-only, deterministic, and fail-closed for a present Orbit delivery contract.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

DEFAULT_SCENARIOS = ("happy", "alternate", "negative", "boundary", "authorization", "failure_recovery")
DEFAULT_VIEWPORTS = ("375x812", "768x1024", "1440x900")


def _json(path: Path, default=None):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def _repo_head(root: Path):
    try:
        p = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, text=True,
                           capture_output=True, timeout=5)
        return p.stdout.strip() if p.returncode == 0 else None
    except Exception:
        return None


def _ui_project(root: Path):
    setup = _json(root / ".orbit" / "setup.json", {}) or {}
    surfaces = {str(s).lower() for s in setup.get("surfaces", [])}
    return bool(surfaces & {"web", "frontend", "ui", "mobile", "ios", "android"}) or \
        (root / ".claude" / "agents" / "designer.md").is_file()


def _artifact(root: Path, value):
    if not str(value or "").strip():
        return False
    p = Path(str(value))
    return (p if p.is_absolute() else root / p).is_file()


def _artifact_path(root: Path, value):
    p = Path(str(value or ""))
    return p if p.is_absolute() else root / p


def _pixel_diff(root: Path, baseline, actual, diff, threshold):
    helper = Path(__file__).resolve().parent.parent / "qa" / "snapshot.py"
    if not helper.is_file():
        helper = root / ".orbit" / "qa" / "snapshot.py"
    if not helper.is_file():
        return False, "pixel-diff helper is missing"
    cmd = [sys.executable, str(helper), "diff", str(_artifact_path(root, baseline)),
           str(_artifact_path(root, actual)), "--threshold", str(threshold),
           "--out", str(_artifact_path(root, diff))]
    try:
        proc = subprocess.run(cmd, cwd=root, text=True, capture_output=True, timeout=30)
        return proc.returncode == 0, (proc.stdout or proc.stderr).strip()
    except Exception as exc:
        return False, f"pixel diff failed: {exc}"


def evaluate(root: Path, evidence_path=None, expected_commit=None, ui_project=None, contract=None):
    root = root.resolve()
    cfg = contract or ((_json(root / ".orbit" / "loop.config.json", {}) or {})
                       .get("delivery_quality") or {})
    if cfg.get("enabled", True) is not True:
        return {"passed": True, "status": "disabled", "errors": []}
    path = Path(evidence_path) if evidence_path else root / str(
        cfg.get("evidence_path", ".orbit/qa/delivery-evidence.json"))
    if not path.is_absolute():
        path = root / path
    data = _json(path)
    errors = []
    if not isinstance(data, dict):
        return {"passed": False, "status": "missing_evidence", "path": str(path),
                "errors": ["missing or unreadable delivery-evidence.json"]}

    commit = str(data.get("commit") or "").strip()
    expected = str(expected_commit or _repo_head(root) or "").strip()
    if not commit:
        errors.append("evidence is not commit-bound")
    elif expected and commit != expected:
        errors.append(f"evidence commit {commit[:8]} does not match delivered commit {expected[:8]}")
    if str(data.get("verdict", "")).upper() != "PASS":
        errors.append("overall QA verdict is not PASS")

    scenarios = data.get("scenarios") if isinstance(data.get("scenarios"), dict) else {}
    cases = scenarios.get("cases") if isinstance(scenarios.get("cases"), list) else []
    required_kinds = tuple(cfg.get("required_scenario_kinds") or DEFAULT_SCENARIOS)
    covered = set()
    for i, case in enumerate(cases):
        if not isinstance(case, dict):
            errors.append(f"scenario case {i + 1} is not an object")
            continue
        kind = str(case.get("kind") or "").lower()
        covered.add(kind)
        if not all(str(case.get(k) or "").strip() for k in
                   ("id", "persona", "preconditions", "steps", "expected", "actual")):
            errors.append(f"scenario {case.get('id') or i + 1} lacks executable Given/When/Then detail")
        if str(case.get("verdict", "")).upper() != "PASS":
            errors.append(f"scenario {case.get('id') or i + 1} did not PASS")
        if not _artifact(root, case.get("evidence")):
            errors.append(f"scenario {case.get('id') or i + 1} has no evidence artifact")
    missing = [k for k in required_kinds if k not in covered]
    if missing:
        errors.append("scenario matrix missing: " + ", ".join(missing))
    if scenarios.get("coverage_complete") is not True:
        errors.append("scenario coverage is not explicitly complete")

    deps = data.get("dependency_regression") if isinstance(data.get("dependency_regression"), dict) else {}
    for key in ("changed_units", "direct_dependents", "transitive_dependents", "related_user_flows"):
        if not isinstance(deps.get(key), list) or not deps.get(key):
            errors.append(f"dependency impact map has no {key}")
    commands = deps.get("commands") if isinstance(deps.get("commands"), list) else []
    if not commands:
        errors.append("no dependency-regression commands were recorded")
    for i, cmd in enumerate(commands):
        if not isinstance(cmd, dict) or not str(cmd.get("command") or "").strip():
            errors.append(f"dependency command {i + 1} is incomplete")
        elif cmd.get("exit_code") != 0 or str(cmd.get("verdict", "PASS")).upper() != "PASS":
            errors.append(f"dependency command failed: {cmd.get('command')}")
        elif not _artifact(root, cmd.get("evidence")):
            errors.append(f"dependency command lacks captured output: {cmd.get('command')}")
    if deps.get("coverage_complete") is not True or str(deps.get("verdict", "")).upper() != "PASS":
        errors.append("related dependency regression is not complete and PASS")

    visual_required = _ui_project(root) if ui_project is None else bool(ui_project)
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    if visual_required:
        if visual.get("applicable") is not True:
            errors.append("UI delivery has no pixel-level visual QA")
        required_viewports = tuple(cfg.get("required_viewports") or DEFAULT_VIEWPORTS)
        comparisons = visual.get("comparisons") if isinstance(visual.get("comparisons"), list) else []
        routes = visual.get("changed_routes") if isinstance(visual.get("changed_routes"), list) else []
        routes = [str(r) for r in routes if str(r).strip()]
        if not routes:
            errors.append("visual evidence does not list every changed route/screen")
        covered_pairs = {(str(c.get("route")), str(c.get("viewport")))
                         for c in comparisons if isinstance(c, dict)}
        missing_pairs = [f"{route}@{viewport}" for route in routes for viewport in required_viewports
                         if (route, viewport) not in covered_pairs]
        if missing_pairs:
            errors.append("pixel comparisons missing changed surfaces: " + ", ".join(missing_pairs))
        threshold = float(cfg.get("max_pixel_mismatch_ratio", 0.01))
        for i, comp in enumerate(comparisons):
            if not isinstance(comp, dict):
                errors.append(f"pixel comparison {i + 1} is invalid")
                continue
            label = f"{comp.get('route', '?')}@{comp.get('viewport', '?')}"
            for key in ("baseline", "actual", "diff"):
                if not _artifact(root, comp.get(key)):
                    errors.append(f"pixel comparison {label} lacks {key} image")
            try:
                ratio = float(comp.get("mismatch_ratio"))
            except (TypeError, ValueError):
                errors.append(f"pixel comparison {label} lacks a numeric mismatch ratio")
                continue
            if ratio > threshold or str(comp.get("verdict", "")).upper() != "PASS":
                errors.append(f"pixel comparison {label} exceeds {threshold:.2%}: {ratio:.2%}")
            if _artifact(root, comp.get("baseline")) and _artifact(root, comp.get("actual")):
                pixel_passed, detail = _pixel_diff(root, comp.get("baseline"), comp.get("actual"),
                                                   comp.get("diff"), threshold)
                if not pixel_passed:
                    errors.append(f"computed pixel diff failed for {label}: {detail}")
        if visual.get("tokens_verdict") != "PASS":
            errors.append("computed design tokens do not match the approved contract")
        if visual.get("accessibility_verdict") != "PASS":
            errors.append("visual accessibility checks did not PASS")
        if visual.get("console_errors") != []:
            errors.append("UI scenarios produced console errors")
        if str(visual.get("verdict", "")).upper() != "PASS":
            errors.append("visual QA verdict is not PASS")

    return {"passed": not errors, "status": "passed" if not errors else "blocked",
            "path": str(path), "commit": commit, "ui_required": visual_required, "errors": errors}


def main():
    ap = argparse.ArgumentParser(description="Validate Orbit's pre-CPO delivery evidence")
    ap.add_argument("--root", default=".", type=Path)
    ap.add_argument("--evidence", default="")
    ap.add_argument("--commit", default="")
    ap.add_argument("--ui", choices=("auto", "yes", "no"), default="auto")
    args = ap.parse_args()
    ui = None if args.ui == "auto" else args.ui == "yes"
    result = evaluate(args.root, args.evidence or None, args.commit or None, ui)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
