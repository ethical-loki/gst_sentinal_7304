"""
HSN Misclassification Scorer Inference Engine: src/ml/misclassification_scorer.py
Automated safety gatekeeper evaluating Day 05 HSN Retrieval predictions.
Computes calibrated empirical error probabilities, safe-to-autofile determinations,
and human-interpretable audit risk factors.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import joblib
import numpy as np
import pandas as pd

from src.ml.misclassification_features import (
    FEATURE_COLUMNS,
    extract_features,
    load_metadata_tables,
)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_ARTIFACTS_DIR = ROOT_DIR / "artifacts"


class HSNMisclassificationScorer:
    """Production Gatekeeper assessing whether a Day 05 HSN prediction is an error or correct."""

    def __init__(
        self,
        artifacts_dir: Optional[Union[str, Path]] = None,
        model_path: Optional[Union[str, Path]] = None,
        calibrator_path: Optional[Union[str, Path]] = None,
        prices_path: Optional[Union[str, Path]] = None,
        priors_path: Optional[Union[str, Path]] = None,
        autofile_threshold: float = 0.15,
        default_prior: float = 0.05,
    ):
        self.artifacts_dir = Path(artifacts_dir or DEFAULT_ARTIFACTS_DIR)
        self.autofile_threshold = float(autofile_threshold)
        self.default_prior = float(default_prior)

        # Paths
        self.model_path = Path(model_path or (self.artifacts_dir / "misclassification_lgbm.joblib"))
        self.calibrator_path = Path(calibrator_path or (self.artifacts_dir / "platt_calibrator.joblib"))
        self.prices_path = Path(prices_path or (self.artifacts_dir / "historical_median_prices.parquet"))
        self.priors_path = Path(priors_path or (self.artifacts_dir / "supplier_priors.parquet"))

        self.model = None
        self.calibrator = None
        self.hsn_medians: Dict[str, float] = {}
        self.chapter_medians: Dict[str, float] = {}
        self.supplier_priors: Dict[str, float] = {}
        self.global_median_price: float = 1000.0

        self._load_artifacts()

    def _load_artifacts(self) -> None:
        """Loads models, calibrator, and statutory metadata tables."""
        # 1. Load calibrator (or base model if calibrator not found)
        if self.calibrator_path.exists():
            self.calibrator = joblib.load(self.calibrator_path)
        elif self.model_path.exists():
            self.model = joblib.load(self.model_path)
        else:
            raise FileNotFoundError(
                f"Missing model artifacts in {self.artifacts_dir}. "
                "Please run src/ml/train_misclassification_scorer.py first."
            )

        if self.model is None and self.model_path.exists():
            try:
                self.model = joblib.load(self.model_path)
            except Exception:
                pass

        # 2. Load historical median prices and supplier priors
        (
            self.hsn_medians,
            self.chapter_medians,
            self.supplier_priors,
            self.global_median_price,
        ) = load_metadata_tables(self.artifacts_dir)

    def extract_line_features(
        self,
        invoice_line: Dict[str, Any],
        day5_retrieval_output: Any,
    ) -> Dict[str, Any]:
        """Extracts the 6 tabular signals for an individual query."""
        return extract_features(
            invoice_line=invoice_line,
            day5_retrieval_output=day5_retrieval_output,
            hsn_medians=self.hsn_medians,
            chapter_medians=self.chapter_medians,
            supplier_priors=self.supplier_priors,
            global_median_price=self.global_median_price,
            default_prior=self.default_prior,
        )

    def predict_risk(
        self,
        invoice_line: Dict[str, Any],
        day5_retrieval_output: Any,
        autofile_threshold: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Assesses empirical misclassification risk on top of Day 05 HSN Retrieval outputs.

        Args:
            invoice_line: Dict containing invoice line item attributes (description, unit_price, supplier_gstin, etc.)
            day5_retrieval_output: Day 05 retrieval result (SearchResultList, list of matches, or dict).
            autofile_threshold: Optional override for the safe autofile cutoff (default 0.15).

        Returns:
            Dict containing:
                - predicted_hsn (str)
                - error_probability (float [0.0, 1.0])
                - is_safe_to_autofile (bool)
                - risk_level ("LOW", "MEDIUM", "HIGH")
                - risk_factors (list[str])
        """
        threshold = self.autofile_threshold if autofile_threshold is None else float(autofile_threshold)

        # 1. Extract 6 tabular signals
        feats_dict = self.extract_line_features(invoice_line, day5_retrieval_output)
        pred_hsn = feats_dict.pop("predicted_hsn")

        # Create input array
        row_values = [feats_dict[c] for c in FEATURE_COLUMNS]
        X = pd.DataFrame([row_values], columns=FEATURE_COLUMNS).astype(np.float32)

        # 2. Probability Inference
        scorer = self.calibrator if self.calibrator is not None else self.model
        prob_arr = scorer.predict_proba(X)
        error_prob = float(prob_arr[0, 1])
        error_prob = max(0.0, min(1.0, error_prob))

        # 3. Decision Gate & Risk Tier
        is_safe = bool(error_prob < threshold)

        if error_prob < 0.15:
            risk_level = "LOW"
        elif error_prob < 0.50:
            risk_level = "MEDIUM"
        else:
            risk_level = "HIGH"

        # 4. Generate Explanatory Audit Factors
        top1_sim = float(feats_dict["top1_similarity_score"])
        margin = float(feats_dict["margin_top1_top2"])
        chap_match = float(feats_dict["chapter_match_flag"])
        entropy = float(feats_dict["token_entropy"])
        price_dev = float(feats_dict["unit_price_deviation"])
        sup_prior = float(feats_dict["supplier_prior_error_freq"])

        audit_factors: List[str] = []
        # Vendor-history check is disabled when no supplier GSTIN was supplied
        vendor_disabled = bool(invoice_line.get("vendor_check_disabled"))

        if is_safe:
            # Positive statutory compliance evidence
            pred_chap = pred_hsn[:2] if len(pred_hsn) >= 2 else "UNKNOWN"
            if chap_match == 1.0:
                audit_factors.append(
                    f"✓ Chapter alignment verified: Declared HSN aligns with vendor's registered Chapter {pred_chap}."
                )
            if price_dev <= 1.5:
                audit_factors.append(
                    f"✓ Economic price verification: Unit price is consistent with statutory benchmark median."
                )
            if top1_sim >= 0.70:
                audit_factors.append(
                    f"✓ Strong statutory correlation: Semantic text matches official tariff master ({top1_sim * 100:.1f}% confidence)."
                )
            if sup_prior <= 0.08 and not vendor_disabled:
                audit_factors.append(
                    f"✓ Vendor compliance history: Supplier exhibits clean historical compliance record ({sup_prior * 100:.1f}% prior error)."
                )
            if not audit_factors:
                audit_factors.append("✓ Item classification complies with statutory benchmarks. Safe to auto-file.")
        else:
            # Risk factors when flagged
            if chap_match == 0.0:
                pred_chap = pred_hsn[:2] if len(pred_hsn) >= 2 else "UNKNOWN"
                audit_factors.append(
                    f"⚠️ Chapter mismatch: Predicted Chapter {pred_chap} diverges from vendor's declared/registered chapter."
                )
            if price_dev > 1.5:
                audit_factors.append(
                    f"⚠️ Economic price deviation: Unit price deviates by {price_dev:.1f}x from statutory median benchmark."
                )
            if top1_sim < 0.65:
                audit_factors.append(
                    f"⚠️ Low retrieval confidence: Semantic similarity score is {top1_sim:.3f} (< 0.650)."
                )
            if sup_prior > 0.10 and not vendor_disabled:
                audit_factors.append(
                    f"⚠️ Vendor historical risk: Supplier has a {sup_prior:.1%} historical misclassification frequency."
                )
            if entropy > 5.5:
                audit_factors.append(
                    f"⚠️ High text entropy ({entropy:.2f} bits): Description contains noisy, unstructured, or random serial text."
                )
            if not audit_factors:
                audit_factors.append(
                    f"⚠️ Statistical gate: Calibrated error probability ({error_prob:.1%}) exceeds safety threshold ({threshold:.1%})."
                )

        return {
            "predicted_hsn": pred_hsn,
            "error_probability": float(round(error_prob, 4)),
            "is_safe_to_autofile": is_safe,
            "risk_level": risk_level,
            "risk_factors": audit_factors,
            "features": feats_dict,
        }
