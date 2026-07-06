#!/usr/bin/env python3
"""
Tests that ORBIT'S OWN generated shell commands don't trip Orbit's OWN safety guard. The guard's
fail-safe (correctly) asks when a command's NAME is an unresolved shell variable (`"$_p"`) — but Orbit
must not *emit* such a command, or /orbit's Step 0 preamble prompts the user to trust Orbit before
Orbit has even started (a P1 trust bug). The fix is in the GENERATOR, not the guard: the executable is
always a LITERAL (`./orbit-preamble`); the variable is only ever a `cd` argument.

Acceptance bar (v0.28.x):
  AC1. /orbit Step 0 preamble runs with NO PreToolUse prompt — the EXACT block from SKILL.md,
       evaluated through guard.evaluate(...), returns None.
  AC2. /orbit-upgrade forced check runs with NO prompt — same, from orbit-upgrade/SKILL.md.
  AC3. The guard STILL asks on a real unresolved command name (`"$X"`) and denies a dangerous
       substitution (`$(rm -rf /)`) — the fix did not loosen the guard.
  AC4. The test evaluates the REAL shipped bash block (extracted from the skill file), not a synthetic
       copy — so it can't drift from what ships. (This whole test is that.)

Run: python3 tests/test_generated_commands.py   (exit 0 = pass)
"""
import importlib.util
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _bash_blocks(text):
    return re.findall(r"```bash\n(.*?)```", text, re.DOTALL)


def _read(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return f.read()


def main():
    fails = []
    spec = importlib.util.spec_from_file_location("guard", os.path.join(ROOT, "assets", "checks", "guard.py"))
    g = importlib.util.module_from_spec(spec)
    sys.modules["guard"] = g
    spec.loader.exec_module(g)

    # AC1 + AC4 — the EXACT Step 0 preamble block from SKILL.md must evaluate to None (no prompt)
    pre = [b for b in _bash_blocks(_read("SKILL.md")) if "orbit-preamble" in b and "orbit-update-check" in b]
    if not pre:
        fails.append("[AC1] could not locate the Step 0 preamble bash block in SKILL.md")
    else:
        block = pre[0]
        v = g.evaluate(block)
        if v is not None:
            fails.append(f"[AC1] the real Step 0 preamble block must evaluate to None (no prompt), got {v}")
        if 'bin/orbit-preamble"; do' in block or re.search(r'\{\s*"\$_p"', block) or re.search(r'=\s*"\$\(\s*"\$_p"', block):
            fails.append("[AC1] the preamble still uses a bare-$var command (for-loop / substitution)")
        if "./orbit-preamble" not in block:
            fails.append("[AC1] the preamble should invoke a LITERAL ./orbit-preamble (executable not a $var)")

    # AC2 — the /orbit-upgrade forced-check block must evaluate to None
    upb = [b for b in _bash_blocks(_read("orbit-upgrade", "SKILL.md")) if "orbit-update-check --force" in b]
    if not upb:
        fails.append("[AC2] could not locate the /orbit-upgrade forced-check bash block")
    else:
        v = g.evaluate(upb[0])
        if v is not None:
            fails.append(f"[AC2] the /orbit-upgrade forced-check block must evaluate to None, got {v}")
        if "./orbit-update-check" not in upb[0]:
            fails.append("[AC2] the forced check should invoke a LITERAL ./orbit-update-check")

    # AC3 — the guard is NOT loosened: still asks on a bare-$var command, denies a real substitution
    ax = g.evaluate('"$X" arg')
    if not ax or ax[0] != "ask":
        fails.append(f"[AC3] guard must still ASK on a bare-$var command name, got {ax}")
    dn = g.evaluate('echo "$(rm -rf /)"')
    if not dn or dn[0] != "deny":
        fails.append(f"[AC3] guard must still DENY a dangerous substitution, got {dn}")

    # (bonus) the scaffolder's wired hook commands invoke an interpreter, never a bare $var
    sspec = importlib.util.spec_from_file_location("scaffold_gc", os.path.join(ROOT, "scripts", "scaffold.py"))
    sc = importlib.util.module_from_spec(sspec)
    sys.modules["scaffold_gc"] = sc
    sspec.loader.exec_module(sc)
    for name in dir(sc):
        if name.endswith("_CMD"):
            val = getattr(sc, name)
            if isinstance(val, str) and val.strip().startswith("$"):
                fails.append(f"[bonus] scaffold.{name} starts with a bare $var command: {val[:50]!r}")

    if fails:
        print(f"FAIL: generated-commands {len(fails)} case(s):")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("PASS: generated-commands (real Step 0 + /orbit-upgrade blocks evaluate to None; guard "
          "still asks/denies real cases; executables are literal)")


if __name__ == "__main__":
    main()
