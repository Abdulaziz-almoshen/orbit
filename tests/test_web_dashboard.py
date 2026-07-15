#!/usr/bin/env python3
"""
The visual web dashboard (v0.34.0) — a READ-ONLY local web board over .orbit/. Tests the snapshot builder
directly: correct shape from real files, secrets redacted, malformed/empty/missing files never crash,
and the HTTP surface is read-only (a POST is rejected). (The terminal dashboard, orbit-status, has its
own test_dashboard.py.)

Run: python3 tests/test_web_dashboard.py   (exit 0 = pass)
"""
import importlib.machinery
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DASH = ROOT / "assets" / "orbit-dashboard"
fails = []


def _load(orbit: Path):
    loader = importlib.machinery.SourceFileLoader("orbit_dashboard", str(DASH))  # extensionless file
    spec = importlib.util.spec_from_loader("orbit_dashboard", loader)
    m = importlib.util.module_from_spec(spec)
    sys.modules["orbit_dashboard"] = m
    loader.exec_module(m)
    m.ORBIT = orbit
    return m


def ck(cond, msg):
    if not cond:
        fails.append(msg)


def test_snapshot_shape_and_redaction():
    with tempfile.TemporaryDirectory() as d:
        orbit = Path(d) / ".orbit"
        orbit.mkdir()
        (orbit / "run.json").write_text(json.dumps({"phase": "build", "active_role": "backend",
                                                    "cycle": 2, "tokens": 1234, "confidence": 75}))
        (orbit / "tasks.json").write_text(json.dumps([{"subject": "do X", "status": "completed"}]))
        (orbit / "setup.json").write_text(json.dumps({"product": "Test product"}))
        (orbit / "attention.json").write_text(json.dumps({"session_id": "S1", "source": "Claude Code",
            "message": "Choose A or B", "question_available": True, "answer_in": "Claude terminal"}))
        (orbit / "sessions.json").write_text(json.dumps({"S1": {"session_id": "S1", "model": "Opus"}}))
        (orbit / "activity.jsonl").write_text(
            json.dumps({"who": "backend", "status": "done", "msg": "token=sk-ABCDEF1234567890 ok"}) + "\n"
            + "this is not json{\n")   # malformed line must be skipped, not crash
        m = _load(orbit)
        snap = m.snapshot()
        ck(snap["run"]["phase"] == "build", "snapshot must read run.json")
        ck(len(snap["activity"]) == 1, f"malformed activity line must be skipped (got {len(snap['activity'])})")
        ck("sk-ABCDEF" not in json.dumps(snap), "a secret-looking token must be redacted from the snapshot")
        ck(snap["tasks"][0]["subject"] == "do X", "checklist must come through")
        ck(snap["project"]["name"] == Path(d).name and snap["project"]["product"] == "Test product",
           f"project identity missing: {snap.get('project')}")
        ck(snap["attention"]["message"] == "Choose A or B" and snap["session"]["model"] == "Opus",
           "reporter must surface exact question + matching Claude session/model")
        reporter = snap["reporter"]
        ck(reporter["state"] == "needs_action" and reporter["urgency"] == "critical",
           f"question must become the reporter's top actionable situation: {reporter}")
        ck(reporter["session_id"] == "S1" and reporter["primary_action"]["kind"] == "focus_session",
           f"question action must target its originating session: {reporter}")
        ck(reporter["next_action"] == "Answer in Claude terminal.",
           f"reporter must turn a location into a concrete instruction: {reporter}")
        ck("session=S1" in reporter["primary_action"]["url"],
           f"focus action must carry the exact session id: {reporter['primary_action']}")


def test_reporter_progress_and_stall():
    with tempfile.TemporaryDirectory() as d:
        orbit = Path(d) / ".orbit"; orbit.mkdir()
        old = "2020-01-01T00:00:00Z"
        (orbit / "run.json").write_text(json.dumps({"phase": "act", "active_task": "P5 — staging",
            "tasks_done": 1, "tasks_total": 3, "last_ts": old}))
        (orbit / "tasks.json").write_text(json.dumps([
            {"subject": "P1", "status": "completed"}, {"subject": "P5 — staging", "status": "active"},
            {"subject": "P6 — production", "status": "pending"}]))
        (orbit / "agents.json").write_text(json.dumps({"builder": {"display": "Claude Builder",
            "status": "active", "started_at": old}}))
        m = _load(orbit); reporter = m.snapshot()["reporter"]
        ck(reporter["state"] == "stalled" and reporter["urgency"] == "high",
           f"quiet active work must proactively surface as stalled: {reporter}")
        ck(reporter["current_task"] == "P5 — staging" and reporter["next_task"] == "P6 — production",
           f"reporter must name current and next work: {reporter}")
        ck(reporter["tasks_done"] == 1 and reporter["tasks_total"] == 3 and
           reporter["progress_percent"] == 33, f"reporter progress is wrong: {reporter}")


def test_qa_scene_state():
    """The QA tracer uses exact-HEAD authoritative Git control state, never project mirrors."""
    with tempfile.TemporaryDirectory() as d:
        repo = Path(d)
        orbit = repo / ".orbit"
        orbit.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "orbit@example.test"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "Orbit"], cwd=repo, check=True)
        (repo / "tracked.txt").write_text("one\n")
        subprocess.run(["git", "add", "tracked.txt"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "one"], cwd=repo, check=True)
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
        (orbit / "loop.config.json").write_text(json.dumps(
            {"independent_qa": {"enabled": True, "external_export": {"approved": True},
                                "provider": {"name": "codex"}},
             "approval_checkpoints": {"deploy": "human"}}))
        control = repo / ".git" / "orbit-independent-qa"
        control.mkdir()
        (control / "current.json").write_text(json.dumps({"schema_version": 1, "status": "pass",
            "target_commit": head, "request_id": "M1", "round": 2, "provider": "codex",
            "verdict": "PASS", "score": 9.2,
            "providers": {"codex": {"status": "pass", "verdict": "PASS", "score": 9.2}}}))
        # A forged project mirror must not affect the displayed authoritative state.
        (orbit / "reviews" / "m1").mkdir(parents=True)
        (orbit / "reviews" / "m1" / "round-99.json").write_text(json.dumps(
            {"result": {"verdict": "CHANGES_REQUIRED", "score": 0}}))
        m = _load(orbit)
        qa = m.snapshot()["qa"]
        ck(qa["enabled"] is True and qa["provider"] == "codex", f"qa provider/enabled wrong: {qa}")
        ck(qa["verdict"] == "PASS" and qa["score"] == 9.2, f"qa must read authoritative verdict: {qa}")
        ck(qa["status"] == "awaiting_deploy_approval", f"human deploy gate must remain visible: {qa}")
        ck(qa["providers"]["codex"]["status"] == "pass", "provider animation state must come from control plane")
        # A new commit makes the old PASS stale; it must become queued for a new exact-commit review.
        (repo / "tracked.txt").write_text("two\n")
        subprocess.run(["git", "commit", "-qam", "two"], cwd=repo, check=True)
        stale = m.snapshot()["qa"]
        ck(stale["status"] == "awaiting_review" and stale["verdict"] is None,
           f"stale verdict must not apply to new HEAD: {stale}")
        # disabled → no verdict, never raises
        (orbit / "loop.config.json").write_text(json.dumps({"independent_qa": {"enabled": False}}))
        m2 = _load(orbit)
        qa2 = m2.snapshot()["qa"]
        ck(qa2["enabled"] is False and qa2["status"] == "off", "disabled QA must report off")
        ck(all(x in m.PAGE for x in ("Delivery pipeline", "id=qaPipe", "function updateQA",
                                     "QA · Codex", "QA · Claude", "@keyframes qahandoff")),
           "the dashboard must ship the exact-commit pipeline and real dual-review animation")


def test_empty_and_malformed_never_crash():
    with tempfile.TemporaryDirectory() as d:
        orbit = Path(d) / ".orbit"
        orbit.mkdir()
        (orbit / "run.json").write_text("{ broken json")
        (orbit / "tasks.json").write_text("not even close")
        m = _load(orbit)
        snap = m.snapshot()          # must not raise
        ck(snap["run"] == {} and snap["tasks"] == [], "malformed run/tasks must degrade to empty, not crash")
        ck(json.dumps(snap), "snapshot must be JSON-serializable even when inputs are garbage")


def test_readonly_http_surface():
    with tempfile.TemporaryDirectory() as d:
        orbit = Path(d) / ".orbit"
        orbit.mkdir()
        (orbit / "run.json").write_text(json.dumps({"phase": "test"}))
        proc = subprocess.Popen([sys.executable, "-u", str(DASH), "--port", "0"], cwd=str(Path(d)),
                                env={**os.environ, "ORBIT_DIR": ".orbit", "PYTHONUNBUFFERED": "1"},
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            base, deadline = None, time.time() + 6      # read the auto-picked port from the URL it prints
            while time.time() < deadline:
                line = proc.stdout.readline()
                m = re.search(r"http://127\.0\.0\.1:(\d+)", line or "")
                if m:
                    base = f"http://127.0.0.1:{m.group(1)}"
                    break
            ck(base is not None, "the dashboard must print its URL on start")
            if base:
                html = urllib.request.urlopen(base + "/", timeout=3).read().decode()
                ck("Orbit board" in html, "GET / must serve the board HTML")
                pet = urllib.request.urlopen(base + "/pet", timeout=3).read().decode()
                ck(all(x in pet for x in ("Orbit reporter", "Open board", "primary_action",
                                           "secondary_action", "progress_percent", "messageHandlers?.orbit")),
                   "GET /pet must serve the actionable live situation panel")
                data = json.loads(urllib.request.urlopen(base + "/data", timeout=3).read())
                ck(data["run"].get("phase") == "test", "GET /data must serve the snapshot")
                ck(data.get("project", {}).get("name") == Path(d).name,
                   f"relative ORBIT_DIR must still resolve the project name: {data.get('project')}")
                try:
                    urllib.request.urlopen(urllib.request.Request(base + "/data", data=b"x"), timeout=3)
                    fails.append("a POST must be rejected — the dashboard is read-only")
                except urllib.error.HTTPError as e:
                    ck(e.code == 405, f"POST must be 405 (got {e.code})")
        except Exception as e:
            fails.append(f"[http] {type(e).__name__}: {e}")
        finally:
            proc.terminate()
            proc.wait(timeout=5)


def main():
    for fn in (test_snapshot_shape_and_redaction, test_reporter_progress_and_stall, test_qa_scene_state,
               test_empty_and_malformed_never_crash, test_readonly_http_surface):
        try:
            fn()
        except Exception as e:
            fails.append(f"[{fn.__name__}] raised {type(e).__name__}: {e}")
    if fails:
        print(f"FAIL: web-dashboard {len(fails)} case(s):")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("PASS: web-dashboard (snapshot shape · secret redaction · empty/malformed never crash · read-only HTTP)")


if __name__ == "__main__":
    main()
