"""
eval/harness.py
────────────────
Runs the golden cases against the reasoning engine and reports the metrics that
gate releases. The lethal one is unsupported_claim_rate: if the engine ever
states a `computed` number it can't trace to retrieved evidence, that's a
hallucination and the build must not ship.

Metrics (per the product doc):
  • bucket_accuracy        — did confidence land in the expected set?
  • unsupported_claim_rate — % of computed claims not traceable to evidence (→ 0)
  • correct_refusal_rate   — of cases that SHOULD refuse, how many returned UNCERTAIN
  • intent_accuracy        — did the router pick the expected intent?
  • must_not_say_violations — forbidden phrases that appeared

Ship-blocker: unsupported_claim_rate > 0  OR  must_not_say_violations > 0.

Usage:
    PYTHONPATH=. python3 -m vinayak.eval.harness            # both companies
    PYTHONPATH=. python3 -m vinayak.eval.harness kbrushes   # one
    run_eval(conn, company_id)                              # programmatic
"""
from __future__ import annotations

import json
import sys

from vinayak.reasoning.engine import answer as reason_answer
from vinayak.memory import store as M
from vinayak.eval.cases import CASES, BOTH


def _seed(conn, company_id, facts) -> list[str]:
    """Write seed facts only if no active fact already exists for that key
    (never clobber real data). Returns ids of facts we created, to clean up."""
    created = []
    for f in facts:
        existing = [x for x in M.active_facts(conn, company_id, f["entity_ref"])
                    if x["claim_key"] == f["claim_key"] and x["status"] == "active"]
        if existing:
            continue
        fact = M.write_fact(conn, company_id, entity_type=f["entity_type"],
                            entity_ref=f["entity_ref"], claim_key=f["claim_key"],
                            claim_value=f["claim_value"], origin="imported")
        created.append(fact["id"])
    return created


def _cleanup(conn, company_id, ids):
    if not ids:
        return
    with conn.cursor() as cur:
        cur.execute("DELETE FROM memory_fact WHERE company_id = %s AND id = ANY(%s::uuid[])",
                    (company_id, ids))
    conn.commit()


def _check_case(conn, company_id, case) -> dict:
    created = _seed(conn, company_id, case.get("seed_facts", []))
    try:
        # Deterministic path: the eval gates the validated numbers/labels, which
        # the LLM phrasing layer never changes. Keeps eval fast, free, reproducible.
        a = reason_answer(conn, company_id, case["q"], use_llm=False)
    finally:
        _cleanup(conn, company_id, created)

    text = (a["answer"] + " " + " ".join(c["text"] for c in a["claims"])).lower()
    ev_ids = {e["id"] for e in a["evidence"]}

    # unsupported computed claims
    computed = [c for c in a["claims"] if c["type"] == "computed"]
    unsupported = [c for c in computed
                   if not c["evidence"] or not all(e in ev_ids for e in c["evidence"])]

    must_not = [s for s in case.get("must_not_say", []) if s.lower() in text]

    checks = {
        "intent_ok": (case.get("expect_intent") is None) or (a["intent"] == case["expect_intent"]),
        "bucket_ok": (case.get("expect_bucket") is None) or (a["confidence_level"] in case["expect_bucket"]),
        "refusal_ok": (not case.get("refusal")) or (a["confidence_level"] == "UNCERTAIN"),
        "must_not_say_ok": len(must_not) == 0,
        "no_unsupported": len(unsupported) == 0,
    }
    return {
        "id": case["id"], "company": company_id, "question": case["q"],
        "intent": a["intent"], "confidence": a["confidence_level"],
        "computed_claims": len(computed), "unsupported": len(unsupported),
        "must_not_violations": must_not,
        "checks": checks,
        "passed": all(checks.values()),
    }


def run_eval(conn, company_id: str | None = None) -> dict:
    results = []
    for case in CASES:
        companies = case.get("companies", BOTH)
        if company_id:
            companies = [company_id] if company_id in companies else []
        for cid in companies:
            results.append(_check_case(conn, cid, case))

    n = len(results) or 1
    refusal_cases = [r for r in results if any(
        c.get("refusal") for c in CASES if c["id"] == r["id"])]
    total_computed = sum(r["computed_claims"] for r in results)
    total_unsupported = sum(r["unsupported"] for r in results)
    must_not_total = sum(len(r["must_not_violations"]) for r in results)

    metrics = {
        "cases_run": len(results),
        "passed": sum(1 for r in results if r["passed"]),
        "intent_accuracy": round(sum(r["checks"]["intent_ok"] for r in results) / n, 3),
        "bucket_accuracy": round(sum(r["checks"]["bucket_ok"] for r in results) / n, 3),
        "correct_refusal_rate": (round(sum(r["checks"]["refusal_ok"] for r in refusal_cases) / len(refusal_cases), 3)
                                 if refusal_cases else 1.0),
        "unsupported_claim_rate": round(total_unsupported / total_computed, 4) if total_computed else 0.0,
        "must_not_say_violations": must_not_total,
    }
    # Ship-blocker rule.
    metrics["ship_blocked"] = metrics["unsupported_claim_rate"] > 0 or must_not_total > 0
    return {"metrics": metrics, "results": results}


if __name__ == "__main__":
    import os
    import psycopg2
    from dotenv import load_dotenv
    load_dotenv()
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cid = sys.argv[1] if len(sys.argv) > 1 else None
    report = run_eval(conn, cid)
    m = report["metrics"]
    print(json.dumps(m, indent=2))
    print(f"\n{m['passed']}/{m['cases_run']} cases passed.")
    for r in report["results"]:
        if not r["passed"]:
            failed = [k for k, v in r["checks"].items() if not v]
            print(f"  ✗ [{r['company']}] {r['id']}: {r['confidence']}/{r['intent']} — failed {failed}")
    print("\nSHIP BLOCKED" if m["ship_blocked"] else "\nOK to ship (no unsupported claims, no forbidden phrases).")
    sys.exit(1 if m["ship_blocked"] else 0)
