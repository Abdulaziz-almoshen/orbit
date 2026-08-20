#!/usr/bin/env python3
"""orbit-statusline — a persistent live task board plus a truthful Claude → Codex QA handoff.

The first line always answers: what task is active, which LLM owns it, how long it has been working,
what is next, and whether work is stalled. The second line keeps Claude and Codex in fixed positions;
the parcel crosses once when real control-plane state hands work between them.

  🛰 BUILD · 5/9 · U6 Implement checkout · Builder 42s · $0.42
     Claude ○  ────📦──  ● Codex QA · 5.6 Sol · REVIEW
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
             if k != "human" and isinstance(v, dict) and v.get("status") in ("active", "blocked")]
    cands.sort(key=lambda x: (x.get("seq", 99), x.get("role", "")))
    return cands[0] if cands else None


def _age_seconds(iso_ts):
    try:
        stamp = time.strptime(str(iso_ts), "%Y-%m-%dT%H:%M:%SZ")
        return max(0, int(time.time() - time.mktime(stamp) + time.timezone))
    except Exception:
        return None


def _dur(seconds):
    if seconds is None:
        return ""
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m{seconds % 60}s"
    return f"{seconds // 3600}h{(seconds % 3600) // 60}m"


def _next_task(tasks):
    if not isinstance(tasks, list):
        return {}
    for status in ("active", "in_progress", "blocked", "pending", "queued"):
        for task in tasks:
            if isinstance(task, dict) and str(task.get("status") or "").lower() == status:
                return task
    return {}


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
    adapters = pcfg.get("adapters") if isinstance(pcfg.get("adapters"), dict) else {}
    routed = isinstance(qa.get("codex_model_router"), dict) and qa["codex_model_router"].get("enabled") is True

    def providers_with_models(states):
        enriched = {}
        for name, value in states.items():
            item = dict(value) if isinstance(value, dict) else {"status": "queued"}
            adapter = adapters.get(name) if isinstance(adapters.get(name), dict) else {}
            if adapter.get("model") and not item.get("model") and not (routed and name == "codex"):
                item["model"] = adapter["model"]
            enriched[name] = item
        return enriched

    if not exact:
        names = ["codex", "claude"] if mode == "both" else [mode]
        return {"status": "awaiting_review", "provider": mode, "head": head,
                "providers": providers_with_models({name: {"status": "queued"} for name in names})}
    states = control.get("providers") if isinstance(control.get("providers"), dict) else {}
    try:
        changed_at = (cp / "orbit-independent-qa" / "current.json").stat().st_mtime
    except Exception:
        changed_at = 0
    return {"status": control.get("status") or "awaiting_review", "provider": mode, "head": head,
            "providers": providers_with_models(states), "_changed_at": changed_at,
            "reason": control.get("reason", ""), "verdict": control.get("verdict")}


def _codex_view(qa: dict) -> tuple[str, str]:
    """Return the real Codex provider state/model; no Codex configuration means no fake handoff."""
    mode = str((qa or {}).get("provider") or "")
    if mode not in ("codex", "both"):
        return "", ""
    providers = (qa or {}).get("providers")
    codex = providers.get("codex") if isinstance(providers, dict) else None
    if not isinstance(codex, dict):
        return str((qa or {}).get("status") or ""), ""
    return str(codex.get("status") or (qa or {}).get("status") or ""), str(codex.get("model") or "")


def _model_label(model: str) -> str:
    return {"gpt-5.6-sol": "5.6 Sol", "gpt-5.6-terra": "5.6 Terra",
            "gpt-5.6-luna": "5.6 Luna"}.get(model, model[:18])


def _parcel_track(status: str, elapsed: float, width: int = 7) -> str:
    """Animate only a real state transition, then settle. No decorative back-and-forth loop."""
    last = width - 1
    step_seconds = .7
    if status == "reviewing":
        pos = min(last, int(max(0, elapsed) / step_seconds))
    elif status == "changes_required":
        pos = max(0, last - int(max(0, elapsed) / step_seconds))
    elif status in ("awaiting_review", "queued"):
        pos = 0
    else:
        pos = last
    return "─" * pos + "📦" + "─" * (last - pos)


def build_handoff_line(qa: dict, now: float = None) -> str:
    """Claude stays left and Codex stays right; the parcel follows actual QA ownership."""
    status, model = _codex_view(qa)
    if status in ("", "off", "awaiting_project_approval"):
        return ""
    now = time.time() if now is None else now
    changed_at = float((qa or {}).get("_changed_at") or now)
    track = _parcel_track(status, now - changed_at)
    model_bit = f" · {_model_label(model)}" if model else ""
    if status == "changes_required":
        return f"   Claude ●  {track}  ● Codex QA{model_bit} · FEEDBACK ←"
    if status == "pass":
        return f"   Claude ○  {track}  ● Codex QA{model_bit} · PASS"
    if status in ("blocked", "error"):
        return f"   Claude ●  {track}  ● Codex QA{model_bit} · BLOCKED"
    if status == "awaiting_deploy_approval":
        return f"   Claude ○  {track}  ● Codex QA{model_bit} · DEPLOY GATE"
    if status == "reviewing":
        return f"   Claude ○  {track}  ● Codex QA{model_bit} · REVIEW →"
    return f"   Claude ●  {track}  ○ Codex QA{model_bit} · QUEUED"


def build_line(claude: dict, run: dict, agents: dict = None, qa: dict = None,
               tasks: list = None) -> str:
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
    task = str(run.get("active_task") or (ag or {}).get("task") or "").strip()
    fallback = _next_task(tasks or [])
    fallback_used = not task and bool(fallback)
    if not task:
        task = str(fallback.get("title") or fallback.get("task") or "").strip()
    task_id = str(fallback.get("id") or "").strip()
    if task:
        label = f"{task_id} {task}".strip()
        seg.append(label[:48])

    owner = str((ag or {}).get("display") or (ag or {}).get("role") or
                (fallback.get("owner") if fallback_used else "") or
                run.get("active_role") or fallback.get("owner") or "").strip()
    if owner:
        elapsed = _dur(_age_seconds((ag or {}).get("started_at") or run.get("last_ts")))
        seg.append((owner + (f" {elapsed}" if elapsed else ""))[:24])

    age = _age_seconds(run.get("last_ts"))
    if age is not None and age >= 60:
        seg.append(f"STALLED {_dur(age)}")

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
        tasks = json.loads((orbit / "tasks.json").read_text()) if orbit else []
        if not isinstance(tasks, list):
            tasks = []
    except Exception:
        tasks = []
    try:
        _record_session(orbit, claude)
    except Exception:
        pass
    try:
        qa = _qa_state(orbit)
        print(build_line(claude, run, agents, qa, tasks))
        handoff = build_handoff_line(qa)
        if handoff:
            print(handoff)
    except Exception:
        print("")                                           # never crash the status line


if __name__ == "__main__":
    main()
