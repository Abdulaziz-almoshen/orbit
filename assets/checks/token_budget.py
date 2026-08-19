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

4. DEGRADE, DON'T THROW. The ladder is trim_packet → downgrade_model → waive_role_with_record.
   Every framework surveyed that throws on exhaustion (LlamaIndex, Pydantic AI) is a library whose
   caller can retry. Orbit is a loop — throwing strands the run. A waived role writes a record so
   the CPO gate can see the run went thin and judge the deliverable accordingly. Never a silent skip.

Estimates are deliberately rough (bytes / divisor), matching orbit-context. This is a stoplight for
a self-governing loop, not billing truth — the authority on real spend is the provider's usage
figures, which this module never sees.
"""
from __future__ import annotations

import json
import math
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

DEFAULT_PER_GEAR = {"T0": 15000, "T1": 60000, "T2": 200000, "T3": 600000, "T4": None}

DEFAULT_CONTRACT = {
    "enabled": True,
    "unit": "tokens",
    "per_gear": DEFAULT_PER_GEAR,
    "reserve_fraction": 0.15,
    "allocation": DEFAULT_ALLOCATION,
    "degrade_ladder": ["trim_packet", "downgrade_model", "waive_role_with_record"],
    "warn_at": 0.75,
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
    gear = str(gear or "T2").upper()
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
        "gear": gear,
        "unit": c.get("unit", "tokens"),
        "total": total,
        "reserve": reserve,
        "reserve_used": 0,
        "warn_at": float(c.get("warn_at", 0.75)),
        "degrade_ladder": list(c.get("degrade_ladder") or DEFAULT_CONTRACT["degrade_ladder"]),
        "allocations": allocations,
        "spent": {r: 0 for r in roles},
        "degrades": [],
        "waived": [],
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


def check(orbit_or_ledger, role: str, estimate: int) -> dict:
    """Pre-flight decision for one dispatch. Never raises — returns the rung of the ladder.

    Returns {"decision": "allow"|"degrade", "action": <rung>, "remaining": int|None, "reason": str}.
    A `degrade` is not a refusal: it is an instruction to run the role in a cheaper shape.
    """
    ledger = orbit_or_ledger if isinstance(orbit_or_ledger, dict) else load(orbit_or_ledger)
    if not ledger:
        return {"decision": "allow", "action": "none", "remaining": None,
                "reason": "no budget ledger for this run — budgeting is off or unopened"}
    left = remaining(ledger, role)
    if left is None:
        return {"decision": "allow", "action": "none", "remaining": None,
                "reason": f"{role} is uncapped at gear {ledger.get('gear')}"}
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
        rung = ladder[-1] if ladder else "waive_role_with_record"
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
    if alloc is not None and spent[role] > alloc:
        ledger["reserve_used"] = min(int(ledger.get("reserve") or 0),
                                     int(ledger.get("reserve_used") or 0) + (spent[role] - alloc))
    if note:
        ledger.setdefault("notes", []).append({"ts": _now(), "role": role, "note": note[:200]})
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
    spent = sum(int(v) for v in (ledger.get("spent") or {}).values())
    if total is None:
        return f"budget {ledger.get('gear')}: ~{spent:,} tok spent (uncapped)"
    pct = int(round(100 * spent / max(1, total)))
    tail = ""
    if ledger.get("waived"):
        tail = f" · waived: {', '.join(ledger['waived'])}"
    return f"budget {ledger.get('gear')}: ~{spent:,}/{total:,} tok ({pct}%){tail}"
