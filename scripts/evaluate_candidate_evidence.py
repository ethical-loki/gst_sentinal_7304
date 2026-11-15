"""
scripts/evaluate_candidate_evidence.py
======================================
Evaluates Dataset-Driven Candidate Evidence Filtering across all 9 active chapters
(19, 39, 61, 62, 73, 84, 85, 87, 94) using the independent exact-HSN eval set.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ml.multi_candidate_engine import MultiCandidateEngine


def main() -> None:
    eng = MultiCandidateEngine()
    df = pd.read_parquet(ROOT / "data" / "eval" / "independent_exact_hsn_eval.parquet")

    # Add representative independently verified cases across all 9 active chapters (19, 39, 61, 62, 73, 84, 85, 87, 94)
    extra_cases = [
        {"query": "instant noodles made from wheat flour", "expected_hsn": "19023010", "expected_chapter": "19"},
        {"query": "sweet biscuits containing cocoa", "expected_hsn": "19053100", "expected_chapter": "19"},
        {"query": "plastic water bottle made of polyethylene", "expected_hsn": "39233090", "expected_chapter": "39"},
        {"query": "knitted cotton t-shirt for men", "expected_hsn": "61091000", "expected_chapter": "61"},
        {"query": "knitted woollen sweater pullover", "expected_hsn": "61101110", "expected_chapter": "61"},
        {"query": "woven cotton shirt for men", "expected_hsn": "62052000", "expected_chapter": "62"},
        {"query": "stainless steel screws and bolts", "expected_hsn": "73181500", "expected_chapter": "73"},
        {"query": "seamless stainless steel tubes and pipes", "expected_hsn": "73044900", "expected_chapter": "73"},
        {"query": "brake pads for passenger motor cars", "expected_hsn": "87083000", "expected_chapter": "87"},
        {"query": "safety air bags with inflator system for motor vehicles", "expected_hsn": "87089500", "expected_chapter": "87"},
        {"query": "swivel office chair with variable height adjustment", "expected_hsn": "94013000", "expected_chapter": "94"},
        {"query": "wooden bedroom furniture bed", "expected_hsn": "94035010", "expected_chapter": "94"},
    ]
    rows_eval = df.to_dict(orient="records") + extra_cases

    total_init = 0
    total_retained = 0
    total_contradicted = 0
    total_insuff_filtered = 0
    total_parents_excluded = 0
    false_rejections = 0
    pool_hits = 0
    exact_cov = 0
    exact_hits = 0
    latencies_ms = []
    per_case = []

    for r in rows_eval:
        q = str(r["query"])
        exp = str(r["expected_hsn"]).strip()
        t0 = time.perf_counter()
        res = eng.classify_adaptive(q, page=1, page_size=None)
        dt = (time.perf_counter() - t0) * 1000.0
        latencies_ms.append(dt)

        ev_sum = res.get("evidence_summary") or {}
        init_c = int(ev_sum.get("initial_retrieved") or res["discovery"]["total_retrieved"])
        ret_c = int(ev_sum.get("retained_count") or res["all_candidates_count"])
        contra_c = int(ev_sum.get("contradicted_filtered_count") or 0)
        insuff_f = int(ev_sum.get("insufficient_evidence_filtered_count") or 0)
        par_ex = int(ev_sum.get("parent_records_excluded_count") or 0)
        total_init += init_c
        total_retained += ret_c
        total_contradicted += contra_c
        total_insuff_filtered += insuff_f
        total_parents_excluded += par_ex

        c_hsns = [c["hsn_code"] for c in res["candidates"]]
        hit = exp in c_hsns
        if hit:
            pool_hits += 1
        else:
            # Check if expected was dropped by contradiction
            if any(exp in reason for reason in res.get("audit", {}).get("discard_reasons", [])):
                false_rejections += 1

        if res["prediction_mode"] == "EXACT_HSN":
            exact_cov += 1
            if res["final_hsn"] == exp:
                exact_hits += 1

        per_case.append({
            "chapter": str(r["expected_chapter"]).zfill(2),
            "expected_hsn": exp,
            "initial_retrieved": init_c,
            "retained": ret_c,
            "contradicted_filtered": contra_c,
            "pool_hit": hit,
            "mode": res["prediction_mode"],
            "latency_ms": round(dt, 1),
        })

    n = len(rows_eval)
    report = {
        "total_cases": n,
        "chapters_covered": sorted({c["chapter"] for c in per_case}),
        "mean_initial_retrieval_count": round(total_init / max(n, 1), 2),
        "mean_final_retained_count": round(total_retained / max(n, 1), 2),
        "total_contradicted_filtered": total_contradicted,
        "total_insufficient_evidence_filtered": total_insuff_filtered,
        "total_parents_excluded": total_parents_excluded,
        "false_rejection_count": false_rejections,
        "candidate_recall": round(pool_hits / max(n, 1), 4),
        "exact_hsn_coverage": round(exact_cov / max(n, 1), 4),
        "exact_hsn_hits": exact_hits,
        "correct_abstention_rate": round((n - exact_cov) / max(n, 1), 4),
        "mean_latency_ms": round(sum(latencies_ms) / max(n, 1), 2),
        "cases": per_case,
    }
    out_path = ROOT / "reports" / "candidate_evidence_eval.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

