"""
Rules Engine & NIC Pre-API Validation Engine for Indian GST E-Invoice & E-Way Bill Payloads.
Combines comprehensive master definitions, NIC Error Code Mappings (IRN 2143-9999 & EWB 4000-4076),
and full statutory validation rules into a single high-performance rules engine.
"""

import re
from datetime import datetime, date
from decimal import Decimal
from typing import Dict, Any, List, Optional, Set, Union

try:
    from src.ingestion.schemas import (
        get_reverse_charge_rejection_reason,
        get_ist_today,
        classify_future_date_diagnostic,
        classify_rule_2172_diagnostic,
        classify_rule_2173_diagnostic,
        classify_rule_2174_diagnostic,
        validate_hsn_statutory,
        classify_rule_2176_diagnostic,
        classify_rule_2177_diagnostic,
        classify_rule_2182_diagnostic,
        classify_rule_2183_diagnostic,
        classify_rule_2184_diagnostic,
        classify_rule_2185_diagnostic,
        classify_rule_2186_diagnostic,
        classify_rule_2187_diagnostic,
        classify_rule_2189_diagnostic,
        classify_rule_2192_diagnostic,
        classify_rule_2193_diagnostic,
        classify_rule_2194_diagnostic,
        classify_rule_2200_diagnostic,
        classify_rule_2201_diagnostic,
        classify_rule_2202_diagnostic,
        classify_rule_2203_diagnostic,
        classify_rule_2211_diagnostic,
        classify_rule_2212_diagnostic,
        classify_rule_2213_diagnostic,
        classify_rule_2227_diagnostic,
        classify_rule_2228_diagnostic,
        classify_rule_2230_diagnostic,
        classify_rule_2231_diagnostic,
        classify_rule_2232_diagnostic,
        classify_rule_2233_diagnostic,
        classify_rule_2234_diagnostic,
        classify_rule_2235_diagnostic,
        classify_rule_2238_diagnostic,
        classify_rule_2239_diagnostic,
        classify_rule_2240_diagnostic,
        classify_rule_2242_diagnostic,
        classify_rule_2243_diagnostic,
        classify_rule_2244_diagnostic,
        classify_rule_2246_diagnostic,
        classify_rule_2247_diagnostic,
        classify_rule_2248_diagnostic,
        classify_rule_2255_diagnostic,
        classify_rule_2258_diagnostic,
        classify_rule_2259_diagnostic,
        classify_rule_2260_diagnostic,
        classify_rule_2261_diagnostic,
        classify_rule_2262_diagnostic,
        classify_rule_2265_diagnostic,
        classify_rule_2266_diagnostic,
        classify_rule_2267_diagnostic,
        classify_rule_2268_diagnostic,
        classify_rule_2269_diagnostic,
        classify_rule_2270_diagnostic,
        classify_rule_2271_diagnostic,
        classify_rule_2272_diagnostic,
        classify_rule_2273_diagnostic,
        classify_rule_2274_diagnostic,
        classify_rule_2275_diagnostic,
        classify_rule_2276_diagnostic,
        classify_rule_2278_diagnostic,
        KNOWN_SEZ_BUYER_GSTINS,
        E_INVOICE_EXEMPT_ENTITIES,
        normalize_uqc_statutory,
        OFFICIAL_UQC_MASTER,
        COMMON_UQC_MAPPING,
    )
except ImportError:
    try:
        from schemas import (
            get_reverse_charge_rejection_reason,
            get_ist_today,
            classify_future_date_diagnostic,
            classify_rule_2172_diagnostic,
            classify_rule_2173_diagnostic,
            classify_rule_2174_diagnostic,
            validate_hsn_statutory,
            classify_rule_2176_diagnostic,
            classify_rule_2177_diagnostic,
            classify_rule_2182_diagnostic,
            classify_rule_2183_diagnostic,
            classify_rule_2184_diagnostic,
            classify_rule_2185_diagnostic,
            classify_rule_2186_diagnostic,
            classify_rule_2187_diagnostic,
            classify_rule_2189_diagnostic,
            classify_rule_2192_diagnostic,
            classify_rule_2193_diagnostic,
            classify_rule_2194_diagnostic,
            classify_rule_2200_diagnostic,
            classify_rule_2201_diagnostic,
            classify_rule_2202_diagnostic,
            classify_rule_2203_diagnostic,
            classify_rule_2211_diagnostic,
            classify_rule_2212_diagnostic,
            classify_rule_2213_diagnostic,
            classify_rule_2227_diagnostic,
            classify_rule_2228_diagnostic,
            classify_rule_2230_diagnostic,
            classify_rule_2231_diagnostic,
            classify_rule_2232_diagnostic,
            classify_rule_2233_diagnostic,
            classify_rule_2234_diagnostic,
            classify_rule_2235_diagnostic,
            classify_rule_2238_diagnostic,
            classify_rule_2239_diagnostic,
            classify_rule_2240_diagnostic,
            classify_rule_2242_diagnostic,
            classify_rule_2243_diagnostic,
            classify_rule_2244_diagnostic,
            classify_rule_2246_diagnostic,
            classify_rule_2247_diagnostic,
            classify_rule_2248_diagnostic,
            classify_rule_2255_diagnostic,
            classify_rule_2258_diagnostic,
            classify_rule_2259_diagnostic,
            classify_rule_2260_diagnostic,
            classify_rule_2261_diagnostic,
            classify_rule_2262_diagnostic,
            classify_rule_2265_diagnostic,
            classify_rule_2266_diagnostic,
            classify_rule_2267_diagnostic,
            classify_rule_2268_diagnostic,
            classify_rule_2269_diagnostic,
            classify_rule_2270_diagnostic,
            classify_rule_2271_diagnostic,
            classify_rule_2272_diagnostic,
            classify_rule_2273_diagnostic,
            classify_rule_2274_diagnostic,
            classify_rule_2275_diagnostic,
            classify_rule_2276_diagnostic,
            classify_rule_2278_diagnostic,
            KNOWN_SEZ_BUYER_GSTINS,
            E_INVOICE_EXEMPT_ENTITIES,
            normalize_uqc_statutory,
            OFFICIAL_UQC_MASTER,
            COMMON_UQC_MAPPING,
        )
    except ImportError:
        get_reverse_charge_rejection_reason = None
        get_ist_today = None
        classify_future_date_diagnostic = None
        classify_rule_2172_diagnostic = None
        classify_rule_2173_diagnostic = None
        classify_rule_2174_diagnostic = None
        validate_hsn_statutory = None
        classify_rule_2176_diagnostic = None
        classify_rule_2177_diagnostic = None
        classify_rule_2182_diagnostic = None
        classify_rule_2183_diagnostic = None
        classify_rule_2184_diagnostic = None
        classify_rule_2185_diagnostic = None
        classify_rule_2186_diagnostic = None
        classify_rule_2187_diagnostic = None
        classify_rule_2189_diagnostic = None
        classify_rule_2192_diagnostic = None
        classify_rule_2193_diagnostic = None
        classify_rule_2194_diagnostic = None
        classify_rule_2200_diagnostic = None
        classify_rule_2201_diagnostic = None
        classify_rule_2202_diagnostic = None
        classify_rule_2203_diagnostic = None
        classify_rule_2211_diagnostic = None
        classify_rule_2212_diagnostic = None
        classify_rule_2213_diagnostic = None
        classify_rule_2227_diagnostic = None
        classify_rule_2228_diagnostic = None
        classify_rule_2230_diagnostic = None
        classify_rule_2231_diagnostic = None
        classify_rule_2232_diagnostic = None
        classify_rule_2233_diagnostic = None
        classify_rule_2234_diagnostic = None
        classify_rule_2235_diagnostic = None
        classify_rule_2238_diagnostic = None
        classify_rule_2239_diagnostic = None
        classify_rule_2240_diagnostic = None
        classify_rule_2242_diagnostic = None
        classify_rule_2243_diagnostic = None
        classify_rule_2244_diagnostic = None
        classify_rule_2246_diagnostic = None
        classify_rule_2247_diagnostic = None
        classify_rule_2248_diagnostic = None
        classify_rule_2255_diagnostic = None
        classify_rule_2258_diagnostic = None
        classify_rule_2259_diagnostic = None
        classify_rule_2260_diagnostic = None
        classify_rule_2261_diagnostic = None
        classify_rule_2262_diagnostic = None
        classify_rule_2265_diagnostic = None
        classify_rule_2266_diagnostic = None
        classify_rule_2267_diagnostic = None
        classify_rule_2268_diagnostic = None
        classify_rule_2269_diagnostic = None
        classify_rule_2270_diagnostic = None
        classify_rule_2271_diagnostic = None
        classify_rule_2272_diagnostic = None
        classify_rule_2273_diagnostic = None
        classify_rule_2274_diagnostic = None
        classify_rule_2275_diagnostic = None
        classify_rule_2276_diagnostic = None
        classify_rule_2278_diagnostic = None
        KNOWN_SEZ_BUYER_GSTINS = set()
        E_INVOICE_EXEMPT_ENTITIES = {}
        normalize_uqc_statutory = None
        OFFICIAL_UQC_MASTER = {}
        COMMON_UQC_MAPPING = {}

# ============================================================================
# 1. STATE CODE MASTER & PINCODE PREFIX MAPPINGS
# ============================================================================

STATE_MASTER: Dict[str, Dict[str, Any]] = {
    "01": {"name": "Jammu & Kashmir", "pin_prefixes": ["18", "19"]},
    "02": {"name": "Himachal Pradesh", "pin_prefixes": ["17"]},
    "03": {"name": "Punjab", "pin_prefixes": ["14", "15"]},
    "04": {"name": "Chandigarh", "pin_prefixes": ["16"]},
    "05": {"name": "Uttarakhand", "pin_prefixes": ["24", "26"]},
    "06": {"name": "Haryana", "pin_prefixes": ["12", "13"]},
    "07": {"name": "Delhi", "pin_prefixes": ["11"]},
    "08": {"name": "Rajasthan", "pin_prefixes": ["30", "31", "32", "33", "34"]},
    "09": {"name": "Uttar Pradesh", "pin_prefixes": ["20", "21", "22", "23", "24", "25", "27", "28"]},
    "10": {"name": "Bihar", "pin_prefixes": ["80", "81", "82", "83", "84", "85"]},
    "11": {"name": "Sikkim", "pin_prefixes": ["73"]},
    "12": {"name": "Arunachal Pradesh", "pin_prefixes": ["79"]},
    "13": {"name": "Nagaland", "pin_prefixes": ["79"]},
    "14": {"name": "Manipur", "pin_prefixes": ["79"]},
    "15": {"name": "Mizoram", "pin_prefixes": ["79"]},
    "16": {"name": "Tripura", "pin_prefixes": ["79"]},
    "17": {"name": "Meghalaya", "pin_prefixes": ["79"]},
    "18": {"name": "Assam", "pin_prefixes": ["78"]},
    "19": {"name": "West Bengal", "pin_prefixes": ["70", "71", "72", "73", "74"]},
    "20": {"name": "Jharkhand", "pin_prefixes": ["81", "82", "83"]},
    "21": {"name": "Odisha", "pin_prefixes": ["75", "76", "77"]},
    "22": {"name": "Chhattisgarh", "pin_prefixes": ["49"]},
    "23": {"name": "Madhya Pradesh", "pin_prefixes": ["45", "46", "47", "48"]},
    "24": {"name": "Gujarat", "pin_prefixes": ["36", "37", "38", "39"]},
    "26": {"name": "Dadra & Nagar Haveli and Daman & Diu", "pin_prefixes": ["39"]},
    "27": {"name": "Maharashtra", "pin_prefixes": ["40", "41", "42", "43", "44"]},
    "28": {"name": "Andhra Pradesh (Old)", "pin_prefixes": ["51", "52", "53"]},
    "29": {"name": "Karnataka", "pin_prefixes": ["56", "57", "58", "59"]},
    "30": {"name": "Goa", "pin_prefixes": ["40"]},
    "31": {"name": "Lakshadweep", "pin_prefixes": ["68"]},
    "32": {"name": "Kerala", "pin_prefixes": ["67", "68", "69"]},
    "33": {"name": "Tamil Nadu", "pin_prefixes": ["60", "61", "62", "63", "64"]},
    "34": {"name": "Puducherry", "pin_prefixes": ["60"]},
    "35": {"name": "Andaman and Nicobar Islands", "pin_prefixes": ["74"]},
    "36": {"name": "Telangana", "pin_prefixes": ["50"]},
    "37": {"name": "Andhra Pradesh", "pin_prefixes": ["51", "52", "53"]},
    "38": {"name": "Ladakh", "pin_prefixes": ["19"]},
    "96": {"name": "Other Country", "pin_prefixes": ["99"]},
    "97": {"name": "Other Territory", "pin_prefixes": ["99"]}
}

VALID_STATE_CODES: Set[str] = set(STATE_MASTER.keys())


def verify_pincode_state(pincode: str, state_code: str) -> bool:
    """
    Validates whether a 6-digit postal PIN code belongs to the specified State code.
    Prevents cross-state PIN mismatches (e.g. 27 Maharashtra GSTIN with 641407 Tamil Nadu PIN).
    """
    if not pincode or not state_code:
        return True
    pin_clean = str(pincode).strip()
    st_clean = str(state_code).strip().zfill(2)

    # Export destination / other country uses 999999
    if st_clean in ("96", "97") or pin_clean == "999999":
        return True

    state_info = STATE_MASTER.get(st_clean)
    if not state_info:
        return False

    prefix = pin_clean[:2]
    return prefix in state_info["pin_prefixes"]


# ============================================================================
# 2. COUNTRY, CURRENCY & PORT CODE MASTERS
# ============================================================================

COUNTRY_MASTER: Dict[str, Dict[str, str]] = {
    "IN": {"name": "India", "currency": "INR"},
    "US": {"name": "United States", "currency": "USD"},
    "GB": {"name": "United Kingdom", "currency": "GBP"},
    "AE": {"name": "United Arab Emirates", "currency": "AED"},
    "SG": {"name": "Singapore", "currency": "SGD"},
    "DE": {"name": "Germany", "currency": "EUR"},
    "FR": {"name": "France", "currency": "EUR"},
    "IT": {"name": "Italy", "currency": "EUR"},
    "NL": {"name": "Netherlands", "currency": "EUR"},
    "CH": {"name": "Switzerland", "currency": "CHF"},
    "JP": {"name": "Japan", "currency": "JPY"},
    "AU": {"name": "Australia", "currency": "AUD"},
    "CA": {"name": "Canada", "currency": "CAD"},
    "CN": {"name": "China", "currency": "CNY"},
    "HK": {"name": "Hong Kong", "currency": "HKD"},
    "SA": {"name": "Saudi Arabia", "currency": "SAR"},
    "ZA": {"name": "South Africa", "currency": "ZAR"},
    "MY": {"name": "Malaysia", "currency": "MYR"},
    "TH": {"name": "Thailand", "currency": "THB"},
    "KR": {"name": "South Korea", "currency": "KRW"},
    "QA": {"name": "Qatar", "currency": "QAR"},
    "KW": {"name": "Kuwait", "currency": "KWD"},
    "OM": {"name": "Oman", "currency": "OMR"},
    "VN": {"name": "Vietnam", "currency": "VND"},
    "ID": {"name": "Indonesia", "currency": "IDR"}
}

COUNTRY_CURRENCY_MAP: Dict[str, str] = {code: data["currency"] for code, data in COUNTRY_MASTER.items()}
VALID_CURRENCIES: Set[str] = {data["currency"] for data in COUNTRY_MASTER.values()} | {"USD", "EUR", "GBP", "INR"}

MAJOR_INDIAN_PORTS: Set[str] = {
    "INMAA1",  # Chennai Sea Port
    "INNSA1",  # Nhava Sheva / JNPT
    "INBOM1",  # Mumbai Sea Port
    "INMUN1",  # Mundra Sea Port
    "INTUT1",  # Tuticorin Sea Port
    "INCCU1",  # Kolkata Sea Port
    "INCOK1",  # Cochin Sea Port
    "INIXY1",  # Kandla Sea Port
    "INBLR4",  # Bengaluru Air Cargo
    "INDEL4",  # Delhi Air Cargo
    "INBOM4",  # Mumbai Air Cargo
    "INMAA4",  # Chennai Air Cargo
    "INHYD4",  # Hyderabad Air Cargo
    "INCCU4",  # Kolkata Air Cargo
    "INAMD4",  # Ahmedabad Air Cargo
}

# ============================================================================
# 3. UQC & CLASSIFICATION MASTERS
# ============================================================================

ALLOWED_UQC: List[str] = [
    "BAG", "BAL", "BDL", "BKL", "BOU", "BOX", "BTL", "BUN", "CAN", "CBM",
    "CCM", "CMS", "CTN", "DOZ", "DRM", "GGR", "GMS", "GRS", "GYD", "KGS", "KLR",
    "KME", "MLT", "MTR", "MTS", "NOS", "PAC", "PCS", "PRS", "QTL", "ROL",
    "SET", "SQF", "SQM", "SQY", "TBS", "TGM", "THD", "TON", "TUB", "UGS",
    "UNT", "YDS", "OTH"
]

ALLOWED_TAX_RATES: List[float] = [0.0, 0.1, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 6.0, 7.5, 12.0, 18.0, 28.0]
ALLOWED_DOC_TYPES: List[str] = ["INV", "CRN", "DBN", "CHL", "BIL", "OTH"]

ALLOWED_TRAN_CATG: List[str] = [
    "B2B",     # Regular Business to Business
    "SEZWP",   # SEZ with payment of tax
    "SEZWOP",  # SEZ without payment of tax
    "EXP",     # Direct Export
    "EXPWP",   # Export with payment of tax
    "EXPWOP",  # Export without payment of tax
    "DEXP",    # Deemed Export
    "B2G",     # Business to Government
    "B2C"      # Business to Consumer
]

ALLOWED_EXP_CAT: List[str] = ["DIR", "DEM", "SEZ", "SED"]
ALLOWED_TRANS_MODE: List[str] = ["REG", "DIS", "SHP", "CMB"]
ALLOWED_TAXABILITY: List[str] = ["TAX", "EXM", "NIL", "NGT"]
VALID_SUB_SUPPLY_TYPES: List[str] = [str(i) for i in range(1, 13)]
VALID_TRANSPORT_MODES: List[str] = ["1", "2", "3", "4"]  # 1: Road, 2: Rail, 3: Air, 4: Ship
ALLOWED_VEH_TYPES: List[str] = ["R", "O"]

# ============================================================================
# 4. NIC IRN ERROR CATALOG (Codes 2143 to 9999)
# ============================================================================

IRN_ERRORS: Dict[int, Dict[str, str]] = {
    2143: {
        "message": "Invoice does not belongs to the user GSTIN",
        "reason": "User is attempting to perform operations on IRN which does not belong to logged in GSTIN",
        "resolution": "Certain operations cannot be carried out on other's IRNs such as cancel etc."
    },
    2146: {
        "message": "Unable to create IRN, Pls. try after some time",
        "reason": "Due to unexpected scenario, IRN could not be generated at the moment",
        "resolution": "Please try after some time or contact helpdesk"
    },
    2147: {
        "message": "Unable to sign invoice, Pl try after some time",
        "reason": "Some unexpected error has occurred while signing the Invoice",
        "resolution": "Please try after some time or contact helpdesk"
    },
    2148: {
        "message": "Requested IRN data is not available",
        "reason": "User is trying to do operation on an IRN not available in eInvoice system",
        "resolution": "Check whether IRN is correct or carried out within permitted time"
    },
    2150: {
        "message": "Duplicate IRN",
        "reason": "Attempting to register a document again which is already registered",
        "resolution": "Check in your ERP whether IRN was already generated for this docno."
    },
    2154: {
        "message": "IRN details are not found",
        "reason": "Document not found in eInvoice system",
        "resolution": "Verify document number and generation timestamp"
    },
    2159: {
        "message": "Invalid value for reverse charge applicable field",
        "reason": "Reverse charge must be 'Y' or 'N'",
        "resolution": "Send either 'Y' or 'N' for reversecharge"
    },
    2162: {
        "message": "Reverse Charge is not applicable for this transaction",
        "reason": "Trying to set Reverse Charges applicable for transactions other than B2B",
        "resolution": "Reverse charge can only be 'Y' for B2B transactions"
    },
    2163: {
        "message": "The document date should not be future date.",
        "reason": "Document date exceeds current server calendar day in IST (Rule 2163)",
        "resolution": "Set document date to today's date or earlier, ensure ERP date logic runs in IST (Asia/Kolkata), and parse strictly as DD/MM/YYYY."
    },
    2164: {
        "message": "Document date is older than 2 days from current date. IRN cannot be generated or changed.",
        "reason": "NIC Rule: IRN generation/modification is restricted if document date is older than 2 days from current date",
        "resolution": "Please change the document date to within 2 days of current date (Prompt: change the date)"
    },
    2169: {
        "message": "Request for IRN is neither from supplier GSTIN or e-Commerce GSTIN",
        "reason": "Logged in user GSTIN does not match supplier or e-commerce GSTIN",
        "resolution": "Ensure request GSTIN matches supplier_gstin or ecom_gstin"
    },
    2172: {
        "message": "For Intra-state transaction, IGST amount is not applicable; only CGST and SGST amounts are applicable",
        "reason": "IGST amount passed for Intra State transaction without IGST_on_IntraState flag",
        "resolution": "Set CGST and SGST for intra-state, or set igstonintra='Y' if eligible"
    },
    2173: {
        "message": "The number of objects passed in ItemList exceeds the maximum line-item limit supported by the API endpoint",
        "reason": "ItemList contains more items than the API threshold (standard maximum 1,000 items)",
        "resolution": "Cap ItemList at maximum 1,000 items, aggregate redundant line items sharing identical HsnCd, GstRt, and unit price, split into separate invoice chunks, or escalate non-splittable bulk invoices to NIC helpdesk"
    },
    2174: {
        "message": "For inter-state transaction, CGST and SGST amounts are not applicable; only IGST amount is applicable",
        "reason": "CGST and SGST taxes passed for inter-state transaction (supplier state != POS)",
        "resolution": "Supplier and POS states are different, so it is an inter-state sale. Clear CGST/SGST to 0.00 and pass the full tax rate under IgstAmt. For Bill-to/Ship-to transactions, retain POS as per Section 10(1)(b) of the IGST Act and apply IGST."
    },
    2176: {
        "message": "HSN code(s)-{0} is invalid",
        "reason": "Wrong HSN code is being passed",
        "resolution": "Pl check the HSN code being passed and Cross-check the correctness of HSN code on e-invoice portal. Still, if you feel it is correct, then please send the details to the helpdesk for verification at e-invoice system side."
    },
    2177: {
        "message": "Unit Quantity Code(s)-{0} is/are not as per master",
        "reason": "The value passed in the Unit field within an item object of ItemList does not match the official 3-character Unit Quantity Code (UQC) master list prescribed by the NIC / GSTN portal. The IRP does not accept colloquial, arbitrary, or ERP-specific abbreviations (e.g., 'KG', 'LITRE', 'PCS.', or 'NO'). If an item's unit is not explicitly on the master list, the fallback code OTH (Others) must be passed.",
        "resolution": "Use official 3-letter standard UQC (e.g. KGS, NOS, PCS, MTR, MTS, PAC, BDL) or fallback code OTH (Others) for unlisted units."
    },
    2182: {
        "message": "Taxable value of all items is not equal to total taxable value",
        "reason": "Sum of assamt across all items != ttlassval in valdt1",
        "resolution": "Reconcile sum(item.assamt) to equal valdt1.ttlassval"
    },
    2183: {
        "message": "SGST value of all items is not equal to total SGST Value",
        "reason": "Sum of sgstamt across all items != sgstval in valdt1",
        "resolution": "Reconcile sum(item.sgstamt) to equal valdt1.sgstval"
    },
    2184: {
        "message": "CGST value of all items must be equal to total CGST value",
        "reason": "Sum of cgstamt across all items != cgstval in valdt1",
        "resolution": "Reconcile sum(item.cgstamt) to equal valdt1.cgstval"
    },
    2185: {
        "message": "IGST value of all items must be equal to total IGST Value",
        "reason": "Sum of igstamt across all items != igstval in valdt1",
        "resolution": "Reconcile sum(item.igstamt) to equal valdt1.igstval"
    },
    2186: {
        "message": "Cess value of all items must be equal to total Cess Value",
        "reason": "Sum of cessamt across all items != cesval in valdt1",
        "resolution": "Reconcile sum(item.cessamt) to equal valdt1.cesval"
    },
    2187: {
        "message": "State Cess Value of all items must be equal to total State CessValue",
        "reason": "The total State Cess declared at the invoice header (ValDtls.StCesVal) does not exactly match the sum of individual State Cess amounts across all line items: ValDtls.StCesVal = sum(ItemList[i].StateCesAmt + ItemList[i].StateCesNonAdvlAmt). If State Cess is applicable (e.g., specific state levies or legacy flood cess items), the sum of ad-valorem and specific State Cess amounts across all line items must equal the header value. If not applicable, both must remain 0.00.",
        "resolution": "Reconcile sum(item.StateCesAmt + item.StateCesNonAdvlAmt) to equal ValDtls.StCesVal to 2 decimal places. Keep Central Cess (CesVal) separate from State Cess (StCesVal).",
        "scenarios": {
            "HEADER_NOT_RECALCULATED_AFTER_ITEM_EDITS": {
                "name": "Header Not Recalculated After Item Edits",
                "fix": "Dynamically aggregate item-level State Cess amounts into ValDtls.StCesVal."
            },
            "STATE_CESS_VS_CENTRAL_CESS_FIELD_CONFUSION": {
                "name": "State Cess vs Central Cess Field Confusion",
                "fix": "Keep Central Compensation Cess (CesVal) separate from State Cess (StCesVal)."
            },
            "SPECIFIC_NON_AD_VALOREM_STATE_CESS_OMITTED": {
                "name": "Specific (Non-Ad-Valorem) State Cess Omitted",
                "fix": "ValDtls.StCesVal must include both rate-based and quantity-based State Cess."
            },
            "DECIMAL_PAISE_TRUNCATION": {
                "name": "Decimal / Paise Truncation",
                "fix": "Header total must match the item-level sum to 2 decimal places."
            }
        }
    },
    2189: {
        "message": "Total Invoice Value is not matching with calculated value",
        "reason": "The final gross invoice value (ValDtls.TotInvVal) does not match the computed total of all item values and invoice-level adjustments within +/- 1.00 tolerance: ValDtls.TotInvVal = sum(ItemList[i].TotItemVal) + ValDtls.OthChrg - ValDtls.Discount + ValDtls.RndOffAmt (or AssVal + CgstVal + SgstVal + IgstVal + CesVal + StCesVal + OthChrg - Discount + RndOffAmt).",
        "resolution": "Ensure ValDtls.TotInvVal matches sum of items, taxes, and other charges minus discount plus round-off within +/- 1.00 tolerance. Do not duplicate item discounts at header.",
        "scenarios": {
            "ITEM_LEVEL_DISCOUNT_SUBTRACTED_AGAIN_AT_HEADER": {
                "name": "Item-Level Discount Subtracted Again at Header",
                "fix": "Set ValDtls.Discount to 0.00 if discounts are already factored into line-item AssAmt / TotItemVal."
            },
            "OTHER_CHARGES_LEFT_OUT_OF_TOTAL": {
                "name": "Other Charges (OthChrg) Left Out of Total",
                "fix": "Freight, packing, or handling charges added to ValDtls.OthChrg must be added to TotInvVal."
            },
            "ROUNDING_OFF_ARITHMETIC_INVERSION": {
                "name": "Rounding Off (RndOffAmt) Arithmetic Inversion",
                "fix": "If rounding down, RndOffAmt must be negative (e.g., -0.40). Positive sign implies addition."
            },
            "TOTAL_ITEM_VALUE_FORMULA_DISCREPANCY": {
                "name": "Total Item Value (TotItemVal) Formula Discrepancy",
                "fix": "TotItemVal for each line must equal AssAmt + Taxes + Cess + Item-level Other Charges."
            }
        }
    },
    2192: {
        "message": "TotAmt value should be equal to (Qty * UnitPrice) for HSN {0}",
        "reason": "grossamt != qty * unitrate",
        "resolution": "grossamt must equal round(qty * unitrate, 2)"
    },
    2193: {
        "message": "For Sl. No. {0}, Taxable Value (AssAmt) value is not equal to (TotAmt - Discount)",
        "reason": "assamt != grossamt - discount",
        "resolution": "assamt must equal round(grossamt - discount, 2)"
    },
    2194: {
        "message": "For Sl. No {0}, Total item value does not match with taxable and tax values of that item",
        "reason": "The total item value (TotItemVal) for a specific line item in ItemList does not match the sum of its assessable value, all applicable taxes, cess, and line-level other charges: TotItemVal = AssAmt + CgstAmt + SgstAmt + IgstAmt + CesAmt + CesNonAdvlAmt + StateCesAmt + StateCesNonAdvlAmt + OthChrg (allowed tolerance of +/- 1.00).",
        "resolution": "Ensure ItemList[i].TotItemVal equals AssAmt + CgstAmt + SgstAmt + IgstAmt + CesAmt + CesNonAdvlAmt + StateCesAmt + StateCesNonAdvlAmt + OthChrg within +/- 1.00. Check for omitted taxes, gross total used instead of net assessable amount, omitted line other charges, omitted cess, or excessive rounding.",
        "scenarios": {
            "TAX_LEFT_OUT_OF_ITEM_TOTAL": {
                "name": "Tax Left Out of Item Total",
                "fix": "TotItemVal is the post-tax gross item total. Tax values must be added to AssAmt."
            },
            "GROSS_TOTAL_USED_WHEN_DISCOUNT_EXISTS": {
                "name": "Gross Total (TotAmt) Used When Discount Exists",
                "fix": "TotItemVal must be derived from AssAmt (net of discount), not from the pre-discount TotAmt."
            },
            "LINE_LEVEL_OTHER_CHARGES_OMITTED": {
                "name": "Line-Level Other Charges (OthChrg) Omitted",
                "fix": "Any item-level packaging, handling, or other charges in OthChrg must be added into TotItemVal."
            },
            "CESS_AMOUNTS_NOT_INCLUDED": {
                "name": "Cess Amounts Not Included",
                "fix": "Both ad-valorem Cess (CesAmt) and non-ad-valorem Cess (CesNonAdvlAmt) must be included in TotItemVal."
            },
            "DECIMAL_PAISE_ROUNDING_DISCREPANCY": {
                "name": "Decimal / Paise Rounding Discrepancy (> ₹1.00)",
                "fix": "The tolerance is strictly +/- 1.00. If rounding differences exceed ₹1.00, align TotItemVal closer to the exact calculated sum."
            }
        }
    },
    2195: {
        "message": "e-Commerce GSTIN is not registered as TCS-GSTIN",
        "reason": "ecom_gstin is not registered as Tax Collector",
        "resolution": "Verify e-commerce GSTIN type on GST portal"
    },
    2200: {
        "message": "State code {0} is invalid for dispatch details or ship details",
        "reason": "The 2-digit numeric state code passed in DispDtls.Stcd (Dispatch Details) or ShipDtls.Stcd (Ship-to Details) is invalid, does not match the GST state code master (01 to 38, 97, 99), or does not match the state code prefix of the GSTIN passed in that section.",
        "resolution": "Ensure DispDtls.Stcd and ShipDtls.Stcd are strictly 2-digit numeric strings with leading zeros ('01' to '38'). Do not use 1-digit codes ('7'), state alpha abbreviations ('MH'), or codes that disagree with the provided section GSTIN prefix. '00' is invalid and '99' is not allowed for physical goods movement.",
        "scenarios": {
            "LEADING_ZERO_OMITTED": {
                "name": "Leading Zero Omitted (1-digit sent)",
                "fix": "Delhi state code is '07', not '7'. State codes must be strictly 2 digits with leading zeros where applicable ('01' to '09')."
            },
            "ALPHA_CODE_USED": {
                "name": "Alpha Code Used Instead of Numeric Code",
                "fix": "State codes must be numeric strings (e.g., '27' for Maharashtra, '29' for Karnataka), not 2-letter state abbreviations."
            },
            "STATE_CODE_DISAGREES_WITH_GSTIN": {
                "name": "State Code Disagrees with Provided GSTIN",
                "fix": "If Gstin is passed inside ShipDtls/DispDtls, the state code Stcd must match the first two digits of that GSTIN."
            },
            "INVALID_OR_NON_EXISTENT_CODE": {
                "name": "Invalid / Non-Existent Code Passed",
                "fix": "'00' is invalid. '99' is reserved for Center Jurisdiction / Other territory services and cannot be used for physical dispatch points. Use valid state code between '01' and '38'."
            }
        }
    },
    2201: {
        "message": "Invalid Port Code for Export Transaction",
        "reason": "Export invoice (trancatg EXPWP / EXPWOP) contains a value in ExpDtls.Port (Shipping Bill Port Code) that does not exist in the official Indian Customs EDI / ICEGATE port code master list, has improper formatting, or is erroneously provided for domestic supply.",
        "resolution": "Ensure ExpDtls.Port is a standard 6-character alphanumeric ICEGATE / UN-LOCODE (e.g. INNSA1, INBOM1, INBOM4, INDEL4, INBLR4) without spaces, hyphens, or city names. Match port type to transport mode (Air vs Sea), and omit ExpDtls entirely for domestic transactions.",
        "scenarios": {
            "INFORMAL_OR_CITY_NAME_USED": {
                "name": "Informal / City Name Used",
                "fix": "Port codes must be standard 6-character alphanumeric ICEGATE/UN-LOCODEs, not city names."
            },
            "AIR_SEA_PORT_CODE_CONFUSION": {
                "name": "Air / Sea Port Code Confusion",
                "fix": "Ensure the 6-character port code matches the exact Customs location where the Shipping Bill is filed (e.g. INBOM4 for Air Cargo, INNSA1 for Ocean Sea Port)."
            },
            "WRONG_FORMAT_SPACING_SPECIAL_CHARS": {
                "name": "Wrong Format / Spacing / Special Characters",
                "fix": "Port codes are strictly 6 alphanumeric uppercase characters without hyphens, dots, or spaces."
            },
            "PORT_CODE_PROVIDED_FOR_DOMESTIC_SUPPLY": {
                "name": "Port Code Provided for Domestic Supply",
                "fix": "ExpDtls (including Port) is only applicable for Export (EXPWP, EXPWOP) transactions. Omit ExpDtls entirely for domestic supply."
            }
        }
    },
    2202: {
        "message": "Invalid Country Code in Export Details",
        "reason": "The country code passed in ExpDtls.CntCode does not match the official ISO 3166-1 alpha-2 (2-character) country code master list recognized by the NIC / GSTN portal, contains a 3-letter alpha code, full country name, lowercase letters, or domestic code 'IN'.",
        "resolution": "Ensure ExpDtls.CntCode is strictly a valid 2-letter uppercase ISO 3166-1 alpha-2 country code (e.g., 'US', 'GB', 'AE', 'DE', 'SG'). Do not use 3-letter codes ('USA'), full country names ('GERMANY'), lowercase letters ('ae'), or domestic code ('IN').",
        "scenarios": [
            "THREE_LETTER_ALPHA_CODE",
            "FULL_COUNTRY_NAME_PASSED",
            "LOWERCASE_COUNTRY_CODE",
            "DOMESTIC_CODE_IN_EXPORT_DETAILS",
            "INVALID_OR_NON_EXISTENT_COUNTRY_CODE"
        ]
    },
    2203: {
        "message": "Invalid Foreign Currency in Export Details",
        "reason": "The currency code passed in ExpDtls.ForCur does not match the official ISO 4217 (3-character) currency code master list recognized by the e-Invoice system, contains currency symbols, colloquial abbreviations, domestic 'INR' in foreign field, or lowercase characters.",
        "resolution": "Ensure ExpDtls.ForCur is strictly a valid 3-character uppercase ISO 4217 currency code (e.g., 'USD', 'EUR', 'GBP', 'AED', 'SGD'). Do not use currency symbols ('$'), colloquial abbreviations ('US$', 'BUCKS'), lowercase letters ('gbp'), or 'INR' for foreign billed invoices.",
        "scenarios": [
            "CURRENCY_SYMBOL_PASSED",
            "COLLOQUIAL_OR_CUSTOM_ABBREVIATION",
            "DOMESTIC_CURRENCY_IN_FOREIGN_FIELD",
            "LOWERCASE_CURRENCY_CODE",
            "INVALID_OR_NON_EXISTENT_CURRENCY_CODE"
        ]
    },
    2211: {
        "message": "Supplier and recipient GSTIN should not be the same",
        "reason": "SellerDtls.Gstin and BuyerDtls.Gstin are identical in the payload. The e-Invoice portal does not permit self-invoicing under the same GSTIN (an entity cannot issue a commercial tax invoice to its own distinct GST registration).",
        "resolution": "For same-state branch transfers, issue a Delivery Challan ('CHL') without IRN. For inter-state distinct persons, pass the destination branch's state-specific GSTIN. For Section 31(3)(f) RCM self-invoices, report directly in GSTR-3B/GSTR-1, not IRP. In testing, use distinct sandbox recipient GSTIN.",
        "scenarios": [
            "INTRA_STATE_BRANCH_TRANSFER_DELIVERY_CHALLAN",
            "INTER_STATE_STOCK_TRANSFER_DISTINCT_GSTIN",
            "TESTING_SANDBOX_DEFAULT_GSTIN",
            "SELF_INVOICE_RCM_SECTION_31_3_F"
        ]
    },
    2212: {
        "message": "Recipient GSTIN cannot be URP for given supply type",
        "reason": "Recipient GSTIN is set to 'URP' for transaction categories (B2B, SEZWP, SEZWOP, DEXP) that strictly require a 15-character registered GSTIN. URP is only permitted for direct exports (EXPWP / EXPWOP) or B2C supplies.",
        "resolution": "For B2B supplies, pass the buyer's active 15-digit GSTIN. For domestic retail consumers, set trancatg='B2C' and generate local dynamic QR code (do not upload to IRP). For overseas foreign buyers, change supply type to 'EXPWP' or 'EXPWOP'. For SEZ units, pass the registered SEZ GSTIN.",
        "scenarios": [
            "REGISTERED_BUYER_MARKED_AS_URP",
            "DOMESTIC_B2C_SUPPLY",
            "EXPORT_TRANSACTION_MISCLASSIFIED_AS_B2B",
            "SEZ_SUPPLY_TREATED_AS_URP"
        ]
    },
    2213: {
        "message": "The supplier GSTIN cannot be URP",
        "reason": "This error occurs when 'URP' (Unregistered Person) is passed in SellerDtls.Gstin. Under Indian GST law, e-Invoicing applies exclusively to registered taxpayers whose aggregate turnover exceeds the mandatory threshold. An unregistered supplier cannot issue an e-Invoice or register an IRN.",
        "resolution": "Always pass the seller's active, 15-character registered GSTIN. Do not upload RCM inward purchase invoices to the IRP. Use active sandbox GSTINs during testing.",
        "scenarios": {
            "SUPPLIER_MARKED_AS_URP_BY_MISTAKE": {
                "name": "Supplier Marked as URP by Mistake",
                "fix": "Always pass the seller's active, 15-character registered GSTIN."
            },
            "REVERSE_CHARGE_RCM_INWARD_INVOICE_UPLOAD": {
                "name": "Reverse Charge (RCM) Inward Invoice Upload",
                "fix": "Do not upload via outbound IRP API. Purchase invoices from unregistered suppliers under RCM are reported directly in GSTR-3B, not on the IRP."
            },
            "TESTING_WITH_DUMMY_DATA": {
                "name": "Testing with Dummy Data",
                "fix": "Use a valid, active GSTIN configured in the e-Invoice sandbox/portal. The IRP validates the seller's GSTIN against the active taxpayer registry; URP is never allowed for the seller."
            }
        }
    },
    2227: {
        "message": "For Sl. No {0}, SGST and CGST amounts are not equal",
        "reason": "This error occurs when the CgstAmt and SgstAmt values in a specific line item within ItemList do not match. Under the GST framework, intra-state tax is split equally between the Central Government (CGST) and the State Government (SGST/UTGST): ItemList[i].CgstAmt = ItemList[i].SgstAmt = (ItemList[i].AssAmt * (GstRt / 2)) / 100.",
        "resolution": "Ensure CgstAmt and SgstAmt are equal for each intra-state item. Tax must be split identically. Round both taxes equally.",
        "scenarios": {
            "UNEQUAL_TAX_SPLIT": {
                "name": "Unequal Tax Split",
                "fix": "Tax must be split identically (e.g., 18% / 2 = 9% each: 900.00 CGST and 900.00 SGST)."
            },
            "ASYMMETRIC_ROUNDING_ACROSS_TAXES": {
                "name": "Asymmetric Rounding Across Taxes",
                "fix": "Individual line CGST and SGST must be identical. If rounding is required, round both equally or adjust unit rate/assessable value."
            },
            "ACCIDENTAL_ZERO_IN_ONE_COMPONENT": {
                "name": "Accidental Zero in One Component",
                "fix": "One component cannot be zero if the other is positive in an intra-state supply."
            }
        }
    },
    2228: {
        "message": "Item list cannot be empty",
        "reason": "This error occurs when the ItemList array in the request payload contains zero items, is passed as null, or is an empty list ([]). Every e-Invoice must contain at least one valid line item.",
        "resolution": "Include at least one valid line item object in ItemList array. Ensure backend serialization waits until line items are loaded before calling the API.",
        "scenarios": {
            "EMPTY_ARRAY_PASSED": {
                "name": "Empty Array Passed",
                "fix": "Include at least one line item object inside the array. An invoice must have at least 1 line item and can have up to 1,000 line items."
            },
            "NULL_ARRAY_PASSED": {
                "name": "Null Array Passed",
                "fix": "ItemList is a mandatory array field in the JSON schema. Pass a non-null array with at least one line item."
            },
            "ERP_DATA_EXTRACTION_GLITCH": {
                "name": "ERP Data Extraction Glitch",
                "fix": "Ensure backend serialization waits until line items are loaded before calling the API. Verify that line items are present in memory/payload before dispatching the payload."
            }
        }
    },
    2230: {
        "message": "IRN Cannot Be Cancelled Because Active E-Way Bill Exists",
        "reason": "This error occurs when attempting to call the Cancel IRN API for an invoice that already has an active, valid E-Way Bill linked to it. The NIC system enforces strict dependency ordering: an invoice cannot be deleted or cancelled while an active transport document (E-Way Bill) authorizing the movement of those goods is alive on the network.",
        "resolution": "Step 1: Cancel the linked E-Way Bill first via Cancel EWB API. Step 2: Cancel the IRN via Cancel IRN API. If the 24-hour cancellation window has lapsed, issue a Credit Note (CRN) instead.",
        "scenarios": {
            "ATTEMPTING_TO_CANCEL_IRN_DIRECTLY_WHILE_EWAY_BILL_IS_ACTIVE": {
                "name": "Attempting to Cancel IRN Directly While E-Way Bill is Active",
                "fix": "Step 1: Call Cancel E-Way Bill API. Step 2: Call Cancel IRN API. An active E-Way Bill locks the IRN against cancellation. The E-Way Bill must be cancelled first."
            },
            "EWAY_BILL_ALREADY_GENERATED_BY_TRANSPORTER_OR_COUNTERPARTY": {
                "name": "E-Way Bill Already Generated by Transporter / Counterparty",
                "fix": "Check active EWBs linked to the document on the E-Way Bill portal, cancel the EWB first, then cancel the IRN. Irrespective of who generated the EWB (supplier or transporter), it must be cancelled prior to IRN cancellation."
            },
            "CANCELLATION_WINDOW_LAPSED_OVER_24_HOURS": {
                "name": "Cancellation Window Lapsed (> 24 Hours)",
                "fix": "Attempting cancellation after 24 hours of IRN generation. IRN cannot be cancelled via API after 24 hours. Issue a Credit Note (CRN) instead."
            }
        }
    },
    2231: {
        "message": "Cannot Generate e-Invoice as Supplier GSTIN is SEZ",
        "reason": "This error occurs when the supplier GSTIN (SellerDtls.Gstin) belongs to a Special Economic Zone (SEZ) unit or developer. Under Notification No. 13/2020 – Central Tax, SEZ units are explicitly exempt from the mandatory e-invoicing provisions, even if their aggregate annual turnover exceeds the statutory threshold.",
        "resolution": "Do not push SEZ outbound invoices to IRP. Generate standard tax invoices directly from ERP. For DTA units selling to SEZ, set SupTyp to SEZWP/SEZWOP. Exclude SEZ GSTINs in integration middleware.",
        "scenarios": {
            "SEZ_UNIT_ATTEMPTING_OUTBOUND_IRN_GENERATION": {
                "name": "SEZ Unit Attempting Outbound IRN Generation",
                "fix": "Do not push SEZ outbound invoices to IRP. Generate standard tax invoices directly from ERP. SEZ units are legally exempted from issuing e-Invoices. Report directly in regular GSTR-1 returns."
            },
            "DTA_ENTITY_INVOICING_TO_SEZ_UNIT": {
                "name": "DTA Entity Invoicing to SEZ Unit (Misrouted Flags)",
                "fix": "Set SupTyp to SEZWP or SEZWOP, keep SellerDtls.Gstin as DTA GSTIN. DTA units selling to SEZ must generate e-Invoices. Only supplies originating from SEZ units are exempt."
            },
            "MULTI_GSTIN_SETUP_TRIGGERING_WRONG_ENTITY": {
                "name": "Multi-GSTIN Setup Triggering Wrong Entity",
                "fix": "Add an exclusion rule in ERP integration middleware to bypass IRP API calls for SEZ GSTINs. Middleware/GSP connectors should filter out SEZ GSTINs prior to invoking the IRP endpoint."
            }
        }
    },
    2232: {
        "message": "POS is incorrect for Export transaction",
        "reason": "This error occurs when an Export transaction (SupTyp is EXP, EXPWP, or EXPWOP) is sent with a Place of Supply (BuyerDtls.Pos) other than the designated 'Other Country' state code '96'. For cross-border export transactions under the GST framework, the Place of Supply lies outside India. The GST system mandates using code '96' for Place of Supply and Recipient State Code in all direct export payloads.",
        "resolution": "Set BuyerDtls.Pos to '96' and StateCode to '96' for direct exports. If the supply is domestic within India, switch supply type to B2B and retain the domestic recipient state code.",
        "scenarios": {
            "SELLER_OWN_STATE_PASSED_AS_POS": {
                "name": "Seller's Own State Passed as POS",
                "fix": "Exports cannot have an Indian domestic state code as POS. Set Pos to '96' and StateCode to '96'."
            },
            "PORT_GATEWAY_STATE_CODE_PASSED_AS_POS": {
                "name": "Port / Gateway State Code Passed as POS",
                "fix": "The exit port's location does not determine POS for direct exports. POS must remain '96'."
            },
            "NUMERIC_VALUE_PASSED_INSTEAD_OF_STRING": {
                "name": "Numeric Value Passed Instead of String",
                "fix": "Pos is defined as a 2-character string in the JSON schema. Ensure quotes are present ('96')."
            },
            "WRONG_SUPPLY_TYPE_SELECTED_FOR_DOMESTIC_SUPPLY": {
                "name": "Wrong Supply Type Selected for Domestic Supply",
                "fix": "If goods/services are supplied within India, switch supply type to B2B rather than EXPWP/EXPWOP."
            }
        }
    },
    2233: {
        "message": "Duplicate SI numbers are not allowed in line items",
        "reason": "This error occurs when the item serial number field (ItemList[i].SlNo) contains duplicate values across line items in an invoice. Every line item inside the ItemList array must have a strictly unique serial number.",
        "resolution": "Ensure loop/mapping index generates sequential, unique strings ('1', '2', '3', etc.). Sub-lines or batch splits must each carry a distinct SlNo. Strip whitespace from serial numbers.",
        "scenarios": {
            "HARDCODED_ONE_ON_ALL_LINE_ITEMS": {
                "name": "Hardcoded '1' on All Line Items",
                "fix": "Ensure the loop/mapping index generates sequential, unique strings ('1', '2', '3', etc.)."
            },
            "MERGED_BATCHES_CARRYING_PARENT_SERIAL_NUMBER": {
                "name": "Merged Batches Carrying Parent Serial Number",
                "fix": "Sub-lines or batch splits must each carry a distinct SlNo if sent as separate items in ItemList."
            },
            "NON_STRING_SPACE_ARTIFACTS_CAUSING_COLLISION": {
                "name": "Non-String / Space Artifacts Causing Collision",
                "fix": "Trailing or leading whitespaces can cause indexing collisions or normalization issues during schema validation. Strip and normalize serial numbers sequentially."
            }
        }
    },
    2234: {
        "message": "For Sl. No {0}, SGST and CGST amount passed does not match with taxable value and tax rate",
        "reason": "CgstAmt and SgstAmt calculated for a line item deviate from AssAmt * (GstRt / 2) / 100 beyond the permitted tolerance of ±1.00",
        "resolution": "CgstAmt and SgstAmt must strictly equal round(AssAmt * (GstRt / 2) / 100, 2) within ±1.00 tolerance",
        "formula": "CgstAmt = SgstAmt = (AssAmt * (GstRt / 2)) / 100 (Tolerance: ±1.00)",
        "tolerance": 1.00,
        "scenarios": {
            "TAX_CALCULATED_ON_GROSS_INSTEAD_OF_ASSAMT": {
                "name": "Tax Calculated on Gross (TotAmt) Instead of Taxable Base (AssAmt)",
                "description": "TotAmt = 10000, Discount = 2000, AssAmt = 8000, GstRt = 18. Sent Cgst=900, Sgst=900 instead of 720.",
                "fix": "Tax must be calculated on the discounted assessable value 8000, not the gross 10000 (8000 * 9% = 720)."
            },
            "FULL_TAX_APPLIED_TO_BOTH_FIELDS": {
                "name": "Full Tax Applied to Both Fields",
                "description": "AssAmt = 10000, GstRt = 18. Sent Cgst=1800, Sgst=1800 instead of 900.",
                "fix": "GstRt represents the total GST rate (18%). Each component takes half (9% = 900.00)."
            },
            "RATE_VS_AMOUNT_DISCONNECT": {
                "name": "Rate vs Amount Disconnect",
                "description": "AssAmt = 10000, GstRt = 12. Sent Cgst=900, Sgst=900 instead of 600.",
                "fix": "CgstAmt and SgstAmt must match the declared GstRt (10000 * 6% = 600)."
            },
            "ROUNDING_DEVIATION_EXCEEDING_ONE_RUPEE": {
                "name": "Rounding Deviation Exceeding ₹1.00",
                "description": "Tax mathematically computes to 45.10, but ERP sends 47.00.",
                "fix": "Align line tax closer to mathematically exact values (±1.00 ceiling). Discrepancies wider than ₹1.00 trigger validation failures."
            }
        }
    },
    2235: {
        "message": "For Sl. No {0}, IGST amount passed is not matching with taxable value and tax rate",
        "reason": "IgstAmt calculated for a line item deviates from AssAmt * GstRt / 100 beyond the permitted tolerance of ±1.00",
        "resolution": "IgstAmt must strictly equal round(AssAmt * GstRt / 100, 2) within ±1.00 tolerance",
        "formula": "IgstAmt = (AssAmt * GstRt) / 100 (Tolerance: ±1.00)",
        "tolerance": 1.00,
        "scenarios": {
            "TAX_CALCULATED_ON_GROSS_INSTEAD_OF_ASSAMT": {
                "name": "Tax Calculated on Gross (TotAmt) Instead of Taxable Base (AssAmt)",
                "description": "TotAmt = 10000, Discount = 1000, AssAmt = 9000, GstRt = 18. Sent Igst=1800 instead of 1620.",
                "fix": "IGST must be calculated on the assessable value (9000 * 18% = 1620), not on the pre-discount total."
            },
            "HALF_RATE_APPLIED_INSTEAD_OF_FULL_RATE": {
                "name": "Half Rate Applied Instead of Full Rate",
                "description": "AssAmt = 10000, GstRt = 18. Sent Igst=900 instead of 1800.",
                "fix": "For inter-state supplies, IGST takes the entire rate (18%), unlike CGST/SGST which splits it into two equal halves."
            },
            "TAX_RATE_MISMATCHES_TAX_AMOUNT": {
                "name": "Tax Rate (GstRt) Mismatches Tax Amount",
                "description": "AssAmt = 50000, GstRt = 18. Sent Igst=6000 (12%) instead of 9000.",
                "fix": "Ensure GstRt and IgstAmt are mutually consistent. 50000 * 18% = 9000.00."
            },
            "ROUNDING_DIFFERENCE_GREATER_THAN_ONE_RUPEE": {
                "name": "Rounding Difference Greater Than ₹1.00",
                "description": "Exact tax is 181.20, but ERP rounds or maps to 183.00.",
                "fix": "Keep the rounding difference within the ±1.00 ceiling."
            }
        }
    },
    2238: {
        "message": "For Sl. No {0}, Quantity is not passed",
        "reason": "The Qty field in a line item inside ItemList is omitted, sent as null, or passed as an empty string. The e-Invoice schema requires a numeric value for quantity across all line items (goods and services alike).",
        "resolution": "Populate Qty with a valid non-zero numeric quantity (up to 3 decimal places, default to 1.00 for services)",
        "scenarios": {
            "SERVICE_LINE_ITEM_WITHOUT_QUANTITY": {
                "name": "Service Line Item Without Quantity",
                "description": "'IsServc': 'Y', Qty omitted or null. Sent Qty=None.",
                "fix": "Even for service lines, Qty must be populated with a valid numeric quantity (default to 1 or 1.00), and Unit set to 'OTH'."
            },
            "PASSING_EMPTY_STRING_INSTEAD_OF_NUMBER": {
                "name": "Passing Empty String Instead of Number",
                "description": "'Qty': '' passed as an empty string instead of numeric type.",
                "fix": "Qty is a numeric type (up to 3 decimal places). Pass positive numeric value (e.g., 10 or 1.00)."
            },
            "ZERO_QUANTITY_PASSED": {
                "name": "Zero Quantity Passed",
                "description": "'Qty': 0 passed for line item.",
                "fix": "Line items must represent a non-zero measurable quantity. Set Qty to 1 (or actual measurable quantity)."
            }
        }
    },
    2239: {
        "message": "For Sl. No {0}, Unit Quantity Code (UQC) is not passed",
        "reason": "The Unit field in an item object inside ItemList is missing, empty, or passed as null. Every line item must have a valid 3-letter Unit Quantity Code (UQC) matching the master list.",
        "resolution": "Pass a valid 3-character uppercase UQC code from the master list (e.g., NOS, KGS, BOX, OTH)",
        "scenarios": {
            "OMITTED_FOR_SERVICE_LINE": {
                "name": "Omitted for Service Line",
                "description": "'IsServc': 'Y', Unit omitted or null.",
                "fix": "For services or items without a specific physical measurement unit, use 'OTH' (Others)."
            },
            "EMPTY_STRING_PASSED": {
                "name": "Empty String Passed",
                "description": "'Unit': '' passed as empty string.",
                "fix": "Pass a valid 3-character uppercase UQC code from the master list (e.g., NOS, KGS, BOX, OTH)."
            },
            "ERP_MASTER_FIELD_UNMAPPED": {
                "name": "ERP Master Field Unmapped",
                "description": "Item created in ERP without mapping to GST UQC table (e.g. 'PIECES', 'PKT').",
                "fix": "Ensure ERP export workflow maps internal units to standard GST UQC values (e.g. NOS, OTH)."
            }
        }
    },
    2240: {
        "message": "For Sl. No {0}, GST rate of tax is incorrect or not as notified",
        "reason": "The tax rate passed in ItemList[i].GstRt is not one of the officially notified GST tax rate slabs: 0, 0.1, 0.25, 0.5, 1, 1.5, 2, 3, 5, 6, 7.5, 12, 18, 28",
        "resolution": "Use official notified GST rate slab strictly matching NIC e-Invoice schema",
        "allowed_slabs": [0, 0.1, 0.25, 0.5, 1, 1.5, 2, 3, 5, 6, 7.5, 12, 18, 28],
        "scenarios": {
            "SINGLE_COMPONENT_PASSED_INSTEAD_OF_COMBINED_RATE": {
                "name": "Single Component Passed Instead of Combined Rate",
                "description": "Intra-state 18% supply, but sent 'GstRt': 9.0 (CGST component only).",
                "fix": "GstRt always represents the total GST rate (CGST + SGST or IGST). Pass total combined rate 18.0."
            },
            "PERCENTAGE_SYMBOL_OR_STRING_SENT": {
                "name": "Percentage Symbol or String Sent",
                "description": "'GstRt': '18%' or 'GstRt': '18' sent as formatted string.",
                "fix": "GstRt must be a numeric floating-point value (e.g. 18.0), not a string with %."
            },
            "ARBITRARY_NON_NOTIFIED_TAX_SLAB": {
                "name": "Arbitrary / Non-Notified Tax Slab",
                "description": "'GstRt': 10.0 or 15.0 passed which is not an approved slab.",
                "fix": "Use notified rate: 12.0 or 18.0. The value must strictly match an official GST rate slab recognized by the IRP."
            },
            "CESS_RATE_ADDED_TO_GST_RATE": {
                "name": "Cess Rate Added to GST Rate",
                "description": "Goods with 28% GST + 12% Cess sent as 'GstRt': 40.0.",
                "fix": "GST Rate and Cess Rate must remain separate in their designated fields (GstRt=28.0 vs CesRt=12.0)."
            }
        }
    },
    2242: {
        "message": "Recipient POS is incorrect for transaction type {0}",
        "reason": "The Place of Supply (BuyerDtls.Pos) is sent as '96' (Other Country) for domestic transaction types like B2B, SEZWP, SEZWOP, or DEXP. Code '96' is reserved strictly for export transactions (EXPWP and EXPWOP).",
        "resolution": "For all domestic transactions, the recipient's POS must be a valid 2-digit Indian State / UT code (01 to 38, 97)",
        "scenarios": {
            "DOMESTIC_SALE_PASSED_WITH_POS_96": {
                "name": "Domestic Sale Passed with POS '96'",
                "description": "'SupTyp': 'B2B', 'BuyerDtls': { 'Pos': '96' }.",
                "fix": "Domestic supplies must carry the destination state's valid 2-digit code (01-38). Set Pos to buyer's actual state code."
            },
            "EXPORT_TRANSACTION_MISCLASSIFIED_AS_B2B": {
                "name": "Export Transaction Misclassified as B2B",
                "description": "Overseas client billed with POS '96', but transaction type was sent as 'SupTyp': 'B2B'.",
                "fix": "If the client is abroad and POS is '96', the supply type must be set to EXPWP or EXPWOP."
            },
            "SEZ_SUPPLY_PASSED_WITH_POS_96": {
                "name": "SEZ Supply Passed with POS '96'",
                "description": "SEZ unit located in India billed with 'SupTyp': 'SEZWP', 'BuyerDtls': { 'Pos': '96' }.",
                "fix": "SEZ units reside in Indian territory; their POS is the state where the SEZ is physically located, never '96'."
            }
        }
    },
    2243: {
        "message": "POS code is invalid",
        "reason": "The 2-digit code passed in BuyerDtls.Pos (Place of Supply) does not exist in the official GST State Master list (01 through 38, 96, or 97).",
        "resolution": "Pass a valid 2-digit state code from the official GST State Master (01 to 38, 96 for exports, or 97 for other territories)",
        "scenarios": {
            "LEADING_ZERO_OMITTED": {
                "name": "Leading Zero Omitted (1-digit sent)",
                "description": "'BuyerDtls': { 'Pos': '7' }.",
                "fix": "Delhi state code is '07', not '7'. Single-digit states (01 to 09) must have leading zeros."
            },
            "ALPHABETIC_STATE_ABBREVIATION_PASSED": {
                "name": "Alphabetic State Abbreviation Passed",
                "description": "'BuyerDtls': { 'Pos': 'KA' }.",
                "fix": "State codes must be numeric strings (e.g., '29' for Karnataka), not alpha abbreviations."
            },
            "INVALID_OR_NON_EXISTENT_CODE": {
                "name": "Invalid / Non-Existent Code",
                "description": "'BuyerDtls': { 'Pos': '00' } or '99' (for standard goods).",
                "fix": "'00' does not exist. '99' is reserved for Center Jurisdiction / Other territory services. Use valid code ('01' to '38', or '96' for exports)."
            },
            "NUMERIC_TYPE_PASSED_INSTEAD_OF_STRING": {
                "name": "Numeric Type Passed Instead of String",
                "description": "'BuyerDtls': { 'Pos': 27 } passed as integer instead of string.",
                "fix": "Pos must be enclosed in double quotes as a string ('27')."
            }
        }
    },
    2244: {
        "message": "Recipient pincode is not provided for the transaction - {0}",
        "reason": "BuyerDtls.Pin is omitted, passed as null, or passed as 0 for domestic transactions where a 6-digit Indian PIN code is mandatory (such as B2B, SEZWP, SEZWOP, or DEXP).",
        "resolution": "Pass a valid 6-digit Indian postal code (or 999999 for cross-border exports)",
        "scenarios": {
            "PIN_CODE_OMITTED_OR_NULL_IN_B2B": {
                "name": "PIN Code Omitted or Null in B2B",
                "description": "'BuyerDtls': { 'Pin': null } or omitted in domestic transaction.",
                "fix": "Pin is mandatory for all domestic transactions and must be a valid 6-digit integer."
            },
            "EXPORT_TRANSACTION_OMITTING_DUMMY_PIN": {
                "name": "Export Transaction Omitting Dummy PIN",
                "description": "'SupTyp': 'EXPWP', Pin omitted or null.",
                "fix": "For cross-border exports, passing the designated foreign PIN integer 999999 is standard schema practice."
            },
            "STRING_TYPE_PASSED_INSTEAD_OF_INTEGER": {
                "name": "String Type Passed Instead of Integer",
                "description": "'BuyerDtls': { 'Pin': '560001' } passed as string.",
                "fix": "In the NIC schema, Pin is strictly defined as an integer, not a string."
            },
            "NON_EXISTENT_OR_INVALID_PIN_FORMAT": {
                "name": "Non-Existent / Invalid PIN Format",
                "description": "'BuyerDtls': { 'Pin': 12345 } (5 digits) or non-numeric.",
                "fix": "Must be a valid 6-digit Indian postal code recognized by the postal directory master."
            }
        }
    },
    2246: {
        "message": "Recepient cannot be SEZ for - {0} transaction",
        "reason": "The buyer's GSTIN (BuyerDtls.Gstin) belongs to a Special Economic Zone (SEZ) unit or developer, but the invoice was sent with a supply type of B2B or DEXP instead of an SEZ-specific supply type.",
        "resolution": "Declare supply type as SEZWP (with payment of tax) or SEZWOP (without payment of tax) when supplying to an SEZ unit",
        "scenarios": {
            "SEZ_SUPPLY_TAGGED_AS_STANDARD_B2B": {
                "name": "SEZ Supply Tagged as Standard B2B",
                "description": "'SupTyp': 'B2B', 'BuyerDtls': { 'Gstin': '24AAACS0000A1Z5' } (SEZ GSTIN).",
                "fix": "Transactions with SEZ units cannot use B2B. Change SupTyp to 'SEZWP' or 'SEZWOP'."
            },
            "DEEMED_EXPORT_USED_FOR_SEZ_UNIT": {
                "name": "Deemed Export Used for SEZ Unit",
                "description": "'SupTyp': 'DEXP', 'BuyerDtls': { 'Gstin': '24AAACS0000A1Z5' } (SEZ GSTIN).",
                "fix": "DEXP is for supplies to Export Oriented Units (EOU), not SEZ units. Change SupTyp to 'SEZWP' or 'SEZWOP'."
            },
            "REGULAR_DTA_BUYER_MARKED_WITH_WRONG_GSTIN": {
                "name": "Regular DTA Buyer Marked with Wrong GSTIN",
                "description": "Transaction was a regular B2B sale, but buyer's sister concern (SEZ unit GSTIN) was entered by error.",
                "fix": "Pass the buyer's domestic DTA unit GSTIN in BuyerDtls.Gstin. Use the correct non-SEZ GSTIN if the sale was meant for a standard domestic entity."
            }
        }
    },
    2247: {
        "message": "Recepient should be SEZ for transaction {0}",
        "reason": "The transaction supply type (TranDtls.SupTyp) is set to SEZWP or SEZWOP, but the recipient's GSTIN (BuyerDtls.Gstin) is registered as a regular domestic taxpayer (DTA) rather than an SEZ unit or developer in the GST master registry.",
        "resolution": "Change supply type to B2B for domestic buyers, or pass the buyer's distinct SEZ unit GSTIN.",
        "scenarios": {
            "DOMESTIC_SALE_MISCLASSIFIED_AS_SEZ": {
                "name": "Domestic Sale Misclassified as SEZ",
                "description": "Supply to a regular domestic company sent with SupTyp = 'SEZWP' or 'SEZWOP'.",
                "fix": "Set SupTyp = 'B2B'. If the counterparty is a standard domestic enterprise, use supply type B2B."
            },
            "WRONG_ENTITY_GSTIN_SELECTED_FOR_SEZ_BUYER": {
                "name": "Wrong Entity GSTIN Selected for SEZ Buyer",
                "description": "Buyer operates both a DTA headquarters and an SEZ branch; the DTA GSTIN was passed in payload.",
                "fix": "Pass the buyer's specific SEZ branch GSTIN in BuyerDtls.Gstin. SEZ entities must register a distinct GSTIN for units located within the Special Economic Zone."
            },
            "SEZ_STATUS_RECENTLY_GRANTED_PORTAL_SYNC_LAG": {
                "name": "SEZ Status Recently Granted / Portal Sync Lag",
                "description": "Buyer recently migrated or registered as an SEZ, but master is not refreshed.",
                "fix": "Verify buyer's status on the GST portal (Search Taxpayer -> Constitution / Taxpayer Type). If newly updated, ensure buyer's GSTIN status reflects active SEZ registration on GSTN before calling IRP."
            }
        }
    },
    2248: {
        "message": "Recepient has to be URP in case of Export transactions",
        "reason": "The transaction supply type (TranDtls.SupTyp) is set to EXPWP or EXPWOP, but BuyerDtls.Gstin contains an Indian domestic GSTIN or custom identifier instead of the literal string 'URP'.",
        "resolution": "Set BuyerDtls.Gstin to 'URP' for cross-border export transactions.",
        "scenarios": {
            "DOMESTIC_GSTIN_PASSED_IN_EXPORT_PAYLOAD": {
                "name": "Domestic GSTIN Passed in Export Payload",
                "description": "Export invoice payload passed a 15-character Indian domestic GSTIN instead of 'URP'.",
                "fix": "Foreign export recipients cannot have an Indian GSTIN. Set BuyerDtls.Gstin to 'URP'."
            },
            "OVERSEAS_TAX_ID_VAT_OR_EIN_PASSED": {
                "name": "Overseas Tax ID / VAT / EIN Passed",
                "description": "Foreign entity registration number (EIN, VAT, TIN) passed in BuyerDtls.Gstin.",
                "fix": "Set BuyerDtls.Gstin to 'URP'. Foreign tax registration numbers belong to internal notes, not BuyerDtls.Gstin."
            },
            "FIELD_PASSED_AS_NULL_OR_BLANK_STRING": {
                "name": "Field Passed as Null or Blank String",
                "description": "BuyerDtls.Gstin was passed as null, None, or empty string on export transaction.",
                "fix": "BuyerDtls.Gstin is a required string field. Set BuyerDtls.Gstin to 'URP'."
            },
            "DOMESTIC_SALE_MISCLASSIFIED_AS_EXPORT": {
                "name": "Domestic Sale Misclassified as Export",
                "description": "Indian domestic buyer invoice tagged as EXPWP or EXPWOP.",
                "fix": "Change SupTyp to 'B2B' and retain the buyer's 15-character domestic GSTIN."
            }
        }
    },
    2255: {
        "message": "Requested Payload is Empty",
        "reason": "This error occurs at the HTTP/API transport layer when the IRP server receives a request with an empty body, zero-byte content length, or malformed data that fails initial JSON deserialization.",
        "resolution": "Ensure request payload serialization completes, body is non-empty, and Content-Type header is set to application/json.",
        "scenarios": {
            "EMPTY_REQUEST_BODY": {
                "name": "Empty Request Body",
                "description": "HTTP POST sent with empty object ({}), empty body, or zero-byte buffer.",
                "fix": "Send the complete, signed/encrypted e-Invoice JSON payload. Ensure serialization completes and the request body contains the full e-Invoice structure."
            },
            "MISSING_OR_INCORRECT_CONTENT_TYPE_HEADER": {
                "name": "Missing or Incorrect Content-Type Header",
                "description": "Header sent as Content-Type: text/plain or header omitted entirely.",
                "fix": "Set header Content-Type: application/json. The API gateway drops or rejects bodies if the MIME type is not set to application/json."
            },
            "PREMATURE_STREAM_FLUSH_OR_CLOSE": {
                "name": "Premature Stream Flush / Premature Close",
                "description": "HTTP client terminates connection or closes stream before payload finishes sending.",
                "fix": "Ensure HTTP client writes the entire buffer and sets a proper Content-Length. Buffer size or network timeouts in the ERP client can lead to an empty body reaching the server."
            },
            "ENCRYPTION_FAILURE_PRODUCING_EMPTY_BUFFER": {
                "name": "Encryption Failure Producing Empty Buffer",
                "description": "GSP/ERP encryption wrapper encounters an unhandled exception and posts an empty string.",
                "fix": "Verify the payload encryption step returns a non-empty base64 string before sending. When using NIC's direct asymmetric encryption, verify the AES-encrypted data output is non-empty."
            }
        }
    },
    2258: {
        "message": "Supplier GSTIN state code does not match state code passed",
        "reason": "The first two digits of SellerDtls.Gstin represent the State Code. If SellerDtls.StateCode does not match this prefix (e.g., GSTIN starts with '27' for Maharashtra, but StateCode is passed as '29'), the payload is rejected with error 2258.",
        "resolution": "Set SellerDtls.StateCode to strictly match the first two numeric digits of SellerDtls.Gstin.",
        "scenarios": {
            "PREFIX_MISMATCH": {
                "name": "Supplier GSTIN Prefix Mismatch",
                "description": "SellerDtls.StateCode does not match the first two numeric digits of SellerDtls.Gstin.",
                "fix": "Set SellerDtls.StateCode to match the first two digits of SellerDtls.Gstin (e.g. '27' for '27AAAAA0000A1Z5')."
            },
            "SUPPLIER_STATE_MISSING": {
                "name": "Supplier State Code Missing",
                "description": "SellerDtls.StateCode was omitted or blank when SellerDtls.Gstin is provided.",
                "fix": "Populate SellerDtls.StateCode with the first two digits of SellerDtls.Gstin."
            }
        }
    },
    2259: {
        "message": "Invalid supplier state code",
        "reason": "The state code passed in SellerDtls.StateCode is invalid. It must be a 2-digit numeric string from the official GST State Master list ('01' to '38', '97'). Alpha abbreviations, integer types, or nonexistent codes are rejected.",
        "resolution": "Pass a valid 2-digit numeric state code as a string from the official GST State Master ('01' through '38', or '97').",
        "scenarios": {
            "ALPHABETIC_STATE_CODE_PASSED": {
                "name": "Alphabetic State Short Code Passed",
                "description": "State abbreviation like 'MH', 'KA', 'DL' passed instead of numeric code.",
                "fix": "Convert alphabetic abbreviation to 2-digit numeric code (e.g., 'MH' -> '27')."
            },
            "NUMERIC_TYPE_PASSED_INSTEAD_OF_STRING": {
                "name": "Numeric Type Passed Instead of String",
                "description": "State code passed as an integer type (e.g., 27) instead of a string.",
                "fix": "Enclose the 2-digit state code in double quotes as a string ('27')."
            },
            "LEADING_ZERO_OMITTED": {
                "name": "Leading Zero Omitted for Single-Digit State",
                "description": "Single-digit state code passed without leading zero (e.g., '7' instead of '07').",
                "fix": "Prepend a leading zero to single-digit state codes (e.g., '7' -> '07')."
            },
            "NON_EXISTENT_STATE_CODE": {
                "name": "Non-Existent or Invalid State Code",
                "description": "Code does not exist in GST State Master (e.g., '00', '99').",
                "fix": "Use a valid code from official GST State Master ('01' to '38', '97') matching supplier's registration."
            },
            "STATE_CODE_OMITTED_OR_NULL": {
                "name": "Supplier State Code Omitted or Null",
                "description": "SellerDtls.StateCode is null or empty string.",
                "fix": "Provide the 2-digit numeric state code corresponding to the supplier."
            }
        }
    },
    2260: {
        "message": "The recipient state code is invalid",
        "reason": "The recipient state code passed in BuyerDtls.StateCode is invalid. It must be a valid 2-digit numeric string from the official GST master list ('01' to '38', '96', '97'). Alpha codes, single-digit codes without leading zero, or nonexistent codes are rejected.",
        "resolution": "Pass a valid 2-digit numeric state code ('01' through '38', '96', or '97').",
        "scenarios": {
            "ALPHABETIC_STATE_CODE_PASSED": {
                "name": "Alphabetic Recipient State Code Passed",
                "description": "State abbreviation like 'KA', 'DL', 'MH' passed instead of numeric state code.",
                "fix": "Convert alphabetic abbreviation to 2-digit numeric code (e.g. 'KA' -> '29')."
            },
            "LEADING_ZERO_OMITTED": {
                "name": "Leading Zero Omitted for Single-Digit State",
                "description": "Single-digit state passed without leading zero (e.g., '9' or '7').",
                "fix": "Prepend a leading zero to single-digit states ('01' to '09', e.g. '9' -> '09')."
            },
            "NUMERIC_TYPE_PASSED_INSTEAD_OF_STRING": {
                "name": "Numeric Type Passed Instead of String",
                "description": "State code passed as integer type instead of string (e.g., 29).",
                "fix": "Pass state code as a 2-character string ('29')."
            },
            "NON_EXISTENT_OR_INVALID_STATE_CODE": {
                "name": "Non-Existent or Invalid Recipient State Code",
                "description": "Code does not exist in GST master (e.g., '00', '99').",
                "fix": "Provide a valid 2-digit state code from the official GST master."
            },
            "STATE_CODE_OMITTED_OR_NULL": {
                "name": "Recipient State Code Omitted or Null",
                "description": "BuyerDtls.StateCode is null or empty string.",
                "fix": "Provide the 2-digit numeric state code of the recipient."
            }
        }
    },
    2261: {
        "message": "The recipient state code is incorrect for {0} transaction",
        "reason": "Direct export transactions (EXPWP / EXPWOP) cross international borders. For foreign recipients, both StateCode and Pos in BuyerDtls must strictly be set to '96' (Other Countries).",
        "resolution": "Set BuyerDtls.StateCode to '96' for direct export transactions.",
        "scenarios": {
            "DOMESTIC_STATE_CODE_IN_EXPORT": {
                "name": "Domestic State Code in Export",
                "description": "Export invoice (EXPWP / EXPWOP) contains an Indian domestic state code (e.g. '27') instead of '96'.",
                "fix": "Set BuyerDtls.StateCode to '96' (Other Countries) for foreign export recipients."
            },
            "EXPORT_STATE_CODE_OMITTED_OR_NULL": {
                "name": "Export State Code Omitted or Null",
                "description": "BuyerDtls.StateCode is omitted or null in an export transaction.",
                "fix": "Set BuyerDtls.StateCode to '96'."
            },
            "DOMESTIC_SALE_MISCLASSIFIED_AS_EXPORT": {
                "name": "Domestic Sale Misclassified as Export",
                "description": "Domestic sale was erroneously tagged with supply type EXPWP / EXPWOP.",
                "fix": "Change supply type to 'B2B' and retain the domestic state code."
            }
        }
    },
    2262: {
        "message": "For Intra-state supply, IGST cannot be charged",
        "reason": "IgstOnIntra can only be set to 'Y' when SellerDtls.StateCode and BuyerDtls.Pos are identical (an intra-state supply legally attracting IGST). If states are different, the supply is already inter-state; setting IgstOnIntra to 'Y' is invalid.",
        "resolution": "Set TranDtls.IgstOnIntra to 'N' for inter-state supplies, or align Place of Supply (Pos) to match supplier state if the sale is genuinely intra-state.",
        "scenarios": {
            "MISAPPLIED_FLAG_ON_INTER_STATE_SALE": {
                "name": "Misapplied Flag on Inter-State Sale",
                "description": "IgstOnIntra is set to 'Y' on an inter-state sale where Seller State != Buyer POS.",
                "fix": "Set TranDtls.IgstOnIntra to 'N'. Supplies between different states are governed by IGST directly."
            },
            "INTRA_STATE_SALE_WITH_INCORRECT_POS": {
                "name": "Intra-State Sale with Incorrect POS",
                "description": "Transaction is actually an intra-state sale attracting IGST, but BuyerDtls.Pos was erroneously set to an out-of-state code.",
                "fix": "Correct BuyerDtls.Pos to match the supplier's state code."
            }
        }
    },
    2265: {
        "message": "Recipient GSTIN state code does not match state code passed",
        "reason": "The first two digits of BuyerDtls.Gstin represent the State Code (e.g. '29' for Karnataka). BuyerDtls.StateCode must match this prefix exactly.",
        "resolution": "Set BuyerDtls.StateCode to match the first two digits of BuyerDtls.Gstin.",
        "scenarios": {
            "PREFIX_MISMATCH": {
                "name": "Recipient GSTIN Prefix Mismatch",
                "description": "BuyerDtls.StateCode does not match the first two numeric digits of BuyerDtls.Gstin.",
                "fix": "Align BuyerDtls.StateCode to match the first two digits of BuyerDtls.Gstin (e.g., '29' for '29BBBBB0000B1Z2')."
            },
            "RECIPIENT_STATE_MISSING": {
                "name": "Recipient State Code Missing",
                "description": "BuyerDtls.StateCode was omitted or blank when registered BuyerDtls.Gstin was provided.",
                "fix": "Populate BuyerDtls.StateCode with the first two digits of BuyerDtls.Gstin."
            }
        }
    },
    2266: {
        "message": "Item Cess amount does not match calculated value",
        "reason": "Line-item Cess amount must equal (ItemList[i].AssAmt * ItemList[i].CesRt) / 100 within +/- 1.00 tolerance. If non-ad-valorem cess applies, declare it in CesNonAdvlAmt.",
        "resolution": "Recompute CesAmt as (AssAmt * CesRt) / 100, or move quantity-based specific cess to CesNonAdvlAmt.",
        "scenarios": {
            "AD_VALOREM_CESS_CALCULATION_ERROR": {
                "name": "Ad-valorem Cess Calculation Error",
                "description": "Line-item CesAmt does not equal (AssAmt * CesRt) / 100 +/- 1.00.",
                "fix": "Recompute CesAmt = (AssAmt * CesRt) / 100."
            },
            "NON_AD_VALOREM_CESS_DECLARED_AS_AD_VALOREM": {
                "name": "Non-Ad-Valorem Cess Declared as Ad-Valorem",
                "description": "Specific or quantity-based cess was declared under CesAmt while CesRt is 0.",
                "fix": "Move quantity-based cess amount to CesNonAdvlAmt and set CesAmt to 0.00."
            },
            "CESS_RATE_OMITTED_WITH_CESS_AMOUNT": {
                "name": "Cess Rate Omitted with Cess Amount",
                "description": "CesAmt > 0 passed without specifying CesRt.",
                "fix": "Specify applicable ad-valorem cess rate in CesRt."
            }
        }
    },
    2267: {
        "message": "Item State Cess amount does not match calculated value",
        "reason": "Line-item State Cess must satisfy (ItemList[i].AssAmt * ItemList[i].StateCesRt) / 100 within +/- 1.00 tolerance. Quantity-based levies belong to StateCesNonAdvlAmt.",
        "resolution": "Recompute StateCesAmt as (AssAmt * StateCesRt) / 100, or move quantity-based levies to StateCesNonAdvlAmt.",
        "scenarios": {
            "STATE_CESS_FORMULA_MISMATCH": {
                "name": "State Cess Formula Mismatch",
                "description": "Line-item StateCesAmt does not equal (AssAmt * StateCesRt) / 100 +/- 1.00.",
                "fix": "Recompute StateCesAmt = (AssAmt * StateCesRt) / 100."
            },
            "NON_AD_VALOREM_STATE_CESS_DECLARED_AS_AD_VALOREM": {
                "name": "Non-Ad-Valorem State Cess Declared as Ad-Valorem",
                "description": "Quantity-based state cess declared under StateCesAmt while StateCesRt is 0.",
                "fix": "Move quantity-based state cess amount to StateCesNonAdvlAmt and set StateCesAmt to 0.00."
            }
        }
    },
    2268: {
        "message": "IGST on intra-state supply is not applicable to Export/SEZ",
        "reason": "Exports and SEZ transactions are deemed inter-state supplies under Section 7(5) of the IGST Act by default. IgstOnIntra must always be 'N' for EXPWP, EXPWOP, SEZWP, and SEZWOP.",
        "resolution": "Set TranDtls.IgstOnIntra to 'N' for all Export and SEZ transaction types.",
        "scenarios": {
            "INVALID_OVERRIDE_ON_EXPORT_OR_SEZ": {
                "name": "Invalid Override on Export/SEZ",
                "description": "IgstOnIntra='Y' passed on deemed inter-state supply (EXPWP, EXPWOP, SEZWP, SEZWOP).",
                "fix": "Set TranDtls.IgstOnIntra to 'N'. Exports and SEZ transactions are deemed inter-state supplies by law."
            }
        }
    },
    2269: {
        "message": "Recipient state code is incorrect",
        "reason": "Code '96' (Other Countries) is permitted solely for export transactions (EXPWP/EXPWOP). For domestic types (B2B, SEZWP, SEZWOP, DEXP, B2G, B2C), send the buyer's 2-digit Indian State/UT code (01-38, 97).",
        "resolution": "Replace '96' with buyer's 2-digit Indian State/UT code (01-38, 97) matching their registration or physical location.",
        "scenarios": {
            "EXPORT_CODE_USED_ON_DOMESTIC_TYPE": {
                "name": "Export Code Used on Domestic Type",
                "description": "Code '96' passed as StateCode on domestic supply type (B2B, SEZWP, SEZWOP, DEXP).",
                "fix": "Set BuyerDtls.StateCode to buyer's 2-digit Indian State/UT code (01-38, 97)."
            },
            "EXPORT_TRANSACTION_MISCLASSIFIED_AS_DOMESTIC": {
                "name": "Export Transaction Misclassified as Domestic",
                "description": "Sale to foreign customer misclassified as B2B instead of EXPWP/EXPWOP.",
                "fix": "Change supply type to 'EXPWP' or 'EXPWOP' and retain '96'."
            }
        }
    },
    2270: {
        "message": "The Allowed Cancellation Time Limit is Crossed, You Cannot Cancel the IRN",
        "reason": "IRN cancellation requested after the statutory 24-hour window from generation time has elapsed.",
        "resolution": "IRN cannot be cancelled directly via API after 24 hours. Issue a Credit Note (CRN) referencing the original invoice to reverse tax liability, or manually modify/delete the line item in GSTR-1 on the GST Common Portal.",
        "scenarios": {
            "PAST_24_HOURS": {
                "name": "Attempting API Cancellation Past 24 Hours",
                "description": "Calling /Cancel API when Generation Time + 24 hours < Current Time.",
                "fix": "Issue a Credit Note (CRN) referencing the original invoice to reverse tax liability and invoice value."
            },
            "DIRECT_DELETION_ON_GSTR1": {
                "name": "Direct Deletion on GSTR-1 Portal",
                "description": "Trying to force cancel via ERP integration after 24 hours.",
                "fix": "Allow the IRN data to auto-populate into GSTR-1, then manually delete or modify the line item inside GSTR-1 on the GST Common Portal (gst.gov.in)."
            }
        }
    },
    2271: {
        "message": "SHIP TO - State Code is Not Valid State Code for B2B, SEZ and Deemed Export Transactions",
        "reason": "ShipDtls.Stcd is invalid, alphabetic, numeric type, single-digit, nonexistent, or passed as '96' (Other Country) for domestic supply types (B2B, SEZWP, SEZWOP, DEXP), or mismatches ShipDtls.Gstin prefix.",
        "resolution": "For domestic shipments, pass a valid 2-digit Indian State/UT code ('01' to '38', '97') matching ShipDtls.Gstin prefix if present. Do not use '96' for domestic supply types.",
        "scenarios": {
            "EXPORT_COUNTRY_CODE_IN_DOMESTIC": {
                "name": "Export Country Code (96) Passed in Domestic Shipment",
                "description": "Domestic deliveries cannot have an international ship-to state code (96).",
                "fix": "Provide the actual delivery state code ('01' to '38', '97')."
            },
            "ALPHA_CODE_USED": {
                "name": "Alpha Code Used Instead of Numeric String",
                "description": "State codes must be 2-digit numeric strings, never alphabetic short codes like 'MH' or 'KA'.",
                "fix": "Convert alphabetic short code to official 2-digit numeric code."
            },
            "NUMERIC_TYPE_PASSED": {
                "name": "Numeric Integer Type Passed",
                "description": "State code passed as numeric integer instead of 2-digit string.",
                "fix": "Convert numeric integer (e.g., 27) to 2-digit string ('27')."
            },
            "LEADING_ZERO_OMITTED": {
                "name": "Leading Zero Omitted",
                "description": "Single-digit state codes (01 through 09) require a mandatory leading zero.",
                "fix": "Format state code with leading zero (e.g., '7' -> '07')."
            },
            "STATE_CODE_DISAGREES_WITH_GSTIN": {
                "name": "State Code Disagrees with ShipDtls.Gstin",
                "description": "If a registered GSTIN is passed under ShipDtls, Stcd must match the first two digits of that GSTIN.",
                "fix": "Align Stcd to match the first two digits of ShipDtls.Gstin."
            }
        }
    },
    2272: {
        "message": "SHIP TO - PIN Code Cannot Be 999999 for B2B, SEZ and Deemed Export Transactions",
        "reason": "ShipDtls.Pin passed as dummy placeholder 999999 for domestic/SEZ supply types (B2B, SEZWP, SEZWOP, DEXP).",
        "resolution": "Provide the genuine 6-digit postal PIN code of the physical delivery destination recognized by the postal master, or omit ShipDtls if identical to BuyerDtls.",
        "scenarios": {
            "DUMMY_OVERSEAS_PIN_FOR_DOMESTIC": {
                "name": "Dummy Overseas PIN 999999 Used for Domestic Delivery",
                "description": "Postal code 999999 is reserved strictly for overseas addresses in direct exports. Domestic deliveries require an authentic 6-digit Indian postal PIN.",
                "fix": "Provide the genuine 6-digit postal PIN code of the physical delivery destination."
            },
            "STRING_DATA_TYPE_PASSED": {
                "name": "String Data Type Passed",
                "description": "Pin in ShipDtls must be a numeric integer, not a string.",
                "fix": "Cast Pin to a 6-digit numeric integer (e.g., 411001)."
            },
            "SEZ_CAMPUS_DELIVERY_DUMMY_PIN": {
                "name": "SEZ Campus Delivery Passed with Dummy PIN",
                "description": "SEZ zones are located within Indian territorial borders and possess valid Indian postal PIN codes.",
                "fix": "Provide authentic Indian postal PIN code for the SEZ delivery campus."
            },
            "REDUNDANT_SHIP_TO_WITH_DUMMY": {
                "name": "Ship-To Address Redundant with Buyer Address",
                "description": "ShipDtls included solely to mirror BuyerDtls, but populated with fallback dummy defaults (999999).",
                "fix": "Omit the ShipDtls block entirely or populate with BuyerDtls.Pin."
            }
        }
    },
    2273: {
        "message": "Dispatch from PIN code cannot be 999999",
        "reason": "DispDtls.Pin passed as dummy placeholder 999999. Goods dispatched from within India must originate from an authentic physical location possessing a genuine 6-digit postal PIN code.",
        "resolution": "Provide the authentic 6-digit Indian postal PIN code of the physical dispatch premises, or populate from SellerDtls.Pin if dispatching from principal place of business.",
        "scenarios": {
            "DUMMY_PIN_ON_DISPATCH_POINT": {
                "name": "Dummy PIN on Indian Dispatch Point",
                "description": "Goods dispatched from within India must have an authentic 6-digit postal PIN code. 999999 is strictly rejected for physical dispatch points.",
                "fix": "Provide the authentic 6-digit postal PIN code of the physical dispatch location."
            },
            "EXPORT_TRANSACTION_DISPATCH_DUMMY": {
                "name": "Export Transaction Erroneously Passed 999999 on Dispatch",
                "description": "Direct export rules mandate 999999 only for foreign BuyerDtls. Indian dispatch locations still require authentic Indian postal PINs.",
                "fix": "Set DispDtls.Pin to the authentic Indian postal PIN code of the dispatch warehouse."
            },
            "STRING_DATA_TYPE_PASSED": {
                "name": "String Data Type Passed",
                "description": "Pin in DispDtls must be a 6-digit numeric integer, not a string.",
                "fix": "Cast Pin to a 6-digit numeric integer (e.g., 400705)."
            }
        }
    },
    2274: {
        "message": "Recipient PIN code cannot be 999999 for {0} transaction.",
        "reason": "BuyerDtls.Pin passed as 999999 on domestic transaction category (B2B, SEZWP, SEZWOP, DEXP). Domestic recipients reside within Indian territorial borders and require authentic 6-digit Indian PIN codes.",
        "resolution": "Provide the genuine 6-digit Indian postal PIN code of the domestic recipient recognized by the postal master list.",
        "scenarios": {
            "OVERSEAS_PIN_ON_DOMESTIC_BUYER": {
                "name": "Overseas PIN Used on Domestic Buyer",
                "description": "For domestic transactions (B2B, SEZWP, SEZWOP, DEXP), the buyer resides in India. Pass the recipient's real 6-digit Indian PIN code; 999999 is rejected.",
                "fix": "Provide the recipient's authentic 6-digit Indian postal PIN code."
            },
            "SEZ_BUYER_PASSED_WITH_DUMMY_PIN": {
                "name": "SEZ Buyer Passed with Dummy PIN",
                "description": "SEZ units/developers are located within Indian territorial borders. Passing 999999 for SEZWP/SEZWOP is rejected under Rule 2274.",
                "fix": "Provide the authentic Indian postal PIN code of the SEZ delivery campus."
            },
            "STRING_DATA_TYPE_PASSED": {
                "name": "String Data Type Passed",
                "description": "Pin in BuyerDtls must be a 6-digit numeric integer, not a string.",
                "fix": "Cast Pin to a 6-digit numeric integer (e.g., 560001)."
            }
        }
    },
    2275: {
        "message": "Recipient PIN code should be 999999 for Direct Export",
        "reason": "BuyerDtls.Pin is not set to 999999 for direct export supply types (EXPWP, EXPWOP). Foreign recipient addresses require 999999 in the central IRP schema.",
        "resolution": "Set BuyerDtls.Pin strictly to 999999 when trancatg is EXPWP or EXPWOP.",
        "scenarios": {
            "DOMESTIC_PIN_ON_EXPORT_BUYER": {
                "name": "Domestic PIN on Direct Export Buyer",
                "description": "Direct cross-border export (EXPWP/EXPWOP) requires recipient PIN to be set specifically to 999999. Passing a domestic Indian PIN code is rejected.",
                "fix": "Set BuyerDtls.Pin = 999999."
            },
            "FOREIGN_ZIP_PASSED_DIRECTLY": {
                "name": "Foreign ZIP Code Passed Directly into Pin Field",
                "description": "Foreign postal codes (e.g. US 5-digit ZIP 94105) cannot be passed in BuyerDtls.Pin; the schema strictly requires 999999.",
                "fix": "Set BuyerDtls.Pin = 999999 and retain foreign postal code in address or remarks."
            },
            "STRING_DATA_TYPE_PASSED": {
                "name": "String Data Type Passed",
                "description": "Pin in BuyerDtls must be a numeric integer 999999.",
                "fix": "Cast Pin to numeric integer 999999."
            }
        }
    },
    2276: {
        "message": "Supplier PIN code cannot be 999999",
        "reason": "SellerDtls.Pin passed as dummy placeholder 999999. Every GST-registered supplier is an Indian entity with a verified principal place of business possessing a valid 6-digit Indian PIN.",
        "resolution": "Provide the registered 6-digit Indian postal PIN code of the supplier entity.",
        "scenarios": {
            "DUMMY_PIN_ON_REGISTERED_SUPPLIER": {
                "name": "Dummy PIN on Registered Supplier",
                "description": "Every GST-registered supplier is an Indian entity with a verified principal or additional place of business. 999999 is completely invalid in SellerDtls.",
                "fix": "Pass the registered 6-digit postal PIN code of the supplier."
            },
            "EXPORT_TRANSACTION_SUPPLIER_DUMMY": {
                "name": "Export Transaction Erroneously Passed 999999 on Seller",
                "description": "Export supply type does not alter the domestic status of the supplier. SellerDtls.Pin must never be 999999.",
                "fix": "Pass the supplier's authentic 6-digit registered Indian PIN code."
            },
            "STRING_DATA_TYPE_PASSED": {
                "name": "String Data Type Passed",
                "description": "Pin in SellerDtls must be a 6-digit numeric integer, not a string.",
                "fix": "Cast Pin to a 6-digit numeric integer (e.g., 400601)."
            }
        }
    },
    2278: {
        "message": "Document number cannot be reused after IRN cancellation",
        "reason": "Attempting to generate an IRN with a document number (DocDtls.No + Typ + FY) whose prior IRN was cancelled. Once an IRN is generated and cancelled, that document number is permanently locked in the central registry.",
        "resolution": "The IRP will never allow re-generation against that exact document number. A new, distinct invoice number must be issued by the ERP (e.g., appending a revision suffix '-A' or generating the next sequential invoice number).",
        "scenarios": {
            "REUSING_CANCELLED_DOCUMENT_NUMBER": {
                "name": "Re-generation on Cancelled Document Number",
                "description": "Once an IRN is generated and subsequently cancelled, the specific document number (DocDtls.No + Typ + Financial Year) is permanently locked in the central registry. The IRP will never allow re-generation against that exact document number.",
                "fix": "Issue a new, distinct invoice number from the ERP (e.g., 'INV/2026/001-A')."
            },
            "ERP_AUTOMATED_RETRY_AFTER_CANCELLATION": {
                "name": "ERP Automated Retry Queue Resubmitting Cancelled Invoice",
                "description": "Automated ERP integration queue attempting to push the original invoice payload after human operator cancelled the original IRN.",
                "fix": "Deactivate retry for the cancelled document and generate a new billing document number in ERP."
            }
        }
    },
    2280: {
        "message": "Invalid document type",
        "reason": "document_type is not one of INV, CRN, DBN",
        "resolution": "Pass valid document_type ('INV', 'CRN', 'DBN')"
    },
    2281: {
        "message": "Invalid document number",
        "reason": "docno exceeds 16 chars or contains invalid characters",
        "resolution": "docno must be 1-16 characters (alphanumeric, '/', '-')"
    },
    2282: {
        "message": "Invalid document date format",
        "reason": "docdt format is not DD/MM/YYYY or DD-MM-YYYY",
        "resolution": "Format docdt as DD-MM-YYYY or DD/MM/YYYY"
    },
    2285: {
        "message": "Field length exceeds permitted character constraints or is out of range",
        "reason": "A mandatory or optional field length violated NIC schema boundary",
        "resolution": "Ensure field length conforms to official NIC character length constraints"
    },
    2288: {
        "message": "Invalid recipient GSTIN",
        "reason": "Buyer GSTIN format is invalid or length is not 15 characters (or URP)",
        "resolution": "Provide valid 15-character recipient GSTIN or URP"
    },
    2289: {
        "message": "Invalid supplier GSTIN",
        "reason": "Supplier GSTIN or self_gstin length is not 15 characters or format mismatch",
        "resolution": "Provide valid 15-character supplier GSTIN"
    },
    2294: {
        "message": "Reverse charge is mandatory if IGST on intra is applicable",
        "reason": "igstonintra='Y' requires reversecharge='Y'",
        "resolution": "Set reversecharge = 'Y' when igstonintra = 'Y'"
    },
    2298: {
        "message": "Recipient cannot be composition/UIN taxpayer for Deemed Exports",
        "reason": "Deemed export cannot be issued to composition dealer or UIN holder",
        "resolution": "Ensure recipient is a regular registered taxpayer"
    },
    2303: {
        "message": "For B2B transactions, buyer POS can be foreign country(96) only for Goods Transport Services",
        "reason": "POS is 96 for B2B but items are not transportation services (9965/9968)",
        "resolution": "Change POS to domestic state code unless service is goods transport"
    },
    2307: {
        "message": "Future date cannot be accepted",
        "reason": "Invoice date or reference date is in the future",
        "resolution": "Ensure dates are today or earlier"
    },
    3039: {
        "message": "Pincode -{1} of {0} does not belong to his/her State - {2}",
        "reason": "Pincode prefix does not match the State code passed for supplier",
        "resolution": "Ensure PIN code belongs to the specified State code"
    },
    3041: {
        "message": "Buyer or Ship Details: Pincode -{0} does not belong to the state-{1}",
        "reason": "Pincode prefix does not match the State code passed for Buyer or Ship location",
        "resolution": "Ensure Buyer/Ship PIN code belongs to the corresponding state"
    }
}

# ============================================================================
# 5. NIC E-WAY BILL ERROR CATALOG (Codes 4000 to 4076)
# ============================================================================

EWB_ERRORS: Dict[int, Dict[str, str]] = {
    4000: {"message": "Status of the IRN is not active"},
    4001: {"message": "Error occurred while creating Eway Bill"},
    4002: {"message": "EwayBill is already generated for this IRN"},
    4009: {"message": "E Way Bill can be generated provided at least HSN of one item belongs to goods."},
    4010: {"message": "E-way Bill cannot generated for Debit Note, Credit Note and Services."},
    4011: {"message": "Vehicle number should be passed in case of transportation mode is Road."},
    4012: {"message": "The transport document number should be passed for transportation modes air and rail"},
    4013: {"message": "The distance between the pincodes given is too high or low."},
    4014: {"message": "Invalid Vehicle Number"},
    4016: {"message": "Transport document date cannot be a future date"},
    4018: {"message": "Invalid Transporter ID"},
    4019: {"message": "Provide Transporter ID in order to generate Part A of e-Way Bill"},
    4020: {"message": "Invalid vehicle type ."},
    4021: {"message": "Transporter document date cannot be earlier than the invoice date."},
    4022: {"message": "vehicle type should be passed in case of transportation mode is Road."},
    4023: {"message": "The transport document date should be passed for of transportation modes air and rail."},
    4024: {"message": "Vehicle type should not be ODC when transmode is other than road and ship"},
    4027: {"message": "Transporter Id is mandatory for generation of Part A slip"},
    4028: {"message": "Transport mode is mandatory as Vehicle Number/Transport Document Number is given"},
    4029: {"message": "Valid distance to be sent in case of same pin codes, you cannot send 0 as distance in this case."},
    4031: {"message": "Ship to details are mandatory for export transactions to generate e-Way Bill."},
    4032: {"message": "Ship to state code cannot be other country code(96) for e-Way Bill generation"},
    4033: {"message": "Ship to PIN code cannot be 999999 for e-Way Bill generation"},
    4034: {"message": "Since you passed Supplier/Recepient/Dispatch from/Ship to Pincode as 999999, distance cannot be 0"},
    4035: {"message": "Dispatch state code cannot be other country code(96) for e-Way Bill generation"},
    4036: {"message": "Dispatch PIN code cannot be 999999 for e-Way Bill generation"},
    4039: {"message": "Vehicle type can not be regular when transport mode is ship"},
    4040: {"message": "For Ship Transport, either vehicle number or transport document number is required"},
    4073: {"message": "Ship-to GSTIN is not required as the transaction type is {0}"},
    4074: {"message": "Ship-to GSTIN is mandatory for the transaction type {0}"},
    4075: {"message": "Invalid ship-to GSTIN"},
    4076: {"message": "Bill-to and ship-to GSTIN should not be same for this transaction type"}
}

# ============================================================================
# 6. VALIDATION REGEX PATTERNS & ERROR CLASS
# ============================================================================

GSTIN_REGEX = r"^[0-9]{2}[0-9A-Z]{13}$"
DATE_REGEX_DASH = r"^[0-3][0-9]-[0-1][0-9]-[2][0][1-2][0-9]$"
DATE_REGEX_ANY = r"^[0-3][0-9][/-][0-1][0-9][/-]20[1-2][0-9]$"
PORT_REGEX = r"^[0-9A-Z]{6,10}$"
VEH_REGEX = r"^[A-Z]{2}[0-9]{2}[A-Z0-9]{1,2}[0-9]{4}$"
IFSC_REGEX = r"^[A-Z]{4}0[A-Z0-9]{6}$"
UPI_REGEX = r"^[\w\.\-]+@[a-zA-Z]{2,}$"
TRANS_ID_REGEX = r"^[0-9]{2}[A-Z0-9]{13}$"


class ValidationError:
    """Represents a specific NIC compliance error mapped directly to error codes."""
    def __init__(self, code: int, field: str, custom_message: Optional[str] = None):
        self.code = code
        self.field = field

        info = IRN_ERRORS.get(code) or EWB_ERRORS.get(code) or {}
        default_msg = info.get("message", f"Validation failure code {code}")

        self.message = custom_message if custom_message else default_msg
        self.reason = info.get("reason", "")
        self.resolution = info.get("resolution", "")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_code": self.code,
            "field": self.field,
            "message": self.message,
            "reason": self.reason,
            "resolution": self.resolution
        }


def validate_nic_2day_rule(
    docdt: Union[str, date, datetime],
    reference_date: Optional[Union[str, date]] = None
) -> Optional[Dict[str, Any]]:
    """
    Enforces the NIC e-Invoice rule: Document date cannot be more than 2 days prior
    to the current date / generation date.
    Returns compliance error dict if violation is detected, None if compliant.
    """
    inv_date = None
    if isinstance(docdt, (datetime, date)):
        inv_date = docdt if isinstance(docdt, date) else docdt.date()
    elif isinstance(docdt, str) and docdt.strip():
        s = docdt.strip()
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%d.%m.%Y"):
            try:
                inv_date = datetime.strptime(s, fmt).date()
                break
            except ValueError:
                continue

    if not inv_date:
        return None

    ref_d = date.today()
    if reference_date:
        if isinstance(reference_date, (datetime, date)):
            ref_d = reference_date if isinstance(reference_date, date) else reference_date.date()
        elif isinstance(reference_date, str):
            for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
                try:
                    ref_d = datetime.strptime(reference_date.strip(), fmt).date()
                    break
                except ValueError:
                    continue

    days_diff = (ref_d - inv_date).days
    if days_diff > 2:
        return {
            "error_code": 2164,
            "field": "docdt1.docdt",
            "message": f"Document date '{inv_date.strftime('%Y-%m-%d')}' is more than 2 days old ({days_diff} days ago). As per NIC rule, IRN cannot be generated or changed for invoices older than 2 days. Prompt: change the date.",
            "reason": f"NIC Rule: IRN generation/modification is strictly restricted when invoice date is older than 2 days (exceeded by {days_diff - 2} days).",
            "resolution": "Please change the document date (docdt) to within the last 2 days of current date (Prompt: change the date)."
        }

    return None


# ============================================================================
# 7. GST RULES ENGINE & VALIDATOR CLASS
# ============================================================================

class RulesEngine:
    """
    Unified Pre-API Validation and Rules Engine for Indian GST E-Invoice & E-Way Bill Payloads.
    Covers every key field, key field length, and key field value validation.
    """

    @classmethod
    def validate_invoice(cls, invoice: Dict[str, Any]) -> List[Dict[str, Any]]:
        errors: List[ValidationError] = []

        # Rule 2255: Requested Payload is Empty
        if not invoice or not isinstance(invoice, dict):
            diag_2255 = classify_rule_2255_diagnostic(raw_body=invoice) if classify_rule_2255_diagnostic else None
            msg = f": {diag_2255['reason']}" if diag_2255 else ""
            return [ValidationError(2255, "payload", f"Requested payload is empty{msg}").to_dict()]

        # ---------------------------------------------------------
        # Section 0: Header & GSTIN Length Validations (self_gstin)
        # ---------------------------------------------------------
        self_gstin = str(invoice.get("self_gstin", "") or "").strip().upper()
        if not self_gstin:
            errors.append(ValidationError(2289, "self_gstin", "self_gstin cannot be blank or null"))
        elif self_gstin == "URP":
            is_rcm = bool(invoice.get("is_rcm_inward") or invoice.get("is_rcm_inward_upload"))
            is_dummy = bool(invoice.get("is_dummy_testing") or invoice.get("dummy_data_testing"))
            diag_2213 = classify_rule_2213_diagnostic(
                seller_gstin=self_gstin,
                is_rcm_inward=is_rcm,
                is_dummy_testing=is_dummy
            ) if classify_rule_2213_diagnostic else None
            diag_msg = f": {diag_2213['reason']}" if diag_2213 else "The supplier GSTIN cannot be URP."
            errors.append(ValidationError(2213, "self_gstin", f"The supplier GSTIN cannot be URP{diag_msg}"))
        elif len(self_gstin) != 15:
            errors.append(ValidationError(2289, "self_gstin", f"Invalid self_gstin length ({len(self_gstin)}). Must be exactly 15 characters."))
        elif not self_gstin[:2].isdigit():
            errors.append(ValidationError(2289, "self_gstin", "self_gstin state code (first 2 digits) must be numeric."))
        elif not re.match(GSTIN_REGEX, self_gstin):
            errors.append(ValidationError(2289, "self_gstin", f"Invalid self_gstin format '{self_gstin}'. Must be 15-character alphanumeric GSTIN."))

        sys_cd = str(invoice.get("system_cd", "") or "").strip()
        if sys_cd and len(sys_cd) > 50:
            errors.append(ValidationError(2285, "system_cd", f"system_cd exceeds max length of 50 characters. Got: {len(sys_cd)}"))

        branch_cd = str(invoice.get("branch_cd", "") or "").strip()
        if branch_cd and len(branch_cd) > 50:
            errors.append(ValidationError(2285, "branch_cd", f"branch_cd exceeds max length of 50 characters. Got: {len(branch_cd)}"))

        vertical_cd = str(invoice.get("vertical_cd", "") or "").strip()
        if vertical_cd and len(vertical_cd) > 50:
            errors.append(ValidationError(2285, "vertical_cd", f"vertical_cd exceeds max length of 50 characters. Got: {len(vertical_cd)}"))

        irnreq = str(invoice.get("irnreq", "") or "").strip().upper()
        if irnreq and irnreq not in ["Y", "N"]:
            errors.append(ValidationError(2285, "irnreq", f"Invalid irnreq '{irnreq}'. Must be 'Y' or 'N'."))

        # ---------------------------------------------------------
        # Section 1: Document Details (docdt1)
        # ---------------------------------------------------------
        docdt1 = invoice.get("docdt1", {}) if isinstance(invoice.get("docdt1"), dict) else invoice
        doc_type = str(docdt1.get("document_type", "") or "").strip().upper()
        docno = str(docdt1.get("docno", "") or "").strip()
        docdt_str = str(docdt1.get("docdt", "") or "").strip()

        if not doc_type:
            errors.append(ValidationError(2280, "docdt1.document_type", "document_type is mandatory and cannot be blank"))
        elif doc_type not in ALLOWED_DOC_TYPES:
            errors.append(ValidationError(2280, "docdt1.document_type", f"Invalid document_type '{doc_type}'. Expected {ALLOWED_DOC_TYPES}"))

        if not docno:
            errors.append(ValidationError(2281, "docdt1.docno", "docno is mandatory and cannot be blank"))
        elif len(docno) > 16:
            errors.append(ValidationError(2281, "docdt1.docno", f"docno exceeds max length of 16. Current length: {len(docno)}"))
        elif not re.match(r"^[0-9A-Za-z/-]+$", docno):
            errors.append(ValidationError(2281, "docdt1.docno", f"Invalid docno '{docno}'. Alphanumeric with '/' and '-' only."))

        # Rule 2278: Document number cannot be reused after IRN cancellation
        is_canc_reuse = bool(invoice.get("is_cancelled_reuse"))
        canc_registry = invoice.get("cancelled_doc_registry")
        if is_canc_reuse or canc_registry:
            if classify_rule_2278_diagnostic:
                diag_2278 = classify_rule_2278_diagnostic(
                    docno=docno,
                    doc_type=doc_type,
                    is_cancelled_reuse=is_canc_reuse,
                    cancelled_doc_registry=canc_registry,
                    supplier_gstin=invoice.get("self_gstin")
                )
                if not diag_2278["is_valid"]:
                    errors.append(ValidationError(2278, "docdt1.docno", f"Document number cannot be reused after IRN cancellation (Rule 2278): {diag_2278['reason']}"))
            else:
                errors.append(ValidationError(2278, "docdt1.docno", f"Document number '{docno}' was previously cancelled and cannot be reused."))

        inv_date = None
        if not docdt_str:
            errors.append(ValidationError(2282, "docdt1.docdt", "docdt (Document Date) is mandatory and cannot be blank"))
        else:
            for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
                try:
                    inv_date = datetime.strptime(docdt_str, fmt)
                    break
                except ValueError:
                    continue
            if not inv_date:
                errors.append(ValidationError(2282, "docdt1.docdt", f"Invalid docdt format '{docdt_str}'. Expected date normalized to DD-MM-YYYY."))
            else:
                today_ist = get_ist_today() if get_ist_today else datetime.now().date()
                if inv_date.date() > today_ist:
                    is_utc = bool(invoice.get("is_utc_context") or invoice.get("utc_desync") or invoice.get("server_utc"))
                    diag = classify_future_date_diagnostic(inv_date.date(), raw_str=docdt_str, server_today=today_ist, is_utc_context=is_utc) if classify_future_date_diagnostic else None
                    reason_msg = diag["reason"] if diag else "Document date cannot exceed the current server calendar day. Set to today's date or earlier."
                    errors.append(ValidationError(2163, "docdt1.docdt", f"The document date should not be future date. {reason_msg}"))
                else:
                    days_diff = (today_ist - inv_date.date()).days
                    irn_req = str(invoice.get("irnreq", "Y") or "Y").strip().upper()
                    if days_diff > 2 and irn_req == "Y":
                        errors.append(ValidationError(
                            2164,
                            "docdt1.docdt",
                            f"Document date '{docdt_str}' is more than 2 days old ({days_diff} days ago). As per NIC rule, IRN cannot be generated or changed for invoices older than 2 days. Prompt: change the date."
                        ))

        orginvno = str(docdt1.get("orginvno", "") or "").strip()
        if orginvno and len(orginvno) > 16:
            errors.append(ValidationError(2281, "docdt1.orginvno", f"orginvno exceeds max length of 16. Current length: {len(orginvno)}"))

        orginvdt = str(docdt1.get("orginvdt", "") or "").strip()
        if orginvdt:
            valid_orgdt = False
            for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
                try:
                    datetime.strptime(orginvdt, fmt)
                    valid_orgdt = True
                    break
                except ValueError:
                    continue
            if not valid_orgdt:
                errors.append(ValidationError(2282, "docdt1.orginvdt", f"Invalid orginvdt format '{orginvdt}'. Expected DD-MM-YYYY."))

        # ---------------------------------------------------------
        # Section 2: Transaction Details (trandt1) & SEZ Rules
        # ---------------------------------------------------------
        trandt1 = invoice.get("trandt1", {}) if isinstance(invoice.get("trandt1"), dict) else invoice
        trancatg = str(trandt1.get("trancatg", "B2B") or "B2B").strip().upper()
        reversecharge = str(trandt1.get("reversecharge", "N") or "N").strip().upper()
        transactionmode = str(trandt1.get("transactionmode", "REG") or "REG").strip().upper()
        igstonintra = str(trandt1.get("igstonintra", "N") or "N").strip().upper()
        refclm = str(trandt1.get("refclm", "") or "").strip().upper()

        if not trancatg:
            errors.append(ValidationError(2159, "trandt1.trancatg", "Transaction Category (trancatg) cannot be blank"))
        elif trancatg not in ALLOWED_TRAN_CATG:
            errors.append(ValidationError(2159, "trandt1.trancatg", f"Invalid trancatg '{trancatg}'. Must be one of {ALLOWED_TRAN_CATG}"))

        is_sez = trancatg in ("SEZWP", "SEZWOP")
        is_export = trancatg in ("EXP", "EXPWP", "EXPWOP")
        is_deemed_exp = trancatg == "DEXP"

        if reversecharge not in ["Y", "N"]:
            errors.append(ValidationError(2159, "trandt1.reversecharge", f"Invalid reversecharge '{reversecharge}'. Must be 'Y' or 'N'"))
        elif trancatg != "B2B" and reversecharge == "Y":
            exp_sec = invoice.get("expdt1") or invoice.get("expdtl") or {}
            w_pay = exp_sec.get("wthpay") if isinstance(exp_sec, dict) else None
            msg = get_reverse_charge_rejection_reason(trancatg, w_pay) if get_reverse_charge_rejection_reason else f"Reverse Charge is not applicable for transaction category '{trancatg}'."
            errors.append(ValidationError(2162, "trandt1.reversecharge", msg))

        if transactionmode not in ["REG", "DIS", "SHP", "CMB"]:
            errors.append(ValidationError(2285, "trandt1.transactionmode", f"Invalid transactionmode '{transactionmode}'. Must be REG, DIS, SHP, or CMB"))

        if igstonintra not in ["Y", "N"]:
            errors.append(ValidationError(2285, "trandt1.igstonintra", f"Invalid igstonintra '{igstonintra}'. Must be 'Y' or 'N'"))
        elif igstonintra == "Y" and reversecharge != "Y":
            errors.append(ValidationError(2294, "trandt1.reversecharge", "Reverse charge is mandatory if IGST on intra is applicable."))
        elif (is_export or is_sez) and igstonintra == "Y":
            errors.append(ValidationError(2268, "trandt1.igstonintra", f"IGST on intra state supply is not applicable to {trancatg} transactions."))

        if refclm and refclm not in ["Y", "N"]:
            errors.append(ValidationError(2285, "trandt1.refclm", f"Invalid refclm value '{refclm}'. Must be 'Y' or 'N'"))

        # ---------------------------------------------------------
        # Section 3: Supplier Details (supplierdt1) & Full Field Validation
        # ---------------------------------------------------------
        sup_raw = invoice.get("supplierdt1") or invoice.get("supplier") or invoice.get("SellerDtls")
        sup = sup_raw if isinstance(sup_raw, dict) else (invoice.get("supplierdt1", {}) if isinstance(invoice.get("supplierdt1"), dict) else invoice)
        sup_gstin = str(sup.get("supplier_gstin", sup.get("gstin", sup.get("Gstin", ""))) or "").strip().upper()
        sup_lglnm = str(sup.get("supplier_lglnm", sup.get("lglnm", sup.get("LglNm", ""))) or "").strip()
        sup_trdnm = str(sup.get("supplier_trdnm", sup.get("trdnm", sup.get("TrdNm", ""))) or "").strip()
        sup_bno = str(sup.get("supplier_bno", sup.get("bno", sup.get("Bno", ""))) or "").strip()
        sup_bnm = str(sup.get("supplier_bnm", sup.get("bnm", sup.get("Bnm", ""))) or "").strip()
        sup_flno = str(sup.get("supplier_flno", sup.get("flno", sup.get("Flno", ""))) or "").strip()
        sup_loc = str(sup.get("supplier_loc", sup.get("loc", sup.get("Loc", ""))) or "").strip()
        sup_dst = str(sup.get("supplier_dst", sup.get("dst", sup.get("Dst", ""))) or "").strip()
        sup_pin = str(sup.get("supplier_pin", sup.get("pin", sup.get("Pin", ""))) or "").strip()
        raw_sup_state = sup.get("supplier_state", sup.get("state", sup.get("StateCode")))
        sup_state = str(raw_sup_state if raw_sup_state is not None else (sup_gstin[:2] if len(sup_gstin) >= 2 else "")).strip()
        if sup_state.isdigit() and len(sup_state) == 1:
            sup_state = sup_state.zfill(2)
        sup_phone = str(sup.get("supplier_phone", sup.get("phone", "")) or "").strip()
        sup_email = str(sup.get("supplier_email", sup.get("email", "")) or "").strip().lower()
        cust_cd = str(sup.get("cust_cd", invoice.get("cust_cd", "")) or "").strip()

        # Supplier GSTIN checks
        is_rcm = bool(invoice.get("is_rcm_inward") or invoice.get("is_rcm_inward_upload"))
        is_dummy = bool(invoice.get("is_dummy_testing") or invoice.get("dummy_data_testing"))
        if not sup_gstin:
            errors.append(ValidationError(2289, "supplierdt1.supplier_gstin", "supplier_gstin cannot be blank or null"))
        elif sup_gstin == "URP" or self_gstin == "URP" or is_rcm or is_dummy:
            diag_2213 = classify_rule_2213_diagnostic(
                seller_gstin=sup_gstin,
                is_rcm_inward=is_rcm,
                is_dummy_testing=is_dummy,
                supplier_state=sup_state,
                doc_type=doc_type,
                trancatg=trancatg,
            ) if classify_rule_2213_diagnostic else None
            diag_msg = f": {diag_2213['reason']}" if diag_2213 else "The supplier GSTIN cannot be URP."
            errors.append(ValidationError(2213, "supplierdt1.supplier_gstin", f"The supplier GSTIN cannot be URP{diag_msg}"))
        elif len(sup_gstin) != 15:
            errors.append(ValidationError(2289, "supplierdt1.supplier_gstin", f"Invalid supplier_gstin length ({len(sup_gstin)}). Must be exactly 15 characters."))
        elif not sup_gstin[:2].isdigit():
            errors.append(ValidationError(2289, "supplierdt1.supplier_gstin", "supplier_gstin state code (first 2 digits) must be numeric."))
        elif not re.match(GSTIN_REGEX, sup_gstin):
            errors.append(ValidationError(2289, "supplierdt1.supplier_gstin", f"Invalid supplier_gstin format '{sup_gstin}'. Must be 15-character alphanumeric GSTIN."))
        elif sup_gstin[:2] != sup_state:
            diag_2258 = classify_rule_2258_diagnostic(
                supplier_gstin=sup_gstin,
                supplier_state=raw_sup_state if raw_sup_state is not None else sup_state
            ) if classify_rule_2258_diagnostic else None
            msg = f": {diag_2258['reason']}" if diag_2258 else f"Supplier state code '{sup_state}' does not match first 2 digits of GSTIN '{sup_gstin[:2]}'."
            errors.append(ValidationError(2258, "supplierdt1.supplier_state", f"Supplier GSTIN state code does not match state code passed{msg}"))

        # Cross check self_gstin vs supplier_gstin
        if self_gstin and sup_gstin and self_gstin != sup_gstin:
            errors.append(ValidationError(2289, "self_gstin", f"self_gstin '{self_gstin}' does not match supplier_gstin '{sup_gstin}'."))

        # Check Rule 2231: Cannot Generate e-Invoice as Supplier GSTIN is SEZ
        is_supplier_sez = bool(
            sup.get("is_sez")
            or sup.get("is_supplier_sez")
            or sup.get("is_sez_supplier")
            or invoice.get("is_supplier_sez")
            or invoice.get("is_sez_supplier")
            or invoice.get("supplier_is_sez")
            or "SEZ" in sup_gstin
            or "SEZ" in self_gstin
        )
        is_dta_to_sez = bool(
            invoice.get("is_dta_to_sez")
            or trancatg in ("SEZWP", "SEZWOP")
        )
        is_multi_gstin = bool(invoice.get("is_multi_gstin_setup") or invoice.get("is_multi_gstin"))

        if is_supplier_sez or is_multi_gstin:
            buy_raw_tmp = invoice.get("buyerdt1") or invoice.get("buyer") or invoice.get("BuyerDtls") or {}
            buy_gstin_tmp = str(buy_raw_tmp.get("buyer_gstin", buy_raw_tmp.get("gstin", buy_raw_tmp.get("Gstin", ""))) or "").strip().upper()
            diag_2231 = classify_rule_2231_diagnostic(
                supplier_gstin=sup_gstin,
                is_supplier_sez=is_supplier_sez,
                trancatg=trancatg,
                buyer_gstin=buy_gstin_tmp,
                is_dta_to_sez=is_dta_to_sez,
                is_multi_gstin_setup=is_multi_gstin,
            ) if classify_rule_2231_diagnostic else None
            if diag_2231 and not diag_2231.get("is_valid"):
                errors.append(ValidationError(2231, "supplierdt1.supplier_gstin", f"Cannot Generate e-Invoice as Supplier GSTIN is SEZ: {diag_2231['reason']}"))

        # Supplier Names & Address lengths
        if not sup_lglnm:
            errors.append(ValidationError(2285, "supplierdt1.supplier_lglnm", "supplier_lglnm is mandatory and cannot be blank"))
        elif not (3 <= len(sup_lglnm) <= 100):
            errors.append(ValidationError(2285, "supplierdt1.supplier_lglnm", f"supplier_lglnm length must be 3-100 characters. Current: {len(sup_lglnm)}"))

        if sup_trdnm and not (3 <= len(sup_trdnm) <= 100):
            errors.append(ValidationError(2285, "supplierdt1.supplier_trdnm", f"supplier_trdnm length must be 3-100 characters. Current: {len(sup_trdnm)}"))

        if sup_bno and len(sup_bno) > 60:
            errors.append(ValidationError(2285, "supplierdt1.supplier_bno", f"supplier_bno exceeds max length of 60. Current: {len(sup_bno)}"))

        if not sup_bnm:
            errors.append(ValidationError(2285, "supplierdt1.supplier_bnm", "supplier_bnm is mandatory and cannot be blank"))
        elif not (3 <= len(sup_bnm) <= 100):
            errors.append(ValidationError(2285, "supplierdt1.supplier_bnm", f"supplier_bnm length must be 3-100 characters. Current: {len(sup_bnm)}"))

        if sup_flno and not (3 <= len(sup_flno) <= 100):
            errors.append(ValidationError(2285, "supplierdt1.supplier_flno", f"supplier_flno length must be 3-100 characters. Current: {len(sup_flno)}"))

        if not sup_loc:
            errors.append(ValidationError(2285, "supplierdt1.supplier_loc", "supplier_loc is mandatory"))
        elif not (3 <= len(sup_loc) <= 50):
            errors.append(ValidationError(2285, "supplierdt1.supplier_loc", f"supplier_loc length must be 3-50. Current: {len(sup_loc)}"))

        if sup_dst and len(sup_dst) > 60:
            errors.append(ValidationError(2285, "supplierdt1.supplier_dst", f"supplier_dst exceeds max length of 60. Current: {len(sup_dst)}"))

        # Supplier PIN code & Cross-State matching (Error 3039)
        if not sup_pin:
            errors.append(ValidationError(2285, "supplierdt1.supplier_pin", "supplier_pin is mandatory"))
        elif sup_pin == "999999":
            if classify_rule_2276_diagnostic:
                diag_2276 = classify_rule_2276_diagnostic(
                    seller_pin=sup_pin,
                    trancatg=trancatg,
                    seller_state=sup_state,
                    seller_gstin=sup_gstin
                )
                errors.append(ValidationError(2276, "supplierdt1.supplier_pin", f"Supplier PIN code cannot be 999999 (Rule 2276): {diag_2276['reason']}"))
            else:
                errors.append(ValidationError(2276, "supplierdt1.supplier_pin", "Supplier PIN code cannot be 999999."))
        elif len(sup_pin) != 6 or not sup_pin.isdigit():
            errors.append(ValidationError(3038, "supplierdt1.supplier_pin", f"Supplier PIN must be exactly 6 digits. Got: {len(sup_pin)}"))
        elif not verify_pincode_state(sup_pin, sup_state):
            state_name = STATE_MASTER.get(sup_state, {}).get("name", sup_state)
            errors.append(ValidationError(3039, "supplierdt1.supplier_pin", f"Pincode '{sup_pin}' of supplier does not belong to State '{sup_state}' ({state_name})."))

        diag_2259 = classify_rule_2259_diagnostic(
            supplier_state=raw_sup_state if raw_sup_state is not None else sup_state,
            supplier_gstin=sup_gstin
        ) if classify_rule_2259_diagnostic else None
        if diag_2259 and not diag_2259["is_valid"]:
            errors.append(ValidationError(2259, "supplierdt1.supplier_state", f"Invalid supplier state code: {diag_2259['reason']}"))
        elif not sup_state:
            errors.append(ValidationError(2259, "supplierdt1.supplier_state", "supplier_state is mandatory"))
        elif len(sup_state) != 2:
            errors.append(ValidationError(2259, "supplierdt1.supplier_state", f"supplier_state must be exactly 2 digits (e.g., '12'). Got: {len(sup_state)}"))

        if sup_phone and len(sup_phone) != 10:
            errors.append(ValidationError(2285, "supplierdt1.supplier_phone", f"supplier_phone must be 10 digits. Got: {len(sup_phone)}"))

        if sup_email:
            if not (10 <= len(sup_email) <= 50):
                errors.append(ValidationError(2285, "supplierdt1.supplier_email", f"supplier_email length must be 10-50. Current: {len(sup_email)}"))
            if "@" not in sup_email or "." not in sup_email:
                errors.append(ValidationError(2285, "supplierdt1.supplier_email", "Invalid email format for supplier_email"))

        if cust_cd and len(cust_cd) > 30:
            errors.append(ValidationError(2285, "cust_cd", f"cust_cd exceeds max length of 30. Current: {len(cust_cd)}"))

        # ---------------------------------------------------------
        # Section 4: Buyer Details (buyerdt1) & Full Field Validation
        # ---------------------------------------------------------
        buy_raw = invoice.get("buyerdt1") or invoice.get("buyer") or invoice.get("BuyerDtls")
        buy = buy_raw if isinstance(buy_raw, dict) else (invoice.get("buyerdt1", {}) if isinstance(invoice.get("buyerdt1"), dict) else invoice)
        buy_gstin = str(buy.get("buyer_gstin", buy.get("gstin", buy.get("Gstin", ""))) or "").strip().upper()
        buy_lglnm = str(buy.get("buyer_lglnm", buy.get("lglnm", buy.get("LglNm", ""))) or "").strip()
        buy_trdnm = str(buy.get("buyer_trdnm", buy.get("trdnm", buy.get("TrdNm", ""))) or "").strip()
        buy_bno = str(buy.get("buyer_bno", buy.get("bno", buy.get("Bno", ""))) or "").strip()
        buy_bnm = str(buy.get("buyer_bnm", buy.get("bnm", buy.get("Bnm", ""))) or "").strip()
        buy_flno = str(buy.get("buyer_flno", buy.get("flno", buy.get("Flno", ""))) or "").strip()
        buy_loc = str(buy.get("buyer_loc", buy.get("loc", buy.get("Loc", ""))) or "").strip()
        buy_dst = str(buy.get("buyer_dst", buy.get("dst", buy.get("Dst", ""))) or "").strip()
        buy_pin = str(buy.get("buyer_pin", buy.get("pin", buy.get("Pin", ""))) or "").strip()
        buy_state = str(buy.get("buyer_state", buy.get("state", buy.get("StateCode", (buy_gstin[:2] if len(buy_gstin) >= 2 else "")))) or "").strip().zfill(2)
        pos = str(buy.get("pos", buy.get("Pos", buy.get("buyer_pos", invoice.get("pos", "")))) or "").strip().zfill(2)
        buy_phone = str(buy.get("buyer_phone", buy.get("phone", "")) or "").strip()
        buy_email = str(buy.get("buyer_email", buy.get("email", "")) or "").strip().lower()

        # Buyer GSTIN checks
        if not buy_gstin:
            errors.append(ValidationError(2288, "buyerdt1.buyer_gstin", "buyer_gstin is mandatory and cannot be blank"))
        else:
            if not (3 <= len(buy_gstin) <= 15):
                errors.append(ValidationError(2288, "buyerdt1.buyer_gstin", f"buyer_gstin length must be 3-15 chars. Got: {len(buy_gstin)}"))
            if buy_gstin != "URP":
                if len(buy_gstin) != 15:
                    errors.append(ValidationError(2288, "buyerdt1.buyer_gstin", f"Invalid buyer_gstin length ({len(buy_gstin)}). Must be 15-digit GSTIN or 'URP'"))
                elif not buy_gstin[:2].isdigit():
                    errors.append(ValidationError(2288, "buyerdt1.buyer_gstin", "buyer_gstin state code (first 2 digits) must be numeric."))
                elif not re.match(GSTIN_REGEX, buy_gstin):
                    errors.append(ValidationError(2288, "buyerdt1.buyer_gstin", f"Invalid buyer_gstin format '{buy_gstin}'. Must be 15-digit GSTIN or 'URP'"))

            if is_export:
                diag_2248 = classify_rule_2248_diagnostic(
                    buyer_gstin=buy_gstin,
                    trancatg=trancatg,
                    is_export=is_export,
                    is_domestic_sale=bool(invoice.get("is_domestic_sale") or invoice.get("is_domestic_misclassified_as_export"))
                ) if classify_rule_2248_diagnostic else None
                if diag_2248 and not diag_2248["is_valid"]:
                    errors.append(ValidationError(2248, "buyerdt1.buyer_gstin", f"Recipient has to be URP in case of Export transactions: {diag_2248['reason']}"))
                elif buy_gstin != "URP":
                    errors.append(ValidationError(2248, "buyerdt1.buyer_gstin", "Recipient has to be URP in case of Export transactions."))
            else:
                if (is_sez or trancatg in ["B2B", "B2G"]) and buy_gstin == "URP":
                    if classify_rule_2212_diagnostic:
                        urp_diag = classify_rule_2212_diagnostic(
                            buyer_gstin=buy_gstin,
                            trancatg=trancatg,
                            buyer_pos=pos,
                            buyer_state=buy_state,
                            buyer_name=buy_lglnm,
                            is_export_foreign=False
                        )
                        if not urp_diag["is_valid"]:
                            errors.append(ValidationError(2212, "buyerdt1.buyer_gstin", urp_diag["reason"]))
                    else:
                        errors.append(ValidationError(2212, "buyerdt1.buyer_gstin", f"buyer_gstin cannot be 'URP' for transaction category '{trancatg}'."))

        # Rule 2246: Recipient Cannot Be SEZ for Supply Type
        is_sez_buyer_entity = bool(
            buy.get("is_sez")
            or buy.get("is_sez_buyer")
            or buy.get("is_sez_unit")
            or invoice.get("buyer_is_sez")
            or (buy_gstin in KNOWN_SEZ_BUYER_GSTINS)
        )
        if is_sez_buyer_entity and trancatg not in ("SEZWP", "SEZWOP"):
            diag_2246 = classify_rule_2246_diagnostic(
                buyer_gstin=buy_gstin,
                trancatg=trancatg,
                is_sez_buyer=is_sez_buyer_entity,
                dta_gstin=invoice.get("dta_gstin"),
                is_dta_sale=bool(invoice.get("is_dta_sale"))
            ) if classify_rule_2246_diagnostic else None
            if diag_2246 and not diag_2246["is_valid"]:
                errors.append(ValidationError(2246, "buyerdt1.buyer_gstin", f"Recipient cannot be SEZ for - {trancatg} transaction: {diag_2246['reason']}"))

        # Rule 2247: Recipient Should Be SEZ for Transaction
        if trancatg in ("SEZWP", "SEZWOP") and not is_sez_buyer_entity:
            diag_2247 = classify_rule_2247_diagnostic(
                buyer_gstin=buy_gstin,
                trancatg=trancatg,
                is_sez_buyer=is_sez_buyer_entity,
                is_dta_sale=bool(invoice.get("is_dta_sale")),
                sez_gstin=invoice.get("sez_gstin"),
                is_portal_sync_lag=bool(invoice.get("is_portal_sync_lag"))
            ) if classify_rule_2247_diagnostic else None
            if diag_2247 and not diag_2247["is_valid"]:
                errors.append(ValidationError(2247, "buyerdt1.buyer_gstin", f"Recipient should be SEZ for - {trancatg} transaction: {diag_2247['reason']}"))

        # Self-invoicing check
        if sup_gstin and buy_gstin and sup_gstin == buy_gstin:
            if classify_rule_2211_diagnostic:
                is_sb = bool(invoice.get("is_sandbox") or invoice.get("sandbox") or invoice.get("testing_env"))
                self_diag = classify_rule_2211_diagnostic(
                    supplier_gstin=sup_gstin,
                    buyer_gstin=buy_gstin,
                    doc_type=doc_type,
                    reversecharge=reversecharge,
                    trancatg=trancatg,
                    buyer_pos=pos,
                    buyer_state=buy_state,
                    is_sandbox=is_sb
                )
                if not self_diag["is_valid"]:
                    errors.append(ValidationError(2211, "buyerdt1.buyer_gstin", self_diag["reason"]))
            else:
                errors.append(ValidationError(2211, "buyerdt1.buyer_gstin", "Supplier and recipient GSTIN should not be the same."))

        # Buyer Names & Address lengths
        if not buy_lglnm:
            errors.append(ValidationError(2285, "buyerdt1.buyer_lglnm", "buyer_lglnm is mandatory and cannot be blank"))
        elif not (3 <= len(buy_lglnm) <= 100):
            errors.append(ValidationError(2285, "buyerdt1.buyer_lglnm", f"buyer_lglnm length must be 3-100 characters. Current: {len(buy_lglnm)}"))

        if buy_trdnm and not (3 <= len(buy_trdnm) <= 100):
            errors.append(ValidationError(2285, "buyerdt1.buyer_trdnm", f"buyer_trdnm length must be 3-100 characters. Current: {len(buy_trdnm)}"))

        if buy_bno and len(buy_bno) > 60:
            errors.append(ValidationError(2285, "buyerdt1.buyer_bno", f"buyer_bno exceeds max length of 60. Current: {len(buy_bno)}"))

        if not buy_bnm:
            errors.append(ValidationError(2285, "buyerdt1.buyer_bnm", "buyer_bnm is mandatory and cannot be blank"))
        elif not (3 <= len(buy_bnm) <= 100):
            errors.append(ValidationError(2285, "buyerdt1.buyer_bnm", f"buyer_bnm length must be 3-100 characters. Current: {len(buy_bnm)}"))

        if buy_flno and not (3 <= len(buy_flno) <= 100):
            errors.append(ValidationError(2285, "buyerdt1.buyer_flno", f"buyer_flno length must be 3-100 characters. Current: {len(buy_flno)}"))

        if not buy_loc:
            errors.append(ValidationError(2285, "buyerdt1.buyer_loc", "buyer_loc is mandatory"))
        elif not (3 <= len(buy_loc) <= 100):
            errors.append(ValidationError(2285, "buyerdt1.buyer_loc", f"buyer_loc length must be 3-100. Current: {len(buy_loc)}"))

        if buy_dst and len(buy_dst) > 60:
            errors.append(ValidationError(2285, "buyerdt1.buyer_dst", f"buyer_dst exceeds max length of 60. Current: {len(buy_dst)}"))

        # Buyer PIN code & POS validations
        raw_pin_val = buy.get("buyer_pin", buy.get("pin", buy.get("Pin")))
        diag_2244 = classify_rule_2244_diagnostic(
            pin=raw_pin_val,
            trancatg=trancatg,
            buyer_state=buy_state,
            buyer_gstin=buy_gstin,
            is_export=is_export
        ) if classify_rule_2244_diagnostic else None
        if diag_2244 and not diag_2244["is_valid"] and diag_2244.get("scenario") != "STRING_TYPE_PASSED_INSTEAD_OF_INTEGER":
            errors.append(ValidationError(2244, "buyerdt1.buyer_pin", f"Recipient pincode is not provided for the transaction: {diag_2244['reason']}"))
        elif not buy_pin:
            errors.append(ValidationError(2244, "buyerdt1.buyer_pin", "buyer_pin is mandatory"))
        elif len(buy_pin) != 6 or not buy_pin.isdigit():
            errors.append(ValidationError(3038, "buyerdt1.buyer_pin", f"buyer_pin must be exactly 6 digits. Got: {len(buy_pin)}"))
        elif is_export:
            if buy_pin != "999999":
                if classify_rule_2275_diagnostic:
                    diag_2275 = classify_rule_2275_diagnostic(buyer_pin=buy_pin, trancatg=trancatg, buyer_state=buy_state)
                    errors.append(ValidationError(2275, "buyerdt1.buyer_pin", f"Recipient PIN code should be 999999 for Direct Export (Rule 2275): {diag_2275['reason']}"))
                else:
                    errors.append(ValidationError(2275, "buyerdt1.buyer_pin", "Recipient PIN code should be 999999 for Direct Export."))
        else:
            if buy_pin == "999999":
                if classify_rule_2274_diagnostic:
                    diag_2274 = classify_rule_2274_diagnostic(buyer_pin=buy_pin, trancatg=trancatg, buyer_state=buy_state, buyer_gstin=buy_gstin)
                    errors.append(ValidationError(2274, "buyerdt1.buyer_pin", f"Recipient PIN code cannot be 999999 for {trancatg} transaction (Rule 2274): {diag_2274['reason']}"))
                else:
                    errors.append(ValidationError(2274, "buyerdt1.buyer_pin", f"Recipient PIN code cannot be 999999 for {trancatg} transaction."))
            elif not verify_pincode_state(buy_pin, buy_state):
                state_name = STATE_MASTER.get(buy_state, {}).get("name", buy_state)
                errors.append(ValidationError(3041, "buyerdt1.buyer_pin", f"Buyer Pincode '{buy_pin}' does not belong to State '{buy_state}' ({state_name})."))

        raw_buy_state = buy.get("buyer_state", buy.get("state", buy.get("StateCode")))
        diag_2260 = classify_rule_2260_diagnostic(
            buyer_state=raw_buy_state if raw_buy_state is not None else buy_state,
            buyer_gstin=buy_gstin,
            trancatg=trancatg
        ) if classify_rule_2260_diagnostic else None
        if diag_2260 and not diag_2260["is_valid"]:
            errors.append(ValidationError(2260, "buyerdt1.buyer_state", f"The recipient state code is invalid: {diag_2260['reason']}"))
        elif not buy_state:
            errors.append(ValidationError(2260, "buyerdt1.buyer_state", "buyer_state is mandatory"))
        elif len(buy_state) != 2:
            errors.append(ValidationError(2260, "buyerdt1.buyer_state", f"buyer_state must be 2 digits. Got: {len(buy_state)}"))
        elif is_export:
            is_dom_exp = bool(invoice.get("is_domestic_sale") or invoice.get("is_domestic_misclassified_as_export") or buy.get("is_domestic_sale"))
            diag_2261 = classify_rule_2261_diagnostic(
                buyer_state=raw_buy_state if raw_buy_state is not None else buy_state,
                trancatg=trancatg,
                is_export=is_export,
                is_domestic_sale=is_dom_exp,
                buyer_gstin=buy_gstin
            ) if classify_rule_2261_diagnostic else None
            if diag_2261 and not diag_2261["is_valid"]:
                errors.append(ValidationError(2261, "buyerdt1.buyer_state", f"The recipient state code is incorrect for {trancatg} transaction: {diag_2261['reason']}"))
            elif buy_state != "96":
                errors.append(ValidationError(2261, "buyerdt1.buyer_state", "Recipient state code must be 96 for Export transactions."))
        elif not is_export and buy_state == "96":
            diag_2269 = classify_rule_2269_diagnostic(
                buyer_state=buy_state,
                trancatg=trancatg,
                buyer_gstin=buy_gstin,
                is_actual_export=bool(invoice.get("is_export_overseas") or invoice.get("is_overseas_client"))
            ) if classify_rule_2269_diagnostic else None
            msg = f": {diag_2269['reason']}" if diag_2269 else ""
            errors.append(ValidationError(2269, "buyerdt1.buyer_state", f"Recipient state code is incorrect{msg}"))
        elif not is_export and buy_gstin != "URP" and len(buy_gstin) == 15:
            diag_2265 = classify_rule_2265_diagnostic(
                buyer_gstin=buy_gstin,
                buyer_state=raw_buy_state if raw_buy_state is not None else buy_state
            ) if classify_rule_2265_diagnostic else None
            if diag_2265 and not diag_2265["is_valid"]:
                errors.append(ValidationError(2265, "buyerdt1.buyer_state", f"Recipient GSTIN state code does not match state code passed: {diag_2265['reason']}"))
            elif buy_gstin[:2] != buy_state:
                errors.append(ValidationError(2265, "buyerdt1.buyer_state", f"Recipient state code '{buy_state}' does not match GSTIN prefix '{buy_gstin[:2]}'."))

        raw_pos_val = buy.get("pos", buy.get("buyer_pos", invoice.get("pos", buy.get("Pos"))))
        if is_export and (pos != "96" or (isinstance(raw_pos_val, (int, float)) and not isinstance(raw_pos_val, bool))):
            is_gw = bool(invoice.get("is_gateway_port_used") or invoice.get("gateway_port_pos"))
            is_dom_mis = bool(invoice.get("is_domestic_misclassified_as_export") or invoice.get("domestic_misclassified"))
            diag_2232 = classify_rule_2232_diagnostic(
                pos=raw_pos_val,
                trancatg=trancatg,
                seller_state=sup_state,
                port=invoice.get("expdt1", {}).get("port") if isinstance(invoice.get("expdt1"), dict) else None,
                is_gateway_port_used=is_gw,
                is_domestic_misclassified_as_export=is_dom_mis,
                recipient_state=buy_state,
            ) if classify_rule_2232_diagnostic else None
            msg = f": {diag_2232['reason']}" if diag_2232 else ""
            errors.append(ValidationError(2232, "buyerdt1.pos", f"POS is incorrect for Export transaction{msg}"))
        else:
            diag_2243 = classify_rule_2243_diagnostic(
                pos=raw_pos_val,
                trancatg=trancatg,
                buyer_state=buy_state,
                buyer_gstin=buy_gstin,
                is_export=is_export
            ) if classify_rule_2243_diagnostic else None
            if diag_2243 and not diag_2243["is_valid"]:
                errors.append(ValidationError(2243, "buyerdt1.pos", f"POS code is invalid: {diag_2243['reason']}"))
            elif not pos:
                errors.append(ValidationError(2243, "buyerdt1.pos", "pos is mandatory and cannot be blank"))
            elif len(pos) != 2 or not pos.isdigit():
                errors.append(ValidationError(2243, "buyerdt1.pos", f"pos must be exactly 2 digits numeric. Got: '{pos}'"))
            elif not is_export and pos == "96":
                diag_2242 = classify_rule_2242_diagnostic(
                    pos=pos,
                    trancatg=trancatg,
                    buyer_state=buy_state,
                    buyer_gstin=buy_gstin,
                    is_sez=is_sez,
                    is_export_overseas=bool(invoice.get("is_export_overseas") or invoice.get("is_overseas_client"))
                ) if classify_rule_2242_diagnostic else None
                msg = f": {diag_2242['reason']}" if diag_2242 else ""
                errors.append(ValidationError(2242, "buyerdt1.pos", f"Recipient POS is incorrect for transaction type {trancatg}{msg}"))

        if buy_phone and len(buy_phone) != 10:
            errors.append(ValidationError(2285, "buyerdt1.buyer_phone", f"buyer_phone must be exactly 10 digits. Got: {len(buy_phone)}"))

        if buy_email:
            if not (10 <= len(buy_email) <= 50):
                errors.append(ValidationError(2285, "buyerdt1.buyer_email", f"buyer_email length must be 10-50 characters. Current: {len(buy_email)}"))
            if "@" not in buy_email or "." not in buy_email:
                errors.append(ValidationError(2285, "buyerdt1.buyer_email", f"Invalid email format for buyer_email: '{buy_email}'"))

        if igstonintra == "Y":
            if is_export or is_sez:
                diag_2268 = classify_rule_2268_diagnostic(
                    igstonintra=igstonintra,
                    trancatg=trancatg
                ) if classify_rule_2268_diagnostic else None
                msg = f": {diag_2268['reason']}" if diag_2268 else ""
                errors.append(ValidationError(2268, "trandt1.igstonintra", f"IGST on intra-state supply is not applicable to Export/SEZ{msg}"))
            else:
                is_act_intra = bool(invoice.get("is_actual_intra") or invoice.get("is_actual_local_sale"))
                diag_2262 = classify_rule_2262_diagnostic(
                    igstonintra=igstonintra,
                    seller_state=sup_state,
                    pos=pos,
                    is_actual_intra=is_act_intra
                ) if classify_rule_2262_diagnostic else None
                if diag_2262 and not diag_2262["is_valid"]:
                    errors.append(ValidationError(2262, "trandt1.igstonintra", f"For Intra-state supply, IGST cannot be charged: {diag_2262['reason']}"))
                elif sup_state != pos:
                    errors.append(ValidationError(2262, "trandt1.igstonintra", f"For Intra-state supply, IGST cannot be charged. Supplier state ({sup_state}) != POS ({pos})."))

        # ---------------------------------------------------------
        # Section 5: Export & Port / Currency Master Validation
        # ---------------------------------------------------------
        exp = invoice.get("expdt1") if isinstance(invoice.get("expdt1"), dict) else (invoice if is_export else None)
        if exp and is_export:
            port = str(exp.get("port", "") or "").strip().upper()
            cntcode = str(exp.get("cntcode", "") or "").strip().upper()
            forcur = str(exp.get("forcur", "") or "").strip().upper()
            expcat = str(exp.get("expcat", "") or "").strip().upper()
            wthpay = str(exp.get("wthpay", "") or "").strip().upper()
            shipbno = str(exp.get("shipbno", "") or "").strip()
            shipbdt = str(exp.get("shipbdt", "") or "").strip()
            invforcur = str(exp.get("invforcur", "") or "").strip()
            expduty = str(exp.get("expduty", "") or "").strip()

            if not cntcode:
                errors.append(ValidationError(2202, "expdt1.cntcode", "cntcode is mandatory when trancatg is 'EXP'"))
            elif len(cntcode) != 2:
                errors.append(ValidationError(2202, "expdt1.cntcode", f"Invalid cntcode length. Got: '{cntcode}' (Expected 2)"))
            elif cntcode not in COUNTRY_MASTER:
                errors.append(ValidationError(2202, "expdt1.cntcode", f"Invalid Country Code '{cntcode}'. Must be valid 2-letter ISO country code."))

            if not forcur:
                errors.append(ValidationError(2203, "expdt1.forcur", "forcur is mandatory when trancatg is 'EXP'"))
            elif cntcode in COUNTRY_CURRENCY_MAP:
                expected_curr = COUNTRY_CURRENCY_MAP.get(cntcode)
                if forcur != expected_curr:
                    errors.append(ValidationError(2203, "expdt1.forcur", f"Mismatch: Country '{cntcode}' uses '{expected_curr}', but found '{forcur}'"))

            if not expcat and trancatg == "EXP":
                errors.append(ValidationError(2285, "expdt1.expcat", "expcat is mandatory when trancatg is 'EXP'"))
            elif expcat and expcat not in ["DIR", "DEM", "SEZ", "SED"]:
                errors.append(ValidationError(2285, "expdt1.expcat", f"Invalid expcat '{expcat}'. Must be DIR, DEM, SEZ, or SED."))

            if not wthpay and trancatg == "EXP":
                errors.append(ValidationError(2285, "expdt1.wthpay", "wthpay is mandatory when trancatg is 'EXP'"))
            elif wthpay and wthpay not in ["Y", "N"]:
                errors.append(ValidationError(2285, "expdt1.wthpay", f"Invalid wthpay '{wthpay}'. Must be 'Y' or 'N'."))

            if shipbno and not (7 <= len(shipbno) <= 20):
                errors.append(ValidationError(2285, "expdt1.shipbno", f"shipbno must be 7-20 chars. Current: {len(shipbno)}"))

            if shipbdt and not re.match(DATE_REGEX_ANY, shipbdt):
                errors.append(ValidationError(2282, "expdt1.shipbdt", f"Invalid shipbdt format '{shipbdt}'. Expected DD/MM/YYYY or DD-MM-YYYY."))

            if classify_rule_2201_diagnostic:
                port_diag = classify_rule_2201_diagnostic(
                    port=port,
                    trancatg=trancatg,
                    transmode=invoice.get("transmode") or invoice.get("trans_mode") or invoice.get("transport_mode") or "1",
                    is_export=True
                )
                if not port_diag["is_valid"]:
                    errors.append(ValidationError(2201, "expdt1.port", port_diag["reason"]))
            elif port:
                if not (6 <= len(port) <= 10):
                    errors.append(ValidationError(2201, "expdt1.port", f"port code must be 6-10 chars. Current: {len(port)}"))
                elif not re.match(PORT_REGEX, port):
                    errors.append(ValidationError(2201, "expdt1.port", f"Invalid port code format '{port}'."))

            if invforcur:
                try:
                    val = float(invforcur)
                    if val < 0:
                        errors.append(ValidationError(2285, "expdt1.invforcur", "invforcur cannot be negative"))
                    parts = invforcur.split(".")
                    if len(parts[0]) > 14 or (len(parts) > 1 and len(parts[1]) > 2):
                        errors.append(ValidationError(2285, "expdt1.invforcur", "invforcur exceeds max precision (14.2)"))
                except ValueError:
                    errors.append(ValidationError(2285, "expdt1.invforcur", f"invforcur must be numeric. Got: '{invforcur}'"))

            if expduty:
                try:
                    val = float(expduty)
                    if val < 0:
                        errors.append(ValidationError(2285, "expdt1.expduty", "expduty cannot be negative"))
                    parts = expduty.split(".")
                    if len(parts[0]) > 14 or (len(parts) > 1 and len(parts[1]) > 2):
                        errors.append(ValidationError(2285, "expdt1.expduty", "expduty exceeds max precision (14.2)"))
                except ValueError:
                    errors.append(ValidationError(2285, "expdt1.expduty", f"expduty must be numeric. Got: '{expduty}'"))

        elif not is_export:
            # Forbidden export fields for non-export transactions & Rule 2201 validation
            exp_check = invoice.get("expdt1") or invoice.get("ExpDtls") or invoice.get("exp_details") or invoice.get("export") or {}
            if isinstance(exp_check, dict):
                exp_port_val = exp_check.get("port") or exp_check.get("Port") or exp_check.get("port_code")
                if exp_port_val:
                    if classify_rule_2201_diagnostic:
                        port_diag = classify_rule_2201_diagnostic(
                            port=exp_port_val,
                            trancatg=trancatg,
                            is_export=False
                        )
                        if not port_diag["is_valid"]:
                            errors.append(ValidationError(2201, "expdt1.port", port_diag["reason"]))
                    else:
                        errors.append(ValidationError(2201, "expdt1.port", "ExpDtls (including Port) is only applicable for Export (EXPWP, EXPWOP) transactions."))
                for f_name in ["expcat", "wthpay", "forcur", "cntcode"]:
                    if exp_check.get(f_name):
                        errors.append(ValidationError(2285, f"expdt1.{f_name}", f"{f_name} must be empty when trancatg is '{trancatg}'"))

        # ---------------------------------------------------------
        # Section 6: Dispatch Details (dispdt1) & Shipping Details (shipdtl)
        # ---------------------------------------------------------
        disp = invoice.get("dispdt1") or invoice.get("DispDtls") or invoice.get("disp_details") or invoice.get("dispatch")
        if disp and isinstance(disp, dict):
            disp_gstin = str(disp.get("disp_gstin", disp.get("gstin", disp.get("Gstin", ""))) or "").strip().upper()
            disp_trdnm = str(disp.get("disp_trdnm", disp.get("trdnm", disp.get("TrdNm", disp.get("nm", disp.get("Nm", ""))))) or "").strip()
            disp_bno = str(disp.get("disp_bno", disp.get("bno", disp.get("Bno", ""))) or "").strip()
            disp_bnm = str(disp.get("disp_bnm", disp.get("bnm", disp.get("Bnm", ""))) or "").strip()
            disp_flno = str(disp.get("disp_flno", disp.get("flno", disp.get("Flno", ""))) or "").strip()
            disp_loc = str(disp.get("disp_loc", disp.get("loc", disp.get("Loc", ""))) or "").strip()
            disp_dst = str(disp.get("disp_dst", disp.get("dst", disp.get("Dst", ""))) or "").strip()
            disp_pin = str(disp.get("disp_pin", disp.get("pin", disp.get("Pin", ""))) or "").strip()
            raw_disp_state = str(disp.get("disp_state", disp.get("stcd", disp.get("Stcd", disp.get("state", "")))) or "").strip()
            disp_state = raw_disp_state.zfill(2) if (raw_disp_state.isdigit() and len(raw_disp_state) == 1) else raw_disp_state
            disp_phone = str(disp.get("disp_phone", disp.get("phone", disp.get("Phone", ""))) or "").strip()
            disp_email = str(disp.get("disp_email", disp.get("email", disp.get("Email", ""))) or "").strip().lower()

            if disp_gstin and disp_gstin != "URP":
                if not (3 <= len(disp_gstin) <= 15):
                    errors.append(ValidationError(2200, "dispdt1.disp_gstin", f"disp_gstin length must be 3-15 chars. Got: {len(disp_gstin)}"))
                elif len(disp_gstin) != 15:
                    errors.append(ValidationError(2200, "dispdt1.disp_gstin", f"Invalid disp_gstin length ({len(disp_gstin)}). Must be 15 characters."))
                elif not disp_gstin[:2].isdigit():
                    errors.append(ValidationError(2200, "dispdt1.disp_gstin", "disp_gstin state code (first 2 digits) must be numeric"))
                elif not re.match(GSTIN_REGEX, disp_gstin):
                    errors.append(ValidationError(2200, "dispdt1.disp_gstin", f"Invalid disp_gstin format '{disp_gstin}'. Must be 15-digit GSTIN or 'URP'"))

            # Rule 2200 Dispatch State Code Validation
            if raw_disp_state:
                if classify_rule_2200_diagnostic:
                    disp_diag = classify_rule_2200_diagnostic(
                        stcd=raw_disp_state,
                        gstin=disp_gstin,
                        pin=disp_pin,
                        loc=disp_loc,
                        section="DispDtls"
                    )
                    if not disp_diag["is_valid"]:
                        errors.append(ValidationError(2200, "dispdt1.disp_state", disp_diag["reason"]))
                elif not raw_disp_state.isdigit() or len(raw_disp_state) != 2 or raw_disp_state not in VALID_STATE_CODES or raw_disp_state in ("00", "99"):
                    errors.append(ValidationError(2200, "dispdt1.disp_state", f"Invalid state code '{raw_disp_state}' for dispatch details."))

            if transactionmode in ["DIS", "CMB"]:
                if not disp_trdnm:
                    errors.append(ValidationError(2285, "dispdt1.disp_trdnm", f"disp_trdnm is mandatory when transactionmode is '{transactionmode}'"))
                elif not (3 <= len(disp_trdnm) <= 100):
                    errors.append(ValidationError(2285, "dispdt1.disp_trdnm", f"disp_trdnm length must be 3-100 characters. Current: {len(disp_trdnm)}"))

                if not disp_bnm:
                    errors.append(ValidationError(2285, "dispdt1.disp_bnm", f"disp_bnm is mandatory when transactionmode is '{transactionmode}'"))
                elif not (3 <= len(disp_bnm) <= 100):
                    errors.append(ValidationError(2285, "dispdt1.disp_bnm", f"disp_bnm length must be 3-100 characters. Current: {len(disp_bnm)}"))

                if not disp_loc:
                    errors.append(ValidationError(2285, "dispdt1.disp_loc", f"disp_loc is mandatory when transactionmode is '{transactionmode}'"))
                elif not (3 <= len(disp_loc) <= 100):
                    errors.append(ValidationError(2285, "dispdt1.disp_loc", f"disp_loc length must be 3-100 characters. Current: {len(disp_loc)}"))

                if not disp_pin:
                    errors.append(ValidationError(2285, "dispdt1.disp_pin", f"disp_pin is mandatory when transactionmode is '{transactionmode}'"))
                elif len(disp_pin) != 6 or not disp_pin.isdigit():
                    errors.append(ValidationError(3038, "dispdt1.disp_pin", f"disp_pin must be exactly 6 digits. Got: {len(disp_pin)}"))

                if not disp_state:
                    errors.append(ValidationError(2200, "dispdt1.disp_state", f"disp_state is mandatory when transactionmode is '{transactionmode}'"))
                elif len(disp_state) != 2:
                    errors.append(ValidationError(2200, "dispdt1.disp_state", f"disp_state must be exactly 2 digits. Got: {len(disp_state)}"))

            if disp_bno and len(disp_bno) > 60:
                errors.append(ValidationError(2285, "dispdt1.disp_bno", f"disp_bno exceeds max length of 60 characters. Current: {len(disp_bno)}"))
            if disp_flno and not (3 <= len(disp_flno) <= 100):
                errors.append(ValidationError(2285, "dispdt1.disp_flno", f"disp_flno length must be 3-100 characters. Current: {len(disp_flno)}"))
            if disp_dst and len(disp_dst) > 60:
                errors.append(ValidationError(2285, "dispdt1.disp_dst", f"disp_dst exceeds max length of 60 characters. Current: {len(disp_dst)}"))
            if disp_phone and len(disp_phone) != 10:
                errors.append(ValidationError(2285, "dispdt1.disp_phone", f"disp_phone must be exactly 10 digits. Got: {len(disp_phone)}"))
            if disp_email:
                if not (10 <= len(disp_email) <= 50):
                    errors.append(ValidationError(2285, "dispdt1.disp_email", f"disp_email length must be 10-50 characters. Current: {len(disp_email)}"))
                if "@" not in disp_email or "." not in disp_email:
                    errors.append(ValidationError(2285, "dispdt1.disp_email", f"Invalid email format for disp_email: '{disp_email}'"))

            if disp_pin == "999999":
                if classify_rule_2273_diagnostic:
                    diag_2273 = classify_rule_2273_diagnostic(
                        disp_pin=disp_pin,
                        trancatg=trancatg,
                        seller_pin=sup_pin,
                        disp_state=disp_state
                    )
                    errors.append(ValidationError(2273, "dispdt1.disp_pin", f"Dispatch from PIN code cannot be 999999 (Rule 2273): {diag_2273['reason']}"))
                else:
                    errors.append(ValidationError(2273, "dispdt1.disp_pin", "Dispatch from PIN code cannot be 999999."))
            elif disp_pin and disp_state and not verify_pincode_state(disp_pin, disp_state):
                errors.append(ValidationError(3041, "dispdt1.disp_pin", f"Dispatch PIN '{disp_pin}' does not belong to State '{disp_state}'."))

        ship = invoice.get("shipdtl") or invoice.get("shipdt1") or invoice.get("ShipDtls") or invoice.get("ship_details") or invoice.get("shipping")
        if ship and isinstance(ship, dict):
            ship_gstin = str(ship.get("ship_gstin", ship.get("gstin", ship.get("Gstin", ""))) or "").strip().upper()
            ship_lglnm = str(ship.get("ship_lglnm", ship.get("lglnm", ship.get("LglNm", ship.get("nm", ship.get("Nm", ""))))) or "").strip()
            ship_trdnm = str(ship.get("ship_trdnm", ship.get("trdnm", ship.get("TrdNm", ""))) or "").strip()
            ship_bno = str(ship.get("ship_bno", ship.get("bno", ship.get("Bno", ""))) or "").strip()
            ship_bnm = str(ship.get("ship_bnm", ship.get("bnm", ship.get("Bnm", ""))) or "").strip()
            ship_flno = str(ship.get("ship_flno", ship.get("flno", ship.get("Flno", ""))) or "").strip()
            ship_loc = str(ship.get("ship_loc", ship.get("loc", ship.get("Loc", ""))) or "").strip()
            ship_dst = str(ship.get("ship_dst", ship.get("dst", ship.get("Dst", ""))) or "").strip()
            ship_pin = str(ship.get("ship_pin", ship.get("pin", ship.get("Pin", ""))) or "").strip()
            raw_ship_state = str(ship.get("ship_state", ship.get("stcd", ship.get("Stcd", ship.get("state", "")))) or "").strip()
            ship_state = raw_ship_state.zfill(2) if (raw_ship_state.isdigit() and len(raw_ship_state) == 1) else raw_ship_state
            ship_phone = str(ship.get("ship_phone", ship.get("phone", ship.get("Phone", ""))) or "").strip()
            ship_email = str(ship.get("ship_email", ship.get("email", ship.get("Email", ""))) or "").strip().lower()

            if ship_gstin and ship_gstin != "URP":
                if not (3 <= len(ship_gstin) <= 15):
                    errors.append(ValidationError(2200, "shipdtl.ship_gstin", f"ship_gstin length must be 3-15 chars. Got: {len(ship_gstin)}"))
                elif len(ship_gstin) != 15:
                    errors.append(ValidationError(2200, "shipdtl.ship_gstin", f"Invalid ship_gstin length ({len(ship_gstin)}). Must be 15 characters."))
                elif not re.match(GSTIN_REGEX, ship_gstin):
                    errors.append(ValidationError(2200, "shipdtl.ship_gstin", f"Invalid ship_gstin format '{ship_gstin}'. Must be 15-digit GSTIN or 'URP'"))

            # Rule 2200 Shipping State Code Validation
            if raw_ship_state:
                if classify_rule_2200_diagnostic:
                    ship_diag = classify_rule_2200_diagnostic(
                        stcd=raw_ship_state,
                        gstin=ship_gstin,
                        pin=ship_pin,
                        loc=ship_loc,
                        section="ShipDtls"
                    )
                    if not ship_diag["is_valid"]:
                        errors.append(ValidationError(2200, "shipdtl.ship_state", ship_diag["reason"]))
                elif not raw_ship_state.isdigit() or len(raw_ship_state) != 2 or raw_ship_state not in VALID_STATE_CODES or raw_ship_state in ("00", "99"):
                    errors.append(ValidationError(2200, "shipdtl.ship_state", f"Invalid state code '{raw_ship_state}' for ship details."))

            if transactionmode in ["SHP", "CMB"]:
                if not ship_lglnm:
                    errors.append(ValidationError(2285, "shipdtl.ship_lglnm", f"ship_lglnm is mandatory when transactionmode is '{transactionmode}'"))
                elif not (3 <= len(ship_lglnm) <= 100):
                    errors.append(ValidationError(2285, "shipdtl.ship_lglnm", f"ship_lglnm length must be 3-100 characters. Current: {len(ship_lglnm)}"))

                if not ship_bnm:
                    errors.append(ValidationError(2285, "shipdtl.ship_bnm", f"ship_bnm is mandatory when transactionmode is '{transactionmode}'"))
                elif not (3 <= len(ship_bnm) <= 100):
                    errors.append(ValidationError(2285, "shipdtl.ship_bnm", f"ship_bnm length must be 3-100 characters. Current: {len(ship_bnm)}"))

                if not ship_loc:
                    errors.append(ValidationError(2285, "shipdtl.ship_loc", f"ship_loc is mandatory when transactionmode is '{transactionmode}'"))
                elif not (3 <= len(ship_loc) <= 100):
                    errors.append(ValidationError(2285, "shipdtl.ship_loc", f"ship_loc length must be 3-100 characters. Current: {len(ship_loc)}"))

                if not ship_pin:
                    errors.append(ValidationError(2285, "shipdtl.ship_pin", f"ship_pin is mandatory when transactionmode is '{transactionmode}'"))
                elif len(ship_pin) != 6 or not ship_pin.isdigit():
                    errors.append(ValidationError(3038, "shipdtl.ship_pin", f"ship_pin must be exactly 6 digits. Got: {len(ship_pin)}"))

                if not ship_state:
                    errors.append(ValidationError(2271, "shipdtl.ship_state", f"ship_state is mandatory when transactionmode is '{transactionmode}'"))
                elif len(ship_state) != 2:
                    errors.append(ValidationError(2271, "shipdtl.ship_state", f"ship_state must be exactly 2 digits. Got: '{ship_state}'"))

            if ship_trdnm and not (3 <= len(ship_trdnm) <= 100):
                errors.append(ValidationError(2285, "shipdtl.ship_trdnm", f"ship_trdnm length must be 3-100 characters. Current: {len(ship_trdnm)}"))
            if ship_bno and len(ship_bno) > 60:
                errors.append(ValidationError(2285, "shipdtl.ship_bno", f"ship_bno exceeds max length of 60 characters. Current: {len(ship_bno)}"))
            if ship_flno and not (3 <= len(ship_flno) <= 100):
                errors.append(ValidationError(2285, "shipdtl.ship_flno", f"ship_flno length must be 3-100 characters. Current: {len(ship_flno)}"))
            if ship_dst and len(ship_dst) > 60:
                errors.append(ValidationError(2285, "shipdtl.ship_dst", f"ship_dst exceeds max length of 60 characters. Current: {len(ship_dst)}"))
            if ship_phone and len(ship_phone) != 10:
                errors.append(ValidationError(2285, "shipdtl.ship_phone", f"ship_phone must be exactly 10 digits. Got: {len(ship_phone)}"))
            if ship_email:
                if not (10 <= len(ship_email) <= 50):
                    errors.append(ValidationError(2285, "shipdtl.ship_email", f"ship_email length must be 10-50 characters. Current: {len(ship_email)}"))
                if "@" not in ship_email or "." not in ship_email:
                    errors.append(ValidationError(2285, "shipdtl.ship_email", f"Invalid email format for ship_email: '{ship_email}'"))

            # Rule 2271: SHIP TO - State Code is Not Valid State Code for B2B, SEZ and Deemed Export Transactions
            if classify_rule_2271_diagnostic:
                diag_2271 = classify_rule_2271_diagnostic(
                    ship_state=raw_ship_state or ship_state,
                    trancatg=trancatg,
                    ship_gstin=ship_gstin,
                    ship_pin=ship_pin,
                    buyer_state=buy_state
                )
                if not diag_2271["is_valid"]:
                    errors.append(ValidationError(2271, "shipdtl.ship_state", f"SHIP TO - State Code is Not Valid (Rule 2271): {diag_2271['reason']}"))
            elif ship_state and (ship_state not in VALID_STATE_CODES or (trancatg not in ("EXP", "EXPWP", "EXPWOP") and ship_state == "96")):
                errors.append(ValidationError(2271, "shipdtl.ship_state", f"Invalid SHIP TO state code '{ship_state}'."))

            # Rule 2272: SHIP TO - PIN Code Cannot Be 999999 for B2B, SEZ and Deemed Export Transactions
            if classify_rule_2272_diagnostic:
                diag_2272 = classify_rule_2272_diagnostic(
                    ship_pin=ship_pin,
                    trancatg=trancatg,
                    buyer_pin=buy_pin,
                    ship_state=ship_state
                )
                if not diag_2272["is_valid"] and diag_2272.get("scenario") != "STRING_DATA_TYPE_PASSED":
                    errors.append(ValidationError(2272, "shipdtl.ship_pin", f"SHIP TO - PIN Code Cannot Be 999999 (Rule 2272): {diag_2272['reason']}"))
            elif (trancatg in ["B2B", "B2G", "SEZWP", "SEZWOP", "DEXP"]) and str(ship_pin).strip() == "999999":
                errors.append(ValidationError(2272, "shipdtl.ship_pin", f"SHIP TO PIN code cannot be 999999 for {trancatg} transactions."))

            if ship_pin and ship_state and str(ship_pin).strip() != "999999" and not verify_pincode_state(ship_pin, ship_state):
                errors.append(ValidationError(3041, "shipdtl.ship_pin", f"Ship PIN '{ship_pin}' does not belong to State '{ship_state}'."))

        # ---------------------------------------------------------
        # Section 7: Line Items (itemdtls) & Comprehensive Tax Checks
        # ---------------------------------------------------------
        raw_items = invoice.get("itemdtls")
        is_null_array = (raw_items is None and ("itemdtls" in invoice or "items" in invoice or "ItemList" in invoice)) or bool(invoice.get("is_null_array"))
        is_glitch = bool(invoice.get("is_erp_extraction_glitch") or invoice.get("erp_glitch"))
        items = raw_items if (raw_items is not None and isinstance(raw_items, list)) else []
        if not items or is_null_array or is_glitch:
            diag_2228 = classify_rule_2228_diagnostic(
                items=items,
                is_null_array=is_null_array,
                is_erp_extraction_glitch=is_glitch,
            ) if classify_rule_2228_diagnostic else None
            diag_msg = f": {diag_2228['reason']}" if diag_2228 else ""
            errors.append(ValidationError(2228, "itemdtls", f"Item list cannot be empty{diag_msg}"))

        max_item_limit = int(invoice.get("middleware_threshold") or 1000)
        is_middleware = bool(invoice.get("is_middleware_restricted") or (invoice.get("middleware_threshold") and int(invoice.get("middleware_threshold")) < 1000))
        is_unsplit_bulk = bool(invoice.get("is_cannot_split_bulk"))

        if len(items) > max_item_limit or is_middleware:
            diag = classify_rule_2173_diagnostic(
                item_count=len(items),
                items=items,
                max_limit=1000,
                is_middleware_restricted=is_middleware,
                middleware_threshold=invoice.get("middleware_threshold"),
                is_cannot_split_bulk=is_unsplit_bulk
            ) if classify_rule_2173_diagnostic else None
            diag_msg = f". {diag['scenario_name']}: {diag['reason']}" if diag else ""
            errors.append(ValidationError(2173, "itemdtls", f"ItemList contains {len(items)} items, exceeding the maximum limit of {max_item_limit} items{diag_msg}"))

        # Rule 2233: Duplicate SI numbers are not allowed in line items
        if len(items) > 1:
            is_batch_split = bool(invoice.get("is_batch_split") or any("batch" in str(k).lower() for itm in items if isinstance(itm, dict) for k in itm.keys()))
            diag_2233 = classify_rule_2233_diagnostic(
                items=items,
                is_batch_split=is_batch_split,
            ) if classify_rule_2233_diagnostic else None
            if diag_2233 and not diag_2233["is_valid"]:
                errors.append(ValidationError(2233, "itemdtls", f"Duplicate SI numbers are not allowed in line items: {diag_2233['reason']} Fix: {diag_2233['resolution']}"))

        is_intra = (sup_state == pos and igstonintra != "Y" and not is_export and not is_sez)
        has_goods_item = False

        sum_assamt = Decimal("0.00")
        sum_cgst = Decimal("0.00")
        sum_sgst = Decimal("0.00")
        sum_igst = Decimal("0.00")
        sum_cess = Decimal("0.00")
        sum_stcess = Decimal("0.00")
        sum_stcesnonad = Decimal("0.00")
        sum_cesnonad = Decimal("0.00")
        sum_totitem = Decimal("0.00")

        for idx, itm in enumerate(items, start=1):
            sl = idx
            prdnm = str(itm.get("prdnm", "") or "").strip()
            prddesc = str(itm.get("prddesc", "") or "").strip()
            isservc = str(itm.get("isservc", "N") or "N").strip().upper()
            hsn = str(itm.get("hsncd", "") or itm.get("hsn", "") or "").strip()
            barcde = str(itm.get("barcde", "") or "").strip()
            raw_qty = str(itm.get("qty", "") or "").strip()
            raw_uqc = str(itm.get("uqc", "") or itm.get("unit", "") or "").strip().upper()

            if not prdnm:
                errors.append(ValidationError(2285, f"itemdtls[{sl}].prdnm", f"prdnm (Product Name) is mandatory for item {sl}"))
            elif not (3 <= len(prdnm) <= 300):
                errors.append(ValidationError(2285, f"itemdtls[{sl}].prdnm", f"prdnm length must be 3-300 characters for item {sl}. Current: {len(prdnm)}"))

            if prddesc and not (3 <= len(prddesc) <= 300):
                errors.append(ValidationError(2285, f"itemdtls[{sl}].prddesc", f"prddesc length must be 3-300 characters for item {sl}. Current: {len(prddesc)}"))

            if isservc not in ["Y", "N"]:
                errors.append(ValidationError(2285, f"itemdtls[{sl}].isservc", f"Invalid isservc '{isservc}' for item {sl}. Must be 'Y' (Service) or 'N' (Goods)"))

            if not hsn:
                errors.append(ValidationError(2176, f"itemdtls[{sl}].hsncd", f"HSN code(s)-(blank) is invalid: Wrong HSN code is being passed. Pl check the HSN code being passed and Cross-check the correctness of HSN code on e-invoice portal. Still, if you feel it is correct, then please send the details to the helpdesk for verification at e-invoice system side."))
            elif not (2 <= len(hsn) <= 8) or not hsn.isdigit():
                errors.append(ValidationError(2176, f"itemdtls[{sl}].hsncd", f"HSN code(s)-{hsn} is invalid: Wrong HSN code is being passed. Pl check the HSN code being passed and Cross-check the correctness of HSN code on e-invoice portal. Still, if you feel it is correct, then please send the details to the helpdesk for verification at e-invoice system side."))
            elif validate_hsn_statutory:
                stat_meta = validate_hsn_statutory(hsn)
                if stat_meta is None:
                    errors.append(ValidationError(2176, f"itemdtls[{sl}].hsncd", f"HSN code(s)-{hsn} is invalid: Wrong HSN code is being passed. Pl check the HSN code being passed and Cross-check the correctness of HSN code on e-invoice portal. Still, if you feel it is correct, then please send the details to the helpdesk for verification at e-invoice system side."))

            if barcde and not (1 <= len(barcde) <= 30):
                errors.append(ValidationError(2285, f"itemdtls[{sl}].barcde", f"barcde length must be 1-30 characters for item {sl}."))

            diag_2238 = classify_rule_2238_diagnostic(
                qty=raw_qty,
                is_service=isservc,
                item_slno=sl,
                prdnm=itm.get("prdnm")
            ) if classify_rule_2238_diagnostic else None
            if diag_2238 and not diag_2238["is_valid"]:
                errors.append(ValidationError(2238, f"itemdtls[{sl}].qty", f"For Sl. No {sl}, Quantity is not passed: {diag_2238['reason']}"))

            diag_2239 = classify_rule_2239_diagnostic(
                unit=raw_uqc,
                is_service=isservc,
                item_slno=sl,
                prdnm=itm.get("prdnm")
            ) if classify_rule_2239_diagnostic else None
            if diag_2239 and not diag_2239["is_valid"]:
                errors.append(ValidationError(2239, f"itemdtls[{sl}].uqc", f"For Sl. No {sl}, Unit Quantity Code (UQC) is not passed: {diag_2239['reason']}"))

            if raw_uqc:
                diag_2177 = classify_rule_2177_diagnostic(raw_uqc) if classify_rule_2177_diagnostic else None
                if diag_2177 and not diag_2177["is_valid"]:
                    errors.append(ValidationError(
                        2177,
                        f"itemdtls[{sl}].uqc",
                        f"Unit Quantity Code(s)-{raw_uqc} is/are not as per master. {diag_2177['reason']} Fix: {diag_2177['resolution']}"
                    ))
                elif not diag_2177 and (len(raw_uqc) > 3 or raw_uqc not in ALLOWED_UQC):
                    errors.append(ValidationError(2177, f"itemdtls[{sl}].uqc", f"Unit Quantity Code '{raw_uqc}' for item {sl} is not as per master."))

            # Numerical precision and calculation checks
            try:
                qty = Decimal(raw_qty or "0")
                unitrate = Decimal(str(itm.get("unitrate", itm.get("unitprice", itm.get("UnitPrice", "0"))) or "0"))
                gross = Decimal(str(itm.get("grossamt", itm.get("totamt", itm.get("TotAmt", "0"))) or "0"))
                discount = Decimal(str(itm.get("discount", itm.get("discval", itm.get("Discount", "0"))) or "0"))
                othchrg = Decimal(str(itm.get("othchrg", itm.get("OthChrg", "0")) or "0"))
                assamt = Decimal(str(itm.get("assamt", itm.get("assval", itm.get("AssAmt", "0"))) or "0"))
                cgstrt = Decimal(str(itm.get("cgstrt", itm.get("gstrate", itm.get("CgstRt", "0"))) or "0"))
                cgstamt = Decimal(str(itm.get("cgstamt", itm.get("cgstval", itm.get("CgstAmt", "0"))) or "0"))
                sgstrt = Decimal(str(itm.get("sgstrt", itm.get("gstrate", itm.get("SgstRt", "0"))) or "0"))
                sgstamt = Decimal(str(itm.get("sgstamt", itm.get("sgstval", itm.get("SgstAmt", "0"))) or "0"))
                igstrt = Decimal(str(itm.get("igstrt", itm.get("gstrate", itm.get("IgstRt", "0"))) or "0"))
                igstamt = Decimal(str(itm.get("igstamt", itm.get("igstval", itm.get("IgstAmt", "0"))) or "0"))
                gstrate = Decimal(str(itm.get("gstrate", itm.get("GstRt", igstrt if igstrt > 0 else (cgstrt + sgstrt))) or "0"))
                cessrt = Decimal(str(itm.get("cessrt", itm.get("cesrt", itm.get("CesRt", "0"))) or "0"))
                cessamt = Decimal(str(itm.get("cessamt", itm.get("cesval", itm.get("CesAmt", "0"))) or "0"))

                # Rule 2240: GST rate of tax is incorrect or not as notified
                raw_gstrt_val = itm.get("gstrate", itm.get("GstRt"))
                diag_2240 = classify_rule_2240_diagnostic(
                    gstrate=raw_gstrt_val if raw_gstrt_val is not None else float(gstrate),
                    cgstrt=cgstrt,
                    sgstrt=sgstrt,
                    cesrt=cessrt,
                    item_slno=sl
                ) if classify_rule_2240_diagnostic else None
                if diag_2240 and not diag_2240["is_valid"]:
                    errors.append(ValidationError(2240, f"itemdtls[{sl}].gstrate", f"For Sl. No {sl}, GST rate of tax is incorrect or not as notified: {diag_2240['reason']}"))
                stcessrt = Decimal(str(itm.get("statecessrt", itm.get("statecesrate", itm.get("StateCesRt", itm.get("stcesrt", itm.get("StCesRt", "0"))))) or "0"))
                stcessamt = Decimal(str(itm.get("statecessamt", itm.get("statecesval", itm.get("StateCesAmt", itm.get("statecesamt", itm.get("stcesval", itm.get("StCesAmt", itm.get("stcessamt", "0"))))))) or "0"))
                cesnonad = Decimal(str(itm.get("cessnonadval", itm.get("cesnonadval", itm.get("CesNonAdVal", itm.get("CesNonAdvlAmt", "0")))) or "0"))
                stcesnonad = Decimal(str(itm.get("statecesnonadvl", itm.get("statecesnonadval", itm.get("StateCesNonAdvlAmt", itm.get("StateCesNonAdVal", itm.get("stcesnonadval", itm.get("stcesnonadvl", "0")))))) or "0"))
                totitemval = Decimal(str(itm.get("totitemval", itm.get("totval", itm.get("TotItemVal", "0"))) or "0"))

                # Gross Amount validation: Qty * UnitPrice (Rule 2192)
                expected_gross = (qty * unitrate).quantize(Decimal("0.01"))
                is_serv_flag = str(itm.get("isservc", itm.get("is_service", "N"))).strip().upper() == "Y" or str(hsn).startswith("99")
                is_rule_2192_violation = False
                if is_serv_flag and qty == Decimal("0.00") and unitrate > Decimal("0.00"):
                    is_rule_2192_violation = True
                elif abs(gross - expected_gross) > Decimal("0.005"):
                    is_rule_2192_violation = True

                if is_rule_2192_violation:
                    diag_2192 = classify_rule_2192_diagnostic(
                        qty=qty,
                        unitprice=unitrate,
                        totamt=gross,
                        discount=discount,
                        gstrate=gstrate,
                        taxes=cgstamt + sgstamt + igstamt,
                        is_service="Y" if is_serv_flag else "N",
                        hsn=str(hsn),
                        item_slno=sl
                    ) if classify_rule_2192_diagnostic else None
                    diag_msg = f" ({diag_2192['scenario_name']}): {diag_2192['reason']}" if diag_2192 else ""
                    errors.append(ValidationError(2192, f"itemdtls[{sl}].grossamt", f"TotAmt ({gross}) should equal Qty*UnitPrice ({expected_gross}) for HSN {hsn}.{diag_msg}"))

                # Assessable Amount validation: Gross - Discount (Rule 2193)
                expected_assamt = (gross - discount).quantize(Decimal("0.01"))
                if abs(assamt - expected_assamt) > Decimal("0.005"):
                    diag_2193 = classify_rule_2193_diagnostic(
                        totamt=gross,
                        discount=discount,
                        assamt=assamt,
                        gstrate=gstrate,
                        taxes=cgstamt + sgstamt + igstamt,
                        othchrg=othchrg,
                        item_slno=sl
                    ) if classify_rule_2193_diagnostic else None
                    diag_msg = f" ({diag_2193['scenario_name']}): {diag_2193['reason']}" if diag_2193 else ""
                    errors.append(ValidationError(2193, f"itemdtls[{sl}].assamt", f"For Sl No {sl}, AssAmt ({assamt}) != Gross - Discount ({expected_assamt}).{diag_msg}"))

                # Inter vs Intra Tax validation
                if is_intra:
                    if igstamt > 0:
                        diag = classify_rule_2172_diagnostic(
                            seller_state=sup_state,
                            buyer_pos=pos,
                            buyer_state=buy_state,
                            buyer_gstin=buy_gstin,
                            igst_amt=igstamt,
                            cgst_amt=cgstamt,
                            sgst_amt=sgstamt,
                            igstonintra=igstonintra
                        ) if classify_rule_2172_diagnostic else None
                        diag_msg = f". {diag['scenario_name']}: {diag['reason']}" if diag else ""
                        errors.append(ValidationError(2172, f"itemdtls[{sl}].igstamt", f"For Intra-state, IGST is not applicable. Item {sl} has IGST {igstamt}{diag_msg}"))
                    if abs(cgstamt - sgstamt) > Decimal("0.005"):
                        diag_2227 = classify_rule_2227_diagnostic(
                            cgstamt=cgstamt,
                            sgstamt=sgstamt,
                            assamt=assamt,
                            gstrate=gstrate,
                            item_slno=sl,
                        ) if classify_rule_2227_diagnostic else None
                        diag_msg = f": {diag_2227['reason']}" if diag_2227 else ""
                        errors.append(ValidationError(2227, f"itemdtls[{sl}]", f"For Sl No {sl}, SGST ({sgstamt}) and CGST ({cgstamt}) amounts must be equal{diag_msg}"))
                    if gstrate > 0:
                        diag_2234 = classify_rule_2234_diagnostic(
                            cgstamt=cgstamt,
                            sgstamt=sgstamt,
                            assamt=assamt,
                            gstrate=gstrate,
                            totamt=gross,
                            discount=discount,
                            item_slno=sl,
                        ) if classify_rule_2234_diagnostic else None
                        if diag_2234 and not diag_2234["is_valid"]:
                            errors.append(ValidationError(2234, f"itemdtls[{sl}].cgstamt", f"For Sl. No {sl}, SGST and CGST amount passed does not match with taxable value and tax rate: {diag_2234['reason']}"))
                else:
                    if cgstamt > 0 or sgstamt > 0:
                        diag = classify_rule_2174_diagnostic(
                            seller_state=sup_state,
                            buyer_pos=pos,
                            buyer_state=buy_state,
                            buyer_gstin=buy_gstin,
                            ship_state=ship.get("ship_state", "") if ship else "",
                            cgst_amt=cgstamt,
                            sgst_amt=sgstamt,
                            igst_amt=igstamt
                        ) if classify_rule_2174_diagnostic else None
                        diag_msg = f". {diag['scenario_name']}: {diag['reason']}" if diag else ""
                        errors.append(ValidationError(2174, f"itemdtls[{sl}].cgstamt", f"For inter-state/SEZ, CGST/SGST not applicable; only IGST applies. Item {sl} has CGST {cgstamt}, SGST {sgstamt}{diag_msg}"))
                    if gstrate > 0:
                        diag_2235 = classify_rule_2235_diagnostic(
                            igstamt=igstamt,
                            assamt=assamt,
                            gstrate=gstrate,
                            totamt=gross,
                            discount=discount,
                            item_slno=sl,
                        ) if classify_rule_2235_diagnostic else None
                        if diag_2235 and not diag_2235["is_valid"]:
                            errors.append(ValidationError(2235, f"itemdtls[{sl}].igstamt", f"For Sl. No {sl}, IGST amount passed is not matching with taxable value and tax rate: {diag_2235['reason']}"))

                # Rule 2266: Line Item Cess Amount validation
                diag_2266 = classify_rule_2266_diagnostic(
                    assval=assamt,
                    cesrate=cessrt,
                    cesval=cessamt,
                    cesnonadvl=cesnonad,
                    item_slno=sl
                ) if classify_rule_2266_diagnostic else None
                if diag_2266 and not diag_2266["is_valid"]:
                    errors.append(ValidationError(2266, f"itemdtls[{sl}].cesval", f"For Sl. No {sl}, Item Cess amount does not match calculated value: {diag_2266['reason']}"))

                # Rule 2267: Line Item State Cess Amount validation
                diag_2267 = classify_rule_2267_diagnostic(
                    assval=assamt,
                    statecesrate=stcessrt,
                    statecesval=stcessamt,
                    statecesnonadvl=stcesnonad,
                    item_slno=sl
                ) if classify_rule_2267_diagnostic else None
                if diag_2267 and not diag_2267["is_valid"]:
                    errors.append(ValidationError(2267, f"itemdtls[{sl}].statecesval", f"For Sl. No {sl}, Item State Cess amount does not match calculated value: {diag_2267['reason']}"))

                # Total Item Value validation (Rule 2194)
                expected_totitem = (assamt + cgstamt + sgstamt + igstamt + cessamt + cesnonad + stcessamt + stcesnonad + othchrg).quantize(Decimal("0.01"))
                if abs(totitemval - expected_totitem) > Decimal("1.00"):
                    diag_2194 = classify_rule_2194_diagnostic(
                        totitemval=totitemval,
                        assamt=assamt,
                        cgstamt=cgstamt,
                        sgstamt=sgstamt,
                        igstamt=igstamt,
                        cesamt=cessamt,
                        cesnonadval=cesnonad,
                        statecesamt=stcessamt,
                        statecesnonadval=stcesnonad,
                        othchrg=othchrg,
                        totamt=gross,
                        discount=discount,
                        item_slno=sl,
                        hsn=str(hsn),
                    ) if classify_rule_2194_diagnostic else None
                    diag_msg = f" ({diag_2194['scenario_name']}): {diag_2194['reason']}" if diag_2194 else ""
                    errors.append(ValidationError(2194, f"itemdtls[{sl}].totitemval", f"For Sl No {sl}, Total item value ({totitemval}) != sum of taxable and taxes ({expected_totitem}).{diag_msg}"))

                sum_assamt += assamt
                sum_cgst += cgstamt
                sum_sgst += sgstamt
                sum_igst += igstamt
                sum_cess += cessamt
                sum_stcess += stcessamt
                sum_stcesnonad += stcesnonad
                sum_cesnonad += cesnonad
                sum_totitem += totitemval

            except Exception as e:
                errors.append(ValidationError(2285, f"itemdtls[{sl}]", f"Numeric calculation error in item {sl}: {str(e)}"))

        # ---------------------------------------------------------
        # Section 8: Value Summary (valdt1) Reconciliation
        # ---------------------------------------------------------
        val_raw = invoice.get("valdt1") or invoice.get("valdtls") or invoice.get("ValDtls")
        valdt1 = val_raw if isinstance(val_raw, dict) else (invoice.get("valdt1", {}) if isinstance(invoice.get("valdt1"), dict) else invoice)
        try:
            ttlassval = Decimal(str(valdt1.get("ttlassval", valdt1.get("assval", valdt1.get("AssVal", "0"))) or "0"))
            cgstval = Decimal(str(valdt1.get("cgstval", valdt1.get("CgstVal", "0")) or "0"))
            sgstval = Decimal(str(valdt1.get("sgstval", valdt1.get("SgstVal", "0")) or "0"))
            igstval = Decimal(str(valdt1.get("igstval", valdt1.get("IgstVal", "0")) or "0"))
            cesval = Decimal(str(valdt1.get("cesval", valdt1.get("CesVal", "0")) or "0"))
            stcesval = Decimal(str(valdt1.get("stcesval", valdt1.get("StCesVal", "0")) or "0"))
            cesnonadval = Decimal(str(valdt1.get("cesnonadval", valdt1.get("CesNonAdVal", "0")) or "0"))
            totinvval = Decimal(str(valdt1.get("totinvval", valdt1.get("totval", valdt1.get("TotInvVal", "0"))) or "0"))
            othchrg = Decimal(str(valdt1.get("othchrg", valdt1.get("OthChrg", "0")) or "0"))
            discval = Decimal(str(valdt1.get("discval", valdt1.get("discount", valdt1.get("Discount", "0"))) or "0"))
            rndoffamt = Decimal(str(valdt1.get("rndoffamt", valdt1.get("RndOffAmt", "0")) or "0"))

            # Reconciliation of header totals with line item sums (Strict mathematical equality for assessable value, +/- Rs 2 tolerance for taxes)
            if abs(ttlassval - sum_assamt) > Decimal("0.005"):
                diag_2182 = classify_rule_2182_diagnostic(
                    header_assval=ttlassval,
                    sum_item_assamt=sum_assamt,
                    items=items,
                    header_discount=discval,
                ) if classify_rule_2182_diagnostic else None
                diag_msg = f" ({diag_2182['scenario_name']}): {diag_2182['reason']}" if diag_2182 else ""
                errors.append(ValidationError(2182, "valdt1.ttlassval", f"Taxable value of items ({sum_assamt}) != total taxable value ({ttlassval}).{diag_msg}"))
            if not is_intra:
                if (cgstval > Decimal("0.00") or sgstval > Decimal("0.00")) and sum_igst > Decimal("0.00"):
                    errors.append(ValidationError(2174, "valdt1.cgstval", "Header Summary vs. Line Items Mismatch: Header totals in ValDtls must mirror line-item taxes. If line items carry IGST, CgstVal and SgstVal in ValDtls must be 0.00."))
            # Rule 2184 CGST Value Reconciliation (Strict mathematical equality: ValDtls.CgstVal == sum(ItemList[i].CgstAmt), or disallowed in inter-state)
            is_rule_2184_violation = False
            if is_intra and abs(cgstval - sum_cgst) > Decimal("0.005"):
                is_rule_2184_violation = True
            elif not is_intra and (cgstval > Decimal("0.00") or sum_cgst > Decimal("0.00")):
                is_rule_2184_violation = True

            if is_rule_2184_violation:
                diag_2184 = classify_rule_2184_diagnostic(
                    header_cgst=cgstval,
                    sum_item_cgst=sum_cgst,
                    items=items,
                    header_sgst=sgstval,
                    sum_item_sgst=sum_sgst,
                    is_inter_state=(not is_intra),
                    seller_state=sup_state,
                    buyer_pos=pos,
                ) if classify_rule_2184_diagnostic else None
                diag_msg = f" ({diag_2184['scenario_name']}): {diag_2184['reason']}" if diag_2184 else ""
                errors.append(ValidationError(2184, "valdt1.cgstval", f"CGST value of items ({sum_cgst}) != total CGST ({cgstval}).{diag_msg}"))
            # Rule 2183 SGST Value Reconciliation (Strict mathematical equality: ValDtls.SgstVal == sum(ItemList[i].SgstAmt), or disallowed in inter-state)
            is_rule_2183_violation = False
            if is_intra and abs(sgstval - sum_sgst) > Decimal("0.005"):
                is_rule_2183_violation = True
            elif not is_intra and (sgstval > Decimal("0.00") or sum_sgst > Decimal("0.00")):
                is_rule_2183_violation = True

            if is_rule_2183_violation:
                diag_2183 = classify_rule_2183_diagnostic(
                    header_sgst=sgstval,
                    sum_item_sgst=sum_sgst,
                    items=items,
                    header_cgst=cgstval,
                    sum_item_cgst=sum_cgst,
                    is_inter_state=(not is_intra),
                    seller_state=sup_state,
                    buyer_pos=pos,
                ) if classify_rule_2183_diagnostic else None
                diag_msg = f" ({diag_2183['scenario_name']}): {diag_2183['reason']}" if diag_2183 else ""
                errors.append(ValidationError(2183, "valdt1.sgstval", f"SGST value of items ({sum_sgst}) != total SGST ({sgstval}).{diag_msg}"))
            # Rule 2185 IGST Value Reconciliation (Strict mathematical equality: ValDtls.IgstVal == sum(ItemList[i].IgstAmt), or disallowed in intra-state)
            is_rule_2185_violation = False
            is_std_intra = (is_intra and igstonintra != "Y" and trancatg not in ("EXP", "EXPWP", "EXPWOP", "SEZWP", "SEZWOP"))
            if is_std_intra and (igstval > Decimal("0.00") or sum_igst > Decimal("0.00")):
                is_rule_2185_violation = True
            elif not is_std_intra and abs(igstval - sum_igst) > Decimal("0.005"):
                is_rule_2185_violation = True

            if is_rule_2185_violation:
                diag_2185 = classify_rule_2185_diagnostic(
                    header_igst=igstval,
                    sum_item_igst=sum_igst,
                    items=items,
                    header_cgst=cgstval,
                    sum_item_cgst=sum_cgst,
                    header_sgst=sgstval,
                    sum_item_sgst=sum_sgst,
                    is_inter_state=(not is_intra),
                    seller_state=sup_state,
                    buyer_pos=pos,
                    igst_on_intra=igstonintra,
                    trancatg=trancatg,
                ) if classify_rule_2185_diagnostic else None
                diag_msg = f" ({diag_2185['scenario_name']}): {diag_2185['reason']}" if diag_2185 else ""
                errors.append(ValidationError(2185, "valdt1.igstval", f"IGST value of items ({sum_igst}) != total IGST ({igstval}).{diag_msg}"))
            # Rule 2186 Cess Value Reconciliation (Strict mathematical equality: ValDtls.CesVal == sum(ItemList[i].CesAmt + ItemList[i].CesNonAdvlAmt))
            sum_total_cess = sum_cess + sum_cesnonad
            if abs(cesval - sum_total_cess) > Decimal("0.005"):
                diag_2186 = classify_rule_2186_diagnostic(
                    header_cess=cesval,
                    sum_item_cess=sum_total_cess,
                    items=items,
                    header_stcess=stcesval,
                    sum_item_stcess=sum_stcess,
                    sum_item_cesad=sum_cess,
                    sum_item_cesnonad=sum_cesnonad,
                ) if classify_rule_2186_diagnostic else None
                diag_msg = f" ({diag_2186['scenario_name']}): {diag_2186['reason']}" if diag_2186 else ""
                errors.append(ValidationError(2186, "valdt1.cesval", f"Cess value of items ({sum_total_cess}) != total Cess ({cesval}).{diag_msg}"))
            # Rule 2187 State Cess Value Reconciliation
            sum_total_stcess = sum_stcess + sum_stcesnonad
            if abs(stcesval - sum_total_stcess) > Decimal("0.005"):
                diag_2187 = classify_rule_2187_diagnostic(
                    header_stcess=stcesval,
                    sum_item_stcess=sum_total_stcess,
                    items=items,
                    header_cess=cesval,
                    sum_item_cess=sum_total_cess,
                    sum_item_stcesad=sum_stcess,
                    sum_item_stcesnonad=sum_stcesnonad,
                ) if classify_rule_2187_diagnostic else None
                diag_msg = f" ({diag_2187['scenario_name']}): {diag_2187['reason']}" if diag_2187 else ""
                errors.append(ValidationError(2187, "valdt1.stcesval", f"State Cess value of items ({sum_total_stcess}) != total State Cess ({stcesval}).{diag_msg}"))

            # Rule 2189 Total Invoice Value Reconciliation (+/- 1.00 tolerance)
            diag_2189 = classify_rule_2189_diagnostic(
                totinvval=totinvval,
                sum_totitem=sum_totitem,
                othchrg=othchrg,
                discount=discval,
                rndoffamt=rndoffamt,
                assval=ttlassval,
                cgstval=cgstval,
                sgstval=sgstval,
                igstval=igstval,
                cesval=cesval,
                stcesval=stcesval,
                items=items,
            ) if classify_rule_2189_diagnostic else None
            if diag_2189 and not diag_2189["is_valid"]:
                calc_val = diag_2189.get("calculated_totinv", totinvval)
                errors.append(ValidationError(2189, "valdt1.totinvval", f"Total Invoice Value ({totinvval}) != calculated value ({calc_val}). ({diag_2189.get('scenario_name', '')}): {diag_2189.get('reason', '')}"))
            elif not diag_2189:
                expected_totinv = ttlassval + cgstval + sgstval + igstval + cesval + stcesval + cesnonadval + othchrg - discval + rndoffamt
                if abs(totinvval - expected_totinv) > Decimal("1.00"):
                    errors.append(ValidationError(2189, "valdt1.totinvval", f"Total Invoice Value ({totinvval}) != calculated value ({expected_totinv})"))
        except Exception as e:
            errors.append(ValidationError(2285, "valdt1.totinvval", f"Invalid invoice value computation: {str(e)}"))

        # ---------------------------------------------------------
        # Section 9: E-Way Bill Details (ewbdt1)
        # ---------------------------------------------------------
        ewb = invoice.get("ewbdt1", {}) if isinstance(invoice.get("ewbdt1"), dict) else invoice
        ewayreq = str(ewb.get("ewayreq", "N") or "N").strip().upper()
        if ewayreq not in ["Y", "N"]:
            errors.append(ValidationError(2285, "ewbdt1.ewayreq", f"Invalid ewayreq '{ewayreq}'. Must be 'Y' or 'N'."))

        if ewayreq == "Y":
            if not has_goods_item:
                errors.append(ValidationError(4009, "ewbdt1", "E Way Bill can be generated provided at least HSN of one item belongs to goods."))
            if doc_type in ["CRN", "DBN"]:
                errors.append(ValidationError(4010, "ewbdt1", "E-way Bill cannot be generated for Debit Note or Credit Note."))

            subsupply = str(ewb.get("subsupplytype", "") or "").strip()
            if not subsupply:
                errors.append(ValidationError(2285, "ewbdt1.subsupplytype", "subsupplytype is required when ewayreq is 'Y'"))
            elif subsupply not in [str(i) for i in range(1, 13)]:
                errors.append(ValidationError(2285, "ewbdt1.subsupplytype", f"Invalid subsupplytype '{subsupply}'. Must be between 1 and 12."))

            mode = str(ewb.get("mode_of_transport", "") or "").strip()
            if not mode:
                errors.append(ValidationError(2285, "ewbdt1.mode_of_transport", "mode_of_transport is required when ewayreq is 'Y'"))
            elif mode not in ["1", "2", "3", "4"]:
                errors.append(ValidationError(2285, "ewbdt1.mode_of_transport", f"Invalid mode_of_transport '{mode}'. Must be 1, 2, 3, or 4."))

            veh_num = str(ewb.get("veh_number", "") or "").strip().upper().replace(" ", "").replace("-", "")
            veh_type = str(ewb.get("veh_type", "") or "").strip().upper()
            doc_no = str(ewb.get("transport_doc_no", "") or "").strip().upper()
            doc_date_str = str(ewb.get("transporter_doc_date", "") or "").strip()
            trans_id = str(ewb.get("transporter_id", "") or "").strip().upper()
            dist_str = str(ewb.get("distance_of_transport", "") or "").strip()

            if not trans_id:
                errors.append(ValidationError(4019, "ewbdt1.transporter_id", "Provide Transporter ID in order to generate Part A of e-Way Bill."))
            elif len(trans_id) != 15:
                errors.append(ValidationError(4019, "ewbdt1.transporter_id", f"transporter_id must be exactly 15 characters. Got: {len(trans_id)}"))
            elif not re.match(TRANS_ID_REGEX, trans_id):
                errors.append(ValidationError(4019, "ewbdt1.transporter_id", f"transporter_id '{trans_id}' has an invalid format."))

            try:
                dist = int(dist_str) if dist_str else 0
                if dist <= 0:
                    errors.append(ValidationError(4029, "ewbdt1.distance_of_transport", "distance_of_transport is required and must be greater than 0 when ewayreq is 'Y'"))
                elif dist > 9999:
                    errors.append(ValidationError(4013, "ewbdt1.distance_of_transport", f"distance_of_transport exceeds max allowed digits (4). Got: {dist}"))
            except ValueError:
                errors.append(ValidationError(4013, "ewbdt1.distance_of_transport", f"Invalid distance value '{dist_str}'."))

            if mode == "1":  # Road
                if not veh_num:
                    errors.append(ValidationError(4011, "ewbdt1.veh_number", "Vehicle number should be passed in case transportation mode is Road."))
                elif not re.match(VEH_REGEX, veh_num) and not (7 <= len(veh_num) <= 15):
                    errors.append(ValidationError(4014, "ewbdt1.veh_number", f"Invalid vehicle number format: '{veh_num}'"))

                if not veh_type:
                    errors.append(ValidationError(4022, "ewbdt1.veh_type", "Vehicle type should be passed in case transportation mode is Road."))
                elif veh_type not in ["R", "O"]:
                    errors.append(ValidationError(4020, "ewbdt1.veh_type", f"Invalid vehicle type '{veh_type}'. Must be 'R' or 'O'."))

            elif mode in ["2", "3", "4"]:  # Rail, Air, Ship
                if not doc_no:
                    errors.append(ValidationError(4012, "ewbdt1.transport_doc_no", f"transport_doc_no is required when mode_of_transport is {mode}"))
                elif len(doc_no) > 15:
                    errors.append(ValidationError(4012, "ewbdt1.transport_doc_no", f"transport_doc_no exceeds max length of 15 characters. Got: {len(doc_no)}"))

                if not doc_date_str:
                    errors.append(ValidationError(4023, "ewbdt1.transporter_doc_date", f"transporter_doc_date is required when mode_of_transport is {mode}"))
                else:
                    try:
                        ewb_dt = datetime.strptime(doc_date_str, "%d-%m-%Y")
                        if ewb_dt.date() > datetime.today().date():
                            errors.append(ValidationError(4016, "ewbdt1.transporter_doc_date", "Transport document date cannot be a future date."))
                        if inv_date and ewb_dt.date() < inv_date.date():
                            errors.append(ValidationError(4021, "ewbdt1.transporter_doc_date", "Transporter document date cannot be earlier than invoice date."))
                    except ValueError:
                        errors.append(ValidationError(4017, "ewbdt1.transporter_doc_date", f"Invalid transporter doc date format '{doc_date_str}'. Expected DD-MM-YYYY."))

            if is_export and not ship:
                errors.append(ValidationError(4031, "shipdtl", "Ship to details are mandatory for export transactions to generate e-Way Bill."))

        # ---------------------------------------------------------
        # Section 10: Payment & UPI Validations (if present)
        # ---------------------------------------------------------
        fininsbr = str(invoice.get("fininsbr", "") or "").strip().upper()
        if fininsbr:
            if len(fininsbr) != 11 or not re.match(IFSC_REGEX, fininsbr):
                errors.append(ValidationError(2285, "fininsbr", f"fininsbr is not a valid IFSC format. Expected 11 characters (e.g. SBIN0001234). Got: '{fininsbr}'"))

        upiid = str(invoice.get("upiid", "") or "").strip().lower()
        if upiid:
            if len(upiid) > 100:
                errors.append(ValidationError(2285, "upiid", f"upiid exceeds max length of 100 characters. Got: {len(upiid)}"))
            elif not re.match(UPI_REGEX, upiid):
                errors.append(ValidationError(2285, "upiid", f"upiid '{upiid}' does not match standard UPI VPA format (e.g., name@bank)"))

        upiacct = str(invoice.get("upiacctnumber", "") or "").strip()
        if upiacct:
            if not upiacct.isdigit() or not (9 <= len(upiacct) <= 18):
                errors.append(ValidationError(2285, "upiacctnumber", f"upiacctnumber must be between 9 and 18 digits. Got: '{upiacct}'"))

        upi_ifsc = str(invoice.get("upiactifsccd", "") or "").strip().upper()
        if upi_ifsc:
            if len(upi_ifsc) != 11 or not re.match(IFSC_REGEX, upi_ifsc):
                errors.append(ValidationError(2285, "upiactifsccd", f"Invalid upiactifsccd format: '{upi_ifsc}'. Expected 11-char IFSC."))

        pmtmode = str(invoice.get("pmtmode", "") or "").strip().upper()
        if pmtmode and pmtmode not in ["CASH", "EPAY", "DIRDBT", "OTH"]:
            errors.append(ValidationError(2285, "pmtmode", f"Invalid pmtmode '{pmtmode}'. Must be CASH, EPAY, DIRDBT, or OTH."))

        return [err.to_dict() for err in errors]

    @classmethod
    def validate_payload_document(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validates entire document containing one or more invoices.
        """
        invoices = payload.get("einvoices", [])
        if not invoices and isinstance(payload, dict):
            invoices = [payload]

        report = {
            "total_invoices": len(invoices),
            "valid_invoices": 0,
            "failed_invoices": 0,
            "results": []
        }

        total_anomalies = 0

        # Optional PriceAnomalyDetector check
        price_detector = None
        try:
            from Template_Converters.price_anomaly_detector import PriceAnomalyDetector
            price_detector = PriceAnomalyDetector
        except ImportError:
            try:
                from price_anomaly_detector import PriceAnomalyDetector
                price_detector = PriceAnomalyDetector
            except ImportError:
                price_detector = None

        for idx, inv in enumerate(invoices, start=1):
            docno = inv.get("docdt1", {}).get("docno", inv.get("docno", f"INV_INDEX_{idx}"))
            errors = cls.validate_invoice(inv)
            is_valid = len(errors) == 0

            price_anom = None
            if price_detector:
                try:
                    price_anom = price_detector.scan_invoice_payload(inv)
                    total_anomalies += price_anom.get("anomaly_count", 0)
                except Exception:
                    price_anom = None

            if is_valid:
                report["valid_invoices"] += 1
            else:
                report["failed_invoices"] += 1

            res_entry = {
                "invoice_number": docno,
                "status": "VALID" if is_valid else "INVALID",
                "error_count": len(errors),
                "errors": errors
            }
            if price_anom:
                res_entry["price_anomaly_report"] = price_anom
            report["results"].append(res_entry)

        report["total_price_anomalies"] = total_anomalies

        return report

    @classmethod
    def check_rate_slab(cls, declared_rate: Any, hsn: Any) -> Dict[str, Any]:
        """RULE_08: Rate Slab Mismatch verification against statutory CBIC tariff."""
        try:
            from src.rules.rate_slab_checker import rate_slab_checker
            return rate_slab_checker.check(declared_rate, hsn)
        except Exception as e:
            return {"flag": None, "error": str(e)}

    @classmethod
    def check_section_17_5(cls, text: str, hsn: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """RULE_08: Section 17(5) Ineligible Input Tax Credit (ITC) Detection."""
        try:
            from src.rules.section_17_5_detector import section_17_5_detector
            return section_17_5_detector.scan(text, hsn=hsn)
        except Exception:
            return None

    @classmethod
    def validate_irn_cancellation(cls, cancel_request: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Validates an IRN cancellation request payload against statutory dependency rules (Rule 2230).
        Enforces:
        1. IRN length and format (64-character hex hash).
        2. Cancellation Reason Code (CnlRsn in "1", "2", "3", "4").
        3. Cancellation Remarks (CnlRem mandatory, max 100 chars).
        4. Dependency ordering: An active E-Way Bill locks the IRN against cancellation.
           If linked EWB is active, Error 2230 is returned with sequential workflow.
        5. Statutory 24-hour window: If cancellation attempted >24 hours after generation, Error 2230 is returned.
        """
        errors: List[ValidationError] = []

        irn = str(cancel_request.get("Irn", cancel_request.get("irn", "")) or "").strip()
        cnl_rsn = str(cancel_request.get("CnlRsn", cancel_request.get("cancelRsnCode", cancel_request.get("cnl_rsn", "")) or "")).strip()
        cnl_rem = str(cancel_request.get("CnlRem", cancel_request.get("cancelRmrk", cancel_request.get("cnl_rem", "")) or "")).strip()

        has_active_ewb = bool(
            cancel_request.get("has_active_ewb")
            or cancel_request.get("ewb_active")
            or (cancel_request.get("ewb_number") and not cancel_request.get("ewb_cancelled"))
            or (cancel_request.get("ewbNo") and not cancel_request.get("ewb_cancelled"))
        )
        hrs = float(cancel_request.get("hours_since_generation", 0.0) or 0.0)
        is_transporter = bool(cancel_request.get("generated_by_transporter") or cancel_request.get("is_transporter_ewb"))

        # IRN Format Check
        if not irn:
            errors.append(ValidationError(2289, "Irn", "Irn is mandatory and cannot be blank or null"))
        elif len(irn) != 64 or not all(c in "0123456789abcdefABCDEF" for c in irn):
            errors.append(ValidationError(2289, "Irn", f"Invalid Irn length ({len(irn)}). Must be exactly 64-character hexadecimal hash."))

        # Reason Code Check: 1=Duplicate, 2=Data Entry Error, 3=Order Cancelled, 4=Others
        if not cnl_rsn:
            errors.append(ValidationError(2285, "CnlRsn", "CnlRsn (Cancellation Reason Code) is mandatory"))
        elif cnl_rsn not in ("1", "2", "3", "4"):
            errors.append(ValidationError(2285, "CnlRsn", f"Invalid CnlRsn '{cnl_rsn}'. Must be 1 (Duplicate), 2 (Data Entry Error), 3 (Order Cancelled), or 4 (Others)"))

        # Remarks Check
        if not cnl_rem:
            errors.append(ValidationError(2285, "CnlRem", "CnlRem (Cancellation Remarks) is mandatory"))
        elif len(cnl_rem) > 100:
            errors.append(ValidationError(2285, "CnlRem", f"CnlRem exceeds maximum length of 100 characters. Got: {len(cnl_rem)}"))

        # Rule 2270: The Allowed Cancellation Time Limit is Crossed (> 24 hours)
        gen_time = cancel_request.get("generation_time") or cancel_request.get("gen_time") or cancel_request.get("irn_date") or cancel_request.get("irn_datetime")
        canc_time = cancel_request.get("cancellation_time") or cancel_request.get("canc_time")
        if hrs > 24.0 or gen_time:
            if classify_rule_2270_diagnostic:
                from datetime import datetime, timedelta
                if not gen_time and hrs > 24.0:
                    gen_time = (datetime.now() - timedelta(hours=hrs)).strftime("%Y-%m-%d %H:%M:%S")
                diag_2270 = classify_rule_2270_diagnostic(
                    generation_time=gen_time,
                    cancellation_time=canc_time,
                    irn=irn
                )
                if not diag_2270["is_valid"]:
                    errors.append(ValidationError(2270, "Irn", f"The Allowed Cancellation Time Limit is Crossed (Rule 2270): {diag_2270['reason']} Resolution: {diag_2270['resolution']}"))

        # Rule 2230: Dependency and Window Validation
        if has_active_ewb or is_transporter:
            diag_2230 = classify_rule_2230_diagnostic(
                has_active_ewb=has_active_ewb,
                ewb_number=cancel_request.get("ewb_number", cancel_request.get("ewbNo")),
                irn=irn,
                hours_since_generation=hrs,
                generated_by_transporter=is_transporter,
                cancel_reason_code=cnl_rsn,
                cancel_remarks=cnl_rem,
            ) if classify_rule_2230_diagnostic else None

            if diag_2230 and not diag_2230.get("is_valid"):
                errors.append(ValidationError(2230, "Irn", f"{diag_2230['reason']} Resolution: {diag_2230['resolution']}"))

        return [e.to_dict() for e in errors]



# Canonical aliases
GSTValidator = RulesEngine
GSTRulesEngine = RulesEngine

from src.rules.statutory_rules import (
    StatutoryRulesEngine,
    calculate_gstin_checksum,
    verify_gstin_checksum,
)
from src.rules.rate_slab_checker import RateSlabChecker, rate_slab_checker
from src.rules.section_17_5_detector import Section175Detector, section_17_5_detector

__all__ = [
    "STATE_MASTER",
    "VALID_STATE_CODES",
    "verify_pincode_state",
    "COUNTRY_MASTER",
    "COUNTRY_CURRENCY_MAP",
    "VALID_CURRENCIES",
    "MAJOR_INDIAN_PORTS",
    "ALLOWED_UQC",
    "ALLOWED_TAX_RATES",
    "ALLOWED_DOC_TYPES",
    "ALLOWED_TRAN_CATG",
    "ALLOWED_EXP_CAT",
    "ALLOWED_TRANS_MODE",
    "ALLOWED_TAXABILITY",
    "VALID_SUB_SUPPLY_TYPES",
    "VALID_TRANSPORT_MODES",
    "ALLOWED_VEH_TYPES",
    "IRN_ERRORS",
    "EWB_ERRORS",
    "ValidationError",
    "validate_nic_2day_rule",
    "RulesEngine",
    "GSTValidator",
    "GSTRulesEngine",
    "StatutoryRulesEngine",
    "RateSlabChecker",
    "rate_slab_checker",
    "Section175Detector",
    "section_17_5_detector",
    "calculate_gstin_checksum",
    "verify_gstin_checksum",
    "OFFICIAL_UQC_MASTER",
    "COMMON_UQC_MAPPING",
    "classify_rule_2177_diagnostic",
    "classify_rule_2182_diagnostic",
    "normalize_uqc_statutory",
]

