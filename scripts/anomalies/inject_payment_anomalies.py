"""
Module: scripts/anomalies/inject_payment_anomalies.py
Description: Injects payment ledger and receipts anomalies (PR-65 to PR-69) 
such as duplicate receipts, unmatched payments, and amount discrepancies.
"""

import os
import sys
import random
import pandas as pd

def inject_payment_anomalies():
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass

    print("Starting payment ledger anomaly injection...")
    os.makedirs("data/raw/ledgers", exist_ok=True)
    os.makedirs("data/processed", exist_ok=True)

    receipts_path = "data/interim/receipts_clean.csv"
    if not os.path.exists(receipts_path):
        receipts_path = "data/raw/ledgers/receipts.csv"

    if os.path.exists(receipts_path):
        df_receipts = pd.read_csv(receipts_path)
    else:
        # Fallback dummy receipts if clean file isn't present
        df_receipts = pd.DataFrame([
            {"receipt_id": f"RCP-{i:04d}", "customer_id": f"CUST-{i:04d}", "invoice_ref": f"SAL-2024-{i:05d}", "receipt_date": "10-10-2024", "amount": 50000.0, "mode": "NEFT"}
            for i in range(1, 101)
        ])

    receipts_records = df_receipts.to_dict('records')
    anomaly_logs = []

    # Inject PR-65 to PR-69 anomalies into payment ledger
    # PR-65/66: Duplicate receipt entry
    if len(receipts_records) > 0:
        dup_rec = receipts_records[0].copy()
        dup_rec['receipt_id'] = "RCP-DUP-001"
        dup_rec['anomaly_tag'] = "PR-66"
        receipts_records.append(dup_rec)
        anomaly_logs.append({"anomaly_id": "PR-66", "row_id": dup_rec['receipt_id'], "description": "Duplicate payment receipt logged against invoice"})

    # PR-67: Amount mismatch between receipt and invoice total
    if len(receipts_records) > 1:
        receipts_records[1]['amount'] = receipts_records[1]['amount'] + 5000.0 # Mismatched amount
        receipts_records[1]['anomaly_tag'] = "PR-67"
        anomaly_logs.append({"anomaly_id": "PR-67", "row_id": receipts_records[1]['receipt_id'], "description": "Receipt amount exceeds invoice balance"})

    # PR-68: Unmatched receipt reference (phantom invoice ref)
    phantom_rec = {
        "receipt_id": "RCP-PHANTOM-01",
        "customer_id": "CUST-9999",
        "invoice_ref": "SAL-NONEXISTENT",
        "receipt_date": "15-11-2024",
        "amount": 25000.0,
        "mode": "Cheque",
        "anomaly_tag": "PR-68"
    }
    receipts_records.append(phantom_rec)
    anomaly_logs.append({"anomaly_id": "PR-68", "row_id": phantom_rec['receipt_id'], "description": "Receipt mapped to non-existent invoice reference"})

    df_final_receipts = pd.DataFrame(receipts_records)
    df_final_receipts.to_csv("data/raw/ledgers/receipts.csv", index=False)

    # Update anomaly log
    log_path = "data/processed/anomaly_log.csv"
    if os.path.exists(log_path):
        df_log = pd.read_csv(log_path)
        df_new_log = pd.DataFrame(anomaly_logs)
        df_combined = pd.concat([df_log, df_new_log], ignore_index=True)
        df_combined.to_csv(log_path, index=False)
    else:
        pd.DataFrame(anomaly_logs).to_csv(log_path, index=False)

    print(f"✓ Payment ledger anomalies injected successfully ({len(receipts_records)} total receipt records).")
    print("=== PAYMENT LEDGER INJECTION COMPLETE ===")

if __name__ == "__main__":
    inject_payment_anomalies()