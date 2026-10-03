"""
Module: scripts/anomalies/inject_receivables_anomalies.py
Description: Injects receivables anomalies into the sales ledger, setting up 3-5 recurring 
defaulters, late payers (10-45 days), accurate ageing buckets as of 31-03-2025, 
and Fixed Worked Example C (PR-65).
"""

import os
import sys
import random
import pandas as pd
from datetime import datetime, timedelta

def inject_receivables_anomalies():
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass

    print("Starting comprehensive receivables anomaly injection...")
    os.makedirs("data/raw/ledgers", exist_ok=True)
    os.makedirs("data/processed", exist_ok=True)

    sales_path = "data/interim/sales_ledger_clean.csv"
    if not os.path.exists(sales_path):
        sales_path = "data/raw/ledgers/sales_ledger.csv"
        
    if not os.path.exists(sales_path):
        raise FileNotFoundError("Sales ledger not found. Please ensure clean sales data exists first.")

    df_sales = pd.read_csv(sales_path)
    sales_records = df_sales.to_dict('records')

    # 1. Define 4 specific recurring defaulters
    recurring_defaulters = ["CUST-0012", "CUST-0045", "CUST-0088", "CUST-0104"]

    # 2. Inject Fixed Worked Example C (PR-65: ₹80,000 taxable, dated 23-08-2024, unpaid, ~220 days old)
    ex_c_inv = {
        "invoice_no": "SAL-EX-C001",
        "customer_id": "CUST-EX-01",
        "customer_gstin": "27DEFGH5678I1Z9",
        "invoice_dt": "23-08-2024",
        "taxable_val": 80000.0,
        "tax": 14400.0,
        "invoice_val": 94400.0,
        "credit_days": 30,
        "due_dt": "22-09-2024",
        "payment_status": "Unpaid",
        "anomaly_tag": "PR-65"
    }
    
    if not any(r['invoice_no'] == "SAL-EX-C001" for r in sales_records):
        sales_records.insert(0, ex_c_inv)

    # 3. Process records: Apply ageing buckets as of 31-03-2025 and inject anomalies
    cutoff_date = datetime(2025, 3, 31)
    processed_sales = []
    anomaly_logs = []

    for idx, row in enumerate(sales_records):
        inv_dt = datetime.strptime(str(row['invoice_dt']), "%d-%m-%Y")
        age_days = (cutoff_date - inv_dt).days
        
        # Ageing Buckets as of 31-03-2025
        if age_days <= 30:
            bucket = "0-30"
        elif age_days <= 60:
            bucket = "31-60"
        elif age_days <= 90:
            bucket = "61-90"
        else:
            bucket = "90+"
            
        row['aging_days'] = age_days
        row['aging_bucket'] = bucket

        # Assign behavior & anomalies
        cust_id = str(row['customer_id'])
        if row['invoice_no'] == "SAL-EX-C001":
            row['payment_status'] = "Unpaid"
            anomaly_logs.append({"anomaly_id": "PR-65", "row_id": row['invoice_no'], "description": "Unpaid overdue invoice exceeding 220 days"})
        elif cust_id in recurring_defaulters or age_days > 90 and random.random() < 0.4:
            row['payment_status'] = "Defaulted / Unpaid"
            row['anomaly_tag'] = "PR-65-DEFAULTER"
        elif random.random() < 0.25: # Late payer (10-45 days late)
            delay = random.randint(10, 45)
            row['payment_status'] = f"Paid Late ({delay} days)"
            row['anomaly_tag'] = "PR-LATE-PAYER"
        else:
            row['payment_status'] = "Paid On Time"
            row['anomaly_tag'] = "None"

        processed_sales.append(row)

    df_final_sales = pd.DataFrame(processed_sales)
    df_final_sales.to_csv("data/raw/ledgers/sales_ledger.csv", index=False)
    
    # Append to anomaly log
    log_path = "data/processed/anomaly_log.csv"
    if os.path.exists(log_path):
        df_log = pd.read_csv(log_path)
        df_new_log = pd.DataFrame(anomaly_logs)
        df_combined = pd.concat([df_log, df_new_log], ignore_index=True)
        df_combined.to_csv(log_path, index=False)
    else:
        pd.DataFrame(anomaly_logs).to_csv(log_path, index=False)

    print(f"✓ Receivables anomaly injection complete. {len(df_final_sales)} invoices processed with precise ageing buckets and PR-65 log entries.")
    print("=== RECEIVABLES LEDGER & ANOMALIES READY ===")

if __name__ == "__main__":
    inject_receivables_anomalies()