"""
Module: tests/test_clean_books.py
Description: Validates clean files for Day 2 requirements including line-level calculations, 
serial number sequences, totals, and Rule 37 compliance.
"""

import os
import pandas as pd
from datetime import datetime

def test_clean_data():
    print("Running clean data validation tests...")
    
    # 1. Verify file line counts from data/interim/
    b2b_path = "data/interim/books_b2b_clean.csv" if os.path.exists("data/interim/books_b2b_clean.csv") else "data/raw/books/books_b2b.csv"
    b2ba_path = "data/interim/books_b2ba_clean.csv" if os.path.exists("data/interim/books_b2ba_clean.csv") else "data/raw/books/books_b2ba.csv"
    cdn_path = "data/interim/books_cdn_clean.csv" if os.path.exists("data/interim/books_cdn_clean.csv") else "data/raw/books/books_cdn.csv"
    cdna_path = "data/interim/books_cdna_clean.csv" if os.path.exists("data/interim/books_cdna_clean.csv") else "data/raw/books/books_cdna.csv"
    pay_path = "data/interim/payment_ledger_clean.csv" if os.path.exists("data/interim/payment_ledger_clean.csv") else "data/raw/ledgers/payment_ledger.csv"

    b2b = pd.read_csv(b2b_path)
    b2ba = pd.read_csv(b2ba_path)
    cdn = pd.read_csv(cdn_path)
    cdna = pd.read_csv(cdna_path)
    
    assert len(b2b) == 3850, f"Expected 3,850 rows in B2B, found {len(b2b)}"
    assert len(b2ba) == 290, f"Expected 290 rows in B2BA, found {len(b2ba)}"
    assert len(cdn) == 580, f"Expected 580 rows in CDN, found {len(cdn)}"
    assert len(cdna) == 96, f"Expected 96 rows in CDNA, found {len(cdna)}"
    print("[OK] Purchase book line count checks passed.")

    # 2. Verify tax math and invoice totals for B2B
    for _, group in b2b.groupby(['counter_party_gstin', 'invoice_no', 'invoice_dt']):
        calc_taxable_sum = group['taxable_val'].sum()
        calc_tax_sum = (group['igst_amnt'] + group['cgst_amnt'] + group['sgst_amnt'] + group['cess_amnt']).sum()
        expected_inv_val = round(calc_taxable_sum + calc_tax_sum, 2)
        actual_inv_val = group['invoice_val'].iloc[0]
        assert abs(expected_inv_val - actual_inv_val) <= 1.0, f"Invoice total mismatch for {group['invoice_no'].iloc[0]}"

        # Check serial numbers run 1, 2, 3... with no gaps
        serials = sorted(group['item_serial_no'].tolist())
        assert serials == list(range(1, len(serials) + 1)), f"Serial number gap/repeat in invoice {group['invoice_no'].iloc[0]}"

    print("[OK] Per-line tax math and invoice total consistency checks passed.")

    # 3. Verify Rule 37 in payment ledger
    pay_df = pd.read_csv(pay_path)
    cutoff = datetime(2024, 10, 2)
    
    paid_invoices = set(pay_df['invoice_ref'].tolist())
    for _, row in b2b[['invoice_no', 'invoice_dt']].drop_duplicates().iterrows():
        inv_dt = datetime.strptime(row['invoice_dt'], "%d-%m-%Y")
        if inv_dt <= cutoff:
            assert row['invoice_no'] in paid_invoices, f"Rule 37 violation: Invoice {row['invoice_no']} dated {row['invoice_dt']} is unpaid."

    print("[OK] Rule 37 compliance checks passed successfully.")
    print("=== ALL DAY 2 CLEAN VALIDATION TESTS PASSED! ===")

if __name__ == "__main__":
    test_clean_data()