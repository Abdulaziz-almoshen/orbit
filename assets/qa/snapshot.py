#!/usr/bin/env python3
"""
snapshot.py — QA screenshot + pixel-diff + console helper for the visual-fidelity gate.

**Helpers, not a bundled browser.** Screenshot/console capture need Playwright (optional
dependency); the pixel `diff` is pure-python (Pillow if importable, else a PPM/P6 fallback).
Nothing here bundles a browser — if Playwright isn't installed we say so and exit 2, so the
QA role can fall back to an installed browser MCP, gstack `/browse`, or a manual check.

Subcommands:
  screenshot <url> --out shot.png [--viewport 1280x800] [--full-page]
  diff <a.png> <b.png> [--threshold 0.01] [--out diff.png]
  console <url>

Exit codes:
  0  ok / diff under threshold
  1  diff over threshold (or a runtime capture error)
  2  a required dependency is missing — prints the exact install line, never a traceback
"""
import argparse
import sys


def _need_playwright():
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        return sync_playwright
    except Exception:
        sys.stderr.write(
            "This subcommand needs Playwright (not bundled).\n"
            "  pip install playwright && playwright install chromium\n"
            "Or use your browser tool instead: an installed browser MCP, gstack `/browse`,\n"
            "or a manual screenshot. (diff works without Playwright.)\n")
        sys.exit(2)


def cmd_screenshot(args):
    sync_playwright = _need_playwright()
    w, h = _parse_viewport(args.viewport)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": w, "height": h})
            page.goto(args.url, wait_until="networkidle")
            page.screenshot(path=args.out, full_page=args.full_page)
            browser.close()
    except Exception as e:
        sys.stderr.write(f"screenshot failed: {e}\n")
        sys.exit(1)
    print(f"wrote {args.out} ({w}x{h}{' full-page' if args.full_page else ''}) from {args.url}")


def cmd_console(args):
    sync_playwright = _need_playwright()
    msgs = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.on("console", lambda m: msgs.append((m.type, m.text)))
            page.on("pageerror", lambda e: msgs.append(("error", str(e))))
            page.goto(args.url, wait_until="networkidle")
            browser.close()
    except Exception as e:
        sys.stderr.write(f"console capture failed: {e}\n")
        sys.exit(1)
    errs = sum(1 for t, _ in msgs if t == "error")
    for t, text in msgs:
        print(f"[{t}] {text}")
    print(f"— {len(msgs)} message(s), {errs} error(s)")
    sys.exit(1 if errs else 0)


# ---- pixel diff (no browser needed) -------------------------------------------------

def _load_image(path):
    """Return (width, height, flat RGB bytes). Pillow if available, else a PPM/P6 reader."""
    try:
        from PIL import Image
        im = Image.open(path).convert("RGB")
        return im.width, im.height, im.tobytes()
    except ImportError:
        return _load_ppm(path)


def _load_ppm(path):
    with open(path, "rb") as f:
        data = f.read()
    if not data.startswith(b"P6"):
        sys.stderr.write(
            f"can't decode {path} without Pillow (only raw PPM/P6 is supported by the "
            "stdlib fallback).\n  pip install pillow   # to diff PNG/JPEG screenshots\n")
        sys.exit(2)
    # parse the P6 header: magic, width, height, maxval — whitespace-separated, '#' comments
    idx, fields = 2, []
    while len(fields) < 3:
        while idx < len(data) and data[idx:idx + 1].isspace():
            idx += 1
        if data[idx:idx + 1] == b"#":
            while idx < len(data) and data[idx:idx + 1] != b"\n":
                idx += 1
            continue
        start = idx
        while idx < len(data) and not data[idx:idx + 1].isspace():
            idx += 1
        fields.append(int(data[start:idx]))
    w, h, _maxval = fields
    idx += 1  # single whitespace after maxval
    return w, h, data[idx:idx + w * h * 3]


def cmd_diff(args):
    wa, ha, pa = _load_image(args.a)
    wb, hb, pb = _load_image(args.b)
    if (wa, ha) != (wb, hb):
        print(f"DIMENSION MISMATCH: {args.a} is {wa}x{ha}, {args.b} is {wb}x{hb} — treating as 100% diff")
        sys.exit(1)
    total = wa * ha
    differing = 0
    diff_mask = bytearray(len(pa)) if args.out else None
    for i in range(0, len(pa), 3):
        d = (abs(pa[i] - pb[i]) + abs(pa[i + 1] - pb[i + 1]) + abs(pa[i + 2] - pb[i + 2]))
        if d > args.tolerance:
            differing += 1
            if diff_mask is not None:
                diff_mask[i] = 255  # highlight changed pixels red
    frac = differing / total if total else 0.0
    if args.out:
        _write_diff(args.out, wa, ha, diff_mask)
    verdict = "PASS" if frac <= args.threshold else "FAIL"
    print(f"{verdict}: {differing}/{total} pixels differ = {frac:.4%} "
          f"(threshold {args.threshold:.4%}){'  → ' + args.out if args.out else ''}")
    sys.exit(0 if frac <= args.threshold else 1)


def _write_diff(out, w, h, mask):
    try:
        from PIL import Image
        Image.frombytes("RGB", (w, h), bytes(mask)).save(out)
    except ImportError:
        with open(out, "wb") as f:                     # PPM fallback so --out still works
            f.write(f"P6\n{w} {h}\n255\n".encode())
            f.write(bytes(mask))


def _parse_viewport(s):
    try:
        w, h = s.lower().split("x")
        return int(w), int(h)
    except Exception:
        sys.stderr.write(f"bad --viewport {s!r}; expected WxH like 1280x800\n")
        sys.exit(2)


def main():
    ap = argparse.ArgumentParser(description="QA screenshot / pixel-diff / console helper (helpers, not a bundled browser)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("screenshot", help="capture a screenshot (needs Playwright)")
    s.add_argument("url")
    s.add_argument("--out", required=True)
    s.add_argument("--viewport", default="1280x800")
    s.add_argument("--full-page", action="store_true")
    s.set_defaults(func=cmd_screenshot)

    d = sub.add_parser("diff", help="pixel-diff two images (no browser needed)")
    d.add_argument("a")
    d.add_argument("b")
    d.add_argument("--threshold", type=float, default=0.01, help="max differing fraction to PASS")
    d.add_argument("--tolerance", type=int, default=0, help="per-pixel channel-sum delta to ignore")
    d.add_argument("--out", help="write a diff image (changed pixels in red)")
    d.set_defaults(func=cmd_diff)

    c = sub.add_parser("console", help="capture console + page errors (needs Playwright)")
    c.add_argument("url")
    c.set_defaults(func=cmd_console)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
