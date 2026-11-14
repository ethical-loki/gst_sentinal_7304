"""
Step 7: Complete 9-Field End-to-End Pipeline Trace & Layer Attribution Audit.

Runs `HSNIntelligenceV2` (and `IntentExtractor` when available / fallback deterministic)
over `data/eval/generalized_test_suite.parquet`, capturing all 9 required trace fields
for every test case so we can pinpoint which layer causes any error.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ml.hsn_v2_pipeline import HSNIntelligenceV2
from src.training.generalized_test_builder import build_generalized_test_dataset


def _get_intent_extractor():
    try:
        from src.nlp.intent_extractor import IntentExtractor
        ext = IntentExtractor()
        if getattr(ext, "client", None) is not None:
            return ext
    except Exception:
        pass
    return None


def _safe_intent_extract(query: str, extractor: Any = None) -> Dict[str, Any]:
    """
    Runs IntentExtractor if available, otherwise uses a deterministic
    grounded fallback so Step 7 works offline & fast.
    """
    if extractor is not None:
        try:
            intent = extractor.extract_intent(query)
            return {
                "product_type": intent.product_type,
                "material": intent.material,
                "use_case": intent.use_case,
                "grounded_search_terms": intent.search_terms or [query],
                "mode": "llm",
            }
        except Exception:
            pass
    return {
        "product_type": query,
        "material": None,
        "use_case": None,
        "grounded_search_terms": [query],
        "mode": "deterministic_fallback",
    }


def evaluate_pipeline(limit: int = 56, use_llm: bool = False) -> Dict[str, Any]:
    suite_path = PROJECT_ROOT / "data" / "eval" / "generalized_test_suite.parquet"
    if not suite_path.exists():
        df = build_generalized_test_dataset()
    else:
        df = pd.read_parquet(suite_path)

    if limit and limit < len(df):
        df = df.head(limit).reset_index(drop=True)

    pipeline = HSNIntelligenceV2()
    extractor = _get_intent_extractor() if use_llm else None
    traces: List[Dict[str, Any]] = []
    layer_attribution = Counter()
    category_summary: Dict[str, Dict[str, int]] = {}

    t0 = time.perf_counter()
    for _, row in df.iterrows():
        q = str(row["query"])
        cat = str(row["category"])
        exp_hsn = str(row["expected_hsn"]).strip()
        exp_chap = str(row["expected_chapter"]).strip().zfill(2)
        is_active = bool(row["is_active_schedule"])

        intent_info = _safe_intent_extract(q, extractor=extractor)
        search_terms = intent_info["grounded_search_terms"]
        effective_query = " ".join(search_terms[:2]) if search_terms else q

        # Capture raw retrieved candidates before reranking, plus Cross-Encoder + 4-class relevance
        expanded_q, _ = pipeline.hybrid_engine._expand_abbreviated_query(effective_query)
        raw_pool = pipeline.hybrid_engine.retrieve_pool(effective_query, pool_size=30, branch_k=45)
        retrieved_hsns = [str(r.get("hsn_code") or "").strip() for r in raw_pool]
        retrieved_chaps = [str(r.get("chapter_code") or "").strip().zfill(2) for r in raw_pool]
        classified_cands = pipeline.classifier.classify(expanded_q or effective_query, raw_pool) if raw_pool else []

        res = pipeline.classify(effective_query)

        # Layer-by-layer correctness & attribution
        if not is_active:
            correct = res.status == "OUT_OF_SCHEDULE"
            if correct:
                blame = "PASS_OUT_OF_SCHEDULE"
            else:
                blame = "SCHEDULE_VERIFICATION_MISS"
        else:
            if res.selected_hsn == exp_hsn:
                correct = True
                blame = "PASS_EXACT_HSN"
            elif res.selected_chapter and res.selected_chapter.zfill(2) == exp_chap:
                correct = True
                blame = "PASS_CHAPTER_MATCH"
            elif res.status in {"AMBIGUOUS_MATERIAL", "AMBIGUOUS_SPECIFICATION", "INSUFFICIENT_INFORMATION"}:
                opt_str = " ".join(
                    str(opt.get("chapter_code", "") if isinstance(opt, dict) else opt)
                    for opt in res.clarification_options
                )
                correct = (exp_hsn in opt_str) or (exp_chap in opt_str) or (exp_chap in retrieved_chaps[:5])
                blame = "PASS_CLARIFICATION" if correct else "AMBIGUITY_MISS"
            elif exp_hsn not in retrieved_hsns and exp_chap not in retrieved_chaps:
                correct = False
                blame = "LAYER2_RETRIEVAL_MISS"
            elif res.status == "OUT_OF_SCHEDULE":
                correct = False
                blame = "SCHEDULE_FALSE_POSITIVE"
            else:
                correct = False
                blame = "LAYER3_RERANKER_OR_THRESHOLD_MISS"

        layer_attribution[blame] += 1
        bucket = category_summary.setdefault(cat, {"total": 0, "passed": 0})
        bucket["total"] += 1
        if correct:
            bucket["passed"] += 1

        trace = {
            "category": cat,
            "expected_hsn": exp_hsn,
            "expected_chapter": exp_chap,
            "is_active_schedule": is_active,
            "correct": correct,
            "layer_attribution": blame,
            # 9 required trace fields:
            "1_original_input": q,
            "2_extracted_intent": {
                "product_type": intent_info["product_type"],
                "material": intent_info["material"],
                "use_case": intent_info["use_case"],
                "mode": intent_info["mode"],
            },
            "3_grounded_search_terms": search_terms,
            "4_retrieved_candidates": [
                {
                    "hsn_code": str(r.get("hsn_code") or ""),
                    "chapter": str(r.get("chapter_code") or ""),
                    "desc": str(r.get("statutory_description") or "")[:90],
                }
                for r in raw_pool[:10]
            ],
            "5_cross_encoder_scores": [
                {
                    "hsn_code": c.candidate.hsn_code,
                    "chapter": c.candidate.chapter_code,
                    "score": round(c.confidence, 4),
                }
                for c in classified_cands[:10]
            ],
            "6_relevance_classifications": [
                {
                    "hsn_code": c.candidate.hsn_code,
                    "relation": c.relation.value,
                    "score": round(c.confidence, 4),
                }
                for c in classified_cands[:10]
            ],
            "7_ambiguity_decision": {
                "status": res.status,
                "separating_attributes": res.separating_attributes,
                "clarification_question": res.clarification_question,
            },
            "8_active_vs_complete_schedule": res.active_vs_statutory,
            "9_final_prediction": {
                "status": res.status,
                "selected_hsn": res.selected_hsn,
                "selected_chapter": res.selected_chapter,
                "confidence": res.confidence,
                "clarification_options": res.clarification_options[:5],
            },
        }
        traces.append(trace)

    elapsed = round(time.perf_counter() - t0, 2)
    total = len(traces)
    passed = sum(1 for t in traces if t["correct"])
    report = {
        "total_cases": total,
        "passed_cases": passed,
        "overall_pass_rate": round(passed / max(total, 1), 4),
        "elapsed_sec": elapsed,
        "layer_attribution": dict(layer_attribution),
        "by_category": {
            k: {
                "total": v["total"],
                "passed": v["passed"],
                "pass_rate": round(v["passed"] / max(v["total"], 1), 4),
            }
            for k, v in sorted(category_summary.items())
        },
        "traces": traces,
    }

    out_path = PROJECT_ROOT / "reports" / "step7_full_pipeline_trace.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=56)
    parser.add_argument("--use-llm", action="store_true")
    args = parser.parse_args()
    rep = evaluate_pipeline(limit=args.limit, use_llm=args.use_llm)
    print(json.dumps({
        "total_cases": rep["total_cases"],
        "passed_cases": rep["passed_cases"],
        "overall_pass_rate": rep["overall_pass_rate"],
        "elapsed_sec": rep["elapsed_sec"],
        "layer_attribution": rep["layer_attribution"],
        "by_category": rep["by_category"],
    }, indent=2))


if __name__ == "__main__":
    main()
