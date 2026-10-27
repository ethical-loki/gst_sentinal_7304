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
    "CCM", "CMS", "CTN", "DOZ", "DRM", "GGR", "GMS", "GRS", "GYD", "KGS", "KLR",
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
        "reason": "Total taxable/assessable value declared at invoice header (ValDtls.AssVal) does not match the sum of taxable/assessable values across all line items (sum(ItemList[i].AssAmt)). Strict mathematical equality enforced.",
        "resolution": "Reconcile ValDtls.AssVal dynamically to strictly equal sum(ItemList[i].AssAmt). Check for: 1. Header not updated after item edits; 2. Pre-tax discount deducted twice; 3. Paise/decimal rounding issue; 4. Gross total (TotAmt) used instead of AssAmt.",
        "scenarios": {
            "HEADER_NOT_UPDATED_AFTER_ITEM_EDITS": {
                "name": "Header Not Updated After Item Edits",
                "fix": "Ensure ValDtls.AssVal dynamically recalculates the sum of all ItemList[i].AssAmt before sending."
            },
            "PRE_TAX_DISCOUNT_DEDUCTED_TWICE": {
                "name": "Pre-tax Discount Deducted Twice",
                "fix": "In e-Invoicing, AssVal must equal the sum of item assessable values (AssAmt), which already account for item-level discounts. Deducting the discount again at ValDtls.AssVal causes a mismatch."
            },
            "PAISE_DECIMAL_ROUNDING_ISSUE": {
                "name": "Paise / Decimal Rounding Issue",
                "fix": "Line-item totals and header assessable values must be identical to 2 decimal places. Reconcile header assessable value or adjust last line item AssAmt."
            },
            "GROSS_TOTAL_USED_AS_ASSVAL": {
                "name": "Gross Total (TotAmt) Used Instead of AssAmt",
                "fix": "AssVal must strictly equal the sum of AssAmt (net taxable value), not TotAmt (gross value before discount)."
            }
        }
    },
    2183: {
        "message": "SGST value of all items is not equal to total SGST Value",
        "reason": "Total SGST declared at the invoice header (ValDtls.SgstVal) does not match the sum of individual SGST amounts across all line items (sum(ItemList[i].SgstAmt)). Strict mathematical equality enforced.",
        "resolution": "Ensure ValDtls.SgstVal dynamically computes the sum of all ItemList[i].SgstAmt. Check for stale header after item edits, paise rounding mismatch, combined taxes under SGST, omitted header values, or inter-state SGST.",
        "scenarios": {
            "HEADER_NOT_RECALCULATED_AFTER_ITEM_EDITS": {
                "name": "Header Not Recalculated After Item Edits",
                "fix": "Ensure ValDtls.SgstVal dynamically computes the sum of all ItemList[i].SgstAmt before sending."
            },
            "DECIMAL_PAISE_ROUNDING_MISMATCH": {
                "name": "Decimal / Paise Rounding Mismatch",
                "fix": "Line-item sum and SgstVal must match to 2 decimal places. Adjust header or line item paise rounding."
            },
            "COMBINED_TAX_PASSED_AS_SINGLE_VALUE": {
                "name": "Combined Tax Passed as Single Value",
                "fix": "Split tax equally between CGST and SGST at the header instead of placing the entire tax under SGST."
            },
            "ITEM_LEVEL_POPULATED_HEADER_ZERO_OR_NULL": {
                "name": "Item Level Populated, Header Left as 0 or Null",
                "fix": "Header tax values in ValDtls are mandatory for intra-state supplies. Populate ValDtls.SgstVal from items."
            },
            "INTER_STATE_TRANSACTION_PASSING_SGST": {
                "name": "Inter-State Transaction Passing SGST",
                "fix": "Inter-state transactions must not carry SGST amounts. Clear both item-level SgstAmt and ValDtls.SgstVal to 0.00 and pass the tax under IgstAmt / IgstVal."
            }
        }
    },
    2184: {
        "message": "CGST value of all items is not equal to total CGST Value",
        "reason": "Total CGST declared at the invoice header (ValDtls.CgstVal) does not match the sum of individual CGST amounts across all line items (sum(ItemList[i].CgstAmt)). Strict mathematical equality enforced.",
        "resolution": "Ensure ValDtls.CgstVal dynamically computes the sum of all ItemList[i].CgstAmt. Check for stale header after item edits, paise rounding mismatch, combined taxes under CGST, omitted header values, or inter-state CGST.",
        "scenarios": {
            "HEADER_NOT_RECALCULATED_AFTER_ITEM_EDITS": {
                "name": "Header Not Recalculated After Item Edits",
                "fix": "Ensure ValDtls.CgstVal dynamically computes the sum of all ItemList[i].CgstAmt before sending."
            },
            "DECIMAL_PAISE_ROUNDING_MISMATCH": {
                "name": "Decimal / Paise Rounding Mismatch",
                "fix": "Line-item sum and CgstVal must match to 2 decimal places. Reconcile paise rounding."
            },
            "COMBINED_TAX_PASSED_AS_SINGLE_VALUE": {
                "name": "Combined Tax Passed as Single Value",
                "fix": "The full tax was placed entirely under CGST at the header instead of splitting it equally between CGST and SGST."
            },
            "ITEM_LEVEL_POPULATED_HEADER_ZERO_OR_NULL": {
                "name": "Item Level Populated, Header Left as 0 or Null",
                "fix": "Header tax values in ValDtls are mandatory for intra-state supplies. CgstVal cannot be 0.00 if line items have positive CGST."
            },
            "INTER_STATE_TRANSACTION_PASSING_CGST": {
                "name": "Inter-State Transaction Passing CGST",
                "fix": "Inter-state transactions must not carry CGST amounts. Clear both item-level CgstAmt and ValDtls.CgstVal to 0.00 and pass the tax under IgstAmt / IgstVal."
            }
        }
    },
    2185: {
        "message": "IGST value of all items is not equal to total IGST Value",
        "reason": "Total IGST declared at the invoice header (ValDtls.IgstVal) does not match the sum of individual IGST amounts across all line items (sum(ItemList[i].IgstAmt)). Strict mathematical equality enforced.",
        "resolution": "Ensure ValDtls.IgstVal dynamically computes the sum of all ItemList[i].IgstAmt. Check for stale header after item edits, paise rounding mismatch, omitted header values, intra-state IGST, or export/SEZ with payment miscalculation.",
        "scenarios": {
            "HEADER_NOT_RECALCULATED_AFTER_ITEM_EDITS": {
                "name": "Header Not Recalculated After Item Edits",
                "fix": "Ensure ValDtls.IgstVal dynamically computes the sum of all ItemList[i].IgstAmt before sending."
            },
            "DECIMAL_PAISE_ROUNDING_MISMATCH": {
                "name": "Decimal / Paise Rounding Mismatch",
                "fix": "Line-item sum and IgstVal must match to 2 decimal places. Reconcile paise rounding."
            },
            "ITEM_LEVEL_POPULATED_HEADER_ZERO_OR_NULL": {
                "name": "Item Level Populated, Header Left as 0 or Null",
                "fix": "Header tax values in ValDtls are mandatory for inter-state supplies. IgstVal cannot be 0.00 if line items have positive IGST."
            },
            "INTRA_STATE_SUPPLY_PASSING_IGST_IN_SUMMARY": {
                "name": "Intra-State Supply Passing IGST in Summary",
                "fix": "For standard intra-state supplies, ValDtls.IgstVal must be 0.00 unless IgstOnIntra is set to 'Y'."
            },
            "EXPORT_SEZ_WITH_PAYMENT_MISCALCULATION": {
                "name": "Export / SEZ with Payment Miscalculation",
                "fix": "In EXPWP / SEZWP, IGST amounts must follow the exact same item-to-header aggregation rules. Ensure sum of IgstAmt across export line items strictly matches ValDtls.IgstVal."
            }
        }
    },
    2186: {
        "message": "Cess value of all items is not equal to total Cess Value",
        "reason": "Total GST Compensation Cess declared at the invoice header (ValDtls.CesVal) does not match the sum of individual Cess amounts across all line items (sum(ItemList[i].CesAmt + ItemList[i].CesNonAdvlAmt)). Strict mathematical equality enforced.",
        "resolution": "Ensure ValDtls.CesVal dynamically sums both ad-valorem Cess (CesAmt) and non-ad-valorem Cess (CesNonAdvlAmt) across all line items to 2 decimal places. Do not mix State Cess into CesVal.",
        "scenarios": {
            "HEADER_NOT_RECALCULATED_AFTER_ITEM_EDITS": {
                "name": "Header Not Recalculated After Item Edits",
                "fix": "Ensure ValDtls.CesVal dynamically sums both ad-valorem Cess (CesAmt) and non-ad-valorem Cess (CesNonAdvlAmt) across all line items."
            },
            "AD_VALOREM_VS_NON_AD_VALOREM_CESS_OMISSION": {
                "name": "Ad-Valorem vs Non-Ad-Valorem Cess Omission",
                "fix": "ValDtls.CesVal represents the aggregate Cess total. It must include both percentage-based Cess (CesAmt) and fixed/quantity-based Cess (CesNonAdvlAmt)."
            },
            "STATE_CESS_MIXED_WITH_CENTRAL_CESS": {
                "name": "State Cess Mixed with Central Cess",
                "fix": "Do not merge State Cess (Kerala Flood Cess / State Cess) into GST Compensation Cess. Keep them in their distinct fields (CesVal vs StCesVal)."
            },
            "DECIMAL_PAISE_ROUNDING_MISMATCH": {
                "name": "Decimal / Paise Rounding Mismatch",
                "fix": "Sum of item CesAmt must match ValDtls.CesVal to 2 decimal places. Reconcile paise rounding."
            },
            "CESS_POPULATED_LINE_ITEM_ZERO_HEADER": {
                "name": "Cess Populated at Line Item but 0/Null at Header",
                "fix": "If any line item carries Cess, ValDtls.CesVal must reflect the non-zero total. If no goods attract Cess, leave both item and header fields as 0.00."
            }
        }
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
        "reason": "The gross total amount of a line item (TotAmt) does not equal the arithmetic product of its quantity (Qty) and unit price (UnitPrice): ItemList[i].TotAmt = ItemList[i].Qty * ItemList[i].UnitPrice. Strict calculation checked at each item row. Triggered by premature discount/tax deduction, decimal rounding in unit price, or zero quantity on services.",
        "resolution": "TotAmt represents gross value before discount and pre-tax. Ensure TotAmt strictly equals Qty * UnitPrice up to 2 decimal places. For services with conceptual quantity, set Qty: 1.",
        "scenarios": {
            "PREMATURE_DISCOUNT_DEDUCTION": {
                "name": "Premature Discount Deduction",
                "fix": "TotAmt represents gross value before discount. Discounts are deducted in AssAmt, not TotAmt. Reconcile TotAmt = Qty * UnitPrice."
            },
            "PREMATURE_TAX_INCLUSION": {
                "name": "Premature Tax Inclusion",
                "fix": "TotAmt is pre-tax. Taxes belong to IgstAmt / CgstAmt / SgstAmt, and post-tax values belong to TotItemVal. Reconcile TotAmt = Qty * UnitPrice."
            },
            "DECIMAL_ROUNDING_IN_UNIT_PRICE": {
                "name": "Decimal Rounding in Unit Price",
                "fix": "TotAmt must match Qty * UnitPrice up to 2 decimal places (or set UnitPrice with 3-4 decimals if ERP supports)."
            },
            "SERVICES_WITH_NULL_OR_MISSING_QTY": {
                "name": "Services with Null or Missing Qty",
                "fix": "Even for service lines (IsServc='Y' or HSN 99xxxx) where quantity is conceptual, set Qty: 1 so that 1 * UnitPrice = TotAmt."
            }
        }
    },
    2193: {
        "message": "For Sl. No. {0}, Taxable Value (AssAmt) value is not equal to (TotAmt - Discount)",
        "reason": "The net taxable value of a line item (AssAmt) does not equal the item gross amount (TotAmt) minus the item discount (Discount): ItemList[i].AssAmt = ItemList[i].TotAmt - ItemList[i].Discount. If Discount is 0.00 or omitted, AssAmt must strictly equal TotAmt.",
        "resolution": "Ensure AssAmt strictly equals TotAmt - Discount for every item row. Provide actual discount in Discount field, exclude taxes and extra charges from AssAmt.",
        "scenarios": {
            "DISCOUNT_PASSED_BUT_NOT_SUBTRACTED": {
                "name": "Discount Passed but Not Subtracted",
                "fix": "When a discount is entered, AssAmt must reflect the discounted assessable base (AssAmt = TotAmt - Discount)."
            },
            "DISCOUNT_SUBTRACTED_IN_TAXABLE_BASE_BUT_ZERO_IN_FIELD": {
                "name": "Discount Subtracted in Taxable Base but Left 0 in Field",
                "fix": "If Discount is passed as 0.00, the schema expects AssAmt = TotAmt. Provide the actual discount amount in 'Discount' (or set TotAmt to net amount)."
            },
            "POST_TAX_VALUE_ENTERED_INTO_ASSESSABLE_AMOUNT": {
                "name": "Post-Tax Value Entered into Assessable Amount",
                "fix": "AssAmt is the taxable amount on which GST is levied. Tax should not be added here; tax is added in TotItemVal."
            },
            "OTHER_ITEM_CHARGES_ADDED_DIRECTLY_TO_ASSAMT": {
                "name": "Other Item Charges Added Directly to AssAmt",
                "fix": "Pass item other charges in OthChrg (or reflect them in UnitPrice directly) so that AssAmt = TotAmt - Discount remains balanced."
            }
        }
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
        "scenarios": [
            "LEADING_ZERO_OMITTED",
            "ALPHA_CODE_USED",
            "STATE_CODE_DISAGREES_WITH_GSTIN",
            "INVALID_OR_NON_EXISTENT_CODE"
        ]
    },
    2201: {
        "message": "Invalid Port Code for Export Transaction",
        "reason": "Export invoice (trancatg EXPWP / EXPWOP) contains a value in ExpDtls.Port (Shipping Bill Port Code) that does not exist in the official Indian Customs EDI / ICEGATE port code master list, has improper formatting, or is erroneously provided for domestic supply.",
        "resolution": "Ensure ExpDtls.Port is a standard 6-character alphanumeric ICEGATE / UN-LOCODE (e.g. INNSA1, INBOM1, INBOM4, INDEL4, INBLR4) without spaces, hyphens, or city names. Match port type to transport mode (Air vs Sea), and omit ExpDtls entirely for domestic transactions.",
        "scenarios": [
            "INFORMAL_OR_CITY_NAME_USED",
            "AIR_SEA_PORT_CODE_CONFUSION",
            "WRONG_FORMAT_SPACING_SPECIAL_CHARS",
            "PORT_CODE_PROVIDED_FOR_DOMESTIC_SUPPLY"
        ]
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

# Alias for compatibility across rules engine and validator
NIC_ERROR_CODES = IRN_ERRORS

# ============================================================================
# 6. OFFICIAL NIC / GSTN UQC MASTER CATALOG & STATUTORY MAPPINGS (Rule 2177)
# ============================================================================

OFFICIAL_UQC_MASTER: Dict[str, Dict[str, str]] = {
    "BAG": {"description": "Bags", "category": "Packaging / Quantity"},
    "BAL": {"description": "Bales", "category": "Packaging / Quantity"},
    "BDL": {"description": "Bundles", "category": "Packaging / Quantity"},
    "BKL": {"description": "Buckles", "category": "Measure"},
    "BOU": {"description": "Billions of Units", "category": "Count / Large Units"},
    "BOX": {"description": "Boxes", "category": "Packaging"},
    "BTL": {"description": "Bottles", "category": "Packaging"},
    "BUN": {"description": "Bunches", "category": "Packaging / Quantity"},
    "CAN": {"description": "Cans", "category": "Packaging"},
    "CBM": {"description": "Cubic Meters", "category": "Volume"},
    "CCM": {"description": "Cubic Centimeters", "category": "Volume"},
    "CMS": {"description": "Centimeters", "category": "Length"},
    "CTN": {"description": "Cartons", "category": "Packaging"},
    "DOZ": {"description": "Dozens", "category": "Count"},
    "DRM": {"description": "Drums", "category": "Packaging"},
    "GGR": {"description": "Great Gross", "category": "Count (12 gross = 1728 units)"},
    "GMS": {"description": "Grams", "category": "Weight"},
    "GRS": {"description": "Gross", "category": "Count (12 dozen = 144 units)"},
    "GYD": {"description": "Gross Yards", "category": "Length"},
    "KGS": {"description": "Kilograms", "category": "Weight"},
    "KLR": {"description": "Kilolitres", "category": "Volume"},
    "KME": {"description": "Kilometres", "category": "Length"},
    "MLT": {"description": "Millilitres", "category": "Volume"},
    "MTR": {"description": "Metres", "category": "Length"},
    "MTS": {"description": "Metric Tons", "category": "Weight"},
    "NOS": {"description": "Numbers", "category": "Count"},
    "PAC": {"description": "Packs", "category": "Packaging"},
    "PCS": {"description": "Pieces", "category": "Count"},
    "PRS": {"description": "Pairs", "category": "Count"},
    "QTL": {"description": "Quintals", "category": "Weight (100 kg)"},
    "ROL": {"description": "Rolls", "category": "Packaging / Length"},
    "SET": {"description": "Sets", "category": "Packaging / Grouping"},
    "SQF": {"description": "Square Feet", "category": "Area"},
    "SQM": {"description": "Square Metres", "category": "Area"},
    "SQY": {"description": "Square Yards", "category": "Area"},
    "TBS": {"description": "Tablets", "category": "Pharmaceutical / Measure"},
    "TGM": {"description": "Ten Grams", "category": "Weight"},
    "THD": {"description": "Thousands", "category": "Count"},
    "TON": {"description": "Tonnes", "category": "Weight"},
    "TUB": {"description": "Tubes", "category": "Packaging"},
    "UGS": {"description": "US Gallons", "category": "Volume"},
    "UNT": {"description": "Units", "category": "Count / Measure"},
    "YDS": {"description": "Yards", "category": "Length"},
    "OTH": {"description": "Others", "category": "Any unit not listed above"}
}

COMMON_UQC_MAPPING: Dict[str, Tuple[str, str, str]] = {
    # 1. Standard Weight KG
    "KG": ("KGS", "STANDARD_WEIGHT_KG", "GST portal requires 3-letter standard KGS."),
    "KGS": ("KGS", "VALID_MASTER_UQC", "Valid standard UQC."),
    "KILOGRAM": ("KGS", "STANDARD_WEIGHT_KG", "GST portal requires 3-letter standard KGS."),
    "KILOGRAMS": ("KGS", "STANDARD_WEIGHT_KG", "GST portal requires 3-letter standard KGS."),
    "KG.": ("KGS", "STANDARD_WEIGHT_KG", "GST portal requires 3-letter standard KGS."),
    "KGS.": ("KGS", "STANDARD_WEIGHT_KG", "GST portal requires 3-letter standard KGS."),

    # 2. Count NO / PIECES
    "NO": ("NOS", "COLLOQUIAL_COUNT_NO", "Map to either NOS (Numbers) or PCS (Pieces)."),
    "NO.": ("NOS", "COLLOQUIAL_COUNT_NO", "Map to either NOS (Numbers) or PCS (Pieces)."),
    "NOS.": ("NOS", "COLLOQUIAL_COUNT_NO", "Map to either NOS (Numbers) or PCS (Pieces)."),
    "NUMBER": ("NOS", "COLLOQUIAL_COUNT_NO", "Map to either NOS (Numbers) or PCS (Pieces)."),
    "NUMBERS": ("NOS", "COLLOQUIAL_COUNT_NO", "Map to either NOS (Numbers) or PCS (Pieces)."),
    "PIECE": ("PCS", "COLLOQUIAL_COUNT_PIECES", "Map to either NOS (Numbers) or PCS (Pieces)."),
    "PIECES": ("PCS", "COLLOQUIAL_COUNT_PIECES", "Map to either NOS (Numbers) or PCS (Pieces)."),
    "PC": ("PCS", "COLLOQUIAL_COUNT_PIECES", "Map to either NOS (Numbers) or PCS (Pieces)."),
    "PCS.": ("PCS", "COLLOQUIAL_COUNT_PIECES", "Map to either NOS (Numbers) or PCS (Pieces)."),

    # 3. Non-Standard Volume Litre
    "LTR": ("OTH", "NON_STANDARD_VOLUME_LTR", "LTR is not part of the standard UQC list. Convert to KLR / MLT or pass OTH."),
    "LTRS": ("OTH", "NON_STANDARD_VOLUME_LTR", "LTR is not part of the standard UQC list. Convert to KLR / MLT or pass OTH."),
    "LITER": ("OTH", "NON_STANDARD_VOLUME_LTR", "LTR is not part of the standard UQC list. Convert to KLR / MLT or pass OTH."),
    "LITERS": ("OTH", "NON_STANDARD_VOLUME_LTR", "LTR is not part of the standard UQC list. Convert to KLR / MLT or pass OTH."),
    "LITRE": ("OTH", "NON_STANDARD_VOLUME_LTR", "LTR is not part of the standard UQC list. Convert to KLR / MLT or pass OTH."),
    "LITRES": ("OTH", "NON_STANDARD_VOLUME_LTR", "LTR is not part of the standard UQC list. Convert to KLR / MLT or pass OTH."),
    "L": ("OTH", "NON_STANDARD_VOLUME_LTR", "LTR is not part of the standard UQC list. Convert to KLR / MLT or pass OTH."),
    "L.": ("OTH", "NON_STANDARD_VOLUME_LTR", "LTR is not part of the standard UQC list. Convert to KLR / MLT or pass OTH."),

    # 4. Linear Measure Meter
    "METER": ("MTR", "LINEAR_MEASURE_METER", "Standard unit of linear measurement is MTR."),
    "METERS": ("MTR", "LINEAR_MEASURE_METER", "Standard unit of linear measurement is MTR."),
    "METRE": ("MTR", "LINEAR_MEASURE_METER", "Standard unit of linear measurement is MTR."),
    "METRES": ("MTR", "LINEAR_MEASURE_METER", "Standard unit of linear measurement is MTR."),
    "MT": ("MTR", "LINEAR_MEASURE_METER", "Standard unit of linear measurement is MTR."),
    "MTR.": ("MTR", "LINEAR_MEASURE_METER", "Standard unit of linear measurement is MTR."),

    # 5. Weight Tonne / Metric Ton
    "TONNE": ("TON", "WEIGHT_TONNES", "Use MTS (Metric Ton) or TON (Tonne)."),
    "TONNES": ("TON", "WEIGHT_TONNES", "Use MTS (Metric Ton) or TON (Tonne)."),
    "METRIC TON": ("MTS", "WEIGHT_METRIC_TON", "Use MTS (Metric Ton) or TON (Tonne)."),
    "METRIC TONS": ("MTS", "WEIGHT_METRIC_TON", "Use MTS (Metric Ton) or TON (Tonne)."),
    "MT.": ("MTR", "LINEAR_MEASURE_METER", "Standard unit of linear measurement is MTR."),

    # 6. Bundles
    "BNDL": ("BDL", "PACKAGING_BUNDLE", "The valid 3-letter code for bundles is BDL."),
    "BUNDLE": ("BDL", "PACKAGING_BUNDLE", "The valid 3-letter code for bundles is BDL."),
    "BUNDLES": ("BDL", "PACKAGING_BUNDLE", "The valid 3-letter code for bundles is BDL."),

    # 7. Packs / Packets
    "PACKET": ("PAC", "PACKAGING_PACKET", "The valid code for packs/packets is PAC."),
    "PACKETS": ("PAC", "PACKAGING_PACKET", "The valid code for packs/packets is PAC."),
    "PKT": ("PAC", "PACKAGING_PACKET", "The valid code for packs/packets is PAC."),
    "PKTS": ("PAC", "PACKAGING_PACKET", "The valid code for packs/packets is PAC."),
    "PACK": ("PAC", "PACKAGING_PACKET", "The valid code for packs/packets is PAC."),
    "PACKS": ("PAC", "PACKAGING_PACKET", "The valid code for packs/packets is PAC."),

    # Common English Names / Plurals
    "BAGS": ("BAG", "PACKAGING_BAGS", "The valid 3-letter code for bags is BAG."),
    "BALES": ("BAL", "PACKAGING_BALES", "The valid 3-letter code for bales is BAL."),
    "BOXES": ("BOX", "PACKAGING_BOXES", "The valid 3-letter code for boxes is BOX."),
    "BOTTLE": ("BTL", "PACKAGING_BOTTLES", "The valid 3-letter code for bottles is BTL."),
    "BOTTLES": ("BTL", "PACKAGING_BOTTLES", "The valid 3-letter code for bottles is BTL."),
    "BUNCH": ("BUN", "PACKAGING_BUNCHES", "The valid 3-letter code for bunches is BUN."),
    "BUNCHES": ("BUN", "PACKAGING_BUNCHES", "The valid 3-letter code for bunches is BUN."),
    "CANS": ("CAN", "PACKAGING_CANS", "The valid 3-letter code for cans is CAN."),
    "CARTON": ("CTN", "PACKAGING_CARTONS", "The valid 3-letter code for cartons is CTN."),
    "CARTONS": ("CTN", "PACKAGING_CARTONS", "The valid 3-letter code for cartons is CTN."),
    "DOZEN": ("DOZ", "COUNT_DOZENS", "The valid 3-letter code for dozens is DOZ."),
    "DOZENS": ("DOZ", "COUNT_DOZENS", "The valid 3-letter code for dozens is DOZ."),
    "DRUM": ("DRM", "PACKAGING_DRUMS", "The valid 3-letter code for drums is DRM."),
    "DRUMS": ("DRM", "PACKAGING_DRUMS", "The valid 3-letter code for drums is DRM."),
    "GRAM": ("GMS", "WEIGHT_GRAMS", "The valid 3-letter code for grams is GMS."),
    "GRAMS": ("GMS", "WEIGHT_GRAMS", "The valid 3-letter code for grams is GMS."),
    "GM": ("GMS", "WEIGHT_GRAMS", "The valid 3-letter code for grams is GMS."),
    "GMS.": ("GMS", "WEIGHT_GRAMS", "The valid 3-letter code for grams is GMS."),
    "QUINTAL": ("QTL", "WEIGHT_QUINTALS", "The valid 3-letter code for quintals is QTL."),
    "QUINTALS": ("QTL", "WEIGHT_QUINTALS", "The valid 3-letter code for quintals is QTL."),
    "ROLL": ("ROL", "PACKAGING_ROLLS", "The valid 3-letter code for rolls is ROL."),
    "ROLLS": ("ROL", "PACKAGING_ROLLS", "The valid 3-letter code for rolls is ROL."),
    "SETS": ("SET", "PACKAGING_SETS", "The valid 3-letter code for sets is SET."),
    "TABLET": ("TBS", "MEASURE_TABLETS", "The valid 3-letter code for tablets is TBS."),
    "TABLETS": ("TBS", "MEASURE_TABLETS", "The valid 3-letter code for tablets is TBS."),
    "THOUSAND": ("THD", "COUNT_THOUSANDS", "The valid 3-letter code for thousands is THD."),
    "THOUSANDS": ("THD", "COUNT_THOUSANDS", "The valid 3-letter code for thousands is THD."),
    "TUBE": ("TUB", "PACKAGING_TUBES", "The valid 3-letter code for tubes is TUB."),
    "TUBES": ("TUB", "PACKAGING_TUBES", "The valid 3-letter code for tubes is TUB."),
    "UNIT": ("UNT", "COUNT_UNITS", "The valid 3-letter code for units is UNT."),
    "UNITS": ("UNT", "COUNT_UNITS", "The valid 3-letter code for units is UNT."),
    "YARD": ("YDS", "LENGTH_YARDS", "The valid 3-letter code for yards is YDS."),
    "YARDS": ("YDS", "LENGTH_YARDS", "The valid 3-letter code for yards is YDS.")
}


def classify_rule_2177_diagnostic(declared_uqc: Any) -> Dict[str, Any]:
    """
    Classifies Indian GST e-Invoicing (NIC / IRP) Error Code 2177:
    'Unit Quantity Code (UQC) is not as per master'
    The IRP does not accept colloquial, arbitrary, or ERP-specific abbreviations
    (e.g., 'KG', 'LITRE', 'PCS.', or 'NO'). If an item's unit is not explicitly on
    the official 3-character master list, the fallback code OTH (Others) must be passed.
    """
    raw_s = str(declared_uqc or "").strip()
    clean_upper = raw_s.upper()

    # 1. Strict Exact match on official 3-letter uppercase master (no punctuation)
    if raw_s == clean_upper and raw_s in ALLOWED_UQC and len(raw_s) == 3:
        meta = OFFICIAL_UQC_MASTER.get(raw_s, {"description": raw_s, "category": "Standard"})
        return {
            "error_code": 2177,
            "is_valid": True,
            "scenario": "VALID_MASTER_UQC",
            "scenario_name": "Valid Official Master UQC",
            "declared_uqc": raw_s,
            "rectified_uqc": raw_s,
            "description": meta["description"],
            "category": meta["category"],
            "reason": f"Unit Quantity Code '{raw_s}' is officially recognized on the NIC master list ({meta['description']}).",
            "resolution": "No correction required."
        }

    # 2. Known colloquial / ERP abbreviation mapping takes precedence for non-standard inputs
    if raw_s in COMMON_UQC_MAPPING or clean_upper in COMMON_UQC_MAPPING:
        lookup_key = raw_s if raw_s in COMMON_UQC_MAPPING else clean_upper
        target, scen, reason = COMMON_UQC_MAPPING[lookup_key]
        if scen != "VALID_MASTER_UQC":
            meta = OFFICIAL_UQC_MASTER.get(target, {"description": target, "category": "Standard"})
            return {
                "error_code": 2177,
                "is_valid": False,
                "scenario": scen,
                "scenario_name": f"Colloquial / ERP Unit Mapping ({raw_s} -> {target})",
                "declared_uqc": raw_s,
                "rectified_uqc": target,
                "description": meta["description"],
                "category": meta["category"],
                "reason": reason,
                "resolution": f"Map '{raw_s}' to official 3-letter standard '{target}' ({meta['description']})."
            }

    # 3. Normalized string in colloquial mapping (e.g. after rstrip)
    norm = clean_upper.rstrip(".")
    if norm in COMMON_UQC_MAPPING:
        target, scen, reason = COMMON_UQC_MAPPING[norm]
        meta = OFFICIAL_UQC_MASTER.get(target, {"description": target, "category": "Standard"})
        return {
            "error_code": 2177,
            "is_valid": False,
            "scenario": scen,
            "scenario_name": f"Colloquial / ERP Unit Mapping ({raw_s} -> {target})",
            "declared_uqc": raw_s,
            "rectified_uqc": target,
            "description": meta["description"],
            "category": meta["category"],
            "reason": reason,
            "resolution": f"Map '{raw_s}' to official 3-letter standard '{target}' ({meta['description']})."
        }

    # 4. If normalized string matches master but had casing or punctuation differences
    if norm in ALLOWED_UQC and len(norm) == 3:
        meta = OFFICIAL_UQC_MASTER.get(norm, {"description": norm, "category": "Standard"})
        return {
            "error_code": 2177,
            "is_valid": False,
            "scenario": "CASE_OR_PUNCTUATION_FORMATTING",
            "scenario_name": f"Formatting Normalization ({raw_s} -> {norm})",
            "declared_uqc": raw_s,
            "rectified_uqc": norm,
            "description": meta["description"],
            "category": meta["category"],
            "reason": f"GST portal requires strict 3-letter uppercase code without punctuation. Original '{raw_s}' formatted to '{norm}'.",
            "resolution": f"Pass official 3-letter standard '{norm}'."
        }

    # 5. Custom / Non-listed units fallback to OTH
    return {
        "error_code": 2177,
        "is_valid": False,
        "scenario": "CUSTOM_NON_LISTED_UNIT",
        "scenario_name": f"Custom / Non-Listed Unit ({raw_s} -> OTH)",
        "declared_uqc": raw_s,
        "rectified_uqc": "OTH",
        "description": "Others",
        "category": "Any unit not listed above",
        "reason": "Use OTH (Others) for unlisted units. The IRP does not accept colloquial, arbitrary, or ERP-specific abbreviations. If an item's unit is not explicitly on the master list, the fallback code OTH (Others) must be passed.",
        "resolution": "Pass OTH (Others) for unlisted units."
    }


def normalize_uqc_statutory(declared_uqc: Any) -> Tuple[str, Dict[str, Any]]:
    """
    Normalizes any raw input Unit Quantity Code to an official 3-letter NIC master code.
    Returns (rectified_uqc, diagnostic_dict).
    """
    diag = classify_rule_2177_diagnostic(declared_uqc)
    return diag["rectified_uqc"], diag
