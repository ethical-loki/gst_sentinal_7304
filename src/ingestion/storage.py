import csv
import os
from typing import List, Dict, Any, Optional, Union
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from src.ingestion.schemas import (
    InvoicePayload,
    InvoiceBatchPayload,
    normalize_reverse_charge,
    classify_rule_2172_diagnostic,
    classify_rule_2174_diagnostic,
    classify_rule_2177_diagnostic,
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
    normalize_uqc_statutory,
)

DEFAULT_STORAGE_DIR = "data/processed_payload"
DEFAULT_STORAGE_PATH = os.path.join(DEFAULT_STORAGE_DIR, "invoices_master.parquet")
DEFAULT_EXCEL_PATH = os.path.join(DEFAULT_STORAGE_DIR, "invoices_export.xlsx")

FLATTENED_INVOICE_SCHEMA = pa.schema([
    # Document & Transaction Details
    ("invoice_id", pa.string()),
    ("doc_type", pa.string()),
    ("doc_date", pa.string()),
    ("transaction_category", pa.string()),
    ("reverse_charge", pa.string()),
    ("igst_on_intra", pa.string()),

    # Supplier Details
    ("supplier_gstin", pa.string()),
    ("supplier_lglnm", pa.string()),
    ("supplier_trdnm", pa.string()),
    ("supplier_state", pa.string()),
    ("supplier_pin", pa.string()),
    ("supplier_loc", pa.string()),
    ("supplier_phone", pa.string()),
    ("supplier_email", pa.string()),

    # Buyer Details
    ("buyer_gstin", pa.string()),
    ("buyer_lglnm", pa.string()),
    ("buyer_trdnm", pa.string()),
    ("buyer_state", pa.string()),
    ("buyer_pin", pa.string()),
    ("buyer_pos", pa.string()),
    ("buyer_loc", pa.string()),
    ("buyer_phone", pa.string()),
    ("buyer_email", pa.string()),

    # Dispatch & Shipping Details
    ("dispatch_name", pa.string()),
    ("dispatch_state", pa.string()),
    ("dispatch_pin", pa.string()),
    ("ship_gstin", pa.string()),
    ("ship_name", pa.string()),
    ("ship_state", pa.string()),
    ("ship_pin", pa.string()),

    # Export Details
    ("export_shipping_bill_no", pa.string()),
    ("export_shipping_bill_date", pa.string()),
    ("export_country", pa.string()),
    ("export_port", pa.string()),

    # Line Item Details
    ("line_item_id", pa.string()),
    ("item_slno", pa.string()),
    ("product_name", pa.string()),
    ("product_description", pa.string()),
    ("is_service", pa.string()),
    ("hsn", pa.string()),
    ("quantity", pa.float64()),
    ("unit", pa.string()),
    ("unit_price", pa.float64()),
    ("gross_amount", pa.float64()),
    ("item_discount", pa.float64()),
    ("pretax_value", pa.float64()),
    ("taxable_value", pa.float64()),
    ("gst_rate", pa.float64()),
    ("cgst_amount", pa.float64()),
    ("sgst_amount", pa.float64()),
    ("igst_amount", pa.float64()),
    ("cess_rate", pa.float64()),
    ("cess_amount", pa.float64()),
    ("state_cess_rate", pa.float64()),
    ("state_cess_amount", pa.float64()),
    ("other_charges", pa.float64()),
    ("total_item_value", pa.float64()),

    # Invoice-Level Valuation Breakdown
    ("inv_taxable_value", pa.float64()),
    ("inv_cgst_amount", pa.float64()),
    ("inv_sgst_amount", pa.float64()),
    ("inv_igst_amount", pa.float64()),
    ("inv_cess_amount", pa.float64()),
    ("inv_discount", pa.float64()),
    ("inv_roundoff", pa.float64()),
    ("inv_total_value", pa.float64()),

    # Transportation & E-Way Bill Details
    ("ewb_required", pa.string()),
    ("transporter_id", pa.string()),
    ("transporter_name", pa.string()),
    ("transport_mode", pa.string()),
    ("transport_doc_no", pa.string()),
    ("transport_doc_date", pa.string()),
    ("transit_distance_km", pa.float64()),
    ("vehicle_number", pa.string()),
    ("vehicle_type", pa.string()),

    # Payment & Settlement
    ("payment_mode", pa.string()),
    ("payment_account_no", pa.string()),
    ("payment_ifsc", pa.string()),
    ("payment_upi", pa.string()),

    # Governance & Status
    ("compliance_status", pa.string()),

    # Module 2: HSN Intelligence & Sentinel ML Telemetry
    ("sentinel_risk_prob", pa.float64()),
    ("sentinel_risk_level", pa.string()),
    ("sentinel_status_badge", pa.string()),
    ("sentinel_recommended_hsn", pa.string()),
    ("sentinel_audit_reasons", pa.string())
])


def flatten_invoice_payload(payload: Union[InvoicePayload, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Flattens a validated InvoicePayload model or standardized dictionary into tabular,
    line-item-grain dictionaries conforming to the comprehensive FLATTENED_INVOICE_SCHEMA.
    """
    def _to_f(v):
        if v is None:
            return 0.0
        try:
            return float(str(v).replace(",", "").strip())
        except Exception:
            return 0.0

    rows = []
    if isinstance(payload, dict):
        docno = str(payload.get("docdt1", {}).get("docno") or payload.get("docno") or "INV-UNKNOWN").strip()
        doc_type = str(payload.get("docdt1", {}).get("document_type") or payload.get("document_type") or "INV").strip()
        doc_dt = str(payload.get("docdt1", {}).get("docdt") or payload.get("docdt") or "").strip()

        trandt = payload.get("trandt1") or payload.get("transaction") or payload.get("trandtls") or payload.get("TranDtls") or {}
        trancatg = str(trandt.get("trancatg") or payload.get("trancatg") or "B2B").strip()
        raw_rc = trandt.get("reversecharge") if "reversecharge" in trandt else (trandt.get("RevChrg") if "RevChrg" in trandt else (payload.get("reversecharge") if "reversecharge" in payload else payload.get("RevChrg", "N")))
        reversecharge, _ = normalize_reverse_charge(raw_rc)
        igstonintra = str(trandt.get("igstonintra") or trandt.get("IgstOnIntra") or payload.get("igstonintra") or payload.get("IgstOnIntra") or "N").strip().upper()
        is_exceptional_intra = bool(
            payload.get("is_exceptional_intra")
            or trandt.get("is_exceptional_intra")
            or igstonintra == "Y"
        )

        sup = payload.get("supplierdt1") or payload.get("supplier") or payload.get("SellerDtls") or {}
        buy = payload.get("buyerdt1") or payload.get("buyer") or payload.get("BuyerDtls") or {}
        disp = payload.get("dispdt1") or payload.get("dispatch") or payload.get("DispDtls") or {}
        ship = payload.get("shipdtl") or payload.get("shipping") or payload.get("ShipDtls") or {}
        exp = payload.get("expdt1") or payload.get("export") or payload.get("ExpDtls") or {}
        val = payload.get("valdt1") or payload.get("valdtls") or payload.get("ValDtls") or {}
        ewb = payload.get("ewbdt1") or payload.get("ewaybill") or payload.get("EwbDtls") or {}
        pay = payload.get("paydtls") or payload.get("payment") or payload.get("PayDtls") or {}
        itemdtls = payload.get("itemdtls") or payload.get("ItemList") or payload.get("items") or []

        sup_st = str(sup.get("supplier_state") or sup.get("state") or sup.get("StateCode") or (sup.get("supplier_gstin") or sup.get("gstin") or sup.get("Gstin", ""))[:2] if len(sup.get("supplier_gstin") or sup.get("gstin") or sup.get("Gstin", "")) >= 2 else "").strip()
        sup_st = sup_st.zfill(2) if sup_st.isdigit() and len(sup_st) == 1 else sup_st

        buy_pos = str(buy.get("pos") or buy.get("Pos") or buy.get("buyer_pos") or buy.get("buyer_state") or buy.get("state") or buy.get("StateCode") or "").strip()
        buy_pos = buy_pos.zfill(2) if buy_pos.isdigit() and len(buy_pos) == 1 else buy_pos

        buy_st = str(buy.get("buyer_state") or buy.get("state") or buy.get("StateCode") or (buy.get("buyer_gstin") or buy.get("gstin") or buy.get("Gstin", ""))[:2] if len(buy.get("buyer_gstin") or buy.get("gstin") or buy.get("Gstin", "")) >= 2 else "").strip()
        buy_st = buy_st.zfill(2) if buy_st.isdigit() and len(buy_st) == 1 else buy_st

        buy_gstin = str(buy.get("buyer_gstin") or buy.get("gstin") or buy.get("Gstin") or "").strip().upper()
        ship_st = str(ship.get("state") or ship.get("ship_state") or ship.get("StateCode") or "").strip()

        dest_state = None
        if buy_gstin and buy_gstin != "URP" and len(buy_gstin) >= 2 and buy_gstin[:2].isdigit():
            dest_state = buy_gstin[:2]
        elif buy_st and buy_st.isdigit() and buy_st != "96":
            dest_state = buy_st

        # Invoice-level financial totals
        inv_assval = _to_f(val.get("assval") or val.get("ttlassval") or val.get("AssVal") or 0.0)
        inv_cgst = _to_f(val.get("cgstval") or val.get("CgstVal") or 0.0)
        inv_sgst = _to_f(val.get("sgstval") or val.get("SgstVal") or 0.0)
        inv_igst = _to_f(val.get("igstval") or val.get("IgstVal") or 0.0)
        inv_ces = _to_f(val.get("cesval") or val.get("CesVal") or 0.0)
        inv_disc = _to_f(val.get("discount") or val.get("discval") or val.get("Discount") or 0.0)
        inv_rnd = _to_f(val.get("rndoffamt") or val.get("RndOffAmt") or 0.0)
        inv_tot = _to_f(val.get("totinvval") or val.get("TotInvVal") or 0.0)

        # E-Way Bill fields
        trans_dist = _to_f(ewb.get("distance_of_transport") or ewb.get("distance") or 0.0)
        veh_num = str(ewb.get("veh_number") or "").strip()
        veh_type = str(ewb.get("veh_type") or "R").strip()
        trans_id = str(ewb.get("transporter_id") or ewb.get("trans_id") or "").strip()
        trans_name = str(ewb.get("transporter_name") or ewb.get("trans_name") or "").strip()
        trans_mode = str(ewb.get("transmode") or ewb.get("mode_of_transport") or "1").strip()
        trans_doc_no = str(ewb.get("transdocno") or ewb.get("transport_doc_no") or "").strip()
        trans_doc_date = str(ewb.get("transdocdt") or ewb.get("transporter_doc_date") or "").strip()
        ewb_req = "Y" if (str(ewb.get("ewayreq")).upper() == "Y" or trans_dist > 0 or inv_tot >= 50000 or (veh_num and veh_num not in ["-", "None", ""])) else "N"

        # Rule 2200 & Rule 2201 Interception for Dispatch, Shipping, and Export (Dict Branch)
        disp_st = str(disp.get("state") or disp.get("dispatch_state") or disp.get("stcd") or disp.get("Stcd") or "").strip()
        disp_gstin = str(disp.get("gstin") or disp.get("disp_gstin") or disp.get("Gstin") or "").strip().upper()
        disp_pin = str(disp.get("pin") or disp.get("dispatch_pin") or disp.get("Pin") or "").strip()
        disp_loc = str(disp.get("loc") or disp.get("disp_loc") or disp.get("Loc") or "").strip()
        disp_name = str(disp.get("nm") or disp.get("dispatch_name") or disp.get("TrdNm") or disp.get("trdnm") or "").strip()

        rule_2200_disp_msg = None
        if disp and disp_st:
            diag_2200_disp = classify_rule_2200_diagnostic(stcd=disp_st, gstin=disp_gstin, pin=disp_pin, loc=disp_loc, section="DispDtls") if classify_rule_2200_diagnostic else None
            if diag_2200_disp and not diag_2200_disp["is_valid"]:
                disp_st = diag_2200_disp["rectified_stcd"]
                rule_2200_disp_msg = f"Rule 2200 Violation ({diag_2200_disp['scenario_name']}): {diag_2200_disp['reason']}"

        ship_st = str(ship.get("state") or ship.get("ship_state") or ship.get("stcd") or ship.get("Stcd") or "").strip()
        ship_gstin = str(ship.get("gstin") or ship.get("ship_gstin") or ship.get("Gstin") or "").strip().upper()
        ship_pin = str(ship.get("pin") or ship.get("ship_pin") or ship.get("Pin") or "").strip()
        ship_loc = str(ship.get("loc") or ship.get("ship_loc") or ship.get("Loc") or "").strip()
        ship_name = str(ship.get("lglnm") or ship.get("ship_name") or ship.get("LglNm") or "").strip()

        rule_2200_ship_msg = None
        if ship and ship_st:
            diag_2200_ship = classify_rule_2200_diagnostic(stcd=ship_st, gstin=ship_gstin, pin=ship_pin, loc=ship_loc, section="ShipDtls") if classify_rule_2200_diagnostic else None
            if diag_2200_ship and not diag_2200_ship["is_valid"]:
                ship_st = diag_2200_ship["rectified_stcd"]
                rule_2200_ship_msg = f"Rule 2200 Violation ({diag_2200_ship['scenario_name']}): {diag_2200_ship['reason']}"

        is_exp_tx = trancatg in ("EXP", "EXPWP", "EXPWOP")
        raw_port = str(exp.get("portCode") or exp.get("port_code") or exp.get("port") or exp.get("Port") or "").strip()
        exp_sbno = str(exp.get("shipBNo") or exp.get("shipping_bill_no") or exp.get("ShipBNo") or exp.get("shipbno") or "").strip()
        exp_sbdt = str(exp.get("shipBDt") or exp.get("shipping_bill_date") or exp.get("ShipBDt") or exp.get("shipbdt") or "").strip()
        exp_cnt = str(exp.get("cntCode") or exp.get("country_code") or exp.get("CntCode") or exp.get("cntcode") or "").strip()
        exp_port = raw_port

        rule_2201_msg = None
        if raw_port or (exp and not is_exp_tx):
            diag_2201 = classify_rule_2201_diagnostic(port=raw_port, trancatg=trancatg, transmode=trans_mode, is_export=is_exp_tx) if classify_rule_2201_diagnostic else None
            if diag_2201 and not diag_2201["is_valid"]:
                if diag_2201.get("omit_expdtls"):
                    exp_port = ""
                    exp_sbno = ""
                    exp_sbdt = ""
                    exp_cnt = ""
                else:
                    exp_port = diag_2201.get("rectified_port") or exp_port
                rule_2201_msg = f"Rule 2201 Violation ({diag_2201['scenario_name']}): {diag_2201['reason']}"

        for i, item in enumerate(itemdtls, start=1):
            slno = str(item.get("slno") or i).strip()
            igstrt = _to_f(item.get("igstrt", 0))
            cgstrt = _to_f(item.get("cgstrt", 0))
            sgstrt = _to_f(item.get("sgstrt", 0))
            gst_rate = igstrt if igstrt > 0 else (cgstrt + sgstrt)
            if gst_rate == 0.0 and _to_f(item.get("gstrate", 0)) > 0:
                gst_rate = _to_f(item.get("gstrate", 0))

            qty = _to_f(item.get("qty") or 0.0)
            uprice = _to_f(item.get("unitrate") or item.get("unitprice") or 0.0)
            gross = _to_f(item.get("grossamt") or item.get("totamt") or (qty * uprice))
            disc = _to_f(item.get("discval") or item.get("discount") or 0.0)
            pretax = _to_f(item.get("pretaxval") or (gross - disc))
            assval = _to_f(item.get("assamt") or item.get("assval") or pretax)

            # Robust HSN & Sentinel Telemetry Resolution
            item_hsn = str(item.get("hsncd") or item.get("hsn") or "").strip()
            prod_name = str(item.get("prdnm") or "").strip()
            prod_desc = str(item.get("prddesc") or "").strip()

            sentinel_audit = item.get("sentinel_audit")
            if not sentinel_audit or not isinstance(sentinel_audit, dict) or not sentinel_audit.get("rectified_hsn"):
                try:
                    from Template_Converters.hsn_resolver import audit_and_rectify_line_item_sentinel
                    sup_gstin = str(sup.get("supplier_gstin") or sup.get("gstin") or "").strip()
                    sentinel_audit = audit_and_rectify_line_item_sentinel(
                        product_name=prod_name,
                        product_desc=prod_desc,
                        declared_hsn=item_hsn,
                        unit_price=uprice,
                        supplier_gstin=sup_gstin
                    )
                except Exception:
                    sentinel_audit = {}

            rectified_hsn = str((sentinel_audit or {}).get("rectified_hsn") or (sentinel_audit or {}).get("original_hsn") or item_hsn).strip()
            should_rectify = bool((sentinel_audit or {}).get("should_rectify", False))
            risk_level = str((sentinel_audit or {}).get("risk_level", "LOW"))
            status_badge = str((sentinel_audit or {}).get("status_badge", "AUTO_APPROVED"))
            risk_prob = _to_f((sentinel_audit or {}).get("error_probability", 0.0))
            reasons = (sentinel_audit or {}).get("reasons", [])
            audit_reasons_str = "; ".join(str(r) for r in reasons) if isinstance(reasons, list) else str(reasons or "")

            stat_rate = _to_f((sentinel_audit or {}).get("statutory_rate", 0.0))
            if gst_rate == 0.0 and stat_rate > 0.0:
                gst_rate = stat_rate

            final_hsn = (rectified_hsn if (should_rectify and rectified_hsn) else (item_hsn if (item_hsn and len(item_hsn) in [2, 4, 6, 8]) else (rectified_hsn or item_hsn)))

            sup_st = str(sup.get("supplier_state") or sup.get("state") or sup.get("StateCode") or (sup.get("supplier_gstin") or sup.get("gstin") or sup.get("Gstin", ""))[:2] if len(sup.get("supplier_gstin") or sup.get("gstin") or sup.get("Gstin", "")) >= 2 else "").strip()
            sup_st = sup_st.zfill(2) if sup_st.isdigit() and len(sup_st) == 1 else sup_st

            buy_pos = str(buy.get("pos") or buy.get("Pos") or buy.get("buyer_pos") or buy.get("buyer_state") or buy.get("state") or buy.get("StateCode") or "").strip()
            buy_pos = buy_pos.zfill(2) if buy_pos.isdigit() and len(buy_pos) == 1 else buy_pos

            buy_st = str(buy.get("buyer_state") or buy.get("state") or buy.get("StateCode") or (buy.get("buyer_gstin") or buy.get("gstin") or buy.get("Gstin", ""))[:2] if len(buy.get("buyer_gstin") or buy.get("gstin") or buy.get("Gstin", "")) >= 2 else "").strip()
            buy_st = buy_st.zfill(2) if buy_st.isdigit() and len(buy_st) == 1 else buy_st

            ship_st = ship_st or str(ship.get("state") or ship.get("ship_state") or ship.get("StateCode") or ship.get("stcd") or ship.get("Stcd") or "").strip()
            is_export_val = trancatg in ("EXP", "EXPWP", "EXPWOP")
            is_sez_val = trancatg in ("SEZWP", "SEZWOP")
            is_intra_by_pos = (sup_st == buy_pos and not is_export_val and not is_sez_val) if (sup_st and buy_pos) else True
            is_intra_line = (is_intra_by_pos and igstonintra != "Y")

            cgst_amt = _to_f(item.get("cgstamt") or item.get("cgstval") or item.get("CgstAmt") or item.get("CgstVal") or 0.0)
            sgst_amt = _to_f(item.get("sgstamt") or item.get("sgstval") or item.get("SgstAmt") or item.get("SgstVal") or 0.0)
            igst_amt = _to_f(item.get("igstamt") or item.get("igstval") or item.get("IgstAmt") or item.get("IgstVal") or 0.0)

            # Rule 2192: Item Total Amount Formula Mismatch (TotAmt = Qty * UnitPrice)
            exp_gross = round(qty * uprice, 2)
            is_serv_line = (str(item.get("isservc") or item.get("is_service") or "N").strip().upper() == "Y" or item_hsn.startswith("99"))
            if is_serv_line and qty == 0.0 and uprice > 0.0:
                diag_2192 = classify_rule_2192_diagnostic(
                    qty=qty, unitprice=uprice, totamt=gross, discount=disc, is_service="Y", hsn=item_hsn, item_slno=slno
                ) if classify_rule_2192_diagnostic else None
                qty = 1.0
                gross = round(qty * uprice, 2)
                status_badge = "FLAGGED_AND_RECTIFIED"
                risk_level = "HIGH"
                risk_prob = max(risk_prob, 0.95)
                r_scen = diag_2192.get("scenario_name", "Services with Null or Missing Qty") if diag_2192 else "Services with Null or Missing Qty"
                r_reason = diag_2192.get("reason", "Even for service lines where quantity is conceptual, set Qty: 1 so that 1 * UnitPrice = TotAmt.") if diag_2192 else "Even for service lines where quantity is conceptual, set Qty: 1."
                r_msg = f"Rule 2192 Violation ({r_scen}): {r_reason}"
                audit_reasons_str = f"{audit_reasons_str}; {r_msg}" if audit_reasons_str else r_msg
            elif abs(gross - exp_gross) > 0.005 and (qty > 0.0 or uprice > 0.0):
                diag_2192 = classify_rule_2192_diagnostic(
                    qty=qty, unitprice=uprice, totamt=gross, discount=disc,
                    gstrate=gst_rate,
                    taxes=cgst_amt + sgst_amt + igst_amt,
                    is_service="Y" if is_serv_line else "N",
                    hsn=item_hsn, item_slno=slno
                ) if classify_rule_2192_diagnostic else None
                gross = exp_gross
                status_badge = "FLAGGED_AND_RECTIFIED"
                risk_level = "HIGH"
                risk_prob = max(risk_prob, 0.95)
                r_scen = diag_2192.get("scenario_name", "Item Total Amount Formula Mismatch") if diag_2192 else "Item Total Amount Formula Mismatch"
                r_reason = diag_2192.get("reason", f"TotAmt must equal Qty * UnitPrice ({exp_gross:.2f}).") if diag_2192 else f"TotAmt must equal Qty * UnitPrice ({exp_gross:.2f})."
                r_msg = f"Rule 2192 Violation ({r_scen}): {r_reason}"
                audit_reasons_str = f"{audit_reasons_str}; {r_msg}" if audit_reasons_str else r_msg

            # Rule 2193: Item Assessable Amount Formula Mismatch (AssAmt = TotAmt - Discount)
            exp_assval = round(gross - disc, 2)
            if abs(assval - exp_assval) > 0.005:
                diag_2193 = classify_rule_2193_diagnostic(
                    totamt=gross, discount=disc, assamt=assval,
                    gstrate=gst_rate,
                    taxes=cgst_amt + sgst_amt + igst_amt,
                    othchrg=_to_f(item.get("othchrg") or 0.0),
                    item_slno=slno
                ) if classify_rule_2193_diagnostic else None
                assval = exp_assval
                status_badge = "FLAGGED_AND_RECTIFIED"
                risk_level = "HIGH"
                risk_prob = max(risk_prob, 0.95)
                r_scen = diag_2193.get("scenario_name", "Item Assessable Amount Formula Mismatch") if diag_2193 else "Item Assessable Amount Formula Mismatch"
                r_reason = diag_2193.get("reason", f"AssAmt must equal TotAmt - Discount ({exp_assval:.2f}).") if diag_2193 else f"AssAmt must equal TotAmt - Discount ({exp_assval:.2f})."
                r_msg = f"Rule 2193 Violation ({r_scen}): {r_reason}"
                audit_reasons_str = f"{audit_reasons_str}; {r_msg}" if audit_reasons_str else r_msg

            # Rule 2174 Inter-State Supply Sentinel Interception & Lakehouse Tax Normalization
            if not is_intra_line and (cgst_amt > 0.0 or sgst_amt > 0.0):
                diag_2174 = classify_rule_2174_diagnostic(
                    seller_state=sup_st,
                    buyer_pos=buy_pos,
                    buyer_state=buy_st,
                    buyer_gstin=buy_gstin,
                    ship_state=ship_st,
                    cgst_amt=cgst_amt,
                    sgst_amt=sgst_amt,
                    igst_amt=igst_amt
                ) if classify_rule_2174_diagnostic else None

                rectified_igst = round(cgst_amt + sgst_amt + igst_amt, 2)
                cgst_amt = 0.0
                sgst_amt = 0.0
                igst_amt = rectified_igst

                status_badge = "FLAGGED_AND_RECTIFIED"
                risk_level = "HIGH"
                risk_prob = max(risk_prob, 0.95)
                scen_name = diag_2174.get("scenario_name", "Standard Inter-State Supply") if diag_2174 else "Standard Inter-State Supply"
                diag_reason = diag_2174.get("reason", "Supplier and POS states are different, so it is an inter-state sale. Clear CGST/SGST to 0.00 and pass the full tax rate under IgstAmt.") if diag_2174 else "Supplier and POS states are different, so it is an inter-state sale. Clear CGST/SGST to 0.00 and pass the full tax rate under IgstAmt."
                rule_msg = f"Rule 2174 Violation ({scen_name}): {diag_reason}"
                audit_reasons_str = f"{audit_reasons_str}; {rule_msg}" if audit_reasons_str else rule_msg

            # Rule 2172 Intra-State Supply Sentinel Interception & Lakehouse Tax Normalization
            elif is_intra_by_pos and igst_amt > 0.0:
                diag_2172 = classify_rule_2172_diagnostic(
                    seller_state=sup_st,
                    buyer_pos=buy_pos,
                    buyer_state=buy_st,
                    buyer_gstin=buy_gstin,
                    igst_amt=igst_amt,
                    cgst_amt=cgst_amt,
                    sgst_amt=sgst_amt,
                    igstonintra=igstonintra,
                    is_exceptional_intra=is_exceptional_intra,
                    header_igst=inv_igst,
                    header_cgst=inv_cgst,
                    header_sgst=inv_sgst,
                ) if classify_rule_2172_diagnostic else None

                scen_2172 = diag_2172.get("scenario") if diag_2172 else "STANDARD_INTRA_STATE"
                scen_name = diag_2172.get("scenario_name", "Standard Intra-State Transaction") if diag_2172 else "Standard Intra-State Transaction"
                diag_reason = diag_2172.get("reason", "Same supplier state and POS means regular intra-state supply. Clear IgstAmt and split tax equally between CGST and SGST.") if diag_2172 else "Same supplier state and POS means regular intra-state supply. Clear IgstAmt and split tax equally between CGST and SGST."

                if scen_2172 == "WRONG_POS_ENTERED":
                    rectified_pos = str(diag_2172.get("destination_state") or dest_state or buy_st).strip().zfill(2)
                    buy_pos = rectified_pos
                    is_intra_line = False
                    is_intra_by_pos = False
                    cgst_amt = 0.0
                    sgst_amt = 0.0
                    rule_msg = f"Rule 2172 Violation ({scen_name}): {diag_reason} (rectified buyer_pos: '{sup_st}' -> '{rectified_pos}')"
                elif scen_2172 == "EXCEPTIONAL_INTRA_STATE_IGST":
                    igstonintra = "Y"
                    reversecharge = "Y"
                    is_intra_line = False
                    cgst_amt = 0.0
                    sgst_amt = 0.0
                    rule_msg = f"Rule 2172 Violation ({scen_name}): {diag_reason}"
                else:
                    tot_tax = round(igst_amt + cgst_amt + sgst_amt, 2)
                    half_split = round(tot_tax / 2.0, 2)
                    cgst_amt = half_split
                    sgst_amt = round(tot_tax - half_split, 2)
                    igst_amt = 0.0
                    rule_msg = f"Rule 2172 Violation ({scen_name}): {diag_reason}"

                status_badge = "FLAGGED_AND_RECTIFIED"
                risk_level = "HIGH"
                risk_prob = max(risk_prob, 0.95)
                audit_reasons_str = f"{audit_reasons_str}; {rule_msg}" if audit_reasons_str else rule_msg
            elif assval > 0 and cgst_amt == 0.0 and sgst_amt == 0.0 and igst_amt == 0.0 and gst_rate > 0:
                if not is_intra_line:
                    igst_amt = round(assval * (gst_rate / 100.0), 2)
                else:
                    cgst_amt = round(assval * (gst_rate / 200.0), 2)
                    sgst_amt = round(assval * (gst_rate / 200.0), 2)
            ces_val = _to_f(item.get("cesval") or item.get("cessamt") or item.get("CesAmt") or 0.0)
            ces_nonad = _to_f(item.get("cesnonadvl") or item.get("cesnonadval") or item.get("cessnonadval") or item.get("cesnonadvlamt") or item.get("CesNonAdvlAmt") or 0.0)
            stces_val = _to_f(item.get("statecesval") or item.get("statecessamt") or item.get("StateCesAmt") or 0.0)
            stces_nonad = _to_f(item.get("statecesnonadvl") or item.get("statecesnonadval") or item.get("StateCesNonAdvlAmt") or 0.0)
            oth_chrg = _to_f(item.get("othchrg") or item.get("OthChrg") or 0.0)

            tot_line_val = _to_f(item.get("totitemval") or item.get("TotItemVal") or 0.0)
            exp_totline = round(assval + cgst_amt + sgst_amt + igst_amt + ces_val + ces_nonad + stces_val + stces_nonad + oth_chrg, 2)

            if abs(tot_line_val - exp_totline) > 1.00:
                diag_2194 = classify_rule_2194_diagnostic(
                    totitemval=tot_line_val,
                    assamt=assval,
                    cgstamt=cgst_amt,
                    sgstamt=sgst_amt,
                    igstamt=igst_amt,
                    cesamt=ces_val,
                    cesnonadval=ces_nonad,
                    statecesamt=stces_val,
                    statecesnonadval=stces_nonad,
                    othchrg=oth_chrg,
                    totamt=gross,
                    discount=disc,
                    item_slno=slno,
                    hsn=final_hsn
                ) if classify_rule_2194_diagnostic else None
                tot_line_val = exp_totline
                status_badge = "FLAGGED_AND_RECTIFIED"
                risk_level = "HIGH"
                risk_prob = max(risk_prob, 0.95)
                r_scen = diag_2194.get("scenario_name", "Total Item Value Formula Mismatch") if diag_2194 else "Total Item Value Formula Mismatch"
                r_reason = diag_2194.get("reason", f"TotItemVal deviates beyond +/- 1.00 tolerance (expected {exp_totline:.2f}).") if diag_2194 else f"TotItemVal deviates beyond +/- 1.00 tolerance (expected {exp_totline:.2f})."
                r_msg = f"Rule 2194 Violation ({r_scen}): {r_reason}"
                audit_reasons_str = f"{audit_reasons_str}; {r_msg}" if audit_reasons_str else r_msg
            elif tot_line_val == 0.0:
                tot_line_val = exp_totline

            # Rule 2177 UQC Standardization & Sentinel Interception
            raw_unit = str(item.get("uqc") or item.get("unit") or "NOS").strip()
            norm_unit, diag_2177 = normalize_uqc_statutory(raw_unit) if normalize_uqc_statutory else (raw_unit, {"is_valid": True})
            if not diag_2177["is_valid"]:
                status_badge = "FLAGGED_AND_RECTIFIED"
                risk_level = "HIGH"
                risk_prob = max(risk_prob, 0.95)
                uqc_msg = f"Rule 2177 Violation ({diag_2177.get('scenario_name', 'Invalid UQC')}): {diag_2177.get('reason', 'UQC not in master')} (original: '{raw_unit}', rectified: '{norm_unit}')"
                audit_reasons_str = f"{audit_reasons_str}; {uqc_msg}" if audit_reasons_str else uqc_msg

            # Rule 2200 Dispatch & Shipping Telemetry
            if rule_2200_disp_msg:
                status_badge = "FLAGGED_AND_RECTIFIED"
                risk_level = "HIGH"
                risk_prob = max(risk_prob, 0.95)
                audit_reasons_str = f"{audit_reasons_str}; {rule_2200_disp_msg}" if audit_reasons_str else rule_2200_disp_msg

            if rule_2200_ship_msg:
                status_badge = "FLAGGED_AND_RECTIFIED"
                risk_level = "HIGH"
                risk_prob = max(risk_prob, 0.95)
                audit_reasons_str = f"{audit_reasons_str}; {rule_2200_ship_msg}" if audit_reasons_str else rule_2200_ship_msg

            # Rule 2201 Export Port Telemetry
            if rule_2201_msg:
                status_badge = "FLAGGED_AND_RECTIFIED"
                risk_level = "HIGH"
                risk_prob = max(risk_prob, 0.95)
                audit_reasons_str = f"{audit_reasons_str}; {rule_2201_msg}" if audit_reasons_str else rule_2201_msg

            rows.append({
                # Document & Transaction Details
                "invoice_id": docno,
                "doc_type": doc_type,
                "doc_date": doc_dt,
                "transaction_category": trancatg,
                "reverse_charge": reversecharge,
                "igst_on_intra": igstonintra,

                # Supplier Details
                "supplier_gstin": str(sup.get("supplier_gstin") or sup.get("gstin") or "").strip(),
                "supplier_lglnm": str(sup.get("supplier_lglnm") or sup.get("lglnm") or "").strip(),
                "supplier_trdnm": str(sup.get("supplier_trdnm") or sup.get("trdnm") or "").strip(),
                "supplier_state": str(sup.get("supplier_state") or sup.get("state") or "").strip(),
                "supplier_pin": str(sup.get("supplier_pin") or sup.get("pin") or "").strip(),
                "supplier_loc": str(sup.get("supplier_loc") or sup.get("loc") or "").strip(),
                "supplier_phone": str(sup.get("supplier_phone") or sup.get("phone") or "").strip(),
                "supplier_email": str(sup.get("supplier_email") or sup.get("email") or "").strip(),

                # Buyer Details
                "buyer_gstin": str(buy.get("buyer_gstin") or buy.get("gstin") or "").strip(),
                "buyer_lglnm": str(buy.get("buyer_lglnm") or buy.get("lglnm") or "").strip(),
                "buyer_trdnm": str(buy.get("buyer_trdnm") or buy.get("trdnm") or "").strip(),
                "buyer_state": str(buy.get("buyer_state") or buy.get("state") or "").strip(),
                "buyer_pin": str(buy.get("buyer_pin") or buy.get("pin") or "").strip(),
                "buyer_pos": buy_pos,
                "buyer_loc": str(buy.get("buyer_loc") or buy.get("loc") or "").strip(),
                "buyer_phone": str(buy.get("buyer_phone") or buy.get("phone") or "").strip(),
                "buyer_email": str(buy.get("buyer_email") or buy.get("email") or "").strip(),

                # Dispatch & Shipping
                "dispatch_name": disp_name,
                "dispatch_state": disp_st,
                "dispatch_pin": disp_pin,
                "ship_gstin": ship_gstin,
                "ship_name": ship_name,
                "ship_state": ship_st,
                "ship_pin": ship_pin,

                # Export Details
                "export_shipping_bill_no": exp_sbno,
                "export_shipping_bill_date": exp_sbdt,
                "export_country": exp_cnt,
                "export_port": exp_port,

                # Line Item Details
                "line_item_id": f"{docno}-L{slno.zfill(2)}",
                "item_slno": slno,
                "product_name": prod_name,
                "product_description": prod_desc,
                "is_service": str(item.get("isservc") or item.get("is_service") or "N").strip(),
                "hsn": final_hsn,
                "quantity": qty,
                "unit": norm_unit,
                "unit_price": uprice,
                "gross_amount": gross,
                "item_discount": disc,
                "pretax_value": pretax,
                "taxable_value": assval,
                "gst_rate": gst_rate,
                "cgst_amount": cgst_amt,
                "sgst_amount": sgst_amt,
                "igst_amount": igst_amt,
                "cess_rate": _to_f(item.get("cesrt") or item.get("cessrt") or item.get("cesrate") or 0.0),
                "cess_amount": _to_f(item.get("cesval") or item.get("cessamt") or 0.0),
                "state_cess_rate": _to_f(item.get("statecesrt") or item.get("statecessrt") or item.get("statecesrate") or 0.0),
                "state_cess_amount": _to_f(item.get("statecesval") or item.get("statecessamt") or 0.0),
                "other_charges": _to_f(item.get("othchrg") or 0.0),
                "total_item_value": tot_line_val,

                # Invoice-Level Valuation Breakdown
                "inv_taxable_value": inv_assval,
                "inv_cgst_amount": 0.0 if not is_intra_line else inv_cgst,
                "inv_sgst_amount": 0.0 if not is_intra_line else inv_sgst,
                "inv_igst_amount": (inv_cgst + inv_sgst + inv_igst) if (not is_intra_line and (inv_cgst > 0 or inv_sgst > 0)) else inv_igst,
                "inv_cess_amount": inv_ces,
                "inv_discount": inv_disc,
                "inv_roundoff": inv_rnd,
                "inv_total_value": inv_tot,

                # Transportation & E-Way Bill Details
                "ewb_required": ewb_req,
                "transporter_id": trans_id,
                "transporter_name": trans_name,
                "transport_mode": trans_mode,
                "transport_doc_no": trans_doc_no,
                "transport_doc_date": trans_doc_date,
                "transit_distance_km": trans_dist,
                "vehicle_number": veh_num,
                "vehicle_type": veh_type,

                # Payment Details
                "payment_mode": str(pay.get("pmtmode") or payload.get("pmtmode") or "").strip(),
                "payment_account_no": str(pay.get("upiacctnumber") or payload.get("upiacctnumber") or "").strip(),
                "payment_ifsc": str(pay.get("upiactifsccd") or payload.get("upiactifsccd") or "").strip(),
                "payment_upi": str(pay.get("upiid") or payload.get("upiid") or "").strip(),

                # Compliance & Status
                "compliance_status": "VALID",

                # Module 2 Sentinel ML Telemetry
                "sentinel_risk_prob": risk_prob,
                "sentinel_risk_level": risk_level,
                "sentinel_status_badge": status_badge,
                "sentinel_recommended_hsn": rectified_hsn or final_hsn,
                "sentinel_audit_reasons": audit_reasons_str
            })

        # Invoice-Level Header Valuation Reconciliation (Rule 2182, Rule 2172 Scenario 4, Rule 2174 Scenario 3, and General Totals)
        sum_line_cgst = round(sum(r["cgst_amount"] for r in rows), 2)
        sum_line_sgst = round(sum(r["sgst_amount"] for r in rows), 2)
        sum_line_igst = round(sum(r["igst_amount"] for r in rows), 2)
        sum_line_assval = round(sum(r["taxable_value"] for r in rows), 2)
        sum_line_totamt = round(sum(r.get("gross_amount", r["taxable_value"]) for r in rows), 2)
        sum_line_disc = round(sum(r.get("item_discount", 0.0) for r in rows), 2)

        header_mismatch_2182 = False
        header_diag_2182 = None
        if abs(inv_assval - sum_line_assval) > 0.005:
            header_mismatch_2182 = True
            if classify_rule_2182_diagnostic:
                header_diag_2182 = classify_rule_2182_diagnostic(
                    header_assval=inv_assval,
                    sum_item_assamt=sum_line_assval,
                    sum_item_totamt=sum_line_totamt,
                    header_discount=inv_disc,
                    sum_item_discount=sum_line_disc,
                    items=[{"AssAmt": r["taxable_value"], "TotAmt": r.get("gross_amount", r["taxable_value"]), "Discount": r.get("item_discount", 0.0)} for r in rows]
                )

        rectified_inv_assval = sum_line_assval

        header_mismatch_2172 = False
        header_diag_2172 = None
        if (sum_line_cgst > 0 or sum_line_sgst > 0) and sum_line_igst == 0.0 and inv_igst > 0.0:
            header_mismatch_2172 = True
            if classify_rule_2172_diagnostic:
                header_diag_2172 = classify_rule_2172_diagnostic(
                    seller_state=sup_st,
                    buyer_pos=buy_pos,
                    buyer_state=buy_st,
                    buyer_gstin=buy_gstin,
                    igst_amt=sum_line_igst,
                    cgst_amt=sum_line_cgst,
                    sgst_amt=sum_line_sgst,
                    header_igst=inv_igst,
                    header_cgst=inv_cgst,
                    header_sgst=inv_sgst,
                    item_tax_summary={"cgst": sum_line_cgst, "sgst": sum_line_sgst, "igst": sum_line_igst}
                )

        header_mismatch_2183 = False
        header_diag_2183 = None
        is_intra_tx = (sup_st == buy_pos and igstonintra != "Y" and trancatg not in ("EXP", "EXPWP", "EXPWOP", "SEZWP", "SEZWOP"))
        if is_intra_tx:
            if abs(inv_sgst - sum_line_sgst) > 0.005:
                header_mismatch_2183 = True
                if classify_rule_2183_diagnostic:
                    header_diag_2183 = classify_rule_2183_diagnostic(
                        header_sgst=inv_sgst,
                        sum_item_sgst=sum_line_sgst,
                        items=[{"SgstAmt": r["sgst_amount"], "CgstAmt": r["cgst_amount"]} for r in rows],
                        header_cgst=inv_cgst,
                        sum_item_cgst=sum_line_cgst,
                        is_inter_state=False,
                        seller_state=sup_st,
                        buyer_pos=buy_pos,
                        igst_on_intra=igstonintra,
                    )
        else:
            if inv_sgst > 0.0 or sum_line_sgst > 0.0:
                header_mismatch_2183 = True
                if classify_rule_2183_diagnostic:
                    header_diag_2183 = classify_rule_2183_diagnostic(
                        header_sgst=inv_sgst,
                        sum_item_sgst=sum_line_sgst,
                        items=[{"SgstAmt": r["sgst_amount"], "CgstAmt": r["cgst_amount"]} for r in rows],
                        header_cgst=inv_cgst,
                        sum_item_cgst=sum_line_cgst,
                        is_inter_state=True,
                        seller_state=sup_st,
                        buyer_pos=buy_pos,
                        igst_on_intra=igstonintra,
                    )

        header_mismatch_2184 = False
        header_diag_2184 = None
        if is_intra_tx:
            if abs(inv_cgst - sum_line_cgst) > 0.005:
                header_mismatch_2184 = True
                if classify_rule_2184_diagnostic:
                    header_diag_2184 = classify_rule_2184_diagnostic(
                        header_cgst=inv_cgst,
                        sum_item_cgst=sum_line_cgst,
                        items=[{"CgstAmt": r["cgst_amount"], "SgstAmt": r["sgst_amount"]} for r in rows],
                        header_sgst=inv_sgst,
                        sum_item_sgst=sum_line_sgst,
                        is_inter_state=False,
                        seller_state=sup_st,
                        buyer_pos=buy_pos,
                        igst_on_intra=igstonintra,
                    )
        else:
            if inv_cgst > 0.0 or sum_line_cgst > 0.0:
                header_mismatch_2184 = True
                if classify_rule_2184_diagnostic:
                    header_diag_2184 = classify_rule_2184_diagnostic(
                        header_cgst=inv_cgst,
                        sum_item_cgst=sum_line_cgst,
                        items=[{"CgstAmt": r["cgst_amount"], "SgstAmt": r["sgst_amount"]} for r in rows],
                        header_sgst=inv_sgst,
                        sum_item_sgst=sum_line_sgst,
                        is_inter_state=True,
                        seller_state=sup_st,
                        buyer_pos=buy_pos,
                        igst_on_intra=igstonintra,
                    )

        header_mismatch_2185 = False
        header_diag_2185 = None
        is_std_intra_store = (is_intra_tx and igstonintra != "Y" and trancatg not in ("EXP", "EXPWP", "EXPWOP", "SEZWP", "SEZWOP"))
        if is_std_intra_store:
            if inv_igst > 0.0 or sum_line_igst > 0.0:
                header_mismatch_2185 = True
                if classify_rule_2185_diagnostic:
                    header_diag_2185 = classify_rule_2185_diagnostic(
                        header_igst=inv_igst,
                        sum_item_igst=sum_line_igst,
                        items=[{"IgstAmt": r["igst_amount"], "CgstAmt": r["cgst_amount"], "SgstAmt": r["sgst_amount"]} for r in rows],
                        header_cgst=inv_cgst,
                        sum_item_cgst=sum_line_cgst,
                        header_sgst=inv_sgst,
                        sum_item_sgst=sum_line_sgst,
                        is_inter_state=(not is_intra_tx),
                        seller_state=sup_st,
                        buyer_pos=buy_pos,
                        igst_on_intra=igstonintra,
                        trancatg=trancatg,
                    )
        else:
            if abs(inv_igst - sum_line_igst) > 0.005:
                header_mismatch_2185 = True
                if classify_rule_2185_diagnostic:
                    header_diag_2185 = classify_rule_2185_diagnostic(
                        header_igst=inv_igst,
                        sum_item_igst=sum_line_igst,
                        items=[{"IgstAmt": r["igst_amount"], "CgstAmt": r["cgst_amount"], "SgstAmt": r["sgst_amount"]} for r in rows],
                        header_cgst=inv_cgst,
                        sum_item_cgst=sum_line_cgst,
                        header_sgst=inv_sgst,
                        sum_item_sgst=sum_line_sgst,
                        is_inter_state=(not is_intra_tx),
                        seller_state=sup_st,
                        buyer_pos=buy_pos,
                        igst_on_intra=igstonintra,
                        trancatg=trancatg,
                    )

        header_mismatch_2186 = False
        header_diag_2186 = None
        sum_item_cesad = round(sum(_to_f(itm.get("cesval") or itm.get("cessamt") or itm.get("CesAmt") or 0.0) for itm in itemdtls), 2)
        sum_item_cesnonad = round(sum(_to_f(itm.get("cesnonadvlamt") or itm.get("cesnonadval") or itm.get("CesNonAdvlAmt") or itm.get("CesNonAdVal") or itm.get("cessnonadval") or 0.0) for itm in itemdtls), 2)
        sum_item_stces = round(sum(_to_f(itm.get("statecesval") or itm.get("statecessamt") or itm.get("StateCesAmt") or itm.get("stcesval") or itm.get("StCesVal") or 0.0) for itm in itemdtls), 2)
        sum_line_total_cess = round(sum_item_cesad + sum_item_cesnonad, 2)
        if abs(inv_ces - sum_line_total_cess) > 0.005:
            header_mismatch_2186 = True
            if classify_rule_2186_diagnostic:
                header_diag_2186 = classify_rule_2186_diagnostic(
                    header_cess=inv_ces,
                    sum_item_cess=sum_line_total_cess,
                    items=itemdtls,
                    header_stcess=_to_f(val.get("stcesval") or val.get("StCesVal") or 0.0),
                    sum_item_stcess=sum_item_stces,
                    sum_item_cesad=sum_item_cesad,
                    sum_item_cesnonad=sum_item_cesnonad,
                )

        if sum_line_igst == 0.0 and (sum_line_cgst > 0 or sum_line_sgst > 0):
            rectified_inv_cgst = sum_line_cgst
            rectified_inv_sgst = sum_line_sgst
            rectified_inv_igst = 0.0
        elif sum_line_igst > 0.0 and sum_line_cgst == 0.0 and sum_line_sgst == 0.0:
            rectified_inv_cgst = 0.0
            rectified_inv_sgst = 0.0
            rectified_inv_igst = sum_line_igst
        else:
            rectified_inv_cgst = sum_line_cgst if sum_line_cgst > 0 else inv_cgst
            rectified_inv_sgst = sum_line_sgst if sum_line_sgst > 0 else inv_sgst
            rectified_inv_igst = sum_line_igst if sum_line_igst > 0 else inv_igst

        rectified_inv_ces = sum_line_total_cess if header_mismatch_2186 else inv_ces

        for r in rows:
            r["buyer_pos"] = buy_pos
            r["igst_on_intra"] = igstonintra
            r["reverse_charge"] = reversecharge
            r["inv_taxable_value"] = rectified_inv_assval
            r["inv_cgst_amount"] = rectified_inv_cgst
            r["inv_sgst_amount"] = rectified_inv_sgst
            r["inv_igst_amount"] = rectified_inv_igst
            r["inv_cess_amount"] = rectified_inv_ces

            calc_tot = round(r["inv_taxable_value"] + r["inv_cgst_amount"] + r["inv_sgst_amount"] + r["inv_igst_amount"] + r["inv_cess_amount"] - r["inv_discount"] + r["inv_roundoff"], 2)
            if r["inv_total_value"] == 0.0 or abs(r["inv_total_value"] - calc_tot) > 0.01:
                r["inv_total_value"] = calc_tot

            if header_mismatch_2182:
                r["sentinel_status_badge"] = "FLAGGED_AND_RECTIFIED"
                r["sentinel_risk_level"] = "HIGH"
                r["sentinel_risk_prob"] = max(r.get("sentinel_risk_prob", 0.0), 0.95)
                h2182_scen = header_diag_2182.get("scenario_name", "Header Not Updated After Item Edits") if header_diag_2182 else "Header Not Updated After Item Edits"
                h2182_reason = header_diag_2182.get("reason", "Ensure ValDtls.AssVal dynamically recalculates the sum of all ItemList[i].AssAmt before sending.") if header_diag_2182 else "Ensure ValDtls.AssVal dynamically recalculates the sum of all ItemList[i].AssAmt before sending."
                h2182_msg = f"Rule 2182 Violation ({h2182_scen}): {h2182_reason}"
                existing_reasons = r.get("sentinel_audit_reasons", "")
                if h2182_msg not in existing_reasons:
                    r["sentinel_audit_reasons"] = f"{existing_reasons}; {h2182_msg}" if existing_reasons else h2182_msg

            if header_mismatch_2172:
                r["sentinel_status_badge"] = "FLAGGED_AND_RECTIFIED"
                r["sentinel_risk_level"] = "HIGH"
                r["sentinel_risk_prob"] = max(r.get("sentinel_risk_prob", 0.0), 0.95)
                h_scen = header_diag_2172.get("scenario_name", "Summary vs. Item Level Mismatch") if header_diag_2172 else "Summary vs. Item Level Mismatch"
                h_reason = header_diag_2172.get("reason", "Header total tax values in ValDtls must match the sum of item-level taxes in ItemList.") if header_diag_2172 else "Header total tax values in ValDtls must match the sum of item-level taxes in ItemList."
                h_msg = f"Rule 2172 Violation ({h_scen}): {h_reason}"
                existing_reasons = r.get("sentinel_audit_reasons", "")
                if h_msg not in existing_reasons:
                    r["sentinel_audit_reasons"] = f"{existing_reasons}; {h_msg}" if existing_reasons else h_msg

            if header_mismatch_2183:
                r["sentinel_status_badge"] = "FLAGGED_AND_RECTIFIED"
                r["sentinel_risk_level"] = "HIGH"
                r["sentinel_risk_prob"] = max(r.get("sentinel_risk_prob", 0.0), 0.95)
                h2183_scen = header_diag_2183.get("scenario_name", "Header Not Recalculated After Item Edits") if header_diag_2183 else "Header Not Recalculated After Item Edits"
                h2183_reason = header_diag_2183.get("reason", "Ensure ValDtls.SgstVal dynamically computes the sum of all ItemList[i].SgstAmt.") if header_diag_2183 else "Ensure ValDtls.SgstVal dynamically computes the sum of all ItemList[i].SgstAmt."
                h2183_msg = f"Rule 2183 Violation ({h2183_scen}): {h2183_reason}"
                existing_reasons = r.get("sentinel_audit_reasons", "")
                if h2183_msg not in existing_reasons:
                    r["sentinel_audit_reasons"] = f"{existing_reasons}; {h2183_msg}" if existing_reasons else h2183_msg

            if header_mismatch_2184:
                r["sentinel_status_badge"] = "FLAGGED_AND_RECTIFIED"
                r["sentinel_risk_level"] = "HIGH"
                r["sentinel_risk_prob"] = max(r.get("sentinel_risk_prob", 0.0), 0.95)
                h2184_scen = header_diag_2184.get("scenario_name", "Header Not Recalculated After Item Edits") if header_diag_2184 else "Header Not Recalculated After Item Edits"
                h2184_reason = header_diag_2184.get("reason", "Ensure ValDtls.CgstVal dynamically computes the sum of all ItemList[i].CgstAmt.") if header_diag_2184 else "Ensure ValDtls.CgstVal dynamically computes the sum of all ItemList[i].CgstAmt."
                h2184_msg = f"Rule 2184 Violation ({h2184_scen}): {h2184_reason}"
                existing_reasons = r.get("sentinel_audit_reasons", "")
                if h2184_msg not in existing_reasons:
                    r["sentinel_audit_reasons"] = f"{existing_reasons}; {h2184_msg}" if existing_reasons else h2184_msg

            if header_mismatch_2185:
                r["sentinel_status_badge"] = "FLAGGED_AND_RECTIFIED"
                r["sentinel_risk_level"] = "HIGH"
                r["sentinel_risk_prob"] = max(r.get("sentinel_risk_prob", 0.0), 0.95)
                h2185_scen = header_diag_2185.get("scenario_name", "Header Not Recalculated After Item Edits") if header_diag_2185 else "Header Not Recalculated After Item Edits"
                h2185_reason = header_diag_2185.get("reason", "Ensure ValDtls.IgstVal dynamically computes the sum of all ItemList[i].IgstAmt.") if header_diag_2185 else "Ensure ValDtls.IgstVal dynamically computes the sum of all ItemList[i].IgstAmt."
                h2185_msg = f"Rule 2185 Violation ({h2185_scen}): {h2185_reason}"
                existing_reasons = r.get("sentinel_audit_reasons", "")
                if h2185_msg not in existing_reasons:
                    r["sentinel_audit_reasons"] = f"{existing_reasons}; {h2185_msg}" if existing_reasons else h2185_msg

            if header_mismatch_2186:
                r["sentinel_status_badge"] = "FLAGGED_AND_RECTIFIED"
                r["sentinel_risk_level"] = "HIGH"
                r["sentinel_risk_prob"] = max(r.get("sentinel_risk_prob", 0.0), 0.95)
                h2186_scen = header_diag_2186.get("scenario_name", "Header Not Recalculated After Item Edits") if header_diag_2186 else "Header Not Recalculated After Item Edits"
                h2186_reason = header_diag_2186.get("reason", "Ensure ValDtls.CesVal dynamically sums both ad-valorem Cess (CesAmt) and non-ad-valorem Cess (CesNonAdvlAmt) across all line items.") if header_diag_2186 else "Ensure ValDtls.CesVal dynamically sums both ad-valorem Cess (CesAmt) and non-ad-valorem Cess (CesNonAdvlAmt) across all line items."
                h2186_msg = f"Rule 2186 Violation ({h2186_scen}): {h2186_reason}"
                existing_reasons = r.get("sentinel_audit_reasons", "")
                if h2186_msg not in existing_reasons:
                    r["sentinel_audit_reasons"] = f"{existing_reasons}; {h2186_msg}" if existing_reasons else h2186_msg

        return rows

    # InvoicePayload model branch
    inv_id = str(payload.docno).strip()
    doc_dt = payload.docdt.isoformat() if hasattr(payload.docdt, "isoformat") else str(payload.docdt).strip()
    sup = payload.supplier
    buy = payload.buyer
    disp = payload.dispdt1
    ship = payload.shipdtl
    exp = payload.expdt1
    val = payload.valdtls
    ewb = payload.ewbdt1

    # Valuation aggregates
    inv_assval = float(val.assval) if val else 0.0
    inv_cgst = float(val.cgstval) if val else 0.0
    inv_sgst = float(val.sgstval) if val else 0.0
    inv_igst = float(val.igstval) if val else 0.0
    inv_ces = float(val.cesval) if val else 0.0
    inv_disc = float(val.discount) if val else 0.0
    inv_rnd = float(val.rndoffamt) if val else 0.0
    inv_tot = float(val.totinvval) if val else 0.0

    # EWB fields
    trans_dist = float(ewb.distance) if ewb else 0.0
    veh_num = str(ewb.veh_number or "") if ewb else ""
    veh_type = str(ewb.veh_type or "R") if ewb else "R"
    trans_id = str(ewb.transporter_id or "") if ewb else ""
    trans_name = str(ewb.transporter_name or "") if ewb else ""
    trans_mode = str(ewb.transmode or "1") if ewb else "1"
    trans_doc_no = str(ewb.transdocno or "") if ewb else ""
    trans_doc_date = str(ewb.transdocdt or "") if ewb else ""
    ewb_req = "Y" if (trans_dist > 0 or inv_tot >= 50000 or (veh_num and veh_num not in ["-", "None", ""])) else "N"

    sup_st = str(getattr(sup, "state", "") or (getattr(sup, "gstin", "")[:2] if getattr(sup, "gstin", None) and len(sup.gstin) >= 2 else "")).strip()
    sup_st = sup_st.zfill(2) if sup_st.isdigit() and len(sup_st) == 1 else sup_st

    buy_pos = str(getattr(buy, "pos", "") or getattr(buy, "state", "") or "").strip()
    buy_pos = buy_pos.zfill(2) if buy_pos.isdigit() and len(buy_pos) == 1 else buy_pos

    buy_st = str(getattr(buy, "state", "") or (getattr(buy, "gstin", "")[:2] if getattr(buy, "gstin", None) and len(buy.gstin) >= 2 else "")).strip()
    buy_st = buy_st.zfill(2) if buy_st.isdigit() and len(buy_st) == 1 else buy_st

    buy_gstin = str(getattr(buy, "gstin", "") or "").strip().upper()
    ship_st = str(getattr(payload.shipdtl, "state", "") or "") if getattr(payload, "shipdtl", None) else ""
    trancatg_m = str(getattr(payload, "trancatg", "B2B") or "B2B").strip().upper()
    raw_cleaned = getattr(payload, "_raw_cleaned", {}) or {}
    reversecharge_m = normalize_reverse_charge(getattr(payload, "reversecharge", getattr(payload, "RevChrg", raw_cleaned.get("reversecharge", "N"))))[0]
    igstonintra_m = str(getattr(payload, "igstonintra", None) or raw_cleaned.get("igstonintra") or "N").strip().upper()
    is_exceptional_intra_m = bool(
        getattr(payload, "is_exceptional_intra", False) or
        getattr(payload, "is_exceptional_intra_igst", False) or
        raw_cleaned.get("is_exceptional_intra") or
        raw_cleaned.get("is_exceptional_intra_igst") or
        igstonintra_m == "Y"
    )
    if is_exceptional_intra_m:
        igstonintra_m = "Y"
        reversecharge_m = "Y"

    dest_state_m = None
    if buy_gstin and buy_gstin != "URP" and len(buy_gstin) >= 2 and buy_gstin[:2].isdigit():
        dest_state_m = buy_gstin[:2]
    # Rule 2200 & Rule 2201 Interception for Dispatch, Shipping, and Export (Model Branch)
    disp_st_m = str(getattr(disp, "state", "") or getattr(disp, "stcd", "") or "").strip()
    disp_gstin_m = str(getattr(disp, "gstin", "") or "").strip().upper()
    disp_pin_m = str(getattr(disp, "pin", "") or "").strip()
    disp_loc_m = str(getattr(disp, "loc", "") or "").strip()
    disp_name_m = str(getattr(disp, "nm", "") or getattr(disp, "trdnm", "") or getattr(disp, "name", "") or "") if disp else ""

    rule_2200_disp_msg_m = None
    if disp and disp_st_m:
        diag_2200_disp_m = classify_rule_2200_diagnostic(stcd=disp_st_m, gstin=disp_gstin_m, pin=disp_pin_m, loc=disp_loc_m, section="DispDtls") if classify_rule_2200_diagnostic else None
        if diag_2200_disp_m and not diag_2200_disp_m["is_valid"]:
            disp_st_m = diag_2200_disp_m["rectified_stcd"]
            rule_2200_disp_msg_m = f"Rule 2200 Violation ({diag_2200_disp_m['scenario_name']}): {diag_2200_disp_m['reason']}"

    ship_st_m = str(getattr(ship, "state", "") or getattr(ship, "stcd", "") or "").strip()
    ship_gstin_m = str(getattr(ship, "gstin", "") or "").strip().upper()
    ship_pin_m = str(getattr(ship, "pin", "") or "").strip()
    ship_loc_m = str(getattr(ship, "loc", "") or "").strip()
    ship_name_m = str(getattr(ship, "lglnm", "") or getattr(ship, "name", "") or "") if ship else ""

    rule_2200_ship_msg_m = None
    if ship and ship_st_m:
        diag_2200_ship_m = classify_rule_2200_diagnostic(stcd=ship_st_m, gstin=ship_gstin_m, pin=ship_pin_m, loc=ship_loc_m, section="ShipDtls") if classify_rule_2200_diagnostic else None
        if diag_2200_ship_m and not diag_2200_ship_m["is_valid"]:
            ship_st_m = diag_2200_ship_m["rectified_stcd"]
            rule_2200_ship_msg_m = f"Rule 2200 Violation ({diag_2200_ship_m['scenario_name']}): {diag_2200_ship_m['reason']}"

    is_exp_tx_m = trancatg_m in ("EXP", "EXPWP", "EXPWOP")
    raw_port_m = str(getattr(exp, "portCode", "") or getattr(exp, "port_code", "") or getattr(exp, "port", "") or "").strip()
    exp_sbno_m = str(getattr(exp, "shipBNo", "") or getattr(exp, "shipping_bill_no", "") or getattr(exp, "shipbno", "") or "") if exp else ""
    exp_sbdt_m = str(getattr(exp, "shipBDt", "") or getattr(exp, "shipping_bill_date", "") or getattr(exp, "shipbdt", "") or "") if exp else ""
    exp_cnt_m = str(getattr(exp, "cntCode", "") or getattr(exp, "country_code", "") or getattr(exp, "cntcode", "") or "") if exp else ""
    exp_port_m = raw_port_m

    rule_2201_msg_m = None
    if raw_port_m or (exp and not is_exp_tx_m):
        diag_2201_m = classify_rule_2201_diagnostic(port=raw_port_m, trancatg=trancatg_m, transmode=trans_mode, is_export=is_exp_tx_m) if classify_rule_2201_diagnostic else None
        if diag_2201_m and not diag_2201_m["is_valid"]:
            if diag_2201_m.get("omit_expdtls"):
                exp_port_m = ""
                exp_sbno_m = ""
                exp_sbdt_m = ""
                exp_cnt_m = ""
            else:
                exp_port_m = diag_2201_m.get("rectified_port") or exp_port_m
            rule_2201_msg_m = f"Rule 2201 Violation ({diag_2201_m['scenario_name']}): {diag_2201_m['reason']}"

    for item in payload.itemdtls:
        slno = str(getattr(item, "slno", "") or getattr(item, "item_slno", "") or "1").strip()
        qty = float(getattr(item, "qty", 0.0) or 0.0)
        uprice = float(getattr(item, "unitprice", 0.0) or getattr(item, "unitrate", 0.0) or 0.0)
        gross = float(getattr(item, "totamt", None) or getattr(item, "grossamt", None) or (qty * uprice))
        disc = float(getattr(item, "discount", 0.0) or getattr(item, "discval", 0.0) or 0.0)
        pretax = float(getattr(item, "pretaxval", None) or (gross - disc))
        assval = float(getattr(item, "assval", 0.0) or getattr(item, "assamt", 0.0) or 0.0)
        gst_rate = float(getattr(item, "gstrate", 0.0) or 0.0)

        # Robust HSN & Sentinel Telemetry Resolution
        item_hsn = str(getattr(item, "hsn", "") or getattr(item, "hsncd", "") or "").strip()
        prod_name = str(getattr(item, "prdnm", "") or getattr(item, "product_name", "") or "").strip()
        prod_desc = str(getattr(item, "prddesc", "") or getattr(item, "product_description", "") or "").strip()
        is_serv = str(getattr(item, "is_service", "N") or getattr(item, "isservc", "N") or "N").strip()

        sentinel_audit = getattr(item, "sentinel_audit", None)
        if not sentinel_audit or not isinstance(sentinel_audit, dict) or not sentinel_audit.get("rectified_hsn"):
            try:
                from Template_Converters.hsn_resolver import audit_and_rectify_line_item_sentinel
                sup_gstin = str(getattr(sup, "gstin", "") or "").strip()
                sentinel_audit = audit_and_rectify_line_item_sentinel(
                    product_name=prod_name,
                    product_desc=prod_desc,
                    declared_hsn=item_hsn,
                    unit_price=uprice,
                    supplier_gstin=sup_gstin
                )
            except Exception:
                sentinel_audit = {}

        rectified_hsn = str((sentinel_audit or {}).get("rectified_hsn") or (sentinel_audit or {}).get("original_hsn") or item_hsn).strip()
        should_rectify = bool((sentinel_audit or {}).get("should_rectify", False))
        risk_level = str((sentinel_audit or {}).get("risk_level", "LOW"))
        status_badge = str((sentinel_audit or {}).get("status_badge", "AUTO_APPROVED"))
        risk_prob = _to_f((sentinel_audit or {}).get("error_probability", 0.0))
        reasons = (sentinel_audit or {}).get("reasons", [])
        audit_reasons_str = "; ".join(str(r) for r in reasons) if isinstance(reasons, list) else str(reasons or "")

        stat_rate = _to_f((sentinel_audit or {}).get("statutory_rate", 0.0))
        if gst_rate == 0.0 and stat_rate > 0.0:
            gst_rate = stat_rate

        final_hsn = (rectified_hsn if (should_rectify and rectified_hsn) else (item_hsn if (item_hsn and len(item_hsn) in [2, 4, 6, 8]) else (rectified_hsn or item_hsn)))

        cgst_amt_m = float(item.cgstval or 0.0)
        sgst_amt_m = float(item.sgstval or 0.0)
        igst_amt_m = float(item.igstval or 0.0)

        # Rule 2192: Item Total Amount Formula Mismatch (TotAmt = Qty * UnitPrice)
        exp_gross_m = round(qty * uprice, 2)
        is_serv_m = (is_serv.upper() == "Y" or final_hsn.startswith("99"))
        if is_serv_m and qty == 0.0 and uprice > 0.0:
            diag_2192_m = classify_rule_2192_diagnostic(
                qty=qty, unitprice=uprice, totamt=gross, discount=disc, is_service="Y", hsn=final_hsn, item_slno=slno
            ) if classify_rule_2192_diagnostic else None
            qty = 1.0
            gross = round(qty * uprice, 2)
            status_badge = "FLAGGED_AND_RECTIFIED"
            risk_level = "HIGH"
            risk_prob = max(risk_prob, 0.95)
            r_scen = diag_2192_m.get("scenario_name", "Services with Null or Missing Qty") if diag_2192_m else "Services with Null or Missing Qty"
            r_reason = diag_2192_m.get("reason", "Even for service lines where quantity is conceptual, set Qty: 1 so that 1 * UnitPrice = TotAmt.") if diag_2192_m else "Even for service lines where quantity is conceptual, set Qty: 1."
            rule_msg = f"Rule 2192 Violation ({r_scen}): {r_reason}"
            audit_reasons_str = f"{audit_reasons_str}; {rule_msg}" if audit_reasons_str else rule_msg
        elif abs(gross - exp_gross_m) > 0.005 and (qty > 0.0 or uprice > 0.0):
            diag_2192_m = classify_rule_2192_diagnostic(
                qty=qty, unitprice=uprice, totamt=gross, discount=disc,
                gstrate=gst_rate,
                taxes=cgst_amt_m + sgst_amt_m + igst_amt_m,
                is_service="Y" if is_serv_m else "N",
                hsn=final_hsn, item_slno=slno
            ) if classify_rule_2192_diagnostic else None
            gross = exp_gross_m
            status_badge = "FLAGGED_AND_RECTIFIED"
            risk_level = "HIGH"
            risk_prob = max(risk_prob, 0.95)
            r_scen = diag_2192_m.get("scenario_name", "Item Total Amount Formula Mismatch") if diag_2192_m else "Item Total Amount Formula Mismatch"
            r_reason = diag_2192_m.get("reason", f"TotAmt must equal Qty * UnitPrice ({exp_gross_m:.2f}).") if diag_2192_m else f"TotAmt must equal Qty * UnitPrice ({exp_gross_m:.2f})."
            rule_msg = f"Rule 2192 Violation ({r_scen}): {r_reason}"
            audit_reasons_str = f"{audit_reasons_str}; {rule_msg}" if audit_reasons_str else rule_msg

        # Rule 2193: Item Assessable Amount Formula Mismatch (AssAmt = TotAmt - Discount)
        exp_assval_m = round(gross - disc, 2)
        if abs(assval - exp_assval_m) > 0.005:
            diag_2193_m = classify_rule_2193_diagnostic(
                totamt=gross, discount=disc, assamt=assval,
                gstrate=gst_rate,
                taxes=cgst_amt_m + sgst_amt_m + igst_amt_m,
                othchrg=float(getattr(item, "othchrg", 0.0) or 0.0),
                item_slno=slno
            ) if classify_rule_2193_diagnostic else None
            assval = exp_assval_m
            status_badge = "FLAGGED_AND_RECTIFIED"
            risk_level = "HIGH"
            risk_prob = max(risk_prob, 0.95)
            r_scen = diag_2193_m.get("scenario_name", "Item Assessable Amount Formula Mismatch") if diag_2193_m else "Item Assessable Amount Formula Mismatch"
            r_reason = diag_2193_m.get("reason", f"AssAmt must equal TotAmt - Discount ({exp_assval_m:.2f}).") if diag_2193_m else f"AssAmt must equal TotAmt - Discount ({exp_assval_m:.2f})."
            rule_msg = f"Rule 2193 Violation ({r_scen}): {r_reason}"
            audit_reasons_str = f"{audit_reasons_str}; {rule_msg}" if audit_reasons_str else rule_msg
        is_export_m = trancatg_m in ("EXP", "EXPWP", "EXPWOP")
        is_sez_m = trancatg_m in ("SEZWP", "SEZWOP")
        is_intra_by_pos_m = (sup_st == buy_pos and not is_export_m and not is_sez_m) if (sup_st and buy_pos) else True
        is_intra_m = (is_intra_by_pos_m and igstonintra_m != "Y")

        # Rule 2174 Inter-State Supply Sentinel Interception & Lakehouse Tax Normalization
        if not is_intra_m and (cgst_amt_m > 0.0 or sgst_amt_m > 0.0):
            diag_2174 = classify_rule_2174_diagnostic(
                seller_state=sup_st,
                buyer_pos=buy_pos,
                buyer_state=buy_st,
                buyer_gstin=buy_gstin,
                ship_state=ship_st,
                cgst_amt=cgst_amt_m,
                sgst_amt=sgst_amt_m,
                igst_amt=igst_amt_m
            ) if classify_rule_2174_diagnostic else None

            rectified_igst_m = round(cgst_amt_m + sgst_amt_m + igst_amt_m, 2)
            cgst_amt_m = 0.0
            sgst_amt_m = 0.0
            igst_amt_m = rectified_igst_m

            status_badge = "FLAGGED_AND_RECTIFIED"
            risk_level = "HIGH"
            risk_prob = max(risk_prob, 0.95)
            scen_name = diag_2174.get("scenario_name", "Standard Inter-State Supply") if diag_2174 else "Standard Inter-State Supply"
            diag_reason = diag_2174.get("reason", "Supplier and POS states are different, so it is an inter-state sale. Clear CGST/SGST to 0.00 and pass the full tax rate under IgstAmt.") if diag_2174 else "Supplier and POS states are different, so it is an inter-state sale. Clear CGST/SGST to 0.00 and pass the full tax rate under IgstAmt."
            rule_msg = f"Rule 2174 Violation ({scen_name}): {diag_reason}"
            audit_reasons_str = f"{audit_reasons_str}; {rule_msg}" if audit_reasons_str else rule_msg

        # Rule 2172 Intra-State Supply Sentinel Interception & Lakehouse Tax Normalization
        elif is_intra_by_pos_m and igst_amt_m > 0.0:
            diag_2172 = classify_rule_2172_diagnostic(
                seller_state=sup_st,
                buyer_pos=buy_pos,
                buyer_state=buy_st,
                buyer_gstin=buy_gstin,
                igst_amt=igst_amt_m,
                cgst_amt=cgst_amt_m,
                sgst_amt=sgst_amt_m,
                igstonintra=igstonintra_m,
                is_exceptional_intra=is_exceptional_intra_m,
                header_igst=inv_igst,
                header_cgst=inv_cgst,
                header_sgst=inv_sgst,
            ) if classify_rule_2172_diagnostic else None

            scen_2172 = diag_2172.get("scenario") if diag_2172 else "STANDARD_INTRA_STATE"
            scen_name = diag_2172.get("scenario_name", "Standard Intra-State Transaction") if diag_2172 else "Standard Intra-State Transaction"
            diag_reason = diag_2172.get("reason", "Same supplier state and POS means regular intra-state supply. Clear IgstAmt and split tax equally between CGST and SGST.") if diag_2172 else "Same supplier state and POS means regular intra-state supply. Clear IgstAmt and split tax equally between CGST and SGST."

            if scen_2172 == "WRONG_POS_ENTERED":
                rectified_pos = str(diag_2172.get("destination_state") or dest_state_m or buy_st).strip().zfill(2)
                buy_pos = rectified_pos
                is_intra_m = False
                is_intra_by_pos_m = False
                cgst_amt_m = 0.0
                sgst_amt_m = 0.0
                rule_msg = f"Rule 2172 Violation ({scen_name}): {diag_reason} (rectified buyer_pos: '{sup_st}' -> '{rectified_pos}')"
            elif scen_2172 == "EXCEPTIONAL_INTRA_STATE_IGST":
                igstonintra_m = "Y"
                reversecharge_m = "Y"
                is_intra_m = False
                cgst_amt_m = 0.0
                sgst_amt_m = 0.0
                rule_msg = f"Rule 2172 Violation ({scen_name}): {diag_reason}"
            else:
                tot_tax_m = round(igst_amt_m + cgst_amt_m + sgst_amt_m, 2)
                half_split_m = round(tot_tax_m / 2.0, 2)
                cgst_amt_m = half_split_m
                sgst_amt_m = round(tot_tax_m - half_split_m, 2)
                igst_amt_m = 0.0
                rule_msg = f"Rule 2172 Violation ({scen_name}): {diag_reason}"

            status_badge = "FLAGGED_AND_RECTIFIED"
            risk_level = "HIGH"
            risk_prob = max(risk_prob, 0.95)
            audit_reasons_str = f"{audit_reasons_str}; {rule_msg}" if audit_reasons_str else rule_msg
        elif assval > 0 and cgst_amt_m == 0.0 and sgst_amt_m == 0.0 and igst_amt_m == 0.0 and gst_rate > 0:
            if not is_intra_m:
                igst_amt_m = round(assval * (gst_rate / 100.0), 2)
            else:
                cgst_amt_m = round(assval * (gst_rate / 200.0), 2)
                sgst_amt_m = round(assval * (gst_rate / 200.0), 2)
        cesval_m = float(getattr(item, "cesval", 0.0) or 0.0)
        cesnonad_m = float(getattr(item, "cesnonadvl", 0.0) or 0.0)
        stcesval_m = float(getattr(item, "statecesval", 0.0) or 0.0)
        stcesnonad_m = float(getattr(item, "statecesnonadvl", 0.0) or 0.0)
        othchrg_m = float(getattr(item, "othchrg", 0.0) or 0.0)

        tot_item_val_m = float(item.totitemval or 0.0)
        exp_totitem_m = round(assval + cgst_amt_m + sgst_amt_m + igst_amt_m + cesval_m + cesnonad_m + stcesval_m + stcesnonad_m + othchrg_m, 2)

        if abs(tot_item_val_m - exp_totitem_m) > 1.00:
            diag_2194_m = classify_rule_2194_diagnostic(
                totitemval=tot_item_val_m,
                assamt=assval,
                cgstamt=cgst_amt_m,
                sgstamt=sgst_amt_m,
                igstamt=igst_amt_m,
                cesamt=cesval_m,
                cesnonadval=cesnonad_m,
                statecesamt=stcesval_m,
                statecesnonadval=stcesnonad_m,
                othchrg=othchrg_m,
                totamt=gross,
                discount=disc,
                item_slno=slno,
                hsn=final_hsn
            ) if classify_rule_2194_diagnostic else None
            tot_item_val_m = exp_totitem_m
            status_badge = "FLAGGED_AND_RECTIFIED"
            risk_level = "HIGH"
            risk_prob = max(risk_prob, 0.95)
            r_scen = diag_2194_m.get("scenario_name", "Total Item Value Formula Mismatch") if diag_2194_m else "Total Item Value Formula Mismatch"
            r_reason = diag_2194_m.get("reason", f"TotItemVal deviates beyond +/- 1.00 tolerance (expected {exp_totitem_m:.2f}).") if diag_2194_m else f"TotItemVal deviates beyond +/- 1.00 tolerance (expected {exp_totitem_m:.2f})."
            rule_msg = f"Rule 2194 Violation ({r_scen}): {r_reason}"
            audit_reasons_str = f"{audit_reasons_str}; {rule_msg}" if audit_reasons_str else rule_msg
        elif tot_item_val_m == 0.0:
            tot_item_val_m = exp_totitem_m

        # Rule 2177 UQC Standardization & Sentinel Interception
        raw_unit_m = str(getattr(item, "unit", "") or getattr(item, "uqc", "") or "NOS").strip()
        norm_unit_m, diag_2177_m = normalize_uqc_statutory(raw_unit_m) if normalize_uqc_statutory else (raw_unit_m, {"is_valid": True})
        if not diag_2177_m["is_valid"]:
            status_badge = "FLAGGED_AND_RECTIFIED"
            risk_level = "HIGH"
            risk_prob = max(risk_prob, 0.95)
            uqc_msg = f"Rule 2177 Violation ({diag_2177_m.get('scenario_name', 'Invalid UQC')}): {diag_2177_m.get('reason', 'UQC not in master')} (original: '{raw_unit_m}', rectified: '{norm_unit_m}')"
            audit_reasons_str = f"{audit_reasons_str}; {uqc_msg}" if audit_reasons_str else uqc_msg

        # Rule 2200 Dispatch & Shipping Telemetry (Model Branch)
        if rule_2200_disp_msg_m:
            status_badge = "FLAGGED_AND_RECTIFIED"
            risk_level = "HIGH"
            risk_prob = max(risk_prob, 0.95)
            audit_reasons_str = f"{audit_reasons_str}; {rule_2200_disp_msg_m}" if audit_reasons_str else rule_2200_disp_msg_m

        if rule_2200_ship_msg_m:
            status_badge = "FLAGGED_AND_RECTIFIED"
            risk_level = "HIGH"
            risk_prob = max(risk_prob, 0.95)
            audit_reasons_str = f"{audit_reasons_str}; {rule_2200_ship_msg_m}" if audit_reasons_str else rule_2200_ship_msg_m

        # Rule 2201 Export Port Telemetry (Model Branch)
        if rule_2201_msg_m:
            status_badge = "FLAGGED_AND_RECTIFIED"
            risk_level = "HIGH"
            risk_prob = max(risk_prob, 0.95)
            audit_reasons_str = f"{audit_reasons_str}; {rule_2201_msg_m}" if audit_reasons_str else rule_2201_msg_m

        rows.append({
            # Document & Transaction Details
            "invoice_id": inv_id,
            "doc_type": str(payload.document_type).strip(),
            "doc_date": doc_dt,
            "transaction_category": str(getattr(payload, "trancatg", "B2B") or "B2B").strip(),
            "reverse_charge": normalize_reverse_charge(getattr(payload, "reversecharge", getattr(payload, "RevChrg", "N")))[0],
            "igst_on_intra": str(getattr(payload, "igstonintra", "N") or "N").strip(),

            # Supplier Details
            "supplier_gstin": str(sup.gstin).strip(),
            "supplier_lglnm": str(sup.lglnm).strip(),
            "supplier_trdnm": str(getattr(sup, "trdnm", "") or "").strip(),
            "supplier_state": str(sup.state).strip(),
            "supplier_pin": str(sup.pin).strip(),
            "supplier_loc": str(getattr(sup, "loc", "") or "").strip(),
            "supplier_phone": str(getattr(sup, "phone", "") or "").strip(),
            "supplier_email": str(getattr(sup, "email", "") or "").strip(),

            # Buyer Details
            "buyer_gstin": str(buy.gstin).strip(),
            "buyer_lglnm": str(buy.lglnm).strip(),
            "buyer_trdnm": str(getattr(buy, "trdnm", "") or "").strip(),
            "buyer_state": str(buy.state).strip(),
            "buyer_pin": str(buy.pin).strip(),
            "buyer_pos": buy_pos,
            "buyer_loc": str(getattr(buy, "loc", "") or "").strip(),
            "buyer_phone": str(getattr(buy, "phone", "") or "").strip(),
            "buyer_email": str(getattr(buy, "email", "") or "").strip(),

            # Dispatch & Shipping
            "dispatch_name": disp_name_m,
            "dispatch_state": disp_st_m,
            "dispatch_pin": disp_pin_m,
            "ship_gstin": ship_gstin_m,
            "ship_name": ship_name_m,
            "ship_state": ship_st_m,
            "ship_pin": ship_pin_m,

            # Export Details
            "export_shipping_bill_no": exp_sbno_m,
            "export_shipping_bill_date": exp_sbdt_m,
            "export_country": exp_cnt_m,
            "export_port": exp_port_m,

            # Line Item Details
            "line_item_id": f"{inv_id}-L{slno.zfill(2)}",
            "item_slno": slno,
            "product_name": prod_name,
            "product_description": prod_desc,
            "is_service": is_serv,
            "hsn": final_hsn,
            "quantity": qty,
            "unit": norm_unit_m,
            "unit_price": uprice,
            "gross_amount": gross,
            "item_discount": disc,
            "pretax_value": pretax,
            "taxable_value": assval,
            "gst_rate": gst_rate,
            "cgst_amount": cgst_amt_m,
            "sgst_amount": sgst_amt_m,
            "igst_amount": igst_amt_m,
            "cess_rate": float(getattr(item, "cesrate", 0.0) or 0.0),
            "cess_amount": float(getattr(item, "cesval", 0.0) or 0.0),
            "state_cess_rate": float(getattr(item, "statecesrate", 0.0) or 0.0),
            "state_cess_amount": float(getattr(item, "statecesval", 0.0) or 0.0),
            "other_charges": float(getattr(item, "othchrg", 0.0) or 0.0),
            "total_item_value": tot_item_val_m,

            # Invoice-Level Valuation Breakdown
            "inv_taxable_value": inv_assval,
            "inv_cgst_amount": 0.0 if not is_intra_m else inv_cgst,
            "inv_sgst_amount": 0.0 if not is_intra_m else inv_sgst,
            "inv_igst_amount": (inv_cgst + inv_sgst + inv_igst) if (not is_intra_m and (inv_cgst > 0 or inv_sgst > 0)) else inv_igst,
            "inv_cess_amount": inv_ces,
            "inv_discount": inv_disc,
            "inv_roundoff": inv_rnd,
            "inv_total_value": inv_tot,

            # Transportation & E-Way Bill Details
            "ewb_required": ewb_req,
            "transporter_id": trans_id,
            "transporter_name": trans_name,
            "transport_mode": trans_mode,
            "transport_doc_no": trans_doc_no,
            "transport_doc_date": trans_doc_date,
            "transit_distance_km": trans_dist,
            "vehicle_number": veh_num,
            "vehicle_type": veh_type,

            # Payment Details
            "payment_mode": str(getattr(payload, "pmtmode", "") or "").strip(),
            "payment_account_no": str(getattr(payload, "upiacctnumber", "") or "").strip(),
            "payment_ifsc": str(getattr(payload, "upiactifsccd", "") or "").strip(),
            "payment_upi": str(getattr(payload, "upiid", "") or "").strip(),

            # Compliance & Status
            "compliance_status": "VALID",

            # Module 2 Sentinel ML Telemetry
            "sentinel_risk_prob": risk_prob,
            "sentinel_risk_level": risk_level,
            "sentinel_status_badge": status_badge,
            "sentinel_recommended_hsn": rectified_hsn or final_hsn,
            "sentinel_audit_reasons": audit_reasons_str
        })

    # Invoice-Level Header Valuation Reconciliation (Rule 2182, Rule 2172 Scenario 4, Rule 2174 Scenario 3, and General Totals)
    sum_line_cgst = round(sum(r["cgst_amount"] for r in rows), 2)
    sum_line_sgst = round(sum(r["sgst_amount"] for r in rows), 2)
    sum_line_igst = round(sum(r["igst_amount"] for r in rows), 2)
    sum_line_assval = round(sum(r["taxable_value"] for r in rows), 2)
    sum_line_totamt = round(sum(r.get("gross_amount", r["taxable_value"]) for r in rows), 2)
    sum_line_disc = round(sum(r.get("item_discount", 0.0) for r in rows), 2)

    header_mismatch_2182 = False
    header_diag_2182 = None
    if abs(inv_assval - sum_line_assval) > 0.005:
        header_mismatch_2182 = True
        if classify_rule_2182_diagnostic:
            header_diag_2182 = classify_rule_2182_diagnostic(
                header_assval=inv_assval,
                sum_item_assamt=sum_line_assval,
                sum_item_totamt=sum_line_totamt,
                header_discount=inv_disc,
                sum_item_discount=sum_line_disc,
                items=[{"AssAmt": r["taxable_value"], "TotAmt": r.get("gross_amount", r["taxable_value"]), "Discount": r.get("item_discount", 0.0)} for r in rows]
            )

    rectified_inv_assval = sum_line_assval

    header_mismatch_2172 = False
    header_diag_2172 = None
    if (sum_line_cgst > 0 or sum_line_sgst > 0) and sum_line_igst == 0.0 and inv_igst > 0.0:
        header_mismatch_2172 = True
        if classify_rule_2172_diagnostic:
            header_diag_2172 = classify_rule_2172_diagnostic(
                seller_state=sup_st,
                buyer_pos=buy_pos,
                buyer_state=buy_st,
                buyer_gstin=buy_gstin,
                igst_amt=sum_line_igst,
                cgst_amt=sum_line_cgst,
                sgst_amt=sum_line_sgst,
                header_igst=inv_igst,
                header_cgst=inv_cgst,
                header_sgst=inv_sgst,
                item_tax_summary={"cgst": sum_line_cgst, "sgst": sum_line_sgst, "igst": sum_line_igst}
            )

    header_mismatch_2183 = False
    header_diag_2183 = None
    is_intra_tx_m = (sup_st == buy_pos and igstonintra_m != "Y" and trancatg_m not in ("EXP", "EXPWP", "EXPWOP", "SEZWP", "SEZWOP"))
    if is_intra_tx_m:
        if abs(inv_sgst - sum_line_sgst) > 0.005:
            header_mismatch_2183 = True
            if classify_rule_2183_diagnostic:
                header_diag_2183 = classify_rule_2183_diagnostic(
                    header_sgst=inv_sgst,
                    sum_item_sgst=sum_line_sgst,
                    items=[{"SgstAmt": r["sgst_amount"], "CgstAmt": r["cgst_amount"]} for r in rows],
                    header_cgst=inv_cgst,
                    sum_item_cgst=sum_line_cgst,
                    is_inter_state=False,
                    seller_state=sup_st,
                    buyer_pos=buy_pos,
                    igst_on_intra=igstonintra_m,
                )
    else:
        if inv_sgst > 0.0 or sum_line_sgst > 0.0:
            header_mismatch_2183 = True
            if classify_rule_2183_diagnostic:
                header_diag_2183 = classify_rule_2183_diagnostic(
                    header_sgst=inv_sgst,
                    sum_item_sgst=sum_line_sgst,
                    items=[{"SgstAmt": r["sgst_amount"], "CgstAmt": r["cgst_amount"]} for r in rows],
                    header_cgst=inv_cgst,
                    sum_item_cgst=sum_line_cgst,
                    is_inter_state=True,
                    seller_state=sup_st,
                    buyer_pos=buy_pos,
                    igst_on_intra=igstonintra_m,
                )

    header_mismatch_2184 = False
    header_diag_2184 = None
    if is_intra_tx_m:
        if abs(inv_cgst - sum_line_cgst) > 0.005:
            header_mismatch_2184 = True
            if classify_rule_2184_diagnostic:
                header_diag_2184 = classify_rule_2184_diagnostic(
                    header_cgst=inv_cgst,
                    sum_item_cgst=sum_line_cgst,
                    items=[{"CgstAmt": r["cgst_amount"], "SgstAmt": r["sgst_amount"]} for r in rows],
                    header_sgst=inv_sgst,
                    sum_item_sgst=sum_line_sgst,
                    is_inter_state=False,
                    seller_state=sup_st,
                    buyer_pos=buy_pos,
                    igst_on_intra=igstonintra_m,
                )
    else:
        if inv_cgst > 0.0 or sum_line_cgst > 0.0:
            header_mismatch_2184 = True
            if classify_rule_2184_diagnostic:
                header_diag_2184 = classify_rule_2184_diagnostic(
                    header_cgst=inv_cgst,
                    sum_item_cgst=sum_line_cgst,
                    items=[{"CgstAmt": r["cgst_amount"], "SgstAmt": r["sgst_amount"]} for r in rows],
                    header_sgst=inv_sgst,
                    sum_item_sgst=sum_line_sgst,
                    is_inter_state=True,
                    seller_state=sup_st,
                    buyer_pos=buy_pos,
                    igst_on_intra=igstonintra_m,
                )

    header_mismatch_2185 = False
    header_diag_2185 = None
    is_std_intra_store_m = (is_intra_tx_m and igstonintra_m != "Y" and trancatg_m not in ("EXP", "EXPWP", "EXPWOP", "SEZWP", "SEZWOP"))
    if is_std_intra_store_m:
        if inv_igst > 0.0 or sum_line_igst > 0.0:
            header_mismatch_2185 = True
            if classify_rule_2185_diagnostic:
                header_diag_2185 = classify_rule_2185_diagnostic(
                    header_igst=inv_igst,
                    sum_item_igst=sum_line_igst,
                    items=[{"IgstAmt": r["igst_amount"], "CgstAmt": r["cgst_amount"], "SgstAmt": r["sgst_amount"]} for r in rows],
                    header_cgst=inv_cgst,
                    sum_item_cgst=sum_line_cgst,
                    header_sgst=inv_sgst,
                    sum_item_sgst=sum_line_sgst,
                    is_inter_state=(not is_intra_tx_m),
                    seller_state=sup_st,
                    buyer_pos=buy_pos,
                    igst_on_intra=igstonintra_m,
                    trancatg=trancatg_m,
                )
    else:
        if abs(inv_igst - sum_line_igst) > 0.005:
            header_mismatch_2185 = True
            if classify_rule_2185_diagnostic:
                header_diag_2185 = classify_rule_2185_diagnostic(
                    header_igst=inv_igst,
                    sum_item_igst=sum_line_igst,
                    items=[{"IgstAmt": r["igst_amount"], "CgstAmt": r["cgst_amount"], "SgstAmt": r["sgst_amount"]} for r in rows],
                    header_cgst=inv_cgst,
                    sum_item_cgst=sum_line_cgst,
                    header_sgst=inv_sgst,
                    sum_item_sgst=sum_line_sgst,
                    is_inter_state=(not is_intra_tx_m),
                    seller_state=sup_st,
                    buyer_pos=buy_pos,
                    igst_on_intra=igstonintra_m,
                    trancatg=trancatg_m,
                )

    header_mismatch_2186 = False
    header_diag_2186 = None
    items_list_m = getattr(payload, "itemdtls", getattr(payload, "items", [])) or []
    val_sec_m = getattr(payload, "valdtls", getattr(payload, "valdetails", None))
    sum_item_cesad_m = round(sum(float(getattr(item, "cesval", 0.0) or 0.0) for item in items_list_m), 2)
    sum_item_cesnonad_m = round(sum(float(getattr(item, "cesnonadval", getattr(item, "cesnonadvl", getattr(item, "cesnonadvlamt", 0.0))) or 0.0) for item in items_list_m), 2)
    sum_item_stces_m = round(sum(float(getattr(item, "statecesval", getattr(item, "statecessamt", getattr(item, "stcesval", 0.0))) or 0.0) for item in items_list_m), 2)
    sum_line_total_cess_m = round(sum_item_cesad_m + sum_item_cesnonad_m, 2)
    if abs(inv_ces - sum_line_total_cess_m) > 0.005:
        header_mismatch_2186 = True
        if classify_rule_2186_diagnostic:
            header_diag_2186 = classify_rule_2186_diagnostic(
                header_cess=inv_ces,
                sum_item_cess=sum_line_total_cess_m,
                items=[{"CesAmt": getattr(itm, "cesval", 0.0), "CesNonAdvlAmt": getattr(itm, "cesnonadval", getattr(itm, "cesnonadvl", getattr(itm, "cesnonadvlamt", 0.0))), "StateCesAmt": getattr(itm, "statecesval", getattr(itm, "statecessamt", getattr(itm, "stcesval", 0.0)))} for itm in items_list_m],
                header_stcess=float(getattr(val_sec_m, "stcesval", 0.0) or 0.0) if val_sec_m else 0.0,
                sum_item_stcess=sum_item_stces_m,
                sum_item_cesad=sum_item_cesad_m,
                sum_item_cesnonad=sum_item_cesnonad_m,
            )

    if sum_line_igst == 0.0 and (sum_line_cgst > 0 or sum_line_sgst > 0):
        rectified_inv_cgst = sum_line_cgst
        rectified_inv_sgst = sum_line_sgst
        rectified_inv_igst = 0.0
    elif sum_line_igst > 0.0 and sum_line_cgst == 0.0 and sum_line_sgst == 0.0:
        rectified_inv_cgst = 0.0
        rectified_inv_sgst = 0.0
        rectified_inv_igst = sum_line_igst
    else:
        rectified_inv_cgst = sum_line_cgst if sum_line_cgst > 0 else inv_cgst
        rectified_inv_sgst = sum_line_sgst if sum_line_sgst > 0 else inv_sgst
        rectified_inv_igst = sum_line_igst if sum_line_igst > 0 else inv_igst

    rectified_inv_ces = sum_line_total_cess_m if header_mismatch_2186 else inv_ces

    for r in rows:
        r["buyer_pos"] = buy_pos
        r["igst_on_intra"] = igstonintra_m
        r["reverse_charge"] = reversecharge_m
        r["inv_taxable_value"] = rectified_inv_assval
        r["inv_cgst_amount"] = rectified_inv_cgst
        r["inv_sgst_amount"] = rectified_inv_sgst
        r["inv_igst_amount"] = rectified_inv_igst
        r["inv_cess_amount"] = rectified_inv_ces

        calc_tot = round(r["inv_taxable_value"] + r["inv_cgst_amount"] + r["inv_sgst_amount"] + r["inv_igst_amount"] + r["inv_cess_amount"] - r["inv_discount"] + r["inv_roundoff"], 2)
        if r["inv_total_value"] == 0.0 or abs(r["inv_total_value"] - calc_tot) > 0.01:
            r["inv_total_value"] = calc_tot

        if header_mismatch_2182:
            r["sentinel_status_badge"] = "FLAGGED_AND_RECTIFIED"
            r["sentinel_risk_level"] = "HIGH"
            r["sentinel_risk_prob"] = max(r.get("sentinel_risk_prob", 0.0), 0.95)
            h2182_scen = header_diag_2182.get("scenario_name", "Header Not Updated After Item Edits") if header_diag_2182 else "Header Not Updated After Item Edits"
            h2182_reason = header_diag_2182.get("reason", "Ensure ValDtls.AssVal dynamically recalculates the sum of all ItemList[i].AssAmt before sending.") if header_diag_2182 else "Ensure ValDtls.AssVal dynamically recalculates the sum of all ItemList[i].AssAmt before sending."
            h2182_msg = f"Rule 2182 Violation ({h2182_scen}): {h2182_reason}"
            existing_reasons = r.get("sentinel_audit_reasons", "")
            if h2182_msg not in existing_reasons:
                r["sentinel_audit_reasons"] = f"{existing_reasons}; {h2182_msg}" if existing_reasons else h2182_msg

        if header_mismatch_2172:
            r["sentinel_status_badge"] = "FLAGGED_AND_RECTIFIED"
            r["sentinel_risk_level"] = "HIGH"
            r["sentinel_risk_prob"] = max(r.get("sentinel_risk_prob", 0.0), 0.95)
            h_scen = header_diag_2172.get("scenario_name", "Summary vs. Item Level Mismatch") if header_diag_2172 else "Summary vs. Item Level Mismatch"
            h_reason = header_diag_2172.get("reason", "Header total tax values in ValDtls must match the sum of item-level taxes in ItemList.") if header_diag_2172 else "Header total tax values in ValDtls must match the sum of item-level taxes in ItemList."
            h_msg = f"Rule 2172 Violation ({h_scen}): {h_reason}"
            existing_reasons = r.get("sentinel_audit_reasons", "")
            if h_msg not in existing_reasons:
                r["sentinel_audit_reasons"] = f"{existing_reasons}; {h_msg}" if existing_reasons else h_msg

        if header_mismatch_2183:
            r["sentinel_status_badge"] = "FLAGGED_AND_RECTIFIED"
            r["sentinel_risk_level"] = "HIGH"
            r["sentinel_risk_prob"] = max(r.get("sentinel_risk_prob", 0.0), 0.95)
            h2183_scen = header_diag_2183.get("scenario_name", "Header Not Recalculated After Item Edits") if header_diag_2183 else "Header Not Recalculated After Item Edits"
            h2183_reason = header_diag_2183.get("reason", "Ensure ValDtls.SgstVal dynamically computes the sum of all ItemList[i].SgstAmt.") if header_diag_2183 else "Ensure ValDtls.SgstVal dynamically computes the sum of all ItemList[i].SgstAmt."
            h2183_msg = f"Rule 2183 Violation ({h2183_scen}): {h2183_reason}"
            existing_reasons = r.get("sentinel_audit_reasons", "")
            if h2183_msg not in existing_reasons:
                r["sentinel_audit_reasons"] = f"{existing_reasons}; {h2183_msg}" if existing_reasons else h2183_msg

        if header_mismatch_2184:
            r["sentinel_status_badge"] = "FLAGGED_AND_RECTIFIED"
            r["sentinel_risk_level"] = "HIGH"
            r["sentinel_risk_prob"] = max(r.get("sentinel_risk_prob", 0.0), 0.95)
            h2184_scen = header_diag_2184.get("scenario_name", "Header Not Recalculated After Item Edits") if header_diag_2184 else "Header Not Recalculated After Item Edits"
            h2184_reason = header_diag_2184.get("reason", "Ensure ValDtls.CgstVal dynamically computes the sum of all ItemList[i].CgstAmt.") if header_diag_2184 else "Ensure ValDtls.CgstVal dynamically computes the sum of all ItemList[i].CgstAmt."
            h2184_msg = f"Rule 2184 Violation ({h2184_scen}): {h2184_reason}"
            existing_reasons = r.get("sentinel_audit_reasons", "")
            if h2184_msg not in existing_reasons:
                r["sentinel_audit_reasons"] = f"{existing_reasons}; {h2184_msg}" if existing_reasons else h2184_msg

        if header_mismatch_2185:
            r["sentinel_status_badge"] = "FLAGGED_AND_RECTIFIED"
            r["sentinel_risk_level"] = "HIGH"
            r["sentinel_risk_prob"] = max(r.get("sentinel_risk_prob", 0.0), 0.95)
            h2185_scen = header_diag_2185.get("scenario_name", "Header Not Recalculated After Item Edits") if header_diag_2185 else "Header Not Recalculated After Item Edits"
            h2185_reason = header_diag_2185.get("reason", "Ensure ValDtls.IgstVal dynamically computes the sum of all ItemList[i].IgstAmt.") if header_diag_2185 else "Ensure ValDtls.IgstVal dynamically computes the sum of all ItemList[i].IgstAmt."
            h2185_msg = f"Rule 2185 Violation ({h2185_scen}): {h2185_reason}"
            existing_reasons = r.get("sentinel_audit_reasons", "")
            if h2185_msg not in existing_reasons:
                r["sentinel_audit_reasons"] = f"{existing_reasons}; {h2185_msg}" if existing_reasons else h2185_msg

        if header_mismatch_2186:
            r["sentinel_status_badge"] = "FLAGGED_AND_RECTIFIED"
            r["sentinel_risk_level"] = "HIGH"
            r["sentinel_risk_prob"] = max(r.get("sentinel_risk_prob", 0.0), 0.95)
            h2186_scen = header_diag_2186.get("scenario_name", "Header Not Recalculated After Item Edits") if header_diag_2186 else "Header Not Recalculated After Item Edits"
            h2186_reason = header_diag_2186.get("reason", "Ensure ValDtls.CesVal dynamically sums both ad-valorem Cess (CesAmt) and non-ad-valorem Cess (CesNonAdvlAmt) across all line items.") if header_diag_2186 else "Ensure ValDtls.CesVal dynamically sums both ad-valorem Cess (CesAmt) and non-ad-valorem Cess (CesNonAdvlAmt) across all line items."
            h2186_msg = f"Rule 2186 Violation ({h2186_scen}): {h2186_reason}"
            existing_reasons = r.get("sentinel_audit_reasons", "")
            if h2186_msg not in existing_reasons:
                r["sentinel_audit_reasons"] = f"{existing_reasons}; {h2186_msg}" if existing_reasons else h2186_msg

    return rows


def write_parquet(
    data: Union[pd.DataFrame, List[Dict[str, Any]]],
    filepath: str,
    schema: Optional[pa.Schema] = None,
    compression: str = "snappy"
) -> bool:
    dirname = os.path.dirname(filepath)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    if isinstance(data, list):
        data = pd.DataFrame(data)
    table = pa.Table.from_pandas(data, schema=schema, preserve_index=False)
    pq.write_table(table, filepath, compression=compression)
    return True


def read_parquet(filepath: str, columns: Optional[List[str]] = None) -> pd.DataFrame:
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Parquet file not found: {filepath}")
    table = pq.read_table(filepath, columns=columns)
    return table.to_pandas()


def append_to_parquet(
    new_data: Union[pd.DataFrame, List[Dict[str, Any]]],
    filepath: str,
    schema: Optional[pa.Schema] = None,
    dedup_cols: Optional[List[str]] = None
) -> bool:
    dirname = os.path.dirname(filepath)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    if isinstance(new_data, list):
        new_data = pd.DataFrame(new_data)
    if new_data is None or new_data.empty:
        return True

    dedup_keys = dedup_cols or ["invoice_id", "item_slno"]

    if not os.path.exists(filepath):
        valid_keys = [k for k in dedup_keys if k in new_data.columns]
        if valid_keys:
            new_data = new_data.drop_duplicates(subset=valid_keys, keep="last")
        if schema is not None:
            for field in schema:
                fname = field.name
                if fname not in new_data.columns:
                    new_data[fname] = 0.0 if pa.types.is_floating(field.type) else ""
                elif pa.types.is_floating(field.type):
                    new_data[fname] = new_data[fname].fillna(0.0)
                elif pa.types.is_string(field.type):
                    new_data[fname] = new_data[fname].fillna("")
        new_table = pa.Table.from_pandas(new_data, schema=schema, preserve_index=False)
        pq.write_table(new_table, filepath, compression="snappy")
        return True

    existing_df = pq.read_table(filepath).to_pandas()
    combined_df = pd.concat([existing_df, new_data], ignore_index=True)

    valid_keys = [k for k in dedup_keys if k in combined_df.columns]
    if valid_keys:
        # Lakehouse Upsert: keep the latest record per (invoice_id, item_slno)
        combined_df = combined_df.drop_duplicates(subset=valid_keys, keep="last")

    if schema is not None:
        for field in schema:
            fname = field.name
            if fname not in combined_df.columns:
                combined_df[fname] = 0.0 if pa.types.is_floating(field.type) else ""
            elif pa.types.is_floating(field.type):
                combined_df[fname] = combined_df[fname].fillna(0.0)
            elif pa.types.is_string(field.type):
                combined_df[fname] = combined_df[fname].fillna("")

    combined_table = pa.Table.from_pandas(combined_df, schema=schema, preserve_index=False)
    pq.write_table(combined_table, filepath, compression="snappy")
    return True


def store_invoice_payload(
    payload: InvoicePayload,
    storage_path: str = DEFAULT_STORAGE_PATH,
    only_validated: bool = True
) -> int:
    # Filter out empty or unvalidated dummy records
    inv_id = getattr(payload, "docno", None)
    if only_validated and (not inv_id or str(inv_id).strip() in ["", "INV-UNKNOWN", "-", "—"]):
        return 0

    flat_rows = flatten_invoice_payload(payload)
    valid_rows = [
        r for r in flat_rows 
        if r.get("invoice_id") and str(r.get("invoice_id")).strip() not in ["", "INV-UNKNOWN", "-", "—"]
    ]
    if not valid_rows:
        return 0

    df_new = pd.DataFrame(valid_rows)
    append_to_parquet(df_new, storage_path, schema=FLATTENED_INVOICE_SCHEMA)
    return len(valid_rows)


def store_invoice_batch(
    payloads: Union[List[Union[InvoicePayload, Dict[str, Any]]], InvoiceBatchPayload],
    storage_path: str = DEFAULT_STORAGE_PATH,
    only_validated: bool = True
) -> int:
    """
    Stores a batch of validated invoices into the master Parquet lakehouse.
    Only validated records with valid invoice IDs are persisted.
    Upserts existing records by (invoice_id, item_slno) to prevent duplication.
    """
    invoices = payloads.einvoices if isinstance(payloads, InvoiceBatchPayload) else payloads
    all_rows: List[Dict[str, Any]] = []

    for p in invoices:
        # Check validation status if only_validated is requested
        if only_validated:
            docno = None
            if isinstance(p, dict):
                docno = p.get("docdt1", {}).get("docno") or p.get("docno")
                if p.get("status") in ["FAILED", "INVALID", "NEEDS_ATTENTION"]:
                    continue
            elif hasattr(p, "docno"):
                docno = p.docno

            if not docno or str(docno).strip() in ["", "INV-UNKNOWN", "-", "—"]:
                continue

        flattened = flatten_invoice_payload(p)
        valid_rows = [
            r for r in flattened 
            if r.get("invoice_id") and str(r.get("invoice_id")).strip() not in ["", "INV-UNKNOWN", "-", "—"]
        ]
        all_rows.extend(valid_rows)

    if not all_rows:
        return 0

    df_new = pd.DataFrame(all_rows)
    append_to_parquet(df_new, storage_path, schema=FLATTENED_INVOICE_SCHEMA)
    return len(all_rows)


def store_processed_json(payload: InvoicePayload, json_path: Optional[str] = None) -> str:
    if json_path is None:
        json_path = os.path.join(DEFAULT_STORAGE_DIR, f"{payload.docno}_processed.json")
    dirname = os.path.dirname(json_path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        f.write(payload.model_dump_json(indent=2))
    return json_path


def store_nic_payload(payload: InvoicePayload, json_path: Optional[str] = None) -> str:
    """Stores the official NIC IRP API nested payload format."""
    import json
    if json_path is None:
        json_path = os.path.join(DEFAULT_STORAGE_DIR, f"{payload.docno}_nic_irp.json")
    dirname = os.path.dirname(json_path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload.to_nic_payload(), f, indent=2)
    return json_path


def store_ewb_payload(payload: InvoicePayload, json_path: Optional[str] = None) -> str:
    """Stores the standalone official NIC E-Way Bill JSON format."""
    import json
    if json_path is None:
        json_path = os.path.join(DEFAULT_STORAGE_DIR, f"{payload.docno}_standalone_ewb.json")
    dirname = os.path.dirname(json_path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload.to_ewb_payload(), f, indent=2)
    return json_path


def export_invoices_to_excel(
    parquet_path: str = DEFAULT_STORAGE_PATH,
    excel_path: str = DEFAULT_EXCEL_PATH,
    invoice_id: Optional[str] = None
) -> str:
    if not os.path.exists(parquet_path):
        raise FileNotFoundError(f"Source parquet file not found at {parquet_path}")

    df = read_parquet(parquet_path)
    if invoice_id:
        df = df[df["invoice_id"] == invoice_id]

    dirname = os.path.dirname(excel_path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Invoices")

    return excel_path


def export_audit_report_csv(validation_report: Dict[str, Any], output_csv_path: str) -> str:
    """
    Exports customer data errors, auto-corrections, and compliance rule violations
    into an Excel-compatible CSV audit trail.
    """
    headers = [
        "Invoice Number",
        "Invoice Status",
        "Type",
        "Category / Error Code",
        "Field / JSON Path",
        "Customer Original Value",
        "System Corrected Value",
        "Description / Rule Reason"
    ]

    dirname = os.path.dirname(output_csv_path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)

    with open(output_csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(headers)

        for res in validation_report.get("results", []):
            inv_no = res.get("invoice_number", "")
            status = res.get("status", "")

            # Corrections
            for c in res.get("corrections_applied", []):
                writer.writerow([
                    inv_no,
                    status,
                    "AUTO_CORRECTION",
                    c.get("category", ""),
                    c.get("field", ""),
                    c.get("original", ""),
                    c.get("corrected", ""),
                    c.get("description", "")
                ])

            # Errors
            for err in res.get("errors", []):
                writer.writerow([
                    inv_no,
                    status,
                    "COMPLIANCE_ERROR",
                    f"Code {err.get('error_code', '')}",
                    err.get("field", ""),
                    "",
                    "",
                    f"{err.get('message', '')} (Reason: {err.get('reason', '')})"
                ])

    return output_csv_path