# Independent QA stage

Orbit can require a second model/provider to evaluate committed work after its internal Safety,
Reviewer, and QA gates. This is a pipeline stage, not another implementation worker.

1. Before implementation, the Planner copies `.orbit/review-requests/TEMPLATE.json`, records the
   measurable acceptance criteria and the pre-manifest `baseline_commit`, obtains founder/authorized
   approval, then commits the armed manifest by itself. Implementation starts in a later commit.
2. The implementation agent commits the candidate and reports the commit plus request path.
3. Orbit runs `scripts/orbit-independent-qa review --request <path> --commit <sha>`. The wrapper resolves
   the engine from the trusted Orbit installation, then creates a
   detached temporary worktree at that exact commit and invokes the configured reviewer adapter.
4. P0/P1 findings, any failed required criterion, a low score, or a non-PASS verdict route back to
   repair. Every repaired commit requires a fresh independent review.
5. `scripts/orbit-independent-qa gate ...` is the mechanical release check. Request edits change the hash
   and invalidate earlier approval.

The stock adapter uses `codex exec`, but `provider.argv` is an argv-array contract and can point to any
reviewer that writes the result schema. Orbit never uses a shell for it.

At install, `bin/orbit-qa-configure` detects runnable Codex/Claude CLIs and stores the one-time default
under `$ORBIT_HOME/qa.json`. Choices are `codex`, `claude`, `both`, or `later`. A project receives only
that provider preference when scaffolded and may override it thereafter; it remains disabled and export
remains unapproved until the project explicitly consents. Claude QA is a fresh, non-persistent,
isolated internal review; Codex is an independent-provider review. `both` requires both verdicts to pass
and aggregates the lower score/worst criterion. A missing selected provider blocks—fallback always needs
human approval. Arabic/RTL detection activates the same project rubric regardless of provider.

Private code export is disabled by default. The runner reads the request and schema from Git—not the
working tree—and verifies the Git sequence baseline → armed-manifest commit → implementation commit.
The authoritative verdict is stored under Git's Orbit control plane, outside the implementation
checkout; `.orbit/reviews/` is only a human-readable mirror. The project agent cannot replace the
trusted engine or self-author a passing mirror. The runner
also rejects later manifest edits. Activating the stage requires both
`independent_qa.enabled=true` and `external_export.approved=true`, with scope fixed to
`committed_snapshot_only`; record `approved_by` and `approved_at` as an auditable consent receipt.
Uncommitted files are never copied into the review worktree. The reviewer is
report-only and must not edit, commit, push, merge, deploy, message, or approve its own implementation.
The runner publishes its current exact-commit status to Git's control plane for the dashboard tracer;
a project mirror, stale commit verdict, or newer file modification time never drives pipeline state.

Project-specific checks belong in rubric files listed by the request—for example GTM lead coverage,
Arabic UI content quality, or prompt/evidence standards. Orbit owns the lifecycle and binding; the
product repository owns its domain oracle.
