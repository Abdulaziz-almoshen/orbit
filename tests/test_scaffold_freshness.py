#!/usr/bin/env python3
"""
Tests scaffold FRESHNESS — the fix for the "silent version lie": the scaffolder deterministically
stamps `.orbit/setup.json`'s orbit_version (so it stops claiming an old version after a refresh),
records a manifest of what it placed, reports drift read-only, and carries UNMODIFIED managed check
hooks forward while PRESERVING customized ones. Separates plugin freshness from project-scaffold
freshness — the mental model /orbit-upgrade was missing.

  A. Fresh scaffold stamps setup.json (orbit_version == VERSION, scaffold_schema present), NO
     last_migrated on a fresh/no-op run, and writes the manifest.
  B. A stale scaffold (old orbit_version) → re-stamped to current + last_migrated_from/at recorded.
  C. --check-drift: fresh → "up to date"; stale (old version + missing file + missing hook) → reports
     the drift categories; it is READ-ONLY (writes nothing).
  D. Broadened migration: an UNMODIFIED managed check (learn.py) recorded in the manifest is carried
     forward + backed up; a CUSTOMIZED one is warned about and left untouched.

Run: python3 tests/test_scaffold_freshness.py   (exit 0 = pass)
"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCAFFOLD = os.path.join(ROOT, "scripts", "scaffold.py")
VERSION = open(os.path.join(ROOT, "VERSION")).read().strip()


def scaffold(target, *extra):
    subprocess.run(["git", "init", "-q", target], check=True)
    return subprocess.run([sys.executable, SCAFFOLD, "--surfaces", "api", "--target", target, *extra],
                          capture_output=True, text=True)


def rescaffold(target, *extra):
    return subprocess.run([sys.executable, SCAFFOLD, "--surfaces", "api", "--target", target, *extra],
                          capture_output=True, text=True)


def main():
    fails = []

    # --- A. fresh scaffold stamps setup.json + writes the manifest -------------------------------
    with tempfile.TemporaryDirectory() as d:
        scaffold(d)
        setup = json.load(open(os.path.join(d, ".orbit", "setup.json")))
        if setup.get("orbit_version") != VERSION:
            fails.append(f"[A] fresh setup.json orbit_version {setup.get('orbit_version')!r} != VERSION {VERSION!r}")
        if setup.get("scaffold_schema") is None:
            fails.append("[A] fresh setup.json missing scaffold_schema")
        if "last_migrated_at" in setup:
            fails.append("[A] fresh scaffold wrongly wrote a last_migrated_at (breaks the no-op contract)")
        man = os.path.join(d, ".orbit", ".scaffold-manifest.json")
        if not os.path.isfile(man):
            fails.append("[A] no .scaffold-manifest.json written")
        else:
            keys = json.load(open(man))
            if ".orbit/checks/guard.py" not in keys or ".orbit/checks/learn.py" not in keys:
                fails.append("[A] manifest missing managed checks")

    # --- B. a stale scaffold gets re-stamped + records the migration ----------------------------
    with tempfile.TemporaryDirectory() as d:
        scaffold(d)
        sp = os.path.join(d, ".orbit", "setup.json")
        data = json.load(open(sp)); data["orbit_version"] = "0.21.0"; data["custom_key"] = "keep me"
        json.dump(data, open(sp, "w"))
        rescaffold(d)
        after = json.load(open(sp))
        if after.get("orbit_version") != VERSION:
            fails.append(f"[B] stale scaffold NOT re-stamped to {VERSION} (still {after.get('orbit_version')!r})")
        if after.get("last_migrated_from") != "0.21.0":
            fails.append(f"[B] last_migrated_from not recorded ({after.get('last_migrated_from')!r})")
        if "last_migrated_at" not in after:
            fails.append("[B] last_migrated_at not recorded on a real migration")
        if after.get("custom_key") != "keep me":
            fails.append("[B] the model-written keys were not preserved on re-stamp")

    # --- C. --check-drift: fresh → up to date; stale → reports drift; READ-ONLY -----------------
    with tempfile.TemporaryDirectory() as d:
        scaffold(d, "--install-hooks")                       # a properly set-up project wires its hooks
        out = rescaffold(d, "--check-drift").stdout
        if "up to date" not in out:
            fails.append(f"[C] fresh scaffold drift should be 'up to date': {out!r}")
        # make it stale: old version, remove a shipped file, drop a hook wiring
        sp = os.path.join(d, ".orbit", "setup.json")
        data = json.load(open(sp)); data["orbit_version"] = "0.21.0"; json.dump(data, open(sp, "w"))
        os.remove(os.path.join(d, ".orbit", "skills", "loop-tiers.md"))
        # snapshot the tree, then run --check-drift, then assert NOTHING changed (read-only)
        import hashlib
        def snap():
            s = {}
            for base, _, fs in os.walk(os.path.join(d, ".orbit")):
                for f in fs:
                    p = os.path.join(base, f)
                    s[p] = hashlib.sha256(open(p, "rb").read()).hexdigest()
            return s
        before = snap()
        out2 = rescaffold(d, "--check-drift").stdout
        if snap() != before:
            fails.append("[C] --check-drift is NOT read-only (it modified files)")
        if "scaffold is behind" not in out2 or "loop-tiers.md" not in out2:
            fails.append(f"[C] stale drift report missing expected content: {out2!r}")
        if "plugin is current" not in out2:
            fails.append("[C] drift report must state the plugin is current (separates the two freshnesses)")

    # --- D. broadened migration: unmodified managed check carried fwd; customized preserved ------
    with tempfile.TemporaryDirectory() as d:
        scaffold(d)
        learn = os.path.join(d, ".orbit", "checks", "learn.py")
        man = os.path.join(d, ".orbit", ".scaffold-manifest.json")
        import hashlib
        # simulate "we placed an OLD learn.py": plant an old-but-ours variant + record ITS hash in the manifest
        old_learn = open(learn, "rb").read() + b"\n# (old shipped line)\n"
        open(learn, "wb").write(old_learn)
        m = json.load(open(man)); m[".orbit/checks/learn.py"] = hashlib.sha256(old_learn).hexdigest()
        json.dump(m, open(man, "w"))
        out = rescaffold(d).stdout
        after = open(learn, "rb").read()
        if b"(old shipped line)" in after:
            fails.append("[D] an UNMODIFIED managed learn.py was not carried forward to current")
        if not any(f.startswith("learn.py.bak.") for f in os.listdir(os.path.dirname(learn))):
            fails.append("[D] no backup written when carrying forward the unmodified learn.py")
    with tempfile.TemporaryDirectory() as d:
        scaffold(d)
        learn = os.path.join(d, ".orbit", "checks", "learn.py")
        # customized (differs from what we placed = the manifest) → must be warned + preserved
        open(learn, "ab").write(b"\n# MY CUSTOM active-learning tweak\n")
        out = rescaffold(d).stdout
        after = open(learn, "rb").read()
        if b"MY CUSTOM active-learning tweak" not in after:
            fails.append("[D] a CUSTOMIZED learn.py was clobbered (must be preserved)")
        if "locally modified" not in out:
            fails.append("[D] no warning for the customized learn.py")

    if fails:
        print(f"FAIL: scaffold-freshness {len(fails)} case(s):")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("PASS: scaffold-freshness (version stamp + migration re-stamp + read-only drift report + "
          "broadened managed-migration preserving customizations)")


if __name__ == "__main__":
    main()
