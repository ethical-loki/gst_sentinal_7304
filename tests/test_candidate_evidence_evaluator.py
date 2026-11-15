"""
tests/test_candidate_evidence_evaluator.py
==========================================
Tests for Dataset-Driven Universal HSN Candidate Profile & Evidence Evaluator.
"""

from pathlib import Path
from unittest.mock import MagicMock

from src.ml.candidate_evidence_evaluator import (
    CONTRADICTED,
    INSUFFICIENT_EVIDENCE,
    POSSIBLY_SUPPORTED,
    SUPPORTED,
    build_candidate_profile,
    consolidate_duplicate_records,
    evaluate_candidate_evidence,
)
from src.ml.multi_candidate_engine import MultiCandidateEngine
from src.ml.product_tariff_reranker import RerankedTariffCandidate
from src.ml.relevance_classifier import ClassifiedTariffCandidate, RelationLabel
from src.nlp.product_intent_analyzer import analyze_product_intent
from src.search.statutory_master_index import StatutoryComparisonResult


def test_evidence_outcomes_and_unstated_material_never_rejected():
    # 1. SUPPORTED: stated material & article match
    intent_steel = analyze_product_intent("stainless steel screws")
    rec_steel = {
        "hsn_code": "73181500",
        "code_length": 8,
        "chapter_code": "73",
        "chapter_title": "Articles of iron or steel",
        "statutory_description": "Other screws and bolts, of iron or steel",
        "tariff_item_desc": "Other screws and bolts, of iron or steel",
        "article_keywords": "screws, bolts, fasteners",
        "material_keywords": "iron, steel, stainless steel",
    }
    prof_steel = build_candidate_profile(rec_steel, None)
    ev_steel = evaluate_candidate_evidence(intent_steel, prof_steel, "SAME_PRODUCT", 0.90)
    assert ev_steel.status == SUPPORTED
    assert "screws" in ev_steel.article_matches
    assert ev_steel.chapter_compatible is True

    # 2. CONTRADICTED: query explicitly states plastic, candidate is iron or steel
    intent_plastic = analyze_product_intent("plastic screws")
    ev_contra = evaluate_candidate_evidence(intent_plastic, prof_steel, "SAME_PRODUCT", 0.70)
    assert ev_contra.status == CONTRADICTED
    assert ev_contra.contradictions

    # 3. POSSIBLY_SUPPORTED (never rejected when material is unstated!)
    intent_unstated = analyze_product_intent("screws")
    ev_missing = evaluate_candidate_evidence(intent_unstated, prof_steel, "SAME_PRODUCT", 0.75)
    assert ev_missing.status == POSSIBLY_SUPPORTED
    assert ev_missing.missing_attributes
    assert not ev_missing.contradictions

    # 4. INSUFFICIENT_EVIDENCE: unrelated relation and no article/material overlap
    rec_other = {
        "hsn_code": "94036000",
        "code_length": 8,
        "chapter_code": "94",
        "chapter_title": "Furniture",
        "statutory_description": "Other wooden furniture",
        "tariff_item_desc": "Other wooden furniture",
        "article_keywords": "furniture, cabinets",
        "material_keywords": "wood",
    }
    prof_other = build_candidate_profile(rec_other, None)
    ev_insuff = evaluate_candidate_evidence(intent_unstated, prof_other, "INSUFFICIENT_INFORMATION", 0.42)
    assert ev_insuff.status == INSUFFICIENT_EVIDENCE


def test_consolidate_preserves_distinct_8digit_hsns():
    c1 = ClassifiedTariffCandidate(
        candidate=RerankedTariffCandidate("84137010", "84", "Centrifugal pumps", 0.9, 2.0),
        relation=RelationLabel.SAME_PRODUCT,
        confidence=0.9,
    )
    c1_dup = ClassifiedTariffCandidate(
        candidate=RerankedTariffCandidate("84137010", "84", "Centrifugal pumps", 0.88, 1.9),
        relation=RelationLabel.SAME_PRODUCT,
        confidence=0.88,
    )
    c2 = ClassifiedTariffCandidate(
        candidate=RerankedTariffCandidate("84137099", "84", "Other centrifugal pumps", 0.85, 1.7),
        relation=RelationLabel.SAME_PRODUCT,
        confidence=0.85,
    )
    out = consolidate_duplicate_records([c1, c1_dup, c2])
    assert [x.candidate.hsn_code for x in out] == ["84137010", "84137099"]


def test_multi_candidate_engine_filters_contradicted_and_exposes_evidence_summary(tmp_path):
    from src.training.feedback_collector import FeedbackCollector

    class _Hybrid:
        total_records = 2

        def _expand_abbreviated_query(self, q: str):
            return q.lower(), q.lower().split()

        def retrieve_with_lineage(self, raw_query: str, branch_k: int = 30):
            return [
                {
                    "hsn_code": "39233090",
                    "code_length": 8,
                    "chapter_code": "39",
                    "chapter_title": "Plastics and articles thereof",
                    "statutory_description": "Carboys, bottles, flasks and similar articles of plastics",
                    "tariff_item_desc": "Other bottles of plastics",
                    "article_keywords": "bottles, flasks, containers",
                    "material_keywords": "plastics, polymer",
                    "source_record_id": "r1",
                    "retrieval_source": "bm25+dense",
                    "bm25_score": 1.0,
                    "vector_score": 0.9,
                    "rrf_score": 0.03,
                },
                {
                    "hsn_code": "73239390",
                    "code_length": 8,
                    "chapter_code": "73",
                    "chapter_title": "Articles of iron or steel",
                    "statutory_description": "Table, kitchen or other household articles of stainless steel",
                    "tariff_item_desc": "Other household articles of stainless steel",
                    "article_keywords": "bottles, household articles",
                    "material_keywords": "stainless steel, iron, steel",
                    "source_record_id": "r2",
                    "retrieval_source": "dense",
                    "bm25_score": 0.4,
                    "vector_score": 0.7,
                    "rrf_score": 0.01,
                },
            ]

    class _Classifier:
        calibration_bundle = None
        reranker = MagicMock()

        def classify(self, product_intent: str, tariff_rows):
            out = []
            for r in tariff_rows:
                cand = RerankedTariffCandidate(
                    hsn_code=r["hsn_code"],
                    chapter_code=r["chapter_code"],
                    description=r["statutory_description"],
                    relevance_score=0.88,
                    raw_logit=2.0,
                    article_keywords=r["article_keywords"],
                    material_keywords=r["material_keywords"],
                    chapter_title=r["chapter_title"],
                    tariff_level="LEAF_8DIGIT",
                )
                out.append(ClassifiedTariffCandidate(candidate=cand, relation=RelationLabel.SAME_PRODUCT, confidence=0.88, relevance_confidence=0.88))
            return out

    stat = MagicMock()
    stat.compare_active_vs_statutory.return_value = StatutoryComparisonResult(
        query="plastic water bottle",
        is_out_of_schedule=False,
        best_active_score=0.88,
        best_inactive_score=0.1,
        reason="Active",
    )
    eng = MultiCandidateEngine(
        hybrid_engine=_Hybrid(),
        relevance_classifier=_Classifier(),
        statutory_index=stat,
        feedback_collector=FeedbackCollector(feedback_dir=tmp_path),
    )
    res = eng.classify_adaptive("plastic water bottle", page=1, page_size=20)
    hsns = [c["hsn_code"] for c in res["candidates"]]
    assert "39233090" in hsns
    assert "73239390" not in hsns  # Stainless steel contradicted by explicit "plastic"
    assert res["evidence_summary"]["contradicted_filtered_count"] == 1
    assert res["evidence_summary"]["supported_count"] == 1
    assert res["candidates"][0]["evidence_status"] == SUPPORTED


def test_ui_renders_candidate_evidence_summary_and_status():
    for ui_rel in ("static/index.html", "frontend/index.html"):
        html = Path(ui_rel).read_text(encoding="utf-8")
        for token in (
            "evidence_summary",
            "evidence_status",
            "evidence_trace",
            "Contradicted Filtered",
            "insufficient_evidence_filtered_count",
            "Hierarchy Context",
        ):
            assert token in html, f"Missing '{token}' in {ui_rel}"


def test_phase14_generic_modifiers_construction_and_semantic_only_guard():
    # 1. Generic modifier ("women") must NOT match unrelated garment ("women's trousers" vs "women's suit")
    intent_suit = analyze_product_intent("women's suit")
    rec_trouser = {
        "hsn_code": "62046200",
        "code_length": 8,
        "chapter_code": "62",
        "chapter_title": "Articles of apparel and clothing accessories, not knitted or crocheted",
        "statutory_description": "Trousers, bib and brace overalls, breeches and shorts, of cotton",
        "tariff_item_desc": "Trousers of cotton",
        "article_keywords": "women's trousers, cotton pants",
        "material_keywords": "cotton",
    }
    prof_trouser = build_candidate_profile(rec_trouser, None)
    ev_trouser = evaluate_candidate_evidence(intent_suit, prof_trouser, "RELATED_PRODUCT", 0.72)
    assert not ev_trouser.article_matches
    # Semantic similarity alone without article/material evidence must stay INSUFFICIENT_EVIDENCE
    assert ev_trouser.status == INSUFFICIENT_EVIDENCE

    # 2. Knitted vs not-knitted construction contradiction
    intent_knit = analyze_product_intent("knitted cotton t-shirt for men")
    ev_woven = evaluate_candidate_evidence(intent_knit, prof_trouser, "SAME_PRODUCT", 0.80)
    assert ev_woven.status == CONTRADICTED
    assert any("Construction contradiction" in c for c in ev_woven.contradictions)

    # 3. No double-counting of the same article stem
    rec_tshirt = {
        "hsn_code": "61091000",
        "code_length": 8,
        "chapter_code": "61",
        "chapter_title": "Articles of apparel and clothing accessories, knitted or crocheted",
        "statutory_description": "T-shirts, singlets and other vests, knitted or crocheted, of cotton",
        "tariff_item_desc": "T-shirts, singlets and other vests, of cotton",
        "article_keywords": "t-shirt, t-shirts, cotton tee",
        "material_keywords": "cotton",
    }
    prof_tshirt = build_candidate_profile(rec_tshirt, None)
    ev_knit = evaluate_candidate_evidence(intent_knit, prof_tshirt, "SAME_PRODUCT", 0.90)
    assert ev_knit.status == SUPPORTED
    assert len(ev_knit.article_matches) == 1


def test_phase14_parent_records_excluded_from_customer_facing_leaves(tmp_path):
    from src.training.feedback_collector import FeedbackCollector

    class _LeafAndParentHybrid:
        total_records = 2

        def _expand_abbreviated_query(self, q: str):
            return q.lower(), q.lower().split()

        def retrieve_with_lineage(self, raw_query: str, branch_k: int = 30):
            return [
                {
                    "hsn_code": "8413",
                    "code_length": 4,
                    "chapter_code": "84",
                    "chapter_title": "Nuclear reactors, boilers, machinery",
                    "statutory_description": "Pumps for liquids",
                    "tariff_item_desc": "Pumps for liquids",
                    "article_keywords": "liquid pumps",
                    "material_keywords": "",
                    "source_record_id": "p4",
                    "retrieval_source": "bm25",
                    "bm25_score": 1.0,
                    "vector_score": 0.9,
                    "rrf_score": 0.03,
                },
                {
                    "hsn_code": "84137010",
                    "code_length": 8,
                    "chapter_code": "84",
                    "chapter_title": "Nuclear reactors, boilers, machinery",
                    "statutory_description": "Primarily designed to handle water: Centrifugal pumps",
                    "tariff_item_desc": "Centrifugal pumps for water",
                    "article_keywords": "centrifugal pumps, water pumps",
                    "material_keywords": "",
                    "source_record_id": "l8",
                    "retrieval_source": "bm25+dense",
                    "bm25_score": 0.95,
                    "vector_score": 0.92,
                    "rrf_score": 0.035,
                },
            ]

    class _LeafParentClassifier:
        calibration_bundle = None
        reranker = MagicMock()

        def classify(self, product_intent: str, tariff_rows):
            out = []
            for r in tariff_rows:
                cand = RerankedTariffCandidate(
                    hsn_code=r["hsn_code"],
                    chapter_code=r["chapter_code"],
                    description=r["statutory_description"],
                    relevance_score=0.90,
                    raw_logit=2.2,
                    article_keywords=r["article_keywords"],
                    material_keywords=r["material_keywords"],
                    chapter_title=r["chapter_title"],
                    tariff_level="HEADING_4DIGIT" if len(r["hsn_code"]) == 4 else "LEAF_8DIGIT",
                )
                out.append(ClassifiedTariffCandidate(candidate=cand, relation=RelationLabel.SAME_PRODUCT, confidence=0.90, relevance_confidence=0.90))
            return out

    stat = MagicMock()
    stat.compare_active_vs_statutory.return_value = StatutoryComparisonResult(
        query="centrifugal water pump",
        is_out_of_schedule=False,
        best_active_score=0.90,
        best_inactive_score=0.1,
        reason="Active",
    )
    eng = MultiCandidateEngine(
        hybrid_engine=_LeafAndParentHybrid(),
        relevance_classifier=_LeafParentClassifier(),
        statutory_index=stat,
        feedback_collector=FeedbackCollector(feedback_dir=tmp_path),
    )
    res = eng.classify_adaptive("centrifugal water pump", page=1, page_size=20)
    assert [c["hsn_code"] for c in res["candidates"]] == ["84137010"]
    assert res["evidence_summary"]["parent_records_excluded_count"] == 1
    assert "8413" in res["hierarchy_context"]["parent_codes"]


def test_phase14_whether_or_not_containing_is_not_treated_as_exclusion():
    intent_biscuit = analyze_product_intent("sweet biscuits containing cocoa")
    rec_biscuit = {
        "hsn_code": "19053100",
        "code_length": 8,
        "chapter_code": "19",
        "chapter_title": "Preparations of cereals, flour, starch or milk; pastrycooks products",
        "statutory_description": "Sweet biscuits, whether or not containing cocoa",
        "tariff_item_desc": "Sweet biscuits",
        "article_keywords": "sweet biscuits, biscuits",
        "material_keywords": "flour, sugar, cocoa",
    }
    prof = build_candidate_profile(rec_biscuit, None)
    ev = evaluate_candidate_evidence(intent_biscuit, prof, "SAME_PRODUCT", 0.90)
    assert ev.status != CONTRADICTED
    assert not ev.contradictions


def test_phase15_priority1_article_identity_protection():
    # 1. Material-only overlap without finished-article match must NOT become POSSIBLY_SUPPORTED
    intent_tshirt = analyze_product_intent("knitted cotton t-shirt for men")
    rec_socks = {
        "hsn_code": "61159500",
        "code_length": 8,
        "chapter_code": "61",
        "chapter_title": "Articles of apparel and clothing accessories, knitted or crocheted",
        "heading_4digit_desc": "Panty hose, tights, stockings, socks and other hosiery",
        "statutory_description": "Socks and hosiery of cotton, knitted or crocheted",
        "tariff_item_desc": "Of cotton",
        "article_keywords": "socks, hosiery, stockings",
        "material_keywords": "cotton",
    }
    prof_socks = build_candidate_profile(rec_socks, None)
    ev_socks = evaluate_candidate_evidence(intent_tshirt, prof_socks, "SAME_PRODUCT", 0.85)
    assert ev_socks.status == INSUFFICIENT_EVIDENCE
    assert "material_only_no_article" in ev_socks.trace_summary

    # 2. When article_keywords is empty, heading_4digit_desc provides article identity evidence
    rec_tshirt_other = {
        "hsn_code": "61091000",
        "code_length": 8,
        "chapter_code": "61",
        "chapter_title": "Articles of apparel and clothing accessories, knitted or crocheted",
        "heading_4digit_desc": "T-shirts, singlets and other vests, knitted or crocheted",
        "statutory_description": "Of cotton",
        "tariff_item_desc": "Of cotton",
        "article_keywords": "",
        "material_keywords": "cotton",
    }
    prof_tshirt = build_candidate_profile(rec_tshirt_other, None)
    ev_tshirt = evaluate_candidate_evidence(intent_tshirt, prof_tshirt, "SAME_PRODUCT", 0.90)
    assert ev_tshirt.status == SUPPORTED
    assert ev_tshirt.article_matches

    # 3. Pure material query (no article noun) is not rejected on missing article match
    intent_mat_only = analyze_product_intent("cotton")
    ev_mat_only = evaluate_candidate_evidence(intent_mat_only, prof_socks, "SAME_PRODUCT", 0.70)
    assert ev_mat_only.status == POSSIBLY_SUPPORTED


