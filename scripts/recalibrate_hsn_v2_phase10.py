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
) -> tuple[List[Dict[str, float]], List[int], List[int]]:
    feats_list: List[Dict[str, float]] = []
    chap_labels: List[int] = []
    hsn_labels: List[int] = []

    for _, r in df_queries.iterrows():
        q = str(r["query"]).strip()
        gold_hsn = str(r["hsn_code"]).strip()
        gold_ch = str(r["chapter_code"]).strip().zfill(2)

        disc = eng.discoverer.discover(q)
        qual = disc.qualifying_classified
        leaves = [c for c in qual if _is_leaf_8digit(c)] or qual
        same_leaves = [c for c in leaves if c.relation == RelationLabel.SAME_PRODUCT]

        # Apply Stage 3 ordering if available
        if same_leaves:
            from src.ml.ambiguity_resolver import analyze_sibling_distinctions
            da = analyze_sibling_distinctions(same_leaves[:20], q)
            if da.get("ranked_indices"):
                same_leaves = [same_leaves[i] for i in da["ranked_indices"]] + same_leaves[20:]
                seen = {id(c) for c in same_leaves}
                leaves = same_leaves + [c for c in leaves if id(c) not in seen]

        if not leaves:
            continue

        feats = extract_query_confidence_features(
            raw_logits=[c.candidate.raw_logit for c in leaves],
            hsn_codes=[c.candidate.hsn_code for c in leaves],
            chapter_codes=[c.candidate.chapter_code for c in leaves],
            query=q,
            rel_threshold_logit=0.97,
            is_ambiguous=len({c.candidate.hsn_code[:4] for c in same_leaves}) > 1,
        )
        pred_hsn = leaves[0].candidate.hsn_code
        pred_ch = str(leaves[0].candidate.chapter_code).strip().zfill(2)

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

    train_df = pd.read_parquet(PROJECT_ROOT / "data" / "training_pairs" / "full_pairs_train.parquet")
    val_df = pd.read_parquet(PROJECT_ROOT / "data" / "training_pairs" / "full_pairs_val.parquet")

    train_val_hsns = set(train_df["hsn_code"].astype(str).str.strip()) | set(val_df["hsn_code"].astype(str).str.strip())
    build_independent_eval_suite(excluded_hsns | train_val_hsns)

    # 2. Prepare disjoint calibration fit (80 queries) and eval (50 queries) from full_pairs_val
    pos_val = val_df[
        (val_df["label"] == 1)
        & (val_df["hsn_code"].astype(str).str.strip().str.len() == 8)
        & (~val_df["hsn_code"].astype(str).str.strip().isin(excluded_hsns))
    ].drop_duplicates(subset=["query"]).reset_index(drop=True)

    # Split by HSN code so fit and eval have zero HSN overlap
    unique_val_hsns = pos_val["hsn_code"].astype(str).str.strip().unique().tolist()
    split_idx = int(len(unique_val_hsns) * 0.6)
    fit_hsns = set(unique_val_hsns[:split_idx])
    eval_hsns = set(unique_val_hsns[split_idx:])

    fit_df = pos_val[pos_val["hsn_code"].astype(str).str.strip().isin(fit_hsns)].head(80).reset_index(drop=True)
    eval_df = pos_val[pos_val["hsn_code"].astype(str).str.strip().isin(eval_hsns)].head(50).reset_index(drop=True)
    print(f"Calibration fit queries: {len(fit_df)}, eval queries: {len(eval_df)}")

    eng = MultiCandidateEngine()
    cal_path = PROJECT_ROOT / "data" / "model_versions" / "hsn_reranker_v1" / "calibration.json"
    old_bundle = CalibrationBundle.load(cal_path)

    fit_feats, fit_chap_y, fit_hsn_y = _collect_features(eng, fit_df)
    eval_feats, eval_chap_y, eval_hsn_y = _collect_features(eng, eval_df)

    # Evaluate OLD bundle on eval split
    old_hsn_probs = old_bundle.hsn_calibrator.predict_proba(eval_feats)
    old_chap_probs = old_bundle.chapter_calibrator.predict_proba(eval_feats)
    old_hsn_metrics = compute_calibration_metrics(eval_hsn_y, old_hsn_probs)
    old_chap_metrics = compute_calibration_metrics(eval_chap_y, old_chap_probs)

    # Fit NEW calibrators on fit split (keep thresholds tau_abstain=0.40, tau_chapter=0.50, tau_exact_hsn=0.55)
    new_chap_cal = LogisticFeatureCalibrator().fit(fit_feats, fit_chap_y, l2=0.1, lr=0.1, steps=1200)
    new_hsn_cal = LogisticFeatureCalibrator().fit(fit_feats, fit_hsn_y, l2=0.1, lr=0.1, steps=1200)

    new_hsn_probs = new_hsn_cal.predict_proba(eval_feats)
    new_chap_probs = new_chap_cal.predict_proba(eval_feats)
    new_hsn_metrics = compute_calibration_metrics(eval_hsn_y, new_hsn_probs)
    new_chap_metrics = compute_calibration_metrics(eval_chap_y, new_chap_probs)
    new_selective = compute_selective_curve(eval_hsn_y, new_hsn_probs)

    cal_report = {
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
    }

    # Save updated calibration bundle if Brier improves
    if new_hsn_metrics["brier"] <= old_hsn_metrics["brier"]:
        new_bundle = CalibrationBundle(
            relevance_calibrator=old_bundle.relevance_calibrator,
            chapter_calibrator=new_chap_cal,
            hsn_calibrator=new_hsn_cal,
            tau_abstain=old_bundle.tau_abstain,
            tau_chapter=old_bundle.tau_chapter,
            tau_exact_hsn=old_bundle.tau_exact_hsn,
            metadata={
                **old_bundle.metadata,
                "phase10_recalibrated": True,
                "phase10_fit_n": len(fit_feats),
                "phase10_eval_n": len(eval_feats),
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

