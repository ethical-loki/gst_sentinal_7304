"""
Unit tests for Phase 5: RelevanceClassifier and ModelDrivenAmbiguityResolver.
"""

from unittest.mock import MagicMock

from src.ml.ambiguity_resolver import (
    ModelDrivenAmbiguityResolver,
    identify_separating_attributes,
)
from src.ml.product_tariff_reranker import RerankedTariffCandidate
from src.ml.relevance_classifier import RelationLabel, RelevanceClassifier


def _make_cand(hsn: str, chapter: str, desc: str, score: float, mat: str = "") -> RerankedTariffCandidate:
    return RerankedTariffCandidate(
        hsn_code=hsn,
        chapter_code=chapter,
        description=desc,
        relevance_score=score,
        raw_logit=0.0,
        chapter_title=f"Chapter {chapter}",
        material_keywords=mat,
    )


def test_related_product_does_not_trigger_false_ambiguity():
    mock_reranker = MagicMock()
    mock_reranker.rerank.return_value = [
        _make_cand("39233090", "39", "Plastic water bottle", 0.91, "plastic, pet"),
        _make_cand("84223000", "84", "Bottle filling machinery", 0.28, "steel"),
    ]

    clf = RelevanceClassifier(
        reranker=mock_reranker, same_product_threshold=0.725, related_threshold=0.35
    )
    resolver = ModelDrivenAmbiguityResolver(classifier=clf)
    res = resolver.resolve("plastic water bottle", [{}, {}])

    assert res.status == "CLEAR"
    assert res.selected_hsn == "39233090"
    assert len(res.same_product_candidates) == 1
    assert len(res.related_product_candidates) == 1


def test_multiple_same_product_materials_trigger_genuine_ambiguity():
    mock_reranker = MagicMock()
    mock_reranker.rerank.return_value = [
        _make_cand("39233090", "39", "Bottles of plastics", 0.86, "plastic, hdpe"),
        _make_cand("73239390", "73", "Tableware and bottles of stainless steel", 0.82, "stainless steel"),
        _make_cand("84223000", "84", "Bottle washing machinery", 0.22, "cast iron"),
    ]

    clf = RelevanceClassifier(
        reranker=mock_reranker, same_product_threshold=0.725, related_threshold=0.35
    )
    resolver = ModelDrivenAmbiguityResolver(classifier=clf)
    res = resolver.resolve("water bottle", [{}, {}, {}])

    assert res.status == "AMBIGUOUS_MATERIAL"
    assert len(res.same_product_candidates) == 2
    assert len(res.related_product_candidates) == 1
    assert len(res.clarification_options) == 2


def test_insufficient_information_triggers_clarification():
    mock_reranker = MagicMock()
    mock_reranker.rerank.return_value = [
        _make_cand("39269099", "39", "Other articles of plastics", 0.52, "plastic"),
        _make_cand("73269099", "73", "Other articles of iron or steel", 0.48, "steel"),
    ]

    clf = RelevanceClassifier(
        reranker=mock_reranker, same_product_threshold=0.725, related_threshold=0.35
    )
    resolver = ModelDrivenAmbiguityResolver(classifier=clf)
    res = resolver.resolve("industrial bracket", [{}, {}])

    assert res.status == "INSUFFICIENT_INFORMATION"
    assert len(res.insufficient_info_candidates) == 2
    assert res.clarification_question is not None


def test_all_related_returns_no_relevant_match():
    mock_reranker = MagicMock()
    mock_reranker.rerank.return_value = [
        _make_cand("84223000", "84", "Packaging machinery", 0.15, "steel"),
    ]

    clf = RelevanceClassifier(
        reranker=mock_reranker, same_product_threshold=0.725, related_threshold=0.35
    )
    resolver = ModelDrivenAmbiguityResolver(classifier=clf)
    res = resolver.resolve("fresh roasted arabica coffee beans", [{}])

    assert res.status == "NO_RELEVANT_MATCH"
    assert res.selected_hsn is None


def test_four_class_relevance_labels_and_calibration():
    mock_reranker = MagicMock()
    mock_reranker.rerank.return_value = [
        _make_cand("39233090", "39", "Plastic water bottle", 0.88, "plastic"),
        _make_cand("39269099", "39", "Other articles of plastics", 0.52, "plastic"),
        _make_cand("84223000", "84", "Bottle filling machinery", 0.28, "steel"),
        _make_cand("61091000", "61", "Cotton knitted t-shirts", 0.09, "cotton"),
    ]

    clf = RelevanceClassifier(
        reranker=mock_reranker,
        same_product_threshold=0.725,
        related_threshold=0.40,
        unrelated_threshold=0.20,
    )
    classified = clf.classify("plastic water bottle", [{}, {}, {}, {}])
    labels = [c.relation for c in classified]
    assert labels == [
        RelationLabel.SAME_PRODUCT,
        RelationLabel.INSUFFICIENT_INFORMATION,
        RelationLabel.RELATED_PRODUCT,
        RelationLabel.UNRELATED,
    ]

    # Calibrate threshold from unseen examples (score_pairs returns logits)
    mock_reranker.score_pairs.return_value = [2.3, 1.7, 0.2, -0.8, -1.7]
    best_thresh, cal_stats = clf.calibrate_from_examples(
        queries=["q1", "q2", "q3", "q4", "q5"],
        tariff_rows=[{}, {}, {}, {}, {}],
        labels=[1, 1, 0, 0, 0],
    )
    assert best_thresh >= 0.55
    assert cal_stats["f1"] == 1.0


def test_identify_separating_attributes_same_chapter_different_construction():
    mock_reranker = MagicMock()
    mock_reranker.rerank.return_value = [
        _make_cand("61091000", "61", "T-shirts, knitted or crocheted, of cotton", 0.84, "cotton"),
        _make_cand("62052000", "62", "Men's shirts, woven, not knitted, of cotton", 0.81, "cotton"),
    ]

    clf = RelevanceClassifier(reranker=mock_reranker, same_product_threshold=0.725)
    resolver = ModelDrivenAmbiguityResolver(classifier=clf)
    res = resolver.resolve("cotton shirt", [{}, {}])

    assert res.status == "AMBIGUOUS_SPECIFICATION"
    assert "construction" in res.separating_attributes
    assert "construction" in res.attribute_evidence
    assert res.clarification_question is not None


def test_identify_separating_attributes_complete_vs_parts():
    from src.ml.relevance_classifier import ClassifiedTariffCandidate

    cands = [
        ClassifiedTariffCandidate(
            candidate=_make_cand("87032291", "87", "Motor cars complete assembled vehicles", 0.83, "steel"),
            relation=RelationLabel.SAME_PRODUCT,
            confidence=0.83,
        ),
        ClassifiedTariffCandidate(
            candidate=_make_cand("87089900", "87", "Other parts and accessories of motor vehicles", 0.80, "steel"),
            relation=RelationLabel.SAME_PRODUCT,
            confidence=0.80,
        ),
    ]
    attrs, evidence = identify_separating_attributes(cands, "motor vehicle")
    assert "product_completeness" in attrs
    assert "product_completeness" in evidence


def test_numeric_constraints_and_sibling_distinction():
    from src.ml.ambiguity_resolver import (
        analyze_sibling_distinctions,
        evaluate_numeric_match,
        extract_numeric_constraints,
        extract_query_numeric_values,
    )
    from src.ml.relevance_classifier import ClassifiedTariffCandidate

    # Compound interval + unit normalization (1000 w == 1 kw)
    cs_le = extract_numeric_constraints("OF AN OUTPUT NOT EXCEEDING 75 KVA")
    cs_mid = extract_numeric_constraints("OF AN OUTPUT EXCEEDING 75 KVA BUT NOT EXCEEDING 375 KVA")
    assert len(cs_le) == 1 and cs_le[0].op == "<="
    assert len(cs_mid) == 2 and cs_mid[0].op == ">" and cs_mid[1].op == "<="

    q_50kva = extract_query_numeric_values("AC alternator 50 kva")
    assert evaluate_numeric_match(cs_le, q_50kva) == "MATCH"
    assert evaluate_numeric_match(cs_mid, q_50kva) == "CONFLICT"

    # Missing numerical info must NEVER be treated as a match
    q_missing = extract_query_numeric_values("AC alternator copper winding")
    assert evaluate_numeric_match(cs_le, q_missing) == "MISSING"

    # Sibling distinction picks matching 85016100 over 85016200 when 50 KVA given,
    # and flags missing_numeric_constraints=True when rating is omitted.
    c1 = ClassifiedTariffCandidate(
        candidate=RerankedTariffCandidate(
            hsn_code="85016200", chapter_code="85",
            description="AC GENERATORS EXCEEDING 75 KVA BUT NOT EXCEEDING 375 KVA",
            tariff_item_desc="EXCEEDING 75 KVA BUT NOT EXCEEDING 375 KVA",
            relevance_score=0.95, raw_logit=4.0,
        ),
        relation=RelationLabel.SAME_PRODUCT, confidence=0.95,
    )
    c2 = ClassifiedTariffCandidate(
        candidate=RerankedTariffCandidate(
            hsn_code="85016100", chapter_code="85",
            description="AC GENERATORS NOT EXCEEDING 75 KVA",
            tariff_item_desc="NOT EXCEEDING 75 KVA",
            relevance_score=0.93, raw_logit=3.6,
        ),
        relation=RelationLabel.SAME_PRODUCT, confidence=0.93,
    )
    res_50 = analyze_sibling_distinctions([c1, c2], "AC generator 50 kva")
    assert res_50["ranked_indices"][0] == 1  # 85016100 promoted to #1
    assert res_50["winner_has_clear_evidence"] is True
    assert res_50["missing_numeric_constraints"] is False

    res_miss = analyze_sibling_distinctions([c1, c2], "AC generator")
    assert res_miss["winner_has_clear_evidence"] is False
    assert res_miss["missing_numeric_constraints"] is True

