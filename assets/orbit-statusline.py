#!/usr/bin/env python3
"""
orbit-statusline — the one-line Claude Code status line for an Orbit run.

Claude Code runs this every couple of seconds with its status-line JSON on stdin. We fuse that
(context %, cost, cache reuse, model) with the project's .orbit/run.json (phase, active role,
task progress, confidence, blocked state) into a single compact line, e.g.:

  🛰 build · builder · 5/9 · ctx 38% · $0.42 · cache 61% · conf 76%
  🛰 ⚠ needs input · build · 5/9 · ctx 38% · $0.42            (when a decision is pending)

Design rules: FAST (runs on a 2s refresh) and FAIL-SAFE — any missing/renamed field just drops
that one segment; a total failure prints an empty line, never a traceback. Cache reuse is labeled
honestly ("cache") — it's cache_read / total_input, NOT a fabricated "tokens saved".

Install: `.claude/settings.json` → {"statusLine": {"type":"command",
"command":"python3 \"$CLAUDE_PROJECT_DIR/scripts/orbit-statusline\"", "refreshInterval": 2}}.
Orbit wires this only if you don't already have a status line (never overwrites yours).
"""
import json
import os
import sys
import time
from pathlib import Path


def _get(d, *path, default=None):
    """Safe nested get: _get(data, 'context_window', 'used_percentage')."""
    cur = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def _age_seconds(iso_ts):
    """Seconds since an ISO 'YYYY-MM-DDTHH:MM:SSZ', or None if unparseable."""
    try:
        t = time.strptime(str(iso_ts), "%Y-%m-%dT%H:%M:%SZ")
        return max(0, int(time.time() - time.mktime(t) + time.timezone))
    except Exception:
        return None


def build_line(claude: dict, run: dict) -> str:
    seg = []
    blocked = run.get("blocked_question")
    if blocked:
        seg.append("⚠ needs input")

    phase = run.get("phase") or run.get("mode")
    if phase:
        seg.append(str(phase))

    role = run.get("active_role")
    if role and not blocked:
        seg.append(str(role))

    total = run.get("tasks_total")
    if isinstance(total, int) and total > 0:
        seg.append(f"{run.get('tasks_done', 0)}/{total}")

    # idle: only surface it once it's meaningful (the run may be waiting on the active agent)
    age = _age_seconds(run.get("last_ts"))
    if age is not None and age >= 30:
        seg.append(f"{age}s idle")

    ctx = _get(claude, "context_window", "used_percentage")
    if isinstance(ctx, (int, float)):
        seg.append(f"ctx {int(ctx)}%")

    cost = _get(claude, "cost", "total_cost_usd")
    if isinstance(cost, (int, float)):
        seg.append(f"${cost:.2f}")

    # cache reuse = cache_read / total_input (honest label — not "tokens saved")
    cur = _get(claude, "context_window", "current_usage", default={})
    total_in = _get(claude, "context_window", "total_input_tokens")
    cache_read = cur.get("cache_read_input_tokens") if isinstance(cur, dict) else None
    if isinstance(total_in, (int, float)) and total_in and isinstance(cache_read, (int, float)):
        seg.append(f"cache {int(100 * cache_read / total_in)}%")

    conf = run.get("confidence")
    if isinstance(conf, (int, float)):
        seg.append(f"conf {int(conf)}%")

    return "🛰 " + " · ".join(seg) if seg else ""


def main():
    try:
        claude = json.load(sys.stdin)
        if not isinstance(claude, dict):
            claude = {}
    except Exception:
        claude = {}
    try:
        project = claude.get("cwd") or _get(claude, "workspace", "current_dir") \
            or os.environ.get("CLAUDE_PROJECT_DIR") or "."
        run = json.loads((Path(project) / ".orbit" / "run.json").read_text())
        if not isinstance(run, dict):
            run = {}
    except Exception:
        run = {}
    try:
        print(build_line(claude, run))
    except Exception:
        print("")                                           # never crash the status line


if __name__ == "__main__":
    main()
