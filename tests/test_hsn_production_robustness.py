"""
Production Robustness Verification Suite for HSN Model Intelligence
Covers:
1. Module 1: Pure HSN Intelligence Engine (Vector Dot-Product S = Q · D^T, Dynamic Ingestion Adaptors)
2. Module 2: HSN Audit Sentinel (Gatekeeper Scorer, Tree SHAP Explanations, Counterfactual Fixes)
3. Day 5: Contrastive HSN Search Engine & Backwards Compatibility
4. FastAPI Backend Endpoints (Module 1 & Module 2 REST API endpoints)
"""

import io
import time
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parent.parent

from src.nlp.hsn_intelligence import (
    HSNIntelligenceEngine,
    DynamicHSNSemanticMatcher,
    HSNMatchDecision,
    SpreadsheetIngestionAdaptor,
    RESTMicroserviceAdaptor,
    DatabaseQueueConsumer,
    clean_trade_description,
)
from src.nlp.hsn_search import HSNSemanticSearchEngine, SearchResultList
from src.ml.hsn_audit_sentinel import (
    HSNAuditSentinel,
    AuditSentinelItemResult,
    AuditSentinelInvoiceReport,
)
from backend.main import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def hsn_engine():
    return HSNIntelligenceEngine()


@pytest.fixture(scope="module")
def audit_sentinel():
    return HSNAuditSentinel()


# ============================================================================
# MODULE 1: PURE HSN INTELLIGENCE ENGINE & GEOMETRIC MATCHER
# ============================================================================

def test_module1_zero_latency_startup(hsn_engine):
    """Module 1: Verifies in-memory catalog and L2 normalized matrix are ready."""
    matcher = hsn_engine.matcher
    assert matcher.catalog_matrix is not None
    assert matcher.catalog_size >= 12000
    assert matcher.embedding_dim in (128, 384)
    # Norm check
    norms = np.linalg.norm(matcher.catalog_matrix[:20], axis=1)
    assert np.allclose(norms, 1.0, atol=1e-3)


def test_module1_edge_cases_and_numeric_hsn(hsn_engine):
    """Module 1: Robustness against empty, whitespace, and direct numeric HSN queries."""
    # Empty query handling
    empty_res = hsn_engine.match_batch(["", "   "])
    assert len(empty_res) == 2
    assert empty_res[0]["decision"] == HSNMatchDecision.UNMAPPED.value

    # Direct numeric code query
    num_res = hsn_engine.match_batch(["7307", "84818090"])
    assert len(num_res) == 2
    assert num_res[0]["matched_hsn"].startswith("7307")
    assert num_res[0]["decision"] == HSNMatchDecision.AUTOMATED_MATCH.value
    assert num_res[1]["matched_hsn"].startswith("8481")


def test_module1_industrial_servo_motor_classification(hsn_engine):
    """Module 1: Verifies standard industrial AC servo motor correctly resolves to 85015290.
    
    Validates:
    1. Post-nominal qualifier parsing ('ac' as specifier, 'motor' as head noun).
    2. GIR 3(a) stemming & specificity (avoids squirrel cage induction 85015310).
    3. Intermediate capacity alignment (750 W to 75 kW: 8501 52 90).
    """
    res = hsn_engine.match_batch(["industrial servo motor ac", "industrial servo motor AC"])
    assert len(res) == 2
    for m in res.matches:
        assert m.matched_hsn == "85015290", f"Expected 85015290, got {m.matched_hsn}"
        assert m.decision == HSNMatchDecision.AUTOMATED_MATCH.value
        assert m.confidence_score >= 0.85
        assert "motors" in m.official_description.lower() or "motor" in m.official_description.lower()


def test_module1_spreadsheet_adaptor_robustness(hsn_engine):
    """Module 1 Adaptor: Auto-detects columns, handles empty and arbitrary DataFrames."""
    adaptor = hsn_engine.spreadsheet_adaptor

    # 1. Custom column name
    df_custom = pd.DataFrame({
        "item_code": ["A1", "A2"],
        "trade_description": ["SS 304 hex nipple 1/2 inch", "cast iron non return check valve 50mm"],
    })
    res_df = adaptor.process_dataframe(df_custom, description_col="trade_description")
    assert "matched_hsn" in res_df.columns
    assert res_df["matched_hsn"].iloc[0].startswith("7307")

    # 2. Missing specified column (fallback to auto-detection)
    res_fallback = adaptor.process_dataframe(df_custom, description_col="non_existent_column")
    assert "matched_hsn" in res_fallback.columns
    assert res_fallback["matched_hsn"].iloc[0].startswith("7307")

    # 3. Completely empty DataFrame
    res_empty = adaptor.process_dataframe(pd.DataFrame())
    assert len(res_empty) == 0


def test_module1_rest_and_queue_adaptors(hsn_engine):
    """Module 1 Adaptors: REST payload and Database Queue processing."""
    # REST microservice adaptor
    rest_adaptor = hsn_engine.rest_adaptor
    payload = {
        "items": [
            {"id": "L1", "description": "1/2 inch SS hex nipple"},
            {"id": "L2", "description": "industrial 2-piece ball valve 1 inch BSP"},
        ]
    }
    resp = rest_adaptor.process_payload(payload)
    assert resp["total_items"] == 2
    assert resp["items"][0]["item_id"] == "L1"
    assert resp["items"][0]["matched_hsn"].startswith("7307")

    # Database Queue consumer
    consumer = hsn_engine.queue_consumer
    mock_db = [{"db_id": 99, "product_description": "solar on grid inverter 5kw 3 phase"}]
    written = []
    consumer.process_unprocessed_batch(
        fetch_items_fn=lambda n: mock_db,
        write_results_fn=lambda updates: written.extend(updates),
    )
    assert len(written) == 1
    assert written[0]["matched_hsn"].startswith("8504")


# ============================================================================
# MODULE 2: HSN AUDIT SENTINEL (GATEKEEPER + SHAP + COUNTERFACTUAL)
# ============================================================================

def test_module2_audit_item_safe_autofile(audit_sentinel):
    """Module 2: Compliant item passes Gatekeeper as AUTO_APPROVED."""
    compliant_line = {
        "product_description": "1/2 inch SS hex nipple",
        "unit_price": 120.0,
        "declared_hsn_chapter": "73",
        "declared_hsn": "73072900",
        "supplier_gstin": "27CLEAN1234F1Z1",
    }
    res = audit_sentinel.audit_item(compliant_line)
    assert isinstance(res, AuditSentinelItemResult)
    assert res.module == "HSNAuditSentinel"
    assert res.flagged is False
    assert res.status_badge == "AUTO_APPROVED"
    assert res.original_prediction.risk_level in ("LOW", "MEDIUM")
    assert res.original_prediction.error_probability < 0.25


def test_module2_audit_item_high_risk_and_counterfactual(audit_sentinel):
    """Module 2: Flagged fraudulent misclassification generates Tree SHAP evidence and counterfactual fixes."""
    # Case A: Chapter mismatch with clean vendor -> counterfactual achieves P(Error|h*) < 0.05 (SAFE_REPLACEMENT_FOUND)
    clean_vendor_line = {
        "product_description": "Screws bolts nuts of iron or steel",
        "unit_price": 450.0,
        "declared_hsn_chapter": "28",  # Declaring steel fasteners under Chapter 28 (Chemicals)
        "declared_hsn": "28011000",
        "supplier_gstin": "27CLEAN1234F1Z1",
    }
    orig_copy = dict(clean_vendor_line)
    res_clean = audit_sentinel.audit_item(clean_vendor_line)

    assert clean_vendor_line == orig_copy, "Read-only invariant violated: input line was mutated!"
    assert isinstance(res_clean, AuditSentinelItemResult)
    assert res_clean.flagged is True
    assert res_clean.status_badge == "FLAGGED"
    assert res_clean.original_prediction.error_probability >= 0.15
    assert len(res_clean.explanations) > 0
    assert any("chapter" in exp.lower() for exp in res_clean.explanations)

    rec_clean = res_clean.counterfactual_recommendation
    assert rec_clean is not None
    assert rec_clean.recommended_hsn.startswith("73")
    assert rec_clean.calibrated_error_probability < 0.05
    assert rec_clean.risk_drop > 0.10
    assert rec_clean.status == "SAFE_REPLACEMENT_FOUND"

    # Case B: Known high-risk vendor (07LJKKT0958C1ZC with 29.4% error history) -> UNRESOLVED_MANUAL_REVIEW
    bogus_vendor_line = {
        "product_description": "Screws bolts nuts of iron or steel",
        "unit_price": 450.0,
        "declared_hsn_chapter": "28",
        "declared_hsn": "28011000",
        "supplier_gstin": "07LJKKT0958C1ZC",
    }
    res_bogus = audit_sentinel.audit_item(bogus_vendor_line)
    rec_bogus = res_bogus.counterfactual_recommendation
    assert rec_bogus is not None
    assert rec_bogus.recommended_hsn.startswith("73")
    assert rec_bogus.risk_drop > 0.25
    assert rec_bogus.status == "UNRESOLVED_MANUAL_REVIEW"


def test_module2_audit_invoice_aggregation(audit_sentinel):
    """Module 2: Audits entire invoice and produces document-level triage report."""
    invoice_payload = {
        "invoice_number": "INV-2026-TEST-001",
        "items": [
            {
                "product_description": "1/2 inch SS hex nipple",
                "unit_price": 120.0,
                "declared_hsn_chapter": "73",
                "declared_hsn": "73072900",
            },
            {
                "product_description": "Screws bolts nuts of iron or steel",
                "unit_price": 450.0,
                "declared_hsn_chapter": "28",  # Misclassification
                "declared_hsn": "28011000",
            },
        ],
    }
    report = audit_sentinel.audit_invoice(invoice_payload)
    assert isinstance(report, AuditSentinelInvoiceReport)
    assert report.invoice_number == "INV-2026-TEST-001"
    assert report.total_items == 2
    assert report.flagged_items_count == 1
    assert report.auto_approved_count == 1
    assert report.overall_status == "FLAGGED"


# ============================================================================
# DAY 5: CONTRASTIVE SEARCH ENGINE & BACKWARDS COMPATIBILITY
# ============================================================================

def test_day5_backwards_compatibility(hsn_engine):
    """Day 5: Search and classify_description return SearchResultList with statutory metadata."""
    # 1. Direct search
    res = hsn_engine.search("ball valve 1 inch BSP", top_k=3)
    assert isinstance(res, SearchResultList)
    assert len(res) > 0
    assert res[0]["hsn_code"].startswith("8481")
    assert "gst_rate" in res[0]
    assert "is_blocked_17_5" in res[0]

    # 2. classify_description alias
    class_res = hsn_engine.classify_description("1/2 inch SS hex nipple", top_k=3)
    assert isinstance(class_res, SearchResultList)
    assert len(class_res) > 0
    assert class_res[0]["hsn_code"].startswith("7307")


# ============================================================================
# FASTAPI ENDPOINTS INTEGRATION
# ============================================================================

def test_api_v1_hsn_intelligence_search(client):
    """API: GET /api/v1/hsn-intelligence/search returns pure Module 1 results."""
    resp = client.get("/api/v1/hsn-intelligence/search?q=hex+nipple&top_k=5")
    assert resp.status_code == 200
    data = resp.json()
    assert "matches" in data
    assert len(data["matches"]) > 0
    assert data["matches"][0]["hsn_code"].startswith("7307")
    assert "gst_rate" in data["matches"][0]


def test_api_v1_hsn_intelligence_batch_match(client):
    """API: POST /api/v1/hsn-intelligence/batch-match processes JSON batch."""
    payload = {
        "items": [
            "SS 304 hex nipple 1/2 inch",
            "industrial 2-piece ball valve 1 inch BSP",
        ]
    }
    resp = client.post("/api/v1/hsn-intelligence/batch-match", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_items"] == 2
    assert len(data["items"]) == 2
    assert data["items"][0]["matched_hsn"].startswith("7307")
    assert data["items"][1]["matched_hsn"].startswith("8481")


def test_api_unified_hsn_search_modes(client):
    """API: GET /api/hsn-search in both 'intelligence' (Module 1) and 'sentinel' (Module 2) modes."""
    # Intelligence mode (Module 1)
    resp_intel = client.get("/api/hsn-search?q=hex+nipple&mode=intelligence")
    assert resp_intel.status_code == 200
    data_intel = resp_intel.json()
    assert data_intel["mode"] == "intelligence"
    assert data_intel["gatekeeper"] is None

    # Sentinel mode (Module 2)
    resp_sent = client.get("/api/hsn-search?q=hex+nipple&mode=sentinel&unit_price=120&chapter=73")
    assert resp_sent.status_code == 200
    data_sent = resp_sent.json()
    assert data_sent["mode"] == "sentinel"
    assert data_sent["gatekeeper"] is not None
    assert "is_safe_to_autofile" in data_sent["gatekeeper"]


def test_api_v1_audit_sentinel_endpoints(client):
    """API: Dedicated Module 2 endpoints /api/v1/audit-sentinel/audit-item and audit-invoice."""
    # Item-level audit
    item_payload = {
        "product_description": "Screws bolts nuts of iron or steel",
        "unit_price": 450.0,
        "declared_hsn_chapter": "28",
        "declared_hsn": "28011000",
    }
    resp_item = client.post("/api/v1/audit-sentinel/audit-item", json=item_payload)
    assert resp_item.status_code == 200
    item_data = resp_item.json()
    assert item_data["module"] == "HSNAuditSentinel"
    assert item_data["flagged"] is True
    assert item_data["status_badge"] == "FLAGGED"
    assert item_data["counterfactual_recommendation"]["recommended_hsn"].startswith("73")

    # Invoice-level audit
    inv_payload = {
        "invoice_number": "INV-PROD-999",
        "items": [item_payload],
    }
    resp_inv = client.post("/api/v1/audit-sentinel/audit-invoice", json=inv_payload)
    assert resp_inv.status_code == 200
    inv_data = resp_inv.json()
    assert inv_data["invoice_number"] == "INV-PROD-999"
    assert inv_data["flagged_items_count"] == 1
    assert inv_data["overall_status"] == "FLAGGED"
