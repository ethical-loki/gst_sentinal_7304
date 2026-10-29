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
        "message": "Supplier GSTIN state codedoes not match with the state code passed in supplier details",
        "reason": "The first two digits of the Supplier GSTIN represent the State Code. The state code passed in SellerDtls.StateCode does not match the first two digits of SellerDtls.Gstin.",
        "resolution": "Align SellerDtls.StateCode to match the first two digits of SellerDtls.Gstin.",
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
