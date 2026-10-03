"""
Module: scripts/gen_purchase.py
Description: Generates clean purchase books (b2b, b2ba, cdn, cdna) following v3 specs.
No HSN/SAC columns. Line-item calculations strictly enforced.
"""

import os
import random
import pandas as pd
from datetime import datetime, timedelta

def generate_clean_purchases():
    print("Generating clean purchase books...")
    
    # Load masters
    vendor_df = pd.read_csv("data/raw/masters/vendor_master.csv")
    item_df = pd.read_csv("data/raw/masters/item_catalogue.csv")
    
    reg_col = 'registration_type' if 'registration_type' in vendor_df.columns else ('vendor_type' if 'vendor_type' in vendor_df.columns else None)
    if reg_col:
        regular_vendors = vendor_df[vendor_df[reg_col].astype(str).str.upper() == 'REGULAR'].to_dict('records')
    else:
        regular_vendors = vendor_df.to_dict('records')
    if not regular_vendors:
        regular_vendors = vendor_df.to_dict('records')
        
    all_vendors = vendor_df.to_dict('records')
    items = item_df.to_dict('records')
    
    start_date = datetime(2024, 4, 1)
    end_date = datetime(2025, 3, 31)
    
    def random_date(start, end):
        delta = end - start
        return start + timedelta(days=random.randint(0, delta.days))

    # Line count targets from v3 spec
    target_b2b_lines = 3850
    b2b_rows = []
    invoice_registry = [] # Track generated invoices for B2BA and CDN linking
    
    line_counts_dist = [1]*60 + [2]*25 + [3]*10 + [4]*5
    current_lines = 0
    inv_counter = 1000
    
    while current_lines < target_b2b_lines:
        inv_counter += 1
        invoice_no = f"INV-2024-{inv_counter:05d}"
        vendor = random.choice(regular_vendors)
        
        inv_date = random_date(start_date, end_date)
        booking_date = inv_date + timedelta(days=random.randint(0, 15))
        if booking_date > end_date:
            booking_date = end_date
            
        fp = inv_date.strftime("%m%Y")
        n_lines = random.choice(line_counts_dist)
        if current_lines + n_lines > target_b2b_lines:
            n_lines = target_b2b_lines - current_lines
            
        v_gstin = vendor.get('vendor_gstin', vendor.get('gstin', ''))
        v_name = vendor.get('vendor_name', vendor.get('trade_name', ''))
        pos = str(vendor['state_code']).zfill(2)
        is_interstate = (pos != '27')
        
        invoice_lines_temp = []
        invoice_taxable_sum = 0.0
        invoice_tax_sum = 0.0
        
        for serial in range(1, n_lines + 1):
            item = random.choice(items)
            qty = random.randint(1, 20)
            p_min = float(item.get('price_min', item.get('unit_price_lower', 100.0)))
            p_max = float(item.get('price_max', item.get('unit_price_upper', 5000.0)))
            unit_price = round(random.uniform(p_min, p_max), 2)
            taxable_val = round(qty * unit_price, 2)
            rate = float(item.get('rate', item.get('gst_rate', 18.0)))
            
            tax_amount = round(taxable_val * (rate / 100.0), 2)
            if is_interstate:
                igst = tax_amount
                cgst, sgst = 0.0, 0.0
            else:
                igst = 0.0
                cgst = round(tax_amount / 2.0, 2)
                sgst = round(tax_amount - cgst, 2)
                
            cess = 0.0
            invoice_taxable_sum += taxable_val
            invoice_tax_sum += (igst + cgst + sgst + cess)
            
            itc_el = item.get('itc_eligible', 'Y')
            cap_fl = item.get('capital_goods_flag', 'Y' if 'Hardware' in str(item.get('category', '')) else 'N')
            
            invoice_lines_temp.append({
                "item_serial_no": serial,
                "description": item['description'],
                "qty": qty,
                "unit_price": unit_price,
                "taxable_val": taxable_val,
                "rate_of_tax": rate,
                "igst_amnt": igst,
                "cgst_amnt": cgst,
                "sgst_amnt": sgst,
                "cess_amnt": cess,
                "itc_eligible": itc_el,
                "itc_claimed": itc_el,
                "capital_goods_flag": cap_fl
            })
            
        invoice_val = round(invoice_taxable_sum + invoice_tax_sum, 2)
        
        # Store for referencing amendments / notes
        invoice_registry.append({
            "vendor_id": vendor['vendor_id'],
            "counter_party_gstin": v_gstin,
            "invoice_no": invoice_no,
            "invoice_dt": inv_date.strftime("%d-%m-%Y"),
            "invoice_val": invoice_val,
            "pos": pos,
            "fp": fp
        })
        
        for l in invoice_lines_temp:
            current_lines += 1
            row_id = f"B2B-{current_lines:05d}"
            b2b_rows.append({
                "row_id": row_id,
                "vendor_id": vendor['vendor_id'],
                "trans_type": "B2B",
                "fp": fp,
                "self_gstin": "27AABCT1234F1Z5",
                "counter_party_gstin": v_gstin,
                "vendor_name": v_name,
                "invoice_type": "Regular",
                "invoice_no": invoice_no,
                "invoice_dt": inv_date.strftime("%d-%m-%Y"),
                "booking_dt": booking_date.strftime("%d-%m-%Y"),
                "item_serial_no": l['item_serial_no'],
                "description": l['description'],
                "qty": l['qty'],
                "unit_price": l['unit_price'],
                "taxable_val": l['taxable_val'],
                "rate_of_tax": l['rate_of_tax'],
                "igst_amnt": l['igst_amnt'],
                "cgst_amnt": l['cgst_amnt'],
                "sgst_amnt": l['sgst_amnt'],
                "cess_amnt": l['cess_amnt'],
                "invoice_val": invoice_val,
                "pos": pos,
                "reverse_charge": "N",
                "itc_eligible": l['itc_eligible'],
                "itc_claimed": l['itc_claimed'],
                "capital_goods_flag": l['capital_goods_flag'],
                "tax_period": fp
            })
            
    df_b2b = pd.DataFrame(b2b_rows)
    os.makedirs("data/interim", exist_ok=True)
    os.makedirs("data/raw/books", exist_ok=True)
    df_b2b.to_csv("data/interim/books_b2b_clean.csv", index=False)
    df_b2b.to_csv("data/raw/books/books_b2b.csv", index=False)
    print(f"Generated clean books_b2b with {len(df_b2b)} rows.")

    # 1. books_b2ba.csv (Target: 290 lines)
    b2ba_rows = []
    sample_b2b_invoices = random.sample(invoice_registry, 100)
    b2ba_line_id = 1
    for inv in sample_b2b_invoices:
        if len(b2ba_rows) >= 290:
            break
        n_lines = min(random.randint(2, 4), 290 - len(b2ba_rows))
        for s in range(1, n_lines + 1):
            item = random.choice(items)
            taxable = round(random.uniform(5000, 40000), 2)
            rate = float(item.get('rate', item.get('gst_rate', 18.0)))
            tax = round(taxable * rate / 100.0, 2)
            b2ba_rows.append({
                "row_id": f"B2BA-{b2ba_line_id:05d}",
                "vendor_id": inv['vendor_id'],
                "trans_type": "B2BA",
                "fp": "102024",
                "self_gstin": "27AABCT1234F1Z5",
                "counter_party_gstin": inv['counter_party_gstin'],
                "vendor_name": "Vendor Trade Name",
                "invoice_type": "Regular",
                "invoice_no": inv['invoice_no'] + "-REV",
                "invoice_dt": "15-10-2024",
                "booking_dt": "20-10-2024",
                "item_serial_no": s,
                "description": item['description'],
                "qty": 5,
                "unit_price": taxable/5,
                "taxable_val": taxable,
                "rate_of_tax": rate,
                "igst_amnt": tax,
                "cgst_amnt": 0.0,
                "sgst_amnt": 0.0,
                "cess_amnt": 0.0,
                "invoice_val": taxable + tax,
                "pos": inv['pos'],
                "reverse_charge": "N",
                "itc_eligible": "Y",
                "itc_claimed": "Y",
                "capital_goods_flag": "N",
                "tax_period": "102024",
                "original_invoice_no": inv['invoice_no'],
                "original_invoice_dt": inv['invoice_dt']
            })
            b2ba_line_id += 1
    df_b2ba = pd.DataFrame(b2ba_rows).head(290)
    df_b2ba.to_csv("data/interim/books_b2ba_clean.csv", index=False)
    df_b2ba.to_csv("data/raw/books/books_b2ba.csv", index=False)
    print(f"Generated clean books_b2ba with {len(df_b2ba)} rows.")

    # 2. books_cdn.csv (Target: 580 lines)
    cdn_rows = []
    for i in range(580):
        inv = random.choice(invoice_registry)
        item = random.choice(items)
        dif_val = round(random.uniform(1000, 15000), 2)
        rate = float(item.get('rate', item.get('gst_rate', 18.0)))
        tax = round(dif_val * rate / 100.0, 2)
        cdn_rows.append({
            "row_id": f"CDN-{i+1:05d}",
            "vendor_id": inv['vendor_id'],
            "trans_type_code": "CDN",
            "fp": inv['fp'],
            "self_gstin": "27AABCT1234F1Z5",
            "counter_party_gstin": inv['counter_party_gstin'],
            "type_of_note": random.choice(["C", "D"]),
            "db_cr_issue_reason": "Sales Return",
            "dbt_crdt_no": f"CDN-{i+1:04d}",
            "dbt_crdt_no_dt": inv['invoice_dt'],
            "invoice_no": inv['invoice_no'],
            "invoice_dt": inv['invoice_dt'],
            "item_serial_no": 1,
            "dif_value": dif_val,
            "rate_of_tax": rate,
            "dif_igst": tax,
            "diff_cgst": 0.0,
            "diff_sgst": 0.0,
            "diff_cess_amnt": 0.0,
            "note_val": round(dif_val + tax, 2),
            "pos": inv['pos']
        })
    df_cdn = pd.DataFrame(cdn_rows)
    df_cdn.to_csv("data/interim/books_cdn_clean.csv", index=False)
    df_cdn.to_csv("data/raw/books/books_cdn.csv", index=False)
    print(f"Generated clean books_cdn with {len(df_cdn)} rows.")

    # 3. books_cdna.csv (Target: 96 lines)
    cdna_rows = []
    for i in range(96):
        cdna_rows.append({
            "row_id": f"CDNA-{i+1:05d}",
            "vendor_id": cdn_rows[i]['vendor_id'],
            "trans_type_code": "CDNA",
            "fp": "112024",
            "self_gstin": "27AABCT1234F1Z5",
            "counter_party_gstin": cdn_rows[i]['counter_party_gstin'],
            "type_of_note": cdn_rows[i]['type_of_note'],
            "db_cr_issue_reason": "Correction",
            "dbt_crdt_no": f"CDNA-{i+1:04d}",
            "dbt_crdt_no_dt": "10-11-2024",
            "invoice_no": cdn_rows[i]['invoice_no'],
            "invoice_dt": cdn_rows[i]['invoice_dt'],
            "item_serial_no": 1,
            "dif_value": cdn_rows[i]['dif_value'],
            "rate_of_tax": cdn_rows[i]['rate_of_tax'],
            "dif_igst": cdn_rows[i]['dif_igst'],
            "diff_cgst": 0.0,
            "diff_sgst": 0.0,
            "diff_cess_amnt": 0.0,
            "note_val": cdn_rows[i]['note_val'],
            "pos": cdn_rows[i]['pos'],
            "or_dbt_crdt_no": cdn_rows[i]['dbt_crdt_no'],
            "or_dbt_crdt_note_dt": cdn_rows[i]['dbt_crdt_no_dt']
        })
    df_cdna = pd.DataFrame(cdna_rows)
    df_cdna.to_csv("data/interim/books_cdna_clean.csv", index=False)
    df_cdna.to_csv("data/raw/books/books_cdna.csv", index=False)
    print(f"Generated clean books_cdna with {len(df_cdna)} rows.")

if __name__ == "__main__":
    generate_clean_purchases()