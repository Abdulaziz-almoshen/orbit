#!/usr/bin/env python3
"""The CPO acceptance gate (after QA): the run cannot finish until a commit-bound verdict envelope
says ACCEPT. Tests the evaluator's every path, the scaffold provisioning (cpo role + playbook +
user-model seed + verdicts dir), and that re-scaffold never clobbers a grown user-model.

Run: python3 tests/test_cpo_gate.py   (exit 0 = pass)
"""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
fails = []


def ck(cond, msg):
    if not cond:
        fails.append(msg)


def _loop():
    loader = importlib.machinery.SourceFileLoader("orbit_loop", str(ROOT / "assets" / "loop.py"))
    spec = importlib.util.spec_from_loader("orbit_loop", loader)
    m = importlib.util.module_from_spec(spec)
    sys.modules["orbit_loop"] = m      # dataclasses on py3.14 resolve annotations via sys.modules
    loader.exec_module(m)
    return m


def test_evaluator_paths():
    m = _loop()
    with tempfile.TemporaryDirectory() as d:
        vdir = Path(d) / ".orbit" / "cpo"
        cfg = {"cpo_acceptance": {"enabled": True}, "paths": {"cpo_verdicts": str(vdir)}}
        out = {"commit": "abc12345", "summary": "x"}

        r = m.evaluate_cpo_acceptance(out, {"cpo_acceptance": {"enabled": False}})
        ck(r["passed"] is True and r["status"] == "disabled", f"disabled must pass through: {r}")

        r = m.evaluate_cpo_acceptance({"summary": "no commit"}, cfg)
        ck(r["passed"] is False and r["status"] == "missing_input",
           f"enabled CPO without a commit must block: {r}")

        r = m.evaluate_cpo_acceptance(out, cfg)
        ck(r["passed"] is False and r["status"] == "pending" and "dispatch the cpo" in r["reason"],
           f"no envelope must block with an actionable pending reason: {r}")

        vdir.mkdir(parents=True)
        (vdir / "round-1.json").write_text(json.dumps(
            {"commit": "abc12345", "verdict": "ITERATE",
             "change_orders": [{"priority": "must", "order": "capture the user's goal"}]}))
        r = m.evaluate_cpo_acceptance(out, cfg)
        ck(r["passed"] is False and r["verdict"] == "ITERATE" and "capture the user's goal" in r["reason"],
           f"ITERATE must block and surface the top change order: {r}")

        time.sleep(0.02)
        (vdir / "round-2.json").write_text(json.dumps({"commit": "ffff9999", "verdict": "ACCEPT"}))
        r = m.evaluate_cpo_acceptance(out, cfg)
        ck(r["passed"] is False and r["status"] == "stale",
           f"an ACCEPT for a DIFFERENT commit must never pass this cycle: {r}")

        time.sleep(0.02)
        (vdir / "round-3.json").write_text(json.dumps({"commit": "abc12345", "verdict": "REDEVELOP",
                                                       "change_orders": []}))
        r = m.evaluate_cpo_acceptance(out, cfg)
        ck(r["passed"] is False and r["verdict"] == "REDEVELOP", f"REDEVELOP must block: {r}")

        time.sleep(0.02)
        (vdir / "round-4.json").write_text(json.dumps({"commit": "abc12345", "verdict": "ACCEPT"}))
        r = m.evaluate_cpo_acceptance(out, cfg)
        ck(r["passed"] is True and r["status"] == "accepted",
           f"a commit-bound ACCEPT must open the gate: {r}")

        (vdir / "round-5.json").write_text("{broken json")
        r = m.evaluate_cpo_acceptance(out, cfg)
        ck(r["passed"] is False and r["status"] == "error", f"a corrupt envelope must block, not crash: {r}")


def test_gate_is_wired_after_qa():
    src = (ROOT / "assets" / "loop.py").read_text()
    qa_at = src.find('steps.run(f"c{cycle}:independent-qa"')
    cpo_at = src.find('steps.run(f"c{cycle}:cpo"')
    ck(qa_at != -1 and cpo_at != -1 and cpo_at > qa_at,
       "the cpo gate must be checkpointed in the decide path strictly AFTER independent QA")
    ck('"cpo"' in src.split("def _g(")[1].split("return")[1],
       "the gate string must include cpo so STATE.md records the verdict gate")
    cfg = json.loads((ROOT / "assets" / "loop.config.json").read_text())
    ck(cfg.get("cpo_acceptance", {}).get("enabled") is True,
       "the shipped config template must install the CPO gate enabled (it is in-model; no export)")
    ck(cfg.get("paths", {}).get("cpo_verdicts") == ".orbit/cpo", "paths.cpo_verdicts must ship")


def test_scaffold_provisions_cpo():
    with tempfile.TemporaryDirectory() as d:
        env = {**os.environ, "ORBIT_HOME": str(Path(d) / "home")}
        target = Path(d) / "repo"
        target.mkdir()
        subprocess.run([sys.executable, str(ROOT / "scripts/scaffold.py"), "--target", str(target)],
                       env=env, text=True, capture_output=True, check=True)
        ck((target / ".claude/agents/cpo.md").is_file(), "scaffold must install the cpo subagent")
        ck((target / ".orbit/roles/cpo.md").is_file(), "scaffold must mirror cpo into portable roles")
        ck((target / ".orbit/skills/product-acceptance.md").is_file(),
           "scaffold must provision the product-acceptance playbook")
        ck((target / ".orbit/cpo").is_dir(), "scaffold must create the verdicts dir")
        seed = target / ".orbit/skills/user-model.md"
        ck(seed.is_file() and "Owned by the CPO" in seed.read_text(),
           "scaffold must seed the user-model skill")
        # a grown user-model must survive re-scaffold untouched
        seed.write_text(seed.read_text() + "\n1. Prefers honest cards over alarms (R1,R2,R3)\n")
        before = seed.read_text()
        subprocess.run([sys.executable, str(ROOT / "scripts/scaffold.py"), "--target", str(target)],
                       env=env, text=True, capture_output=True, check=True)
        ck(seed.read_text() == before, "re-scaffold must NEVER clobber learned user preferences")


def main():
    for fn in (test_evaluator_paths, test_gate_is_wired_after_qa, test_scaffold_provisions_cpo):
        try:
            fn()
        except Exception as e:
            fails.append(f"[{fn.__name__}] raised {type(e).__name__}: {e}")
    if fails:
        print(f"FAIL: cpo-gate ({len(fails)})")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("PASS: cpo-gate (verdict paths · commit binding · wired after QA · scaffolded role+playbook+user-model)")


if __name__ == "__main__":
    main()
