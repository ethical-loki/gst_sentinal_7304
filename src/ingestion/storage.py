import csv
import os
from typing import List, Dict, Any, Optional, Union
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from src.ingestion.schemas import InvoicePayload, InvoiceBatchPayload

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

        trandt = payload.get("trandt1") or payload.get("transaction") or {}
        trancatg = str(trandt.get("trancatg") or payload.get("trancatg") or "B2B").strip()
        reversecharge = str(trandt.get("reversecharge") or payload.get("reversecharge") or "N").strip()
        igstonintra = str(trandt.get("igstonintra") or payload.get("igstonintra") or "N").strip()

        sup = payload.get("supplierdt1") or payload.get("supplier") or {}
        buy = payload.get("buyerdt1") or payload.get("buyer") or {}
        disp = payload.get("dispdt1") or payload.get("dispatch") or {}
        ship = payload.get("shipdtl") or payload.get("shipping") or {}
        exp = payload.get("expdt1") or payload.get("export") or {}
        val = payload.get("valdt1") or payload.get("valdtls") or {}
        ewb = payload.get("ewbdt1") or payload.get("ewaybill") or {}
        pay = payload.get("paydtls") or payload.get("payment") or {}
        itemdtls = payload.get("itemdtls") or []

        # Invoice-level financial totals
        inv_assval = _to_f(val.get("assval") or val.get("ttlassval") or 0.0)
        inv_cgst = _to_f(val.get("cgstval") or 0.0)
        inv_sgst = _to_f(val.get("sgstval") or 0.0)
        inv_igst = _to_f(val.get("igstval") or 0.0)
        inv_ces = _to_f(val.get("cesval") or 0.0)
        inv_disc = _to_f(val.get("discount") or val.get("discval") or 0.0)
        inv_rnd = _to_f(val.get("rndoffamt") or 0.0)
        inv_tot = _to_f(val.get("totinvval") or 0.0)

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

            final_hsn = rectified_hsn if (rectified_hsn and (should_rectify or not item_hsn or len(item_hsn) not in [6, 8])) else item_hsn

            cgst_amt = _to_f(item.get("cgstamt") or item.get("cgstval") or 0.0)
            sgst_amt = _to_f(item.get("sgstamt") or item.get("sgstval") or 0.0)
            igst_amt = _to_f(item.get("igstamt") or item.get("igstval") or 0.0)
            if assval > 0 and cgst_amt == 0.0 and sgst_amt == 0.0 and igst_amt == 0.0 and gst_rate > 0:
                sup_st = str(sup.get("supplier_state") or sup.get("state") or "").strip()
                buy_pos = str(buy.get("pos") or buy.get("buyer_pos") or buy.get("buyer_state") or buy.get("state") or "").strip()
                if sup_st and buy_pos and sup_st != buy_pos:
                    igst_amt = round(assval * (gst_rate / 100.0), 2)
                else:
                    cgst_amt = round(assval * (gst_rate / 200.0), 2)
                    sgst_amt = round(assval * (gst_rate / 200.0), 2)
            tot_line_val = _to_f(item.get("totitemval") or 0.0)
            if tot_line_val == 0.0 or abs(tot_line_val - assval) < 0.01:
                tot_line_val = round(assval + cgst_amt + sgst_amt + igst_amt + _to_f(item.get("cesval") or item.get("cessamt") or 0.0), 2)

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
                "buyer_pos": str(buy.get("pos") or buy.get("buyer_pos") or buy.get("buyer_state") or buy.get("state") or "").strip(),
                "buyer_loc": str(buy.get("buyer_loc") or buy.get("loc") or "").strip(),
                "buyer_phone": str(buy.get("buyer_phone") or buy.get("phone") or "").strip(),
                "buyer_email": str(buy.get("buyer_email") or buy.get("email") or "").strip(),

                # Dispatch & Shipping
                "dispatch_name": str(disp.get("nm") or disp.get("dispatch_name") or "").strip(),
                "dispatch_state": str(disp.get("state") or disp.get("dispatch_state") or "").strip(),
                "dispatch_pin": str(disp.get("pin") or disp.get("dispatch_pin") or "").strip(),
                "ship_gstin": str(ship.get("gstin") or ship.get("ship_gstin") or "").strip(),
                "ship_name": str(ship.get("lglnm") or ship.get("ship_name") or "").strip(),
                "ship_state": str(ship.get("state") or ship.get("ship_state") or "").strip(),
                "ship_pin": str(ship.get("pin") or ship.get("ship_pin") or "").strip(),

                # Export Details
                "export_shipping_bill_no": str(exp.get("shipBNo") or exp.get("shipping_bill_no") or "").strip(),
                "export_shipping_bill_date": str(exp.get("shipBDt") or exp.get("shipping_bill_date") or "").strip(),
                "export_country": str(exp.get("cntCode") or exp.get("country_code") or "").strip(),
                "export_port": str(exp.get("portCode") or exp.get("port_code") or "").strip(),

                # Line Item Details
                "line_item_id": f"{docno}-L{slno.zfill(2)}",
                "item_slno": slno,
                "product_name": prod_name,
                "product_description": prod_desc,
                "is_service": str(item.get("isservc") or item.get("is_service") or "N").strip(),
                "hsn": final_hsn,
                "quantity": qty,
                "unit": str(item.get("uqc") or item.get("unit") or "NOS").strip(),
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
                "inv_cgst_amount": inv_cgst,
                "inv_sgst_amount": inv_sgst,
                "inv_igst_amount": inv_igst,
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

    for item in payload.itemdtls:
        slno = str(item.slno).strip()
        qty = float(item.qty)
        uprice = float(item.unitprice)
        gross = float(item.totamt) if hasattr(item, "totamt") and item.totamt else (qty * uprice)
        disc = float(item.discount) if hasattr(item, "discount") and item.discount else 0.0
        pretax = float(item.pretaxval) if hasattr(item, "pretaxval") and item.pretaxval else (gross - disc)
        assval = float(item.assval)
        gst_rate = float(item.gstrate)

        # Robust HSN & Sentinel Telemetry Resolution
        item_hsn = str(item.hsn).strip()
        prod_name = str(item.prdnm).strip()
        prod_desc = str(item.prddesc or "").strip()

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

        final_hsn = rectified_hsn if (rectified_hsn and (should_rectify or not item_hsn or len(item_hsn) not in [6, 8])) else item_hsn

        cgst_amt_m = float(item.cgstval or 0.0)
        sgst_amt_m = float(item.sgstval or 0.0)
        igst_amt_m = float(item.igstval or 0.0)
        if assval > 0 and cgst_amt_m == 0.0 and sgst_amt_m == 0.0 and igst_amt_m == 0.0 and gst_rate > 0:
            sup_st = str(sup.state or "").strip()
            buy_pos = str(buy.pos or buy.state or "").strip()
            if sup_st and buy_pos and sup_st != buy_pos:
                igst_amt_m = round(assval * (gst_rate / 100.0), 2)
            else:
                cgst_amt_m = round(assval * (gst_rate / 200.0), 2)
                sgst_amt_m = round(assval * (gst_rate / 200.0), 2)
        tot_item_val_m = float(item.totitemval or 0.0)
        if tot_item_val_m == 0.0 or abs(tot_item_val_m - assval) < 0.01:
            tot_item_val_m = round(assval + cgst_amt_m + sgst_amt_m + igst_amt_m, 2)

        rows.append({
            # Document & Transaction Details
            "invoice_id": inv_id,
            "doc_type": str(payload.document_type).strip(),
            "doc_date": doc_dt,
            "transaction_category": str(getattr(payload, "trancatg", "B2B") or "B2B").strip(),
            "reverse_charge": str(getattr(payload, "reversecharge", "N") or "N").strip(),
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
            "buyer_pos": str(buy.pos or buy.state).strip(),
            "buyer_loc": str(getattr(buy, "loc", "") or "").strip(),
            "buyer_phone": str(getattr(buy, "phone", "") or "").strip(),
            "buyer_email": str(getattr(buy, "email", "") or "").strip(),

            # Dispatch & Shipping
            "dispatch_name": str(getattr(disp, "nm", "") or getattr(disp, "name", "") or "") if disp else "",
            "dispatch_state": str(getattr(disp, "state", "") or "") if disp else "",
            "dispatch_pin": str(getattr(disp, "pin", "") or "") if disp else "",
            "ship_gstin": str(getattr(ship, "gstin", "") or "") if ship else "",
            "ship_name": str(getattr(ship, "lglnm", "") or getattr(ship, "name", "") or "") if ship else "",
            "ship_state": str(getattr(ship, "state", "") or "") if ship else "",
            "ship_pin": str(getattr(ship, "pin", "") or "") if ship else "",

            # Export Details
            "export_shipping_bill_no": str(getattr(exp, "shipBNo", "") or getattr(exp, "shipping_bill_no", "") or "") if exp else "",
            "export_shipping_bill_date": str(getattr(exp, "shipBDt", "") or getattr(exp, "shipping_bill_date", "") or "") if exp else "",
            "export_country": str(getattr(exp, "cntCode", "") or getattr(exp, "country_code", "") or "") if exp else "",
            "export_port": str(getattr(exp, "portCode", "") or getattr(exp, "port_code", "") or "") if exp else "",

            # Line Item Details
            "line_item_id": f"{inv_id}-L{slno.zfill(2)}",
            "item_slno": slno,
            "product_name": prod_name,
            "product_description": prod_desc,
            "is_service": str(item.is_service).strip(),
            "hsn": final_hsn,
            "quantity": qty,
            "unit": str(item.unit).strip(),
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
            "inv_cgst_amount": inv_cgst,
            "inv_sgst_amount": inv_sgst,
            "inv_igst_amount": inv_igst,
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
    return rows


def write_parquet(
    data: pd.DataFrame,
    filepath: str,
    schema: Optional[pa.Schema] = None,
    compression: str = "snappy"
) -> None:
    dirname = os.path.dirname(filepath)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    table = pa.Table.from_pandas(data, schema=schema, preserve_index=False)
    pq.write_table(table, filepath, compression=compression)


def read_parquet(filepath: str, columns: Optional[List[str]] = None) -> pd.DataFrame:
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Parquet file not found: {filepath}")
    table = pq.read_table(filepath, columns=columns)
    return table.to_pandas()


def append_to_parquet(
    new_data: pd.DataFrame,
    filepath: str,
    schema: Optional[pa.Schema] = None,
    dedup_cols: Optional[List[str]] = None
) -> None:
    dirname = os.path.dirname(filepath)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    if new_data is None or new_data.empty:
        return

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
        return

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