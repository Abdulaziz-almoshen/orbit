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
import calendar
import hashlib
import json
import os
import re
import shutil
import time
from pathlib import Path

SCHEMA_VERSION = 3                         # bumps if setup.json / manifest shape changes
MANIFEST_REL = ".orbit/.scaffold-manifest.json"   # {rel: sha256} of managed files WE placed

# The engine/check files the scaffolder MANAGES and can carry forward on a re-run. `marker` is a
# version-STABLE substring identifying the file as ours (so we don't touch an unrelated file at
# that path). We auto-replace a managed check ONLY when it is byte-identical to what we last placed
# (the manifest) OR to a known-old shipped version — i.e. the user has NOT customized it. A
# customized file (or unknown provenance) gets a warning + manual instructions, never an overwrite.
MANAGED_CHECKS = {
    ".orbit/loop.py":                   ("loop.py",                  b"Reference self-prompting loop runner"),
    ".orbit/checks/guard.py":           ("checks/guard.py",           b"Orbit safety guard"),
    ".orbit/checks/route.py":           ("checks/route.py",           b"UserPromptSubmit hook"),
    ".orbit/checks/learn.py":           ("checks/learn.py",           b"active-learning"),
    ".orbit/checks/orbit-stop-check.py":("checks/orbit-stop-check.py", b"observability backstop"),
    "scripts/orbit-dashboard":          ("orbit-dashboard",            b"orbit-dashboard"),
}
# Known-old shipped hashes for repos scaffolded BEFORE the manifest existed (no manifest to compare).
_LEGACY_OLD = {
    ".orbit/loop.py": {
        "2c5b87a05a617fea38a0bacfdaa8cc3881850f8f1cc0551106dec4825a230559",  # 0.40.0
    },
    ".orbit/checks/guard.py": {
        "0c5eb314a1dc64ad408adeb0d2170644f9bc48eeb343b562fbe6bf17fb098013",  # <0.23.0 (dead output shape)
        "3c5f77344b6857059593dc28e612fd9cae07948401adf6b447ae9df3270abc9c",  # 0.23.0 (narrow + bypassable)
    },
    ".orbit/checks/route.py": {
        "6e821feb7f8b2c400d1f1254a0f5fef2d225ab8858af5bde0c226987f62f8ec8",
        "3cdb8b75d49da422b8b09504e3f612f6e6b3d539d41ee35923aa98ef1c21c77b",
        "39040718046c1e57aede2eab41291c874da37392507693205f80ec880cae1584",
        "92c14909470a56f2405900cdc1a1e1a414bd96326682eecacb60f088ddca16fd",
    },
    "scripts/orbit-dashboard": {
        "93fb9084f4037b2db8a47653529b4ae64629889f5679f1f6d68af162d576457c",  # 0.42.0
        "4ed87c61f0aba95ecf39ce4ee9dd36afb6aa3d50cb4c82b6ed408851f549f9e3",  # 3344f4a scene
    },
}


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# Repo-policy content Orbit never ships in a stock check. Its presence is a strong "this file was
# customized" signal that OVERRIDES any manifest vouch — a poisoned pre-0.28.1 manifest (which recorded a
# CUSTOMIZED hash as if we placed it) can't launder such a file back to "managed/safe-to-upgrade".
_POLICY_MARKERS = (b"REQUIRE_DEPLOY_APPROVAL", b"STANDING DEPLOY AUTHORITY", b"DEPLOY_APPROVAL",
                   b"STANDING_DEPLOY_AUTHORITY")


def _has_policy_markers(content: bytes) -> bool:
    return any(m in content for m in _POLICY_MARKERS)


def _read_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def _classify_managed(rel: str, content: bytes, manifest: dict):
    """Classify a managed check file that EXISTS at `rel` with bytes `content`. The single source of
    truth for 'is this safe to auto-upgrade?' — used by both migrate_hooks (the full-scaffold path)
    and the --plan-refresh / --apply-safe-refresh modes. Returns (state, new_bytes):
      • foreign    — not our hook of this kind (marker absent) → never touch; new_bytes is None
      • current    — already byte-identical to the shipped version → nothing to do
      • upgrade     — unmodified since WE placed it (manifest/legacy match) but shipped moved → safe swap
      • customized  — an Orbit hook the user changed (or unknown provenance) → hands off; suggest a diff
    """
    src_rel, marker = MANAGED_CHECKS[rel]
    if marker not in content:
        return ("foreign", None)                            # not an Orbit hook of this kind — leave it
    new = (ASSETS / src_rel).read_bytes()
    cur = _sha(content)
    if cur == _sha(new):
        return ("current", new)                             # already the current shipped version

    # It differs from the current shipped bytes → "unmodified Orbit code (safe to swap)" or "the user
    # customized it (hands off)"? Two hard rules protect the safety wall from the manifest-laundering bug:
    #   (a) ANY repo-policy marker ⇒ customized, full stop (a poisoned manifest can't override content).
    #   (b) guard.py is the safety wall: NEVER trust a manifest vouch for it (a pre-0.28.1 scaffold could
    #       have recorded a customized guard's hash). It upgrades ONLY if its bytes match a hash we KNOW
    #       we shipped (_LEGACY_OLD) — a hash we can't have laundered. Other hooks may trust the manifest.
    if _has_policy_markers(content):
        return ("customized", new)
    known_shipped = cur in _LEGACY_OLD.get(rel, set())
    if rel.endswith("checks/guard.py"):
        return ("upgrade", new) if known_shipped else ("customized", new)
    manifest_vouch = rel in manifest and cur == manifest[rel]
    return (("upgrade" if (known_shipped or manifest_vouch) else "customized"), new)


def repair_manifest(target: Path) -> list:
    """Remove POISONED manifest entries. The manifest records the SHIPPED bytes we placed, so a re-run
    can tell 'unmodified since we placed it' from 'the user customized it'. A pre-0.28.1 scaffold could
    record a CUSTOMIZED check's own hash as if we placed it (manifest laundering), which would let a
    later 'safe' refresh clobber it. An entry is poisoned when it vouches for the file's CURRENT bytes
    but those bytes aren't a version we shipped (current or known-old), or the file carries repo-policy
    markers. Dropping the entry makes the file classify (correctly) as 'customized' thereafter. Returns
    the repaired rels; writes only when something changed."""
    p = target / MANIFEST_REL
    manifest = _read_json(p)
    if not isinstance(manifest, dict) or not manifest:
        return []
    repaired = []
    for rel in list(manifest):
        if rel not in MANAGED_CHECKS:
            continue
        f = target / rel
        if not f.exists():
            continue
        content = f.read_bytes()
        cur = _sha(content)
        if manifest.get(rel) != cur:
            continue                                        # manifest already differs from the file → not this bug
        # Poisoned = the manifest vouches for content carrying REPO-POLICY markers (Orbit never ships those,
        # so we can't have placed it). NOTE: 'unknown hash' alone is NOT poison — a legitimately old,
        # UNMODIFIED check has a non-current hash the manifest rightly vouches for (that's how it upgrades).
        if _has_policy_markers(content):
            del manifest[rel]
            repaired.append(rel)
    if repaired:
        p.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return repaired


def migrate_hooks(target: Path, created, warnings):
    """Carry existing repos forward to the current shipped check hooks (security/correctness fixes).
    Auto-replaces a managed check ONLY when it is UNMODIFIED — a known-old shipped version (or, for
    non-guard hooks, the manifest vouches unmodified-since-placed). A locally-modified hook (e.g. a
    guard with custom §8 rules) is warned about and NEVER overwritten; an already-current hook is left
    untouched. Repairs a poisoned (laundered) manifest FIRST, so a customized guard can't be clobbered."""
    for rel in repair_manifest(target):
        created.append(f"{rel}  (manifest repaired — a CUSTOMIZED check had been mis-recorded as "
                       f"Orbit-managed; it will NOT be auto-upgraded)")
    manifest = _read_json(target / MANIFEST_REL)
    for rel, (src_rel, marker) in MANAGED_CHECKS.items():
        dst = target / rel
        if not dst.exists():
            continue                                        # fresh file — normal _place copies the new one
        content = dst.read_bytes()
        state, new = _classify_managed(rel, content, manifest)
        # HARD safety net for the wall: never overwrite a guard that carries repo policy, whatever else says.
        if rel.endswith("checks/guard.py") and _has_policy_markers(content):
            state = "customized"
        if state in ("foreign", "current"):
            continue
        if state == "upgrade":                              # ours, unchanged by the user → carry forward
            bak = dst.with_name(dst.name + f".bak.{int(time.time())}")
            bak.write_bytes(content)
            dst.write_bytes(new)
            dst.chmod(0o755)
            created.append(f"{rel}  (⚠ UPDATED to the current shipped version — security/correctness "
                           f"fixes; old version → {bak.name})")
        else:                                               # customized or unknown → hands off
            warnings.append(
                f"{rel} is an Orbit hook that was locally modified — NOT auto-replaced (your custom "
                f"rules are preserved). To take the newer fixes, diff it against {ASSETS / src_rel} "
                f"and port your changes.")

SKILL_ROOT = Path(__file__).resolve().parent.parent
ASSETS = SKILL_ROOT / "assets"
REFERENCES = SKILL_ROOT / "references"
PLAYBOOKS = REFERENCES / "playbooks"
AGENTS = ASSETS / "claude-agents"

# Engine files: (source in assets, destination relative to target repo root, chmod)
FILE_PLAN = [
    ("loop.config.json", ".orbit/loop.config.json", None),
    ("loop.py",          ".orbit/loop.py",          0o755),
    ("counterfactual.py", ".orbit/counterfactual.py", 0o755),  # bounded pre-build falsification gate
    ("repair.py",        ".orbit/repair.py",        0o755),  # bounded post-review repair packets
    ("activity.py",      ".orbit/activity.py",      None),
    ("confidence.py",    ".orbit/confidence.py",    None),   # evidence-based delivery confidence
    ("lifecycle.py",     ".orbit/lifecycle.py",     None),   # mode detection + phase strip
    ("ralph_loop.sh",    "scripts/ralph_loop.sh",     0o755),
    ("orbit-lock",       "scripts/orbit-lock",        0o755),   # thin wrapper → trusted bin/orbit-lock
    ("orbit-worktree",   "scripts/orbit-worktree",    0o755),   # isolated worker worktree manager
    ("orbit-independent-qa", "scripts/orbit-independent-qa", 0o755),  # trusted second-provider gate
    ("orbit-qa-hook",   "scripts/orbit-qa-hook",      0o755),   # opt-in native Git post-commit QA trigger
    ("orbit-memory",     "scripts/orbit-memory",      0o755),   # review/promote/forget the learning ledger
    ("orbit-context",    "scripts/orbit-context",     0o755),   # context budget doctor + safe compactor
    ("orbit-status",     "scripts/orbit-status",      0o755),
    ("orbit-dashboard",  "scripts/orbit-dashboard",   0o755),   # read-only local web board over .orbit/
    ("orbit-pet",        "scripts/orbit-pet",         0o755),   # macOS always-on-top board reporter
    ("orbit-statusline.py", "scripts/orbit-statusline", 0o755),  # the one-line Claude Code status line

    ("security/rules.json", ".orbit/security/rules.json", None),  # declarative repo rules for the trusted guard
    ("checks/guard.py",  ".orbit/checks/guard.py",    0o755),  # built-in ruleset reference (the wired wall is the trusted orbit-guard)
    ("checks/route.py",  ".orbit/checks/route.py",    0o755),  # the UserPromptSubmit router (Phase 6a)
    ("checks/orbit-stop-check.py", ".orbit/checks/orbit-stop-check.py", 0o755),  # Stop: observability backstop
    ("checks/learn.py",  ".orbit/checks/learn.py",    0o755),  # the active-learning ledger helper
    ("qa/independent-review-request.schema.json", ".orbit/qa/independent-review-request.schema.json", None),
    ("qa/independent-review-result.schema.json", ".orbit/qa/independent-review-result.schema.json", None),
    ("qa/review-request.template.json", ".orbit/review-requests/TEMPLATE.json", None),
]

# Reusable skill-library playbooks copied into .orbit/skills/ (the provisioning step).
PLAYBOOKS_ALWAYS = ["clarify-and-challenge.md", "planning-and-decision-briefs.md",
                    "technical-review.md", "active-learning.md",
                    "product-discovery.md", "market-and-competitive-research.md",
                    "qa-validation.md", "goal-pipeline.md", "architecture-decisions.md",
                    "safety-rules.md", "deliverable-reports.md", "loop-tiers.md",
                    "counterfactual-regret.md", "iterative-repair.md"]
PLAYBOOKS_FRONTEND = ["design-methodology.md", "anti-ai-aesthetics.md", "design-styles.md",
                      "taste-preflight.md"]

# QA visual-fidelity helpers (screenshot / pixel-diff / computed-token extraction). Frontend-only,
# since they act on a rendered UI. Helpers, not a bundled browser — they degrade gracefully when
# Playwright isn't installed. Placed executable into .orbit/qa/. (src under assets/qa/ -> dst rel.)
QA_FRONTEND = [("qa/snapshot.py", ".orbit/qa/snapshot.py"),
               ("qa/extract-tokens.py", ".orbit/qa/extract-tokens.py"),
               ("qa/visual-gate.py", ".orbit/qa/visual-gate.py")]   # REQUIRED visual gate for HEAVY UI

# The design gate hook (Phase 2) — a coarse PreToolUse backstop that asks once per cycle when a
# UI production file is edited with no design-decision record. Frontend-only (it acts on a
# rendered UI); placed but NOT wired unless --install-hooks (see install_hooks below).
DESIGN_GATE_FRONTEND = [("checks/design-gate.py", ".orbit/checks/design-gate.py")]

# The UNIVERSAL spine — every project gets these (routing, planning, gates, reporting). Copied
# verbatim to .claude/agents/<role>.md and, frontmatter-stripped, to .orbit/roles/<role>.md.
ROLES_CORE = ["dispatcher", "orchestrator", "advisor", "product-discovery", "market-researcher", "planner",
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
    ".orbit/artifacts", ".orbit/checks", ".orbit/decisions", ".orbit/locks", ".orbit/security",
    ".orbit/qa", ".orbit/review-requests", ".orbit/reviews",
    ".claude/agents", "scripts",
]

GUARD_CMD = 'python3 "$CLAUDE_PROJECT_DIR/.orbit/checks/guard.py"'
ROUTE_CMD = 'python3 "$CLAUDE_PROJECT_DIR/.orbit/checks/route.py"'
DESIGN_GATE_CMD = 'python3 "$CLAUDE_PROJECT_DIR/.orbit/checks/design-gate.py"'
STOP_CHECK_CMD = 'python3 "$CLAUDE_PROJECT_DIR/.orbit/checks/orbit-stop-check.py"'
# The telemetry collector is wired from the TRUSTED Orbit INSTALL (not copied into the repo), so
# editing the product repo can't alter it — unlike guard/route/design-gate, which are project-local
# BECAUSE they're meant to be customized per repo (the guard's RULES block especially).
# A project-level hook can't see $CLAUDE_PLUGIN_ROOT (verified against the docs), so we RESOLVE the
# install at hook-run time across BOTH supported layouts: the skills-dir clone
# (${CLAUDE_CONFIG_DIR:-~/.claude}/skills/orbit) AND the marketplace plugin cache
# (~/.claude/plugins/cache/<marketplace>/orbit/<version>/, confirmed on disk). `exec` runs the first
# match with stdin intact; if Orbit isn't found anywhere the loop just exits 0 (no telemetry, never
# an error). The $CLAUDE_PLUGIN_ROOT candidate is a bonus for the day project hooks ever get it.
ORBIT_HOOK_CMD = (
    "sh -c 'for p in "
    '"${CLAUDE_PLUGIN_ROOT:-}/bin/orbit-hook" '
    '"${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills/orbit/bin/orbit-hook" '
    '"$HOME"/.claude/plugins/cache/*/orbit/*/bin/orbit-hook '
    '"${CLAUDE_CONFIG_DIR:-$HOME/.claude}"/plugins/cache/*/orbit/*/bin/orbit-hook; '
    "do [ -f \"$p\" ] && exec python3 \"$p\"; done; exit 0'"
)
# The TRUSTED safety wall (v0.31.0): runs the plugin's hardened built-in guard + the repo's DECLARATIVE
# .orbit/security/rules.json, from the trusted install — so a repo can't weaken its own wall by editing
# a Python file, and guard fixes upgrade with the plugin. Fails open. NEW scaffolds wire this instead of
# the project-local guard.py; existing repos that already wired guard.py keep it (never re-wired/clobbered).
ORBIT_GUARD_CMD = (
    "sh -c 'for p in "
    '"${CLAUDE_PLUGIN_ROOT:-}/bin/orbit-guard" '
    '"${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills/orbit/bin/orbit-guard" '
    '"$HOME"/.claude/plugins/cache/*/orbit/*/bin/orbit-guard '
    '"${CLAUDE_CONFIG_DIR:-$HOME/.claude}"/plugins/cache/*/orbit/*/bin/orbit-guard; '
    "do [ -f \"$p\" ] && exec python3 \"$p\"; done; exit 0'"
)
ORBIT_HOOK_EVENTS = ["SubagentStart", "SubagentStop", "TaskCreated", "TaskCompleted",
                     "PostToolUse", "PostToolUseFailure", "PostToolBatch", "Stop", "Notification"]
STATUSLINE_CMD = 'python3 "$CLAUDE_PROJECT_DIR/scripts/orbit-statusline"'
# The single-writer lock hook — trusted-install resolved (like orbit-hook), so a repo can't weaken its
# own lock. Fails OPEN on any error (a bug never bricks the repo); disable with ORBIT_LOCK_DISABLE=1.
ORBIT_LOCK_HOOK_CMD = (
    "sh -c 'for p in "
    '"${CLAUDE_PLUGIN_ROOT:-}/bin/orbit-lock-hook" '
    '"${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills/orbit/bin/orbit-lock-hook" '
    '"$HOME"/.claude/plugins/cache/*/orbit/*/bin/orbit-lock-hook '
    '"${CLAUDE_CONFIG_DIR:-$HOME/.claude}"/plugins/cache/*/orbit/*/bin/orbit-lock-hook; '
    "do [ -f \"$p\" ] && exec python3 \"$p\"; done; exit 0'"
)


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


def _orbit_version() -> str:
    try:
        return (SKILL_ROOT / "VERSION").read_text().strip() or "unknown"
    except Exception:
        return "unknown"


def _write_manifest(target: Path) -> None:
    """Record the sha256 of each managed check WE placed, so a later re-run can tell 'unmodified since
    we placed it' (safe to carry forward) from 'the user customized it' (hands off).

    CRITICAL: the manifest must only ever hold hashes of the SHIPPED bytes we actually wrote — never the
    hash of a customized file. If we recorded a customized guard's own hash, the very next re-run would
    see cur == manifest[rel], read it as 'unmodified since placed', and CLOBBER the customization (the
    'never clobber the customized guard' invariant, silently broken on the 2nd re-run). So: record the
    current hash only when the on-disk file IS the current shipped version; for a customized/old file,
    preserve the prior manifest entry (the shipped hash from when we placed it) and never overwrite it.
    Idempotent: same files → same content → no rewrite."""
    prev = _read_json(target / MANIFEST_REL)
    m = {}
    for rel, (src_rel, _marker) in MANAGED_CHECKS.items():
        p = target / rel
        if not p.exists():
            continue
        cur = _sha(p.read_bytes())
        if cur == _sha((ASSETS / src_rel).read_bytes()):
            m[rel] = cur                                    # we own the current shipped bytes → record them
        elif rel in prev:
            m[rel] = prev[rel]                              # customized/old → keep the hash of what WE placed
        # else: customized with no prior record → do NOT fabricate an entry (stays 'customized' forever)
    out = target / MANIFEST_REL
    text = json.dumps(m, indent=2, sort_keys=True) + "\n"
    try:
        if not out.exists() or out.read_text() != text:
            out.write_text(text)
    except Exception:
        pass


def _stamp_setup(target: Path, prev_version: str) -> None:
    """Stamp .orbit/setup.json with the CURRENT orbit_version + scaffold_schema — deterministically,
    so the version metadata stops lying after a refresh. Preserves the model-written keys (domain
    characterization + choices). `last_migrated_from`/`_at` are written ONLY when the version actually
    changed — never a fresh timestamp on a no-op re-run, so the 're-run changes nothing' contract holds."""
    p = target / ".orbit/setup.json"
    data = _read_json(p)
    cur = _orbit_version()
    data["orbit_version"] = cur
    data["scaffold_schema"] = SCHEMA_VERSION
    if prev_version and prev_version != cur:                 # a real migration → record it (with a time)
        data["last_migrated_from"] = prev_version
        data["last_migrated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    text = json.dumps(data, indent=2, sort_keys=True) + "\n"
    try:
        if not p.exists() or p.read_text() != text:
            p.write_text(text)
    except Exception:
        pass


def _merge_loop_config_defaults(target: Path, created: list, warnings: list) -> None:
    """Add newly shipped top-level defaults while preserving all project customizations."""
    dst = target / ".orbit/loop.config.json"
    src = ASSETS / "loop.config.json"
    if not dst.exists():
        return
    try:
        current = json.loads(dst.read_text())
        defaults = json.loads(src.read_text())
        changed = []
        for key in ("_independent_qa_help", "independent_qa"):
            if key not in current:
                current[key] = defaults[key]
                changed.append(key)
        qa = current.get("independent_qa", {})
        if isinstance(qa, dict) and "auto_review" not in qa:
            qa["auto_review"] = json.loads(json.dumps(defaults["independent_qa"]["auto_review"]))
            changed.append("independent_qa.auto_review")
        provider = qa.get("provider", {}) if isinstance(qa, dict) else {}
        shipped_codex_argv = defaults["independent_qa"]["provider"]["adapters"]["codex"]["argv"]
        if (isinstance(provider, dict) and provider.get("name") == "codex"
                and provider.get("argv") == shipped_codex_argv):
            replacement = json.loads(json.dumps(defaults["independent_qa"]["provider"]))
            replacement["mode"] = "codex"
            qa["provider"] = replacement
            qa.setdefault("arabic_content_qa", defaults["independent_qa"]["arabic_content_qa"])
            changed.append("independent_qa.provider(v0.41→v0.42)")
        paths = current.setdefault("paths", {})
        for key in ("independent_reviews", "independent_qa_runner"):
            if key not in paths:
                paths[key] = defaults["paths"][key]
                changed.append(f"paths.{key}")
        if changed:
            dst.write_text(json.dumps(current, indent=2) + "\n")
            created.append(f".orbit/loop.config.json  (added defaults: {', '.join(changed)}; existing values preserved)")
    except Exception as exc:
        warnings.append(f"Could not add independent-QA defaults to .orbit/loop.config.json: {exc}")


def _detect_arabic_surface(target: Path) -> bool:
    """Bounded signal for Arabic/RTL content; a project can override the resulting config."""
    candidates = [target / "CLAUDE.md", target / "docs/ARABIC_CONTENT_GUIDE.md"]
    candidates += list(target.glob("**/ar.json"))[:20] + list(target.glob("**/ar/*.json"))[:20]
    for path in candidates:
        try:
            if path.is_file() and re.search(r"[\u0600-\u06ff]", path.read_text(errors="ignore")[:200000]):
                return True
        except Exception:
            pass
    return False


def _apply_qa_preference(target: Path, created: list, warnings: list) -> None:
    """Preselect the install-time reviewer once, without granting project export consent.

    Provider availability/preference is a user-level convenience. Enabling review and exporting a
    private committed snapshot are project-level decisions, so a fresh scaffold must retain the
    shipped disabled/unapproved values. Never overwrite a project's later choice.
    """
    setup_path = target / ".orbit/setup.json"
    setup = _read_json(setup_path)
    if setup.get("qa_preference_applied"):
        return
    pref_root = Path(os.environ.get("ORBIT_HOME", str(Path.home() / ".orbit")))
    pref = _read_json(pref_root / "qa.json")
    if not pref.get("configured"):
        return
    config_path = target / ".orbit/loop.config.json"
    try:
        config = json.loads(config_path.read_text())
        qa = config.setdefault("independent_qa", {})
        selected = pref.get("provider", "claude")
        qa.setdefault("provider", {})["mode"] = "claude" if selected == "later" else selected
        qa["provider"]["fallback_requires_human_approval"] = True
        qa.setdefault("enabled", False)
        consent = qa.setdefault("external_export", {})
        consent.setdefault("approved", False)
        consent.setdefault("approved_by", "")
        consent.setdefault("approved_at", "")
        consent.setdefault("scope", "committed_snapshot_only")
        arabic = qa.setdefault("arabic_content_qa", {"mode": "auto_detect"})
        arabic["detected"] = _detect_arabic_surface(target)
        config_path.write_text(json.dumps(config, indent=2) + "\n")
        setup["qa_preference_applied"] = {"provider": selected, "at": pref.get("approved_at", "")}
        setup_path.parent.mkdir(parents=True, exist_ok=True)
        setup_path.write_text(json.dumps(setup, indent=2, sort_keys=True) + "\n")
        created.append(f".orbit/loop.config.json  (QA provider preference={selected}; project QA remains opt-in; "
                       f"Arabic detected={arabic['detected']})")
    except Exception as exc:
        warnings.append(f"Could not apply Orbit QA preference: {exc}")


def scaffold_drift(target: Path) -> dict:
    """READ-ONLY: how stale is THIS project's scaffold vs the current plugin? Separates plugin
    freshness (what /orbit-upgrade fixes) from project-scaffold freshness (what a re-run of /orbit
    fixes). Never writes. The staleness signal the /orbit preamble surfaces so a project doesn't
    silently run an old local scaffold while the plugin reports 'current'."""
    cur = _orbit_version()
    proj_v = _read_json(target / ".orbit/setup.json").get("orbit_version")
    has_ui = (target / ".claude/agents/designer.md").exists()
    expected = [dst for _, dst, _ in FILE_PLAN] + [f".orbit/skills/{pb}" for pb in PLAYBOOKS_ALWAYS]
    if has_ui:
        expected += [f".orbit/skills/{pb}" for pb in PLAYBOOKS_FRONTEND]
        expected += [d for _, d in DESIGN_GATE_FRONTEND]
    missing = [e for e in expected if not (target / e).exists()]
    settings = _read_json(target / ".claude/settings.json")
    wired = json.dumps(settings.get("hooks", {})) + json.dumps(settings.get("statusLine", {}))
    hook_drift = [name for name, tok in (
        ("router", "route.py"),
        ("observability Stop hook", "orbit-stop-check.py"), ("telemetry", "orbit-hook"),
        ("writer lock", "orbit-lock-hook"), ("status line", "orbit-statusline")) if tok not in wired]
    if "guard.py" not in wired and "orbit-guard" not in wired:   # either wall counts as wired
        hook_drift.insert(0, "safety guard")
    guard = target / ".orbit/checks/guard.py"
    guard_custom = False                                     # derive from the SAME classifier the refresh
    if guard.exists():                                       # plan uses, so drift + plan can never disagree
        _gstate, _ = _classify_managed(".orbit/checks/guard.py", guard.read_bytes(),
                                       _read_json(target / MANIFEST_REL))
        guard_custom = (_gstate == "customized")
    stale_prose = []
    for rel in (".orbit/STATE.md", "CLAUDE.md"):
        f = target / rel
        try:
            if f.exists() and proj_v and proj_v != cur and proj_v in f.read_text():
                stale_prose.append(rel)
        except Exception:
            pass
    return {
        "plugin_version": cur, "scaffold_version": proj_v,
        "metadata_stale_or_missing": (proj_v != cur),
        "missing_files": missing, "hook_drift": hook_drift,
        "role_template_drift_advisory": (proj_v != cur),     # roles/CLAUDE.md are never overwritten → may lag
        "stale_prose_advisory": stale_prose,
        "guard_customized_preserved": guard_custom,
        "legacy_guard_wired": ("guard.py" in wired and "orbit-guard" not in wired),
    }


def _print_drift(target: Path) -> None:
    d = scaffold_drift(target)
    if not (target / ".orbit").is_dir():
        print("Not an Orbit-scaffolded repo (no .orbit/). Run /orbit to set it up."); return
    fresh = (not d["metadata_stale_or_missing"] and not d["missing_files"] and not d["hook_drift"])
    print(f"Orbit scaffold drift — plugin v{d['plugin_version']} · this project's scaffold "
          f"v{d['scaffold_version'] or 'unknown'}")
    if d.get("legacy_guard_wired"):
        print("  • safety wall: this repo wires the legacy project-local guard.py (still hardened + "
              "carried forward). You can migrate to the TRUSTED orbit-guard (built-in + declarative\n"
              "    .orbit/security/rules.json, un-weakenable) — move your custom rules into rules.json, "
              "then swap the PreToolUse Bash hook to orbit-guard. Optional; the legacy guard is not clobbered.")
    if fresh:
        print("  ✓ up to date — scaffold matches the current plugin."); return
    print("  ✓ plugin is current (that's what /orbit-upgrade checks) — but this PROJECT's scaffold is behind:")
    if d["metadata_stale_or_missing"]:
        print(f"  • scaffold metadata old/missing (setup.json says {d['scaffold_version'] or 'nothing'})")
    if d["missing_files"]:
        print(f"  • {len(d['missing_files'])} file(s) the current plugin ships are missing: "
              f"{', '.join(x.split('/')[-1] for x in d['missing_files'][:6])}"
              + (" …" if len(d['missing_files']) > 6 else ""))
    if d["hook_drift"]:
        print(f"  • hook drift — not wired: {', '.join(d['hook_drift'])}")
    if d["role_template_drift_advisory"]:
        print("  • roles / CLAUDE.md may be stale (advisory — never auto-overwritten; review by hand)")
    if d["stale_prose_advisory"]:
        print(f"  • stale prose (advisory): {', '.join(d['stale_prose_advisory'])} still names an old version")
    if d["guard_customized_preserved"]:
        print("  • your guard.py is customized — it will be PRESERVED (warned, not overwritten) on a re-run")
    print("  Fix: re-run `/orbit` here — it adds the missing files/hooks and re-stamps the version,\n"
          "       hash-gating (never clobbering) your customized guard.")


def refresh_plan(target: Path) -> list:
    """READ-ONLY: what a SAFE refresh would do to managed Orbit files (checks plus dashboard),
    per file. Never writes. Each entry is {rel, state} with state ∈
    add | upgrade | customized | current | foreign — the exact classification --apply-safe-refresh acts
    on (it applies add + upgrade, leaves customized/foreign/current alone)."""
    manifest = _read_json(target / MANIFEST_REL)
    out = []
    for rel in MANAGED_CHECKS:
        dst = target / rel
        if not dst.exists():
            out.append({"rel": rel, "state": "add"})
            continue
        state, _ = _classify_managed(rel, dst.read_bytes(), manifest)
        out.append({"rel": rel, "state": state})
    return out


def _managed_diff(target: Path, rel: str, max_lines: int = 40) -> str:
    """A bounded unified diff of a CUSTOMIZED managed hook (the project's version → the current shipped
    one) so the user can hand-merge the newer fixes. Suggestion only — never applied."""
    import difflib
    src_rel, _ = MANAGED_CHECKS[rel]
    yours = (target / rel).read_text(errors="replace").splitlines(keepends=True)
    shipped = (ASSETS / src_rel).read_text(errors="replace").splitlines(keepends=True)
    diff = list(difflib.unified_diff(yours, shipped, fromfile=f"a/{rel} (yours)",
                                     tofile=f"b/{rel} (current shipped)", n=2))
    body = "".join(diff[:max_lines])
    if len(diff) > max_lines:
        body += f"      … ({len(diff) - max_lines} more diff lines — run `diff` yourself to see all)\n"
    return body


def _print_refresh_plan(target: Path) -> None:
    """READ-ONLY preview for `--plan-refresh`: what the safe managed-hook refresh would change, with a
    patch suggestion for any customized hook. Writes nothing."""
    if not (target / ".orbit").is_dir():
        print("Not an Orbit-scaffolded repo (no .orbit/). Run /orbit to set it up."); return
    plan = refresh_plan(target)
    by = {s: [p["rel"] for p in plan if p["state"] == s]
          for s in ("add", "upgrade", "customized", "current", "foreign")}
    print(f"Orbit safe-refresh plan (READ-ONLY) — managed checks/tools · plugin v{_orbit_version()}")
    if by["upgrade"]:
        print(f"  ⬆ would auto-upgrade (unmodified since placed → current; backup kept): {len(by['upgrade'])}")
        for rel in by["upgrade"]:
            print(f"      {rel}")
    if by["add"]:
        print(f"  + would add (managed hook missing): {len(by['add'])}")
        for rel in by["add"]:
            print(f"      {rel}")
    if by["current"]:
        print(f"  ✓ already current: {len(by['current'])}")
    if by["customized"]:
        print(f"  ⚠ customized — NOT auto-applied (your changes are preserved): {len(by['customized'])}")
        for rel in by["customized"]:
            print(f"      {rel} — diff (yours → current shipped):")
            print(_managed_diff(target, rel), end="")
    if by["upgrade"] or by["add"]:
        print("\n  Apply just the SAFE ones (never customized files):"
              "  python3 scaffold.py --apply-safe-refresh --target <repo>")
    else:
        print("\n  Nothing to auto-apply. ✓  (customized hooks, if any, are yours to hand-merge.)")


def _apply_safe_refresh(target: Path) -> None:
    """WRITE ONLY THE SAFE FILES for `--apply-safe-refresh`: add missing managed hooks + upgrade the
    ones unmodified since we placed them (backups kept). NEVER touches a customized hook — it's printed
    as a patch suggestion instead. Idempotent: a second run on a current project changes nothing. Does
    NOT re-stamp the version or add playbooks/roles — that's a full `/orbit` re-run's job (noted below)."""
    if not (target / ".orbit").is_dir():
        print("Not an Orbit-scaffolded repo (no .orbit/). Run /orbit to set it up."); return
    created, warnings = [], []
    for rel, (src_rel, _marker) in MANAGED_CHECKS.items():          # add missing managed hooks (ours, safe)
        dst = target / rel
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes((ASSETS / src_rel).read_bytes())
            dst.chmod(0o755)
            created.append(f"{rel}  (added — was missing)")
    migrate_hooks(target, created, warnings)                        # upgrade unmodified, warn on customized
    _write_manifest(target)                                         # record what we now have as 'ours'
    print(f"Orbit safe-refresh applied — managed checks/tools · plugin v{_orbit_version()}")
    for c in created or ["(nothing to add or upgrade — all managed hooks are current or customized)"]:
        print("  +", c)
    for w in warnings:
        print("  ! ", w)
    print("\n  Scope: this refreshes ONLY managed checks and the read-only dashboard.\n"
          "  For missing playbooks/roles and the version stamp, run `/orbit` here (it merges, never clobbers).")


def _active_writer_lock(target: Path) -> bool:
    """Return True when a writer may still be using this project.

    Automatic healing treats malformed locks as active and never breaks ownership implicitly.
    """
    p = target / ".orbit/locks/active-writer.json"
    if not p.exists():
        return False
    try:
        data = json.loads(p.read_text())
        heartbeat = data.get("heartbeat_at") or data.get("started_at")
        ttl = int(data.get("ttl_seconds") or 1800)
        parsed = time.strptime(heartbeat, "%Y-%m-%dT%H:%M:%SZ")
        age = time.time() - calendar.timegm(parsed)
        return age < ttl
    except Exception:
        return True


def _auto_heal(target: Path) -> str:
    """Perform the safe, non-interactive subset of a full scaffold refresh.

    This never edits settings, CLAUDE.md, roles, domain skills, or customized checks. It is safe to
    run from the update preamble because it only adds Orbit-owned missing files and stamps metadata.
    """
    if not (target / ".orbit").is_dir():
        return "not an Orbit repo"
    if _active_writer_lock(target):
        return "preserved (active writer lock)"

    created, skipped, warnings = [], [], []
    prev_version = _read_json(target / ".orbit/setup.json").get("orbit_version", "")
    has_ui = (target / ".claude/agents/designer.md").exists()
    for d in DIRS:
        (target / d).mkdir(parents=True, exist_ok=True)
    for src_rel, dst_rel, mode in FILE_PLAN:
        _place(ASSETS / src_rel, target / dst_rel, created, skipped, mode)
    _merge_loop_config_defaults(target, created, warnings)
    _apply_qa_preference(target, created, warnings)
    playbooks = PLAYBOOKS_ALWAYS + (PLAYBOOKS_FRONTEND if has_ui else [])
    for pb in playbooks:
        _place(PLAYBOOKS / pb, target / ".orbit/skills" / pb, created, skipped)
    if has_ui:
        for src_rel, dst_rel in QA_FRONTEND + DESIGN_GATE_FRONTEND:
            _place(ASSETS / src_rel, target / dst_rel, created, skipped, 0o755)

    migrate_hooks(target, created, warnings)
    _write_manifest(target)
    _stamp_setup(target, prev_version)
    parts = []
    if created:
        parts.append(f"repaired {len(created)} file(s)")
    if prev_version and prev_version != _orbit_version():
        parts.append(f"scaffold {prev_version}->{_orbit_version()}")
    if warnings:
        parts.append(f"preserved {len(warnings)} customized check(s)")
    return ", ".join(parts) if parts else "already healthy"


def install_hooks(target: Path, has_ui: bool = False) -> None:
    """Wire Orbit's always-on hooks into .claude/settings.json (default-on + announced):

      • PreToolUse(Bash) → orbit-guard  — the binding safety wall (deny/ask on dangerous commands),
        TRUSTED-install resolved = built-in hardened rules + the repo's declarative
        .orbit/security/rules.json. A repo that already wired the legacy project-local guard.py keeps it.
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
    # The safety wall. NEW repos wire the TRUSTED orbit-guard (built-in rules + declarative
    # .orbit/security/rules.json, resolved from the install so the repo can't weaken its own wall).
    # A repo that ALREADY wired the project-local guard.py keeps it — we never re-wire or clobber it
    # (its custom §8 rules are preserved; `orbit-doctor` suggests migrating to rules.json).
    _guard_wired = any(("guard.py" in json.dumps(e) or "orbit-guard" in json.dumps(e)) for e in pre)
    if not _guard_wired:
        pre.append({"matcher": "Bash", "hooks": [{"type": "command", "command": ORBIT_GUARD_CMD}]})
        added.append("PreToolUse[matcher=Bash] → orbit-guard   (TRUSTED safety wall: built-in rules + "
                     ".orbit/security/rules.json; a repo can't weaken its own wall)")

    ups = hooks.setdefault("UserPromptSubmit", [])
    if not any("route.py" in json.dumps(e) for e in ups):
        ups.append({"hooks": [{"type": "command", "command": ROUTE_CMD}]})
        added.append("UserPromptSubmit → route.py            (routing: classify task vs question)")

    if has_ui and not any("design-gate.py" in json.dumps(e) for e in pre):
        pre.append({"matcher": "Edit|Write|MultiEdit",
                    "hooks": [{"type": "command", "command": DESIGN_GATE_CMD}]})
        added.append("PreToolUse[matcher=Edit|Write|MultiEdit] → design-gate.py   "
                     "(design: ask once/cycle if a UI edit has no design record)")

    # Single-writer lock (v0.30.0): deny writes under a FOREIGN session's lock — many readers, one
    # writer. Two matchers (the edit tools + Bash), added together + idempotently. Trusted-install
    # resolved (a repo can't weaken its own lock) and FAIL-OPEN on any error (never bricks the repo).
    if not any("orbit-lock-hook" in json.dumps(e) for e in pre):
        pre.append({"matcher": "Edit|Write|MultiEdit",
                    "hooks": [{"type": "command", "command": ORBIT_LOCK_HOOK_CMD}]})
        pre.append({"matcher": "Bash",
                    "hooks": [{"type": "command", "command": ORBIT_LOCK_HOOK_CMD}]})
        added.append("PreToolUse[Edit|Write|MultiEdit + Bash] → orbit-lock-hook   "
                     "(single-writer lock: block writes under another session's lock)")

    # Stop → orbit-stop-check.py: the observability backstop. Fails loudly (blocks once) if a routed
    # task did real work but never made the board visible (no .orbit/tasks.json / set_team) — i.e. it
    # ran as a black box instead of Orbit's checklist. Conservative + fail-open (see the hook header).
    stop = hooks.setdefault("Stop", [])
    if not any("orbit-stop-check.py" in json.dumps(e) for e in stop):
        stop.append({"hooks": [{"type": "command", "command": STOP_CHECK_CMD}]})
        added.append("Stop → orbit-stop-check.py            "
                     "(observability: block once if a task ran without a visible checklist)")

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
    ap.add_argument("--check-drift", action="store_true",
                    help="READ-ONLY: report how stale this project's scaffold is vs the current plugin, then exit")
    ap.add_argument("--plan-refresh", action="store_true",
                    help="READ-ONLY: preview what a safe managed-hook refresh would change (with a patch "
                         "suggestion for any customized hook), then exit")
    ap.add_argument("--apply-safe-refresh", action="store_true",
                    help="WRITE ONLY SAFE FILES: add missing managed hooks + upgrade unmodified ones "
                         "(backups kept); never touches a customized hook. Then exit.")
    ap.add_argument("--auto-heal", action="store_true",
                    help="NON-INTERACTIVE safe refresh: add missing Orbit-owned files, refresh proven "
                         "unchanged checks, and stamp metadata; never edits settings or custom files")
    args = ap.parse_args()
    target = args.target.resolve()

    if args.check_drift:                                     # read-only staleness report — never writes
        _print_drift(target)
        return
    if args.plan_refresh:                                    # read-only refresh preview — never writes
        _print_refresh_plan(target)
        return
    if args.apply_safe_refresh:                              # writes ONLY the safe (unmodified/missing) hooks
        _apply_safe_refresh(target)
        return
    if args.auto_heal:
        print(f"Orbit auto-heal · plugin v{_orbit_version()} · {_auto_heal(target)}")
        return

    if not target.is_dir():
        raise SystemExit(f"target is not a directory: {target}")

    # resolve the project's surfaces → the specialist roster (engineers + whether a Designer)
    surfaces = [s.strip().lower() for s in args.surfaces.split(",") if s.strip()]
    if args.frontend and not any(s in UI_SURFACES for s in surfaces):
        surfaces.append("web")
    engineers, has_ui = resolve_engineers(surfaces)

    created, skipped, warnings = [], [], []
    prev_version = _read_json(target / ".orbit/setup.json").get("orbit_version", "")   # for the version stamp

    for d in DIRS:
        (target / d).mkdir(parents=True, exist_ok=True)
    _gitkeep = target / ".orbit/locks/.gitkeep"                     # keep the (otherwise-empty) lock dir in git
    if not _gitkeep.exists():
        _gitkeep.write_text("")

    # 0. migrate known-old shipped hooks in an existing repo (before the never-overwrite copy below)
    migrate_hooks(target, created, warnings)

    # 1. engine files
    for src_rel, dst_rel, mode in FILE_PLAN:
        _place(ASSETS / src_rel, target / dst_rel, created, skipped, mode)
    _merge_loop_config_defaults(target, created, warnings)
    _apply_qa_preference(target, created, warnings)

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

    # 5. record what we placed (for precise 'unmodified' migration) + stamp the version deterministically
    _write_manifest(target)
    _stamp_setup(target, prev_version)

    _team = ", ".join(sorted(engineers.keys())) + (" + designer" if has_ui else "")
    print(f"Scaffolded orbit skeleton into: {target}")
    _cur_v = _orbit_version()
    if prev_version and prev_version != _cur_v:
        print(f"Version: migrated this scaffold {prev_version} → {_cur_v} (setup.json re-stamped).")
    else:
        print(f"Version: scaffold stamped at orbit v{_cur_v} (setup.json).")
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
            "\nSafety guard: NOT wired yet (re-run with --install-hooks, or let the skill do it in\n"
            "Phase 6a). When wired it's the TRUSTED orbit-guard (built-in wall + your declarative\n"
            ".orbit/security/rules.json) — a repo can't weaken its own wall. Add repo rules in\n"
            "rules.json; .orbit/checks/guard.py is the built-in ruleset reference (editing it does\n"
            "nothing once the trusted runner is wired)."
        )
    print(
        "\nTo undo everything later: run `orbit-uninstall` from this repo — or its full path\n"
        "`~/.claude/skills/orbit/bin/orbit-uninstall` if it isn't on your PATH — (lists, asks, then\n"
        "removes .orbit/, scripts/ralph_loop.sh, scripts/orbit-status, and any Orbit hooks;\n"
        "leaves your CLAUDE.md alone)."
    )


if __name__ == "__main__":
    main()
