#!/usr/bin/env python3
"""
The required visual QA gate (v0.35.0). HEAVY UI can't pass without visual evidence: a missing screenshot
blocks, a blank canvas blocks, mobile horizontal overflow blocks, and sub-AA contrast blocks — while
non-HEAVY work is N/A. Crafts real PNGs (no Pillow needed) to exercise blank/overflow detection.

Run: python3 tests/test_visual_gate.py   (exit 0 = pass)
"""
import importlib.util
import json
import struct
import sys
import tempfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GATE = ROOT / "assets" / "qa" / "visual-gate.py"
fails = []


def _load():
    spec = importlib.util.spec_from_file_location("visual_gate", GATE)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


G = _load()


def ck(cond, msg):
    if not cond:
        fails.append(msg)


def _png(path: Path, w: int, h: int, noise: bool):
    raw = bytearray()
    for y in range(h):
        raw.append(0)                                # filter type 0 per scanline
        for x in range(w):
            if noise:
                v = (x * 31 + y * 17) % 256
                raw += bytes([v, (v * 3) % 256, (v * 7) % 256])
            else:
                raw += bytes([200, 200, 200])        # flat grey → "blank"

    def chunk(typ, data):
        return struct.pack(">I", len(data)) + typ + data + struct.pack(">I", zlib.crc32(typ + data) & 0xffffffff)

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)   # 8-bit RGB
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
                     + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))


def _heavy(root: Path, tokens=None):
    (root / "design").mkdir(parents=True, exist_ok=True)
    rec = {"impact_level": "HEAVY"}
    if tokens:
        rec["tokens"] = tokens
    (root / "design" / "approved.json").write_text(json.dumps(rec))


def _blocked(root, **kw):
    _checks, blocked = G.evaluate(root, **kw)
    return blocked


def test_missing_screenshot_blocks():
    with tempfile.TemporaryDirectory() as d:
        r = Path(d)
        _heavy(r)
        ck(_blocked(r) is True, "HEAVY UI with no screenshot must BLOCK")


def test_blank_screenshot_blocks():
    with tempfile.TemporaryDirectory() as d:
        r = Path(d)
        _heavy(r)
        shot = r / "shot.png"
        _png(shot, 1280, 800, noise=False)           # flat grey → blank
        ck(_blocked(r, screenshot=str(shot)) is True, "a blank (flat-colour) screenshot must BLOCK")


def test_good_screenshot_passes():
    with tempfile.TemporaryDirectory() as d:
        r = Path(d)
        _heavy(r)
        shot = r / "shot.png"
        _png(shot, 1280, 800, noise=True)            # real content
        ck(_blocked(r, screenshot=str(shot)) is False, "a non-blank, well-sized screenshot must pass")


def test_mobile_overflow_blocks():
    with tempfile.TemporaryDirectory() as d:
        r = Path(d)
        _heavy(r)
        shot = r / "shot.png"
        mob = r / "mobile.png"
        _png(shot, 1280, 800, noise=True)
        _png(mob, 900, 1600, noise=True)             # 900px wide >> 390 viewport → horizontal overflow
        ck(_blocked(r, screenshot=str(shot), mobile=str(mob), mobile_viewport=390, dpr=2) is True,
           "a mobile screenshot wider than the viewport must BLOCK (overflow)")
        # a correctly-sized mobile capture passes
        _png(mob, 390, 1600, noise=True)
        ck(_blocked(r, screenshot=str(shot), mobile=str(mob), mobile_viewport=390, dpr=2) is False,
           "an in-viewport mobile capture must not block on overflow")


def test_low_contrast_blocks():
    with tempfile.TemporaryDirectory() as d:
        r = Path(d)
        _heavy(r, tokens={"text_color": "#777777", "background_color": "#888888"})   # ~1.2:1
        shot = r / "shot.png"
        _png(shot, 1280, 800, noise=True)
        ck(_blocked(r, screenshot=str(shot)) is True, "sub-AA body contrast must BLOCK")
        # good contrast passes
        _heavy(r, tokens={"text_color": "#111111", "background_color": "#ffffff"})
        ck(_blocked(r, screenshot=str(shot)) is False, "AA-passing contrast must not block")


def test_not_heavy_is_na():
    with tempfile.TemporaryDirectory() as d:
        r = Path(d)                                  # no design/approved.json
        ck(_blocked(r) is False, "non-HEAVY work is N/A — the gate must not block")


def main():
    for fn in (test_missing_screenshot_blocks, test_blank_screenshot_blocks, test_good_screenshot_passes,
               test_mobile_overflow_blocks, test_low_contrast_blocks, test_not_heavy_is_na):
        try:
            fn()
        except Exception as e:
            fails.append(f"[{fn.__name__}] raised {type(e).__name__}: {e}")
    if fails:
        print(f"FAIL: visual-gate {len(fails)} case(s):")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("PASS: visual-gate (missing→block · blank→block · good→pass · mobile overflow→block · "
          "sub-AA contrast→block · non-HEAVY→N/A)")


if __name__ == "__main__":
    main()
