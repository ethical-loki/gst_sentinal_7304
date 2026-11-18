from pathlib import Path
from types import SimpleNamespace

from src.ml.candidate_evidence_evaluator import (
    CONTRADICTED,
    build_candidate_profile,
    evaluate_candidate_evidence,
)
from src.ml.multi_candidate_engine import MultiCandidateEngine
from src.ml.stage3_statutory_verifier import (
    build_stage3_final_decision,
    chapter_to_wco_section,
    evaluate_gir_sequence,
    lookup_verified_gst_rate,
    verify_statutory_hierarchy,
)
from src.nlp.product_intent_analyzer import analyze_product_intent


ROOT = Path(__file__).resolve().parent.parent


def test_statutory_hierarchy_verification_rejects_parent_and_prefix_mismatch():
    assert "Section XVI" in chapter_to_wco_section("84")
    assert "Section XI" in chapter_to_wco_section("61")

    valid = verify_statutory_hierarchy(
        {
            "hsn_code": "84137010",
            "chapter_code": "84",
            "heading_4digit": "8413",
            "heading_4digit_desc": "PUMPS FOR LIQUIDS",
            "subheading_6digit": "841370",
            "subheading_6digit_desc": "OTHER CENTRIFUGAL PUMPS",
            "tariff_item_desc": "PRIMARILY DESIGNED TO HANDLE WATER",
            "statutory_description": "PUMPS FOR LIQUIDS - OTHER CENTRIFUGAL PUMPS: PRIMARILY DESIGNED TO HANDLE WATER",
        },
        None,
    )
    assert valid["hierarchy_valid"] is True
    assert valid["is_leaf_8digit"] is True

    parent_only = verify_statutory_hierarchy(
        {"hsn_code": "8413", "chapter_code": "84", "statutory_description": "PUMPS FOR LIQUIDS"},
        None,
    )
    assert parent_only["hierarchy_valid"] is False
    assert "Not an 8-digit tariff item leaf" in parent_only["issues"]

    mismatch = verify_statutory_hierarchy(
        {
            "hsn_code": "84137010",
            "chapter_code": "85",
            "statutory_description": "PUMPS",
        },
        None,
    )
    assert mismatch["hierarchy_valid"] is False
    assert "Parent-child code prefix mismatch" in mismatch["issues"]


def test_conditional_gir_sequence_applicability():
    pi_simple = analyze_product_intent("Stainless steel hex bolt")
    cand1 = SimpleNamespace(
        candidate=SimpleNamespace(hsn_code="73181500", chapter_code="73"),
    )
    gir1 = evaluate_gir_sequence(
        pi_simple,
        [cand1],
        {"73181500": {"statutory_article_matches": ["bolt"], "heading_compatible": True}},
        {},
        {"winner_has_clear_evidence": True},
    )
    rules1 = [s["rule"] for s in gir1["gir_reasoning"]]
    assert "GIR 1" in rules1
    assert "GIR 6" in rules1
    assert "GIR 3" not in rules1
    assert "GIR 5" not in rules1

    pi_complex = analyze_product_intent("Unassembled pump kit in fitted carrying case")
    cand2 = SimpleNamespace(
        candidate=SimpleNamespace(hsn_code="84137010", chapter_code="84"),
    )
    cand3 = SimpleNamespace(
        candidate=SimpleNamespace(hsn_code="85011019", chapter_code="85"),
    )
    gir2 = evaluate_gir_sequence(
        pi_complex,
        [cand2, cand3],
        {"84137010": {"statutory_article_matches": ["pump"], "heading_compatible": True}},
        {},
        {"winner_has_clear_evidence": False},
    )
    rules2 = [s["rule"] for s in gir2["gir_reasoning"]]
    assert {"GIR 1", "GIR 2", "GIR 3", "GIR 5", "GIR 6"} <= set(rules2)


def test_broad_parent_example_material_does_not_falsely_contradict_leaf():
    pi = analyze_product_intent("quilted cotton filled bed comforter and pillow")
    prof = build_candidate_profile(
        {
            "hsn_code": "94049099",
            "chapter_code": "94",
            "chapter_title": "FURNITURE; BEDDING, MATTRESSES",
            "heading_4digit_desc": "MATTRESS SUPPORTS; ARTICLES OF BEDDING (FOR EXAMPLE, MATTRESSES, QUILTS OR OF CELLULAR RUBBER OR PLASTICS, WHETHER OR NOT COVERED)",
            "subheading_6digit_desc": "OTHER",
            "tariff_item_desc": "OTHER",
            "statutory_description": "MATTRESS SUPPORTS; ARTICLES OF BEDDING (FOR EXAMPLE, MATTRESSES, QUILTS OR OF CELLULAR RUBBER OR PLASTICS, WHETHER OR NOT COVERED) - OTHER : OTHER",
        },
        None,
    )
    ev = evaluate_candidate_evidence(pi, prof, "INSUFFICIENT_INFORMATION", 0.70)
    assert ev.status != CONTRADICTED


def test_verified_gst_rate_lookup_and_stage3_outcomes():
    rate = lookup_verified_gst_rate("61091000")
    if rate is not None:
        assert rate["verified"] is True
        assert rate["effective_date"]

    assert lookup_verified_gst_rate("99999999") is None

    pi = analyze_product_intent("Cotton t-shirt")
    abstain_dec = build_stage3_final_decision(
        original_description="Cotton t-shirt",
        prediction_mode="INSUFFICIENT_INFORMATION",
        final_hsn=None,
        final_chapter=None,
        hsn_confidence=0.25,
        clarification_reason="Insufficient evidence.",
        product_intent=pi,
        qualifying_leaves=[],
        evidence_by_hsn={},
        raw_records_by_id={},
        dist_analysis={},
        questions=[],
        contradicted_reasons=[],
    )
    assert abstain_dec["decision_outcome"] == "ABSTAIN"
    assert abstain_dec["verified_gst_rate"] is None

    clar_dec = build_stage3_final_decision(
        original_description="Cotton t-shirt",
        prediction_mode="CHAPTER_ONLY_CLARIFY",
        final_hsn=None,
        final_chapter="61",
        hsn_confidence=0.65,
        clarification_reason="Need construction.",
        product_intent=pi,
        qualifying_leaves=[],
        evidence_by_hsn={},
        raw_records_by_id={},
        dist_analysis={},
        questions=[{"attribute": "construction", "question": "Knitted or woven?", "options": ["Knitted", "Woven"]}],
        contradicted_reasons=[],
    )
    assert clar_dec["decision_outcome"] == "CUSTOMER_CLARIFICATION_REQUIRED"


def test_end_to_end_classify_adaptive_exposes_stage3_decision_and_ui():
    engine = MultiCandidateEngine()
    res = engine.classify_adaptive("Stainless steel centrifugal water pump 2HP", page=1, page_size=5)
    assert "stage3_decision" in res
    s3 = res["stage3_decision"]
    assert s3["decision_outcome"] in {
        "EXACT_CLASSIFICATION",
        "MULTIPLE_CANDIDATES",
        "CUSTOMER_CLARIFICATION_REQUIRED",
        "ABSTAIN",
    }
    assert isinstance(s3["gir_reasoning"], list)
    assert len(s3["gir_reasoning"]) >= 1

    for rel in ("static/index.html", "frontend/index.html"):
        html = (ROOT / rel).read_text(encoding="utf-8")
        assert "stage3DecisionCard" in html
        assert "verified_gst_rate" in html
