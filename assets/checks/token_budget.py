#!/usr/bin/env python3
"""
token_budget — the goal → role → tokens allocator for an Orbit run.

WHY THIS SHAPE

Orbit already had `hard_limits.token_budget` in loop.config.json, but it was read only by
`loop.py`, whose `dispatch()` is a `NotImplementedError` stub. The budget existed and enforced
nothing. This module is the live-path replacement: it is a plain ledger on disk that the
orchestrator debits before each dispatch, so the contract is inspectable rather than aspirational.

Four properties, each chosen against a specific published result:

1. ALLOCATION BY GEAR, NOT FLAT. A T1 task and a T3 task should not carry the same machinery.
   AgentPrune (ICLR 2025) measured 28.1–72.8% token reduction from pruning multi-agent
   communication with a *performance gain*, and Chen et al. (NeurIPS 2024) showed the accuracy
   curve over LM calls is non-monotonic — it rises, then falls. More roles is not more quality.

2. RESERVE. A fixed fraction is withheld from role allocations so an overspending role borrows
   from the reserve instead of silently starving the roles after it. Without this, budget
   exhaustion is discovered by the last role in the order — usually the reporter, which is
   precisely the one whose failure is most visible and least informative.

3. MODEL-VISIBLE COUNTDOWN. `packet_note()` renders the remaining allocation into the dispatch
   packet. Anthropic's task-budget beta works this way for a measured reason: a hard cap truncates
   mid-thought, whereas a budget the model can see lets it land the plane. Their docs also warn
   this can trigger *premature* wrap-up, so the note only appears once spending crosses warn_at.

4. LAND, DON'T LEAK. The ladder is trim_packet → downgrade_model → budget_pause_with_checkpoint.
   Exhaustion never silently drops a quality gate and never opens an unmetered retry. Orbit preserves
   the immutable goal, writes a resumable checkpoint, and spends the protected closeout allowance on
   an honest result or evidence-backed pause.

Estimates are deliberately rough (bytes / divisor), matching orbit-context. This is a stoplight for
a self-governing loop, not billing truth — the authority on real spend is the provider's usage
figures, which this module never sees.
"""
from __future__ import annotations

import json
import math
import re
import time
from pathlib import Path

LEDGER_REL = ".orbit/budget.json"
DEFAULT_DIVISOR = 4

# Fractions of the gear budget, after the reserve is withheld. They sum to 1.0 across the full
# spine; a gear that runs fewer roles renormalizes over the roles it actually runs (see plan()).
DEFAULT_ALLOCATION = {
    "product-discovery": 0.08,
    "business-analyst": 0.05,
    "market-researcher": 0.07,
    "planner": 0.08,
    "designer": 0.12,
    "builder": 0.30,
    "safety-gate": 0.03,
    "reviewer": 0.08,
    "qa-engineer": 0.09,
    "cpo": 0.07,
    "reporter": 0.03,
}

DEFAULT_PER_GEAR = {"T0": 8000, "T1": 25000, "T2": 60000, "T3": 140000, "T4": 240000}

# A dispatch is reserved at its historical/policy slice before Claude starts it. This bounds the
# overshoot to one already-admitted call and, crucially, prevents two concurrent agents from both
# seeing the same remaining balance. Values are bootstrap p90s; real installs can tune them from
# PostToolUse[Agent].tool_response.totalTokens telemetry.
DEFAULT_ROLE_SLICE = {
    "dispatcher": 2000, "product-discovery": 7000, "business-analyst": 5000,
    "market-researcher": 7000, "planner": 7000, "designer": 9000, "builder": 12000,
    "frontend-engineer": 12000, "backend-engineer": 12000, "mobile-developer": 12000,
    "data-engineer": 12000, "cli-engineer": 10000, "safety-gate": 4000,
    "reviewer": 6000, "qa-engineer": 7000, "cpo": 5000, "reporter": 2500,
    "advisor": 10000,
}

DEFAULT_CONTRACT = {
    "enabled": True,
    "unit": "tokens",
    "per_gear": DEFAULT_PER_GEAR,
    "reserve_fraction": 0.15,
    "allocation": DEFAULT_ALLOCATION,
    "degrade_ladder": ["trim_packet", "downgrade_model", "budget_pause_with_checkpoint"],
    "warn_at": 0.75,
    "fail_closed": True,
    "closeout_fraction": 0.10,
    "role_slice_tokens": DEFAULT_ROLE_SLICE,
    "max_agent_calls": {"T0": 0, "T1": 4, "T2": 6, "T3": 10, "T4": 14},
}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def contract(orbit: Path) -> dict:
    """Merge the project's token_budget block over the defaults. Missing block → defaults."""
    cfg = _read_json(orbit / "loop.config.json")
    out = dict(DEFAULT_CONTRACT)
    block = cfg.get("token_budget")
    if isinstance(block, dict):
        out.update({k: v for k, v in block.items() if not k.startswith("_")})
    return out


def estimate_tokens(text: str, divisor: int = DEFAULT_DIVISOR) -> int:
    """Rough pre-flight estimate. Same divisor convention as orbit-context, deliberately."""
    return int(math.ceil(len(text.encode("utf-8")) / max(1, divisor)))


def normalize_gear(gear: str) -> str:
    """Map every possible T label to a governed tier. T5/T100 are rigorous, never uncapped."""
    raw = str(gear or "T1").strip().upper()
    try:
        number = int(raw[1:]) if raw.startswith("T") else int(raw)
    except (TypeError, ValueError):
        return "T1"
    return f"T{max(0, min(4, number))}"


def size_goal(goal: str) -> dict:
    """Deterministically size a goal before execution; no model call and no user prompt.

    This is intentionally conservative: explicit gears win, irreversible/production breadth gets
    T4, and otherwise accumulated breadth/risk/uncertainty signals select T1-T3. The returned
    reasons make the estimate inspectable on the board and in tests.
    """
    text = str(goal or "")
    lower = text.lower()
    explicit = re.search(r"\bT(\d+)\b", text, re.IGNORECASE)
    if explicit:
        gear = normalize_gear(explicit.group(0))
        return {"gear": gear, "score": int(gear[1:]), "reasons": ["explicit gear"]}

    signals = {
        "production/irreversible": re.compile(
            r"\b(production|prod deploy|rollout|multi[- ]repo|across repos|payment|billing|"
            r"migration|migrate|compliance|security incident|data loss)\b"),
        "architecture/data boundary": re.compile(
            r"\b(architecture|architect|schema|database|auth|permission|provision|isolation|"
            r"api contract|state machine|infrastructure)\b"),
        "breadth": re.compile(
            r"(^|\n)\s*\d+[.)]\s|\b(across|whole|entire|end[- ]to[- ]end|multiple|every|all dependencies|"
            r"frontend and backend|design and qa)\b"),
        "research/uncertainty": re.compile(
            r"\b(research|discovery|compare|evaluate|unknown|uncertain|best practice|market)\b"),
        "delivery scope": re.compile(
            r"\b(implement|build|refactor|redesign|integrate|deploy|release|ship|version)\b"),
    }
    weights = {"production/irreversible": 3, "architecture/data boundary": 2,
               "breadth": 3, "research/uncertainty": 2, "delivery scope": 1}
    reasons = [name for name, pattern in signals.items() if pattern.search(lower)]
    score = sum(weights[name] for name in reasons)
    if len(re.findall(r"(^|\n)\s*\d+[.)]\s", lower)) >= 3:
        score += 2; reasons.append("multi-item goal")
    words = len(text.split())
    if words >= 80:
        score += 2; reasons.append("long multi-constraint goal")
    elif words >= 30:
        score += 1; reasons.append("multi-constraint goal")
    if "production/irreversible" in reasons and ("breadth" in reasons or score >= 7):
        gear = "T4"
    elif score >= 5:
        gear = "T3"
    elif score >= 2:
        gear = "T2"
    else:
        gear = "T1"
    return {"gear": gear, "score": score, "reasons": reasons or ["bounded change"]}


def estimate_packet(paths, note: str = "", root: Path | None = None,
                    divisor: int = DEFAULT_DIVISOR) -> int:
    """Estimate what a dispatch packet will cost: the note plus every file it names.

    This is the pre-flight number. LiteLLM is the only surveyed system that reserves before the
    call rather than accounting after it, and it does so because post-hoc debiting always
    overshoots by roughly the in-flight concurrency.
    """
    total = estimate_tokens(note, divisor)
    base = root or Path(".")
    for rel in paths or []:
        try:
            p = Path(rel)
            p = p if p.is_absolute() else base / p
            if p.is_file():
                total += int(math.ceil(p.stat().st_size / max(1, divisor)))
        except Exception:
            continue
    return total


def plan(orbit: Path, gear: str, roles: list, goal: str = "") -> dict:
    """Open a ledger for one goal at one gear, allocating across exactly the roles that will run.

    Renormalizing over the running roles is the point of gear-scaling: when a T1 run skips
    discovery and market research, their share flows to the roles that remain rather than
    evaporating into an unused budget the run then feels obliged to spend.
    """
    c = contract(orbit)
    requested_gear = str(gear or "T1").upper()
    gear = normalize_gear(requested_gear)
    per_gear = c.get("per_gear") or DEFAULT_PER_GEAR
    total = per_gear.get(gear, per_gear.get("T2"))
    roles = [str(r) for r in (roles or []) if str(r).strip()]

    alloc_tbl = c.get("allocation") or DEFAULT_ALLOCATION
    reserve_frac = float(c.get("reserve_fraction", 0.15) or 0.0)

    allocations: dict = {}
    if total is None:                                   # T4/mission — tracked, never capped
        allocations = {r: None for r in roles}
        reserve = None
    else:
        total = int(total)
        reserve = int(round(total * reserve_frac))
        spendable = total - reserve
        weights = {r: float(alloc_tbl.get(r, 0.05)) for r in roles}
        wsum = sum(weights.values()) or 1.0
        allocations = {r: int(round(spendable * (w / wsum))) for r, w in weights.items()}

    ledger = {
        "schema": 1,
        "opened_at": _now(),
        "goal": goal[:500],
        "goal_hash": __import__("hashlib").sha256(goal.strip().encode()).hexdigest()[:16],
        "session_id": "",
        "requested_gear": requested_gear,
        "gear": gear,
        "unit": c.get("unit", "tokens"),
        "total": total,
        "reserve": reserve,
        "reserve_used": 0,
        "closeout_fraction": float(c.get("closeout_fraction", 0.10) or 0.0),
        "warn_at": float(c.get("warn_at", 0.75)),
        "degrade_ladder": list(c.get("degrade_ladder") or DEFAULT_CONTRACT["degrade_ladder"]),
        "allocations": allocations,
        "spent": {r: 0 for r in roles},
        "degrades": [],
        "waived": [],
        "status": "active",
        "agent_calls": 0,
        "reservations": {},
        "actual_usage": {"input_tokens": 0, "output_tokens": 0,
                         "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
        "parent_usage": {"input_tokens": 0, "output_tokens": 0,
                         "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
    }
    _write(orbit, ledger)
    return ledger


def _write(orbit: Path, ledger: dict) -> None:
    path = orbit / "budget.json" if orbit.name == ".orbit" else orbit / LEDGER_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(ledger, indent=2) + "\n")
    tmp.replace(path)


def load(orbit: Path) -> dict:
    path = orbit / "budget.json" if orbit.name == ".orbit" else orbit / LEDGER_REL
    return _read_json(path)


def remaining(ledger: dict, role: str) -> int | None:
    """Tokens left for this role, including whatever is left of the shared reserve.

    Returning the reserve as part of a role's headroom is deliberate: the reserve exists to absorb
    one role's overrun, so a role should be able to see it before it decides to trim.
    """
    alloc = (ledger.get("allocations") or {}).get(role)
    if alloc is None:
        return None
    spent = int((ledger.get("spent") or {}).get(role, 0))
    reserve_left = int(ledger.get("reserve") or 0) - int(ledger.get("reserve_used") or 0)
    return max(0, alloc - spent) + max(0, reserve_left)


def total_spent(ledger: dict) -> int:
    delegated = sum(int(v or 0) for v in (ledger.get("spent") or {}).values())
    parent = sum(int(v or 0) for v in (ledger.get("parent_usage") or {}).values())
    return delegated + parent


def total_reserved(ledger: dict) -> int:
    return sum(int((v or {}).get("tokens", 0) or 0)
               for v in (ledger.get("reservations") or {}).values())


def global_remaining(ledger: dict, protect_closeout: bool = False) -> int:
    total = ledger.get("total")
    if total is None:  # legacy ledgers are upgraded to a hard T4 ceiling on the next preflight
        total = DEFAULT_PER_GEAR["T4"]
    closeout = int(total * float(ledger.get("closeout_fraction", 0.10) or 0.0))
    usable = total - (closeout if protect_closeout else 0)
    return max(0, usable - total_spent(ledger) - total_reserved(ledger))


def sync_gear(orbit: Path, requested_gear: str) -> dict:
    """Raise/lower the envelope without resetting spend. Arbitrary gears saturate at hard T4."""
    ledger = load(orbit)
    if not ledger:
        return {}
    c = contract(orbit)
    gear = normalize_gear(requested_gear)
    total = int((c.get("per_gear") or DEFAULT_PER_GEAR).get(gear) or DEFAULT_PER_GEAR["T4"])
    ledger["requested_gear"] = str(requested_gear or gear).upper()
    ledger["gear"] = gear
    ledger["total"] = total
    ledger["reserve"] = int(round(total * float(c.get("reserve_fraction", 0.15) or 0.0)))
    ledger["closeout_fraction"] = float(c.get("closeout_fraction", 0.10) or 0.0)
    roles = list((ledger.get("allocations") or {}).keys())
    weights = {r: float((c.get("allocation") or DEFAULT_ALLOCATION).get(r, 0.05)) for r in roles}
    wsum = sum(weights.values()) or 1.0
    spendable = total - int(ledger["reserve"])
    ledger["allocations"] = {
        r: int(round(spendable * (weight / wsum))) for r, weight in weights.items()
    }
    for role in roles:
        ledger.setdefault("spent", {}).setdefault(role, 0)
    _write(orbit, ledger)
    return ledger


def open_session(orbit: Path, session_id: str, goal: str, gear: str = "T1") -> dict:
    """Open once per Claude session. User follow-ups cannot reset the same session's allowance."""
    current = load(orbit)
    if current and current.get("session_id") == session_id and current.get("status") == "active":
        return current
    roles = ["planner", "reviewer", "qa-engineer", "reporter"]
    ledger = plan(orbit, gear, roles, goal)
    ledger["session_id"] = session_id
    ledger["closeout_fraction"] = float(contract(orbit).get("closeout_fraction", 0.10) or 0.0)
    _write(orbit, ledger)
    return ledger


def sync_parent_usage(orbit: Path, transcript_path: str) -> dict:
    """Recompute root-session usage from Claude's transcript without double charging messages.

    The Agent hook reports delegated usage directly. Root model turns do not pass through Agent, but
    hook payloads carry `transcript_path`; assistant records contain provider usage. Recomputing the
    aggregate is deterministic and survives repeated hooks, compaction, and process restarts.
    """
    ledger = load(orbit)
    path = Path(str(transcript_path or ""))
    if not ledger or not path.is_file():
        return ledger
    totals = {"input_tokens": 0, "output_tokens": 0,
              "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
    seen = set()
    try:
        for line in path.read_text(errors="ignore").splitlines():
            row = json.loads(line)
            message = row.get("message") if isinstance(row.get("message"), dict) else row
            if row.get("type") != "assistant" and message.get("role") != "assistant":
                continue
            usage = message.get("usage") if isinstance(message.get("usage"), dict) else {}
            identity = str(message.get("id") or row.get("uuid") or "")
            if identity and identity in seen:
                continue
            if identity:
                seen.add(identity)
            for key in totals:
                totals[key] += int(usage.get(key, 0) or 0)
    except Exception:
        return ledger
    ledger["parent_usage"] = totals
    ledger["parent_messages_metered"] = len(seen)
    ledger["updated_at"] = _now()
    _write(orbit, ledger)
    return ledger


def check(orbit_or_ledger, role: str, estimate: int) -> dict:
    """Pre-flight decision for one dispatch. Never raises — returns the rung of the ladder.

    Returns {"decision": "allow"|"degrade"|"deny", "action": <rung>, ...}. A `degrade` is an
    instruction to use a cheaper shape; trusted admission may conservatively deny that edge.
    """
    ledger = orbit_or_ledger if isinstance(orbit_or_ledger, dict) else load(orbit_or_ledger)
    if not ledger:
        return {"decision": "deny", "action": "open_ledger", "remaining": 0,
                "reason": "no budget ledger — governed agent dispatch fails closed"}
    global_left = global_remaining(ledger, protect_closeout=role not in ("cpo", "reporter"))
    if estimate > global_left:
        return {"decision": "deny", "action": "budget_pause", "remaining": global_left,
                "reason": (f"{role} needs ~{estimate:,} tokens but the governed goal has "
                           f"~{global_left:,} dispatchable tokens left")}
    left = remaining(ledger, role)
    if left is None:
        return {"decision": "allow", "action": "none", "remaining": global_left,
                "reason": f"{role} has no private slice; the governed global ceiling still applies"}
    if estimate <= left:
        alloc = (ledger.get("allocations") or {}).get(role) or 1
        spent = int((ledger.get("spent") or {}).get(role, 0))
        if (spent + estimate) / alloc >= float(ledger.get("warn_at", 0.75)):
            return {"decision": "allow", "action": "none", "remaining": left,
                    "reason": f"{role} is past its warn mark — keep the packet tight"}
        return {"decision": "allow", "action": "none", "remaining": left, "reason": "within budget"}

    ladder = ledger.get("degrade_ladder") or DEFAULT_CONTRACT["degrade_ladder"]
    over = estimate - left
    if over <= left:                                    # a trim can plausibly close the gap
        rung = ladder[0] if ladder else "trim_packet"
    elif over <= left * 3:
        rung = ladder[1] if len(ladder) > 1 else "downgrade_model"
    else:
        rung = ladder[-1] if ladder else "budget_pause_with_checkpoint"
    return {"decision": "degrade", "action": rung, "remaining": left,
            "reason": (f"{role} needs ~{estimate:,} tokens but has ~{left:,} left "
                       f"(over by ~{over:,}) — apply '{rung}'")}


def spend(orbit: Path, role: str, tokens: int, note: str = "") -> dict:
    """Record actual spend after a dispatch, draining the reserve when a role overruns."""
    ledger = load(orbit)
    if not ledger:
        return {}
    spent = ledger.setdefault("spent", {})
    spent[role] = int(spent.get(role, 0)) + int(tokens)
    alloc = (ledger.get("allocations") or {}).get(role)
    overruns = sum(max(0, int(value) - int((ledger.get("allocations") or {}).get(name, value)))
                   for name, value in spent.items())
    ledger["reserve_used"] = min(int(ledger.get("reserve") or 0), overruns)
    if note:
        ledger.setdefault("notes", []).append({"ts": _now(), "role": role, "note": note[:200]})
    _write(orbit, ledger)
    return ledger


def reserve(orbit: Path, role: str, reservation_id: str, estimate: int) -> dict:
    """Atomically record admission. The trusted hook serializes calls around this operation."""
    ledger = load(orbit)
    if not ledger:
        return {}
    ledger.setdefault("reservations", {})[reservation_id] = {
        "role": role, "tokens": int(estimate), "ts": _now()
    }
    ledger["agent_calls"] = int(ledger.get("agent_calls", 0)) + 1
    _write(orbit, ledger)
    return ledger


def reconcile(orbit: Path, reservation_id: str, role: str, tokens: int,
              usage: dict | None = None) -> dict:
    ledger = load(orbit)
    if not ledger:
        return {}
    ledger.setdefault("reservations", {}).pop(reservation_id, None)
    spent = ledger.setdefault("spent", {})
    spent[role] = int(spent.get(role, 0)) + max(0, int(tokens or 0))
    aggregate = ledger.setdefault("actual_usage", {})
    for key in ("input_tokens", "output_tokens", "cache_creation_input_tokens",
                "cache_read_input_tokens"):
        aggregate[key] = int(aggregate.get(key, 0)) + int((usage or {}).get(key, 0) or 0)
    ledger["updated_at"] = _now()
    _write(orbit, ledger)
    return ledger


def record_degrade(orbit: Path, role: str, action: str, reason: str) -> dict:
    """Log a rung of the ladder being applied. A waive additionally lands in `waived` so the CPO
    gate can see the run was thinner than the gear advertised."""
    ledger = load(orbit)
    if not ledger:
        return {}
    entry = {"ts": _now(), "role": role, "action": action, "reason": reason[:300]}
    ledger.setdefault("degrades", []).append(entry)
    if action.startswith("waive"):
        ledger.setdefault("waived", []).append(role)
    _write(orbit, ledger)
    return ledger


def packet_note(ledger: dict, role: str) -> str:
    """The model-visible countdown, rendered only once the role crosses its warn mark.

    Anthropic's docs are explicit that surfacing a remaining-token count too early causes models to
    wrap up prematurely, so silence below the threshold is a feature, not an omission.
    """
    left = remaining(ledger, role)
    if left is None:
        return ""
    alloc = (ledger.get("allocations") or {}).get(role) or 0
    spent = int((ledger.get("spent") or {}).get(role, 0))
    if not alloc or (spent / alloc) < float(ledger.get("warn_at", 0.75)):
        return ""
    return (f"[orbit] TOKEN BUDGET: ~{left:,} tokens remain for {role} at gear "
            f"{ledger.get('gear')}. Land this cleanly — return the verdict and its evidence, "
            f"drop optional exploration. Do not start a new line of investigation.")


def summary(ledger: dict) -> str:
    """One-line board/status rendering."""
    if not ledger:
        return ""
    total = ledger.get("total")
    spent = total_spent(ledger)
    if total is None:
        total = DEFAULT_PER_GEAR["T4"]
    pct = int(round(100 * spent / max(1, total)))
    tail = ""
    if ledger.get("waived"):
        tail = f" · waived: {', '.join(ledger['waived'])}"
    return f"budget {ledger.get('gear')}: ~{spent:,}/{total:,} tok ({pct}%){tail}"
