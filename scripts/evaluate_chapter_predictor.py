"""
scripts/evaluate_chapter_predictor.py
======================================
Task 11: Benchmark evaluation tool for HSN Chapter Predictor.
Evaluates accuracy (Top-1, Top-3), abstention rate, latency,
and per-category/family breakdown against stratified gold sets.
"""

import sys
import os
import csv
import time
import json
import argparse
from pathlib import Path
from collections import defaultdict

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.chapter_predictor.predictor import ChapterPredictor


def evaluate(file_path: str, max_samples: int = None):
    path = Path(file_path)
    if not path.exists():
        print(f"Error: file not found: {file_path}")
        return

    print(f"\n========================================================")
    print(f"🚀 Running Chapter Predictor Evaluation on: {path.name}")
    print(f"========================================================")

    predictor = ChapterPredictor.get_instance()

    with open(path, "r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))

    if max_samples and max_samples < len(reader):
        reader = reader[:max_samples]

    total = len(reader)
    top1_correct = 0
    top3_correct = 0
    abstentions = 0
    latencies = []

    category_stats = defaultdict(lambda: {"total": 0, "top1": 0, "top3": 0, "abstain": 0})
    variant_stats = defaultdict(lambda: {"total": 0, "top1": 0, "top3": 0, "abstain": 0})

    start_all = time.perf_counter()

    for idx, row in enumerate(reader, 1):
        product_name = row["product_name"]
        expected = str(row["expected_chapter"]).zfill(2)
        category = row.get("category", "General")
        variant = row.get("variant", "plain")

        t0 = time.perf_counter()
        result = predictor.predict(product_name)
        dt = (time.perf_counter() - t0) * 1000.0
        latencies.append(dt)

        pred_ch = str(result.chapter).zfill(2)
        top3_chs = [pred_ch] + [str(alt.chapter).zfill(2) for alt in result.alternatives[:2]]

        is_top1 = (pred_ch == expected) and (result.status == "OK")
        is_top3 = (expected in top3_chs)
        is_abstain = (result.status != "OK")

        if is_top1:
            top1_correct += 1
        if is_top3:
            top3_correct += 1
        if is_abstain:
            abstentions += 1

        category_stats[category]["total"] += 1
        if is_top1: category_stats[category]["top1"] += 1
        if is_top3: category_stats[category]["top3"] += 1
        if is_abstain: category_stats[category]["abstain"] += 1

        variant_stats[variant]["total"] += 1
        if is_top1: variant_stats[variant]["top1"] += 1
        if is_top3: variant_stats[variant]["top3"] += 1
        if is_abstain: variant_stats[variant]["abstain"] += 1

        if idx % 50 == 0 or idx == total:
            print(f"[{idx}/{total}] Processed... Current Top-1: {top1_correct/idx*100:.1f}%, Abstain: {abstentions/idx*100:.1f}%", flush=True)

    total_time = time.perf_counter() - start_all
    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0

    print("\n" + "="*60)
    print("📊 OVERALL BENCHMARK RESULTS")
    print("="*60)
    print(f"Dataset:            {path.name} ({total} items)")
    print(f"Top-1 Accuracy:     {top1_correct}/{total} ({top1_correct/total*100:.2f}%)")
    print(f"Top-3 Accuracy:     {top3_correct}/{total} ({top3_correct/total*100:.2f}%)")
    print(f"Abstention Rate:    {abstentions}/{total} ({abstentions/total*100:.2f}%)")
    print(f"Average Latency:    {avg_latency:.2f} ms/item")
    print(f"Total Test Time:    {total_time:.2f} s")

    print("\n" + "-"*60)
    print("📈 BREAKDOWN BY QUERY VARIANT")
    print("-"*60)
    print(f"{'Variant':<15} | {'Count':<6} | {'Top-1':<8} | {'Top-3':<8} | {'Abstain':<8}")
    print("-" * 55)
    for var, s in sorted(variant_stats.items()):
        cnt = s["total"]
        t1_pct = s["top1"] / cnt * 100 if cnt else 0
        t3_pct = s["top3"] / cnt * 100 if cnt else 0
        ab_pct = s["abstain"] / cnt * 100 if cnt else 0
        print(f"{var:<15} | {cnt:<6} | {t1_pct:>6.1f}% | {t3_pct:>6.1f}% | {ab_pct:>6.1f}%")

    print("\n" + "-"*60)
    print("🏛️ BREAKDOWN BY COMMODITY CATEGORY")
    print("-"*60)
    print(f"{'Category':<32} | {'Count':<6} | {'Top-1':<8} | {'Top-3':<8}")
    print("-" * 60)
    for cat, s in sorted(category_stats.items()):
        cnt = s["total"]
        t1_pct = s["top1"] / cnt * 100 if cnt else 0
        t3_pct = s["top3"] / cnt * 100 if cnt else 0
        print(f"{cat:<32} | {cnt:<6} | {t1_pct:>6.1f}% | {t3_pct:>6.1f}%")

    report = {
        "dataset": path.name,
        "total_items": total,
        "top1_accuracy": top1_correct / total if total else 0,
        "top3_accuracy": top3_correct / total if total else 0,
        "abstention_rate": abstentions / total if total else 0,
        "avg_latency_ms": avg_latency,
        "category_stats": dict(category_stats),
        "variant_stats": dict(variant_stats)
    }

    out_file = REPO_ROOT / "data" / "eval" / f"benchmark_result_{path.stem}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\n[OK] Benchmark report saved to {out_file.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="data/eval/dev_set.csv", help="Path to evaluation CSV")
    parser.add_argument("--max", type=int, default=None, help="Max items to evaluate")
    args = parser.parse_args()
    evaluate(args.dataset, args.max)
