"""
Pre-API Validation Engine for Indian GST E-Invoice & E-Way Bill Payloads.
Checks all NIC IRN (2143-9999) and EWB (4000-4076) compliance rules before dispatch,
including complete GSTIN length validation, key field & value constraints,
SEZ transactions, PIN-State mismatches, Port codes, and Currency masters.
"""

import re
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, List, Optional

try:
    from .error_mappings import (
        IRN_ERRORS,
        EWB_ERRORS,
        ALLOWED_DOC_TYPES,
        ALLOWED_TRAN_CATG,
        ALLOWED_TAX_RATES,
        ALLOWED_UQC,
        VALID_STATE_CODES,
        STATE_MASTER,
        verify_pincode_state,
        COUNTRY_CURRENCY_MAP,
        COUNTRY_MASTER,
        VALID_CURRENCIES,
        MAJOR_INDIAN_PORTS,
        classify_rule_2177_diagnostic,
        normalize_uqc_statutory
    )
except ImportError:
    from error_mappings import (
        IRN_ERRORS,
        EWB_ERRORS,
        ALLOWED_DOC_TYPES,
        ALLOWED_TRAN_CATG,
        ALLOWED_TAX_RATES,
        ALLOWED_UQC,
        VALID_STATE_CODES,
        STATE_MASTER,
        verify_pincode_state,
        COUNTRY_CURRENCY_MAP,
        COUNTRY_MASTER,
        VALID_CURRENCIES,
        MAJOR_INDIAN_PORTS,
        classify_rule_2177_diagnostic,
        normalize_uqc_statutory
    )

try:
    from .price_anomaly_detector import PriceAnomalyDetector
except ImportError:
    try:
        from price_anomaly_detector import PriceAnomalyDetector
    except ImportError:
        PriceAnomalyDetector = None

try:
    from .hsn_resolver import validate_hsn_statutory, lookup_hsn_code
except ImportError:
    try:
        from hsn_resolver import validate_hsn_statutory, lookup_hsn_code
    except ImportError:
        validate_hsn_statutory = None
        lookup_hsn_code = None

try:
    from src.ingestion.schemas import (
        get_reverse_charge_rejection_reason,
        get_ist_today,
        classify_future_date_diagnostic,
        classify_rule_2172_diagnostic,
        classify_rule_2173_diagnostic,
        classify_rule_2174_diagnostic,
        classify_rule_2182_diagnostic,
        classify_rule_2183_diagnostic,
        classify_rule_2184_diagnostic,
        classify_rule_2185_diagnostic,
        classify_rule_2186_diagnostic,
        classify_rule_2192_diagnostic,
        classify_rule_2193_diagnostic,
        classify_rule_2194_diagnostic,
        classify_rule_2200_diagnostic,
        classify_rule_2201_diagnostic,
        classify_rule_2202_diagnostic,
        classify_rule_2203_diagnostic,
        classify_rule_2211_diagnostic,
        classify_rule_2212_diagnostic,
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
            classify_rule_2182_diagnostic,
            classify_rule_2183_diagnostic,
            classify_rule_2184_diagnostic,
            classify_rule_2185_diagnostic,
            classify_rule_2186_diagnostic,
            classify_rule_2192_diagnostic,
            classify_rule_2193_diagnostic,
            classify_rule_2194_diagnostic,
            classify_rule_2200_diagnostic,
            classify_rule_2201_diagnostic,
            classify_rule_2202_diagnostic,
            classify_rule_2203_diagnostic,
            classify_rule_2211_diagnostic,
            classify_rule_2212_diagnostic,
        )
    except ImportError:
        get_reverse_charge_rejection_reason = None
        get_ist_today = None
        classify_future_date_diagnostic = None
        classify_rule_2172_diagnostic = None
        classify_rule_2173_diagnostic = None
        classify_rule_2174_diagnostic = None
        classify_rule_2182_diagnostic = None
        classify_rule_2183_diagnostic = None
        classify_rule_2184_diagnostic = None
        classify_rule_2185_diagnostic = None
        classify_rule_2186_diagnostic = None
        classify_rule_2192_diagnostic = None
        classify_rule_2193_diagnostic = None
        classify_rule_2194_diagnostic = None
        classify_rule_2200_diagnostic = None
        classify_rule_2201_diagnostic = None
        classify_rule_2202_diagnostic = None
        classify_rule_2203_diagnostic = None
        classify_rule_2211_diagnostic = None
        classify_rule_2212_diagnostic = None

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


class GSTValidator:
    """
    Validates E-Invoice and E-Way Bill payloads against official NIC specifications.
    Covers every key field, key field length, and key field value validation.
    """

    @classmethod
    def validate_invoice(cls, invoice: Dict[str, Any]) -> List[Dict[str, Any]]:
        errors: List[ValidationError] = []

        # ---------------------------------------------------------
        # Section 0: Header & GSTIN Length Validations (self_gstin)
        # ---------------------------------------------------------
        self_gstin = str(invoice.get("self_gstin", "") or "").strip().upper()
        if not self_gstin:
            errors.append(ValidationError(2289, "self_gstin", "self_gstin cannot be blank or null"))
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
        is_export = trancatg == "EXP"
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
        sup_bno = str(sup.get("supplier_bno", "") or "").strip()
        sup_bnm = str(sup.get("supplier_bnm", "") or "").strip()
        sup_flno = str(sup.get("supplier_flno", "") or "").strip()
        sup_loc = str(sup.get("supplier_loc", sup.get("loc", sup.get("Loc", ""))) or "").strip()
        sup_dst = str(sup.get("supplier_dst", "") or "").strip()
        sup_pin = str(sup.get("supplier_pin", sup.get("pin", sup.get("Pin", ""))) or "").strip()
        sup_state = str(sup.get("supplier_state", sup.get("state", sup.get("StateCode", (sup_gstin[:2] if len(sup_gstin) >= 2 else "")))) or "").strip().zfill(2)
        sup_phone = str(sup.get("supplier_phone", sup.get("phone", "")) or "").strip()
        sup_email = str(sup.get("supplier_email", sup.get("email", "")) or "").strip().lower()
        cust_cd = str(sup.get("cust_cd", invoice.get("cust_cd", "")) or "").strip()

        # Supplier GSTIN checks
        if not sup_gstin:
            errors.append(ValidationError(2289, "supplierdt1.supplier_gstin", "supplier_gstin cannot be blank or null"))
        elif len(sup_gstin) != 15:
            errors.append(ValidationError(2289, "supplierdt1.supplier_gstin", f"Invalid supplier_gstin length ({len(sup_gstin)}). Must be exactly 15 characters."))
        elif not sup_gstin[:2].isdigit():
            errors.append(ValidationError(2289, "supplierdt1.supplier_gstin", "supplier_gstin state code (first 2 digits) must be numeric."))
        elif not re.match(GSTIN_REGEX, sup_gstin):
            errors.append(ValidationError(2289, "supplierdt1.supplier_gstin", f"Invalid supplier_gstin format '{sup_gstin}'. Must be 15-character alphanumeric GSTIN."))
        elif sup_gstin == "URP":
            errors.append(ValidationError(2213, "supplierdt1.supplier_gstin", "The supplier GSTIN cannot be URP."))
        elif sup_gstin[:2] != sup_state:
            errors.append(ValidationError(2258, "supplierdt1.supplier_state", f"Supplier state code '{sup_state}' does not match first 2 digits of GSTIN '{sup_gstin[:2]}'."))

        # Cross check self_gstin vs supplier_gstin
        if self_gstin and sup_gstin and self_gstin != sup_gstin:
            errors.append(ValidationError(2289, "self_gstin", f"self_gstin '{self_gstin}' does not match supplier_gstin '{sup_gstin}'."))

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
            errors.append(ValidationError(2276, "supplierdt1.supplier_pin", "Supplier PIN code cannot be 999999."))
        elif len(sup_pin) != 6 or not sup_pin.isdigit():
            errors.append(ValidationError(3038, "supplierdt1.supplier_pin", f"Supplier PIN must be exactly 6 digits. Got: {len(sup_pin)}"))
        elif not verify_pincode_state(sup_pin, sup_state):
            state_name = STATE_MASTER.get(sup_state, {}).get("name", sup_state)
            errors.append(ValidationError(3039, "supplierdt1.supplier_pin", f"Pincode '{sup_pin}' of supplier does not belong to State '{sup_state}' ({state_name})."))

        if not sup_state:
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
        buy_bno = str(buy.get("buyer_bno", "") or "").strip()
        buy_bnm = str(buy.get("buyer_bnm", "") or "").strip()
        buy_flno = str(buy.get("buyer_flno", "") or "").strip()
        buy_loc = str(buy.get("buyer_loc", buy.get("loc", buy.get("Loc", ""))) or "").strip()
        buy_dst = str(buy.get("buyer_dst", "") or "").strip()
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
                if buy_gstin != "URP":
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
        if not buy_pin:
            errors.append(ValidationError(2244, "buyerdt1.buyer_pin", "buyer_pin is mandatory"))
        elif len(buy_pin) != 6 or not buy_pin.isdigit():
            errors.append(ValidationError(3038, "buyerdt1.buyer_pin", f"buyer_pin must be exactly 6 digits. Got: {len(buy_pin)}"))
        elif is_export:
            if buy_pin != "999999":
                errors.append(ValidationError(2275, "buyerdt1.buyer_pin", "Recipient PIN code should be 999999 for Direct Export."))
        else:
            if buy_pin == "999999":
                errors.append(ValidationError(2274, "buyerdt1.buyer_pin", f"Recipient PIN code cannot be 999999 for {trancatg} transaction."))
            elif not verify_pincode_state(buy_pin, buy_state):
                state_name = STATE_MASTER.get(buy_state, {}).get("name", buy_state)
                errors.append(ValidationError(3041, "buyerdt1.buyer_pin", f"Buyer Pincode '{buy_pin}' does not belong to State '{buy_state}' ({state_name})."))

        if not buy_state:
            errors.append(ValidationError(2260, "buyerdt1.buyer_state", "buyer_state is mandatory"))
        elif len(buy_state) != 2:
            errors.append(ValidationError(2260, "buyerdt1.buyer_state", f"buyer_state must be 2 digits. Got: {len(buy_state)}"))
        elif is_export and buy_state != "96":
            errors.append(ValidationError(2261, "buyerdt1.buyer_state", "Recipient state code must be 96 for Export transactions."))
        elif not is_export and buy_gstin != "URP" and len(buy_gstin) == 15 and buy_gstin[:2] != buy_state:
            errors.append(ValidationError(2265, "buyerdt1.buyer_state", f"Recipient state code '{buy_state}' does not match GSTIN prefix '{buy_gstin[:2]}'."))

        if not pos:
            errors.append(ValidationError(2243, "buyerdt1.pos", "pos is mandatory and cannot be blank"))
        elif len(pos) != 2 or not pos.isdigit():
            errors.append(ValidationError(2243, "buyerdt1.pos", f"pos must be exactly 2 digits numeric. Got: '{pos}'"))
        elif is_export and pos != "96":
            errors.append(ValidationError(2232, "buyerdt1.pos", "POS must be 96 (Other Country) for Export transactions."))
        elif not is_export and pos == "96":
            errors.append(ValidationError(2242, "buyerdt1.pos", f"Recipient POS cannot be 96 for {trancatg} transaction."))

        if buy_phone and len(buy_phone) != 10:
            errors.append(ValidationError(2285, "buyerdt1.buyer_phone", f"buyer_phone must be exactly 10 digits. Got: {len(buy_phone)}"))

        if buy_email:
            if not (10 <= len(buy_email) <= 50):
                errors.append(ValidationError(2285, "buyerdt1.buyer_email", f"buyer_email length must be 10-50 characters. Current: {len(buy_email)}"))
            if "@" not in buy_email or "." not in buy_email:
                errors.append(ValidationError(2285, "buyerdt1.buyer_email", f"Invalid email format for buyer_email: '{buy_email}'"))

        if igstonintra == "Y" and sup_state != pos:
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
            elif classify_rule_2202_diagnostic:
                cnt_diag = classify_rule_2202_diagnostic(
                    cntcode=cntcode,
                    buyer_state=buy_state,
                    buyer_loc=buy_loc,
                    forcur=forcur,
                    port=port
                )
                if not cnt_diag["is_valid"]:
                    errors.append(ValidationError(2202, "expdt1.cntcode", cnt_diag["reason"]))
            elif len(cntcode) != 2:
                errors.append(ValidationError(2202, "expdt1.cntcode", f"Invalid cntcode length. Got: '{cntcode}' (Expected 2)"))
            elif cntcode not in COUNTRY_MASTER:
                errors.append(ValidationError(2202, "expdt1.cntcode", f"Invalid Country Code '{cntcode}'. Must be valid 2-letter ISO country code."))

            if not forcur:
                errors.append(ValidationError(2203, "expdt1.forcur", "forcur is mandatory when trancatg is 'EXP'"))
            elif classify_rule_2203_diagnostic:
                cur_diag = classify_rule_2203_diagnostic(
                    forcur=forcur,
                    cntcode=cntcode,
                    billed_in_inr=False
                )
                if not cur_diag["is_valid"]:
                    errors.append(ValidationError(2203, "expdt1.forcur", cur_diag["reason"]))
            elif cntcode in COUNTRY_CURRENCY_MAP:
                expected_curr = COUNTRY_CURRENCY_MAP.get(cntcode)
                if forcur != expected_curr:
                    errors.append(ValidationError(2203, "expdt1.forcur", f"Mismatch: Country '{cntcode}' uses '{expected_curr}', but found '{forcur}'"))

            if not expcat:
                errors.append(ValidationError(2285, "expdt1.expcat", "expcat is mandatory when trancatg is 'EXP'"))
            elif expcat not in ["DIR", "DEM", "SEZ", "SED"]:
                errors.append(ValidationError(2285, "expdt1.expcat", f"Invalid expcat '{expcat}'. Must be DIR, DEM, SEZ, or SED."))

            if not wthpay:
                errors.append(ValidationError(2285, "expdt1.wthpay", "wthpay is mandatory when trancatg is 'EXP'"))
            elif wthpay not in ["Y", "N"]:
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

            if (trancatg in ["B2B", "B2G", "SEZWP", "SEZWOP", "DEXP"]) and ship_pin == "999999":
                errors.append(ValidationError(2272, "shipdtl.ship_pin", f"SHIP TO PIN code cannot be 999999 for {trancatg} transactions."))
            elif ship_pin and ship_state and not verify_pincode_state(ship_pin, ship_state):
                errors.append(ValidationError(3041, "shipdtl.ship_pin", f"Ship PIN '{ship_pin}' does not belong to State '{ship_state}'."))

            if ship_state and ship_state not in VALID_STATE_CODES:
                errors.append(ValidationError(2271, "shipdtl.ship_state", f"Invalid SHIP TO state code '{ship_state}'."))

        # ---------------------------------------------------------
        # Section 7: Line Items (itemdtls) & Comprehensive Tax Checks
        # ---------------------------------------------------------
        items = invoice.get("itemdtls", [])
        if not items:
            errors.append(ValidationError(2228, "itemdtls", "Item list cannot be empty."))

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

        is_intra = (sup_state == pos and igstonintra != "Y" and not is_export and not is_sez)
        has_goods_item = False

        sum_assamt = Decimal("0.00")
        sum_cgst = Decimal("0.00")
        sum_sgst = Decimal("0.00")
        sum_igst = Decimal("0.00")
        sum_cess = Decimal("0.00")
        sum_stcess = Decimal("0.00")
        sum_cesnonad = Decimal("0.00")

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

            if isservc == "N":
                has_goods_item = True
                if not raw_qty or raw_qty in ["0", "0.0", "0.00", "0.000"]:
                    errors.append(ValidationError(2238, f"itemdtls[{sl}].qty", f"qty is mandatory for goods item {sl} (isservc = 'N')"))
                if not raw_uqc:
                    errors.append(ValidationError(2239, f"itemdtls[{sl}].uqc", f"uqc is mandatory for goods item {sl} (isservc = 'N')"))

            if raw_uqc:
                diag_2177 = classify_rule_2177_diagnostic(raw_uqc)
                if not diag_2177["is_valid"]:
                    errors.append(ValidationError(
                        2177,
                        f"itemdtls[{sl}].uqc",
                        f"Unit Quantity Code(s)-{raw_uqc} is/are not as per master. {diag_2177['reason']} Fix: {diag_2177['resolution']}"
                    ))

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
                stcessrt = Decimal(str(itm.get("statecessrt", itm.get("stcesrt", itm.get("StCesRt", "0"))) or "0"))
                stcessamt = Decimal(str(itm.get("statecessamt", itm.get("stcesval", itm.get("StCesAmt", "0"))) or "0"))
                cesnonad = Decimal(str(itm.get("cessnonadval", itm.get("cesnonadval", itm.get("CesNonAdVal", "0"))) or "0"))
                stcesnonad = Decimal(str(itm.get("statecesnonadvl", itm.get("statecesnonadval", itm.get("StateCesNonAdvlAmt", itm.get("StateCesNonAdVal", "0")))) or "0"))
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
                    if cgstamt != sgstamt:
                        errors.append(ValidationError(2227, f"itemdtls[{sl}]", f"For Sl No {sl}, SGST ({sgstamt}) and CGST ({cgstamt}) amounts must be equal."))
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
                sum_cesnonad += cesnonad

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
            if abs(stcesval - sum_stcess) > Decimal("2.00"):
                errors.append(ValidationError(2187, "valdt1.stcesval", f"State Cess value of items ({sum_stcess}) != total State Cess ({stcesval})"))

            expected_totinv = ttlassval + cgstval + sgstval + igstval + cesval + stcesval + cesnonadval + othchrg - discval
            if abs(totinvval - expected_totinv) > Decimal("2.00"):
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

        for idx, inv in enumerate(invoices, start=1):
            docno = inv.get("docdt1", {}).get("docno", inv.get("docno", f"INV_INDEX_{idx}"))
            errors = cls.validate_invoice(inv)
            is_valid = len(errors) == 0

            price_anom = None
            if PriceAnomalyDetector:
                try:
                    price_anom = PriceAnomalyDetector.scan_invoice_payload(inv)
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
