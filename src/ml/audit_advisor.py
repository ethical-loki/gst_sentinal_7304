"""
HSN Audit Advisor Service: src/ml/audit_advisor.py
High-level service coordinating retrieval, risk scoring, Tree SHAP explainability,
and counterfactual recommendation generation for GST Sentinel audit workflows.
Adheres to strict read-only invoice immutability.
"""

import copy
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field

from src.ml.counterfactual_generator import HSNCounterfactualGenerator
from src.ml.explainability_engine import HSNExplainabilityEngine
from src.ml.misclassification_scorer import HSNMisclassificationScorer
from src.nlp.hsn_search import HSNSemanticSearchEngine

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_ARTIFACTS_DIR = ROOT_DIR / "artifacts"


# ==============================================================================
# Pydantic Schemas for Frontend / API Integration
# ==============================================================================

class OriginalPrediction(BaseModel):
    hsn: str = Field(..., description="Declared or initially retrieved HSN code")
    error_probability: float = Field(..., description="Calibrated misclassification risk probability [0.0, 1.0]")
    risk_level: str = Field(..., description="Risk tier: LOW, MEDIUM, or HIGH")


class CounterfactualRecommendation(BaseModel):
    recommended_hsn: str = Field(..., description="Minimal corrective intervention HSN code")
    description: str = Field(..., description="Statutory tariff description for recommended HSN")
    calibrated_error_probability: float = Field(..., description="Post-intervention risk probability P(Error | h*)")
    risk_drop: float = Field(..., description="Absolute drop in error risk delta")
    status: str = Field(..., description="SAFE_REPLACEMENT_FOUND or UNRESOLVED_MANUAL_REVIEW")


class SuggestedAction(BaseModel):
    action_type: str = Field(..., description="REPLACE_HSN, NO_ACTION_REQUIRED, or MANUAL_INSPECTION")
    replacement_hsn: Optional[str] = Field(None, description="Recommended HSN code for one-click fix")
    statutory_description: Optional[str] = Field(None, description="Official statutory tariff description")
    post_intervention_risk: Optional[float] = Field(None, description="Post-intervention calibrated error risk")
    risk_delta: Optional[float] = Field(None, description="Expected drop in misclassification risk")
    explanation: str = Field(..., description="Human-readable guidance for tax auditor")


class AuditItemResult(BaseModel):
    flagged: bool = Field(..., description="True if item exceeds risk threshold")
    status_badge: str = Field(..., description="Frontend badge: FLAGGED or AUTO_APPROVED")
    original_prediction: OriginalPrediction
    explanations: List[str] = Field(default_factory=list, description="Deconstructed Tree SHAP audit evidence")
    human_readable_reasons: List[str] = Field(default_factory=list, description="Bullet points for frontend display")
    counterfactual_recommendation: Optional[CounterfactualRecommendation] = None
    suggested_action: Optional[SuggestedAction] = None
    shap_attributions: Optional[Dict[str, float]] = None


class InvoiceAuditReport(BaseModel):
    invoice_number: str = Field(..., description="Invoice identifier or document reference")
    total_items: int = Field(..., description="Total line items evaluated")
    flagged_items_count: int = Field(..., description="Number of items requiring review or reclassification")
    auto_approved_count: int = Field(..., description="Number of items safe to auto-file")
    overall_status: str = Field(..., description="FLAGGED if any item flagged else AUTO_APPROVED")
    items: List[AuditItemResult] = Field(default_factory=list, description="Per-item audit and recommendation details")


# ==============================================================================
# High-Level Audit Advisor Coordinator
# ==============================================================================

class HSNAuditAdvisor:
    """
    High-level audit service orchestrating retrieval, Gatekeeper scoring,
    Tree SHAP explainability, and counterfactual simulation for GST Sentinel.
    """

    def __init__(
        self,
        scorer: Optional[HSNMisclassificationScorer] = None,
        explainer: Optional[HSNExplainabilityEngine] = None,
        counterfactual_gen: Optional[HSNCounterfactualGenerator] = None,
        search_engine: Optional[HSNSemanticSearchEngine] = None,
        artifacts_dir: Optional[Union[str, Path]] = None,
        safety_threshold: float = 0.05,
        flag_threshold: float = 0.15,
    ):
        self.artifacts_dir = Path(artifacts_dir or DEFAULT_ARTIFACTS_DIR)
        self.safety_threshold = float(safety_threshold)
        self.flag_threshold = float(flag_threshold)

        # Initialize underlying engines lazily / with dependency injection
        self.scorer = scorer or HSNMisclassificationScorer(
            artifacts_dir=self.artifacts_dir,
            autofile_threshold=self.flag_threshold,
        )
        self.explainer = explainer or HSNExplainabilityEngine(
            model=self.scorer.model,
            artifacts_dir=self.artifacts_dir,
            hsn_medians=self.scorer.hsn_medians,
            chapter_medians=self.scorer.chapter_medians,
            global_median_price=self.scorer.global_median_price,
        )
        self.counterfactual_gen = counterfactual_gen or HSNCounterfactualGenerator(
            scorer=self.scorer,
            explainer=self.explainer,
            artifacts_dir=self.artifacts_dir,
            safety_threshold=self.safety_threshold,
            flag_threshold=self.flag_threshold,
        )
        self._search_engine = search_engine

    @property
    def search_engine(self) -> HSNSemanticSearchEngine:
        """Lazy loader for Day 05 HSN Semantic Search Engine."""
        if self._search_engine is None:
            self._search_engine = HSNSemanticSearchEngine()
        return self._search_engine

    def review_line_item(
        self,
        invoice_line: Dict[str, Any],
        day5_retrieval_output: Optional[Any] = None,
        top_k: int = 5,
    ) -> AuditItemResult:
        """
        Audits a single invoice line item:
        1. Ensures read-only immutability.
        2. Retrieves Day 05 candidate HSN codes if not provided.
        3. Evaluates Day 06 risk, extracts Tree SHAP drivers, and simulates counterfactuals.
        4. Serializes into Pydantic AuditItemResult.
        """
        # Strict Read-Only Safety Invariant: deep copy input record upfront
        line_clean = copy.deepcopy(invoice_line)

        # 1. Retrieve candidate HSNs from Day 05 search engine if not provided
        candidates = day5_retrieval_output
        if candidates is None:
            desc = (
                line_clean.get("product_description")
                or line_clean.get("clean_description")
                or line_clean.get("description")
                or ""
            )
            candidates = self.search_engine.search(desc, top_k=top_k)

        # 2. Run Counterfactual Simulation & Explainability Engine
        gen_result = self.counterfactual_gen.generate(
            invoice_line=line_clean,
            candidates=candidates,
            safety_threshold=self.safety_threshold,
        )

        # 3. Construct Pydantic Response Payload
        orig_dict = gen_result["original_prediction"]
        orig_obj = OriginalPrediction(
            hsn=orig_dict["hsn"],
            error_probability=orig_dict["error_probability"],
            risk_level=orig_dict["risk_level"],
        )

        rec_dict = gen_result.get("counterfactual_recommendation")
        rec_obj = None
        if rec_dict:
            rec_obj = CounterfactualRecommendation(
                recommended_hsn=rec_dict["recommended_hsn"],
                description=rec_dict["description"],
                calibrated_error_probability=rec_dict["calibrated_error_probability"],
                risk_drop=rec_dict["risk_drop"],
                status=rec_dict["status"],
            )

        act_dict = gen_result.get("suggested_action")
        act_obj = None
        if act_dict:
            act_obj = SuggestedAction(
                action_type=act_dict["action_type"],
                replacement_hsn=act_dict.get("replacement_hsn"),
                statutory_description=act_dict.get("statutory_description"),
                post_intervention_risk=act_dict.get("post_intervention_risk"),
                risk_delta=act_dict.get("risk_delta"),
                explanation=act_dict["explanation"],
            )

        return AuditItemResult(
            flagged=gen_result["flagged"],
            status_badge=gen_result["status_badge"],
            original_prediction=orig_obj,
            explanations=gen_result.get("explanations", []),
            human_readable_reasons=gen_result.get("human_readable_reasons", []),
            counterfactual_recommendation=rec_obj,
            suggested_action=act_obj,
            shap_attributions=gen_result.get("shap_attributions", {}),
        )

    def review_invoice(
        self,
        invoice_payload: Union[Dict[str, Any], List[Dict[str, Any]]],
        top_k: int = 5,
    ) -> InvoiceAuditReport:
        """
        Audits an entire draft invoice document across all line items.
        Preserves strict invoice immutability.
        """
        payload_copy = copy.deepcopy(invoice_payload)

        inv_num = "DRAFT_INV"
        raw_items: List[Dict[str, Any]] = []

        if isinstance(payload_copy, list):
            raw_items = payload_copy
        elif isinstance(payload_copy, dict):
            inv_num = str(
                payload_copy.get("invoice_number")
                or payload_copy.get("invoice_no")
                or payload_copy.get("document_number")
                or payload_copy.get("id")
                or "DRAFT_INV"
            )
            raw_items = (
                payload_copy.get("items")
                or payload_copy.get("line_items")
                or payload_copy.get("lines")
                or [payload_copy]
            )

        item_audits: List[AuditItemResult] = []
        flagged_count = 0
        auto_approved_count = 0

        for item in raw_items:
            res = self.review_line_item(item, top_k=top_k)
            item_audits.append(res)
            if res.flagged:
                flagged_count += 1
            else:
                auto_approved_count += 1

        overall_status = "FLAGGED" if flagged_count > 0 else "AUTO_APPROVED"

        return InvoiceAuditReport(
            invoice_number=inv_num,
            total_items=len(item_audits),
            flagged_items_count=flagged_count,
            auto_approved_count=auto_approved_count,
            overall_status=overall_status,
            items=item_audits,
        )
