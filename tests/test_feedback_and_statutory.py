"""
Unit & integration tests for Phase 6 (FeedbackCollector) and Phase 7 (StatutoryMasterIndex & HSNIntelligenceV2).
"""

import pandas as pd

from src.search.statutory_master_index import StatutoryMasterIndex
from src.training.feedback_collector import FeedbackCollector


def test_feedback_collector_separates_pending_and_verified(tmp_path):
    fc = FeedbackCollector(feedback_dir=tmp_path)

    # 1. Pending customer feedback must NOT create training pairs
    fid = fc.record_pending_feedback(
        query="stainless steel water bottle",
        predicted_hsn="84223000",
        predicted_context="Machinery | Bottle filling machine",
        predicted_score=0.79,
        customer_selected_hsn="73239390",
        reason="Predicted machine instead of bottle",
    )
    assert fid
    assert fc.pending_path.exists()
    assert not fc.verified_pairs_path.exists()

    # 2. Expert confirmation creates verified positive + hard-negative pairs
    added = fc.confirm_expert_correction(
        query="stainless steel water bottle",
        incorrect_row={
            "hsn_code": "84223000",
            "chapter_code": "84",
            "heading_4digit": "8422",
            "statutory_description": "Machinery for filling bottles",
        },
        correct_row={
            "hsn_code": "73239390",
            "chapter_code": "73",
            "heading_4digit": "7323",
            "statutory_description": "Table, kitchen or other household articles of stainless steel",
        },
        expert_id="gst_ca_01",
    )
    assert added == 2
    ver_df = pd.read_parquet(fc.verified_pairs_path)
    assert len(ver_df) == 2
    assert set(ver_df["label"].tolist()) == {0, 1}
    assert set(ver_df["relation"].tolist()) == {"RELATED_PRODUCT", "SAME_PRODUCT"}


def test_statutory_master_index_detects_out_of_schedule(tmp_path):
    statutory_rows = [
        {
            "hsn_code": "09012110",
            "chapter": "09",
            "description": "Roasted arabica coffee beans",
            "hsn_description": "Coffee, whether or not roasted",
            "clean_description": "roasted arabica coffee beans",
            "search_text": "roasted arabica coffee beans chapter 09",
            "standard_rate": 5.0,
        },
        {
            "hsn_code": "30049099",
            "chapter": "30",
            "description": "Medicaments paracetamol tablets",
            "hsn_description": "Pharmaceutical medicaments",
            "clean_description": "medicaments paracetamol tablets pharmaceutical",
            "search_text": "medicaments paracetamol tablets pharmaceutical chapter 30",
            "standard_rate": 12.0,
        },
        {
            "hsn_code": "39233090",
            "chapter": "39",
            "description": "Plastic water bottles and carboys",
            "hsn_description": "Carboys, bottles, flasks of plastics",
            "clean_description": "plastic water bottles and carboys",
            "search_text": "plastic water bottles carboys chapter 39",
            "standard_rate": 18.0,
        },
    ]
    active_rows = [
        {"chapter_code": "39"},
        {"chapter_code": "73"},
        {"chapter_code": "84"},
    ]

    stat_path = tmp_path / "tariff_master.parquet"
    act_path = tmp_path / "active.parquet"
    pd.DataFrame(statutory_rows).to_parquet(stat_path, index=False)
    pd.DataFrame(active_rows).to_parquet(act_path, index=False)

    idx = StatutoryMasterIndex(
        statutory_parquet=stat_path,
        active_parquet=act_path,
        meta_dir=tmp_path / "meta",
    )
    assert idx.active_chapters == {"39", "73", "84"}

    cov_coffee = idx.check_schedule_coverage("roasted arabica coffee beans", min_bm25_score=0.1)
    assert cov_coffee.is_out_of_schedule is True
    assert cov_coffee.predicted_chapter == "09"

    cov_bottle = idx.check_schedule_coverage("plastic water bottles", min_bm25_score=0.1)
    assert cov_bottle.is_out_of_schedule is False
    assert cov_bottle.predicted_chapter == "39"


def test_compare_active_vs_statutory_rejects_active_when_inactive_wins(tmp_path):
    from unittest.mock import MagicMock
    from src.ml.product_tariff_reranker import RerankedTariffCandidate

    statutory_rows = [
        {
            "hsn_code": "09012110",
            "chapter": "09",
            "description": "Roasted arabica coffee beans",
            "hsn_description": "Coffee, whether or not roasted",
            "clean_description": "roasted arabica coffee beans",
            "search_text": "roasted arabica coffee beans chapter 09",
            "standard_rate": 5.0,
        },
        {
            "hsn_code": "39233090",
            "chapter": "39",
            "description": "Plastic containers for storage",
            "hsn_description": "Carboys, bottles, flasks of plastics",
            "clean_description": "plastic containers for storage",
            "search_text": "plastic containers storage chapter 39",
            "standard_rate": 18.0,
        },
        {
            "hsn_code": "73239390",
            "chapter": "73",
            "description": "Stainless steel kitchenware",
            "hsn_description": "Table kitchen articles of steel",
            "clean_description": "stainless steel kitchenware",
            "search_text": "stainless steel kitchenware chapter 73",
            "standard_rate": 18.0,
        },
        {
            "hsn_code": "84713010",
            "chapter": "84",
            "description": "Portable automatic data processing machines",
            "hsn_description": "Laptops and notebooks",
            "clean_description": "portable automatic data processing machines laptops",
            "search_text": "laptops computers chapter 84",
            "standard_rate": 18.0,
        },
    ]
    active_rows = [{"chapter_code": "39"}, {"chapter_code": "73"}, {"chapter_code": "84"}]
    stat_path = tmp_path / "tariff_master.parquet"
    act_path = tmp_path / "active.parquet"
    pd.DataFrame(statutory_rows).to_parquet(stat_path, index=False)
    pd.DataFrame(active_rows).to_parquet(act_path, index=False)

    idx = StatutoryMasterIndex(
        statutory_parquet=stat_path,
        active_parquet=act_path,
        meta_dir=tmp_path / "meta",
    )

    mock_reranker = MagicMock()
    mock_reranker.rerank.return_value = [
        RerankedTariffCandidate(
            hsn_code="09012110",
            chapter_code="09",
            description="Roasted arabica coffee beans",
            relevance_score=0.94,
            raw_logit=2.75,
            chapter_title="Chapter 09",
            material_keywords="",
        )
    ]

    # Even if an active chapter candidate crossed 0.725 (e.g., 0.78),
    # the inactive Chapter 09 candidate scores 0.94 (> 0.78 + 0.02) and must win.
    comp = idx.compare_active_vs_statutory(
        query="roasted arabica coffee beans",
        best_active_score=0.78,
        reranker=mock_reranker,
        top_k=5,
        inactive_advantage_margin=0.02,
    )
    assert comp.is_out_of_schedule is True
    assert comp.best_inactive_match["chapter"] == "09"
    assert comp.best_inactive_match["hsn_code"] == "09012110"
    assert comp.best_inactive_score == 0.94
    assert comp.best_active_score == 0.78


def test_feedback_retraining_lifecycle_blocks_unverified_and_promotes_improved(tmp_path):
    from unittest.mock import MagicMock
    import pytest

    fc = FeedbackCollector(feedback_dir=tmp_path)
    fid = fc.record_pending_feedback(
        query="stainless steel water bottle",
        predicted_hsn="84223000",
        predicted_context="Machinery",
        predicted_score=0.79,
        customer_selected_hsn="73239390",
    )

    # 1. Must refuse retraining while only unverified pending feedback exists
    with pytest.raises(ValueError, match="unverified"):
        fc.run_retraining_lifecycle("hsn_reranker_v2")

    assert len(fc.list_pending_feedback("PENDING_EXPERT_REVIEW")) == 1

    # 2. Expert approves pending feedback -> creates verified pairs
    added = fc.approve_pending_feedback(
        feedback_id=fid,
        expert_id="gst_ca_02",
        incorrect_row={"hsn_code": "84223000", "chapter_code": "84", "statutory_description": "Filling machinery"},
        correct_row={"hsn_code": "73239390", "chapter_code": "73", "statutory_description": "Stainless steel bottle"},
    )
    assert added == 2
    assert len(fc.list_pending_feedback("PENDING_EXPERT_REVIEW")) == 0
    assert len(fc.list_pending_feedback("VERIFIED")) == 1

    # Create tiny dummy base_train parquet
    base_train = tmp_path / "base_train.parquet"
    pd.DataFrame([{"query": "q", "tariff_context": "ctx", "label": 1}]).to_parquet(base_train, index=False)

    mock_registry = MagicMock()
    mock_registry.get_active.return_value = {"metrics": {"test_roc_auc": 0.92}}

    # 3. Regression is rejected (not promoted)
    res_reg = fc.run_retraining_lifecycle(
        new_version_name="hsn_reranker_v2_bad",
        base_train_parquet=base_train,
        registry=mock_registry,
        trainer_fn=lambda **kw: {"test_metrics": {"roc_auc": 0.89}, "calibrated_threshold": 0.70},
    )
    assert res_reg["status"] == "REJECTED_REGRESSION"
    assert res_reg["promoted"] is False
    mock_registry.promote.assert_not_called()

    # 4. Improvement is promoted
    res_ok = fc.run_retraining_lifecycle(
        new_version_name="hsn_reranker_v2",
        base_train_parquet=base_train,
        registry=mock_registry,
        trainer_fn=lambda **kw: {"test_metrics": {"roc_auc": 0.94}, "calibrated_threshold": 0.73},
    )
    assert res_ok["status"] == "PROMOTED"
    assert res_ok["promoted"] is True
    mock_registry.promote.assert_called_once_with("hsn_reranker_v2")

