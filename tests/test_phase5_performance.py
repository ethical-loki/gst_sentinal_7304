"""
tests/test_phase5_performance.py
================================
Phase 5 tests for CrossEncoder CPU INT8 dynamic quantization, pair cache,
thread tuning, and FP32-vs-INT8 ranking fidelity.
"""

import numpy as np

from src.ml.model_registry import ModelRegistry
from src.ml.product_tariff_reranker import BASELINE_RERANKER_MODEL, ProductTariffReranker


def test_crossencoder_cpu_int8_quantization_and_fp32_parity():
    active = ModelRegistry().get_active_entry()
    model_path = active["model_path"] if active else BASELINE_RERANKER_MODEL

    fp32 = ProductTariffReranker(
        model_name_or_path=model_path,
        device="cpu",
        max_length=384,
        batch_size=16,
        quantize_int8=False,
    )
    int8 = ProductTariffReranker(
        model_name_or_path=model_path,
        device="cpu",
        max_length=384,
        batch_size=16,
        quantize_int8=True,
    )

    assert fp32._quantized_int8 is False
    assert int8._quantized_int8 is True

    query = "centrifugal water pump stainless steel impeller"
    rows = [
        {
            "hsn_code": "84137010",
            "chapter_code": "84",
            "statutory_description": "PUMPS FOR LIQUIDS - OTHER CENTRIFUGAL PUMPS: PRIMARILY DESIGNED TO HANDLE WATER",
            "tariff_item_desc": "PRIMARILY DESIGNED TO HANDLE WATER",
        },
        {
            "hsn_code": "84137099",
            "chapter_code": "84",
            "statutory_description": "PUMPS FOR LIQUIDS - OTHER CENTRIFUGAL PUMPS: OTHER",
            "tariff_item_desc": "OTHER",
        },
        {
            "hsn_code": "73181500",
            "chapter_code": "73",
            "statutory_description": "SCREWS, BOLTS, NUTS, COACH-SCREWS, SCREW HOOKS, RIVETS, COTTERS, OF IRON OR STEEL",
            "tariff_item_desc": "OTHER SCREWS AND BOLTS, WHETHER OR NOT WITH THEIR NUTS OR WASHERS",
        },
        {
            "hsn_code": "61091000",
            "chapter_code": "61",
            "statutory_description": "T-SHIRTS, SINGLETS AND OTHER VESTS, KNITTED OR CROCHETED: OF COTTON",
            "tariff_item_desc": "OF COTTON",
        },
    ]

    r_fp32 = fp32.rerank(query, rows, normalize_sigmoid=False)
    r_int8 = int8.rerank(query, rows, normalize_sigmoid=False)

    scores_fp32 = {r.hsn_code: r.raw_logit for r in r_fp32}
    scores_int8 = {r.hsn_code: r.raw_logit for r in r_int8}
    keys = sorted(scores_fp32.keys())
    v_fp32 = np.array([scores_fp32[k] for k in keys], dtype=np.float64)
    v_int8 = np.array([scores_int8[k] for k in keys], dtype=np.float64)

    corr = float(np.corrcoef(v_fp32, v_int8)[0, 1])
    assert corr >= 0.985, f"INT8 vs FP32 logit correlation dropped: {corr}"
    assert r_int8[0].hsn_code == r_fp32[0].hsn_code

    # Verify in-memory pair cache hits on repeat call
    hits_before = int8.pair_cache_hits
    _ = int8.rerank(query, rows, normalize_sigmoid=False)
    assert int8.pair_cache_hits >= hits_before + len(rows)
