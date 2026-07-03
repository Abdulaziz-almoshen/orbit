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
        s.write_text(json.dumps({"model": "claude-x", "hooks": {"Stop": [{"keep": 1}]}}))
        sc.install_hooks(t)
        data = json.loads(s.read_text())
        if data.get("model") != "claude-x":
            fails.append("user's unrelated setting was dropped")
        if "Stop" not in data.get("hooks", {}):
            fails.append("user's unrelated hook was dropped")
        if "PreToolUse" not in data["hooks"] or "UserPromptSubmit" not in data["hooks"]:
            fails.append("Orbit hooks were not installed into a valid file")
        if not list((t / ".claude").glob("settings.json.bak*")):
            fails.append("valid file was not backed up before edit")

        # 3. idempotent — re-run does not double-add
        sc.install_hooks(t)
        data2 = json.loads(s.read_text())
        if len(data2["hooks"]["PreToolUse"]) != 1 or len(data2["hooks"]["UserPromptSubmit"]) != 1:
            fails.append("re-running install_hooks double-added a hook")

    if fails:
        print("FAIL: install_hooks")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("PASS: install_hooks (clobber guard + idempotent merge + user keys preserved)")


if __name__ == "__main__":
    main()
