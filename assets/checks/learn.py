#!/usr/bin/env python3
"""
learn.py — Orbit's active-learning ledger (the anti-thrash backbone).

The model decides *what* is worth learning (the gate lives in `active-learning.md`); this script
only **validates + appends** the structured record, and reads it back deduped/decayed. Append-only
JSONL is the source of truth — markdown (CLAUDE.md / skills / decisions log) is a *promoted view*
generated from it, never surgically rewritten every turn. This is the design mem0 / gstack / Zep all
converged on to avoid file churn.

Usage:
  learn.py record '{"type":"convention","key":"rtl-everywhere","insight":"…","confidence":9,"source":"user-stated","files":["src/x"]}'
  learn.py recall [--limit N]      # deduped (latest wins per key|type), confidence-decayed, ranked

Safety (silent posture): the *helper* enforces schema + an injection scan + trust-by-source. The
user-origin gate (only promote standing rules from the user's own message, never tool/web/PR text)
is the model's job per active-learning.md. Fails open; never blocks.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

LEDGER = Path(".orbit/learnings.jsonl")
# Durable CROSS-PROJECT rules live outside any one repo, in ORBIT_HOME. Promotion here is the ONLY way a
# learning becomes a standing rule — and it is a deliberate HUMAN act (`orbit-memory promote`), NEVER
# automatic, and gated on source==user-stated + the injection scan. So a prompt-injected "rule" (which is
# 'observed'/'inferred' at best, and refused at record time if it smells injected) can't auto-promote.
DURABLE = Path(os.path.expanduser(os.environ.get("ORBIT_HOME", "~/.orbit"))) / "durable-rules.jsonl"
TYPES = {"convention", "pattern", "pitfall", "preference", "domain", "decision"}
SOURCES = {"user-stated", "observed", "inferred"}
KEY_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,48}$")
# reject insight text that smells like an injected instruction (poisoning defense)
INJECTION_RE = re.compile(
    r"(ignore (all|previous|prior)|disregard|system prompt|you are now|"
    r"</?(system|instructions?)>|exfiltrat|curl\s+http|rm\s+-rf)", re.I)
DECAY_DAYS = 30  # observed/inferred lose 1 confidence point per 30 days; user-stated never decays


def _fail(msg: str) -> None:
    sys.stderr.write(f"learn.py: {msg}\n")
    sys.exit(0)  # fail OPEN — a bad record is dropped, never blocks the agent


def record(raw: str) -> None:
    try:
        e = json.loads(raw)
    except Exception:
        _fail("record is not valid JSON — dropped")
        return
    t = str(e.get("type", "")).lower()
    key = str(e.get("key", "")).lower()
    src = str(e.get("source", "")).lower()
    insight = str(e.get("insight", "")).strip()
    try:
        conf = int(e.get("confidence", 0))
    except Exception:
        conf = 0
    if t not in TYPES: _fail(f"bad type {t!r} (one of {sorted(TYPES)})"); return
    if not KEY_RE.match(key): _fail(f"bad key {key!r} (kebab-case, 2-49 chars)"); return
    if src not in SOURCES: _fail(f"bad source {src!r}"); return
    if not (1 <= conf <= 10): _fail("confidence must be 1-10"); return
    if not insight: _fail("empty insight"); return
    if INJECTION_RE.search(insight): _fail("insight looks injected — refused"); return

    row = {
        "ts": int(time.time()),
        "type": t, "key": key, "insight": insight[:500],
        "confidence": conf, "source": src,
        "trusted": src == "user-stated",         # only user-stated rules are trusted across projects
        "files": [str(f) for f in (e.get("files") or [])][:10],
        "skill": str(e.get("skill", ""))[:60],
    }
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a") as f:
        f.write(json.dumps(row) + "\n")
    print(f"recorded: [{t}] {key} (conf {conf}, {src})")


def _ts(r) -> float:
    try:
        return float(r.get("ts", 0))
    except (TypeError, ValueError):
        return 0.0


def _rows() -> list:
    if not LEDGER.exists():
        return []
    out = []
    for ln in LEDGER.read_text().splitlines():
        try:
            r = json.loads(ln)
            if isinstance(r, dict):
                out.append(r)
        except Exception:
            continue                                     # a bad line never breaks recall
    return out


def _latest(rows: list) -> dict:
    """Dedup by (key|type): latest timestamp wins (an 'update' == append with same key). A tombstone
    (forget) is the latest record → the key is dropped from the live view."""
    latest: dict = {}
    for r in rows:
        k = (r.get("key"), r.get("type"))
        if k not in latest or _ts(r) >= _ts(latest[k]):
            latest[k] = r
    return {k: r for k, r in latest.items() if not r.get("tombstone")}


def _eff(r, now) -> int:
    try:
        eff = int(r.get("confidence", 0) or 0)
    except (TypeError, ValueError):
        eff = 0
    if r.get("source") != "user-stated":                # decay unverified; user-stated holds
        eff -= int((now - _ts(r)) // (DECAY_DAYS * 86400))
    return eff


def recall(limit: int) -> None:
    now = time.time()
    out = [(_eff(r, now), _ts(r), r) for r in _latest(_rows()).values()]
    out.sort(key=lambda x: (x[0], x[1]), reverse=True)
    for eff, _t, r in out[:limit]:
        conf = r.get("confidence", "?")
        print(f"[{r.get('type', '?')}] {r.get('key', '?')} "
              f"(eff {max(eff, 0)}/{conf}, {r.get('source', '?')}): {r.get('insight', '')}")


def promote(key: str) -> None:
    """HUMAN action: promote a learning to a durable CROSS-PROJECT rule (ORBIT_HOME/durable-rules.jsonl).
    The security boundary: nothing auto-promotes; promotion is ALWAYS explicit AND gated on
    source==user-stated + the injection scan — so an injected/observed 'rule' can never become standing."""
    cands = [r for r in _latest(_rows()).values() if r.get("key") == key.lower()]
    if not cands:
        _fail(f"no live learning with key {key!r} to promote"); return
    r = max(cands, key=_ts)
    if r.get("source") != "user-stated":
        print(f"REFUSED: {key} is source={r.get('source')!r}. Only USER-STATED learnings can become "
              f"durable cross-project rules (prompt-injected/observed content never auto-promotes).")
        return
    if INJECTION_RE.search(str(r.get("insight", ""))):
        print(f"REFUSED: {key} insight looks injected — not promoted."); return
    DURABLE.parent.mkdir(parents=True, exist_ok=True)
    rule = {"ts": int(time.time()), "key": r["key"], "type": r.get("type"), "insight": r.get("insight"),
            "confidence": r.get("confidence"), "source": "user-stated",
            "origin_project": Path.cwd().name, "promoted_at": int(time.time())}
    with DURABLE.open("a") as f:
        f.write(json.dumps(rule) + "\n")
    print(f"promoted: [{r.get('type')}] {key} → durable cross-project rule ({DURABLE})")


def forget(key: str) -> None:
    """Append a tombstone so a key drops out of the live view (append-only — history is preserved)."""
    cands = [r for r in _latest(_rows()).values() if r.get("key") == key.lower()]
    if not cands:
        _fail(f"no live learning with key {key!r} to forget"); return
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a") as f:
        for r in cands:
            f.write(json.dumps({"ts": int(time.time()), "key": r["key"], "type": r.get("type"),
                                "tombstone": True}) + "\n")
    print(f"forgot: {key} (tombstoned; history preserved)")


def review() -> None:
    """The memory-hygiene surface: what's live, what's promotable, what CONFLICTS, and what's durable."""
    rows = _rows()
    live = _latest(rows)
    now = time.time()
    # conflicts: a key recorded with MORE THAN ONE distinct source or insight across its history
    by_key: dict = {}
    for r in rows:
        if r.get("tombstone"):
            continue
        by_key.setdefault(r.get("key"), []).append(r)
    conflicts = {k: v for k, v in by_key.items()
                 if len({x.get("source") for x in v}) > 1 or len({x.get("insight") for x in v}) > 1}
    promotable = [r for r in live.values() if r.get("source") == "user-stated"]
    durable_n = len(DURABLE.read_text().splitlines()) if DURABLE.exists() else 0

    print(f"Orbit memory review — {len(live)} live learning(s) · {len(promotable)} promotable "
          f"(user-stated) · {len(conflicts)} conflicted · {durable_n} durable cross-project rule(s)")
    for eff, _t, r in sorted(((_eff(r, now), _ts(r), r) for r in live.values()), reverse=True):
        tag = "★ promotable" if r.get("source") == "user-stated" else "decays" if eff < int(r.get("confidence", 0) or 0) else ""
        warn = "  ⚠ CONFLICT" if r.get("key") in conflicts else ""
        print(f"  [{r.get('type','?')}] {r.get('key','?')} (eff {max(eff,0)}/{r.get('confidence','?')}, "
              f"{r.get('source','?')}) {tag}{warn}")
    if conflicts:
        print("  Conflicts need a human call: `orbit-memory forget <key>` the wrong one, or re-`record` the right one.")
    print("  Promote a user-stated learning to a standing cross-project rule: `orbit-memory promote <key>`.")


def main() -> None:
    argv = sys.argv
    if len(argv) >= 3 and argv[1] == "record":
        record(argv[2])
    elif len(argv) >= 2 and argv[1] == "recall":
        n = 5
        if "--limit" in argv:
            try: n = int(argv[argv.index("--limit") + 1])
            except Exception: n = 5
        recall(n)
    elif len(argv) >= 2 and argv[1] == "review":
        review()
    elif len(argv) >= 3 and argv[1] == "promote":
        promote(argv[2])
    elif len(argv) >= 3 and argv[1] in ("forget", "delete"):
        forget(argv[2])
    else:
        _fail("usage: learn.py record '<json>' | recall [--limit N] | review | promote <key> | forget <key>")


if __name__ == "__main__":
    main()
