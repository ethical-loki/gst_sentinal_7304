import sys
import time
from pathlib import Path
import numpy as np
import pandas as pd

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.nlp.preprocessor import DynamicHSNMasterEngine, compute_shannon_entropy
from src.rules_engine import StatutoryRulesEngine, verify_gstin_checksum


def run_master_integration_suite():
    print("\n" + "=" * 65)
    print("       GST SENTINEL: MASTER END-TO-END INTEGRATION TEST       ")
    print("=" * 65 + "\n")

    # -------------------------------------------------------------
    # 1. TEST PREPROCESSOR & SHANNON ENTROPY GATE (Day 02 / Day 03)
    # -------------------------------------------------------------
    print("[1/3] Testing Dynamic HSN Master & Text Quality Gate...")
    hsn_master_path = ROOT_DIR / "data" / "raw" / "Final_hsn_sac_copy.xlsx"
    engine_master = DynamicHSNMasterEngine(hsn_excel_path=str(hsn_master_path))
    
    assert len(engine_master.valid_hsn_set) > 0, "HSN Master failed to load any records!"

    # Shannon Entropy Checks
    clean_desc = "Cold rolled stainless steel tubes 25mm"
    repetitive_garbage = "XXXXXXXXXXXXXXXXXXXXXX"
    symbols_garbage = "@#$%^&!~_+|}{<>?:"

    entropy_clean = compute_shannon_entropy(clean_desc)
    entropy_rep = compute_shannon_entropy(repetitive_garbage)

    assert entropy_rep == 0.0, f"Repetitive text entropy expected 0.0, got {entropy_rep}"
    assert (
        engine_master.entropy_lower_bound <= entropy_clean <= engine_master.entropy_upper_bound
    ), "Clean description unexpectedly fell outside safe entropy zone!"

    print("  -> Dynamic HSN Master verified.")
    print(f"  -> Shannon Entropy Safe Zone [{engine_master.entropy_lower_bound:.2f} - {engine_master.entropy_upper_bound:.2f}] verified.")

    # -------------------------------------------------------------
    # 2. TEST PARTITION INTEGRITY & ZERO-LEAKAGE (Day 03)
    # -------------------------------------------------------------
    print("\n[2/3] Testing Dataset Partitions, Stratification & Leakage...")
    train_path = ROOT_DIR / "data" / "train.parquet"
    val_path = ROOT_DIR / "data" / "val.parquet"
    test_path = ROOT_DIR / "data" / "test.parquet"

    assert train_path.exists() and val_path.exists() and test_path.exists(), (
        "Parquet split files missing! Run scripts/split_corpus.py first."
    )

    train_df = pd.read_parquet(train_path)
    val_df = pd.read_parquet(val_path)
    test_df = pd.read_parquet(test_path)

    # Size Verification (8,400 / 1,800 / 1,800)
    assert len(train_df) == 8400, f"Expected 8400 train rows, found {len(train_df)}"
    assert len(val_df) == 1800, f"Expected 1800 val rows, found {len(val_df)}"
    assert len(test_df) == 1800, f"Expected 1800 test rows, found {len(test_df)}"

    # Zero ID Leakage Verification
    train_ids = set(train_df["line_item_id"])
    val_ids = set(val_df["line_item_id"])
    test_ids = set(test_df["line_item_id"])

    assert len(train_ids.intersection(val_ids)) == 0, "Data leakage: Train & Val share line_item_id!"
    assert len(train_ids.intersection(test_ids)) == 0, "Data leakage: Train & Test share line_item_id!"
    assert len(val_ids.intersection(test_ids)) == 0, "Data leakage: Val & Test share line_item_id!"

    # Stratification Verification across error classes
    train_dist = train_df["error_type"].value_counts(normalize=True).sort_index()
    val_dist = val_df["error_type"].value_counts(normalize=True).sort_index()
    test_dist = test_df["error_type"].value_counts(normalize=True).sort_index()

    assert np.allclose(train_dist.values, val_dist.values, atol=0.01), "Train vs Val stratification skewed!"
    assert np.allclose(train_dist.values, test_dist.values, atol=0.01), "Train vs Test stratification skewed!"

    # Prior Feature Check
    assert "seller_hsn_prior" in train_df.columns, "seller_hsn_prior missing from features!"
    print("  -> 70/15/15 row distribution verified (8,400 / 1,800 / 1,800).")
    print("  -> Zero cross-partition ID leakage confirmed.")
    print("  -> Stratified anomaly distributions confirmed within <1% margin.")

    # -------------------------------------------------------------
    # 3. TEST DETERMINISTIC STATUTORY RULES ENGINE (Day 04)
    # -------------------------------------------------------------
    print("\n[3/3] Testing Statutory Rules Engine (RULE_01 to RULE_04)...")
    rules_engine = StatutoryRulesEngine(config_path=str(ROOT_DIR / "config" / "statutory_rules.yaml"))

    # Baseline Compliant Invoice
    clean_sample = {
        "invoice_id": "INV_TEST_001",
        "line_item_id": "L1",
        "supplier_gstin": "27AABCU9603R1ZN",  # Valid checksum
        "recipient_gstin": "27BBBPS1234K1Z0",
        "supplier_state": "27",
        "declared_pos": "27",
        "declared_hsn": "7306",
        "quantity": 10.0,
        "item_taxable_value": 10000.0,
        "declared_effective_rate": 18.0,
        "cgst_amount": 900.0,
        "sgst_amount": 900.0,
        "igst_amount": 0.0,
    }

    # Zero False Positive Check
    clean_violations = rules_engine.evaluate(clean_sample)
    assert len(clean_violations) == 0, f"False positive on clean record: {clean_violations}"

    # RULE_01: Missing Mandatory Field
    r1_sample = clean_sample.copy()
    r1_sample["recipient_gstin"] = ""
    assert "RULE_01_MISSING_RECIPIENT_GSTIN" in rules_engine.evaluate(r1_sample), "RULE_01 failed to detect blank field!"

    # RULE_02: POS Interstate Mismatch
    r2_sample = clean_sample.copy()
    r2_sample["declared_pos"] = "29"  # Inter-state POS with CGST/SGST declared
    assert "RULE_02_INTER_STATE_WITH_CGST_SGST" in rules_engine.evaluate(r2_sample), "RULE_02 failed on inter-state POS mismatch!"

    # RULE_03: Arithmetic Discrepancy > ₹0.05
    r3_sample = clean_sample.copy()
    r3_sample["cgst_amount"] = 900.10  # ₹0.10 discrepancy
    assert "RULE_03_ARITHMETIC_VARIANCE_EXCEEDED" in rules_engine.evaluate(r3_sample), "RULE_03 failed to catch rounding breach!"

    # RULE_04: Modulo-36 GSTIN Checksum
    r4_sample = clean_sample.copy()
    r4_sample["supplier_gstin"] = "27AABCU9603R1ZX"  # Invalid check character
    assert "RULE_04_INVALID_GSTIN_CHECKSUM" in rules_engine.evaluate(r4_sample), "RULE_04 failed to detect invalid check digit!"
    assert verify_gstin_checksum("27AABCU9603R1ZN") is True, "Checksum validator failed on valid GSTIN!"
    assert verify_gstin_checksum("27AABCU9603R1ZX") is False, "Checksum validator passed corrupted GSTIN!"

    # Latency Benchmark (<0.1 ms / line item)
    iterations = 2000
    start_time = time.perf_counter()
    for _ in range(iterations):
        rules_engine.evaluate(clean_sample)
    latency_ms = ((time.perf_counter() - start_time) / iterations) * 1000

    print(f"  -> RULE_01, RULE_02, RULE_03, and RULE_04: 100% detection verified.")
    print(f"  -> Evaluation Latency: {latency_ms:.4f} ms per record (SLA Target: <0.1 ms).")
    assert latency_ms < 0.1, f"Latency SLA breached: {latency_ms:.4f} ms exceeds 0.1 ms"

    # -------------------------------------------------------------
    # FINAL PASS CONFIRMATION
    # -------------------------------------------------------------
    print("\n" + "=" * 65)
    print("  ALL SYSTEMS OPERATIONAL: DAYS 01 THROUGH 04 ARE FULLY CERTIFIED! ")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    run_master_integration_suite()