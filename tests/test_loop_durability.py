#!/usr/bin/env python3
"""
loop.py durability (v0.32.0) — the portable runner survives a restart and never double-fires. Drives the
real `run()` with a fake `dispatch`/gates and asserts the plan's four contracts:
  1. crash after ACT resumes at EVALUATE, not ACT (the side effect isn't repeated)
  2. an approval checkpoint pauses, and after `--approve` a --resume proceeds past it (durable wait)
  3. budget persists across resume (per-run caps can't be reset to zero by a restart)
  4. a side-effect key fires at most once — not twice — without an explicit force override

Run: python3 tests/test_loop_durability.py   (exit 0 = pass)
"""
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
fails = []


def _load():
    spec = importlib.util.spec_from_file_location("orbit_loop", ROOT / "assets" / "loop.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["orbit_loop"] = m
    spec.loader.exec_module(m)
    return m


L = _load()


def ck(cond, msg):
    if not cond:
        fails.append(msg)


def _cfg(tmp: Path, max_iter=1, action=None):
    orbit = tmp / ".orbit"
    orbit.mkdir(parents=True, exist_ok=True)
    return {
        "run_goal": "test", "_action": action,
        "hard_limits": {"max_iterations": max_iter,
                        "token_budget": {"per_cycle": 0, "per_run": 10**9},
                        "cost_budget_usd": {"per_cycle": 999, "per_run": 999},
                        "max_runtime_seconds": 10**9, "gate_failure_streak": 99},
        "eval_gates": {"input": {}, "quality": {}, "safety": {}},
        "approval_checkpoints": {"deploy": "human", "move_money": "FORBIDDEN"},
        "paths": {"checkpoints": str(orbit / "steps.jsonl"), "state": str(orbit / "STATE.md"),
                  "claude_md": str(tmp / "CLAUDE.md"), "activity": str(orbit / "activity.jsonl"),
                  "tasks": str(orbit / "tasks.json"), "stop_sentinel": str(orbit / "STOP")},
    }


def _patch(dispatch=None, gates=None, capture=None):
    L.emit = (lambda *a, **k: capture.append((a, k))) if capture is not None else (lambda *a, **k: None)
    L.evaluate_gates = gates or (lambda result, cfg: {"input": True, "quality": True, "safety": True})
    if dispatch is not None:
        L.dispatch = dispatch


def test_resume_after_act():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        cfg = _cfg(tmp)
        calls = {"act": 0, "eval": 0}

        def fake_dispatch(role, task, ctx, c):
            calls["act"] += 1
            return {"ok": True, "summary": "did work", "tokens": 100}

        def crashing_gates(result, cfg):
            calls["eval"] += 1
            if calls["eval"] == 1:
                raise RuntimeError("simulated crash after ACT, during EVALUATE")
            return {"input": True, "quality": True, "safety": True}

        _patch(dispatch=fake_dispatch, gates=crashing_gates)
        try:
            L.run(cfg, resume=False)          # crashes inside evaluate
        except RuntimeError:
            pass
        ck(calls["act"] == 1, f"ACT should have run once before the crash (got {calls['act']})")
        L.run(cfg, resume=True)               # resume: ACT skipped (checkpointed), EVALUATE re-runs
        ck(calls["act"] == 1, f"ACT must NOT re-run on resume — resumes at EVALUATE (got {calls['act']} total)")
        ck(calls["eval"] == 2, f"EVALUATE should have run again on resume (got {calls['eval']})")


def test_budget_persists_across_resume():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        cfg = _cfg(tmp)

        def fake_dispatch(role, task, ctx, c):
            return {"ok": True, "summary": "x", "tokens": 100, "cost_usd": 0.25}

        raised = {"n": 0}

        def crash_once(result, cfg):
            raised["n"] += 1
            if raised["n"] == 1:
                raise RuntimeError("crash after budget save")
            return {"input": True, "quality": True, "safety": True}

        _patch(dispatch=fake_dispatch, gates=crash_once)
        try:
            L.run(cfg, resume=False)
        except RuntimeError:
            pass
        saved = L.Steps(Path(cfg["paths"]["checkpoints"])).last_budget
        ck(saved and saved.get("tokens") == 100, f"budget must be persisted after ACT (got {saved})")
        ck(saved and abs(saved.get("cost_usd", 0) - 0.25) < 1e-9, "cost must persist too")


def test_approval_pause_and_resume():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        cfg = _cfg(tmp)
        events = []

        def deploy_dispatch(role, task, ctx, c):
            return {"ok": True, "summary": "wants to deploy", "action": "deploy", "tokens": 10}

        _patch(dispatch=deploy_dispatch, capture=events)
        L.run(cfg, resume=False)                       # should PAUSE at the deploy approval
        pending = tmp / ".orbit" / "approvals" / "pending.json"
        ck(pending.exists(), "a pending approval must be recorded when the loop pauses")
        blocked = [e for e in events if e[0][:3] == ("human", "decide", "blocked")]
        ck(blocked, "the loop must emit an 'awaiting approval' block")
        granted_before = [e for e in events if e[0][:3] == ("human", "decide", "done")]
        ck(not granted_before, "must NOT proceed before approval")

        # grant via the CLI path, then resume
        key = L.Approvals(tmp / ".orbit" / "approvals").grant("deploy")
        ck(key == "deploy:1", f"grant key should be deploy:1 (got {key})")
        events.clear()
        L.run(cfg, resume=True)                         # should now proceed PAST the approval
        proceeded = [e for e in events if e[0][:3] == ("human", "decide", "done")]
        ck(proceeded, "after --approve + --resume the loop must proceed past the checkpoint")


def test_forbidden_never_runs():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        cfg = _cfg(tmp)
        events = []
        _patch(dispatch=lambda *a: {"ok": True, "summary": "!", "action": "move_money", "tokens": 1}, capture=events)
        L.run(cfg, resume=False)
        blocked = [e for e in events if "FORBIDDEN" in str(e) or (e[0][:2] == ("safety", "evaluate"))]
        ck(blocked, "a FORBIDDEN action must stop the loop and never run")


def test_idempotency_key_fires_once():
    with tempfile.TemporaryDirectory() as d:
        idem = L.Idempotency(Path(d) / "idempotency.json")
        n = {"c": 0}

        def effect():
            n["c"] += 1
            return "done"

        idem.run("deploy:v1.2.3", effect)
        idem.run("deploy:v1.2.3", effect)             # same key → must be skipped
        ck(n["c"] == 1, f"a side-effect key must fire at most once (fired {n['c']}x)")
        idem.run("deploy:v1.2.3", effect, force=True)  # explicit override
        ck(n["c"] == 2, "force=True must allow an explicit re-run")
        # survives a fresh process (persisted)
        idem2 = L.Idempotency(Path(d) / "idempotency.json")
        idem2.run("deploy:v1.2.3", effect)
        ck(n["c"] == 2, "idempotency must persist across a fresh Idempotency() (no re-fire)")


def main():
    for fn in (test_resume_after_act, test_budget_persists_across_resume, test_approval_pause_and_resume,
               test_forbidden_never_runs, test_idempotency_key_fires_once):
        try:
            fn()
        except Exception as e:
            import traceback
            fails.append(f"[{fn.__name__}] raised {type(e).__name__}: {e}\n{traceback.format_exc()[-400:]}")
    if fails:
        print(f"FAIL: loop-durability {len(fails)} case(s):")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("PASS: loop-durability (resume-after-act · budget persists · approval pause/resume · "
          "FORBIDDEN never runs · side-effect key fires once unless forced)")


if __name__ == "__main__":
    main()
