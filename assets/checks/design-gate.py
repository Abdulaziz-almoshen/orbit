#!/usr/bin/env python3
"""
Orbit design gate — a PreToolUse hook that catches the SILENT SKIP of the prototype-before-develop
gate on UI production files. It is a coarse traceability backstop, NOT a per-change heavy-redesign
blocker: it can only see which file is being edited (Claude Code's PreToolUse event carries
`tool_input.file_path` for Edit/Write/MultiEdit, never the content), so it cannot judge whether an
edit is "heavy" or verify that real prototypes were built or genuinely compared. What it CAN check
is whether *any* design-decision record exists for this work — a HEAVY approval
(`design/approved.json`) or a TRIVIAL triage marker (`.orbit/design/TRIVIAL`). Neither existing is
the one thing a hook can catch: the case where the Designer's determination step (see
`design-methodology.md`) never ran at all.

Honest v1 limitation, stated plainly: this is existence-based, not identity-based — it does not
verify the record is FOR the specific file/component being edited, only that *some* design
decision was recorded recently in this repo. A determined skip (touching an unrelated UI file
right after an unrelated approval) can slip past. That's the honest ceiling of a hook that only
sees a file path.

Protocol (Claude Code ≥ 2.1): read the PreToolUse JSON on stdin; print NOTHING to allow, or
    {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                            "permissionDecision": "ask",
                            "permissionDecisionReason": "..."}}
to pause for a human. This hook NEVER denies — a false positive costs one keystroke, not a
blocked workflow. It asks **at most once per cycle** (tracked via `.orbit/design/.asked`); once
the human clears it, every other UI edit in the same cycle proceeds silently. Fail OPEN: any
error allows the edit, because a guard must never brick a legitimate change.

Only wired into `.claude/settings.json` on repos with a UI surface (`has_ui` in scaffold.py) —
backend/data/CLI repos never see this hook.
"""
import json
import os
import re
import sys
from pathlib import Path

_UI_EXTS = {".tsx", ".jsx", ".vue", ".svelte", ".css", ".scss", ".html"}
_TEST_MARKERS = ("/test/", "/tests/", "/__tests__/", ".test.", ".spec.")


def _is_ui_production_file(file_path: str) -> bool:
    p = file_path.replace("\\", "/")
    if "/.orbit/" in f"/{p}" or p.startswith(".orbit/"):
        return False                                       # never gate the Designer's own previews
    ext = os.path.splitext(p)[1].lower()
    if ext not in _UI_EXTS:
        return False                                        # docs/config/backend never match this list
    low = p.lower()
    if any(m in low for m in _TEST_MARKERS):
        return False                                        # test files aren't production UI
    return True


def _has_design_record(root: Path) -> bool:
    """A HEAVY approval or a TRIVIAL triage marker exists anywhere in the repo. Existence-based
    (see the module docstring's honest limitation) — not tied to the specific file being edited."""
    return (root / "design" / "approved.json").exists() or \
           (root / ".orbit" / "design" / "TRIVIAL").exists()


def _current_cycle(root: Path):
    """Best-effort current loop cycle, for de-duplicating the ask (NOT for record freshness).
    Tries STATE.md's 'Iteration: <n> of <max>' line, then the last cycle-tagged activity.jsonl
    event. Returns None if unknowable — the ask still fires once, just without cycle-scoping."""
    state = root / ".orbit" / "STATE.md"
    if state.exists():
        try:
            m = re.search(r"Iteration:\s*(\d+)", state.read_text(errors="ignore"))
            if m:
                return int(m.group(1))
        except Exception:
            pass
    activity = root / ".orbit" / "activity.jsonl"
    if activity.exists():
        cycle = None
        try:
            for line in activity.read_text(errors="ignore").splitlines():
                try:
                    ev = json.loads(line)
                except Exception:
                    continue
                if isinstance(ev, dict) and "cycle" in ev:
                    cycle = ev["cycle"]
        except Exception:
            pass
        if cycle is not None:
            try:
                return int(cycle)
            except (TypeError, ValueError):
                return None
    return None


def _already_asked_this_cycle(root: Path, cur) -> bool:
    marker = root / ".orbit" / "design" / ".asked"
    if not marker.exists():
        return False
    try:
        stored = marker.read_text(errors="ignore").strip()
    except Exception:
        return True                                          # unreadable but present -> don't re-nag
    return stored == ("unknown" if cur is None else str(cur))


def _mark_asked(root: Path, cur) -> None:
    marker = root / ".orbit" / "design" / ".asked"
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("unknown" if cur is None else str(cur))
    except Exception:
        pass                                                  # best-effort; a write failure just
                                                                # means it may ask again — never fatal


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict) or data.get("tool_name") not in ("Edit", "Write", "MultiEdit"):
            return  # allow (print nothing) — not a file-editing tool call
        file_path = (data.get("tool_input") or {}).get("file_path") or ""
        if not file_path or not _is_ui_production_file(file_path):
            return  # allow — not a UI production file this gate cares about
        root = Path(data.get("cwd") or ".")
        if _has_design_record(root):
            return  # allow — a design decision trail exists
        cur = _current_cycle(root)
        if _already_asked_this_cycle(root, cur):
            return  # allow — already asked once this cycle, don't nag on every subsequent edit
        _mark_asked(root, cur)
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": (
                "[orbit] UI production edit with no design record this cycle — if this is HEAVY, "
                "run the prototype gate (design-methodology.md) and write design/approved.json; "
                "if TRIVIAL, approve this once or drop .orbit/design/TRIVIAL."
            ),
        }}))
    except Exception:
        return  # fail OPEN — this gate must never brick a legitimate edit


if __name__ == "__main__":
    main()
