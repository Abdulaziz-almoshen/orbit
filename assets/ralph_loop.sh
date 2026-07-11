#!/usr/bin/env bash
#
# Ralph loop -- external driver for the self-prompting system on the Claude Code path.
#
# The idea (Daisy / "Ralph loop"): instead of one long-running agent whose context rots,
# restart a FRESH agent each cycle and let CLAUDE.md + STATE.md carry the memory. Each
# iteration is a clean `claude -p` invocation that reads state, does ONE cycle, and writes
# state back. This script is the brake: it enforces loop.config.json's hard limits in plain
# bash — max iterations, max runtime, the STOP sentinel, and (via `claude -p --output-format
# json`) the per-run AND per-cycle token + cost budgets, plus the gate-failure streak (counted
# from "GATE_FAILED" lines the agent writes to STATE.md) — so the loop cannot run unbounded or
# thrash. If the JSON usage fields are unavailable it says so and falls back to iterations +
# runtime + streak. (The one limit it cannot enforce is the model's honesty about a gate failing;
# that self-report is inherent to the fresh-agent-per-cycle model and is documented, not hidden.)
#
# Usage:  scripts/ralph_loop.sh [path/to/loop.config.json]
# Stop early at any time:  touch .orbit/STOP   (or Ctrl-C)

set -euo pipefail

CONFIG="${1:-.orbit/loop.config.json}"
[ -f "$CONFIG" ] || { echo "config not found: $CONFIG" >&2; exit 1; }

# --- read hard limits from the config (python3, so no jq dependency; $2 = default) --------
read_cfg() { python3 -c "import json;c=json.load(open('$CONFIG'));print(c$1)" 2>/dev/null || printf '%s' "$2"; }
MAX_ITERS="$(read_cfg "['hard_limits']['max_iterations']" 50)"
MAX_RUNTIME="$(read_cfg "['hard_limits']['max_runtime_seconds']" 3600)"
TOKEN_BUDGET="$(read_cfg "['hard_limits']['token_budget']['per_run']" 0)"
COST_BUDGET="$(read_cfg "['hard_limits']['cost_budget_usd']['per_run']" 0)"
TOKEN_PER_CYCLE="$(read_cfg "['hard_limits']['token_budget']['per_cycle']" 0)"
COST_PER_CYCLE="$(read_cfg "['hard_limits']['cost_budget_usd']['per_cycle']" 0)"
GATE_STREAK_MAX="$(read_cfg "['hard_limits']['gate_failure_streak']" 0)"
STOP_SENTINEL="$(read_cfg "['paths']['stop_sentinel']" .orbit/STOP)"
STATE_FILE="$(read_cfg "['paths']['state']" .orbit/STATE.md)"
EXECUTOR_MODEL="$(read_cfg "['model_policy']['executor']['model']" "")"
EXECUTOR_DISPLAY="$(read_cfg "['model_policy']['executor']['display']" "executor")"
ADVISOR_DISPLAY="$(read_cfg "['model_policy']['advisor']['display']" "advisor")"
CLAUDE_MODEL_ARGS=()
if [ -n "$EXECUTOR_MODEL" ] && [ "$EXECUTOR_MODEL" != "inherit" ]; then
  CLAUDE_MODEL_ARGS=(--model "$EXECUTOR_MODEL")
fi

START="$(date +%s)"
ITER=1
COST_SPENT=0
TOKENS_SPENT=0
PARSE_OK=1
GATE_STREAK=0
PREV_GATE_FAILS=0

# float/int compare via python: returns 0 (true) if $1 >= $2 and $2 > 0
over() { python3 -c "import sys; a,b=float('$1'),float('$2'); sys.exit(0 if b>0 and a>=b else 1)"; }

# The prompt is the SAME every cycle -- the system prompts itself via the files.
read -r -d '' CYCLE_PROMPT <<'EOF' || true
Run exactly ONE cycle of the self-prompting loop, then stop:
1. READ: read CLAUDE.md, then .orbit/STATE.md. That is your full memory -- you have no
   prior conversation.
2. PLAN: take the top item from STATE.md's task queue. For anything non-trivial, write the
   plan first.
   For T2+ work, run the Counterfactual Regret Gate before ACT: write a compact
   .orbit/artifacts/<cycle>/counterfactual.json packet, identify up to three ways the plan could be
   wrong, and run the cheapest falsification probe. Record only Assumption -> Probe -> Evidence ->
   Decision. A failed probe routes back to discovery, plan, build, or review; do not build on a failed
   assumption. Validate the packet with .orbit/counterfactual.py. This is inline Executor work; do
   not spawn another worker for it.
3. ACT: delegate to the appropriate sub-agent(s) per .orbit/roles/ (use Claude Code
   subagents in .claude/agents/). Roles write artifacts to .orbit/artifacts/ and report
   back. Each role announces itself: open its report with "[role] ..." and emit to
   .orbit/activity.py; keep the checklist current (TaskCreate/TaskUpdate, and .orbit/tasks.json for
   the orbit-status dashboard) so a watcher can see who's talking and what's done.
   Honor .orbit/loop.config.json model_policy: the executor lane does ordinary loop work; call the
   Advisor (Opus) only on-demand for a real decision fork, max once this cycle, with a tiny packet and
   an advisor_reason recorded in STATE/activity.
4. EVALUATE: check the output against CLAUDE.md section 3 and the eval gates in
   .orbit/loop.config.json (input / quality / safety). Safety has veto power. If an eval gate
   FAILS this cycle, append the line "GATE_FAILED: <which gate + why>" to STATE.md (the runner
   counts consecutive gate failures and stops the loop after the configured streak).
5. UPDATE: overwrite STATE.md's snapshot/queue/handoffs, append one line to the cycle log
   and any new decisions.
6. DECIDE: if the run goal is met -> write the line "RUN_GOAL_MET" at the end of STATE.md.
   If a human-approval checkpoint or a blocker is hit -> write "AWAITING_HUMAN: <reason>"
   at the end of STATE.md. Otherwise leave the next task queued for the next cycle.

Respect every limit in loop.config.json. Never take a FORBIDDEN action (e.g. moving
money). Never take an irreversible, financial, or outward-facing action without a human --
propose it via STATE.md instead. Then STOP; do not start another cycle yourself.
EOF

echo "Ralph loop starting: max_iters=$MAX_ITERS max_runtime=${MAX_RUNTIME}s token_budget=$TOKEN_BUDGET/run ($TOKEN_PER_CYCLE/cycle) cost_budget=\$$COST_BUDGET/run gate_streak=$GATE_STREAK_MAX executor=$EXECUTOR_DISPLAY advisor=$ADVISOR_DISPLAY/on-demand"
echo "Tip: in another pane, run  scripts/orbit-status --follow  to watch live (Ctrl-C to stop)."

while :; do
  # --- hard limits, checked before every cycle (the brake) --------------------------
  if [ -f "$STOP_SENTINEL" ]; then echo "[STOP] sentinel $STOP_SENTINEL present"; break; fi
  if [ "$ITER" -gt "$MAX_ITERS" ]; then echo "[STOP] max_iterations ($MAX_ITERS) reached"; break; fi
  NOW="$(date +%s)"; ELAPSED=$((NOW - START))
  if [ "$ELAPSED" -ge "$MAX_RUNTIME" ]; then echo "[STOP] max_runtime (${MAX_RUNTIME}s) reached"; break; fi
  if [ "$PARSE_OK" = 1 ]; then
    if over "$COST_SPENT" "$COST_BUDGET"; then echo "[STOP] per-run cost budget (\$$COST_BUDGET) reached — spent \$$COST_SPENT"; break; fi
    if over "$TOKENS_SPENT" "$TOKEN_BUDGET"; then echo "[STOP] per-run token budget ($TOKEN_BUDGET) reached — spent $TOKENS_SPENT"; break; fi
  fi

  echo "=== cycle $ITER (elapsed ${ELAPSED}s, spent \$$COST_SPENT / $TOKENS_SPENT tok) ==="

  # --- one fresh-context cycle (JSON output so we can meter cost + tokens) -----------
  TMPOUT="$(mktemp)"
  if ! claude -p --output-format json "${CLAUDE_MODEL_ARGS[@]}" "$CYCLE_PROMPT" > "$TMPOUT"; then
    echo "[STOP] claude exited non-zero on cycle $ITER"; rm -f "$TMPOUT"; break
  fi
  # show the agent's result text so progress is visible
  python3 -c "import json,sys
try: print(json.load(open('$TMPOUT')).get('result') or '')
except Exception: pass"
  # meter this cycle's spend
  STATS="$(python3 -c "import json
try:
    d=json.load(open('$TMPOUT')); u=d.get('usage') or {}
    t=sum(int(u.get(k,0) or 0) for k in ('input_tokens','output_tokens','cache_read_input_tokens','cache_creation_input_tokens'))
    c=float(d.get('total_cost_usd') or d.get('cost_usd') or 0)
    print(f'{c} {t}')
except Exception: print('FAIL')")"
  rm -f "$TMPOUT"
  if [ "$STATS" = "FAIL" ]; then
    if [ "$PARSE_OK" = 1 ]; then echo "[warn] couldn't read cost/tokens from claude JSON — enforcing iterations + runtime only"; fi
    PARSE_OK=0
  else
    C="${STATS%% *}"; T="${STATS##* }"
    COST_SPENT="$(python3 -c "print($COST_SPENT + $C)")"
    TOKENS_SPENT="$(python3 -c "print($TOKENS_SPENT + $T)")"
    # per-CYCLE budget: a single cycle blowing its cap is a runaway signal — stop the loop.
    if over "$T" "$TOKEN_PER_CYCLE"; then echo "[STOP] cycle $ITER exceeded per-cycle token budget ($TOKEN_PER_CYCLE) — used $T"; break; fi
    if over "$C" "$COST_PER_CYCLE"; then echo "[STOP] cycle $ITER exceeded per-cycle cost budget (\$$COST_PER_CYCLE) — used \$$C"; break; fi
  fi

  # --- check the sentinels the agent may have written to STATE.md -------------------
  if [ -f "$STATE_FILE" ]; then
    if grep -q "RUN_GOAL_MET" "$STATE_FILE"; then echo "[DONE] run goal met"; break; fi
    if grep -q "AWAITING_HUMAN" "$STATE_FILE"; then
      echo "[PAUSE] awaiting human:"; grep "AWAITING_HUMAN" "$STATE_FILE"; break
    fi
    # gate-failure streak: count NEW "GATE_FAILED" lines this cycle; stop after N in a row.
    GATE_FAILS="$(grep -c "GATE_FAILED" "$STATE_FILE" 2>/dev/null || echo 0)"
    if [ "$GATE_FAILS" -gt "$PREV_GATE_FAILS" ]; then GATE_STREAK=$((GATE_STREAK + 1)); else GATE_STREAK=0; fi
    PREV_GATE_FAILS="$GATE_FAILS"
    if [ "$GATE_STREAK_MAX" -gt 0 ] && [ "$GATE_STREAK" -ge "$GATE_STREAK_MAX" ]; then
      echo "[STOP] gate-failure streak ($GATE_STREAK ≥ $GATE_STREAK_MAX) — the loop isn't making progress"; break
    fi
  fi

  ITER=$((ITER + 1))
done

echo "Ralph loop ended after $((ITER)) cycle(s), $(( $(date +%s) - START ))s."
