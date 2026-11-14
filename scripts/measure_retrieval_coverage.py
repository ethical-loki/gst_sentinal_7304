"""
Step 4: Measure Layer 2 Retrieval Coverage (Recall@15, Recall@40, Exact HSN & Chapter Recall).

Evaluates HybridHSNEngine.retrieve_pool() on held-out unseen test queries
from `data/training_pairs/positive_pairs_test.parquet` before modifying any reranker.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.search.hybrid_retrieval import HybridHSNEngine


def measure_coverage(limit: int = 200, seed: int = 42) -> dict:
    test_path = PROJECT_ROOT / "data" / "training_pairs" / "positive_pairs_test.parquet"
    df = pd.read_parquet(test_path)
    if limit and limit < len(df):
        df = df.sample(n=limit, random_state=seed).reset_index(drop=True)

    engine = HybridHSNEngine.get_instance()

    hits_15_hsn = 0
    hits_40_hsn = 0
    hits_15_chap = 0
    hits_40_chap = 0
    by_strategy = defaultdict(lambda: {"n": 0, "hsn_15": 0, "hsn_40": 0, "chap_15": 0, "chap_40": 0})
    by_chapter = defaultdict(lambda: {"n": 0, "hsn_15": 0, "hsn_40": 0, "chap_15": 0, "chap_40": 0})
    missed_examples = []

    t0 = time.perf_counter()
    for _, row in df.iterrows():
        q = str(row["query"])
        target_hsn = str(row["hsn_code"]).strip()
        target_chap = str(row["chapter_code"]).strip().zfill(2)
        strategy = str(row.get("query_strategy", "unknown"))

        pool_40 = engine.retrieve_pool(q, pool_size=40, branch_k=50)
        pool_15 = pool_40[:15]

        hsns_15 = {str(r.get("hsn_code") or r.get("code_str") or "").strip() for r in pool_15}
        hsns_40 = {str(r.get("hsn_code") or r.get("code_str") or "").strip() for r in pool_40}
        chaps_15 = {str(r.get("chapter_code") or r.get("chapter_str") or "").strip().zfill(2) for r in pool_15}
        chaps_40 = {str(r.get("chapter_code") or r.get("chapter_str") or "").strip().zfill(2) for r in pool_40}

        h15 = int(target_hsn in hsns_15)
        h40 = int(target_hsn in hsns_40)
        c15 = int(target_chap in chaps_15)
        c40 = int(target_chap in chaps_40)

        hits_15_hsn += h15
        hits_40_hsn += h40
        hits_15_chap += c15
        hits_40_chap += c40

        for bucket in (by_strategy[strategy], by_chapter[target_chap]):
            bucket["n"] += 1
            bucket["hsn_15"] += h15
            bucket["hsn_40"] += h40
            bucket["chap_15"] += c15
            bucket["chap_40"] += c40

        if not h40 and len(missed_examples) < 15:
            missed_examples.append({
                "query": q,
                "target_hsn": target_hsn,
                "target_chapter": target_chap,
                "strategy": strategy,
                "top5_retrieved_hsn": [str(r.get("hsn_code") or "").strip() for r in pool_40[:5]],
            })

    elapsed = round(time.perf_counter() - t0, 2)
    n = len(df)

    def _rates(d: dict) -> dict:
        out = {}
        for k, v in sorted(d.items()):
            cnt = max(v["n"], 1)
            out[k] = {
                "n": v["n"],
                "recall_15_hsn": round(v["hsn_15"] / cnt, 4),
                "recall_40_hsn": round(v["hsn_40"] / cnt, 4),
                "recall_15_chapter": round(v["chap_15"] / cnt, 4),
                "recall_40_chapter": round(v["chap_40"] / cnt, 4),
            }
        return out

    report = {
        "total_queries": n,
        "elapsed_sec": elapsed,
        "recall_at_15_exact_hsn": round(hits_15_hsn / max(n, 1), 4),
        "recall_at_40_exact_hsn": round(hits_40_hsn / max(n, 1), 4),
        "recall_at_15_chapter": round(hits_15_chap / max(n, 1), 4),
        "recall_at_40_chapter": round(hits_40_chap / max(n, 1), 4),
        "improvement_hsn_15_to_40": round((hits_40_hsn - hits_15_hsn) / max(n, 1), 4),
        "by_strategy": _rates(by_strategy),
        "by_chapter": _rates(by_chapter),
        "sample_missed_at_40": missed_examples,
    }

    out_path = PROJECT_ROOT / "reports" / "step4_retrieval_coverage.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()
    rep = measure_coverage(limit=args.limit)
    print(json.dumps({
        "total_queries": rep["total_queries"],
        "elapsed_sec": rep["elapsed_sec"],
        "recall_at_15_exact_hsn": rep["recall_at_15_exact_hsn"],
        "recall_at_40_exact_hsn": rep["recall_at_40_exact_hsn"],
        "recall_at_15_chapter": rep["recall_at_15_chapter"],
        "recall_at_40_chapter": rep["recall_at_40_chapter"],
        "improvement_hsn_15_to_40": rep["improvement_hsn_15_to_40"],
    }, indent=2))


if __name__ == "__main__":
    main()

