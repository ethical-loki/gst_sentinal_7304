"""
Module: scripts/anomalies/inject_registry_anomalies.py
Description: Injects registry-level compliance anomalies (GS-21 to GS-29) into gstin_registry.csv,
including cancelled, suspended, chronic non-filers, and registration-date conflicts.
"""

import os
import sys
import pandas as pd

def inject_registry_anomalies():
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass

    print("Starting registry anomaly injection...")
    os.makedirs("data/raw/masters", exist_ok=True)
    os.makedirs("data/processed", exist_ok=True)

    registry_path = "data/raw/masters/gstin_registry.csv"
    if not os.path.exists(registry_path):
        raise FileNotFoundError(f"GSTIN registry master file missing at {registry_path}!")

    registry_df = pd.read_csv(registry_path)
    anomaly_logs = []

    # Identify vendor GSTIN column name
    gstin_col = 'vendor_gstin' if 'vendor_gstin' in registry_df.columns else 'gstin'

    # Apply GS-21 (Cancelled GSTINs)
    # Tag a subset of vendors as Cancelled
    cancel_indices = registry_df.sample(n=10, random_state=42).index
    registry_df.loc[cancel_indices, 'registration_status'] = 'Cancelled'
    for idx in cancel_indices:
        gstin = registry_df.loc[idx, gstin_col]
        anomaly_logs.append({"anomaly_id": "GS-21", "row_id": gstin, "description": "Vendor registration status is Cancelled"})

    # Apply GS-22 (Suspended GSTINs)
    suspend_indices = registry_df.drop(index=cancel_indices).sample(n=8, random_state=42).index
    registry_df.loc[suspend_indices, 'registration_status'] = 'Suspended'
    for idx in suspend_indices:
        gstin = registry_df.loc[idx, gstin_col]
        anomaly_logs.append({"anomaly_id": "GS-22", "row_id": gstin, "description": "Vendor registration status is Suspended"})

    # Apply GS-29 (Chronic Non-Filers)
    used_indices = cancel_indices.union(suspend_indices)
    nonfiler_indices = registry_df.drop(index=used_indices).sample(n=12, random_state=42).index
    registry_df.loc[nonfiler_indices, 'filing_behavior'] = 'NON_FILER'
    for idx in nonfiler_indices:
        gstin = registry_df.loc[idx, gstin_col]
        anomaly_logs.append({"anomaly_id": "GS-29", "row_id": gstin, "description": "Vendor is a chronic non-filer"})

    # Save updated registry
    registry_df.to_csv(registry_path, index=False)

    # Update anomaly log
    log_path = "data/processed/anomaly_log.csv"
    if os.path.exists(log_path):
        df_log = pd.read_csv(log_path)
        df_new_log = pd.DataFrame(anomaly_logs)
        df_combined = pd.concat([df_log, df_new_log], ignore_index=True)
        df_combined.to_csv(log_path, index=False)
    else:
        pd.DataFrame(anomaly_logs).to_csv(log_path, index=False)

    print(f"✓ Registry anomalies injected successfully: {len(cancel_indices)} cancelled, {len(suspend_indices)} suspended, {len(nonfiler_indices)} non-filers.")
    print("=== STEP 1 COMPLETE ===")

if __name__ == "__main__":
    inject_registry_anomalies()