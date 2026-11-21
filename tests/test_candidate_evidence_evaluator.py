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


def test_phase16_task3_household_vs_conveyance_and_generic_penalty():
    intent_storage = analyze_product_intent("plastic household food storage container with lid")
    rec_household = {
        "hsn_code": "39241090",
        "code_length": 8,
        "chapter_code": "39",
        "chapter_title": "Plastics and articles thereof",
        "heading_4digit_desc": "Tableware, kitchenware, other household articles and hygienic or toilet articles, of plastics",
        "statutory_description": "Tableware, kitchenware, other household articles of plastics - food storage container",
        "tariff_item_desc": "Other",
        "article_keywords": "food storage container, household container",
        "material_keywords": "plastics",
    }
    rec_conveyance = {
        "hsn_code": "39239090",
        "code_length": 8,
        "chapter_code": "39",
        "chapter_title": "Plastics and articles thereof",
        "heading_4digit_desc": "Articles for the conveyance or packing of goods, of plastics",
        "statutory_description": "Articles for the conveyance or packing of goods, of plastics - container",
        "tariff_item_desc": "Other",
        "article_keywords": "container",
        "material_keywords": "plastics",
    }
    ev_house = evaluate_candidate_evidence(intent_storage, build_candidate_profile(rec_household, None), "SAME_PRODUCT", 0.85)
    ev_conv = evaluate_candidate_evidence(intent_storage, build_candidate_profile(rec_conveyance, None), "SAME_PRODUCT", 0.85)
    assert ev_house.heading_compatible is True
    assert ev_house.evidence_score > ev_conv.evidence_score
    assert "role_mismatch=household_storage_vs_conveyance_packing" in ev_conv.trace_summary


def test_phase17_task1_complete_article_vs_parts_protection():
    intent_pump = analyze_product_intent("centrifugal water pump")
    rec_part = {
        "hsn_code": "84139120",
        "code_length": 8,
        "chapter_code": "84",
        "chapter_title": "Nuclear reactors, boilers, machinery and mechanical appliances; parts thereof",
        "heading_4digit_desc": "Pumps for liquids, whether or not fitted with a measuring device; liquid elevators",
        "subheading_6digit_desc": "PARTS",
        "tariff_item_desc": "OF CENTRIFUGAL PUMPS",
        "statutory_description": "PUMPS FOR LIQUIDS... - PARTS - OF CENTRIFUGAL PUMPS",
        "article_keywords": "centrifugal pump parts, impeller, pump casing",
        "material_keywords": "cast iron, steel",
    }
    rec_complete = {
        "hsn_code": "84137010",
        "code_length": 8,
        "chapter_code": "84",
        "chapter_title": "Nuclear reactors, boilers, machinery and mechanical appliances; parts thereof",
        "heading_4digit_desc": "Pumps for liquids, whether or not fitted with a measuring device; liquid elevators",
        "subheading_6digit_desc": "OTHER CENTRIFUGAL PUMPS",
        "tariff_item_desc": "PRIMARILY DESIGNED TO HANDLE WATER",
        "statutory_description": "PUMPS FOR LIQUIDS... - OTHER CENTRIFUGAL PUMPS - PRIMARILY DESIGNED TO HANDLE WATER",
        "article_keywords": "centrifugal water pump, water pump",
        "material_keywords": "cast iron, steel",
    }
    ev_part = evaluate_candidate_evidence(intent_pump, build_candidate_profile(rec_part, None), "SAME_PRODUCT", 0.90)
    ev_comp = evaluate_candidate_evidence(intent_pump, build_candidate_profile(rec_complete, None), "SAME_PRODUCT", 0.88)
    assert ev_part.role_mismatch == "complete_article_vs_parts"
    assert ev_part.status == POSSIBLY_SUPPORTED
    assert ev_comp.role_mismatch == ""
    assert ev_comp.evidence_score > ev_part.evidence_score

    # When the user explicitly asks for spare parts, parts-only tariff item is NOT penalized
    intent_spare = analyze_product_intent("spare impeller parts for centrifugal pump")
    ev_spare = evaluate_candidate_evidence(intent_spare, build_candidate_profile(rec_part, None), "SAME_PRODUCT", 0.90)
    assert ev_spare.role_mismatch == ""


def test_phase19_task1_synthetic_material_keywords_do_not_contradict():
    # Cases #82, #98, #99: synthetic material_keywords must NOT trigger CONTRADICTED when statutory text is material-neutral
    cases = [
        (
            "dual-driver wooden enclosure loudspeaker system",
            {
                "hsn_code": "85182290",
                "code_length": 8,
                "chapter_code": "85",
                "chapter_title": "Electrical machinery and equipment",
                "heading_4digit_desc": "Microphones and stands therefor; loudspeakers",
                "subheading_6digit_desc": "Multiple loudspeakers, mounted in the same enclosure",
                "tariff_item_desc": "OTHER",
                "statutory_description": "Multiple loudspeakers, mounted in the same enclosure - Other",
                "article_keywords": "loudspeaker, speaker system",
                "material_keywords": "copper, brass, plastics",
            },
        ),
        (
            "quilted cotton filled bed comforter and pillow",
            {
                "hsn_code": "94049099",
                "code_length": 8,
                "chapter_code": "94",
                "chapter_title": "Furniture; bedding, mattresses, cushions",
                "heading_4digit_desc": "Mattress supports; articles of bedding and similar furnishing",
                "subheading_6digit_desc": "OTHER",
                "tariff_item_desc": "OTHER",
                "statutory_description": "Articles of bedding and similar furnishing - Other",
                "article_keywords": "comforter, pillow, bedding",
                "material_keywords": "plastics, rubber, polyester",
            },
        ),
        (
            "decorative brass ceiling chandelier light fitting",
            {
                "hsn_code": "94051020",
                "code_length": 8,
                "chapter_code": "94",
                "chapter_title": "Furniture; lamps and lighting fittings",
                "heading_4digit_desc": "Lamps and lighting fittings including searchlights and spotlights",
                "subheading_6digit_desc": "Chandeliers and other electric ceiling or wall lighting fittings",
                "tariff_item_desc": "Chandeliers",
                "statutory_description": "Chandeliers and other electric ceiling lighting fittings",
                "article_keywords": "chandelier, ceiling light fitting",
                "material_keywords": "plastics",
            },
        ),
    ]
    for q, rec in cases:
        ev = evaluate_candidate_evidence(analyze_product_intent(q), build_candidate_profile(rec, None), "INSUFFICIENT_INFORMATION", 0.65)
        assert ev.status != CONTRADICTED, f"False CONTRADICTED on {q}: {ev.contradictions}"
        assert not ev.contradictions


def test_phase19_task4_statutory_spelling_normalization():
    # Case #73: "VACCUM CLEANERS" in statutory master must match "vacuum cleaner" at search/eval time
    intent_vac = analyze_product_intent("electric canister vacuum cleaner for home")
    rec_vac = {
        "hsn_code": "85086000",
        "code_length": 8,
        "chapter_code": "85",
        "chapter_title": "Electrical machinery",
        "heading_4digit_desc": "VACCUM CLEANERS",
        "subheading_6digit_desc": "",
        "tariff_item_desc": "OTHER VACCUM CLEANERS",
        "statutory_description": "VACCUM CLEANERS - OTHER VACCUM CLEANERS",
        "article_keywords": "vaccum cleaner",
        "material_keywords": "",
    }
    ev = evaluate_candidate_evidence(intent_vac, build_candidate_profile(rec_vac, None), "UNRELATED", 0.11)
    assert ev.heading_compatible is True
    assert ev.article_matches


def test_phase19_task2_and_task3_rescue_and_multiheading_safety(tmp_path):
    from src.ml.confidence_calibrator import CalibrationBundle, evaluate_decision_thresholds
    from src.training.feedback_collector import FeedbackCollector

    # Task 3: multi-heading tie with low distinction_confidence must NEVER emit EXACT_HSN (#4)
    bundle = CalibrationBundle(tau_abstain=0.45, tau_chapter=0.70, tau_exact_hsn=0.65)
    dec = evaluate_decision_thresholds(
        bundle=bundle,
        best_rel_conf=0.98,
        chap_conf=0.97,
        hsn_conf=0.69,
        has_same_product=True,
        n_same_leaves=2,
        n_unique_headings=2,
        winner_has_clear_evidence=True,
        distinction_confidence=0.0015,
    )
    assert dec.prediction_mode == "MULTIPLE_CANDIDATES"
    assert dec.requires_clarification is True

    # Task 2: Safe rescue of UNRELATED candidate with strong statutory article+heading match
    # without promoting c.relation to SAME_PRODUCT or status to SUPPORTED
    class _RescueHybrid:
        total_records = 1

        def _expand_abbreviated_query(self, q: str):
            return q.lower(), q.lower().split()

        def retrieve_with_lineage(self, raw_query: str, branch_k: int = 30):
            return [
                {
                    "hsn_code": "85086000",
                    "code_length": 8,
                    "chapter_code": "85",
                    "chapter_title": "Electrical machinery and equipment",
                    "heading_4digit_desc": "VACCUM CLEANERS",
                    "statutory_description": "VACCUM CLEANERS - OTHER VACCUM CLEANERS",
                    "tariff_item_desc": "OTHER VACCUM CLEANERS",
                    "article_keywords": "vacuum cleaner",
                    "material_keywords": "",
                    "source_record_id": "r_vac",
                    "retrieval_source": "bm25+dense",
                    "bm25_score": 1.0,
                    "vector_score": 0.9,
                    "rrf_score": 0.03,
                }
            ]

    class _UnrelatedClassifier:
        calibration_bundle = None
        reranker = MagicMock()

        def classify(self, product_intent: str, tariff_rows):
            return [
                ClassifiedTariffCandidate(
                    candidate=RerankedTariffCandidate(
                        hsn_code=tariff_rows[0]["hsn_code"],
                        chapter_code="85",
                        description=tariff_rows[0]["statutory_description"],
                        relevance_score=0.10,
                        raw_logit=-2.1,
                        heading_4digit_desc=tariff_rows[0]["heading_4digit_desc"],
                        tariff_item_desc=tariff_rows[0]["tariff_item_desc"],
                        article_keywords=tariff_rows[0]["article_keywords"],
                        chapter_title=tariff_rows[0]["chapter_title"],
                        tariff_level="LEAF_8DIGIT",
                    ),
                    relation=RelationLabel.UNRELATED,
                    confidence=0.10,
                    relevance_confidence=0.10,
                )
            ]

    stat = MagicMock()
    stat.compare_active_vs_statutory.return_value = StatutoryComparisonResult(
        query="electric canister vacuum cleaner",
        is_out_of_schedule=False,
        best_active_score=0.10,
        best_inactive_score=0.05,
        reason="Active",
    )
    eng = MultiCandidateEngine(
        hybrid_engine=_RescueHybrid(),
        relevance_classifier=_UnrelatedClassifier(),
        statutory_index=stat,
        feedback_collector=FeedbackCollector(feedback_dir=tmp_path),
    )
    res = eng.classify_adaptive("electric canister vacuum cleaner", page=1, page_size=10)
    assert res["evidence_summary"]["rescued_candidates_count"] == 1
    assert res["candidates"][0]["hsn_code"] == "85086000"
    assert res["candidates"][0]["relevance_category"] == "UNRELATED"
    assert res["candidates"][0]["evidence_status"] == POSSIBLY_SUPPORTED
    assert res["candidates"][0]["evidence_trace"]["rescued_by_statutory_evidence"] is True
    assert res["prediction_mode"] != "EXACT_HSN"


def test_phase20_task1_task2_task3_selective_rescue_case73_and_spare_parts(tmp_path):
    from src.search.hybrid_retrieval import HybridHSNEngine
    from src.training.feedback_collector import FeedbackCollector

    # 1. Spare-parts head preservation (Task 2)
    pi_spare = analyze_product_intent("spare parts for marine outboard engine")
    assert "marine outboard engine" in pi_spare.finished_article.lower()

    # 2. Case #73: 85091000 (SAME_PRODUCT) vs rescued 85086000 (UNRELATED, strong statutory match)
    # must NOT emit EXACT_HSN 85091000
    class _Case73Hybrid:
        total_records = 2

        def _expand_abbreviated_query(self, q: str):
            return q.lower(), q.lower().split()

        def retrieve_with_lineage(self, raw_query: str, branch_k: int = 30):
            return [
                {
                    "hsn_code": "85091000",
                    "code_length": 8,
                    "chapter_code": "85",
                    "chapter_title": "Electrical machinery",
                    "heading_4digit_desc": "ELECTRO-MECHANICAL DOMESTIC APPLIANCES",
                    "statutory_description": "CONTAINED ELECTRIC MOTOR VACUUM CLEANERS",
                    "tariff_item_desc": "CONTAINED ELECTRIC MOTOR VACUUM CLEANERS",
                    "article_keywords": "vacuum cleaner",
                    "material_keywords": "",
                    "source_record_id": "r1",
                    "retrieval_source": "bm25+dense",
                    "bm25_score": 1.0,
                    "vector_score": 0.9,
                    "rrf_score": 0.03,
                },
                {
                    "hsn_code": "85086000",
                    "code_length": 8,
                    "chapter_code": "85",
                    "chapter_title": "Electrical machinery",
                    "heading_4digit_desc": "VACCUM CLEANERS",
                    "statutory_description": "VACCUM CLEANERS - OTHER VACCUM CLEANERS",
                    "tariff_item_desc": "OTHER VACCUM CLEANERS",
                    "article_keywords": "vaccum cleaner",
                    "material_keywords": "",
                    "source_record_id": "r2",
                    "retrieval_source": "bm25",
                    "bm25_score": 0.8,
                    "vector_score": 0.7,
                    "rrf_score": 0.02,
                },
            ]

    class _Case73Classifier:
        calibration_bundle = None
        reranker = MagicMock()

        def classify(self, product_intent: str, tariff_rows):
            out = []
            for r in tariff_rows:
                is_8509 = r["hsn_code"] == "85091000"
                cand = RerankedTariffCandidate(
                    hsn_code=r["hsn_code"],
                    chapter_code="85",
                    description=r["statutory_description"],
                    relevance_score=0.90 if is_8509 else 0.11,
                    raw_logit=2.2 if is_8509 else -2.1,
                    heading_4digit_desc=r["heading_4digit_desc"],
                    tariff_item_desc=r["tariff_item_desc"],
                    article_keywords=r["article_keywords"],
                    chapter_title=r["chapter_title"],
                    tariff_level="LEAF_8DIGIT",
                )
                out.append(ClassifiedTariffCandidate(
                    candidate=cand,
                    relation=RelationLabel.SAME_PRODUCT if is_8509 else RelationLabel.UNRELATED,
                    confidence=0.90 if is_8509 else 0.11,
                    relevance_confidence=0.90 if is_8509 else 0.11,
                ))
            return out

    stat = MagicMock()
    stat.compare_active_vs_statutory.return_value = StatutoryComparisonResult(
        query="electric canister vacuum cleaner for home",
        is_out_of_schedule=False,
        best_active_score=0.90,
        best_inactive_score=0.05,
        reason="Active",
    )
    eng = MultiCandidateEngine(
        hybrid_engine=_Case73Hybrid(),
        relevance_classifier=_Case73Classifier(),
        statutory_index=stat,
        feedback_collector=FeedbackCollector(feedback_dir=tmp_path),
    )
    res = eng.classify_adaptive("electric canister vacuum cleaner for home", page=1, page_size=10)
    assert res["prediction_mode"] == "MULTIPLE_CANDIDATES"
    assert res["final_hsn"] is None
    assert "8508" in res["clarification"]["reason"]

    # 3. Task 3 / Stage 1 Task 8: Dynamic corpus-driven morphological prefix expansion
    # (without manually maintained commercial-to-statutory dictionaries)
    hyb_dummy = HybridHSNEngine.__new__(HybridHSNEngine)
    hyb_dummy._vocab_freq = {"auxiliary": 10, "machinery": 20}
    exp_q, exp_toks = hyb_dummy._expand_abbreviated_query("auxi. mach. parts")
    assert "auxiliary" in exp_toks and "machinery" in exp_toks


def test_phase3_negated_attribute_contradiction_and_extreme_logit_rescue_guard():
    """Verify generic non-<attr> negation contradicts positive <attr> statutory branch."""
    intent_noncirc = analyze_product_intent("non-circular rectangular hollow structural iron tube")
    rec_circ = {
        "hsn_code": "73063010",
        "code_length": 8,
        "chapter_code": "73",
        "chapter_title": "Articles of iron or steel",
        "heading_4digit_desc": "OTHER TUBES, PIPES AND HOLLOW PROFILES, OF IRON OR STEEL",
        "subheading_6digit_desc": "OTHER, WELDED, OF CIRCULAR CROSS-SECTION, OF IRON OR NON-ALLOY STEEL",
        "tariff_item_desc": "OF IRON",
        "statutory_description": "OTHER TUBES - OTHER, WELDED, OF CIRCULAR CROSS-SECTION: OF IRON",
        "article_keywords": "tube, pipe",
        "material_keywords": "iron",
    }
    ev_circ = evaluate_candidate_evidence(
        intent_noncirc, build_candidate_profile(rec_circ, None), "SAME_PRODUCT", 0.90
    )
    assert ev_circ.status == CONTRADICTED
    assert any("non-circular" in c.lower() for c in ev_circ.contradictions)
    assert ev_circ.compatibility_level == "EXPLICIT_CONTRADICTION"

    rec_noncirc = {
        **rec_circ,
        "hsn_code": "73066010",
        "subheading_6digit_desc": "OTHER, WELDED, OF NON-CIRCULAR CROSS-SECTION",
        "statutory_description": "OTHER TUBES - OTHER, WELDED, OF NON-CIRCULAR CROSS-SECTION: OF IRON",
    }
    ev_noncirc = evaluate_candidate_evidence(
        intent_noncirc, build_candidate_profile(rec_noncirc, None), "SAME_PRODUCT", 0.96
    )
    assert ev_noncirc.status == SUPPORTED
    assert not ev_noncirc.contradictions

    # Symmetric rigid vs flexible statutory form check (Ch 39)
    intent_flex = analyze_product_intent("flexible pvc tubing")
    rec_rigid = {
        "hsn_code": "39172310",
        "code_length": 8,
        "chapter_code": "39",
        "chapter_title": "Plastics and articles thereof",
        "heading_4digit_desc": "TUBES, PIPES AND HOSES, AND FITTINGS THEREFOR, OF PLASTICS - TUBES, PIPES AND HOSES, RIGID",
        "subheading_6digit_desc": "OF POLYMERS OF VINYL CHLORIDE",
        "tariff_item_desc": "SEAMLESS TUBES",
        "statutory_description": "TUBES, PIPES AND HOSES, RIGID : OF POLYMERS OF VINYL CHLORIDE",
        "article_keywords": "tubes, pipes",
        "material_keywords": "pvc",
    }
    ev_rigid = evaluate_candidate_evidence(
        intent_flex, build_candidate_profile(rec_rigid, None), "SAME_PRODUCT", 0.85
    )
    assert ev_rigid.status == CONTRADICTED
    assert any("rigid" in c.lower() for c in ev_rigid.contradictions)



