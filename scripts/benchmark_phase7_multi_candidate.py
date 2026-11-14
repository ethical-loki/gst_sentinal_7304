"""
Phase 7 & Phase 8 Fair Benchmark Report Generator (`scripts/benchmark_phase7_multi_candidate.py`).

Evaluates BOTH `HSNIntelligenceV2` (Phase 6) and `MultiCandidateEngine` (Phase 7/8)
on the identical 51-case `data/eval/generalized_test_suite.parquet` under identical
strict and clarification-aware scoring rules, PLUS evaluates exact 8-digit HSN
accuracy and progressive clarification resolution on the 35-case unseen
`data/eval/exact_hsn_eval_suite.parquet`.
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ml.hsn_v2_pipeline import HSNIntelligenceV2
from src.ml.multi_candidate_engine import MultiCandidateEngine


def _score_unified(
    *,
    mode: str,
    final_hsn: Optional[str],
    final_chapter: Optional[str],
    cand_hsns: List[str],
    cand_chaps: List[str],
    exp_hsn: str,
    exp_chap: str,
    is_active: bool,
    category: str,
) -> Tuple[bool, bool]:
    """
    Returns `(strict_ok, clarification_aware_ok)` using identical rules for Phase 6 & Phase 7.
    """
    if not is_active:
        ok = mode == "OUT_OF_SCHEDULE"
        return ok, ok

    if mode in ("EXACT_HSN", "CLEAR"):
        if exp_hsn and len(exp_hsn) == 8:
            ok = (final_hsn == exp_hsn) or (bool(final_chapter) and str(final_chapter).zfill(2) == exp_chap)
        else:
            ok = bool(final_chapter) and str(final_chapter).zfill(2) == exp_chap
        return ok, ok

    if mode in ("CHAPTER_ONLY_CLARIFY", "CLARIFY_AMBIGUOUS", "AMBIGUOUS_MATERIAL", "AMBIGUOUS_SPECIFICATION"):
        ok = bool(final_chapter) and str(final_chapter).zfill(2) == exp_chap
        return ok, ok

    if mode == "MULTIPLE_CANDIDATES":
        ok = (exp_hsn in cand_hsns) or (exp_chap in cand_chaps[:8])
        return ok, ok

    if mode == "INSUFFICIENT_INFORMATION":
        # Strict mode treats abstention as False; clarification-aware treats abstention
        # on genuinely underspecified/ambiguous categories as safe abstention.
        safe_cat = category in ("ambiguous_material", "ambiguous_specification", "insufficient_info")
        return False, safe_cat

    return False, False


def main() -> None:
    suite_path = PROJECT_ROOT / "data" / "eval" / "generalized_test_suite.parquet"
    df = pd.read_parquet(suite_path)

    v2 = HSNIntelligenceV2()
    engine = MultiCandidateEngine(
        hybrid_engine=v2.hybrid_engine,
        relevance_classifier=v2.classifier,
        statutory_index=v2.statutory_index,
        feedback_collector=v2.feedback,
        initial_branch_k=30,
        max_eval_budget=250,
    )

    # ── 1. Fair Head-to-Head on 51-case Generalized Suite ───────────────────────
    p6_lats: List[float] = []
    p6_modes = Counter()
    p6_strict, p6_aware = 0, 0

    p7_lats: List[float] = []
    p7_modes = Counter()
    p7_strict, p7_aware = 0, 0
    by_cat: Dict[str, Dict[str, int]] = {}

    chap_ok, chap_n = 0, 0
    multi_ok, multi_n = 0, 0
    clar_ok, clar_n = 0, 0
    oos_ok, oos_n = 0, 0

    cand_precisions: List[float] = []
    alt_counts: List[int] = []
    dup_rates: List[float] = []
    complete_count = 0
    recall_at_pool_hits = 0
    active_total = 0

    for _, row in df.iterrows():
        q = str(row["query"])
        cat = str(row["category"])
        exp_hsn = str(row["expected_hsn"]).strip()
        exp_chap = str(row["expected_chapter"]).strip().zfill(2)
        is_active = bool(row["is_active_schedule"])

        # Phase 6 evaluation
        t0 = time.perf_counter()
        v2_res = v2.classify(q)
        p6_lats.append((time.perf_counter() - t0) * 1000.0)
        p6_mode = str(getattr(v2_res, "prediction_mode", None) or getattr(v2_res, "status", None) or "INSUFFICIENT_INFORMATION")
        p6_modes[p6_mode] += 1
        p6_cands = getattr(v2_res, "statutory_matches", None) or []
        p6_hsns = [str(c.get("hsn_code", "")) for c in p6_cands]
        p6_chaps = [str(c.get("chapter_code", "") or str(c.get("hsn_code", ""))[:2]).zfill(2) for c in p6_cands if c.get("chapter_code") or c.get("hsn_code")]
        s6, a6 = _score_unified(
            mode=p6_mode,
            final_hsn=getattr(v2_res, "selected_hsn", None),
            final_chapter=getattr(v2_res, "selected_chapter", None),
            cand_hsns=p6_hsns,
            cand_chaps=p6_chaps,
            exp_hsn=exp_hsn,
            exp_chap=exp_chap,
            is_active=is_active,
            category=cat,
        )
        p6_strict += int(s6)
        p6_aware += int(a6)

        # Phase 7/8 evaluation
        res = engine.classify_adaptive(q, page=1, page_size=None)
        mode = res["prediction_mode"]
        p7_modes[mode] += 1
        p7_lats.append(float(res["audit"]["execution_metrics"]["total_time_ms"]))
        if res["discovery"]["discovery_complete"]:
            complete_count += 1

        cands = res["candidates"]
        alt_counts.append(len(cands))
        dup_grps = [g["count"] - 1 for g in res["candidate_groups"] if g["group_type"] == "DUPLICATE_DESCRIPTION"]
        dup_rates.append(sum(dup_grps) / max(len(cands), 1))

        cand_hsns = [c["hsn_code"] for c in cands]
        cand_chaps = [str(c["chapter_code"]).zfill(2) for c in cands]

        if is_active:
            active_total += 1
            if exp_hsn in cand_hsns or exp_chap in cand_chaps:
                recall_at_pool_hits += 1
            if cands:
                chap_hits_in_pool = sum(1 for ch in cand_chaps if ch == exp_chap)
                cand_precisions.append(chap_hits_in_pool / len(cands))

        s7, a7 = _score_unified(
            mode=mode,
            final_hsn=res["final_hsn"],
            final_chapter=res["final_chapter"],
            cand_hsns=cand_hsns,
            cand_chaps=cand_chaps,
            exp_hsn=exp_hsn,
            exp_chap=exp_chap,
            is_active=is_active,
            category=cat,
        )
        p7_strict += int(s7)
        p7_aware += int(a7)

        if not is_active:
            oos_n += 1
            if s7:
                oos_ok += 1
        else:
            if mode in ("EXACT_HSN", "CHAPTER_ONLY_CLARIFY"):
                chap_n += 1
                if res["final_chapter"] and str(res["final_chapter"]).zfill(2) == exp_chap:
                    chap_ok += 1
            if mode in ("CHAPTER_ONLY_CLARIFY", "MULTIPLE_CANDIDATES"):
                clar_n += 1
                if s7:
                    clar_ok += 1
            if mode == "MULTIPLE_CANDIDATES":
                multi_n += 1
                if s7:
                    multi_ok += 1

        b = by_cat.setdefault(cat, {"total": 0, "strict_passed": 0, "aware_passed": 0})
        b["total"] += 1
        b["strict_passed"] += int(s7)
        b["aware_passed"] += int(a7)

    # ── 2. Exhaustive-reference recall check on 5 active queries (up to 600-record deep scan) ──
    exh_engine = MultiCandidateEngine(
        hybrid_engine=v2.hybrid_engine,
        relevance_classifier=v2.classifier,
        statutory_index=v2.statutory_index,
        feedback_collector=v2.feedback,
        initial_branch_k=600,
        max_eval_budget=600,
    )
    active_5 = df[df["is_active_schedule"] == True].head(5)
    exh_adaptive_hits = 0
    exh_ref_hits = 0
    for _, row in active_5.iterrows():
        q = str(row["query"])
        exp_hsn = str(row["expected_hsn"]).strip()
        exp_chap = str(row["expected_chapter"]).strip().zfill(2)
        ad_res = engine.classify_adaptive(q, page=1, page_size=None, exhaustive=False)
        ex_res = exh_engine.classify_adaptive(q, page=1, page_size=None, exhaustive=False)
        ad_set = {c["hsn_code"] for c in ad_res["candidates"]} | {str(c["chapter_code"]).zfill(2) for c in ad_res["candidates"]}
        ex_set = {c["hsn_code"] for c in ex_res["candidates"]} | {str(c["chapter_code"]).zfill(2) for c in ex_res["candidates"]}
        if exp_hsn in ad_set or exp_chap in ad_set:
            exh_adaptive_hits += 1
        if exp_hsn in ex_set or exp_chap in ex_set:
            exh_ref_hits += 1

    # ── 3. Verified Exact-HSN & Progressive Clarification Evaluation (35 unseen cases) ──
    exact_eval_path = PROJECT_ROOT / "data" / "eval" / "exact_hsn_eval_suite.parquet"
    exact_eval_summary: Dict[str, Any] = {}
    if exact_eval_path.exists():
        edf = pd.read_parquet(exact_eval_path)
        det_df = edf[edf["case_type"] == "exact_detailed"]
        amb_df = edf[edf["case_type"] == "ambiguous_with_clarification"]

        det_exact_hits, det_exact_cov, det_abstain, det_chap_hits, det_pool_recall = 0, 0, 0, 0, 0
        for _, r in det_df.iterrows():
            res = engine.classify_adaptive(str(r["query"]), page=1, page_size=None)
            exp_hsn = str(r["expected_hsn"]).strip()
            exp_chap = str(r["expected_chapter"]).strip().zfill(2)
            cand_hsns = [c["hsn_code"] for c in res["candidates"]]
            if exp_hsn in cand_hsns:
                det_pool_recall += 1
            if res["final_chapter"] and str(res["final_chapter"]).zfill(2) == exp_chap:
                det_chap_hits += 1
            if res["prediction_mode"] == "EXACT_HSN":
                det_exact_cov += 1
                if res["final_hsn"] == exp_hsn:
                    det_exact_hits += 1
            elif res["prediction_mode"] == "INSUFFICIENT_INFORMATION":
                det_abstain += 1

        amb_before_exact, amb_after_exact = 0, 0
        amb_before_recall, amb_after_recall = 0, 0
        for _, r in amb_df.iterrows():
            q = str(r["query"])
            exp_hsn = str(r["expected_hsn"]).strip()
            attrs = json.loads(str(r["clarification_attributes_json"] or "{}"))
            b_res = engine.classify_adaptive(q, page=1, page_size=None)
            a_res = engine.clarify_and_refine(q, previous_confirmed={}, new_answers=attrs, page=1, page_size=None)
            if exp_hsn in [c["hsn_code"] for c in b_res["candidates"]]:
                amb_before_recall += 1
            if exp_hsn in [c["hsn_code"] for c in a_res["candidates"]]:
                amb_after_recall += 1
            if b_res["prediction_mode"] == "EXACT_HSN" and b_res["final_hsn"] == exp_hsn:
                amb_before_exact += 1
            if a_res["prediction_mode"] == "EXACT_HSN" and a_res["final_hsn"] == exp_hsn:
                amb_after_exact += 1

        exact_eval_summary = {
            "total_unseen_cases": len(edf),
            "detailed_cases": len(det_df),
            "detailed_exact_hsn_accuracy_given_exact": round(det_exact_hits / max(det_exact_cov, 1), 4),
            "detailed_exact_hsn_overall_accuracy": round(det_exact_hits / max(len(det_df), 1), 4),
            "detailed_exact_hsn_coverage": round(det_exact_cov / max(len(det_df), 1), 4),
            "detailed_abstention_rate": round(det_abstain / max(len(det_df), 1), 4),
            "detailed_chapter_accuracy": round(det_chap_hits / max(len(det_df), 1), 4),
            "detailed_candidate_pool_recall": round(det_pool_recall / max(len(det_df), 1), 4),
            "clarification_cases": len(amb_df),
            "clarification_before_exact_hsn_hits": f"{amb_before_exact}/{len(amb_df)}",
            "clarification_after_exact_hsn_hits": f"{amb_after_exact}/{len(amb_df)}",
            "clarification_before_pool_recall": f"{amb_before_recall}/{len(amb_df)}",
            "clarification_after_pool_recall": f"{amb_after_recall}/{len(amb_df)}",
        }

    report = {
        "total_cases": len(df),
        "fair_comparison_51_cases": {
            "phase6_v2": {
                "strict_passed": p6_strict,
                "strict_pass_rate": round(p6_strict / max(len(df), 1), 4),
                "clarification_aware_passed": p6_aware,
                "clarification_aware_pass_rate": round(p6_aware / max(len(df), 1), 4),
                "prediction_modes": dict(p6_modes),
                "latency_mean_ms": round(float(np.mean(p6_lats)), 2),
                "latency_p95_ms": round(float(np.percentile(p6_lats, 95)), 2),
            },
            "phase7_8_adaptive": {
                "strict_passed": p7_strict,
                "strict_pass_rate": round(p7_strict / max(len(df), 1), 4),
                "clarification_aware_passed": p7_aware,
                "clarification_aware_pass_rate": round(p7_aware / max(len(df), 1), 4),
                "prediction_modes": dict(p7_modes),
                "latency_mean_ms": round(float(np.mean(p7_lats)), 2),
                "latency_p95_ms": round(float(np.percentile(p7_lats, 95)), 2),
            },
        },
        "metrics": {
            "candidate_recall_at_pool_active": round(recall_at_pool_hits / max(active_total, 1), 4),
            "exhaustive_reference_recall_5q": f"{exh_adaptive_hits}/{exh_ref_hits}",
            "candidate_precision_mean": round(float(np.mean(cand_precisions)) if cand_precisions else 0.0, 4),
            "alternative_coverage_mean_candidates": round(float(np.mean(alt_counts)) if alt_counts else 0.0, 2),
            "duplicate_rate_mean": round(float(np.mean(dup_rates)) if dup_rates else 0.0, 4),
            "discovery_completeness_rate": round(complete_count / max(len(df), 1), 4),
            "chapter_prediction_accuracy": f"{chap_ok}/{chap_n}" if chap_n else "N/A",
            "multiple_candidate_coverage": f"{multi_ok}/{multi_n}" if multi_n else "N/A",
            "clarification_necessity_accuracy": f"{clar_ok}/{clar_n}" if clar_n else "N/A",
            "out_of_schedule_accuracy": f"{oos_ok}/{oos_n}" if oos_n else "N/A",
            "latency_mean_ms": round(float(np.mean(p7_lats)) if p7_lats else 0.0, 2),
            "latency_p95_ms": round(float(np.percentile(p7_lats, 95)) if p7_lats else 0.0, 2),
        },
        "exact_hsn_unseen_evaluation": exact_eval_summary,
        "by_category": {
            k: {
                **v,
                "strict_pass_rate": round(v["strict_passed"] / v["total"], 4),
                "aware_pass_rate": round(v["aware_passed"] / v["total"], 4),
            }
            for k, v in sorted(by_cat.items())
        },
    }

    out_path = PROJECT_ROOT / "reports" / "phase7_benchmark_report.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
