#!/usr/bin/env python3
"""
Verifiable releases 1a (v0.37.0) — integrity substrate. `checksums.txt` is a deterministic sha256
manifest of the shipped tree; `bin/orbit-verify` recomputes it to prove an install is exactly what
shipped (and reports the channel as unsigned until a signed `checksums.txt.asc` ships). Signing itself
(1b) needs the maintainer's key/CI; this tests the parts that don't.

Run: python3 tests/test_verifiable_release.py   (exit 0 = pass)
"""
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERIFY = ROOT / "bin" / "orbit-verify"
fails = []


def ck(cond, msg):
    if not cond:
        fails.append(msg)


def test_manifest_is_wellformed():
    man = ROOT / "checksums.txt"
    ck(man.exists(), "checksums.txt must be committed at the repo root")
    if not man.exists():
        return
    lines = [ln for ln in man.read_text().splitlines() if ln.strip()]
    paths = []
    for ln in lines:
        m = re.match(r"^([0-9a-f]{64})  (.+)$", ln)
        ck(bool(m), f"malformed manifest line: {ln[:60]!r}")
        if m:
            paths.append(m.group(2))
    ck(len(paths) == len(set(paths)), "manifest has duplicate paths")
    ck(paths == sorted(paths), "manifest must be sorted by path (deterministic)")
    ck("checksums.txt" not in paths, "the manifest must not list itself")
    # a few known shipped files must be covered
    for must in ("VERSION", "assets/checks/guard.py", "bin/orbit-verify"):
        ck(must in paths, f"manifest should cover {must}")


def _fake_install(d: Path):
    (d / "a.txt").write_text("hello orbit")
    (d / "sub").mkdir()
    (d / "sub" / "b.txt").write_text("world")
    rel = ["a.txt", "sub/b.txt"]
    man = "\n".join(f"{hashlib.sha256((d / p).read_bytes()).hexdigest()}  {p}" for p in rel)
    (d / "checksums.txt").write_text(man + "\n")


def _verify(root, want_json=False):
    args = [sys.executable, str(VERIFY), "--root", str(root)] + (["--json"] if want_json else [])
    return subprocess.run(args, capture_output=True, text=True)


def test_verify_clean_passes():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        _fake_install(p)
        r = _verify(p, want_json=True)
        ck(r.returncode == 0, f"a clean tree must verify (exit 0); got {r.returncode}: {r.stdout[-200:]}")
        j = json.loads(r.stdout)
        ck(j["ok"] and j["checked"] == 2 and not j["modified"] and not j["missing"], f"clean json wrong: {j}")
        ck(j["signature"] == "unsigned", "no .asc → signature must be reported 'unsigned' (honest)")


def test_verify_detects_tamper():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        _fake_install(p)
        (p / "a.txt").write_text("TAMPERED")
        r = _verify(p, want_json=True)
        ck(r.returncode == 1, "a modified file must fail verification (exit 1)")
        ck("a.txt" in json.loads(r.stdout)["modified"], "the modified file must be named")


def test_verify_detects_missing():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        _fake_install(p)
        (p / "sub" / "b.txt").unlink()
        r = _verify(p, want_json=True)
        ck(r.returncode == 1, "a missing file must fail verification (exit 1)")
        ck("sub/b.txt" in json.loads(r.stdout)["missing"], "the missing file must be named")


def test_real_install_verifies():
    r = _verify(ROOT)
    ck(r.returncode == 0, f"the committed tree must verify against its own checksums.txt; got:\n{r.stdout[-300:]}")


def main():
    for fn in (test_manifest_is_wellformed, test_verify_clean_passes, test_verify_detects_tamper,
               test_verify_detects_missing, test_real_install_verifies):
        try:
            fn()
        except Exception as e:
            fails.append(f"[{fn.__name__}] raised {type(e).__name__}: {e}")
    if fails:
        print(f"FAIL: verifiable-release {len(fails)} case(s):")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("PASS: verifiable-release (manifest well-formed · verify clean/tamper/missing · unsigned "
          "reported honestly · real tree verifies)")


if __name__ == "__main__":
    main()
