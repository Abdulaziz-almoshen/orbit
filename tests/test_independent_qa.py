#!/usr/bin/env python3
"""Regression coverage for Orbit's independent, commit-bound QA gate."""
import importlib.util
import importlib.machinery
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
loader = importlib.machinery.SourceFileLoader("independent_qa", str(ROOT / "bin/orbit-independent-qa"))
spec = importlib.util.spec_from_loader("independent_qa", loader)
qa = importlib.util.module_from_spec(spec)
sys.modules["independent_qa"] = qa
loader.exec_module(qa)


def run(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], text=True, capture_output=True, check=True).stdout.strip()


def commit(repo, message):
    run(repo, "add", ".")
    run(repo, "commit", "-m", message)
    return run(repo, "rev-parse", "HEAD")


def main():
    fails = []
    # A fresh scaffold installs the stage; a reinstall additively migrates old config.
    with tempfile.TemporaryDirectory() as d:
        target = Path(d)
        subprocess.run([sys.executable, str(ROOT / "scripts/scaffold.py"), "--target", str(target)],
                       text=True, capture_output=True, check=True)
        expected = ["scripts/orbit-independent-qa", ".orbit/qa/independent-review-request.schema.json",
                    ".orbit/qa/independent-review-result.schema.json", ".orbit/review-requests/TEMPLATE.json"]
        for rel in expected:
            if not (target / rel).exists():
                fails.append(f"fresh scaffold missing {rel}")
        cfg_path = target / ".orbit/loop.config.json"
        cfg = json.loads(cfg_path.read_text())
        if "independent_qa" not in cfg or cfg["independent_qa"].get("enabled") is not False:
            fails.append("fresh scaffold did not install disabled-by-default independent QA config")
        cfg.pop("independent_qa", None); cfg.pop("_independent_qa_help", None)
        cfg["custom_project_value"] = "preserve-me"
        cfg.get("paths", {}).pop("independent_reviews", None)
        cfg.get("paths", {}).pop("independent_qa_runner", None)
        cfg_path.write_text(json.dumps(cfg))
        subprocess.run([sys.executable, str(ROOT / "scripts/scaffold.py"), "--target", str(target)],
                       text=True, capture_output=True, check=True)
        migrated = json.loads(cfg_path.read_text())
        if ("independent_qa" not in migrated or migrated.get("custom_project_value") != "preserve-me"
                or "independent_qa_runner" not in migrated.get("paths", {})):
            fails.append("reinstall did not add QA defaults while preserving project config")

    with tempfile.TemporaryDirectory() as d:
        repo = Path(d) / "repo"
        repo.mkdir()
        run(repo, "init")
        run(repo, "config", "user.email", "orbit@example.test")
        run(repo, "config", "user.name", "Orbit Test")
        (repo / ".orbit/qa").mkdir(parents=True)
        (repo / ".orbit/review-requests").mkdir()
        shutil.copy2(ROOT / "assets/qa/independent-review-result.schema.json",
                     repo / ".orbit/qa/independent-review-result.schema.json")
        helper = repo / "fake_reviewer.py"
        helper.write_text("""import json,sys\nout=sys.argv[1]\njson.dump({'schema_version':1,'verdict':'PASS','score':9.2,'summary':'proved','findings':[],'criteria':[{'id':'AC-1','verdict':'PASS','evidence':'test passed'}],'recommendations':[]},open(out,'w'))\n""")
        config = {
            "independent_qa": {"enabled": True, "min_score": 8.5, "max_rounds": 3,
                "external_export": {"approved": True, "approved_by": "founder",
                                    "approved_at": "2026-07-15T00:00:00Z",
                                    "scope": "committed_snapshot_only"},
                "provider": {"name": "fake", "argv": [sys.executable, "{repo}/fake_reviewer.py", "{output}"]}},
            "paths": {"independent_reviews": ".orbit/reviews"}
        }
        (repo / ".orbit/loop.config.json").write_text(json.dumps(config))
        (repo / "product.txt").write_text("before\n")
        baseline = commit(repo, "baseline")
        request = {"schema_version": 1, "id": "milestone-1", "goal": "ship safely",
                   "baseline_commit": baseline,
                   "acceptance_criteria": [{"id": "AC-1", "text": "feature works", "required": True}],
                   "armed": {"approved": True, "approved_by": "founder", "approved_at": "2026-07-15T00:00:00Z"}}
        request_path = repo / ".orbit/review-requests/milestone-1.json"
        request_path.write_text(json.dumps(request))
        commit(repo, "arm acceptance manifest")
        (repo / "product.txt").write_text("after\n")
        target = commit(repo, "implement feature")

        try:
            status = qa.run_review(repo, request_path, target)
            if not status.get("passed"):
                fails.append(f"valid independent review did not pass: {status}")
            gate = qa.check_gate(repo, request_path, target)
            if not gate.get("passed"):
                fails.append(f"matching gate did not pass: {gate}")
            # A forged project mirror cannot replace the authoritative control-plane result.
            mirror = Path(status["report_path"])
            forged = json.loads(mirror.read_text()); forged["result"]["verdict"] = "BLOCKED"
            mirror.write_text(json.dumps(forged))
            if not qa.check_gate(repo, request_path, target).get("passed"):
                fails.append("editing the project report mirror changed the authoritative gate")
        except Exception as exc:
            fails.append(f"valid review crashed: {exc}")

        # A later code commit has no matching approval and must fail closed.
        (repo / "product.txt").write_text("changed again\n")
        changed = commit(repo, "change after approval")
        if qa.check_gate(repo, request_path, changed).get("passed"):
            fails.append("a code change reused an earlier independent approval")

        # Working-tree secrets/manifest edits are ignored because the request is read from Git.
        request["goal"] = "UNCOMMITTED SECRET"
        request_path.write_text(json.dumps(request))
        committed, _ = qa.committed_request(repo, request_path, target)
        if committed["goal"] != "ship safely":
            fails.append("independent QA read the uncommitted request instead of the Git snapshot")

        # Consent is a hard runtime wall, not merely documentation.
        cfg_path = repo / ".orbit/loop.config.json"
        cfg = json.loads(cfg_path.read_text()); cfg["independent_qa"]["external_export"]["approved"] = False
        cfg_path.write_text(json.dumps(cfg)); commit(repo, "revoke export consent")
        try:
            qa.run_review(repo, request_path, "HEAD")
            fails.append("review ran without explicit external-export consent")
        except qa.QAError as exc:
            if "not approved" not in str(exc):
                fails.append(f"wrong consent failure: {exc}")

    if fails:
        print(f"FAIL: independent-qa ({len(fails)})")
        for failure in fails:
            print("  -", failure)
        return 1
    print("PASS: independent-qa (consent wall + committed snapshot + hash/commit binding + stale rejection)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
