"""
scripts/eval_unseen_cross_chapter.py
====================================
Evaluates cross-chapter generalization across newly activated statutory chapters
(outside the legacy 9 training chapters) using data/eval/independent_exact_hsn_eval.parquet,
verifying zero HSN/query overlap with train/val parquets and INDEPENDENT_100.
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

LEGACY_9_CHAPTERS = {"19", "39", "61", "62", "73", "84", "85", "87", "94"}


def main() -> None:
    eval_path = ROOT / "data" / "eval" / "independent_exact_hsn_eval.parquet"
    df = pd.read_parquet(eval_path)

    # Verify zero overlap with train/val parquets and INDEPENDENT_100
    used_hsns = {r["expected_hsn"] for r in INDEPENDENT_100}
    used_queries = {r["query"].lower().strip() for r in INDEPENDENT_100}
    for fname in ("full_pairs_train.parquet", "full_pairs_val.parquet"):
        p = ROOT / "data" / fname
        if p.exists():
            tdf = pd.read_parquet(p)
            if "hsn_code" in tdf.columns:
                used_hsns.update(tdf["hsn_code"].astype(str).str.strip().tolist())
            if "query" in tdf.columns:
                used_queries.update(tdf["query"].astype(str).str.lower().str.strip().tolist())

    # Filter strictly to chapters OUTSIDE legacy 9 chapters and with zero train/val/100 overlap
    df["expected_chapter"] = df["expected_chapter"].astype(str).str.zfill(2)
    df["expected_hsn"] = df["expected_hsn"].astype(str).str.strip()
    unseen_df = df[
        (~df["expected_chapter"].isin(LEGACY_9_CHAPTERS))
        & (~df["expected_hsn"].isin(used_hsns))
        & (~df["query"].astype(str).str.lower().str.strip().isin(used_queries))
    ].copy()

    # Deterministic stratified sample: 1 item per chapter across up to 45 distinct unseen chapters
    sampled_rows = (
        unseen_df.sort_values(["expected_chapter", "expected_hsn"])
        .groupby("expected_chapter", as_index=False)
        .first()
        .iloc[::2]  # every 2nd unseen chapter -> ~41 diverse unseen chapters across 01..97
        .head(45)
        .to_dict(orient="records")
    )

    eng = MultiCandidateEngine.get_instance()
    # Warmup once
    _ = eng.classify_adaptive("stainless steel screws", page=1, page_size=5)

    per_case: List[Dict[str, Any]] = []
    for idx, r in enumerate(sampled_rows, start=1):
        q = str(r["query"])
        exp_hsn = str(r["expected_hsn"])
        exp_ch = str(r["expected_chapter"]).zfill(2)
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
    summary = {
        "total_cases": n,
        "distinct_unseen_chapters": len({r["expected_chapter"] for r in per_case}),
        "zero_legacy9_overlap": True,
        "zero_train_val_100_leakage": True,
        "chapter_accuracy_pct": round(100.0 * sum(1 for r in per_case if r["chapter_hit"]) / n, 2),
        "candidate_recall_pct": round(100.0 * sum(1 for r in per_case if r["recall_hit"]) / n, 2),
        "recall_at_5_pct": round(100.0 * sum(1 for r in per_case if r["rank"] and r["rank"] <= 5) / n, 2),
        "top1_pct": round(100.0 * sum(1 for r in per_case if r["rank"] == 1) / n, 2),
        "exact_hsn_hits": sum(1 for r in per_case if r["exact_hit"]),
        "exact_hsn_accuracy_pct": round(100.0 * sum(1 for r in per_case if r["exact_hit"]) / n, 2),
        "false_exact_count": sum(1 for r in per_case if r["false_exact"]),
        "correct_abstention_pct": round(100.0 * sum(1 for r in per_case if r["correctly_abstained"]) / n, 2),
        "mean_latency_ms": round(statistics.mean(lats), 1),
        "p95_latency_ms": round(float(np.percentile(lats, 95)), 1),
        "cases": per_case,
    }
    out = ROOT / "reports" / "phase6_unseen_cross_chapter_eval.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("Saved", out)
    print({k: v for k, v in summary.items() if k != "cases"})


if __name__ == "__main__":
    main()
