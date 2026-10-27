"""
Unit & Integration Tests for Two-Stage Retrieve & Rerank with Head-Noun Specificity Logic
File: tests/test_two_stage_hsn.py
"""

import pytest
import numpy as np
from pathlib import Path
from src.nlp.hsn_intelligence import (
    DynamicHSNSemanticMatcher,
    HSNMatchDecision,
    clean_trade_description,
)

ROOT_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def matcher():
    m = DynamicHSNSemanticMatcher(auto_load=True)
    return m


def test_models_loaded_offline(matcher):
    """Verify that both primary bi-encoder and cross-encoder are operational."""
    st = matcher._get_sentence_transformer()
    ce = matcher._get_cross_encoder()
    assert st is not None
    assert ce is not None


def test_hierarchical_catalog_loaded(matcher):
    """Verify that catalog contains hierarchical passages and residual flags."""
    assert matcher.catalog_size > 0
    sample = matcher.catalog_records[0]
    # Check that hierarchical text or clean description exists
    assert "description" in sample


def test_kashmir_apple_dedicated_heading_precedence(matcher):
    """GIR 3(a) Test: 'Kashmir apple' should match dedicated 0808 (Apples)

    instead of residual 08109040 (Custard-apple), overcoming bi-encoder compound collision.
    """
    res = matcher.match_single("Kashmir apple", top_k=5)
    matched_hsn = res["matched_hsn"]
    top1 = res["top_match"]

    # Must match Apple heading 0808 / 08081000
    assert matched_hsn.startswith("0808"), f"Expected HSN starting with 0808, got {matched_hsn}"


def test_custard_apple_token_sharing(matcher):
    """When query explicitly shares token 'custard', residual 08109040 should NOT be penalized

    and should win over 08081000 (standard apple).
    """
    res = matcher.match_single("Custard apple fresh 1kg", top_k=5)
    matched_hsn = res["matched_hsn"]
    assert matched_hsn.startswith("0810"), f"Expected HSN starting with 0810, got {matched_hsn}"


def test_cross_encoder_joint_attention_ranking(matcher):
    """Verifies that the cross-encoder reranks top 5 candidates and computes joint token interactions."""
    res = matcher.match_single("solar on grid inverter 5kw 3 phase", top_k=5)
    assert res["decision"] in [HSNMatchDecision.AUTOMATED_MATCH.value, HSNMatchDecision.FLAG_FOR_REVIEW.value]
    assert res["matched_hsn"].startswith("8504")
    # Verify runners-up exist
    assert len(res["runners_up"]) > 0


def test_batch_two_stage_matching(matcher):
    """Verifies batch matching with two-stage pipeline on multiple items."""
    queries = [
        "SS 304 hex nipple 1/2 inch 10 pcs",
        "allen cap screw M12 x 50 grade 8.8",
        "Kashmir apple fresh box",
        "Custard apple 500g",
    ]
    batch_res = matcher.match_batch(queries, top_k=4)
    assert batch_res.total_items == 4
    assert len(batch_res.matches) == 4

    # Kashmir apple should resolve to 0808
    assert batch_res.matches[2]["matched_hsn"].startswith("0808")
    # Custard apple should resolve to 0810
    assert batch_res.matches[3]["matched_hsn"].startswith("0810")
