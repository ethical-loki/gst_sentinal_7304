"""
Module: tests/test_hsn_clarification_session.py
Description: Comprehensive test suite for HSN Clarification Session Data Contract Schema v1.0.0,
             lifecycle statuses, persistence across restarts, and transition auditing.
"""

import os
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from src.ml.hsn_clarification_session import (
    ClarificationSessionManager,
    SCHEMA_VERSION,
    ALLOWED_STATUSES
)


@pytest.fixture
def temp_manager(tmp_path):
    db_file = tmp_path / "test_sessions.db"
    return ClarificationSessionManager(db_path=db_file)


@pytest.fixture
def client():
    return TestClient(app)


def test_session_contract_schema_version_1_0_0(temp_manager):
    """
    Validates that a newly created session strictly adheres to the
    HSN Clarification Session Data Contract Schema v1.0.0.
    """
    candidates = [
        {"candidate_id": "CAND_001", "hsn_code": "73044100", "description": "Stainless steel pipe"},
        {"candidate_id": "CAND_002", "hsn_code": "73041910", "description": "Carbon steel pipe"}
    ]
    session = temp_manager.create_or_get_active_session(
        product_description="Industrial pipe",
        retrieved_candidates=candidates
    )

    data = session.to_contract_dict()

    # Required top-level keys in Schema v1.0.0
    required_keys = [
        "session_id",
        "schema_version",
        "product_description",
        "ambiguity_analysis",
        "generated_questions",
        "customer_answers",
        "status",
        "created_at",
        "updated_at",
        "submitted_at"
    ]
    for k in required_keys:
        assert k in data, f"Missing required contract key: {k}"

    assert data["schema_version"] == "1.0.0"
    assert data["session_id"].startswith("CLAR-")
    assert data["product_description"] == "Industrial pipe"
    assert data["status"] == "IN_PROGRESS"
    assert data["submitted_at"] is None
    assert isinstance(data["ambiguity_analysis"], dict)
    assert isinstance(data["generated_questions"], list)
    assert len(data["generated_questions"]) > 0
    assert isinstance(data["customer_answers"], list)
    assert data["created_at"].endswith("Z")
    assert data["updated_at"].endswith("Z")


def test_prevent_duplicate_sessions(temp_manager):
    """
    Persistence requirement: Prevent duplicate sessions from being created unintentionally.
    """
    s1 = temp_manager.create_or_get_active_session("Industrial pipe")
    s2 = temp_manager.create_or_get_active_session("industrial pipe")

    assert s1.session_id == s2.session_id, "Manager should reuse active IN_PROGRESS session"


def test_record_answers_and_preserve_unknown(temp_manager):
    """
    Preserve every valid customer answer, preserve Unknown responses, maintain timestamps.
    """
    candidates = [
        {"candidate_id": "CAND_001", "hsn_code": "63101010", "description": "Cotton rags, sorted"},
        {"candidate_id": "CAND_002", "hsn_code": "63109010", "description": "Synthetic rags, other than sorted"}
    ]
    session = temp_manager.create_or_get_active_session("Rags", retrieved_candidates=candidates)

    answers = [
        {
            "question_id": "Q001",
            "selected_option_id": "OPT001",
            "selected_value": "cotton",
            "free_text": None,
            "is_unknown": False
        },
        {
            "question_id": "Q002",
            "selected_option_id": "OPT_UNKNOWN",
            "selected_value": None,
            "free_text": None,
            "is_unknown": True
        }
    ]

    updated_session = temp_manager.record_answers(session.session_id, answers)
    ans_list = updated_session.customer_answers
    assert len(ans_list) == 2

    # Verify cotton answer
    q1_ans = next(a for a in ans_list if a["question_id"] == "Q001")
    assert q1_ans["selected_value"] == "cotton"
    assert q1_ans["is_unknown"] is False
    assert "answered_at" in q1_ans

    # Verify Unknown preservation
    q2_ans = next(a for a in ans_list if a["question_id"] == "Q002")
    assert q2_ans["selected_option_id"] == "OPT_UNKNOWN"
    assert q2_ans["selected_value"] is None
    assert q2_ans["is_unknown"] is True
    assert "answered_at" in q2_ans


def test_lifecycle_status_transitions_not_completed_on_submit(temp_manager):
    """
    Mandatory rule: A session must not be marked COMPLETED merely because
    the customer submitted answers.
    Transitions: IN_PROGRESS -> SUBMITTED -> VERIFICATION_IN_PROGRESS -> COMPLETED.
    """
    candidates = [
        {"candidate_id": "CAND_001", "hsn_code": "73044100", "description": "Stainless steel pipe"},
        {"candidate_id": "CAND_002", "hsn_code": "73041910", "description": "Carbon steel pipe"}
    ]
    session = temp_manager.create_or_get_active_session("Industrial pipe", retrieved_candidates=candidates)
    assert session.status == "IN_PROGRESS"

    answers = [
        {
            "question_id": session.generated_questions[0]["question_id"],
            "selected_option_id": "OPT001",
            "selected_value": "stainless_steel",
            "free_text": None,
            "is_unknown": False
        }
    ]

    # Explicit SUBMITTED transition
    session = temp_manager.record_answers(session.session_id, answers)
    session = temp_manager.transition_status(session.session_id, "SUBMITTED", reason="Customer submitted answers")
    assert session.status == "SUBMITTED"
    assert session.status != "COMPLETED", "Must NOT be marked COMPLETED merely because customer submitted answers"
    assert session.submitted_at is not None

    # Verification transition
    session = temp_manager.transition_status(session.session_id, "VERIFICATION_IN_PROGRESS", reason="Processing verification")
    assert session.status == "VERIFICATION_IN_PROGRESS"

    # Completion transition
    session = temp_manager.transition_status(session.session_id, "COMPLETED", reason="Verification finished")
    assert session.status == "COMPLETED"


def test_persistence_across_manager_restarts(tmp_path):
    """
    Persistence requirement: Support session retrieval after application restart.
    """
    db_file = tmp_path / "persistent_sessions.db"

    # Instance 1: Create session & record answer
    candidates = [
        {"candidate_id": "CAND_001", "hsn_code": "73044100", "description": "Stainless steel pipe"},
        {"candidate_id": "CAND_002", "hsn_code": "73041910", "description": "Carbon steel pipe"}
    ]
    mgr1 = ClarificationSessionManager(db_path=db_file)
    s1 = mgr1.create_or_get_active_session("Industrial pipe", retrieved_candidates=candidates)
    q1_id = s1.generated_questions[0]["question_id"]
    mgr1.record_answers(s1.session_id, [{
        "question_id": q1_id,
        "selected_option_id": "OPT001",
        "selected_value": "stainless_steel",
        "free_text": None,
        "is_unknown": False
    }])
    mgr1.transition_status(s1.session_id, "SUBMITTED", reason="Customer submitted")

    # Instance 2: Simulate complete application restart with new manager instance
    mgr2 = ClarificationSessionManager(db_path=db_file)
    recovered = mgr2.get_session(s1.session_id)

    assert recovered is not None
    assert recovered.session_id == s1.session_id
    assert recovered.product_description == "Industrial pipe"
    assert recovered.status == "SUBMITTED"
    assert len(recovered.customer_answers) == 1
    assert recovered.customer_answers[0]["selected_value"] == "stainless_steel"
    assert recovered.submitted_at is not None


def test_status_history_audit_trail(temp_manager):
    """
    Maintain a clear status transition history or equivalent audit information.
    """
    session = temp_manager.create_or_get_active_session("Industrial pipe")
    temp_manager.transition_status(session.session_id, "SUBMITTED", reason="Answers submitted by user")
    temp_manager.transition_status(session.session_id, "VERIFICATION_IN_PROGRESS", reason="Calling DeepSeek")
    temp_manager.transition_status(session.session_id, "COMPLETED", reason="Verification passed")

    detailed = temp_manager.get_session(session.session_id).to_detail_dict()
    history = detailed["status_history"]

    assert len(history) >= 4
    statuses = [h["to_status"] for h in history]
    assert "IN_PROGRESS" in statuses
    assert "SUBMITTED" in statuses
    assert "VERIFICATION_IN_PROGRESS" in statuses
    assert "COMPLETED" in statuses
    for h in history:
        assert "timestamp" in h
        assert "reason" in h


def test_api_session_endpoints_lifecycle(client):
    """
    End-to-end integration test across API endpoints:
    1. POST /api/v1/hsn-clarification/sessions -> creates session
    2. GET /api/v1/hsn-clarification/sessions/{id} -> retrieves session contract
    3. POST /api/v1/hsn-clarification/sessions/{id}/submit -> submits & completes verification
    """
    # 1. Create session
    resp1 = client.post("/api/v1/hsn-clarification/sessions", json={
        "product_description": "Industrial pipe",
        "retrieved_candidates": [
            {"candidate_id": "CAND_001", "hsn_code": "73044100", "description": "Stainless steel pipe"},
            {"candidate_id": "CAND_002", "hsn_code": "73041910", "description": "Carbon steel pipe"}
        ]
    })
    assert resp1.status_code == 200
    s_data = resp1.json()
    assert s_data["schema_version"] == "1.0.0"
    assert s_data["status"] == "IN_PROGRESS"
    session_id = s_data["session_id"]
    q1 = s_data["generated_questions"][0]

    # 2. Retrieve session
    resp2 = client.get(f"/api/v1/hsn-clarification/sessions/{session_id}")
    assert resp2.status_code == 200
    assert resp2.json()["session_id"] == session_id

    # 3. Submit and verify
    submit_payload = {
        "customer_answers": [
            {
                "question_id": q1["question_id"],
                "selected_option_id": "OPT_001",
                "selected_value": "stainless_steel",
                "free_text": None,
                "is_unknown": False
            }
        ]
    }
    resp3 = client.post(f"/api/v1/hsn-clarification/sessions/{session_id}/submit", json=submit_payload)
    assert resp3.status_code == 200
    final_data = resp3.json()
    assert final_data["status"] in ("COMPLETED", "MANUAL_REVIEW")
    assert final_data["submitted_at"] is not None
    assert "verification_result" in final_data

