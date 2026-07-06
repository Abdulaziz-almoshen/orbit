#!/usr/bin/env python3
"""
Tests that ORBIT'S OWN generated shell commands don't trip Orbit's OWN safety guard. The guard's
fail-safe asks when a command's NAME is an unresolved shell variable (`"$_p"`) — correct in general,
but Orbit must not *emit* such a command, or /orbit's Step 0 preamble prompts the user every run
(a self-inflicted false positive). The fix: invoke a resolved path through an interpreter
(`bash "$_p"`) so the command name is `bash`, not the variable.

  A. No skill file emits the bare-`$var`-as-command anti-pattern; the preamble uses `bash "$_p"`.
  B. The guard ALLOWS the fixed for-loop-exec idiom, and (documenting the class it protects against)
     still ASKS on the bare form — so the regression is about the GENERATOR, not a guard weakening.
  C. The scaffolder's wired hook commands invoke an interpreter, never a bare `$var`.

Run: python3 tests/test_generated_commands.py   (exit 0 = pass)
"""
import importlib.util
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUARD = os.path.join(ROOT, "assets", "checks", "guard.py")

# The self-tripping anti-pattern: a `"$VAR"` in COMMAND position (start of a command / substitution),
# NOT already guarded by an interpreter (bash/sh/python3/exec …). Kept deliberately specific.
_BARE = re.compile(r'(?:\{\s*|;\s*|&&\s*|\bdo\s+|\bthen\s+|\$\(\s*|=\s*"\$\(\s*)"\$[A-Za-z_][A-Za-z0-9_]*"\s*(?:;|\)|--|\s|$)')
_INTERP = ("bash ", "sh ", "python3 ", "python ", "exec ")


def _guard(cmd):
    p = subprocess.run([sys.executable, GUARD],
                       input=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}),
                       capture_output=True, text=True, timeout=10)
    out = p.stdout.strip()
    return json.loads(out)["hookSpecificOutput"]["permissionDecision"] if out else "ALLOW"


def main():
    fails = []

    # --- A. no skill file emits a bare-$var command; the preamble uses an interpreter --------------
    skill_files = [os.path.join(ROOT, "SKILL.md"),
                   os.path.join(ROOT, "orbit-upgrade", "SKILL.md")]
    for f in skill_files:
        with open(f, encoding="utf-8") as fh:
            text = fh.read()
        for m in _BARE.finditer(text):
            frag = m.group(0)
            # allow it only if an interpreter immediately precedes the var (defensive; the regex already excludes most)
            fails.append(f"[A] {os.path.basename(f)} emits a bare-$var command (guard will prompt): …{frag!r}…")
    # the preamble MUST invoke the resolved path via bash (the fix)
    with open(os.path.join(ROOT, "SKILL.md"), encoding="utf-8") as fh:
        skill = fh.read()
    if 'bash "$_p"' not in skill:
        fails.append("[A] SKILL.md preamble no longer invokes the resolved path via `bash \"$_p\"`")

    # --- B. guard ALLOWS the fixed idiom; still ASKS on the bare form (fix is in the generator) ----
    fixed = 'for _p in a b; do [ -x "$_p" ] && { bash "$_p"; exit 0; }; done'
    if _guard(fixed) != "ALLOW":
        fails.append(f"[B] guard should ALLOW the interpreter-invoked idiom, got {_guard(fixed)}")
    bare = 'for _p in a b; do [ -x "$_p" ] && { "$_p"; exit 0; }; done'
    if _guard(bare) != "ask":
        fails.append(f"[B] guard should still ASK on a bare-$var command (fail-safe), got {_guard(bare)}")

    # --- C. the scaffolder's wired hook commands invoke an interpreter, never a bare $var ----------
    spec = importlib.util.spec_from_file_location("scaffold_gc", os.path.join(ROOT, "scripts", "scaffold.py"))
    sc = importlib.util.module_from_spec(spec)
    sys.modules["scaffold_gc"] = sc
    spec.loader.exec_module(sc)
    for name in dir(sc):
        if name.endswith("_CMD"):
            val = getattr(sc, name)
            if isinstance(val, str) and val.strip().startswith('"$') or (isinstance(val, str) and val.strip().startswith('$')):
                fails.append(f"[C] scaffold.{name} starts with a bare $var command: {val[:50]!r}")

    if fails:
        print(f"FAIL: generated-commands {len(fails)} case(s):")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("PASS: generated-commands (Orbit's own commands don't trip its own guard; interpreter-invoked)")


if __name__ == "__main__":
    main()
