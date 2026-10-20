"""
Training Pipeline for Day 06 LightGBM Misclassification Scorer & Platt Scaling Calibration
File: src/ml/train_misclassification_scorer.py

1. Ingests train.parquet, val.parquet, test.parquet.
2. Computes historical median prices & supplier priors strictly from train split (Zero Data Leakage).
3. Extracts the 6 tabular signals against Day 05 HSN Retrieval Engine.
4. Trains lightgbm.LGBMClassifier with anti-overfitting constraints.
5. Performs Platt Scaling calibration using held-out val.parquet split.
6. Evaluates and benchmarks against Precision, Recall, ROC-AUC, and Brier Score.
7. Persists production artifacts to artifacts/.
"""

import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    classification_report,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.ml.misclassification_features import (
    FEATURE_COLUMNS,
    PlattCalibrator,
    compute_historical_priors,
    extract_features,
    save_metadata_tables,
)
from src.nlp.hsn_search import HSNSemanticSearchEngine


def extract_split_features(
    df: pd.DataFrame,
    engine: HSNSemanticSearchEngine,
    hsn_medians: Dict[str, float],
    chapter_medians: Dict[str, float],
    supplier_priors: Dict[str, float],
    global_median_price: float,
    query_cache: Dict[str, Any],
    split_name: str = "train",
) -> Tuple[pd.DataFrame, np.ndarray, List[str]]:
    """Extracts 6 tabular features and binary target labels for a dataframe split with caching."""
    cache_path = ROOT_DIR / "artifacts" / f"extracted_day06_{split_name}.parquet"
    if cache_path.exists():
        print(f"[{split_name.upper()}] Loading pre-extracted features from {cache_path.name}...")
        cached_df = pd.read_parquet(cache_path)
        X_df = cached_df[FEATURE_COLUMNS].astype(np.float32)
        y_arr = cached_df["target_y"].to_numpy(dtype=np.int32)
        pred_hsns = cached_df["predicted_hsn"].tolist()
        misclass_rate = float(np.mean(y_arr)) * 100.0
        print(f"  -> {split_name.upper()} loaded {len(X_df):,} samples | Misclassification Rate: {misclass_rate:.2f}%")
        return X_df, y_arr, pred_hsns

    print(f"[{split_name.upper()}] Extracting Day 06 signals for {len(df):,} items...")
    t0 = time.time()

    desc_col = "product_description" if "product_description" in df.columns else "clean_description"
    true_col = "true_hsn" if "true_hsn" in df.columns else "declared_hsn"

    records = df.to_dict(orient="records")
    feature_rows = []
    y_labels = []
    predicted_hsns = []

    for i, row in enumerate(records):
        desc = str(row.get(desc_col, "")).strip()

        # Cached Day 05 Retrieval Search
        if desc not in query_cache:
            res = engine.search(desc, top_k=2)
            query_cache[desc] = res
        else:
            res = query_cache[desc]

        feats = extract_features(
            invoice_line=row,
            day5_retrieval_output=res,
            hsn_medians=hsn_medians,
            chapter_medians=chapter_medians,
            supplier_priors=supplier_priors,
            global_median_price=global_median_price,
        )

        pred_hsn = feats.pop("predicted_hsn")
        predicted_hsns.append(pred_hsn)
        feature_rows.append(feats)

        # Target definition:
        # y = 1 if Predicted Top-1 HSN != Ground Truth HSN else 0
        true_hsn = str(row.get(true_col, "")).strip().replace(".0", "")
        pred_clean = str(pred_hsn).strip().replace(".0", "")
        if not pred_clean or not true_hsn:
            y_val = 1
        elif pred_clean == true_hsn:
            y_val = 0
        else:
            min_l = min(len(pred_clean), len(true_hsn))
            if min_l >= 4 and pred_clean[:4] == true_hsn[:4]:
                y_val = 0
            elif min_l >= 2 and pred_clean[:min_l] == true_hsn[:min_l]:
                y_val = 0
            else:
                y_val = 1
        y_labels.append(y_val)

    X_df = pd.DataFrame(feature_rows)[FEATURE_COLUMNS].astype(np.float32)
    y_arr = np.array(y_labels, dtype=np.int32)

    elapsed = time.time() - t0
    misclass_rate = np.mean(y_arr) * 100.0
    print(
        f"  -> {split_name.upper()} completed in {elapsed:.1f}s | "
        f"Misclassification Rate: {misclass_rate:.2f}% ({np.sum(y_arr)} / {len(y_arr)})"
    )

    try:
        save_df = X_df.copy()
        save_df["target_y"] = y_arr
        save_df["predicted_hsn"] = predicted_hsns
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        save_df.to_parquet(cache_path, index=False)
    except Exception as e:
        print(f"  [WARN] Failed to write cache {cache_path.name}: {e}")

    return X_df, y_arr, predicted_hsns


def train_and_calibrate(
    data_dir: Path = ROOT_DIR / "data",
    artifacts_dir: Path = ROOT_DIR / "artifacts",
) -> Dict[str, Any]:
    """Orchestrates end-to-end training, Platt calibration, and evaluation."""
    print("\n" + "=" * 68)
    print("      DAY 06: LIGHTGBM MISCLASSIFICATION SCORER & PLATT CALIBRATION     ")
    print("=" * 68 + "\n")

    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load Data Splits
    train_path = data_dir / "train.parquet"
    val_path = data_dir / "val.parquet"
    test_path = data_dir / "test.parquet"

    assert train_path.exists(), f"Missing train split: {train_path}"
    assert val_path.exists(), f"Missing val split: {val_path}"
    assert test_path.exists(), f"Missing test split: {test_path}"

    print("[1/5] Loading Parquet Data Splits...")
    df_train = pd.read_parquet(train_path)
    df_val = pd.read_parquet(val_path)
    df_test = pd.read_parquet(test_path)
    print(f"  -> Train samples: {len(df_train):,}")
    print(f"  -> Val samples  : {len(df_val):,}")
    print(f"  -> Test samples : {len(df_test):,}")

    # 2. Compute Historical Priors strictly from Train (Zero Data Leakage)
    print("\n[2/5] Computing Historical Median Prices & Supplier Priors (Zero Leakage)...")
    hsn_meds, chap_meds, sup_priors, global_med = compute_historical_priors(df_train)
    prices_path, priors_path = save_metadata_tables(
        hsn_meds, chap_meds, sup_priors, global_med, output_dir=artifacts_dir
    )
    print(f"  -> Saved median prices ({len(hsn_meds):,} HSNs, {len(chap_meds):,} Chapters) to {prices_path.name}")
    print(f"  -> Saved supplier priors ({len(sup_priors):,} Vendors) to {priors_path.name}")

    # 3. Initialize Day 05 Retrieval Engine & Extract Features
    print("\n[3/5] Initializing Day 05 HSN Retrieval Engine & Query Caching...")
    engine = HSNSemanticSearchEngine()
    query_cache: Dict[str, Any] = {}

    X_train, y_train, _ = extract_split_features(
        df_train, engine, hsn_meds, chap_meds, sup_priors, global_med, query_cache, "train"
    )
    X_val, y_val, _ = extract_split_features(
        df_val, engine, hsn_meds, chap_meds, sup_priors, global_med, query_cache, "val"
    )
    X_test, y_test, _ = extract_split_features(
        df_test, engine, hsn_meds, chap_meds, sup_priors, global_med, query_cache, "test"
    )

    # 4. Train LightGBM Classifier
    print("\n[4/5] Training LightGBM Misclassification Scorer...")
    # Parameters adhering to architectural specifications
    base_lgbm = lgb.LGBMClassifier(
        objective="binary",
        boosting_type="gbdt",
        max_depth=5,
        num_leaves=31,
        learning_rate=0.04,
        n_estimators=150,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        importance_type="gain",
        verbose=-1,
    )
    base_lgbm.fit(X_train, y_train)

    # Platt Scaling Probability Calibration using held-out Val Split
    print("  -> Fitting Platt Scaling (Sigmoidal Logistic Calibrator) on Validation Split...")
    calibrated_model = PlattCalibrator(base_estimator=base_lgbm)
    calibrated_model.fit(X_val, y_val)

    # Save models
    model_file = artifacts_dir / "misclassification_lgbm.joblib"
    calibrator_file = artifacts_dir / "platt_calibrator.joblib"
    joblib.dump(base_lgbm, model_file)
    joblib.dump(calibrated_model, calibrator_file)
    print(f"  -> Saved Base LightGBM model to {model_file.name}")
    print(f"  -> Saved Calibrated Classifier to {calibrator_file.name}")

    # 5. Evaluate on Test Split
    print("\n[5/5] Evaluating Calibrated Model on Held-Out Test Split...")
    raw_probs = base_lgbm.predict_proba(X_test)[:, 1]
    cal_probs = calibrated_model.predict_proba(X_test)[:, 1]
    preds = (cal_probs >= 0.5).astype(int)

    test_acc = accuracy_score(y_test, preds)
    test_prec = precision_score(y_test, preds, zero_division=0)
    test_rec = recall_score(y_test, preds, zero_division=0)
    test_f1 = f1_score(y_test, preds, zero_division=0)
    test_auc = roc_auc_score(y_test, cal_probs)

    brier_uncal = brier_score_loss(y_test, raw_probs)
    brier_cal = brier_score_loss(y_test, cal_probs)

    print("\n" + "-" * 50)
    print(f"  Accuracy           : {test_acc:.4f}")
    print(f"  Precision (Error)  : {test_prec:.4f}")
    print(f"  Recall (Error)     : {test_rec:.4f}")
    print(f"  F1-Score           : {test_f1:.4f}")
    print(f"  ROC-AUC            : {test_auc:.4f}")
    print(f"  Brier Score (Raw)  : {brier_uncal:.4f}")
    print(f"  Brier Score (Cal)  : {brier_cal:.4f} (Target: < 0.15)")
    print("-" * 50)

    # Feature Importances
    importances = base_lgbm.feature_importances_
    sorted_idx = np.argsort(importances)[::-1]
    print("\nFeature Importances (Gain):")
    for idx in sorted_idx:
        print(f"  - {FEATURE_COLUMNS[idx]:<28}: {importances[idx]:.2f}")

    print("\n" + "=" * 68)
    print("  SUCCESS: DAY 06 MISCLASSIFICATION SCORER TRAINED & CALIBRATED!")
    print("=" * 68 + "\n")

    return {
        "accuracy": test_acc,
        "precision": test_prec,
        "recall": test_rec,
        "f1": test_f1,
        "roc_auc": test_auc,
        "brier_score_calibrated": brier_cal,
        "brier_score_uncalibrated": brier_uncal,
        "model_file": str(model_file),
        "calibrator_file": str(calibrator_file),
        "prices_file": str(prices_path),
        "priors_file": str(priors_path),
    }


if __name__ == "__main__":
    train_and_calibrate()
