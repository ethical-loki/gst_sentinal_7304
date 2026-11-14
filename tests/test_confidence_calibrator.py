"""
Unit tests for Phase 6 Confidence Calibration (`src/ml/confidence_calibrator.py`).
"""

import numpy as np

from src.ml.confidence_calibrator import (
    CalibrationBundle,
    LogisticFeatureCalibrator,
    ScalarLogitCalibrator,
    compute_calibration_metrics,
    compute_selective_curve,
    extract_query_confidence_features,
)


def test_temperature_and_platt_preserve_ranking_and_improve_ece():
    # Overconfident logits (e.g. z=4.0 -> sigmoid=0.982, yet empirical accuracy ~0.75)
    rng = np.random.default_rng(42)
    z_fit = np.linspace(-3.0, 5.0, 200)
    true_p = 1.0 / (1.0 + np.exp(-0.5 * z_fit))
    y_fit = (rng.random(200) < true_p).astype(int)

    z_eval = np.linspace(-3.0, 5.0, 200)
    true_p_eval = 1.0 / (1.0 + np.exp(-0.5 * z_eval))
    y_eval = (rng.random(200) < true_p_eval).astype(int)

    uncal_probs = 1.0 / (1.0 + np.exp(-z_eval))
    uncal_m = compute_calibration_metrics(y_eval, uncal_probs)

    temp = ScalarLogitCalibrator().fit(z_fit, y_fit, method="temperature")
    assert temp.scale > 0  # strictly preserves ranking
    temp_probs = temp.predict_proba(z_eval)
    assert np.all(np.diff(temp_probs) >= 0)  # monotonic
    temp_m = compute_calibration_metrics(y_eval, temp_probs)
    assert temp_m["nll"] < uncal_m["nll"]
    assert temp_m["ece"] < uncal_m["ece"]

    platt = ScalarLogitCalibrator().fit(z_fit, y_fit, method="platt")
    assert platt.scale > 0
    platt_probs = platt.predict_proba(z_eval)
    assert np.all(np.diff(platt_probs) >= 0)


def test_chapter_vs_hsn_confidence_separation_on_sibling_ties():
    # Synthetic query-level calibration data:
    # - Chapter is correct whenever top1_logit is high (>= 2.0) even with siblings
    # - Exact HSN is only reliable when margin is high and n_siblings is small
    fit_feats = []
    y_chap = []
    y_hsn = []
    for i in range(60):
        clear_margin = i % 2 == 0
        f = {
            "top1_logit": 3.5,
            "top1_top2_margin": 2.2 if clear_margin else 0.05,
            "n_siblings_same_heading": 1.0 if clear_margin else 5.0,
            "n_distinct_headings_above": 1.0,
            "n_distinct_chapters_above": 1.0,
            "is_ambiguous": 0.0,
            "query_token_count": 4.0,
        }
        fit_feats.append(f)
        y_chap.append(1)
        y_hsn.append(1 if clear_margin else 0)

    # Add a few low-logit negatives so both classes exist in y_chap
    for _ in range(10):
        fit_feats.append({
            "top1_logit": -1.5,
            "top1_top2_margin": 0.1,
            "n_siblings_same_heading": 1.0,
            "n_distinct_headings_above": 1.0,
            "n_distinct_chapters_above": 1.0,
            "is_ambiguous": 0.0,
            "query_token_count": 2.0,
        })
        y_chap.append(0)
        y_hsn.append(0)

    chap_cal = LogisticFeatureCalibrator().fit(fit_feats, y_chap)
    hsn_cal = LogisticFeatureCalibrator().fit(fit_feats, y_hsn)

    # Tied siblings case: high logit, tiny margin, 5 siblings
    tied_feat = extract_query_confidence_features(
        raw_logits=[3.5, 3.45, 3.40, 3.35, 3.30],
        hsn_codes=["39264031", "39264039", "39264041", "39264049", "39264051"],
        chapter_codes=["39", "39", "39", "39", "39"],
        query="plastic statuettes",
    )
    p_chap = chap_cal.predict_proba_one(tied_feat)
    p_hsn = hsn_cal.predict_proba_one(tied_feat)
    assert p_chap > 0.75
    assert p_hsn < 0.35
    assert p_chap > p_hsn


def test_calibration_bundle_roundtrip_and_selective_curve(tmp_path):
    bundle = CalibrationBundle(
        relevance_calibrator=ScalarLogitCalibrator(method="temperature", scale=0.65, bias=0.0),
        tau_abstain=0.40,
        tau_chapter=0.72,
        tau_exact_hsn=0.60,
    )
    out = bundle.save(tmp_path / "calibration.json")
    loaded = CalibrationBundle.load(out)
    assert loaded.relevance_calibrator.scale == 0.65
    assert loaded.tau_chapter == 0.72
    assert loaded.tau_exact_hsn == 0.60

    curve = compute_selective_curve([1, 1, 0, 0], [0.9, 0.8, 0.4, 0.2], thresholds=(0.5, 0.85))
    assert curve[0]["coverage"] == 0.5
    assert curve[0]["accuracy"] == 1.0
    assert curve[1]["coverage"] == 0.25

