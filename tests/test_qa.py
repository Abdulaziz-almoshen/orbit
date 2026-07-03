#!/usr/bin/env python3
"""
Tests the QA visual helpers (Phase 7):
 - snapshot.py `diff` is pure-python and correct: identical→PASS(0), over-threshold→FAIL(1),
   threshold raises the bar, dimension mismatch→exit 1, and it never needs a browser.
 - extract-tokens.py's comparison helpers pull the right declared values from a DESIGN.md and
   match them case/space-insensitively against rendered values.
Screenshot/console/extraction (Playwright) aren't exercised here — they degrade to exit 2, which
is a manual/CI-with-browser check per the plan's acceptance criteria.

Run: python3 tests/test_qa.py   (exit 0 = pass)
"""
import importlib.util
import os
import subprocess
import sys
import tempfile

QA = os.path.join(os.path.dirname(__file__), "..", "assets", "qa")


def _ppm(path, pixels, w, h):
    with open(path, "wb") as f:
        f.write(f"P6\n{w} {h}\n255\n".encode())
        f.write(bytes(pixels))


def _diff(a, b, *extra):
    return subprocess.run([sys.executable, os.path.join(QA, "snapshot.py"), "diff", a, b, *extra],
                          capture_output=True, text=True)


def _load_extract():
    spec = importlib.util.spec_from_file_location("extract_tokens", os.path.join(QA, "extract-tokens.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    fails = []
    with tempfile.TemporaryDirectory() as d:
        p = lambda n: os.path.join(d, n)
        black = [0, 0, 0] * 16
        one_white = list(black); one_white[0:3] = [255, 255, 255]
        _ppm(p("a.ppm"), black, 4, 4)
        _ppm(p("same.ppm"), black, 4, 4)
        _ppm(p("b.ppm"), one_white, 4, 4)   # 1/16 = 6.25% differ
        _ppm(p("small.ppm"), [0, 0, 0] * 9, 3, 3)

        r = _diff(p("a.ppm"), p("same.ppm"))
        if r.returncode != 0 or "PASS" not in r.stdout:
            fails.append(f"identical images should PASS exit 0, got {r.returncode}: {r.stdout.strip()}")

        r = _diff(p("a.ppm"), p("b.ppm"))
        if r.returncode != 1 or "FAIL" not in r.stdout:
            fails.append(f"6.25% diff vs 1% threshold should FAIL exit 1, got {r.returncode}: {r.stdout.strip()}")

        r = _diff(p("a.ppm"), p("b.ppm"), "--threshold", "0.1")
        if r.returncode != 0 or "PASS" not in r.stdout:
            fails.append(f"6.25% diff vs 10% threshold should PASS exit 0, got {r.returncode}: {r.stdout.strip()}")

        r = _diff(p("a.ppm"), p("small.ppm"))
        if r.returncode != 1 or "MISMATCH" not in r.stdout:
            fails.append(f"dimension mismatch should exit 1, got {r.returncode}: {r.stdout.strip()}")

        # --out writes a diff artifact without a browser
        r = _diff(p("a.ppm"), p("b.ppm"), "--out", p("diff.ppm"))
        if not os.path.exists(p("diff.ppm")):
            fails.append("--out did not write a diff image")

    # extract-tokens comparison helpers
    ex = _load_extract()
    design = "--color-primary: #2B6CB0;\nbody { font-size: 16px; }\nradius 8px"
    wanted = ex._wanted_values(design)
    if "#2b6cb0" not in wanted:
        fails.append(f"_wanted_values missed the hex token: {wanted}")
    if "16px" not in wanted:
        fails.append(f"_wanted_values missed the px token: {wanted}")
    rendered = {"color": ["rgb(43, 108, 176)"], "font-size": ["16px", "14px"]}
    blob = ex._rendered_blob(rendered)
    if ex._norm("16px") not in blob:
        fails.append("rendered blob should contain a declared size that IS present")

    if fails:
        print("FAIL: qa")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("PASS: qa (pure-python diff correctness + token-compare helpers; no browser needed)")


if __name__ == "__main__":
    main()
