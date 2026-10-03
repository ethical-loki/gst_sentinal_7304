"""
Module: scripts/anomalies/inject_recon_anomalies.py
Description: Generates GSTR-2B with realistic reconciliation anomalies (PR-70 to PR-76) 
targeting ~8-10% mismatch/omission rate to achieve a 90-92% reconciliation match rate.
"""

import os
import sys
import random
import pandas as pd

def inject_recon_anomalies():
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass

    print("Generating GSTR-2B with realistic reconciliation anomalies...")
    os.makedirs("data/raw/gstr2b", exist_ok=True)
    os.makedirs("data/processed", exist_ok=True)

    registry_path = "data/raw/masters/gstin_registry.csv"
    b2b_path = "data/raw/books/books_b2b.csv"
    
    if not os.path.exists(registry_path) or not os.path.exists(b2b_path):
        raise FileNotFoundError("Master registry or books_b2b file missing.")

    registry_df = pd.read_csv(registry_path)
    taxpayer_col = 'taxpayer_type' if 'taxpayer_type' in registry_df.columns else 'registration_type'
    gstin_col = 'vendor_gstin' if 'vendor_gstin' in registry_df.columns else 'gstin'
    comp_gstins = set(registry_df[registry_df[taxpayer_col].astype(str).str.upper() == 'COMPOSITION'][gstin_col])
    b2b_df = pd.read_csv(b2b_path)

    anomaly_logs = []

    # Base GSTR-2B excludes composition vendors
    gstr2b_df = b2b_df[~b2b_df['counter_party_gstin'].isin(comp_gstins)].copy()
    gstr2b_df['fp'] = gstr2b_df['fp'].astype(str)
    
    # We want ~8-10% of rows to have anomalies (omissions, value mismatches, period shifts)
    total_gstr2b_rows = len(gstr2b_df)
    anomaly_target_count = int(total_gstr2b_rows * 0.09) # ~9% anomalies
    
    anomaly_indices = random.sample(list(gstr2b_df.index), min(anomaly_target_count, total_gstr2b_rows))

    # Split anomalies into categories
    third = len(anomaly_indices) // 3
    omitted_indices = anomaly_indices[:third]
    value_mismatch_indices = anomaly_indices[third:2*third]
    period_shift_indices = anomaly_indices[2*third:]

    # 1. PR-70: Omitted invoices in GSTR-2B (including Example E)
    omitted_invoices = gstr2b_df.loc[omitted_indices, 'invoice_no'].tolist()
    gstr2b_df = gstr2b_df.drop(omitted_indices)
    for inv in omitted_invoices:
        anomaly_logs.append({"anomaly_id": "PR-70", "row_id": inv, "description": "Invoice present in books but omitted in GSTR-2B"})

    # 2. PR-71: Value Mismatches
    for idx in value_mismatch_indices:
        if idx in gstr2b_df.index:
            inv_no = gstr2b_df.loc[idx, 'invoice_no']
            gstr2b_df.loc[idx, 'taxable_val'] += 10000.0
            gstr2b_df.loc[idx, 'invoice_val'] += 11800.0
            anomaly_logs.append({"anomaly_id": "PR-71", "row_id": inv_no, "description": "Value mismatch between Books and GSTR-2B"})

    # 3. PR-75: Period shifts
    for idx in period_shift_indices:
        if idx in gstr2b_df.index:
            inv_no = gstr2b_df.loc[idx, 'invoice_no']
            gstr2b_df.loc[idx, 'fp'] = "082024" # Shifted period
            anomaly_logs.append({"anomaly_id": "PR-75", "row_id": inv_no, "description": "Tax period mismatch (shifted filing period in 2B)"})

    # Save modified GSTR-2B B2B file
    gstr2b_df.to_csv("data/raw/gstr2b/gstr2b_b2b.csv", index=False)
    
    # Copy other GSTR-2B sections
    for sec in ["b2ba", "cdnr", "cdnra"]:
        src = f"data/interim/gstr2b_{sec}.csv"
        dst = f"data/raw/gstr2b/gstr2b_{sec}.csv"
        if os.path.exists(src):
            pd.read_csv(src).to_csv(dst, index=False)

    # Update anomaly log
    log_path = "data/processed/anomaly_log.csv"
    df_log = pd.read_csv(log_path) if os.path.exists(log_path) else pd.DataFrame()
    df_new_log = pd.DataFrame(anomaly_logs)
    pd.concat([df_log, df_new_log], ignore_index=True).to_csv(log_path, index=False)

    print(f"✓ GSTR-2B recon anomalies injected: {len(omitted_invoices)} omitted, {len(value_mismatch_indices)} value mismatches, {len(period_shift_indices)} period shifts.")
    print("=== STEP 2 RECON ANOMALIES COMPLETE ===")

if __name__ == "__main__":
    inject_recon_anomalies()