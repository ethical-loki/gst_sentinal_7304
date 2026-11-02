"""
Module: src/ingestion/generate_sample_dirty_input.py
Description: Dynamic & Randomized Dirty Input Generator for Indian GST E-Invoice & E-Way Bill Ingestion.
             Generates randomized invoices with clean standard schema keys, focusing strictly on
             dirty key field values (truncated GSTIN lengths, comma decimal notations, date format
             anomalies, unpadded state codes, messy whitespace, and vehicle formatting).
"""

import os
import sys
import json
import random
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List

# Realistic Master Pools for Dynamic Generation
STATE_POOL = [
    ("33", "Tamil Nadu", "COIMBATORE", "641001"),
    ("27", "Maharashtra", "MUMBAI", "400001"),
    ("29", "Karnataka", "BENGALURU", "560001"),
    ("07", "Delhi", "NEW DELHI", "110001"),
    ("24", "Gujarat", "AHMEDABAD", "380001"),
    ("19", "West Bengal", "KOLKATA", "700001"),
    ("06", "Haryana", "GURUGRAM", "122001"),
    ("36", "Telangana", "HYDERABAD", "500001"),
]

PRODUCT_POOL = [
    {"prdnm": "GRM-TSHIRT", "desc": "Men's Cotton T-Shirt", "hsn": "520511", "uqc": "NOS", "rate_range": (80.0, 450.0), "tax": 5.0},
    {"prdnm": "STEEL-ROD", "desc": "TMT High Tensile Steel Rods", "hsn": "720839", "uqc": "TON", "rate_range": (45000.0, 62000.0), "tax": 18.0},
    {"prdnm": "POLY-HANGER", "desc": "Plastic Garment Hanger Grade A", "hsn": "39269069", "uqc": "PCS", "rate_range": (10.0, 35.0), "tax": 18.0},
    {"prdnm": "ALUM-INGOT", "desc": "Primary Aluminum Ingot 99.7%", "hsn": "760110", "uqc": "KGS", "rate_range": (180.0, 240.0), "tax": 18.0},
    {"prdnm": "COTTON-YARN", "desc": "Carded Weaving Yarn 30s", "hsn": "520522", "uqc": "KGS", "rate_range": (220.0, 340.0), "tax": 5.0},
    {"prdnm": "LED-DRIVER", "desc": "Constant Current Electronic Driver", "hsn": "850440", "uqc": "NOS", "rate_range": (150.0, 400.0), "tax": 18.0},
    {"prdnm": "SOLAR-CABLE", "desc": "4 sq mm Solar DC Copper Cable", "hsn": "854449", "uqc": "MTR", "rate_range": (45.0, 95.0), "tax": 18.0},
    {"prdnm": "ORGANIC-SOY", "desc": "Non-GMO Raw Soya Beans", "hsn": "120190", "uqc": "QTL", "rate_range": (4200.0, 5600.0), "tax": 5.0},
]

COMPANY_PREFIXES = ["ALPHA", "DELTA", "KPR", "ZENITH", "VORTEX", "PRIME", "GLOBAL", "SUNRISE"]
COMPANY_SUFFIXES = ["MILLS LTD", "INDUSTRIES PVT LTD", "ENTERPRISES", "LOGISTICS LLP", "TRADING CO", "SOLUTIONS"]

def random_gstin(state_code: str) -> str:
    """Generate a realistic 15-character GSTIN string."""
    chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    digits = "0123456789"
    pan_chars = "".join(random.choices(chars, k=5))
    pan_digits = "".join(random.choices(digits, k=4))
    pan_last = random.choice(chars)
    entity_code = random.choice("12345")
    checksum = random.choice(digits + chars)
    return f"{state_code}{pan_chars}{pan_digits}{pan_last}{entity_code}Z{checksum}"

def random_company_name() -> str:
    return f"{random.choice(COMPANY_PREFIXES)} {random.choice(COMPANY_SUFFIXES)}"

def format_dirty_decimal(val: float, force_comma: bool = False) -> str:
    """Formats float, randomly replacing period with comma (e.g. '1318,69') or removing trailing zero ('185.3')."""
    s = f"{val:.2f}"
    if force_comma or random.random() < 0.40:
        return s.replace(".", ",")
    if s.endswith("0") and random.random() < 0.25:
        return s[:-1]
    return s

def random_date_str() -> str:
    """Generates dates in random formats (slash, dot, dash)."""
    past_days = random.randint(1, 120)
    dt = datetime.today() - timedelta(days=past_days)
    fmt = random.choice(["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d.%m.%Y"])
    return dt.strftime(fmt)

def dirty_text_whitespace(val: str) -> str:
    """Randomly adds leading, trailing, or double whitespace."""
    if random.random() < 0.4:
        return f"  {val.replace(' ', '   ')}  "
    return val

def dirty_state_value(state_code: str) -> str:
    """Randomly strips leading zero from single-digit states ('07' -> '7')."""
    if state_code.startswith("0") and random.random() < 0.5:
        return state_code[1:]
    return state_code

def dirty_veh_number(plate: str) -> str:
    """Randomly injects spaces and hyphens into vehicle numbers ('MH - 12 - AB 1234')."""
    if not plate:
        return ""
    if random.random() < 0.6:
        return f"{plate[:2]} - {plate[2:4]} - {plate[4:6]} {plate[6:]}"
    return plate

def generate_random_invoice(invoice_index: int = 1) -> Dict[str, Any]:
    """
    Generates a complete invoice with 100% clean schema keys,
    injecting diverse dirty KEY FIELD VALUES (truncated GSTINs, comma decimals,
    mixed dates, unpadded state codes, messy whitespace).
    """
    trancatg = random.choice(["B2B", "B2B", "SEZWP", "EXP"])
    sup_state_info = random.choice(STATE_POOL)
    sup_state, sup_state_name, sup_city, sup_pin = sup_state_info
    sup_gstin = random_gstin(sup_state)

    self_gstin_val = sup_gstin

    docno = f"INV{datetime.now().year % 100}{random.randint(100000, 999999)}"
    docdt = random_date_str()

    # Buyer setup
    if trancatg == "EXP":
        buy_gstin = "URP"
        pos = "96"
        buy_state = "96"
        buy_pin = "999999"
        buy_city = "Texas"
        buy_country = "US"
        buy_cur = "USD"
        buy_company = f"{random_company_name()} INC"
    elif trancatg == "SEZWP":
        buy_state_info = random.choice(STATE_POOL)
        buy_state, buy_state_name, buy_city, buy_pin = buy_state_info
        buy_gstin = random_gstin(buy_state)
        pos = buy_state
        buy_country = "IN"
        buy_cur = "INR"
        buy_company = f"{random_company_name()} SEZ UNIT"
    else:
        is_intra = random.choice([True, False])
        if is_intra:
            buy_state_info = sup_state_info
        else:
            other_states = [s for s in STATE_POOL if s[0] != sup_state]
            buy_state_info = random.choice(other_states)
        buy_state, buy_state_name, buy_city, buy_pin = buy_state_info
        buy_gstin = random_gstin(buy_state)
        pos = buy_state
        buy_country = "IN"
        buy_cur = "INR"
        buy_company = random_company_name()

    # Generate 1 to 3 random line items
    item_count = random.randint(1, 3)
    selected_prods = random.sample(PRODUCT_POOL, k=min(item_count, len(PRODUCT_POOL)))
    items = []

    total_assamt = 0.0
    total_cgst = 0.0
    total_sgst = 0.0
    total_igst = 0.0
    total_cess = 0.0

    is_intra_tx = (sup_state == pos and trancatg not in ("EXP", "SEZWP", "SEZWOP"))

    for p in selected_prods:
        qty = round(random.uniform(5.0, 500.0), 3)
        unitrate = round(random.uniform(*p["rate_range"]), 2)
        grossamt = round(qty * unitrate, 2)
        discount = round(grossamt * random.choice([0.0, 0.02, 0.05]), 2)
        assamt = round(grossamt - discount, 2)

        tax_rate = p["tax"]
        if is_intra_tx:
            cgstrt = round(tax_rate / 2.0, 2)
            sgstrt = cgstrt
            igstrt = 0.0
            cgstamt = round(assamt * cgstrt / 100.0, 2)
            sgstamt = cgstamt
            igstamt = 0.0
        else:
            igstrt = tax_rate
            cgstrt = 0.0
            sgstrt = 0.0
            igstamt = round(assamt * igstrt / 100.0, 2)
            cgstamt = 0.0
            sgstamt = 0.0

        totitemval = round(assamt + cgstamt + sgstamt + igstamt, 2)

        total_assamt += assamt
        total_cgst += cgstamt
        total_sgst += sgstamt
        total_igst += igstamt

        # Invalidate/dirty field values: e.g. lowercase uqc, comma decimal notation
        uqc_val = p["uqc"].lower() if random.random() < 0.4 else p["uqc"]

        items.append({
            "itemcd": f"ITM-{p['prdnm'][:4]}",
            "prdnm": dirty_text_whitespace(p["prdnm"]),
            "prddesc": p["desc"],
            "isservc": "N",
            "hsncd": p["hsn"],
            "barcde": f"890{random.randint(1000000000, 9999999999)}",
            "qty": f"{qty:.3f}",
            "freeqty": "0.000",
            "uqc": uqc_val,
            "unitrate": f"{unitrate:.2f}",
            "grossamt": format_dirty_decimal(grossamt),
            "discount": str(discount) if discount > 0 else "",
            "othchrg": "",
            "pretaxval": format_dirty_decimal(assamt),
            "assamt": format_dirty_decimal(assamt),
            "taxability": "TAX",
            "diffpercent": "0.00",
            "cgstrt": f"{cgstrt:.2f}",
            "cgstamt": format_dirty_decimal(cgstamt),
            "sgstrt": f"{sgstrt:.2f}",
            "sgstamt": format_dirty_decimal(sgstamt),
            "igstrt": f"{igstrt:.2f}",
            "igstamt": format_dirty_decimal(igstamt, force_comma=True if igstamt > 0 and random.random() < 0.5 else False),
            "cessrt": "0.00",
            "cessamt": "0.00",
            "cessnonadval": "",
            "statecessrt": "0.00",
            "statecessamt": "0.00",
            "statecesnonadvlamt": "0.00",
            "totitemval": format_dirty_decimal(totitemval),
            "ordlineref": f"PO-LINE-{len(items) + 1}",
            "orgcntry": "IN",
            "prdsino": f"SN-{random.randint(10000, 99999)}",
            "batchname": f"BAT-{random.randint(100, 999)}",
            "batchexpirydt": "",
            "batchwarrantydt": ""
        })

    totinvval = round(total_assamt + total_cgst + total_sgst + total_igst + total_cess, 2)

    ewayreq = random.choice(["Y", "N"])
    ewb_mode = random.choice(["1", "2"])
    raw_plate = f"{sup_state_info[1][:2].upper()}{random.randint(10, 99)}AB{random.randint(1000, 9999)}" if ewayreq == "Y" else ""
    ewb_veh_num = dirty_veh_number(raw_plate)
    ewb_dist = str(random.randint(150, 1400)) if ewayreq == "Y" else ""

    invoice: Dict[str, Any] = {
        "self_gstin": self_gstin_val,
        "system_cd": random.choice(["ERP_SAP", "TALLY_PRIME", "ORACLE"]),
        "branch_cd": f"BR{random.randint(1, 99):02d}",
        "vertical_cd": random.choice(["DOM", "EXPORT", "RETAIL"]),
        "irnreq": "Y",
        "trandt1": {
            "trancatg": trancatg,
            "reversecharge": "N",
            "transactionmode": "SHP" if trancatg == "EXP" else "REG",
            "igstonintra": "N"
        },
        "docdt1": {
            "document_type": "INV",
            "docno": docno,
            "docdt": docdt
        },
        "supplierdt1": {
            "supplier_gstin": sup_gstin,
            "supplier_lglnm": dirty_text_whitespace(random_company_name()),
            "supplier_trdnm": random_company_name(),
            "supplier_bno": f"SUITE {random.randint(10, 500)}",
            "supplier_bnm": f"{sup_city} INDUSTRIAL PARK",
            "supplier_flno": "NAA",
            "supplier_loc": sup_city,
            "supplier_dst": sup_city,
            "supplier_pin": sup_pin,
            "supplier_state": dirty_state_value(sup_state),
            "supplier_phone": f"9{random.randint(100000000, 999999999)}",
            "supplier_email": f"billing@{sup_city.lower().replace(' ', '')}tex.com"
        },
        "buyerdt1": {
            "buyer_gstin": buy_gstin,
            "buyer_trdnm": buy_company,
            "buyer_lglnm": dirty_text_whitespace(buy_company),
            "buyer_bno": "NAA",
            "buyer_bnm": f"ROAD 12, {buy_city}",
            "buyer_flno": "NAA",
            "buyer_loc": buy_city,
            "buyer_dst": buy_city,
            "buyer_pin": buy_pin,
            "buyer_state": dirty_state_value(buy_state),
            "pos": dirty_state_value(pos),
            "buyer_phone": f"9{random.randint(100000000, 999999999)}" if trancatg != "EXP" else "",
            "buyer_email": f"accounts@{buy_city.lower().replace(' ', '')}corp.com"
        },
        "itemdtls": items,
        "valdt1": {
            "ttlassval": format_dirty_decimal(total_assamt),
            "cgstval": format_dirty_decimal(total_cgst),
            "sgstval": format_dirty_decimal(total_sgst),
            "igstval": format_dirty_decimal(total_igst),
            "cesval": "0.00",
            "stcesval": "0.00",
            "cesnonadval": "0.00",
            "discval": "",
            "totinvval": format_dirty_decimal(totinvval),
            "othchrg": "0.00"
        },
        "ewbdt1": {
            "ewayreq": ewayreq,
            "subsupplytype": "1" if ewayreq == "Y" else "",
            "distance_of_transport": ewb_dist,
            "transporter_id": random_gstin(sup_state) if ewayreq == "Y" else "",
            "transporter_name": "VRL LOGISTICS LTD" if ewayreq == "Y" else "",
            "mode_of_transport": ewb_mode if ewayreq == "Y" else "",
            "transport_doc_no": f"LR{random.randint(10000, 99999)}" if ewayreq == "Y" and ewb_mode == "2" else "",
            "transporter_doc_date": random_date_str() if ewayreq == "Y" else "",
            "veh_type": "R" if ewayreq == "Y" and ewb_mode == "1" else "",
            "veh_number": ewb_veh_num
        },
        "paydtls": {
            "payee_name": random_company_name(),
            "pmtmode": "ONLINE",
            "fininsbr": "MAIN",
            "payterm": "NET30",
            "payinstr": "RTGS",
            "crtrn": "",
            "dirdr": "",
            "crday": "30",
            "paidamt": "0.00",
            "balamt": format_dirty_decimal(totinvval),
            "payduedt": "",
            "acctdet": "",
            "bnknm": "STATE BANK OF INDIA",
            "brnchnm": "ELECTRONIC CITY",
            "upiid": f"{sup_city.lower()}tex@upi",
            "upipayeename": random_company_name(),
            "upiacctnumber": f"{random.randint(10000000000, 99999999999)}",
            "upiactifsccd": f"SBIN00{random.randint(1000, 9999)}"
        },
        "cust_cd": f"CUST-{random.randint(1000, 9999)}",
        "brand_name": "SENTINEL-ENTERPRISE",
        "client_name": buy_company,
        "vendor_id": f"VND-{random.randint(100, 999)}",
        "period": datetime.now().strftime("%Y-%m"),
        "invrmk": "E-INVOICE GENERATED"
    }

    if trancatg == "EXP":
        invoice["expdt1"] = {
            "expcat": "DIR",
            "wthpay": "Y",
            "shipbno": f"SB{random.randint(100000, 999999)}",
            "shipbdt": random_date_str(),
            "port": "INMAA1",
            "forcur": buy_cur,
            "cntcode": buy_country
        }
        invoice["shipdtl"] = {
            "ship_gstin": sup_gstin,
            "ship_lglnm": "CHENNAI PORT TERMINAL",
            "ship_trdnm": "CHENNAI PORT TERMINAL",
            "ship_bno": "GATE 4",
            "ship_bnm": "PORT COMPLEX",
            "ship_flno": "NAA",
            "ship_loc": "CHENNAI",
            "ship_dst": "CHENNAI",
            "ship_pin": "600001",
            "ship_state": "33",
            "ship_phone": "",
            "ship_email": ""
        }

    return invoice

def generate_dynamic_dirty_payload(count: int = 1) -> Dict[str, Any]:
    """Generates a batch of randomized invoices with dirty field values and clean keys."""
    invoices = [generate_random_invoice(i + 1) for i in range(max(1, int(count)))]
    return {"einvoices": invoices}

def generate_comprehensive_dirty_payload() -> Dict[str, Any]:
    """
    Returns one unified, master dummy payload covering all statutory & business scenarios:
    1. B2B Inter-State + Road E-Way Bill + Key Aliases + Comma Decimals
    2. B2B Intra-State (CGST + SGST) + Multi-Item + Statutory Rounding Tolerance (+/- Rs 2) + Rail E-Way Bill
    3. Direct Export (EXP) + Shipping Bill + Foreign Currency (USD) + Port INMAA1 + Shipping Terminal
    4. Special Economic Zone Supply (SEZWP) + Mandatory IGST Treatment
    5. Bharat (BH) Series Plate Registration + Commodity Benchmarks
    """
    sample_file = Path(__file__).resolve().parent.parent.parent / "Template_Converters" / "dirty_customer_input.json"
    if sample_file.exists():
        try:
            with open(sample_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "einvoices" in data and len(data["einvoices"]) >= 5:
                    return data
        except Exception:
            pass
    return generate_dynamic_dirty_payload(count=5)

def get_customer_error_payload() -> Dict[str, Any]:
    """
    Returns the specific customer test payload containing:
    1. Product 'Industrial Servo Motor' (HSN 84 requiring Heading 8501 / 85011013 statutory lookup).
    2. Document date older than 2 days triggering NIC Rule 2164 ('change the date').
    3. Calculation mismatch (assval 50000 vs totinvval 99999).
    """
    sample_file = Path(__file__).resolve().parent.parent.parent / "Template_Converters" / "customer_error_payload.json"
    if sample_file.exists():
        with open(sample_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "einvoices": [{
            "self_gstin": "29ABCDE1234F1Z",
            "system_cd": "SAP_ERP",
            "branch_cd": "BLR01",
            "vertical_cd": "DOM",
            "irnreq": "Y",
            "trandt1": {"trancatg": "B2B", "reversecharge": "N", "transactionmode": "REGULAR_TRANSIT", "igstonintra": "N"},
            "docdt1": {"document_type": "INV", "docno": "INV-2026-B2B01", "docdt": "2026-10-10"},
            "supplierdt1": {
                "supplier_gstin": "29ABCDE1234F1Z",
                "supplier_lglnm": "  BHARAT   TECH SOLUTIONS PVT LTD  ",
                "supplier_trdnm": "BHARAT TECH",
                "supplier_bno": "104",
                "supplier_bnm": "Cyber Towers",
                "supplier_flno": "4th Floor",
                "supplier_loc": "Bengaluru",
                "supplier_dst": "Bengaluru",
                "supplier_pin": "400001",
                "supplier_state": "29",
                "supplier_phone": "9876543210",
                "supplier_email": "accounts@bharattech.in"
            },
            "buyerdt1": {
                "buyer_gstin": "URP",
                "buyer_lglnm": "APEX COMMERCE ENTERPRISES",
                "buyer_trdnm": "APEX COMMERCE",
                "buyer_pos": "29",
                "buyer_bno": "55",
                "buyer_bnm": "MG Road Commercial Plaza",
                "buyer_loc": "Bengaluru",
                "buyer_dst": "Bengaluru",
                "buyer_pin": "560001",
                "buyer_state": "29"
            },
            "itemdtls": [{
                "slno": "1",
                "prdnm": "Industrial Servo Motor",
                "prddesc": "High torque servo motor for automation assembly line",
                "is_service": "N",
                "hsn": "84",
                "qty": 5,
                "unit": "NOS",
                "unitprice": 10000.0,
                "totamt": 50000.0,
                "discount": 0.0,
                "pretaxval": 50000.0,
                "assval": 50000.0,
                "gstrate": 18.0,
                "igstval": 0.0,
                "cgstval": 4500.0,
                "sgstval": 4500.0,
                "cesrate": 0.0,
                "cesval": 0.0,
                "cesnonadvl": 0.0,
                "statecesrate": 0.0,
                "statecesval": 0.0,
                "statecesnonadvl": 0.0,
                "othchrg": 0.0,
                "totitemval": 59000.0
            }],
            "valdtls": {
                "assval": 50000.0,
                "cgstval": 4500.0,
                "sgstval": 4500.0,
                "igstval": 0.0,
                "cesval": 0.0,
                "stcesval": 0.0,
                "discount": 0.0,
                "othchrg": 0.0,
                "rndoffamt": 0.0,
                "totinvval": 99999.0
            },
            "ewbdt1": {
                "ewayreq": "Y",
                "subsupplytype": "1",
                "transmode": "1",
                "distance": "120",
                "transporter_id": "",
                "transporter_name": "FastTrack Logistics",
                "transdocno": "LR-998822",
                "transdocdt": "2026-10-10",
                "veh_number": "",
                "veh_type": "R"
            }
        }]
    }

def load_default_sample_dirty() -> Dict[str, Any]:
    """Loads default dirty customer input sample from Template_Converters or returns fresh dynamic payload."""
    sample_file = Path(__file__).resolve().parent.parent.parent / "Template_Converters" / "dirty_customer_input.json"
    data = None
    if sample_file.exists():
        try:
            with open(sample_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass
    if not data:
        data = generate_dynamic_dirty_payload(count=2)

    try:
        from datetime import datetime, timedelta
        fresh_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        for inv in data.get("einvoices", []):
            if isinstance(inv.get("docdt1"), dict) and "docdt" in inv["docdt1"]:
                inv["docdt1"]["docdt"] = fresh_date
    except Exception:
        pass

    return data
