#!/usr/bin/env python3
"""
Scaffold the deterministic skeleton of the orbit system into a target repo.

This lays down the mechanical, identical-every-time part in ONE run — so /orbit setup is a
script (seconds), not the model authoring ~20 files by hand (minutes). It creates the dirs and
drops in: the engine files (loop.config.json, loop.py, activity.py, ralph_loop.sh, orbit-status,
guard.py), the reusable skill-library playbooks, the working-state file, and the full standard
sub-agent team (both the Claude Code adapters in .claude/agents/ and the model-agnostic specs in
.orbit/roles/).

It deliberately does NOT write the ONE genuinely bespoke file -- CLAUDE.md -- which the agent
authors per-repo from references/claude-md-template.md after characterizing the project. That's
the same split mature tools use (deterministic scaffold via CLI/templates; the LLM writes only
the project-specific spec).

Safety: never overwrites. If a target file exists it's left untouched and reported, so your
existing files are never clobbered.

Usage:
  python scaffold.py --target /path/to/repo      # default target: current directory
  python scaffold.py --frontend                  # also stand up the Designer + design playbooks
  python scaffold.py --install-hooks             # also wire the PreToolUse safety hook
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import time
from pathlib import Path

# Hooks that shipped with a defect in an earlier version and must be re-provisioned in existing
# repos. `marker` is a version-STABLE substring that identifies the file as an Orbit hook of this
# kind (so we know when a file is "ours, but outdated" vs unrelated). We auto-replace ONLY a file
# whose sha256 is a known-old shipped version; a file that's ours-but-modified gets a warning +
# manual instructions; a file already at the current shipped version is left untouched.
HOOK_MIGRATIONS = [
    {"src": "checks/guard.py", "dst": ".orbit/checks/guard.py",
     "marker": b"Orbit safety guard",
     "old_hashes": {
         "0c5eb314a1dc64ad408adeb0d2170644f9bc48eeb343b562fbe6bf17fb098013",  # <0.23.0 (dead output shape)
         "3c5f77344b6857059593dc28e612fd9cae07948401adf6b447ae9df3270abc9c",  # 0.23.0 (narrow + bypassable)
     },
     "why": "the safety wall used an output shape Claude Code ignored (<0.23.0, blocks did nothing) "
            "and had narrow coverage with several one-token bypasses (0.23.0); 0.23.1 hardens it"},
    {"src": "checks/route.py", "dst": ".orbit/checks/route.py",
     "marker": b"UserPromptSubmit hook",
     "old_hashes": {
         "6e821feb7f8b2c400d1f1254a0f5fef2d225ab8858af5bde0c226987f62f8ec8",
         "3cdb8b75d49da422b8b09504e3f612f6e6b3d539d41ee35923aa98ef1c21c77b",
         "39040718046c1e57aede2eab41291c874da37392507693205f80ec880cae1584",
         "92c14909470a56f2405900cdc1a1e1a414bd96326682eecacb60f088ddca16fd",
     },
     "why": "its event log crashed the orbit-status dashboard and its injected routing text overclaimed"},
]


def migrate_hooks(target: Path, created, warnings):
    """Carry existing repos forward to the current shipped hooks (security/correctness fixes).
    Auto-replaces ONLY a byte-identical known-old shipped version; a locally-modified hook is
    warned about (never overwritten); an already-current hook is left untouched."""
    for m in HOOK_MIGRATIONS:
        dst = target / m["dst"]
        if not dst.exists():
            continue                                        # fresh file — normal _place copies the new one
        content = dst.read_bytes()
        if m["marker"] not in content:
            continue                                        # not an Orbit hook of this kind — leave it
        src = ASSETS / m["src"]
        new = src.read_bytes()
        cur = hashlib.sha256(content).hexdigest()
        if cur == hashlib.sha256(new).hexdigest():
            continue                                        # already the current shipped version
        if cur in m["old_hashes"]:
            bak = dst.with_name(dst.name + f".bak.{int(time.time())}")
            bak.write_bytes(content)
            dst.write_bytes(new)
            dst.chmod(0o755)
            created.append(f"{m['dst']}  (⚠ UPDATED — {m['why']}; old version → {bak.name})")
        else:
            warnings.append(
                f"{m['dst']} is an outdated Orbit hook that was locally modified — NOT auto-replaced. "
                f"({m['why']}.) Fix: diff it against {src} and port your changes.")

SKILL_ROOT = Path(__file__).resolve().parent.parent
ASSETS = SKILL_ROOT / "assets"
REFERENCES = SKILL_ROOT / "references"
PLAYBOOKS = REFERENCES / "playbooks"
AGENTS = ASSETS / "claude-agents"

# Engine files: (source in assets, destination relative to target repo root, chmod)
FILE_PLAN = [
    ("loop.config.json", ".orbit/loop.config.json", None),
    ("loop.py",          ".orbit/loop.py",          0o755),
    ("activity.py",      ".orbit/activity.py",      None),
    ("confidence.py",    ".orbit/confidence.py",    None),   # evidence-based delivery confidence
    ("lifecycle.py",     ".orbit/lifecycle.py",     None),   # mode detection + phase strip
    ("ralph_loop.sh",    "scripts/ralph_loop.sh",     0o755),
    ("orbit-status",     "scripts/orbit-status",      0o755),
    ("orbit-statusline.py", "scripts/orbit-statusline", 0o755),  # the one-line Claude Code status line

    ("checks/guard.py",  ".orbit/checks/guard.py",    0o755),  # placed, NOT wired (see skill Phase 6a)
    ("checks/route.py",  ".orbit/checks/route.py",    0o755),  # the UserPromptSubmit router (Phase 6a)
    ("checks/learn.py",  ".orbit/checks/learn.py",    0o755),  # the active-learning ledger helper
]

# Reusable skill-library playbooks copied into .orbit/skills/ (the provisioning step).
PLAYBOOKS_ALWAYS = ["clarify-and-challenge.md", "planning-and-decision-briefs.md",
                    "technical-review.md", "active-learning.md",
                    "product-discovery.md", "market-and-competitive-research.md",
                    "qa-validation.md", "goal-pipeline.md", "architecture-decisions.md",
                    "safety-rules.md"]
PLAYBOOKS_FRONTEND = ["design-methodology.md", "anti-ai-aesthetics.md", "design-styles.md"]

# QA visual-fidelity helpers (screenshot / pixel-diff / computed-token extraction). Frontend-only,
# since they act on a rendered UI. Helpers, not a bundled browser — they degrade gracefully when
# Playwright isn't installed. Placed executable into .orbit/qa/. (src under assets/qa/ -> dst rel.)
QA_FRONTEND = [("qa/snapshot.py", ".orbit/qa/snapshot.py"),
               ("qa/extract-tokens.py", ".orbit/qa/extract-tokens.py")]

# The design gate hook (Phase 2) — a coarse PreToolUse backstop that asks once per cycle when a
# UI production file is edited with no design-decision record. Frontend-only (it acts on a
# rendered UI); placed but NOT wired unless --install-hooks (see install_hooks below).
DESIGN_GATE_FRONTEND = [("checks/design-gate.py", ".orbit/checks/design-gate.py")]

# The UNIVERSAL spine — every project gets these (routing, planning, gates, reporting). Copied
# verbatim to .claude/agents/<role>.md and, frontmatter-stripped, to .orbit/roles/<role>.md.
ROLES_CORE = ["dispatcher", "orchestrator", "product-discovery", "market-researcher", "planner",
              "reviewer", "qa-engineer", "reporter", "safety-gate"]

# The PROJECT-SPECIFIC specialists — provisioned from the detected surfaces, NOT a fixed template.
# surface keyword -> (engineer filename, display name, what it owns). One engineer per surface;
# duplicates (web+frontend) collapse to one. Generated from builder.md with the name substituted.
SURFACE_ENGINEERS = {
    "web":      ("frontend-engineer", "Frontend Engineer", "the web UI"),
    "frontend": ("frontend-engineer", "Frontend Engineer", "the web UI"),
    "ui":       ("frontend-engineer", "Frontend Engineer", "the web UI"),
    "mobile":   ("mobile-developer",  "Mobile Developer",  "the mobile app"),
    "ios":      ("mobile-developer",  "Mobile Developer",  "the mobile app"),
    "android":  ("mobile-developer",  "Mobile Developer",  "the mobile app"),
    "api":      ("backend-engineer",  "Backend Engineer",  "the API / services"),
    "backend":  ("backend-engineer",  "Backend Engineer",  "the API / services"),
    "server":   ("backend-engineer",  "Backend Engineer",  "the API / services"),
    "data":     ("data-engineer",     "Data Engineer",     "data pipelines / ETL / ML"),
    "ml":       ("data-engineer",     "Data Engineer",     "data pipelines / ETL / ML"),
    "cli":      ("cli-engineer",      "CLI Engineer",      "the command-line tool"),
}
UI_SURFACES = {"web", "frontend", "ui", "mobile", "ios", "android"}  # → stand up the Designer

DIRS = [
    ".orbit", ".orbit/roles", ".orbit/skills",
    ".orbit/artifacts", ".orbit/checks", ".orbit/decisions", ".claude/agents", "scripts",
]

GUARD_CMD = 'python3 "$CLAUDE_PROJECT_DIR/.orbit/checks/guard.py"'
ROUTE_CMD = 'python3 "$CLAUDE_PROJECT_DIR/.orbit/checks/route.py"'
DESIGN_GATE_CMD = 'python3 "$CLAUDE_PROJECT_DIR/.orbit/checks/design-gate.py"'
# The telemetry collector is wired from the TRUSTED Orbit INSTALL (not copied into the repo), so
# editing the product repo can't alter it — unlike guard/route/design-gate, which are project-local
# BECAUSE they're meant to be customized per repo (the guard's RULES block especially). Resolved at
# hook-run time via the default install location; degrades to a no-op if Orbit lives elsewhere.
ORBIT_HOOK_CMD = 'python3 "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills/orbit/bin/orbit-hook"'
ORBIT_HOOK_EVENTS = ["SubagentStart", "SubagentStop", "TaskCreated", "TaskCompleted",
                     "PostToolUse", "PostToolUseFailure", "PostToolBatch", "Stop", "Notification"]
STATUSLINE_CMD = 'python3 "$CLAUDE_PROJECT_DIR/scripts/orbit-statusline"'


def _strip_frontmatter(text: str) -> str:
    """Remove a leading YAML frontmatter block (--- ... ---) for the portable role spec."""
    return re.sub(r"\A---\n.*?\n---\n+", "", text, count=1, flags=re.DOTALL)


def _place(src: Path, dst: Path, created, skipped, mode=None, transform=None):
    """Copy src→dst, never overwriting; optionally transform the text first."""
    rel = dst
    if not src.exists():
        skipped.append(f"{rel}  (MISSING SOURCE {src.name})")
        return
    if dst.exists():
        skipped.append(f"{rel}  (exists -- left untouched)")
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if transform:
        dst.write_text(transform(src.read_text()))
    else:
        shutil.copy2(src, dst)
    if mode:
        dst.chmod(mode)
    created.append(str(rel))


def _emit(dst: Path, text: str, created, skipped):
    """Write generated text to dst, never overwriting."""
    if dst.exists():
        skipped.append(f"{dst}  (exists -- left untouched)")
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(text)
    created.append(str(dst))


def _engineer_text(builder: str, name: str, display: str, scope: str) -> str:
    """Generate a per-surface engineer adapter from the generic builder.md template."""
    t = builder.replace("name: builder", f"name: {name}", 1)
    t = t.replace(
        "The executor. Use to produce the core output of the product",
        f"The {display} — owns {scope}. Use to produce/implement that surface",
    )
    t = t.replace("# Role: Builder / Executor (Claude Code subagent)",
                  f"# Role: {display} (Claude Code subagent)")
    t = t.replace("Mirrors `.orbit/roles/builder.md`", f"Mirrors `.orbit/roles/{name}.md`")
    return t


def resolve_engineers(surfaces):
    """surfaces (list of keywords) -> {filename: (display, scope)} + has_ui. One engineer per
    surface, duplicates collapsed. Empty/unknown → a single generic 'builder'."""
    eng = {}
    for s in surfaces:
        if s in SURFACE_ENGINEERS:
            fn, disp, scope = SURFACE_ENGINEERS[s]
            eng.setdefault(fn, (disp, scope))
    if not eng:
        eng["builder"] = ("Builder / Executor", "the product's output")
    has_ui = any(s in UI_SURFACES for s in surfaces)
    return eng, has_ui


def install_hooks(target: Path, has_ui: bool = False) -> None:
    """Wire Orbit's always-on hooks into .claude/settings.json (default-on + announced):

      • PreToolUse(Bash) → guard.py  — the binding safety wall (deny/ask on dangerous commands).
      • UserPromptSubmit → route.py  — the deterministic router: classifies every message
        (task → loop, question → direct) and injects the decision as the default lane.
      • PreToolUse(Edit|Write|MultiEdit) → design-gate.py — UI repos only (has_ui): a coarse
        backstop that asks once per cycle if a UI production file has no design-decision record.
        Never denies; fails open. Not a per-change heavy-redesign blocker — see its own docstring.
      • [SubagentStart/Stop, TaskCreated/Completed, PostToolUse(+Failure/Batch), Stop, Notification]
        → bin/orbit-hook — the telemetry collector, wired from the TRUSTED install path (not the
        repo), observe-only + fail-open: makes long runs visible in orbit-status / the status line.

    Backs up settings.json first, merges each hook idempotently (never double-adds), prints what it
    added + the one-line removal. Remove anytime with `orbit-uninstall`.

    If an existing settings.json is present but unparseable, ABORT rather than overwrite it — a
    corrupt-but-recoverable user file must never be clobbered by a fresh `{}`."""
    settings = target / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    backed_up = settings.exists()
    if backed_up:
        try:
            data = json.loads(settings.read_text())
        except (json.JSONDecodeError, ValueError) as e:
            print(f"⚠️  {settings} exists but is not valid JSON ({e}).")
            print("    Refusing to overwrite it. Fix or move that file, then re-run — "
                  "your hooks were NOT installed.")
            return
        settings.with_suffix(f".json.bak.{int(time.time())}").write_text(settings.read_text())

    hooks = data.setdefault("hooks", {})
    added = []

    pre = hooks.setdefault("PreToolUse", [])
    if not any("guard.py" in json.dumps(e) for e in pre):
        pre.append({"matcher": "Bash", "hooks": [{"type": "command", "command": GUARD_CMD}]})
        added.append("PreToolUse[matcher=Bash] → guard.py   (safety: deny/ask on dangerous commands)")

    ups = hooks.setdefault("UserPromptSubmit", [])
    if not any("route.py" in json.dumps(e) for e in ups):
        ups.append({"hooks": [{"type": "command", "command": ROUTE_CMD}]})
        added.append("UserPromptSubmit → route.py            (routing: classify task vs question)")

    if has_ui and not any("design-gate.py" in json.dumps(e) for e in pre):
        pre.append({"matcher": "Edit|Write|MultiEdit",
                    "hooks": [{"type": "command", "command": DESIGN_GATE_CMD}]})
        added.append("PreToolUse[matcher=Edit|Write|MultiEdit] → design-gate.py   "
                     "(design: ask once/cycle if a UI edit has no design record)")

    # Telemetry collector (observe-only, fail-open) across the run-lifecycle events → makes long
    # runs visible in orbit-status / the status line without the model having to remember to emit.
    hook_added = False
    for event in ORBIT_HOOK_EVENTS:
        lst = hooks.setdefault(event, [])
        if not any("orbit-hook" in json.dumps(e) for e in lst):
            lst.append({"hooks": [{"type": "command", "command": ORBIT_HOOK_CMD}]})
            hook_added = True
    if hook_added:
        added.append(f"[{', '.join(ORBIT_HOOK_EVENTS)}] → orbit-hook   "
                     "(telemetry: live run visibility; observe-only, fail-open)")

    # Status line — add ONLY if the user has none; NEVER overwrite an existing one.
    statusline_manual = False
    if "statusLine" not in data:
        data["statusLine"] = {"type": "command", "command": STATUSLINE_CMD, "refreshInterval": 2}
        added.append("statusLine → orbit-statusline   (live one-line run summary, 2s refresh)")
    else:
        statusline_manual = True

    if added:
        tmp = settings.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(settings)
        print("Installed Orbit's always-on hooks (announced, not silent):")
        for a in added:
            print("  + .claude/settings.json  →  hooks." + a)
        if backed_up:
            print("  (your previous settings.json was backed up alongside it)")
    else:
        print("Orbit hooks already wired in .claude/settings.json — left as-is.")
    if statusline_manual:
        print("  Note: you already have a statusLine — left untouched. To use Orbit's, set")
        print(f"        .claude/settings.json statusLine.command to: {STATUSLINE_CMD}")
    print("  Remove anytime:  orbit-uninstall   (or delete those hook blocks)")


def main():
    ap = argparse.ArgumentParser(description="Scaffold the orbit skeleton")
    ap.add_argument("--target", default=".", type=Path, help="target repo root")
    ap.add_argument("--surfaces", default="",
                    help="comma-separated technical surfaces detected from the repo "
                         "(web,mobile,api,backend,data,cli) — provisions one engineer per surface "
                         "+ the Designer if any UI surface. Empty → a single generic builder.")
    ap.add_argument("--frontend", action="store_true",
                    help="back-compat alias: implies a web surface (Designer + design playbooks)")
    ap.add_argument("--install-hooks", action="store_true",
                    help="also wire the always-on safety hook into .claude/settings.json")
    args = ap.parse_args()
    target = args.target.resolve()

    if not target.is_dir():
        raise SystemExit(f"target is not a directory: {target}")

    # resolve the project's surfaces → the specialist roster (engineers + whether a Designer)
    surfaces = [s.strip().lower() for s in args.surfaces.split(",") if s.strip()]
    if args.frontend and not any(s in UI_SURFACES for s in surfaces):
        surfaces.append("web")
    engineers, has_ui = resolve_engineers(surfaces)

    created, skipped, warnings = [], [], []

    for d in DIRS:
        (target / d).mkdir(parents=True, exist_ok=True)

    # 0. migrate known-old shipped hooks in an existing repo (before the never-overwrite copy below)
    migrate_hooks(target, created, warnings)

    # 1. engine files
    for src_rel, dst_rel, mode in FILE_PLAN:
        _place(ASSETS / src_rel, target / dst_rel, created, skipped, mode)

    # 2. working-state file (from the reference template)
    _place(REFERENCES / "state-template.md", target / ".orbit/STATE.md", created, skipped)

    # 3. skill-library playbooks -> .orbit/skills/ (design playbooks only when there's a UI surface)
    playbooks = PLAYBOOKS_ALWAYS + (PLAYBOOKS_FRONTEND if has_ui else [])
    for pb in playbooks:
        _place(PLAYBOOKS / pb, target / ".orbit/skills" / pb, created, skipped)

    # 3b. the 67-style design catalog (UI surfaces only) -> .orbit/skills/design-styles/
    styles_src = PLAYBOOKS / "design-styles"
    if has_ui and styles_src.is_dir():
        styles_dst = target / ".orbit/skills/design-styles"
        if styles_dst.exists():
            skipped.append(".orbit/skills/design-styles/  (exists -- left untouched)")
        else:
            shutil.copytree(styles_src, styles_dst)
            created.append(f".orbit/skills/design-styles/  ({len(list(styles_dst.glob('*.md')))} styles)")

    # 3c. QA visual-fidelity helpers (UI surfaces only) -> .orbit/qa/
    if has_ui:
        (target / ".orbit/qa").mkdir(parents=True, exist_ok=True)
        for src_rel, dst_rel in QA_FRONTEND:
            _place(ASSETS / src_rel, target / dst_rel, created, skipped, 0o755)

    # 3d. the design gate hook (UI surfaces only) -> .orbit/checks/design-gate.py
    #     placed here always on has_ui repos; WIRED into settings.json only via --install-hooks.
    if has_ui:
        for src_rel, dst_rel in DESIGN_GATE_FRONTEND:
            _place(ASSETS / src_rel, target / dst_rel, created, skipped, 0o755)

    # 4a. the universal spine -> .claude/agents/ (verbatim) + .orbit/roles/ (frontmatter-stripped)
    for role in ROLES_CORE:
        src = AGENTS / f"{role}.md"
        _place(src, target / ".claude/agents" / f"{role}.md", created, skipped)
        _place(src, target / ".orbit/roles" / f"{role}.md", created, skipped, transform=_strip_frontmatter)

    # 4b. the Designer — only if the project has a UI surface
    if has_ui:
        src = AGENTS / "designer.md"
        _place(src, target / ".claude/agents/designer.md", created, skipped)
        _place(src, target / ".orbit/roles/designer.md", created, skipped, transform=_strip_frontmatter)

    # 4c. the specialists — ONE ENGINEER PER DETECTED SURFACE (generated from builder.md)
    builder_text = (AGENTS / "builder.md").read_text()
    for fn, (disp, scope) in engineers.items():
        if fn == "builder":                       # generic fallback (no surfaces detected)
            _place(AGENTS / "builder.md", target / ".claude/agents/builder.md", created, skipped)
            _place(AGENTS / "builder.md", target / ".orbit/roles/builder.md", created, skipped,
                   transform=_strip_frontmatter)
        else:
            adapter = _engineer_text(builder_text, fn, disp, scope)
            _emit(target / ".claude/agents" / f"{fn}.md", adapter, created, skipped)
            _emit(target / ".orbit/roles" / f"{fn}.md", _strip_frontmatter(adapter), created, skipped)

    _team = ", ".join(sorted(engineers.keys())) + (" + designer" if has_ui else "")
    print(f"Scaffolded orbit skeleton into: {target}")
    print(f"Specialists for this project (from surfaces {surfaces or '[none → generic builder]'}): {_team}")
    print("\nCreated:")
    for c in created or ["(nothing new)"]:
        print("  +", c)
    if skipped:
        print("\nSkipped (already present or missing source):")
        for s in skipped:
            print("  -", s)
    if warnings:
        print("\n⚠️  ACTION NEEDED:")
        for w in warnings:
            print("  ! ", w)

    print(
        "\nThe skeleton is down. The ONLY thing left to author by hand is the project-specific part:\n"
        "  * CLAUDE.md  -> from references/claude-md-template.md: fill the project name, what it is,\n"
        "                  §3 success criteria, §8 stop conditions, and §10 routing. (This is the one\n"
        "                  file the model writes — everything above was deterministic.)\n"
        "  * .orbit/skills/<domain>.md  -> the product's core domain how-to (one skill).\n"
        "  * the engineers are already named per detected surface; add a specialist only if needed.\n"
        "  * wire loop.py dispatch() to your orchestrator; tune loop.config.json thresholds."
    )
    if args.install_hooks:
        print()
        install_hooks(target, has_ui)
    else:
        print(
            "\nSafety guard: .orbit/checks/guard.py is PLACED but NOT wired (re-run with\n"
            "--install-hooks to wire it, or let the skill do it by default in Phase 6a)."
        )
    print(
        "\nTo undo everything later: run `orbit-uninstall` from this repo — or its full path\n"
        "`~/.claude/skills/orbit/bin/orbit-uninstall` if it isn't on your PATH — (lists, asks, then\n"
        "removes .orbit/, scripts/ralph_loop.sh, scripts/orbit-status, and any Orbit hooks;\n"
        "leaves your CLAUDE.md alone)."
    )


if __name__ == "__main__":
    main()
