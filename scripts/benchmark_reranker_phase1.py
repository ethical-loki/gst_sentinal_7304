"""
scripts/benchmark_reranker_phase1.py
====================================
Phase 1 Benchmark: BAAI/bge-reranker-v2-m3 vs cross-encoder/ms-marco-MiniLM-L-6-v2

Evaluates both models on the exact same Layer-2 Hybrid Retrieval candidate pool
(BM25 + Dense MiniLM + RRF) across:
  1. Golden Intent Benchmarks (queries with expected_chapter in the 9 active chapters)
  2. Adversarial Product-vs-Machinery / Component-vs-Article Distinction Tests

Measures:
  - Top-1 Chapter Accuracy
  - Top-3 Chapter Hit Rate
  - Mean Reciprocal Rank (MRR)
  - Inference Latency (ms/query for reranking 15 candidates on local hardware)
  - Adversarial Separation Margin
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

# Ensure project root is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

from src.ml.product_tariff_reranker import (
    BASELINE_RERANKER_MODEL,
    DEFAULT_RERANKER_MODEL,
    ProductTariffReranker,
)
from src.search.hybrid_retrieval import HybridHSNEngine, tokenize

ACTIVE_CHAPTERS = {"19", "39", "61", "62", "73", "84", "85", "87", "94"}

ADVERSARIAL_CASES = [
    {
        "query": "plastic water bottle",
        "expected_chapter": "39",
        "distractor_chapter": "84",
        "note": "Finished plastic article (Ch 39) vs bottle-making/filling machinery (Ch 84)",
    },
    {
        "query": "cotton t-shirt knitted",
        "expected_chapter": "61",
        "distractor_chapter": "84",
        "note": "Knitted garment (Ch 61) vs knitting/sewing machinery (Ch 84)",
    },
    {
        "query": "stainless steel seamless pipe",
        "expected_chapter": "73",
        "distractor_chapter": "84",
        "note": "Steel article (Ch 73) vs pipe-forming/welding machinery (Ch 84)",
    },
    {
        "query": "wooden office chair with metal frame",
        "expected_chapter": "94",
        "distractor_chapter": "84",
        "note": "Furniture (Ch 94) vs woodworking machinery (Ch 84)",
    },
    {
        "query": "sweet chocolate biscuits",
        "expected_chapter": "19",
        "distractor_chapter": "84",
        "note": "Bakery food product (Ch 19) vs bakery/biscuit-making machinery (Ch 84)",
    },
    {
        "query": "passenger motor car 1500cc",
        "expected_chapter": "87",
        "distractor_chapter": "84",
        "note": "Complete vehicle (Ch 87) vs engine/vehicle-manufacturing machinery (Ch 84)",
    },
    {
        "query": "lithium ion battery pack for electric vehicle",
        "expected_chapter": "85",
        "distractor_chapter": "87",
        "note": "Electrical accumulator (Ch 85) vs electric vehicle (Ch 87)",
    },
    {
        "query": "woven cotton men formal shirt",
        "expected_chapter": "62",
        "distractor_chapter": "84",
        "note": "Woven garment (Ch 62) vs textile weaving/sewing machinery (Ch 84)",
    },
]


def retrieve_rrf_candidates(engine: HybridHSNEngine, query: str, pool_size: int = 15) -> List[Dict[str, Any]]:
    """
    Replicates Layer 2 (BM25 + Dense + RRF) from HybridHSNEngine without running
    its internal Cross-Encoder, so all benchmarked rerankers see the exact same candidates.
    """
    q = (query or "").strip().lower()
    q_tokens = tokenize(q)
    if not q_tokens:
        return []

    s_head = np.array(engine.bm25_heading.get_scores(q_tokens))
    s_syn = np.array(engine.bm25_synonyms.get_scores(q_tokens))
    s_chap = np.array(engine.bm25_chapter.get_scores(q_tokens))
    s_sub = np.array(engine.bm25_subclause.get_scores(q_tokens))

    def min_max(arr: np.ndarray) -> np.ndarray:
        denom = arr.max() - arr.min()
        return (arr - arr.min()) / denom if denom > 0 else np.zeros_like(arr)

    bm25_composite = (
        3.0 * min_max(s_head)
        + 2.5 * min_max(s_syn)
        + 1.5 * min_max(s_chap)
        + 1.0 * min_max(s_sub)
    )
    top_bm25_indices = np.argsort(bm25_composite)[::-1][:20]

    q_emb = engine.embedding_model.encode([q], convert_to_numpy=True, normalize_embeddings=True)[0]
    cos_sims = np.dot(engine.dense_embeddings, q_emb)
    top_vector_indices = np.argsort(cos_sims)[::-1][:20]

    k_rrf = 60.0
    rrf_map: Dict[int, float] = {}
    for rank, idx in enumerate(top_bm25_indices):
        rrf_map[idx] = rrf_map.get(idx, 0.0) + (1.0 / (k_rrf + rank + 1))
    for rank, idx in enumerate(top_vector_indices):
        rrf_map[idx] = rrf_map.get(idx, 0.0) + (1.0 / (k_rrf + rank + 1))

    candidate_indices = sorted(rrf_map.keys(), key=lambda i: rrf_map[i], reverse=True)[:pool_size]
    return [engine.records[idx] for idx in candidate_indices]


def load_benchmark_queries(max_queries: int = 40) -> List[Dict[str, Any]]:
    """Loads active-chapter queries from golden_intent_benchmarks.json."""
    bench_path = ROOT_DIR / "data" / "golden_intent_benchmarks.json"
    with open(bench_path, "r", encoding="utf-8") as f:
        items = json.load(f)

    valid = []
    for item in items:
        exp_ch = str(item.get("expected_chapter", "")).strip().zfill(2)
        if exp_ch in ACTIVE_CHAPTERS and item.get("query"):
            valid.append({
                "query": item["query"],
                "expected_chapter": exp_ch,
                "category": item.get("category", "unknown"),
            })
    return valid[:max_queries]


def evaluate_model(
    model_name: str,
    golden_pool: List[Tuple[Dict[str, Any], List[Dict[str, Any]]]],
    adv_pool: List[Tuple[Dict[str, Any], List[Dict[str, Any]]]],
) -> Dict[str, Any]:
    print(f"\n{'=' * 70}")
    print(f"Benchmarking Model: {model_name}")
    print(f"{'=' * 70}")

    reranker = ProductTariffReranker(model_name_or_path=model_name, local_files_only=True)
    print(f"Load Time: {reranker.load_time_s:.2f}s | Device: {reranker.device}")

    top1_hits = 0
    top3_hits = 0
    rr_sum = 0.0
    latencies_ms: List[float] = []
    failures: List[Dict[str, Any]] = []

    for item, candidates in golden_pool:
        t0 = time.perf_counter()
        ranked = reranker.rerank(item["query"], candidates)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        latencies_ms.append(elapsed_ms)

        exp_ch = item["expected_chapter"]
        chapters = [str(r.chapter_code).zfill(2) for r in ranked]

        if chapters and chapters[0] == exp_ch:
            top1_hits += 1
        else:
            failures.append({
                "query": item["query"],
                "expected_chapter": exp_ch,
                "predicted_top1_chapter": chapters[0] if chapters else None,
                "predicted_top1_hsn": ranked[0].hsn_code if ranked else None,
                "predicted_top1_desc": ranked[0].description[:80] if ranked else None,
                "top1_score": round(ranked[0].relevance_score, 4) if ranked else 0.0,
            })

        if exp_ch in chapters[:3]:
            top3_hits += 1

        rr = 0.0
        for rank_idx, ch in enumerate(chapters, start=1):
            if ch == exp_ch:
                rr = 1.0 / rank_idx
                break
        rr_sum += rr

    n = len(golden_pool)
    top1_acc = top1_hits / n if n else 0.0
    top3_acc = top3_hits / n if n else 0.0
    mrr = rr_sum / n if n else 0.0
    avg_latency = sum(latencies_ms) / len(latencies_ms) if latencies_ms else 0.0

    # Adversarial evaluation
    adv_wins = 0
    adv_margins: List[float] = []
    adv_details: List[Dict[str, Any]] = []

    for case, candidates in adv_pool:
        ranked = reranker.rerank(case["query"], candidates)
        exp_ch = case["expected_chapter"]
        dist_ch = case["distractor_chapter"]

        top_exp = next((r for r in ranked if str(r.chapter_code).zfill(2) == exp_ch), None)
        top_dist = next((r for r in ranked if str(r.chapter_code).zfill(2) == dist_ch), None)

        exp_score = top_exp.relevance_score if top_exp else 0.0
        dist_score = top_dist.relevance_score if top_dist else 0.0
        margin = exp_score - dist_score
        top1_ch = str(ranked[0].chapter_code).zfill(2) if ranked else ""
        won = top1_ch == exp_ch

        if won:
            adv_wins += 1
        adv_margins.append(margin)
        adv_details.append({
            "query": case["query"],
            "expected_chapter": exp_ch,
            "top1_chapter": top1_ch,
            "won": won,
            "exp_score": round(exp_score, 4),
            "distractor_score": round(dist_score, 4),
            "margin": round(margin, 4),
        })

    metrics = {
        "model": model_name,
        "device": reranker.device,
        "load_time_s": round(reranker.load_time_s, 2),
        "golden_queries_evaluated": n,
        "top1_chapter_accuracy": round(top1_acc, 4),
        "top3_chapter_hit_rate": round(top3_acc, 4),
        "mrr": round(mrr, 4),
        "avg_latency_ms_per_15_candidates": round(avg_latency, 1),
        "adversarial_win_rate": round(adv_wins / len(adv_pool), 4) if adv_pool else 0.0,
        "adversarial_avg_margin": round(sum(adv_margins) / len(adv_margins), 4) if adv_margins else 0.0,
        "sample_failures": failures[:10],
        "adversarial_details": adv_details,
    }

    print(f"Golden Queries (n={n}):")
    print(f"  Top-1 Chapter Accuracy : {top1_acc:.1%} ({top1_hits}/{n})")
    print(f"  Top-3 Chapter Hit Rate : {top3_acc:.1%} ({top3_hits}/{n})")
    print(f"  MRR                    : {mrr:.4f}")
    print(f"  Avg Latency (15 cands) : {avg_latency:.1f} ms")
    print(f"Adversarial Product-vs-Machinery (n={len(adv_pool)}):")
    print(f"  Win Rate               : {adv_wins}/{len(adv_pool)} ({metrics['adversarial_win_rate']:.1%})")
    print(f"  Avg Score Margin       : {metrics['adversarial_avg_margin']:+.4f}")

    return metrics


def main():
    print("Initializing HybridHSNEngine (Layer 2 Retrieval)...")
    engine = HybridHSNEngine.get_instance()

    golden_queries = load_benchmark_queries(max_queries=40)
    print(f"Loaded {len(golden_queries)} active-chapter golden queries.")

    golden_pool = [(q, retrieve_rrf_candidates(engine, q["query"], pool_size=15)) for q in golden_queries]
    adv_pool = [(c, retrieve_rrf_candidates(engine, c["query"], pool_size=15)) for c in ADVERSARIAL_CASES]

    # Measure Layer 2 retrieval ceiling (Recall@15)
    recall_15 = sum(
        1 for item, cands in golden_pool
        if item["expected_chapter"] in {str(c.get("chapter_code", "")).zfill(2) for c in cands}
    ) / len(golden_pool)
    print(f"Layer-2 Retrieval Ceiling (Chapter Recall@15): {recall_15:.1%}")

    results = {
        "layer2_recall_at_15": round(recall_15, 4),
        "models": [],
    }

    for model_name in [BASELINE_RERANKER_MODEL, DEFAULT_RERANKER_MODEL]:
        metrics = evaluate_model(model_name, golden_pool, adv_pool)
        results["models"].append(metrics)

    out_path = ROOT_DIR / "reports" / "phase1_reranker_benchmark.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nBenchmark report saved to {out_path}")


if __name__ == "__main__":
    main()

