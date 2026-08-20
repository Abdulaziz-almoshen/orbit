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


def asks(output: dict) -> bool:
    return (output.get("hookSpecificOutput", {}).get("permissionDecision") == "ask")


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
                     "tool_input": {"subagent_type": "reporter", "prompt": "summarize",
                                    "run_in_background": True}})
        out = pre.get("hookSpecificOutput", {})
        if out.get("permissionDecision") != "allow":
            fails.append(f"admissible Agent edge was not allowed: {pre}")
        updated = out.get("updatedInput", {})
        if updated.get("run_in_background") is not True or updated.get("model") != "haiku":
            fails.append("Agent edge did not preserve background execution and policy model routing")
        ledger = json.loads((orbit / "budget.json").read_text())
        if "edge-1" not in ledger.get("reservations", {}):
            fails.append("preflight did not reserve the Agent edge")

        # Async launch keeps its reservation; measurable completion reconciles it later.
        invoke(project, {"hook_event_name": "PostToolUse", "tool_name": "Agent",
                         "tool_use_id": "edge-1", "cwd": str(project),
                         "tool_input": {"subagent_type": "reporter"},
                         "tool_response": {"status": "async_launched"}})
        if "edge-1" not in json.loads((orbit / "budget.json").read_text()).get("reservations", {}):
            fails.append("background launch prematurely dropped its budget reservation")

        oversized = invoke(project, {"hook_event_name": "PreToolUse", "tool_name": "Agent",
                     "tool_use_id": "oversized", "cwd": str(project),
                     "tool_input": {"subagent_type": "planner", "prompt": "repository dump " * 1000}})
        if oversized.get("hookSpecificOutput", {}).get("permissionDecision") != "deny":
            fails.append("oversized repository-shaped Agent packet was not hard-denied")
        if asks(oversized):
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

        # The T1 call cap prunes optional communication, never a required Planner edge.
        ledger = json.loads((orbit / "budget.json").read_text())
        ledger["gear"] = "T1"; ledger["requested_gear"] = "T1"; ledger["agent_calls"] = 4
        (orbit / "budget.json").write_text(json.dumps(ledger))
        (orbit / "activity.jsonl").write_text(json.dumps({"phase": "gear", "gear": "T1"}) + "\n")
        ceiling = invoke(project, {"hook_event_name": "PreToolUse", "tool_name": "Agent",
                          "tool_use_id": "edge-5", "cwd": str(project),
                          "tool_input": {"subagent_type": "planner", "prompt": "more"}})
        if ceiling.get("hookSpecificOutput", {}).get("permissionDecision") != "allow":
            fails.append("required Planner edge was pruned by the optional Agent-call ceiling")
        if asks(ceiling):
            fails.append("Agent-call ceiling exposed a confirmation path")
        ledger = json.loads((orbit / "budget.json").read_text())
        if ledger.get("gear") != "T1":
            fails.append("required Planner edge unnecessarily widened the token envelope")

        # Optional Advisor communication still obeys the call ceiling and expands only when capacity exists.
        optional = invoke(project, {"hook_event_name": "PreToolUse", "tool_name": "Agent",
                          "tool_use_id": "optional-advisor", "cwd": str(project),
                          "tool_input": {"subagent_type": "advisor", "prompt": "second opinion"}})
        ledger = json.loads((orbit / "budget.json").read_text())
        if optional.get("hookSpecificOutput", {}).get("permissionDecision") != "allow" or ledger.get("gear") != "T2":
            fails.append("optional Agent pressure was not governed by one-gear reconsideration")

    with tempfile.TemporaryDirectory() as td:
        project = Path(td); (project / ".orbit").mkdir()
        denied = invoke(project, {"hook_event_name": "PreToolUse", "tool_name": "Agent",
                         "cwd": str(project), "tool_input": {"subagent_type": "planner"}})
        decision = denied.get("hookSpecificOutput", {}).get("permissionDecision")
        if decision != "deny" or asks(denied):
            fails.append("missing ledger must deny without a confirmation path")

    # Installing/upgrading the governor during a live board must bind to the unfinished run goal,
    # never replace it with the next conversational follow-up.
    with tempfile.TemporaryDirectory() as td:
        project = Path(td); orbit = project / ".orbit"; orbit.mkdir()
        (orbit / "loop.config.json").write_text((ROOT / "assets/loop.config.json").read_text())
        (orbit / "run.json").write_text(json.dumps({"goal": "Ship the original product goal"}))
        (orbit / "active-goal.json").write_text(json.dumps({
            "route_id": "route-original", "goal": "Ship the original product goal", "gear": "T1"
        }))
        (orbit / "tasks.json").write_text(json.dumps([
            {"id": "U1", "title": "Build", "status": "done"},
            {"id": "U2", "title": "Report", "status": "pending"},
        ]))
        invoke(project, {"hook_event_name": "UserPromptSubmit", "session_id": "upgrade-session",
                         "prompt": "what is happening?", "cwd": str(project)})
        if json.loads((orbit / "budget.json").read_text()).get("goal") != "Ship the original product goal":
            fails.append("mid-run governor activation replaced the board goal with a follow-up question")

        # A later follow-up also repairs a previously mis-bound active ledger without resetting spend.
        ledger = json.loads((orbit / "budget.json").read_text())
        ledger["goal"] = "what is happening?"; ledger["goal_hash"] = "wrong"; ledger["spent"]["reviewer"] = 123
        (orbit / "budget.json").write_text(json.dumps(ledger))
        invoke(project, {"hook_event_name": "UserPromptSubmit", "session_id": "upgrade-session",
                         "prompt": "is CPO back?", "cwd": str(project)})
        repaired = json.loads((orbit / "budget.json").read_text())
        if repaired.get("goal") != "Ship the original product goal" or repaired["spent"].get("reviewer") != 123:
            fails.append("unfinished-board goal repair reset spend or retained the follow-up goal")

        # Trusted compatibility path clears stale INPUT and disables an old customized Stop marker
        # when the latest routed turn is only a question.
        (orbit / "run.json").write_text(json.dumps({"goal": "Ship the original product goal",
                                                     "blocked_question": "Claude is waiting"}))
        (orbit / ".last-task-route").write_text("old-task")
        with (orbit / "activity.jsonl").open("a") as stream:
            stream.write(json.dumps({"phase": "route", "status": "info",
                                     "msg": "routing: question — status?"}) + "\n")
        invoke(project, {"hook_event_name": "UserPromptSubmit", "session_id": "upgrade-session",
                         "prompt": "status?", "cwd": str(project)})
        if json.loads((orbit / "run.json").read_text()).get("blocked_question") is not None:
            fails.append("trusted hook did not clear stale user-input state")
        if (orbit / ".last-task-route").exists():
            fails.append("question turn retained an old task Stop-gate marker")

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
        if sum(ledger.get("parent_usage", {}).values()) != 0:
            fails.append("pre-goal transcript history was charged to the new goal")
        with transcript.open("a") as stream:
            stream.write(json.dumps({"type": "assistant", "message": {"id": "m2",
                "role": "assistant", "usage": {"input_tokens": 18000, "output_tokens": 3000}}}) + "\n")
        resized = invoke(project, {"hook_event_name": "PreToolUse", "tool_name": "Agent",
                         "tool_use_id": "root-edge", "cwd": str(project),
                         "transcript_path": str(transcript),
                         "tool_input": {"subagent_type": "planner", "prompt": "delegate"}})
        ledger = json.loads((orbit / "budget.json").read_text())
        if sum(ledger.get("parent_usage", {}).values()) != 21000:
            fails.append("per-goal root usage delta was missing or double-counted")
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
