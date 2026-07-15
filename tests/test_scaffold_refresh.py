#!/usr/bin/env python3
"""
Tests the MANAGED-PATCHING surface completed in v0.29.0: `scaffold.py --plan-refresh` (read-only
preview) and `--apply-safe-refresh` (write only the safe files), plus the `bin/orbit-doctor` entry
point. The invariant that matters most: a CUSTOMIZED managed hook (e.g. a guard with local rules) is
NEVER clobbered — not on the first refresh, and not on any later one.

Regression pin (the v0.29.0 bugfix): before this release, `_write_manifest` recorded the hash of
whatever was on disk — including a customized guard — which "laundered" the customization into looking
unmodified, so the SECOND refresh (or 2nd `/orbit` re-run) would auto-upgrade and overwrite it. Tests
`repeated_refresh_preserves_customization` and `repeated_full_scaffold_preserves_customization` pin
that shut for both the refresh path and the full-scaffold path (they share `_write_manifest`).

Run: python3 tests/test_scaffold_refresh.py   (exit 0 = pass)
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAFFOLD = ROOT / "scripts" / "scaffold.py"
ASSETS = ROOT / "assets"
MANIFEST_REL = ".orbit/.scaffold-manifest.json"
fails = []


def _run(*args):
    return subprocess.run([sys.executable, str(SCAFFOLD), *args],
                          capture_output=True, text=True)


def _scaffold(target, surfaces="api"):
    r = _run("--target", str(target), "--surfaces", surfaces)
    if r.returncode != 0:
        fails.append(f"[setup] scaffold failed: {r.stderr[-400:]}")


def _sha(p: Path):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _tree_fingerprint(target: Path):
    parts = []
    for f in sorted(target.rglob("*")):
        if f.is_file():
            parts.append(f"{f.relative_to(target)}:{_sha(f)}")
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def _make_upgradeable(target: Path, rel: str):
    """Turn a managed hook into an 'unmodified-since-placed but shipped-moved' (→ auto-upgrade) case:
    write old-but-marker-bearing content and record ITS hash in the manifest (so it reads as ours)."""
    p = target / rel
    old = b"# OLD but unmodified-since-placed\n" + p.read_bytes()
    p.write_bytes(old)
    man = target / MANIFEST_REL
    m = json.loads(man.read_text())
    m[rel] = hashlib.sha256(old).hexdigest()
    man.write_text(json.dumps(m, indent=2, sort_keys=True) + "\n")


def test_plan_refresh_is_read_only():
    with tempfile.TemporaryDirectory() as d:
        t = Path(d)
        _scaffold(t)
        before = _tree_fingerprint(t)
        r = _run("--plan-refresh", "--target", str(t))
        if r.returncode != 0:
            fails.append(f"[plan-read-only] non-zero exit: {r.stderr[-200:]}")
        if _tree_fingerprint(t) != before:
            fails.append("[plan-read-only] --plan-refresh mutated the project (must be read-only)")
        if "already current: 5" not in r.stdout:
            fails.append(f"[plan-read-only] fresh scaffold should show 5 current managed files; got:\n{r.stdout}")


def test_plan_refresh_classifies_and_shows_diff():
    with tempfile.TemporaryDirectory() as d:
        t = Path(d)
        _scaffold(t)
        (t / ".orbit/checks/guard.py").write_bytes(
            (t / ".orbit/checks/guard.py").read_bytes() + b"\n# my local rule\n")   # customized
        (t / ".orbit/checks/route.py").unlink()                                     # add
        _make_upgradeable(t, ".orbit/checks/learn.py")                              # upgrade
        r = _run("--plan-refresh", "--target", str(t))
        out = r.stdout
        checks = [
            ("learn.py" in out and "auto-upgrade" in out, "learn.py listed under auto-upgrade"),
            ("route.py" in out and "would add" in out, "route.py listed under would-add"),
            ("guard.py" in out and "customized" in out, "guard.py listed under customized"),
            ("# my local rule" in out or "--- a/.orbit/checks/guard.py" in out,
             "a patch-suggestion diff is printed for the customized guard"),
        ]
        for ok, why in checks:
            if not ok:
                fails.append(f"[plan-classify] expected {why}; full output:\n{out}")


def test_apply_safe_refresh_upgrades_adds_preserves():
    with tempfile.TemporaryDirectory() as d:
        t = Path(d)
        _scaffold(t)
        guard = t / ".orbit/checks/guard.py"
        guard.write_bytes(guard.read_bytes() + b"\n# my local rule\n")
        guard_custom_sha = _sha(guard)
        (t / ".orbit/checks/route.py").unlink()
        _make_upgradeable(t, ".orbit/checks/learn.py")
        _run("--apply-safe-refresh", "--target", str(t))
        # learn upgraded to current shipped
        if _sha(t / ".orbit/checks/learn.py") != _sha(ASSETS / "checks/learn.py"):
            fails.append("[apply] learn.py was not upgraded to the current shipped version")
        # route re-added
        if not (t / ".orbit/checks/route.py").exists():
            fails.append("[apply] missing route.py was not re-added")
        # guard preserved byte-for-byte
        if _sha(guard) != guard_custom_sha:
            fails.append("[apply] CUSTOMIZED guard.py was modified (must be preserved)")
        # a backup exists for the upgraded file
        if not list((t / ".orbit/checks").glob("learn.py.bak.*")):
            fails.append("[apply] no backup was kept for the upgraded learn.py")


def test_repeated_refresh_preserves_customization():
    """THE regression pin: a customized guard must survive refresh #1, #2 AND #3 unchanged."""
    with tempfile.TemporaryDirectory() as d:
        t = Path(d)
        _scaffold(t)
        guard = t / ".orbit/checks/guard.py"
        guard.write_bytes(guard.read_bytes() + b"\n# my local rule\n")
        sha0 = _sha(guard)
        for i in (1, 2, 3):
            _run("--apply-safe-refresh", "--target", str(t))
            if _sha(guard) != sha0:
                fails.append(f"[repeated-refresh] guard clobbered on refresh #{i} (manifest-laundering bug)")
                break
        if b"# my local rule" not in guard.read_bytes():
            fails.append("[repeated-refresh] guard lost its custom rule across refreshes")
        baks = list((t / ".orbit/checks").glob("guard.py.bak.*"))
        if baks:
            fails.append(f"[repeated-refresh] a customized guard was backed-up/replaced ({len(baks)} .bak) — must be hands-off")


def test_repeated_full_scaffold_preserves_customization():
    """Same bug, the full `/orbit` re-run path: customize the guard, then re-scaffold twice."""
    with tempfile.TemporaryDirectory() as d:
        t = Path(d)
        _scaffold(t)
        guard = t / ".orbit/checks/guard.py"
        guard.write_bytes(guard.read_bytes() + b"\n# my local rule\n")
        sha0 = _sha(guard)
        _scaffold(t)
        _scaffold(t)
        if _sha(guard) != sha0 or b"# my local rule" not in guard.read_bytes():
            fails.append("[repeated-scaffold] customized guard clobbered across two /orbit re-runs")


def test_poisoned_manifest_never_clobbers_customized_guard():
    """P0 regression (v0.31.1): a pre-0.28.1 scaffold could 'launder' a CUSTOMIZED guard's hash into the
    manifest, so a later 'safe' refresh believed it was Orbit-owned and would overwrite it. The guard now
    upgrades ONLY on a known-shipped hash (never a manifest vouch), policy markers force 'customized', and
    the manifest is repaired. Uses the real recruitment-platform marker `REQUIRE_DEPLOY_APPROVAL = False`."""
    with tempfile.TemporaryDirectory() as d:
        t = Path(d)
        _scaffold(t)
        guard = t / ".orbit/checks/guard.py"
        guard.write_bytes(guard.read_bytes() + b"\n# recruitment-platform specifics\nREQUIRE_DEPLOY_APPROVAL = False\n")
        sha0 = _sha(guard)
        # POISON the manifest exactly as a pre-fix scaffold did: record the CUSTOMIZED hash as "placed"
        man = t / MANIFEST_REL
        m = json.loads(man.read_text())
        m[".orbit/checks/guard.py"] = sha0
        man.write_text(json.dumps(m, indent=2, sort_keys=True) + "\n")
        # drift and plan must AGREE that it's customized (no "would auto-upgrade")
        drift = _run("--check-drift", "--target", str(t)).stdout
        plan = _run("--plan-refresh", "--target", str(t)).stdout
        if "guard.py is customized" not in drift:
            fails.append(f"[poisoned] drift must call the guard customized; got:\n{drift[:300]}")
        if "guard.py" in plan and "auto-upgrade" in plan:
            fails.append(f"[poisoned] plan must NOT offer to auto-upgrade the customized guard; got:\n{plan[:300]}")
        # apply-safe-refresh must leave the guard byte-for-byte unchanged (repeatedly) and repair the manifest
        for i in (1, 2, 3):
            _run("--apply-safe-refresh", "--target", str(t))
            if _sha(guard) != sha0:
                fails.append(f"[poisoned] guard was CLOBBERED on apply #{i} (the P0 bug)")
                break
        if b"REQUIRE_DEPLOY_APPROVAL" not in guard.read_bytes():
            fails.append("[poisoned] the guard lost its repo policy")
        if list((t / ".orbit/checks").glob("guard.py.bak.*")):
            fails.append("[poisoned] a customized guard was backed-up/replaced — must be untouched")
        if ".orbit/checks/guard.py" in json.loads((t / MANIFEST_REL).read_text()):
            fails.append("[poisoned] the laundered manifest entry was not repaired (removed)")


def test_markerless_custom_guard_also_protected():
    """Defense-in-depth: even WITHOUT a policy marker, a guard whose bytes aren't a known-shipped version
    is never auto-upgraded on a manifest vouch (the guard trusts only known-shipped hashes)."""
    with tempfile.TemporaryDirectory() as d:
        t = Path(d)
        _scaffold(t)
        guard = t / ".orbit/checks/guard.py"
        guard.write_bytes(guard.read_bytes() + b"\n# a quiet local tweak, no policy marker\n")
        sha0 = _sha(guard)
        man = t / MANIFEST_REL
        m = json.loads(man.read_text())
        m[".orbit/checks/guard.py"] = sha0
        man.write_text(json.dumps(m, indent=2, sort_keys=True) + "\n")
        _run("--apply-safe-refresh", "--target", str(t))
        if _sha(guard) != sha0:
            fails.append("[markerless] a customized guard with a poisoned manifest was clobbered")


def test_orbit_doctor_is_read_only():
    doctor = ROOT / "bin" / "orbit-doctor"
    if not os.access(doctor, os.X_OK):
        fails.append("[doctor] bin/orbit-doctor is missing or not executable")
        return
    with tempfile.TemporaryDirectory() as d:
        t = Path(d)
        _scaffold(t)
        before = _tree_fingerprint(t)
        r = subprocess.run([str(doctor), str(t)], capture_output=True, text=True,
                           env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(ROOT)})
        if r.returncode != 0:
            fails.append(f"[doctor] non-zero exit on a scaffolded repo: {r.stderr[-200:]}")
        if _tree_fingerprint(t) != before:
            fails.append("[doctor] orbit-doctor mutated the project (must be read-only)")
        if "scaffold drift" not in r.stdout or "safe-refresh plan" not in r.stdout:
            fails.append(f"[doctor] expected drift + refresh-plan sections; got:\n{r.stdout[:300]}")


def main():
    for fn in (test_plan_refresh_is_read_only, test_plan_refresh_classifies_and_shows_diff,
               test_apply_safe_refresh_upgrades_adds_preserves, test_repeated_refresh_preserves_customization,
               test_repeated_full_scaffold_preserves_customization,
               test_poisoned_manifest_never_clobbers_customized_guard, test_markerless_custom_guard_also_protected,
               test_orbit_doctor_is_read_only):
        try:
            fn()
        except Exception as e:
            fails.append(f"[{fn.__name__}] raised {type(e).__name__}: {e}")
    if fails:
        print(f"FAIL: scaffold-refresh {len(fails)} case(s):")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("PASS: scaffold-refresh (plan-refresh read-only + classifies; apply-safe-refresh "
          "upgrades/adds/preserves; customized guard survives repeated refresh AND re-scaffold; "
          "orbit-doctor read-only)")


if __name__ == "__main__":
    main()
