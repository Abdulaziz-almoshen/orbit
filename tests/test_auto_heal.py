#!/usr/bin/env python3
"""Regression tests for the preamble's non-interactive project self-heal."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAFFOLD = ROOT / "scripts" / "scaffold.py"


def run(target):
    return subprocess.run(
        [sys.executable, str(SCAFFOLD), "--auto-heal", "--target", str(target)],
        text=True, capture_output=True, check=True,
    )


def main():
    failures = []
    with tempfile.TemporaryDirectory() as td:
        target = Path(td)
        (target / ".orbit/locks").mkdir(parents=True)
        (target / ".claude").mkdir()
        (target / ".claude/agents").mkdir()
        (target / ".claude/agents/backend-engineer.md").write_text(
            "---\nname: backend-engineer\ntools: Read, Write\n---\n\n# Custom backend worker\nKEEP ME\n")
        (target / ".orbit/setup.json").write_text(json.dumps({
            "orbit_version": "0.28.1", "surfaces": ["api"], "domain_skills": ["domain"]
        }))
        # A user who removed Bash hooks must not have them silently restored by healing.
        settings = {"hooks": {"PreToolUse": [{"matcher": "Edit|Write|MultiEdit"}]}}
        (target / ".claude/settings.json").write_text(json.dumps(settings))

        first = run(target)
        if not (target / ".orbit/loop.py").exists():
            failures.append("missing engine was not restored")
        if not (target / ".orbit/skills/iterative-repair.md").exists():
            failures.append("missing playbook was not restored")
        worker = (target / ".claude/agents/backend-engineer.md").read_text()
        if "observer: watchdog" not in worker or "KEEP ME" not in worker:
            failures.append("auto-heal did not activate the observer while preserving the worker body")
        if not (target / ".claude/agents/watchdog.md").exists():
            failures.append("auto-heal did not restore the watchdog agent")
        healed_settings = json.loads((target / ".claude/settings.json").read_text())
        if healed_settings.get("env", {}).get("CLAUDE_CODE_EXPERIMENTAL_OBSERVER_AGENTS") != "1":
            failures.append("auto-heal did not enable the observer environment gate")
        setup = json.loads((target / ".orbit/setup.json").read_text())
        if setup.get("orbit_version") != (ROOT / "VERSION").read_text().strip():
            failures.append("setup metadata was not stamped to plugin version")
        if any(h.get("matcher") == "Bash" for h in json.loads(
                (target / ".claude/settings.json").read_text()).get("hooks", {}).get("PreToolUse", [])):
            failures.append("auto-heal re-enabled a user-disabled Bash hook")

        before = (target / ".orbit/setup.json").read_text()
        second = run(target)
        if (target / ".orbit/setup.json").read_text() != before:
            failures.append("second auto-heal was not idempotent")
        if "already healthy" not in second.stdout:
            failures.append(f"second run was not a no-op: {second.stdout!r}")

        (target / ".orbit/locks/active-writer.json").write_text(json.dumps({
            "heartbeat_at": "2099-01-01T00:00:00Z", "ttl_seconds": 1800
        }))
        locked_before = (target / ".orbit/setup.json").read_text()
        locked = run(target)
        if (target / ".orbit/setup.json").read_text() != locked_before:
            failures.append("active writer lock did not prevent auto-heal writes")
        if "active writer lock" not in locked.stdout:
            failures.append(f"lock preservation was not reported: {locked.stdout!r}")

    if failures:
        print("FAIL: auto-heal")
        for failure in failures:
            print("  -", failure)
        return 1
    print("PASS: auto-heal (safe files, metadata, idempotency, disabled hooks, active lock)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
