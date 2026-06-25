#!/usr/bin/env python3
"""
route.py — Orbit's UserPromptSubmit hook: the deterministic router in front of EVERY message.

Once Orbit is installed in a repo, Claude Code runs this BEFORE the model sees each user prompt.
*The system* classifies the request (task vs. question) — not the model — and injects the routing
decision as a live instruction every turn. This is what makes Orbit control the project instead of
being an optional rule the model may or may not follow.

- TASK (build / fix / add / implement / change the product) → inject: route it through the loop.
- QUESTION (status / explanation) → inject: answer directly, no loop.
- AMBIGUOUS → inject: ask one clarifying question, then route per CLAUDE.md §10.

Honest scope: the hook DECIDES routing deterministically and forces the directive into context every
turn (that part is the system's, guaranteed). The model still *executes* the loop — Claude Code can't
make a hook run the sub-agent team itself. But a per-turn, front-of-context, system-issued directive
is a real control layer, not a passive memory rule. It FAILS OPEN: any error → no injection, prompt
proceeds untouched. It never blocks a prompt.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

# Verbs/phrases that mean "change the product" → route through the loop.
TASK_PAT = re.compile(
    r"\b("
    r"build|implement|add|create|make|develop|fix|debug|refactor|rewrite|write|"
    r"set\s?up|scaffold|migrate|redesign|re-?design|port|integrate|optimi[sz]e|"
    r"rename|remove|delete|drop|update|change|modify|replace|convert|generate|"
    r"wire|hook\s?up|deploy|ship|build\s?out|start\s+(?:dev|development|building|implementing)"
    r")\b",
    re.IGNORECASE,
)

# Interrogative / status openers → answer directly.
QUESTION_PAT = re.compile(
    r"^\s*(what|whats|what's|why|how|when|where|who|which|is|are|am|do|does|did|"
    r"can|could|should|would|will|has|have|explain|show|list|tell\s+me|describe|"
    r"status|are\s+we|is\s+it)\b",
    re.IGNORECASE,
)

TASK_CTX = (
    "[orbit] SYSTEM ROUTING DECISION — this message is a TASK. Route it through the loop. "
    "**If it's a substantial goal/feature, the planning team reviews it as experts FIRST, before "
    "building.** Understand the real intent, then bring the team's knowledge to bear (discovery: is "
    "this the right bet?; prior-art/market: does it already exist, or is there a better/reusable way?; "
    "technical judgment: risks, blast radius, a simpler path). **If that knowledge reveals something "
    "material — a wrong premise, a better/more scalable approach, a real risk, a reuse-over-build, or "
    "a missing requirement — you MUST surface it to the user, backed by evidence (the 'surprise': be "
    "smarter than the ask).** If the goal and the plan are genuinely sound and you have nothing "
    "material to add, say so in ONE line and proceed — never manufacture friction, never rubber-stamp "
    "when you do have a better read. Then run read→plan→act→evaluate→update→decide via the roles in "
    ".claude/agents/. Small/clear/reversible → just do it (no review theater). Drive the "
    "TaskCreate/TaskUpdate checklist + write .orbit/tasks.json + .orbit/activity.jsonl. Do NOT "
    "free-edit a source-of-truth file outside the loop."
)
QUESTION_CTX = (
    "[orbit] SYSTEM ROUTING DECISION — this message is a QUESTION. Answer it directly: no loop, no "
    "roles, no ceremony. Read .orbit/STATE.md only if it helps."
)
AMBIGUOUS_CTX = (
    "[orbit] SYSTEM ROUTING DECISION — ambiguous. Ask exactly ONE clarifying question, then route per "
    "CLAUDE.md §10 (task → loop; question → direct). Lean to the loop if it would change the product."
)


def classify(prompt: str) -> str:
    p = prompt.strip()
    if not p or p.startswith("/"):          # slash-commands / empty → don't interfere
        return "skip"
    has_task = bool(TASK_PAT.search(p))
    looks_question = bool(QUESTION_PAT.match(p)) or p.rstrip().endswith("?")
    if has_task and not looks_question:
        return "task"
    if has_task and looks_question:          # "how do I add X?" — asking, not commanding
        return "question"
    if looks_question:
        return "question"
    return "ambiguous"


def emit_activity(cwd: Path, kind: str, prompt: str) -> None:
    """Best-effort: let the system 'act first' visibly — log the routing decision to the stream."""
    try:
        orbit = cwd / ".orbit"
        if not orbit.is_dir():
            return
        line = {
            "ts": int(time.time()),
            "who": "dispatcher",
            "phase": "route",
            "status": "start" if kind == "task" else "info",
            "msg": f"routing decision: {kind} — {prompt[:80]}",
        }
        with (orbit / "activity.jsonl").open("a") as f:
            f.write(json.dumps(line) + "\n")
    except Exception:
        pass


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)                          # fail open
    prompt = str(data.get("prompt", "") or "")
    cwd = Path(data.get("cwd") or ".")

    kind = classify(prompt)
    if kind == "skip":
        sys.exit(0)

    ctx = {"task": TASK_CTX, "question": QUESTION_CTX, "ambiguous": AMBIGUOUS_CTX}[kind]
    if kind in ("task", "ambiguous"):
        emit_activity(cwd, kind, prompt)

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": ctx,
        }
    }))
    sys.exit(0)


if __name__ == "__main__":
    main()
