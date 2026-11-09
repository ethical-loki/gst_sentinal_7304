"""
Module: tests/test_clarification.py
Description: Comprehensive test suite for Dynamic Clarification Question Generator
             adhering to Schema Version 1.0.0 and all 12 Mandatory Rules.
"""

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from src.ml.dynamic_question_generator import (
    DynamicQuestionGenerator,
    get_dynamic_question_generator,
    SCHEMA_VERSION
)


@pytest.fixture
def generator():
    return get_dynamic_question_generator()


@pytest.fixture
def client():
    return TestClient(app)


def test_schema_compliance_industrial_pipe(generator):
    """
    Validates Dynamic Clarification Question Schema v1.0.0 for 'Industrial pipe'.
    Asserts all required fields, types, and grounded candidate options.
    """
    candidates = [
        {"candidate_id": "CAND_001", "hsn_code": "73044100", "description": "Seamless stainless steel pipes"},
        {"candidate_id": "CAND_002", "hsn_code": "73041910", "description": "Carbon steel line pipe for oil/gas"},
        {"candidate_id": "CAND_003", "hsn_code": "39172110", "description": "Tubes, pipes and hoses of plastics (PVC / polymer)"}
    ]
    res = generator.generate_questions("Industrial pipe", retrieved_candidates=candidates)

    assert res["schema_version"] == "1.0.0"
    assert res["question_generation_status"] == "SUCCESS"
    assert res["product_description"] == "Industrial pipe"
    assert isinstance(res["questions"], list)
    assert len(res["questions"]) > 0

    q = res["questions"][0]
    # Required keys in question contract
    assert "question_id" in q
    assert "attribute" in q
    assert "question" in q
    assert "reason" in q
    assert "affected_candidates" in q
    assert "options" in q
    assert "allow_free_text" in q
    assert "required" in q

    assert isinstance(q["allow_free_text"], bool)
    assert q["allow_free_text"] is True  # Mandatory Rule 9
    assert isinstance(q["required"], bool)
    assert q["required"] is True

    # Rule 2: Question relates to product description
    assert "pipe" in q["question"].lower()

    # Rule 3: Must explain why answer matters
    assert len(q["reason"]) > 10

    # Rule 4: Grounded options
    opt_values = [opt["value"] for opt in q["options"]]
    assert "stainless_steel" in opt_values or "carbon_steel" in opt_values or "plastic_pvc" in opt_values

    # Rule 5: Always include Unknown / Not sure
    has_unknown = any(
        opt["option_id"] == "OPT_UNKNOWN" and opt["value"] == "unknown" and "Unknown" in opt["label"]
        for opt in q["options"]
    )
    assert has_unknown is True


def test_schema_compliance_rags(generator):
    """
    Validates questions generated for 'Rags' distinguishing material and sorting state.
    """
    candidates = [
        {"candidate_id": "CAND_001", "hsn_code": "63101010", "description": "Cotton rags, sorted"},
        {"candidate_id": "CAND_002", "hsn_code": "63109010", "description": "Synthetic rags, other than sorted"}
    ]
    res = generator.generate_questions("Rags", retrieved_candidates=candidates)

    assert res["schema_version"] == "1.0.0"
    assert res["question_generation_status"] == "SUCCESS"
    assert len(res["questions"]) >= 1

    attributes = [q["attribute"] for q in res["questions"]]
    # Should clarify material or sorting state
    assert any(a in ("material", "sorting_state") for a in attributes)

    for q in res["questions"]:
        assert q["allow_free_text"] is True
        # Rule 5 check
        assert any(opt["value"] == "unknown" for opt in q["options"])


def test_rule_11_unambiguous_or_continue_verification_skipped(generator):
    """
    Rule 11: Do not generate questions if the analysis result is not ambiguous
    or can continue verification. Returns SKIPPED status and empty questions list.
    """
    ambiguity_clean = {
        "schema_version": "1.0.0",
        "is_ambiguous": False,
        "ambiguity_reason": "No material ambiguity detected.",
        "missing_attributes": [],
        "conflicting_facts": [],
        "unclear_terminology": [],
        "clarification_questions": [],
        "affected_candidates": [],
        "can_continue_verification": True,
        "recommended_action": "CONTINUE_VERIFICATION"
    }
    res = generator.generate_questions(
        "Industrial servo motor 5 HP",
        ambiguity_result=ambiguity_clean,
        retrieved_candidates=[]
    )

    assert res["schema_version"] == "1.0.0"
    assert res["question_generation_status"] == "SKIPPED"
    assert res["questions"] == []


def test_rule_11_manual_review_skipped(generator):
    """
    Rule 11: Do not generate questions if the analysis result requires MANUAL_REVIEW.
    """
    ambiguity_manual = {
        "schema_version": "1.0.0",
        "is_ambiguous": True,
        "ambiguity_reason": "Irreconcilable conflict across Chapters 84 and 90.",
        "missing_attributes": [],
        "conflicting_facts": ["Contradictory candidate headings"],
        "unclear_terminology": [],
        "clarification_questions": [],
        "affected_candidates": ["CAND_1", "CAND_2"],
        "can_continue_verification": False,
        "recommended_action": "MANUAL_REVIEW"
    }
    res = generator.generate_questions(
        "Complex diagnostic apparatus",
        ambiguity_result=ambiguity_manual,
        retrieved_candidates=[]
    )

    assert res["schema_version"] == "1.0.0"
    assert res["question_generation_status"] == "SKIPPED"
    assert res["questions"] == []


def test_rule_5_mandatory_unknown_option_always_present(generator):
    """
    Rule 5: Always include 'Unknown / Not sure' as the final choice.
    """
    candidates = [
        {"candidate_id": "CAND_001", "hsn_code": "85011011", "description": "Electric motors <= 750 W"},
        {"candidate_id": "CAND_002", "hsn_code": "85015290", "description": "Electric motors > 750 W but <= 75 kW"}
    ]
    res = generator.generate_questions("Industrial motor", retrieved_candidates=candidates)
    assert res["question_generation_status"] == "SUCCESS"
    for q in res["questions"]:
        unknown_opts = [
            opt for opt in q["options"]
            if opt["option_id"] == "OPT_UNKNOWN" or opt["value"] == "unknown"
        ]
        assert len(unknown_opts) == 1
        assert "Unknown" in unknown_opts[0]["label"]


def test_rule_7_no_duplicate_attributes(generator):
    """
    Rule 7: Avoid duplicate questions for the same attribute.
    """
    res = generator.generate_questions("Industrial pipe")
    attributes = [q["attribute"] for q in res["questions"]]
    assert len(attributes) == len(set(attributes)), "Duplicate attributes found in generated questions"


def test_rule_8_affected_candidates_grounded(generator):
    """
    Rule 8: Candidate IDs in questions must be grounded in actual candidates.
    """
    candidates = [
        {"candidate_id": "CAND_101", "hsn_code": "73041000", "description": "Steel pipe"},
        {"candidate_id": "CAND_102", "hsn_code": "39172000", "description": "PVC pipe"}
    ]
    res = generator.generate_questions("Industrial pipe", retrieved_candidates=candidates)
    for q in res["questions"]:
        for cid in q["affected_candidates"]:
            assert cid in ("CAND_101", "CAND_102")


def test_api_generate_questions_endpoint(client):
    """
    Validates POST /api/v1/hsn-intelligence/generate-questions endpoint.
    """
    payload = {
        "product_description": "Industrial pipe",
        "retrieved_candidates": [
            {"candidate_id": "CAND_001", "hsn_code": "73044100", "description": "Stainless steel pipe"},
            {"candidate_id": "CAND_002", "hsn_code": "73041910", "description": "Carbon steel pipe"}
        ]
    }
    response = client.post("/api/v1/hsn-intelligence/generate-questions", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["schema_version"] == "1.0.0"
    assert data["question_generation_status"] == "SUCCESS"
    assert data["product_description"] == "Industrial pipe"
    assert len(data["questions"]) > 0

    q = data["questions"][0]
    assert q["allow_free_text"] is True
    assert q["required"] is True
    assert any(opt["value"] == "unknown" for opt in q["options"])
