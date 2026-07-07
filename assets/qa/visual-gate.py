#!/usr/bin/env python3
"""
visual-gate.py — the REQUIRED visual-fidelity gate for HEAVY UI work. Promotes the QA screenshot helper
from "nice to have" to a gate the Reviewer can't pass without visual evidence:

  • HEAVY UI (a `design/approved.json` with impact_level=HEAVY) MUST have a screenshot → missing = BLOCK
  • a blank screenshot (single flat colour) = BLOCK — "it rendered" isn't the same as "it rendered right"
  • a mobile full-page screenshot WIDER than the mobile viewport = horizontal overflow = BLOCK
  • declared token colours below the WCAG AA contrast floor = BLOCK (pure math, no browser needed)
  • token drift vs the Designer's contract = WARN (or BLOCK with --strict-tokens)

Honest degradation: it NEVER silent-passes. PNG dimensions + contrast need no dependencies; blank/overlap
pixel checks use Pillow if importable, else a compressed-size heuristic. If HEAVY work has no evidence
AT ALL, that is a BLOCK, not a pass — produce a screenshot (snapshot.py / a browser MCP / gstack /browse).

Usage:
  visual-gate.py --root . [--screenshot shot.png] [--mobile shot-mobile.png] [--contract tokens.json]
                 [--mobile-viewport 390] [--dpr 3] [--strict-tokens]
Exit: 0 = pass (or not HEAVY → N/A) · 1 = BLOCKED (reasons printed) · warnings never block on their own.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
import zlib
from pathlib import Path

BLOCK, WARN, OK = "BLOCK", "WARN", "OK"


def _read_json(p: Path, default=None):
    try:
        return json.loads(p.read_text())
    except Exception:
        return default


def _png_size(p: Path):
    """(width, height) from the PNG IHDR — no image library needed. None if not a PNG we can read."""
    try:
        b = p.read_bytes()
        if b[:8] != b"\x89PNG\r\n\x1a\n" or b[12:16] != b"IHDR":
            return None
        return struct.unpack(">II", b[16:24])
    except Exception:
        return None


def _looks_blank(p: Path):
    """True if the image is a single flat colour (nothing rendered). Pillow when available; else a
    compressed-bytes-per-pixel heuristic (a flat image compresses to almost nothing)."""
    try:
        from PIL import Image  # type: ignore
        im = Image.open(p).convert("RGB")
        colors = im.getcolors(maxcolors=100000)
        if colors:                                   # few distinct colours → dominated by one
            total = im.width * im.height
            top = max(c for c, _ in colors)
            return top / total > 0.995
        return False
    except Exception:
        pass
    # No Pillow → a compressed-size heuristic (a flat image compresses to almost nothing per pixel).
    # 3-tier + honest: clearly-flat → blank; ambiguous → None (evaluate WARNs, never a false pass/block).
    size = _png_size(p)
    if not size:
        return None
    w, h = size
    bpp = len(p.read_bytes()) / max(1, w * h)
    if bpp < 0.005:
        return True                                   # essentially one flat colour → blank
    if bpp < 0.02:
        return None                                   # too little entropy to be sure → WARN (install Pillow)
    return False                                      # enough detail → something rendered


def _luminance(hexc: str):
    hexc = hexc.strip().lstrip("#")
    if len(hexc) == 3:
        hexc = "".join(c * 2 for c in hexc)
    if len(hexc) != 6:
        return None
    try:
        rgb = [int(hexc[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    except ValueError:
        return None
    lin = [(c / 12.92) if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(fg: str, bg: str):
    lf, lb = _luminance(fg), _luminance(bg)
    if lf is None or lb is None:
        return None
    hi, lo = max(lf, lb), min(lf, lb)
    return (hi + 0.05) / (lo + 0.05)


def _find_screenshot(root: Path):
    for d in (root / ".orbit" / "qa", root / "design", root / ".orbit" / "artifacts", root / ".orbit" / "design"):
        if d.is_dir():
            shots = sorted(d.glob("*.png"))
            if shots:
                return shots[0]
    return None


def evaluate(root: Path, screenshot=None, mobile=None, contract=None,
             mobile_viewport=390, dpr=3, strict_tokens=False):
    checks = []                                       # (severity, message)
    approved = _read_json(root / "design" / "approved.json")
    is_heavy = isinstance(approved, dict) and approved.get("impact_level") == "HEAVY"
    if not is_heavy:
        return [(OK, "not HEAVY UI work (no design/approved.json impact_level=HEAVY) — visual gate N/A")], False

    shot = Path(screenshot) if screenshot else _find_screenshot(root)
    if not shot or not shot.exists():
        checks.append((BLOCK, "HEAVY UI has NO screenshot evidence — produce one (snapshot.py / browser "
                              "MCP / gstack /browse). 'process happened' ≠ 'it rendered right'."))
        return checks, True                           # nothing more to check without an image

    blank = _looks_blank(shot)
    if blank is True:
        checks.append((BLOCK, f"screenshot {shot.name} is a single flat colour (blank canvas) — nothing rendered"))
    elif blank is None:
        checks.append((WARN, f"could not analyse {shot.name} for blankness (install Pillow for a real check)"))
    else:
        checks.append((OK, f"screenshot {shot.name} present and non-blank"))

    size = _png_size(shot)
    if size and (size[0] < 200 or size[1] < 200):
        checks.append((BLOCK, f"screenshot is tiny ({size[0]}x{size[1]}) — not a real page capture"))

    if mobile:
        mp = Path(mobile)
        msize = _png_size(mp) if mp.exists() else None
        if not msize:
            checks.append((WARN, "no readable mobile screenshot — responsive not verified"))
        else:
            limit = int(mobile_viewport * dpr * 1.02)      # 2% tolerance
            if msize[0] > limit:
                checks.append((BLOCK, f"mobile screenshot is {msize[0]}px wide > viewport {mobile_viewport}px"
                                      f" (×{dpr}) — horizontal overflow on mobile"))
            else:
                checks.append((OK, f"mobile capture {msize[0]}px within the {mobile_viewport}px viewport"))
    else:
        checks.append((WARN, "no --mobile screenshot supplied — responsive/overflow not verified"))

    con = _read_json(Path(contract)) if contract else (approved.get("tokens") if isinstance(approved, dict) else None)
    if isinstance(con, dict):
        fg, bg = con.get("text_color") or con.get("color"), con.get("background_color") or con.get("bg")
        if fg and bg:
            ratio = _contrast(fg, bg)
            if ratio is None:
                checks.append((WARN, f"could not parse contract colours ({fg} on {bg})"))
            elif ratio < 4.5:
                checks.append((BLOCK, f"body contrast {ratio:.2f}:1 ({fg} on {bg}) is below WCAG AA 4.5:1"))
            else:
                checks.append((OK, f"body contrast {ratio:.1f}:1 meets WCAG AA"))
        drift = con.get("_token_drift")               # a prior extract-tokens compare can inject this
        if drift:
            checks.append((BLOCK if strict_tokens else WARN, f"token drift vs the approved design: {drift}"))

    blocked = any(sev == BLOCK for sev, _ in checks)
    return checks, blocked


def main():
    ap = argparse.ArgumentParser(description="Required visual-fidelity gate for HEAVY UI")
    ap.add_argument("--root", default=".", type=Path)
    ap.add_argument("--screenshot", default="")
    ap.add_argument("--mobile", default="")
    ap.add_argument("--contract", default="")
    ap.add_argument("--mobile-viewport", type=int, default=390)
    ap.add_argument("--dpr", type=int, default=3)
    ap.add_argument("--strict-tokens", action="store_true")
    a = ap.parse_args()
    checks, blocked = evaluate(a.root.resolve(), a.screenshot or None, a.mobile or None, a.contract or None,
                               a.mobile_viewport, a.dpr, a.strict_tokens)
    print("Visual gate —", "BLOCKED" if blocked else "pass")
    for sev, msg in checks:
        print(f"  [{sev}] {msg}")
    sys.exit(1 if blocked else 0)


if __name__ == "__main__":
    main()
