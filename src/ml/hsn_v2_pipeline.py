"""
src/ml/hsn_v2_pipeline.py
=========================
Unified HSN Intelligence V2 Pipeline (Phases 1–7)

Integrates:
  1. Complete 98-Chapter Statutory Out-of-Schedule Gate (`StatutoryMasterIndex`)
  2. Layer 2 Hybrid Retrieval (`HybridHSNEngine` BM25 + MiniLM Dense + RRF)
  3. Layer 3 Fine-Tuned Product-to-Tariff Reranker (`ProductTariffReranker` via `ModelRegistry`)
  4. Layer 4 Model-Driven Relevance & Ambiguity Resolution (`RelevanceClassifier` + `ModelDrivenAmbiguityResolver`)
  5. Continuous Feedback Loop (`FeedbackCollector`)
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.ml.ambiguity_resolver import AmbiguityResolutionResult, ModelDrivenAmbiguityResolver
from src.ml.relevance_classifier import RelevanceClassifier
from src.search.hybrid_retrieval import HybridHSNEngine
from src.search.statutory_master_index import StatutoryCoverageResult, StatutoryMasterIndex
from src.training.feedback_collector import FeedbackCollector

logger = logging.getLogger(__name__)


@dataclass
class HSNV2ClassificationResult:
    query: str
    status: str  # "CLEAR" | "AMBIGUOUS_MATERIAL" | "INSUFFICIENT_INFORMATION" | "OUT_OF_SCHEDULE"
    selected_hsn: Optional[str] = None
    selected_chapter: Optional[str] = None
    selected_description: Optional[str] = None
    confidence: float = 0.0
    clarification_question: Optional[str] = None
    clarification_options: List[str] = field(default_factory=list)
    statutory_matches: List[Dict[str, Any]] = field(default_factory=list)
    rationale: str = ""


class HSNIntelligenceV2:
    """End-to-end orchestrator for HSN Intelligence V2."""

    def __init__(
        self,
        statutory_index: Optional[StatutoryMasterIndex] = None,
        hybrid_engine: Optional[HybridHSNEngine] = None,
        relevance_classifier: Optional[RelevanceClassifier] = None,
        feedback_collector: Optional[FeedbackCollector] = None,
    ):
        self.statutory_index = statutory_index or StatutoryMasterIndex()
        self.hybrid_engine = hybrid_engine or HybridHSNEngine.get_instance()
        self.classifier = relevance_classifier or RelevanceClassifier()
        self.resolver = ModelDrivenAmbiguityResolver(classifier=self.classifier)
        self.feedback = feedback_collector or FeedbackCollector()

    def classify(self, query: str, pool_size: int = 15) -> HSNV2ClassificationResult:
        q = (query or "").strip()
        if not q:
            return HSNV2ClassificationResult(
                query="",
                status="INSUFFICIENT_INFORMATION",
                clarification_question="Please provide a product description.",
            )

        # 1. Layer 2 Active Schedule Retrieval
        candidates = self.hybrid_engine.search(q, top_k=pool_size)

        # 2 & 3. Layer 3 Reranking + Layer 4 Model-Driven Ambiguity Resolution
        if candidates:
            res: AmbiguityResolutionResult = self.resolver.resolve(q, candidates)
            if res.status in ("CLEAR", "AMBIGUOUS_MATERIAL"):
                coverage = self.statutory_index.check_schedule_coverage(q)
                return HSNV2ClassificationResult(
                    query=q,
                    status=res.status,
                    selected_hsn=res.selected_hsn,
                    selected_chapter=res.selected_chapter,
                    selected_description=res.selected_description,
                    confidence=res.confidence,
                    clarification_question=res.clarification_question,
                    clarification_options=res.clarification_options,
                    statutory_matches=coverage.top_statutory_matches[:3],
                    rationale=res.rationale,
                )
        else:
            res = AmbiguityResolutionResult(
                status="NO_RELEVANT_MATCH",
                rationale="No matching candidates found in active schedule.",
            )

        # 4. No SAME_PRODUCT in active chapters -> Full 98-Chapter Statutory Out-of-Schedule Check
        coverage: StatutoryCoverageResult = self.statutory_index.check_schedule_coverage(q)
        if coverage.is_out_of_schedule:
            top_stat = coverage.top_statutory_matches[0] if coverage.top_statutory_matches else {}
            return HSNV2ClassificationResult(
                query=q,
                status="OUT_OF_SCHEDULE",
                selected_hsn=top_stat.get("hsn_code"),
                selected_chapter=coverage.predicted_chapter,
                selected_description=top_stat.get("description"),
                confidence=0.0,
                statutory_matches=coverage.top_statutory_matches,
                rationale=coverage.reason,
            )

        return HSNV2ClassificationResult(
            query=q,
            status="INSUFFICIENT_INFORMATION",
            selected_hsn=res.selected_hsn,
            selected_chapter=res.selected_chapter or coverage.predicted_chapter,
            selected_description=res.selected_description,
            confidence=res.confidence,
            clarification_question=res.clarification_question,
            clarification_options=res.clarification_options,
            statutory_matches=coverage.top_statutory_matches[:3],
            rationale=res.rationale,
        )
