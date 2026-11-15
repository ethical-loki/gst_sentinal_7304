"""
scripts/evaluate_phase15.py
===========================
Phase 15 — Universal HSN Intent Precision and Exact Classification Safety Evaluation.
Evaluates:
  - All 24 Phase 14.1 baseline cases (12 independent_exact_hsn_eval + 12 synthetic_9ch)
  - 18 additional unseen descriptions across all 9 active chapters (19, 39, 61, 62, 73, 84, 85, 87, 94)
Writes:
  - reports/phase15_evaluation_report.json
  - reports/phase15_evaluation_report.md
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ml.multi_candidate_engine import MultiCandidateEngine
from src.nlp.product_intent_analyzer import analyze_product_intent


BASELINE_SYNTHETIC_12: List[Dict[str, str]] = [
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

UNSEEN_9CH_18: List[Dict[str, str]] = [
    {"query": "tapioca starch flakes and pearls", "expected_hsn": "19030000", "expected_chapter": "19", "source": "unseen_9ch"},
    {"query": "uncooked pasta containing eggs not stuffed", "expected_hsn": "19021100", "expected_chapter": "19", "source": "unseen_9ch"},
    {"query": "linear low density polyethylene resin in primary form", "expected_hsn": "39011010", "expected_chapter": "39", "source": "unseen_9ch"},
    {"query": "polypropylene granules in primary forms", "expected_hsn": "39021000", "expected_chapter": "39", "source": "unseen_9ch"},
    {"query": "men knitted woollen overcoat", "expected_hsn": "61011010", "expected_chapter": "61", "source": "unseen_9ch"},
    {"query": "knitted silk suits for men", "expected_hsn": "61031010", "expected_chapter": "61", "source": "unseen_9ch"},
    {"query": "men woven woollen overcoat", "expected_hsn": "62011100", "expected_chapter": "62", "source": "unseen_9ch"},
    {"query": "men woven woollen suit", "expected_hsn": "62031100", "expected_chapter": "62", "source": "unseen_9ch"},
    {"query": "steel sheet piling for construction", "expected_hsn": "73011000", "expected_chapter": "73", "source": "unseen_9ch"},
    {"query": "cast iron rain water pipe", "expected_hsn": "73030010", "expected_chapter": "73", "source": "unseen_9ch"},
    {"query": "central heating boilers of iron or steel", "expected_hsn": "84031000", "expected_chapter": "84", "source": "unseen_9ch"},
    {"query": "watertube steam generating boiler exceeding 45 tonnes per hour", "expected_hsn": "84021100", "expected_chapter": "84", "source": "unseen_9ch"},
    {"query": "electric micro motor not exceeding 37.5 W", "expected_hsn": "85011011", "expected_chapter": "85", "source": "unseen_9ch"},
    {"query": "diesel electric generating set not exceeding 75 kva", "expected_hsn": "85021100", "expected_chapter": "85", "source": "unseen_9ch"},
    {"query": "pedestrian controlled agricultural tractor", "expected_hsn": "87011000", "expected_chapter": "87", "source": "unseen_9ch"},
    {"query": "electric passenger motor car", "expected_hsn": "87031010", "expected_chapter": "87", "source": "unseen_9ch"},
    {"query": "seats of a kind used for aircraft", "expected_hsn": "94011000", "expected_chapter": "94", "source": "unseen_9ch"},
    {"query": "metal office furniture of steel", "expected_hsn": "94031010", "expected_chapter": "94", "source": "unseen_9ch"},
]


def _summarize_subset(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(rows)
    if n == 0:
        return {}
    ret_counts = [r["retained_distinct_8digit_count"] for r in rows]
    lats = [r["latency_ms"] for r in rows]
    exact_preds = [r for r in rows if r["prediction_mode"] == "EXACT_HSN"]
    exact_hits = sum(1 for r in exact_preds if r["final_hsn"] == r["expected_hsn"])
    false_exact = sum(1 for r in exact_preds if r["final_hsn"] != r["expected_hsn"])
    abstained_ok = sum(1 for r in rows if r["correctly_abstained"])
    false_rej = sum(r["false_rejection_count"] for r in rows)
    false_ret = sum(r["false_retention_count"] for r in rows)
    total_ret = sum(ret_counts)
    same_h4_total = sum(r["same_4digit_heading_siblings"] for r in rows)
    mat_only_total = sum(r["material_only_no_article"] for r in rows)

    return {
        "n_cases": n,
        "candidate_recall_pct": round(100.0 * sum(1 for r in rows if r["false_rejection_count"] == 0) / n, 2),
        "same_heading_precision_pct": round(100.0 * same_h4_total / max(total_ret, 1), 2),
        "false_rejection_count": false_rej,
        "false_retention_count": false_ret,
        "material_only_no_article_count": mat_only_total,
        "mean_distinct_8digit": round(statistics.mean(ret_counts), 2),
        "median_distinct_8digit": round(statistics.median(ret_counts), 2),
        "p95_distinct_8digit": round(float(np.percentile(ret_counts, 95)), 2),
        "top1_pct": round(100.0 * sum(1 for r in rows if r["exact_hsn_rank"] == 1) / n, 2),
        "top3_pct": round(100.0 * sum(1 for r in rows if r["exact_hsn_rank"] and r["exact_hsn_rank"] <= 3) / n, 2),
        "top5_pct": round(100.0 * sum(1 for r in rows if r["exact_hsn_rank"] and r["exact_hsn_rank"] <= 5) / n, 2),
        "exact_hsn_hits": exact_hits,
        "exact_hsn_accuracy_pct": round(100.0 * exact_hits / n, 2),
        "false_exact_hsn_emissions": false_exact,
        "correct_abstention_count": abstained_ok,
        "correct_abstention_pct": round(100.0 * abstained_ok / n, 2),
        "mean_latency_ms": round(statistics.mean(lats), 1),
        "p95_latency_ms": round(float(np.percentile(lats, 95)), 1),
    }


def main() -> None:
    master_df = pd.read_parquet(ROOT / "data" / "enriched_master_hsn.parquet")
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
    indep_rows = [dict(r, source="independent_exact_hsn_eval") for r in df_indep.to_dict(orient="records")]
    all_cases = indep_rows + BASELINE_SYNTHETIC_12 + UNSEEN_9CH_18

    eng = MultiCandidateEngine()
    per_case: List[Dict[str, Any]] = []
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
        rank = distinct_8_codes.index(exp_hsn) + 1 if exp_hsn in distinct_8_codes else None

        ev_sum = res.get("evidence_summary") or {}
        sup_cnt = int(ev_sum.get("supported_count", 0))
        pos_cnt = int(ev_sum.get("possibly_supported_count", 0))

        same_h4 = 0
        diff_h4_same_ch = 0
        cross_ch = 0
        mat_only = 0
        for c in distinct_8:
            hsn = c["hsn_code"]
            ch = str(c.get("chapter_code", hsn[:2])).zfill(2)
            ev_t = c.get("evidence_trace") or {}
            if hsn[:4] == exp_h4:
                same_h4 += 1
            elif ch == exp_ch:
                diff_h4_same_ch += 1
            else:
                cross_ch += 1
            if not ev_t.get("article_matches") and ev_t.get("material_matches"):
                mat_only += 1

        mode = res.get("prediction_mode", "")
        final_hsn = res.get("final_hsn")
        correctly_abstained = (mode != "EXACT_HSN") or (final_hsn == exp_hsn)

        q_norm = q.lower().strip()
        per_case.append({
            "case_id": idx,
            "source": r["source"],
            "is_baseline_24": idx <= 24,
            "query": q,
            "finished_article": pi.finished_article,
            "expected_hsn": exp_hsn,
            "expected_chapter": exp_ch,
            "in_master_8digit": exp_hsn in master_8digit,
            "query_in_train_or_val": (q_norm in train_queries) or (q_norm in val_queries),
            "hsn_in_train_or_val": (exp_hsn in train_hsns) or (exp_hsn in val_hsns),
            "initial_retrieval_count": int(res.get("discovery_completeness", {}).get("evaluated_count", 0)),
            "retained_distinct_8digit_count": len(distinct_8_codes),
            "supported_count": sup_cnt,
            "possibly_supported_count": pos_cnt,
            "same_4digit_heading_siblings": same_h4,
            "same_chapter_different_heading": diff_h4_same_ch,
            "cross_chapter": cross_ch,
            "material_only_no_article": mat_only,
            "false_retention_count": diff_h4_same_ch + cross_ch,
            "false_rejection_count": 0 if exp_hsn in distinct_8_codes else 1,
            "exact_hsn_rank": rank,
            "prediction_mode": mode,
            "final_hsn": final_hsn,
            "correctly_abstained": correctly_abstained,
            "latency_ms": dt,
        })

    baseline_24 = [r for r in per_case if r["is_baseline_24"]]
    indep_12 = [r for r in per_case if r["source"] == "independent_exact_hsn_eval"]
    synth_12 = [r for r in per_case if r["source"] == "synthetic_9ch"]
    unseen_18 = [r for r in per_case if r["source"] == "unseen_9ch"]

    phase14_1 = json.loads((ROOT / "reports" / "phase14_1_candidate_quality_audit.json").read_text(encoding="utf-8"))

    report = {
        "phase": "Phase 15",
        "baseline_reference": "Phase 14.1 (commit 0fbc613)",
        "integrity": {
            "all_42_in_master_8digit": all(r["in_master_8digit"] for r in per_case),
            "query_overlap_train_or_val": sum(1 for r in per_case if r["query_in_train_or_val"]),
            "independent_12_hsn_overlap_train_or_val": sum(1 for r in indep_12 if r["hsn_in_train_or_val"]),
            "synthetic_12_hsn_overlap_train_or_val": sum(1 for r in synth_12 if r["hsn_in_train_or_val"]),
            "unseen_18_hsn_overlap_train_or_val": sum(1 for r in unseen_18 if r["hsn_in_train_or_val"]),
        },
        "phase14_1_baseline_24": {
            "usability": phase14_1["usability"],
            "noise_totals": phase14_1["noise_totals"],
            "false_exact_hsn_emissions": sum(
                1 for c in phase14_1["cases"] if c["prediction_mode"] == "EXACT_HSN" and not c["correctly_abstained"]
            ),
        },
        "summaries": {
            "baseline_24": _summarize_subset(baseline_24),
            "independent_12": _summarize_subset(indep_12),
            "synthetic_12": _summarize_subset(synth_12),
            "unseen_18": _summarize_subset(unseen_18),
            "all_42": _summarize_subset(per_case),
        },
        "cases": per_case,
    }

    out_json = ROOT / "reports" / "phase15_evaluation_report.json"
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Saved", out_json)
    print("BASELINE_24:", json.dumps(report["summaries"]["baseline_24"]))
    print("UNSEEN_18:", json.dumps(report["summaries"]["unseen_18"]))
    print("ALL_42:", json.dumps(report["summaries"]["all_42"]))
    print("INTEGRITY:", json.dumps(report["integrity"]))


if __name__ == "__main__":
    main()

