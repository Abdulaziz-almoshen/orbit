#!/usr/bin/env python3
"""
extract-tokens.py — pull the design tokens a page ACTUALLY renders, and (optionally) check
them against the approved design.

**A helper, not a bundled browser.** Reading computed styles needs Playwright (optional). Its
job: catch the classic "the CSS says #2b6cb0 but the button renders #3b82f6" drift that a
screenshot diff can miss. Without Playwright it prints the install line and exits 2 (never a
traceback) — the QA role then falls back to an installed browser MCP, gstack `/browse`, or manual.

Usage:
  extract-tokens.py <url> [--selector CSS] [--out tokens.json]
  extract-tokens.py <url> --compare DESIGN.md      # token-by-token PASS/FAIL vs the approved design

Exit codes: 0 ok / all compared tokens PASS; 1 a compared token FAILED; 2 missing dependency.
"""
import argparse
import json
import re
import sys

# The properties we harvest distinct rendered values for — the ones a design system pins down.
_PROPS = ["font-family", "font-size", "font-weight", "line-height", "color",
          "background-color", "border-color", "border-radius", "margin", "padding",
          "letter-spacing", "box-shadow"]

_JS = """(props) => {
  const seen = {}; props.forEach(p => seen[p] = new Set());
  const els = document.querySelectorAll('*');
  for (const el of els) {
    const cs = getComputedStyle(el);
    for (const p of props) {
      const v = cs.getPropertyValue(p);
      if (v && v !== 'none' && v !== 'normal' && v !== 'auto') seen[p].add(v.trim());
    }
  }
  const out = {}; for (const p of props) out[p] = Array.from(seen[p]).sort();
  return out;
}"""


def _extract(url, selector):
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        sys.stderr.write(
            "extract-tokens needs Playwright (not bundled).\n"
            "  pip install playwright && playwright install chromium\n"
            "Or read computed styles with your browser tool (an installed browser MCP, gstack\n"
            "`/browse`) instead.\n")
        sys.exit(2)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(url, wait_until="networkidle")
            if selector:
                page.wait_for_selector(selector, timeout=5000)
            tokens = page.evaluate(_JS, _PROPS)
            browser.close()
            return tokens
    except Exception as e:
        sys.stderr.write(f"token extraction failed: {e}\n")
        sys.exit(1)


# ---- comparison against the approved design -----------------------------------------

_HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
_PX = re.compile(r"\b\d+(?:\.\d+)?(?:px|rem|em)\b")
_VAR = re.compile(r"--[\w-]+\s*:\s*([^;]+);")


def _wanted_values(design_text):
    """Best-effort: the concrete token values DESIGN.md declares — CSS var values, hex colors,
    and sizes. We check presence, not exhaustiveness (honest about being a helper)."""
    wanted = set()
    for m in _VAR.findall(design_text):
        wanted.add(m.strip())
    wanted |= {h.lower() for h in _HEX.findall(design_text)}
    wanted |= set(_PX.findall(design_text))
    # drop trivial/noise values
    return {w for w in wanted if w and w.lower() not in ("0", "0px", "inherit", "initial")}


def _norm(s):
    return re.sub(r"\s+", "", s).lower()


def _rendered_blob(tokens):
    return _norm(" ".join(v for vals in tokens.values() for v in vals))


def cmd_compare(url, selector, design_path):
    with open(design_path, encoding="utf-8") as f:
        design_text = f.read()
    wanted = _wanted_values(design_text)
    if not wanted:
        print(f"no concrete token values found in {design_path} (looked for CSS vars, hex colors, px/rem/em).")
        print("Nothing to compare — treating as vacuously OK.")
        return 0
    tokens = _extract(url, selector)
    blob = _rendered_blob(tokens)
    fails = 0
    for w in sorted(wanted):
        present = _norm(w) in blob
        print(f"  {'PASS' if present else 'FAIL'}  {w}")
        if not present:
            fails += 1
    print(f"— {len(wanted) - fails}/{len(wanted)} declared token value(s) found rendered at {url}")
    if fails:
        print("  (a FAIL means the value DESIGN.md declares wasn't found in any element's computed "
              "style — hex/size mismatch, or the token isn't applied.)")
    return 1 if fails else 0


def main():
    ap = argparse.ArgumentParser(description="Extract rendered design tokens; optionally check vs the approved design")
    ap.add_argument("url")
    ap.add_argument("--selector", help="wait for this selector before reading (ensures the page is ready)")
    ap.add_argument("--out", help="write the tokens JSON here (default: stdout)")
    ap.add_argument("--compare", metavar="DESIGN.md", help="token-by-token PASS/FAIL vs this design file")
    args = ap.parse_args()

    if args.compare:
        sys.exit(cmd_compare(args.url, args.selector, args.compare))

    tokens = _extract(args.url, args.selector)
    out = json.dumps(tokens, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(out + "\n")
        print(f"wrote {args.out} ({sum(len(v) for v in tokens.values())} distinct values across {len(tokens)} properties)")
    else:
        print(out)


if __name__ == "__main__":
    main()
