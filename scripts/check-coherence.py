#!/usr/bin/env python3
"""
Coherence gate — catches roster/skill drift between the docs and what the scaffolder
actually provisions. The failure mode this prevents: a role or CLAUDE.md references a
`.orbit/skills/<x>.md` that `scripts/scaffold.py` never copies in (a "phantom skill"),
or a doc names a spine role the scaffolder doesn't create (roster drift). Both look fine
in review and break silently at runtime.

Invariants enforced:
  A. Every role in ROLES_CORE has an agent template in assets/claude-agents/<role>.md,
     and the fallback builder + designer templates exist.
  B. Every playbook in PLAYBOOKS_ALWAYS / PLAYBOOKS_FRONTEND exists in references/playbooks/.
  C. Every `.orbit/skills/<name>.md` a shipped agent template LOADS is either provisioned
     (in a PLAYBOOKS_* list) or an explicitly author-per-domain skill — no phantoms.
  D. The "universal spine" list in SKILL.md and references/roles.md names exactly ROLES_CORE.
  F. Every placed check/hook script (FILE_PLAN + QA_FRONTEND + DESIGN_GATE_FRONTEND src files,
     plus every *_CMD constant's referenced filename) exists in assets/ — a hook wired into
     settings.json can never point at a file the scaffolder doesn't actually place.

Run:  python3 scripts/check-coherence.py   (exit 0 = coherent, 1 = drift found)
"""
import importlib.util
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Skills authored per-domain by the user (placeholders / rubrics we intentionally do NOT ship).
AUTHOR_PER_DOMAIN = {"input-validation", "output-formatting", "quality-review",
                     "domain", "domain-knowledge"}


def _load_scaffold():
    spec = importlib.util.spec_from_file_location(
        "scaffold", os.path.join(ROOT, "scripts", "scaffold.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["scaffold"] = mod
    spec.loader.exec_module(mod)          # main() is guarded by __name__, so import is safe
    return mod


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def main():
    sc = _load_scaffold()
    fails = []

    # --- A. spine roles have agent templates ---------------------------------------
    for role in sc.ROLES_CORE:
        if not os.path.isfile(os.path.join(ROOT, "assets", "claude-agents", f"{role}.md")):
            fails.append(f"[A] ROLES_CORE has '{role}' but assets/claude-agents/{role}.md is missing")
    for extra in ("builder", "designer"):
        if not os.path.isfile(os.path.join(ROOT, "assets", "claude-agents", f"{extra}.md")):
            fails.append(f"[A] assets/claude-agents/{extra}.md is missing (needed by scaffolder)")

    # --- B. provisioned playbooks exist --------------------------------------------
    provisioned = set()
    for pb in list(sc.PLAYBOOKS_ALWAYS) + list(sc.PLAYBOOKS_FRONTEND):
        provisioned.add(pb[:-3] if pb.endswith(".md") else pb)
        if not os.path.isfile(os.path.join(ROOT, "references", "playbooks", pb)):
            fails.append(f"[B] PLAYBOOKS list names '{pb}' but references/playbooks/{pb} is missing")

    # --- C. no phantom skill loads in shipped agent templates ----------------------
    agents_dir = os.path.join(ROOT, "assets", "claude-agents")
    skill_ref = re.compile(r"\.orbit/skills/([A-Za-z0-9_-]+)\.md")
    loaded = set()                                          # every playbook some agent references
    for fn in sorted(os.listdir(agents_dir)):
        if not fn.endswith(".md"):
            continue
        text = _read("assets", "claude-agents", fn)
        for name in skill_ref.findall(text):
            loaded.add(name)
            if name in provisioned or name in AUTHOR_PER_DOMAIN:
                continue
            fails.append(f"[C] {fn} loads .orbit/skills/{name}.md — not provisioned and not "
                         f"author-per-domain (phantom skill)")

    # --- E. no DEAD provisioning: every always-provisioned playbook is loaded by some agent ----
    # (the reverse of C — catches a playbook copied into every repo that no role ever reads).
    always = {pb[:-3] if pb.endswith(".md") else pb for pb in sc.PLAYBOOKS_ALWAYS}
    for name in sorted(always):
        if name not in loaded:
            fails.append(f"[E] playbook '{name}.md' is provisioned into every repo (PLAYBOOKS_ALWAYS) "
                         f"but no agent template loads it — dead provisioning (wire it to a role or drop it)")

    # --- F. every placed check/hook script's source file actually exists -----------
    placed_lists = [sc.FILE_PLAN, sc.QA_FRONTEND, sc.DESIGN_GATE_FRONTEND]
    placed_srcs = set()
    for plist in placed_lists:
        for entry in plist:
            src_rel = entry[0]
            placed_srcs.add(src_rel)
            if not os.path.isfile(os.path.join(ROOT, "assets", src_rel)):
                fails.append(f"[F] a placement list names 'assets/{src_rel}' but that file is missing")
    # every *_CMD constant (the hooks actually wired into settings.json) must reference a file
    # that some placement list above places — otherwise install_hooks could wire a dead path.
    cmd_ref = re.compile(r"\.orbit/checks/([A-Za-z0-9_-]+\.py)")
    for name in dir(sc):
        if not name.endswith("_CMD"):
            continue
        cmd = getattr(sc, name)
        if not isinstance(cmd, str):
            continue
        m = cmd_ref.search(cmd)
        if not m:
            continue
        fn = m.group(1)
        if f"checks/{fn}" not in placed_srcs:
            fails.append(f"[F] {name} references checks/{fn} but no placement list places it")

    # --- D. the documented spine matches ROLES_CORE --------------------------------
    core = set(sc.ROLES_CORE)
    for doc in ("SKILL.md", os.path.join("references", "roles.md")):
        text = _read(*doc.split("/")) if "/" in doc else _read(doc)
        m = re.search(r"universal spine[^\n]*?\(([^)]*)\)", text, re.IGNORECASE | re.DOTALL)
        if not m:
            fails.append(f"[D] {doc}: no 'universal spine (…)' roster list found")
            continue
        listed = set(re.findall(r"[a-z][a-z-]+", m.group(1)))
        missing = core - listed
        if missing:
            fails.append(f"[D] {doc}: spine list is missing {sorted(missing)}")

    if fails:
        print("FAIL: coherence")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print(f"PASS: coherence ({len(sc.ROLES_CORE)} spine roles, {len(provisioned)} provisioned "
          f"playbooks, 0 phantom skills)")


if __name__ == "__main__":
    main()
