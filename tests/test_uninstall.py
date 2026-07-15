#!/usr/bin/env python3
"""
Tests bin/orbit-uninstall: it removes exactly the Orbit-authored files + Orbit-tagged hooks,
preserves the user's CLAUDE.md and their own settings, and is safe to re-run.

Run: python3 tests/test_uninstall.py   (exit 0 = pass)
"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNINSTALL = os.path.join(ROOT, "bin", "orbit-uninstall")
SCAFFOLD = os.path.join(ROOT, "scripts", "scaffold.py")


def main():
    fails = []
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["git", "init", "-q", d], check=True)
        subprocess.run([sys.executable, SCAFFOLD, "--install-hooks", "--target", d],
                       capture_output=True, check=True)
        # a user CLAUDE.md and a user-owned hook that must survive
        claude_md = os.path.join(d, "CLAUDE.md")
        with open(claude_md, "w") as f:
            f.write("# my project\nuser-authored content that must never be deleted\n")
        settings = os.path.join(d, ".claude", "settings.json")
        data = json.load(open(settings))
        data.setdefault("hooks", {}).setdefault("Stop", []).append(
            {"hooks": [{"type": "command", "command": "echo mine"}]})  # a non-orbit hook
        data["model"] = "user-choice"
        json.dump(data, open(settings, "w"), indent=2)
        keep_file = os.path.join(d, "src.py")
        open(keep_file, "w").write("print(1)\n")

        subprocess.run([UNINSTALL, "--force"], cwd=d, capture_output=True, text=True)

        # removed
        for gone in (".orbit", "scripts/ralph_loop.sh", "scripts/orbit-status", "scripts/orbit-independent-qa"):
            if os.path.exists(os.path.join(d, gone)):
                fails.append(f"orbit-uninstall left {gone} behind")
        # preserved
        if not os.path.exists(claude_md) or "user-authored" not in open(claude_md).read():
            fails.append("CLAUDE.md was deleted or altered (must be left alone)")
        if not os.path.exists(keep_file):
            fails.append("an unrelated user file was deleted")
        after = json.load(open(settings))
        if after.get("model") != "user-choice":
            fails.append("user's settings key was dropped")
        blob = json.dumps(after.get("hooks", {}))
        if "echo mine" not in blob:
            fails.append("user's own (non-Orbit) hook was removed")
        if ".orbit/" in blob:
            fails.append("an Orbit-tagged hook survived the uninstall")
        if not any(x.startswith("settings.json.bak") for x in os.listdir(os.path.join(d, ".claude"))):
            fails.append("no settings.json backup was written before editing hooks")

        # idempotent — a second run is clean and must not error
        r2 = subprocess.run([UNINSTALL, "--force"], cwd=d, capture_output=True, text=True)
        if r2.returncode != 0:
            fails.append(f"second uninstall run errored: {r2.stderr.strip()[:200]}")

    if fails:
        print("FAIL: uninstall")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("PASS: uninstall (removes Orbit files + Orbit hooks, preserves CLAUDE.md + user settings, idempotent)")


if __name__ == "__main__":
    main()
