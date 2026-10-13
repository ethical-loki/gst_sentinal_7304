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
        MAJOR_INDIAN_PORTS
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
        MAJOR_INDIAN_PORTS
    )

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
            elif inv_date.date() > datetime.today().date():
                errors.append(ValidationError(2163, "docdt1.docdt", f"Document date '{docdt_str}' cannot be a future date."))

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
        elif trancatg not in ("B2B", "SEZWP", "SEZWOP") and reversecharge == "Y":
            errors.append(ValidationError(2162, "trandt1.reversecharge", f"Reverse Charge is not applicable for transaction category '{trancatg}'."))

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
        sup = invoice.get("supplierdt1", {}) if isinstance(invoice.get("supplierdt1"), dict) else invoice
        sup_gstin = str(sup.get("supplier_gstin", "") or "").strip().upper()
        sup_lglnm = str(sup.get("supplier_lglnm", "") or "").strip()
        sup_trdnm = str(sup.get("supplier_trdnm", "") or "").strip()
        sup_bno = str(sup.get("supplier_bno", "") or "").strip()
        sup_bnm = str(sup.get("supplier_bnm", "") or "").strip()
        sup_flno = str(sup.get("supplier_flno", "") or "").strip()
        sup_loc = str(sup.get("supplier_loc", "") or "").strip()
        sup_dst = str(sup.get("supplier_dst", "") or "").strip()
        sup_pin = str(sup.get("supplier_pin", "") or "").strip()
        sup_state = str(sup.get("supplier_state", "") or "").strip().zfill(2)
        sup_phone = str(sup.get("supplier_phone", "") or "").strip()
        sup_email = str(sup.get("supplier_email", "") or "").strip().lower()
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
        buy = invoice.get("buyerdt1", {}) if isinstance(invoice.get("buyerdt1"), dict) else invoice
        buy_gstin = str(buy.get("buyer_gstin", "") or "").strip().upper()
        buy_lglnm = str(buy.get("buyer_lglnm", "") or "").strip()
        buy_trdnm = str(buy.get("buyer_trdnm", "") or "").strip()
        buy_bno = str(buy.get("buyer_bno", "") or "").strip()
        buy_bnm = str(buy.get("buyer_bnm", "") or "").strip()
        buy_flno = str(buy.get("buyer_flno", "") or "").strip()
        buy_loc = str(buy.get("buyer_loc", "") or "").strip()
        buy_dst = str(buy.get("buyer_dst", "") or "").strip()
        buy_pin = str(buy.get("buyer_pin", "") or "").strip()
        buy_state = str(buy.get("buyer_state", "") or "").strip().zfill(2)
        pos = str(buy.get("pos", invoice.get("pos", "")) or "").strip().zfill(2)
        buy_phone = str(buy.get("buyer_phone", "") or "").strip()
        buy_email = str(buy.get("buyer_email", "") or "").strip().lower()

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
                    errors.append(ValidationError(2212, "buyerdt1.buyer_gstin", f"buyer_gstin cannot be 'URP' for transaction category '{trancatg}'."))

        # Self-invoicing check
        if sup_gstin and buy_gstin and sup_gstin == buy_gstin:
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

            if port:
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
            # Forbidden export fields for non-export transactions
            exp_check = invoice.get("expdt1") or {}
            for f_name in ["expcat", "wthpay", "forcur", "cntcode"]:
                if exp_check.get(f_name):
                    errors.append(ValidationError(2285, f"expdt1.{f_name}", f"{f_name} must be empty when trancatg is '{trancatg}'"))

        # ---------------------------------------------------------
        # Section 6: Dispatch Details (dispdt1) & Shipping Details (shipdtl)
        # ---------------------------------------------------------
        disp = invoice.get("dispdt1")
        if disp and isinstance(disp, dict):
            disp_gstin = str(disp.get("disp_gstin", "") or "").strip().upper()
            disp_trdnm = str(disp.get("disp_trdnm", "") or "").strip()
            disp_bno = str(disp.get("disp_bno", "") or "").strip()
            disp_bnm = str(disp.get("disp_bnm", "") or "").strip()
            disp_flno = str(disp.get("disp_flno", "") or "").strip()
            disp_loc = str(disp.get("disp_loc", "") or "").strip()
            disp_dst = str(disp.get("disp_dst", "") or "").strip()
            disp_pin = str(disp.get("disp_pin", "") or "").strip()
            disp_state = str(disp.get("disp_state", "") or "").strip().zfill(2)
            disp_phone = str(disp.get("disp_phone", "") or "").strip()
            disp_email = str(disp.get("disp_email", "") or "").strip().lower()

            if disp_gstin and disp_gstin != "URP":
                if not (3 <= len(disp_gstin) <= 15):
                    errors.append(ValidationError(2200, "dispdt1.disp_gstin", f"disp_gstin length must be 3-15 chars. Got: {len(disp_gstin)}"))
                elif len(disp_gstin) != 15:
                    errors.append(ValidationError(2200, "dispdt1.disp_gstin", f"Invalid disp_gstin length ({len(disp_gstin)}). Must be 15 characters."))
                elif not disp_gstin[:2].isdigit():
                    errors.append(ValidationError(2200, "dispdt1.disp_gstin", "disp_gstin state code (first 2 digits) must be numeric"))
                elif not re.match(GSTIN_REGEX, disp_gstin):
                    errors.append(ValidationError(2200, "dispdt1.disp_gstin", f"Invalid disp_gstin format '{disp_gstin}'. Must be 15-digit GSTIN or 'URP'"))

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

        ship = invoice.get("shipdtl") or invoice.get("shipdt1")
        if ship and isinstance(ship, dict):
            ship_gstin = str(ship.get("ship_gstin", "") or "").strip().upper()
            ship_lglnm = str(ship.get("ship_lglnm", "") or "").strip()
            ship_trdnm = str(ship.get("ship_trdnm", "") or "").strip()
            ship_bno = str(ship.get("ship_bno", "") or "").strip()
            ship_bnm = str(ship.get("ship_bnm", "") or "").strip()
            ship_flno = str(ship.get("ship_flno", "") or "").strip()
            ship_loc = str(ship.get("ship_loc", "") or "").strip()
            ship_dst = str(ship.get("ship_dst", "") or "").strip()
            ship_pin = str(ship.get("ship_pin", "") or "").strip()
            ship_state = str(ship.get("ship_state", "") or "").strip().zfill(2)
            ship_phone = str(ship.get("ship_phone", "") or "").strip()
            ship_email = str(ship.get("ship_email", "") or "").strip().lower()

            if ship_gstin and ship_gstin != "URP":
                if not (3 <= len(ship_gstin) <= 15):
                    errors.append(ValidationError(2200, "shipdtl.ship_gstin", f"ship_gstin length must be 3-15 chars. Got: {len(ship_gstin)}"))
                elif len(ship_gstin) != 15:
                    errors.append(ValidationError(2200, "shipdtl.ship_gstin", f"Invalid ship_gstin length ({len(ship_gstin)}). Must be 15 characters."))
                elif not re.match(GSTIN_REGEX, ship_gstin):
                    errors.append(ValidationError(2200, "shipdtl.ship_gstin", f"Invalid ship_gstin format '{ship_gstin}'. Must be 15-digit GSTIN or 'URP'"))

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
            hsn = str(itm.get("hsncd", "") or "").strip()
            barcde = str(itm.get("barcde", "") or "").strip()
            raw_qty = str(itm.get("qty", "") or "").strip()
            raw_uqc = str(itm.get("uqc", "") or "").strip().upper()

            if not prdnm:
                errors.append(ValidationError(2285, f"itemdtls[{sl}].prdnm", f"prdnm (Product Name) is mandatory for item {sl}"))
            elif not (3 <= len(prdnm) <= 300):
                errors.append(ValidationError(2285, f"itemdtls[{sl}].prdnm", f"prdnm length must be 3-300 characters for item {sl}. Current: {len(prdnm)}"))

            if prddesc and not (3 <= len(prddesc) <= 300):
                errors.append(ValidationError(2285, f"itemdtls[{sl}].prddesc", f"prddesc length must be 3-300 characters for item {sl}. Current: {len(prddesc)}"))

            if isservc not in ["Y", "N"]:
                errors.append(ValidationError(2285, f"itemdtls[{sl}].isservc", f"Invalid isservc '{isservc}' for item {sl}. Must be 'Y' (Service) or 'N' (Goods)"))

            if not hsn:
                errors.append(ValidationError(2176, f"itemdtls[{sl}].hsncd", f"hsncd is mandatory for item {sl}"))
            elif not (2 <= len(hsn) <= 8) or not hsn.isdigit():
                errors.append(ValidationError(2176, f"itemdtls[{sl}].hsncd", f"HSN code '{hsn}' for item {sl} must be 2-8 digits."))

            if barcde and not (1 <= len(barcde) <= 30):
                errors.append(ValidationError(2285, f"itemdtls[{sl}].barcde", f"barcde length must be 1-30 characters for item {sl}."))

            if isservc == "N":
                has_goods_item = True
                if not raw_qty or raw_qty in ["0", "0.0", "0.00", "0.000"]:
                    errors.append(ValidationError(2238, f"itemdtls[{sl}].qty", f"qty is mandatory for goods item {sl} (isservc = 'N')"))
                if not raw_uqc:
                    errors.append(ValidationError(2239, f"itemdtls[{sl}].uqc", f"uqc is mandatory for goods item {sl} (isservc = 'N')"))

            if raw_uqc:
                if len(raw_uqc) > 3:
                    errors.append(ValidationError(2177, f"itemdtls[{sl}].uqc", f"uqc exceeds max length of 3 characters for item {sl}. Got: '{raw_uqc}'"))
                elif raw_uqc not in ALLOWED_UQC:
                    errors.append(ValidationError(2177, f"itemdtls[{sl}].uqc", f"Unit Quantity Code '{raw_uqc}' for item {sl} is not as per master."))

            # Numerical precision and calculation checks
            try:
                qty = Decimal(raw_qty or "0")
                unitrate = Decimal(str(itm.get("unitrate", "0") or "0"))
                gross = Decimal(str(itm.get("grossamt", "0") or "0"))
                discount = Decimal(str(itm.get("discount", "0") or "0"))
                othchrg = Decimal(str(itm.get("othchrg", "0") or "0"))
                assamt = Decimal(str(itm.get("assamt", "0") or "0"))
                cgstrt = Decimal(str(itm.get("cgstrt", "0") or "0"))
                cgstamt = Decimal(str(itm.get("cgstamt", "0") or "0"))
                sgstrt = Decimal(str(itm.get("sgstrt", "0") or "0"))
                sgstamt = Decimal(str(itm.get("sgstamt", "0") or "0"))
                igstrt = Decimal(str(itm.get("igstrt", "0") or "0"))
                igstamt = Decimal(str(itm.get("igstamt", "0") or "0"))
                cessrt = Decimal(str(itm.get("cessrt", "0") or "0"))
                cessamt = Decimal(str(itm.get("cessamt", "0") or "0"))
                stcessrt = Decimal(str(itm.get("statecessrt", "0") or "0"))
                stcessamt = Decimal(str(itm.get("statecessamt", "0") or "0"))
                cesnonad = Decimal(str(itm.get("cessnonadval", "0") or "0"))
                totitemval = Decimal(str(itm.get("totitemval", "0") or "0"))

                # Gross Amount validation: Qty * UnitPrice
                expected_gross = (qty * unitrate).quantize(Decimal("0.01"))
                if abs(gross - expected_gross) > Decimal("0.05"):
                    errors.append(ValidationError(2192, f"itemdtls[{sl}].grossamt", f"TotAmt ({gross}) should equal Qty*UnitPrice ({expected_gross}) for item {sl}"))

                # Assessable Amount validation: Gross - Discount
                expected_assamt = (gross - discount).quantize(Decimal("0.01"))
                if abs(assamt - expected_assamt) > Decimal("0.05"):
                    errors.append(ValidationError(2193, f"itemdtls[{sl}].assamt", f"For Sl No {sl}, AssAmt ({assamt}) != Gross - Discount ({expected_assamt})"))

                # Inter vs Intra Tax validation
                if is_intra:
                    if igstamt > 0:
                        errors.append(ValidationError(2172, f"itemdtls[{sl}].igstamt", f"For Intra-state, IGST is not applicable. Item {sl} has IGST {igstamt}"))
                    if cgstamt != sgstamt:
                        errors.append(ValidationError(2227, f"itemdtls[{sl}]", f"For Sl No {sl}, SGST ({sgstamt}) and CGST ({cgstamt}) amounts must be equal."))
                else:
                    if cgstamt > 0 or sgstamt > 0:
                        errors.append(ValidationError(2174, f"itemdtls[{sl}]", f"For inter-state/SEZ, CGST/SGST not applicable; only IGST applies. Item {sl} has CGST/SGST."))

                # Total Item Value validation
                expected_totitem = assamt + cgstamt + sgstamt + igstamt + cessamt + stcessamt + cesnonad
                if abs(totitemval - expected_totitem) > Decimal("1.00"):
                    errors.append(ValidationError(2194, f"itemdtls[{sl}].totitemval", f"For Sl No {sl}, Total item value ({totitemval}) != sum of taxable and taxes ({expected_totitem})"))

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
        valdt1 = invoice.get("valdt1", {}) if isinstance(invoice.get("valdt1"), dict) else invoice
        try:
            ttlassval = Decimal(str(valdt1.get("ttlassval", "0") or "0"))
            cgstval = Decimal(str(valdt1.get("cgstval", "0") or "0"))
            sgstval = Decimal(str(valdt1.get("sgstval", "0") or "0"))
            igstval = Decimal(str(valdt1.get("igstval", "0") or "0"))
            cesval = Decimal(str(valdt1.get("cesval", "0") or "0"))
            stcesval = Decimal(str(valdt1.get("stcesval", "0") or "0"))
            cesnonadval = Decimal(str(valdt1.get("cesnonadval", "0") or "0"))
            totinvval = Decimal(str(valdt1.get("totinvval", "0") or "0"))
            othchrg = Decimal(str(valdt1.get("othchrg", "0") or "0"))
            discval = Decimal(str(valdt1.get("discval", "0") or "0"))

            # Reconciliation of header totals with line item sums within +/- Rs 2 tolerance
            if abs(ttlassval - sum_assamt) > Decimal("2.00"):
                errors.append(ValidationError(2182, "valdt1.ttlassval", f"Taxable value of items ({sum_assamt}) != total taxable value ({ttlassval})"))
            if abs(cgstval - sum_cgst) > Decimal("2.00"):
                errors.append(ValidationError(2184, "valdt1.cgstval", f"CGST value of items ({sum_cgst}) != total CGST ({cgstval})"))
            if abs(sgstval - sum_sgst) > Decimal("2.00"):
                errors.append(ValidationError(2183, "valdt1.sgstval", f"SGST value of items ({sum_sgst}) != total SGST ({sgstval})"))
            if abs(igstval - sum_igst) > Decimal("2.00"):
                errors.append(ValidationError(2185, "valdt1.igstval", f"IGST value of items ({sum_igst}) != total IGST ({igstval})"))
            if abs(cesval - sum_cess) > Decimal("2.00"):
                errors.append(ValidationError(2186, "valdt1.cesval", f"Cess value of items ({sum_cess}) != total Cess ({cesval})"))
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

        for idx, inv in enumerate(invoices, start=1):
            docno = inv.get("docdt1", {}).get("docno", inv.get("docno", f"INV_INDEX_{idx}"))
            errors = cls.validate_invoice(inv)
            is_valid = len(errors) == 0

            if is_valid:
                report["valid_invoices"] += 1
            else:
                report["failed_invoices"] += 1

            report["results"].append({
                "invoice_number": docno,
                "status": "VALID" if is_valid else "INVALID",
                "error_count": len(errors),
                "errors": errors
            })

        return report
