#!/usr/bin/env python3
"""Contract tests for deterministic indexing, bounded retrieval, provenance, and incremental no-op."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("orbit_repo_intel", ROOT / "assets/checks/repository_intelligence.py")
intel = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(intel)


def put(root, rel, text):
    p = root / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text); return p


def main():
    failures = []
    with tempfile.TemporaryDirectory() as d:
        root = Path(d); (root / ".orbit").mkdir()
        put(root, "services/scheduling/reschedule.py", """
from services.availability.panel import reserve_panel
def reschedule_interview(interview_id, slot):
    publish('interview.rescheduled')
    return reserve_panel(interview_id, slot)
""")
        put(root, "services/availability/panel.py", "def reserve_panel(interview_id, slot):\n    return True\n")
        put(root, "apps/api/routes.ts", "router.patch('/interviews/:id/schedule', rescheduleInterview)\n")
        put(root, "workers/notifications/subscriber.ts", "subscribe('interview.rescheduled', notifyPanel)\n")
        put(root, "db/migrations/021_interview_schedule.sql", "ALTER TABLE interviews ADD COLUMN scheduled_at timestamp;\n")
        put(root, "tests/scheduling/test_reschedule.py", "from services.scheduling.reschedule import reschedule_interview\ndef test_reschedule_keeps_panel(): pass\n")
        put(root, "CODEOWNERS", "/services/scheduling/ @recruiting-core\n/services/availability/ @calendar-team\n")
        put(root, "package.json", '{"scripts":{"test":"pytest"}}')
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "add", "."], cwd=root, check=True)
        subprocess.run(["git", "-c", "user.name=Orbit", "-c", "user.email=orbit@example.test", "commit", "-qm", "fixture"], cwd=root, check=True)

        first = intel.build(root)
        packet = intel.query(root, "reschedule interview without losing panel availability", max_tokens=900, max_files=8)
        paths = {x["path"] for x in packet["retrieval"]["files"]}
        expected = {"services/scheduling/reschedule.py", "services/availability/panel.py",
                    "tests/scheduling/test_reschedule.py"}
        if not expected <= paths:
            failures.append(f"missing impact files: {sorted(expected-paths)}; got {sorted(paths)}")
        if packet["retrieval"]["estimated_tokens"] > 900 or len(paths) > 8:
            failures.append("retrieval exceeded its hard packet cap")
        if not all(e.get("extractor") and e.get("line") for item in packet["retrieval"]["files"] for e in item["evidence"]):
            failures.append("retrieval emitted evidence without provenance")
        owners = {x["owner"] for x in packet["retrieval"]["owners"]}
        if not {"@recruiting-core", "@calendar-team"} <= owners:
            failures.append(f"CODEOWNERS did not resolve for retrieved impact files: {owners}")
        con = intel._connect(root / ".orbit/intelligence/index.sqlite3")
        if not con.execute("SELECT 1 FROM edges WHERE kind='call' AND src=? AND dst=?",
                           ("services/scheduling/reschedule.py", "services/availability/panel.py")).fetchone():
            failures.append("AST call relationship was not resolved to its unique definition")
        con.close()
        db = root / ".orbit/intelligence/index.sqlite3"
        stable_mtime = db.stat().st_mtime_ns
        second = intel.build(root)
        if second["changed"] != 0 or second["removed"] != 0:
            failures.append(f"no-op update was not incremental: {second}")
        if db.stat().st_mtime_ns != stable_mtime:
            failures.append("no-op update rewrote the index")
        panel = root / "services/availability/panel.py"
        time.sleep(0.002); os.utime(panel, None)
        touched = intel.build(root)
        con = intel._connect(db)
        stored_mtime = con.execute("SELECT mtime_ns FROM files WHERE path=?",
                                   ("services/availability/panel.py",)).fetchone()[0]
        con.close()
        if touched["changed"] != 0 or stored_mtime != panel.stat().st_mtime_ns:
            failures.append("same-content touch was re-extracted or its metadata checkpoint was not advanced")
        subprocess.run(["git", "-c", "user.name=Orbit", "-c", "user.email=orbit@example.test",
                        "commit", "--allow-empty", "-qm", "history-only"], cwd=root, check=True)
        history = intel.build(root)
        con = intel._connect(db)
        indexed_head = con.execute("SELECT value FROM meta WHERE key='git_head'").fetchone()[0]
        con.close()
        actual_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        if history["changed"] != 0 or indexed_head != actual_head:
            failures.append("Git HEAD movement did not refresh the historical co-change checkpoint")
        time.sleep(0.002)
        put(root, "services/availability/panel.py", "def reserve_panel(interview_id, slot):\n    return slot is not None\n")
        third = intel.build(root)
        if third["changed"] != 1 or third["changed_paths"] != ["services/availability/panel.py"]:
            failures.append(f"incremental update did not isolate one changed file: {third}")
        if first["files"] != 8:
            failures.append(f"unexpected fixture file count: {first}")

    # Exactly max_files lexical seeds plus a one-hop neighbor must remain exactly capped. This is
    # the production failure that previously emitted 13 files for a configured maximum of 12.
    with tempfile.TemporaryDirectory() as d:
        root = Path(d); (root / ".orbit").mkdir()
        for i in range(12):
            body = f"def attestation_isolation_version_{i}():\n    return True\n"
            if i == 0:
                body = ("from dependency import verify\n"
                        f"def attestation_isolation_version_{i}():\n    return verify()\n")
            put(root, f"service/seed_{i:02}.py", body)
        put(root, "dependency.py", "def verify(): return True\n")
        intel.build(root)
        capped = intel.query(root, "attestation isolation version", max_tokens=4000, max_files=12)
        if len(capped["retrieval"]["files"]) != 12:
            failures.append("one-hop expansion crossed the exact 12-file cap")
    if failures:
        print("FAIL: repository intelligence")
        for failure in failures: print("  -", failure)
        return 1
    print("PASS: repository intelligence (deterministic index · one-hop bounded packet · provenance · incremental update)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
