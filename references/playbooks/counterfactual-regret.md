# Playbook: Counterfactual Regret Gate

The Counterfactual Regret Gate is a cheap pre-build falsification pass for T2+ work. It asks what
could make the current plan look successful while being wrong, then tests one high-value assumption
before paying for implementation. It is a decision instrument, not another sub-agent or a request
for private reasoning.

## Contract

Write `.orbit/artifacts/<cycle>/counterfactual.json` with:

```json
{
  "schema": 1,
  "cycle": 1,
  "decision": "rank customers by readiness",
  "assumption": "reply speed is a useful readiness signal",
  "hypotheses": [{
    "failure": "serious customers reply slowly during work hours",
    "signal": "closed-won conversations have slower replies than lost leads",
    "probe": "compare reply-delay distributions for the last 30 won and lost conversations"
  }],
  "selected_probe": "compare reply-delay distributions for the last 30 won and lost conversations",
  "outcome": "pending",
  "backtrack": "none"
}
```

Keep at most three hypotheses. Choose the cheapest probe that could change the decision. The probe
must produce an observable result: a test, query, repository inspection, browser check, or cited
source. Do not write a generic risk list.

## Decision Rules

- `pass` -> continue to Plan or Build and record the evidence path.
- `fail` -> set `backtrack` using the failure taxonomy and return to that phase before building.
- `inconclusive` -> call the Opus Advisor only when the decision is expensive, architectural, or
  safety-sensitive; otherwise narrow the probe or ask the user.
- A repeated failed assumption is a learning candidate, not permission to quietly change the goal.

Failure routes:

| Failure kind | Return to |
| --- | --- |
| missing_evidence | discovery |
| wrong_assumption | discovery |
| architecture_risk | plan |
| implementation_defect | build |
| verification_gap | review |

## Budget and User Output

The Executor performs the gate inline. It gets one compact packet and one probe by default. No fleet
is spawned. The Advisor is a fallback for unresolved high-cost decisions, not a second routine planner.
Report only: `Assumption -> Probe -> Evidence -> Decision -> Next phase`. The board shows the probe and
the selected backtrack target when it fails.
