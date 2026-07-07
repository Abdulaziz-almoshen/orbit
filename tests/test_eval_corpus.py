#!/usr/bin/env python3
"""
Deterministic eval corpora as a CI gate (v0.36.0). Runs evals/run-corpus.py (guard red-team + router)
and fails if ANY case regresses — so the published pass-rates can't silently rot. This is the automated,
model-free half of the eval story (the task-quality A/B in run-eval.sh still needs a live model + judge).

Run: python3 tests/test_eval_corpus.py   (exit 0 = 100% on every corpus)
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
fails = []


def main():
    spec = importlib.util.spec_from_file_location("run_corpus", ROOT / "evals" / "run-corpus.py")
    rc = importlib.util.module_from_spec(spec)
    sys.modules["run_corpus"] = rc
    spec.loader.exec_module(rc)

    for name, fn in rc.SUITES.items():
        rows, failures = fn()
        if not rows:
            fails.append(f"[{name}] corpus is empty — expected cases")
        for f in failures:
            fails.append(f"[{name}] expect {f['expect']} got {f['got']}: {f['input'][:60]!r}")

    if fails:
        print(f"FAIL: eval-corpus {len(fails)} regression(s):")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    total = sum(len(rc.SUITES[n]()[0]) for n in rc.SUITES)
    print(f"PASS: eval-corpus ({total} deterministic cases across {len(rc.SUITES)} corpora, 100%)")


if __name__ == "__main__":
    main()
