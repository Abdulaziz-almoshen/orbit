#!/usr/bin/env python3
"""
Tests the decision-card flow (Phase 6): activity.ask() writes .orbit/pending-question.json + pins
run.json.blocked_question with the CLEAN title; the dashboard renders the card (options + the
recommended marker); activity.resolve_question() clears both and unblocks.

Run: python3 tests/test_decision_card.py   (exit 0 = pass)
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STATUS = os.path.join(ROOT, "assets", "orbit-status")


def _load_activity(orbit_dir):
    os.environ["ORBIT_DIR"] = orbit_dir
    spec = importlib.util.spec_from_file_location("activity_dc", os.path.join(ROOT, "assets", "activity.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    fails = []
    with tempfile.TemporaryDirectory() as d:
        orbit = os.path.join(d, ".orbit")
        os.makedirs(orbit)
        a = _load_activity(orbit)
        a.new_run(mode="feature")
        a.ask("Choose implementation path", why="Two routes differ in risk and time.",
              recommended="A",
              options=[{"id": "A", "label": "Small patch", "tradeoff": "Fastest, lower scope"},
                       {"id": "B", "label": "Refactor first", "tradeoff": "Cleaner, slower"}])

        card = json.loads(open(os.path.join(orbit, "pending-question.json")).read())
        if card["title"] != "Choose implementation path" or card["recommended"] != "A" \
                or len(card["options"]) != 2:
            fails.append(f"pending-question.json malformed: {card}")
        run = json.loads(open(os.path.join(orbit, "run.json")).read())
        if run.get("blocked_question") != "Choose implementation path":
            fails.append(f"run.json blocked_question should be the CLEAN title, got {run.get('blocked_question')!r}")

        # dashboard renders the card
        r = subprocess.run([sys.executable, STATUS], capture_output=True, text=True,
                           env={**os.environ, "ORBIT_DIR": orbit, "NO_COLOR": "1"}, timeout=10)
        for needle in ("Decision needed", "Choose implementation path", "Small patch",
                       "recommended", "Refactor first"):
            if needle not in r.stdout:
                fails.append(f"dashboard missing decision-card element '{needle}'")

        # --json surfaces the structured card
        j = subprocess.run([sys.executable, STATUS, "--json"], capture_output=True, text=True,
                           env={**os.environ, "ORBIT_DIR": orbit, "NO_COLOR": "1"}, timeout=10)
        obj = json.loads(j.stdout)
        if not obj["run"].get("pending_question"):
            fails.append("--json did not include the pending_question card")

        # resolve → both cleared
        a.resolve_question("A")
        if os.path.exists(os.path.join(orbit, "pending-question.json")):
            fails.append("resolve_question did not remove pending-question.json")
        run = json.loads(open(os.path.join(orbit, "run.json")).read())
        if run.get("blocked_question") is not None:
            fails.append(f"resolve_question did not unblock: {run.get('blocked_question')!r}")

    if fails:
        print("FAIL: decision-card")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("PASS: decision-card (ask writes+pins clean title, dashboard renders card, resolve clears)")


if __name__ == "__main__":
    main()
