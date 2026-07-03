#!/usr/bin/env python3
"""
Tests assets/confidence.py (evidence-based delivery confidence) and assets/lifecycle.py (mode
detection + phase strip). Pure modules — imported directly.

Run: python3 tests/test_confidence_lifecycle.py   (exit 0 = pass)
"""
import importlib.util
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "assets", f"{name}.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    fails = []
    conf = _load("confidence")
    life = _load("lifecycle")

    # --- confidence -------------------------------------------------------------------
    if conf.score([]) != 50:
        fails.append(f"no evidence should be a neutral 50, got {conf.score([])}")
    # tests pass + reviewer pass + safety pending → 50+15+10 = 75
    r = conf.evaluate([{"kind": "test", "status": "pass"}, {"kind": "review", "status": "pass"}])
    if r["score"] != 75:
        fails.append(f"tests+review pass should be 75, got {r['score']}")
    # a failing test outweighs and drops below base
    if conf.score([{"kind": "test", "status": "fail"}]) != 35:
        fails.append(f"failing test should be 35 (50-15), got {conf.score([{'kind':'test','status':'fail'}])}")
    # a safety concern is the heaviest (-20)
    if conf.score([{"kind": "safety", "status": "fail"}]) != 30:
        fails.append("safety fail should be 30 (50-20)")
    # blockers + large diff stack and clamp at 0
    low = conf.score([{"kind": "test", "status": "fail"}], blockers=3, large_unreviewed_diff=True)
    if low != 0:
        fails.append(f"heavy negatives should clamp to 0, got {low}")
    # full green: 50+15+10+10+10+10 = 105 → clamps at 100, and the reason names the passes
    full = conf.evaluate([{"kind": "test", "status": "pass"}, {"kind": "lint", "status": "pass"},
                          {"kind": "review", "status": "pass"}, {"kind": "safety", "status": "pass"},
                          {"kind": "qa", "status": "pass"}])
    if full["score"] != 100:
        fails.append(f"all five green should clamp to 100, got {full['score']}")
    if "pass" not in full["reason"]:
        fails.append(f"reason should name the passing signals: {full['reason']}")
    # malformed signals are ignored, not fatal
    try:
        conf.evaluate([None, {"kind": None}, "garbage", {"status": "pass"}])
    except Exception as e:
        fails.append(f"confidence should tolerate malformed signals, raised {e}")

    # --- lifecycle --------------------------------------------------------------------
    cases = {
        "fix the crash on login": "bug",
        "reproduce the failing test": "bug",
        "redesign the settings screen": "design",
        "improve the button styling and layout": "design",
        "refactor the auth module and rename helpers": "refactor",
        "build the events ETL pipeline and backfill": "data",
        "add a logout button": "feature",
        "implement a new export endpoint": "feature",
    }
    for text, want in cases.items():
        got = life.detect(text)
        if got != want:
            fails.append(f"detect({text!r}) = {got}, expected {want}")
    # phase strip highlights the current phase
    s = life.strip("feature", "build")
    if "[Build]" not in s or "Discover" not in s or "Report" not in s:
        fails.append(f"strip did not bracket the current phase: {s}")
    # unknown mode falls back to feature, never raises
    if life.phases("nonsense") != life.phases("feature"):
        fails.append("unknown mode should fall back to feature phases")

    if fails:
        print("FAIL: confidence/lifecycle")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("PASS: confidence/lifecycle (evidence scoring clamps + reasons; mode detect + phase strip)")


if __name__ == "__main__":
    main()
