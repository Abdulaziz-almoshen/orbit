#!/usr/bin/env python3
"""
route.py — Orbit's UserPromptSubmit hook: the deterministic router in front of EVERY message.

Once Orbit is installed in a repo, Claude Code runs this BEFORE the model sees each user prompt.
It classifies the request (task vs. question) deterministically and injects the **default lane** as
a live instruction every turn. The injection is mechanical and guaranteed (it fires every turn, no
model in the loop) — but it's a keyword matcher, not the last word: the model executes the loop and
may override a clear misclassification with a one-line reason (the Dispatcher role ratifies).

- TASK (build / fix / add / implement / an operational command, incl. polite "can you…") → route through the loop.
- QUESTION (status / explanation / "how do I…") → answer directly, no loop.
- ACK / negation / slash-command / short reply ("yes", "go ahead", "don't…", "/orbit") → inject nothing.
- AMBIGUOUS → inject a SOFT directive: decide the lane yourself; only ask if genuinely blocked.

Honest scope: classification is a fast, **deterministic English-keyword matcher** (not an LLM, not
NLP) — non-English or unusual phrasing falls to the soft "ambiguous" directive rather than being
forced. The hook DECIDES the lane and injects the directive every turn (that part is the system's,
guaranteed); the model still *executes* the loop — a hook can't run the sub-agent team itself. It
FAILS OPEN: any error → no injection, prompt proceeds untouched. It never blocks a prompt. (The
§8 SAFETY hook is the different one — a hard wall that can actually stop a tool; this router only
injects text.)
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

# A bare acknowledgment / confirmation / short reply → the loop must NOT interject.
ACK_PAT = re.compile(
    r"^\s*(y|yes|yep|yeah|no|nope|ok|okay|k|sure|sounds good|go ahead|go for it|proceed|"
    r"continue|do it|please do|makes sense|got it|great|perfect|nice|thanks|thank you|ty|thx|"
    r"lgtm|ship it|approved|correct|right|agreed|option\s+\w+|[a-d1-9])\s*[.!)]*\s*$",
    re.IGNORECASE,
)

# Verbs that mean "change the product / do operational work" → route through the loop.
TASK_PAT = re.compile(
    r"\b("
    r"build|implement|add|create|make|develop|fix|debug|refactor|rewrite|write|"
    r"set\s?up|scaffold|migrate|redesign|re-?design|port|integrate|optimi[sz]e|"
    r"rename|remove|delete|drop|update|change|modify|replace|convert|generate|"
    r"wire|hook\s?up|deploy|ship|build\s?out|"
    r"run|execute|install|uninstall|commit|push|merge|rebase|revert|bump|release|tag|"
    r"test|retest|verify|translate|move|extract|split|configure|connect|disconnect|"
    r"upgrade|downgrade|format|lint|clean|seed|mock|stub|document|benchmark|profile|"
    r"roll\s?back|start\s+(?:dev|development|building|implementing)"
    r")\b",
    re.IGNORECASE,
)

# A polite request that WRAPS an action ("can you fix…", "please add…") → still a task.
POLITE_PAT = re.compile(
    r"^\s*(please\s+)?(can|could|would|will|would you mind)\s+(you\s+)?(please\s+)?", re.IGNORECASE,
)

# Genuine info-seeking openers → answer directly. (NO can/could/would/will — those are requests.)
QUESTION_PAT = re.compile(
    r"^\s*(what|whats|what's|why|how|when|where|who|which|is|are|am|do|does|did|should|"
    r"has|have|explain|describe|clarify|walk\s+me|status|is\s+it|is\s+there)\b",
    re.IGNORECASE,
)

# Leading negation of an action → the user is deferring/declining; don't route it as work-to-do.
NEGATION_PAT = re.compile(r"^\s*(don'?t|do not|no need to|never mind|nevermind|stop|hold off|not yet)\b",
                          re.IGNORECASE)

TASK_CTX = (
    "[orbit] ROUTING — default lane: TASK. Route it through the loop (deterministic keyword match; "
    "if it's clearly NOT a task, say so in one line and answer directly instead). "
    "**If it's a substantial goal/feature, the planning team reviews it as experts FIRST, before "
    "building.** Understand the real intent, then bring the team's knowledge to bear (discovery: is "
    "this the right bet?; prior-art/market: does it already exist, or is there a better/reusable way?; "
    "technical judgment: risks, blast radius, a simpler path). **If that knowledge reveals something "
    "material — a wrong premise, a better/more scalable approach, a real risk, a reuse-over-build, or "
    "a missing requirement — you MUST surface it to the user, backed by evidence (the 'surprise': be "
    "smarter than the ask), as an AskUserQuestion with selectable options, your recommendation first "
    "labeled '(Recommended)' — never a question buried in prose.** If the goal and the plan are genuinely sound and you have nothing "
    "material to add, say so in ONE line and proceed — never manufacture friction, never rubber-stamp "
    "when you do have a better read. Then run read→plan→act→evaluate→update→decide via the roles in "
    ".claude/agents/. Small/clear/reversible → just do it (no review theater). Drive the "
    "TaskCreate/TaskUpdate checklist + write .orbit/tasks.json + .orbit/activity.jsonl. Do NOT "
    "free-edit a source-of-truth file outside the loop."
)
QUESTION_CTX = (
    "[orbit] ROUTING — default lane: QUESTION. Answer it directly: no loop, no roles, no ceremony "
    "(deterministic keyword match; if it's actually a task, say so and route it). Read "
    ".orbit/STATE.md only if it helps."
)
AMBIGUOUS_CTX = (
    "[orbit] routing: unclassified — decide the lane yourself per CLAUDE.md §10 (task → loop; "
    "question → answer directly). Do NOT force a question. Only if a genuinely blocking ambiguity "
    "stops you from proceeding, ask ONE AskUserQuestion (2-4 selectable options, your recommendation "
    "FIRST labeled '(Recommended)', a one-line trade-off each — never a question buried in prose)."
)


_INFO_OPENER = re.compile(
    r"^\s*(explain|describe|clarify|walk\s+me|show|list|tell|what|whats|what's|how|why|when|"
    r"where|who|which)\b", re.IGNORECASE,
)


def classify(prompt: str) -> str:
    p = prompt.strip()
    if not p or p.startswith("/"):              # slash-commands / empty → don't interfere
        return "skip"
    if ACK_PAT.match(p):                          # "yes" / "ok" / "go ahead" / "option 2" → say nothing
        return "skip"
    if NEGATION_PAT.match(p):                     # "don't build X yet" → not work-to-do; don't interject
        return "skip"

    has_task = bool(TASK_PAT.search(p))
    ends_q = p.rstrip().endswith("?")
    opener_q = bool(QUESTION_PAT.match(p))
    polite = POLITE_PAT.match(p)

    if polite:                                    # "can you <X>" — a request, not an interrogative
        if has_task:
            return "task"                         # "can you fix the bug?" → task
        rem = p[polite.end():]
        return "question" if _INFO_OPENER.match(rem) else "ambiguous"  # "can you explain…" → question

    if opener_q:                                  # "how do I add X?" / "what does Y do?" → answer
        return "question"
    if has_task:                                  # imperative action → loop
        return "task"
    if ends_q:                                    # a trailing '?' with no task verb → a question
        return "question"
    if len(p.split()) < 4:                        # short, no verb, not a question → don't interject
        return "skip"
    return "ambiguous"


# Strip ANSI/terminal control sequences so a prompt can't inject codes into the live view:
# OSC (ESC] … BEL/ST), PM/APC/DCS (ESC ^/_/P … ST), CSI (ESC[ …), and C0 controls / DEL / 8-bit CSI.
_CONTROL = re.compile(
    r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)?"
    r"|\x1b[\^_P][^\x1b]*(?:\x1b\\)?"
    r"|\x1b\[[0-9;?]*[ -/]*[@-~]"
    r"|[\x00-\x1f\x7f\x9b]"
)

# Known secret shapes — replaced with [redacted] so a key pasted into a prompt never lands in the
# activity log. Bias to over-redact: a false positive costs a garbled word, a miss leaks a key.
_SECRET_PREFIX = re.compile(
    r"\bsk-(?:proj|ant|live|test)-[A-Za-z0-9_\-]{6,}"    # OpenAI/Anthropic/Stripe project keys
    r"|\b(?:sk|pk|rk)-[A-Za-z0-9]{16,}"                  # generic sk-/pk-/rk- keys
    r"|\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{16,}"       # GitHub tokens
    r"|\bgithub_pat_[A-Za-z0-9_]{20,}"
    r"|\bAKIA[0-9A-Z]{16}\b"                             # AWS access key id
    r"|\bASIA[0-9A-Z]{16}\b"
    r"|\bxox[baprs]-[A-Za-z0-9\-]{10,}"                  # Slack
    r"|\bAIza[0-9A-Za-z_\-]{20,}"                        # Google API key
    r"|\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{4,}"  # JWT
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----",
    re.IGNORECASE,
)
# labeled secrets: keep the label, redact the value — `token: abc123` → `token: [redacted]`
_SECRET_KV = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?key|secret(?:[_-]?key)?|token|password|passwd|pwd|bearer|authorization)"
    r"(\s*[:=]\s*|\s+)([^\s'\"]{6,})"
)


def _scrub_secrets(t: str) -> str:
    t = _SECRET_PREFIX.sub("[redacted]", t)
    t = _SECRET_KV.sub(lambda m: f"{m.group(1)}{m.group(2)}[redacted]", t)
    return t


def _redact(text: str, cap: int = 80) -> str:
    """A privacy-safe, dashboard-safe summary of a prompt: strip ANSI/terminal escapes + control
    chars (no terminal injection / OSC framing), scrub anything that looks like a secret (API keys,
    tokens, JWTs, private keys), collapse whitespace, cap length. We log a short redacted summary for
    context, never the full raw prompt — and never a key that happened to be in it."""
    t = _CONTROL.sub(" ", str(text or ""))
    t = _scrub_secrets(t)
    t = re.sub(r"\s+", " ", t).strip()
    return (t[: cap - 1] + "…") if len(t) > cap else t


def _find_orbit(start: Path) -> Path:
    """Find the nearest .orbit/ from `start` upward (so working in packages/app still records to the
    repo-root scaffold). Prefers $CLAUDE_PROJECT_DIR when it points at a scaffolded repo. None if none."""
    import os
    proj = os.environ.get("CLAUDE_PROJECT_DIR")
    if proj and (Path(proj) / ".orbit").is_dir():
        return Path(proj) / ".orbit"
    try:
        cur = Path(start).resolve()
    except Exception:
        return None
    for p in [cur, *cur.parents]:
        if (p / ".orbit").is_dir():
            return p / ".orbit"
    return None


def emit_activity(cwd: Path, kind: str, prompt: str) -> None:
    """Best-effort: let the system 'act first' visibly — log the routing DECISION to the stream.
    Stores a redacted, secret-scrubbed, control-stripped summary, never the raw prompt."""
    try:
        orbit = _find_orbit(cwd)
        if orbit is None or not orbit.is_dir():
            return
        run_id = ""
        try:                                     # best-effort: tie the event to the current run
            run_id = json.loads((orbit / "run.json").read_text()).get("run_id", "")
        except Exception:
            pass
        line = {  # schema 2 — same shape activity.py writes, so scripts/orbit-status renders it
            "schema": 2,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "run_id": run_id,
            "role": "dispatcher",
            "phase": "route",
            "status": "start" if kind == "task" else "info",
            "msg": f"routing: {kind} — {_redact(prompt)}",
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
