"""
scripts/eval_additional_commercial.py
=====================================
Additional 20-case independently authored commercial product description validation
across 20 distinct statutory chapters (04..96), verified zero overlap with
INDEPENDENT_100, full_pairs_train/val, and independent_exact_hsn_eval.parquet.
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.benchmark_phase17_independent import INDEPENDENT_100
from src.ml.multi_candidate_engine import MultiCandidateEngine

ADDITIONAL_COMMERCIAL_20: List[Dict[str, str]] = [
    {"query": "powdered infant milk food formula packed for retail", "expected_hsn": "04021020", "expected_chapter": "04"},
    {"query": "unroasted non-decaffeinated coffee beans grade c", "expected_hsn": "09011113", "expected_chapter": "09"},
    {"query": "common milling wheat grain in bulk", "expected_hsn": "10019910", "expected_chapter": "10"},
    {"query": "natural amorphous graphite powder flake", "expected_hsn": "25041020", "expected_chapter": "25"},
    {"query": "dried organo-therapeutic gland extract of human origin", "expected_hsn": "30019010", "expected_chapter": "30"},
    {"query": "natural rubber pale crepe raw sheet", "expected_hsn": "40012920", "expected_chapter": "40"},
    {"query": "uncoated handmade paperboard sheets", "expected_hsn": "48021020", "expected_chapter": "48"},
    {"query": "knitted 100% cotton bed linen sheet", "expected_hsn": "63021010", "expected_chapter": "63"},
    {"query": "waterproof rubber ankle boots with moulded outer soles", "expected_hsn": "64019210", "expected_chapter": "64"},
    {"query": "ceramic thermal insulating roof tiles", "expected_hsn": "69010030", "expected_chapter": "69"},
    {"query": "unworked borosilicate glass tubing with low thermal expansion", "expected_hsn": "70023200", "expected_chapter": "70"},
    {"query": "ferro-silico-manganese alloy lumps for steelmaking", "expected_hsn": "72023000", "expected_chapter": "72"},
    {"query": "smelted copper matte intermediate metallurgical product", "expected_hsn": "74011000", "expected_chapter": "74"},
    {"query": "unwrought unalloyed pure aluminium wire bars", "expected_hsn": "76011030", "expected_chapter": "76"},
    {"query": "manual metal cutting hacksaw hand saw", "expected_hsn": "82021010", "expected_chapter": "82"},
    {"query": "spare cylinder and lock body parts for padlocks", "expected_hsn": "83016000", "expected_chapter": "83"},
    {"query": "self-propelled railway track inspection maintenance vehicle", "expected_hsn": "86040000", "expected_chapter": "86"},
    {"query": "unmounted optical calcite crystal lens prism element", "expected_hsn": "90019010", "expected_chapter": "90"},
    {"query": "collectible metal figurine doll representing human character", "expected_hsn": "95021020", "expected_chapter": "95"},
    {"query": "carved vegetable nut ivory decorative article", "expected_hsn": "96020010", "expected_chapter": "96"},
]


def main() -> None:
    master_df = pd.read_parquet(ROOT / "data" / "enriched_master_hsn.parquet")
    master_8digit = set(master_df.loc[master_df["code_length"] == 8, "hsn_code"].astype(str).str.strip())

    used_hsns = {r["expected_hsn"] for r in INDEPENDENT_100}
    used_queries = {r["query"].lower().strip() for r in INDEPENDENT_100}
    for fname in ("full_pairs_train.parquet", "full_pairs_val.parquet"):
        tdf = pd.read_parquet(ROOT / "data" / "training_pairs" / fname)
        used_hsns.update(tdf["hsn_code"].astype(str).str.strip())
        used_queries.update(tdf["query"].astype(str).str.lower().str.strip())
    eval_df = pd.read_parquet(ROOT / "data" / "eval" / "independent_exact_hsn_eval.parquet")
    used_hsns.update(eval_df["expected_hsn"].astype(str).str.strip())

    for r in ADDITIONAL_COMMERCIAL_20:
        assert r["expected_hsn"] in master_8digit, f"{r['expected_hsn']} not 8-digit master leaf"
        assert r["expected_hsn"] not in used_hsns, f"Leakage: {r['expected_hsn']}"
        assert r["query"].lower().strip() not in used_queries, f"Query leakage: {r['query']}"

    eng = MultiCandidateEngine.get_instance()
    _ = eng.classify_adaptive("stainless steel screws", page=1, page_size=5)

    per_case: List[Dict[str, Any]] = []
    for idx, r in enumerate(ADDITIONAL_COMMERCIAL_20, start=1):
        q = r["query"]
        exp_hsn = r["expected_hsn"]
        exp_ch = r["expected_chapter"]
        t0 = time.perf_counter()
        res = eng.classify_adaptive(q, page=1, page_size=None)
        dt = round((time.perf_counter() - t0) * 1000.0, 1)

        cands = res.get("candidates", [])
        distinct_8 = [c for c in cands if len(str(c.get("hsn_code", ""))) >= 8]
        codes = list(dict.fromkeys(c["hsn_code"] for c in distinct_8))
        rank = codes.index(exp_hsn) + 1 if exp_hsn in codes else None
        top_ch = distinct_8[0].get("chapter_code", "").zfill(2) if distinct_8 else (res.get("final_chapter") or "")
        mode = res.get("prediction_mode", "")
        final_hsn = res.get("final_hsn")

        per_case.append({
            "case_id": idx,
            "query": q,
            "expected_hsn": exp_hsn,
            "expected_chapter": exp_ch,
            "top_chapter": top_ch,
            "chapter_hit": top_ch == exp_ch,
            "retained_8digit": len(codes),
            "recall_hit": exp_hsn in codes,
            "rank": rank,
            "prediction_mode": mode,
            "final_hsn": final_hsn,
            "exact_hit": mode == "EXACT_HSN" and final_hsn == exp_hsn,
            "false_exact": mode == "EXACT_HSN" and final_hsn != exp_hsn,
            "correctly_abstained": (mode != "EXACT_HSN") or (final_hsn == exp_hsn),
            "latency_ms": dt,
        })

    n = len(per_case)
    lats = [r["latency_ms"] for r in per_case]
    exact_preds = [r for r in per_case if r["prediction_mode"] == "EXACT_HSN"]
    summary = {
        "total_cases": n,
        "distinct_chapters": len({r["expected_chapter"] for r in per_case}),
        "zero_leakage_verified": True,
        "chapter_accuracy_pct": round(100.0 * sum(1 for r in per_case if r["chapter_hit"]) / n, 2),
        "candidate_recall_pct": round(100.0 * sum(1 for r in per_case if r["recall_hit"]) / n, 2),
        "recall_at_5_pct": round(100.0 * sum(1 for r in per_case if r["rank"] and r["rank"] <= 5) / n, 2),
        "recall_at_10_pct": round(100.0 * sum(1 for r in per_case if r["rank"] and r["rank"] <= 10) / n, 2),
        "top1_pct": round(100.0 * sum(1 for r in per_case if r["rank"] == 1) / n, 2),
        "exact_hsn_hits": sum(1 for r in per_case if r["exact_hit"]),
        "exact_hsn_coverage_pct": round(100.0 * sum(1 for r in per_case if r["exact_hit"]) / n, 2),
        "exact_hsn_precision_pct": round(100.0 * sum(1 for r in exact_preds if r["exact_hit"]) / len(exact_preds), 2) if exact_preds else 100.0,
        "false_exact_count": sum(1 for r in per_case if r["false_exact"]),
        "correct_abstention_pct": round(100.0 * sum(1 for r in per_case if r["correctly_abstained"]) / n, 2),
        "mean_latency_ms": round(statistics.mean(lats), 1),
        "median_latency_ms": round(statistics.median(lats), 1),
        "p95_latency_ms": round(float(np.percentile(lats, 95)), 1),
        "cases": per_case,
    }
    out = ROOT / "reports" / "final_closure_additional_commercial.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("Saved", out)
    print({k: v for k, v in summary.items() if k != "cases"})


if __name__ == "__main__":
    main()
