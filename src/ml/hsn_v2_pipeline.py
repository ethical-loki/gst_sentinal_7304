"""
src/ml/hsn_v2_pipeline.py
=========================
Unified HSN Intelligence V2 Pipeline

Integrates:
  1. Layer 2 Active Schedule Retrieval (`HybridHSNEngine` BM25 + MiniLM Dense + RRF)
  2. Layer 3 Fine-Tuned Cross-Encoder Verification (`ProductTariffReranker`)
  3. Layer 4 4-Class Relevance & Attribute-Driven Ambiguity Resolution
  4. Independent Complete 98-Chapter Statutory Master Comparison (`StatutoryMasterIndex`)
     so an active-chapter result is never accepted if an inactive chapter has
     stronger statutory relevance.
  5. Continuous Feedback Loop (`FeedbackCollector`)
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.ml.ambiguity_resolver import AmbiguityResolutionResult, ModelDrivenAmbiguityResolver
from src.ml.confidence_calibrator import extract_query_confidence_features
from src.ml.relevance_classifier import RelevanceClassifier
from src.search.hybrid_retrieval import HybridHSNEngine
from src.search.statutory_master_index import StatutoryComparisonResult, StatutoryMasterIndex
from src.training.feedback_collector import FeedbackCollector

logger = logging.getLogger(__name__)


@dataclass
class HSNV2ClassificationResult:
    query: str
    status: str  # "CLEAR" | "AMBIGUOUS_MATERIAL" | "AMBIGUOUS_SPECIFICATION" | "INSUFFICIENT_INFORMATION" | "OUT_OF_SCHEDULE"
    selected_hsn: Optional[str] = None
    selected_chapter: Optional[str] = None
    selected_description: Optional[str] = None
    confidence: float = 0.0
    relevance_confidence: float = 0.0
    chapter_confidence: float = 0.0
    hsn_confidence: float = 0.0
    prediction_mode: str = "EXACT_HSN"  # "EXACT_HSN" | "CHAPTER_ONLY_CLARIFY" | "CLARIFY_AMBIGUOUS" | "INSUFFICIENT_INFORMATION" | "OUT_OF_SCHEDULE"
    abstention_reason: Optional[str] = None
    separating_attributes: List[str] = field(default_factory=list)
    attribute_evidence: Dict[str, List[str]] = field(default_factory=dict)
    clarification_question: Optional[str] = None
    clarification_options: List[str] = field(default_factory=list)
    statutory_matches: List[Dict[str, Any]] = field(default_factory=list)
    active_vs_statutory: Dict[str, Any] = field(default_factory=dict)
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

    def classify(self, query: str, pool_size: int = 30) -> HSNV2ClassificationResult:
        q = (query or "").strip()
        if not q:
            return HSNV2ClassificationResult(
                query="",
                status="INSUFFICIENT_INFORMATION",
                clarification_question="Please provide a product description.",
            )

        # 1. Search Active Classification Dataset (expanded pool avoids premature GIR-6 6-digit loss)
        expanded_q, _ = self.hybrid_engine._expand_abbreviated_query(q)
        eval_query = expanded_q if expanded_q else q
        raw_pool = self.hybrid_engine.retrieve_pool(
            q, pool_size=pool_size, branch_k=max(45, pool_size + 15)
        )
        if raw_pool:
            classified = self.classifier.classify(eval_query, raw_pool)
            best_active_score = classified[0].confidence if classified else 0.0
            best_rel_conf = (
                classified[0].relevance_confidence
                if classified and classified[0].relevance_confidence > 0
                else best_active_score
            )
            res: AmbiguityResolutionResult = self.resolver.resolve_classified(q, classified)
        else:
            classified = []
            best_active_score = 0.0
            best_rel_conf = 0.0
            res = AmbiguityResolutionResult(
                status="NO_RELEVANT_MATCH",
                rationale="No matching candidates found in active schedule.",
            )

        # Compute independent calibrated chapter_confidence & hsn_confidence
        bundle = getattr(self.classifier, "calibration_bundle", None)
        if classified and bundle is not None:
            feats = extract_query_confidence_features(
                raw_logits=[c.candidate.raw_logit for c in classified],
                hsn_codes=[c.candidate.hsn_code for c in classified],
                chapter_codes=[c.candidate.chapter_code for c in classified],
                query=q,
                rel_threshold_logit=0.97,
                is_ambiguous=res.status in ("AMBIGUOUS_MATERIAL", "AMBIGUOUS_SPECIFICATION"),
            )
            chap_conf = round(float(bundle.chapter_calibrator.predict_proba_one(feats)), 4)
            hsn_conf = round(float(bundle.hsn_calibrator.predict_proba_one(feats)), 4)
        else:
            chap_conf = round(float(best_rel_conf), 4)
            hsn_conf = round(float(best_rel_conf), 4)

        # 2. Independently check Complete 98-Chapter Statutory Master and compare relevance
        comp: StatutoryComparisonResult = self.statutory_index.compare_active_vs_statutory(
            query=eval_query,
            best_active_score=best_active_score,
            reranker=self.classifier.reranker,
        )
        comp_summary = {
            "best_active_score": comp.best_active_score,
            "best_inactive_score": comp.best_inactive_score,
            "best_inactive_match": comp.best_inactive_match,
            "reason": comp.reason,
        }

        if comp.is_out_of_schedule and comp.best_inactive_match:
            inact = comp.best_inactive_match
            inact_score = float(inact.get("reranker_score", 0.0))
            return HSNV2ClassificationResult(
                query=q,
                status="OUT_OF_SCHEDULE",
                selected_hsn=inact.get("hsn_code"),
                selected_chapter=inact.get("chapter"),
                selected_description=inact.get("description"),
                confidence=inact_score,
                relevance_confidence=inact_score,
                chapter_confidence=inact_score,
                hsn_confidence=0.0,
                prediction_mode="OUT_OF_SCHEDULE",
                statutory_matches=comp.top_statutory_matches[:5],
                active_vs_statutory=comp_summary,
                rationale=comp.reason,
            )

        tau_abstain = bundle.tau_abstain if bundle is not None else 0.20
        if res.status == "NO_RELEVANT_MATCH" or (classified and best_rel_conf < tau_abstain):
            return HSNV2ClassificationResult(
                query=q,
                status="INSUFFICIENT_INFORMATION",
                selected_hsn=None,
                selected_chapter=None,
                confidence=best_rel_conf,
                relevance_confidence=best_rel_conf,
                chapter_confidence=chap_conf,
                hsn_confidence=0.0,
                prediction_mode="INSUFFICIENT_INFORMATION",
                abstention_reason=(
                    f"Calibrated relevance ({best_rel_conf:.2f}) below safe abstention threshold ({tau_abstain:.2f})."
                ),
                clarification_question=res.clarification_question
                or f"Insufficient product evidence for '{q}'. Please provide product identity, material, and intended use.",
                statutory_matches=comp.top_statutory_matches[:5],
                active_vs_statutory=comp_summary,
                rationale=res.rationale,
            )

        # Determine safe prediction mode (Scenario A vs B vs C)
        clar_opts = list(res.clarification_options)
        clar_q = res.clarification_question
        pred_mode = "EXACT_HSN"
        abst_reason = None

        if res.status in ("AMBIGUOUS_MATERIAL", "AMBIGUOUS_SPECIFICATION"):
            pred_mode = "CLARIFY_AMBIGUOUS"
        elif res.status == "INSUFFICIENT_INFORMATION":
            pred_mode = "INSUFFICIENT_INFORMATION"
            abst_reason = "No candidate met the calibrated SAME_PRODUCT threshold."
        elif res.status == "CLEAR" and bundle is not None and hsn_conf < bundle.tau_exact_hsn:
            # Scenario B: Chapter/heading is supported, but exact 8-digit HSN confidence is low
            same_head = [
                c for c in res.same_product_candidates
                if res.selected_hsn and c.candidate.hsn_code[:4] == res.selected_hsn[:4]
            ]
            if len(same_head) >= 2:
                pred_mode = "CHAPTER_ONLY_CLARIFY"
                abst_reason = (
                    f"Heading {res.selected_hsn[:4]} is supported (chapter_confidence={chap_conf:.2f}), "
                    f"but {len(same_head)} sibling 8-digit items compete (hsn_confidence={hsn_conf:.2f} < {bundle.tau_exact_hsn:.2f})."
                )
                if not clar_opts:
                    clar_opts = [
                        f"HSN {c.candidate.hsn_code} (Ch {c.candidate.chapter_code}): {c.candidate.description[:60]}"
                        for c in same_head[:4]
                    ]
                if not clar_q:
                    clar_q = (
                        f"Heading {res.selected_hsn[:4]} (Chapter {res.selected_chapter}) applies to '{q}', "
                        f"but exact 8-digit specification is needed to select between {len(same_head)} tariff items."
                    )

        return HSNV2ClassificationResult(
            query=q,
            status=res.status,
            selected_hsn=res.selected_hsn,
            selected_chapter=res.selected_chapter,
            selected_description=res.selected_description,
            confidence=res.confidence,
            relevance_confidence=round(float(best_rel_conf), 4),
            chapter_confidence=chap_conf,
            hsn_confidence=hsn_conf,
            prediction_mode=pred_mode,
            abstention_reason=abst_reason,
            separating_attributes=res.separating_attributes,
            attribute_evidence=res.attribute_evidence,
            clarification_question=clar_q,
            clarification_options=clar_opts,
            statutory_matches=comp.top_statutory_matches[:5],
            active_vs_statutory=comp_summary,
            rationale=res.rationale,
        )
