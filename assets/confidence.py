#!/usr/bin/env python3
"""
confidence.py — delivery confidence from EVIDENCE, not vibes.

A single number (0–100) + a plain-English reason, computed from the proof signals a run actually
produced (passing tests, a clean reviewer/safety/QA gate) and the risks it carries (a failing test,
an unresolved blocker, a large unreviewed diff, a safety concern). It's the honest answer to "how
sure are we this is done?" — and it degrades gracefully: no evidence yet ⇒ a neutral 50, not a
fake 100.

Used by the Reporter (final answer), orbit-status (the dashboard), and orbit-statusline. Stdlib
only; never raises — a malformed signal is ignored, not fatal.

Signal weights (deltas off a neutral base of 50):
  +15 tests pass        -15 a failing test
  +10 lint/typecheck    -10 an unresolved blocker
  +10 reviewer pass     -10 a large unreviewed diff
  +10 safety pass       -20 a safety concern
  +10 QA / pixel pass
"""
from __future__ import annotations

BASE = 50

# proof.kind (or a signal key) -> {status: points}. A "pass" adds; a "fail" subtracts (its own weight).
_POSITIVE = {
    "test": 15, "tests": 15,
    "lint": 10, "typecheck": 10, "types": 10,
    "review": 10, "reviewer": 10,
    "safety": 10,
    "qa": 10, "pixel": 10,
}
_FAIL_PENALTY = {
    "test": -15, "tests": -15,
    "safety": -20,                                   # a safety FAIL is the heaviest signal
}
_DEFAULT_FAIL = -10                                  # any other failing check

# Risk flags (not proof events) — passed to evaluate() as booleans/counts.
_BLOCKER = -10
_LARGE_UNREVIEWED_DIFF = -10


def _clamp(n: int) -> int:
    return max(0, min(100, int(n)))


def evaluate(proof_events=None, blockers: int = 0, large_unreviewed_diff: bool = False):
    """Return {"score": int 0-100, "reason": str, "components": [(label, delta)]}.

    proof_events: iterable of {"kind": str, "status": "pass"|"fail"|...} (e.g. the proof field of
                  activity events). blockers: count of unresolved blockers. large_unreviewed_diff:
                  True if the diff is big and hasn't been reviewed."""
    score = BASE
    parts, passed, pending, failed = [], [], [], []
    seen = set()

    for ev in (proof_events or []):
        try:
            kind = str((ev or {}).get("kind", "")).lower().strip()
            status = str((ev or {}).get("status", "")).lower().strip()
        except Exception:
            continue
        if not kind or kind in seen:                # count each kind once (latest wins upstream)
            continue
        if status in ("pass", "passed", "ok", "green"):
            pts = _POSITIVE.get(kind, 0)
            if pts:
                score += pts
                parts.append((f"{kind} pass", pts))
                passed.append(kind)
                seen.add(kind)
        elif status in ("fail", "failed", "red", "error"):
            pts = _FAIL_PENALTY.get(kind, _DEFAULT_FAIL)
            score += pts
            parts.append((f"{kind} FAIL", pts))
            failed.append(kind)
            seen.add(kind)
        else:
            pending.append(kind)

    try:
        b = int(blockers or 0)
    except Exception:
        b = 0
    if b > 0:
        score += _BLOCKER * b
        parts.append((f"{b} blocker(s)", _BLOCKER * b))
    if large_unreviewed_diff:
        score += _LARGE_UNREVIEWED_DIFF
        parts.append(("large unreviewed diff", _LARGE_UNREVIEWED_DIFF))

    score = _clamp(score)
    bits = []
    if passed:
        bits.append(", ".join(sorted(set(passed))) + " pass")
    if failed:
        bits.append(", ".join(sorted(set(failed))) + " FAIL")
    if pending:
        bits.append(", ".join(sorted(set(pending))) + " pending")
    if b > 0:
        bits.append(f"{b} blocker(s)")
    if large_unreviewed_diff:
        bits.append("large unreviewed diff")
    reason = f"{score}%: " + ("; ".join(bits) if bits else "no evidence yet — neutral")
    return {"score": score, "reason": reason, "components": parts}


def score(proof_events=None, blockers: int = 0, large_unreviewed_diff: bool = False) -> int:
    return evaluate(proof_events, blockers, large_unreviewed_diff)["score"]
