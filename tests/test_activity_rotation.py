#!/usr/bin/env python3
"""
Activity-log auto-rotation (the durable half of the context-budget gate). Telemetry is not memory: the
append-only `.orbit/activity.jsonl` must never grow into token debt (a subagent that reads a 400 KB log
burns ~100k tokens). `activity.emit` now rotates the log once it crosses a byte cap — keeping the last N
events live and archiving the rest under `.orbit/archive/activity/` — automatically, without anyone
running `orbit-context compact`. This test proves it bounds the file and loses no events.

Run: python3 tests/test_activity_rotation.py   (exit 0 = pass)
"""
import contextlib
import importlib.util
import io
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
fails = []


def _load_activity(orbit_dir, max_bytes, keep):
    os.environ["ORBIT_DIR"] = str(orbit_dir)
    os.environ["ORBIT_ACTIVITY_MAX_BYTES"] = str(max_bytes)
    os.environ["ORBIT_ACTIVITY_KEEP"] = str(keep)
    spec = importlib.util.spec_from_file_location("orbit_activity", ROOT / "assets" / "activity.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["orbit_activity"] = m
    spec.loader.exec_module(m)
    return m


def ck(cond, msg):
    if not cond:
        fails.append(msg)


def main():
    with tempfile.TemporaryDirectory() as d:
        orbit = Path(d) / ".orbit"
        cap, keep = 20000, 50
        a = _load_activity(orbit, cap, keep)
        with contextlib.redirect_stdout(io.StringIO()):     # silence emit's inline echo
            for i in range(2000):
                a.emit("builder", "act", "info", f"event {i} " + "x" * 40)

        act = orbit / "activity.jsonl"
        ck(act.exists(), "activity.jsonl must exist")
        live = [ln for ln in act.read_text().splitlines() if ln.strip()]
        arc_dir = orbit / "archive" / "activity"
        archived = []
        if arc_dir.is_dir():
            for f in arc_dir.glob("*.jsonl"):
                archived += [ln for ln in f.read_text().splitlines() if ln.strip()]

        # 1. the live log is bounded BY BYTES (the real guarantee); the event count oscillates between
        #    `keep` and ~cap/bytes-per-event, so assert it's far below what was emitted, not exactly keep.
        ck(act.stat().st_size <= cap, f"live log must stay <= cap {cap}, got {act.stat().st_size}")
        ck(keep <= len(live) < 500, f"live log must stay bounded (≥{keep}, «2000), got {len(live)}")
        # 2. rotation actually happened (archive exists + holds the overflow)
        ck(len(archived) > 0, "older events must be archived, not dropped")
        # 3. NO events lost — live + archived == everything emitted
        ck(len(live) + len(archived) == 2000, f"no events may be lost: {len(live)}+{len(archived)} != 2000")
        # 4. the last event is still live (recency preserved)
        ck("event 1999" in act.read_text(), "the most recent event must remain in the live log")

    if fails:
        print(f"FAIL: activity-rotation {len(fails)} case(s):")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("PASS: activity-rotation (live log bounded to the cap · overflow archived · zero events lost · "
          "recency preserved)")


if __name__ == "__main__":
    main()
