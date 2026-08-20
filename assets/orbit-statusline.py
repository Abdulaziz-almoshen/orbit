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
        return f"   Claude ●  {track}  ● Codex QA{model_bit} · " + _c("33", "FEEDBACK ←")
    if status == "pass":
        return f"   Claude ○  {track}  ● Codex QA{model_bit} · " + _c("32", "PASS")
    if status in ("blocked", "error"):
        return f"   Claude ●  {track}  ● Codex QA{model_bit} · " + _c("1;31", "BLOCKED")
    if status == "awaiting_deploy_approval":
        return f"   Claude ○  {track}  ● Codex QA{model_bit} · " + _c("33", "DEPLOY GATE")
    if status == "reviewing":
        return f"   Claude ○  {track}  ● Codex QA{model_bit} · " + _c("36", "REVIEW →")
    return f"   Claude ●  {track}  ○ Codex QA{model_bit} · " + _c("2", "QUEUED")


def _trim(text: str, limit: int) -> str:
    """Trim at a word boundary, never mid-word — a goal cut to 'the iso…' reads as a glitch."""
    text = " ".join(str(text).split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    space = cut.rfind(" ")
    if space > limit - 24:
        cut = cut[:space]
    return cut + "…"


def _c(code: str, text: str) -> str:
    """Color a WHOLE token (never split a mark from its label, so plain-text grep still works).

    Claude Code renders ANSI in the status area; NO_COLOR opts out. 2=dim, 32=green, 33=yellow,
    31=red, 36=cyan, 1;31=bold red. Color is the glance layer: the eye finds the one amber ▸ or
    the red ⚠ without reading a word.
    """
    if os.environ.get("NO_COLOR"):
        return text
    return f"\x1b[{code}m{text}\x1b[0m"


def _bar(done: int, total: int, cells: int = 8) -> str:
    filled = max(0, min(cells, round(cells * done / max(1, total))))
    return _c("32", "▰" * filled) + _c("2", "▱" * (cells - filled))


def _budget_percent(budget: dict) -> tuple:
    """(percent, pressure_hint) from the ledger, or (None, '') when no ledger is open.

    Display-only: sums recorded role spend, the parent session's own usage (cache reads at the
    configured weight), and outstanding reservations — so this number can never sit at 0% while a
    task's envelope shows tokens moving, which is exactly the contradiction users reported.
    """
    total = (budget or {}).get("total")
    if not isinstance(total, int) or total <= 0:
        return None, ""
    spent = sum(int(v or 0) for v in ((budget or {}).get("spent") or {}).values())
    parent = (budget or {}).get("parent_usage") or {}
    spent += sum(int(parent.get(k, 0) or 0) for k in
                 ("input_tokens", "output_tokens", "cache_creation_input_tokens"))
    weight = max(0.0, min(1.0, float((budget or {}).get("cache_read_weight", 0.10) or 0.0)))
    spent += int(round(int(parent.get("cache_read_input_tokens", 0) or 0) * weight))
    for value in ((budget or {}).get("reservations") or {}).values():
        if isinstance(value, dict):
            spent += int(value.get("tokens", 0) or 0)
        elif isinstance(value, (int, float)):
            spent += int(value)
    pct = round(100 * spent / total)
    gear = str((budget or {}).get("gear") or "")
    return pct, (" → auto-resize" if pct > 100 and gear != "T4" else "")


def build_goal_line(run: dict, active_goal: dict = None, budget: dict = None,
                    cost=None) -> str:
    run_goal = str(run.get("goal") or "").strip()
    budget_goal = str((budget or {}).get("goal") or "").strip()
    goal = str((active_goal or {}).get("goal") or run_goal or budget_goal).strip()
    if not goal:
        return ""
    gear = str((budget or {}).get("gear") or (active_goal or {}).get("gear") or "").strip()
    drift = bool(run_goal and budget_goal and " ".join(run_goal.lower().split()) !=
                 " ".join(budget_goal.lower().split()))
    tail = (" · " + _c("36", gear) if gear else "")
    if drift:
        tail += " · " + _c("1;31", "⚠ ALIGN")
    if isinstance(cost, (int, float)):
        tail += " · " + _c("2", f"${cost:.2f}")
    return f"🛰 GOAL · {_trim(goal, 84)}" + tail


def _active_board_task(run: dict, tasks: list):
    """The board task that matches what's running: id + token envelope come from here.

    Matching by title (or taking the first unfinished item when the run names nothing) is what
    fixes the 'U9 U9' doubling — the id is only ever prefixed when the label doesn't carry it.
    """
    named = " ".join(str(run.get("active_task") or "").split()).lower()
    board = _next_task(tasks or [])
    if named and isinstance(board, dict):
        title = " ".join(str(board.get("title") or board.get("task") or "").split()).lower()
        if title and title not in named and named not in title:
            for task in tasks or []:
                if isinstance(task, dict):
                    cand = " ".join(str(task.get("title") or task.get("task") or "").split()).lower()
                    if cand and (cand in named or named in cand):
                        return task
            return {}
    return board if isinstance(board, dict) else {}


def build_now_line(claude: dict, run: dict, agents: dict = None, tasks: list = None,
                   budget: dict = None, minimal: bool = False) -> str:
    """One line answering: is Orbit waiting on ME — and if not, what is it doing right now.

    When the run is blocked, the QUESTION leads the line. Burying '⚠ INPUT' between counters,
    with the actual question only findable by scrolling the transcript, was the single worst part
    of the old surface.
    """
    seg = []
    blocked = run.get("blocked_question")
    if blocked:
        seg.append(_c("1;31", "⚠ INPUT") + " · " + _c("33", _trim(str(blocked), 48)))
    if minimal:
        phase = str(run.get("phase") or run.get("mode") or "").strip().upper()
        if phase:
            seg.append(phase[:10])

    total = run.get("tasks_total")
    if isinstance(total, int) and total > 0:
        done = int(run.get("tasks_done", 0) or 0)
        seg.append(f"{_bar(done, total)} {done}/{total}")

    ag = _active_agent(agents or {})
    board = _active_board_task(run, tasks or [])
    task = " ".join(str(run.get("active_task") or (ag or {}).get("task") or
                        board.get("title") or board.get("task") or "").split())
    task_id = str(board.get("id") or "").strip()
    if task:
        label = task if (not task_id or task.startswith(task_id)) else f"{task_id} {task}"
        seg.append(_trim(label, 46))

    owner = str((ag or {}).get("display") or (ag or {}).get("role") or
                run.get("active_role") or board.get("owner") or "").strip()
    if owner:
        seconds = _age_seconds((ag or {}).get("started_at") or run.get("last_ts"))
        # <5s flickers; >24h is a stale record, not a ten-day-running agent — both stay silent
        elapsed = _dur(seconds) if seconds is not None and 5 <= seconds < 86400 else ""
        seg.append(_c("36", (owner + (f" {elapsed}" if elapsed else ""))[:24]))

    envelope = board.get("token_budget") if isinstance(board.get("token_budget"), dict) else {}
    if envelope:
        used = int(envelope.get("spent", 0) or 0) + int(envelope.get("reserved", 0) or 0)
        limit = int(envelope.get("limit", 0) or 0)
        ratio = used / limit if limit else 0
        token_text = f"tok {used / 1000:.1f}/{limit / 1000:.1f}k"
        seg.append(_c("31", token_text) if ratio >= 0.9 else
                   _c("33", token_text) if ratio >= 0.75 else token_text)

    # A blocked run is already alarmed (and its question shown); STALLED on top is a double siren.
    age = _age_seconds(run.get("last_ts"))
    if not blocked and age is not None and age >= 60:
        seg.append(_c("1;31", f"STALLED {_dur(age)}"))

    open_tasks = [t for t in (tasks or []) if isinstance(t, dict) and
                  str(t.get("status") or "").lower() not in ("done", "completed", "skipped")]
    upcoming = [t for t in open_tasks if t is not board and t.get("id") != board.get("id")]
    if blocked:
        upcoming = []                  # the alarm line stays about the alarm; the queue can wait
    if upcoming:
        head = upcoming[0]
        nxt = " ".join(str(head.get("title") or head.get("task") or "").split())
        seg.append(_c("2", _trim(f"next {head.get('id', '')} {nxt}".replace("next  ", "next "), 40)))
        if len(upcoming) > 1:
            seg.append(_c("2", f"+{len(upcoming) - 1} queued"))

    pct, pressure = _budget_percent(budget)
    if pct is not None:
        tone = "31" if pct >= 100 else ("33" if pct >= 75 else "32")
        seg.append(_c(tone, f"budget {pct}%{pressure}"))

    if minimal:
        cost = _get(claude, "cost", "total_cost_usd")
        if isinstance(cost, (int, float)):
            seg.append(f"${cost:.2f}")

    prefix = "🛰 " if minimal else "   "
    return prefix + " · ".join(seg) if seg else ""


def build_stage_line(tasks: list, agents: dict = None) -> str:
    """The single role-state strip. The old surface said the same thing four times — active role
    in the run line, again in the queue line, a stage strip, then a two-line 15-role bench of
    mostly idle dots. One strip carries it all; the full bench stays on `orbit-status --team`
    and the web dashboard, which are the right surfaces for that depth."""
    stages = [
        ("Plan", {"product-discovery", "business-analyst", "market-researcher", "planner"}),
        ("Build", {"designer", "builder", "frontend-engineer", "backend-engineer",
                   "mobile-developer", "data-engineer", "cli-engineer"}),
        ("Safe", {"safety-gate"}), ("Review", {"reviewer"}),
        ("QA", {"qa-engineer"}), ("CPO", {"cpo"}), ("Report", {"reporter"}),
    ]
    agents = agents if isinstance(agents, dict) else {}
    rendered = []
    for label, owners in stages:
        states = {str(t.get("status") or "").lower() for t in (tasks or [])
                  if isinstance(t, dict) and str(t.get("owner") or "") in owners}
        # live agent truth counts too — a SubagentStart lights the stage before any board write
        for role in owners:
            detail = agents.get(role)
            if isinstance(detail, dict) and detail.get("status"):
                states.add(str(detail.get("status")).lower())
        states.discard("available"); states.discard("idle")
        if not states:
            mark = "·"
        elif states & {"active", "in_progress"}:
            mark = "▸"
        elif states & {"blocked", "failed"}:
            mark = "!"
        elif states <= {"done", "completed", "skipped"}:
            mark = "✓"
        else:
            mark = "○"
        tone = {"✓": "32", "▸": "33", "!": "1;31", "○": "0", "·": "2"}[mark]
        rendered.append(_c(tone, f"{mark}{label}") if tone != "0" else f"{mark}{label}")
    return "   " + "  ".join(rendered)


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
    active_goal = _read_json(orbit / "active-goal.json", {}) if orbit else {}
    budget = _read_json(orbit / "budget.json", {}) if orbit else {}
    try:
        _record_session(orbit, claude)
    except Exception:
        pass
    try:
        qa = _qa_state(orbit)
        goal_line = build_goal_line(run, active_goal, budget,
                                    cost=_get(claude, "cost", "total_cost_usd"))
        if goal_line:
            print(goal_line)
        print(build_now_line(claude, run, agents, tasks, budget, minimal=not goal_line))
        if tasks:
            print(build_stage_line(tasks, agents))
        handoff = build_handoff_line(qa)
        if handoff:
            print(handoff)
    except Exception:
        print("")                                           # never crash the status line


if __name__ == "__main__":
    main()
