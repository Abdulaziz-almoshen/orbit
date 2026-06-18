#!/usr/bin/env bash
#
# Ralph loop -- external driver for the self-prompting system on the Claude Code path.
#
# The idea (Daisy / "Ralph loop"): instead of one long-running agent whose context rots,
# restart a FRESH agent each cycle and let CLAUDE.md + STATE.md carry the memory. Each
# iteration is a clean `claude -p` invocation that reads state, does ONE cycle, and writes
# state back. This script is the brake: it enforces the same hard limits as loop.config.json
# in plain bash, so the loop physically cannot run unbounded.
#
# Usage:  scripts/ralph_loop.sh [path/to/loop.config.json]
# Stop early at any time:  touch .orbit/STOP   (or Ctrl-C)

set -euo pipefail

CONFIG="${1:-.orbit/loop.config.json}"
[ -f "$CONFIG" ] || { echo "config not found: $CONFIG" >&2; exit 1; }

# --- read hard limits from the config (python3, so no jq dependency) ----------------
read_cfg() { python3 -c "import json,sys;print(json.load(open('$CONFIG'))$1)"; }
MAX_ITERS="$(read_cfg "['hard_limits']['max_iterations']")"
MAX_RUNTIME="$(read_cfg "['hard_limits']['max_runtime_seconds']")"
STOP_SENTINEL="$(read_cfg "['paths']['stop_sentinel']")"
STATE_FILE="$(read_cfg "['paths']['state']")"

START="$(date +%s)"
ITER=1

# The prompt is the SAME every cycle -- the system prompts itself via the files.
read -r -d '' CYCLE_PROMPT <<'EOF' || true
Run exactly ONE cycle of the self-prompting loop, then stop:
1. READ: read CLAUDE.md, then .orbit/STATE.md. That is your full memory -- you have no
   prior conversation.
2. PLAN: take the top item from STATE.md's task queue. For anything non-trivial, write the
   plan first.
3. ACT: delegate to the appropriate sub-agent(s) per .orbit/roles/ (use Claude Code
   subagents in .claude/agents/). Roles write artifacts to .orbit/artifacts/ and report
   back. Each role announces itself: open its report with "[role] ..." and emit to
   .orbit/activity.py; keep the checklist current (TodoWrite, and .orbit/tasks.json for
   the orbit-status dashboard) so a watcher can see who's talking and what's done.
4. EVALUATE: check the output against CLAUDE.md section 3 and the eval gates in
   .orbit/loop.config.json (input / quality / safety). Safety has veto power.
5. UPDATE: overwrite STATE.md's snapshot/queue/handoffs, append one line to the cycle log
   and any new decisions.
6. DECIDE: if the run goal is met -> write the line "RUN_GOAL_MET" at the end of STATE.md.
   If a human-approval checkpoint or a blocker is hit -> write "AWAITING_HUMAN: <reason>"
   at the end of STATE.md. Otherwise leave the next task queued for the next cycle.

Respect every limit in loop.config.json. Never take a FORBIDDEN action (e.g. moving
money). Never take an irreversible, financial, or outward-facing action without a human --
propose it via STATE.md instead. Then STOP; do not start another cycle yourself.
EOF

echo "Ralph loop starting: max_iters=$MAX_ITERS max_runtime=${MAX_RUNTIME}s"
echo "Tip: in another pane, run  scripts/orbit-status --follow  to watch who's talking live."

while :; do
  # --- hard limits, checked before every cycle (the brake) --------------------------
  if [ -f "$STOP_SENTINEL" ]; then echo "[STOP] sentinel $STOP_SENTINEL present"; break; fi
  if [ "$ITER" -gt "$MAX_ITERS" ]; then echo "[STOP] max_iterations ($MAX_ITERS) reached"; break; fi
  NOW="$(date +%s)"; ELAPSED=$((NOW - START))
  if [ "$ELAPSED" -ge "$MAX_RUNTIME" ]; then echo "[STOP] max_runtime (${MAX_RUNTIME}s) reached"; break; fi

  echo "=== cycle $ITER (elapsed ${ELAPSED}s) ==="

  # --- one fresh-context cycle ------------------------------------------------------
  # --print/-p runs headless; the agent's memory is the files, not this process.
  if ! claude -p "$CYCLE_PROMPT"; then
    echo "[STOP] claude exited non-zero on cycle $ITER"; break
  fi

  # --- check the sentinels the agent may have written to STATE.md -------------------
  if [ -f "$STATE_FILE" ]; then
    if grep -q "RUN_GOAL_MET" "$STATE_FILE"; then echo "[DONE] run goal met"; break; fi
    if grep -q "AWAITING_HUMAN" "$STATE_FILE"; then
      echo "[PAUSE] awaiting human:"; grep "AWAITING_HUMAN" "$STATE_FILE"; break
    fi
  fi

  ITER=$((ITER + 1))
done

echo "Ralph loop ended after $((ITER)) cycle(s), $(( $(date +%s) - START ))s."
