"""
Payload Builder and Auto-Correction Engine for Indian GST E-Invoice & E-Way Bill.
Cleanses dirty keys (OCR/manual typos), normalizes formats, enforces tax math,
generates compliant NIC JSON payloads, and maintains a complete, detailed Audit Log
of every correction applied.
"""

import re
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List, Optional, Tuple, Union
from collections import OrderedDict

try:
    from .error_mappings import (
        COUNTRY_CURRENCY_MAP,
        ALLOWED_UQC,
        ALLOWED_TAX_RATES,
        ALLOWED_DOC_TYPES,
        ALLOWED_TRAN_CATG,
        ALLOWED_EXP_CAT,
        ALLOWED_TRANS_MODE,
        VALID_STATE_CODES,
        classify_rule_2177_diagnostic,
        normalize_uqc_statutory,
        OFFICIAL_UQC_MASTER,
        COMMON_UQC_MAPPING,
    )
except ImportError:
    from error_mappings import (
        COUNTRY_CURRENCY_MAP,
        ALLOWED_UQC,
        ALLOWED_TAX_RATES,
        ALLOWED_DOC_TYPES,
        ALLOWED_TRAN_CATG,
        ALLOWED_EXP_CAT,
        ALLOWED_TRANS_MODE,
        VALID_STATE_CODES,
        classify_rule_2177_diagnostic,
        normalize_uqc_statutory,
        OFFICIAL_UQC_MASTER,
        COMMON_UQC_MAPPING,
    )

try:
    from .price_anomaly_detector import PriceAnomalyDetector
except ImportError:
    try:
        from price_anomaly_detector import PriceAnomalyDetector
    except ImportError:
        PriceAnomalyDetector = None

try:
    from .hsn_resolver import lookup_hsn_code, validate_nic_2day_rule, audit_and_rectify_line_item_sentinel, validate_hsn_statutory
except ImportError:
    try:
        from hsn_resolver import lookup_hsn_code, validate_nic_2day_rule, audit_and_rectify_line_item_sentinel, validate_hsn_statutory
    except ImportError:
        lookup_hsn_code = None
        validate_nic_2day_rule = None
        audit_and_rectify_line_item_sentinel = None
        validate_hsn_statutory = None

try:
    from src.rules.rate_slab_checker import rate_slab_checker
    from src.rules.section_17_5_detector import section_17_5_detector
except ImportError:
    try:
        import sys
        from pathlib import Path
        _root = Path(__file__).resolve().parent.parent
        if str(_root) not in sys.path:
            sys.path.insert(0, str(_root))
        from src.rules.rate_slab_checker import rate_slab_checker
        from src.rules.section_17_5_detector import section_17_5_detector
    except Exception:
        rate_slab_checker = None
        section_17_5_detector = None

try:
    from src.ingestion.schemas import (
        normalize_reverse_charge,
        get_reverse_charge_rejection_reason,
        get_ist_today,
        get_ist_now,
        classify_future_date_diagnostic,
        classify_rule_2172_diagnostic,
        classify_rule_2173_diagnostic,
        classify_rule_2174_diagnostic,
        aggregate_redundant_line_items,
        split_invoice_payload_chunks,
    )
except Exception:
    try:
        import sys
        from pathlib import Path
        _root = Path(__file__).resolve().parent.parent
        if str(_root) not in sys.path:
            sys.path.insert(0, str(_root))
        from src.ingestion.schemas import (
            normalize_reverse_charge,
            get_reverse_charge_rejection_reason,
            get_ist_today,
            get_ist_now,
            classify_future_date_diagnostic,
            classify_rule_2172_diagnostic,
            classify_rule_2173_diagnostic,
            classify_rule_2174_diagnostic,
            aggregate_redundant_line_items,
            split_invoice_payload_chunks,
        )
    except Exception:
        normalize_reverse_charge = None
        get_reverse_charge_rejection_reason = None
        get_ist_today = None
        get_ist_now = None
        classify_future_date_diagnostic = None
        classify_rule_2172_diagnostic = None
        classify_rule_2173_diagnostic = None
        classify_rule_2174_diagnostic = None
        aggregate_redundant_line_items = None
        split_invoice_payload_chunks = None

KEY_ALIASES = {
    # Header
    "system.cd": "system_cd", "system cd": "system_cd",
    "vertical cd": "vertical_cd", "vertical.cd": "vertical_cd",
    "branch cd": "branch_cd", "branch.cd": "branch_cd",
    "self gstin": "self_gstin",
    
    # trandt1
    "trancatg": "trancatg", "tran_catg": "trancatg", "supply_type": "trancatg", "suptyp": "trancatg",
    "reversecharge": "reversecharge", "reverse_charge": "reversecharge", "rev_chrg": "reversecharge",
    "revchrg": "reversecharge", "revcharge": "reversecharge", "rcm": "reversecharge", "regrev": "reversecharge",
    "trandtls": "trandt1", "tran_dtls": "trandt1", "trandtl": "trandt1",
    "transactionmode": "transactionmode", "trans_mode": "transactionmode",
    "igstonintra": "igstonintra", "igst_on_intra": "igstonintra", "igst on intra": "igstonintra",
    
    # expdt1
    "expcat": "expcat", "exp_cat": "expcat",
    "wthpay": "wthpay", "wth_pay": "wthpay",
    "shipbno": "shipbno",
    "shipbdt": "shipbdt", "ship_bdt": "shipbdt",
    "forcur": "forcur", "foreign_currency": "forcur",
    "cntcode": "cntcode", "country_code": "cntcode",
    
    # docdt1
    "document_type": "document_type", "doc_type": "document_type",
    "docno": "docno", "doc_no": "docno", "document_no": "docno",
    "docdt": "docdt", "doc_dt": "docdt", "document_date": "docdt",
    "dt": "docdt", "docdate": "docdt", "doc_date": "docdt",
    
    # supplierdt1
    "supplier_lginm": "supplier_lglnm", "supplier_1g1nm": "supplier_lglnm", "supplier lglnm": "supplier_lglnm",
    "supplier_trdnm": "supplier_trdnm", "supplier trdnm": "supplier_trdnm",
    "supplier_bno": "supplier_bno", "supplier bno": "supplier_bno",
    "supplier_bnm": "supplier_bnm", "supplier bnm": "supplier_bnm",
    "supplier flno": "supplier_flno", "supplier_flno": "supplier_flno", "supplier fino": "supplier_flno",
    "supplier_loc": "supplier_loc", "supplier loc": "supplier_loc",
    "supplier_dst": "supplier_dst", "supplier dst": "supplier_dst",
    "supplier_pin": "supplier_pin", "supplier pin": "supplier_pin",
    "supplier state": "supplier_state", "supplier_state": "supplier_state",
    "supplier_phone": "supplier_phone", "supplier phone": "supplier_phone",
    "supplier_email": "supplier_email", "supplier email": "supplier_email",
    
    # buyerdt1
    "buyer_lginm": "buyer_lglnm", "buyer_1g1nm": "buyer_lglnm", "buyer lglnm": "buyer_lglnm",
    "buyer_trdnm": "buyer_trdnm", "buyer trdnm": "buyer_trdnm",
    "buyer_bno": "buyer_bno", "buyer bno": "buyer_bno",
    "buyer_bnm": "buyer_bnm", "buyer bnm": "buyer_bnm",
    "buyer flno": "buyer_flno", "buyer_flno": "buyer_flno", "buyer fino": "buyer_flno",
    "buyer loc": "buyer_loc", "buyer_loc": "buyer_loc",
    "buyer_dst": "buyer_dst", "buyer dst": "buyer_dst",
    "buyer pin": "buyer_pin", "buyer_pin": "buyer_pin",
    "buyer state": "buyer_state", "buyer_state": "buyer_state",
    "buyer phone": "buyer_phone", "buyer_phone": "buyer_phone",
    "buyer email": "buyer_email", "buyer_email": "buyer_email",
    
    # shipdtl / dispdt1
    "ship 1g1nm": "ship_lglnm", "ship_lginm": "ship_lglnm", "ship_1g1nm": "ship_lglnm",
    "ship bno": "ship_bno", "ship bnm": "ship_bnm", "ship flno": "ship_flno",
    "ship loc": "ship_loc", "ship dst": "ship_dst", "ship pin": "ship_pin",
    "ship state": "ship_state", "ship phone": "ship_phone", "ship email": "ship_email",
    
    # Line items
    "hsn": "hsncd", "hsn_code": "hsncd", "hsn code": "hsncd",
    "is_service": "isservc", "is service": "isservc", "isservice": "isservc",
    "unit": "uqc", "ugc": "uqc", "uom": "uqc",
    "unit_rate": "unitrate", "unitprice": "unitrate", "unit_price": "unitrate",
    "gross_amt": "grossamt", "gross_amount": "grossamt", "totamt": "grossamt", "total_amt": "grossamt",
    "pretaxval": "pretaxval", "pretax_val": "pretaxval", "pre_tax_val": "pretaxval",
    "ass_amt": "assamt", "taxable_amt": "assamt", "assval": "assamt", "taxable_val": "assamt", "taxable_value": "assamt",
    "gstrate": "gstrate", "gst_rate": "gstrate", "gst rate": "gstrate", "gstrt": "gstrate",
    "cgstval": "cgstval", "sgstval": "sgstval", "igstval": "igstval",
    "cgstamt": "cgstamt", "sgstamt": "sgstamt", "igstamt": "igstamt",
    "cesrate": "cessrt", "cesval": "cesval", "cessamt": "cessamt", "cesnonadvl": "cessnonadval",
    "statecesrate": "statecessrt", "statecesval": "statecessamt",
    "tot_item_val": "totitemval", "total_item_value": "totitemval",
    
    # valdt1
    "total_taxable_value": "ttlassval", "total_ass_val": "ttlassval",
    "total_cgst": "cgstval", "total_sgst": "sgstval", "total_igst": "igstval",
    "total_cess": "cesval", "total_state_cess": "stcesval",
    "total_inv_val": "totinvval", "total_invoice_value": "totinvval",
    "oth_chrg": "othchrg", "other_charges": "othchrg",
    "disc_val": "discval", "discount_val": "discval"
}

def clean_key_name(raw_key: str) -> str:
    """Dynamically normalizes arbitrary dictionary keys."""
    k = str(raw_key).strip().lower()
    if k in KEY_ALIASES:
        return KEY_ALIASES[k]
    k_norm = re.sub(r"[\s\.\-]+", "_", k)
    if k_norm in KEY_ALIASES:
        return KEY_ALIASES[k_norm]
    k_norm = k_norm.replace("1g1nm", "lglnm").replace("lginm", "lglnm").replace("fino", "flno")
    if k_norm in ("ugc", "uom", "unit_qty_cd"):
        k_norm = "uqc"
    return KEY_ALIASES.get(k_norm, k_norm)

def normalize_dict_keys_with_log(d: Any, path: str = "") -> Tuple[Any, List[Dict[str, Any]]]:
    """Recursively normalizes keys and records every key change in the audit trail."""
    modifications = []
    if isinstance(d, dict):
        new_d = {}
        for k, v in d.items():
            clean_k = clean_key_name(k)
            curr_path = f"{path}.{k}" if path else k
            if clean_k != k:
                modifications.append({
                    "category": "KEY_NAME_NORMALIZATION",
                    "field": curr_path,
                    "original": k,
                    "corrected": clean_k,
                    "description": f"Standardized non-compliant key '{k}' to schema key '{clean_k}'"
                })
            cleaned_v, child_mods = normalize_dict_keys_with_log(v, curr_path)
            modifications.extend(child_mods)
            new_d[clean_k] = cleaned_v
        return new_d, modifications
    elif isinstance(d, list):
        new_list = []
        for idx, item in enumerate(d):
            curr_path = f"{path}[{idx+1}]"
            cleaned_item, child_mods = normalize_dict_keys_with_log(item, curr_path)
            modifications.extend(child_mods)
            new_list.append(cleaned_item)
        return new_list, modifications
    return d, modifications

# ============================================================================
# Master Definitions from Part 1
# ============================================================================

COUNTRY_CURRENCY_MAP = {
    "IN": "INR",
    "US": "USD",
    "GB": "GBP",
    "AE": "AED",
    "SG": "SGD",
    "JP": "JPY",
    "AU": "AUD",
    "CA": "CAD",
    "CN": "CNY",
    "HK": "HKD",
    "DE": "EUR",
    "FR": "EUR",
    "IT": "EUR",
}

ALLOWED_UQC = [
    "BAG", "BAL", "BDL", "BKL", "BOU", "BOX", "BTL", "BUN", "CAN", "CBM", 
    "CCM", "CMS", "CTN", "DOZ", "DRM", "GGR", "GMS", "GRS", "GYD", "KGS", "KLR", 
    "KME", "MLT", "MTR", "MTS", "NOS", "PAC", "PCS", "PRS", "QTL", "ROL", 
    "SET", "SQF", "SQM", "SQY", "TBS", "TGM", "THD", "TON", "TUB", "UGS", 
    "UNT", "YDS", "OTH"
]

# ============================================================================
# Part 1 Normalization Helpers
# ============================================================================

def normalize_buyer_gstin(raw: str):
    if raw is None:
        return ""
    s = str(raw).strip().upper()
    if s != "URP":
        s = re.sub(r"[^0-9A-Z]", "", s)
    return s

def normalize_numeric_string(raw: str):
    if raw is None:
        return ""
    s = str(raw).strip()
    return re.sub(r"[^0-9]", "", s)

def normalize_date(raw: str):
    if raw is None:
        return ""
    s = str(raw).strip()
    normalized = re.sub(r"[-. ]", "/", s)
    return normalized

def normalize_gstin(raw: str):
    s = "" if raw is None else str(raw).strip().upper()
    s = s.replace(" ", "")
    normalized = re.sub(r"[^0-9A-Z]", "", s)
    return normalized

def normalize_uppercase(raw: str):
    if raw is None:
        return ""
    return str(raw).strip().upper()

def normalize_field(raw: str):
    if raw is None:
        return ""
    return str(raw).strip()

def normalize_doc_number(raw: str):
    if raw is None:
        return ""
    s = str(raw).strip()
    normalized = re.sub(r"[^0-9A-Za-z/-]", "", s)
    return normalized

def normalize_email(raw: str):
    if raw is None:
        return ""
    return str(raw).strip().lower()

def normalize_ship_gstin(raw: str):
    if raw is None:
        return ""
    s = str(raw).strip().upper()
    if s != "URP":
        s = re.sub(r"[^0-9A-Z]", "", s)
    return s

def normalize_ship_lglnm(raw: str):
    if raw is None:
        return ""
    return str(raw).strip()

def normalize_ship_trdnm(raw: str):
    if raw is None:
        return ""
    return str(raw).strip()

def normalize_ship_bno(raw: str):
    if raw is None:
        return ""
    return str(raw).strip()

def normalize_ship_bnm(raw: str):
    if raw is None:
        return ""
    return " ".join(str(raw).split()).strip()

def normalize_ship_flno(raw: str):
    if raw is None:
        return ""
    return " ".join(str(raw).split()).strip()

def normalize_ship_loc(raw: str):
    if raw is None:
        return ""
    return " ".join(str(raw).split()).strip()

def normalize_ship_dst(raw: str):
    if raw is None:
        return ""
    return " ".join(str(raw).split()).strip()

def normalize_ship_pin(raw: str):
    if raw is None:
        return ""
    s = str(raw).strip()
    return re.sub(r"[^0-9]", "", s)

def normalize_state_code(raw: str):
    if raw is None:
        return ""
    s = re.sub(r"[^0-9]", "", str(raw).strip())
    if len(s) == 1:
        s = s.zfill(2)
    return s

def normalize_date_dash(raw: str):
    if raw is None:
        return ""
    s = str(raw).strip()
    normalized = re.sub(r"[/ .]", "-", s)
    return normalized

def normalize_product_name(raw: str):
    if raw is None:
        return ""
    return " ".join(str(raw).split()).strip()

def process_payload(input_file: Any, output_valid: str = "valid.json", output_invalid: str = "invalid.json"):
    if isinstance(input_file, dict):
        payload = input_file
    else:
        try:
            with open(input_file, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception as e:
            print(f"Failed to read input file: {e}")
            return None

    errors = []
    warnings = []
    def get_nrom(key, func=normalize_field):
        return func(payload.get(key, ""))

    allowed_pmt_modes = ["CASH", "EPAY", "DIRDBT", "OTH"]
    allowed_trancatg = ["B2B", "B2G", "EXP", "B2C"]
    ALLOWED_TAXABILITY = ["TAX", "EXM", "NIL", "NGT"]
    allowed_transmode = ["REG", "DIS", "SHP", "CMB"]
    allowed_expcat = ["DIR", "DEM", "SEZ", "SED"]
    allowed_doc_types = ["INV", "CRN", "DBN", "CHL", "BIL", "OTH"]
    date_pattern = r"^[0-3][0-9]/[0-1][0-9]/[2][0][1-2][0-9]$"
    port_pattern = r"^[0-9A-Z]{6,10}$"
    buyer_gstin_pattern = r"^[0-9]{2}[0-9A-Z]{13}$"
    gstin_pattern = r"^[0-9]{2}[0-9A-Z]{13}$"
    ship_gstin_pattern = r"^(?:[0-9]{2}[0-9A-Z]{13}|URP)$"
    date_pattern_dash = r"^[0-3][0-9]-[0-1][0-9]-[2][0][1-2][0-9]$"
    date_regex = r"^[0-3][0-9]-[0-1][0-9]-20[1-2][0-9]$"
    remark_pattern = r"^[0-9A-Za-z/\-\(\) ]*$"
    adv_pattern = r"^[0-9A-Za-z/\-\(\)]*$"
    tend_pattern = r"^[0-9A-Za-z/\-\(\)]*$"
    contr_pattern = r"^[0-9A-Za-z/\-\(\)]*$"
    ext_pattern = r"^[0-9A-Za-z/\-\(\)]*$"
    proj_pattern = r"^[0-9A-Za-z/\-\(\)]*$"
    po_pattern = r"^[0-9A-Za-z/\-\(\)]*$"
    allowed_values = ["Y", "N"]
    valid_subtypes = [str(i) for i in range(1, 13)]
    valid_modes = ["1", "2", "3", "4"]
    raw_dist = payload.get("distance_of_transport") if isinstance(payload, dict) else ""
    trans_id_pattern = r"^[0-9]{2}[A-Z0-9]{13}$"
    non_road_modes = ["2", "3", "4"]
    allowed_veh_types = ["R", "O"]
    veh_pattern = r"^[A-Z]{2}[0-9]{2}[A-Z0-9]{1,2}[0-9]{4}$"
    upi_pattern = r"^[\w\.\-]+@[a-zA-Z]{2,}$"
    ifsc_pattern = r"^[A-Z]{4}0[A-Z0-9]{6}$"
    target_format = "%d-%m-%Y"

    if not isinstance(payload, dict):
        return {"payload": payload, "errors": errors}

    norm_gstin       = normalize_gstin(payload.get("self_gstin", ""))
    norm_sys         = normalize_field(payload.get("system_cd", ""))
    norm_br          = normalize_field(payload.get("branch_cd", ""))
    norm_vert        = normalize_field(payload.get("vertical_cd", ""))
    norm_irnreq      = normalize_uppercase(payload.get("irnreq", ""))
    norm_irn         = normalize_field(payload.get("irn", ""))
    norm_trancatg    = normalize_uppercase(payload.get("trancatg", ""))
    raw_rev          = payload.get("reversecharge", payload.get("RevChrg", payload.get("revchrg", "")))
    norm_revcharge   = normalize_reverse_charge(raw_rev)[0] if normalize_reverse_charge else normalize_uppercase(raw_rev)
    norm_transmode   = normalize_uppercase(payload.get("transactionmode", ""))
    norm_ecom_gstin  = normalize_gstin(payload.get("ecom_gstin", ""))
    norm_igst_intra  = normalize_uppercase(payload.get("igst_on_intra", ""))
    norm_expcat      = normalize_uppercase(payload.get("expcat", ""))
    norm_wthpay      = normalize_uppercase(payload.get("wthpay", ""))
    norm_shipbno     = normalize_field(payload.get("shipbno", ""))
    norm_shipbdt     = normalize_date(payload.get("shipbdt", ""))
    norm_port        = normalize_uppercase(payload.get("port", ""))
    norm_invforcur   = normalize_field(payload.get("invforcur", ""))
    norm_forcur      = normalize_uppercase(payload.get("forcur", ""))
    norm_refclm      = normalize_uppercase(payload.get("refclm", ""))
    norm_cntcode     = normalize_uppercase(payload.get("cntcode", ""))
    norm_expduty     = normalize_field(payload.get("expduty", ""))
    norm_doc_type    = normalize_uppercase(payload.get("document_type", ""))
    norm_docno       = normalize_doc_number(payload.get("docno", ""))
    raw_docdt        = payload.get("docdt", "")
    norm_docdt       = ""
    norm_orginvno    = normalize_doc_number(payload.get("orginvno", ""))
    norm_orginvdt    = normalize_date(payload.get("orginvdt", ""))
    norm_sup_gstin   = normalize_gstin(payload.get("supplier_gstin", ""))
    norm_sup_lglnm   = normalize_field(payload.get("supplier_lglnm", ""))
    norm_sup_trdnm   = normalize_field(payload.get("supplier_trdnm", ""))
    norm_sup_bno     = normalize_field(payload.get("supplier_bno", ""))
    norm_sup_bnm     = normalize_field(payload.get("supplier_bnm", ""))
    norm_sup_flno    = normalize_field(payload.get("supplier_flno", ""))
    norm_sup_loc     = normalize_field(payload.get("supplier_loc", ""))
    norm_sup_dst     = normalize_field(payload.get("supplier_dst", ""))
    norm_sup_pin     = normalize_numeric_string(payload.get("supplier_pin", ""))
    norm_sup_state   = normalize_numeric_string(payload.get("supplier_state", ""))
    norm_sup_phone   = normalize_numeric_string(payload.get("supplier_phone", ""))
    norm_sup_email   = normalize_field(payload.get("supplier_email", ""))
    norm_cust_cd     = normalize_field(payload.get("cust_cd", ""))
    norm_buy_gstin   = normalize_buyer_gstin(payload.get("buyer_gstin", ""))
    norm_buy_lglnm   = normalize_field(payload.get("buyer_lglnm", ""))
    norm_buy_trdnm   = normalize_field(payload.get("buyer_trdnm", ""))
    norm_buy_bno     = normalize_field(payload.get("buyer_bno", ""))
    norm_buy_bnm     = normalize_field(payload.get("buyer_bnm", ""))
    norm_buy_flno    = normalize_field(payload.get("buyer_flno", ""))
    norm_buy_loc     = normalize_field(payload.get("buyer_loc", ""))
    norm_buy_dst     = normalize_field(payload.get("buyer_dst", ""))
    norm_buy_pin     = normalize_numeric_string(payload.get("buyer_pin", ""))
    norm_buy_state   = normalize_numeric_string(payload.get("buyer_state", ""))
    raw_pos          = payload.get("pos", "")
    norm_pos         = normalize_numeric_string(raw_pos)
    norm_buy_phone   = normalize_numeric_string(payload.get("buyer_phone", ""))
    norm_buy_email   = normalize_field(payload.get("buyer_email", ""))
    norm_disp_gstin  = normalize_buyer_gstin(payload.get("disp_gstin", ""))
    norm_disp_trdnm  = normalize_field(payload.get("disp_trdnm", ""))
    norm_disp_bno    = normalize_field(payload.get("disp_bno", ""))
    norm_disp_bnm    = normalize_field(payload.get("disp_bnm", ""))
    norm_disp_flno   = normalize_field(payload.get("disp_flno", ""))
    norm_disp_loc    = normalize_field(payload.get("disp_loc", ""))
    norm_disp_dst    = normalize_field(payload.get("disp_dst", ""))
    norm_disp_pin    = normalize_numeric_string(payload.get("disp_pin", ""))
    norm_disp_state  = normalize_numeric_string(payload.get("disp_state", ""))
    norm_disp_phone  = normalize_numeric_string(payload.get("disp_phone", ""))
    norm_disp_email  = normalize_email(payload.get("disp_email", ""))
    norm_ship_gstin  = normalize_ship_gstin(payload.get("ship_gstin", ""))
    norm_ship_lglnm  = normalize_ship_lglnm(payload.get("ship_lglnm", ""))
    norm_ship_trdnm  = normalize_ship_trdnm(payload.get("ship_trdnm", ""))
    norm_ship_bno    = normalize_ship_bno(payload.get("ship_bno", ""))
    norm_ship_bnm    = normalize_ship_bnm(payload.get("ship_bnm", ""))
    norm_ship_flno   = normalize_ship_flno(payload.get("ship_flno", ""))
    norm_ship_loc    = normalize_ship_loc(payload.get("ship_loc", ""))
    norm_ship_dst    = normalize_ship_dst(payload.get("ship_dst", ""))
    norm_ship_pin    = normalize_ship_pin(payload.get("ship_pin", ""))
    norm_ship_state  = normalize_state_code(payload.get("ship_state", ""))
    norm_ship_phone  = normalize_numeric_string(payload.get("ship_phone", ""))
    norm_ship_email  = normalize_email(payload.get("ship_email", ""))
    norm_frmdt       = normalize_date_dash(payload.get("frmdt", ""))
    norm_todt        = normalize_date_dash(payload.get("todt", ""))
    norm_itemcd      = normalize_field(payload.get("itemcd", ""))
    norm_prdnm       = normalize_product_name(payload.get("prdnm", ""))
    norm_prddesc     = " ".join(str(payload.get("prddesc", "")).split()).strip() if payload.get("prddesc") else ""
    norm_isservc     = normalize_uppercase(payload.get("isservc", ""))
    norm_hsncd       = normalize_numeric_string(payload.get("hsncd", ""))
    norm_barcde      = normalize_field(payload.get("barcde", ""))
    norm_qty         = str(payload.get("qty", "")).strip() if payload.get("qty") is not None else ""
    norm_freeqty     = str(payload.get("freeqty", "")).strip() if payload.get("freeqty") is not None else ""
    norm_uqc         = normalize_uppercase(payload.get("uqc", ""))
    norm_unitrate    = str(payload.get("unitrate", "")).strip() if payload.get("unitrate") is not None else ""
    norm_grossamt    = str(payload.get("grossamt", "")).strip() if payload.get("grossamt") is not None else ""
    norm_discount    = str(payload.get("discount", "")).strip() if payload.get("discount") is not None else ""
    norm_othchrg     = str(payload.get("othchrg", "")).strip() if payload.get("othchrg") is not None else ""
    norm_pretaxval   = str(payload.get("pretaxval", "")).strip() if payload.get("pretaxval") is not None else ""
    norm_assamt      = str(payload.get("assamt", "")).strip() if payload.get("assamt") is not None else ""
    norm_taxability  = normalize_uppercase(payload.get("taxability", ""))
    norm_diffpercent = str(payload.get("diffpercent", "")).strip() if payload.get("diffpercent") is not None else ""
    norm_cgstrt      = str(payload.get("cgstrt", "")).strip() if payload.get("cgstrt") is not None else ""
    norm_cgstamt     = str(payload.get("cgstamt", "")).strip() if payload.get("cgstamt") is not None else ""
    norm_sgstrt      = str(payload.get("sgstrt", "")).strip() if payload.get("sgstrt") is not None else ""
    norm_sgstamt     = str(payload.get("sgstamt", "")).strip() if payload.get("sgstamt") is not None else ""
    norm_igstrt      = str(payload.get("igstrt", "")).strip() if payload.get("igstrt") is not None else ""
    norm_igstamt     = str(payload.get("igstamt", "")).strip() if payload.get("igstamt") is not None else ""
    norm_cessrt      = str(payload.get("cessrt", "")).strip() if payload.get("cessrt") is not None else ""
    norm_cessamt     = str(payload.get("cessamt", "")).strip() if payload.get("cessamt") is not None else ""
    norm_cessnonadval = str(payload.get("cessnonadval", "")).strip() if payload.get("cessnonadval") is not None else ""
    norm_statecessrt = str(payload.get("statecessrt", "")).strip() if payload.get("statecessrt") is not None else ""
    norm_statecessamt = str(payload.get("statecessamt", "")).strip() if payload.get("statecessamt") is not None else ""
    norm_statecesnonadvl = str(payload.get("statecesnonadvlamt", "")).strip() if payload.get("statecesnonadvlamt") is not None else ""
    norm_totitemval  = str(payload.get("totitemval", "")).strip() if payload.get("totitemval") is not None else ""
    norm_ordlineref  = str(payload.get("ordlineref", "")).strip() if payload.get("ordlineref") is not None else ""
    norm_orgcntry    = str(payload.get("orgcntry", "")).strip().upper() if payload.get("orgcntry") is not None else ""
    norm_prdsino     = str(payload.get("prdsino", "")).strip() if payload.get("prdsino") is not None else ""
    norm_batchname   = str(payload.get("batchname", "")).strip() if payload.get("batchname") is not None else ""
    norm_batchexpirydt = str(payload.get("batchexpirydt", "")).strip() if payload.get("batchexpirydt") is not None else ""
    norm_batchwarrantydt = str(payload.get("batchwarrantydt", "")).strip() if payload.get("batchwarrantydt") is not None else ""
    norm_ttlassval   = str(payload.get("ttlassval", "")).strip() if payload.get("ttlassval") is not None else ""
    norm_cgstval     = str(payload.get("cgstval", "")).strip() if payload.get("cgstval") is not None else ""
    norm_sgstval     = str(payload.get("sgstval", "")).strip() if payload.get("sgstval") is not None else ""
    norm_igstval     = str(payload.get("igstval", "")).strip() if payload.get("igstval") is not None else ""
    norm_cesval      = str(payload.get("cesval", "")).strip() if payload.get("cesval") is not None else ""
    norm_stcesval    = str(payload.get("stcesval", "")).strip() if payload.get("stcesval") is not None else ""
    norm_cesnonadval = str(payload.get("cesnonadval", "")).strip() if payload.get("cesnonadval") is not None else ""
    norm_discval     = str(payload.get("discval", "")).strip() if payload.get("discval") is not None else ""
    norm_othchrgval  = str(payload.get("othchrgval", "")).strip() if payload.get("othchrgval") is not None else ""
    norm_rndoffamt   = str(payload.get("rndoffamt", "")).strip() if payload.get("rndoffamt") is not None else ""
    norm_totinvval   = str(payload.get("totinvval", "")).strip() if payload.get("totinvval") is not None else ""
    norm_payee_name  = str(payload.get("payee_name", "")).strip() if payload.get("payee_name") is not None else ""
    norm_pmtmode     = str(payload.get("pmtmode", "")).strip().upper() if payload.get("pmtmode") is not None else ""
    norm_fininsbr    = str(payload.get("fininsbr", "")).strip().upper() if payload.get("fininsbr") is not None else ""
    norm_payterm     = str(payload.get("payterm", "")).strip() if payload.get("payterm") is not None else ""
    norm_payinstr    = str(payload.get("payinstr", "")).strip() if payload.get("payinstr") is not None else ""
    norm_crtrn       = str(payload.get("crtrn", "")).strip() if payload.get("crtrn") is not None else ""
    norm_dirdr       = str(payload.get("dirdr", "")).strip() if payload.get("dirdr") is not None else ""
    norm_crday       = str(payload.get("crday", "")).strip() if payload.get("crday") is not None else ""
    norm_paidamt     = str(payload.get("paidamt", "")).strip() if payload.get("paidamt") is not None else ""
    norm_balamt = str(payload.get("balamt", "")).strip() if payload.get("balamt") is not None else ""
    norm_payduedt = str(payload.get("payduedt", "")).strip().replace("/", "-") if payload.get("payduedt") is not None else ""
    norm_acctdet = str(payload.get("acctdet", "")).strip() if payload.get("acctdet") is not None else ""
    norm_bnknm = str(payload.get("bnknm", "")).strip() if payload.get("bnknm") is not None else ""
    norm_brnchnm = str(payload.get("brnchnm", "")).strip() if payload.get("brnchnm") is not None else ""
    norm_invrmk = str(payload.get("invrmk", "")).strip() if payload.get("invrmk") is not None else ""
    norm_invstdt = str(payload.get("invstdt", "")).strip().replace("/", "-") if payload.get("invstdt") is not None else ""
    norm_invenddt = str(payload.get("invenddt", "")).strip().replace("/", "-") if payload.get("invenddt") is not None else ""
    norm_othrefno = str(payload.get("othrefno", "")).strip() if payload.get("othrefno") is not None else ""
    norm_recadvref = str(payload.get("recadvref", "")).strip() if payload.get("recadvref") is not None else ""
    norm_recadvdt = str(payload.get("recadvdt", "")).strip().replace("/", "-") if payload.get("recadvdt") is not None else ""
    norm_tendref = str(payload.get("tendref", "")).strip() if payload.get("tendref") is not None else ""
    norm_contrref = str(payload.get("contrref", "")).strip() if payload.get("contrref") is not None else ""
    norm_extref = str(payload.get("extref", "")).strip() if payload.get("extref") is not None else ""
    norm_projref = str(payload.get("projref", "")).strip() if payload.get("projref") is not None else ""
    raw_porefdt = payload.get("porefdt", "")
    norm_porefdt = ""
    norm_poref = str(payload.get("poref", "")).strip() if payload.get("poref") is not None else ""
    norm_ewayreq = str(payload.get("ewayreq", "")).strip().upper()
    norm_subsupplytype = str(payload.get("subsupplytype", "")).strip() if payload.get("subsupplytype") is not None else ""
    norm_mode_of_transport = str(payload.get("mode_of_transport", "")).strip() if payload.get("mode_of_transport") is not None else ""
    norm_distance_str = str(raw_dist).strip() if raw_dist is not None else ""
    norm_distance = norm_distance_str
    norm_distance_val = None
    try:
        if raw_dist is not None and str(raw_dist).strip() != "":
            norm_distance_val = int(raw_dist)
    except (ValueError, TypeError):
        errors.append(f"Invalid distance_of_transport:'{raw_dist}'.Must be a number")
    norm_transporter_id = str(payload.get("transporter_id", "")).strip().upper()
    norm_transporter_name = str(payload.get("transporter_name", "")).strip() if payload.get("transporter_name") is not None else ""
    norm_transport_doc_no = str(payload.get("transport_doc_no", "")).strip().upper()
    norm_trans_doc_dt = str(payload.get("transporter_doc_date", "")).strip().replace("/", "-") if payload.get("transporter_doc_date") is not None else ""
    norm_veh_type = str(payload.get("veh_type", "")).strip().upper()
    raw_veh = str(payload.get("veh_number", "")).strip().upper()
    norm_veh_number = raw_veh.replace(" ", "").replace("-", "")
    norm_brand_name = str(payload.get("brand_name", "")).strip() if payload.get("brand_name") is not None else ""
    norm_client_name = str(payload.get("client_name", "")).strip() if payload.get("client_name") is not None else ""
    norm_vendor_id = str(payload.get("vendor_id", "")).strip() if payload.get("vendor_id") is not None else ""
    norm_period = str(payload.get("period", "")).strip() if payload.get("period") is not None else ""
    norm_upiid = str(payload.get("upiid", "")).strip().lower() if payload.get("upiid") is not None else ""
    norm_upipayeename = str(payload.get("upipayeename", "")).strip() if payload.get("upipayeename") is not None else ""
    norm_upiacct = str(payload.get("upiacctnumber", "")).strip() if payload.get("upiacctnumber") is not None else ""
    norm_upi_ifsc = str(payload.get("upiactifsccd", "")).strip().upper() if payload.get("upiactifsccd") is not None else ""
    mandatory_fields = [
        "self_gstin", "system_cd", "branch_cd", "vertical_cd", 
        "irnreq", "irn", "trancatg", "reversecharge", "transactionmode",
        "ecom_gstin", "igst_on_intra", "expcat", "wthpay", "shipbno", 
        "shipbdt", "port", "invforcur", "forcur", "refclm", "cntcode", "expduty", "document_type", "docno", "docdt", "orginvno",
        "orginvdt", "supplier_gstin", "supplier_lglnm", "supplier_trdnm", "supplier_bno", "supplier_bnm", "supplier_flno",
        "supplier_loc", "supplier_dst", "supplier_pin", "supplier_state", 
        "supplier_phone", "supplier_email", "cust_cd", "buyer_gstin", "buyer_lglnm", "buyer_trdnm", "buyer_bno", "buyer_bnm",
        "buyer_flno", "buyer_loc", "buyer_dst", "buyer_pin", "buyer_state", "pos", "buyer_phone", "buyer_email", "disp_gstin",
        "disp_trdnm", "disp_bno", "disp_bnm", "disp_flno", "disp_loc", "disp_dst", "disp_pin", "disp_state", "disp_phone", "disp_email",
        "ship_gstin", "ship_lglnm", "ship_trdnm", "ship_bno", "ship_bnm", "ship_flno", "ship_loc", "ship_dst", "ship_pin", "ship_state",
        "ship_phone", "ship_email", "frmdt", "todt", "itemcd", "prdnm", "prddesc", "isservc", "hsncd", "barcde", "qty", "freeqty", "uqc",
        "unitrate", "grossamt", "discount", "othchrg", "pretaxval", "assamt", "taxability", "diffpercent", "cgstrt", "cgstamt", "sgstrt",
        "sgstamt", "igstrt", "igstamt", "cessrt", "cessamt", "cessnonadval", "statecessrt", "statecessamt", "statecesnonadvlamt", "totitemval",
        "ordlineref", "orgcntry", "prdsino", "batchname", "batchexpirydt", "batchwarrantydt", "ttlassval", "cgstval", "sgstval",
        "igstval", "cesval", "stcesval", "cesnonadval", "discval", "othchrgval", "rndoffamt", "totinvval", "payee_name", "pmtmode", "fininsbr",
        "payterm", "payinstr", "crtrn", "dirdr", "crday", "paidamt", "balamt", "payduedt", "acctdet", "bnknm", "brnchnm", "invrmk", "invstdt",
        "invenddt", "othrefno", "recadvref", "recadvdt", "tendref", "contrref", "extref", "projref", "porefdt", "poref", "ewayreq", "subsupplytype",
        "mode_of_transport", "distance_of_transport", "transporter_id", "transporter_name", "transport_doc_no", "transporter_doc_date", "veh_type",
        "veh_number", "brand_name", "client_name", "vendor_id", "period", "upiid", "upipayeename", "upiacctnumber", "upiactifsccd"
    ]
    
    missing = [f for f in mandatory_fields if f not in payload]
    if missing:
        errors.append(f"Mandatory field key(s) missing: {', '.join(missing)}")
    if not norm_gstin:
        errors.append("self_gstin cannot be blank or null")
    elif len(norm_gstin) != 15:
        errors.append(f"Invalid self_gstin length ({len(norm_gstin)})")
    elif not norm_gstin[:2].isdigit():
        errors.append("self_gstin state code must be numeric")
    if not norm_trancatg:
        errors.append("Transaction Category (trancatg) cannot be blank")
    elif norm_trancatg not in allowed_trancatg:
        errors.append(f"Invalid trancatg. Must be one of {allowed_trancatg}")
    if norm_refclm and norm_refclm not in ["Y", "N"]:
        errors.append(f"Invalid refclm value '{norm_refclm}'. Must be 'Y' or 'N'")
    if norm_trancatg == "EXP":
        if not norm_cntcode:
            errors.append("cntcode is mandatory when trancatg is 'EXP'")
        elif len(norm_cntcode) != 2:
            errors.append(f"Invalid cntcode length. Got: '{norm_cntcode}' (Expected 2)")
        if not norm_forcur:
            errors.append("forcur is mandatory when trancatg is 'EXP'")
        if norm_cntcode and norm_forcur:
            expected_currency = COUNTRY_CURRENCY_MAP.get(norm_cntcode)
            if not expected_currency:
                errors.append(f"Country code '{norm_cntcode}' is not recognized in our system.")
            elif norm_forcur != expected_currency:
                errors.append(f"Mismatch: Country '{norm_cntcode}' uses '{expected_currency}', but found '{norm_forcur}'")
        if not norm_expcat:
            errors.append("expcat is mandatory when trancatg is 'EXP'")
        elif norm_expcat not in allowed_expcat:
            errors.append(f"Invalid expcat '{norm_expcat}'. Must be {allowed_expcat}")
        if not norm_wthpay:
            errors.append("wthpay is mandatory when trancatg is 'EXP'")
        elif norm_wthpay not in ["Y", "N"]:
            errors.append(f"Invalid wthpay '{norm_wthpay}'. Must be 'Y' or 'N'")
    else:
        forbidden_fields = {"expcat": norm_expcat, "wthpay": norm_wthpay, "forcur": norm_forcur, "cntcode": norm_cntcode}
        for field_name, value in forbidden_fields.items():
            if value != "":
                errors.append(f"{field_name} must be empty when trancatg is '{norm_trancatg}'")
    if norm_shipbno and not (7 <= len(norm_shipbno) <= 20):
        errors.append(f"shipbno must be 7-20 chars. Current: {len(norm_shipbno)}")
    if norm_shipbdt and not re.match(date_pattern, norm_shipbdt):
        errors.append(f"Invalid shipbdt format '{norm_shipbdt}'. Expected DD/MM/YYYY")
    if norm_port:
        if not (6 <= len(norm_port) <= 10):
            errors.append(f"port code must be 6-10 chars. Current: {len(norm_port)}")
        elif not re.match(port_pattern, norm_port):
            errors.append(f"Invalid port code format '{norm_port}'.")
    if norm_invforcur:
        try:
            val = float(norm_invforcur)
            if val < 0: 
                errors.append("invforcur cannot be negative")
            if "." in norm_invforcur:
                parts = norm_invforcur.split(".")
                if len(parts[0]) > 14 or len(parts[1]) > 2:
                    errors.append("invforcur exceeds max precision (14.2)")
            elif len(norm_invforcur) > 14:
                errors.append("invforcur exceeds max length of 14 digits")
        except ValueError:
            errors.append(f"invforcur must be numeric. Got: '{norm_invforcur}'")
    if norm_revcharge not in ["Y", "N"]:
        errors.append("Reverse Charge must be 'Y' or 'N'")
    elif norm_trancatg and norm_trancatg != "B2B" and norm_revcharge == "Y":
        reason = get_reverse_charge_rejection_reason(norm_trancatg, norm_wthpay) if get_reverse_charge_rejection_reason else f"Reverse Charge is not applicable for transaction category '{norm_trancatg}'."
        errors.append(f"Rule 2162: {reason}")
    if norm_transmode not in allowed_transmode:
        errors.append(f"Invalid transactionmode. Must be one of {allowed_transmode}")
    if norm_expduty != "":
        try:
            val = float(norm_expduty)
            if val < 0:
                errors.append("expduty cannot be negative")
            if "." in norm_expduty:
                parts = norm_expduty.split(".")
                if len(parts[0]) > 14 or len(parts[1]) > 2:
                    errors.append("expduty exceeds max precision (14.2)")
            elif len(norm_expduty) > 14:
                errors.append("expduty exceeds max length of 14 digits")
        except ValueError:
            errors.append(f"expduty must be numeric. Got:'{norm_expduty}'")
    if not norm_doc_type:
        errors.append("document_type is mandatory and cannot be blank")
    elif norm_doc_type not in allowed_doc_types:
        errors.append(f"Invalid document_type'{norm_doc_type}'.Must be one of {allowed_doc_types}")
    if not norm_docno:
        errors.append("docno is mandatory and cannot be blank (or contained only invalid characters)")
    elif len(norm_docno) > 16:
        errors.append(f"docno exceeds max length of 16. Current length: {len(norm_docno)}")
    if not raw_docdt:
        errors.append("docdt is mandatory and cannot be blank")
    else:
        for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%m/%d/%Y", "%d.%m.%Y", "%d-%m-%y", "%d/%m/%y"):
            try:
                norm_docdt = datetime.strptime(raw_docdt, fmt).strftime(target_format)
                break
            except ValueError:
                continue
        if not norm_docdt:
            errors.append(f"Invalid docdt format'{raw_docdt}'. Expected date normalized to DD-MM-YYYY")
    if norm_orginvno and len(norm_orginvno) > 16:
        errors.append(f"orginvno exceeds max length of 16. Current length:{len(norm_orginvno)}")
    if norm_orginvdt:
        if not re.match(date_pattern, norm_orginvdt):
            errors.append(f"Invalid orginvdt format '{norm_orginvdt}'.Expected DD/MM/YYYY")
    if not norm_sup_gstin:
        errors.append("supplier_gstin cannot be blank or null")
    elif len(norm_sup_gstin) != 15:
        errors.append(f"Invalid supplier_gstin length ({len(norm_sup_gstin)})")
    elif not norm_sup_gstin[:2].isdigit():
        errors.append("supplier_gstin state code must be numeric")
    if not norm_sup_lglnm:
        errors.append("supplier_lglnm is mandatory and cannot be blank")
    else:
        name_len = len(norm_sup_lglnm)
        if name_len < 3 or name_len > 100:
            errors.append(f"supplier_lglnm length must be 3-100 characters. Current: {name_len}")
    if norm_sup_trdnm:
        trd_len = len(norm_sup_trdnm)
        if trd_len < 3 or trd_len > 100:
            errors.append(f"supplier_trdnm length must be 3-100 characters. Current: {trd_len}")
    if norm_sup_bno and len(norm_sup_bno) > 60:
        errors.append(f"supplier_bno exceeds max length of 60. Current: {len(norm_sup_bno)}")
    if not norm_sup_bnm:
        errors.append("supplier_bnm is mandatory and cannot be blank")
    elif not (3 <= len(norm_sup_bnm) <= 100):
        errors.append(f"supplier_bnm length must be 3-100 characters. Current: {len(norm_sup_bnm)}")
    if norm_sup_flno:
        if not (3 <= len(norm_sup_flno) <= 100):
            errors.append(f"supplier_flno length must be 3-100 characters. Current: {len(norm_sup_flno)}")
    if not norm_sup_loc:
        errors.append("supplier_loc is mandatory")
    elif not (3 <= len(norm_sup_loc) <= 50):
        errors.append(f"supplier_loc length must be 3-50. Current: {len(norm_sup_loc)}")
    if norm_sup_dst and len(norm_sup_dst) > 60:
        errors.append(f"supplier_dst exceeds max length of 60")
    if not norm_sup_pin:
        errors.append("supplier_pin is mandatory")
    elif len(norm_sup_pin) != 6:
        errors.append(f"supplier_pin must be exactly 6 digits. Got: {len(norm_sup_pin)}")
    if not norm_sup_state:
        errors.append("supplier_state is mandatory")
    elif len(norm_sup_state) != 2:
        errors.append(f"supplier_state must be exactly 2 digits (e.g., '12'). Got: {len(norm_sup_state)}")
    if norm_sup_phone and len(norm_sup_phone) != 10:
        errors.append(f"supplier_phone must be 10 digits. Got: {len(norm_sup_phone)}")
    if norm_sup_email:
        if not (10 <= len(norm_sup_email) <= 50):
            errors.append(f"supplier_email length must be 10-50. Current: {len(norm_sup_email)}")
        if "@" not in norm_sup_email or "." not in norm_sup_email:
            errors.append("Invalid email format for supplier_email")
    if norm_cust_cd and len(norm_cust_cd) > 30:
        errors.append(f"cust_cd exceeds max length of 30")
    if not norm_buy_gstin:
        errors.append("buyer_gstin is mandatory and cannot be blank")
    else:
        if not (3 <= len(norm_buy_gstin) <= 15):
            errors.append(f"buyer_gstin length must be 3-15 chars. Got: {len(norm_buy_gstin)}")
        if norm_buy_gstin != "URP":
            if not re.match(buyer_gstin_pattern, norm_buy_gstin):
                errors.append(f"Invalid buyer_gstin format '{norm_buy_gstin}'. Must be 15-digit GSTIN or 'URP'")
        if norm_trancatg in ["EXP", "B2C"] and norm_buy_gstin != "URP":
            pass 
        elif norm_trancatg in ["B2B", "B2G"] and norm_buy_gstin == "URP":
            errors.append(f"buyer_gstin cannot be 'URP' for transaction category '{norm_trancatg}'")
    if not norm_buy_lglnm:
        errors.append("buyer_lglnm is mandatory and cannot be blank")
    else:
        buy_name_len = len(norm_buy_lglnm)
        if buy_name_len < 3 or buy_name_len > 100:
            errors.append(f"buyer_lglnm length must be 3-100 characters. Current: {buy_name_len}")
    if norm_buy_trdnm:
        buy_trd_len = len(norm_buy_trdnm)
        if buy_trd_len < 3 or buy_trd_len > 100:
            errors.append(f"buyer_trdnm length must be 3-100 characters. Current: {buy_trd_len}")
    if norm_buy_bno and len(norm_buy_bno) > 60:
        errors.append(f"buyer_bno exceeds max length of 60. Current: {len(norm_buy_bno)}")
    if not norm_buy_bnm:
        errors.append("buyer_bnm is mandatory and cannot be blank")
    elif not (3 <= len(norm_buy_bnm) <= 100):
        errors.append(f"buyer_bnm length must be 3-100 characters. Current: {len(norm_buy_bnm)}")
    if norm_buy_flno: 
        buy_flno_len = len(norm_buy_flno)
        if buy_flno_len < 3 or buy_flno_len > 100:
            errors.append(f"buyer_flno length must be 3-100 characters. Current: {buy_flno_len}")
    if not norm_buy_loc:
        errors.append("buyer_loc is mandatory")
    elif not (3 <= len(norm_buy_loc) <= 100):
        errors.append(f"buyer_loc length must be 3-100. Current: {len(norm_buy_loc)}")
    if norm_buy_dst and len(norm_buy_dst) > 60:
        errors.append(f"buyer_dst exceeds max length of 60")
    if not norm_buy_pin:
        errors.append("buyer_pin is mandatory")
    elif len(norm_buy_pin) != 6:
        errors.append(f"buyer_pin must be 6 digits. Got: {len(norm_buy_pin)}")
    if not norm_buy_state:
        errors.append("buyer_state is mandatory")
    elif len(norm_buy_state) != 2:
        errors.append(f"buyer_state must be 2 digits. Got: {len(norm_buy_state)}")
    if norm_pos and len(norm_pos) == 1:
        norm_pos = norm_pos.zfill(2)
    if norm_trancatg == "EXP":
        norm_pos = "96"
    elif not norm_pos:
        if norm_buy_gstin and norm_buy_gstin != "URP" and len(norm_buy_gstin) >= 2:
            norm_pos = norm_buy_gstin[:2]
    if norm_trancatg == "B2C" and not norm_pos:
        errors.append("pos is mandatory for B2C transactions (no value provided and no buyer_gstin available for fallback)")
    if norm_pos:
        if len(norm_pos) != 2:
            errors.append(f"pos must be exactly 2 digits. Got: '{norm_pos}' (Length: {len(norm_pos)})")
        if not norm_pos.isdigit():
            errors.append(f"pos must be a numeric state code. Got: '{norm_pos}'")
    if norm_buy_phone == "":
        pass 
    elif len(norm_buy_phone) != 10:
        errors.append(f"buyer_phone must be exactly 10 digits. Got: {len(norm_buy_phone)}")
    if norm_buy_email:
        email_len = len(norm_buy_email)
        if not (10 <= email_len <= 50):
            errors.append(f"buyer_email length must be 10-50 characters. Current: {email_len}")
        if "@" not in norm_buy_email or "." not in norm_buy_email:
            errors.append(f"Invalid email format for buyer_email: '{norm_buy_email}'")
    if norm_disp_gstin:
        if norm_disp_gstin == "URP":
            pass 
        else:
            if not (3 <= len(norm_disp_gstin) <= 15):
                errors.append(f"disp_gstin length must be 3-15 chars. Got: {len(norm_disp_gstin)}")
            elif not re.match(gstin_pattern, norm_disp_gstin):
                errors.append(f"Invalid disp_gstin format '{norm_disp_gstin}'. Must be 15-digit GSTIN or 'URP'")
            elif not norm_disp_gstin[:2].isdigit():
                errors.append("disp_gstin state code (first 2 digits) must be numeric")
    if norm_transmode in ["DIS", "CMB"]:
        if not norm_disp_trdnm:
            errors.append(f"disp_trdnm is mandatory when transactionmode is '{norm_transmode}'")
        else:
            trd_len = len(norm_disp_trdnm)
            if trd_len < 3 or trd_len > 100:
                errors.append(f"disp_trdnm length must be 3-100 characters. Current: {trd_len}")
    if norm_disp_bno:
        if len(norm_disp_bno) > 60:
            errors.append(f"disp_bno exceeds max length of 60. Current: {len(norm_disp_bno)}")
    if norm_transmode in ["DIS", "CMB"]:
        if not norm_disp_bnm:
            errors.append(f"disp_bnm is mandatory when transactionmode is '{norm_transmode}'")
        else:
            bnm_len = len(norm_disp_bnm)
            if bnm_len < 3 or bnm_len > 100:
                errors.append(f"disp_bnm length must be 3-100 characters. Current: {bnm_len}")
    if norm_disp_flno:
        flno_len = len(norm_disp_flno)
        if flno_len < 3 or flno_len > 100:
            errors.append(f"disp_flno length must be 3-100 characters. Current: {flno_len}")
    if norm_transmode in ["DIS", "CMB"]:
        if not norm_disp_loc:
            errors.append(f"disp_loc is mandatory when transactionmode is '{norm_transmode}'")
        else:
            loc_len = len(norm_disp_loc)
            if loc_len < 3 or loc_len > 100:
                errors.append(f"disp_loc length must be 3-100 characters. Current: {loc_len}")
    if norm_disp_dst and len(norm_disp_dst) > 60:
        errors.append(f"disp_dst exceeds max length of 60 characters. Current: {len(norm_disp_dst)}")
    if norm_transmode in ["DIS", "CMB"]:
        if not norm_disp_pin:
            errors.append(f"disp_pin is mandatory when transactionmode is '{norm_transmode}'")
        elif len(norm_disp_pin) != 6:
            errors.append(f"disp_pin must be exactly 6 digits. Got: {len(norm_disp_pin)}")
    else:
        if norm_disp_pin and len(norm_disp_pin) != 6:
            errors.append(f"Invalid disp_pin format; must be 6 digits.")
    if len(norm_disp_state) == 1:
        norm_disp_state = norm_disp_state.zfill(2)
    if norm_transmode in ["DIS", "CMB"]:
        if not norm_disp_state:
            errors.append(f"disp_state is mandatory when transactionmode is '{norm_transmode}'")
        elif len(norm_disp_state) != 2:
            errors.append(f"disp_state must be exactly 2 digits. Got: {len(norm_disp_state)}")
    else:
        if norm_disp_state and len(norm_disp_state) != 2:
            errors.append(f"Invalid disp_state format; must be 2 digits.")
    if norm_disp_phone != "":
        if len(norm_disp_phone) != 10:
            errors.append(f"disp_phone must be exactly 10 digits. Got: {len(norm_disp_phone)}")
    if norm_disp_email:
        email_len = len(norm_disp_email)
        if not (10 <= email_len <= 50):
            errors.append(f"disp_email length must be 10-50 characters. Current: {email_len}")
        if "@" not in norm_disp_email or "." not in norm_disp_email.split("@")[-1]:
            errors.append(f"Invalid email format for disp_email: '{norm_disp_email}'")
    if norm_ship_gstin:
        ship_len = len(norm_ship_gstin)
        if ship_len < 3 or ship_len > 15:
            errors.append(f"ship_gstin length must be 3-15 chars. Got: {ship_len}")
        if not re.match(ship_gstin_pattern, norm_ship_gstin):
            errors.append(f"Invalid ship_gstin format '{norm_ship_gstin}'. Must be 15-digit GSTIN or 'URP'")
    if norm_transmode in ["SHP", "CMB"]:
        if not norm_ship_lglnm:
            errors.append(f"ship_lglnm is mandatory when transactionmode is '{norm_transmode}'")
        else:
            ship_name_len = len(norm_ship_lglnm)
            if ship_name_len < 3 or ship_name_len > 100:
                errors.append(f"ship_lglnm length must be 3-100 characters. Current: {ship_name_len}")
    else:
        pass
    if norm_ship_trdnm:
        ship_trd_len = len(norm_ship_trdnm)
        if ship_trd_len < 3 or ship_trd_len > 100:
            errors.append(f"ship_trdnm length must be 3-100 characters. Current: {ship_trd_len}")
    if norm_ship_bno and len(norm_ship_bno) > 60:
        errors.append(f"ship_bno exceeds max length of 60 characters. Current: {len(norm_ship_bno)}")
    if norm_transmode in ["SHP", "CMB"] and not norm_ship_bno:
        pass
    
    if norm_transmode in ["SHP", "CMB"]:
        if not norm_ship_bnm:
            errors.append(f"ship_bnm is mandatory when transactionmode is '{norm_transmode}'")
        else:
            bnm_len = len(norm_ship_bnm)
            if bnm_len < 3 or bnm_len > 100:
                errors.append(f"ship_bnm length must be 3-100 characters. Current: {bnm_len}")
    if norm_ship_flno:
        flno_len = len(norm_ship_flno)
        if flno_len < 3 or flno_len > 100:
            errors.append(f"ship_flno length must be 3-100 characters. Current: {flno_len}")
    if norm_transmode in ["SHP", "CMB"]:
        if not norm_ship_loc:
            errors.append(f"ship_loc is mandatory when transactionmode is '{norm_transmode}'")
        else:
            loc_len = len(norm_ship_loc)
            if loc_len < 3 or loc_len > 100:
                errors.append(f"ship_loc length must be 3-100 characters. Current: {loc_len}")
    elif norm_ship_loc:
        loc_len = len(norm_ship_loc)
        if loc_len < 3 or loc_len > 100:
            errors.append(f"ship_loc length must be 3-100 characters. Current: {loc_len}")
    if norm_ship_dst:
        if len(norm_ship_dst) > 60:
            errors.append(f"ship_dst exceeds max length of 60 characters. Current: {len(norm_ship_dst)}")

    if norm_transmode in ["SHP", "CMB"] and not norm_ship_dst:
        errors.append(f"ship_dst is recommended/mandatory when transactionmode is '{norm_transmode}'")
    if norm_transmode in ["SHP", "CMB"]:
        if not norm_ship_pin:
            errors.append(f"ship_pin is mandatory when transactionmode is '{norm_transmode}'")
        elif len(norm_ship_pin) != 6:
            errors.append(f"ship_pin must be exactly 6 digits. Got: {len(norm_ship_pin)}")
    else:
        if norm_ship_pin and len(norm_ship_pin) != 6:
            errors.append(f"Invalid ship_pin format; must be 6 digits.")
    if norm_transmode in ["SHP", "CMB"]:
        if not norm_ship_state:
            errors.append(f"ship_state is mandatory when transactionmode is '{norm_transmode}'")
        elif len(norm_ship_state) != 2:
            errors.append(f"ship_state must be exactly 2 digits. Got: '{norm_ship_state}'")
    else:
        if norm_ship_state and len(norm_ship_state) != 2:
            errors.append(f"Invalid ship_state format; must be 2 digits.")
    if norm_ship_phone != "":
        if len(norm_ship_phone) != 10:
            errors.append(f"ship_phone must be exactly 10 digits. Got: {len(norm_ship_phone)}")
    if norm_ship_email:
        ship_email_len = len(norm_ship_email)
        if not (10 <= ship_email_len <= 50):
            errors.append(f"ship_email length must be 10-50 characters. Current: {ship_email_len}")
    
        if "@" not in norm_ship_email or "." not in norm_ship_email.split("@")[-1]:
            errors.append(f"Invalid email format for ship_email: '{norm_ship_email}'")
    if norm_frmdt:
        if not re.match(date_pattern_dash, norm_frmdt):
            errors.append(f"Invalid frmdt format '{norm_frmdt}'. Expected DD-MM-YYYY")
    if norm_todt:
        if not re.match(date_pattern_dash, norm_todt):
            errors.append(f"Invalid todt format '{norm_todt}'. Expected DD-MM-YYYY")
    if norm_itemcd:
        if len(norm_itemcd) > 100:
            errors.append(f"itemcd exceeds max length of 100 characters. Current: {len(norm_itemcd)}")
    if not norm_prdnm:
        errors.append("prdnm (Product Name) is mandatory and cannot be blank")
    else:
        prd_len = len(norm_prdnm)
        if prd_len < 3 or prd_len > 300:
            errors.append(f"prdnm length must be 3-300 characters. Current: {prd_len}")
    if norm_prddesc:
        desc_len = len(norm_prddesc)
        if desc_len < 3 or desc_len > 300:
            errors.append(f"prddesc length must be 3-300 characters. Current: {desc_len}")
    if not norm_isservc:
        errors.append("isservc (Service indicator) is mandatory and cannot be blank")
    elif norm_isservc not in ["Y", "N"]:
        errors.append(f"Invalid isservc value '{norm_isservc}'. Must be 'Y' (Service) or 'N' (Goods)")
    if not norm_hsncd:
        errors.append("hsncd (HSN/SAC Code) is mandatory and cannot be blank")
    else:
        hsn_len = len(norm_hsncd)
        if hsn_len < 2 or hsn_len > 8:
            errors.append(f"hsncd length must be between 2 and 8 digits. Got: {hsn_len}")
        if hsn_len % 2 != 0 and hsn_len != 1: 
            pass
    if norm_barcde:
        bar_len = len(norm_barcde)
        if bar_len < 1 or bar_len > 30:
            errors.append(f"barcde length must be between 1 and 30 characters. Current: {bar_len}")
    
    if norm_isservc == "N" and not norm_qty:
        errors.append("qty is mandatory when the item is Goods (isservc = 'N')")
    elif norm_qty:
        try:
            qty_val = float(norm_qty)
            if qty_val < 0:
                errors.append("qty cannot be negative")
            if "." in norm_qty:
                parts = norm_qty.split(".")
                if len(parts[0]) > 8: # 11 total - 3 decimal = 8 integer digits
                    errors.append(f"qty integer part exceeds 8 digits. Got: {len(parts[0])}")
                if len(parts[1]) > 3:
                    errors.append(f"qty decimal part exceeds 3 places. Got: {len(parts[1])}")
            else:
                if len(norm_qty) > 8:
                    errors.append(f"qty exceeds max length of 8 digits for integer value.")
        except ValueError:
            errors.append(f"qty must be a numeric decimal. Got: '{norm_qty}'")
    if norm_freeqty:
        try:
            fq_val = float(norm_freeqty)
            if fq_val < 0:
                errors.append("freeqty cannot be negative")
            if "." in norm_freeqty:
                parts = norm_freeqty.split(".")
                if len(parts[0]) > 9:
                    errors.append(f"freeqty integer part exceeds 9 digits. Got: {len(parts[0])}")
                if len(parts[1]) > 3:
                    errors.append(f"freeqty decimal part exceeds 3 places. Got: {len(parts[1])}")
            else:
                if len(norm_freeqty) > 9:
                    errors.append(f"freeqty integer exceeds max length of 9 digits.")
        except ValueError:
            errors.append(f"freeqty must be a numeric value. Got: '{norm_freeqty}'")
    if norm_isservc == "N" and not norm_uqc:
        errors.append("uqc is mandatory when the item is Goods (isservc = 'N')")
    elif norm_uqc:
        if len(norm_uqc) > 3:
            errors.append(f"uqc exceeds max length of 3 characters. Got: '{norm_uqc}'")
        elif norm_uqc not in ALLOWED_UQC:
            errors.append(f"Invalid uqc code '{norm_uqc}'. Must be a valid code from UQC Master (e.g., BAG, PCS, NOS)")
    if not norm_unitrate:
        errors.append("unitrate (Per Unit Rate) is mandatory and cannot be blank")
    else:
        try:
            ur_val = float(norm_unitrate)
            if ur_val < 0:
                errors.append("unitrate cannot be negative")
            if "." in norm_unitrate:
                parts = norm_unitrate.split(".")
                if len(parts[0]) > 13:
                    errors.append(f"unitrate integer part exceeds 13 digits. Got: {len(parts[0])}")
                if len(parts[1]) > 3:
                    errors.append(f"unitrate decimal part exceeds 3 places. Got: {len(parts[1])}")
            else:
                if len(norm_unitrate) > 13:
                    errors.append(f"unitrate integer exceeds max length of 13 digits.")
        except ValueError:
            errors.append(f"unitrate must be a numeric decimal. Got: '{norm_unitrate}'")
    if not norm_grossamt:
        errors.append("grossamt (Total Amount) is mandatory and cannot be blank")
    else:
        try:
            gross_val = float(norm_grossamt)
            if gross_val < 0:
                errors.append("grossamt cannot be negative")
            if "." in norm_grossamt:
                parts = norm_grossamt.split(".")
                if len(parts[0]) > 15:
                    errors.append(f"grossamt integer part exceeds 15 digits. Got: {len(parts[0])}")
                if len(parts[1]) > 2:
                    errors.append(f"grossamt decimal part exceeds 2 places. Got: {len(parts[1])}")
            else:
                if len(norm_grossamt) > 15:
                    errors.append(f"grossamt integer exceeds max length of 15 digits.")
        except ValueError:
            errors.append(f"grossamt must be a numeric decimal. Got: '{norm_grossamt}'")
    if norm_discount:
        try:
            disc_val = float(norm_discount)
            if disc_val < 0:
                errors.append("discount cannot be negative")
            if "." in norm_discount:
                parts = norm_discount.split(".")
                if len(parts[0]) > 15:
                    errors.append(f"discount integer part exceeds 15 digits. Got: {len(parts[0])}")
                if len(parts[1]) > 2:
                    errors.append(f"discount decimal part exceeds 2 places. Got: {len(parts[1])}")
            else:
                if len(norm_discount) > 15:
                    errors.append(f"discount integer exceeds max length of 15 digits.")
                
        except ValueError:
            errors.append(f"discount must be a numeric decimal. Got: '{norm_discount}'")
    if norm_othchrg:
        try:
            oth_val = float(norm_othchrg)
            if oth_val < 0:
                errors.append("othchrg (Other Charges) cannot be negative")
            if "." in norm_othchrg:
                parts = norm_othchrg.split(".")
                if len(parts[0]) > 15:
                    errors.append(f"othchrg integer part exceeds 15 digits. Got: {len(parts[0])}")
                if len(parts[1]) > 2:
                    errors.append(f"othchrg decimal part exceeds 2 places. Got: {len(parts[1])}")
            else:
                if len(norm_othchrg) > 15:
                    errors.append(f"othchrg integer exceeds max length of 15 digits.")
        except ValueError:
            errors.append(f"othchrg must be a numeric decimal. Got: '{norm_othchrg}'")
    if norm_pretaxval:
        try:
            pretax_val = float(norm_pretaxval)
            if pretax_val < 0:
                errors.append("pretaxval cannot be negative")
            if "." in norm_pretaxval:
                parts = norm_pretaxval.split(".")
                if len(parts[0]) > 15:
                    errors.append(f"pretaxval integer part exceeds 15 digits. Got: {len(parts[0])}")
                if len(parts[1]) > 2:
                    errors.append(f"pretaxval decimal part exceeds 2 places. Got: {len(parts[1])}")
            else:
                if len(norm_pretaxval) > 15:
                    errors.append(f"pretaxval integer exceeds max length of 15 digits.")
                
        except ValueError:
            errors.append(f"pretaxval must be a numeric decimal. Got: '{norm_pretaxval}'")
    if not norm_assamt:
        errors.append("assamt (Assessable Amount) is mandatory and cannot be blank")
    else:
        try:
            ass_val = float(norm_assamt)
            if ass_val < 0:
                errors.append("assamt cannot be negative")
        
            if "." in norm_assamt:
                parts = norm_assamt.split(".")
                if len(parts[0]) > 15:
                    errors.append(f"assamt integer part exceeds 15 digits. Got: {len(parts[0])}")
                if len(parts[1]) > 2:
                    errors.append(f"assamt decimal part exceeds 2 places. Got: {len(parts[1])}")
            else:
                if len(norm_assamt) > 15:
                    errors.append(f"assamt integer exceeds max length of 15 digits.")
        except ValueError:
            errors.append(f"assamt must be a numeric decimal. Got: '{norm_assamt}'")
    if not norm_taxability:
        errors.append("taxability is mandatory and cannot be blank")
    elif norm_taxability not in ALLOWED_TAXABILITY:
        errors.append(f"Invalid taxability code '{norm_taxability}'. Must be one of: {', '.join(ALLOWED_TAXABILITY)}")
    
    if norm_diffpercent:
        try:
            diff_val = float(norm_diffpercent)
            if diff_val < 0:
                errors.append("diffpercent cannot be negative")
        
            if "." in norm_diffpercent:
                parts = norm_diffpercent.split(".")
                if len(parts[0]) > 3:
                    errors.append(f"diffpercent integer part exceeds 3 digits. Got: {len(parts[0])}")
                if len(parts[1]) > 3:
                    errors.append(f"diffpercent decimal part exceeds 3 places. Got: {len(parts[1])}")
            else:
                if len(norm_diffpercent) > 3:
                    errors.append(f"diffpercent integer exceeds max length of 3 digits.")
                
        except ValueError:
            errors.append(f"diffpercent must be a numeric decimal. Got: '{norm_diffpercent}'")
    if not norm_cgstrt:
        errors.append("cgstrt (CGST Rate) is mandatory and cannot be blank")
    else:
        try:
            cgst_rate_val = float(norm_cgstrt)
            if cgst_rate_val < 0:
                errors.append("cgstrt cannot be negative")
            if "." in norm_cgstrt:
                parts = norm_cgstrt.split(".")
                if len(parts[0]) > 3:
                    errors.append(f"cgstrt integer part exceeds 3 digits. Got: {len(parts[0])}")
                if len(parts[1]) > 3:
                    errors.append(f"cgstrt decimal part exceeds 3 places. Got: {len(parts[1])}")
            else:
                if len(norm_cgstrt) > 3:
                    errors.append(f"cgstrt integer exceeds max length of 3 digits.")
                
        except ValueError:
            errors.append(f"cgstrt must be a numeric decimal. Got: '{norm_cgstrt}'")
    if not norm_cgstamt:
        errors.append("cgstamt (CGST Amount) is mandatory and cannot be blank")
    else:
        try:
            cgst_amt_val = float(norm_cgstamt)
            if cgst_amt_val < 0:
                errors.append("cgstamt cannot be negative")
            if "." in norm_cgstamt:
                parts = norm_cgstamt.split(".")
                if len(parts[0]) > 15:
                    errors.append(f"cgstamt integer part exceeds 15 digits. Got: {len(parts[0])}")
                if len(parts[1]) > 2:
                    errors.append(f"cgstamt decimal part exceeds 2 places. Got: {len(parts[1])}")
            else:
                if len(norm_cgstamt) > 15:
                    errors.append(f"cgstamt integer exceeds max length of 15 digits.")
        except ValueError:
            errors.append(f"cgstamt must be a numeric decimal. Got: '{norm_cgstamt}'")
    if not norm_sgstrt:
        errors.append("sgstrt (SGST Rate) is mandatory and cannot be blank")
    else:
        try:
            sgst_rate_val = float(norm_sgstrt)
            if sgst_rate_val < 0:
                errors.append("sgstrt cannot be negative")
            if "." in norm_sgstrt:
                parts = norm_sgstrt.split(".")
                if len(parts[0]) > 3:
                    errors.append(f"sgstrt integer part exceeds 3 digits. Got: {len(parts[0])}")
                if len(parts[1]) > 3:
                    errors.append(f"sgstrt decimal part exceeds 3 places. Got: {len(parts[1])}")
            else:
                if len(norm_sgstrt) > 3:
                    errors.append(f"sgstrt integer exceeds max length of 3 digits.")
        except ValueError:
            errors.append(f"sgstrt must be a numeric decimal. Got: '{norm_sgstrt}'")
    if not norm_sgstamt:
        errors.append("sgstamt (SGST Amount) is mandatory and cannot be blank")
    else:
        try:
            sgst_amt_val = float(norm_sgstamt)
            if sgst_amt_val < 0:
                errors.append("sgstamt cannot be negative")
            if "." in norm_sgstrt:
                parts = norm_sgstamt.split(".")
                if len(parts[0]) > 15:
                    errors.append(f"sgstamt integer part exceeds 15 digits. Got: {len(parts[0])}")
                if len(parts[1]) > 2:
                    errors.append(f"sgstamt decimal part exceeds 2 places. Got: {len(parts[1])}")
            else:
                if len(norm_sgstamt) > 15:
                    errors.append(f"sgstamt integer exceeds max length of 15 digits.")
        except ValueError:
            errors.append(f"sgstamt must be a numeric decimal. Got: '{norm_sgstamt}'")
    if not norm_igstrt:
        errors.append("igstrt (IGST Rate) is mandatory and cannot be blank")
    else:
        try:
            igst_rate_val = float(norm_igstrt)
            if igst_rate_val < 0:
                errors.append("igstrt cannot be negative")
            if "." in norm_igstrt:
                parts = norm_igstrt.split(".")
                if len(parts[0]) > 3:
                    errors.append(f"igstrt integer part exceeds 3 digits. Got: {len(parts[0])}")
                if len(parts[1]) > 3:
                    errors.append(f"igstrt decimal part exceeds 3 places. Got: {len(parts[1])}")
            else:
                if len(norm_igstrt) > 3:
                    errors.append(f"igstrt integer exceeds max length of 3 digits.")
        except ValueError:
            errors.append(f"igstrt must be a numeric decimal. Got: '{norm_igstrt}'")
    if not norm_igstamt:
        errors.append("igstamt (IGST Amount) is mandatory and cannot be blank")
    else:
        try:
            igst_amt_val = float(norm_igstamt)
            if igst_amt_val < 0:
                errors.append("igstamt cannot be negative")
            if "." in norm_igstamt:
                parts = norm_igstamt.split(".")
                if len(parts[0]) > 15:
                    errors.append(f"igstamt integer part exceeds 15 digits. Got: {len(parts[0])}")
                if len(parts[1]) > 2:
                    errors.append(f"igstamt decimal part exceeds 2 places. Got: {len(parts[1])}")
            else:
                if len(norm_igstamt) > 15:
                    errors.append(f"igstamt integer exceeds max length of 15 digits.")
        except ValueError:
            errors.append(f"igstamt must be a numeric decimal. Got: '{norm_igstamt}'")
    if not norm_cessrt:
        errors.append("cessrt (Cess Rate) is mandatory and cannot be blank")
    else:
        try:
            cess_rate_val = float(norm_cessrt)
            if cess_rate_val < 0:
                errors.append("cessrt cannot be negative")
            if "." in norm_cessrt:
                parts = norm_cessrt.split(".")
                if len(parts[0]) > 3:
                    errors.append(f"cessrt integer part exceeds 3 digits. Got: {len(parts[0])}")
                if len(parts[1]) > 3:
                    errors.append(f"cessrt decimal part exceeds 3 places. Got: {len(parts[1])}")
            else:
                if len(norm_cessrt) > 3:
                    errors.append(f"cessrt integer exceeds max length of 3 digits.")
                
        except ValueError:
            errors.append(f"cessrt must be a numeric decimal. Got: '{norm_cessrt}'")
    if not norm_cessamt:
        errors.append("cessamt (Cess Amount) is mandatory and cannot be blank")
    else:
        try:
            cess_amt_val = float(norm_cessamt)
            if cess_amt_val < 0:
                errors.append("cessamt cannot be negative")
            if "." in norm_cessamt:
                parts = norm_cessamt.split(".")
                if len(parts[0]) > 15:
                    errors.append(f"cessamt integer part exceeds 15 digits. Got: {len(parts[0])}")
                if len(parts[1]) > 2:
                    errors.append(f"cessamt decimal part exceeds 2 places. Got: {len(parts[1])}")
            else:
                if len(norm_cessamt) > 15:
                    errors.append(f"cessamt integer exceeds max length of 15 digits.")
        except ValueError:
            errors.append(f"cessamt must be a numeric decimal. Got: '{norm_cessamt}'")
    if not norm_cessnonadval:
        errors.append("cessnonadval (Non-Advalorem Cess) is mandatory and cannot be blank")
    else:
        try:
            non_adv_val = float(norm_cessnonadval)
            if non_adv_val < 0:
                errors.append("cessnonadval cannot be negative")
            if "." in norm_cessnonadval:
                parts = norm_cessnonadval.split(".")
                if len(parts[0]) > 15:
                    errors.append(f"cessnonadval integer part exceeds 15 digits. Got: {len(parts[0])}")
                if len(parts[1]) > 2:
                    errors.append(f"cessnonadval decimal part exceeds 2 places. Got: {len(parts[1])}")
            else:
                if len(norm_cessnonadval) > 15:
                    errors.append(f"cessnonadval integer exceeds max length of 15 digits.")
                
        except ValueError:
            errors.append(f"cessnonadval must be a numeric decimal. Got: '{norm_cessnonadval}'")
    if not norm_statecessrt:
        errors.append("statecessrt (State Cess Rate) is mandatory and cannot be blank")
    else:
        try:
            st_cess_rate_val = float(norm_statecessrt)
            if st_cess_rate_val < 0:
                errors.append("statecessrt cannot be negative")
            if "." in norm_statecessrt:
                parts = norm_statecessrt.split(".")
                if len(parts[0]) > 3:
                    errors.append(f"statecessrt integer part exceeds 3 digits. Got: {len(parts[0])}")
                if len(parts[1]) > 3:
                    errors.append(f"statecessrt decimal part exceeds 3 places. Got: {len(parts[1])}")
            else:
                if len(norm_statecessrt) > 3:
                    errors.append(f"statecessrt integer exceeds max length of 3 digits.")
        except ValueError:
            errors.append(f"statecessrt must be a numeric decimal. Got: '{norm_statecessrt}'")
    if not norm_statecessamt:
        errors.append("statecessamt (State Cess Amount) is mandatory and cannot be blank")
    else:
        try:
            st_cess_amt_val = float(norm_statecessamt)
            if st_cess_amt_val < 0:
                errors.append("statecessamt cannot be negative")
            if "." in norm_statecessamt:
                parts = norm_statecessamt.split(".")
                if len(parts[0]) > 15:
                    errors.append(f"statecessamt integer part exceeds 15 digits. Got: {len(parts[0])}")
                if len(parts[1]) > 2:
                    errors.append(f"statecessamt decimal part exceeds 2 places. Got: {len(parts[1])}")
            else:
                if len(norm_statecessamt) > 15:
                    errors.append(f"statecessamt integer exceeds max length of 15 digits.")
        except ValueError:
            errors.append(f"statecessamt must be a numeric decimal. Got: '{norm_statecessamt}'")
    if norm_statecesnonadvl:
        try:
            st_non_adv_val = float(norm_statecesnonadvl)
            if st_non_adv_val < 0:
                errors.append("statecesnonadvlamt cannot be negative")
            if "." in norm_statecesnonadvl:
                parts = norm_statecesnonadvl.split(".")
                if len(parts[0]) > 15:
                    errors.append(f"statecesnonadvlamt integer part exceeds 15 digits. Got: {len(parts[0])}")
                if len(parts[1]) > 2:
                    errors.append(f"statecesnonadvlamt decimal part exceeds 2 places. Got: {len(parts[1])}")
            else:
                if len(norm_statecesnonadvl) > 15:
                    errors.append(f"statecesnonadvlamt integer exceeds max length of 15 digits.")
        except ValueError:
            errors.append(f"statecesnonadvlamt must be a numeric decimal. Got: '{norm_statecesnonadvl}'")
    if not norm_totitemval:
        errors.append("totitemval (Total Item Value) is mandatory and cannot be blank")
    else:
        try:
            tot_val = float(norm_totitemval)
            if tot_val < 0:
                errors.append("totitemval cannot be negative")
            if "." in norm_totitemval:
                parts = norm_totitemval.split(".")
                if len(parts[0]) > 15 or len(parts[1]) > 2:
                    errors.append(f"totitemval precision error. Max 15.2 digits allowed.")
            elif len(norm_totitemval) > 15:
                errors.append(f"totitemval integer part exceeds 15 digits.")
            calculated_total = (
                float(norm_assamt or 0) + 
                float(norm_cgstamt or 0) + 
                float(norm_sgstamt or 0) + 
                float(norm_igstamt or 0) + 
                float(norm_cessamt or 0) + 
                float(norm_statecessamt or 0) + 
                float(norm_cessnonadval or 0) +
                float(norm_statecesnonadvl or 0)
            )
            if abs(tot_val - calculated_total) > 0.01:
                errors.append(
                    f"totitemval ({tot_val}) mismatch. "
                    f"Sum of components equals: {round(calculated_total, 2)}"
                )

        except ValueError:
            errors.append(f"totitemval must be a numeric decimal. Got: '{norm_totitemval}'")
    
    if norm_ordlineref:
        if len(norm_ordlineref) < 1:
            errors.append("ordlineref cannot be an empty string")
        if len(norm_ordlineref) > 50:
            errors.append(f"ordlineref exceeds max length of 50 characters. Got: {len(norm_ordlineref)}")
    if norm_orgcntry:
        if len(norm_orgcntry) != 2:
            errors.append(f"orgcntry must be exactly 2 characters (ISO alpha-2). Got: {len(norm_orgcntry)}")
        if not norm_orgcntry.isalpha():
            errors.append(f"orgcntry must contain only letters. Got: '{norm_orgcntry}'")
    if norm_prdsino:
        if len(norm_prdsino) < 1:
            errors.append("prdsino cannot be an empty string if provided")
        if len(norm_prdsino) > 20:
            errors.append(f"prdsino exceeds max length of 20 characters. Got: {len(norm_prdsino)}")

    if norm_batchname:
        if len(norm_batchname) > 20:
            errors.append(f"batchname exceeds max length of 20 characters. Got: {len(norm_batchname)}")
        if not re.match(r'^[a-zA-Z0-9\-/]+$', norm_batchname):
            errors.append(f"batchname contains invalid characters. Only alphanumeric, '-' and '/' are allowed. Got: '{norm_batchname}'")
    if norm_batchexpirydt:
        date_pattern = r"^[0-3][0-9]-[0-1][0-9]-20[1-2][0-9]$"
        if not re.match(date_pattern, norm_batchexpirydt):
            errors.append(f"batchexpirydt format mismatch. Expected DD-MM-YYYY (2010-2029). Got: '{norm_batchexpirydt}'")
        else:
            try:
                datetime.strptime(norm_batchexpirydt, "%d-%m-%Y")
            except ValueError:
                errors.append(f"batchexpirydt is not a valid calendar date. Got: '{norm_batchexpirydt}'")
    if norm_batchwarrantydt:
        warranty_pattern = r"^[0-3][0-9]-[0-1][0-9]-20[1-2][0-9]$"
        if not re.match(warranty_pattern, norm_batchwarrantydt):
            errors.append(f"batchwarrantydt format mismatch. Expected DD-MM-YYYY (2010-2029). Got: '{norm_batchwarrantydt}'")
        else:
            try:
                datetime.strptime(norm_batchwarrantydt, "%d-%m-%Y")
            except ValueError:
                errors.append(f"batchwarrantydt is not a valid calendar date. Got: '{norm_batchwarrantydt}'")
    if not norm_ttlassval:
        errors.append("ttlassval (Total Assessable Value) is mandatory and cannot be blank")
    else:
        try:
            ttl_ass_val = float(norm_ttlassval)
            if ttl_ass_val < 0:
                errors.append("ttlassval cannot be negative")
            if "." in norm_ttlassval:
                parts = norm_ttlassval.split(".")
                if len(parts[0]) > 15:
                    errors.append(f"ttlassval integer part exceeds 15 digits. Got: {len(parts[0])}")
                if len(parts[1]) > 2:
                    errors.append(f"ttlassval decimal part exceeds 2 places. Got: {len(parts[1])}")
            else:
                if len(norm_ttlassval) > 15:
                    errors.append(f"ttlassval integer exceeds max length of 15 digits.")
        except ValueError:
            errors.append(f"ttlassval must be a numeric decimal. Got: '{norm_ttlassval}'")
    if not norm_cgstval:
        errors.append("cgstval (Total CGST Value) is mandatory and cannot be blank")
    else:
        try:
            ttl_cgst = float(norm_cgstval)
            if ttl_cgst < 0:
                errors.append("cgstval cannot be negative")
            if "." in norm_cgstval:
                parts = norm_cgstval.split(".")
                if len(parts[0]) > 15:
                    errors.append(f"cgstval integer part exceeds 15 digits. Got: {len(parts[0])}")
                if len(parts[1]) > 2:
                    errors.append(f"cgstval decimal part exceeds 2 places. Got: {len(parts[1])}")
            else:
                if len(norm_cgstval) > 15:
                    errors.append(f"cgstval integer exceeds max length of 15 digits.")
        except ValueError:
            errors.append(f"cgstval must be a numeric decimal. Got: '{norm_cgstval}'")
    if not norm_sgstval:
        errors.append("sgstval (Total SGST Value) is mandatory and cannot be blank")
    else:
        try:
            ttl_sgst = float(norm_sgstval)
            if ttl_sgst < 0:
                errors.append("sgstval cannot be negative")
            if "." in norm_sgstval:
                parts = norm_sgstval.split(".")
                if len(parts[0]) > 15:
                    errors.append(f"sgstval integer part exceeds 15 digits. Got: {len(parts[0])}")
                if len(parts[1]) > 2:
                    errors.append(f"sgstval decimal part exceeds 2 places. Got: {len(parts[1])}")
            else:
                if len(norm_sgstval) > 15:
                    errors.append(f"sgstval integer exceeds max length of 15 digits.")
        except ValueError:
            errors.append(f"sgstval must be a numeric decimal. Got: '{norm_sgstval}'")
    if not norm_igstval:
        errors.append("igstval (Total IGST Value) is mandatory and cannot be blank")
    else:
        try:
            ttl_igst = float(norm_igstval)
            if ttl_igst < 0:
                errors.append("igstval cannot be negative")
            if "." in norm_igstval:
                parts = norm_igstval.split(".")
                if len(parts[0]) > 15:
                    errors.append(f"igstval integer part exceeds 15 digits. Got: {len(parts[0])}")
                if len(parts[1]) > 2:
                    errors.append(f"igstval decimal part exceeds 2 places. Got: {len(parts[1])}")
            else:
                if len(norm_igstval) > 15:
                    errors.append(f"igstval integer exceeds max length of 15 digits.")
        except ValueError:
            errors.append(f"igstval must be a numeric decimal. Got: '{norm_igstval}'")
    if not norm_cesval:
        errors.append("cesval (Total Cess Value) is mandatory and cannot be blank")
    else:
        try:
            ttl_cess = float(norm_cesval)
            if ttl_cess < 0:
                errors.append("cesval cannot be negative")
            if "." in norm_cesval:
                parts = norm_cesval.split(".")
                if len(parts[0]) > 15:
                    errors.append(f"cesval integer part exceeds 15 digits. Got: {len(parts[0])}")
                if len(parts[1]) > 2:
                    errors.append(f"cesval decimal part exceeds 2 places. Got: {len(parts[1])}")
            else:
                if len(norm_cesval) > 15:
                    errors.append(f"cesval integer exceeds max length of 15 digits.")
        except ValueError:
            errors.append(f"cesval must be a numeric decimal. Got: '{norm_cesval}'")
    if not norm_stcesval:
        errors.append("stcesval (Total State CESS Value) is mandatory and cannot be blank")
    else:
        try:
            ttl_st_cess = float(norm_stcesval)
            if ttl_st_cess < 0:
                errors.append("stcesval cannot be negative")
            if "." in norm_stcesval:
                parts = norm_stcesval.split(".")
                if len(parts[0]) > 15:
                    errors.append(f"stcesval integer part exceeds 15 digits. Got: {len(parts[0])}")
                if len(parts[1]) > 2:
                    errors.append(f"stcesval decimal part exceeds 2 places. Got: {len(parts[1])}")
            else:
                if len(norm_stcesval) > 15:
                    errors.append(f"stcesval integer exceeds max length of 15 digits.")
        except ValueError:
            errors.append(f"stcesval must be a numeric decimal. Got: '{norm_stcesval}'")
    if not norm_cesnonadval:
        errors.append("cesnonadval (Total Cess Non-advol Value) is mandatory and cannot be blank")
    else:
        try:
            ttl_ces_nonad = float(norm_cesnonadval)
            if ttl_ces_nonad < 0:
                errors.append("cesnonadval cannot be negative")
            if "." in norm_cesnonadval:
                parts = norm_cesnonadval.split(".")
                if len(parts[0]) > 15:
                    errors.append(f"cesnonadval integer part exceeds 15 digits. Got: {len(parts[0])}")
                if len(parts[1]) > 2:
                    errors.append(f"cesnonadval decimal part exceeds 2 places. Got: {len(parts[1])}")
            else:
                if len(norm_cesnonadval) > 15:
                    errors.append(f"cesnonadval integer exceeds max length of 15 digits.")
        except ValueError:
            errors.append(f"cesnonadval must be a numeric decimal. Got: '{norm_cesnonadval}'")
    if norm_discval:
        try:
            ttl_disc = float(norm_discval)
            if ttl_disc < 0:
                errors.append("discval cannot be negative")
            if "." in norm_discval:
                parts = norm_discval.split(".")
                if len(parts[0]) > 15:
                    errors.append(f"discval integer part exceeds 15 digits. Got: {len(parts[0])}")
                if len(parts[1]) > 2:
                    errors.append(f"discval decimal part exceeds 2 places. Got: {len(parts[1])}")
            else:
                if len(norm_discval) > 15:
                    errors.append(f"discval integer exceeds max length of 15 digits.")
        except ValueError:
            errors.append(f"discval must be a numeric decimal. Got: '{norm_discval}'")
    if norm_othchrgval:
        try:
            ttl_oth_chrg = float(norm_othchrgval)
            if ttl_oth_chrg < 0:
                errors.append("othchrgval cannot be negative")
            if "." in norm_othchrgval:
                parts = norm_othchrgval.split(".")
                if len(parts[0]) > 15:
                    errors.append(f"othchrgval integer part exceeds 15 digits. Got: {len(parts[0])}")
                if len(parts[1]) > 2:
                    errors.append(f"othchrgval decimal part exceeds 2 places. Got: {len(parts[1])}")
            else:
                if len(norm_othchrgval) > 15:
                    errors.append(f"othchrgval integer exceeds max length of 15 digits.")
        except ValueError:
            errors.append(f"othchrgval must be a numeric decimal. Got: '{norm_othchrgval}'")
    if norm_rndoffamt:
        try:
            val_rndoff = float(norm_rndoffamt)
            if val_rndoff < 0:
                errors.append("rndoffamt cannot be negative per schema constraints")
            if "." in norm_rndoffamt:
                parts = norm_rndoffamt.split(".")
                if len(parts[0]) > 4:
                    errors.append(f"rndoffamt integer part exceeds 4 digits. Got: {len(parts[0])}")
                if len(parts[1]) > 2:
                    errors.append(f"rndoffamt decimal part exceeds 2 places. Got: {len(parts[1])}")
            else:
                if len(norm_rndoffamt) > 4:
                    errors.append(f"rndoffamt integer exceeds max length of 4 digits.")
        except ValueError:
            errors.append(f"rndoffamt must be a numeric decimal. Got: '{norm_rndoffamt}'")
    if not norm_totinvval:
        errors.append("totinvval (Total Invoice Value) is mandatory and cannot be blank")
    else:
        try:
            ttl_inv_val = float(norm_totinvval)
            if ttl_inv_val < 0:
                errors.append("totinvval cannot be negative")
            if "." in norm_totinvval:
                parts = norm_totinvval.split(".")
                if len(parts[0]) > 15:
                    errors.append(f"totinvval integer part exceeds 15 digits. Got: {len(parts[0])}")
                if len(parts[1]) > 2:
                    errors.append(f"totinvval decimal part exceeds 2 places. Got: {len(parts[1])}")
            else:
                if len(norm_totinvval) > 15:
                    errors.append(f"totinvval integer exceeds max length of 15 digits.")
        except ValueError:
            errors.append(f"totinvval must be a numeric decimal. Got: '{norm_totinvval}'")
    if norm_payee_name:
        if len(norm_payee_name) > 100:
            errors.append(f"payee_name exceeds max length of 100 characters. Got: {len(norm_payee_name)}")
        allowed_chars = " .&'-()/,"
        if not all(c.isalnum() or c in allowed_chars for c in norm_payee_name):
            errors.append(f"payee_name contains invalid special characters. Got: '{norm_payee_name}'")
    if norm_pmtmode:
        if len(norm_pmtmode) > 6:
            errors.append(f"pmtmode exceeds max length of 6 characters. Got: {len(norm_pmtmode)}")
        if norm_pmtmode not in allowed_pmt_modes:
            errors.append(f"Invalid pmtmode. Expected one of {allowed_pmt_modes}. Got: '{norm_pmtmode}'")
    if norm_fininsbr:
        if len(norm_fininsbr) > 11:
            errors.append(f"fininsbr exceeds max length of 11 characters. Got: {len(norm_fininsbr)}")
        ifsc_pattern = r"^[A-Z]{4}0[A-Z0-9]{6}$"
        if not re.match(ifsc_pattern, norm_fininsbr):
            errors.append(f"fininsbr is not a valid IFSC format. Expected 4 letters, '0', then 6 digits/letters. Got: '{norm_fininsbr}'")
    if norm_payterm:
        if len(norm_payterm) < 1:
            errors.append("payterm must contain at least 1 character if provided.")
        if len(norm_payterm) > 100:
            errors.append(f"payterm exceeds max length of 100 characters. Got: {len(norm_payterm)}")
    if norm_payinstr:
        if len(norm_payinstr) < 1:
            errors.append("payinstr cannot be an empty string if provided")
        if len(norm_payinstr) > 100:
            errors.append(f"payinstr exceeds max length of 100 characters. Got: {len(norm_payinstr)}")
    if norm_crtrn:
        if len(norm_crtrn) < 1:
            errors.append("crtrn cannot be an empty string if provided")
        if len(norm_crtrn) > 100:
            errors.append(f"crtrn exceeds max length of 100 characters. Got: {len(norm_crtrn)}")
    if norm_dirdr:
        if len(norm_dirdr) < 1:
            errors.append("dirdr cannot be an empty string if provided")
        if len(norm_dirdr) > 100:
            errors.append(f"dirdr exceeds max length of 100 characters. Got: {len(norm_dirdr)}")
    if norm_crday:
        try:
            val_crday = int(norm_crday)
            if val_crday < 0:
                errors.append("crday (Credit Days) cannot be negative")
            if len(norm_crday) > 9:
                errors.append(f"crday exceeds max length of 9 digits. Got: {len(norm_crday)}")
        except ValueError:
            errors.append(f"crday must be a valid integer. Got: '{norm_crday}'")
    if norm_paidamt:
        try:
            val_paid = float(norm_paidamt)
            if val_paid < 0:
                errors.append("paidamt cannot be negative")
            if "." in norm_paidamt:
                parts = norm_paidamt.split(".")
                if len(parts[0]) > 15:
                    errors.append(f"paidamt integer part exceeds 15 digits. Got: {len(parts[0])}")
                if len(parts[1]) > 2:
                    errors.append(f"paidamt decimal part exceeds 2 places. Got: {len(parts[1])}")
            else:
                if len(norm_paidamt) > 15:
                    errors.append(f"paidamt integer exceeds max length of 15 digits.")
        except ValueError:
            errors.append(f"paidamt must be a numeric decimal. Got: '{norm_paidamt}'")
    if norm_balamt:
        try:
            val_bal = float(norm_balamt)
            if val_bal < 0:
                errors.append("balamt (Balance Amount) cannot be negative")
            if "." in norm_balamt:
                parts = norm_balamt.split(".")
                if len(parts[0]) > 15:
                    errors.append(f"balamt integer part exceeds 15 digits. Got: {len(parts[0])}")
                if len(parts[1]) > 2:
                    errors.append(f"balamt decimal part exceeds 2 places. Got: {len(parts[1])}")
            else:
                if len(norm_balamt) > 15:
                    errors.append(f"balamt integer exceeds max length of 15 digits.")

        except ValueError:
            errors.append(f"balamt must be a numeric decimal. Got: '{norm_balamt}'")
    if norm_payduedt:
        if not re.match(date_regex, norm_payduedt):
            errors.append(f"payduedt format is invalid. Expected DD-MM-YYYY (2010-2029). Got: '{norm_payduedt}'")
        else:
            try:
                datetime.strptime(norm_payduedt, "%d-%m-%Y")
            except ValueError:
                errors.append(f"payduedt is a malformed date: '{norm_payduedt}'")
    if norm_acctdet:
        if len(norm_acctdet) < 1:
            errors.append("acctdet cannot be empty if provided")
        if len(norm_acctdet) > 18:
            errors.append(f"acctdet exceeds max length of 18 characters. Got: {len(norm_acctdet)}")
        if not norm_acctdet.isalnum():
            if not all(c.isalnum() or c == '-' for c in norm_acctdet):
                errors.append(f"acctdet contains invalid characters. Got: '{norm_acctdet}'")
    if norm_bnknm:
        if len(norm_bnknm) < 1:
            errors.append("bnknm cannot be an empty string if provided")
        if len(norm_bnknm) > 50:
            errors.append(f"bnknm exceeds max length of 50 characters. Got: {len(norm_bnknm)}")
        allowed_chars = " .&-"
        if not all(c.isalnum() or c in allowed_chars for c in norm_bnknm):
            warnings.append(f"bnknm contains unusual characters: '{norm_bnknm}'")
    if norm_brnchnm:
        if len(norm_brnchnm) < 1:
            errors.append("brnchnm cannot be an empty string if provided")
        if len(norm_brnchnm) > 50:
            errors.append(f"brnchnm exceeds max length of 50 characters. Got: {len(norm_brnchnm)}")
    if norm_invrmk:
        rmk_len = len(norm_invrmk)
        if rmk_len < 3 or rmk_len > 100:
            errors.append(f"invrmk length must be between 3 and 100. Got: {rmk_len}")
        if not re.match(remark_pattern, norm_invrmk):
            errors.append(f"invrmk contains invalid characters. Allowed: Alphanumeric and / - ( )")
    if norm_invstdt:
        if not re.match(date_regex, norm_invstdt):
            errors.append(f"invstdt format invalid. Expected DD-MM-YYYY (2010-2029). Got: '{norm_invstdt}'")
        else:
            try:
                datetime.strptime(norm_invstdt, "%d-%m-%Y")
            except ValueError:
                errors.append(f"invstdt is not a valid calendar date: '{norm_invstdt}'")
    if norm_invenddt:
        if not re.match(date_regex, norm_invenddt):
            errors.append(f"invenddt format invalid. Expected DD-MM-YYYY (2010-2029). Got: '{norm_invenddt}'")
        else:
            try:
                end_dt = datetime.strptime(norm_invenddt, "%d-%m-%Y")
                if norm_invstdt:
                    start_dt = datetime.strptime(norm_invstdt, "%d-%m-%Y")
                    if end_dt < start_dt:
                        errors.append("invenddt (End Date) cannot be earlier than invstdt (Start Date)")
            except ValueError:
                errors.append(f"invenddt is not a valid calendar date: '{norm_invenddt}'")
    if norm_othrefno:
        if len(norm_othrefno) < 1:
            errors.append("othrefno cannot be empty if provided")
        if len(norm_othrefno) > 20:
            errors.append(f"othrefno exceeds max length of 20 characters. Got: {len(norm_othrefno)}")
    if norm_recadvref:
        ref_len = len(norm_recadvref)
        if ref_len < 1 or ref_len > 20:
            errors.append(f"recadvref length must be between 1 and 20. Got: {ref_len}")
        if not re.match(adv_pattern, norm_recadvref):
            errors.append(f"recadvref contains invalid characters. Allowed: Alphanumeric and / - ( )")
    if norm_recadvdt:
        if not re.match(date_regex, norm_recadvdt):
            errors.append(f"recadvdt format invalid. Expected DD-MM-YYYY. Got: '{norm_recadvdt}'")
        else:
            try:
                adv_dt = datetime.strptime(norm_recadvdt, "%d-%m-%Y")
            except ValueError:
                errors.append(f"recadvdt is not a valid calendar date: '{norm_recadvdt}'")
    if norm_tendref:
        ref_len = len(norm_tendref)
        if ref_len < 1 or ref_len > 20:
            errors.append(f"tendref length must be between 1 and 20. Got: {ref_len}")
        if not re.match(tend_pattern, norm_tendref):
            errors.append(f"tendref contains invalid characters. Allowed: Alphanumeric and / - ( )")
    if norm_contrref:
        ref_len = len(norm_contrref)
        if ref_len < 1 or ref_len > 20:
            errors.append(f"contrref length must be between 1 and 20. Got: {ref_len}")
        if not re.match(contr_pattern, norm_contrref):
            errors.append(f"contrref contains invalid characters. Allowed: Alphanumeric and / - ( )")
    if norm_extref:
        ref_len = len(norm_extref)
        if ref_len < 1 or ref_len > 20:
            errors.append(f"extref length must be between 1 and 20. Got: {ref_len}")
        if not re.match(ext_pattern, norm_extref):
            errors.append(f"extref contains invalid characters. Allowed: Alphanumeric and / - ( )")
    if norm_projref:
        ref_len = len(norm_projref)
        if ref_len < 1 or ref_len > 20:
            errors.append(f"projref length must be between 1 and 20. Got: {ref_len}")
        if not re.match(proj_pattern, norm_projref):
            errors.append(f"projref contains invalid characters. Allowed: Alphanumeric and / - ( )")
    if raw_porefdt:
        for fmt in ("%d-%m-%Y", "%d/%m/%y", "%d/%m/%Y", "%d.%m.%Y", "%Y-%m-%d", "%d-%m-%y"):
            try:
                norm_porefdt = datetime.strptime(raw_porefdt, fmt).strftime(target_format)
                break
            except ValueError:
                continue
        if norm_porefdt:
            try:
                po_dt  = datetime.strptime(norm_porefdt, target_format)
                doc_dt = datetime.strptime(norm_docdt, target_format)
                if po_dt > doc_dt:
                    errors.append(f"Business Logic Error: PO Date ({norm_porefdt}) cannot be after Document Date ({norm_docdt})")
                else:
                    print(f"Success! Normalized '{raw_porefdt}' to '{norm_porefdt}'")
            except ValueError:
                errors.append(f"Invalid Date: Could not validate '{norm_porefdt}' against docdt.")
        else:errors.append(f"Normalization Error: Format of '{raw_porefdt}' not recognized. Use DD-MM-YY.")
    if norm_poref:
        ref_len = len(norm_poref)
        if ref_len < 1 or ref_len > 20:
            errors.append(f"poref length must be between 1 and 20. Got: {ref_len}")
        if not re.match(po_pattern, norm_poref):
            errors.append(f"poref contains invalid characters. Allowed: Alphanumeric and / - ( )")
    if not norm_ewayreq:
        errors.append("ewayreq is a mandatory field and cannot be empty.")
    elif len(norm_ewayreq) != 1:
        errors.append(f"ewayreq must be exactly 1 character. Got: {len(norm_ewayreq)}")
    elif norm_ewayreq not in allowed_values:
        errors.append(f"ewayreq contains invalid value '{norm_ewayreq}'. Must be 'Y' or 'N'.")
    if norm_ewayreq == "Y":
        if not norm_subsupplytype:
            errors.append("subsupplytype is required when ewayreq is 'Y'")
        elif norm_subsupplytype not in valid_subtypes:
            errors.append(f"Invalid subsupplytype '{norm_subsupplytype}'. Must be between 1 and 12.")
    if len(norm_subsupplytype) > 2:
        errors.append("subsupplytype exceeds max length of 2 characters")
    if norm_ewayreq == "Y":
        if not norm_mode_of_transport:
            errors.append("mode_of_transport is required when ewayreq is 'Y'")
        elif norm_mode_of_transport not in valid_modes:
            errors.append(f"Invalid mode_of_transport '{norm_mode_of_transport}'. Must be 1, 2, 3, or 4.")
    if len(norm_mode_of_transport) > 1:
        errors.append("mode_of_transport exceeds max length of 1 character")
    
    if norm_ewayreq == "Y":
        if norm_distance_val is None or norm_distance_val <= 0:
            errors.append("distance_of_transport is required and must be greater than 0 when ewayreq is 'Y'")
        if norm_distance_val > 9999:
            errors.append(f"distance_of_transport exceeds max allowed digits (4). Got: {norm_distance}")
        if norm_distance_val > 4000:
            warnings.append("distance_of_transport exceeds the standard 4000km threshold; please verify.")
    if norm_ewayreq == "Y":
        if not norm_transporter_id:
            errors.append("transporter_id is required for EWB Part-A generation when ewayreq is 'Y'")
        elif len(norm_transporter_id) != 15:
            errors.append(f"transporter_id must be exactly 15 characters. Got: {len(norm_transporter_id)}")
        elif not re.match(trans_id_pattern, norm_transporter_id):
            errors.append(f"transporter_id '{norm_transporter_id}' has an invalid format.")
    elif len(norm_transporter_id) > 15:
        errors.append("transporter_id exceeds max length of 15 characters")
    if norm_transporter_name:
        if len(norm_transporter_name) > 100:
            errors.append(f"transporter_name exceeds max length of 100 characters. Got: {len(norm_transporter_name)}")
        if norm_transporter_name.isdigit():
            warnings.append("transporter_name appears to be numeric; please verify if this is a name.")
    if norm_ewayreq == "Y" and norm_mode_of_transport in non_road_modes:
        if not norm_transport_doc_no:
            errors.append(f"transport_doc_no is required when mode_of_transport is {norm_mode_of_transport}")
    if len(norm_transport_doc_no) > 15:
        errors.append(f"transport_doc_no exceeds max length of 15 characters. Got: {len(norm_transport_doc_no)}")
    if norm_ewayreq == "Y" and norm_mode_of_transport in non_road_modes:
        if not norm_trans_doc_dt:
            errors.append(f"transporter_doc_date is required when mode_of_transport is {norm_mode_of_transport}")
        else:
            if not re.match(date_regex, norm_trans_doc_dt):
                errors.append(f"transporter_doc_date format invalid. Expected DD-MM-YYYY. Got: '{norm_trans_doc_dt}'")
            else:
                try:
                    doc_dt = datetime.strptime(norm_trans_doc_dt, "%d-%m-%Y")
                    if doc_dt > datetime.now():
                        errors.append("transporter_doc_date cannot be a future date")
                except ValueError:
                    errors.append(f"transporter_doc_date is not a valid calendar date: '{norm_trans_doc_dt}'")
    if norm_ewayreq == "Y" and norm_mode_of_transport == "1":
        if not norm_veh_type:
            errors.append("veh_type is required for Road transport when ewayreq is 'Y'")
        elif norm_veh_type not in allowed_veh_types:
            errors.append(f"Invalid veh_type '{norm_veh_type}'. Must be 'R' (Regular) or 'O' (ODC).")
    if len(norm_veh_type) > 1:
        errors.append("veh_type exceeds max length of 1 character")
    if norm_ewayreq == "Y" and norm_mode_of_transport == "1":
        if not norm_veh_number:
            errors.append("veh_number is required for Road transport when ewayreq is 'Y'")
        elif not re.match(veh_pattern, norm_veh_number):
            if len(norm_veh_number) < 7 or len(norm_veh_number) > 15:
                errors.append(f"Invalid vehicle number format: '{norm_veh_number}'")
            else:
                warnings.append(f"Vehicle number '{norm_veh_number}' does not match standard patterns.")
    if len(norm_veh_number) > 15:
        errors.append("veh_number exceeds max length of 15 characters")
    
    if norm_brand_name:
        name_len = len(norm_brand_name)
        if name_len > 100:
            errors.append(f"brand_name exceeds max length of 100 characters. Got: {name_len}")
        if not any(char.isalnum() for char in norm_brand_name):
            warnings.append("brand_name contains only symbols; please verify.")
    if norm_client_name:
        name_len = len(norm_client_name)
        if name_len > 100:
            errors.append(f"client_name exceeds max length of 100 characters. Got: {name_len}")
        if len(norm_client_name) > 0 and not any(c.isalpha() for c in norm_client_name):
            warnings.append("client_name contains no alphabetic characters; please verify.")
    if norm_vendor_id:
        vid_len = len(norm_vendor_id)
        if vid_len > 100:
            errors.append(f"vendor_id exceeds max length of 100 characters. Got: {vid_len}")
    if norm_period:
        period_len = len(norm_period)
        if period_len > 30:
            errors.append(f"period exceeds max length of 30 characters. Got: {period_len}")
        if norm_period.isdigit() and len(norm_period) == 4:
            pass
    if norm_upiid:
        if len(norm_upiid) > 100:
            errors.append(f"upiid exceeds max length of 100 characters. Got: {len(norm_upiid)}")
        elif not re.match(upi_pattern, norm_upiid):
            warnings.append(f"upiid '{norm_upiid}' does not match standard VPA format (e.g., name@bank)")
    if norm_upipayeename:
        name_len = len(norm_upipayeename)
        if name_len > 100:
            errors.append(f"upipayeename exceeds max length of 100 characters. Got: {name_len}")
        if not re.match(r"^[a-zA-Z0-9\s\.]*$", norm_upipayeename):
            warnings.append("upipayeename contains special characters; please ensure it matches the bank account name.")
    if norm_upiacct:
        if not norm_upiacct.isdigit():
            errors.append(f"upiacctnumber must contain only numbers. Got: '{norm_upiacct}'")
        acct_len = len(norm_upiacct)
        if acct_len < 9 or acct_len > 18:
            errors.append(f"upiacctnumber must be between 9 and 18 digits. Got: {acct_len}")
    if norm_upi_ifsc:
        if len(norm_upi_ifsc) != 11:
            errors.append(f"upiactifsccd must be exactly 11 characters. Got: {len(norm_upi_ifsc)}")
        elif not re.match(ifsc_pattern, norm_upi_ifsc):
            errors.append(f"Invalid upiactifsccd format: '{norm_upi_ifsc}'. Expected format: BBBB0CCCCCC")
    output_data = OrderedDict()
    output_data["self_gstin"] = norm_gstin
    output_data["system_cd"] = norm_sys
    output_data["branch_cd"] = norm_br
    output_data["vertical_cd"] = norm_vert
    output_data["irnreq"] = norm_irnreq
    output_data["irn"] = norm_irn
    output_data["trancatg"] = norm_trancatg
    output_data["reversecharge"] = norm_revcharge
    output_data["transactionmode"] = norm_transmode
    output_data["ecom_gstin"] = norm_ecom_gstin
    output_data["igst_on_intra"] = norm_igst_intra
    output_data["expcat"] = norm_expcat
    output_data["wthpay"] = norm_wthpay 
    output_data["shipbno"] = norm_shipbno 
    output_data["shipbdt"] = norm_shipbdt 
    output_data["port"] = norm_port 
    output_data["invforcur"] = norm_invforcur
    output_data["forcur"] = norm_forcur
    output_data["refclm"] = norm_refclm
    output_data["cntcode"] = norm_cntcode 
    output_data["expduty"]=norm_expduty
    output_data["document_type"]=norm_doc_type
    output_data["docno"] = norm_docno
    output_data["docdt"]=norm_docdt
    output_data["orginvno"]=norm_orginvno
    output_data["orginvdt"]=norm_orginvdt
    output_data["supplier_gstin"] = norm_sup_gstin
    output_data["supplier_lglnm"] = norm_sup_lglnm
    output_data["supplier_trdnm"] = norm_sup_trdnm
    output_data["supplier_bno"] = norm_sup_bno
    output_data["supplier_bnm"] = norm_sup_bnm
    output_data["supplier_flno"] = norm_sup_flno
    output_data["supplier_loc"] = norm_sup_loc
    output_data["supplier_dst"] = norm_sup_dst
    output_data["supplier_pin"] = norm_sup_pin
    output_data["supplier_state"] = norm_sup_state
    output_data["supplier_phone"] = norm_sup_phone
    output_data["supplier_email"] = norm_sup_email
    output_data["cust_cd"] = norm_cust_cd
    output_data["buyer_gstin"] = norm_buy_gstin
    output_data["buyer_lglnm"] = norm_buy_lglnm
    output_data["buyer_trdnm"] = norm_buy_trdnm
    output_data["buyer_bno"] = norm_buy_bno
    output_data["buyer_bnm"] = norm_buy_bnm
    output_data["buyer_flno"] = norm_buy_flno
    output_data["buyer_loc"] = norm_buy_loc
    output_data["buyer_dst"] = norm_buy_dst
    output_data["buyer_pin"] = norm_buy_pin
    output_data["buyer_state"] = norm_buy_state
    output_data["pos"]=norm_pos
    output_data["buyer_phone"] = norm_buy_phone
    output_data["buyer_email"] = norm_buy_email
    output_data["disp_gstin"] = norm_disp_gstin
    output_data["disp_trdnm"] = norm_disp_trdnm
    output_data["disp_bno"] = norm_disp_bno
    output_data["disp_flno"] = norm_disp_flno
    output_data["disp_loc"] = norm_disp_loc
    output_data["disp_dst"] = norm_disp_dst
    output_data["disp_pin"] = norm_disp_pin
    output_data["disp_state"] = norm_disp_state
    output_data["disp_phone"] = norm_disp_phone
    output_data["disp_email"] = norm_disp_email
    output_data["ship_gstin"] = norm_ship_gstin
    output_data["ship_lglnm"] = norm_ship_lglnm
    output_data["ship_trdnm"] = norm_ship_trdnm
    output_data["ship_bno"] = norm_ship_bno
    output_data["ship_bnm"] = norm_ship_bnm
    output_data["ship_flno"] = norm_ship_flno
    output_data["ship_loc"] = norm_ship_loc
    output_data["ship_dst"] = norm_ship_dst
    output_data["ship_pin"] = norm_ship_pin
    output_data["ship_state"] = norm_ship_state
    output_data["ship_phone"] = norm_ship_phone
    output_data["ship_email"] = norm_ship_email
    output_data["frmdt"] = norm_frmdt
    output_data["todt"] = norm_todt
    output_data["itemcd"] = norm_itemcd
    output_data["prdnm"] = norm_prdnm
    output_data["prddesc"] = norm_prddesc
    output_data["isservc"] = norm_isservc
    output_data["hsncd"] = norm_hsncd
    output_data["barcde"] = norm_barcde
    output_data["qty"] = norm_qty
    output_data["freeqty"] = norm_freeqty
    output_data["uqc"] = norm_uqc
    output_data["unitrate"] = norm_unitrate
    output_data["grossamt"] = norm_grossamt
    output_data["discount"] = norm_discount
    output_data["othchrg"] = norm_othchrg
    output_data["pretaxval"] = norm_pretaxval
    output_data["assamt"] = norm_assamt
    output_data["taxability"] = norm_taxability
    output_data["diffpercent"] = norm_diffpercent
    output_data["cgstrt"] = norm_cgstrt
    output_data["cgstamt"] = norm_cgstamt
    output_data["sgstrt"] = norm_sgstrt
    output_data["sgstamt"] = norm_sgstamt
    output_data["igstrt"] = norm_igstrt
    output_data["igstamt"] = norm_igstamt
    output_data["cessrt"] = norm_cessrt
    output_data["cessamt"] = norm_cessamt
    output_data["cessnonadval"] = norm_cessnonadval
    output_data["statecessrt"] = norm_statecessrt
    output_data["statecessamt"] = norm_statecessamt
    output_data["statecesnonadvlamt"] = norm_statecesnonadvl
    output_data["totitemval"] = norm_totitemval
    output_data["ordlineref"] = norm_ordlineref
    output_data["orgcntry"] = norm_orgcntry
    output_data["prdsino"] = norm_prdsino
    output_data["batchname"] = norm_batchname
    output_data["batchexpirydt"] = norm_batchexpirydt
    output_data["batchwarrantydt"] = norm_batchwarrantydt
    output_data["ttlassval"] = norm_ttlassval
    output_data["cgstval"] = norm_cgstval
    output_data["sgstval"] = norm_sgstval
    output_data["igstval"] = norm_igstval
    output_data["cesval"] = norm_cesval
    output_data["stcesval"] = norm_stcesval
    output_data["cesnonadval"] = norm_cesnonadval
    output_data["discval"] = norm_discval
    output_data["othchrgval"] = norm_othchrgval
    output_data["rndoffamt"] = norm_rndoffamt
    output_data["totinvval"] = norm_totinvval
    output_data["payee_name"] = norm_payee_name
    output_data["pmtmode"] = norm_pmtmode
    output_data["fininsbr"] = norm_fininsbr
    output_data["payterm"] = norm_payterm
    output_data["payinstr"] = norm_payinstr
    output_data["crtrn"] = norm_crtrn
    output_data["dirdr"] = norm_dirdr
    output_data["crday"] = norm_crday
    output_data["paidamt"] = norm_paidamt
    output_data["balamt"] = norm_balamt
    output_data["payduedt"] = norm_payduedt
    output_data["acctdet"] = norm_acctdet
    output_data["bnknm"] = norm_bnknm
    output_data["brnchnm"] = norm_brnchnm
    output_data["invrmk"] = norm_invrmk
    output_data["invstdt"] = norm_invstdt
    output_data["invenddt"] = norm_invenddt
    output_data["othrefno"] = norm_othrefno
    output_data["recadvref"] = norm_recadvref
    output_data["recadvdt"] = norm_recadvdt
    output_data["tendref"] = norm_tendref
    output_data["contrref"] = norm_contrref
    output_data["extref"] = norm_extref
    output_data["projref"] = norm_projref
    output_data["porefdt"] = norm_porefdt
    output_data["poref"] = norm_poref
    output_data["ewayreq"] = norm_ewayreq
    output_data["subsupplytype"] = norm_subsupplytype
    output_data["mode_of_transport"] = norm_mode_of_transport
    output_data["distance_of_transport"] = norm_distance_str
    output_data["transporter_id"] = norm_transporter_id
    output_data["transporter_name"] = norm_transporter_name
    output_data["transport_doc_no"] = norm_transport_doc_no
    output_data["transporter_doc_date"] = norm_trans_doc_dt
    output_data["veh_type"] = norm_veh_type
    output_data["veh_number"] = norm_veh_number
    output_data["brand_name"] = norm_brand_name
    output_data["client_name"] = norm_client_name
    output_data["vendor_id"] = norm_vendor_id
    output_data["period"] = norm_period
    output_data["upiid"] = norm_upiid
    output_data["upipayeename"] = norm_upipayeename
    output_data["upiacctnumber"] = norm_upiacct
    output_data["upiactifsccd"] = norm_upi_ifsc
    if errors:
        output_data["error"] = " | ".join(errors)
        if output_invalid:
            try:
                with open(output_invalid, "w", encoding="utf-8") as f:
                    json.dump(output_data, f, indent=2)
                print(f"❌ Validation failed: {output_invalid}")
            except Exception as e:
                pass
    else:
        if "error" in output_data:
            del output_data["error"]
        if output_valid:
            try:
                with open(output_valid, "w", encoding="utf-8") as f:
                    json.dump(output_data, f, indent=2)
                print(f"✅ Validation successful: {output_valid}")
            except Exception as e:
                pass
    return {"payload": output_data, "errors": errors, "warnings": warnings}

def clean_str(val: Any) -> str:
    if val is None:
        return ""
    return str(val).strip().strip("\"' \t\r\n")

def clean_decimal_str(val: Any, decimals: int = 2, audit_log: Optional[List[Dict[str, Any]]] = None, field: str = "") -> str:
    """Cleans decimal strings, converts commas to dots, and logs changes."""
    if val is None or str(val).strip() == "":
        return f"0.{'0' * decimals}"
    s_raw = str(val).strip()
    s = s_raw.replace(" ", "")
    has_comma = "," in s
    if "," in s and "." in s:
        s = s.replace(",", "")
    elif "," in s and "." not in s:
        s = s.replace(",", ".")
    s = re.sub(r"[^\d.-]", "", s)
    try:
        d = Decimal(s)
        fmt = f"0.{'0' * decimals}"
        quantized = str(d.quantize(Decimal(fmt), rounding=ROUND_HALF_UP))
        if has_comma and audit_log is not None and field:
            audit_log.append({
                "category": "FORMAT_NORMALIZATION",
                "field": field,
                "original": s_raw,
                "corrected": quantized,
                "description": f"Replaced comma decimal separator '{s_raw}' with standard point notation '{quantized}'"
            })
        return quantized
    except Exception:
        return "0.00"

def clean_int_str(val: Any) -> str:
    return normalize_numeric_string(val)

def normalize_date_to_standard(raw_date: Any, target_sep: str = "-", audit_log: Optional[List[Dict[str, Any]]] = None, field: str = "") -> str:
    """Converts dates to DD-MM-YYYY format and logs format changes."""
    if not raw_date:
        return ""
    s_raw = str(raw_date).strip()
    formats = [
        "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d.%m.%Y",
        "%d-%m-%y", "%d/%m/%y", "%Y/%m/%d"
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(s_raw, fmt)
            normalized = dt.strftime(f"%d{target_sep}%m{target_sep}%Y")
            if normalized != s_raw and audit_log is not None and field:
                audit_log.append({
                    "category": "DATE_FORMAT_NORMALIZATION",
                    "field": field,
                    "original": s_raw,
                    "corrected": normalized,
                    "description": f"Standardized date format from '{s_raw}' to '{normalized}'"
                })
            return normalized
        except ValueError:
            continue
    return s_raw

def clean_state_code(raw_state: Any, audit_log: Optional[List[Dict[str, Any]]] = None, field: str = "") -> str:
    if not raw_state:
        return ""
    padded = normalize_state_code(raw_state)
    if len(str(raw_state).strip()) == 1 and audit_log is not None and field:
        audit_log.append({
            "category": "STATE_CODE_PADDING",
            "field": field,
            "original": raw_state,
            "corrected": padded,
            "description": f"Padded single digit state code '{raw_state}' to 2-digit format '{padded}'"
        })
    return padded

def clean_gstin(raw_gstin: Any) -> str:
    return normalize_buyer_gstin(raw_gstin)


class PayloadBuilder:
    """
    Builds and auto-corrects Indian GST E-Invoice & E-Way Bill payloads,
    tracking an exhaustive audit trail of all corrections.
    """

    @classmethod
    def auto_correct_and_build(cls, raw_invoice: Dict[str, Any], taxable_value_input: Optional[Union[float, Decimal, Dict[str, Any]]] = None) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Takes raw/dirty invoice data, applies key aliasing, value normalization,
        HSN lookups against Statutory Tariff Master & ML HSN Intelligence (128-D Contrastive Hybrid),
        statutory tax rates reconciliation, and tax calculations (with optional user taxable value override),
        returning (corrected_invoice, audit_log).
        """
        audit_log: List[Dict[str, Any]] = []

        if taxable_value_input is None and isinstance(raw_invoice, dict):
            taxable_value_input = raw_invoice.get("taxable_value_input") or raw_invoice.get("custom_taxable_value") or raw_invoice.get("override_taxable_value")

        # Step 1: Normalize dictionary keys and collect key modifications
        data, key_mods = normalize_dict_keys_with_log(raw_invoice)
        audit_log.extend(key_mods)

        # Step 2: Extract top-level sections (support both nested NIC and flat format)
        trandt1 = data.get("trandt1") if isinstance(data.get("trandt1"), dict) else data
        expdt1 = data.get("expdt1") if isinstance(data.get("expdt1"), dict) else (data if data.get("expcat") or data.get("port") else {})
        docdt1 = data.get("docdt1") if isinstance(data.get("docdt1"), dict) else data
        supplierdt1 = data.get("supplierdt1") if isinstance(data.get("supplierdt1"), dict) else data
        buyerdt1 = data.get("buyerdt1") if isinstance(data.get("buyerdt1"), dict) else data
        dispdt1 = data.get("dispdt1") if isinstance(data.get("dispdt1"), dict) else (data if data.get("disp_gstin") or data.get("disp_trdnm") or data.get("disp_loc") else None)
        shipdtl = data.get("shipdtl", data.get("shipdt1")) if isinstance(data.get("shipdtl", data.get("shipdt1")), dict) else (data if data.get("ship_gstin") or data.get("ship_lglnm") or data.get("ship_loc") else None)
        itemdtls = data.get("itemdtls", [])
        if not itemdtls and (data.get("prdnm") or data.get("hsncd")):
            itemdtls = [data]
        valdt1 = data.get("valdt1") if isinstance(data.get("valdt1"), dict) else data
        ewbdt1 = data.get("ewbdt1") if isinstance(data.get("ewbdt1"), dict) else data

        # Header Details & GSTIN Preservation (GSTIN cannot be normalized or guessed; preserve as is)
        self_gstin = clean_gstin(data.get("self_gstin", ""))
        sup_gstin = clean_gstin(supplierdt1.get("supplier_gstin", data.get("supplier_gstin", "")))

        # Fallback only if self_gstin was completely omitted:
        if not self_gstin and sup_gstin:
            self_gstin = sup_gstin
        elif not sup_gstin and self_gstin:
            sup_gstin = self_gstin

        system_cd = clean_str(data.get("system_cd", ""))
        branch_cd = clean_str(data.get("branch_cd", ""))
        vertical_cd = clean_str(data.get("vertical_cd", ""))
        irnreq = clean_str(data.get("irnreq", "Y")).upper() or "Y"

        # Transaction Details (trandt1)
        raw_trancatg = clean_str(trandt1.get("trancatg", "B2B")).upper() or "B2B"
        trancatg = raw_trancatg

        # Determine raw reverse charge and field name
        raw_rev_val = None
        has_rev = False
        rc_field = "trandt1.reversecharge"
        for k in ("RevChrg", "revchrg", "reversecharge", "reverse_charge", "rev_chrg", "rcm"):
            if k in trandt1:
                raw_rev_val = trandt1[k]
                rc_field = f"trandt1.{k}"
                has_rev = True
                break
        if not has_rev:
            for k in ("RevChrg", "revchrg", "reversecharge", "reverse_charge", "rev_chrg", "rcm"):
                if k in data:
                    raw_rev_val = data[k]
                    rc_field = k
                    has_rev = True
                    break
        if not has_rev:
            raw_rev_val = trandt1.get("reversecharge", "N")

        if normalize_reverse_charge:
            norm_rc, rc_audit = normalize_reverse_charge(raw_rev_val, field_name=rc_field)
            if rc_audit:
                audit_log.append(rc_audit)
            reversecharge = norm_rc
        else:
            reversecharge = clean_str(raw_rev_val).upper() or "N"

        transactionmode = clean_str(trandt1.get("transactionmode", "REG")).upper() or "REG"
        igstonintra = clean_str(trandt1.get("igstonintra", "N")).upper() or "N"

        # Scenario 3: Valid Exceptional Intra-State IGST Supply
        is_exceptional_intra = bool(
            data.get("is_exceptional_intra_igst") or
            trandt1.get("is_exceptional_intra_igst") or
            (str(trandt1.get("igstonintra", "")).strip().upper() == "Y")
        )
        if is_exceptional_intra and trancatg not in ("EXP", "EXPWP", "EXPWOP", "SEZWP", "SEZWOP"):
            if igstonintra != "Y":
                audit_log.append({
                    "category": "BUSINESS_RULE_AUTO_CORRECTION",
                    "field": "trandt1.igstonintra",
                    "original": igstonintra or "N",
                    "corrected": "Y",
                    "description": 'If the transaction legally requires IGST on intra-state movement, set the flag "IgstOnIntra": "Y" under TranDtls.'
                })
            igstonintra = "Y"

        # Reverse Charge Rule Check (Rule 2162)
        if trancatg != "B2B" and reversecharge == "Y":
            exp_sec = expdt1 or data.get("expdtl") or {}
            w_pay = exp_sec.get("wthpay") if isinstance(exp_sec, dict) else None
            reason_msg = get_reverse_charge_rejection_reason(trancatg, w_pay) if get_reverse_charge_rejection_reason else f"Reverse charge is not applicable for '{trancatg}' transactions (Rule 2162); auto-set to 'N'"
            audit_log.append({
                "category": "BUSINESS_RULE_AUTO_CORRECTION",
                "field": "trandt1.reversecharge",
                "original": "Y",
                "corrected": "N",
                "description": reason_msg
            })
            reversecharge = "N"

        if igstonintra == "Y" and reversecharge != "Y":
            audit_log.append({
                "category": "BUSINESS_RULE_AUTO_CORRECTION",
                "field": "trandt1.reversecharge",
                "original": reversecharge,
                "corrected": "Y",
                "description": "Reverse charge is mandatory when IGST on intra is enabled (Rule 2294); auto-set to 'Y'"
            })
            reversecharge = "Y"

        # Export & SEZ checks
        is_export = trancatg == "EXP"
        is_sez = trancatg in ("SEZWP", "SEZWOP")
        is_sez_buyer_flag = bool(data.get("is_sez_buyer") or "SEZ" in str(buyerdt1.get("buyer_lglnm", "")).upper() or "SEZ" in str(buyerdt1.get("buyer_trdnm", "")).upper())
        if is_sez and not is_sez_buyer_flag:
            audit_log.append({
                "category": "SUPPLY_TYPE_AUTO_CORRECTION",
                "field": "trandt1.trancatg",
                "original": trancatg,
                "corrected": "B2B",
                "description": f"Auto-aligned transaction category from '{trancatg}' to 'B2B' as recipient is a regular domestic taxpayer (Rule 2247)."
            })
            trancatg = "B2B"
            is_sez = False

        if (is_export or is_sez) and igstonintra == "Y":
            audit_log.append({
                "category": "BUSINESS_RULE_AUTO_CORRECTION",
                "field": "trandt1.igstonintra",
                "original": "Y",
                "corrected": "N",
                "description": f"IGST on intra state supply is not applicable to {trancatg} transactions (Rule 2268); auto-set to 'N'"
            })
            igstonintra = "N"

        # Export Details (expdt1)
        clean_expdt1 = {}
        if is_export or expdt1:
            expcat = clean_str(expdt1.get("expcat", "DIR")).upper() or "DIR"
            wthpay = clean_str(expdt1.get("wthpay", "Y")).upper() or "Y"
            shipbno = clean_str(expdt1.get("shipbno", ""))
            shipbdt = normalize_date_to_standard(expdt1.get("shipbdt", ""), audit_log=audit_log, field="expdt1.shipbdt")
            port = clean_str(expdt1.get("port", "")).upper()
            cntcode = clean_str(expdt1.get("cntcode", "")).upper()
            forcur = clean_str(expdt1.get("forcur", "")).upper()

            if cntcode in COUNTRY_CURRENCY_MAP and (not forcur or forcur not in COUNTRY_CURRENCY_MAP.values()):
                correct_cur = COUNTRY_CURRENCY_MAP[cntcode]
                audit_log.append({
                    "category": "CURRENCY_MASTER_ALIGNMENT",
                    "field": "expdt1.forcur",
                    "original": forcur,
                    "corrected": correct_cur,
                    "description": f"Auto-aligned foreign currency to '{correct_cur}' matching country code '{cntcode}'"
                })
                forcur = correct_cur

            clean_expdt1 = {
                "expcat": expcat,
                "wthpay": wthpay,
                "shipbno": shipbno,
                "shipbdt": shipbdt,
                "port": port,
                "forcur": forcur,
                "cntcode": cntcode
            }

        # Document Details (docdt1)
        raw_docno = clean_str(docdt1.get("docno", ""))
        clean_docno = re.sub(r"[^0-9A-Za-z/-]", "", raw_docno)[:16]
        if clean_docno != raw_docno:
            audit_log.append({
                "category": "FORMAT_NORMALIZATION",
                "field": "docdt1.docno",
                "original": raw_docno,
                "corrected": clean_docno,
                "description": "Removed invalid punctuation characters from document number per NIC Rule 2281"
            })

        raw_doc_dt = docdt1.get("docdt", docdt1.get("Dt", data.get("docdt", data.get("Dt", ""))))
        norm_doc_dt = normalize_date_to_standard(raw_doc_dt, audit_log=audit_log, field="docdt1.docdt")
        clean_docdt1 = {
            "document_type": clean_str(docdt1.get("document_type", "INV")).upper() or "INV",
            "docno": clean_docno,
            "docdt": norm_doc_dt
        }

        # Future date (Rule 2163) and NIC 2-Day rule compliance checks for IRN generation
        if clean_docdt1["docdt"]:
            try:
                inv_dt = datetime.strptime(clean_docdt1["docdt"], "%d-%m-%Y").date()
                today_ist = get_ist_today() if get_ist_today else datetime.now().date()
                if inv_dt > today_ist:
                    is_utc = bool(data.get("is_utc_context") or data.get("utc_desync") or data.get("server_utc"))
                    diag = classify_future_date_diagnostic(inv_dt, raw_str=str(raw_doc_dt), server_today=today_ist, is_utc_context=is_utc) if classify_future_date_diagnostic else None
                    if diag:
                        audit_log.append({
                            "category": f"NIC_RULE_2163_{diag['scenario']}",
                            "field": "docdt1.docdt",
                            "original": str(raw_doc_dt),
                            "corrected": diag["valid_str"].replace("/", "-"),
                            "description": diag["reason"]
                        })
                        clean_docdt1["docdt"] = diag["valid_str"].replace("/", "-")
                        inv_dt = diag["valid_date"]
                    else:
                        clean_docdt1["docdt"] = today_ist.strftime("%d-%m-%Y")
                        inv_dt = today_ist

                days_diff = (today_ist - inv_dt).days
                if days_diff > 2 and irnreq == "Y":
                    new_date_str = today_ist.strftime("%d-%m-%Y")
                    audit_log.append({
                        "category": "NIC_RULE_DATE_RESTRICTION",
                        "field": "docdt1.docdt",
                        "original": clean_docdt1["docdt"],
                        "corrected": new_date_str,
                        "description": f"NIC 2-day rule: Auto-aligned document date '{clean_docdt1['docdt']}' ({days_diff} days old) to current date '{new_date_str}' (NIC Rule 2164 compliant)."
                    })
                    clean_docdt1["docdt"] = new_date_str
                    inv_dt = today_ist
            except Exception:
                pass

        # Supplier Details (supplierdt1)
        raw_sup_state = clean_str(supplierdt1.get("supplier_state", ""))
        sup_state = clean_state_code(raw_sup_state or (sup_gstin[:2] if len(sup_gstin) >= 2 else ""), audit_log=audit_log, field="supplierdt1.supplier_state")

        if sup_gstin and len(sup_gstin) >= 2 and sup_gstin[:2].isdigit() and sup_state != sup_gstin[:2]:
            audit_log.append({
                "category": "BUSINESS_RULE_AUTO_CORRECTION",
                "field": "supplierdt1.supplier_state",
                "original": sup_state,
                "corrected": sup_gstin[:2],
                "description": f"Synchronized supplier state code '{sup_state}' with first 2 digits of GSTIN '{sup_gstin[:2]}' (Rule 2258)"
            })
            sup_state = sup_gstin[:2]

        clean_supplierdt1 = {
            "supplier_gstin": sup_gstin,
            "supplier_lglnm": normalize_field(supplierdt1.get("supplier_lglnm", "")),
            "supplier_trdnm": normalize_field(supplierdt1.get("supplier_trdnm", supplierdt1.get("supplier_lglnm", ""))),
            "supplier_bno": normalize_field(supplierdt1.get("supplier_bno", "")),
            "supplier_bnm": normalize_ship_bnm(supplierdt1.get("supplier_bnm", "")),
            "supplier_flno": normalize_ship_flno(supplierdt1.get("supplier_flno", "NAA")),
            "supplier_loc": normalize_ship_loc(supplierdt1.get("supplier_loc", "")),
            "supplier_dst": normalize_ship_dst(supplierdt1.get("supplier_dst", "")),
            "supplier_pin": normalize_numeric_string(supplierdt1.get("supplier_pin", "")),
            "supplier_state": sup_state,
            "supplier_phone": normalize_numeric_string(supplierdt1.get("supplier_phone", "")),
            "supplier_email": normalize_email(supplierdt1.get("supplier_email", ""))
        }

        # Buyer Details (buyerdt1)
        raw_buy_gstin = normalize_buyer_gstin(buyerdt1.get("buyer_gstin", data.get("buyer_gstin", "")))
        buy_gstin = raw_buy_gstin
        if raw_buy_gstin and raw_buy_gstin != "URP" and len(raw_buy_gstin) != 15:
            audit_log.append({
                "category": "INVALID_GSTIN_LENGTH",
                "field": "buyerdt1.buyer_gstin",
                "original": raw_buy_gstin,
                "corrected": raw_buy_gstin,
                "description": f"Customer input buyer_gstin '{raw_buy_gstin}' has invalid length ({len(raw_buy_gstin)} chars, expected 15 or 'URP')."
            })
        raw_pos = normalize_field(buyerdt1.get("pos", data.get("pos", "")))
        pos = clean_state_code(raw_pos, audit_log=audit_log, field="buyerdt1.pos")
        raw_buy_state = normalize_field(buyerdt1.get("buyer_state", data.get("buyer_state", "")))
        buy_state = clean_state_code(raw_buy_state, audit_log=audit_log, field="buyerdt1.buyer_state")
        buy_pin = normalize_numeric_string(buyerdt1.get("buyer_pin", data.get("buyer_pin", "")))

        # Export Auto-Alignments
        if is_export:
            if buy_gstin != "URP":
                audit_log.append({
                    "category": "EXPORT_RULE_AUTO_ALIGNMENT",
                    "field": "buyerdt1.buyer_gstin",
                    "original": buy_gstin,
                    "corrected": "URP",
                    "description": "Auto-set Buyer GSTIN to 'URP' as mandatory for Export transactions (Rule 2248)"
                })
                buy_gstin = "URP"

            if pos != "96":
                audit_log.append({
                    "category": "EXPORT_RULE_AUTO_ALIGNMENT",
                    "field": "buyerdt1.pos",
                    "original": pos,
                    "corrected": "96",
                    "description": "Auto-set POS to '96' (Other Country) for Export transactions (Rule 2232)"
                })
                pos = "96"

            if buy_state != "96":
                audit_log.append({
                    "category": "EXPORT_RULE_AUTO_ALIGNMENT",
                    "field": "buyerdt1.buyer_state",
                    "original": buy_state,
                    "corrected": "96",
                    "description": "Auto-set Buyer State to '96' (Other Country) for Export transactions (Rule 2261)"
                })
                buy_state = "96"

            if buy_pin != "999999":
                audit_log.append({
                    "category": "EXPORT_RULE_AUTO_ALIGNMENT",
                    "field": "buyerdt1.buyer_pin",
                    "original": buy_pin,
                    "corrected": "999999",
                    "description": "Auto-set Buyer PIN to '999999' as mandatory for Direct Export transactions (Rule 2275)"
                })
                buy_pin = "999999"
        else:
            # Domestic / SEZ fallback resolution
            # Scenario 2: Wrong Place of Supply (Pos) Entered
            # Seller State = "27", Recipient is in Karnataka (29), but payload has: "BuyerDtls": { "Pos": "27" }
            dest_state = None
            if buy_gstin and buy_gstin != "URP" and len(buy_gstin) >= 2 and buy_gstin[:2].isdigit():
                dest_state = buy_gstin[:2]
            elif buy_state and buy_state.isdigit() and buy_state != "96":
                dest_state = buy_state

            if dest_state and sup_state and dest_state != sup_state:
                if pos == sup_state or not pos:
                    audit_log.append({
                        "category": "BUSINESS_RULE_AUTO_CORRECTION",
                        "field": "buyerdt1.pos",
                        "original": pos or "(blank)",
                        "corrected": dest_state,
                        "description": "If this was actually an inter-state sale to an out-of-state recipient, fix the recipient's Pos code to match the destination state."
                    })
                    pos = dest_state

            # Rule 2174 / Scenario 2: Incorrect Place of Supply (Pos) Passed on Local Sale
            ship_state_val = str(shipdtl.get("ship_state", shipdtl.get("state", "")) if shipdtl else "").strip()
            is_actual_local = bool(
                raw_invoice.get("is_actual_local_sale") or
                data.get("is_actual_local_sale") or
                (dest_state and sup_state and dest_state == sup_state and pos != sup_state and not ship_state_val) or
                (dest_state and sup_state and dest_state == sup_state and pos != sup_state and ship_state_val == sup_state)
            )
            if dest_state and sup_state and is_actual_local and pos != sup_state:
                audit_log.append({
                    "category": "BUSINESS_RULE_AUTO_CORRECTION",
                    "field": "buyerdt1.pos",
                    "original": pos,
                    "corrected": sup_state,
                    "description": f"If the transaction was actually a local intra-state sale, correct Pos to match the supplier's state ({sup_state}) (Rule 2174)."
                })
                pos = sup_state

            # Rule 2174 / Scenario 4: Bill-to / Ship-to State Confusion (Section 10(1)(b) of the IGST Act)
            if ship_state_val and sup_state and ship_state_val == sup_state and pos != sup_state:
                audit_log.append({
                    "category": "STATUTORY_BILL_TO_SHIP_TO_RULE",
                    "field": "buyerdt1.pos",
                    "original": pos,
                    "corrected": pos,
                    "description": 'In "Bill To – Ship To" transactions where the billing party is out-of-state, the Place of Supply is the billing party\'s state, making the invoice inter-state requiring IGST (Section 10(1)(b) of the IGST Act).'
                })

            if not pos and buy_gstin and buy_gstin != "URP" and len(buy_gstin) >= 2:
                pos = buy_gstin[:2]
                audit_log.append({
                    "category": "BUSINESS_RULE_AUTO_CORRECTION",
                    "field": "buyerdt1.pos",
                    "original": "",
                    "corrected": pos,
                    "description": f"Derived missing POS '{pos}' from Buyer GSTIN prefix"
                })
            if not buy_state and buy_gstin and buy_gstin != "URP" and len(buy_gstin) >= 2:
                buy_state = buy_gstin[:2]
                audit_log.append({
                    "category": "BUSINESS_RULE_AUTO_CORRECTION",
                    "field": "buyerdt1.buyer_state",
                    "original": "",
                    "corrected": buy_state,
                    "description": f"Derived missing Buyer State '{buy_state}' from Buyer GSTIN prefix"
                })
            if not pos and buy_state:
                pos = buy_state
            if not buy_state and pos:
                buy_state = pos

        clean_buyerdt1 = {
            "is_sez_buyer": True if (is_sez or is_sez_buyer_flag or data.get("is_sez_buyer") or buyerdt1.get("is_sez_buyer")) else False,
            "buyer_gstin": buy_gstin,
            "buyer_trdnm": normalize_field(buyerdt1.get("buyer_trdnm", "")),
            "buyer_lglnm": normalize_field(buyerdt1.get("buyer_lglnm", "")),
            "buyer_bno": normalize_field(buyerdt1.get("buyer_bno", "NAA")),
            "buyer_bnm": normalize_ship_bnm(buyerdt1.get("buyer_bnm", "")),
            "buyer_flno": normalize_ship_flno(buyerdt1.get("buyer_flno", "NAA")),
            "buyer_loc": normalize_ship_loc(buyerdt1.get("buyer_loc", "")),
            "buyer_dst": normalize_ship_dst(buyerdt1.get("buyer_dst", "")),
            "buyer_pin": buy_pin,
            "buyer_state": buy_state,
            "pos": pos,
            "buyer_phone": normalize_numeric_string(buyerdt1.get("buyer_phone", "")),
            "buyer_email": normalize_email(buyerdt1.get("buyer_email", ""))
        }

        # Dispatch Details (dispdt1)
        clean_dispdt1 = None
        if dispdt1:
            raw_disp_gstin = normalize_buyer_gstin(dispdt1.get("disp_gstin", ""))
            if raw_disp_gstin and raw_disp_gstin != "URP" and len(raw_disp_gstin) != 15:
                audit_log.append({
                    "category": "INVALID_GSTIN_LENGTH",
                    "field": "dispdt1.disp_gstin",
                    "original": raw_disp_gstin,
                    "corrected": raw_disp_gstin,
                    "description": f"Customer input disp_gstin '{raw_disp_gstin}' has invalid length ({len(raw_disp_gstin)} chars, expected 15 or 'URP')."
                })
            disp_st = clean_state_code(dispdt1.get("disp_state", ""), audit_log=audit_log, field="dispdt1.disp_state")
            if raw_disp_gstin and len(raw_disp_gstin) >= 2 and raw_disp_gstin[:2].isdigit() and disp_st != raw_disp_gstin[:2]:
                audit_log.append({
                    "category": "BUSINESS_RULE_AUTO_CORRECTION",
                    "field": "dispdt1.disp_state",
                    "original": disp_st,
                    "corrected": raw_disp_gstin[:2],
                    "description": f"Synchronized dispatch state code '{disp_st}' with first 2 digits of dispatch GSTIN '{raw_disp_gstin[:2]}' (Rule 2200/2258)"
                })
                disp_st = raw_disp_gstin[:2]
            clean_dispdt1 = {
                "disp_gstin": raw_disp_gstin,
                "disp_trdnm": normalize_ship_trdnm(dispdt1.get("disp_trdnm", "")),
                "disp_bno": normalize_ship_bno(dispdt1.get("disp_bno", "NAA")),
                "disp_bnm": normalize_ship_bnm(dispdt1.get("disp_bnm", "NAA")),
                "disp_flno": normalize_ship_flno(dispdt1.get("disp_flno", "NAA")),
                "disp_loc": normalize_ship_loc(dispdt1.get("disp_loc", "")),
                "disp_dst": normalize_ship_dst(dispdt1.get("disp_dst", "")),
                "disp_pin": normalize_ship_pin(dispdt1.get("disp_pin", "")),
                "disp_state": disp_st,
                "disp_phone": normalize_numeric_string(dispdt1.get("disp_phone", "")),
                "disp_email": normalize_email(dispdt1.get("disp_email", ""))
            }

        # Shipping Details (shipdtl)
        clean_shipdtl = None
        if shipdtl:
            raw_ship_gstin = normalize_ship_gstin(shipdtl.get("ship_gstin", ""))
            if raw_ship_gstin and raw_ship_gstin != "URP" and len(raw_ship_gstin) != 15:
                audit_log.append({
                    "category": "INVALID_GSTIN_LENGTH",
                    "field": "shipdtl.ship_gstin",
                    "original": raw_ship_gstin,
                    "corrected": raw_ship_gstin,
                    "description": f"Customer input ship_gstin '{raw_ship_gstin}' has invalid length ({len(raw_ship_gstin)} chars, expected 15 or 'URP')."
                })
            ship_st = clean_state_code(shipdtl.get("ship_state", ""), audit_log=audit_log, field="shipdtl.ship_state")
            ship_pin_val = normalize_ship_pin(shipdtl.get("ship_pin", ""))
            if raw_ship_gstin and raw_ship_gstin != "URP" and len(raw_ship_gstin) >= 2 and raw_ship_gstin[:2].isdigit() and ship_st != raw_ship_gstin[:2]:
                is_port = (is_export or "PORT" in str(shipdtl.get("ship_lglnm", "")).upper() or "PORT" in str(shipdtl.get("ship_loc", "")).upper() or "TERMINAL" in str(shipdtl.get("ship_lglnm", "")).upper())
                pin_prefix = str(ship_pin_val)[:2] if ship_pin_val else ""
                # Check if pin matches ship_st
                pin_matches_st = (ship_st == "33" and pin_prefix in ("60", "61", "62", "63", "64")) or (ship_st == "27" and pin_prefix in ("40", "41", "42", "43", "44"))
                if is_port or pin_matches_st:
                    audit_log.append({
                        "category": "BUSINESS_RULE_AUTO_CORRECTION",
                        "field": "shipdtl.ship_gstin",
                        "original": raw_ship_gstin,
                        "corrected": "URP",
                        "description": f"Designated ship_gstin as 'URP' for port terminal facility in state {ship_st} (NIC Rule 2200 compliant)."
                    })
                    raw_ship_gstin = "URP"
                else:
                    audit_log.append({
                        "category": "BUSINESS_RULE_AUTO_CORRECTION",
                        "field": "shipdtl.ship_state",
                        "original": ship_st,
                        "corrected": raw_ship_gstin[:2],
                        "description": f"Synchronized shipping state code '{ship_st}' with first 2 digits of shipping GSTIN '{raw_ship_gstin[:2]}' (Rule 2200/2258)"
                    })
                    ship_st = raw_ship_gstin[:2]
            clean_shipdtl = {
                "ship_gstin": raw_ship_gstin,
                "ship_lglnm": normalize_ship_lglnm(shipdtl.get("ship_lglnm", "")),
                "ship_trdnm": normalize_ship_trdnm(shipdtl.get("ship_trdnm", "")),
                "ship_bno": normalize_ship_bno(shipdtl.get("ship_bno", "NAA")),
                "ship_bnm": normalize_ship_bnm(shipdtl.get("ship_bnm", "NAA")),
                "ship_flno": normalize_ship_flno(shipdtl.get("ship_flno", "NAA")),
                "ship_loc": normalize_ship_loc(shipdtl.get("ship_loc", "")),
                "ship_dst": normalize_ship_dst(shipdtl.get("ship_dst", "")),
                "ship_pin": normalize_ship_pin(shipdtl.get("ship_pin", "")),
                "ship_state": ship_st,
                "ship_phone": normalize_numeric_string(shipdtl.get("ship_phone", "")),
                "ship_email": normalize_email(shipdtl.get("ship_email", ""))
            }

        # Inter-State vs Intra-State determination
        # SEZ & Export are ALWAYS inter-state supplies (IGST only)
        is_intra = (sup_state == pos and igstonintra != "Y" and not is_export and not is_sez)

        # Rule 2173: ItemList maximum line-item limit & redundant granularity evaluation
        max_item_limit = int(raw_invoice.get("middleware_threshold") or 1000)
        is_middleware = bool(raw_invoice.get("is_middleware_restricted") or (raw_invoice.get("middleware_threshold") and int(raw_invoice.get("middleware_threshold")) < 1000))
        is_unsplit_bulk = bool(raw_invoice.get("is_cannot_split_bulk"))

        if len(itemdtls) > max_item_limit or is_middleware:
            consolidated_items, red_count, totals = aggregate_redundant_line_items(itemdtls) if aggregate_redundant_line_items else (itemdtls, 0, {})
            diag = classify_rule_2173_diagnostic(
                item_count=len(itemdtls),
                items=itemdtls,
                max_limit=1000,
                is_middleware_restricted=is_middleware,
                middleware_threshold=raw_invoice.get("middleware_threshold"),
                is_cannot_split_bulk=is_unsplit_bulk
            ) if classify_rule_2173_diagnostic else None

            if red_count > 0 and len(consolidated_items) <= max_item_limit:
                audit_log.append({
                    "category": "RULE_2173_ITEM_LIMIT_SUMMARIZATION",
                    "field": "itemdtls",
                    "original": f"{len(itemdtls)} items",
                    "corrected": f"{len(consolidated_items)} items",
                    "description": f"{diag['scenario_name']}: {diag['reason']} Aggregated {len(itemdtls)} line items into {len(consolidated_items)} summarized items sharing identical HsnCd, GstRt, and unit price. {diag['fix']}" if diag else "Aggregated redundant line items."
                })
                itemdtls = consolidated_items
            elif len(itemdtls) > max_item_limit:
                audit_log.append({
                    "category": "RULE_2173_ITEM_LIMIT_EXCEEDED",
                    "field": "itemdtls",
                    "original": f"{len(itemdtls)} items",
                    "corrected": f"Capped to {max_item_limit} items" if not is_unsplit_bulk else f"{len(itemdtls)} items",
                    "description": f"{diag['scenario_name']}: {diag['reason']} {diag['fix']}" if diag else f"Capped items to limit {max_item_limit}."
                })
                if not is_unsplit_bulk and raw_invoice.get("auto_cap_items", True):
                    itemdtls = itemdtls[:max_item_limit]

        # Line Items (itemdtls) with auto-math & tax allocation
        clean_itemdtls: List[Dict[str, Any]] = []
        total_assamt = Decimal("0.00")
        total_cgst = Decimal("0.00")
        total_sgst = Decimal("0.00")
        total_igst = Decimal("0.00")
        total_cess = Decimal("0.00")
        total_stcess = Decimal("0.00")
        total_cesnonad = Decimal("0.00")

        for idx, raw_item in enumerate(itemdtls, start=1):
            item = normalize_dict_keys_with_log(raw_item)[0] if isinstance(raw_item, dict) else raw_item
            prdnm = normalize_product_name(item.get("prdnm", f"ITEM_{idx}"))
            prddesc = normalize_product_name(item.get("prddesc", prdnm))
            isservc = normalize_uppercase(item.get("isservc", "N")) or "N"
            hsncd = normalize_numeric_string(item.get("hsncd", ""))
            orig_hsn = hsncd
            hsn_statutory_rate = None
            if lookup_hsn_code:
                # 1. Check if HSN is missing, incomplete (< 4 digits), or invalid length
                needs_lookup = not hsncd or len(hsncd) not in [4, 6, 8] or len(hsncd) < 4

                # Fast path: If HSN code exists in CBIC statutory master, skip heavy transformer cross-encoder reranker
                stat_meta = validate_hsn_statutory(hsncd) if (not needs_lookup and validate_hsn_statutory) else None
                if stat_meta is not None:
                    hsn_statutory_rate = Decimal(str(stat_meta.get("standard_rate", 18.0)))
                    matches = []
                else:
                    matches = lookup_hsn_code(prdnm, prddesc, hsn_prefix=hsncd if len(hsncd) in [2, 3, 4] else None, top_k=3)
                if matches:
                    best_m = matches[0]
                    official_hsn = best_m["hsn_code"]
                    conf_val = float(best_m.get("confidence_pct", 100.0))
                    # If HSN is incomplete or completely mismatching official tariff with high ML confidence (>= 75%)
                    if needs_lookup or (conf_val >= 75.0 and hsncd and not official_hsn.startswith(hsncd[:2]) and not hsncd.startswith(official_hsn[:2])):
                        # Auto-correct HSN only when customer provides taxable value input or confirms HSN decision
                        if taxable_value_input is not None or item.get("apply_hsn_correction") is True:
                            hsncd = official_hsn
                            hsn_statutory_rate = Decimal(str(best_m.get("gst_rate", 18.0)))
                        else:
                            # Do not silently auto-correct HSN; keep customer's original HSN code
                            hsncd = orig_hsn
                            hsn_statutory_rate = Decimal(str(best_m.get("gst_rate", 18.0)))
                        audit_log.append({
                            "category": "HSN_TARIFF_SCHEDULE_LOOKUP",
                            "field": f"itemdtls[{idx}].hsncd",
                            "original": orig_hsn or "(blank)",
                            "corrected": hsncd,
                            "description": f"⚠️ NIC Rule 2176 Violation: HSN code(s)-{orig_hsn or '(blank)'} is invalid. Wrong HSN code is being passed. Pl check the HSN code being passed and Cross-check the correctness of HSN code on e-invoice portal. Still, if you feel it is correct, then please send the details to the helpdesk for verification at e-invoice system side. Based on Statutory Tariff Master & ML HSN Intelligence, the correct official HSN is '{hsncd}' ({best_m.get('description', '')[:50]}...) with statutory {hsn_statutory_rate}% GST. Auto-corrected to ensure NIC IRN compliance."
                        })
                        audit_log.append({
                            "category": "WRONG_HSN_CODE_DETECTED",
                            "field": f"itemdtls[{idx}].hsncd",
                            "original": orig_hsn or "(blank)",
                            "corrected": hsncd,
                            "description": f"⚠️ NIC Rule 2176 Violation: HSN code(s)-{orig_hsn or '(blank)'} is invalid. Wrong HSN code is being passed. Pl check the HSN code being passed and Cross-check the correctness of HSN code on e-invoice portal. Still, if you feel it is correct, then please send the details to the helpdesk for verification at e-invoice system side. Based on Statutory Tariff Master & ML HSN Intelligence, the correct official HSN is '{hsncd}' ({best_m.get('description', '')[:50]}...) with statutory {hsn_statutory_rate}% GST. Auto-corrected to ensure NIC IRN compliance."
                        })
                        if best_m.get("is_blocked_17_5") == 1:
                            audit_log.append({
                                "category": "ITC_BLOCKED_SECTION_17_5",
                                "field": f"itemdtls[{idx}].hsncd",
                                "original": orig_hsn or "(blank)",
                                "corrected": hsncd,
                                "description": f"🚫 Section 17(5) Ineligible ITC Alert: Statutory HSN '{hsncd}' ({best_m.get('description', '')[:50]}...) has blocked Input Tax Credit. Reason: {best_m.get('blocked_17_5_reason', 'Section 17(5) Blocked ITC')}"
                            })
                    elif hsn_statutory_rate is None:
                        hsn_statutory_rate = Decimal(str(best_m.get("gst_rate", 18.0)))

            # Day 8: Rate Slab Check & Section 17(5) Rule Detection
            rate_slab_mismatch_rate = None
            declared_rate_candidate = None
            for g_k in ("gstrate", "gst_rate", "gst rate", "tax_rate", "gstrt", "gst_rt"):
                if g_k in item and item.get(g_k) is not None and str(item.get(g_k)).strip() != "":
                    try:
                        declared_rate_candidate = float(clean_decimal_str(item.get(g_k), 2))
                        break
                    except Exception:
                        pass
            if declared_rate_candidate is None:
                try:
                    r_ig = float(clean_decimal_str(item.get("igstrt", "0.00"), 2))
                    r_cg = float(clean_decimal_str(item.get("cgstrt", "0.00"), 2))
                    r_sg = float(clean_decimal_str(item.get("sgstrt", "0.00"), 2))
                    if r_ig > 0:
                        declared_rate_candidate = r_ig
                    elif r_cg + r_sg > 0:
                        declared_rate_candidate = r_cg + r_sg
                except Exception:
                    pass

            if rate_slab_checker and declared_rate_candidate is not None and hsncd:
                rate_slab_res = rate_slab_checker.check(declared_rate_candidate, hsncd)
                if rate_slab_res and rate_slab_res.get("flag") == "RATE_SLAB_MISMATCH":
                    stat_r = Decimal(str(rate_slab_res.get("statutory_rate", 18.0)))
                    rate_slab_mismatch_rate = stat_r
                    hsn_statutory_rate = stat_r
                    audit_log.append({
                        "category": "RATE_SLAB_MISMATCH",
                        "field": f"itemdtls[{idx}].gstrate",
                        "original": str(rate_slab_res.get("declared_rate")),
                        "corrected": str(stat_r),
                        "description": rate_slab_res.get("message", f"⚠️ Rate Slab Mismatch: Declared rate {rate_slab_res.get('declared_rate')}% does not match statutory rate {stat_r}% for HSN {hsncd}. Overriding with statutory rate.")
                    })

            # Section 17(5) text scan
            if section_17_5_detector:
                p_text = f"{prdnm} {prddesc}".strip()
                sec175_match = section_17_5_detector.scan(p_text, hsn=hsncd)
                if sec175_match and sec175_match.get("flag") == "ITC_BLOCKED_SECTION_17_5":
                    sub_clause = sec175_match.get("sub_clause", "17(5)")
                    full_tag = sec175_match.get("full_tag", f"ITC Blocked: CGST Act Section {sub_clause}")
                    matched_term = sec175_match.get("matched_term", "")
                    audit_log.append({
                        "category": "ITC_BLOCKED_SECTION_17_5",
                        "field": f"itemdtls[{idx}].prddesc",
                        "original": prddesc or prdnm,
                        "corrected": full_tag,
                        "description": f"🚫 {full_tag}: Ineligible for Input Tax Credit under CGST Act. Matched term: '{matched_term}'. Detected in product description for item '{prdnm}'."
                    })

            raw_uqc = str(item.get("uqc") or item.get("unit") or "NOS").strip()
            norm_uqc, diag_uqc = normalize_uqc_statutory(raw_uqc)
            if not diag_uqc["is_valid"]:
                audit_log.append({
                    "category": "UQC_MASTER_AUTO_ALIGNMENT",
                    "field": f"itemdtls[{idx}].uqc",
                    "original": raw_uqc,
                    "corrected": norm_uqc,
                    "description": f"Unit Quantity Code '{raw_uqc}' is not as per NIC master (Rule 2177). {diag_uqc['reason']} Auto-aligned to '{norm_uqc}'."
                })
            uqc = norm_uqc

            qty_d = Decimal(clean_decimal_str(item.get("qty", "1.000"), 3, audit_log=audit_log, field=f"itemdtls[{idx}].qty"))
            unitrate_d = Decimal(clean_decimal_str(item.get("unitrate", "0.00"), 2, audit_log=audit_log, field=f"itemdtls[{idx}].unitrate"))

            # Module 2: Qwen 2.5 Neural Verifier, ML HSN Gatekeeper & Counterfactual Self-Healing
            sentinel_audit = None
            if audit_and_rectify_line_item_sentinel:
                try:
                    decl_rt_raw = float(item.get("igstrt") or (float(item.get("cgstrt", 0)) + float(item.get("sgstrt", 0))) or item.get("gstrate", 0) or 0.0)
                    sentinel_audit = audit_and_rectify_line_item_sentinel(
                        product_name=prdnm,
                        product_desc=prddesc,
                        declared_hsn=hsncd,
                        unit_price=float(unitrate_d),
                        supplier_gstin=sup_gstin,
                        declared_rate=decl_rt_raw if decl_rt_raw > 0 else None
                    )
                except Exception as ex:
                    print(f"[WARN] Module 2 Sentinel error: {ex}")

            if sentinel_audit and sentinel_audit.get("should_rectify"):
                cf_hsn = str(sentinel_audit.get("rectified_hsn", "") or "").strip()
                is_same_heading = bool(orig_hsn and cf_hsn and len(orig_hsn) >= 4 and len(cf_hsn) >= 4 and orig_hsn[:4] == cf_hsn[:4])
                if cf_hsn and cf_hsn.lower() not in ("none", "nan") and cf_hsn.isdigit() and cf_hsn != orig_hsn and not is_same_heading:
                    cf_rate = Decimal(str(sentinel_audit.get("statutory_rate", 18.0)))
                    err_p = float(sentinel_audit.get("error_probability", 0.0))
                    post_p = float(sentinel_audit.get("post_intervention_risk", 0.0))
                    r_drop = float(sentinel_audit.get("risk_drop", 0.0))
                    r_level = str(sentinel_audit.get("risk_level", "HIGH"))
                    reasons_l = sentinel_audit.get("reasons", [])
                    reasons_txt = ", ".join(reasons_l) if isinstance(reasons_l, list) else str(reasons_l)

                    audit_log.append({
                        "category": "MODULE_2_SENTINEL_HSN_RECTIFICATION",
                        "field": f"itemdtls[{idx}].hsncd",
                        "original": orig_hsn or "(blank)",
                        "corrected": cf_hsn,
                        "description": (
                            f"🛡️ Module 2 HSN Sentinel Interception: Declared HSN '{orig_hsn}' flagged with P(Error) = {err_p:.1%} ({r_level} risk). "
                            f"SHAP Root Causes: {reasons_txt}. "
                            f"Auto-rectified to Counterfactual HSN '{cf_hsn}' (Post-Intervention P(Error) = {post_p:.1%}, -{r_drop:.1%} risk drop) "
                            f"with statutory {cf_rate}% GST before transmission to NIC portal."
                        )
                    })
                    hsncd = cf_hsn
                    hsn_statutory_rate = cf_rate

            calculated_gross = (qty_d * unitrate_d).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            raw_gross_str = item.get("grossamt", "")
            grossamt_str = clean_decimal_str(raw_gross_str, 2, audit_log=audit_log, field=f"itemdtls[{idx}].grossamt")
            grossamt_d = Decimal(grossamt_str)
            if abs(grossamt_d - calculated_gross) > Decimal("0.05"):
                audit_log.append({
                    "category": "TAX_MATH_RECALCULATION",
                    "field": f"itemdtls[{idx}].grossamt",
                    "original": raw_gross_str,
                    "corrected": str(calculated_gross),
                    "description": f"Recalculated Gross Amount as Qty ({qty_d}) * UnitRate ({unitrate_d}) (Rule 2192)"
                })
                grossamt_d = calculated_gross

            discount_d = Decimal(clean_decimal_str(item.get("discount", "0.00"), 2, audit_log=audit_log, field=f"itemdtls[{idx}].discount"))
            othchrg_d = Decimal(clean_decimal_str(item.get("othchrg", "0.00"), 2, audit_log=audit_log, field=f"itemdtls[{idx}].othchrg"))

            calculated_assamt = (grossamt_d - discount_d).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            raw_assamt_str = item.get("assamt", "")
            assamt_str = clean_decimal_str(raw_assamt_str, 2, audit_log=audit_log, field=f"itemdtls[{idx}].assamt")
            assamt_d = Decimal(assamt_str)
            if abs(assamt_d - calculated_assamt) > Decimal("0.05"):
                audit_log.append({
                    "category": "TAX_MATH_RECALCULATION",
                    "field": f"itemdtls[{idx}].assamt",
                    "original": raw_assamt_str,
                    "corrected": str(calculated_assamt),
                    "description": f"Recalculated Assessable Value as Gross ({grossamt_d}) - Discount ({discount_d}) (Rule 2193)"
                })
                assamt_d = calculated_assamt

            # User taxable value input option override
            override_assamt = None
            if taxable_value_input is not None:
                if isinstance(taxable_value_input, (int, float, Decimal, str)) and str(taxable_value_input).strip():
                    override_assamt = Decimal(clean_decimal_str(taxable_value_input, 2))
                elif isinstance(taxable_value_input, dict):
                    if idx in taxable_value_input or str(idx) in taxable_value_input:
                        v = taxable_value_input.get(idx, taxable_value_input.get(str(idx)))
                        override_assamt = Decimal(clean_decimal_str(v, 2))
                    elif "assval" in taxable_value_input or "assamt" in taxable_value_input:
                        override_assamt = Decimal(clean_decimal_str(taxable_value_input.get("assval", taxable_value_input.get("assamt")), 2))
            elif item.get("custom_taxable_value") or item.get("taxable_value_input"):
                v = item.get("custom_taxable_value") or item.get("taxable_value_input")
                override_assamt = Decimal(clean_decimal_str(v, 2))

            if override_assamt is not None and override_assamt > Decimal("0.00"):
                if abs(assamt_d - override_assamt) > Decimal("0.01"):
                    audit_log.append({
                        "category": "TAXABLE_VALUE_MODIFICATION",
                        "field": f"itemdtls[{idx}].assamt",
                        "original": str(assamt_d),
                        "corrected": str(override_assamt),
                        "description": f"Applied user-provided taxable value input option Rs {override_assamt} and recalculated statutory taxes."
                    })
                assamt_d = override_assamt
                grossamt_d = (assamt_d + discount_d).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                if qty_d > Decimal("0.00"):
                    unitrate_d = (grossamt_d / qty_d).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            taxability = clean_str(item.get("taxability", "TAX")).upper() or "TAX"

            # Prioritize explicit customer-declared gstrate / gst_rate first!
            declared_gstrate = None
            for g_k in ("gstrate", "gst_rate", "gst rate", "tax_rate", "gstrt", "gst_rt"):
                if g_k in item and item.get(g_k) is not None and str(item.get(g_k)).strip() != "":
                    try:
                        declared_gstrate = Decimal(clean_decimal_str(item.get(g_k), 2))
                        break
                    except Exception:
                        pass

            raw_igstrt = Decimal(clean_decimal_str(item.get("igstrt", "0.00"), 2))
            raw_cgstrt = Decimal(clean_decimal_str(item.get("cgstrt", "0.00"), 2))
            raw_sgstrt = Decimal(clean_decimal_str(item.get("sgstrt", "0.00"), 2))

            if sentinel_audit and sentinel_audit.get("should_rectify") and hsn_statutory_rate is not None:
                gst_rate = hsn_statutory_rate
            elif rate_slab_mismatch_rate is not None:
                # Override gst_rate with statutory_rate (fix the silent wrong rate bug)
                gst_rate = rate_slab_mismatch_rate
            elif declared_gstrate is not None:
                gst_rate = declared_gstrate
            elif raw_igstrt > 0:
                gst_rate = raw_igstrt
            elif raw_cgstrt + raw_sgstrt > 0:
                gst_rate = raw_cgstrt + raw_sgstrt
            elif hsn_statutory_rate is not None:
                gst_rate = hsn_statutory_rate
            else:
                gst_rate = Decimal("0.00")

            cessrt_d = Decimal(clean_decimal_str(item.get("cessrt", "0.00"), 2))
            cessamt_d = Decimal(clean_decimal_str(item.get("cessamt", "0.00"), 2))
            cessnonadval_d = Decimal(clean_decimal_str(item.get("cessnonadval", "0.00"), 2))
            statecessrt_d = Decimal(clean_decimal_str(item.get("statecessrt", "0.00"), 2))
            statecessamt_d = Decimal(clean_decimal_str(item.get("statecessamt", "0.00"), 2))

            # Tax Allocation
            raw_item_igst = Decimal(clean_decimal_str(item.get("igstamt", item.get("igstval", "0.00")), 2))
            raw_item_cgst = Decimal(clean_decimal_str(item.get("cgstamt", item.get("cgstval", "0.00")), 2))
            raw_item_sgst = Decimal(clean_decimal_str(item.get("sgstamt", item.get("sgstval", "0.00")), 2))

            if is_intra:
                if raw_item_igst > Decimal("0.00") and raw_item_cgst == Decimal("0.00") and raw_item_sgst == Decimal("0.00"):
                    audit_log.append({
                        "category": "TAX_ALLOCATION_AUTO_CORRECTION",
                        "field": f"itemdtls[{idx}].igstamt",
                        "original": str(raw_item_igst),
                        "corrected": "0.00",
                        "description": "Same supplier state and POS means regular intra-state supply. Clear IgstAmt and split tax equally between CGST and SGST."
                    })
                cgstrt_d = (gst_rate / Decimal("2")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                sgstrt_d = cgstrt_d
                igstrt_d = Decimal("0.00")
                cgstamt_d = (assamt_d * cgstrt_d / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                sgstamt_d = cgstamt_d
                igstamt_d = Decimal("0.00")
            else:
                if raw_item_cgst > Decimal("0.00") or raw_item_sgst > Decimal("0.00"):
                    audit_log.append({
                        "category": "TAX_ALLOCATION_AUTO_CORRECTION",
                        "field": f"itemdtls[{idx}].cgstamt",
                        "original": f"CGST: {raw_item_cgst}, SGST: {raw_item_sgst}",
                        "corrected": f"IGST: {(assamt_d * gst_rate / Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}",
                        "description": "Supplier and POS states are different, so it is an inter-state sale. Clear CGST/SGST to 0.00 and pass the full tax rate under IgstAmt (Rule 2174)."
                    })
                igstrt_d = gst_rate
                cgstrt_d = Decimal("0.00")
                sgstrt_d = Decimal("0.00")
                igstamt_d = (assamt_d * igstrt_d / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                cgstamt_d = Decimal("0.00")
                sgstamt_d = Decimal("0.00")

            calculated_totitemval = (
                assamt_d + cgstamt_d + sgstamt_d + igstamt_d +
                cessamt_d + statecessamt_d + cessnonadval_d + othchrg_d
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            raw_totitemval = item.get("totitemval", "")
            if raw_totitemval:
                curr_totval_d = Decimal(clean_decimal_str(raw_totitemval, 2, audit_log=audit_log, field=f"itemdtls[{idx}].totitemval"))
                if abs(curr_totval_d - calculated_totitemval) > Decimal("0.05"):
                    audit_log.append({
                        "category": "TAX_MATH_RECALCULATION",
                        "field": f"itemdtls[{idx}].totitemval",
                        "original": raw_totitemval,
                        "corrected": str(calculated_totitemval),
                        "description": "Recalculated Total Item Value to match sum of assessable value and all taxes (Rule 2194)"
                    })

            total_assamt += assamt_d
            total_cgst += cgstamt_d
            total_sgst += sgstamt_d
            total_igst += igstamt_d
            total_cess += cessamt_d
            total_stcess += statecessamt_d
            total_cesnonad += cessnonadval_d

            clean_itemdtls.append({
                "prdnm": prdnm,
                "prddesc": prddesc,
                "isservc": isservc,
                "hsncd": hsncd,
                "qty": str(qty_d),
                "uqc": uqc,
                "unitrate": str(unitrate_d),
                "grossamt": str(grossamt_d),
                "discount": str(discount_d) if discount_d > 0 else "",
                "othchrg": str(othchrg_d) if othchrg_d > 0 else "",
                "assamt": str(assamt_d),
                "taxability": taxability,
                "gstrate": str(gst_rate),
                "cgstrt": str(cgstrt_d),
                "cgstamt": str(cgstamt_d),
                "sgstrt": str(sgstrt_d),
                "sgstamt": str(sgstamt_d),
                "igstrt": str(igstrt_d),
                "igstamt": str(igstamt_d),
                "cessrt": str(cessrt_d),
                "cessamt": str(cessamt_d),
                "cessnonadval": str(cessnonadval_d) if cessnonadval_d > 0 else "",
                "statecessrt": str(statecessrt_d),
                "statecessamt": str(statecessamt_d),
                "totitemval": str(calculated_totitemval),
                "sentinel_audit": sentinel_audit or {
                    "is_flagged": False,
                    "should_rectify": False,
                    "original_hsn": orig_hsn,
                    "rectified_hsn": hsncd,
                    "error_probability": 0.0,
                    "post_intervention_risk": 0.0,
                    "risk_drop": 0.0,
                    "risk_level": "LOW",
                    "status_badge": "AUTO_APPROVED",
                    "reasons": []
                }
            })

        # AI Price & Unit Rate Anomaly Detection Scan
        if PriceAnomalyDetector:
            try:
                anomaly_report = PriceAnomalyDetector.scan_invoice_payload({"itemdtls": clean_itemdtls})
                if anomaly_report.get("has_anomalies"):
                    for anom in anomaly_report.get("findings", []):
                        if anom.get("is_anomaly"):
                            audit_log.append({
                                "category": "PRICE_UNIT_RATE_ANOMALY",
                                "field": f"itemdtls[{anom['item_index']}].unitrate",
                                "original": str(anom['unitrate']),
                                "corrected": str(anom.get('suggested_rate') or anom['unitrate']),
                                "severity": anom.get("severity", "MEDIUM"),
                                "anomaly_type": anom.get("anomaly_type"),
                                "risk_score": anom.get("risk_score", 0),
                                "description": anom.get("reason", "Unit rate anomaly detected against statutory benchmark.")
                            })
            except Exception:
                pass

        # Value Summary (valdt1) Reconciliation
        inv_disc = Decimal(clean_decimal_str(valdt1.get("discval", "0.00"), 2))
        inv_othchrg = Decimal(clean_decimal_str(valdt1.get("othchrg", "0.00"), 2))

        calculated_totinvval = (
            total_assamt + total_cgst + total_sgst + total_igst +
            total_cess + total_stcess + total_cesnonad + inv_othchrg - inv_disc
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        raw_totinvval = valdt1.get("totinvval", "")
        if raw_totinvval:
            curr_totinv_d = Decimal(clean_decimal_str(raw_totinvval, 2, audit_log=audit_log, field="valdt1.totinvval"))
            if abs(curr_totinv_d - calculated_totinvval) > Decimal("0.05"):
                audit_log.append({
                    "category": "INVOICE_TOTALS_RECONCILIATION",
                    "field": "valdt1.totinvval",
                    "original": raw_totinvval,
                    "corrected": str(calculated_totinvval),
                    "description": "Reconciled Total Invoice Value with sum of items, taxes, other charges minus discounts (Rule 2189)"
                })

        # Scenario 4: Summary vs. Item Level Mismatch
        raw_igstval_str = valdt1.get("igstval") or valdt1.get("igstamt") or ""
        if raw_igstval_str:
            curr_igst_d = Decimal(clean_decimal_str(raw_igstval_str, 2))
            if curr_igst_d > Decimal("0.00") and total_igst == Decimal("0.00") and (total_cgst > 0 or total_sgst > 0):
                audit_log.append({
                    "category": "INVOICE_TOTALS_RECONCILIATION",
                    "field": "valdt1.igstval",
                    "original": raw_igstval_str,
                    "corrected": "0.00",
                    "description": "Header total tax values in ValDtls must match the sum of item-level taxes in ItemList."
                })

        # Scenario 3: Header Summary vs. Line Items Mismatch (Rule 2174)
        raw_cgstval_str = valdt1.get("cgstval") or valdt1.get("cgstamt") or ""
        raw_sgstval_str = valdt1.get("sgstval") or valdt1.get("sgstamt") or ""
        if raw_cgstval_str or raw_sgstval_str:
            curr_cgst_d = Decimal(clean_decimal_str(raw_cgstval_str or "0.00", 2))
            curr_sgst_d = Decimal(clean_decimal_str(raw_sgstval_str or "0.00", 2))
            if (curr_cgst_d > Decimal("0.00") or curr_sgst_d > Decimal("0.00")) and total_igst > Decimal("0.00") and total_cgst == Decimal("0.00") and total_sgst == Decimal("0.00"):
                audit_log.append({
                    "category": "INVOICE_TOTALS_RECONCILIATION",
                    "field": "valdt1.cgstval",
                    "original": f"CGST: {raw_cgstval_str}, SGST: {raw_sgstval_str}",
                    "corrected": "0.00",
                    "description": "Header totals in ValDtls must mirror line-item taxes. If line items carry IGST, CgstVal and SgstVal in ValDtls must be 0.00 (Rule 2174)."
                })

        clean_valdt1 = {
            "assamt": str(total_assamt),
            "ttlassval": str(total_assamt),
            "cgstamt": str(total_cgst),
            "sgstamt": str(total_sgst),
            "igstamt": str(total_igst),
            "cessamt": str(total_cess),
            "statecessamt": str(total_stcess),
            "cesnonadval": str(total_cesnonad),
            "totdisc": str(inv_disc) if inv_disc > 0 else "0.00",
            "totinvval": str(calculated_totinvval),
            "othchrg": str(inv_othchrg) if inv_othchrg > 0 else "0.00"
        }

        # E-Way Bill Details (ewbdt1)
        ewayreq = clean_str(ewbdt1.get("ewayreq", "N")).upper() or "N"
        raw_trans_id = clean_gstin(ewbdt1.get("transporter_id", ""))
        if raw_trans_id and len(raw_trans_id) != 15:
            audit_log.append({
                "category": "INVALID_TRANSPORTER_ID_LENGTH",
                "field": "ewbdt1.transporter_id",
                "original": raw_trans_id,
                "corrected": raw_trans_id,
                "description": f"Customer input transporter_id '{raw_trans_id}' has invalid length ({len(raw_trans_id)} chars, expected 15)."
            })
        clean_ewbdt1 = {
            "ewayreq": ewayreq,
            "subsupplytype": clean_str(ewbdt1.get("subsupplytype", "")),
            "distance_of_transport": clean_int_str(ewbdt1.get("distance_of_transport", "")),
            "transporter_id": raw_trans_id,
            "transporter_name": clean_str(ewbdt1.get("transporter_name", "")),
            "mode_of_transport": clean_str(ewbdt1.get("mode_of_transport") or ewbdt1.get("transmode") or data.get("mode_of_transport") or data.get("transmode") or ""),
            "transport_doc_no": clean_str(ewbdt1.get("transport_doc_no", "")).upper(),
            "transporter_doc_date": normalize_date_to_standard(ewbdt1.get("transporter_doc_date", ""), audit_log=audit_log, field="ewbdt1.transporter_doc_date"),
            "veh_type": clean_str(ewbdt1.get("veh_type", "")).upper(),
            "veh_number": clean_str(ewbdt1.get("veh_number", "")).upper().replace(" ", "").replace("-", "")
        }

        # Assemble Standard Output Structure
        # Align transporter_doc_date if earlier than invoice date (NIC Rule 4021)
        raw_trans_dt = clean_ewbdt1.get("transporter_doc_date", "")
        if raw_trans_dt and clean_docdt1.get("docdt"):
            try:
                t_dt = datetime.strptime(raw_trans_dt, "%d-%m-%Y").date()
                i_dt = datetime.strptime(clean_docdt1["docdt"], "%d-%m-%Y").date()
                if t_dt < i_dt:
                    audit_log.append({
                        "category": "NIC_RULE_4021_DATE_ALIGNMENT",
                        "field": "ewbdt1.transporter_doc_date",
                        "original": raw_trans_dt,
                        "corrected": clean_docdt1["docdt"],
                        "description": f"NIC Rule 4021: Aligned transporter document date '{raw_trans_dt}' to invoice date '{clean_docdt1['docdt']}'"
                    })
                    clean_ewbdt1["transporter_doc_date"] = clean_docdt1["docdt"]
            except Exception:
                pass

        # Rule 4009: E-Way bill requires at least one goods item
        if clean_ewbdt1.get("ewayreq") == "Y":
            has_goods = any(
                str(it.get("isservc", "N")).upper() != "Y" and not str(it.get("hsncd", "")).startswith("99")
                for it in clean_itemdtls
            )
            if not has_goods:
                audit_log.append({
                    "category": "NIC_RULE_4009_EWB_SERVICES",
                    "field": "ewbdt1.ewayreq",
                    "original": "Y",
                    "corrected": "N",
                    "description": "Auto-disabled ewayreq ('Y' -> 'N'): E-Way Bill cannot be generated for pure service supplies (NIC Rule 4009)."
                })
                clean_ewbdt1["ewayreq"] = "N"

        out_invoice: Dict[str, Any] = OrderedDict()
        if is_sez or is_sez_buyer_flag or data.get("is_sez_buyer"):
            out_invoice["buyer_is_sez"] = True
            out_invoice["is_sez_buyer"] = True
        out_invoice["self_gstin"] = self_gstin
        out_invoice["system_cd"] = system_cd
        out_invoice["branch_cd"] = branch_cd
        out_invoice["vertical_cd"] = vertical_cd
        out_invoice["irnreq"] = irnreq
        out_invoice["trandt1"] = {
            "trancatg": trancatg,
            "reversecharge": reversecharge,
            "transactionmode": transactionmode,
            "igstonintra": igstonintra
        }
        out_invoice["reversecharge"] = reversecharge
        if clean_expdt1:
            out_invoice["expdt1"] = clean_expdt1
        out_invoice["docdt1"] = clean_docdt1
        out_invoice["docdt"] = clean_docdt1["docdt"]
        out_invoice["supplierdt1"] = clean_supplierdt1
        out_invoice["buyerdt1"] = clean_buyerdt1
        if clean_dispdt1:
            out_invoice["dispdt1"] = clean_dispdt1
        if clean_shipdtl:
            out_invoice["shipdtl"] = clean_shipdtl
        out_invoice["itemdtls"] = clean_itemdtls
        out_invoice["valdt1"] = clean_valdt1
        out_invoice["ewbdt1"] = clean_ewbdt1

        return out_invoice, audit_log

    @classmethod
    def convert_payload_document_with_audit(cls, input_data: Any, taxable_value_input: Optional[Union[float, Decimal, Dict[str, Any]]] = None) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Converts full payload document and returns (corrected_payload, audit_reports).
        Supports optional taxable_value_input override.
        """
        if isinstance(input_data, dict):
            if taxable_value_input is None:
                taxable_value_input = input_data.get("taxable_value_input") or input_data.get("custom_taxable_value")
            raw_invoices = input_data.get("einvoices", [input_data]) if "einvoices" in input_data else [input_data]
        elif isinstance(input_data, list):
            raw_invoices = input_data
        else:
            raise ValueError("Invalid payload root. Expected dict or list.")

        corrected_invoices = []
        audit_reports = []

        for idx, inv in enumerate(raw_invoices, start=1):
            clean_inv, audit_log = cls.auto_correct_and_build(inv, taxable_value_input=taxable_value_input)
            corrected_invoices.append(clean_inv)
            docno = clean_inv.get("docdt1", {}).get("docno", f"INV_INDEX_{idx}")
            audit_reports.append({
                "invoice_number": docno,
                "corrections_count": len(audit_log),
                "corrections": audit_log
            })

        return {"einvoices": corrected_invoices}, audit_reports

    @classmethod
    def convert_payload_document(cls, input_data: Any) -> Dict[str, Any]:
        """Backward-compatible wrapper returning only corrected payload."""
        return cls.convert_payload_document_with_audit(input_data)[0]

    # Aliases
    build_payload = auto_correct_and_build


if __name__ == "__main__":
    import os
    if os.path.exists("rescuepe.log"):
        process_payload("rescuepe.log", "valid.json", "error.json")
