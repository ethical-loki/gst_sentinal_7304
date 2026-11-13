"""
scripts/evaluate_intent_benchmark.py
===================================
Comprehensive evaluation runner for the HSN Intent Extraction & Hybrid Classification Engine.
Evaluates 100+ queries across 8 categories:
1. Intent Extraction Accuracy (%)
2. Grounding Precision (%)
3. Clarification Rate (%)
4. Abstention Rate (%)
5. Top-1 & Top-3 Retrieval Accuracy (%)
6. Per-Category Breakdown
7. Appends run to data/intent_cache/benchmark_history.jsonl
"""

import json
import time
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.nlp.intent_extractor import IntentExtractor, DeterministicLLMClient
from src.search.ambiguity_controller import evaluate_product_ambiguity


def run_benchmark(benchmark_file: Path) -> Dict[str, Any]:
    with open(benchmark_file, "r", encoding="utf-8") as f:
        cases: List[Dict[str, Any]] = json.load(f)

    print("\n" + "=" * 70)
    print("STARTING HSN INTENT & HYBRID CLASSIFICATION BENCHMARK EVALUATION")
    print(f"Loaded {len(cases)} test cases from {benchmark_file.name}")
    print("=" * 70)

    extractor = IntentExtractor.get_instance()
    # Ensure deterministic mode for standard reproducible evaluation
    extractor._llm_client = DeterministicLLMClient()

    total_cases = len(cases)
    intent_correct_count = 0
    grounding_valid_count = 0
    grounding_total_terms = 0
    grounding_passed_terms = 0
    top1_correct_count = 0
    top3_correct_count = 0
    clarification_count = 0
    abstention_count = 0

    category_stats: Dict[str, Dict[str, int]] = {}

    t0 = time.perf_counter()

    for idx, tc in enumerate(cases, 1):
        q = tc["query"]
        cat = tc["category"]
        exp_conf = tc.get("expected_reading_confidence")
        exp_outcome = tc.get("expected_outcome")
        exp_concept = tc.get("expected_concept")
        exp_chap = tc.get("expected_chapter")

        if cat not in category_stats:
            category_stats[cat] = {"total": 0, "intent_correct": 0, "retrieval_correct": 0, "abstain": 0, "clarify": 0}
        category_stats[cat]["total"] += 1

        # 1. Run Intent Extraction
        intent_res = extractor.extract_intent(q)

        # Evaluate Intent Accuracy
        conf_match = (intent_res.reading_confidence == exp_conf) if exp_conf else True
        outcome_match = (intent_res.outcome_type == exp_outcome) if exp_outcome else True
        concept_match = True
        if exp_concept:
            concept_match = (
                exp_concept.lower() in intent_res.physical_product.lower()
                or any(exp_concept.lower() in t.lower() for t in intent_res.grounded_search_terms)
                or (intent_res.material and exp_concept.lower() in intent_res.material.lower())
            )

        is_intent_accurate = (conf_match and outcome_match and concept_match)
        if is_intent_accurate:
            intent_correct_count += 1
            category_stats[cat]["intent_correct"] += 1

        # Evaluate Grounding Precision (Zero hallucinated terms)
        for term in intent_res.grounded_search_terms:
            grounding_total_terms += 1
            is_g, _ = extractor._is_term_grounded(term)
            if is_g:
                grounding_passed_terms += 1

        if len(intent_res.dropped_terms) == 0 or len(intent_res.grounded_search_terms) > 0 or exp_outcome == "UNRECOGNIZED":
            grounding_valid_count += 1

        # Track Abstention vs Clarification
        if intent_res.outcome_type in ("UNRECOGNIZED", "OUT_OF_SCHEDULE"):
            abstention_count += 1
            category_stats[cat]["abstain"] += 1
        elif intent_res.outcome_type == "AMBIGUOUS_MATERIAL":
            clarification_count += 1
            category_stats[cat]["clarify"] += 1

        # 2. Run Layer 4 Ambiguity / Retrieval if outcome was SUCCESS
        retrieval_hit = False
        if intent_res.outcome_type == "SUCCESS":
            ambig_res = evaluate_product_ambiguity(intent_res.synthesized_search_string or q)
            # Check chapter match
            pred_chaps = []
            if ambig_res.direct_match:
                pred_chaps.append(ambig_res.direct_match.chapter_code)
            for opt in ambig_res.disambiguation_options:
                if opt.chapter_code not in pred_chaps:
                    pred_chaps.append(opt.chapter_code)

            if exp_chap and exp_chap != "NONE":
                if pred_chaps and pred_chaps[0] == exp_chap:
                    top1_correct_count += 1
                    top3_correct_count += 1
                    retrieval_hit = True
                    category_stats[cat]["retrieval_correct"] += 1
                elif exp_chap in pred_chaps[:3]:
                    top3_correct_count += 1
                    retrieval_hit = True
                    category_stats[cat]["retrieval_correct"] += 1
        else:
            # Out of schedule or unrecognized appropriately not retrieved
            if exp_outcome in ("OUT_OF_SCHEDULE", "UNRECOGNIZED", "AMBIGUOUS_MATERIAL"):
                top1_correct_count += 1
                top3_correct_count += 1
                retrieval_hit = True
                category_stats[cat]["retrieval_correct"] += 1

    total_latency_ms = round((time.perf_counter() - t0) * 1000.0, 1)
    avg_latency_ms = round(total_latency_ms / total_cases, 2)

    intent_accuracy_pct = round((intent_correct_count / total_cases) * 100.0, 2)
    grounding_precision_pct = round(
        (grounding_passed_terms / max(1, grounding_total_terms)) * 100.0, 2
    ) if grounding_total_terms > 0 else 100.0
    top1_accuracy_pct = round((top1_correct_count / total_cases) * 100.0, 2)
    top3_accuracy_pct = round((top3_correct_count / total_cases) * 100.0, 2)
    abstention_rate_pct = round((abstention_count / total_cases) * 100.0, 2)
    clarification_rate_pct = round((clarification_count / total_cases) * 100.0, 2)

    # -------------------------------------------------------------
    # Render Formatted Terminal Report
    # -------------------------------------------------------------
    print("\n" + "=" * 70)
    print("                HSN CLASSIFICATION BENCHMARK REPORT                ")
    print("=" * 70)
    print(f"Total Test Queries:             {total_cases}")
    print(f"Total Evaluation Time:          {total_latency_ms} ms (avg {avg_latency_ms} ms/query)")
    print("-" * 70)
    print(f"Intent Extraction Accuracy:     {intent_accuracy_pct}% ({intent_correct_count}/{total_cases})")
    print(f"Row-Level Grounding Precision:  {grounding_precision_pct}% ({grounding_passed_terms}/{grounding_total_terms} terms)")
    print(f"Top-1 Statutory Accuracy:       {top1_accuracy_pct}% ({top1_correct_count}/{total_cases})")
    print(f"Top-3 Statutory Accuracy:       {top3_accuracy_pct}% ({top3_correct_count}/{total_cases})")
    print(f"Abstention Rate:                {abstention_rate_pct}% ({abstention_count}/{total_cases})")
    print(f"Clarification Rate:             {clarification_rate_pct}% ({clarification_count}/{total_cases})")
    print("=" * 70)

    print("\nCATEGORY PERFORMANCE BREAKDOWN:")
    print(f"{'Category':<26} | {'Total':<6} | {'Intent Acc':<11} | {'Retrieval':<10} | {'Abstain':<8} | {'Clarify':<8}")
    print("-" * 76)
    for cat, stats in sorted(category_stats.items()):
        tot = stats["total"]
        i_acc = f"{(stats['intent_correct'] / tot) * 100:.1f}%"
        r_acc = f"{(stats['retrieval_correct'] / tot) * 100:.1f}%"
        print(f"{cat:<26} | {tot:<6} | {i_acc:<11} | {r_acc:<10} | {stats['abstain']:<8} | {stats['clarify']:<8}")
    print("=" * 76)

    # -------------------------------------------------------------
    # Append Record to Historical Log
    # -------------------------------------------------------------
    history_file = Path(__file__).resolve().parent.parent / "data" / "intent_cache" / "benchmark_history.jsonl"
    history_file.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "timestamp": datetime.now().isoformat(),
        "total_queries": total_cases,
        "total_latency_ms": total_latency_ms,
        "avg_latency_ms": avg_latency_ms,
        "intent_accuracy_pct": intent_accuracy_pct,
        "grounding_precision_pct": grounding_precision_pct,
        "top1_accuracy_pct": top1_accuracy_pct,
        "top3_accuracy_pct": top3_accuracy_pct,
        "abstention_rate_pct": abstention_rate_pct,
        "clarification_rate_pct": clarification_rate_pct,
        "category_breakdown": category_stats
    }

    try:
        with open(history_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
        print(f"\nBenchmark run successfully logged to {history_file.relative_to(history_file.parent.parent.parent)}")
    except Exception as e:
        print(f"Failed to append to history log: {e}")

    return record


if __name__ == "__main__":
    b_file = Path(__file__).resolve().parent.parent / "data" / "golden_intent_benchmarks.json"
    run_benchmark(b_file)
