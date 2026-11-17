import json
from pathlib import Path
import pytest

from src.nlp.stage1_chapter_analyzer import (
    load_statutory_chapter_index,
    identify_relevant_chapters,
    build_canonical_stage1_result,
)
from src.nlp.product_intent_analyzer import analyze_product_intent
from src.search.hybrid_retrieval import HybridHSNEngine
from src.ml.multi_candidate_engine import MultiCandidateEngine


ROOT = Path(__file__).resolve().parent.parent


def test_official_chapter_catalog_loads_dynamically_from_master():
    catalog = {c["chapter_code"]: c["chapter_title"] for c in load_statutory_chapter_index()}
    assert len(catalog) >= 9
    for ch_code in ("84", "85", "73", "39", "61", "94"):
        assert ch_code in catalog
        assert len(catalog[ch_code].strip()) > 0


@pytest.mark.parametrize(
    "description,expected_chapters",
    [
        ("Variable Frequency Drive 5.5kW 3-phase AC motor speed controller", {"85", "84"}),
        ("Centrifugal water pump 2HP stainless steel impeller", {"84"}),
        ("Stainless steel hex bolt M10 fastener", {"73"}),
        ("Men knitted 100% cotton round neck t-shirt", {"61", "62"}),
        ("Ergonomic wooden office chair with adjustable armrests", {"94"}),
    ],
)
def test_canonical_stage1_result_and_dynamic_chapters(description, expected_chapters):
    s1 = build_canonical_stage1_result(description)
    # JSON serializable canonical contract
    encoded = json.dumps(s1)
    decoded = json.loads(encoded)

    assert decoded["original_description"] == description
    assert decoded["stage"] == "STAGE_1"
    assert "primary_commercial_article" in decoded
    assert "materials_and_composition" in decoded
    assert "components_and_relationships" in decoded
    assert "characteristics" in decoded
    assert "explicit_attributes" in decoded
    assert "missing_attributes" in decoded
    assert "stage2_search_representation" in decoded
    assert "chapter_candidates" in decoded

    assert decoded["primary_commercial_article"]
    assert decoded["article_category"]

    ch_cands = decoded["chapter_candidates"]
    assert len(ch_cands) >= 1
    returned_chapters = {c["chapter_code"] for c in ch_cands}
    assert returned_chapters & expected_chapters, (
        f"Expected one of {expected_chapters} in {returned_chapters} for '{description}'"
    )
    for c in ch_cands:
        assert c["chapter_title"]
        assert c["why_relevant"]
        assert 0.0 <= float(c["confidence"]) <= 1.0
        assert isinstance(c["supporting_attributes"], list)
        assert isinstance(c["limiting_or_contradictory_evidence"], list)


def test_stage2_hybrid_retrieval_consumes_stage1_and_preserves_cross_chapter():
    engine = HybridHSNEngine()
    desc = "Variable Frequency Drive 5.5kW 3-phase AC motor controller"
    s1 = build_canonical_stage1_result(desc)

    results = engine.retrieve_with_lineage(desc, branch_k=20, stage1_result=s1)
    assert len(results) > 0

    first = results[0]
    assert "chapter_guided" in first
    assert "cross_chapter_discovery" in first
    assert "cross_chapter_reason" in first
    assert "retrieval_explanation" in first
    assert any(r.get("chapter_guided") for r in results)


def test_classify_adaptive_handoff_and_explainability_fields():
    engine = MultiCandidateEngine()
    desc = "Centrifugal water pump 2HP stainless steel"
    s1 = build_canonical_stage1_result(desc)

    res = engine.classify_adaptive(desc, stage1_result=s1, page=1, page_size=5)
    assert res["stage1_handoff"]["received_stage1"] is True
    assert res["stage1_handoff"]["primary_commercial_article"]
    assert isinstance(res["stage1_handoff"]["guided_chapters"], list)

    cands = res.get("candidates") or []
    assert len(cands) > 0
    c0 = cands[0]
    for field in (
        "bm25_score",
        "vector_score",
        "rrf_score",
        "chapter_guided",
        "cross_chapter_discovery",
        "cross_chapter_reason",
        "retrieval_explanation",
        "heading_4digit_desc",
        "subheading_6digit_desc",
        "tariff_item_desc",
        "matching_attributes",
        "missing_attributes",
    ):
        assert field in c0, f"Missing Stage 2 explainability field '{field}'"


def test_api_stage1_and_stage2_handoff_endpoints():
    from fastapi.testclient import TestClient
    from backend.main import app

    client = TestClient(app)

    r1 = client.post(
        "/api/v1/hsn-rag/step1-context-aggregator",
        json={"product": "Stainless steel centrifugal water pump 2HP"},
    )
    assert r1.status_code == 200
    d1 = r1.json()
    assert "stage1_result" in d1
    s1 = d1["stage1_result"]
    assert s1["primary_commercial_article"]
    assert len(s1["chapter_candidates"]) >= 1

    # Invalid stage1_result must return 400
    r_bad = client.post(
        "/api/v1/hsn-v2/classify-adaptive",
        json={"description": "water pump", "stage1_result": "invalid"},
    )
    assert r_bad.status_code == 400

    # Valid one-click handoff passes structured stage1_result cleanly
    r2 = client.post(
        "/api/v1/hsn-v2/classify-adaptive",
        json={
            "description": "Stainless steel centrifugal water pump 2HP",
            "stage1_result": s1,
            "page": 1,
            "page_size": 5,
        },
    )
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["stage1_handoff"]["received_stage1"] is True
    assert len(d2["candidates"]) > 0


@pytest.mark.parametrize("rel_path", ["static/index.html", "frontend/index.html"])
def test_ui_has_one_click_stage1_to_stage2_handoff_and_explainability(rel_path):
    html = (ROOT / rel_path).read_text(encoding="utf-8")
    for token in (
        "proceedToStage2Btn",
        "Proceed to Stage 2 – Discover HSN Candidates",
        "window.proceedToStage2",
        "window._stage1StructuredResult",
        "stage1StructuredDetails",
        "Dynamic Chapter Candidates",
        "bm25_score",
        "vector_score",
        "rrf_score",
        "cross_chapter_reason",
        "heading_4digit_desc",
        "matching_attributes",
        "missing_attributes",
    ):
        assert token in html, f"Expected UI token '{token}' in {rel_path}"
