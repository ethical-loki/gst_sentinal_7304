"""
Unit tests for Phase 5: RelevanceClassifier and ModelDrivenAmbiguityResolver.
"""

from unittest.mock import MagicMock

from src.ml.ambiguity_resolver import ModelDrivenAmbiguityResolver
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

