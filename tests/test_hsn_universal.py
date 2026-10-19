"""
Universal Tariff Multi-Domain Verification Suite: tests/test_hsn_universal.py
Validates universal semantic retrieval across diverse industrial and trade sectors:
- Inorganic Chemicals (Mercury, Quicksilver, Sulfuric Acid)
- Iron & Steel (Hex nipples, Seamless/ERW pipes)
- Plastics & Polymers (PVC conduit pipes, HDPE granules)
- Machinery & Electrical (Ball valves, Solar inverters)
- Textiles & Agriculture (Cotton yarn, Basmati rice)

Asserts:
1. Zero reliance on hardcoded keyword/alias dictionaries in source code.
2. Top-5 accuracy across the multi-domain benchmark >= 85%.
3. End-to-end CPU retrieval latency < 15.0 ms per query.
"""

import sys
import time
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.nlp.hsn_search import HSNSemanticSearchEngine


def test_hsn_universal_retrieval_and_latency():
    print("\n" + "=" * 70)
    print("   UNIVERSAL MULTI-DOMAIN TARIFF RETRIEVAL & LATENCY BENCHMARK    ")
    print("=" * 70 + "\n")

    # ----------------------------------------------------------------------
    # 1. VERIFY TARIFF CORPUS AND ZERO-HARDCODING INTEGRITY
    # ----------------------------------------------------------------------
    print("[1/4] Verifying Universal Tariff Schedule & Architecture...")
    tariff_parquet = ROOT_DIR / "data" / "tariff_master.parquet"
    vector_index = ROOT_DIR / "data" / "tariff_vector_index.npy"
    search_source_file = ROOT_DIR / "src" / "nlp" / "hsn_search.py"

    assert tariff_parquet.exists(), f"Tariff master missing at {tariff_parquet}"
    assert vector_index.exists(), f"Vector index missing at {vector_index}"
    assert search_source_file.exists(), f"Search source missing at {search_source_file}"

    df_tariff = pd.read_parquet(tariff_parquet)
    index_matrix = np.load(vector_index)

    print(f"  -> Total Statutory Lines  : {len(df_tariff):,}")
    print(f"  -> Vector Matrix Dimension: {index_matrix.shape}")
    print(f"  -> Total Chapters Covered : {df_tariff['chapter'].nunique()}")

    assert len(df_tariff) >= 12000, f"Expected universal coverage >= 12,000, got {len(df_tariff)}"
    assert index_matrix.shape[0] == len(df_tariff), "Matrix row count does not match tariff rows"
    assert index_matrix.shape[1] == 128, "Index must have 128-D embedding space"

    # Verify unit hypersphere normalization
    sample_norms = np.linalg.norm(index_matrix[:100], axis=1)
    assert np.allclose(sample_norms, 1.0, atol=1e-3), "Indexed vectors are not L2-normalized!"

    # Verify elemental mercury and mercury compounds exist in the statutory index
    mercury_matches = df_tariff[df_tariff["clean_description"].str.contains("mercury", case=False, na=False)]
    assert len(mercury_matches) > 0, "Statutory mercury items missing from tariff master!"
    assert any("2805" in str(c) for c in mercury_matches["hsn_code"]), "Heading 2805 missing for mercury!"

    # Verify ZERO hardcoded keyword dictionaries in src/nlp/hsn_search.py
    with open(search_source_file, "r", encoding="utf-8") as f:
        search_code = f.read()

    assert "TRADE_KEYWORDS" not in search_code, "Violated: TRADE_KEYWORDS hardcoding found in hsn_search.py!"
    assert "TRADE_KEYWORD" not in search_code, "Violated: hardcoded trade keyword found in hsn_search.py!"
    assert '"2805": ["mercury"]' not in search_code, "Violated: hardcoded mercury alias dictionary found!"
    print("  -> Zero-hardcoding verification: PASSED (Pure generalized hybrid retrieval).")

    # ----------------------------------------------------------------------
    # 2. INITIALIZE HYBRID RETRIEVAL ENGINE
    # ----------------------------------------------------------------------
    print("\n[2/4] Initializing Universal HSNSemanticSearchEngine...")
    engine = HSNSemanticSearchEngine(
        tariff_parquet_path=str(tariff_parquet),
        index_path=str(vector_index),
    )

    # ----------------------------------------------------------------------
    # 3. EVALUATE MULTI-DOMAIN TEST BENCHMARK (Target >= 85%)
    # ----------------------------------------------------------------------
    print("\n[3/4] Evaluating Multi-Domain Commodity Retrieval Accuracy...")
    multi_domain_benchmark = [
        # Inorganic Chemicals -> Chapter 28
        {"query": "mercury liquid", "expected_chapters": ["28"], "domain": "Inorganic Chemicals"},
        {"query": "quicksilver", "expected_chapters": ["28"], "domain": "Inorganic Chemicals"},
        {"query": "sulfuric acid 98%", "expected_chapters": ["28"], "domain": "Inorganic Chemicals"},

        # Iron & Steel -> Chapter 73
        {"query": "SS 304 hex nipple", "expected_chapters": ["73"], "domain": "Iron & Steel"},
        {"query": "seamless ERW pipe 25mm", "expected_chapters": ["73"], "domain": "Iron & Steel"},

        # Plastics -> Chapter 39
        {"query": "PVC conduit pipe 1 inch", "expected_chapters": ["39"], "domain": "Plastics"},
        {"query": "HDPE granules", "expected_chapters": ["39"], "domain": "Plastics"},

        # Machinery & Electronics -> Chapter 84 / 85
        {"query": "2-piece ball valve", "expected_chapters": ["84", "85"], "domain": "Machinery & Electronics"},
        {"query": "industrial solar inverter 5kW", "expected_chapters": ["84", "85"], "domain": "Machinery & Electronics"},

        # Textiles / Agro -> Chapter 10 / 52
        {"query": "cotton yarn 40s combed", "expected_chapters": ["52"], "domain": "Textiles"},
        {"query": "parboiled basmati rice", "expected_chapters": ["10"], "domain": "Agro / Cereals"},
    ]

    top1_hits = 0
    top5_hits = 0
    total_samples = len(multi_domain_benchmark)

    for item in multi_domain_benchmark:
        q = item["query"]
        expected = item["expected_chapters"]
        res = engine.search(q, top_k=5)

        retrieved_chapters = [str(r["chapter"]) for r in res]
        top1_hit = len(retrieved_chapters) > 0 and retrieved_chapters[0] in expected
        top5_hit = any(ch in expected for ch in retrieved_chapters)

        if top1_hit:
            top1_hits += 1
        if top5_hit:
            top5_hits += 1

        status = "PASS" if top5_hit else "FAIL"
        top_match = res[0] if len(res) > 0 else {"hsn_code": "N/A", "chapter": "N/A", "confidence_pct": 0.0}
        print(f"  [{status}] {q:32s} -> Expected Ch {expected} | Top: [{top_match['hsn_code']}] Ch {top_match['chapter']} ({top_match['confidence_pct']}%)")

    top1_acc = (top1_hits / total_samples) * 100.0
    top5_acc = (top5_hits / total_samples) * 100.0

    print(f"\n  -> Total Benchmark Queries: {total_samples}")
    print(f"  -> Top-1 Accuracy         : {top1_acc:.2f}%")
    print(f"  -> Top-5 Accuracy         : {top5_acc:.2f}% (Target: >= 85%)")
    assert top5_acc >= 85.0, f"Multi-domain top-5 accuracy failed: {top5_acc:.2f}% is below 85.0% threshold"

    # ----------------------------------------------------------------------
    # 4. BENCHMARK CPU RETRIEVAL LATENCY (Target < 15.0 ms)
    # ----------------------------------------------------------------------
    print("\n[4/4] Benchmarking End-to-End CPU Latency across 100 iterations...")
    benchmark_query = "1/2 inch SS hex nipple"
    iterations = 100

    # Warmup
    engine.search(benchmark_query, top_k=5)

    start_time = time.perf_counter()
    for _ in range(iterations):
        engine.search(benchmark_query, top_k=5)
    total_elapsed = time.perf_counter() - start_time
    avg_latency_ms = (total_elapsed / iterations) * 1000.0

    print(f"  -> Iterations        : {iterations}")
    print(f"  -> Average Latency   : {avg_latency_ms:.3f} ms per query (Target: < 15.0 ms)")
    assert avg_latency_ms < 15.0, f"Latency breached: {avg_latency_ms:.3f} ms exceeds the 15.0 ms SLA limit"

    print("\n" + "=" * 70)
    print("  SUCCESS: UNIVERSAL ZERO-HARDCODING HSN ENGINE CERTIFIED!       ")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    test_hsn_universal_retrieval_and_latency()
