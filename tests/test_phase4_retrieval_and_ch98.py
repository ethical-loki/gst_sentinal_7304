"""
tests/test_phase4_retrieval_and_ch98.py
======================================
Phase 4 tests for:
1. Chapter 98 special statutory import regime gating (9801 project imports, 9802-9805).
2. Heading-level permissive "any material" clauses (e.g. Heading 9404) not falsely contradicted.
3. Stage 1 chapter index full-chapter coverage without truncation + head-noun prioritization.
4. Leaf-first Stage 2 retrieval allocation (8-digit leaves prioritized over 4/6-digit headers).
"""

from src.ml.candidate_evidence_evaluator import (
    CONTRADICTED,
    build_candidate_profile,
    evaluate_candidate_evidence,
)
from src.ml.stage3_statutory_verifier import evaluate_statutory_notes
from src.nlp.product_intent_analyzer import analyze_product_intent
from src.nlp.stage1_chapter_analyzer import (
    build_canonical_stage1_result,
    identify_relevant_chapters,
    load_statutory_chapter_index,
)
from src.search.hybrid_retrieval import HybridHSNEngine


def test_chapter_98_special_regime_gate_blocks_ordinary_goods_and_allows_explicit_regime():
    # Ordinary industrial spare parts must NOT be matched to 9801 Project Imports
    intent_parts = analyze_product_intent("spare parts for industrial heat exchanger plant")
    rec_9801 = {
        "hsn_code": "98010030",
        "code_length": 8,
        "chapter_code": "98",
        "chapter_title": "Project imports; laboratory chemicals; passengers' baggage",
        "heading_4digit": "9801",
        "heading_4digit_desc": "ALL ITEMS OF MACHINERY, INSTRUMENTS, APPARATUS, SPARE PARTS IMPORTED FOR INITIAL SETTING UP",
        "subheading_6digit": "980100",
        "subheading_6digit_desc": "INDUSTRIAL PLANTS; IRRIGATION PROJECTS; POWER PROJECTS",
        "tariff_item_desc": "ALL ITEMS OF MACHINERY IMPORTED FOR INITIAL SETTING UP OF INDUSTRIAL PLANTS",
        "statutory_description": "PROJECT IMPORTS - INDUSTRIAL PLANTS",
        "article_keywords": "machinery, spare parts, plant",
        "material_keywords": "",
    }
    prof_9801 = build_candidate_profile(rec_9801, None)
    ev_parts = evaluate_candidate_evidence(intent_parts, prof_9801, "SAME_PRODUCT", 0.70)
    assert ev_parts.status == CONTRADICTED
    assert any("Chapter 98" in c for c in ev_parts.contradictions)

    # Statutory notes should also surface the CONDITIONAL CHAPTER_98_PROJECT_IMPORTS requirement
    notes_parts = evaluate_statutory_notes("98", intent_parts)
    assert any(
        ev.get("rule_id") == "CHAPTER_98_PROJECT_IMPORTS" and ev.get("effect") == "CONDITIONAL"
        for ev in notes_parts["note_evaluations"]
    )

    # Ordinary industrial chemical dryer must NOT match 9802 Laboratory Chemicals
    intent_chem = analyze_product_intent("industrial tray dryer for chemical processing")
    rec_9802 = {
        "hsn_code": "98020000",
        "code_length": 8,
        "chapter_code": "98",
        "chapter_title": "Project imports; laboratory chemicals; passengers' baggage",
        "heading_4digit": "9802",
        "heading_4digit_desc": "LABORATORY CHEMICALS",
        "subheading_6digit": "980200",
        "subheading_6digit_desc": "LABORATORY CHEMICALS",
        "tariff_item_desc": "LABORATORY CHEMICALS",
        "statutory_description": "LABORATORY CHEMICALS",
        "article_keywords": "chemicals",
        "material_keywords": "",
    }
    prof_9802 = build_candidate_profile(rec_9802, None)
    ev_chem = evaluate_candidate_evidence(intent_chem, prof_9802, "SAME_PRODUCT", 0.70)
    assert ev_chem.status == CONTRADICTED
    assert any("Chapter 98" in c for c in ev_chem.contradictions)

    # Explicit Project Imports declaration is NOT blocked by the Chapter 98 regime gate
    explicit_query = "all items of machinery imported for initial setting up under project imports regulations"
    intent_explicit = analyze_product_intent(explicit_query)
    ev_explicit = evaluate_candidate_evidence(intent_explicit, prof_9801, "SAME_PRODUCT", 0.90)
    assert not any("Chapter 98" in c for c in ev_explicit.contradictions)


def test_permissive_any_material_heading_does_not_false_contradict_cotton_comforter():
    intent = analyze_product_intent("quilted cotton filled bed comforter and pillow")
    rec_9404 = {
        "hsn_code": "94049099",
        "code_length": 8,
        "chapter_code": "94",
        "chapter_title": "Furniture; bedding, mattresses, mattress supports, cushions and similar stuffed furnishings",
        "heading_4digit": "9404",
        "heading_4digit_desc": (
            "MATTRESS SUPPORTS; ARTICLES OF BEDDING AND SIMILAR FURNISHING "
            "(FOR EXAMPLE, MATTRESSES, QUILTS, EIDERDOWNS, CUSHIONS, POUFFES AND PILLOWS) "
            "FITTED WITH SPRINGS OR STUFFED OR INTERNALLY FITTED WITH ANY MATERIAL "
            "OR OF CELLULAR RUBBER OR PLASTICS, WHETHER OR NOT COVERED"
        ),
        "subheading_6digit": "940490",
        "subheading_6digit_desc": "OTHER",
        "tariff_item_desc": "OTHER : OTHER",
        "statutory_description": "MATTRESS SUPPORTS; ARTICLES OF BEDDING ... STUFFED OR INTERNALLY FITTED WITH ANY MATERIAL ... : OTHER",
        "article_keywords": "bedding, quilts, pillows",
        "material_keywords": "cellular rubber, plastics",
    }
    prof = build_candidate_profile(rec_9404, None)
    ev = evaluate_candidate_evidence(intent, prof, "SAME_PRODUCT", 0.85)
    assert ev.status != CONTRADICTED
    assert ev.contradictions == []


def test_stage1_chapter_index_includes_full_chapter85_and_head_noun_prioritization():
    catalog = {c["chapter_code"]: c for c in load_statutory_chapter_index()}
    assert "85" in catalog
    assert "97" in catalog
    # Verify Chapter 85 rows beyond row 300 (e.g. 8525 terms) are indexed
    ch85_tokens = catalog["85"]["heading_tokens"] | catalog["85"]["article_tokens"]
    assert "transceiver" in ch85_tokens or "transmission" in ch85_tokens

    # Coffee/espresso brewing machine must prioritize machinery chapter 84 over food chapters
    intent_coffee = analyze_product_intent("commercial espresso coffee brewing machine")
    assert intent_coffee.product_head_noun == "machine"
    chapters = identify_relevant_chapters(intent_coffee, top_k=5)
    ch_codes = [c["chapter_code"] for c in chapters]
    assert "84" in ch_codes[:2]


def test_hybrid_retrieval_leaf_first_and_recovered_phase4_targets():
    engine = HybridHSNEngine.get_instance()
    assert len(engine._leaf_indices) >= 14000
    assert all(
        len(str(engine.records[int(i)].get("hsn_code") or "").strip()) == 8
        for i in engine._leaf_indices[:200]
    )

    # Recovered benchmark recall targets under default initial branch_k=70
    for query, expected_hsn in (
        ("knitted viscose artificial fibre women top", "61143020"),
        ("spare parts for industrial heat exchanger plant", "84199010"),
        ("network ethernet router and packet switch", "85176270"),
        ("quilted cotton filled bed comforter and pillow", "94049099"),
    ):
        s1 = build_canonical_stage1_result(query)
        rows = engine.retrieve_with_lineage(query, branch_k=70, stage1_result=s1)
        hsn_list = [str(r.get("hsn_code") or "").strip() for r in rows]
        assert expected_hsn in hsn_list, f"{expected_hsn} missing from Stage 2 pool for '{query}'"
