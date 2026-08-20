#!/usr/bin/env python3
"""
Tests scaffold.install_hooks (Phase 6.3 — the settings-clobber guard):
 - A corrupt/unparseable settings.json is NEVER overwritten; hooks are not installed.
 - A valid settings.json gets both hooks, is backed up first, and merges idempotently
   (re-running does not double-add).
 - A user's own unrelated settings keys survive the merge.

Run: python3 tests/test_install_hooks.py   (exit 0 = pass)
"""
import importlib.util
import json
import os
import sys
import tempfile

spec = importlib.util.spec_from_file_location(
    "scaffold", os.path.join(os.path.dirname(__file__), "..", "scripts", "scaffold.py"))
sc = importlib.util.module_from_spec(spec)
sys.modules["scaffold"] = sc
spec.loader.exec_module(sc)
Path = sc.Path


def main():
    fails = []

    # 1. corrupt settings.json is preserved verbatim, no hooks, no backup
    with tempfile.TemporaryDirectory() as d:
        t = Path(d)
        (t / ".claude").mkdir()
        s = t / ".claude" / "settings.json"
        corrupt = '{ "hooks": { broken '
        s.write_text(corrupt)
        sc.install_hooks(t)
        if s.read_text() != corrupt:
            fails.append("corrupt settings.json was modified (clobber guard failed)")
        if list((t / ".claude").glob("settings.json.bak*")):
            fails.append("a backup was written for a file we refused to touch")

    # 2. valid settings.json → both hooks, backed up, user keys survive
    with tempfile.TemporaryDirectory() as d:
        t = Path(d)
        (t / ".claude").mkdir()
        s = t / ".claude" / "settings.json"
        s.write_text(json.dumps({"model": "claude-x", "hooks": {"Stop": [{"keep": 1}]},
                                 "env": {"CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1"}}))
        sc.install_hooks(t)
        data = json.loads(s.read_text())
        if data.get("model") != "claude-x":
            fails.append("user's unrelated setting was dropped")
        if "Stop" not in data.get("hooks", {}):
            fails.append("user's unrelated hook was dropped")
        if "PreToolUse" not in data["hooks"] or "UserPromptSubmit" not in data["hooks"]:
            fails.append("Orbit hooks were not installed into a valid file")
        wired = json.dumps(data["hooks"])
        for token in ("orbit-resource-hook", "PreCompact", "PostCompact"):
            if token not in wired and token not in data["hooks"]:
                fails.append(f"resource-governor hook missing: {token}")
        env = data.get("env", {})
        if env.get("CLAUDE_AUTOCOMPACT_PCT_OVERRIDE") != "70":
            fails.append("proactive compaction threshold was not installed")
        if "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS" in env:
            fails.append("Orbit did not restore background LLM task execution")
        if data.get("permissions", {}).get("defaultMode") != "acceptEdits":
            fails.append("routine in-repo edits were not made non-interactive")
        if "Bash(*)" not in data.get("permissions", {}).get("allow", []):
            fails.append("sandboxed Bash was not made non-interactive")
        # v0.62-0.67 force-wrote a sandbox lockdown (enabled + allowUnsandboxedCommands=false)
        # that silently broke SSH/deploys in scaffolded repos. The contract is now the opposite:
        # Orbit NEVER writes sandbox restrictions — that envelope belongs to the user alone.
        if "sandbox" in data:
            fails.append(f"scaffold wrote a sandbox policy into user settings: {data['sandbox']}")

        if not list((t / ".claude").glob("settings.json.bak*")):
            fails.append("valid file was not backed up before edit")

    # 1c. migration: the exact lockdown v0.62 imposed is removed; a customized block is sacred
    with tempfile.TemporaryDirectory() as d:
        t2 = Path(d)
        (t2 / ".claude").mkdir()
        imposed = {"sandbox": {"enabled": True, "autoAllowBashIfSandboxed": True,
                               "allowUnsandboxedCommands": False}}
        (t2 / ".claude" / "settings.json").write_text(json.dumps(imposed))
        sc.install_hooks(t2)
        healed = json.loads((t2 / ".claude" / "settings.json").read_text())
        if "sandbox" in healed:
            fails.append(f"the v0.62 imposed lockdown was not migrated away: {healed['sandbox']}")
    with tempfile.TemporaryDirectory() as d:
        t3 = Path(d)
        (t3 / ".claude").mkdir()
        custom = {"sandbox": {"enabled": True, "autoAllowBashIfSandboxed": True,
                              "allowUnsandboxedCommands": False,
                              "allowedHosts": ["129.212.193.243"]}}
        (t3 / ".claude" / "settings.json").write_text(json.dumps(custom))
        sc.install_hooks(t3)
        kept = json.loads((t3 / ".claude" / "settings.json").read_text()).get("sandbox", {})
        if kept.get("allowedHosts") != ["129.212.193.243"] or kept.get("enabled") is not True:
            fails.append(f"a user-customized sandbox block was altered: {kept}")

        # 3. idempotent — re-run does not double-add (compare counts across runs, not a magic number,
        #    so the check survives the hook set growing — e.g. the v0.30.0 writer-lock entries)
        n_pre, n_ups = len(data["hooks"]["PreToolUse"]), len(data["hooks"]["UserPromptSubmit"])
        sc.install_hooks(t)
        data2 = json.loads(s.read_text())
        if len(data2["hooks"]["PreToolUse"]) != n_pre or len(data2["hooks"]["UserPromptSubmit"]) != n_ups:
            fails.append("re-running install_hooks double-added a hook")
        if data2.get("permissions", {}).get("allow", []).count("Bash(*)") != 1:
            fails.append("re-running install_hooks duplicated Bash auto-approval")

    # 4. Reporter-only activation observes permissions but never installs the Bash safety/ask hook.
    with tempfile.TemporaryDirectory() as d:
        t = Path(d); (t / ".claude").mkdir()
        s = t / ".claude" / "settings.json"; s.write_text("{}")
        sc.install_hooks(t, reporter_only=True)
        data = json.loads(s.read_text())
        if "PermissionRequest" not in data.get("hooks", {}):
            fails.append("reporter-only activation did not wire exact permission-request telemetry")
        if data.get("hooks", {}).get("PreToolUse"):
            fails.append("reporter-only activation installed a PreToolUse/Bash hook")
        if "orbit-statusline" not in json.dumps(data.get("statusLine", {})):
            fails.append("reporter-only activation did not wire the terminal reporter")

    if fails:
        print("FAIL: install_hooks")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("PASS: install_hooks (clobber guard + idempotent merge + user keys preserved)")


if __name__ == "__main__":
    main()
