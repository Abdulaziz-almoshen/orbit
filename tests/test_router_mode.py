#!/usr/bin/env python3
"""Router always-mode (v0.51.0): every real request engages the loop, visibly. Tests the hook
end-to-end (stdin JSON → injected context), per mode:
- always (default): ambiguous → TASK; short imperative ("restart it") → TASK; question → direct
  answer WITH a visible marker; acks/negations/slash stay silent.
- smart: the conservative behavior — ambiguous soft, no markers.

Run: python3 tests/test_router_mode.py   (exit 0 = pass)
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "assets" / "checks" / "route.py"
fails = []


def ck(cond, msg):
    if not cond:
        fails.append(msg)


def run_hook(prompt, orbit_cfg=None):
    with tempfile.TemporaryDirectory() as d:
        orbit = Path(d) / ".orbit"
        orbit.mkdir()
        if orbit_cfg is not None:
            (orbit / "loop.config.json").write_text(json.dumps(orbit_cfg))
        proc = subprocess.run([sys.executable, str(HOOK)], text=True, capture_output=True,
                              input=json.dumps({"prompt": prompt, "cwd": d}))
        if not proc.stdout.strip():
            return None
        return json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"]


def test_always_mode_default():
    ctx = run_hook("the dashboard feels slow")            # ambiguous phrasing
    ck(ctx is not None and "default lane: TASK" in ctx,
       "always (default): ambiguous phrasing must engage the loop as TASK")
    ck(ctx is not None and "loop engaged" in ctx,
       "always: the TASK lane must demand the visible ⏣ orbit marker")

    ctx = run_hook("restart it")                          # short imperative, no matched verb needed
    ck(ctx is not None and "default lane: TASK" in ctx,
       "always: a short imperative must engage the loop, not be skipped")

    ctx = run_hook("what does the dispatcher do")
    ck(ctx is not None and "direct answer" in ctx and "QUESTION" in ctx,
       "always: a question is answered directly but VISIBLY (marker included)")

    for silent in ("yes", "go ahead", "don't push this", "/orbit", ""):
        ck(run_hook(silent) is None, f"always: {silent!r} must stay silent")


def test_smart_mode_optout():
    cfg = {"router": {"mode": "smart"}}
    ctx = run_hook("the dashboard feels slow", cfg)
    ck(ctx is not None and "unclassified" in ctx,
       "smart: ambiguous must get the soft directive, not forced TASK")
    ck(run_hook("restart it", cfg) is not None and "TASK" in run_hook("restart it", cfg),
       "restart is now a task verb even in smart mode")
    ctx = run_hook("what does the dispatcher do", cfg)
    ck(ctx is not None and "direct answer" not in ctx,
       "smart: questions carry no marker (conservative behavior preserved)")


def main():
    for fn in (test_always_mode_default, test_smart_mode_optout):
        try:
            fn()
        except Exception as e:
            fails.append(f"[{fn.__name__}] raised {type(e).__name__}: {e}")
    if fails:
        print(f"FAIL: router-mode ({len(fails)})")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("PASS: router-mode (always engages loop visibly · short imperatives routed · acks silent · smart opt-out)")


if __name__ == "__main__":
    main()
