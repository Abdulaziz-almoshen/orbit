#!/usr/bin/env python3
"""
lifecycle.py — pick the right lifecycle for a task, and render its phase strip.

Different work has a different natural shape; showing the wrong one ("Discover → Plan → Build …"
for a one-line bug fix) makes the dashboard lie. This detects the mode from the task text and
supplies the ordered phases so orbit-status can draw an honest "where are we" strip. Stdlib only,
never raises.

Modes:
  feature:  Discover → Plan → Build → Verify → Safety → Report
  bug:      Reproduce → Diagnose → Fix → Regression → Report
  design:   Taste → Prototype → Select → Implement → Pixel-QA
  refactor: Map → Change → Compatibility → Tests → Review
  data:     Validate → Transform → Compare → Safety → Report
"""
from __future__ import annotations
import re

LIFECYCLES = {
    "feature":  ["discover", "plan", "build", "verify", "safety", "report"],
    "bug":      ["reproduce", "diagnose", "fix", "regression", "report"],
    "design":   ["taste", "prototype", "select", "implement", "pixel-qa"],
    "refactor": ["map", "change", "compatibility", "tests", "review"],
    "data":     ["validate", "transform", "compare", "safety", "report"],
}

# Checked in priority order — first mode whose pattern matches wins (bug beats design beats …).
_PATTERNS = [
    ("bug",      r"\b(bug|fix|broken|crash(?:es|ing)?|regression|reproduce|failing|stack ?trace|traceback|defect|hotfix|error)\b"),
    ("design",   r"\b(re-?design|design|ui|ux|styling?|layout|prototype|visual|css|typograph|palette|mockup|look and feel|theme)\b"),
    ("refactor", r"\b(refactor|clean ?up|restructure|rename|extract|decouple|tech ?debt|simplif|reorganiz)\b"),
    ("data",     r"\b(pipeline|etl|dataset|ingest|backfill|rollup|transform|schema migration|data ?warehouse|parquet)\b"),
    # feature is the default (add/build/implement/new/support/endpoint/…) — no pattern needed.
]


def detect(text: str) -> str:
    """Classify a task description into a lifecycle mode. Default: 'feature'."""
    t = (text or "").lower()
    for mode, pat in _PATTERNS:
        try:
            if re.search(pat, t):
                return mode
        except Exception:
            continue
    return "feature"


def phases(mode: str) -> list:
    return list(LIFECYCLES.get(mode, LIFECYCLES["feature"]))


def strip(mode: str, current_phase: str = "", sep: str = " › ") -> str:
    """Render the phase strip with the current phase bracketed, e.g.
    'Discover › Plan › [Build] › Verify › Safety › Report'. Case-insensitive on current_phase."""
    cur = (current_phase or "").lower().strip()
    out = []
    for p in phases(mode):
        label = p[:1].upper() + p[1:]
        out.append(f"[{label}]" if p == cur else label)
    return sep.join(out)
