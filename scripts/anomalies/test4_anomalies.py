"""
Module: tests/test_day4_anomalies.py
Description: Validates Day 4 anomaly injection counts, required fixed worked examples (A, B, C), 
and anomaly log entries.
"""

import os
import sys
import pandas as pd

def test_day4_anomalies():
    # Configure UTF-8 encoding for Windows console output
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass

    print("Running Day 4 anomaly validation tests...")
    
    # 1. Verify file paths and row counts
    files_to_check = {
        "data/raw/books/books_b2b.csv": 4000,
        "data/raw/books/books_b2ba.csv": 300,
        "data/raw/books/books_cdn.csv": 600,
        "data/raw/books/books_cdna.csv": 100
    }
    
    for filepath, expected_count in files_to_check.items():
        assert os.path.exists(filepath), f"Missing file: {filepath}"
        df = pd.read_csv(filepath)
        assert len(df) == expected_count, f"Row count mismatch for {filepath}: got {len(df)}, expected {expected_count}"
        print(f"✓ {os.path.basename(filepath)} row count check passed ({expected_count} rows).")

    # 2. Verify Fixed Worked Examples A, B, and C are present
    b2b_df = pd.read_csv("data/raw/books/books_b2b.csv")
    sales_df = pd.read_csv("data/raw/ledgers/sales_ledger.csv")
    
    # Check Example A (PR-01: Duplicate invoice or lines)
    assert any(b2b_df['invoice_no'].astype(str).str.contains("INV-EX-A", na=False)), "Fixed Worked Example A (PR-01) missing in B2B books!"
    print("✓ Fixed Worked Example A (PR-01) verified.")

    # Check Example B (PR-26: Blocked credit 'Car repair and servicing')
    blocked_credit_rows = b2b_df[b2b_df['description'].astype(str).str.contains("Car repair and servicing", case=False, na=False)]
    assert len(blocked_credit_rows) > 0, "Fixed Worked Example B (PR-26) missing in B2B books!"
    print("✓ Fixed Worked Example B (PR-26) verified.")

    # Check Example C (PR-65: Unpaid overdue invoice SAL-EX-C001)
    ex_c_rows = sales_df[sales_df['invoice_no'].astype(str) == "SAL-EX-C001"]
    assert len(ex_c_rows) > 0, "Fixed Worked Example C (PR-65) missing in sales ledger!"
    print("✓ Fixed Worked Example C (PR-65) verified.")

    # 3. Verify Anomaly Log exists and is populated
    log_path = "data/processed/anomaly_log.csv"
    assert os.path.exists(log_path), "Anomaly log file missing!"
    df_log = pd.read_csv(log_path)
    assert len(df_log) > 0, "Anomaly log is empty!"
    print(f"✓ Anomaly log verified with {len(df_log)} recorded anomaly entries.")

    print("=== ALL DAY 4 ANOMALY VALIDATION TESTS PASSED SUCCESSFULLY! ===")

if __name__ == "__main__":
    test_day4_anomalies()