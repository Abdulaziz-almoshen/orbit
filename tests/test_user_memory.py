#!/usr/bin/env python3
"""User-memory intake, five-request clock, review hygiene, Stop gate, and CPO binding."""
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILS = []


def ck(value, message):
    if not value:
        FAILS.append(message)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def seeded(root):
    orbit = root / ".orbit"
    (orbit / "skills").mkdir(parents=True)
    (orbit / "checks").mkdir()
    (orbit / "skills" / "user-model.md").write_text("# User model\n\n## Signals\n")
    return orbit


def test_intake_and_review():
    memory = load(ROOT / "assets/checks/user_memory.py", "user_memory_test")
    with tempfile.TemporaryDirectory() as d:
        orbit = seeded(Path(d))
        ck(not memory.status(orbit, require_latest=True)["passed"],
           "an untouched seed is not a delivery review; shipping must require an explicit checkpoint")
        for i in range(4):
            result = memory.record_request(orbit, f"Please inspect item {i}")
        ck(result["requests_since_review"] == 4 and not result["review_due"],
           "review must not be overdue before request five")
        result = memory.record_request(orbit, "Please inspect item five")
        ck(result["review_due"] and result["total_requests"] == 5,
           "the fifth real request must mechanically require review")
        result = memory.review(orbit, ["all"], "checkpoint", "No new durable user signal.")
        ck(result["passed"] and result["last_reviewed_request"] == 5,
           "an honest no-signal checkpoint must reset the five-request clock")

        result = memory.record_request(
            orbit, "Why you're doing this? Always run the full dependency tests. token=verysecretvalue")
        ck(result["pending_event_ids"] == ["U6"] and not result["passed"],
           "a correction/always signal must be captured immediately and block review status")
        ledger = (orbit / "memory/user-events.jsonl").read_text()
        ck("verysecretvalue" not in ledger and "[redacted]" in ledger,
           "captured event excerpts must scrub labeled secrets")
        try:
            memory.review(orbit, ["all"], "checkpoint", "nothing")
            ck(False, "checkpoint must not bypass a pending important event")
        except ValueError:
            pass
        result = memory.review(orbit, ["U6"], "promote",
                               "Before shipping, run the full dependency regression suite.")
        ck(result["passed"] and "full dependency regression" in
           (orbit / "skills/user-model.md").read_text(),
           "reviewed user-stated evidence must promote as a project signal")


def stop_hook(cwd):
    proc = subprocess.run([sys.executable, str(ROOT / "assets/checks/orbit-stop-check.py")],
                          input=json.dumps({"cwd": str(cwd)}), text=True, capture_output=True,
                          env={**os.environ, "CLAUDE_PROJECT_DIR": str(cwd)})
    return json.loads(proc.stdout) if proc.stdout.strip() else None


def test_stop_blocks_stale_memory():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d); orbit = seeded(root)
        (orbit / "checks/user_memory.py").write_bytes((ROOT / "assets/checks/user_memory.py").read_bytes())
        (orbit / "loop.config.json").write_text(json.dumps({
            "user_memory": {"enabled": True, "require_review_before_delivery": True,
                            "max_requests_between_reviews": 5},
            "cpo_acceptance": {"enabled": False}, "delivery_quality": {"enabled": False}
        }))
        memory = load(orbit / "checks/user_memory.py", "user_memory_stop_test")
        memory.record_request(orbit, "Always inspect the exact UI before shipping")
        (orbit / ".last-task-route").write_text("route")
        route = {"phase": "route", "status": "start"}
        work = [{"phase": "act", "status": "done"} for _ in range(4)]
        (orbit / "activity.jsonl").write_text("\n".join(json.dumps(x) for x in [route, *work]))
        time.sleep(0.02)
        (orbit / "tasks.json").write_text("[]")
        out = stop_hook(root)
        ck(out and "USER MEMORY GATE" in out.get("reason", ""),
           "substantial delivery must stop on pending/latest-unreviewed user memory")
        memory.review(orbit, ["U1"], "promote", "Inspect the exact UI before shipping.")
        ck(stop_hook(root) is None, "a current cleared memory checkpoint must release the Stop gate")


def test_cpo_binds_memory_sha():
    loop = load(ROOT / "assets/loop.py", "orbit_loop_memory_test")
    with tempfile.TemporaryDirectory() as d:
        root = Path(d); vdir = root / "cpo"; vdir.mkdir()
        checkpoint = root / "checkpoint.json"
        checkpoint.write_text(json.dumps({"total_requests": 3, "last_reviewed_request": 3,
                                          "pending_event_ids": [],
                                          "last_reviewed_at": "2026-08-07T00:00:00Z"}))
        cfg = {"cpo_acceptance": {"enabled": True, "require_delivery_evidence": False,
                                  "require_user_memory_checkpoint": True},
               "user_memory": {"enabled": True},
               "paths": {"cpo_verdicts": str(vdir), "user_memory_checkpoint": str(checkpoint)}}
        grill = [{"lens": lens, "verdict": "clean", "evidence": "checked"} for lens in
                 ("domain", "policy", "product", "design_ux", "system_design", "slop")]
        verdict = {"commit": "abc", "verdict": "ACCEPT",
                   "basis": {"skills": ["user-model signal U1"]}, "grill": grill}
        (vdir / "round-1.json").write_text(json.dumps(verdict))
        result = loop.evaluate_cpo_acceptance({"commit": "abc"}, cfg)
        ck(result.get("status") == "user_memory_unbound",
           "CPO must reject an ACCEPT that does not cite the exact memory checkpoint")
        verdict["user_memory"] = {"path": str(checkpoint),
                                  "last_reviewed_request": 3,
                                  "sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest()}
        time.sleep(0.02)
        (vdir / "round-2.json").write_text(json.dumps(verdict))
        result = loop.evaluate_cpo_acceptance({"commit": "abc"}, cfg)
        ck(result.get("passed") is True, f"exact memory checkpoint binding must pass: {result}")


def test_scaffold_provisions_memory():
    with tempfile.TemporaryDirectory() as d:
        target = Path(d) / "repo"; target.mkdir()
        subprocess.run([sys.executable, str(ROOT / "scripts/scaffold.py"), "--target", str(target)],
                       text=True, capture_output=True, check=True,
                       env={**os.environ, "ORBIT_HOME": str(Path(d) / "home")})
        for rel in (".orbit/checks/user_memory.py", ".orbit/memory/checkpoint.json",
                    ".orbit/memory/user-events.jsonl", ".orbit/skills/user-memory-architecture.md"):
            ck((target / rel).exists(), f"fresh scaffold must provision {rel}")
        cfg = json.loads((target / ".orbit/loop.config.json").read_text())
        ck(cfg.get("user_memory", {}).get("max_requests_between_reviews") == 5,
           "fresh scaffold must ship the five-request contract")

        route = target / ".orbit/checks/route.py"
        proc = subprocess.run([sys.executable, str(route)], input=json.dumps({
            "cwd": str(target), "prompt": "Always review the exact result before shipping"
        }), text=True, capture_output=True,
            env={**os.environ, "CLAUDE_PROJECT_DIR": str(target)})
        state = json.loads((target / ".orbit/memory/checkpoint.json").read_text())
        ck(proc.returncode == 0 and state.get("pending_event_ids") == ["U1"] and
           "REVIEW NOW" in proc.stdout,
           "the installed UserPromptSubmit router must capture and surface important memory events")


def main():
    for fn in (test_intake_and_review, test_stop_blocks_stale_memory,
               test_cpo_binds_memory_sha, test_scaffold_provisions_memory):
        try:
            fn()
        except Exception as exc:
            FAILS.append(f"{fn.__name__} raised {type(exc).__name__}: {exc}")
    if FAILS:
        print(f"FAIL: user-memory ({len(FAILS)})")
        for failure in FAILS:
            print("  -", failure)
        raise SystemExit(1)
    print("PASS: user-memory (intake · ≤5 review clock · Stop gate · CPO SHA binding · scaffold)")


if __name__ == "__main__":
    main()
