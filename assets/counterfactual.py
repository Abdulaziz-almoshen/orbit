#!/usr/bin/env python3
"""Bounded Counterfactual Regret packets for Orbit's pre-build falsification gate."""
from __future__ import annotations

import json
from pathlib import Path

SCHEMA = 1
STATES = {"pending", "pass", "fail", "inconclusive"}
ROUTES = {"none", "discovery", "plan", "build", "review"}


def _text(value, limit):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= limit


def validate(packet: dict, cfg: dict | None = None) -> list[str]:
    """Return structural errors. A non-empty result means the packet cannot gate a build."""
    cf = (cfg or {}).get("counterfactual", {})
    max_h = int(cf.get("max_hypotheses", 3))
    max_bytes = int(cf.get("max_packet_bytes", 12000))
    errors = []
    if not isinstance(packet, dict):
        return ["packet must be an object"]
    if packet.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA}")
    for key in ("cycle", "decision", "assumption", "hypotheses", "selected_probe", "outcome", "backtrack"):
        if key not in packet:
            errors.append(f"missing {key}")
    if not isinstance(packet.get("cycle"), int) or packet.get("cycle", 0) < 1:
        errors.append("cycle must be a positive integer")
    if not _text(packet.get("decision"), 160):
        errors.append("decision must be a short non-empty string")
    if not _text(packet.get("assumption"), 500):
        errors.append("assumption must be a short non-empty string")
    hypotheses = packet.get("hypotheses")
    if not isinstance(hypotheses, list) or not hypotheses:
        errors.append("hypotheses must be a non-empty list")
    elif len(hypotheses) > max_h:
        errors.append(f"hypotheses must contain at most {max_h} items")
    else:
        for i, h in enumerate(hypotheses, 1):
            if not isinstance(h, dict):
                errors.append(f"hypothesis {i} must be an object")
                continue
            for key in ("failure", "signal", "probe"):
                if not _text(h.get(key), 500):
                    errors.append(f"hypothesis {i} missing short {key}")
    if not _text(packet.get("selected_probe"), int(cf.get("max_probe_words", 120)) * 8):
        errors.append("selected_probe is missing or too large")
    if packet.get("outcome") not in STATES:
        errors.append(f"outcome must be one of {sorted(STATES)}")
    if packet.get("backtrack") not in ROUTES:
        errors.append(f"backtrack must be one of {sorted(ROUTES)}")
    try:
        if len(json.dumps(packet, ensure_ascii=False).encode()) > max_bytes:
            errors.append(f"packet exceeds {max_bytes} bytes")
    except (TypeError, ValueError):
        errors.append("packet must be JSON serializable")
    return errors


def route_failure(kind: str, cfg: dict | None = None) -> str:
    """Map a failed probe to a bounded phase return, safely defaulting to discovery."""
    routes = ((cfg or {}).get("counterfactual", {}) or {}).get("failure_routes", {})
    route = routes.get(kind, "discovery")
    return route if route in ROUTES - {"none"} else "discovery"


def load(path: str | Path, cfg: dict | None = None) -> dict:
    packet = json.loads(Path(path).read_text())
    errors = validate(packet, cfg)
    if errors:
        raise ValueError("invalid counterfactual packet: " + "; ".join(errors))
    return packet


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Validate an Orbit counterfactual packet")
    parser.add_argument("packet")
    args = parser.parse_args()
    try:
        load(args.packet)
    except Exception as exc:
        print(f"FAIL: {exc}")
        raise SystemExit(1)
    print("PASS: counterfactual packet")
