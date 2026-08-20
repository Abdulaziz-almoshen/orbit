#!/usr/bin/env python3
"""End-to-end contract for the trusted zero-model-call resource governor."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "bin/orbit-resource-hook"


def invoke(project: Path, payload: dict):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(project))
    proc = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), text=True,
                          capture_output=True, env=env, check=True)
    return json.loads(proc.stdout) if proc.stdout.strip() else {}


def main():
    fails = []
    with tempfile.TemporaryDirectory() as td:
        project = Path(td); orbit = project / ".orbit"; orbit.mkdir()
        (orbit / "loop.config.json").write_text((ROOT / "assets/loop.config.json").read_text())
        (orbit / "checks").mkdir()
        shutil.copy2(ROOT / "assets/checks/repository_intelligence.py",
                     orbit / "checks/repository_intelligence.py")
        invoke(project, {"hook_event_name": "UserPromptSubmit", "session_id": "s1",
                         "prompt": "Fix the checkout", "cwd": str(project)})
        (orbit / "intelligence").mkdir()
        (orbit / "intelligence/latest.json").write_text(json.dumps({
            "policy": {"hops": 1}, "retrieval": {"files": [], "estimated_tokens": 0}}))
        ledger = json.loads((orbit / "budget.json").read_text())
        if ledger.get("total") != 25000 or ledger.get("goal") != "Fix the checkout":
            fails.append("session intake did not open the default governed T1 ledger")

        ledger["spent"]["planner"] = 1234
        (orbit / "budget.json").write_text(json.dumps(ledger))
        invoke(project, {"hook_event_name": "UserPromptSubmit", "session_id": "s1",
                         "prompt": "and test it", "cwd": str(project)})
        if json.loads((orbit / "budget.json").read_text())["spent"]["planner"] != 1234:
            fails.append("follow-up prompt reset the session allowance")

        # Orbit-generated packet drift is repaired within the same caps before dispatch; it never
        # becomes a user confirmation or a retry loop.
        (orbit / "intelligence/latest.json").write_text(json.dumps({
            "policy": {"hops": 1},
            "retrieval": {"files": [{"path": f"f{i}"} for i in range(13)],
                          "estimated_tokens": 2000}}))
        repaired = invoke(project, {"hook_event_name": "PreToolUse", "tool_name": "Agent",
                           "tool_use_id": "repair-edge", "cwd": str(project),
                           "tool_input": {"subagent_type": "reporter", "prompt": "summarize"}})
        if repaired.get("hookSpecificOutput", {}).get("permissionDecision") != "allow":
            fails.append(f"Orbit-owned oversized evidence was not auto-repaired: {repaired}")
        packet = json.loads((orbit / "intelligence/latest.json").read_text())
        if len(packet.get("retrieval", {}).get("files", [])) > 12:
            fails.append("automatic evidence repair still exceeded the 12-file cap")
        invoke(project, {"hook_event_name": "PostToolUse", "tool_name": "Agent",
                         "tool_use_id": "repair-edge", "cwd": str(project),
                         "tool_input": {"subagent_type": "reporter"},
                         "tool_response": {"status": "completed", "totalTokens": 10}})

        pre = invoke(project, {"hook_event_name": "PreToolUse", "tool_name": "Agent",
                     "tool_use_id": "edge-1", "cwd": str(project),
                     "tool_input": {"subagent_type": "reporter", "prompt": "summarize"}})
        out = pre.get("hookSpecificOutput", {})
        if out.get("permissionDecision") != "allow":
            fails.append(f"admissible Agent edge was not allowed: {pre}")
        updated = out.get("updatedInput", {})
        if updated.get("run_in_background") is not False or updated.get("model") != "haiku":
            fails.append("Agent edge was not forced measurable and routed to its policy model")
        ledger = json.loads((orbit / "budget.json").read_text())
        if "edge-1" not in ledger.get("reservations", {}):
            fails.append("preflight did not reserve the Agent edge")

        oversized = invoke(project, {"hook_event_name": "PreToolUse", "tool_name": "Agent",
                     "tool_use_id": "oversized", "cwd": str(project),
                     "tool_input": {"subagent_type": "planner", "prompt": "repository dump " * 1000}})
        if oversized.get("hookSpecificOutput", {}).get("permissionDecision") != "deny":
            fails.append("oversized repository-shaped Agent packet was not hard-denied")
        if "ask" in json.dumps(oversized).lower():
            fails.append("oversized Agent packet exposed a confirmation path")

        invoke(project, {"hook_event_name": "PostToolUse", "tool_name": "Agent",
                         "tool_use_id": "edge-1", "cwd": str(project),
                         "tool_input": {"subagent_type": "reporter"},
                         "tool_response": {"status": "completed", "totalTokens": 777,
                                           "usage": {"input_tokens": 500, "output_tokens": 277}}})
        ledger = json.loads((orbit / "budget.json").read_text())
        if ledger["spent"].get("reporter") != 787 or "edge-1" in ledger.get("reservations", {}):
            fails.append("PostToolUse did not reconcile reservation to actual usage")

        (orbit / "activity.jsonl").write_text(json.dumps({"phase": "gear", "gear": "T100"}) + "\n")
        invoke(project, {"hook_event_name": "PreToolUse", "tool_name": "Agent",
                         "tool_use_id": "edge-2", "cwd": str(project),
                         "tool_input": {"subagent_type": "reporter", "prompt": "final"}})
        ledger = json.loads((orbit / "budget.json").read_text())
        if ledger.get("gear") != "T4" or ledger.get("total") != 240000:
            fails.append("arbitrary high gear did not clamp to hard T4")

        (orbit / "STATE.md").write_text("# State\nnext: verify")
        (orbit / "tasks.json").write_text('[{"task":"verify","status":"active"}]')
        invoke(project, {"hook_event_name": "PreCompact", "cwd": str(project)})
        checkpoint = json.loads((orbit / "context-checkpoint.json").read_text())
        if checkpoint.get("goal") != "Fix the checkout" or not isinstance(checkpoint.get("tasks"), list):
            fails.append("compaction checkpoint lost goal or task evidence")
        restored = invoke(project, {"hook_event_name": "PostCompact", "cwd": str(project)})
        if "RESOURCE CHECKPOINT" not in json.dumps(restored):
            fails.append("PostCompact did not restore the bounded goal checkpoint")

        # T1 allows four Agent edges. A fifth triggers automatic governed reconsideration to T2,
        # preserving the goal and spend without asking the user.
        ledger = json.loads((orbit / "budget.json").read_text())
        ledger["gear"] = "T1"; ledger["requested_gear"] = "T1"; ledger["agent_calls"] = 4
        (orbit / "budget.json").write_text(json.dumps(ledger))
        (orbit / "activity.jsonl").write_text(json.dumps({"phase": "gear", "gear": "T1"}) + "\n")
        ceiling = invoke(project, {"hook_event_name": "PreToolUse", "tool_name": "Agent",
                          "tool_use_id": "edge-5", "cwd": str(project),
                          "tool_input": {"subagent_type": "planner", "prompt": "more"}})
        if ceiling.get("hookSpecificOutput", {}).get("permissionDecision") != "allow":
            fails.append("gear-specific Agent-call pressure was not auto-reconsidered")
        if "ask" in json.dumps(ceiling).lower():
            fails.append("Agent-call ceiling exposed a confirmation path")
        ledger = json.loads((orbit / "budget.json").read_text())
        if ledger.get("gear") != "T2" or not ledger.get("reconsiderations"):
            fails.append("Agent-call pressure did not produce a recorded T1→T2 reconsideration")

    with tempfile.TemporaryDirectory() as td:
        project = Path(td); (project / ".orbit").mkdir()
        denied = invoke(project, {"hook_event_name": "PreToolUse", "tool_name": "Agent",
                         "cwd": str(project), "tool_input": {"subagent_type": "planner"}})
        decision = denied.get("hookSpecificOutput", {}).get("permissionDecision")
        if decision != "deny" or "ask" in json.dumps(denied).lower():
            fails.append("missing ledger must deny without a confirmation path")

    # Root model usage shares the same ceiling and repeated hooks do not double count it.
    with tempfile.TemporaryDirectory() as td:
        project = Path(td); orbit = project / ".orbit"; orbit.mkdir()
        (orbit / "loop.config.json").write_text((ROOT / "assets/loop.config.json").read_text())
        (orbit / "checks").mkdir()
        shutil.copy2(ROOT / "assets/checks/repository_intelligence.py",
                     orbit / "checks/repository_intelligence.py")
        (orbit / "intelligence").mkdir()
        (orbit / "intelligence/latest.json").write_text(json.dumps({
            "policy": {"hops": 1}, "retrieval": {"files": [], "estimated_tokens": 0}}))
        transcript = project / "session.jsonl"
        transcript.write_text(json.dumps({"type": "assistant", "message": {"id": "m1",
            "role": "assistant", "usage": {"input_tokens": 18000, "output_tokens": 3000}}}) + "\n")
        base = {"session_id": "s2", "prompt": "root-heavy goal", "cwd": str(project),
                "transcript_path": str(transcript)}
        invoke(project, {"hook_event_name": "UserPromptSubmit", **base})
        invoke(project, {"hook_event_name": "UserPromptSubmit", **base})
        ledger = json.loads((orbit / "budget.json").read_text())
        if sum(ledger.get("parent_usage", {}).values()) != 21000:
            fails.append("root transcript usage was missing or double-counted")
        resized = invoke(project, {"hook_event_name": "PreToolUse", "tool_name": "Agent",
                         "tool_use_id": "root-edge", "cwd": str(project),
                         "transcript_path": str(transcript),
                         "tool_input": {"subagent_type": "planner", "prompt": "delegate"}})
        ledger = json.loads((orbit / "budget.json").read_text())
        if resized.get("hookSpecificOutput", {}).get("permissionDecision") != "allow" or ledger.get("gear") == "T1":
            fails.append("measured root usage did not trigger automatic governed expansion")
        if ledger.get("goal") != "root-heavy goal" or not ledger.get("reconsiderations"):
            fails.append("mid-goal expansion lost the immutable goal or its audit record")

    if fails:
        print("FAIL: resource governor")
        for failure in fails: print("  -", failure)
        return 1
    print("PASS: resource governor (immutable goal · auto reconsideration · bounded evidence · actual charge · checkpoint)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
