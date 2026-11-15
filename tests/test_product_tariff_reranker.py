"""
Unit tests for src/ml/product_tariff_reranker.py
"""

from unittest.mock import MagicMock, patch

from src.ml.product_tariff_reranker import (
    ProductTariffReranker,
    _sigmoid,
    classify_tariff_level,
    format_tariff_context,
)


def test_sigmoid_bounds():
    assert abs(_sigmoid(0.0) - 0.5) < 1e-6
    assert _sigmoid(10.0) > 0.9999
    assert _sigmoid(-10.0) < 0.0001


def test_format_tariff_context_dict():
    row = {
        "chapter_title": "Plastics and articles thereof",
        "heading_4digit_desc": "Carboys, bottles, flasks",
        "HSN Description": "Bottles of plastics",
        "Article Keywords": "bottle, flask",
        "Material Keywords": "plastic, hdpe, pet",
    }
    ctx = format_tariff_context(row)
    assert "Plastics and articles thereof" in ctx
    assert "Bottles of plastics" in ctx
    assert "bottle, flask" in ctx
    assert "plastic, hdpe, pet" in ctx


def test_rerank_ordering_with_mock_cross_encoder():
    mock_ce = MagicMock()
    # Scores: first row (machinery) gets -2.5, second row (plastic bottle) gets +3.0
    mock_ce.predict.return_value = [-2.5, 3.0]

    with patch("src.ml.product_tariff_reranker.CrossEncoder", return_value=mock_ce):
        reranker = ProductTariffReranker(model_name_or_path="mock-model", local_files_only=True)
        rows = [
            {
                "HSN Code": "84223000",
                "chapter_code": "84",
                "HSN Description": "Machinery for filling, closing, sealing bottles",
                "Article Keywords": "bottling machine",
                "Material Keywords": "steel",
            },
            {
                "HSN Code": "39233090",
                "chapter_code": "39",
                "HSN Description": "Carboys, bottles, flasks and similar articles of plastics",
                "Article Keywords": "water bottle",
                "Material Keywords": "plastic",
            },
        ]
        results = reranker.rerank("plastic water bottle", rows)

    assert len(results) == 2
    assert results[0].hsn_code == "39233090"
    assert results[0].chapter_code == "39"
    assert results[0].raw_logit == 3.0
    assert results[0].relevance_score > 0.9
    assert results[1].hsn_code == "84223000"
    assert results[1].relevance_score < 0.1


def test_format_tariff_context_prioritizes_leaf_details():
    row = {
        "hsn_code": "85016100",
        "chapter_title": "Electrical machinery and equipment",
        "heading_4digit_desc": "Electric motors and generators",
        "subheading_6digit_desc": "AC generators (alternators)",
        "tariff_item_desc": "OF AN OUTPUT NOT EXCEEDING 75 KVA",
        "article_keywords": "alternator 50 kva",
        "material_keywords": "copper",
    }
    ctx = format_tariff_context(row)
    assert ctx.startswith("HSN 85016100 | OF AN OUTPUT NOT EXCEEDING 75 KVA")
    assert ctx.index("OF AN OUTPUT NOT EXCEEDING 75 KVA") < ctx.index("Electric motors and generators")
    assert ctx.index("Electric motors and generators") < ctx.index("Electrical machinery and equipment")


def test_classify_tariff_level():
    assert classify_tariff_level("85016100") == "LEAF_8DIGIT"
    assert classify_tariff_level("850161") == "SUBHEADING_6DIGIT"
    assert classify_tariff_level("8501") == "HEADING_4DIGIT"

