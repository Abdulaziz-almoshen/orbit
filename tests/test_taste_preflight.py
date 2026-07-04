#!/usr/bin/env python3
"""
Tests the TasteSkill merge (v0.27.0) — the taste-preflight playbook and its wiring.

Covers the step-8 acceptance list end-to-end:
  1. The Designer (and its design skills) is provisioned ONLY for UI repos — a backend/api repo
     gets no designer.md and no taste-preflight.md.
  2. A UI repo provisions taste-preflight.md into .orbit/skills/ (alongside the other design skills).
  3. A UI repo provisions the richer 67-style catalog into .orbit/skills/design-styles/.
  4. The Designer agent template LOADS taste-preflight (so the role actually reads it) and records
     a taste_preflight block on HEAVY.
  5. QA + Reviewer gates REQUIRE the taste_preflight record on HEAVY UI (content of the shipped
     playbooks / roles doc), and the anti-slop bans are folded into anti-ai-aesthetics.md.
  6. The em-dash ban is scoped to shipped UI copy — NOT Orbit's own internal docs (the adaptation
     that keeps the house style intact).

(The design-gate HOOK behaviour — HEAVY-without-taste_preflight asks — is covered in
test_design_gate.py; the provisioning-count coherence is covered by scripts/check-coherence.py.)

Run: python3 tests/test_taste_preflight.py   (exit 0 = pass)
"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCAFFOLD = os.path.join(ROOT, "scripts", "scaffold.py")
PLAYBOOKS = os.path.join(ROOT, "references", "playbooks")


def _scaffold(surfaces):
    d = tempfile.mkdtemp()
    subprocess.run(["git", "init", "-q", d], check=True)
    subprocess.run([sys.executable, SCAFFOLD, "--surfaces", surfaces, "--target", d],
                   capture_output=True, text=True, check=True)
    return d


def _read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


def main():
    fails = []

    # --- 1/2/3. UI repo: Designer + taste-preflight + 67-style catalog all provisioned ------
    ui = _scaffold("web")
    try:
        if not os.path.isfile(os.path.join(ui, ".claude", "agents", "designer.md")):
            fails.append("[1] UI repo: designer.md agent not provisioned")
        if not os.path.isfile(os.path.join(ui, ".orbit", "roles", "designer.md")):
            fails.append("[1] UI repo: .orbit/roles/designer.md not provisioned")
        tp = os.path.join(ui, ".orbit", "skills", "taste-preflight.md")
        if not os.path.isfile(tp):
            fails.append("[2] UI repo: taste-preflight.md NOT copied into .orbit/skills/")
        styles_dir = os.path.join(ui, ".orbit", "skills", "design-styles")
        n_styles = len([f for f in os.listdir(styles_dir) if f.endswith(".md")]) if os.path.isdir(styles_dir) else 0
        if n_styles < 67:
            fails.append(f"[3] UI repo: expected the 67-style catalog, found {n_styles} styles")
    finally:
        subprocess.run(["rm", "-rf", ui])

    # --- 1. non-UI repo: no Designer, no taste-preflight ------------------------------------
    api = _scaffold("api")
    try:
        if os.path.isfile(os.path.join(api, ".claude", "agents", "designer.md")):
            fails.append("[1] non-UI repo: designer.md should NOT be provisioned")
        if os.path.isfile(os.path.join(api, ".orbit", "skills", "taste-preflight.md")):
            fails.append("[1] non-UI repo: taste-preflight.md should NOT be provisioned")
    finally:
        subprocess.run(["rm", "-rf", api])

    # --- 4. the Designer LOADS taste-preflight AND records the block ONLY on the HEAVY branch --
    #     (a substring check can't tell HEAVY-only from unconditional — so assert the STRUCTURE:
    #      taste_preflight must live inside the HEAVY branch, and the TRIVIAL branch must NOT
    #      require it. This catches a regression where it leaks onto the TRIVIAL fast lane.)
    designer = _read(ROOT, "assets", "claude-agents", "designer.md")
    if ".orbit/skills/taste-preflight.md" not in designer:
        fails.append("[4] designer.md does not LOAD .orbit/skills/taste-preflight.md (coherence: phantom risk)")
    ti, hi = designer.find("**TRIVIAL**"), designer.find("**HEAVY**")
    s2 = designer.find("\n2.", hi if hi >= 0 else 0)          # end of procedure step 1 (the HEAVY branch)
    if ti < 0 or hi < 0 or s2 < 0 or not (ti < hi < s2):
        fails.append("[4] designer.md procedure structure changed — can't locate the TRIVIAL/HEAVY "
                     f"branches to verify conditional recording (ti={ti}, hi={hi}, s2={s2})")
    else:
        trivial_branch, heavy_branch = designer[ti:hi], designer[hi:s2]
        if "taste_preflight" not in heavy_branch and "taste preflight" not in heavy_branch.lower():
            fails.append("[4] designer.md does not record/run the taste preflight on the HEAVY branch")
        if "taste_preflight" in trivial_branch or "taste preflight" in trivial_branch.lower():
            fails.append("[4] designer.md ties the taste preflight to the TRIVIAL branch — it must be "
                         "HEAVY-only (the TRIVIAL fast lane skips it)")

    # --- 5. QA + Reviewer BOTH require the record; bans folded into anti-ai-aesthetics ---------
    #     (per-ROW check, not a global count — a count>=2 could be satisfied by one row alone.)
    qa = _read(PLAYBOOKS, "qa-validation.md")
    if "taste_preflight" not in qa:
        fails.append("[5] qa-validation.md does not require the taste_preflight record on HEAVY")
    roles = _read(ROOT, "references", "roles.md")
    rows = {ln.split("**", 2)[1].strip(): ln for ln in roles.splitlines()
            if ln.startswith("| **") and ln.count("**") >= 2}
    for role in ("Reviewer / Evaluator", "QA Engineer"):
        row = rows.get(role, "")
        if "taste_preflight" not in row:
            fails.append(f"[5] roles.md '{role}' row does not require the taste_preflight record")
    bans = _read(PLAYBOOKS, "anti-ai-aesthetics.md")
    for tell in ("Em-dash", "fake dashboard", "purple", "beige", "John Doe"):
        if tell.lower() not in bans.lower():
            fails.append(f"[5] anti-ai-aesthetics.md missing folded-in anti-slop ban: {tell!r}")

    # --- 5b. the taste gate is HEAVY-only end-to-end: a TRIVIAL marker skips it, a HEAVY -------
    #     approval with NO taste_preflight does NOT. (Acceptance items #2/#3/#5 at the hook layer.)
    gate = os.path.join(ROOT, "assets", "checks", "design-gate.py")

    def _gate_decision(repo):
        payload = json.dumps({"tool_name": "Edit",
                              "tool_input": {"file_path": os.path.join(repo, "src", "X.tsx")},
                              "cwd": repo})
        out = subprocess.run([sys.executable, gate], input=payload,
                             capture_output=True, text=True, timeout=10).stdout.strip()
        return json.loads(out)["hookSpecificOutput"]["permissionDecision"] if out else None

    with tempfile.TemporaryDirectory() as d:                  # TRIVIAL marker, no taste_preflight → allow
        os.makedirs(os.path.join(d, ".orbit", "design"))
        open(os.path.join(d, ".orbit", "design", "TRIVIAL"), "w").write("trivial: copy fix\n")
        if _gate_decision(d) is not None:
            fails.append("[3] TRIVIAL work is not exempt from the taste gate (hook asked with a TRIVIAL marker)")
    with tempfile.TemporaryDirectory() as d:                  # HEAVY, no taste_preflight → ask
        os.makedirs(os.path.join(d, "design"))
        with open(os.path.join(d, "design", "approved.json"), "w") as f:
            json.dump({"component": "x", "impact_level": "HEAVY"}, f)
        if _gate_decision(d) != "ask":
            fails.append("[5] HEAVY approval with no taste_preflight is not gated by the hook")

    # --- 6. em-dash ban is SCOPED to shipped UI copy, not Orbit's own docs -----------------
    taste = _read(PLAYBOOKS, "taste-preflight.md")
    if "em-dash" not in taste.lower():
        fails.append("[6] taste-preflight.md does not mention the em-dash ban")
    # the scoping sentence must exist so the ban isn't read as applying to internal docs
    if "internal" not in taste.lower() or "shipped" not in taste.lower():
        fails.append("[6] taste-preflight.md does not SCOPE the em-dash ban to shipped UI copy "
                     "(must exempt Orbit's internal docs)")
    # and the playbook itself uses em-dashes freely (proves the house style is intact)
    if "—" not in taste:
        fails.append("[6] taste-preflight.md avoids em-dashes itself — the scope note is meant to "
                     "keep the internal house style, which uses them")

    if fails:
        print(f"FAIL: taste-preflight {len(fails)} case(s):")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("PASS: taste-preflight (UI-only provisioning + 67 styles + designer loads it + QA/Reviewer "
          "gates + folded bans + scoped em-dash ban)")


if __name__ == "__main__":
    main()
