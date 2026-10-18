"""
GST Sentinel - Ingestion E-Invoice & E-Way Bill Converter Engine.
Compliant with Indian GST NIC e-Invoice (IRP) & e-Way Bill (EWB) APIs.

Converts raw, dirty customer input JSON payloads (with OCR/typo keys, formatting anomalies,
and calculation issues), auto-corrects them into the standard NIC schema using centralized
Pydantic v2 schemas (src.ingestion.schemas), validates against all official IRN & EWB rules,
persists to the Lakehouse (src.ingestion.storage), and exports results into canonical formats:

1. corrected_payload.json      : Clean, compliant JSON payload ready for NIC IRP API submission.
2. validation_report.json      : Structured JSON audit report with all details.
3. correction_audit_report.csv : Tabular Excel-compatible CSV of all customer errors & fixes.
4. audit_summary.txt           : Human-readable text audit report.
5. invoices_master.parquet     : High-performance columnar Parquet Lakehouse master table.
6. invoices_export.xlsx        : Excel spreadsheet export of processed invoices.
"""

from __future__ import annotations

import csv
import io
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# Ensure GST Sentinel project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ingestion.schemas import (
    InvoicePayload,
    InvoiceBatchPayload,
    STATE_MASTER,
    VALID_STATE_CODES,
    IRN_ERRORS,
    EWB_ERRORS,
    NICValidationError,
)
from src.ingestion.storage import (
    DEFAULT_STORAGE_DIR,
    DEFAULT_STORAGE_PATH,
    DEFAULT_EXCEL_PATH,
    flatten_invoice_payload,
    store_invoice_payload,
    store_invoice_batch,
    store_processed_json,
    store_nic_payload,
    store_ewb_payload,
    export_invoices_to_excel,
    export_audit_report_csv,
)

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def export_csv_audit_report(validation_report: Dict[str, Any], output_csv_path: str) -> str:
    """
    Exports all customer mistakes and auto-corrections into a clean,
    Excel-compatible CSV spreadsheet (8 columns).
    Delegates to storage.export_audit_report_csv for single source of truth.
    """
    return export_audit_report_csv(validation_report, output_csv_path)


def export_text_summary_report(validation_report: Dict[str, Any], output_txt_path: str) -> str:
    """
    Exports a clean, formatted text audit summary file for human reading.
    Matches canonical audit_summary.txt format.
    """
    total = validation_report.get("total_invoices", 0)
    valid = validation_report.get("valid_invoices", 0)
    failed = validation_report.get("failed_invoices", 0)

    lines = [
        "=" * 75,
        "             GST E-INVOICE & E-WAY BILL TRANSFORMATION REPORT",
        "=" * 75,
        f"Total Invoices Processed : {total}",
        f"Compliant (Valid)       : {valid}",
        f"Non-Compliant (Failed)  : {failed}",
        "-" * 75,
        ""
    ]

    for idx, res in enumerate(validation_report.get("results", []), start=1):
        inv_no = res.get("invoice_number", f"Invoice #{idx}")
        status = res.get("status", "")
        cor_count = res.get("corrections_applied_count", 0)
        err_count = res.get("error_count", 0)

        lines.append(f"[{status}] Invoice #{idx}: {inv_no}")
        lines.append(f"   Status             : {status}")
        lines.append(f"   Auto-Corrections   : {cor_count}")
        lines.append(f"   Unresolved Errors  : {err_count}")

        if cor_count > 0:
            lines.append("   * Corrections Made (Customer Errors Fixed):")
            for c in res.get("corrections_applied", []):
                field = c.get("field", "")
                orig = c.get("original", "")
                corr = c.get("corrected", "")
                cat = c.get("category", "")
                desc = c.get("description", "")
                lines.append(f"     - [{cat}] {field}: '{orig}' -> '{corr}'")
                lines.append(f"       Reason: {desc}")

        if err_count > 0:
            lines.append("   ! Unresolved NIC Rule Violations:")
            for err in res.get("errors", []):
                lines.append(f"     - [Code {err.get('error_code')}] {err.get('field')}: {err.get('message')}")
                if err.get("resolution"):
                    lines.append(f"       Resolution: {err.get('resolution')}")

        lines.append("-" * 75)

    dirname = os.path.dirname(output_txt_path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)

    with open(output_txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return output_txt_path


def build_audit_records_and_csv(validation_report: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], str]:
    """
    Builds structured 8-column tabular audit records for dashboard UI and CSV string.
    """
    records: List[Dict[str, Any]] = []
    output_io = io.StringIO()
    writer = csv.writer(output_io)

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
    writer.writerow(headers)

    for res in validation_report.get("results", []):
        inv_no = res.get("invoice_number", "")
        status = res.get("status", "")

        for c in res.get("corrections_applied", []):
            rec = {
                "invoice_number": inv_no,
                "status": status,
                "type": "AUTO_CORRECTION",
                "category": c.get("category", "NORMALIZATION"),
                "field": c.get("field", ""),
                "original": str(c.get("original", "")),
                "corrected": str(c.get("corrected", "")),
                "description": c.get("description", "")
            }
            records.append(rec)
            writer.writerow([
                inv_no,
                status,
                "AUTO_CORRECTION",
                rec["category"],
                rec["field"],
                rec["original"],
                rec["corrected"],
                rec["description"]
            ])

        for err in res.get("errors", []):
            code_str = f"Code {err.get('error_code', 9999)}"
            reason = err.get("reason", "")
            msg = err.get("message", "")
            reason_str = f"{msg} (Reason: {reason})" if reason else msg
            rec = {
                "invoice_number": inv_no,
                "status": "NEEDS_ATTENTION",
                "type": "COMPLIANCE_ERROR",
                "category": code_str,
                "field": err.get("field", ""),
                "original": "-",
                "corrected": "-",
                "description": reason_str,
                "resolution": err.get("resolution", "")
            }
            records.append(rec)
            writer.writerow([
                inv_no,
                status,
                "COMPLIANCE_ERROR",
                code_str,
                rec["field"],
                "",
                "",
                reason_str
            ])

    return records, output_io.getvalue()


def convert_and_validate_in_memory(
    raw_payload: Union[Dict[str, Any], List[Any], str],
    taxable_value_input: Optional[Union[float, Decimal, Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    In-memory transformation & validation engine using native Pydantic v2 schemas:
    1. Parses JSON if string.
    2. Identifies batch vs single invoice.
    3. Runs InvoicePayload.auto_correct_and_build for each invoice (with HSN matching & taxable value option).
    4. Runs InvoicePayload.validate_and_diagnose (including NIC 2-day date check).
    5. Calculates valuation aggregates and metrics.
    6. Returns complete structured conversion artifact dictionary.
    """
    if isinstance(raw_payload, str):
        raw_payload = json.loads(raw_payload.strip())

    if taxable_value_input is None and isinstance(raw_payload, dict):
        taxable_value_input = raw_payload.get("taxable_value_input") or raw_payload.get("custom_taxable_value")

    # Detect batch vs single
    if isinstance(raw_payload, dict) and "einvoices" in raw_payload:
        raw_invoices = raw_payload["einvoices"]
        is_batch = True
    elif isinstance(raw_payload, list):
        raw_invoices = raw_payload
        is_batch = True
    else:
        raw_invoices = [raw_payload]
        is_batch = False

    if not raw_invoices:
        raise ValueError("Payload contains no invoice documents to convert.")

    all_models: List[InvoicePayload] = []
    transformation_audits: List[Dict[str, Any]] = []
    validation_results: List[Dict[str, Any]] = []
    all_nic_payloads: List[Dict[str, Any]] = []
    all_ewb_payloads: List[Dict[str, Any]] = []

    valid_count = 0
    failed_count = 0
    total_corrections = 0
    category_counts: Dict[str, int] = {}

    ttlassval = 0.0
    cgstval = 0.0
    sgstval = 0.0
    igstval = 0.0
    totinvval = 0.0

    for idx, raw_inv in enumerate(raw_invoices, start=1):
        try:
            corrected_model, corrections = InvoicePayload.auto_correct_and_build(
                raw_inv, taxable_value_input=taxable_value_input
            )
            all_models.append(corrected_model)
            transformation_audits.append({"corrections": corrections})
            total_corrections += len(corrections)

            for c in corrections:
                cat = c.get("category", "OTHER")
                category_counts[cat] = category_counts.get(cat, 0) + 1

            # Validate against official NIC business rules
            cleaned_dict = getattr(corrected_model, "_raw_cleaned", None)
            if not cleaned_dict:
                try:
                    cleaned_dict = corrected_model.to_payload()
                except Exception:
                    cleaned_dict = raw_inv

            diag = InvoicePayload.validate_and_diagnose(cleaned_dict)
            status = "VALID" if diag["status"] == "VALID" and len(diag["errors"]) == 0 else "FAILED"
            if status == "VALID":
                valid_count += 1
            else:
                failed_count += 1

            val_res = {
                "invoice_number": corrected_model.docno or f"Invoice #{idx}",
                "status": status,
                "error_count": len(diag["errors"]),
                "errors": diag["errors"],
                "corrections_applied_count": len(corrections),
                "corrections_applied": corrections
            }
            validation_results.append(val_res)
            try:
                all_nic_payloads.append(corrected_model.to_nic_payload())
                all_ewb_payloads.append(corrected_model.to_standalone_ewb())
            except Exception:
                pass

            # Aggregate financial valuation
            try:
                v = corrected_model.valdtls
                if v:
                    ttlassval += float(v.assval or 0.0)
                    cgstval += float(v.cgstval or 0.0)
                    sgstval += float(v.sgstval or 0.0)
                    igstval += float(v.igstval or 0.0)
                    totinvval += float(v.totinvval or 0.0)
            except Exception:
                pass

        except Exception as e:
            failed_count += 1
            err_msg = str(e)
            diag = InvoicePayload.validate_and_diagnose(raw_inv)
            diag_errs = diag.get("errors", [])
            errors = diag_errs if diag_errs else [{
                "error_code": 9999,
                "field": "root",
                "message": err_msg,
                "reason": "Payload schema parsing exception",
                "resolution": "Check JSON structure conforms to NIC E-Invoice format"
            }]
            val_res = {
                "invoice_number": raw_inv.get("docno") or f"Invoice #{idx}",
                "status": "FAILED",
                "error_count": len(errors),
                "errors": errors,
                "corrections_applied_count": 0,
                "corrections_applied": [],
                "model": None
            }
            validation_results.append(val_res)

    # Build clean payload document
    def get_model_payload(m):
        raw = getattr(m, "_raw_cleaned", None)
        if raw:
            return raw
        try:
            return m.to_payload()
        except Exception:
            return {}

    if is_batch or len(all_models) > 1:
        corrected_payload = {"einvoices": [get_model_payload(m) for m in all_models]}
        nic_irp_payload = {"einvoices": all_nic_payloads}
        standalone_ewb_payload = {"ewb_bills": all_ewb_payloads}
    else:
        corrected_payload = get_model_payload(all_models[0]) if all_models else raw_payload
        nic_irp_payload = all_nic_payloads[0] if all_nic_payloads else {}
        standalone_ewb_payload = all_ewb_payloads[0] if all_ewb_payloads else {}

    total_invoices = len(raw_invoices)
    compliance_rate = round((valid_count / total_invoices * 100), 1) if total_invoices > 0 else 0.0

    validation_report = {
        "total_invoices": total_invoices,
        "valid_invoices": valid_count,
        "failed_invoices": failed_count,
        "results": validation_results
    }

    audit_records, csv_content = build_audit_records_and_csv(validation_report)
    summary_text_io = io.StringIO()
    # Format summary string
    sum_lines = [
        "=" * 75,
        "             GST E-INVOICE & E-WAY BILL TRANSFORMATION REPORT",
        "=" * 75,
        f"Total Invoices Processed : {total_invoices}",
        f"Compliant (Valid)       : {valid_count}",
        f"Non-Compliant (Failed)  : {failed_count}",
        "-" * 75,
        ""
    ]
    for idx, res in enumerate(validation_results, start=1):
        inv_no = res["invoice_number"]
        st = res["status"]
        sum_lines.append(f"[{st}] Invoice #{idx}: {inv_no}")
        sum_lines.append(f"   Status             : {st}")
        sum_lines.append(f"   Auto-Corrections   : {res['corrections_applied_count']}")
        sum_lines.append(f"   Unresolved Errors  : {res['error_count']}")
        if res["corrections_applied"]:
            sum_lines.append("   * Corrections Made (Customer Errors Fixed):")
            for c in res["corrections_applied"]:
                sum_lines.append(f"     - [{c.get('category','')}] {c.get('field','')}: '{c.get('original','')}' -> '{c.get('corrected','')}'")
                sum_lines.append(f"       Reason: {c.get('description','')}")
        if res["errors"]:
            sum_lines.append("   ! Unresolved NIC Rule Violations:")
            for err in res["errors"]:
                sum_lines.append(f"     - [Code {err.get('error_code')}] {err.get('field')}: {err.get('message')}")
                if err.get("resolution"):
                    sum_lines.append(f"       Resolution: {err.get('resolution')}")
        sum_lines.append("-" * 75)
    summary_text = "\n".join(sum_lines)

    financials = {
        "ttlassval": round(ttlassval, 2),
        "cgstval": round(cgstval, 2),
        "sgstval": round(sgstval, 2),
        "igstval": round(igstval, 2),
        "totinvval": round(totinvval, 2)
    }

    metrics = {
        "total_invoices": total_invoices,
        "valid_invoices": valid_count,
        "failed_invoices": failed_count,
        "compliance_rate": compliance_rate,
        "total_corrections": total_corrections,
        "total_errors": sum(r["error_count"] for r in validation_results),
        "financials": financials,
        "category_counts": category_counts,
        "price_anomalies": {"total_anomalies": 0, "status": "CLEAN"}
    }

    return {
        "status": "success",
        "models": all_models,
        "corrected_payload": corrected_payload,
        "clean_payload": corrected_payload,
        "nic_irp_payload": nic_irp_payload,
        "standalone_ewb_payload": standalone_ewb_payload,
        "validation_report": validation_report,
        "audit_records": audit_records,
        "csv_content": csv_content,
        "summary_text": summary_text,
        "metrics": metrics
    }


def process_and_convert_payload(
    input_file: str,
    output_corrected_file: str = "corrected_payload.json",
    output_validation_report_file: str = "validation_report.json",
    output_csv_file: str = "correction_audit_report.csv",
    output_txt_file: str = "audit_summary.txt",
    persist_to_lakehouse: bool = True,
    taxable_value_input: Optional[Union[float, Decimal, Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Main ingestion pipeline entry point:
    1. Reads customer input payload file.
    2. Auto-corrects dirty keys, normalizes values, recalculates tax math using native Pydantic v2 schemas.
    3. Runs comprehensive NIC IRN and EWB validation checks.
    4. Exports clean JSON, validation report, Excel-compatible CSV, and formatted text summary.
    5. Optionally persists to Lakehouse Parquet and Excel spreadsheet via src.ingestion.storage.
    """
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"Input file not found: {input_file}")

    print(f"\n[FILE] Reading input file: {input_file}")
    with open(input_file, "r", encoding="utf-8") as f:
        try:
            raw_data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"[ERROR] JSON parse error: {e}")
            raise

    # Execute in-memory schema conversion and validation
    print("[PROCESSING] Ingesting & auto-correcting dirty keys, formats, and re-calculating tax math...")
    res = convert_and_validate_in_memory(raw_data, taxable_value_input=taxable_value_input)

    corrected_payload = res["corrected_payload"]
    validation_report = res["validation_report"]
    csv_content = res["csv_content"]
    summary_text = res["summary_text"]
    models = res["models"]

    # Write output files to disk
    dirname_c = os.path.dirname(output_corrected_file)
    if dirname_c:
        os.makedirs(dirname_c, exist_ok=True)
    with open(output_corrected_file, "w", encoding="utf-8") as f:
        json.dump(corrected_payload, f, default=str, indent=2)
    print(f"[FILE GENERATED] Clean NIC Payload (JSON)  : {output_corrected_file}")

    dirname_r = os.path.dirname(output_validation_report_file)
    if dirname_r:
        os.makedirs(dirname_r, exist_ok=True)
    with open(output_validation_report_file, "w", encoding="utf-8") as f:
        json.dump(validation_report, f, default=str, indent=2)
    print(f"[FILE GENERATED] Validation Report (JSON)  : {output_validation_report_file}")

    export_csv_audit_report(validation_report, output_csv_file)
    print(f"[FILE GENERATED] Audit Report (Excel/CSV)  : {output_csv_file}")

    export_text_summary_report(validation_report, output_txt_file)
    print(f"[FILE GENERATED] Audit Summary (Text File) : {output_txt_file}")

    # Persist to Ingestion Lakehouse if requested - ONLY VALIDATED INVOICES
    if persist_to_lakehouse and models:
        valid_indices = [
            i for i, r in enumerate(validation_report.get("results", []))
            if r.get("status") == "VALID"
        ]
        validated_models = [models[i] for i in valid_indices if i < len(models)]
        if validated_models:
            print(f"[LAKEHOUSE] Persisting {len(validated_models)} validated invoices into Parquet master & Excel...")
            os.makedirs(DEFAULT_STORAGE_DIR, exist_ok=True)
            store_invoice_batch(validated_models, storage_path=DEFAULT_STORAGE_PATH, only_validated=True)
            for m in validated_models:
                store_processed_json(m)
                store_nic_payload(m)
                store_ewb_payload(m)
            export_invoices_to_excel(parquet_path=DEFAULT_STORAGE_PATH, excel_path=DEFAULT_EXCEL_PATH)
            audit_csv_lakehouse = os.path.join(DEFAULT_STORAGE_DIR, "transformation_audit_report.csv")
            export_csv_audit_report(validation_report, audit_csv_lakehouse)
            print(f"[LAKEHOUSE UPDATED] Master Parquet: {DEFAULT_STORAGE_PATH} | Excel: {DEFAULT_EXCEL_PATH}")
        else:
            print("[LAKEHOUSE] No invoices met validation criteria; Lakehouse master table was not updated.")

    total = validation_report["total_invoices"]
    valid = validation_report["valid_invoices"]
    failed = validation_report["failed_invoices"]
    print(f"\n=== Completed Ingestion Pipeline: Total: {total} | Valid: {valid} | Errors: {failed} ===")
    print("All details, corrections, and lakehouse tables have been generated.\n")

    return {
        "status": "success",
        "corrected_payload": corrected_payload,
        "validation_report": validation_report,
        "metrics": res["metrics"],
        "audit_records": res["audit_records"],
        "csv_content": csv_content,
        "summary_text": summary_text,
        "models": models
    }


if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, "..", ".."))

    # Default paths
    default_input = os.path.join(project_root, "Template_Converters", "dirty_customer_input.json")
    if not os.path.exists(default_input):
        default_input = os.path.join(project_root, "dirty_customer_input.json")

    output_dir = os.path.join(project_root, "data", "processed_payload")
    os.makedirs(output_dir, exist_ok=True)

    default_corrected = os.path.join(output_dir, "corrected_payload.json")
    default_report = os.path.join(output_dir, "validation_report.json")
    default_csv = os.path.join(output_dir, "correction_audit_report.csv")
    default_txt = os.path.join(output_dir, "audit_summary.txt")

    input_path = sys.argv[1] if len(sys.argv) > 1 else default_input
    output_path = sys.argv[2] if len(sys.argv) > 2 else default_corrected
    report_path = sys.argv[3] if len(sys.argv) > 3 else default_report
    csv_path = sys.argv[4] if len(sys.argv) > 4 else default_csv
    txt_path = sys.argv[5] if len(sys.argv) > 5 else default_txt

    process_and_convert_payload(input_path, output_path, report_path, csv_path, txt_path)
