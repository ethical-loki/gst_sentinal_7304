"""
Unit tests for Phase 2: SyntheticQueryGenerator and TrainingDataBuilder.
"""

import pandas as pd

from src.ml.synthetic_query_generator import SyntheticQueryGenerator
from src.training.training_data_builder import TrainingDataBuilder


def test_synthetic_query_generator_produces_diverse_queries():
    gen = SyntheticQueryGenerator(seed=42, use_llm=False)
    row = {
        "hsn_code": "39233090",
        "chapter_code": "39",
        "chapter_title": "Plastics and articles thereof",
        "statutory_description": "Carboys, bottles, flasks and similar articles",
        "tariff_item_desc": "Bottles and flasks of plastics",
        "article_keywords": "water bottle, plastic flask, beverage bottle",
        "material_keywords": "polyethylene, pet, hdpe",
        "consumer_synonyms": "sports bottle",
    }
    queries = gen.generate_for_row(row, max_queries=5)
    assert len(queries) >= 3
    strategies = {q.strategy for q in queries}
    assert "article_only" in strategies
    assert len({q.query.lower() for q in queries}) == len(queries)


def test_training_data_builder_zero_hsn_leakage(tmp_path):
    rows = []
    for ch in ["39", "73", "84"]:
        for i in range(10):
            rows.append(
                {
                    "hsn_code": f"{ch}0100{i:02d}",
                    "chapter_code": ch,
                    "chapter_title": f"Chapter {ch}",
                    "heading_4digit": f"{ch}01",
                    "heading_4digit_desc": f"Heading {ch}01",
                    "subheading_6digit_desc": f"Subheading {i}",
                    "tariff_item_desc": f"Item {i} of chapter {ch}",
                    "statutory_description": f"Statutory item {i}",
                    "article_keywords": f"article_{ch}_{i}, widget_{i}",
                    "material_keywords": f"material_{ch}",
                    "consumer_synonyms": f"syn_{i}",
                }
            )
    master_path = tmp_path / "master.parquet"
    out_dir = tmp_path / "pairs"
    pd.DataFrame(rows).to_parquet(master_path, index=False)

    builder = TrainingDataBuilder(master_parquet=master_path, output_dir=out_dir, seed=42)
    stats = builder.run(leaf_8digit_only=True, max_queries_per_row=3)

    train_df = pd.read_parquet(out_dir / "positive_pairs_train.parquet")
    val_df = pd.read_parquet(out_dir / "positive_pairs_val.parquet")
    test_df = pd.read_parquet(out_dir / "positive_pairs_test.parquet")

    train_codes = set(train_df["hsn_code"])
    val_codes = set(val_df["hsn_code"])
    test_codes = set(test_df["hsn_code"])

    assert train_codes.isdisjoint(val_codes)
    assert train_codes.isdisjoint(test_codes)
    assert val_codes.isdisjoint(test_codes)
    assert stats["splits"]["train"]["positive_pairs"] == len(train_df)
    assert (train_df["label"] == 1).all()
    assert (train_df["relation"] == "SAME_PRODUCT").all()

