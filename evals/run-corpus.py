#!/usr/bin/env python3
"""
run-corpus.py — Orbit's DETERMINISTIC eval corpora (no model, no network; machine-checkable).

Two suites, each a JSONL corpus of (input → expected decision), so a regression is a hard failure a CI
can catch (unlike the task-quality A/B in run-eval.sh, which needs a live model + a judge):

  • guard  — dangerous / safe shell commands → expected deny | ask | allow. Codifies the guard's
             red-team corpus (obfuscation: `cd x && …`, `sh -c "…"`, `$( … )`, quoted vars, heredocs).
  • router — user prompts → expected lane task | question | ambiguous | skip.

Usage:  run-corpus.py [--suite guard|router|all] [--json]
Exit:   0 = every case matched · 1 = at least one regression (printed) · 2 = corpus/loader error.
"""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _mod(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


def _corpus(name):
    rows = []
    for ln in (ROOT / "evals" / "corpus" / f"{name}.jsonl").read_text().splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("//"):
            rows.append(json.loads(ln))
    return rows


def run_guard():
    g = _mod("guard", "assets/checks/guard.py")
    fails = []
    rows = _corpus("guard")
    for r in rows:
        v = g.evaluate(r["cmd"])
        got = v[0] if v else "allow"
        if got != r["expect"]:
            fails.append({"input": r["cmd"], "expect": r["expect"], "got": got, "note": r.get("note", "")})
    return rows, fails


def run_router():
    rt = _mod("route", "assets/checks/route.py")
    fails = []
    rows = _corpus("router")
    for r in rows:
        got = rt.classify(r["prompt"])
        if got != r["expect"]:
            fails.append({"input": r["prompt"], "expect": r["expect"], "got": got, "note": r.get("note", "")})
    return rows, fails


SUITES = {"guard": run_guard, "router": run_router}


def main():
    ap = argparse.ArgumentParser(description="Deterministic eval corpora (guard + router)")
    ap.add_argument("--suite", default="all", choices=["all", "guard", "router"])
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    names = list(SUITES) if a.suite == "all" else [a.suite]
    results, total_fail = {}, 0
    for n in names:
        rows, fails = SUITES[n]()
        results[n] = {"total": len(rows), "passed": len(rows) - len(fails), "failures": fails}
        total_fail += len(fails)

    if a.json:
        print(json.dumps(results, indent=2))
    else:
        for n in names:
            r = results[n]
            rate = 100.0 * r["passed"] / r["total"] if r["total"] else 100.0
            print(f"{n:8} {r['passed']}/{r['total']}  ({rate:.1f}%)")
            for f in r["failures"]:
                print(f"   ✗ expect {f['expect']} got {f['got']}: {f['input'][:70]!r}  {f['note']}")
        print("✅ corpora clean" if total_fail == 0 else f"❌ {total_fail} regression(s)")
    sys.exit(1 if total_fail else 0)


if __name__ == "__main__":
    main()
