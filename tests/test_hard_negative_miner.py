"""
Unit tests for Phase 3: HardNegativeMiner and Ambiguity Safeguard.
"""

import numpy as np
import pandas as pd

from src.ml.hard_negative_miner import HardNegativeMiner, is_ambiguous_neighbor


def test_safeguard_blocks_same_heading_and_keyword_overlap():
    pos = {
        "hsn_clean": "39233090",
        "chapter_clean": "39",
        "article_keywords": "water bottle, plastic bottle, flask",
    }
    sibling_same_heading = {
        "hsn_clean": "39233010",
        "chapter_clean": "39",
        "article_keywords": "carboy, jerrycan",
    }
    is_ambig, reason = is_ambiguous_neighbor(pos, sibling_same_heading)
    assert is_ambig is True
    assert reason == "same_4digit_heading"

    keyword_overlap_other_ch = {
        "hsn_clean": "73239390",
        "chapter_clean": "73",
        "article_keywords": "water bottle, steel flask, flask",
    }
    is_ambig2, reason2 = is_ambiguous_neighbor(pos, keyword_overlap_other_ch)
    assert is_ambig2 is True
    assert reason2 == "article_keyword_overlap"

    machinery_distractor = {
        "hsn_clean": "84223000",
        "chapter_clean": "84",
        "article_keywords": "bottling machine, filling machinery",
    }
    is_ambig3, reason3 = is_ambiguous_neighbor(pos, machinery_distractor)
    assert is_ambig3 is False
    assert reason3 == "safe_negative"


def test_hard_negative_miner_pipeline_with_mock_embeddings(tmp_path):
    master_rows = [
        {
            "hsn_code": "39233090",
            "chapter_code": "39",
            "chapter_title": "Plastics",
            "heading_4digit": "3923",
            "heading_4digit_desc": "Carboys, bottles",
            "statutory_description": "Bottles of plastics",
            "article_keywords": "plastic bottle",
            "material_keywords": "hdpe",
        },
        {
            "hsn_code": "39233010",
            "chapter_code": "39",
            "chapter_title": "Plastics",
            "heading_4digit": "3923",
            "heading_4digit_desc": "Carboys, bottles",
            "statutory_description": "Carboys of plastics",
            "article_keywords": "carboy",
            "material_keywords": "hdpe",
        },
        {
            "hsn_code": "84223000",
            "chapter_code": "84",
            "chapter_title": "Machinery",
            "heading_4digit": "8422",
            "heading_4digit_desc": "Filling machinery",
            "statutory_description": "Machinery for filling bottles",
            "article_keywords": "bottling machine",
            "material_keywords": "steel",
        },
        {
            "hsn_code": "39241090",
            "chapter_code": "39",
            "chapter_title": "Plastics",
            "heading_4digit": "3924",
            "heading_4digit_desc": "Tableware",
            "statutory_description": "Plastic tableware",
            "article_keywords": "plastic plate",
            "material_keywords": "pp",
        },
    ]
    master_path = tmp_path / "master.parquet"
    pd.DataFrame(master_rows).to_parquet(master_path, index=False)

    pos_df = pd.DataFrame(
        [
            {
                "split": "train",
                "query": "hdpe plastic bottle",
                "query_strategy": "material_article",
                "hsn_code": "39233090",
                "chapter_code": "39",
                "heading_4digit": "3923",
                "tariff_context": "Plastics | Bottles of plastics",
                "label": 1,
                "relation": "SAME_PRODUCT",
            }
        ]
    )

    miner = HardNegativeMiner(master_parquet=master_path, pairs_dir=tmp_path)
    # Deterministic mock embeddings: 39233090 and 39233010 and 84223000 are close
    miner.doc_embeddings = np.array(
        [
            [1.0, 0.0],
            [0.95, 0.1],
            [0.90, 0.2],
            [0.60, 0.8],
        ],
        dtype=np.float32,
    )
    miner.encode_queries = lambda q: np.array([[1.0, 0.0]], dtype=np.float32)

    combined, stats = miner.mine_for_split(pos_df, negatives_per_positive=2, top_k_search=4)
    assert stats["total_positives"] == 1
    assert stats["total_negatives_mined"] == 2
    assert stats["skipped_same_heading_safeguard"] >= 1
    neg_hsns = set(combined[combined["label"] == 0]["hsn_code"])
    assert "39233010" not in neg_hsns  # Blocked by same_4digit_heading safeguard
    assert "84223000" in neg_hsns  # Cross-chapter distractor mined

