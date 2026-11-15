"""
scripts/audit_phase14_candidate_quality.py
==========================================
Phase 14.1 — Candidate Quality Diagnostic Audit (read-only; no production changes).
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ml.multi_candidate_engine import MultiCandidateEngine
from src.nlp.product_intent_analyzer import analyze_product_intent


def main() -> None:
    master_df = pd.read_parquet(ROOT / "data" / "enriched_master_hsn.parquet")
    master_hsns = set(master_df["hsn_code"].astype(str).str.strip())
    master_8digit = set(
        master_df.loc[master_df["code_length"] == 8, "hsn_code"].astype(str).str.strip()
    )

    train_df = pd.read_parquet(ROOT / "data" / "training_pairs" / "full_pairs_train.parquet")
    val_df = pd.read_parquet(ROOT / "data" / "training_pairs" / "full_pairs_val.parquet")
    train_queries = set(train_df["query"].astype(str).str.lower().str.strip()) if "query" in train_df.columns else set()
    val_queries = set(val_df["query"].astype(str).str.lower().str.strip()) if "query" in val_df.columns else set()
    train_hsns = set(train_df["hsn_code"].astype(str).str.strip()) if "hsn_code" in train_df.columns else set()
    val_hsns = set(val_df["hsn_code"].astype(str).str.strip()) if "hsn_code" in val_df.columns else set()

    df_indep = pd.read_parquet(ROOT / "data" / "eval" / "independent_exact_hsn_eval.parquet")
    extra_cases = [
        {"query": "instant noodles made from wheat flour", "expected_hsn": "19023010", "expected_chapter": "19", "source": "synthetic_9ch"},
        {"query": "sweet biscuits containing cocoa", "expected_hsn": "19053100", "expected_chapter": "19", "source": "synthetic_9ch"},
        {"query": "plastic water bottle made of polyethylene", "expected_hsn": "39233090", "expected_chapter": "39", "source": "synthetic_9ch"},
        {"query": "knitted cotton t-shirt for men", "expected_hsn": "61091000", "expected_chapter": "61", "source": "synthetic_9ch"},
        {"query": "knitted woollen sweater pullover", "expected_hsn": "61101110", "expected_chapter": "61", "source": "synthetic_9ch"},
        {"query": "woven cotton shirt for men", "expected_hsn": "62052000", "expected_chapter": "62", "source": "synthetic_9ch"},
        {"query": "stainless steel screws and bolts", "expected_hsn": "73181500", "expected_chapter": "73", "source": "synthetic_9ch"},
        {"query": "seamless stainless steel tubes and pipes", "expected_hsn": "73044900", "expected_chapter": "73", "source": "synthetic_9ch"},
        {"query": "brake pads for passenger motor cars", "expected_hsn": "87083000", "expected_chapter": "87", "source": "synthetic_9ch"},
        {"query": "safety air bags with inflator system for motor vehicles", "expected_hsn": "87089500", "expected_chapter": "87", "source": "synthetic_9ch"},
        {"query": "swivel office chair with variable height adjustment", "expected_hsn": "94013000", "expected_chapter": "94", "source": "synthetic_9ch"},
        {"query": "wooden bedroom furniture bed", "expected_hsn": "94035010", "expected_chapter": "94", "source": "synthetic_9ch"},
    ]
    indep_rows = [dict(r, source="independent_exact_hsn_eval") for r in df_indep.to_dict(orient="records")]
    all_cases = indep_rows + extra_cases

    eng = MultiCandidateEngine()
    per_case = []
    retained_counts = []
    top1_hits = 0
    top3_hits = 0
    top5_hits = 0
    clar_reducible = 0
    noise_totals = Counter()

    for idx, r in enumerate(all_cases, start=1):
        q = str(r["query"])
        exp_hsn = str(r["expected_hsn"]).strip()
        exp_ch = str(r["expected_chapter"]).strip().zfill(2)
        exp_h4 = exp_hsn[:4]

        pi = analyze_product_intent(q)
        t0 = time.perf_counter()
        res = eng.classify_adaptive(q, page=1, page_size=None)
        dt = round((time.perf_counter() - t0) * 1000.0, 1)

        cands = res.get("candidates", [])
        distinct_8 = [c for c in cands if len(str(c.get("hsn_code", ""))) >= 8]
        distinct_8_codes = list(dict.fromkeys(c["hsn_code"] for c in distinct_8))
        n_ret = len(distinct_8_codes)
        retained_counts.append(n_ret)

        ev_sum = res.get("evidence_summary") or {}
        init_ret = int(ev_sum.get("initial_retrieved") or res["discovery"]["total_retrieved"])
        supp_c = int(ev_sum.get("supported_count") or 0)
        poss_c = int(ev_sum.get("possibly_supported_count") or 0)

        rank = (distinct_8_codes.index(exp_hsn) + 1) if exp_hsn in distinct_8_codes else None
        false_rej = 0 if rank is not None else 1
        if rank == 1:
            top1_hits += 1
        if rank is not None and rank <= 3:
            top3_hits += 1
        if rank is not None and rank <= 5:
            top5_hits += 1

        # Noise / relevance breakdown of retained 8-digit candidates
        same_h4 = 0
        same_ch_diff_h4 = 0
        cross_ch = 0
        mat_only = 0
        for c in cands:
            hc = str(c.get("hsn_code", ""))
            ch = str(c.get("chapter_code", "")).zfill(2)
            ev_t = c.get("evidence_trace") or {}
            art_m = ev_t.get("article_matches") or []
            mat_m = ev_t.get("material_matches") or []
            if hc[:4] == exp_h4:
                same_h4 += 1
            elif ch == exp_ch:
                same_ch_diff_h4 += 1
            else:
                cross_ch += 1
            if not art_m and mat_m:
                mat_only += 1

        # False retention = retained candidates outside the expected 4-digit heading
        # (conservatively separating genuine same-heading siblings from cross-heading/cross-chapter noise)
        false_ret = same_ch_diff_h4 + cross_ch

        noise_totals["same_4digit_heading_siblings"] += same_h4
        noise_totals["same_chapter_different_heading"] += same_ch_diff_h4
        noise_totals["cross_chapter"] += cross_ch
        noise_totals["material_only_no_article"] += mat_only

        mode = res.get("prediction_mode")
        final_hsn = res.get("final_hsn")
        if mode == "EXACT_HSN":
            correctly_abstained = (final_hsn == exp_hsn)
        else:
            correctly_abstained = True

        clar_req = bool((res.get("clarification") or {}).get("required"))
        if clar_req and n_ret > 1:
            clar_reducible += 1

        q_low = q.lower().strip()
        per_case.append({
            "case_id": idx,
            "source": r["source"],
            "query": q,
            "finished_article": pi.finished_article,
            "expected_hsn": exp_hsn,
            "expected_chapter": exp_ch,
            "in_master_8digit": exp_hsn in master_8digit,
            "query_in_train": q_low in train_queries,
            "query_in_val": q_low in val_queries,
            "hsn_in_train": exp_hsn in train_hsns,
            "hsn_in_val": exp_hsn in val_hsns,
            "initial_retrieval_count": init_ret,
            "retained_distinct_8digit_count": n_ret,
            "supported_count": supp_c,
            "possibly_supported_count": poss_c,
            "same_4digit_heading_siblings": same_h4,
            "same_chapter_different_heading": same_ch_diff_h4,
            "cross_chapter": cross_ch,
            "material_only_no_article": mat_only,
            "false_retention_count": false_ret,
            "false_rejection_count": false_rej,
            "exact_hsn_rank": rank,
            "prediction_mode": mode,
            "final_hsn": final_hsn,
            "correctly_abstained": correctly_abstained,
            "clarification_required": clar_req,
            "separating_attributes": (res.get("clarification") or {}).get("separating_attributes", []),
            "latency_ms": dt,
        })

    n = len(per_case)
    usability = {
        "mean_distinct_8digit": round(statistics.mean(retained_counts), 2),
        "median_distinct_8digit": round(statistics.median(retained_counts), 2),
        "p95_distinct_8digit": round(float(np.percentile(retained_counts, 95)), 2),
        "cases_gt_5": sum(1 for x in retained_counts if x > 5),
        "cases_gt_10": sum(1 for x in retained_counts if x > 10),
        "cases_gt_20": sum(1 for x in retained_counts if x > 20),
        "cases_gt_30": sum(1 for x in retained_counts if x > 30),
        "top1_pct": round(100.0 * top1_hits / n, 2),
        "top3_pct": round(100.0 * top3_hits / n, 2),
        "top5_pct": round(100.0 * top5_hits / n, 2),
        "clarification_reducible_pct": round(100.0 * clar_reducible / n, 2),
    }

    integrity = {
        "all_24_in_master_8digit": all(c["in_master_8digit"] for c in per_case),
        "query_overlap_train": sum(1 for c in per_case if c["query_in_train"]),
        "query_overlap_val": sum(1 for c in per_case if c["query_in_val"]),
        "hsn_overlap_train": sum(1 for c in per_case if c["hsn_in_train"]),
        "hsn_overlap_val": sum(1 for c in per_case if c["hsn_in_val"]),
        "independent_12_hsn_overlap_train": sum(1 for c in per_case[:12] if c["hsn_in_train"]),
        "independent_12_hsn_overlap_val": sum(1 for c in per_case[:12] if c["hsn_in_val"]),
    }

    report = {
        "total_cases": n,
        "usability": usability,
        "noise_totals": dict(noise_totals),
        "integrity": integrity,
        "cases": per_case,
    }
    out_json = ROOT / "reports" / "phase14_1_candidate_quality_audit.json"
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("AUDIT_SUMMARY:", json.dumps({"usability": usability, "noise_totals": dict(noise_totals), "integrity": integrity}, indent=2))


if __name__ == "__main__":
    main()

