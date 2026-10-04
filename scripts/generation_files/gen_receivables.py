"""
Module: scripts/gen_receivables.py
Description: Generates clean sales_ledger.csv and receipts.csv aligned with customer behavior and masters.
"""

import os
import random
import pandas as pd
from datetime import datetime, timedelta

def generate_receivables():
    print("Generating clean receivables and sales ledger...")
    
    # Load customer masters
    cust_path = "data/raw/masters/customer_master.csv"
    if not os.path.exists(cust_path):
        raise FileNotFoundError(f"Customer master not found at {cust_path}. Please ensure master data exists.")
        
    cust_df = pd.read_csv(cust_path)
    
    sales_rows = []
    receipt_rows = []
    start_date = datetime(2024, 4, 1)
    end_date = datetime(2025, 3, 31)
    
    # Generate structured sales items across customers
    for i in range(1200):
        cust = cust_df.sample(1).iloc[0]
        inv_no = f"SAL-2024-{i+1:05d}"
        inv_date = start_date + timedelta(days=random.randint(0, 300))
        
        taxable = round(random.uniform(10000.0, 250000.0), 2)
        tax = round(taxable * 0.18, 2)
        inv_val = round(taxable + tax, 2)
        
        credit_days = int(cust.get('credit_terms_days', 30))
        due_date = inv_date + timedelta(days=credit_days)
        
        sales_rows.append({
            "invoice_no": inv_no,
            "customer_id": cust.get('customer_id', 'CUST-001'),
            "customer_gstin": cust.get('customer_gstin', cust.get('gstin', '')),
            "invoice_dt": inv_date.strftime("%d-%m-%Y"),
            "taxable_val": taxable,
            "tax": tax,
            "invoice_val": inv_val,
            "credit_days": credit_days,
            "due_dt": due_date.strftime("%d-%m-%Y")
        })
        
        # Determine payment behavior matching customer tier
        behavior = str(cust.get('behavior_tier', cust.get('payment_behavior', 'good'))).lower()
        if "good" in behavior:
            pay_delay = random.randint(-5, 10)
        elif "late" in behavior:
            pay_delay = random.randint(15, 45)
        else:
            pay_delay = random.randint(60, 120) if random.random() > 0.3 else None
            
        if pay_delay is not None:
            receipt_date = due_date + timedelta(days=pay_delay)
            if receipt_date <= end_date:
                receipt_rows.append({
                    "receipt_id": f"RCP-{i+1:05d}",
                    "customer_id": cust.get('customer_id', 'CUST-001'),
                    "invoice_ref": inv_no,
                    "receipt_date": receipt_date.strftime("%d-%m-%Y"),
                    "amount": inv_val,
                    "mode": random.choice(["NEFT", "RTGS", "UPI", "Cheque"])
                })
                
    df_sales = pd.DataFrame(sales_rows)
    df_receipts = pd.DataFrame(receipt_rows)
    
    os.makedirs("data/interim", exist_ok=True)
    os.makedirs("data/raw/ledgers", exist_ok=True)
    
    df_sales.to_csv("data/interim/sales_ledger_clean.csv", index=False)
    df_sales.to_csv("data/raw/ledgers/sales_ledger.csv", index=False)
    
    df_receipts.to_csv("data/interim/receipts_clean.csv", index=False)
    df_receipts.to_csv("data/raw/ledgers/receipts.csv", index=False)
    
    print(f"Generated sales ledger ({len(df_sales)} rows) and receipts ({len(df_receipts)} rows) successfully.")

if __name__ == "__main__":
    generate_receivables()