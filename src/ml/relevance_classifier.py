"""
src/ml/relevance_classifier.py
==============================
Phase 5: Model-Driven Product-to-Tariff Relevance Classifier

Classifies each retrieved tariff candidate into one of three semantic
relationships with respect to the queried product:
  - SAME_PRODUCT: Description actually classifies the queried product.
  - RELATED_PRODUCT: Description mentions a related product, process, or component
    (e.g. machinery processing that product) and must NOT trigger material ambiguity.
  - INSUFFICIENT_INFORMATION: Uncertain band — not enough evidence to confirm or reject.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, List, Optional, Sequence

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
    INSUFFICIENT_INFORMATION = "INSUFFICIENT_INFORMATION"


@dataclass
class ClassifiedTariffCandidate:
    candidate: RerankedTariffCandidate
    relation: RelationLabel
    confidence: float


class RelevanceClassifier:
    """
    Wraps a calibrated ProductTariffReranker to assign SAME_PRODUCT,
    RELATED_PRODUCT, or INSUFFICIENT_INFORMATION to candidate tariff rows.
    """

    def __init__(
        self,
        reranker: Optional[ProductTariffReranker] = None,
        same_product_threshold: Optional[float] = None,
        related_threshold: float = 0.35,
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
        self.dominant_margin = float(dominant_margin)

    def classify(
        self,
        product_intent: str,
        tariff_rows: Sequence[Any],
    ) -> List[ClassifiedTariffCandidate]:
        """
        Scores and classifies all candidate tariff rows into semantic relationship labels.
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
                # treat it as RELATED_PRODUCT rather than competing SAME_PRODUCT.
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
            else:
                rel = RelationLabel.RELATED_PRODUCT

            classified.append(
                ClassifiedTariffCandidate(
                    candidate=cand,
                    relation=rel,
                    confidence=round(score, 4),
                )
            )

        return classified

