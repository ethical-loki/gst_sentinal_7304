"""
Dynamic Multi-Input HSN Semantic Matcher Verification Suite
File: tests/test_dynamic_hsn_matcher.py

Validates the complete 4-phase offline vector geometry pipeline:
1. Zero-latency startup & pre-computed N x 384 matrix in RAM
2. Vectorized cleaning and dynamic batch encoding
3. Parallel BLAS matrix multiplication S = Q · D^T
4. Dynamic thresholding guardrails (>=0.70 auto, 0.45-0.70 review, <0.45 unmapped)
5. Multi-candidate Top-1 + Top-3 runners-up payload
6. Dynamic ingestion adaptors (Spreadsheet, REST, Database Queue)
7. Backwards compatibility with single-item classify_description and hybrid search
"""

import io
import time
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from src.nlp.hsn_intelligence import (
    HSNIntelligenceEngine,
    DynamicHSNSemanticMatcher,
    SpreadsheetIngestionAdaptor,
    RESTMicroserviceAdaptor,
    DatabaseQueueConsumer,
    clean_trade_description,
    HSNMatchDecision,
    HSNConfidenceLevel,
)

ROOT_DIR = Path(__file__).resolve().parent.parent
TARIFF_PARQUET = ROOT_DIR / "data" / "tariff_master.parquet"
INDEX_384_NPY = ROOT_DIR / "data" / "tariff_vector_index_384.npy"


def test_clean_trade_description_junk_stripping():
    """Phase 2: Verifies special junk characters, punctuation, and trailing quantities are stripped."""
    test_cases = [
        ("Item #1: SS hex nipple 1/2 inch, 10 pcs - pkt [urgent]", "ss hex nipple 1 2 inch"),
        ("Line 04: allen cap screw M12 x 50 grade 8.8 (100 nos)", "allen cap screw m12 x 50 grade 8.8"),
        ("Cast iron non return check valve 50mm, 5 kgs/box", "cast iron non return check valve 50mm"),
        ("uPVC elbow 90 degree solvent weld, 25 pkts", "upvc elbow 90 degree solvent weld"),
        ("dry type isolation transformer 10 kva, 2 sets", "dry type isolation transformer 10 kva"),
        ("flange class 150 slip on forged steel | 100 meters", "flange class 150 slip on forged steel"),
    ]
    for raw, expected_substr in test_cases:
        cleaned = clean_trade_description(raw)
        assert expected_substr in cleaned, f"Expected '{expected_substr}' in '{cleaned}' (raw: '{raw}')"
        # Verify unit words are cleanly removed
        assert "pcs" not in cleaned
        assert "pkts" not in cleaned
        assert "nos" not in cleaned


def test_zero_latency_startup_and_persistence():
    """Phase 1: Verifies instant binary matrix loading into RAM without re-encoding catalog."""
    t0 = time.perf_counter()
    matcher = DynamicHSNSemanticMatcher(auto_load=True)
    load_time_ms = (time.perf_counter() - t0) * 1000.0

    assert matcher.catalog_matrix is not None, "Catalog matrix not loaded into RAM"
    assert matcher.catalog_matrix.ndim == 2, "Catalog matrix must be 2D (N x D)"
    assert matcher.catalog_matrix.shape[1] == 384, f"Expected 384-D matrix, got {matcher.catalog_matrix.shape[1]}"
    assert matcher.catalog_matrix.shape[0] >= 12000, f"Expected >= 12,000 catalog entries, got {matcher.catalog_matrix.shape[0]}"
    assert matcher.catalog_size == matcher.catalog_matrix.shape[0]

    # Verify L2 unit normalization: ||v|| = 1.0
    norms = np.linalg.norm(matcher.catalog_matrix[:50], axis=1)
    assert np.allclose(norms, 1.0, atol=1e-3), "Catalog vectors are not L2-normalized!"

    print(f"\n[OK] Startup latency: {load_time_ms:.2f} ms for {matcher.catalog_size:,} records (384-D)")
    assert load_time_ms < 5000.0, "Startup took too long (should be near instant file read)"


def test_parallel_geometric_matching_and_thresholding():
    """Phase 3 & 4: Verifies matrix multiplication S = Q · D^T and dynamic threshold routing."""
    engine = HSNIntelligenceEngine()

    batch_input = [
        # Clear statutory items (expect Automated Match >= 0.70)
        "SS 304 hex nipple 1/2 inch",
        "industrial 2-piece ball valve 1 inch BSP",
        "allen cap screw M12 x 50 grade 8.8",
        "solar on grid inverter 5kw 3 phase",
        "copper flexible power cable 3 core 2.5 sq mm",
        "rubber gasket seal ring",
        # Borderline / ambiguous item (expect Flag for Review 0.45 - 0.70 or match)
        "general industrial fitting component",
        # Unrecognized / nonsensical query (expect low confidence < 0.70)
        "completely unknown extraterrestrial antimatter dark matter widget xyz 999",
    ]

    t0 = time.perf_counter()
    results = engine.match_batch(batch_input)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    print(f"\n[OK] Batch of {len(batch_input)} matched in {elapsed_ms:.2f} ms")
    assert len(results) == len(batch_input)
    assert results.total_items == len(batch_input)
    assert results.embedding_dim == 384

    # Verify high confidence matches for real industrial items
    for idx in range(6):
        item = results[idx]
        assert item["decision"] == HSNMatchDecision.AUTOMATED_MATCH.value, (
            f"Expected AUTOMATED_MATCH for '{item['raw_description']}', got {item['decision']} (score: {item['confidence_score']})"
        )
        assert item["confidence_score"] >= 0.70
        assert item["matched_hsn"] is not None
        assert len(item["matched_hsn"]) >= 4

    # Check that each result contains Top-1 match and Top-3 runners-up
    for item in results:
        assert "top_match" in item
        assert "runners_up" in item
        assert len(item["runners_up"]) <= 3
        # Check runners-up scores are in descending order
        if len(item["runners_up"]) >= 2:
            s1 = item["runners_up"][0]["score"]
            s2 = item["runners_up"][1]["score"]
            assert s1 >= s2 - 1e-5, f"Runners-up not sorted: {s1} < {s2}"

    # Verify nonsensical query is NOT classified as automated match
    obscure_item = results[-1]
    assert obscure_item["confidence_score"] < 0.70, "Nonsensical query should not have automated match"


def test_batch_chunking_operational_guardrail():
    """Operational Guardrail: Verifies input batches > 1000 items are safely chunked into blocks of 256."""
    matcher = DynamicHSNSemanticMatcher(auto_load=True)

    # Synthetic batch of 1,050 items
    base_item = "stainless steel industrial ball valve"
    large_batch = [f"{base_item} model {i} 10 pcs" for i in range(1050)]

    t0 = time.perf_counter()
    # Test vectorize_batch with chunking
    q_mat, cleaned = matcher.vectorize_batch(large_batch, chunk_size=256)
    elapsed = time.perf_counter() - t0

    assert q_mat.shape == (1050, 384)
    assert len(cleaned) == 1050
    # Confirm L2 normalization
    row_norms = np.linalg.norm(q_mat[:50], axis=1)
    assert np.allclose(row_norms, 1.0, atol=1e-3)
    print(f"\n[OK] Chunked batch vectorization of 1,050 items took {elapsed:.2f} s")


def test_spreadsheet_ingestion_adaptor():
    """Adaptor 1: Verifies spreadsheet processing and column augmentation."""
    engine = HSNIntelligenceEngine()
    adaptor = engine.spreadsheet_adaptor

    sample_df = pd.DataFrame({
        "item_id": [101, 102, 103],
        "item_description": [
            "SS 304 hex nipple 1/2 inch 50 pcs",
            "hex head bolt with nylon nut M10 200 pcs",
            "dry type isolation transformer 10 kva",
        ],
        "unit_price": [150.0, 12.5, 45000.0],
        "qty": [50, 200, 1],
    })

    augmented_df = adaptor.process_dataframe(sample_df, description_col="item_description")

    # Verify added columns
    assert "matched_hsn" in augmented_df.columns
    assert "hsn_confidence_pct" in augmented_df.columns
    assert "match_decision" in augmented_df.columns
    assert "standard_gst_rate" in augmented_df.columns
    assert "runner_up_1_hsn" in augmented_df.columns

    assert len(augmented_df) == 3
    for idx, row in augmented_df.iterrows():
        assert row["matched_hsn"] is not None
        assert row["hsn_confidence_pct"] >= 70.0
        assert row["match_decision"] == HSNMatchDecision.AUTOMATED_MATCH.value

    # Verify CSV export round-trip
    csv_bytes = augmented_df.to_csv(index=False).encode("utf-8")
    loaded_df = adaptor.process_file(io.BytesIO(csv_bytes))
    assert "matched_hsn" in loaded_df.columns


def test_rest_microservice_adaptor_latency():
    """Adaptor 2: Verifies REST JSON payload processing with low latency on CPU."""
    engine = HSNIntelligenceEngine()
    adaptor = engine.rest_adaptor

    payload = {
        "items": [
            {"id": "LINE_01", "description": "1/2 inch SS hex nipple 10 pcs"},
            {"id": "LINE_02", "description": "industrial 2-piece ball valve 1 inch BSP"},
            {"id": "LINE_03", "description": "copper flexible power cable 3 core 2.5 sq mm"},
            {"id": "LINE_04", "description": "solar on grid inverter 5kw 3 phase"},
        ]
    }

    t0 = time.perf_counter()
    resp = adaptor.process_payload(payload)
    latency_ms = (time.perf_counter() - t0) * 1000.0

    print(f"\n[OK] REST Adaptor latency: {latency_ms:.2f} ms (internal batch latency: {resp['latency_ms']:.2f} ms)")
    assert resp["total_items"] == 4
    assert resp["automated_matches"] >= 3
    assert len(resp["items"]) == 4

    # Verify item-level schema
    for it in resp["items"]:
        assert "item_id" in it
        assert "matched_hsn" in it
        assert "confidence_score" in it
        assert "runners_up" in it
        assert len(it["runners_up"]) <= 3


def test_database_queue_consumer():
    """Adaptor 3: Verifies bulk polling and write-back consumer worker."""
    engine = HSNIntelligenceEngine()
    consumer = engine.queue_consumer

    unprocessed_mock_db = [
        {"db_id": 1, "product_description": "SS 304 socket weld tee connector", "status": "PENDING"},
        {"db_id": 2, "product_description": "solar on grid inverter 5kw 3 phase", "status": "PENDING"},
        {"db_id": 3, "product_description": "cast iron non return check valve 50mm", "status": "PENDING"},
    ]

    written_updates = []

    def mock_fetch(batch_size: int):
        return unprocessed_mock_db[:batch_size]

    def mock_write(updates):
        nonlocal written_updates
        written_updates.extend(updates)

    processed_count = consumer.process_unprocessed_batch(
        fetch_items_fn=mock_fetch,
        write_results_fn=mock_write,
        batch_size=10,
    )

    assert processed_count == 3
    assert len(written_updates) == 3
    for u in written_updates:
        assert "matched_hsn" in u
        assert "confidence_pct" in u
        assert "match_decision" in u
        assert u["confidence_pct"] >= 70.0


def test_backwards_compatibility_classify_description():
    """Verifies that single-item classify_description and search remain 100% functional."""
    engine = HSNIntelligenceEngine()

    res = engine.classify_description("SS 304 hex nipple", top_k=5)
    assert len(res) > 0
    assert hasattr(res, "matches")
    assert res[0]["hsn"].startswith("7307")

    search_res = engine.search("industrial 2-piece ball valve", top_k=3)
    assert len(search_res) > 0
    assert search_res[0]["hsn"].startswith("8481")


if __name__ == "__main__":
    pytest.main(["-v", __file__])
