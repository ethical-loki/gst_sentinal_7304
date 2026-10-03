"""
Module: scripts/gen_payment_ledger.py
Description: Generates clean payment_ledger.csv satisfying Rule 37.
"""

import os
import random
import pandas as pd
from datetime import datetime, timedelta

def generate_payment_ledger():
    print("Generating clean payment ledger...")
    cutoff_date = datetime(2024, 10, 2)
    end_date = datetime(2025, 3, 31)
    
    vendor_df = pd.read_csv("data/raw/masters/vendor_master.csv")
    df_b2b = pd.read_csv("data/interim/books_b2b_clean.csv")
    
    payments = []
    pay_id = 1
    
    # Group unique invoices from b2b clean
    invoices = df_b2b[['vendor_id', 'invoice_no', 'invoice_dt', 'invoice_val']].drop_duplicates().to_dict('records')
    
    for inv in invoices:
        inv_date = datetime.strptime(inv['invoice_dt'], "%d-%m-%Y")
        is_old = inv_date <= cutoff_date
        
        if is_old:
            max_pay_delay = 30  # Force strict on-time/early payment for rule 37
        else:
            r = random.random()
            if r < 0.90:
                max_pay_delay = 30
            elif r < 0.98:
                max_pay_delay = 80
            else:
                continue # Unpaid
                
        pay_date = inv_date + timedelta(days=random.randint(1, max_pay_delay))
        if pay_date > end_date:
            pay_date = end_date
            
        payments.append({
            "payment_id": f"PAY-{pay_id:05d}",
            "vendor_id": inv['vendor_id'],
            "section": "B2B",
            "invoice_ref": inv['invoice_no'],
            "payment_date": pay_date.strftime("%d-%m-%Y"),
            "amount": inv['invoice_val'],
            "mode": random.choice(["NEFT", "RTGS", "Bank Transfer"]),
            "utr": f"UTR{random.randint(100000000, 999999999)}"
        })
        pay_id += 1
        
    df_pay = pd.DataFrame(payments)
    os.makedirs("data/interim", exist_ok=True)
    os.makedirs("data/raw/ledgers", exist_ok=True)
    df_pay.to_csv("data/interim/payment_ledger_clean.csv", index=False)
    df_pay.to_csv("data/raw/ledgers/payment_ledger.csv", index=False)
    print(f"Generated payment ledger with {len(df_pay)} records respecting Rule 37.")

if __name__ == "__main__":
    generate_payment_ledger()