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
    ("invoice_id", pa.string()),
    ("doc_type", pa.string()),
    ("doc_date", pa.string()),
    ("supplier_gstin", pa.string()),
    ("supplier_lglnm", pa.string()),
    ("supplier_state", pa.string()),
    ("supplier_pin", pa.string()),
    ("buyer_gstin", pa.string()),
    ("buyer_lglnm", pa.string()),
    ("buyer_state", pa.string()),
    ("buyer_pin", pa.string()),
    ("buyer_pos", pa.string()),
    ("line_item_id", pa.string()),
    ("item_slno", pa.string()),
    ("product_name", pa.string()),
    ("product_description", pa.string()),
    ("is_service", pa.string()),
    ("hsn", pa.string()),
    ("quantity", pa.float64()),
    ("unit", pa.string()),
    ("unit_price", pa.float64()),
    ("taxable_value", pa.float64()),
    ("gst_rate", pa.float64()),
    ("cgst_amount", pa.float64()),
    ("sgst_amount", pa.float64()),
    ("igst_amount", pa.float64()),
    ("total_item_value", pa.float64()),
    ("inv_total_value", pa.float64()),
    ("transit_distance_km", pa.float64()),
    ("vehicle_number", pa.string()),
    ("vehicle_type", pa.string())
])


def flatten_invoice_payload(payload: Union[InvoicePayload, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Flattens a validated InvoicePayload model or standardized dictionary into tabular,
    line-item-grain dictionaries conforming to FLATTENED_INVOICE_SCHEMA.
    """
    rows = []
    if isinstance(payload, dict):
        docno = payload.get("docdt1", {}).get("docno") or payload.get("docno") or "INV-UNKNOWN"
        doc_type = payload.get("docdt1", {}).get("document_type") or payload.get("document_type") or "INV"
        doc_dt = str(payload.get("docdt1", {}).get("docdt") or payload.get("docdt") or "")
        sup = payload.get("supplierdt1") or payload.get("supplier") or {}
        buy = payload.get("buyerdt1") or payload.get("buyer") or {}
        ewb = payload.get("ewbdt1") or {}
        val = payload.get("valdt1") or payload.get("valdtls") or {}
        itemdtls = payload.get("itemdtls") or []

        def _to_f(v):
            try:
                return float(str(v).replace(",", ""))
            except Exception:
                return 0.0

        for i, item in enumerate(itemdtls, start=1):
            slno = str(item.get("slno") or i)
            igstrt = _to_f(item.get("igstrt", 0))
            cgstrt = _to_f(item.get("cgstrt", 0))
            sgstrt = _to_f(item.get("sgstrt", 0))
            gst_rate = igstrt if igstrt > 0 else (cgstrt + sgstrt)

            rows.append({
                "invoice_id": docno,
                "doc_type": doc_type,
                "doc_date": doc_dt,
                "supplier_gstin": sup.get("supplier_gstin") or sup.get("gstin") or "",
                "supplier_lglnm": sup.get("supplier_lglnm") or sup.get("lglnm") or "",
                "supplier_state": str(sup.get("supplier_state") or sup.get("state") or ""),
                "supplier_pin": str(sup.get("supplier_pin") or sup.get("pin") or ""),
                "buyer_gstin": buy.get("buyer_gstin") or buy.get("gstin") or "",
                "buyer_lglnm": buy.get("buyer_lglnm") or buy.get("lglnm") or "",
                "buyer_state": str(buy.get("buyer_state") or buy.get("state") or ""),
                "buyer_pin": str(buy.get("buyer_pin") or buy.get("pin") or ""),
                "buyer_pos": str(buy.get("pos") or buy.get("buyer_pos") or buy.get("buyer_state") or buy.get("state") or ""),
                "line_item_id": f"{docno}-L{slno.zfill(2)}",
                "item_slno": slno,
                "product_name": item.get("prdnm") or "",
                "product_description": item.get("prddesc") or "",
                "is_service": item.get("isservc") or item.get("is_service") or "N",
                "hsn": item.get("hsncd") or item.get("hsn") or "",
                "quantity": _to_f(item.get("qty") or 0.0),
                "unit": item.get("uqc") or item.get("unit") or "NOS",
                "unit_price": _to_f(item.get("unitrate") or item.get("unitprice") or 0.0),
                "taxable_value": _to_f(item.get("assamt") or item.get("assval") or 0.0),
                "gst_rate": gst_rate,
                "cgst_amount": _to_f(item.get("cgstamt") or item.get("cgstval") or 0.0),
                "sgst_amount": _to_f(item.get("sgstamt") or item.get("sgstval") or 0.0),
                "igst_amount": _to_f(item.get("igstamt") or item.get("igstval") or 0.0),
                "total_item_value": _to_f(item.get("totitemval") or 0.0),
                "inv_total_value": _to_f(val.get("totinvval") or 0.0),
                "transit_distance_km": _to_f(ewb.get("distance_of_transport") or ewb.get("distance") or 0.0),
                "vehicle_number": str(ewb.get("veh_number") or ""),
                "vehicle_type": str(ewb.get("veh_type") or "R")
            })
        return rows

    # InvoicePayload model branch
    inv_id = payload.docno
    doc_dt = payload.docdt.isoformat() if hasattr(payload.docdt, "isoformat") else str(payload.docdt)
    sup = payload.supplier
    buy = payload.buyer
    ewb = payload.ewbdt1

    for item in payload.itemdtls:
        rows.append({
            "invoice_id": inv_id,
            "doc_type": payload.document_type,
            "doc_date": doc_dt,
            "supplier_gstin": sup.gstin,
            "supplier_lglnm": sup.lglnm,
            "supplier_state": sup.state,
            "supplier_pin": sup.pin,
            "buyer_gstin": buy.gstin,
            "buyer_lglnm": buy.lglnm,
            "buyer_state": buy.state,
            "buyer_pin": buy.pin,
            "buyer_pos": buy.pos or buy.state,
            "line_item_id": f"{inv_id}-L{str(item.slno).zfill(2)}",
            "item_slno": str(item.slno),
            "product_name": item.prdnm,
            "product_description": item.prddesc or "",
            "is_service": item.is_service,
            "hsn": item.hsn,
            "quantity": float(item.qty),
            "unit": item.unit,
            "unit_price": float(item.unitprice),
            "taxable_value": float(item.assval),
            "gst_rate": float(item.gstrate),
            "cgst_amount": float(item.cgstval),
            "sgst_amount": float(item.sgstval),
            "igst_amount": float(item.igstval),
            "total_item_value": float(item.totitemval),
            "inv_total_value": float(payload.valdtls.totinvval) if payload.valdtls else 0.0,
            "transit_distance_km": float(ewb.distance) if ewb else 0.0,
            "vehicle_number": str(ewb.veh_number) if ewb and ewb.veh_number else "",
            "vehicle_type": str(ewb.veh_type) if ewb and ewb.veh_type else "R"
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
    schema: Optional[pa.Schema] = None
) -> None:
    dirname = os.path.dirname(filepath)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    new_table = pa.Table.from_pandas(new_data, schema=schema, preserve_index=False)
    if not os.path.exists(filepath):
        pq.write_table(new_table, filepath, compression="snappy")
        return

    existing_table = pq.read_table(filepath)
    combined = pa.concat_tables([existing_table, new_table])
    pq.write_table(combined, filepath, compression="snappy")


def store_invoice_payload(payload: InvoicePayload, storage_path: str = DEFAULT_STORAGE_PATH) -> int:
    flat_rows = flatten_invoice_payload(payload)
    df_new = pd.DataFrame(flat_rows)
    append_to_parquet(df_new, storage_path, schema=FLATTENED_INVOICE_SCHEMA)
    return len(flat_rows)


def store_invoice_batch(
    payloads: Union[List[InvoicePayload], InvoiceBatchPayload],
    storage_path: str = DEFAULT_STORAGE_PATH
) -> int:
    """
    Stores a batch of validated invoices into the master Parquet lakehouse.
    """
    invoices = payloads.einvoices if isinstance(payloads, InvoiceBatchPayload) else payloads
    all_rows: List[Dict[str, Any]] = []
    for p in invoices:
        all_rows.extend(flatten_invoice_payload(p))
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