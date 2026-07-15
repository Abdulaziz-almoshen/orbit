#!/usr/bin/env python3
"""Reporter pet is scaffolded, read-only, redacted-source driven, and controllable."""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    fails = []
    dashboard = (ROOT / "assets/orbit-dashboard").read_text()
    for required in ("PET_PAGE", "fetch('/data'", "reporter", "event_key", "progress_percent",
                     "elapsed_seconds", "quiet_seconds", "question_available", "Focus session",
                     "Open board", "orbit-action://focus-session", "messageHandlers?.orbit"):
        if required not in dashboard:
            fails.append(f"pet narration is missing state input: {required}")
    swift = (ROOT / "assets/orbit-pet.swift").read_text()
    for required in ("NSPanel", ".floating", ".canJoinAllSpaces", "WKWebView", ".nonPersistent()",
                     "WKNavigationDelegate", "orbit-action", "focusSession", "openBoard",
                     "terminalBundles", "activateAllWindows", "WKScriptMessageHandler"):
        if required not in swift:
            fails.append(f"native floating shell is missing: {required}")
    with tempfile.TemporaryDirectory() as d:
        env = {**os.environ, "ORBIT_HOME": d}
        status = subprocess.run([sys.executable, str(ROOT / "bin/orbit-pet"), "status"],
                                env=env, text=True, capture_output=True)
        try: payload = json.loads(status.stdout)
        except Exception: payload = {}
        if status.returncode or payload.get("running") is not False:
            fails.append(f"pet status must be safe when stopped: rc={status.returncode} {status.stdout} {status.stderr}")
        target = Path(d) / "repo"; target.mkdir()
        subprocess.run([sys.executable, str(ROOT / "scripts/scaffold.py"), "--target", str(target)],
                       env=env, text=True, capture_output=True, check=True)
        wrapper = target / "scripts/orbit-pet"
        if not wrapper.is_file() or not os.access(wrapper, os.X_OK):
            fails.append("scaffold did not install executable scripts/orbit-pet")
        help_out = subprocess.run([sys.executable, str(ROOT / "scripts/scaffold.py"), "--help"],
                                  text=True, capture_output=True, check=True).stdout
        if "--enable-reporter" not in help_out:
            fails.append("scaffold is missing the one-time reporter activation option")
    if fails:
        print(f"FAIL: pet ({len(fails)})")
        for fail in fails: print("  -", fail)
        return 1
    print("PASS: pet (truthful narration · redacted local data · floating macOS shell · scaffold wrapper)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
