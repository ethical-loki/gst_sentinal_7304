"""
Phase 10 Stage 4: Independent Confidence Recalibration & Leakage-Resistant Eval Builder.

1. Builds `data/eval/independent_exact_hsn_eval.parquet` from 8-digit leaf HSNs
   with ZERO overlap against train, val, generalized_test_suite, generalized_test_large,
   and exact_hsn_eval_suite.
2. Evaluates the existing `calibration.json` on non-truncated Stage 1-3 outputs over
   a held-out validation split (`full_pairs_val.parquet` excluding all eval HSNs).
3. Refits `chapter_calibrator` and `hsn_calibrator` on the disjoint fit split,
   reports NLL / Brier / ECE / selective accuracy before vs after, and updates
   `data/model_versions/hsn_reranker_v1/calibration.json` if Brier/ECE improve.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Set

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ml.confidence_calibrator import (
    CalibrationBundle,
    LogisticFeatureCalibrator,
    compute_calibration_metrics,
    compute_selective_curve,
    extract_query_confidence_features,
)
from src.ml.multi_candidate_engine import MultiCandidateEngine, _is_leaf_8digit
from src.ml.relevance_classifier import RelationLabel


def _clean_text(val: object) -> str:
    s = str(val or "").strip()
    if s.lower() in ("", "nan", "none", "other", "others", "-"):
        return ""
    return re.sub(r"\s+", " ", s).strip()


def build_independent_eval_suite(excluded_hsns: Set[str]) -> Path:
    master = pd.read_parquet(PROJECT_ROOT / "data" / "enriched_master_hsn.parquet")
    leaf = master[master["hsn_code"].astype(str).str.strip().str.len() == 8].copy()
    leaf["hsn_code"] = leaf["hsn_code"].astype(str).str.strip()
    leaf["chapter_code"] = leaf["chapter_code"].astype(str).str.strip().str.zfill(2)
    leaf = leaf[~leaf["hsn_code"].isin(excluded_hsns)].copy()

    desc_counts = leaf["statutory_description"].astype(str).str.lower().value_counts()
    leaf["desc_freq"] = leaf["statutory_description"].astype(str).str.lower().map(desc_counts)

    rows: List[Dict[str, Any]] = []
    for ch in sorted(leaf["chapter_code"].unique()):
        ch_df = leaf[
            (leaf["chapter_code"] == ch)
            & (leaf["desc_freq"] == 1)
            & (leaf["tariff_item_desc"].apply(lambda x: len(_clean_text(x)) >= 12))
        ].reset_index(drop=True)
        for idx in range(min(3, len(ch_df))):
            r = ch_df.iloc[idx]
            h4 = _clean_text(r["heading_4digit_desc"])
            s6 = _clean_text(r["subheading_6digit_desc"])
            t8 = _clean_text(r["tariff_item_desc"])
            mat = _clean_text(r["material_keywords"])
            parts = []
            for p in (h4, s6, t8):
                if p and p.lower() not in " ".join(parts).lower():
                    parts.append(p)
            q = " - ".join(parts)
            if mat and mat.lower() not in q.lower():
                q = f"{q} ({mat.split(',')[0].strip()})"
            rows.append({
                "case_type": "independent_exact",
                "query": q,
                "expected_hsn": r["hsn_code"],
                "expected_chapter": ch,
                "is_active_schedule": True,
            })

    out_path = PROJECT_ROOT / "data" / "eval" / "independent_exact_hsn_eval.parquet"
    pd.DataFrame(rows).to_parquet(out_path, index=False)
    print(f"Built {len(rows)} zero-leakage independent eval cases -> {out_path}")
    return out_path


def _collect_features(
    eng: MultiCandidateEngine,
    df_queries: pd.DataFrame,
    tag: str = "split",
) -> tuple[List[Dict[str, float]], List[int], List[int]]:
    feats_list: List[Dict[str, float]] = []
    chap_labels: List[int] = []
    hsn_labels: List[int] = []
    total = len(df_queries)

    for idx_i, (_, r) in enumerate(df_queries.iterrows(), start=1):
        q = str(r["query"]).strip()
        gold_hsn = str(r["hsn_code"]).strip()
        gold_ch = str(r["chapter_code"]).strip().zfill(2)

        res = eng.classify_adaptive(q, page=1, page_size=None)
        if idx_i % 10 == 0 or idx_i == total:
            print(f"[{tag}] {idx_i}/{total} collected", flush=True)
        cands = [c for c in res.get("candidates", []) if len(str(c.get("hsn_code", ""))) >= 8]
        if not cands:
            continue

        conf_pool = [
            c for c in cands
            if c.get("relevance_category") == "SAME_PRODUCT"
            or (c.get("evidence_trace") or {}).get("rescued_by_statutory_evidence")
        ] or cands
        import math
        p_thr = min(0.99, max(0.01, float(getattr(eng.classifier, "same_product_threshold", 0.725))))
        rel_thr_logit = math.log(p_thr / (1.0 - p_thr))
        same_h4s = {c["hsn_code"][:4] for c in cands if c.get("relevance_category") == "SAME_PRODUCT"}
        stat_dist = res.get("statutory_distinction") or {}
        feats = extract_query_confidence_features(
            raw_logits=[float(c.get("raw_logit") or 0.0) for c in conf_pool],
            hsn_codes=[c["hsn_code"] for c in conf_pool],
            chapter_codes=[c["chapter_code"] for c in conf_pool],
            query=q,
            rel_threshold_logit=rel_thr_logit,
            is_ambiguous=len(same_h4s) > 1,
            statutory_clear_winner=1.0 if stat_dist.get("winner_has_clear_evidence") else 0.0,
            statutory_evidence_margin=float(stat_dist.get("evidence_margin") or 0.0),
        )
        pred_hsn = cands[0]["hsn_code"]
        pred_ch = str(cands[0]["chapter_code"]).strip().zfill(2)

        feats_list.append(feats)
        chap_labels.append(1 if pred_ch == gold_ch else 0)
        hsn_labels.append(1 if pred_hsn == gold_hsn else 0)

    return feats_list, chap_labels, hsn_labels


def main() -> None:
    # 1. Gather all eval/train HSNs to guarantee zero leakage
    excluded_hsns: Set[str] = set()
    for p in (
        PROJECT_ROOT / "data" / "eval" / "generalized_test_suite.parquet",
        PROJECT_ROOT / "data" / "eval" / "generalized_test_large.parquet",
        PROJECT_ROOT / "data" / "eval" / "exact_hsn_eval_suite.parquet",
    ):
        if p.exists():
            d = pd.read_parquet(p)
            excluded_hsns.update(d["expected_hsn"].astype(str).str.strip())

    from scripts.benchmark_phase17_independent import INDEPENDENT_100
    for item in INDEPENDENT_100:
        excluded_hsns.add(item["expected_hsn"])

    train_df = pd.read_parquet(PROJECT_ROOT / "data" / "training_pairs" / "full_pairs_train.parquet")
    val_df = pd.read_parquet(PROJECT_ROOT / "data" / "training_pairs" / "full_pairs_val.parquet")

    train_val_hsns = set(train_df["hsn_code"].astype(str).str.strip()) | set(val_df["hsn_code"].astype(str).str.strip())
    build_independent_eval_suite(excluded_hsns | train_val_hsns)

    # 2. Prepare disjoint calibration fit (60 queries) and eval (40 queries) from full_pairs_val
    pos_val = val_df[
        (val_df["label"] == 1)
        & (val_df["hsn_code"].astype(str).str.strip().str.len() == 8)
        & (~val_df["hsn_code"].astype(str).str.strip().isin(excluded_hsns))
    ].drop_duplicates(subset=["query"]).reset_index(drop=True)

    # Split by HSN code so fit and eval have zero HSN overlap
    unique_val_hsns = pos_val["hsn_code"].astype(str).str.strip().unique().tolist()
    split_idx = int(len(unique_val_hsns) * 0.60)
    fit_hsns = set(unique_val_hsns[:split_idx])
    eval_hsns = set(unique_val_hsns[split_idx:])

    fit_df = pos_val[pos_val["hsn_code"].astype(str).str.strip().isin(fit_hsns)].head(60).reset_index(drop=True)
    eval_df = pos_val[pos_val["hsn_code"].astype(str).str.strip().isin(eval_hsns)].head(40).reset_index(drop=True)
    print(f"Calibration fit queries: {len(fit_df)}, eval queries: {len(eval_df)}")

    eng = MultiCandidateEngine()
    from src.ml.model_registry import ModelRegistry
    active_entry = ModelRegistry().get_active_entry()
    active_dir = Path(active_entry["model_path"]) if active_entry and active_entry.get("model_path") else (PROJECT_ROOT / "data" / "model_versions" / "hsn_reranker_v1")
    cal_path = active_dir / "calibration.json"
    v1_cal_path = PROJECT_ROOT / "data" / "model_versions" / "hsn_reranker_v1" / "calibration.json"
    if cal_path.exists():
        old_bundle = CalibrationBundle.load(cal_path)
    elif v1_cal_path.exists():
        old_bundle = CalibrationBundle.load(v1_cal_path)
    else:
        old_bundle = CalibrationBundle(tau_abstain=0.40, tau_chapter=0.50, tau_exact_hsn=0.55)

    fit_feats, fit_chap_y, fit_hsn_y = _collect_features(eng, fit_df, tag="fit")
    eval_feats, eval_chap_y, eval_hsn_y = _collect_features(eng, eval_df, tag="eval")

    # Evaluate OLD bundle on eval split
    old_hsn_probs = old_bundle.hsn_calibrator.predict_proba(eval_feats)
    old_chap_probs = old_bundle.chapter_calibrator.predict_proba(eval_feats)
    old_hsn_metrics = compute_calibration_metrics(eval_hsn_y, old_hsn_probs)
    old_chap_metrics = compute_calibration_metrics(eval_chap_y, old_chap_probs)

    # Fit NEW calibrators on fit split (keep thresholds tau_abstain=0.40, tau_chapter=0.50, tau_exact_hsn=0.55)
    # Enforce monotonic directional signs on structural ambiguity vs statutory distinction features
    # so small-sample collinearity cannot invert unambiguous single-heading weights.
    hsn_signs = {
        "top1_logit": 1,
        "top1_top2_margin": 1,
        "n_siblings_same_heading": -1,
        "n_distinct_headings_above": -1,
        "n_distinct_chapters_above": -1,
        "is_ambiguous": -1,
        "statutory_clear_winner": 1,
        "statutory_evidence_margin": 1,
    }
    new_chap_cal = LogisticFeatureCalibrator().fit(
        fit_feats, fit_chap_y, l2=0.08, lr=0.1, steps=1200,
        sign_constraints={"top1_logit": 1, "top1_top2_margin": 1, "n_distinct_chapters_above": -1},
    )
    new_hsn_cal = LogisticFeatureCalibrator().fit(
        fit_feats, fit_hsn_y, l2=0.08, lr=0.1, steps=1200, sign_constraints=hsn_signs
    )

    new_hsn_probs = new_hsn_cal.predict_proba(eval_feats)
    new_chap_probs = new_chap_cal.predict_proba(eval_feats)
    new_hsn_metrics = compute_calibration_metrics(eval_hsn_y, new_hsn_probs)
    new_chap_metrics = compute_calibration_metrics(eval_chap_y, new_chap_probs)
    new_selective = compute_selective_curve(eval_hsn_y, new_hsn_probs)

    cal_report = {
        "model_dir": str(active_dir),
        "fit_n": len(fit_feats),
        "eval_n": len(eval_feats),
        "fit_hsn_base_accuracy": round(float(np.mean(fit_hsn_y)), 4),
        "eval_hsn_base_accuracy": round(float(np.mean(eval_hsn_y)), 4),
        "eval_chapter_base_accuracy": round(float(np.mean(eval_chap_y)), 4),
        "old_hsn_calibration": old_hsn_metrics,
        "new_hsn_calibration": new_hsn_metrics,
        "old_chapter_calibration": old_chap_metrics,
        "new_chapter_calibration": new_chap_metrics,
        "new_hsn_selective_curve": new_selective,
        "new_hsn_weights": new_hsn_cal.weights,
        "new_hsn_bias": round(float(new_hsn_cal.bias), 6),
    }

    # Save updated calibration bundle if Brier improves or new model lacks calibration.json
    if (not cal_path.exists()) or (new_hsn_metrics["brier"] <= old_hsn_metrics["brier"]):
        new_bundle = CalibrationBundle(
            relevance_calibrator=old_bundle.relevance_calibrator,
            chapter_calibrator=new_chap_cal,
            hsn_calibrator=new_hsn_cal,
            tau_abstain=old_bundle.tau_abstain,
            tau_chapter=old_bundle.tau_chapter,
            tau_exact_hsn=old_bundle.tau_exact_hsn,
            metadata={
                **old_bundle.metadata,
                "model_path": str(active_dir),
                "phase3_recalibrated": True,
                "phase3_fit_n": len(fit_feats),
                "phase3_eval_n": len(eval_feats),
            },
        )
        new_bundle.save(cal_path)
        cal_report["calibration_updated"] = True
    else:
        cal_report["calibration_updated"] = False

    rep_path = PROJECT_ROOT / "reports" / "phase10_calibration_report.json"
    rep_path.write_text(json.dumps(cal_report, indent=2), encoding="utf-8")
    print(json.dumps(cal_report, indent=2))


if __name__ == "__main__":
    main()

