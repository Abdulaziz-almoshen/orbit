#!/usr/bin/env python3
"""
Context budget gate (v0.38.0): Orbit must diagnose bloated working context before expensive
orchestration, and compact must archive old append-only history instead of deleting it.

Run: python3 tests/test_context_budget.py   (exit 0 = pass)
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "bin/orbit-context"
CONFIG = ROOT / "assets/loop.config.json"


def _project(tmp: Path) -> Path:
    orbit = tmp / ".orbit"
    orbit.mkdir()
    cfg = json.loads(CONFIG.read_text())
    cfg["context_budget"].update({
        "total_warn_tokens": 60,
        "total_fail_tokens": 120,
        "state_warn_tokens": 30,
        "state_fail_tokens": 80,
        "activity_warn_tokens": 30,
        "activity_fail_tokens": 80,
        "steps_warn_tokens": 30,
        "steps_fail_tokens": 80,
        "state_keep_recent_entries": 3,
        "activity_keep_events": 4,
        "steps_keep_events": 3,
    })
    (orbit / "loop.config.json").write_text(json.dumps(cfg))
    return tmp


def test_doctor_thresholds():
    with tempfile.TemporaryDirectory() as d:
        root = _project(Path(d))
        (root / ".orbit/STATE.md").write_text("x" * 400)
        r = subprocess.run([sys.executable, str(TOOL), "doctor", str(root)],
                           text=True, capture_output=True)
        assert r.returncode == 2, r.stdout + r.stderr
        assert "FAIL" in r.stdout and "STATE" in r.stdout, r.stdout


def test_compact_archives_integrity():
    with tempfile.TemporaryDirectory() as d:
        root = _project(Path(d))
        activity = [json.dumps({"n": i, "msg": "x" * 40}) for i in range(10)]
        steps = [json.dumps({"step": i, "msg": "y" * 40}) for i in range(8)]
        (root / ".orbit/activity.jsonl").write_text("\n".join(activity) + "\n")
        (root / ".orbit/steps.jsonl").write_text("\n".join(steps) + "\n")
        (root / ".orbit/STATE.md").write_text(
            "# Working State\n\n"
            "## Decision log\n"
            + "".join(f"- d{i}\n" for i in range(7))
            + "\n## Cycle log\n"
            + "".join(f"- c{i}\n" for i in range(7))
        )
        r = subprocess.run([sys.executable, str(TOOL), "compact", str(root)],
                           text=True, capture_output=True)
        assert r.returncode in (0, 2), r.stdout + r.stderr
        assert len((root / ".orbit/activity.jsonl").read_text().splitlines()) == 4
        assert len((root / ".orbit/steps.jsonl").read_text().splitlines()) == 3
        state = (root / ".orbit/STATE.md").read_text()
        assert "- d0" in state and "- d4" not in state
        assert "- c0" in state and "- c4" not in state
        archives = list((root / ".orbit/archive").glob("*"))
        assert archives, "compact must keep an archive directory"
        archived = "\n".join(p.read_text(errors="ignore") for p in archives[0].glob("*.archived"))
        assert '"n": 0' in archived and "- d4" in archived and "- c4" in archived


def main():
    fails = []
    for fn in (test_doctor_thresholds, test_compact_archives_integrity):
        try:
            fn()
        except Exception as e:
            fails.append(f"{fn.__name__}: {type(e).__name__}: {e}")
    if fails:
        print("FAIL: context-budget")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("PASS: context-budget (doctor thresholds + compact archive integrity)")


if __name__ == "__main__":
    main()
