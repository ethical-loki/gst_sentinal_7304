"""
tests/test_hsn_rag_layer.py
===========================
Comprehensive Test Suite for HSN & ITC-HS RAG Application Layer:
- Stage 1: Customs Classification & Tariff Attribute Extractor
- Stage 2: Statutory Context Retriever (RAG Augmentation)
- Stage 3: Statutory HSN & ITC-HS Legal Verification Engine
- End-to-End RAG Pipeline Execution & API Endpoints
"""

import pytest
from fastapi.testclient import TestClient
from backend.main import app
from src.nlp.hsn_rag_layer import (
    get_hsn_rag_application_layer,
    AttributeExtractionResult,
    StatutoryVerificationResult,
    RAGPipelineResult
)

client = TestClient(app)
rag = get_hsn_rag_application_layer()


def test_stage1_extraction_sports_shoes_ambiguity():
    """Sports Shoes without upper material must flag needs_clarification=True."""
    res = rag.extract_attributes("Sports Shoes")
    assert isinstance(res, AttributeExtractionResult)
    assert res.product_normalized == "Sports Shoes"
    assert res.needs_clarification is True
    assert res.clarification is not None
    assert "upper" in res.clarification.question.lower()
    assert len(res.clarification.options) >= 3
    assert any("6402" in opt or "Plastics" in opt for opt in res.clarification.options)
    assert any("6403" in opt or "Leather" in opt for opt in res.clarification.options)
    assert any("6404" in opt or "Textile" in opt for opt in res.clarification.options)


def test_stage1_extraction_whole_roasted_coffee_beans():
    """Whole Roasted Coffee Beans must extract Coffee material, roasted state, and needs_clarification=False."""
    res = rag.extract_attributes("Whole Roasted Coffee Beans")
    assert res.needs_clarification is False
    assert res.clarification is None
    assert "Coffee" in res.attributes.material
    assert "Roasted" in res.attributes.processing_state
    assert res.attributes.mounted_state == "not_applicable"
    assert "0901" in res.search_keywords or "coffee roasted" in res.search_keywords


def test_stage1_extraction_mounted_brake_pads():
    """Mounted Brake Pads must detect mounted_state='mounted' and automotive function."""
    res = rag.extract_attributes("Mounted Brake Linings / Brake Pads for Passenger Cars")
    assert res.needs_clarification is False
    assert res.attributes.mounted_state == "mounted"
    assert "braking" in res.attributes.function_use.lower() or "motor vehicle" in res.attributes.function_use.lower()


def test_stage2_context_retrieval():
    """Context retriever must inject statutory legal notes and candidate headings."""
    ext = rag.extract_attributes("Whole Roasted Coffee Beans")
    ctx = rag.retrieve_statutory_context(ext)
    assert "candidates" in ctx
    assert "statutory_notes" in ctx
    notes_str = " ".join(ctx["statutory_notes"])
    assert "Chapter 09" in notes_str or "Chapter 18" in notes_str
    assert "General Interpretative Rule" in notes_str or "GIR" in notes_str


def test_stage3_legal_verification_coffee_vs_cocoa():
    """Coffee Beans must strictly resolve to Chapter 09 (0901 21 10) and reject Cocoa (1801 00 00)."""
    ext = rag.extract_attributes("Whole Roasted Coffee Beans")
    ctx = rag.retrieve_statutory_context(ext)
    ver = rag.verify_statutory_classification(
        product_description="Whole Roasted Coffee Beans",
        extraction=ext,
        candidates=ctx["candidates"],
        statutory_notes=ctx["statutory_notes"]
    )
    assert isinstance(ver, StatutoryVerificationResult)
    assert ver.selected_hsn.replace(" ", "") == "09012110"
    assert ver.gst_rate_expected is None
    assert "Chapter 18 Note 1" in ver.statutory_rationale or "GIR 1" in ver.statutory_rationale
    assert any("1801" in rej.hsn for rej in ver.rejected_candidates)


def test_stage3_legal_verification_mounted_brakes():
    """Mounted brake pads must resolve to Heading 8708 and reject Chapter 68 unmounted friction."""
    ext = rag.extract_attributes("Mounted Brake Linings / Brake Pads for Passenger Cars")
    ctx = rag.retrieve_statutory_context(ext)
    ver = rag.verify_statutory_classification(
        product_description="Mounted Brake Linings / Brake Pads for Passenger Cars",
        extraction=ext,
        candidates=ctx["candidates"],
        statutory_notes=ctx["statutory_notes"]
    )
    assert ver.selected_hsn.replace(" ", "") in ["87083000", "87083100"]
    assert ver.gst_rate_expected is None
    assert "Chapter 68 Note 1" in ver.statutory_rationale or "Section XVII" in ver.statutory_rationale
    assert any("6813" in rej.hsn for rej in ver.rejected_candidates)


def test_stage3_legal_verification_lithium_ion_battery():
    """Lithium-ion Battery Pack must resolve to 8507 60 00 and reject 8506 (primary non-rechargeable)."""
    ext = rag.extract_attributes("Lithium-ion Battery Pack")
    ctx = rag.retrieve_statutory_context(ext)
    ver = rag.verify_statutory_classification(
        product_description="Lithium-ion Battery Pack",
        extraction=ext,
        candidates=ctx["candidates"],
        statutory_notes=ctx["statutory_notes"]
    )
    assert ver.selected_hsn.replace(" ", "") == "85076000"
    assert ver.gst_rate_expected is None
    assert any("8506" in rej.hsn for rej in ver.rejected_candidates)


def test_end_to_end_pipeline_ambiguous_item_pauses_for_clarification():
    """Industrial pipe without material must halt with status='REQUIRES_CLARIFICATION'."""
    pipe_res = rag.run_pipeline("Industrial pipe")
    assert pipe_res.status == "REQUIRES_CLARIFICATION"
    assert pipe_res.verification is None
    assert pipe_res.extraction.needs_clarification is True
    assert pipe_res.extraction.clarification is not None


def test_end_to_end_pipeline_clarified_item_completes():
    """Industrial pipe with customer clarification 'Stainless steel' must complete to 7304 11 10."""
    pipe_res = rag.run_pipeline(
        product_description="Industrial pipe",
        customer_clarification="Stainless steel seamless line pipe"
    )
    assert pipe_res.status == "SUCCESS"
    assert pipe_res.verification is not None
    assert pipe_res.verification.selected_hsn.replace(" ", "") == "73041110"


def test_api_rag_extract_attributes_endpoint():
    """Test POST /api/v1/hsn-rag/extract-attributes."""
    resp = client.post(
        "/api/v1/hsn-rag/extract-attributes",
        json={"product_description": "Sports Shoes"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["product_normalized"] == "Sports Shoes"
    assert data["needs_clarification"] is True


def test_api_rag_pipeline_endpoint():
    """Test POST /api/v1/hsn-rag/pipeline for Whole Roasted Coffee Beans."""
    resp = client.post(
        "/api/v1/hsn-rag/pipeline",
        json={"product_description": "Whole Roasted Coffee Beans"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "SUCCESS"
    assert data["verification"]["selected_hsn"].replace(" ", "") == "09012110"


def test_three_stage_clarification_resolution_architecture():
    """
    Test the Three-Stage Clarification Resolution Architecture:
    [User Input: 'PVC'] -> [Stage 1: Context Aggregator] -> [Stage 2: Vector Search Index (Top 3)] -> [Stage 3: AI Legal Selector]
    """
    res = rag.resolve_clarification_three_stage(
        base_product="Industrial Pipe",
        user_clarification="PVC"
    )
    assert res["status"] == "RESOLVED_VIA_3_STAGE_ARCHITECTURE"

    # Stage 1: Context Aggregator check
    s1 = res["stage1_context_aggregator"]
    assert "Industrial Pipe" in s1["master_search_string"]
    assert any(w in s1["master_search_string"] for w in ("PVC", "Plastics"))

    # Stage 2: Vector Search Index check (Top 3 official candidates from data/raw/HSN_SAC (1).xlsx)
    s2 = res["stage2_vector_search"]
    assert len(s2["top_3_candidates"]) == 3
    top3_codes = [c["hsn_code"] for c in s2["top_3_candidates"]]
    assert any(c in top3_codes for c in ("3917 23 10", "3917 21 10"))

    # Stage 3: AI Legal Selector check (Strictly from Top 3)
    s3 = res["stage3_ai_legal_selector"]
    assert s3["strictly_from_top3_guardrail"] is True
    assert s3["selected_hsn"] in top3_codes
    assert s3["selected_hsn"] in ("3917 23 10", "3917 21 10")
    assert s3["gst_rate"] is None


def test_api_resolve_clarification_endpoint():
    """Test POST /api/v1/hsn-rag/resolve-clarification endpoint."""
    resp = client.post(
        "/api/v1/hsn-rag/resolve-clarification",
        json={
            "base_product": "Industrial Pipe",
            "user_clarification": "PVC"
        }
    )
    assert resp.status_code == 200
    data = resp.json()
    master_str = data["stage1_context_aggregator"]["master_search_string"]
    assert "Industrial Pipe" in master_str
    assert "PVC" in master_str or "Plastics" in master_str
    assert len(data["stage2_vector_search"]["top_3_candidates"]) == 3
    assert data["stage3_ai_legal_selector"]["selected_hsn"] in ("3917 23 10", "3917 21 10")
    assert data["unified_row"]["final_hsn"] in ("3917 23 10", "3917 21 10")
    assert data["unified_row"]["final_gst_rate"] is None


def test_statutory_auditor_format_a_success_and_outdated_code_rejection():
    """
    Test FORMAT A (SUCCESS):
    - Rejects deprecated 7304.10 (Rule 4: Outdated Code Detection)
    - Avoids residual .90 'Other' bucket (Rule 2: Commodity Form Specificity)
    - Selects 7304 11 10 for Stainless Steel Pipe
    """
    top_3 = [
        {"option_id": "OPTION_1", "hsn_code": "7304 10 11", "official_description": "[DEPRECATED PRE-2007] Line pipe", "chapter": "73", "gst_rate": None, "similarity_score": 0.99},
        {"option_id": "OPTION_2", "hsn_code": "7304 11 90", "official_description": "Line pipe : -- Of stainless steel : --- Blanks for tubes and pipes (Other)", "chapter": "73", "gst_rate": None, "similarity_score": 0.96},
        {"option_id": "OPTION_3", "hsn_code": "7304 11 10", "official_description": "Line pipe : -- Of stainless steel : --- Tubes and pipes", "chapter": "73", "gst_rate": None, "similarity_score": 0.95}
    ]
    out = rag.evaluate_statutory_customs_auditor(
        user_raw_input="Stainless Steel Line Pipe",
        context_aggregator_attributes={"material": "Stainless Steel", "processing_state": "Seamless Line Pipe"},
        vector_search_top_3_options=top_3
    )
    assert out["status"] == "SUCCESS"
    assert out["hsn_code"] == "7304 11 10"
    assert out["gst_rate"] is None
    assert "7304 10 11" in out["statutory_rationale"]  # Outdated code rejection noted
    assert "7304 11 90" in out["statutory_rationale"]  # Residual .90 avoidance noted


def test_statutory_auditor_format_b_material_specificity_bifurcation():
    """
    Test FORMAT B (NEED_CLARIFICATION):
    When user inputs 'Steel Pipe' without specifying Stainless Steel (7304.11) vs Carbon Steel (7304.19),
    Rule 1 (Material Specificity) halts and returns NEED_CLARIFICATION.
    """
    resp = client.post(
        "/api/v1/hsn-rag/statutory-auditor-evaluate",
        json={"user_raw_input": "Steel Pipe"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "NEED_CLARIFICATION"
    assert data["hsn_code"] is None
    assert data["gst_rate"] is None
    assert len(data["missing_attributes"]) > 0
    assert "Stainless Steel" in data["user_prompt_suggestion"] and "Carbon Steel" in data["user_prompt_suggestion"]
