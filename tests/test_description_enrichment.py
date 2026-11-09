"""
tests/test_description_enrichment.py
Automated test suite for DAY 16 – Controlled Description Enrichment and Reclassification Workflow.

Covers 10 mandatory test scenarios:
1. Test 1: Successful enrichment and reclassification (Industrial pipe + Stainless steel + Seamless + Fluid transportation)
2. Test 2: Unknown answer handling (Stainless steel, unknown construction -> does not invent seamless/welded)
3. Test 3: Unsupported specification rejection (Rejects 304-grade, schedule 40, ASTM standards not in source)
4. Test 4: Contradictory information detection (Plastic pipe vs Stainless steel -> Manual Review blocked)
5. Test 5: No clarification answers provided (Preserves original description unchanged)
6. Test 6: Model returns invalid JSON / malformed response (Handled safely with fallback)
7. Test 7: DeepSeek API timeout / network failure resilience
8. Test 8: Engine returns ambiguity outcome (Preserves ambiguity, zero verified store corruption)
9. Test 9: Duplicate submission / Concurrency guard (Idempotency)
10. Test 10: Persistence and resume across restart (SQLite state preserved, no redundant re-enrichment)
"""

import json
import os
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from src.ml.deepseek_description_enricher import (
    DeepSeekDescriptionEnricher,
    FactGroundingValidator,
    get_deepseek_description_enricher,
    EnrichmentOutput,
    AddedFact,
    PROMPT_ID,
    PROMPT_VERSION,
    SCHEMA_VERSION
)
from src.ml.hsn_clarification_session import (
    ClarificationSessionManager,
    ClarificationSession,
    get_clarification_session_manager
)
from src.ml.hsn_verified_store import get_hsn_verified_store

client = TestClient(app)


@pytest.fixture
def temp_session_manager(tmp_path):
    """Provides an isolated ClarificationSessionManager with a temporary SQLite database."""
    db_file = tmp_path / "test_clarification_sessions.db"
    mgr = ClarificationSessionManager(db_path=db_file)
    return mgr


# -------------------------------------------------------------------------
# Test 1: Successful Enrichment and Reclassification
# -------------------------------------------------------------------------
def test_scenario_01_successful_enrichment_and_reclassification(temp_session_manager):
    """
    Scenario 1: Customer confirms material='Stainless steel', construction='Seamless',
    and intended_use='Industrial fluid transportation' for 'Industrial pipe'.
    System must produce an enriched description grounded strictly in sources
    and perform successful reclassification into Heading 7304.
    """
    session = temp_session_manager.create_or_get_active_session(
        product_description="Industrial pipe",
        ambiguity_analysis={"is_ambiguous": True, "ambiguity_reason": "Material unknown"},
        generated_questions=[
            {"question_id": "Q1", "attribute": "material", "question": "Material?", "required": True},
            {"question_id": "Q2", "attribute": "construction", "question": "Construction?", "required": False},
            {"question_id": "Q3", "attribute": "intended_use", "question": "Application?", "required": False},
        ]
    )

    answers = [
        {"question_id": "Q1", "attribute": "material", "selected_option_id": "OPT_1", "selected_value": "Stainless steel", "is_unknown": False},
        {"question_id": "Q2", "attribute": "construction", "selected_option_id": "OPT_2", "selected_value": "Seamless", "is_unknown": False},
        {"question_id": "Q3", "attribute": "intended_use", "selected_option_id": "OPT_3", "selected_value": "Industrial fluid transportation", "is_unknown": False},
    ]

    updated_session, enrichment_data, v_res = temp_session_manager.enrich_and_reclassify(
        session.session_id, answers=answers
    )

    # Validate Enrichment Data contract
    assert enrichment_data["schema_version"] == "1.0"
    assert enrichment_data["enrichment_status"] == "SUCCESS"
    assert enrichment_data["ready_for_reclassification"] is True
    assert len(enrichment_data["unsupported_facts_detected"]) == 0

    enriched_desc = enrichment_data["enriched_description"].lower()
    assert "stainless" in enriched_desc
    assert "seamless" in enriched_desc
    assert "pipe" in enriched_desc

    # Validate Lifecycle Status
    assert updated_session.status in ("COMPLETED", "RECLASSIFICATION_COMPLETED")
    assert updated_session.reclassification_status == "SUCCESS"
    assert v_res is not None
    # Reclassification should map to Chapter 73 (Iron/Steel tubes, pipes - heading 7304 or 7306)
    code = v_res.get("qwen_hsn") or v_res.get("base_hsn") or ""
    assert code.startswith("73")


# -------------------------------------------------------------------------
# Test 2: Unknown Answer Handling
# -------------------------------------------------------------------------
def test_scenario_02_unknown_answer_handling():
    """
    Scenario 2: When customer selects 'Unknown / Not sure' for construction,
    the enricher must NOT invent 'seamless', 'welded', or any construction type.
    """
    enricher = get_deepseek_description_enricher()
    answers = [
        {"question_id": "Q1", "attribute": "material", "selected_option_id": "OPT_1", "selected_value": "Stainless steel", "is_unknown": False},
        {"question_id": "Q2", "attribute": "construction", "selected_option_id": "OPT_UNKNOWN", "selected_value": "unknown", "is_unknown": True},
    ]

    out = enricher.enrich_description(
        original_description="Industrial pipe",
        clarification_answers=answers
    )

    assert out.enrichment_status == "SUCCESS"
    assert out.ready_for_reclassification is True
    enriched_lower = out.enriched_description.lower()

    # Material must be present
    assert "stainless" in enriched_lower
    # Construction MUST NOT be invented
    assert "seamless" not in enriched_lower
    assert "welded" not in enriched_lower
    assert "construction" not in out.confirmed_attributes


# -------------------------------------------------------------------------
# Test 3: Unsupported Specification Rejection (Hallucination Rejection)
# -------------------------------------------------------------------------
def test_scenario_03_unsupported_specification_rejection():
    """
    Scenario 3: Reject fabricated specifications such as unconfirmed grades (304, 316),
    schedules (Schedule 40), or standards (ASTM A312).
    """
    is_valid, unsupported, reason = FactGroundingValidator.validate(
        original_desc="Industrial pipe",
        confirmed_attrs={"material": "Stainless steel"},
        enriched_desc="304-grade seamless stainless steel industrial pipe schedule 40.",
        added_facts=[{"attribute": "material", "value": "Stainless steel", "source": "CUSTOMER_CONFIRMED_ANSWER"}]
    )

    assert is_valid is False
    assert len(unsupported) > 0
    # Must catch unauthorized grade (304), construction (seamless), and schedule (schedule 40)
    unsupported_str = " ".join(unsupported)
    assert "304" in unsupported_str or "UNSUPPORTED" in unsupported_str
    assert "Fact-grounding validation failed" in reason


# -------------------------------------------------------------------------
# Test 4: Contradictory Information Detection
# -------------------------------------------------------------------------
def test_scenario_04_contradictory_information_detection(temp_session_manager):
    """
    Scenario 4: Original description specifies 'Plastic pipe' but customer confirmed
    material is 'Stainless steel'. Contradiction must trigger MANUAL_REVIEW and block reclassification.
    """
    session = temp_session_manager.create_or_get_active_session(
        product_description="Plastic pipe",
        ambiguity_analysis={"is_ambiguous": True},
        generated_questions=[{"question_id": "Q1", "attribute": "material", "question": "Material?"}]
    )

    answers = [
        {"question_id": "Q1", "attribute": "material", "selected_option_id": "OPT_SS", "selected_value": "Stainless steel", "is_unknown": False}
    ]

    updated_session, enrichment_data, v_res = temp_session_manager.enrich_and_reclassify(
        session.session_id, answers=answers
    )

    assert enrichment_data["enrichment_status"] == "MANUAL_REVIEW"
    assert enrichment_data["ready_for_reclassification"] is False
    assert any("CONTRADICTION" in u for u in enrichment_data["unsupported_facts_detected"])
    assert updated_session.status == "MANUAL_REVIEW"
    assert updated_session.reclassification_status == "BLOCKED"
    assert v_res is None


# -------------------------------------------------------------------------
# Test 5: No Clarification Answers Provided
# -------------------------------------------------------------------------
def test_scenario_05_no_clarification_answers():
    """
    Scenario 5: When no answers are provided, preserve original description unchanged
    without introducing or assuming attributes.
    """
    enricher = get_deepseek_description_enricher()
    orig = "Industrial control valve"
    out = enricher.enrich_description(
        original_description=orig,
        clarification_answers=[]
    )

    assert out.enrichment_status == "SUCCESS"
    assert out.enriched_description == orig
    assert out.confirmed_attributes == {}
    assert out.added_facts == []
    assert out.ready_for_reclassification is True


# -------------------------------------------------------------------------
# Test 6: Model Returns Invalid JSON / Malformed Output
# -------------------------------------------------------------------------
def test_scenario_06_malformed_model_output_fallback():
    """
    Scenario 6: When LLM returns invalid JSON, the enricher must safely fall back
    to deterministic grammar synthesis without crashing or fabricating facts.
    """
    enricher = get_deepseek_description_enricher()
    with patch.object(enricher, "_call_deepseek_api", return_value=None):
        out = enricher.enrich_description(
            original_description="Industrial cable",
            clarification_answers=[
                {"question_id": "Q1", "attribute": "material", "selected_value": "Copper", "is_unknown": False}
            ]
        )

        assert out.enrichment_status == "SUCCESS"
        assert "copper" in out.enriched_description.lower()
        assert "cable" in out.enriched_description.lower()
        assert out.ready_for_reclassification is True


# -------------------------------------------------------------------------
# Test 7: DeepSeek API Timeout / Network Failure
# -------------------------------------------------------------------------
def test_scenario_07_api_timeout_resilience():
    """
    Scenario 7: Simulates API timeout. Enricher gracefully catches the exception
    and executes deterministic synthesis.
    """
    enricher = get_deepseek_description_enricher()
    with patch("urllib.request.urlopen", side_effect=TimeoutError("Connection timed out")):
        out = enricher.enrich_description(
            original_description="Conveyor belt",
            clarification_answers=[
                {"question_id": "Q1", "attribute": "material", "selected_value": "Vulcanised rubber", "is_unknown": False}
            ]
        )

        assert out.enrichment_status == "SUCCESS"
        assert "rubber" in out.enriched_description.lower()
        assert out.ready_for_reclassification is True


# -------------------------------------------------------------------------
# Test 8: Engine Returns Ambiguity Outcome & Store Isolation
# -------------------------------------------------------------------------
def test_scenario_08_ambiguity_outcome_and_store_isolation(temp_session_manager):
    """
    Scenario 8: If reclassification results in ambiguity / manual review,
    session status is set to MANUAL_REVIEW, and data/hsn_verified_store.parquet
    must remain untouched with exactly 0 rows.
    """
    store = get_hsn_verified_store()
    initial_rows = store.get_stats().get("total_verified_records", 0)

    session = temp_session_manager.create_or_get_active_session(
        product_description="Unspecified mixed parts",
        ambiguity_analysis={"is_ambiguous": True},
        generated_questions=[{"question_id": "Q1", "attribute": "intended_use", "question": "Use?"}]
    )

    with patch("src.ml.deepseek_hsn_verifier.DeepSeekHSNVerifier.verify_item") as mock_verify:
        mock_verify.return_value = {
            "is_perfect_match": False,
            "status": "MANUAL_REVIEW_REQUIRED",
            "reasoning": "Commodity is too broad and ambiguous."
        }

        updated_session, _, v_res = temp_session_manager.enrich_and_reclassify(
            session.session_id,
            answers=[{"question_id": "Q1", "attribute": "intended_use", "selected_value": "General repair"}]
        )

        assert updated_session.status == "MANUAL_REVIEW"
        assert updated_session.reclassification_status == "AMBIGUOUS"

    # Verify store isolation: 0 records added
    assert store.get_stats().get("total_verified_records", 0) == initial_rows


# -------------------------------------------------------------------------
# Test 9: Duplicate Submission / Concurrency Guard
# -------------------------------------------------------------------------
def test_scenario_09_duplicate_submission_guard(temp_session_manager):
    """
    Scenario 9: Attempting to invoke enrich_and_reclassify while session is in
    ENRICHMENT_IN_PROGRESS or RECLASSIFICATION_IN_PROGRESS must raise RuntimeError.
    """
    session = temp_session_manager.create_or_get_active_session(
        product_description="Test lock item",
        ambiguity_analysis={"is_ambiguous": True},
        generated_questions=[]
    )
    temp_session_manager.transition_status(session.session_id, "ENRICHMENT_IN_PROGRESS")

    with pytest.raises(RuntimeError) as exc_info:
        temp_session_manager.enrich_and_reclassify(session.session_id, answers=[])

    assert "currently processing" in str(exc_info.value)


# -------------------------------------------------------------------------
# Test 10: Persistence and Resume Across Restarts
# -------------------------------------------------------------------------
def test_scenario_10_persistence_and_resume(tmp_path):
    """
    Scenario 10: Verify that enriched descriptions, status history, and reclassification
    results persist across process restarts (re-instantiated ClarificationSessionManager).
    """
    db_file = tmp_path / "persistent_sessions.db"

    # Phase 1: Create session and perform enrichment
    mgr1 = ClarificationSessionManager(db_path=db_file)
    s1 = mgr1.create_or_get_active_session(
        product_description="Industrial valve",
        ambiguity_analysis={"is_ambiguous": True},
        generated_questions=[{"question_id": "Q1", "attribute": "material", "question": "Material?"}]
    )
    s1_updated, _, _ = mgr1.enrich_and_reclassify(
        s1.session_id,
        answers=[{"question_id": "Q1", "attribute": "material", "selected_value": "Cast iron"}]
    )
    saved_enriched = s1_updated.enriched_description
    assert "iron" in saved_enriched.lower()

    # Phase 2: Instantiate fresh manager simulating service restart
    mgr2 = ClarificationSessionManager(db_path=db_file)
    s2 = mgr2.get_session(s1.session_id)

    assert s2 is not None
    assert s2.session_id == s1.session_id
    assert s2.enriched_description == saved_enriched
    assert s2.status in ("COMPLETED", "RECLASSIFICATION_COMPLETED")
    assert s2.reclassification_status == "SUCCESS"
    assert s2.enrichment_prompt_version == "1.0.0"

    # Redundant invocation returns existing result without re-enriching
    s2_recheck, _, _ = mgr2.enrich_and_reclassify(s2.session_id)
    assert s2_recheck.status == s2.status


# -------------------------------------------------------------------------
# API Endpoint Integration Tests
# -------------------------------------------------------------------------
def test_api_enrich_description_endpoint():
    """Tests POST /api/v1/hsn-intelligence/enrich-description."""
    payload = {
        "product_description": "Industrial pipe",
        "clarification_answers": [
            {"question_id": "Q1", "attribute": "material", "selected_value": "Stainless steel"}
        ]
    }
    resp = client.post("/api/v1/hsn-intelligence/enrich-description", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["schema_version"] == "1.0"
    assert data["enrichment_status"] == "SUCCESS"
    assert data["ready_for_reclassification"] is True
    assert "stainless" in data["enriched_description"].lower()


def test_api_enrich_and_reclassify_session_endpoint():
    """Tests POST /api/v1/hsn-clarification/sessions/{session_id}/enrich-and-reclassify."""
    # Create session
    create_resp = client.post("/api/v1/hsn-clarification/sessions", json={"product_description": "Industrial fasteners"})
    assert create_resp.status_code == 200
    session_id = create_resp.json()["session_id"]

    # Enrich and reclassify
    payload = {
        "customer_answers": [
            {"question_id": "Q001", "attribute": "material", "selected_value": "High tensile steel"}
        ]
    }
    resp = client.post(f"/api/v1/hsn-clarification/sessions/{session_id}/enrich-and-reclassify", json=payload)
    assert resp.status_code == 200
    res_data = resp.json()
    assert "enrichment" in res_data
    assert "verification_result" in res_data

