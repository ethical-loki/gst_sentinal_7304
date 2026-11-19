import re
from pathlib import Path

from src.ml.candidate_evidence_evaluator import (
    CONTRADICTED,
    INSUFFICIENT_EVIDENCE,
    POSSIBLY_SUPPORTED,
    SUPPORTED,
    build_candidate_profile,
    evaluate_candidate_evidence,
)
from src.ml.multi_candidate_engine import MultiCandidateEngine
from src.nlp.product_intent_analyzer import analyze_product_intent


ROOT = Path(__file__).resolve().parent.parent


def test_modifier_or_material_overlap_without_head_noun_is_related_different_article():
    # Diagnostic generalization: modifier ("hexagonal") or material ("stainless steel") alone
    # must NOT establish article compatibility with a different primary article ("nut" vs "bolt").
    pi_bolt = analyze_product_intent("Stainless steel hexagonal bolts")
    nut_prof = build_candidate_profile(
        {
            "hsn_code": "73181600",
            "chapter_code": "73",
            "chapter_title": "ARTICLES OF IRON OR STEEL",
            "heading_4digit_desc": "SCREWS, BOLTS, NUTS, COACH-SCREWS, SCREW HOOKS, RIVETS, COTTERS, COTTER-PINS, WASHERS AND SIMILAR ARTICLES, OF IRON OR STEEL",
            "subheading_6digit_desc": "NUTS",
            "tariff_item_desc": "HEXAGONAL NUTS",
            "statutory_description": "HEXAGONAL NUTS OF STAINLESS STEEL",
            "article_keywords": "hexagonal nut, nut",
            "material_keywords": "stainless steel",
        },
        None,
    )
    # Remove 'bolt' from nut's article_tokens to simulate a pure nut leaf record
    nut_prof.article_tokens.discard("bolt")
    ev = evaluate_candidate_evidence(pi_bolt, nut_prof, "RELATED_PRODUCT", 0.65)
    assert ev.primary_article_matched is False
    assert ev.compatibility_level == "RELATED_DIFFERENT_ARTICLE"
    assert ev.status != SUPPORTED


def test_cross_chapter_different_articles_sharing_material_and_modifiers():
    pi_pump = analyze_product_intent("Stainless steel centrifugal water pump")
    heater_prof = build_candidate_profile(
        {
            "hsn_code": "84191910",
            "chapter_code": "84",
            "chapter_title": "NUCLEAR REACTORS, BOILERS, MACHINERY",
            "heading_4digit_desc": "MACHINERY, PLANT OR LABORATORY EQUIPMENT; INSTANTANEOUS OR STORAGE WATER HEATERS",
            "subheading_6digit_desc": "WATER HEATERS",
            "tariff_item_desc": "STORAGE WATER HEATERS",
            "statutory_description": "INSTANTANEOUS OR STORAGE WATER HEATERS OF STAINLESS STEEL",
            "article_keywords": "water heater",
            "material_keywords": "stainless steel",
        },
        None,
    )
    ev = evaluate_candidate_evidence(pi_pump, heater_prof, "RELATED_PRODUCT", 0.55)
    assert ev.primary_article_matched is False
    assert ev.compatibility_level == "RELATED_DIFFERENT_ARTICLE"
    assert ev.status == INSUFFICIENT_EVIDENCE


def test_direct_compatibility_missing_attr_and_explicit_contradiction():
    pi_shirt = analyze_product_intent("Men knitted 100% cotton t-shirt")
    direct_prof = build_candidate_profile(
        {
            "hsn_code": "61091000",
            "chapter_code": "61",
            "chapter_title": "ARTICLES OF APPAREL AND CLOTHING ACCESSORIES, KNITTED OR CROCHETED",
            "heading_4digit_desc": "T-SHIRTS, SINGLETS AND OTHER VESTS, KNITTED OR CROCHETED",
            "subheading_6digit_desc": "OF COTTON",
            "tariff_item_desc": "OF COTTON",
            "statutory_description": "T-SHIRTS, SINGLETS AND OTHER VESTS, KNITTED OR CROCHETED - OF COTTON",
        },
        None,
    )
    ev_direct = evaluate_candidate_evidence(pi_shirt, direct_prof, "SAME_PRODUCT", 0.90)
    assert ev_direct.primary_article_matched is True
    assert ev_direct.compatibility_level == "DIRECT_COMPATIBILITY"
    assert ev_direct.status == SUPPORTED

    # Conflicting construction (woven vs knitted) -> EXPLICIT_CONTRADICTION
    woven_prof = build_candidate_profile(
        {
            "hsn_code": "62052000",
            "chapter_code": "62",
            "chapter_title": "ARTICLES OF APPAREL, NOT KNITTED OR CROCHETED",
            "heading_4digit_desc": "MEN'S OR BOYS' SHIRTS, WOVEN",
            "subheading_6digit_desc": "OF COTTON",
            "tariff_item_desc": "OF COTTON",
            "statutory_description": "MEN'S OR BOYS' SHIRTS, NOT KNITTED OR CROCHETED - OF COTTON",
        },
        None,
    )
    ev_contra = evaluate_candidate_evidence(pi_shirt, woven_prof, "SAME_PRODUCT", 0.85)
    assert ev_contra.compatibility_level == "EXPLICIT_CONTRADICTION"
    assert ev_contra.status == CONTRADICTED

    # Missing material -> NOT contradicted, PARTIAL_COMPATIBILITY
    pi_unstated = analyze_product_intent("Knitted t-shirt")
    ev_missing = evaluate_candidate_evidence(pi_unstated, direct_prof, "SAME_PRODUCT", 0.80)
    assert ev_missing.status in {POSSIBLY_SUPPORTED, SUPPORTED}
    assert ev_missing.compatibility_level != "EXPLICIT_CONTRADICTION"


def test_no_hardcoded_hsn_rules_in_candidate_evidence_evaluator():
    src = (ROOT / "src" / "ml" / "candidate_evidence_evaluator.py").read_text(encoding="utf-8")
    assert not re.search(r"['\"]\d{8}['\"]", src)


def test_parts_role_alignment_for_spare_parts_queries():
    pi_parts = analyze_product_intent("spare parts for industrial air compressor")
    parts_prof = build_candidate_profile(
        {
            "hsn_code": "84149019",
            "chapter_code": "84",
            "chapter_title": "NUCLEAR REACTORS, BOILERS, MACHINERY",
            "heading_4digit_desc": "AIR OR VACUUM PUMPS, AIR OR OTHER GAS COMPRESSORS AND FANS",
            "subheading_6digit_desc": "PARTS",
            "tariff_item_desc": "OTHER",
            "statutory_description": "AIR OR OTHER GAS COMPRESSORS - PARTS : OTHER",
        },
        None,
    )
    ev = evaluate_candidate_evidence(pi_parts, parts_prof, "RELATED_PRODUCT", 0.70)
    assert ev.primary_article_matched is True
    assert ev.status == POSSIBLY_SUPPORTED
    assert ev.compatibility_level == "PARTIAL_COMPATIBILITY"


def test_hierarchy_qualifying_leaf_inherits_parent_article_identity():
    pi_sheet = analyze_product_intent("biaxially oriented polyester sheet for packaging")
    qual_sheet_prof = build_candidate_profile(
        {
            "hsn_code": "39206932",
            "chapter_code": "39",
            "chapter_title": "PLASTICS AND ARTICLES THEREOF",
            "heading_4digit_desc": "OTHER PLATES, SHEETS, FILM, FOIL AND STRIP, OF PLASTICS",
            "subheading_6digit_desc": "OF OTHER POLYESTERS",
            "tariff_item_desc": "FLEXIBLE, PLAIN",
            "statutory_description": "OTHER PLATES, SHEETS, FILM, FOIL AND STRIP, OF PLASTICS - OF OTHER POLYESTERS: FLEXIBLE, PLAIN",
        },
        None,
    )
    ev_sheet = evaluate_candidate_evidence(pi_sheet, qual_sheet_prof, "SAME_PRODUCT", 0.85)
    assert ev_sheet.primary_article_matched is True
    assert ev_sheet.status in {SUPPORTED, POSSIBLY_SUPPORTED}

    pi_engine = analyze_product_intent("petrol spark-ignition motorcycle engine 150cc")
    qual_eng_prof = build_candidate_profile(
        {
            "hsn_code": "84073290",
            "chapter_code": "84",
            "chapter_title": "NUCLEAR REACTORS, BOILERS, MACHINERY",
            "heading_4digit_desc": "SPARK-IGNITION RECIPROCATING OR ROTARY INTERNAL COMBUSTION PISTON ENGINES",
            "subheading_6digit_desc": "OF A CYLINDER CAPACITY EXCEEDING 50 CC BUT NOT EXCEEDING 250 CC",
            "tariff_item_desc": "OTHER",
            "statutory_description": "SPARK-IGNITION RECIPROCATING INTERNAL COMBUSTION PISTON ENGINES - OF A CYLINDER CAPACITY EXCEEDING 50 CC BUT NOT EXCEEDING 250 CC: OTHER",
        },
        None,
    )
    ev_eng = evaluate_candidate_evidence(pi_engine, qual_eng_prof, "SAME_PRODUCT", 0.85)
    assert ev_eng.primary_article_matched is True
    assert ev_eng.status in {SUPPORTED, POSSIBLY_SUPPORTED}


def test_end_to_end_cross_chapter_compatibility_and_confidence_separation():
    engine = MultiCandidateEngine()
    for q in (
        "Stainless steel hexagonal bolts",
        "Centrifugal water pump 2HP stainless steel",
        "Ergonomic wooden office chair",
    ):
        res = engine.classify_adaptive(q, page=1, page_size=5)
        cands = res.get("candidates") or []
        assert len(cands) > 0
        c0 = cands[0]
        assert "compatibility_level" in c0["evidence_trace"]
        assert "primary_article_matched" in c0["evidence_trace"]
        # Final calibrated confidence is computed separately from raw RRF score
        assert res["stage3_decision"]["calibrated_confidence"] != c0.get("rrf_score")
