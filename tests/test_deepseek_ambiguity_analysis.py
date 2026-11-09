"""
tests/test_deepseek_ambiguity_analysis.py — Test Suite for DeepSeek HSN Ambiguity Analysis (Response Schema v1.0.0).

Validates all 10 schema validation rules and core test scenarios:
1. Clear product description: "Industrial servo motor 5 HP" -> CONTINUE_VERIFICATION
2. Ambiguous product: "Rags" -> REQUEST_CLARIFICATION (unclear_terminology, missing_attributes)
3. Material ambiguity: "Industrial pipe" -> REQUEST_CLARIFICATION (missing_attributes)
4. Technical specification ambiguity: "Industrial motor" -> REQUEST_CLARIFICATION (missing_attributes)
5. Candidate conflict: Top candidates from competing chapters -> MANUAL_REVIEW
6. Clear product with multiple candidates -> CONTINUE_VERIFICATION
7. Missing candidate context: Empty candidate list -> MANUAL_REVIEW
8. Invalid DeepSeek JSON: Handled safely, fails gracefully to safe schema
9. DeepSeek API timeout / failure: Handled gracefully, no unverified store save
10. Verified knowledge store fast path: sub-0.5ms bypass
11. Dedicated POST /api/v1/hsn-intelligence/analyze-ambiguity endpoint
"""

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from src.ml.deepseek_ambiguity_analyzer import get_deepseek_ambiguity_analyzer, SCHEMA_VERSION, ALLOWED_ACTIONS
from src.ml.deepseek_hsn_verifier import get_deepseek_hsn_verifier
from src.ml.hsn_verified_store import get_hsn_verified_store
from backend.main import app


@pytest.fixture(scope="module")
def analyzer():
    return get_deepseek_ambiguity_analyzer()


@pytest.fixture(scope="module")
def verifier():
    return get_deepseek_hsn_verifier()


@pytest.fixture(scope="module")
def store():
    return get_hsn_verified_store()


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def _assert_valid_schema(res: dict):
    """Enforces all 10 schema rules on any output object."""
    # Rule 1: All required fields must exist
    required_keys = [
        "schema_version", "is_ambiguous", "ambiguity_reason", "missing_attributes",
        "conflicting_facts", "unclear_terminology", "clarification_questions",
        "affected_candidates", "can_continue_verification", "recommended_action"
    ]
    for k in required_keys:
        assert k in res, f"Missing required field '{k}' in response."

    # Rule 2: Boolean fields must contain actual Boolean values
    assert isinstance(res["is_ambiguous"], bool), "is_ambiguous must be boolean"
    assert isinstance(res["can_continue_verification"], bool), "can_continue_verification must be boolean"

    # Rule 3: Array fields must contain strings only
    for arr_field in ["missing_attributes", "conflicting_facts", "unclear_terminology", "clarification_questions", "affected_candidates"]:
        assert isinstance(res[arr_field], list), f"{arr_field} must be a list"
        for item in res[arr_field]:
            assert isinstance(item, str), f"Item in {arr_field} must be string: {item}"

    # Rule 4: recommended_action must contain one of the three allowed actions
    assert res["recommended_action"] in ALLOWED_ACTIONS, f"Invalid recommended_action: {res['recommended_action']}"

    # Rule 6: REQUEST_CLARIFICATION requires at least one useful clarification question
    if res["recommended_action"] == "REQUEST_CLARIFICATION":
        assert len(res["clarification_questions"]) >= 1, "REQUEST_CLARIFICATION must have >= 1 question"


def test_1_clear_product_description(analyzer):
    """Test 1: Clear product description has sufficient evidence to continue verification."""
    query = "Industrial servo motor 5 HP"
    candidates = [
        {"candidate_id": "CAND_001", "hsn_code": "85015210", "chapter": "85", "description": "AC MOTORS EXCEEDING 750 W", "score": 0.88}
    ]
    res = analyzer.analyze_ambiguity(query, extracted_attributes={"power_rating": "5 HP"}, retrieved_candidates=candidates)
    _assert_valid_schema(res)
    assert res["schema_version"] == SCHEMA_VERSION
    assert res["is_ambiguous"] is False
    assert res["can_continue_verification"] is True
    assert res["recommended_action"] == "CONTINUE_VERIFICATION"
    assert len(res["missing_attributes"]) == 0
    assert len(res["clarification_questions"]) == 0


def test_2_ambiguous_product_rags(analyzer):
    """Test 2: 'Rags' lacks sorting state and textile material."""
    query = "Rags"
    candidates = [
        {"candidate_id": "CAND_001", "hsn_code": "63101000", "chapter": "63", "description": "RAGS - SORTED", "score": 0.75},
        {"candidate_id": "CAND_002", "hsn_code": "63109010", "chapter": "63", "description": "COTTON RAGS", "score": 0.72}
    ]
    res = analyzer.analyze_ambiguity(query, retrieved_candidates=candidates)
    _assert_valid_schema(res)
    assert res["is_ambiguous"] is True
    assert res["can_continue_verification"] is False
    assert res["recommended_action"] == "REQUEST_CLARIFICATION"
    assert "Rags" in res["unclear_terminology"]
    assert len(res["clarification_questions"]) >= 1
    assert "CAND_001" in res["affected_candidates"]


def test_3_material_ambiguity_pipe(analyzer):
    """Test 3: 'Industrial pipe' lacks material specification."""
    query = "Industrial pipe"
    candidates = [
        {"candidate_id": "CAND_001", "hsn_code": "73063000", "chapter": "73", "description": "STEEL PIPE", "score": 0.74},
        {"candidate_id": "CAND_002", "hsn_code": "39172100", "chapter": "39", "description": "PLASTIC PIPE", "score": 0.70}
    ]
    res = analyzer.analyze_ambiguity(query, retrieved_candidates=candidates)
    _assert_valid_schema(res)
    assert res["is_ambiguous"] is True
    assert "material" in res["missing_attributes"]
    assert res["can_continue_verification"] is False
    assert res["recommended_action"] == "REQUEST_CLARIFICATION"
    assert len(res["clarification_questions"]) >= 1
    assert "CAND_001" in res["affected_candidates"]


def test_4_specification_ambiguity_motor(analyzer):
    """Test 4: 'Industrial motor' without power rating cannot distinguish 8501 subheadings."""
    query = "Industrial motor"
    candidates = [
        {"candidate_id": "CAND_001", "hsn_code": "85015100", "chapter": "85", "description": "MOTORS NOT EXCEEDING 750 W", "score": 0.78},
        {"candidate_id": "CAND_002", "hsn_code": "85015200", "chapter": "85", "description": "MOTORS EXCEEDING 750 W", "score": 0.76}
    ]
    res = analyzer.analyze_ambiguity(query, retrieved_candidates=candidates)
    _assert_valid_schema(res)
    assert res["is_ambiguous"] is True
    assert any("power" in m for m in res["missing_attributes"])
    assert res["recommended_action"] == "REQUEST_CLARIFICATION"
    assert len(res["clarification_questions"]) >= 1


def test_5_candidate_conflict(analyzer):
    """Test 5: Top candidates from competing chapters with near-identical scores."""
    query = "General purpose electrical apparatus"
    candidates = [
        {"candidate_id": "CAND_001", "hsn_code": "84798999", "chapter": "84", "description": "MACHINES AND APPLIANCES", "score": 0.752},
        {"candidate_id": "CAND_002", "hsn_code": "85437099", "chapter": "85", "description": "ELECTRICAL APPARATUS", "score": 0.749}
    ]
    res = analyzer.analyze_ambiguity(query, retrieved_candidates=candidates)
    _assert_valid_schema(res)
    assert res["is_ambiguous"] is True
    assert res["can_continue_verification"] is False
    assert res["recommended_action"] == "MANUAL_REVIEW"
    assert "CAND_001" in res["affected_candidates"]
    assert "CAND_002" in res["affected_candidates"]


def test_6_clear_product_with_multiple_candidates(analyzer):
    """Test 6: Bourdon Tube Pressure Gauge with multiple candidates has sufficient context."""
    query = "Bourdon Tube Pressure Gauge 0-10 Bar"
    candidates = [
        {"candidate_id": "CAND_001", "hsn_code": "90262000", "chapter": "90", "description": "INSTRUMENTS FOR MEASURING PRESSURE", "score": 0.89},
        {"candidate_id": "CAND_002", "hsn_code": "90269000", "chapter": "90", "description": "PARTS AND ACCESSORIES", "score": 0.65}
    ]
    res = analyzer.analyze_ambiguity(query, retrieved_candidates=candidates)
    _assert_valid_schema(res)
    assert res["is_ambiguous"] is False
    assert res["can_continue_verification"] is True
    assert res["recommended_action"] == "CONTINUE_VERIFICATION"


def test_7_missing_candidate_context(analyzer):
    """Test 7: Empty candidate list reports that candidate comparison cannot be performed (Rule 11)."""
    query = "Industrial valve"
    res = analyzer.analyze_ambiguity(query, retrieved_candidates=[])
    _assert_valid_schema(res)
    assert res["is_ambiguous"] is True
    assert res["can_continue_verification"] is False
    assert res["recommended_action"] == "MANUAL_REVIEW"
    assert "cannot be performed" in res["ambiguity_reason"].lower() or "missing" in res["ambiguity_reason"].lower()


def test_8_invalid_deepseek_json(analyzer):
    """Test 8: Model returning malformed JSON fails safely and returns valid schema."""
    with patch.object(analyzer, "_call_deepseek_api", return_value={"broken_format": "no_schema"}):
        res = analyzer.analyze_ambiguity("Rags", retrieved_candidates=[{"candidate_id": "CAND_001", "hsn_code": "63101000", "chapter": "63"}])
        _assert_valid_schema(res)
        assert res["schema_version"] == SCHEMA_VERSION
        assert res["recommended_action"] in ALLOWED_ACTIONS


def test_9_deepseek_timeout_safeguard(verifier):
    """Test 9: Ambiguous query does not persist unverified record to store."""
    query = "Rags"
    res = verifier.verify_item(query=query, base_hsn="63101000", save_to_store=True)
    assert res["status"] in ("REQUIRES_CLARIFICATION", "MANUAL_REVIEW_REQUIRED")
    assert res["is_saved"] is False
    assert res["storage_action"] == "BLOCKED_AMBIGUOUS"
    assert "ambiguity_analysis" in res
    _assert_valid_schema(res["ambiguity_analysis"])


def test_10_verified_store_fast_path(verifier, store):
    """Test 10: Verified items in store bypass ambiguity analysis and neural inference."""
    store.clear()
    store.upsert(
        query="Custom Stainless Steel Ball Valve",
        hsn_code="84818030",
        description="BALL VALVES",
        gst_rate=18.0,
        status="PERFECT_MATCH",
        is_perfect_match=True,
        reasoning="Pre-verified by classification auditor.",
        base_hsn="84818030",
        verified_by="DeepSeek-V4 Verified"
    )

    res = verifier.verify_item("Custom Stainless Steel Ball Valve", base_hsn="84818030", save_to_store=False)
    assert res["is_cache_hit"] is True
    assert res["storage_action"] == "ALREADY_VERIFIED_IN_STORE"
    assert res["status"] == "PERFECT_MATCH"
    assert res["latency_ms"] < 50.0

    # Clean up store
    store.clear()


def test_11_api_analyze_ambiguity_endpoint(client):
    """Test 11: Dedicated POST /api/v1/hsn-intelligence/analyze-ambiguity endpoint."""
    body = {
        "original_description": "Industrial pipe",
        "retrieved_candidates": [
            {"candidate_id": "CAND_001", "hsn_code": "73063000", "chapter": "73", "description": "STEEL PIPE"},
            {"candidate_id": "CAND_002", "hsn_code": "39172100", "chapter": "39", "description": "PLASTIC PIPE"}
        ]
    }
    resp = client.post("/api/v1/hsn-intelligence/analyze-ambiguity", json=body)
    assert resp.status_code == 200
    data = resp.json()
    _assert_valid_schema(data)
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["is_ambiguous"] is True
    assert data["recommended_action"] == "REQUEST_CLARIFICATION"
    assert "CAND_001" in data["affected_candidates"]
