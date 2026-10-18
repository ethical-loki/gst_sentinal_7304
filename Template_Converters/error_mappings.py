"""
Comprehensive Master Definitions and NIC Error Code Mappings for Indian GST
E-Invoice (IRN) and E-Way Bill (EWB) compliance.
Includes State Code Master, Pincode-State mapping, Port Codes, Currency Codes,
Country Codes, and full SEZ transaction rules.
"""

from typing import Dict, Any, List, Set

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
    "CCM", "CMS", "CTN", "DOZ", "DRM", "GMS", "GRS", "GYD", "KGS", "KLR",
    "KME", "MLT", "MTR", "MTS", "NOS", "PAC", "PCS", "PRS", "QTL", "ROL",
    "SET", "SQF", "SQM", "SQY", "TBS", "TGM", "THD", "TON", "TUB", "UGS",
    "UNT", "YDS", "OTH"
]

ALLOWED_TAX_RATES: List[float] = [0.0, 0.1, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 6.0, 7.5, 12.0, 18.0, 28.0]
ALLOWED_DOC_TYPES: List[str] = ["INV", "CRN", "DBN", "CHL", "BIL", "OTH"]

# Expanded Transaction Categories supporting SEZ & Deemed Export
ALLOWED_TRAN_CATG: List[str] = [
    "B2B",     # Regular Business to Business
    "SEZWP",   # SEZ with payment of tax
    "SEZWOP",  # SEZ without payment of tax
    "EXP",     # Direct Export
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
        "reason": "Trying to set Reverse Charges applicable for transactions other than B2B/SEZ",
        "resolution": "Reverse charge can only be 'Y' for B2B/SEZ transactions"
    },
    2163: {
        "message": "The document date should not be future date.",
        "reason": "Attempting to set future date for the document date",
        "resolution": "Check the document date; docdt cannot be in the future"
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
        "message": "You have exceeded the limit of number of items",
        "reason": "User passed payload with items exceeding allowed API limit",
        "resolution": "Split invoice or use bulk/special API"
    },
    2174: {
        "message": "For inter-state transaction, CGST and SGST amounts are not applicable; only IGST amount is applicable",
        "reason": "CGST and SGST taxes passed for inter-state transaction (supplier state != POS)",
        "resolution": "Set only IGST amount for inter-state/SEZ transactions; CGST and SGST must be 0"
    },
    2176: {
        "message": "HSN code(s)-{0} is invalid",
        "reason": "Wrong HSN code passed",
        "resolution": "Check HSN code against NIC master (minimum 4 to 8 digits for goods, 6 for services 99xxxx)"
    },
    2177: {
        "message": "Unit Quantity Code(s)-{0} is/are not as per master",
        "reason": "Invalid unit code passed",
        "resolution": "Use standard UQC (e.g., NOS, PCS, KGS, BAG, MTR, TON, etc.)"
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
        "reason": "Sum of statecessamt across all items != stcesval in valdt1",
        "resolution": "Reconcile sum(item.statecessamt) to equal valdt1.stcesval"
    },
    2189: {
        "message": "Total Invoice Value is not matching with calculated value",
        "reason": "totinvval != ttlassval + taxes + othchrg - discval (+/- 1.00 tolerance)",
        "resolution": "Ensure totinvval matches total items + other charges - discount"
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
        "reason": "totitemval != assamt + cgst + sgst + igst + cess + stcess + othchrg",
        "resolution": "Ensure totitemval matches taxable value plus all taxes and other charges"
    },
    2195: {
        "message": "e-Commerce GSTIN is not registered as TCS-GSTIN",
        "reason": "ecom_gstin is not registered as Tax Collector",
        "resolution": "Verify e-commerce GSTIN type on GST portal"
    },
    2200: {
        "message": "State code {0} is invalid for dispatch details or ship details",
        "reason": "Invalid 2-digit state code in dispatch or ship details",
        "resolution": "Provide valid state code (01-38)"
    },
    2201: {
        "message": "Invalid Port Code",
        "reason": "Wrong port code format (must be 6-10 alphanumeric characters, e.g. INMAA1)",
        "resolution": "Verify Indian Port code from master list"
    },
    2202: {
        "message": "Invalid Country Code",
        "reason": "Wrong 2-letter ISO country code passed for export",
        "resolution": "Use standard ISO-2 country code (e.g., US, GB, AE, SG, DE)"
    },
    2203: {
        "message": "Invalid Foreign Currency",
        "reason": "Currency does not match destination country or ISO master",
        "resolution": "Provide valid 3-letter currency code (e.g., USD, EUR, GBP)"
    },
    2211: {
        "message": "Supplier and recipient GSTIN should not be the same.",
        "reason": "Self-invoicing is not permitted for e-invoice generation",
        "resolution": "Supplier GSTIN and Buyer GSTIN must be different"
    },
    2212: {
        "message": "The recipient GSTIN cannot be URP for supply type {0}",
        "reason": "URP passed for B2B/B2G/SEZ transaction",
        "resolution": "For B2B, B2G, and SEZ, pass valid 15-character recipient GSTIN"
    },
    2213: {
        "message": "The supplier GSTIN cannot be URP",
        "reason": "Supplier GSTIN is set to URP",
        "resolution": "Supplier GSTIN must be a valid 15-character GSTIN"
    },
    2227: {
        "message": "For Sl. No {0}, SGST and CGST amounts are not equal",
        "reason": "For intra-state supply, CGST and SGST amounts must be identical",
        "resolution": "Ensure cgstamt == sgstamt for each item"
    },
    2228: {
        "message": "Item list cannot be empty",
        "reason": "No items found in itemdtls",
        "resolution": "At least one line item must be present in itemdtls"
    },
    2231: {
        "message": "Cannot generate e-Invoice as the supplier GSTIN - {0} is SEZ",
        "reason": "SEZ unit supplier is exempt from generating e-invoice",
        "resolution": "Do not generate IRN for SEZ supplier"
    },
    2232: {
        "message": "POS is incorrect for {0} transaction",
        "reason": "POS must be 96 for Direct Export transactions",
        "resolution": "For EXP transactions, pos must be '96'"
    },
    2233: {
        "message": "Duplicate SI numbers are not allowed in line items",
        "reason": "Line item serial numbers are duplicated",
        "resolution": "Each item must have a unique sequential item index/number"
    },
    2234: {
        "message": "For Sl. No {0}, SGST and CGST amount passed does not match with taxable value and tax rate",
        "reason": "cgstamt or sgstamt != round(assamt * (rate/2) / 100, 2)",
        "resolution": "Pass correct CGST/SGST amounts matching the tax rate"
    },
    2235: {
        "message": "For Sl. No {0}, IGST amount passed is not matching with taxable value and tax rate",
        "reason": "igstamt != round(assamt * rate / 100, 2)",
        "resolution": "Pass correct IGST amount matching the tax rate"
    },
    2238: {
        "message": "For Sl. No {0}, Quantity is not passed",
        "reason": "Quantity missing for goods item",
        "resolution": "Pass numeric qty for goods items (isservc = 'N')"
    },
    2239: {
        "message": "For Sl. No {0}, Unit Quantity Code (UQC) is not passed",
        "reason": "UQC missing for goods item",
        "resolution": "Pass valid UQC for goods items"
    },
    2240: {
        "message": "For Sl. No {0}, GST rate of tax is incorrect or not as notified",
        "reason": "Tax rate is not among approved GST slabs (0, 0.1, 0.25, 0.5, 1, 1.5, 3, 5, 12, 18, 28)",
        "resolution": "Use standard notified GST rate"
    },
    2242: {
        "message": "Recipient POS is incorrect for transaction type {0}",
        "reason": "POS passed as 96 for domestic transaction",
        "resolution": "Pass valid 2-digit Indian state code for domestic POS"
    },
    2243: {
        "message": "POS code is invalid",
        "reason": "POS is not a valid 2-digit state code",
        "resolution": "Use valid state code (01-38 or 96 for exports)"
    },
    2244: {
        "message": "Recipient pincode is not provided for the transaction - {0}",
        "reason": "Buyer PIN code is missing",
        "resolution": "Pass valid 6-digit PIN code (or 999999 for exports)"
    },
    2246: {
        "message": "Recepient cannot be SEZ for - {0} transaction",
        "reason": "SEZ recipient passed for non-SEZ transaction type",
        "resolution": "Use SEZWP or SEZWOP transaction category when buyer is an SEZ unit"
    },
    2247: {
        "message": "Recepient should be SEZ for transaction {0}",
        "reason": "Transaction category is SEZWP or SEZWOP but buyer is not an SEZ unit",
        "resolution": "Pass SEZ recipient GSTIN or change transaction category"
    },
    2248: {
        "message": "Recepient has to be URP in case of Export transactions",
        "reason": "Buyer GSTIN was not set to 'URP' for export transaction",
        "resolution": "Set buyer_gstin = 'URP' for export transactions"
    },
    2258: {
        "message": "Supplier GSTIN state codedoes not match with the state code passed in supplier details",
        "reason": "First 2 digits of supplier_gstin != supplier_state",
        "resolution": "Ensure supplier_state equals supplier_gstin[:2]"
    },
    2259: {
        "message": "Invalid supplier state code",
        "reason": "Supplier state code is not valid (01-38)",
        "resolution": "Pass valid 2-digit numeric state code"
    },
    2260: {
        "message": "The recipient state code is invalid",
        "reason": "Buyer state code is not valid",
        "resolution": "Pass valid 2-digit state code (01-38 or 96 for exports)"
    },
    2261: {
        "message": "The recipient state code is incorrect for {0} transaction",
        "reason": "Recipient state code must be 96 for export transactions",
        "resolution": "Set buyer_state = '96' for export transactions"
    },
    2262: {
        "message": "For Intra-state supply, IGST cannot be charged",
        "reason": "igstonintra='Y' but supplier state != POS",
        "resolution": "igstonintra can only be 'Y' when supplier_state == pos"
    },
    2265: {
        "message": "Recipient GSTIN state code does not match with the state code passed in recipient details",
        "reason": "First 2 digits of buyer_gstin != buyer_state",
        "resolution": "Ensure buyer_state matches first two digits of buyer_gstin"
    },
    2268: {
        "message": "IGST on intra state supply is not applicable to export/SEZ transactions",
        "reason": "igstonintra='Y' for export or SEZ transaction",
        "resolution": "Set igstonintra = 'N' for export and SEZ transactions"
    },
    2271: {
        "message": "SHIP TO - state code is not valid statecode for B2B, SEZ and Deemed Export transactions",
        "reason": "Invalid state code in shipdtl",
        "resolution": "Pass valid 2-digit state code (01-38)"
    },
    2272: {
        "message": "SHIP TO - PIN code cannot be 999999 for B2B, SEZ and Deemed Export transactions",
        "reason": "ship_pin passed as 999999 for domestic/SEZ transaction",
        "resolution": "Provide actual 6-digit PIN code for shipping location"
    },
    2273: {
        "message": "Dispatch from PIN code cannot be 999999",
        "reason": "disp_pin passed as 999999",
        "resolution": "Dispatch from PIN code must be a valid 6-digit domestic PIN code"
    },
    2274: {
        "message": "Recipient PIN code cannot be 999999 for {0} transaction.",
        "reason": "buyer_pin passed as 999999 for domestic transaction",
        "resolution": "Provide actual 6-digit PIN code for domestic buyer"
    },
    2275: {
        "message": "Recipient PIN code should be 999999 for Direct Export",
        "reason": "buyer_pin is not 999999 for Direct Export",
        "resolution": "Set buyer_pin = '999999' when trancatg is 'EXP'"
    },
    2276: {
        "message": "Supplier PIN code cannot be 999999",
        "reason": "supplier_pin passed as 999999",
        "resolution": "Supplier PIN code must be a valid 6-digit domestic PIN code"
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
