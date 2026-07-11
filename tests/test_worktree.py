#!/usr/bin/env python3
"""Worktree lifecycle and registry isolation tests."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "bin" / "orbit-worktree"


def run(*args, cwd):
    return subprocess.run([sys.executable, str(TOOL), *args], cwd=cwd, text=True,
                          capture_output=True)


def main():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "repo"
        root.mkdir()
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.email", "orbit@test"], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.name", "Orbit Test"], check=True)
        (root / ".orbit/locks").mkdir(parents=True)
        (root / ".orbit/worktree.json").write_text("{}\n")
        (root / "README").write_text("seed\n")
        subprocess.run(["git", "-C", str(root), "add", "."], check=True)
        subprocess.run(["git", "-C", str(root), "commit", "-qm", "seed"], check=True)
        made = run("create", "--task", "frontend-modal", "--budget-tokens", "9000", cwd=root)
        if made.returncode:
            print("FAIL: worktree create", made.stderr)
            return 1
        info = json.loads(made.stdout)
        worker = Path(info["worktree"])
        if not worker.is_dir() or info["branch"] != "orbit/frontend-modal":
            print("FAIL: worktree metadata/path", info)
            return 1
        if not (worker / ".orbit/worktree.json").exists():
            print("FAIL: worker metadata missing")
            return 1
        status = run("status", cwd=root)
        if status.returncode or str(worker) not in status.stdout:
            print("FAIL: worktree status", status.stdout, status.stderr)
            return 1
        finished = run("finish", str(worker), "--summary", "modal fix ready", "--tests", "pytest -q", cwd=root)
        if finished.returncode:
            print("FAIL: worktree finish", finished.stdout, finished.stderr)
            return 1
        packet = json.loads(finished.stdout)
        if packet.get("status") != "ready_for_review" or packet.get("budget", {}).get("tokens") != 9000:
            print("FAIL: completion packet", packet)
            return 1
        status = run("status", cwd=root)
        if '"merge_queue": 1' not in status.stdout or '"status": "ready_for_review"' not in status.stdout:
            print("FAIL: merge queue status", status.stdout)
            return 1
        removed = run("remove", str(worker), "--force", cwd=root)
        if removed.returncode or worker.exists():
            print("FAIL: worktree remove", removed.stdout, removed.stderr)
            return 1
    print("PASS: worktree (isolated branch, metadata, common registry, lifecycle)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
