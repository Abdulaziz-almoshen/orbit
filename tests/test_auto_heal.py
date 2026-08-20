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
        (target / ".orbit").mkdir(parents=True)
        (target / ".claude").mkdir()
        (target / ".claude/agents").mkdir()
        (target / ".claude/agents/backend-engineer.md").write_text(
            "---\nname: backend-engineer\ntools: Read, Write\n---\n\n# Custom backend worker\nKEEP ME\n")
        (target / ".orbit/setup.json").write_text(json.dumps({
            "orbit_version": "0.28.1", "surfaces": ["api"], "domain_skills": ["domain"]
        }))
        # An installed Orbit project must not drift into a present-but-inactive state.
        settings = {"env": {"CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1"},
                    "hooks": {"PreToolUse": [{"matcher": "Edit|Write|MultiEdit"}]}}
        (target / ".claude/settings.json").write_text(json.dumps(settings))

        first = run(target)
        if not (target / ".orbit/loop.py").exists():
            failures.append("missing engine was not restored")
        if not (target / ".orbit/skills/iterative-repair.md").exists():
            failures.append("missing playbook was not restored")
        if not (target / ".orbit/skills/business-analysis.md").exists():
            failures.append("business-analysis playbook was not backfilled")
        if not (target / ".claude/agents/business-analyst.md").exists():
            failures.append("Business Analyst role was not backfilled")
        if not (target / ".orbit/roles/business-analyst.md").exists():
            failures.append("portable Business Analyst role was not backfilled")
        healed_cfg = json.loads((target / ".orbit/loop.config.json").read_text())
        if healed_cfg.get("capability_enforcement", {}).get("mode") != "strict":
            failures.append("strict capability contract was not backfilled")
        budget_cfg = healed_cfg.get("token_budget", {})
        if (budget_cfg.get("force_synchronous_agents") is not False
                or budget_cfg.get("closeout_fraction") != 0.15
                or "cpo" not in budget_cfg.get("completion_roles", [])):
            failures.append("restored autonomous/protected token-budget defaults were not migrated")
        worker = (target / ".claude/agents/backend-engineer.md").read_text()
        orchestrator = (target / ".claude/agents/orchestrator.md").read_text()
        if "KEEP ME" not in worker or "observer: watchdog" in worker:
            failures.append("auto-heal did not preserve the worker while pruning its redundant observer")
        if "observer: watchdog" not in orchestrator or "observeSubagents: true" not in orchestrator:
            failures.append("auto-heal did not activate the propagated root observer")
        if not (target / ".claude/agents/watchdog.md").exists():
            failures.append("auto-heal did not restore the watchdog agent")
        healed_settings = json.loads((target / ".claude/settings.json").read_text())
        if healed_settings.get("env", {}).get("CLAUDE_CODE_EXPERIMENTAL_OBSERVER_AGENTS") != "1":
            failures.append("auto-heal did not enable the observer environment gate")
        if "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS" in healed_settings.get("env", {}):
            failures.append("auto-heal did not restore background LLM tasks")
        if "Bash(*)" not in healed_settings.get("permissions", {}).get("allow", []):
            failures.append("auto-heal did not remove routine Bash confirmation prompts")
        if healed_settings.get("sandbox", {}).get("allowUnsandboxedCommands") is not False:
            failures.append("auto-heal did not enforce the Bash sandbox boundary")
        setup = json.loads((target / ".orbit/setup.json").read_text())
        if setup.get("orbit_version") != (ROOT / "VERSION").read_text().strip():
            failures.append("setup metadata was not stamped to plugin version")
        wired = json.dumps(healed_settings.get("hooks", {}))
        if "orbit-guard" not in wired or "orbit-resource-hook" not in wired:
            failures.append("auto-heal did not restore required trusted enforcement hooks")

        before = (target / ".orbit/setup.json").read_text()
        second = run(target)
        if (target / ".orbit/setup.json").read_text() != before:
            failures.append("second auto-heal was not idempotent")
        if "already healthy" not in second.stdout:
            failures.append(f"second run was not a no-op: {second.stdout!r}")


    if failures:
        print("FAIL: auto-heal")
        for failure in failures:
            print("  -", failure)
        return 1
    print("PASS: auto-heal (safe files, metadata, idempotency, required hooks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
