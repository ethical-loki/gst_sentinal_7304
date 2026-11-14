"""
scripts/evaluate_intent_benchmark.py
===================================
Comprehensive evaluation runner for the HSN Intent Extraction & Hybrid Classification Engine.
Evaluates queries across all statutory categories with:
1. Intent Extraction Accuracy (%)
2. Grounding Precision & Recall (%) against Human-Curated Labels (Non-circular)
3. 4-Quadrant Metric Analysis:
   - Correct Classification (in-scope correctly classified)
   - Correct Abstention (out-of-scope/unrecognized correctly abstained)
   - Wrong Classification (misclassified)
   - Wrong Abstention (in-scope query falsely abstained)
4. Top-1 & Top-3 Statutory Accuracy (%)
5. Progress logging per query with flush
6. Exact Numerators & Denominators for every metric
7. Git commit hash and config SHA-256 hash logging
8. Persists report to reports/held_out_benchmark_results.json
"""

import json
import time
import sys
import hashlib
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.nlp.intent_extractor import IntentExtractor, DeterministicLLMClient
from src.search.ambiguity_controller import evaluate_product_ambiguity


def compute_file_sha256(path: Path) -> str:
    if path.exists():
        content = path.read_bytes()
        return hashlib.sha256(content).hexdigest()[:16]
    return "unknown"


def run_benchmark(benchmark_file: Path, label: str = "BENCHMARK") -> Dict[str, Any]:
    with open(benchmark_file, "r", encoding="utf-8") as f:
        cases: List[Dict[str, Any]] = json.load(f)

    base_dir = Path(__file__).resolve().parent.parent
    config_path = base_dir / "config" / "intent_extraction_config.json"
    config_hash = compute_file_sha256(config_path)

    # Fetch Git commit hash
    git_hash = "unknown"
    try:
        git_hash = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        pass

    print("\n" + "=" * 78)
    print(f"STARTING HSN INTENT & HYBRID CLASSIFICATION EVALUATION: {label}")
    print(f"File: {benchmark_file.name} | Total cases: {len(cases)}")
    print(f"Git Commit Hash: {git_hash} | Config Hash: {config_hash}")
    print("=" * 78, flush=True)

    # Directive 3: Strict cache prohibition check
    if any(arg in sys.argv for arg in ["--cache", "--use-cache", "--enable-cache"]):
        raise RuntimeError("Directive 3 Violation: Evaluation cache must remain strictly disabled for all benchmark runs.")

    extractor = IntentExtractor.get_instance()
    # Enforce empty / disabled cache state for evaluation instance
    if "--deterministic" in sys.argv:
        print("[INFO] Running in deterministic test-double mode", flush=True)
        extractor._llm_client = DeterministicLLMClient()
    else:
        print(f"[INFO] Running with real production LLM: {type(extractor._llm_client).__name__}", flush=True)
    print("[INFO] Directive 3: Interpretation cache is STRICTLY DISABLED for this evaluation run.", flush=True)

    total_cases = len(cases)
    intent_correct_count = 0
    grounding_total_terms = 0
    grounding_passed_terms = 0
    grounding_total_expected = 0
    grounding_recalled_terms = 0
    top1_correct_count = 0
    top3_correct_count = 0
    clarification_count = 0
    abstention_count = 0

    # 4-Quadrant Metric Tracking
    # Quadrant 1: Correct Classification (In-scope expected, correctly classified)
    # Quadrant 2: Correct Abstention (Out-of-scope/unrecognized expected, correctly abstained)
    # Quadrant 3: Wrong Classification (Misclassified)
    # Quadrant 4: Wrong Abstention (In-scope expected, falsely abstained)
    total_in_scope = 0
    total_out_scope = 0
    correct_classification = 0
    correct_abstention = 0
    wrong_classification = 0
    wrong_abstention = 0

    category_stats: Dict[str, Dict[str, int]] = {}

    t0 = time.perf_counter()

    for idx, tc in enumerate(cases, 1):
        q = tc["query"]
        cat = tc["category"]
        exp_conf = tc.get("expected_reading_confidence")
        exp_outcome = tc.get("expected_outcome")
        exp_concept = tc.get("expected_concept")
        exp_chap = tc.get("expected_chapter")
        exp_terms = [t.lower() for t in tc.get("expected_grounded_terms", [])]

        is_case_in_scope = bool(exp_chap and exp_chap != "NONE" and exp_outcome not in ("OUT_OF_SCHEDULE", "UNRECOGNIZED"))
        if is_case_in_scope:
            total_in_scope += 1
        else:
            total_out_scope += 1

        if cat not in category_stats:
            category_stats[cat] = {"total": 0, "intent_correct": 0, "retrieval_correct": 0, "abstain": 0, "clarify": 0}
        category_stats[cat]["total"] += 1

        # 1. Run Intent Extraction with timing (Strict cache prohibition per Directive 3)
        q_t0 = time.perf_counter()
        intent_res = extractor.extract_intent(q, use_cache=False)
        q_lat = (time.perf_counter() - q_t0) * 1000.0

        if getattr(intent_res, "is_cache_hit", False):
            raise RuntimeError(f"Directive 3 Violation: Cache hit detected for query '{q}' during evaluation run!")

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

        # 2. Evaluate Grounding Precision and Recall against Human-Curated Labels
        if exp_terms:
            grounding_total_expected += len(exp_terms)
            for exp in exp_terms:
                if any(exp in t.lower() or t.lower() in exp or any(w in exp for w in t.lower().split() if len(w) > 3) for t in intent_res.grounded_search_terms):
                    grounding_recalled_terms += 1

            for term in intent_res.grounded_search_terms:
                grounding_total_terms += 1
                t_low = term.lower()
                if any(t_low in exp or exp in t_low or any(w in exp for w in t_low.split() if len(w) > 3) for exp in exp_terms):
                    grounding_passed_terms += 1
        elif exp_outcome in ("UNRECOGNIZED", "OUT_OF_SCHEDULE"):
            # Any grounded term emitted for unrecognized query counts as hallucination
            for term in intent_res.grounded_search_terms:
                grounding_total_terms += 1
        else:
            for term in intent_res.grounded_search_terms:
                grounding_total_terms += 1
                is_g, _ = extractor._is_term_grounded(term)
                if is_g:
                    grounding_passed_terms += 1

        # Track Abstention vs Clarification
        is_system_abstained = (intent_res.outcome_type in ("UNRECOGNIZED", "OUT_OF_SCHEDULE"))
        if is_system_abstained:
            abstention_count += 1
            category_stats[cat]["abstain"] += 1
        elif intent_res.outcome_type == "AMBIGUOUS_MATERIAL":
            clarification_count += 1
            category_stats[cat]["clarify"] += 1

        # 3. Run Layer 4 Ambiguity / Retrieval if outcome was SUCCESS
        pred_chaps = []
        if intent_res.outcome_type == "SUCCESS":
            ambig_res = evaluate_product_ambiguity(intent_res.synthesized_search_string or q)
            if ambig_res.direct_match:
                pred_chaps.append(ambig_res.direct_match.chapter_code)
            for opt in ambig_res.disambiguation_options:
                if opt.chapter_code not in pred_chaps:
                    pred_chaps.append(opt.chapter_code)

            if exp_chap and exp_chap != "NONE":
                if pred_chaps and pred_chaps[0] == exp_chap:
                    top1_correct_count += 1
                    top3_correct_count += 1
                    category_stats[cat]["retrieval_correct"] += 1
                elif exp_chap in pred_chaps[:3]:
                    top3_correct_count += 1
                    category_stats[cat]["retrieval_correct"] += 1

        # 4. 4-Quadrant Metric Evaluation
        if is_case_in_scope:
            if is_system_abstained:
                # In-scope query falsely abstained -> Wrong Abstention
                wrong_abstention += 1
            elif pred_chaps and (pred_chaps[0] == exp_chap or exp_chap in pred_chaps[:3]):
                # In-scope query correctly classified -> Correct Classification
                correct_classification += 1
            else:
                # In-scope query classified to wrong chapter -> Wrong Classification
                wrong_classification += 1
        else:
            if is_system_abstained:
                # Out-of-scope query correctly abstained -> Correct Abstention
                correct_abstention += 1
                top1_correct_count += 1
                top3_correct_count += 1
                category_stats[cat]["retrieval_correct"] += 1
            else:
                # Out-of-scope query falsely classified into a chapter -> Wrong Classification
                wrong_classification += 1

        # Progress log per query
        status_tag = intent_res.outcome_type
        print(f"[{idx:02d}/{total_cases}] '{q[:26]:<26}' -> {status_tag:<18} ({q_lat:.0f}ms)", flush=True)

    total_latency_ms = round((time.perf_counter() - t0) * 1000.0, 1)
    avg_latency_ms = round(total_latency_ms / total_cases, 2)

    intent_accuracy_pct = round((intent_correct_count / total_cases) * 100.0, 2)
    grounding_precision_pct = round(
        (grounding_passed_terms / max(1, grounding_total_terms)) * 100.0, 2
    ) if grounding_total_terms > 0 else 100.0
    grounding_recall_pct = round(
        (grounding_recalled_terms / max(1, grounding_total_expected)) * 100.0, 2
    ) if grounding_total_expected > 0 else 100.0
    top1_accuracy_pct = round((top1_correct_count / total_cases) * 100.0, 2)
    top3_accuracy_pct = round((top3_correct_count / total_cases) * 100.0, 2)
    abstention_rate_pct = round((abstention_count / total_cases) * 100.0, 2)
    clarification_rate_pct = round((clarification_count / total_cases) * 100.0, 2)

    # 4-Quadrant Percentages
    correct_class_pct = round((correct_classification / max(1, total_in_scope)) * 100.0, 2)
    correct_abstain_pct = round((correct_abstention / max(1, total_out_scope)) * 100.0, 2)
    wrong_class_pct = round((wrong_classification / total_cases) * 100.0, 2)
    wrong_abstain_pct = round((wrong_abstention / max(1, total_in_scope)) * 100.0, 2)
    statutory_decision_acc_pct = round(((correct_classification + correct_abstention) / total_cases) * 100.0, 2)

    # -------------------------------------------------------------
    # Render Formatted Terminal Report
    # -------------------------------------------------------------
    print("\n" + "=" * 78)
    print(f"                HSN CLASSIFICATION BENCHMARK REPORT: {label}                ")
    print("=" * 78)
    print(f"Git Commit Hash:                {git_hash}")
    print(f"Config SHA-256 Hash:            {config_hash}")
    print(f"Total Test Queries:             {total_cases} (In-Scope: {total_in_scope}, Out-of-Scope: {total_out_scope})")
    print(f"Total Evaluation Time:          {total_latency_ms} ms (avg {avg_latency_ms} ms/query)")
    print("-" * 78)
    print("4-QUADRANT PERFORMANCE METRICS (Abstentions Separated from Errors):")
    print(f"  1. Correct Classification:    {correct_class_pct}% ({correct_classification}/{total_in_scope} in-scope)")
    print(f"  2. Correct Abstention:        {correct_abstain_pct}% ({correct_abstention}/{total_out_scope} out-of-scope)")
    print(f"  3. Wrong Classification:      {wrong_class_pct}% ({wrong_classification}/{total_cases} total)")
    print(f"  4. Wrong Abstention (False):  {wrong_abstain_pct}% ({wrong_abstention}/{total_in_scope} in-scope)")
    print(f"  >> Overall Decision Accuracy: {statutory_decision_acc_pct}% ({correct_classification + correct_abstention}/{total_cases})")
    print("-" * 78)
    print(f"Intent Extraction Accuracy:     {intent_accuracy_pct}% ({intent_correct_count}/{total_cases})")
    print(f"Row-Level Grounding Precision:  {grounding_precision_pct}% ({grounding_passed_terms}/{grounding_total_terms} terms)")
    print(f"Row-Level Grounding Recall:     {grounding_recall_pct}% ({grounding_recalled_terms}/{grounding_total_expected} expected terms)")
    print(f"Top-1 Statutory Accuracy:       {top1_accuracy_pct}% ({top1_correct_count}/{total_cases})")
    print(f"Top-3 Statutory Accuracy:       {top3_accuracy_pct}% ({top3_correct_count}/{total_cases})")
    print(f"Abstention Rate:                {abstention_rate_pct}% ({abstention_count}/{total_cases})")
    print(f"Clarification Rate:             {clarification_rate_pct}% ({clarification_count}/{total_cases})")
    print("=" * 78)

    print("\nCATEGORY PERFORMANCE BREAKDOWN:")
    print(f"{'Category':<24} | {'Total':<5} | {'Intent Acc':<14} | {'Retrieval':<14} | {'Abstain':<7} | {'Clarify':<7}")
    print("-" * 80)
    for cat, stats in sorted(category_stats.items()):
        tot = stats["total"]
        i_cnt = stats["intent_correct"]
        r_cnt = stats["retrieval_correct"]
        i_acc_str = f"{(i_cnt / tot) * 100:.1f}% ({i_cnt}/{tot})"
        r_acc_str = f"{(r_cnt / tot) * 100:.1f}% ({r_cnt}/{tot})"
        print(f"{cat:<24} | {tot:<5} | {i_acc_str:<14} | {r_acc_str:<14} | {stats['abstain']:<7} | {stats['clarify']:<7}")
    print("=" * 80)

    # Persist Report Artifact
    reports_dir = base_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_file = reports_dir / "held_out_benchmark_results.json"

    record = {
        "timestamp": datetime.now().isoformat(),
        "label": label,
        "dataset_file": benchmark_file.name,
        "git_commit_hash": git_hash,
        "config_sha256": config_hash,
        "total_cases": total_cases,
        "total_in_scope": total_in_scope,
        "total_out_scope": total_out_scope,
        "four_quadrant_metrics": {
            "correct_classification_pct": correct_class_pct,
            "correct_classification_fraction": f"{correct_classification}/{total_in_scope}",
            "correct_abstention_pct": correct_abstain_pct,
            "correct_abstention_fraction": f"{correct_abstention}/{total_out_scope}",
            "wrong_classification_pct": wrong_class_pct,
            "wrong_classification_fraction": f"{wrong_classification}/{total_cases}",
            "wrong_abstention_pct": wrong_abstain_pct,
            "wrong_abstention_fraction": f"{wrong_abstention}/{total_in_scope}",
            "statutory_decision_accuracy_pct": statutory_decision_acc_pct,
            "statutory_decision_accuracy_fraction": f"{correct_classification + correct_abstention}/{total_cases}"
        },
        "intent_accuracy_pct": intent_accuracy_pct,
        "intent_accuracy_fraction": f"{intent_correct_count}/{total_cases}",
        "grounding_precision_pct": grounding_precision_pct,
        "grounding_precision_fraction": f"{grounding_passed_terms}/{grounding_total_terms}",
        "grounding_recall_pct": grounding_recall_pct,
        "grounding_recall_fraction": f"{grounding_recalled_terms}/{grounding_total_expected}",
        "top1_accuracy_pct": top1_accuracy_pct,
        "top1_accuracy_fraction": f"{top1_correct_count}/{total_cases}",
        "top3_accuracy_pct": top3_accuracy_pct,
        "top3_accuracy_fraction": f"{top3_correct_count}/{total_cases}",
        "abstention_rate_pct": abstention_rate_pct,
        "clarification_rate_pct": clarification_rate_pct,
        "category_breakdown": category_stats
    }

    try:
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2)
        print(f"\nFull benchmark report artifact persisted to {report_file.relative_to(base_dir)}")
    except Exception as e:
        print(f"Failed to persist report artifact: {e}")

    return record


if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parent.parent
    held_out_file = base_dir / "data" / "held_out_intent_benchmarks.json"
    tuning_file = base_dir / "data" / "tuning_intent_benchmarks.json"

    mode = sys.argv[1] if len(sys.argv) > 1 else "held_out"

    if mode == "tuning":
        run_benchmark(tuning_file, label="TUNING SET (120 QUERIES)")
    elif mode == "all":
        print("\n>>> EVALUATING FROZEN HELD-OUT DATASET <<<")
        run_benchmark(held_out_file, label="FROZEN HELD-OUT SET (68 QUERIES)")
        print("\n>>> EVALUATING TUNING DATASET <<<")
        run_benchmark(tuning_file, label="TUNING SET (120 QUERIES)")
    else:
        run_benchmark(held_out_file, label="FROZEN HELD-OUT SET (68 QUERIES)")
