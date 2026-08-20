#!/usr/bin/env python3
"""orbit-statusline — a stable Claude Code run line plus a fixed QA handoff line.

Only state that changes the operator's next decision is shown: phase, progress, active owner, cost,
blocker, and QA gate. Context/cache/confidence detail belongs in the dashboard. The second line is a
fixed-position contract: Claude builds on the left; Codex reviews code and content on the right.

  🛰 BUILD · 5/9 · Builder · $0.42
     Claude ○  ──📦──▶  ● Codex QA · REVIEW
  🛰 ⚠ INPUT · BUILD · 5/9 · $0.42

Install: `.claude/settings.json` → {"statusLine": {"type":"command",
"command":"python3 \"$CLAUDE_PROJECT_DIR/scripts/orbit-statusline\"", "refreshInterval": 2}}.
Orbit wires this only if you don't already have a status line (never overwrites yours).
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def _get(d, *path, default=None):
    """Safe nested get: _get(data, 'context_window', 'used_percentage')."""
    cur = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def _find_orbit(start):
    """Nearest .orbit/ from `start` upward, so the status line still finds the repo-root scaffold
    when Claude is working in a subdir. None if none found."""
    try:
        cur = Path(start).resolve()
    except Exception:
        return None
    for p in [cur, *cur.parents]:
        if (p / ".orbit").is_dir():
            return p / ".orbit"
    return None


def _active_agent(agents: dict):
    """The agent working now (first with status active/blocked), or None."""
    if not isinstance(agents, dict):
        return None
    cands = [dict(v, role=k) for k, v in agents.items()
             if isinstance(v, dict) and v.get("status") in ("active", "blocked")]
    cands.sort(key=lambda x: (x.get("seq", 99), x.get("role", "")))
    return cands[0] if cands else None


def _read_json(path, default):
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, type(default)) else default
    except Exception:
        return default


def _record_session(orbit: Path, claude: dict) -> None:
    """Remember which Claude/model owns a session so external reporters can identify it.

    This is bounded, project-local telemetry. It never stores prompts or transcript contents.
    """
    sid = str(claude.get("session_id") or "").strip()
    if not orbit or not sid:
        return
    path = orbit / "sessions.json"
    sessions = _read_json(path, {})
    model = _get(claude, "model", "display_name") or _get(claude, "model", "id") or "Claude Code"
    terminal_program = str(os.environ.get("TERM_PROGRAM") or "")
    terminal_session = str(os.environ.get("TERM_SESSION_ID") or os.environ.get("ITERM_SESSION_ID") or "")
    terminal_bundles = {"Apple_Terminal": "com.apple.Terminal", "iTerm.app": "com.googlecode.iterm2",
                        "vscode": "com.microsoft.VSCode", "WarpTerminal": "dev.warp.Warp-Stable",
                        "ghostty": "com.mitchellh.ghostty", "WezTerm": "com.github.wez.wezterm"}
    sessions[sid] = {"session_id": sid, "agent": "Claude Code", "model": str(model),
                     "cwd": str(_get(claude, "workspace", "project_dir") or claude.get("cwd") or ""),
                     "terminal_program": terminal_program, "terminal_session": terminal_session,
                     "terminal_bundle": terminal_bundles.get(terminal_program, ""),
                     "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    ordered = sorted(sessions.items(), key=lambda x: x[1].get("updated_at", ""), reverse=True)[:12]
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(dict(ordered), indent=2) + "\n")
    os.replace(tmp, path)


def _git(root: Path, *args) -> str:
    try:
        p = subprocess.run(["git", "-C", str(root), *args], text=True, capture_output=True, timeout=.5)
        return p.stdout.strip() if p.returncode == 0 else ""
    except Exception:
        return ""


def _qa_state(orbit: Path) -> dict:
    """Small exact-commit QA view for the terminal reporter; authoritative state stays in Git."""
    if not orbit:
        return {}
    cfg = _read_json(orbit / "loop.config.json", {})
    qa = cfg.get("independent_qa") if isinstance(cfg.get("independent_qa"), dict) else {}
    if qa.get("enabled") is not True:
        return {}
    pcfg = qa.get("provider") if isinstance(qa.get("provider"), dict) else {}
    mode = str(pcfg.get("mode") or pcfg.get("name") or "claude")
    head = _git(orbit.parent, "rev-parse", "HEAD")
    common = _git(orbit.parent, "rev-parse", "--git-common-dir")
    control = {}
    try:
        cp = Path(common)
        if common and not cp.is_absolute():
            cp = (orbit.parent / cp).resolve()
        control = _read_json(cp / "orbit-independent-qa" / "current.json", {}) if common else {}
    except Exception:
        control = {}
    exact = bool(head and control.get("target_commit") == head)
    if not exact:
        names = ["codex", "claude"] if mode == "both" else [mode]
        return {"status": "awaiting_review", "provider": mode, "head": head,
                "providers": {name: {"status": "queued"} for name in names}}
    return {"status": control.get("status") or "awaiting_review", "provider": mode, "head": head,
            "providers": control.get("providers") if isinstance(control.get("providers"), dict) else {},
            "reason": control.get("reason", ""), "verdict": control.get("verdict")}


def _codex_status(qa: dict) -> str:
    """Return Codex's state when available; the aggregate state is a safe fallback."""
    providers = (qa or {}).get("providers")
    codex = providers.get("codex") if isinstance(providers, dict) else None
    if isinstance(codex, dict) and codex.get("status"):
        return str(codex["status"])
    return str((qa or {}).get("status") or "")


def build_handoff_line(qa: dict) -> str:
    """Fixed Claude/Codex positions. State may change; the box never travels or animates."""
    status = _codex_status(qa)
    if status in ("", "off", "awaiting_project_approval"):
        return ""
    if status == "changes_required":
        return "   Claude ●  ◀─💬────  ● Codex QA · FEEDBACK"
    if status == "pass":
        return "   Claude ○  ───✓───  ● Codex QA · PASS"
    if status in ("blocked", "error"):
        return "   Claude ●  ───⛔───  ● Codex QA · BLOCKED"
    if status == "awaiting_deploy_approval":
        return "   Claude ○  ───✓───  ● Codex QA · DEPLOY GATE"
    if status == "reviewing":
        return "   Claude ○  ──📦──▶  ● Codex QA · REVIEW"
    return "   Claude ●  ──📦──▶  ○ Codex QA · QUEUED"


def build_line(claude: dict, run: dict, agents: dict = None, qa: dict = None) -> str:
    seg = []
    blocked = run.get("blocked_question")
    if blocked:
        seg.append("⚠ INPUT")

    phase = str(run.get("phase") or run.get("mode") or "").strip().upper()
    if phase:
        seg.append(phase[:10])

    total = run.get("tasks_total")
    if isinstance(total, int) and total > 0:
        seg.append(f"{run.get('tasks_done', 0)}/{total}")

    ag = _active_agent(agents or {})
    if ag and not blocked:
        seg.append(str(ag.get("display") or ag.get("role") or "agent")[:18])
    elif run.get("active_role") and not blocked:
        seg.append(str(run["active_role"])[:18])

    cost = _get(claude, "cost", "total_cost_usd")
    if isinstance(cost, (int, float)):
        seg.append(f"${cost:.2f}")

    return "🛰 " + " · ".join(seg) if seg else ""


def main():
    try:
        claude = json.load(sys.stdin)
        if not isinstance(claude, dict):
            claude = {}
    except Exception:
        claude = {}
    # Prefer the ORIGINAL project dir (repo root) over cwd, then walk up — so a subdir still finds it.
    orbit = None
    for cand in (_get(claude, "workspace", "project_dir"), claude.get("cwd"),
                 _get(claude, "workspace", "current_dir"), os.environ.get("CLAUDE_PROJECT_DIR"), "."):
        if cand:
            orbit = _find_orbit(cand)
            if orbit:
                break
    try:
        run = json.loads((orbit / "run.json").read_text()) if orbit else {}
        if not isinstance(run, dict):
            run = {}
    except Exception:
        run = {}
    try:
        agents = json.loads((orbit / "agents.json").read_text()) if orbit else {}
        if not isinstance(agents, dict):
            agents = {}
    except Exception:
        agents = {}
    try:
        _record_session(orbit, claude)
    except Exception:
        pass
    try:
        qa = _qa_state(orbit)
        print(build_line(claude, run, agents, qa))
        handoff = build_handoff_line(qa)
        if handoff:
            print(handoff)
    except Exception:
        print("")                                           # never crash the status line


if __name__ == "__main__":
    main()
