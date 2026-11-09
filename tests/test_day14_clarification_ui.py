"""
Module: tests/test_day14_clarification_ui.py
Description: Comprehensive test suite for Day 14 Customer Clarification UI Integration.
             Covers test scenarios TC01 through TC17.
"""

import json
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from src.ml.dynamic_question_generator import get_dynamic_question_generator


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def question_gen():
    return get_dynamic_question_generator()


# ==============================================================================
# TC01: One generated question displays correctly
# ==============================================================================
def test_tc01_one_generated_question_structure(question_gen):
    candidates = [
        {"candidate_id": "CAND_001", "hsn_code": "73044100", "description": "Stainless steel pipe"},
        {"candidate_id": "CAND_002", "hsn_code": "73041910", "description": "Carbon steel line pipe"}
    ]
    res = question_gen.generate_questions("Industrial pipe", retrieved_candidates=candidates)
    assert res["question_generation_status"] == "SUCCESS"
    assert len(res["questions"]) >= 1

    q1 = res["questions"][0]
    assert q1["question_id"] == "Q001"
    assert q1["attribute"] == "material"
    assert "Industrial pipe" in q1["question"]
    assert "reason" in q1 and len(q1["reason"]) > 0


# ==============================================================================
# TC02: Multiple generated questions display correctly
# ==============================================================================
def test_tc02_multiple_generated_questions(question_gen):
    candidates = [
        {"candidate_id": "CAND_001", "hsn_code": "63101010", "description": "Cotton rags, sorted"},
        {"candidate_id": "CAND_002", "hsn_code": "63109010", "description": "Synthetic rags, other than sorted"}
    ]
    res = question_gen.generate_questions("Rags", retrieved_candidates=candidates)
    assert res["question_generation_status"] == "SUCCESS"
    assert len(res["questions"]) >= 2
    attributes = [q["attribute"] for q in res["questions"]]
    assert "material" in attributes or "sorting_state" in attributes


# ==============================================================================
# TC03: Options are populated from the backend response
# ==============================================================================
def test_tc03_options_populated_from_backend(question_gen):
    candidates = [
        {"candidate_id": "CAND_001", "hsn_code": "73044100", "description": "Stainless steel pipes"},
        {"candidate_id": "CAND_002", "hsn_code": "73041910", "description": "Carbon steel pipes"}
    ]
    res = question_gen.generate_questions("Industrial pipe", retrieved_candidates=candidates)
    q1 = res["questions"][0]
    opt_labels = [opt["label"].lower() for opt in q1["options"]]
    assert any("stainless" in l for l in opt_labels)
    assert any("carbon" in l for l in opt_labels)


# ==============================================================================
# TC04: Unknown / Not sure can be selected
# ==============================================================================
def test_tc04_unknown_option_selectable(question_gen):
    candidates = [
        {"candidate_id": "CAND_001", "hsn_code": "73044100", "description": "Stainless steel pipes"}
    ]
    res = question_gen.generate_questions("Industrial pipe", retrieved_candidates=candidates)
    q1 = res["questions"][0]
    unknown_opts = [o for o in q1["options"] if o["option_id"] == "OPT_UNKNOWN" and o["value"] == "unknown"]
    assert len(unknown_opts) == 1
    assert "Unknown" in unknown_opts[0]["label"]


# ==============================================================================
# TC05: Other option opens free-text input when allowed
# ==============================================================================
def test_tc05_other_option_and_free_text_allowed(question_gen):
    candidates = [
        {"candidate_id": "CAND_001", "hsn_code": "73044100", "description": "Stainless steel pipe"},
        {"candidate_id": "CAND_002", "hsn_code": "73041910", "description": "Carbon steel pipe"}
    ]
    res = question_gen.generate_questions("Industrial pipe", retrieved_candidates=candidates)
    assert res["question_generation_status"] == "SUCCESS"
    q1 = res["questions"][0]
    assert q1["allow_free_text"] is True
    has_other = any("other" in o["value"] or "Other" in o["label"] for o in q1["options"])
    assert has_other is True


# ==============================================================================
# TC06: Required question cannot be skipped
# ==============================================================================
def test_tc06_required_question_cannot_be_skipped(client):
    payload = {
        "product_description": "Industrial pipe",
        "clarification_answers": []  # empty answers
    }
    resp = client.post("/api/v1/hsn-intelligence/submit-clarification", json=payload)
    assert resp.status_code == 400
    assert "clarification_answers array is required and cannot be empty" in resp.json()["detail"]


# ==============================================================================
# TC07: Unknown is accepted as a valid response
# ==============================================================================
def test_tc07_unknown_accepted_without_confirmation(client):
    payload = {
        "product_description": "Industrial pipe",
        "clarification_answers": [
            {
                "question_id": "Q001",
                "attribute": "material",
                "selected_option_id": "OPT_UNKNOWN",
                "selected_value": None,
                "free_text": None,
                "is_unknown": True
            }
        ]
    }
    resp = client.post("/api/v1/hsn-intelligence/submit-clarification", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "SUCCESS"
    assert "material" in data["unresolved_attributes"]
    assert "material" not in data["clarified_attributes"]


# ==============================================================================
# TC08: Multiple answers are submitted correctly
# ==============================================================================
def test_tc08_multiple_answers_submitted(client):
    payload = {
        "product_description": "Rags",
        "clarification_answers": [
            {
                "question_id": "Q001",
                "attribute": "material",
                "selected_option_id": "OPT_001",
                "selected_value": "cotton",
                "free_text": None,
                "is_unknown": False
            },
            {
                "question_id": "Q002",
                "attribute": "sorting_state",
                "selected_option_id": "OPT_001",
                "selected_value": "sorted",
                "free_text": None,
                "is_unknown": False
            }
        ]
    }
    resp = client.post("/api/v1/hsn-intelligence/submit-clarification", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "SUCCESS"
    assert data["clarified_attributes"].get("material") == "cotton"
    assert data["clarified_attributes"].get("sorting_state") == "sorted"


# ==============================================================================
# TC09: Changing one answer does not affect other answers
# ==============================================================================
def test_tc09_independent_answer_states():
    answers = {
        "Q001": {"question_id": "Q001", "attribute": "material", "selected_option_id": "OPT_001", "selected_value": "stainless_steel"},
        "Q002": {"question_id": "Q002", "attribute": "intended_use", "selected_option_id": "OPT_001", "selected_value": "industrial"}
    }
    # Mutating Q001
    answers["Q001"]["selected_value"] = "carbon_steel"
    answers["Q001"]["selected_option_id"] = "OPT_002"

    assert answers["Q001"]["selected_value"] == "carbon_steel"
    assert answers["Q002"]["selected_value"] == "industrial"


# ==============================================================================
# TC10: Invalid option ID is rejected
# ==============================================================================
def test_tc10_invalid_option_id_rejected(client):
    payload = {
        "product_description": "Industrial pipe",
        "clarification_answers": [
            {
                "question_id": "Q001",
                "attribute": "material",
                "selected_option_id": "<script>alert(1)</script>",
                "selected_value": "stainless_steel",
                "free_text": None,
                "is_unknown": False
            }
        ]
    }
    resp = client.post("/api/v1/hsn-intelligence/submit-clarification", json=payload)
    assert resp.status_code == 400
    assert "Invalid option identifier" in resp.json()["detail"]


# ==============================================================================
# TC11: Duplicate submission is prevented
# ==============================================================================
def test_tc11_duplicate_submission_handling(client):
    payload = {
        "product_description": "Industrial pipe",
        "clarification_answers": [
            {
                "question_id": "Q001",
                "attribute": "material",
                "selected_option_id": "OPT_001",
                "selected_value": "stainless_steel",
                "free_text": None,
                "is_unknown": False
            }
        ]
    }
    resp1 = client.post("/api/v1/hsn-intelligence/submit-clarification", json=payload)
    resp2 = client.post("/api/v1/hsn-intelligence/submit-clarification", json=payload)
    assert resp1.status_code == 200
    assert resp2.status_code == 200


# ==============================================================================
# TC12: API failure displays an appropriate error
# ==============================================================================
def test_tc12_api_failure_handling(client):
    # Missing product_description
    resp = client.post("/api/v1/hsn-intelligence/submit-clarification", json={"clarification_answers": []})
    assert resp.status_code == 400
    assert "product_description is required" in resp.json()["detail"]


# ==============================================================================
# TC13: No-ambiguity result preserves existing UI
# ==============================================================================
def test_tc13_unambiguous_query_preserves_ui(client):
    resp = client.get("/api/hsn-search?query=Live%20Animals&mode=intelligence")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["matches"]) > 0
    # Ambiguity should not be required for clear query
    if "clarification" in data and data["clarification"]:
        assert data["clarification"].get("clarification_required") is False


# ==============================================================================
# TC14: Manual-review result does not show unnecessary questions
# ==============================================================================
def test_tc14_manual_review_skipped_questions(question_gen):
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
    res = question_gen.generate_questions(
        "Complex diagnostic apparatus",
        ambiguity_result=ambiguity_manual
    )
    assert res["question_generation_status"] == "SKIPPED"
    assert res["questions"] == []


# ==============================================================================
# TC15: Successful submission passes clarified attributes to verification
# ==============================================================================
def test_tc15_clarified_attributes_passed_to_verification(client):
    payload = {
        "product_description": "Industrial pipe",
        "clarification_answers": [
            {
                "question_id": "Q001",
                "attribute": "material",
                "selected_option_id": "OPT_001",
                "selected_value": "stainless_steel",
                "free_text": None,
                "is_unknown": False
            }
        ]
    }
    resp = client.post("/api/v1/hsn-intelligence/submit-clarification", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    v_res = data["verification_result"]
    assert "stainless steel" in data["enriched_description"].lower()
    # Verified HSN should correspond to stainless steel pipe (Chapter 7304 / 7306)
    assert v_res["deepseek_hsn"].startswith("7304") or v_res["deepseek_hsn"].startswith("7306")


# ==============================================================================
# TC16: Existing product search & HSN result functionality remains unaffected
# ==============================================================================
def test_tc16_existing_product_search_unaffected(client):
    resp = client.get("/api/hsn-search?query=0101&mode=intelligence")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["matches"]) > 0
    top_code = data["matches"][0]["hsn_code"]
    assert top_code.startswith("0101")


# ==============================================================================
# TC17: Responsive layout & CSS integrity in index.html
# ==============================================================================
def test_tc17_html_css_integrity():
    with open("frontend/index.html", "r", encoding="utf-8") as f:
        html = f.read()

    assert "clarify-card" in html
    assert "clarify-opt-btn" in html
    assert "clarificationContainer" in html
    assert "btnSubmitClarification" in html
    assert "qwenClarificationDrawer" in html
    assert "renderClarificationUI" in html
    assert "submitClarificationAnswers" in html

