"""
Step 5: Cross-Encoder Validation Benchmark (10 Golden + 4 Adversarial Queries).

Compares:
  1. Existing MiniLM baseline (cross-encoder/ms-marco-MiniLM-L-6-v2)
  2. Current fine-tuned reranker (data/model_versions/hsn_reranker_v1)
  3. BGE Reranker v2 M3 (BAAI/bge-reranker-v2-m3)

Does NOT replace hsn_reranker_v1 automatically; reports accuracy, separation margin,
adversarial rejection, and latency per query on CPU.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ml.product_tariff_reranker import (
    BASELINE_RERANKER_MODEL,
    DEFAULT_RERANKER_MODEL,
    ProductTariffReranker,
)
from src.search.hybrid_retrieval import HybridHSNEngine

GOLDEN_10: List[Dict[str, Any]] = [
    {"query": "plastic water bottle", "expected_chapter": "39"},
    {"query": "stainless steel water bottle", "expected_chapter": "73"},
    {"query": "laptop computer", "expected_chapter": "84"},
    {"query": "cotton knitted t-shirt", "expected_chapter": "61"},
    {"query": "men woven cotton formal shirt", "expected_chapter": "62"},
    {"query": "lithium ion battery pack", "expected_chapter": "85"},
    {"query": "wooden office chair", "expected_chapter": "94"},
    {"query": "pasta and noodles", "expected_chapter": "19"},
    {"query": "car brake pads", "expected_chapter": "87"},
    {"query": "stainless steel kitchen sink", "expected_chapter": "73"},
]

ADVERSARIAL_4: List[Dict[str, Any]] = [
    {"query": "roasted arabica coffee beans", "expected_chapter": "OUT_OF_SCHEDULE"},
    {"query": "paracetamol 500mg tablets", "expected_chapter": "OUT_OF_SCHEDULE"},
    {"query": "fresh basmati rice", "expected_chapter": "OUT_OF_SCHEDULE"},
    {"query": "gold wedding ring", "expected_chapter": "OUT_OF_SCHEDULE"},
]


def _evaluate_model(
    model_name: str,
    reranker: ProductTariffReranker,
    pools: Dict[str, List[Dict[str, Any]]],
    threshold: float = 0.725,
) -> Dict[str, Any]:
    golden_hits = 0
    adv_rejected = 0
    latencies: List[float] = []
    details: List[Dict[str, Any]] = []

    for item in GOLDEN_10:
        q = item["query"]
        cands = pools[q]
        t0 = time.perf_counter()
        ranked = reranker.rerank(q, cands, normalize_sigmoid=True)
        dt = time.perf_counter() - t0
        latencies.append(dt)

        top = ranked[0] if ranked else None
        hit = bool(top and top.chapter_code.zfill(2) == item["expected_chapter"])
        if hit:
            golden_hits += 1
        details.append({
            "type": "golden",
            "query": q,
            "expected_chapter": item["expected_chapter"],
            "top_hsn": top.hsn_code if top else None,
            "top_chapter": top.chapter_code if top else None,
            "top_score": round(top.relevance_score, 4) if top else 0.0,
            "hit": hit,
            "latency_sec": round(dt, 3),
        })

    for item in ADVERSARIAL_4:
        q = item["query"]
        cands = pools[q]
        t0 = time.perf_counter()
        ranked = reranker.rerank(q, cands, normalize_sigmoid=True)
        dt = time.perf_counter() - t0
        latencies.append(dt)

        top = ranked[0] if ranked else None
        top_score = top.relevance_score if top else 0.0
        rejected = top_score < threshold
        if rejected:
            adv_rejected += 1
        details.append({
            "type": "adversarial",
            "query": q,
            "expected": "score < threshold",
            "top_hsn": top.hsn_code if top else None,
            "top_chapter": top.chapter_code if top else None,
            "top_score": round(top_score, 4),
            "rejected": rejected,
            "latency_sec": round(dt, 3),
        })

    avg_lat = sum(latencies) / max(len(latencies), 1)
    return {
        "model": model_name,
        "golden_top1_chapter_accuracy": round(golden_hits / len(GOLDEN_10), 4),
        "golden_hits": f"{golden_hits}/{len(GOLDEN_10)}",
        "adversarial_rejection_rate": round(adv_rejected / len(ADVERSARIAL_4), 4),
        "adversarial_rejected": f"{adv_rejected}/{len(ADVERSARIAL_4)}",
        "avg_latency_sec": round(avg_lat, 3),
        "total_eval_sec": round(sum(latencies), 2),
        "details": details,
    }


def main():
    engine = HybridHSNEngine.get_instance()
    all_queries = [x["query"] for x in GOLDEN_10 + ADVERSARIAL_4]
    pools = {q: engine.retrieve_pool(q, pool_size=15, branch_k=20) for q in all_queries}

    v1_path = PROJECT_ROOT / "data" / "model_versions" / "hsn_reranker_v1"
    models = [
        ("MiniLM-baseline", BASELINE_RERANKER_MODEL, 160),
        ("hsn_reranker_v1", str(v1_path), 160),
        ("BGE-reranker-v2-m3", DEFAULT_RERANKER_MODEL, 160),
    ]

    results = []
    for label, path_or_id, max_len in models:
        print(f"Benchmarking {label} ({path_or_id})...", flush=True)
        reranker = ProductTariffReranker(model_name_or_path=path_or_id, max_length=max_len)
        res = _evaluate_model(label, reranker, pools)
        results.append(res)
        print(
            f"  -> Golden: {res['golden_hits']}, Adversarial rejected: {res['adversarial_rejected']}, "
            f"Avg latency: {res['avg_latency_sec']}s",
            flush=True,
        )

    out_path = PROJECT_ROOT / "reports" / "step5_reranker_comparison.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"models": results}, indent=2), encoding="utf-8")
    print(f"Saved Step 5 report to {out_path}")


if __name__ == "__main__":
    main()

