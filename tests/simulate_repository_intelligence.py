#!/usr/bin/env python3
"""Controlled retrieval simulation. Reports measured fixture results; extrapolation is labeled."""
import importlib.util
import json
import random
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("orbit_repo_sim", ROOT / "assets/checks/repository_intelligence.py")
intel = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(intel)


def put(root, rel, text):
    p = root / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text)


def main():
    random.seed(7)
    cases = [
        ("reschedule interview preserve panel availability", "reschedule interview preserve panel availability",
         {"services/scheduling/reschedule.py", "services/availability/panel.py", "tests/scheduling/test_reschedule.py"}),
        ("move the meeting and keep the same interviewers", "reschedule interview preserve panel availability",
         {"services/scheduling/reschedule.py", "services/availability/panel.py", "tests/scheduling/test_reschedule.py"}),
        ("candidate consent deletion audit database", "candidate consent deletion audit database",
         {"services/privacy/delete_candidate.py", "db/migrations/042_consent.sql", "tests/privacy/test_delete_candidate.py"}),
        ("honor a person's right to be forgotten with an evidence trail", "candidate consent deletion audit database",
         {"services/privacy/delete_candidate.py", "db/migrations/042_consent.sql", "tests/privacy/test_delete_candidate.py"}),
        ("offer approval API notify finance", "offer approval API notify finance",
         {"apps/api/offer_routes.ts", "services/offers/approve.py", "workers/finance/subscriber.ts"}),
        ("compensation sign-off should tell accounting", "offer approval API notify finance",
         {"apps/api/offer_routes.ts", "services/offers/approve.py", "workers/finance/subscriber.ts"}),
    ]
    with tempfile.TemporaryDirectory() as d:
        root = Path(d); (root / ".orbit").mkdir()
        # Decoys model a broad enterprise repository without consuming model context.
        for i in range(600):
            put(root, f"packages/module_{i:03d}/service_{i:03d}.py",
                f"class LedgerComponent{i}:\n    def reconcile_record_{i}(self, value):\n        return value\n" + "# stable enterprise module\n" * 30)
        put(root, "services/scheduling/reschedule.py", "from services.availability.panel import reserve_panel\ndef reschedule_interview(x):\n publish('interview.rescheduled')\n return reserve_panel(x)\n")
        put(root, "services/availability/panel.py", "def reserve_panel(interview): return interview\n")
        put(root, "tests/scheduling/test_reschedule.py", "from services.scheduling.reschedule import reschedule_interview\ndef test_reschedule_preserves_panel_availability(): pass\n")
        put(root, "services/privacy/delete_candidate.py", "def delete_candidate_consent_audit(candidate): return candidate\n")
        put(root, "db/migrations/042_consent.sql", "ALTER TABLE candidate_consent ADD COLUMN deleted_at timestamp;\n")
        put(root, "tests/privacy/test_delete_candidate.py", "from services.privacy.delete_candidate import delete_candidate_consent_audit\ndef test_candidate_consent_deletion_audit(): pass\n")
        put(root, "apps/api/offer_routes.ts", "router.post('/offers/:id/approve', approveOffer)\n")
        put(root, "services/offers/approve.py", "def approve_offer_finance(x):\n publish('offer.approved')\n return x\n")
        put(root, "workers/finance/subscriber.ts", "subscribe('offer.approved', notifyFinance)\n")
        started = time.perf_counter(); stats = intel.build(root); index_ms = (time.perf_counter()-started)*1000
        rows = []
        for goal, targeted_goal, truth in cases:
            started = time.perf_counter(); packet = intel.query(root, goal, max_tokens=1200, max_files=10); query_ms = (time.perf_counter()-started)*1000
            got = {x["path"] for x in packet["retrieval"]["files"]}
            hit = len(got & truth)
            targeted = intel.query(root, targeted_goal, max_tokens=1200, max_files=10)
            recovered = {x["path"] for x in targeted["retrieval"]["files"]}
            rows.append({"goal": goal, "truth_files": len(truth), "retrieved_files": len(got),
                         "hits": hit, "first_pass_recall": hit/len(truth), "precision": hit/max(1, len(got)),
                         "targeted_internal_query": targeted_goal if targeted_goal != goal else None,
                         "recall_after_targeted_query": len(recovered & truth)/len(truth),
                         "evidence_tokens": packet["retrieval"]["estimated_tokens"], "query_ms": round(query_ms, 1)})
        avg_recall = sum(x["first_pass_recall"] for x in rows)/len(rows)
        recovered_recall = sum(x["recall_after_targeted_query"] for x in rows)/len(rows)
        raw = stats["source_bytes"]//4; evidence = sum(x["evidence_tokens"] for x in rows)/len(rows)
        result = {"simulation": "controlled synthetic repository; not an enterprise benchmark",
                  "fixture": {"files": stats["files"], "source_bytes": stats["source_bytes"], "index_ms": round(index_ms, 1)},
                  "cases": rows,
                  "aggregate": {"first_pass_recall_at_10": round(avg_recall, 3),
                                "recall_after_internal_targeted_query": round(recovered_recall, 3),
                                "semantic_alias_cases_requiring_expansion": sum(1 for x in rows if x["targeted_internal_query"]),
                                "average_evidence_tokens": round(evidence),
                                "raw_repository_token_estimate": raw,
                                "context_reduction_percent": round((1-evidence/max(1, raw))*100, 2)},
                  "million_loc_projection": {"assumption_tokens_per_loc": "1.9-3.8 (range, not measured)",
                                             "raw_scan_tokens": "1.9M-3.8M per role",
                                             "orbit_packet_cap": 4000,
                                             "important": "Projection is arithmetic; validate recall on each real enterprise repository."}}
        print(json.dumps(result, indent=2))


if __name__ == "__main__": main()
