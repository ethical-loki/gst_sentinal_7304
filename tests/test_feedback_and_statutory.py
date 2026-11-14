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

