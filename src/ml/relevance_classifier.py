"""
src/ml/relevance_classifier.py
==============================
Step 2: Model-Driven 4-Class Product-to-Tariff Relevance Classifier

Classifies each retrieved tariff candidate into one of four semantic
relationships with respect to the queried product:
  - SAME_PRODUCT: Candidate describes the actual product.
  - RELATED_PRODUCT: Candidate describes a related product, process, or component
    (must NOT trigger material ambiguity).
  - INSUFFICIENT_INFORMATION: Available evidence is insufficient to confirm or reject.
  - UNRELATED: Candidate is semantically irrelevant.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from src.ml.confidence_calibrator import CalibrationBundle
from src.ml.model_registry import ModelRegistry
from src.ml.product_tariff_reranker import (
    BASELINE_RERANKER_MODEL,
    ProductTariffReranker,
    RerankedTariffCandidate,
)

logger = logging.getLogger(__name__)


class RelationLabel(str, Enum):
    SAME_PRODUCT = "SAME_PRODUCT"
    RELATED_PRODUCT = "RELATED_PRODUCT"
    UNRELATED = "UNRELATED"
    INSUFFICIENT_INFORMATION = "INSUFFICIENT_INFORMATION"


@dataclass
class ClassifiedTariffCandidate:
    candidate: RerankedTariffCandidate
    relation: RelationLabel
    confidence: float
    relevance_confidence: float = 0.0


class RelevanceClassifier:
    """
    Wraps a calibrated ProductTariffReranker to assign SAME_PRODUCT,
    RELATED_PRODUCT, INSUFFICIENT_INFORMATION, or UNRELATED to candidate rows.

    Note: The default `same_product_threshold` (loaded from ModelRegistry, e.g. 0.725)
    is an initial configuration that should be validated and recalibrated against
    unseen examples via `calibrate_from_examples(...)`.
    """

    def __init__(
        self,
        reranker: Optional[ProductTariffReranker] = None,
        same_product_threshold: Optional[float] = None,
        related_threshold: float = 0.40,
        unrelated_threshold: float = 0.20,
        dominant_margin: float = 0.25,
    ):
        registry = ModelRegistry()
        active_entry = registry.get_active_entry()

        if reranker is None:
            model_path = active_entry["model_path"] if active_entry else BASELINE_RERANKER_MODEL
            self.reranker = ProductTariffReranker(
                model_name_or_path=model_path,
                max_length=144,
                local_files_only=True,
            )
        else:
            self.reranker = reranker

        if same_product_threshold is not None:
            self.same_product_threshold = float(same_product_threshold)
        elif active_entry is not None:
            self.same_product_threshold = float(active_entry.get("calibrated_threshold", 0.725))
        else:
            self.same_product_threshold = 0.725

        self.related_threshold = float(related_threshold)
        self.unrelated_threshold = float(unrelated_threshold)
        self.dominant_margin = float(dominant_margin)

        self.calibration_bundle: Optional[CalibrationBundle] = None
        if active_entry and active_entry.get("model_path"):
            cal_path = Path(active_entry["model_path"]) / "calibration.json"
            if cal_path.exists():
                try:
                    self.calibration_bundle = CalibrationBundle.load(cal_path)
                    logger.info(f"Loaded Phase 6 CalibrationBundle from {cal_path}")
                except Exception as e:
                    logger.warning(f"Failed to load CalibrationBundle from {cal_path}: {e}")

    def calibrate_from_examples(
        self,
        queries: Sequence[str],
        tariff_rows: Sequence[Any],
        labels: Sequence[int],
    ) -> Tuple[float, Dict[str, float]]:
        """
        Recalibrates `same_product_threshold` using actual classification performance
        (maximizing F1) on a validation set of unseen examples.
        """
        from src.training.evaluation_pipeline import calibrate_threshold

        pairs = list(zip(queries, [str(r) for r in tariff_rows]))
        raw_logits = np.array(self.reranker.score_pairs(pairs), dtype=np.float64)
        probs = 1.0 / (1.0 + np.exp(-np.clip(raw_logits, -30.0, 30.0)))
        best_thresh, stats = calibrate_threshold(np.array(labels, dtype=int), probs)
        self.same_product_threshold = best_thresh
        logger.info(f"Recalibrated same_product_threshold={best_thresh} (F1={stats.get('f1')})")
        return best_thresh, stats

    def classify(
        self,
        product_intent: str,
        tariff_rows: Sequence[Any],
    ) -> List[ClassifiedTariffCandidate]:
        """
        Scores and classifies all candidate tariff rows into the 4 semantic relationship labels.
        """
        ranked = self.reranker.rerank(product_intent, tariff_rows, normalize_sigmoid=True)
        if not ranked:
            return []

        top_score = ranked[0].relevance_score
        classified: List[ClassifiedTariffCandidate] = []

        for idx, cand in enumerate(ranked):
            score = cand.relevance_score
            if score >= self.same_product_threshold:
                # If a different-chapter candidate is far below a dominant top match,
                # classify as RELATED_PRODUCT rather than competing SAME_PRODUCT.
                if (
                    idx > 0
                    and (top_score - score) >= self.dominant_margin
                    and cand.chapter_code != ranked[0].chapter_code
                ):
                    rel = RelationLabel.RELATED_PRODUCT
                else:
                    rel = RelationLabel.SAME_PRODUCT
            elif score >= self.related_threshold:
                rel = RelationLabel.INSUFFICIENT_INFORMATION
            elif score >= self.unrelated_threshold:
                rel = RelationLabel.RELATED_PRODUCT
            else:
                rel = RelationLabel.UNRELATED

            rel_conf = (
                float(self.calibration_bundle.relevance_calibrator.predict_proba(cand.raw_logit))
                if self.calibration_bundle is not None
                else round(score, 4)
            )
            classified.append(
                ClassifiedTariffCandidate(
                    candidate=cand,
                    relation=rel,
                    confidence=round(score, 4),
                    relevance_confidence=round(rel_conf, 4),
                )
            )

        return classified
