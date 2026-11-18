from pathlib import Path
import pytest


ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("rel_path", ["static/index.html", "frontend/index.html"])
def test_three_screen_sequential_ui_structure_and_state_machine(rel_path):
    html = (ROOT / rel_path).read_text(encoding="utf-8")

    # 1. Central state machine & all 8 required states
    for state_name in (
        "STAGE1_NOT_STARTED",
        "STAGE1_RUNNING",
        "STAGE1_COMPLETED",
        "STAGE2_RUNNING",
        "STAGE2_COMPLETED",
        "STAGE3_RUNNING",
        "STAGE3_COMPLETED",
        "WORKFLOW_ERROR",
    ):
        assert state_name in html, f"Missing state {state_name} in {rel_path}"

    # 2. Distinct screen tabs & single-screen isolation functions
    for token in (
        "1. Product Understanding",
        "2. HSN Discovery",
        "3. Statutory Verification",
        "window.hsnWorkflow",
        "window.syncWorkflowUI",
        "window.navigateToStageScreen",
        "window.onStage1InputChanged",
        "window.resetHsnWorkflow",
        "proceedToStage2Btn",
        "Proceed to Stage 2 – Discover HSN Candidates",
        "proceedToStage3Btn",
        "Proceed to Stage 3 – Statutory Verification",
        "window.renderStage3Screen",
        "stage3DecisionCard",
    ):
        assert token in html, f"Missing token '{token}' in {rel_path}"

    # 3. Stage 2 panel must live in Screen 2 (step2Body), NOT inside Screen 1 (step1Box)
    s1_start = html.index('id="step1Box"')
    s2_start = html.index('id="step2Box"')
    s3_start = html.index('id="step3Box"')
    s1_section = html[s1_start:s2_start]
    s2_section = html[s2_start:s3_start]
    assert 'id="adaptiveDiscoveryPanel"' not in s1_section
    assert 'id="adaptiveDiscoveryPanel"' in s2_section


def test_sequential_api_workflow_stainless_steel_hexagonal_bolts():
    from fastapi.testclient import TestClient
    from backend.main import app

    client = TestClient(app)

    # Screen 1: Stage 1 only
    r1 = client.post(
        "/api/v1/hsn-rag/step1-context-aggregator",
        json={"product": "Stainless steel hexagonal bolts"},
    )
    assert r1.status_code == 200
    d1 = r1.json()
    s1 = d1["stage1_result"]
    assert s1["primary_commercial_article"]
    assert len(s1["chapter_candidates"]) >= 1

    # Screen 2 -> Screen 3: Stage 2 receives Stage 1 structured result and produces candidates + Stage 3 decision
    r2 = client.post(
        "/api/v1/hsn-v2/classify-adaptive",
        json={
            "description": "Stainless steel hexagonal bolts",
            "stage1_result": s1,
            "page": 1,
            "page_size": 10,
        },
    )
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["stage1_handoff"]["received_stage1"] is True
    assert len(d2["candidates"]) > 0
    assert "stage2_retrieval_summary" in d2
    assert "stage3_decision" in d2
    assert d2["stage3_decision"]["decision_outcome"] in {
        "EXACT_CLASSIFICATION",
        "MULTIPLE_CANDIDATES",
        "CUSTOMER_CLARIFICATION_REQUIRED",
        "ABSTAIN",
    }
