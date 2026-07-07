#!/usr/bin/env python3
"""
The boring resolver (v0.31.2). `bin/orbit-resolve` makes `/orbit-upgrade` deterministic: it ALWAYS names
the active install (it runs from it), lists stale copies without confusing them for active, and reports
dirtiness + how many commits behind origin. No candidate-loop prose, no "standard paths didn't resolve."

Simulates a skills-dir install + a stale plugin-cache copy under an isolated HOME.

Run: python3 tests/test_orbit_resolve.py   (exit 0 = pass)
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESOLVE = ROOT / "bin" / "orbit-resolve"
fails = []


def ck(cond, msg):
    if not cond:
        fails.append(msg)


def _git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), "-c", "user.email=t@t", "-c", "user.name=t", *args],
                   capture_output=True, text=True)


def _make_skills_install(home: Path, version="0.31.1", git=True):
    inst = home / ".claude" / "skills" / "orbit"
    (inst / "bin").mkdir(parents=True)
    (inst / "VERSION").write_text(version + "\n")
    (inst / "bin" / "orbit-resolve").write_bytes(RESOLVE.read_bytes())
    (inst / "bin" / "orbit-resolve").chmod(0o755)
    if git:
        _git(inst, "init", "-q")
        _git(inst, "add", "-A")
        _git(inst, "commit", "-qm", "init")
    return inst


def _resolve(inst, home, *args):
    r = subprocess.run([sys.executable, str(inst / "bin" / "orbit-resolve"), *args],
                       capture_output=True, text=True, env={**os.environ, "HOME": str(home),
                       "CLAUDE_CONFIG_DIR": str(home / ".claude")})
    ck(r.returncode == 0, f"orbit-resolve must exit 0 (got {r.returncode}: {r.stderr[-200:]})")
    try:
        return json.loads(r.stdout)
    except Exception:
        fails.append(f"orbit-resolve did not print JSON: {r.stdout[:200]!r}")
        return {}


def test_active_and_stale():
    with tempfile.TemporaryDirectory() as d:
        home = Path(d)
        inst = _make_skills_install(home)
        # a stale plugin-cache copy
        cache = home / ".claude" / "plugins" / "cache" / "orbit" / "orbit" / "0.4.0"
        cache.mkdir(parents=True)
        (cache / "VERSION").write_text("0.4.0\n")
        info = _resolve(inst, home)
        ck(info.get("active_install") == str(inst.resolve()), f"active_install should be the skills dir; got {info.get('active_install')}")
        ck(info.get("version") == "0.31.1", f"version should be 0.31.1; got {info.get('version')}")
        ck(info.get("is_git") is True, "is_git should be True for the skills clone")
        others = info.get("other_installs", [])
        ck(any("0.4.0" in o["path"] and o["active"] is False for o in others),
           f"the stale plugin-cache 0.4.0 must be listed as active:false; got {others}")
        ck(all(o["path"] != info["active_install"] for o in others), "the active install must not appear in other_installs")


def test_dirty_tracked_files():
    with tempfile.TemporaryDirectory() as d:
        home = Path(d)
        inst = _make_skills_install(home)
        (inst / "VERSION").write_text("0.31.1-local\n")   # modify a tracked file
        info = _resolve(inst, home)
        ck(info.get("dirty") is True, "a modified tracked file should make dirty=true")
        ck(any("VERSION" in f for f in info.get("dirty_files", [])), f"dirty_files should list VERSION; got {info.get('dirty_files')}")


def test_behind_counts_commits():
    with tempfile.TemporaryDirectory() as d:
        home = Path(d)
        remote = home / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], capture_output=True)
        inst = _make_skills_install(home, git=False)
        _git(inst, "init", "-q", "-b", "main")
        _git(inst, "add", "-A")
        _git(inst, "commit", "-qm", "init")
        _git(inst, "remote", "add", "origin", str(remote))
        _git(inst, "push", "-q", "origin", "main")
        # advance the remote from a second clone
        work2 = home / "work2"
        subprocess.run(["git", "clone", "-q", str(remote), str(work2)], capture_output=True)
        (work2 / "NEW").write_text("x")
        _git(work2, "add", "-A")
        _git(work2, "commit", "-qm", "ahead")
        _git(work2, "push", "-q", "origin", "main")
        info = _resolve(inst, home, "--upgrade-check")
        ck(info.get("behind", 0) >= 1, f"behind should be >=1 after the remote advanced; got {info.get('behind')}")


def test_never_fails_without_git():
    with tempfile.TemporaryDirectory() as d:
        home = Path(d)
        inst = _make_skills_install(home, git=False)   # no .git
        info = _resolve(inst, home)
        ck(info.get("is_git") is False, "is_git should be False without a .git")
        ck(info.get("active_install") == str(inst.resolve()), "active_install must still resolve without git")
        ck(info.get("version") == "0.31.1", "version must still resolve without git")


def main():
    if not os.access(RESOLVE, os.X_OK):
        print("FAIL: bin/orbit-resolve missing or not executable")
        sys.exit(1)
    for fn in (test_active_and_stale, test_dirty_tracked_files, test_behind_counts_commits, test_never_fails_without_git):
        try:
            fn()
        except Exception as e:
            fails.append(f"[{fn.__name__}] raised {type(e).__name__}: {e}")
    if fails:
        print(f"FAIL: orbit-resolve {len(fails)} case(s):")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("PASS: orbit-resolve (active vs stale · dirty tracked files · behind counts commits · never fails without git)")


if __name__ == "__main__":
    main()
