"""
Day 05 Test Suite: tests/test_day_5.py
Automated acceptance criteria verification for In-House Contrastive Semantic HSN Text Encoder:
1. Artifact Verification: Confirm existence and schema validity of
   - data/tariff_master.parquet
   - models/hsn_contrastive_mlp.pt
   - data/tariff_vector_index.npy
2. Latency SLA: Full inference pipeline (Hashing -> PyTorch MLP -> Top-5 Cosine dot product)
   must execute in < 15 ms per line item on CPU.
3. Accuracy SLA: Top-5 HSN retrieval accuracy on the held-out description validation set
   must achieve >= 85%.
"""

import os
import sys
import time
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
import torch

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.models.tokenizer import FeatureHashingTokenizer
from src.models.hsn_encoder import HSNContrastiveMLP
from src.nlp.hsn_search import HSNSearchEngine

TARIFF_PARQUET = ROOT_DIR / "data" / "tariff_master.parquet"
MODEL_PATH = ROOT_DIR / "models" / "hsn_contrastive_mlp.pt"
VECTOR_INDEX_NPY = ROOT_DIR / "data" / "tariff_vector_index.npy"
VAL_PARQUET = ROOT_DIR / "data" / "val.parquet"


def test_artifact_verification():
    """Confirms existence and schema validity of all Day 5 model and index artifacts."""
    print("\n[1/3] Verifying Day 5 Artifacts...")

    # 1. Verify data/tariff_master.parquet
    assert TARIFF_PARQUET.exists(), f"Tariff master missing: {TARIFF_PARQUET}"
    tariff_df = pd.read_parquet(TARIFF_PARQUET)
    assert len(tariff_df) >= 1000, f"Expected >= 1000 tariff records, found {len(tariff_df)}"

    expected_cols = {
        "hsn_code", "hsn_4digit", "chapter", "description",
        "clean_description", "standard_rate", "is_blocked_17_5",
        "blocked_17_5_reason", "effective_date"
    }
    missing_cols = expected_cols - set(tariff_df.columns)
    assert not missing_cols, f"Missing columns in tariff master: {missing_cols}"
    print(f"  [OK] tariff_master.parquet validated ({len(tariff_df)} records, {len(tariff_df.columns)} columns)")

    # 2. Verify models/hsn_contrastive_mlp.pt
    assert MODEL_PATH.exists(), f"Model weights missing: {MODEL_PATH}"
    state_dict = torch.load(MODEL_PATH, map_location="cpu")
    model = HSNContrastiveMLP(input_dim=32768, hidden_dim=512, output_dim=128)
    model.load_state_dict(state_dict)
    model.eval()
    print("  [OK] hsn_contrastive_mlp.pt loaded into 32768->512->128 MLP successfully")

    # 3. Verify data/tariff_vector_index.npy
    assert VECTOR_INDEX_NPY.exists(), f"Vector index missing: {VECTOR_INDEX_NPY}"
    index_matrix = np.load(VECTOR_INDEX_NPY)
    assert index_matrix.ndim == 2, f"Expected 2D index matrix, got shape {index_matrix.shape}"
    assert index_matrix.shape[1] == 128, f"Expected 128 embedding dim, got {index_matrix.shape[1]}"
    assert index_matrix.shape[0] == len(tariff_df), (
        f"Index row count {index_matrix.shape[0]} does not match tariff master {len(tariff_df)}"
    )

    # Unit hypersphere check: ||z||_2 == 1.0
    norms = np.linalg.norm(index_matrix, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-3), "Vector index rows must lie on the unit hypersphere!"
    print(f"  [OK] tariff_vector_index.npy validated ({index_matrix.shape[0]} x {index_matrix.shape[1]} unit vectors)")


def test_latency_sla():
    """Confirms inference pipeline executes in < 15ms per line item on CPU."""
    print("\n[2/3] Benchmarking Latency SLA (< 15 ms on CPU)...")
    search_engine = HSNSearchEngine(
        tariff_path=TARIFF_PARQUET,
        index_path=VECTOR_INDEX_NPY,
        model_path=MODEL_PATH
    )

    sample_queries = [
        "SS 304 Flange 25mm Class 150 Industrial Fitting",
        "Centrifugal water pump 5HP with electric motor",
        "Live horses for breeding and racing",
        "Cotton woven fabric plain dyed 180 GSM",
        "Polyvinyl chloride PVC rigid conduit pipe 20mm",
        "Hydraulic check valve 1/2 inch BSP threaded",
        "Portland slag cement 50kg bag Grade 53",
        "Electric transformer 11kV to 415V 500kVA",
        "Articles of vulcanized rubber gasket seal",
        "Roasted arabica coffee beans grounded"
    ] * 10  # 100 test iterations

    latencies = []
    # Warmup
    _ = search_engine.search("Warmup test query", top_k=5)

    for q in sample_queries:
        res = search_engine.search(q, top_k=5)
        lat = res["latency_ms"]
        latencies.append(lat)
        assert len(res["matches"]) > 0, f"No matches found for query: {q}"

    avg_latency = float(np.mean(latencies))
    p95_latency = float(np.percentile(latencies, 95))
    max_latency = float(np.max(latencies))

    print(f"  [METRIC] Mean Latency   : {avg_latency:.2f} ms")
    print(f"  [METRIC] P95 Latency    : {p95_latency:.2f} ms")
    print(f"  [METRIC] Max Latency    : {max_latency:.2f} ms")
    print(f"  [TARGET] SLA Threshold  : < 15.00 ms")

    assert avg_latency < 15.0, f"Average latency {avg_latency:.2f} ms breached SLA threshold of 15.0 ms!"
    assert p95_latency < 15.0, f"P95 latency {p95_latency:.2f} ms breached SLA threshold of 15.0 ms!"
    print("  [OK] Latency SLA strictly satisfied (< 15 ms).")


def test_accuracy_sla():
    """Confirms Top-5 HSN retrieval accuracy on held-out descriptions achieves >= 85%."""
    print("\n[3/3] Evaluating Top-5 Retrieval Accuracy SLA (>= 85%)...")
    search_engine = HSNSearchEngine(
        tariff_path=TARIFF_PARQUET,
        index_path=VECTOR_INDEX_NPY,
        model_path=MODEL_PATH
    )

    assert VAL_PARQUET.exists(), f"Validation parquet missing: {VAL_PARQUET}"
    val_df = pd.read_parquet(VAL_PARQUET)

    # Sample representative evaluation items
    eval_candidates = []
    for _, row in val_df.iterrows():
        desc = str(row.get("product_description", "")).strip()
        true_hsn = str(row.get("true_hsn", "")).strip()
        if desc and true_hsn and true_hsn.lower() != "nan" and len(desc) >= 5:
            # Clean ground truth HSN
            h_clean = "".join(filter(str.isdigit, true_hsn))
            if len(h_clean) >= 2:
                if len(h_clean) in (3, 5, 7):
                    h_clean = "0" + h_clean
                eval_candidates.append({
                    "query": desc,
                    "true_hsn": h_clean,
                    "true_4digit": h_clean[:4] if len(h_clean) >= 4 else h_clean.zfill(4)
                })

    # Evaluate on held-out sample (at least 300 items)
    sample_size = min(400, len(eval_candidates))
    np.random.seed(42)
    sample_eval = np.random.choice(eval_candidates, size=sample_size, replace=False)

    hits_top1 = 0
    hits_top5 = 0

    for item in sample_eval:
        res = search_engine.search(item["query"], top_k=5)
        matches = res["matches"]

        cand_codes = [m["hsn_code"] for m in matches]
        cand_4digits = [m["hsn_4digit"] for m in matches]

        target_code = item["true_hsn"]
        target_4d = item["true_4digit"]

        # Check Top-1
        if matches:
            top_m = matches[0]
            if top_m["hsn_code"] == target_code or top_m["hsn_4digit"] == target_4d:
                hits_top1 += 1

        # Check Top-5: exact code match OR 4-digit heading match
        is_hit = False
        for m in matches:
            if m["hsn_code"] == target_code or m["hsn_4digit"] == target_4d:
                is_hit = True
                break
            if len(target_code) >= 4 and m["hsn_code"].startswith(target_4d):
                is_hit = True
                break

        if is_hit:
            hits_top5 += 1

    top1_acc = (hits_top1 / sample_size) * 100.0
    top5_acc = (hits_top5 / sample_size) * 100.0

    print(f"  [METRIC] Evaluated Samples : {sample_size}")
    print(f"  [METRIC] Top-1 Accuracy    : {top1_acc:.2f}%")
    print(f"  [METRIC] Top-5 Accuracy    : {top5_acc:.2f}%")
    print(f"  [TARGET] SLA Threshold     : >= 85.00%")

    assert top5_acc >= 85.0, f"Top-5 retrieval accuracy {top5_acc:.2f}% failed to achieve required 85.0% SLA!"
    print("  [OK] Accuracy SLA strictly satisfied (>= 85%).")


if __name__ == "__main__":
    test_artifact_verification()
    test_latency_sla()
    test_accuracy_sla()
