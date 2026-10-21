"""
ML Intelligence Package for GST Sentinel
Contains:
- Day 06: HSN Misclassification Scorer, Feature Extraction, and Platt Calibration.
- Day 07: Tree SHAP Explainability Engine, Counterfactual Recommendation Generator, and Audit Advisor.
"""

from src.ml.audit_advisor import (
    AuditItemResult,
    CounterfactualRecommendation,
    HSNAuditAdvisor,
    InvoiceAuditReport,
    OriginalPrediction,
    SuggestedAction,
)
from src.ml.hsn_audit_sentinel import (
    AuditSentinelInvoiceReport,
    AuditSentinelItemResult,
    HSNAuditSentinel,
)
from src.ml.counterfactual_generator import HSNCounterfactualGenerator
from src.ml.explainability_engine import (
    CHAPTER_DESCRIPTIONS,
    HSNExplainabilityEngine,
    get_chapter_description,
)
from src.ml.misclassification_features import (
    FEATURE_COLUMNS,
    PlattCalibrator,
    compute_token_entropy,
    extract_features,
    load_metadata_tables,
)
from src.ml.misclassification_scorer import HSNMisclassificationScorer

__all__ = [
    "FEATURE_COLUMNS",
    "PlattCalibrator",
    "compute_token_entropy",
    "extract_features",
    "load_metadata_tables",
    "HSNMisclassificationScorer",
    "CHAPTER_DESCRIPTIONS",
    "get_chapter_description",
    "HSNExplainabilityEngine",
    "HSNCounterfactualGenerator",
    "HSNAuditAdvisor",
    "HSNAuditSentinel",
    "AuditSentinelItemResult",
    "AuditSentinelInvoiceReport",
    "OriginalPrediction",
    "CounterfactualRecommendation",
    "SuggestedAction",
    "AuditItemResult",
    "InvoiceAuditReport",
]
