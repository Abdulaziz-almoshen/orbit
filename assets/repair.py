#!/usr/bin/env python3
"""Structured repair packets for Orbit's bounded post-review iteration loop."""
from __future__ import annotations

import json
from pathlib import Path

SCHEMA = 1
STATUSES = {"queued", "in_progress", "passed", "blocked", "escalated"}
SOURCES = {"reviewer", "qa", "safety", "counterfactual"}
SEVERITIES = {"P0", "P1", "P2", "P3"}


def _text(value, limit):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= limit


def validate(packet: dict, cfg: dict | None = None) -> list[str]:
    """Validate a repair packet before it enters the next build attempt."""
    limit = int(((cfg or {}).get("iteration", {}) or {}).get("max_failure_packet_bytes", 12000))
    errors = []
    if not isinstance(packet, dict):
        return ["packet must be an object"]
    if packet.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA}")
    required = ("id", "cycle", "attempt", "source", "severity", "criterion", "evidence",
                "failure", "root_cause", "required_change", "verification", "owner", "max_attempts", "status")
    for key in required:
        if key not in packet:
            errors.append(f"missing {key}")
    if not _text(packet.get("id"), 80):
        errors.append("id must be a short non-empty string")
    for key in ("cycle", "attempt", "max_attempts"):
        if not isinstance(packet.get(key), int) or packet.get(key, 0) < 1:
            errors.append(f"{key} must be a positive integer")
    if packet.get("source") not in SOURCES:
        errors.append(f"source must be one of {sorted(SOURCES)}")
    if packet.get("severity") not in SEVERITIES:
        errors.append(f"severity must be one of {sorted(SEVERITIES)}")
    for key in ("criterion", "evidence", "failure", "root_cause", "required_change", "owner"):
        if not _text(packet.get(key), 1200):
            errors.append(f"{key} must be a short non-empty string")
    verification = packet.get("verification")
    if not isinstance(verification, list) or not verification or len(verification) > 8:
        errors.append("verification must contain 1-8 checks")
    elif any(not _text(item, 300) for item in verification):
        errors.append("verification checks must be short strings")
    if packet.get("status") not in STATUSES:
        errors.append(f"status must be one of {sorted(STATUSES)}")
    try:
        if len(json.dumps(packet, ensure_ascii=False).encode()) > limit:
            errors.append(f"packet exceeds {limit} bytes")
    except (TypeError, ValueError):
        errors.append("packet must be JSON serializable")
    return errors


def next_action(packet: dict, cfg: dict | None = None) -> str:
    """Return the next deterministic action for a failed or completed repair."""
    max_attempts = int(((cfg or {}).get("iteration", {}) or {}).get("max_repair_attempts", 2))
    attempt = int(packet.get("attempt", 0))
    if packet.get("status") == "passed":
        return "retest-regression"
    if attempt > min(max_attempts, int(packet.get("max_attempts", max_attempts))):
        return "escalate"
    if packet.get("status") in {"queued", "in_progress"}:
        return "repair"
    return "escalate"


def load(path: str | Path, cfg: dict | None = None) -> dict:
    packet = json.loads(Path(path).read_text())
    errors = validate(packet, cfg)
    if errors:
        raise ValueError("invalid repair packet: " + "; ".join(errors))
    return packet


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Validate an Orbit repair packet")
    parser.add_argument("packet")
    args = parser.parse_args()
    try:
        load(args.packet)
    except Exception as exc:
        print(f"FAIL: {exc}")
        raise SystemExit(1)
    print("PASS: repair packet")
