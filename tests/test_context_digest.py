#!/usr/bin/env python3
"""Regression tests for user-model visibility, compaction, and the specialist digest.

The user-model reached 100KB in a live install precisely because `orbit-context doctor` could not
see it and nothing pruned it, while every spine role read it whole. These tests pin all three.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CTX = ROOT / "bin" / "orbit-context"


def run(cmd, target):
    return subprocess.run([sys.executable, str(CTX), cmd, str(target)],
                          text=True, capture_output=True)


def _fat_user_model(orbit: Path, signals: int = 400) -> None:
    lines = [
        "# User model — testproj", "",
        "## Rules (durable — 3+ consistent signals each)",
        "1. Ship fast, explain briefly (evidence: R3, R7, R12)",
        "2. Never narrate routine tool calls (evidence: R1, R4, R9)", "",
        "## Signals (dated observations, newest first)",
    ]
    for i in range(signals, 0, -1):                    # newest first, per the documented format
        lines.append(f"- 2026-08-{(i % 28) + 1:02d} R{i} [accepted]: signal {i} " + "padding " * 12)
    lines += ["", "## Vocabulary", '- "ship it" → commit, push, and deploy without asking']
    (orbit / "skills").mkdir(parents=True, exist_ok=True)
    (orbit / "skills" / "user-model.md").write_text("\n".join(lines) + "\n")


def main() -> int:
    failures = []
    with tempfile.TemporaryDirectory() as td:
        target = Path(td)
        orbit = target / ".orbit"
        orbit.mkdir()
        (orbit / "loop.config.json").write_text((ROOT / "assets/loop.config.json").read_text())
        _fat_user_model(orbit)

        # --- the doctor can SEE the user-model (it could not before v0.60.0) ---------------
        doc = run("doctor", target)
        if "user-model" not in doc.stdout:
            failures.append("doctor does not report the user-model")
        if "skills" not in doc.stdout:
            failures.append("doctor does not report the .orbit/skills total")

        # --- the digest is bounded and keeps the durable parts -----------------------------
        dig = run("digest", target)
        digest = orbit / "skills" / "user-model-digest.md"
        if not digest.exists():
            failures.append("digest was not written")
        else:
            text = digest.read_text()
            if "Ship fast" not in text or "Never narrate" not in text:
                failures.append("digest dropped the durable Rules")
            if "ship it" not in text:
                failures.append("digest dropped the Vocabulary")
            if "GENERATED" not in text:
                failures.append("digest is missing its do-not-edit header")
            full = (orbit / "skills" / "user-model.md").stat().st_size
            if len(text.encode()) >= full:
                failures.append("digest is not smaller than the source")
            # cap is 2500 tokens at divisor 4 → 10,000 bytes
            if len(text.encode()) > 10_000 + 200:
                failures.append(f"digest blew its token cap: {len(text.encode())} bytes")
            if "R400" not in text:
                failures.append("digest dropped the NEWEST signal (signals are newest-first)")
            if "R1 [" in text:
                failures.append("digest kept the oldest signal — it should be capped")

        # --- compaction prunes signals and preserves Rules/Vocabulary ----------------------
        before = (orbit / "skills" / "user-model.md").stat().st_size
        comp = run("compact", target)
        after_text = (orbit / "skills" / "user-model.md").read_text()
        if (orbit / "skills" / "user-model.md").stat().st_size >= before:
            failures.append("compact did not shrink the user-model")
        if "Ship fast" not in after_text or "ship it" not in after_text:
            failures.append("compact destroyed durable Rules/Vocabulary")
        if "user-model" not in comp.stdout:
            failures.append("compact does not report user-model work")
        archives = list((orbit / "archive").rglob("user-model.md.backup"))
        if not archives:
            failures.append("compact did not back up the user-model before rewriting it")

        # --- idempotency: a second compact must not eat the kept signals -------------------
        kept_once = after_text.count("- 2026-")
        run("compact", target)
        kept_twice = (orbit / "skills" / "user-model.md").read_text().count("- 2026-")
        if kept_once != kept_twice:
            failures.append(f"compact is not idempotent: {kept_once} → {kept_twice} signals")

        # --- no user-model at all → clean no-op, never a crash -----------------------------
        with tempfile.TemporaryDirectory() as td2:
            bare = Path(td2)
            (bare / ".orbit").mkdir()
            r = run("digest", bare)
            if r.returncode != 0:
                failures.append(f"digest on a project with no user-model should exit 0: {r.stderr}")

    if failures:
        print("FAIL: context digest")
        for f in failures:
            print("  -", f)
        return 1
    print("PASS: context digest (visibility, bounded digest, compaction, idempotency, no-op)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
