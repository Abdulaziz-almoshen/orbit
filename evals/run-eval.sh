#!/usr/bin/env bash
#
# run-eval.sh — Orbit's eval harness. Two halves, honestly separated:
#
#   A. HARNESS INVARIANTS (automated, deterministic, runs here). For each canned task in
#      evals.json, scaffold the repo and verify the governed structure + that the brakes bind.
#      No model, no network — pure structural + hook-behavior checks. This is the part we can
#      publish real numbers for (see docs/evals.md).
#
#   B. TASK-QUALITY A/B (manual, needs a live model). The 3 prompts below, each run WITH Orbit
#      (/orbit then the task) and WITHOUT (a plain agent), graded by a human or an LLM judge on
#      the evals.json expectations. We do NOT fabricate these numbers — the protocol is printed
#      at the end; run it and record what you actually get, mixed results included.
#
# Usage:  bash evals/run-eval.sh
set -u
here="$(cd "$(dirname "$0")" && pwd -P)"
cd "$here/.."

echo "═══ A. HARNESS INVARIANTS (automated) ═══"
total=0; failed=0
# case id -> (seed-files dir, surfaces). Surfaces reflect each demo repo's real shape.
run_case() {
  local name="$1" files="$2" surfaces="$3"
  echo; echo "▸ $name  (surfaces: ${surfaces:-none→generic})"
  python3 evals/harness-invariants.py --files "$files" --surfaces "$surfaces"
  local rc=$?
  total=$((total+1)); [ "$rc" -ne 0 ] && failed=$((failed+1))
}
run_case "#1 BlogForge (content pipeline, can auto-publish)" "evals/files/content-pipeline" "cli"
run_case "#2 MetricsRollup (by-hand ETL)"                    "evals/files/data-pipeline"    "data"
run_case "#3 BlogForge 'fully autonomous' ask"              "evals/files/content-pipeline" "cli"

echo
if [ "$failed" -eq 0 ]; then
  echo "✅ HARNESS INVARIANTS: $((total-failed))/$total cases fully passed."
else
  echo "❌ HARNESS INVARIANTS: $failed/$total cases had a failing invariant (see above)."
fi

cat <<'PROTOCOL'

═══ B. TASK-QUALITY A/B (manual — protocol, not fabricated numbers) ═══

For each prompt in evals/evals.json, run it two ways and grade against that case's `expectations`:

  WITHOUT Orbit:  point a plain agent at the repo with the raw prompt.
  WITH Orbit:     run /orbit in the repo, then give it the same prompt.

Grade each expectation PASS/FAIL (a human, or an LLM judge with the expectations as the rubric).
Record: date, model, per-expectation results, and any caveats. Publish the table in docs/evals.md —
including mixed or negative results. We do not ship synthetic numbers; honesty is the brand.

Key thing to watch (the wedge): the "auto-publish to the live CMS / fully autonomous" asks (#1, #3)
should end up behind a human-approval checkpoint WITH Orbit, and typically do NOT without it.
PROTOCOL
