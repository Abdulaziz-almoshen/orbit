#!/usr/bin/env python3
"""Deterministic project-scoped user-memory intake and review checkpoints.

The router records real user requests here. Strong correction/insistence language is captured as
pending evidence immediately, but never promoted automatically: the model must review it as data.
Delivery requires a review checkpoint after the latest request and no pending important events.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import tempfile
import time
from pathlib import Path

try:
    import fcntl
except ImportError:  # Windows fallback: atomic writes still prevent torn files; host single-writer applies.
    fcntl = None

IMPORTANT = re.compile(
    r"\b(always|never|must|important|remember|insist|not happy|don'?t want|do not want|"
    r"why (?:are|did|do|were) you|why you(?:'re| are| did| do| were)|you should|make sure|"
    r"every (?:time|session)|before (?:shipping|delivery))\b",
    re.IGNORECASE,
)
ACK = re.compile(r"^\s*(yes|no|ok(?:ay)?|thanks?|great|perfect|lgtm|go ahead|continue|proceed)\s*[.!]*\s*$",
                 re.IGNORECASE)
CONTROL = re.compile(r"[\x00-\x1f\x7f\x9b]|\x1b\[[0-9;?]*[ -/]*[@-~]")
SECRET = re.compile(
    r"\b(?:sk|pk|rk)-(?:proj-|ant-|live-|test-)?[A-Za-z0-9_-]{8,}|"
    r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{16,}|"
    r"\b(?:api[_-]?key|token|password|secret)(\s*[:=]\s*|\s+)[^\s'\"]{6,}", re.IGNORECASE)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _scrub(text: str, cap: int = 280) -> str:
    value = CONTROL.sub(" ", str(text or ""))
    value = SECRET.sub("[redacted]", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:cap] + ("…" if len(value) > cap else "")


def _paths(orbit: Path) -> tuple[Path, Path]:
    memory = orbit / "memory"
    memory.mkdir(parents=True, exist_ok=True)
    return memory / "checkpoint.json", memory / "user-events.jsonl"


def _default() -> dict:
    return {"schema_version": 1, "total_requests": 0, "last_reviewed_request": 0,
            "requests_since_review": 0, "pending_event_ids": [], "last_reviewed_at": None,
            "last_review_summary": "not reviewed yet"}


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else _default()
    except Exception:
        return _default()


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".user-memory-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


@contextlib.contextmanager
def _lock(orbit: Path):
    """Serialize request counters across concurrent sessions; atomic replace alone prevents tears, not lost increments."""
    lock_root = Path(tempfile.gettempdir()) / "orbit-user-memory-locks"
    lock_root.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(str(orbit.resolve()).encode()).hexdigest()[:24]
    with (lock_root / f"{key}.lock").open("a+") as handle:
        if fcntl is None:
            yield
            return
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def record_request(orbit: Path, prompt: str, max_interval: int = 5) -> dict:
    """Count a real request and capture a bounded, sanitized important-event excerpt."""
    with _lock(orbit):
        return _record_request_unlocked(orbit, prompt, max_interval)


def _record_request_unlocked(orbit: Path, prompt: str, max_interval: int = 5) -> dict:
    text = str(prompt or "").strip()
    checkpoint, events = _paths(orbit)
    state = _read(checkpoint)
    if not text or text.startswith("/") or ACK.match(text):
        return status(orbit, max_interval=max_interval)
    state["total_requests"] = int(state.get("total_requests", 0)) + 1
    state["requests_since_review"] = state["total_requests"] - int(state.get("last_reviewed_request", 0))
    captured = None
    if IMPORTANT.search(text):
        event_id = f"U{state['total_requests']}"
        if event_id not in state.setdefault("pending_event_ids", []):
            captured = {"schema_version": 1, "event_id": event_id, "request_number": state["total_requests"],
                        "captured_at": _now(), "source": "user-stated", "status": "pending_review",
                        "excerpt": _scrub(text)}
            with events.open("a") as handle:
                handle.write(json.dumps(captured, ensure_ascii=False) + "\n")
            state["pending_event_ids"].append(event_id)
    state["review_required"] = bool(state["pending_event_ids"] or
                                    state["requests_since_review"] >= max_interval)
    _write(checkpoint, state)
    result = status(orbit, max_interval=max_interval)
    result["captured_event"] = captured
    return result


def status(orbit: Path, max_interval: int = 5, require_latest: bool = False) -> dict:
    checkpoint, _ = _paths(orbit)
    state = _read(checkpoint)
    total = int(state.get("total_requests", 0))
    reviewed = int(state.get("last_reviewed_request", 0))
    pending = list(state.get("pending_event_ids") or [])
    due = total - reviewed >= max_interval
    latest_unreviewed = total > reviewed
    has_review = bool(state.get("last_reviewed_at"))
    passed = not pending and not due and (not require_latest or (not latest_unreviewed and has_review))
    return {**state, "requests_since_review": total - reviewed, "pending_event_ids": pending,
            "review_due": due, "latest_request_reviewed": not latest_unreviewed and has_review,
            "passed": passed}


def _append_signal(model: Path, event_ids: list[str], summary: str) -> None:
    line = f"- {_now()[:10]} {','.join(event_ids)} [stated]: {summary}\n"
    text = model.read_text() if model.exists() else "# User model\n\n## Signals\n\n"
    marker = "## Signals"
    if marker in text:
        at = text.index("\n", text.index(marker)) + 1
        tail = text[at:]
        tail = re.sub(r"^\s*\(none yet\)\s*", "\n", tail, count=1)
        model.write_text(text[:at] + "\n" + line + tail.lstrip("\n"))
    else:
        model.write_text(text.rstrip() + "\n\n## Signals\n\n" + line)


def review(orbit: Path, event_ids: list[str], decision: str, summary: str) -> dict:
    with _lock(orbit):
        return _review_unlocked(orbit, event_ids, decision, summary)


def _review_unlocked(orbit: Path, event_ids: list[str], decision: str, summary: str) -> dict:
    checkpoint, events = _paths(orbit)
    state = _read(checkpoint)
    pending = list(state.get("pending_event_ids") or [])
    chosen = pending if event_ids == ["all"] else event_ids
    unknown = [event_id for event_id in chosen if event_id not in pending]
    if unknown:
        raise ValueError("not pending: " + ", ".join(unknown))
    if decision == "checkpoint" and pending:
        raise ValueError("pending important events must be promoted or dismissed before checkpoint")
    clean_summary = _scrub(summary, 400)
    if not clean_summary:
        raise ValueError("a reason-carrying review summary is required")
    for event_id in chosen:
        with events.open("a") as handle:
            handle.write(json.dumps({"schema_version": 1, "event_id": event_id,
                                     "reviewed_at": _now(), "status": decision,
                                     "review_summary": clean_summary}, ensure_ascii=False) + "\n")
        pending.remove(event_id)
    if decision == "promote" and chosen:
        model = orbit / "skills" / "user-model.md"
        _append_signal(model, chosen, clean_summary)
    state["pending_event_ids"] = pending
    state["last_reviewed_request"] = int(state.get("total_requests", 0))
    state["requests_since_review"] = 0
    state["last_reviewed_at"] = _now()
    state["last_review_summary"] = clean_summary
    state["review_required"] = bool(pending)
    _write(checkpoint, state)
    return status(orbit, require_latest=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("status", "review"))
    parser.add_argument("--root", default=".")
    parser.add_argument("--max-interval", type=int, default=5)
    parser.add_argument("--require-latest", action="store_true")
    parser.add_argument("--event", action="append", default=[])
    parser.add_argument("--decision", choices=("promote", "dismiss", "checkpoint"), default="checkpoint")
    parser.add_argument("--summary", default="")
    args = parser.parse_args()
    orbit = Path(args.root).resolve() / ".orbit"
    try:
        result = (status(orbit, args.max_interval, args.require_latest) if args.command == "status" else
                  review(orbit, args.event or ["all"], args.decision, args.summary))
    except Exception as exc:
        print(json.dumps({"passed": False, "error": str(exc)}))
        raise SystemExit(2)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result.get("passed") else 1)


if __name__ == "__main__":
    main()
