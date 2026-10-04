"""
Module: scripts/gen_payment_ledger.py
Description: Generates clean payment_ledger.csv covering all sections (B2B, B2BA, CDN, CDNA) 
satisfying Rule 37 based on the updated purchase books.
"""

import os
import random
import pandas as pd
from datetime import datetime, timedelta

def generate_payment_ledger():
    print("Generating clean payment ledger covering all purchase sections...")
    cutoff_date = datetime(2024, 10, 2)
    end_date = datetime(2025, 3, 31)
    
    all_invoices = []
    
    # 1. Extract from B2B Books
    b2b_path = "data/interim/books_b2b_clean.csv"
    if os.path.exists(b2b_path):
        df_b2b = pd.read_csv(b2b_path)
        cols = ['vendor_id', 'invoice_no', 'invoice_dt', 'invoice_val']
        if 'counter_party_gstin' in df_b2b.columns:
            cols.append('counter_party_gstin')
        b2b_inv = df_b2b[cols].drop_duplicates()
        for _, row in b2b_inv.iterrows():
            all_invoices.append({
                "vendor_id": row['vendor_id'],
                "counter_party_gstin": row.get('counter_party_gstin', ''),
                "section": "B2B",
                "invoice_ref": row['invoice_no'],
                "invoice_dt": row['invoice_dt'],
                "invoice_val": row['invoice_val']
            })

    # 2. Extract from B2BA (Amendments) Books
    b2ba_path = "data/interim/books_b2ba_clean.csv"
    if os.path.exists(b2ba_path):
        df_b2ba = pd.read_csv(b2ba_path)
        cols = ['vendor_id', 'invoice_no', 'invoice_dt', 'invoice_val']
        if 'counter_party_gstin' in df_b2ba.columns:
            cols.append('counter_party_gstin')
        b2ba_inv = df_b2ba[cols].drop_duplicates()
        for _, row in b2ba_inv.iterrows():
            all_invoices.append({
                "vendor_id": row['vendor_id'],
                "counter_party_gstin": row.get('counter_party_gstin', ''),
                "section": "B2BA",
                "invoice_ref": row['invoice_no'],
                "invoice_dt": row['invoice_dt'],
                "invoice_val": row['invoice_val']
            })

    # 3. Extract from CDN (Credit/Debit Notes) Books
    cdn_path = "data/interim/books_cdn_clean.csv"
    if os.path.exists(cdn_path):
        df_cdn = pd.read_csv(cdn_path)
        cols = ['vendor_id', 'invoice_no', 'invoice_dt', 'note_val']
        if 'counter_party_gstin' in df_cdn.columns:
            cols.append('counter_party_gstin')
        cdn_inv = df_cdn[cols].drop_duplicates()
        for _, row in cdn_inv.iterrows():
            all_invoices.append({
                "vendor_id": row['vendor_id'],
                "counter_party_gstin": row.get('counter_party_gstin', ''),
                "section": "CDN",
                "invoice_ref": row['invoice_no'],
                "invoice_dt": row['invoice_dt'],
                "invoice_val": row['note_val']
            })

    # 4. Extract from CDNA (Amended Credit/Debit Notes) Books
    cdna_path = "data/interim/books_cdna_clean.csv"
    if os.path.exists(cdna_path):
        df_cdna = pd.read_csv(cdna_path)
        cols = ['vendor_id', 'invoice_no', 'invoice_dt', 'note_val']
        if 'counter_party_gstin' in df_cdna.columns:
            cols.append('counter_party_gstin')
        cdna_inv = df_cdna[cols].drop_duplicates()
        for _, row in cdna_inv.iterrows():
            all_invoices.append({
                "vendor_id": row['vendor_id'],
                "counter_party_gstin": row.get('counter_party_gstin', ''),
                "section": "CDNA",
                "invoice_ref": row['invoice_no'],
                "invoice_dt": row['invoice_dt'],
                "invoice_val": row['note_val']
            })

    if not all_invoices:
        raise FileNotFoundError("No purchase book interim files found! Run gen_purchase.py first.")

    payments = []
    pay_id = 1
    
    for inv in all_invoices:
        try:
            inv_date = datetime.strptime(str(inv['invoice_dt']), "%d-%m-%Y")
        except ValueError:
            continue
            
        is_old = inv_date <= cutoff_date
        
        if is_old:
            max_pay_delay = 30  # Strict payment window for older legacy entries
        else:
            r = random.random()
            if r < 0.90:
                max_pay_delay = 30
            elif r < 0.98:
                max_pay_delay = 80
            else:
                continue  # Unpaid past 180 days -> triggers Rule 37 reversal
                
        pay_date = inv_date + timedelta(days=random.randint(1, max_pay_delay))
        if pay_date > end_date:
            pay_date = end_date
            
        payments.append({
            "payment_id": f"PAY-{pay_id:05d}",
            "vendor_id": inv['vendor_id'],
            "counter_party_gstin": inv.get('counter_party_gstin', ''),
            "section": inv['section'],
            "invoice_ref": inv['invoice_ref'],
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
    print(f"Generated comprehensive payment ledger with {len(df_pay)} records across all sections (B2B, B2BA, CDN, CDNA).")

if __name__ == "__main__":
    generate_payment_ledger()