#!/usr/bin/env python3
"""The CPO acceptance gate (after QA): the run cannot finish until a commit-bound verdict envelope
says ACCEPT. Tests the evaluator's every path, the scaffold provisioning (cpo role + playbook +
user-model seed + verdicts dir), and that re-scaffold never clobbers a grown user-model.

Run: python3 tests/test_cpo_gate.py   (exit 0 = pass)
"""
import importlib.machinery
import importlib.util
import hashlib
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
        cfg = {"cpo_acceptance": {"enabled": True, "require_delivery_evidence": False},
               "paths": {"cpo_verdicts": str(vdir)}}
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
        ck(r["passed"] is False and r["status"] == "ungrounded",
           f"an ACCEPT with no skill basis and no seeded updates must be rejected: {r}")

        time.sleep(0.02)
        full_grill = [{"lens": l, "verdict": "clean", "evidence": f"checked {l}"}
                      for l in ("domain", "policy", "product", "design_ux", "system_design", "slop")]
        (vdir / "round-4b.json").write_text(json.dumps(
            {"commit": "abc12345", "verdict": "ACCEPT",
             "user_model_updates": ["first signal: prefers honest states"], "grill": full_grill}))
        r = m.evaluate_cpo_acceptance(out, cfg)
        ck(r["passed"] is True, f"fresh project: grilled ACCEPT seeding the first signals passes: {r}")

        def grill(overrides=None):
            lenses = {l: {"lens": l, "verdict": "clean", "evidence": f"checked {l}"}
                      for l in ("domain", "policy", "product", "design_ux", "system_design", "slop")}
            for l, v in (overrides or {}).items():
                if v is None:
                    lenses.pop(l)
                else:
                    lenses[l] = v
            return list(lenses.values())

        def accept(g):
            return {"commit": "abc12345", "verdict": "ACCEPT",
                    "basis": {"skills": ["user-model R1: honest states over alarms"],
                              "research": ["walked the flow"]},
                    "grill": g}

        time.sleep(0.02)
        (vdir / "round-4c.json").write_text(json.dumps(accept(grill({"slop": None}))))
        r = m.evaluate_cpo_acceptance(out, cfg)
        ck(r["passed"] is False and r["status"] == "ungrilled" and "slop" in r["reason"],
           f"an ACCEPT missing a grill lens must be rejected naming the lens: {r}")

        time.sleep(0.02)
        (vdir / "round-4d.json").write_text(json.dumps(accept(grill({"design_ux": {
            "lens": "design_ux", "verdict": "findings",
            "findings": [{"severity": "must", "finding": "dead submit button — no error state"}]}}))))
        r = m.evaluate_cpo_acceptance(out, cfg)
        ck(r["passed"] is False and r["status"] == "grill_failed" and "dead submit button" in r["reason"],
           f"an open must finding must block ACCEPT and name the finding: {r}")

        time.sleep(0.02)
        (vdir / "round-4e.json").write_text(json.dumps(accept(grill({"slop": {
            "lens": "slop", "verdict": "findings",
            "findings": [{"severity": "should", "finding": "one hedgy sentence in the empty state",
                          "waived_because": "user approved the copy verbatim in review"}]}}))))
        r = m.evaluate_cpo_acceptance(out, cfg)
        ck(r["passed"] is True and r["status"] == "accepted" and "lenses grilled clean" in r["reason"],
           f"full grill with only waived/resolved findings must open the gate: {r}")

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
    ck(cfg.get("cpo_acceptance", {}).get("require_delivery_evidence") is True,
       "CPO ACCEPT must require the exact pre-CPO delivery evidence")
    delivery_at = src.find('steps.run(f"c{cycle}:delivery-quality"')
    ck(delivery_at != -1 and qa_at != -1 and delivery_at < qa_at < cpo_at,
       "delivery-quality must run before independent QA and CPO")
    ck(cfg.get("paths", {}).get("cpo_verdicts") == ".orbit/cpo", "paths.cpo_verdicts must ship")


def test_cpo_binds_delivery_evidence():
    m = _loop()
    with tempfile.TemporaryDirectory() as d:
        root = Path(d); vdir = root / "cpo"; vdir.mkdir()
        evidence = root / "delivery-evidence.json"
        cfg = {"cpo_acceptance": {"enabled": True, "require_delivery_evidence": True},
               "paths": {"cpo_verdicts": str(vdir), "delivery_evidence": str(evidence)}}
        grill = [{"lens": l, "verdict": "clean", "evidence": f"checked {l}"}
                 for l in ("domain", "policy", "product", "design_ux", "system_design", "slop")]
        verdict = {"commit": "abc", "verdict": "ACCEPT", "basis": {"skills": ["user-model R1"]},
                   "grill": grill}
        (vdir / "round-1.json").write_text(json.dumps(verdict))
        result = m.evaluate_cpo_acceptance({"commit": "abc"}, cfg)
        ck(result.get("status") == "qa_evidence_missing", "CPO must reject ACCEPT with no QA evidence")
        evidence.write_text(json.dumps({"commit": "abc", "verdict": "PASS"}))
        verdict["qa_evidence"] = {"path": str(evidence), "commit": "abc",
                                  "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest()}
        time.sleep(0.02)
        (vdir / "round-2.json").write_text(json.dumps(verdict))
        result = m.evaluate_cpo_acceptance({"commit": "abc"}, cfg)
        ck(result.get("passed") is True, f"CPO must accept exact hashed PASS evidence: {result}")


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
        ck((target / ".orbit/checks/delivery-quality-gate.py").is_file(),
           "scaffold must install the deterministic pre-CPO delivery-quality gate")
        ck((target / ".orbit/qa/delivery-evidence.template.json").is_file(),
           "scaffold must install the delivery evidence template")
        seed = target / ".orbit/skills/user-model.md"
        ck(seed.is_file() and "Owned by the CPO" in seed.read_text(),
           "scaffold must seed the user-model skill")
        # a grown user-model must survive re-scaffold untouched
        seed.write_text(seed.read_text() + "\n1. Prefers honest cards over alarms (R1,R2,R3)\n")
        before = seed.read_text()
        subprocess.run([sys.executable, str(ROOT / "scripts/scaffold.py"), "--target", str(target)],
                       env=env, text=True, capture_output=True, check=True)
        ck(seed.read_text() == before, "re-scaffold must NEVER clobber learned user preferences")


def _run_stop_hook(orbit_root, cwd):
    hook = ROOT / "assets" / "checks" / "orbit-stop-check.py"
    proc = subprocess.run([sys.executable, str(hook)], text=True, capture_output=True,
                          input=json.dumps({"cwd": str(cwd)}),
                          env={**os.environ, "CLAUDE_PROJECT_DIR": str(cwd)})
    return json.loads(proc.stdout) if proc.stdout.strip() else None


def test_stop_vigilance():
    """The CPO stays on duty: substantial routed work with a visible board but NO accepting verdict
    blocks the stop once; ACCEPT or an explicit park releases it."""
    with tempfile.TemporaryDirectory() as d:
        cwd = Path(d)
        orbit = cwd / ".orbit"
        (orbit / "cpo").mkdir(parents=True)
        (orbit / "loop.config.json").write_text(json.dumps({"cpo_acceptance": {"enabled": True}}))
        (orbit / ".last-task-route").write_text("x")
        route_line = {"schema": 2, "phase": "route", "status": "start", "msg": "routing: task"}
        work = [{"schema": 2, "phase": "act", "status": "done", "msg": f"w{i}"} for i in range(4)]
        (orbit / "activity.jsonl").write_text("\n".join(json.dumps(x) for x in [route_line, *work]) + "\n")
        time.sleep(0.02)
        (orbit / "tasks.json").write_text("[]")             # board IS visible → old hook would allow

        out = _run_stop_hook(orbit, cwd)
        ck(out is not None and out.get("decision") == "block" and "CPO ON DUTY" in out.get("reason", ""),
           f"an open goal with no verdict must block the stop: {out}")
        out2 = _run_stop_hook(orbit, cwd)
        ck(out2 is None, f"vigilance must block at most ONCE per route: {out2}")

        (orbit / ".cpo-stop-warned").unlink()               # fresh route simulation: ACCEPT releases
        time.sleep(0.02)
        (orbit / "cpo" / "round-1.json").write_text(json.dumps({"commit": "abc", "verdict": "ACCEPT"}))
        ck(_run_stop_hook(orbit, cwd) is None, "an ACCEPT newer than the route must release the watch")

        (orbit / "cpo" / "round-1.json").unlink()
        (orbit / "cpo" / "parked").write_text("user parked: demo later")
        ck(_run_stop_hook(orbit, cwd) is None, "an explicit park must release the watch")


def main():
    for fn in (test_evaluator_paths, test_gate_is_wired_after_qa, test_cpo_binds_delivery_evidence,
               test_scaffold_provisions_cpo,
               test_stop_vigilance):
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
