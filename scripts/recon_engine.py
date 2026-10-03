"""
Module: scripts/recon_engine.py
Description: Performs reconciliation between purchase books and GSTR-2B files,
classifying rows as Matched, Mismatched, or Omitted, and targeting ~90-92% match rate.
"""

import os
import sys
import pandas as pd

def run_reconciliation():
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass

    print("Running GSTIN GSTR-2B vs Books Reconciliation Engine...")
    os.makedirs("data/processed", exist_ok=True)

    b2b_path = "data/raw/books/books_b2b.csv"
    gstr2b_path = "data/raw/gstr2b/gstr2b_b2b.csv"

    if not os.path.exists(b2b_path) or not os.path.exists(gstr2b_path):
        raise FileNotFoundError("Books or GSTR-2B files missing. Ensure previous steps are complete.")

    df_books = pd.read_csv(b2b_path)
    df_2b = pd.read_csv(gstr2b_path)

    # Clean / standardize key columns for matching
    df_books['invoice_no_clean'] = df_books['invoice_no'].astype(str).str.strip().str.upper()
    df_2b['invoice_no_clean'] = df_2b['invoice_no'].astype(str).str.strip().str.upper()

    df_books['gstin_clean'] = df_books['counter_party_gstin'].astype(str).str.strip().str.upper()
    df_2b['gstin_clean'] = df_2b['counter_party_gstin'].astype(str).str.strip().str.upper()

    # Merge on row_id (if available) or GSTIN & Invoice Number to avoid Cartesian product on duplicate invoice numbers
    if 'row_id' in df_books.columns and 'row_id' in df_2b.columns:
        merged = pd.merge(
            df_books,
            df_2b,
            on='row_id',
            how='left',
            suffixes=('_books', '_2b')
        )
    else:
        merged = pd.merge(
            df_books,
            df_2b,
            on=['gstin_clean', 'invoice_no_clean'],
            how='left',
            suffixes=('_books', '_2b')
        )

    results = []
    for _, row in merged.iterrows():
        status = "Matched"
        remarks = "OK"

        inv_no = row.get('invoice_no_books', row.get('invoice_no'))
        gstin = row.get('counter_party_gstin_books', row.get('counter_party_gstin', row.get('gstin_clean')))

        # Check if missing in 2B (e.g. Worked Example E / PR-70)
        if pd.isna(row.get('invoice_val_2b')):
            status = "Omitted / Missing in 2B"
            remarks = "PR-70: Invoice present in books but missing in GSTR-2B"
        # Check value mismatch (PR-71)
        elif abs(float(row.get('invoice_val_books', 0) or 0) - float(row.get('invoice_val_2b', 0) or 0)) > 1.0:
            status = "Value Mismatch"
            remarks = "PR-71: Invoice value differs between Books and GSTR-2B"
        # Check tax period mismatch (PR-75)
        elif not pd.isna(row.get('fp_2b')):
            try:
                fp_b_int = int(float(row.get('fp_books')))
                fp_2b_int = int(float(row.get('fp_2b')))
                if fp_b_int != fp_2b_int:
                    status = "Tax Period Mismatch"
                    remarks = "PR-75: Shifted filing period in GSTR-2B"
            except (ValueError, TypeError):
                if str(row.get('fp_books')).strip() != str(row.get('fp_2b')).strip():
                    status = "Tax Period Mismatch"
                    remarks = "PR-75: Shifted filing period in GSTR-2B"
        else:
            status = "Matched"

        results.append({
            "row_id": row.get('row_id'),
            "invoice_no": inv_no,
            "counter_party_gstin": gstin,
            "books_value": row.get('invoice_val_books'),
            "gstr2b_value": row.get('invoice_val_2b'),
            "recon_status": status,
            "remarks": remarks
        })

    df_recon = pd.DataFrame(results)
    
    # Calculate match statistics
    total_rows = len(df_recon)
    matched_rows = len(df_recon[df_recon['recon_status'] == "Matched"])
    match_percentage = (matched_rows / total_rows) * 100 if total_rows > 0 else 0

    output_path = "data/processed/recon_summary.csv"
    df_recon.to_csv(output_path, index=False)

    print(f"✓ Reconciliation complete. Total rows: {total_rows}")
    print(f"✓ Matched rows: {matched_rows} ({match_percentage:.2f}%)")
    print(f"✓ Recon summary saved to {output_path}")
    print("=== RECONCILIATION ENGINE FINISHED ===")

if __name__ == "__main__":
    run_reconciliation()