#!/usr/bin/env python3
"""The opt-in Git hook launches exact-commit dual-provider QA and records live state."""
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "bin" / "orbit-qa-hook"


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], text=True, capture_output=True,
                          check=True).stdout.strip()


def commit(repo, message):
    git(repo, "add", ".")
    git(repo, "commit", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def main():
    fails = []
    with tempfile.TemporaryDirectory() as d:
        repo = Path(d) / "repo"; repo.mkdir()
        git(repo, "init", "-q"); git(repo, "config", "user.email", "orbit@example.test")
        git(repo, "config", "user.name", "Orbit")
        (repo / ".orbit/qa").mkdir(parents=True)
        (repo / ".orbit/review-requests").mkdir()
        (repo / "scripts").mkdir()
        schema = ROOT / "assets/qa/independent-review-result.schema.json"
        (repo / ".orbit/qa/independent-review-result.schema.json").write_bytes(schema.read_bytes())
        reviewer = repo / "reviewer.py"
        reviewer.write_text("""import json,sys
json.dump({'schema_version':1,'verdict':'PASS','score':9.3,'summary':'proved','findings':[],
'criteria':[{'id':'AC-1','verdict':'PASS','evidence':'deterministic test'}],
'recommendations':[]},open(sys.argv[1],'w'))
""")
        config = {"independent_qa": {"enabled": True, "min_score": 8.5, "max_rounds": 2,
            "auto_review": {"enabled": True, "trigger": "post_commit",
                            "request": ".orbit/review-requests/M1.json"},
            "external_export": {"approved": True, "approved_by": "owner",
                "approved_at": "2026-07-15T00:00:00Z", "scope": "committed_snapshot_only"},
            "provider": {"mode": "both", "adapters": {
                "codex": {"argv": [sys.executable, "{repo}/reviewer.py", "{output}"]},
                "claude": {"argv": [sys.executable, "{repo}/reviewer.py", "{output}"]}}}},
            "paths": {"independent_reviews": ".orbit/reviews"}}
        (repo / ".orbit/loop.config.json").write_text(json.dumps(config))
        (repo / "product.txt").write_text("before\n")
        baseline = commit(repo, "baseline")
        request = {"schema_version": 1, "id": "M1", "goal": "safe feature",
            "baseline_commit": baseline,
            "acceptance_criteria": [{"id": "AC-1", "text": "works", "required": True}],
            "armed": {"approved": True, "approved_by": "owner",
                      "approved_at": "2026-07-15T00:00:00Z"}}
        (repo / ".orbit/review-requests/M1.json").write_text(json.dumps(request))
        commit(repo, "arm manifest")
        installed = subprocess.run([str(HOOK), "install", str(repo)], text=True, capture_output=True)
        if installed.returncode:
            fails.append(f"hook install failed: {installed.stderr}")
        (repo / "product.txt").write_text("after\n")
        target = commit(repo, "implement")
        common = Path(git(repo, "rev-parse", "--git-common-dir"))
        if not common.is_absolute(): common = (repo / common).resolve()
        current = common / "orbit-independent-qa/current.json"
        deadline = time.time() + 12
        state = {}
        while time.time() < deadline:
            if current.is_file():
                try: state = json.loads(current.read_text())
                except Exception: state = {}
                if state.get("status") in {"pass", "changes_required", "blocked", "error"}: break
            time.sleep(.05)
        if state.get("status") != "pass" or state.get("target_commit") != target:
            fails.append(f"post-commit QA did not pass exact commit: {state}")
        if subprocess.run([str(HOOK), "gate", str(repo), target]).returncode:
            fails.append("exact passed commit was rejected by the push gate")
        providers = state.get("providers", {})
        if set(providers) != {"codex", "claude"} or any(x.get("status") != "pass" for x in providers.values()):
            fails.append(f"dual-provider final states missing: {providers}")
        events_path = common / "orbit-independent-qa/events.jsonl"
        events = [json.loads(x) for x in events_path.read_text().splitlines() if x.strip()]
        if not any(e.get("status") == "queued" for e in events):
            fails.append("queued state was not recorded")
        if not any((e.get("providers", {}).get("codex", {}).get("status") == "reviewing") for e in events):
            fails.append("Codex reviewing state was not recorded")
        if not any((e.get("providers", {}).get("claude", {}).get("status") == "reviewing") for e in events):
            fails.append("Claude reviewing state was not recorded")
        (repo / "product.txt").write_text("unreviewed\n")
        # Disable the auto launcher for this commit so the exact-commit gate is tested deterministically.
        config["independent_qa"]["auto_review"]["enabled"] = False
        (repo / ".orbit/loop.config.json").write_text(json.dumps(config))
        unreviewed = commit(repo, "unreviewed")
        config["independent_qa"]["auto_review"]["enabled"] = True
        (repo / ".orbit/loop.config.json").write_text(json.dumps(config))
        if subprocess.run([str(HOOK), "gate", str(repo), unreviewed], stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL).returncode == 0:
            fails.append("unreviewed exact commit was allowed through the push gate")
        # Reinstall is idempotent; a foreign hook is never overwritten.
        again = subprocess.run([str(HOOK), "install", str(repo)], text=True, capture_output=True)
        if again.returncode: fails.append("managed hook reinstall was not idempotent")
        hook_path = common / "hooks/post-commit"
        hook_path.write_text("#!/bin/sh\necho foreign\n"); hook_path.chmod(0o755)
        foreign = subprocess.run([str(HOOK), "install", str(repo)], text=True, capture_output=True)
        if foreign.returncode == 0 or "refusing to overwrite" not in foreign.stderr:
            fails.append("foreign post-commit hook was overwritten or not rejected")
    if fails:
        print(f"FAIL: qa-hook ({len(fails)})")
        for fail in fails: print("  -", fail)
        return 1
    print("PASS: qa-hook (opt-in post-commit · exact commit · dual live states · no hook overwrite)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
