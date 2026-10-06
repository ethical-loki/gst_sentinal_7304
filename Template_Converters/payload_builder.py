"""
Payload Builder and Auto-Correction Engine for Indian GST E-Invoice & E-Way Bill.
Cleanses dirty keys (OCR/manual typos), normalizes formats, enforces tax math,
generates compliant NIC JSON payloads, and maintains a complete, detailed Audit Log
of every correction applied.
"""

import re
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List, Optional, Tuple
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
    )

KEY_ALIASES = {
    # Header
    "system.cd": "system_cd", "system cd": "system_cd",
    "vertical cd": "vertical_cd", "vertical.cd": "vertical_cd",
    "branch cd": "branch_cd", "branch.cd": "branch_cd",
    "self gstin": "self_gstin",
    
    # trandt1
    "trancatg": "trancatg", "tran_catg": "trancatg",
    "reversecharge": "reversecharge", "reverse_charge": "reversecharge",
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
    "ugc": "uqc", "uom": "uqc",
    "unit_rate": "unitrate", "unitprice": "unitrate",
    "gross_amt": "grossamt", "gross_amount": "grossamt",
    "ass_amt": "assamt", "taxable_amt": "assamt",
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
    if val is None:
        return ""
    return re.sub(r"[^\d]", "", str(val).strip())

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
    s = clean_int_str(raw_state)
    if len(s) == 1:
        padded = s.zfill(2)
        if audit_log is not None and field:
            audit_log.append({
                "category": "STATE_CODE_PADDING",
                "field": field,
                "original": raw_state,
                "corrected": padded,
                "description": f"Padded single digit state code '{raw_state}' to 2-digit format '{padded}'"
            })
        return padded
    return s

def clean_gstin(raw_gstin: Any) -> str:
    if not raw_gstin:
        return ""
    s = str(raw_gstin).strip().upper()
    if s == "URP":
        return "URP"
    return re.sub(r"[^0-9A-Z]", "", s)


class PayloadBuilder:
    """
    Builds and auto-corrects Indian GST E-Invoice & E-Way Bill payloads,
    tracking an exhaustive audit trail of all corrections.
    """

    @classmethod
    def auto_correct_and_build(cls, raw_invoice: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Takes raw/dirty invoice data, applies key aliasing, value normalization,
        and tax calculations, returning (corrected_invoice, audit_log).
        """
        audit_log: List[Dict[str, Any]] = []

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
        reversecharge = clean_str(trandt1.get("reversecharge", "N")).upper() or "N"
        transactionmode = clean_str(trandt1.get("transactionmode", "REG")).upper() or "REG"
        igstonintra = clean_str(trandt1.get("igstonintra", "N")).upper() or "N"

        # Reverse Charge Rule Check
        if trancatg not in ("B2B", "SEZWP", "SEZWOP") and reversecharge == "Y":
            audit_log.append({
                "category": "BUSINESS_RULE_AUTO_CORRECTION",
                "field": "trandt1.reversecharge",
                "original": "Y",
                "corrected": "N",
                "description": f"Reverse charge is not applicable for '{trancatg}' transactions (Rule 2162); auto-set to 'N'"
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

        clean_docdt1 = {
            "document_type": clean_str(docdt1.get("document_type", "INV")).upper() or "INV",
            "docno": clean_docno,
            "docdt": normalize_date_to_standard(docdt1.get("docdt", ""), audit_log=audit_log, field="docdt1.docdt")
        }

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
            "supplier_lglnm": clean_str(supplierdt1.get("supplier_lglnm", "")),
            "supplier_trdnm": clean_str(supplierdt1.get("supplier_trdnm", supplierdt1.get("supplier_lglnm", ""))),
            "supplier_bno": clean_str(supplierdt1.get("supplier_bno", "")),
            "supplier_bnm": clean_str(supplierdt1.get("supplier_bnm", "")),
            "supplier_flno": clean_str(supplierdt1.get("supplier_flno", "NAA")),
            "supplier_loc": clean_str(supplierdt1.get("supplier_loc", "")),
            "supplier_dst": clean_str(supplierdt1.get("supplier_dst", "")),
            "supplier_pin": clean_int_str(supplierdt1.get("supplier_pin", "")),
            "supplier_state": sup_state,
            "supplier_phone": clean_int_str(supplierdt1.get("supplier_phone", "")),
            "supplier_email": clean_str(supplierdt1.get("supplier_email", "")).lower()
        }

        # Buyer Details (buyerdt1)
        raw_buy_gstin = clean_gstin(buyerdt1.get("buyer_gstin", data.get("buyer_gstin", "")))
        buy_gstin = raw_buy_gstin
        if raw_buy_gstin and raw_buy_gstin != "URP" and len(raw_buy_gstin) != 15:
            audit_log.append({
                "category": "INVALID_GSTIN_LENGTH",
                "field": "buyerdt1.buyer_gstin",
                "original": raw_buy_gstin,
                "corrected": raw_buy_gstin,
                "description": f"Customer input buyer_gstin '{raw_buy_gstin}' has invalid length ({len(raw_buy_gstin)} chars, expected 15 or 'URP')."
            })
        raw_pos = clean_str(buyerdt1.get("pos", data.get("pos", "")))
        pos = clean_state_code(raw_pos, audit_log=audit_log, field="buyerdt1.pos")
        raw_buy_state = clean_str(buyerdt1.get("buyer_state", data.get("buyer_state", "")))
        buy_state = clean_state_code(raw_buy_state, audit_log=audit_log, field="buyerdt1.buyer_state")
        buy_pin = clean_int_str(buyerdt1.get("buyer_pin", data.get("buyer_pin", "")))

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
            "buyer_gstin": buy_gstin,
            "buyer_trdnm": clean_str(buyerdt1.get("buyer_trdnm", "")),
            "buyer_lglnm": clean_str(buyerdt1.get("buyer_lglnm", "")),
            "buyer_bno": clean_str(buyerdt1.get("buyer_bno", "NAA")),
            "buyer_bnm": clean_str(buyerdt1.get("buyer_bnm", "")),
            "buyer_flno": clean_str(buyerdt1.get("buyer_flno", "NAA")),
            "buyer_loc": clean_str(buyerdt1.get("buyer_loc", "")),
            "buyer_dst": clean_str(buyerdt1.get("buyer_dst", "")),
            "buyer_pin": buy_pin,
            "buyer_state": buy_state,
            "pos": pos,
            "buyer_phone": clean_int_str(buyerdt1.get("buyer_phone", "")),
            "buyer_email": clean_str(buyerdt1.get("buyer_email", "")).lower()
        }

        # Dispatch Details (dispdt1)
        clean_dispdt1 = None
        if dispdt1:
            raw_disp_gstin = clean_gstin(dispdt1.get("disp_gstin", ""))
            if raw_disp_gstin and raw_disp_gstin != "URP" and len(raw_disp_gstin) != 15:
                audit_log.append({
                    "category": "INVALID_GSTIN_LENGTH",
                    "field": "dispdt1.disp_gstin",
                    "original": raw_disp_gstin,
                    "corrected": raw_disp_gstin,
                    "description": f"Customer input disp_gstin '{raw_disp_gstin}' has invalid length ({len(raw_disp_gstin)} chars, expected 15 or 'URP')."
                })
            clean_dispdt1 = {
                "disp_gstin": raw_disp_gstin,
                "disp_trdnm": clean_str(dispdt1.get("disp_trdnm", "")),
                "disp_bno": clean_str(dispdt1.get("disp_bno", "NAA")),
                "disp_bnm": clean_str(dispdt1.get("disp_bnm", "NAA")),
                "disp_flno": clean_str(dispdt1.get("disp_flno", "NAA")),
                "disp_loc": clean_str(dispdt1.get("disp_loc", "")),
                "disp_dst": clean_str(dispdt1.get("disp_dst", "")),
                "disp_pin": clean_int_str(dispdt1.get("disp_pin", "")),
                "disp_state": clean_state_code(dispdt1.get("disp_state", ""), audit_log=audit_log, field="dispdt1.disp_state"),
                "disp_phone": clean_int_str(dispdt1.get("disp_phone", "")),
                "disp_email": clean_str(dispdt1.get("disp_email", "")).lower()
            }

        # Shipping Details (shipdtl)
        clean_shipdtl = None
        if shipdtl:
            raw_ship_gstin = clean_gstin(shipdtl.get("ship_gstin", ""))
            if raw_ship_gstin and raw_ship_gstin != "URP" and len(raw_ship_gstin) != 15:
                audit_log.append({
                    "category": "INVALID_GSTIN_LENGTH",
                    "field": "shipdtl.ship_gstin",
                    "original": raw_ship_gstin,
                    "corrected": raw_ship_gstin,
                    "description": f"Customer input ship_gstin '{raw_ship_gstin}' has invalid length ({len(raw_ship_gstin)} chars, expected 15 or 'URP')."
                })
            clean_shipdtl = {
                "ship_gstin": raw_ship_gstin,
                "ship_lglnm": clean_str(shipdtl.get("ship_lglnm", "")),
                "ship_trdnm": clean_str(shipdtl.get("ship_trdnm", "")),
                "ship_bno": clean_str(shipdtl.get("ship_bno", "NAA")),
                "ship_bnm": clean_str(shipdtl.get("ship_bnm", "NAA")),
                "ship_flno": clean_str(shipdtl.get("ship_flno", "NAA")),
                "ship_loc": clean_str(shipdtl.get("ship_loc", "")),
                "ship_dst": clean_str(shipdtl.get("ship_dst", "")),
                "ship_pin": clean_int_str(shipdtl.get("ship_pin", "")),
                "ship_state": clean_state_code(shipdtl.get("ship_state", ""), audit_log=audit_log, field="shipdtl.ship_state"),
                "ship_phone": clean_int_str(shipdtl.get("ship_phone", "")),
                "ship_email": clean_str(shipdtl.get("ship_email", "")).lower()
            }

        # Inter-State vs Intra-State determination
        # SEZ & Export are ALWAYS inter-state supplies (IGST only)
        is_intra = (sup_state == pos and igstonintra != "Y" and not is_export and not is_sez)

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
            prdnm = clean_str(item.get("prdnm", f"ITEM_{idx}"))
            prddesc = clean_str(item.get("prddesc", prdnm))
            isservc = clean_str(item.get("isservc", "N")).upper() or "N"
            hsncd = clean_int_str(item.get("hsncd", ""))
            raw_uqc = clean_str(item.get("uqc", "NOS")).upper() or "NOS"
            uqc = raw_uqc if raw_uqc in ALLOWED_UQC else "OTH"

            qty_d = Decimal(clean_decimal_str(item.get("qty", "1.000"), 3, audit_log=audit_log, field=f"itemdtls[{idx}].qty"))
            unitrate_d = Decimal(clean_decimal_str(item.get("unitrate", "0.00"), 2, audit_log=audit_log, field=f"itemdtls[{idx}].unitrate"))

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

            taxability = clean_str(item.get("taxability", "TAX")).upper() or "TAX"

            raw_igstrt = Decimal(clean_decimal_str(item.get("igstrt", "0.00"), 2))
            raw_cgstrt = Decimal(clean_decimal_str(item.get("cgstrt", "0.00"), 2))
            raw_sgstrt = Decimal(clean_decimal_str(item.get("sgstrt", "0.00"), 2))

            if raw_igstrt > 0:
                gst_rate = raw_igstrt
            elif raw_cgstrt + raw_sgstrt > 0:
                gst_rate = raw_cgstrt + raw_sgstrt
            else:
                gst_rate = Decimal("0.00")

            cessrt_d = Decimal(clean_decimal_str(item.get("cessrt", "0.00"), 2))
            cessamt_d = Decimal(clean_decimal_str(item.get("cessamt", "0.00"), 2))
            cessnonadval_d = Decimal(clean_decimal_str(item.get("cessnonadval", "0.00"), 2))
            statecessrt_d = Decimal(clean_decimal_str(item.get("statecessrt", "0.00"), 2))
            statecessamt_d = Decimal(clean_decimal_str(item.get("statecessamt", "0.00"), 2))

            # Tax Allocation
            if is_intra:
                cgstrt_d = (gst_rate / Decimal("2")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                sgstrt_d = cgstrt_d
                igstrt_d = Decimal("0.00")
                cgstamt_d = (assamt_d * cgstrt_d / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                sgstamt_d = cgstamt_d
                igstamt_d = Decimal("0.00")
            else:
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
                "totitemval": str(calculated_totitemval)
            })

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

        clean_valdt1 = {
            "ttlassval": str(total_assamt),
            "cgstval": str(total_cgst),
            "sgstval": str(total_sgst),
            "igstval": str(total_igst),
            "cesval": str(total_cess),
            "stcesval": str(total_stcess),
            "cesnonadval": str(total_cesnonad),
            "discval": str(inv_disc) if inv_disc > 0 else "",
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
            "mode_of_transport": clean_str(ewbdt1.get("mode_of_transport", "")),
            "transport_doc_no": clean_str(ewbdt1.get("transport_doc_no", "")).upper(),
            "transporter_doc_date": normalize_date_to_standard(ewbdt1.get("transporter_doc_date", ""), audit_log=audit_log, field="ewbdt1.transporter_doc_date"),
            "veh_type": clean_str(ewbdt1.get("veh_type", "")).upper(),
            "veh_number": clean_str(ewbdt1.get("veh_number", "")).upper().replace(" ", "").replace("-", "")
        }

        # Assemble Standard Output Structure
        out_invoice: Dict[str, Any] = OrderedDict()
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
        if clean_expdt1:
            out_invoice["expdt1"] = clean_expdt1
        out_invoice["docdt1"] = clean_docdt1
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
    def convert_payload_document_with_audit(cls, input_data: Any) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Converts full payload document and returns (corrected_payload, audit_reports).
        """
        if isinstance(input_data, dict):
            raw_invoices = input_data.get("einvoices", [input_data]) if "einvoices" in input_data else [input_data]
        elif isinstance(input_data, list):
            raw_invoices = input_data
        else:
            raise ValueError("Invalid payload root. Expected dict or list.")

        corrected_invoices = []
        audit_reports = []

        for idx, inv in enumerate(raw_invoices, start=1):
            clean_inv, audit_log = cls.auto_correct_and_build(inv)
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
