import sys
import time
from pathlib import Path
import numpy as np
import pandas as pd
import torch

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.nlp.hsn_search import HSNSemanticSearchEngine


def test_day_05_encoder_and_retrieval():
    print("\n" + "=" * 65)
    print("      DAY 05 BENCHMARK: CONTRASTIVE HSN ENCODER & SEARCH       ")
    print("=" * 65 + "\n")

    # ----------------------------------------------------------------------
    # 1. VERIFY REQUIRED ARTIFACTS
    # ----------------------------------------------------------------------
    print("[1/3] Verifying Generated Artifacts...")
    tariff_parquet = ROOT_DIR / "data" / "tariff_master.parquet"
    model_weights = ROOT_DIR / "models" / "hsn_contrastive_mlp.pt"
    vector_index = ROOT_DIR / "data" / "tariff_vector_index.npy"

    assert tariff_parquet.exists(), f"Missing artifact: {tariff_parquet}"
    assert model_weights.exists(), f"Missing artifact: {model_weights}"
    assert vector_index.exists(), f"Missing artifact: {vector_index}"

    df_tariff = pd.read_parquet(tariff_parquet)
    index_matrix = np.load(vector_index)

    assert len(df_tariff) > 0, "Tariff master parquet is empty!"
    assert (
        index_matrix.ndim == 2 and index_matrix.shape[1] == 128
    ), f"Expected index shape (N, 128), got {index_matrix.shape}"
    assert (
        len(df_tariff) == index_matrix.shape[0]
    ), f"Mismatch: {len(df_tariff)} tariff rows vs {index_matrix.shape[0]} vector rows"

    # Verify unit-sphere normalization (L2 norm ~ 1.0)
    norms = np.linalg.norm(index_matrix[:50], axis=1)
    assert np.allclose(norms, 1.0, atol=1e-3), "Indexed vectors are not L2-normalized!"
    print(f"  -> Tariff parquet verified: {len(df_tariff):,} statutory entries.")
    print(f"  -> Vector index matrix verified: shape {index_matrix.shape}.")
    print("  -> Model weights loaded and L2 hypersphere normalization confirmed.")

    # ----------------------------------------------------------------------
    # 2. EVALUATE TOP-5 RETRIEVAL ACCURACY (Target >= 85%)
    # ----------------------------------------------------------------------
    print("\n[2/3] Evaluating Top-5 Accuracy on Commercial Slang Descriptions...")
    engine = HSNSemanticSearchEngine(
        tariff_parquet_path=str(tariff_parquet),
        model_path=str(model_weights),
        index_path=str(vector_index),
    )

    # Ground-truth test evaluation suite (Trade jargon, abbreviations, specs)
    test_eval_set = [
        {"desc": "1/2 inch SS hex nipple", "expected_hsn_prefix": "7307"},
        {"desc": "SS welded pipe 25mm dia 2mm thk", "expected_hsn_prefix": "7306"},
        {"desc": "MS seamless hydraulic tube", "expected_hsn_prefix": "7304"},
        {"desc": "industrial 2-piece ball valve 1 inch BSP", "expected_hsn_prefix": "8481"},
        {"desc": "allen cap screw M12 x 50 grade 8.8", "expected_hsn_prefix": "7318"},
        {"desc": "hex head bolt with nylon nut", "expected_hsn_prefix": "7318"},
        {"desc": "uPVC elbow 90 degree solvent weld", "expected_hsn_prefix": "3917"},
        {"desc": "copper flexible power cable 3 core 2.5 sq mm", "expected_hsn_prefix": "8544"},
        {"desc": "FR PVC insulated industrial wiring copper", "expected_hsn_prefix": "8544"},
        {"desc": "solar on grid inverter 5kw 3 phase", "expected_hsn_prefix": "8504"},
        {"desc": "SMPS 24V 5A power supply industrial", "expected_hsn_prefix": "8504"},
        {"desc": "GI reducing bush 1 inch to 1/2 inch", "expected_hsn_prefix": "7307"},
        {"desc": "cast iron non return check valve 50mm", "expected_hsn_prefix": "8481"},
        {"desc": "HDPE coil pipe 63mm 6kg pressure", "expected_hsn_prefix": "3917"},
        {"desc": "spring lock washer zinc plated M10", "expected_hsn_prefix": "7318"},
        {"desc": "flange class 150 slip on forged steel", "expected_hsn_prefix": "7307"},
        {"desc": "dry type isolation transformer 10 kva", "expected_hsn_prefix": "8504"},
        {"desc": "armoured aluminum cable 4C x 16 sq mm", "expected_hsn_prefix": "8544"},
        {"desc": "SS 304 socket weld tee connector", "expected_hsn_prefix": "7307"},
        {"desc": "needle valve 6000 psi SS body", "expected_hsn_prefix": "8481"},
    ]

    top1_hits = 0
    top5_hits = 0
    total_samples = len(test_eval_set)

    for item in test_eval_set:
        query = item["desc"]
        target = item["expected_hsn_prefix"]
        results = engine.search(query, top_k=5)
        matched_prefixes = [str(r["hsn"])[: len(target)] for r in results]

        if target == matched_prefixes[0]:
            top1_hits += 1
        if target in matched_prefixes:
            top5_hits += 1

    top1_acc = (top1_hits / total_samples) * 100.0
    top5_acc = (top5_hits / total_samples) * 100.0

    print(f"  -> Evaluation Samples : {total_samples}")
    print(f"  -> Top-1 Accuracy    : {top1_acc:.2f}%")
    print(f"  -> Top-5 Accuracy    : {top5_acc:.2f}% (Target: >= 85%)")
    assert (
        top5_acc >= 85.0
    ), f"Top-5 accuracy failed: {top5_acc:.2f}% is below 85.0% threshold"

    # ----------------------------------------------------------------------
    # 3. BENCHMARK RETRIEVAL LATENCY (Target < 15 ms on CPU)
    # ----------------------------------------------------------------------
    print("\n[3/3] Benchmarking End-to-End Search Latency on CPU...")
    benchmark_query = "1/2 inch SS hex nipple"
    iterations = 100

    # Warmup pass
    engine.search(benchmark_query, top_k=5)

    start_time = time.perf_counter()
    for _ in range(iterations):
        engine.search(benchmark_query, top_k=5)
    total_elapsed = time.perf_counter() - start_time
    avg_latency_ms = (total_elapsed / iterations) * 1000.0

    print(f"  -> Iterations        : {iterations}")
    print(f"  -> Average Latency   : {avg_latency_ms:.3f} ms per query (Target: < 15.0 ms)")
    assert (
        avg_latency_ms < 15.0
    ), f"Latency breached: {avg_latency_ms:.3f} ms exceeds the 15 ms SLA limit"

    # ----------------------------------------------------------------------
    # FINAL VERIFICATION CERTIFICATE
    # ----------------------------------------------------------------------
    print("\n" + "=" * 65)
    print("  SUCCESS: DAY 05 CONTRASTIVE ENCODER IS FULLY CERTIFIED!")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    test_day_05_encoder_and_retrieval()