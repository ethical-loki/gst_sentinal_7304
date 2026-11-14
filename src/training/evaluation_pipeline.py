"""
src/training/evaluation_pipeline.py
===================================
Phase 4 / 8: Evaluation & Threshold Calibration Pipeline

Evaluates a ProductTariffReranker checkpoint on:
  1. Held-out pairwise classification (`full_pairs_val.parquet` / `full_pairs_test.parquet`)
     including ROC-AUC, F1, Precision, Recall, and optimal sigmoid threshold calibration.
  2. End-to-end Golden Intent Benchmarks & Adversarial Product-vs-Machinery suite
     over the Layer-2 Hybrid Retrieval candidate pool.
"""

import json
import logging
import math
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score

from src.ml.product_tariff_reranker import ProductTariffReranker

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent


def _sigmoid_arr(logits: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(logits, -30.0, 30.0)))


def calibrate_threshold(y_true: np.ndarray, probs: np.ndarray) -> Tuple[float, Dict[str, float]]:
    """
    Finds the probability threshold in [0.15, 0.85] that maximizes F1 on validation data.
    """
    best_thresh = 0.50
    best_f1 = -1.0
    best_stats: Dict[str, float] = {}

    for thresh in np.linspace(0.15, 0.85, 29):
        preds = (probs >= thresh).astype(int)
        f1 = float(f1_score(y_true, preds, zero_division=0))
        if f1 > best_f1:
            best_f1 = f1
            best_thresh = float(round(thresh, 4))
            best_stats = {
                "f1": round(f1, 4),
                "precision": round(float(precision_score(y_true, preds, zero_division=0)), 4),
                "recall": round(float(recall_score(y_true, preds, zero_division=0)), 4),
                "accuracy": round(float((preds == y_true).mean()), 4),
            }
    return best_thresh, best_stats


def evaluate_pairs(
    reranker: ProductTariffReranker,
    pairs_df: pd.DataFrame,
    threshold: Optional[float] = None,
    max_samples: Optional[int] = None,
) -> Dict[str, Any]:
    """Evaluates pairwise classification performance on a val/test parquet DataFrame."""
    df = pairs_df
    if max_samples is not None and len(df) > max_samples:
        df = df.sample(n=max_samples, random_state=42).reset_index(drop=True)

    pairs = list(zip(df["query"].astype(str).tolist(), df["tariff_context"].astype(str).tolist()))
    y_true = df["label"].astype(int).to_numpy()

    t0 = time.perf_counter()
    raw_logits = np.array(reranker.score_pairs(pairs), dtype=np.float64)
    elapsed_s = time.perf_counter() - t0
    probs = _sigmoid_arr(raw_logits)

    auc = float(roc_auc_score(y_true, probs)) if len(np.unique(y_true)) > 1 else 0.0

    if threshold is None:
        used_thresh, thresh_metrics = calibrate_threshold(y_true, probs)
    else:
        used_thresh = float(threshold)
        preds = (probs >= used_thresh).astype(int)
        thresh_metrics = {
            "f1": round(float(f1_score(y_true, preds, zero_division=0)), 4),
            "precision": round(float(precision_score(y_true, preds, zero_division=0)), 4),
            "recall": round(float(recall_score(y_true, preds, zero_division=0)), 4),
            "accuracy": round(float((preds == y_true).mean()), 4),
        }

    # Cross-chapter hard-negative rejection rate at calibrated threshold
    neg_mask = y_true == 0
    cross_neg_mask = neg_mask & (df.get("negative_type", pd.Series(["none"] * len(df))) == "cross_chapter").to_numpy()
    cross_rejection = (
        float((probs[cross_neg_mask] < used_thresh).mean()) if cross_neg_mask.any() else 0.0
    )

    return {
        "samples_evaluated": len(df),
        "roc_auc": round(auc, 4),
        "calibrated_threshold": used_thresh,
        **thresh_metrics,
        "cross_chapter_neg_rejection_rate": round(cross_rejection, 4),
        "eval_time_s": round(elapsed_s, 2),
    }


def evaluate_end_to_end_retrieval(
    reranker: ProductTariffReranker,
    max_golden_queries: int = 40,
) -> Dict[str, Any]:
    """
    Runs the Phase 1 Golden Intent + Adversarial Product-vs-Machinery benchmark
    using the provided `ProductTariffReranker` over Layer-2 RRF candidates.
    """
    from scripts.benchmark_reranker_phase1 import (
        ADVERSARIAL_CASES,
        load_benchmark_queries,
        retrieve_rrf_candidates,
    )
    from src.search.hybrid_retrieval import HybridHSNEngine

    engine = HybridHSNEngine.get_instance()
    golden_queries = load_benchmark_queries(max_queries=max_golden_queries)

    top1_hits = 0
    top3_hits = 0
    rr_sum = 0.0
    latencies_ms: List[float] = []

    for item in golden_queries:
        cands = retrieve_rrf_candidates(engine, item["query"], pool_size=15)
        t0 = time.perf_counter()
        ranked = reranker.rerank(item["query"], cands)
        latencies_ms.append((time.perf_counter() - t0) * 1000.0)

        exp_ch = item["expected_chapter"]
        chapters = [str(r.chapter_code).zfill(2) for r in ranked]
        if chapters and chapters[0] == exp_ch:
            top1_hits += 1
        if exp_ch in chapters[:3]:
            top3_hits += 1
        for rank_idx, ch in enumerate(chapters, start=1):
            if ch == exp_ch:
                rr_sum += 1.0 / rank_idx
                break

    adv_wins = 0
    adv_margins: List[float] = []
    for case in ADVERSARIAL_CASES:
        cands = retrieve_rrf_candidates(engine, case["query"], pool_size=15)
        ranked = reranker.rerank(case["query"], cands)
        exp_ch = case["expected_chapter"]
        dist_ch = case["distractor_chapter"]
        top_exp = next((r for r in ranked if str(r.chapter_code).zfill(2) == exp_ch), None)
        top_dist = next((r for r in ranked if str(r.chapter_code).zfill(2) == dist_ch), None)
        exp_score = top_exp.relevance_score if top_exp else 0.0
        dist_score = top_dist.relevance_score if top_dist else 0.0
        adv_margins.append(exp_score - dist_score)
        if ranked and str(ranked[0].chapter_code).zfill(2) == exp_ch:
            adv_wins += 1

    n = len(golden_queries)
    return {
        "golden_queries": n,
        "top1_chapter_accuracy": round(top1_hits / n, 4) if n else 0.0,
        "top3_chapter_hit_rate": round(top3_hits / n, 4) if n else 0.0,
        "mrr": round(rr_sum / n, 4) if n else 0.0,
        "avg_latency_ms": round(sum(latencies_ms) / len(latencies_ms), 1) if latencies_ms else 0.0,
        "adversarial_win_rate": round(adv_wins / len(ADVERSARIAL_CASES), 4),
        "adversarial_avg_margin": round(sum(adv_margins) / len(adv_margins), 4),
    }

