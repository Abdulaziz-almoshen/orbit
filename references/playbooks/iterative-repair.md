# Playbook: Iterative Repair Loop

The repair loop is the post-build half of Orbit. A Reviewer, QA Engineer, Safety gate, or
Counterfactual probe does not merely write a report; it creates a bounded repair packet that becomes
the next executable task.

## Failure to repair

Write `.orbit/artifacts/<cycle>/repair-<id>.json`:

```json
{
  "schema": 1,
  "id": "REV-004",
  "cycle": 2,
  "attempt": 1,
  "source": "reviewer",
  "severity": "P1",
  "criterion": "AC-3",
  "evidence": "tests/test_booking.py:81 reproduces duplicate booking",
  "failure": "duplicate booking is accepted",
  "root_cause": "the uniqueness check runs after the write",
  "required_change": "validate the booking key before persistence",
  "verification": ["pytest tests/test_booking.py -q", "repeat the duplicate request"],
  "owner": "builder",
  "max_attempts": 2,
  "status": "queued"
}
```

Every packet must contain evidence, a required change, and a verification check. “Looks wrong” is
not a repair packet. The Builder receives the packet plus only the relevant files, not the full
activity log or the entire conversation.

## State machine

```text
review_failed -> repair_queued -> repairing -> retesting
                                      |            |
                                      |            +-> passed -> regression_check
                                      +-----------------------> escalated
```

- First failure: create one targeted repair task and reserve the repair budget.
- Repair: change only what the packet requires, then run its verification checks.
- Retest: the original failing check must pass, plus a focused regression check.
- Same failure twice: stop repairing, call the Advisor for an architectural diagnosis or ask the
  human. Do not keep re-running the same worker.
- A new failure gets a new packet and a new owner; never mutate the old evidence.

## Backtracking

- QA product failure -> `build`.
- Reviewer design or implementation finding -> `build`.
- Reviewer architecture finding -> `plan`.
- Missing requirement or wrong assumption -> `discovery`.
- Safety failure -> `escalated`; never auto-repair around a safety veto.

The board must show the failure ID, owner, attempt number, and next verification. The user-facing
summary is: `Failure -> Repair -> Retest -> Result`. Keep private reasoning out of the artifact.
