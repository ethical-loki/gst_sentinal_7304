import os
import random
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

TARIFF_PATH = "data/raw/tariff_master.parquet"
OUTPUT_CORPUS_PATH = "data/raw/synthetic_invoice_corpus.parquet"

TOTAL_ROWS = 12000
TARGET_ERRORS = {
    "hsn_misclass": 800,
    "rate_mismatch": 600,
    "blocked_17_5": 500,
    "pos_error": 300,
    "math_error": 200,
    "clean": 9600
}

SECTORS = [
    "Engineering", "Metals", "IT", "FMCG", "Logistics", "Chemicals",
    "Textiles", "Automotive", "Hospitality", "Healthcare", "Construction", "Mining"
]

INDIAN_STATES = ["27", "29", "07", "33", "24", "06", "19", "09", "36", "10"]

SLANG_MODIFIERS = [
    "MS Flange 25mm Class 150", "SS 304 Hex Bolt w/ Nut", "Heavy Duty Bushing",
    "Labour charges for fabrication at site", "Transport charges / Bilty fee / Hamali",
    "Industrial Grade Packing Material", "Electrical Conduit PVC 20mm",
    "Hydraulic Hose Assembly", "Standard Coupling Nut 10mm"
]

def generate_gstin(state_code, pan=None):
    if not pan:
        letters = "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=5))
        digits = "".join(random.choices("0123456789", k=4))
        last_letter = random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
        pan = f"{letters}{digits}{last_letter}"
    return f"{state_code}{pan}1Z{random.choice('0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ')}"

def build_vendor_profiles(num_vendors=250):
    vendors = []
    for i in range(num_vendors):
        state = random.choice(INDIAN_STATES)
        tier_roll = random.random()
        if tier_roll < 0.70:
            tier = "Tier 1"
            reg = round(random.uniform(0.95, 1.00), 2)
            var = round(random.uniform(0.00, 0.02), 3)
            err = round(random.uniform(0.00, 0.01), 3)
            trust = round(random.uniform(0.90, 1.00), 2)
            r86b = False
            non_file = 0
        elif tier_roll < 0.95:
            tier = "Tier 2"
            reg = round(random.uniform(0.80, 0.95), 2)
            var = round(random.uniform(0.02, 0.08), 3)
            err = round(random.uniform(0.02, 0.06), 3)
            trust = round(random.uniform(0.65, 0.89), 2)
            r86b = False
            non_file = random.choice([0, 1])
        else:
            tier = "Tier 3"
            reg = round(random.uniform(0.40, 0.79), 2)
            var = round(random.uniform(0.10, 0.35), 3)
            err = round(random.uniform(0.15, 0.40), 3)
            trust = round(random.uniform(0.20, 0.60), 2)
            r86b = random.choice([True, False])
            non_file = random.choice([2, 3, 4])

        vendors.append({
            "vendor_id": f"VND-{i+1:04d}",
            "gstin": generate_gstin(state),
            "lglnm": f"Enterprise Supplier {i+1} Pvt Ltd",
            "state": state,
            "pin": f"{state}00{random.randint(10, 99)}",
            "tier": tier,
            "reg": reg,
            "var": var,
            "err": err,
            "trust": trust,
            "r86b": r86b,
            "non_file": non_file,
            "is_msme": random.choice([True, False])
        })
    return vendors

def main():
    if not os.path.exists(TARIFF_PATH):
        raise FileNotFoundError(f"Tariff master missing at {TARIFF_PATH}")

    df_tariff = pd.read_parquet(TARIFF_PATH)
    clean_tariff = df_tariff[~df_tariff["is_blocked_17_5"]].reset_index(drop=True)
    blocked_tariff = df_tariff[df_tariff["is_blocked_17_5"]].reset_index(drop=True)

    vendors = build_vendor_profiles(250)
    
    error_pool = []
    for err_type, count in TARGET_ERRORS.items():
        error_pool.extend([err_type] * count)
    random.shuffle(error_pool)

    rows = []
    
    for idx in range(TOTAL_ROWS):
        assigned_error = error_pool[idx]
        vendor = random.choice(vendors)
        sector = random.choice(SECTORS)
        
        invoice_id = f"INV-2026-{10000 + (idx // 2)}"
        line_item_id = f"{invoice_id}-L{((idx % 2) + 1):02d}"
        
        buyer_state = random.choice(INDIAN_STATES)
        buyer_pin = f"{buyer_state}00{random.randint(10, 99)}"
        buyer_gstin = generate_gstin(buyer_state) if random.random() > 0.05 else "URP"
        
        true_pos = buyer_state
        declared_pos = buyer_state
        
        if assigned_error == "blocked_17_5":
            tariff_item = blocked_tariff.sample(1).iloc[0]
        else:
            tariff_item = clean_tariff.sample(1).iloc[0]

        true_hsn = str(tariff_item["hsn_code"])
        declared_hsn = true_hsn
        true_rate = float(tariff_item["standard_rate"])
        declared_rate = true_rate

        prod_desc = str(tariff_item["hsn_description"])
        if random.random() < 0.40:
            prod_desc = f"{random.choice(SLANG_MODIFIERS)} - {prod_desc[:40]}"

        log_val = np.random.normal(9.8, 1.4)
        taxable_val = round(float(np.exp(log_val)), 2)
        qty = random.choice([1, 2, 5, 10, 20, 50, 100])
        unit_price = round(taxable_val / qty, 2)
        taxable_val = round(unit_price * qty, 2)

        is_hsn_misclass = False
        is_rate_mismatch = False
        is_blocked_17_5 = (assigned_error == "blocked_17_5")
        is_pos_error = False
        is_math_error = False

        if assigned_error == "hsn_misclass":
            is_hsn_misclass = True
            diff_tariff = clean_tariff[clean_tariff["chapter"] != tariff_item["chapter"]]
            declared_hsn = str(diff_tariff.sample(1).iloc[0]["hsn_code"])

        elif assigned_error == "rate_mismatch":
            is_rate_mismatch = True
            other_slabs = [s for s in [0.0, 5.0, 12.0, 18.0, 28.0] if s != true_rate]
            declared_rate = random.choice(other_slabs)

        elif assigned_error == "pos_error":
            is_pos_error = True
            declared_pos = vendor["state"] if vendor["state"] != buyer_state else random.choice([s for s in INDIAN_STATES if s != vendor["state"]])

        intra_state = (vendor["state"] == declared_pos)
        calculated_tax = round(taxable_val * (declared_rate / 100.0), 2)
        
        if intra_state:
            cgst = round(calculated_tax / 2.0, 2)
            sgst = round(calculated_tax / 2.0, 2)
            igst = 0.0
        else:
            cgst = 0.0
            sgst = 0.0
            igst = calculated_tax

        if assigned_error == "math_error":
            is_math_error = True
            cgst = round(cgst * 0.70, 2)
            sgst = round(sgst * 0.70, 2)
            igst = round(igst * 0.70, 2)

        total_item_val = round(taxable_val + cgst + sgst + igst, 2)
        
        has_err = (assigned_error != "clean")
        
        exposure = 0.0
        if has_err:
            tax_gap = abs((taxable_val * (true_rate / 100.0)) - (cgst + sgst + igst))
            penalty = max(10000.0, tax_gap * 0.10)
            interest = round(tax_gap * 0.18 * (180.0 / 365.0), 2)
            exposure = round(tax_gap + penalty + interest, 2)

        distance = random.randint(30, 1500)
        calc_dist = distance if random.random() > 0.05 else distance + random.randint(150, 400)

        rows.append({
            "invoice_id": invoice_id,
            "doc_type": "INV",
            "doc_date": "2026-10-10",
            "system_cd": "SAP_ERP",
            "branch_cd": f"LOC{random.randint(1, 9):02d}",
            "vertical_cd": "DOM",
            "sector": sector,
            "irn_required": "Y",
            "irn_hash": None,
            "supplier_gstin": vendor["gstin"],
            "supplier_lglnm": vendor["lglnm"],
            "supplier_state": vendor["state"],
            "supplier_pin": vendor["pin"],
            "buyer_gstin": buyer_gstin,
            "buyer_lglnm": f"Buyer Commerce Entity {idx % 500} Ltd",
            "buyer_state": buyer_state,
            "buyer_pin": buyer_pin,
            "buyer_pos": true_pos,
            "declared_pos": declared_pos,
            "reverse_charge_flag": "N",
            "line_item_id": line_item_id,
            "item_slno": str((idx % 2) + 1),
            "product_name": str(tariff_item["hsn_description"])[:30],
            "product_description": prod_desc,
            "is_service": "Y" if true_hsn.startswith("99") else "N",
            "declared_hsn": declared_hsn,
            "true_hsn": true_hsn,
            "quantity": float(qty),
            "unit_code": "NOS",
            "unit_price": unit_price,
            "item_total_amount": taxable_val,
            "item_discount": 0.0,
            "item_taxable_value": taxable_val,
            "declared_gst_rate": declared_rate,
            "true_gst_rate": true_rate,
            "cgst_amount": cgst,
            "sgst_amount": sgst,
            "igst_amount": igst,
            "cess_rate": 0.0,
            "cess_amount": 0.0,
            "total_item_value": total_item_val,
            "inv_assessable_value": taxable_val,
            "inv_cgst_total": cgst,
            "inv_sgst_total": sgst,
            "inv_igst_total": igst,
            "inv_total_value": total_item_val,
            "declared_total_inv_value": total_item_val if not is_math_error else round(total_item_val + 5000.0, 2),
            "eway_bill_required": "Y" if total_item_val >= 50000.0 else "N",
            "subsupplytype": "1",
            "transit_mode": "1",
            "transit_distance_km": float(distance),
            "calculated_distance_km": float(calc_dist),
            "transporter_id": generate_gstin("27") if distance > 100 else "",
            "transporter_name": "FastTrack Logistics Pvt Ltd",
            "transport_doc_no": f"LR-{random.randint(100000, 999999)}",
            "transdocdt": "2026-10-10",
            "vehicle_number": f"MH{random.randint(10, 99)}AB{random.randint(1000, 9999)}",
            "vehicle_type": "R",
            "vendor_risk_tier": vendor["tier"],
            "vendor_filing_regularity": vendor["reg"],
            "vendor_gstr_variance": vendor["var"],
            "vendor_error_rate": vendor["err"],
            "vendor_trust_score": vendor["trust"],
            "rule_86b_violation_flag": vendor["r86b"],
            "consecutive_non_filing_count": vendor["non_file"],
            "is_msme_vendor": vendor["is_msme"],
            "msme_turnaround_days": random.randint(10, 60),
            "has_error": has_err,
            "error_type": assigned_error,
            "is_hsn_misclass": is_hsn_misclass,
            "is_rate_mismatch": is_rate_mismatch,
            "is_blocked_17_5": is_blocked_17_5,
            "is_pos_error": is_pos_error,
            "is_math_error": is_math_error,
            "statutory_exposure_rupees": exposure,
            "split_partition": "unassigned"
        })

    df_corpus = pd.DataFrame(rows)
    table = pa.Table.from_pandas(df_corpus)
    pq.write_table(table, OUTPUT_CORPUS_PATH, compression="snappy")
    
    print(f"successfully built {len(df_corpus)} records in {OUTPUT_CORPUS_PATH}")
    print("error breakdown:")
    print(df_corpus["error_type"].value_counts())

if __name__ == "__main__":
    main()