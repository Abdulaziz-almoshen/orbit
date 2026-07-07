#!/usr/bin/env python3
"""
gen-checksums.py — write `checksums.txt`, a deterministic sha256 manifest of every SHIPPED (git-tracked)
file. Run at release time (before tagging). It is the integrity backbone for verifiable installs:
`bin/orbit-verify` recomputes these hashes against an installed tree to detect tampering/corruption, and
a future detached signature (`checksums.txt.asc`, signed in CI with the maintainer's key) signs THIS file
— so one signature covers the whole tree. No signing here (that needs the key); this is the substrate.

Format: `<sha256>  <path>` per line, sorted by path (stable across machines). Usage: gen-checksums.py
"""
import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "checksums.txt"
# Files that are not part of the shipped, verifiable tree (self, its signature, VCS metadata).
EXCLUDE = {"checksums.txt", "checksums.txt.asc"}


def tracked_files():
    r = subprocess.run(["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("gen-checksums: not a git repo (need `git ls-files`)")
    return sorted(p for p in r.stdout.splitlines() if p and p not in EXCLUDE)


def main():
    lines = []
    for rel in tracked_files():
        f = ROOT / rel
        if not f.is_file():
            continue                                   # a submodule / deleted-but-tracked entry
        lines.append(f"{hashlib.sha256(f.read_bytes()).hexdigest()}  {rel}")
    OUT.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT.name}: {len(lines)} files")


if __name__ == "__main__":
    main()
