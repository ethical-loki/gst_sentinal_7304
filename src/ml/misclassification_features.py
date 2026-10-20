"""
Feature Extraction Pipeline for Day 06 HSN Misclassification Scorer: src/ml/misclassification_features.py
Extracts the 6 required tabular signals from invoice data and Day 05 HSN Retrieval outputs:
1. top1_similarity_score (Float32)
2. margin_top1_top2 (Float32)
3. chapter_match_flag (Int32 / Float32: 0 or 1)
4. token_entropy (Float32)
5. unit_price_deviation (Float32)
6. supplier_prior_error_freq (Float32)
"""

import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd

from sklearn.linear_model import LogisticRegression

FEATURE_COLUMNS = [
    "top1_similarity_score",
    "margin_top1_top2",
    "chapter_match_flag",
    "token_entropy",
    "unit_price_deviation",
    "supplier_prior_error_freq",
]


class PlattCalibrator:
    """Platt Scaling probability calibrator using univariate logistic regression

    fitted on base model's raw margins/logits.
    """

    def __init__(self, base_estimator=None):
        self.base_estimator = base_estimator
        self.lr = LogisticRegression(solver="lbfgs", C=1.0)
        self.is_fitted = False

    def fit(self, X_val, y_val):
        """Fits Platt scaling on validation logits."""
        if hasattr(self.base_estimator, "predict"):
            raw_scores = self.base_estimator.predict(X_val, raw_score=True)
        else:
            raw_scores = np.asarray(X_val)

        raw_scores = np.asarray(raw_scores).reshape(-1, 1)
        self.lr.fit(raw_scores, y_val)
        self.is_fitted = True
        return self

    def predict_proba(self, X):
        """Returns calibrated probabilities [P(y=0), P(y=1)]."""
        if hasattr(self.base_estimator, "predict"):
            raw_scores = self.base_estimator.predict(X, raw_score=True)
        else:
            raw_scores = np.asarray(X)

        raw_scores = np.asarray(raw_scores).reshape(-1, 1)
        return self.lr.predict_proba(raw_scores)

    def predict(self, X):
        probs = self.predict_proba(X)[:, 1]
        return (probs >= 0.5).astype(int)


def compute_token_entropy(text: object) -> float:
    """Computes Shannon entropy over tokenized words of the raw invoice description.

    Formula: H = -sum(p_i * log2(p_i))
    """
    if text is None or (isinstance(text, float) and math.isnan(text)):
        return 0.0
    text_str = str(text).strip()
    if not text_str:
        return 0.0

    tokens = re.findall(r"\b[a-zA-Z0-9]+\b", text_str.lower())
    if not tokens:
        return 0.0

    total_tokens = len(tokens)
    counts = Counter(tokens)
    entropy = -sum(
        (cnt / total_tokens) * math.log2(cnt / total_tokens)
        for cnt in counts.values()
    )
    return float(round(entropy, 4))


def extract_retrieval_signals(day5_retrieval_output: Any) -> Tuple[str, float, float]:
    """Extracts predicted HSN, top1 similarity score, and top1-top2 margin from Day 05 retrieval output.

    Returns:
        (predicted_hsn, top1_score, margin_top1_top2)
    """
    candidates: List[Dict[str, Any]] = []

    if isinstance(day5_retrieval_output, list):
        candidates = day5_retrieval_output
    elif isinstance(day5_retrieval_output, dict):
        if "matches" in day5_retrieval_output and isinstance(day5_retrieval_output["matches"], list):
            candidates = day5_retrieval_output["matches"]
        elif "candidates" in day5_retrieval_output and isinstance(day5_retrieval_output["candidates"], list):
            candidates = day5_retrieval_output["candidates"]
        elif "predicted_hsn" in day5_retrieval_output:
            score = float(day5_retrieval_output.get("score", day5_retrieval_output.get("similarity_score", 1.0)))
            pred_hsn = str(day5_retrieval_output["predicted_hsn"]).strip()
            return pred_hsn, min(1.0, max(0.0, score)), min(1.0, max(0.0, score))
        else:
            candidates = [day5_retrieval_output]
    elif hasattr(day5_retrieval_output, "matches"):
        candidates = getattr(day5_retrieval_output, "matches")

    if not candidates:
        return "", 0.0, 0.0

    top1 = candidates[0]
    pred_hsn = str(top1.get("hsn_code", top1.get("hsn", top1.get("predicted_hsn", "")))).strip()
    raw_s1 = top1.get("score", top1.get("similarity_score", None))
    if raw_s1 is None and "confidence_pct" in top1:
        s1 = float(top1["confidence_pct"]) / 100.0
    elif raw_s1 is not None:
        s1 = float(raw_s1)
    else:
        s1 = 0.5
    s1 = min(1.0, max(0.0, s1))

    if len(candidates) >= 2:
        top2 = candidates[1]
        raw_s2 = top2.get("score", top2.get("similarity_score", None))
        if raw_s2 is None and "confidence_pct" in top2:
            s2 = float(top2["confidence_pct"]) / 100.0
        elif raw_s2 is not None:
            s2 = float(raw_s2)
        else:
            s2 = 0.0
        s2 = min(1.0, max(0.0, s2))
        margin = max(0.0, s1 - s2)
    else:
        margin = s1

    return pred_hsn, float(round(s1, 4)), float(round(margin, 4))


def compute_historical_priors(
    train_df: pd.DataFrame,
    default_prior: float = 0.05
) -> Tuple[Dict[str, float], Dict[str, float], Dict[str, float], float]:
    """Computes zero-leakage statutory historical median prices and supplier prior error frequencies

    strictly from train split data.

    Returns:
        (hsn_medians, chapter_medians, supplier_priors, global_median_price)
    """
    df = train_df.copy()

    # Determine ground truth HSN and error indicator
    hsn_col = "true_hsn" if "true_hsn" in df.columns else "declared_hsn"
    price_col = "unit_price" if "unit_price" in df.columns else "price"

    prices = pd.to_numeric(df[price_col], errors="coerce").fillna(0.0)
    df["_unit_price"] = prices
    df["_hsn"] = df[hsn_col].astype(str).str.strip()
    df["_chapter"] = df["_hsn"].str[:2].str.zfill(2)

    # 1. HSN Medians
    hsn_medians = df.groupby("_hsn")["_unit_price"].median().to_dict()

    # 2. Chapter Medians
    chapter_medians = df.groupby("_chapter")["_unit_price"].median().to_dict()

    # 3. Global Price Median
    valid_prices = prices[prices > 0]
    global_median_price = float(valid_prices.median()) if not valid_prices.empty else 1000.0

    # 4. Supplier Priors
    # If error column exists, compute supplier error frequency: errors / total_invoices_seen
    supplier_priors: Dict[str, float] = {}
    supplier_col = "supplier_gstin" if "supplier_gstin" in df.columns else "vendor_id"

    if supplier_col in df.columns:
        if "is_hsn_misclass" in df.columns:
            df["_is_err"] = df["is_hsn_misclass"].astype(int)
        elif "has_error" in df.columns and "declared_hsn" in df.columns and "true_hsn" in df.columns:
            df["_is_err"] = (df["declared_hsn"].astype(str) != df["true_hsn"].astype(str)).astype(int)
        else:
            df["_is_err"] = 0

        grouped = df.groupby(supplier_col)["_is_err"].agg(["sum", "count"])
        for supplier, row in grouped.iterrows():
            total = int(row["count"])
            errs = int(row["sum"])
            freq = errs / total if total > 0 else default_prior
            supplier_priors[str(supplier).strip()] = float(round(freq, 4))

    return hsn_medians, chapter_medians, supplier_priors, global_median_price


def extract_features(
    invoice_line: Dict[str, Any],
    day5_retrieval_output: Any,
    hsn_medians: Optional[Dict[str, float]] = None,
    chapter_medians: Optional[Dict[str, float]] = None,
    supplier_priors: Optional[Dict[str, float]] = None,
    global_median_price: float = 1000.0,
    default_prior: float = 0.05,
) -> Dict[str, Any]:
    """Extracts the 6 tabular signals for an individual invoice line item and Day 05 retrieval output.

    Returns:
        Dict with keys:
            - top1_similarity_score: np.float32
            - margin_top1_top2: np.float32
            - chapter_match_flag: np.float32 (0.0 or 1.0)
            - token_entropy: np.float32
            - unit_price_deviation: np.float32
            - supplier_prior_error_freq: np.float32
            - predicted_hsn: str
    """
    hsn_medians = hsn_medians or {}
    chapter_medians = chapter_medians or {}
    supplier_priors = supplier_priors or {}

    # Signal 1 & 2: Top-1 Score & Margin Top-1 - Top-2
    pred_hsn, top1_score, margin_top1_top2 = extract_retrieval_signals(day5_retrieval_output)

    # Signal 3: Chapter Match Flag
    pred_chapter = pred_hsn[:2].zfill(2) if len(pred_hsn) >= 2 else ""
    vendor_exp_chapter = (
        invoice_line.get("declared_hsn_chapter")
        or invoice_line.get("vendor_chapter")
        or invoice_line.get("expected_chapter")
        or invoice_line.get("supplier_chapter")
    )
    if not vendor_exp_chapter and "declared_hsn" in invoice_line:
        vendor_exp_chapter = str(invoice_line["declared_hsn"]).strip()[:2]

    if vendor_exp_chapter:
        exp_chap_clean = str(vendor_exp_chapter).strip().replace(".0", "").zfill(2)
        chapter_match_flag = 1.0 if (pred_chapter and pred_chapter == exp_chap_clean) else 0.0
    else:
        chapter_match_flag = 0.0

    # Signal 4: Token Entropy
    if "token_entropy" in invoice_line and invoice_line["token_entropy"] is not None:
        token_entropy = float(invoice_line["token_entropy"])
    else:
        desc_text = (
            invoice_line.get("product_description")
            or invoice_line.get("clean_description")
            or invoice_line.get("description")
            or invoice_line.get("product_name")
            or ""
        )
        token_entropy = compute_token_entropy(desc_text)

    # Signal 5: Unit Price Deviation
    # deviation = |unit_price - median_price| / (median_price + 1e-5)
    unit_price = float(
        invoice_line.get("unit_price", invoice_line.get("price", invoice_line.get("rate", 0.0))) or 0.0
    )

    median_price = None
    if pred_hsn in hsn_medians:
        median_price = hsn_medians[pred_hsn]
    elif len(pred_hsn) >= 4 and pred_hsn[:4] in hsn_medians:
        median_price = hsn_medians[pred_hsn[:4]]
    elif pred_chapter in chapter_medians:
        median_price = chapter_medians[pred_chapter]

    if median_price is None or median_price <= 0:
        median_price = global_median_price

    unit_price_deviation = abs(unit_price - median_price) / (median_price + 1e-5)

    # Signal 6: Supplier Prior Error Frequency
    supplier_key = (
        invoice_line.get("supplier_gstin")
        or invoice_line.get("vendor_id")
        or invoice_line.get("supplier_id")
        or invoice_line.get("supplier_lglnm")
    )
    supplier_prior = default_prior
    if supplier_key:
        s_clean = str(supplier_key).strip()
        if s_clean in supplier_priors:
            supplier_prior = supplier_priors[s_clean]

    return {
        "top1_similarity_score": np.float32(top1_score),
        "margin_top1_top2": np.float32(margin_top1_top2),
        "chapter_match_flag": np.float32(chapter_match_flag),
        "token_entropy": np.float32(token_entropy),
        "unit_price_deviation": np.float32(unit_price_deviation),
        "supplier_prior_error_freq": np.float32(supplier_prior),
        "predicted_hsn": pred_hsn,
    }


def save_metadata_tables(
    hsn_medians: Dict[str, float],
    chapter_medians: Dict[str, float],
    supplier_priors: Dict[str, float],
    global_median_price: float,
    output_dir: Union[str, Path] = "artifacts"
) -> Tuple[Path, Path]:
    """Saves historical median prices and supplier priors to Parquet format in output_dir."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # Historical Median Prices DataFrame
    records = []
    for hsn, med in hsn_medians.items():
        records.append({
            "code_type": "hsn",
            "code": str(hsn),
            "median_price": float(med),
            "chapter": str(hsn)[:2].zfill(2)
        })
    for chap, med in chapter_medians.items():
        records.append({
            "code_type": "chapter",
            "code": str(chap).zfill(2),
            "median_price": float(med),
            "chapter": str(chap).zfill(2)
        })
    records.append({
        "code_type": "global",
        "code": "GLOBAL",
        "median_price": float(global_median_price),
        "chapter": "ALL"
    })
    df_prices = pd.DataFrame(records)
    prices_file = out_path / "historical_median_prices.parquet"
    df_prices.to_parquet(prices_file, index=False)

    # Supplier Priors DataFrame
    sup_records = [
        {"supplier_gstin": str(k), "prior_error_freq": float(v)}
        for k, v in supplier_priors.items()
    ]
    df_priors = pd.DataFrame(sup_records)
    priors_file = out_path / "supplier_priors.parquet"
    df_priors.to_parquet(priors_file, index=False)

    return prices_file, priors_file


def load_metadata_tables(
    artifacts_dir: Union[str, Path] = "artifacts"
) -> Tuple[Dict[str, float], Dict[str, float], Dict[str, float], float]:
    """Loads historical median prices and supplier priors from Parquet artifacts."""
    art_path = Path(artifacts_dir)
    prices_file = art_path / "historical_median_prices.parquet"
    priors_file = art_path / "supplier_priors.parquet"

    hsn_medians: Dict[str, float] = {}
    chapter_medians: Dict[str, float] = {}
    global_median: float = 1000.0
    supplier_priors: Dict[str, float] = {}

    if prices_file.exists():
        df_p = pd.read_parquet(prices_file)
        for _, r in df_p.iterrows():
            ctype = r["code_type"]
            c = str(r["code"])
            m = float(r["median_price"])
            if ctype == "hsn":
                hsn_medians[c] = m
            elif ctype == "chapter":
                chapter_medians[c] = m
            elif ctype == "global":
                global_median = m

    if priors_file.exists():
        df_s = pd.read_parquet(priors_file)
        for _, r in df_s.iterrows():
            supplier_priors[str(r["supplier_gstin"])] = float(r["prior_error_freq"])

    return hsn_medians, chapter_medians, supplier_priors, global_median
