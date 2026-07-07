#!/usr/bin/env python3
"""
Trusted safety runner (v0.31.0). The guard's executable logic moved to the trusted install
(`bin/orbit-guard`), and a repo contributes only DECLARATIVE rules (`.orbit/security/rules.json`). Core
invariant: a repo can ADD caution but can NEVER weaken the built-in wall, and a tampered project file
is irrelevant once the trusted runner is wired.

Covers: compile_rules (data-only, escalate-only), the built-in wall unchanged, the trusted orbit-guard
binary end-to-end, and scaffold wiring (new → orbit-guard, existing → keep guard.py).

Run: python3 tests/test_trusted_guard.py   (exit 0 = pass)
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
fails = []


def _load_guard():
    spec = importlib.util.spec_from_file_location("guard", ROOT / "assets" / "checks" / "guard.py")
    g = importlib.util.module_from_spec(spec)
    sys.modules["guard"] = g
    spec.loader.exec_module(g)
    return g


G = _load_guard()


def ck(cond, msg):
    if not cond:
        fails.append(msg)


def _dec(cmd):
    G.EXTRA_RULES = getattr(G, "EXTRA_RULES", [])
    v = G.evaluate(cmd)
    return v[0] if v else "allow"


def test_builtin_wall_unchanged():
    G.EXTRA_RULES = []
    ck(_dec("rm -rf /") == "deny", "built-in: rm -rf / must deny")
    ck(_dec("git push --force") == "deny", "built-in: force-push must deny")
    ck(_dec("git push") == "ask", "built-in: plain push must ask")
    ck(_dec("ls -la") == "allow", "built-in: ls must allow")


def test_project_rules_add_caution():
    G.EXTRA_RULES = G.compile_rules([
        {"id": "deploy", "decision": "ask", "match": {"argv_contains": ["deploy"]}, "reason": "checkpoint"},
        {"id": "migrate", "decision": "deny", "match": {"argv_contains": ["manage.py", "migrate"]}, "reason": "frozen"},
    ])
    ck(_dec("deploy prod") == "ask", "project rule should add an ask for deploy")
    ck(_dec("python manage.py migrate") == "deny", "project rule should deny migrations")
    ck(_dec("python manage.py shell") == "allow", "unrelated command unaffected")


def test_project_rules_cannot_weaken():
    # 'allow' is never honored, and an 'ask' can't lower a built-in deny
    compiled = G.compile_rules([
        {"id": "a", "decision": "allow", "match": {"argv_contains": ["rm"]}, "reason": "try allow"},
        {"id": "b", "decision": "ask", "match": {"argv_contains": ["rm"]}, "reason": "try soften"},
    ])
    ck(len(compiled) == 1, f"'allow' rule must be dropped at compile (got {len(compiled)} rules)")
    G.EXTRA_RULES = compiled
    ck(_dec("rm -rf /") == "deny", "a project rule must NOT downgrade the built-in rm -rf / deny")


def test_compile_rules_robustness():
    ck(G.compile_rules("not a list") == [], "non-list rules → []")
    ck(G.compile_rules([{"decision": "deny"}]) == [], "a rule with no match conditions is skipped")
    ck(len(G.compile_rules([{"decision": "deny", "match": {"argv_contains": ["x"]}}] * 500)) == 200,
       "rules are capped at 200")
    # AND semantics within argv_contains
    G.EXTRA_RULES = G.compile_rules([{"decision": "deny", "match": {"argv_contains": ["a", "b"]}, "reason": "r"}])
    ck(_dec("a b") == "deny" and _dec("a") == "allow", "argv_contains requires ALL tokens present")
    # argv_regex
    G.EXTRA_RULES = G.compile_rules([{"decision": "ask", "match": {"argv_regex": "push .*prod"}, "reason": "r"}])
    ck(_dec("git push origin prod") == "ask", "argv_regex should match")
    G.EXTRA_RULES = []


def _run_guard(payload, rules=None):
    """Drive the trusted orbit-guard binary end-to-end. Returns ('allow','') or (decision, reason)."""
    with tempfile.TemporaryDirectory() as d:
        t = Path(d)
        (t / ".orbit" / "security").mkdir(parents=True)
        if rules is not None:
            (t / ".orbit" / "security" / "rules.json").write_text(json.dumps({"version": 1, "rules": rules}))
        elif rules == "corrupt":
            (t / ".orbit" / "security" / "rules.json").write_text("{ broken")
        pl = dict(payload)
        pl.setdefault("cwd", str(t))
        r = subprocess.run([sys.executable, str(ROOT / "bin" / "orbit-guard")], input=json.dumps(pl),
                           capture_output=True, text=True, env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(ROOT)})
        out = r.stdout.strip()
        if not out:
            return ("allow", "")
        d2 = json.loads(out)["hookSpecificOutput"]
        return (d2["permissionDecision"], d2.get("permissionDecisionReason", ""))


def test_orbit_guard_binary():
    ck(_run_guard({"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}})[0] == "deny",
       "orbit-guard: built-in deny end-to-end")
    ck(_run_guard({"tool_name": "Bash", "tool_input": {"command": "git push"}})[0] == "ask",
       "orbit-guard: built-in ask end-to-end")
    ck(_run_guard({"tool_name": "Bash", "tool_input": {"command": "deploy prod"}},
                  rules=[{"id": "d", "decision": "ask", "match": {"argv_contains": ["deploy"]}, "reason": "cp"}])[0] == "ask",
       "orbit-guard: project rule applied end-to-end")
    ck(_run_guard({"tool_name": "Edit", "tool_input": {"file_path": "x"}})[0] == "allow",
       "orbit-guard: non-Bash tool allowed")
    # fail open on garbage
    r = subprocess.run([sys.executable, str(ROOT / "bin" / "orbit-guard")], input="not json",
                       capture_output=True, text=True, env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(ROOT)})
    ck(r.returncode == 0 and not r.stdout.strip(), "orbit-guard: garbage payload → fail open")


def test_scaffold_wires_trusted_guard():
    scaffold = ROOT / "scripts" / "scaffold.py"
    with tempfile.TemporaryDirectory() as d:
        t = Path(d)
        subprocess.run([sys.executable, str(scaffold), "--target", str(t), "--surfaces", "api", "--install-hooks"],
                       capture_output=True, text=True)
        pre = json.loads((t / ".claude/settings.json").read_text())["hooks"]["PreToolUse"]
        ck(any("orbit-guard" in json.dumps(e) for e in pre), "fresh scaffold wires the trusted orbit-guard")
        ck(not any(".orbit/checks/guard.py" in json.dumps(e) for e in pre), "fresh scaffold does NOT wire legacy guard.py")
        ck((t / ".orbit/security/rules.json").exists(), "fresh scaffold provisions .orbit/security/rules.json")
    # existing repo with legacy guard.py wired → kept, orbit-guard NOT added
    with tempfile.TemporaryDirectory() as d:
        t = Path(d)
        (t / ".claude").mkdir()
        (t / ".orbit").mkdir()
        (t / ".claude/settings.json").write_text(json.dumps(
            {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command",
             "command": 'python3 "$CLAUDE_PROJECT_DIR/.orbit/checks/guard.py"'}]}]}}))
        subprocess.run([sys.executable, str(scaffold), "--target", str(t), "--surfaces", "api", "--install-hooks"],
                       capture_output=True, text=True)
        pre = json.loads((t / ".claude/settings.json").read_text())["hooks"]["PreToolUse"]
        ck(any(".orbit/checks/guard.py" in json.dumps(e) for e in pre), "existing legacy guard.py is KEPT")
        ck(not any("orbit-guard" in json.dumps(e) for e in pre), "existing repo is NOT re-wired to orbit-guard")


def test_repo_cannot_shadow_the_engine():
    """Adversarial: a repo plants a fake 'allow-everything' assets/checks/guard.py in its OWN tree and
    runs orbit-guard from there. The REAL plugin guard must load (rm -rf / still denies)."""
    with tempfile.TemporaryDirectory() as d:
        t = Path(d)
        (t / "assets" / "checks").mkdir(parents=True)
        (t / ".orbit" / "security").mkdir(parents=True)
        (t / "assets" / "checks" / "guard.py").write_text(
            "def evaluate(cmd,_depth=0): return None\ndef compile_rules(r): return []\nEXTRA_RULES=[]\n")
        r = subprocess.run([sys.executable, str(ROOT / "bin" / "orbit-guard")],
                           input=json.dumps({"cwd": str(t), "tool_name": "Bash", "tool_input": {"command": "rm -rf /"}}),
                           capture_output=True, text=True, env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(ROOT)})
        out = r.stdout.strip()
        dec = json.loads(out)["hookSpecificOutput"]["permissionDecision"] if out else "allow"
        ck(dec == "deny", "a repo's fake guard.py must NOT shadow the trusted engine (rm -rf / must stay deny)")


def test_hostile_rules_never_weaken():
    """Adversarial: no rules.json variant may disable the built-in wall."""
    variants = [
        [{"decision": "allow", "match": {"argv_contains": ["rm"]}, "reason": "x"}],
        [{"decision": "ask", "match": {"argv_contains": ["rm"]}, "reason": "x"}],
        [{"decision": "warn", "match": {"argv_contains": ["rm"]}, "reason": "x"}],
        ["a-string", 42, None],
        [{"decision": "deny", "match": {}, "reason": "no conditions"}],
    ]
    for v in variants:
        G.EXTRA_RULES = G.compile_rules(v)
        ck(_dec("rm -rf /") == "deny", f"hostile rules {v!r:.40} must not weaken the built-in deny")
    G.EXTRA_RULES = []


def main():
    for fn in (test_builtin_wall_unchanged, test_project_rules_add_caution, test_project_rules_cannot_weaken,
               test_compile_rules_robustness, test_orbit_guard_binary, test_scaffold_wires_trusted_guard,
               test_repo_cannot_shadow_the_engine, test_hostile_rules_never_weaken):
        try:
            fn()
        except Exception as e:
            fails.append(f"[{fn.__name__}] raised {type(e).__name__}: {e}")
    if fails:
        print(f"FAIL: trusted-guard {len(fails)} case(s):")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("PASS: trusted-guard (built-in wall unchanged · project rules escalate-only · can't weaken a "
          "deny · corrupt→built-in · orbit-guard binary e2e · scaffold wires trusted / keeps legacy)")


if __name__ == "__main__":
    main()
