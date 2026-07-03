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
import re
import sys
import time
from pathlib import Path

LEDGER = Path(".orbit/learnings.jsonl")
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


def recall(limit: int) -> None:
    if not LEDGER.exists():
        return
    def _ts(r):
        try:
            return float(r.get("ts", 0))
        except (TypeError, ValueError):
            return 0.0

    rows = []
    for ln in LEDGER.read_text().splitlines():
        try:
            r = json.loads(ln)
            if isinstance(r, dict):
                rows.append(r)
        except Exception:
            continue                                     # a bad line never breaks recall
    # dedup by (key|type): latest timestamp wins (an "update" == append with same key)
    latest: dict = {}
    for r in rows:
        k = (r.get("key"), r.get("type"))
        if k not in latest or _ts(r) >= _ts(latest[k]):
            latest[k] = r
    now = time.time()
    out = []
    for r in latest.values():
        try:
            eff = int(r.get("confidence", 0) or 0)
        except (TypeError, ValueError):
            eff = 0
        if r.get("source") != "user-stated":            # decay unverified; user-stated holds
            eff -= int((now - _ts(r)) // (DECAY_DAYS * 86400))
        out.append((eff, _ts(r), r))
    out.sort(key=lambda x: (x[0], x[1]), reverse=True)
    for eff, _t, r in out[:limit]:
        conf = r.get("confidence", "?")
        print(f"[{r.get('type', '?')}] {r.get('key', '?')} "
              f"(eff {max(eff, 0)}/{conf}, {r.get('source', '?')}): {r.get('insight', '')}")


def main() -> None:
    if len(sys.argv) >= 3 and sys.argv[1] == "record":
        record(sys.argv[2])
    elif len(sys.argv) >= 2 and sys.argv[1] == "recall":
        n = 5
        if "--limit" in sys.argv:
            try: n = int(sys.argv[sys.argv.index("--limit") + 1])
            except Exception: n = 5
        recall(n)
    else:
        _fail("usage: learn.py record '<json>' | learn.py recall [--limit N]")


if __name__ == "__main__":
    main()
