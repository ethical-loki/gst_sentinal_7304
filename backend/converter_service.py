"""
Converter Service for GST Sentinel.
Integrates Template_Converters engine with FastAPI backend and web dashboards.
Handles dynamic dirty payload generation, schema transformation, auto-correction,
NIC compliance rule validation, tabular audit report generation, and file exports.
"""

import os
import sys
import json
import csv
import io
from pathlib import Path
from typing import Dict, Any, List, Union, Tuple

# Ensure Template_Converters directory is on sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_CONVERTERS_DIR = BASE_DIR / "Template_Converters"

if str(TEMPLATE_CONVERTERS_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATE_CONVERTERS_DIR))

try:
    from payload_builder import PayloadBuilder
    from validator import GSTValidator
    from generate_sample_dirty_input import generate_dynamic_dirty_payload
except ImportError as e:
    raise ImportError(f"Failed to import Template_Converters modules: {e}")


def load_default_sample_dirty() -> Dict[str, Any]:
    """Loads default dirty customer input sample from Template_Converters or project root."""
    sample_paths = [
        TEMPLATE_CONVERTERS_DIR / "dirty_customer_input.json",
        BASE_DIR / "dirty_customer_input.json"
    ]
    for p in sample_paths:
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    # If not found on disk, generate a fresh dynamic batch
    return generate_dynamic_dirty_payload(count=2)


def generate_random_dirty(count: int = 1) -> Dict[str, Any]:
    """Generates randomized dirty input payload with clean keys and realistic dirty field values."""
    clamped_count = max(1, min(10, int(count)))
    return generate_dynamic_dirty_payload(count=clamped_count)


def build_csv_audit_text(validation_report: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], str]:
    """
    Builds tabular audit records array and formatted CSV string.
    Matches export_csv_audit_report structure from E-invoice_e_way converter.
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

        # 1. Auto-corrections
        for c in res.get("corrections_applied", []):
            rec = {
                "invoice_number": inv_no,
                "status": status,
                "type": "AUTO_CORRECTION",
                "category": c.get("category", ""),
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

        # 2. Compliance errors
        for err in res.get("errors", []):
            code_str = f"Code {err.get('error_code', '')}"
            reason_str = f"{err.get('message', '')} (Reason: {err.get('reason', '')})"
            rec = {
                "invoice_number": inv_no,
                "status": status,
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


def build_text_summary(validation_report: Dict[str, Any]) -> str:
    """
    Builds clean, human-readable text audit summary matching audit_summary.txt format.
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

    return "\n".join(lines)


def calculate_financial_aggregates(corrected_payload: Dict[str, Any]) -> Dict[str, float]:
    """Calculates cumulative tax and invoice valuation aggregates across all invoices."""
    ttlassval = 0.0
    cgstval = 0.0
    sgstval = 0.0
    igstval = 0.0
    totinvval = 0.0

    for inv in corrected_payload.get("einvoices", []):
        val = inv.get("valdt1", {})
        try:
            ttlassval += float(str(val.get("ttlassval", 0)).replace(",", ""))
        except (ValueError, TypeError):
            pass
        try:
            cgstval += float(str(val.get("cgstval", 0)).replace(",", ""))
        except (ValueError, TypeError):
            pass
        try:
            sgstval += float(str(val.get("sgstval", 0)).replace(",", ""))
        except (ValueError, TypeError):
            pass
        try:
            igstval += float(str(val.get("igstval", 0)).replace(",", ""))
        except (ValueError, TypeError):
            pass
        try:
            totinvval += float(str(val.get("totinvval", 0)).replace(",", ""))
        except (ValueError, TypeError):
            pass

    return {
        "ttlassval": round(ttlassval, 2),
        "cgstval": round(cgstval, 2),
        "sgstval": round(sgstval, 2),
        "igstval": round(igstval, 2),
        "totinvval": round(totinvval, 2)
    }


def process_converter_pipeline(raw_data: Union[Dict[str, Any], List[Any], str], sync_to_disk: bool = True) -> Dict[str, Any]:
    """
    Executes the full Template Converter & NIC Validation pipeline:
    1. Parse raw data if string.
    2. PayloadBuilder auto-corrects dirty keys & formats, builds audit trail.
    3. GSTValidator validates NIC IRN & EWB rules.
    4. Merges audits into validation report.
    5. Builds CSV report, text summary, and financial KPI metrics.
    6. Optionally updates disk files in Template_Converters directory.
    """
    # Parse JSON if string
    if isinstance(raw_data, str):
        raw_data = json.loads(raw_data.strip())

    if not isinstance(raw_data, (dict, list)):
        raise ValueError("Invalid payload input: Expected JSON Object or Array.")

    # 1. Auto-correct & build clean payload + audit log
    corrected_payload, transformation_audits = PayloadBuilder.convert_payload_document_with_audit(raw_data)

    # 2. Validate against NIC business rules
    validation_report = GSTValidator.validate_payload_document(corrected_payload)

    # 3. Merge transformation audit log into validation report
    total_corrections_count = 0
    category_counts: Dict[str, int] = {}

    for idx, res in enumerate(validation_report.get("results", [])):
        audit = transformation_audits[idx] if idx < len(transformation_audits) else {}
        corrections = audit.get("corrections", [])
        res["corrections_applied_count"] = len(corrections)
        res["corrections_applied"] = corrections
        total_corrections_count += len(corrections)

        for c in corrections:
            cat = c.get("category", "OTHER")
            category_counts[cat] = category_counts.get(cat, 0) + 1

    # 4. Generate Tabular CSV Records and Text Summary
    audit_records, csv_content = build_csv_audit_text(validation_report)
    summary_text = build_text_summary(validation_report)

    # 5. Financial aggregates
    financials = calculate_financial_aggregates(corrected_payload)

    # 6. Synchronize output files to disk for file exports and CLI parity
    if sync_to_disk:
        try:
            with open(TEMPLATE_CONVERTERS_DIR / "corrected_payload.json", "w", encoding="utf-8") as f:
                json.dump(corrected_payload, f, indent=2)
            with open(TEMPLATE_CONVERTERS_DIR / "validation_report.json", "w", encoding="utf-8") as f:
                json.dump(validation_report, f, indent=2)
            with open(TEMPLATE_CONVERTERS_DIR / "correction_audit_report.csv", "w", encoding="utf-8-sig") as f:
                f.write(csv_content)
            with open(TEMPLATE_CONVERTERS_DIR / "audit_summary.txt", "w", encoding="utf-8") as f:
                f.write(summary_text)
        except Exception as e:
            print(f"[WARN] Failed to write output files to Template_Converters: {e}")

    total_invoices = validation_report.get("total_invoices", 0)
    valid_invoices = validation_report.get("valid_invoices", 0)
    failed_invoices = validation_report.get("failed_invoices", 0)
    compliance_rate = round((valid_invoices / total_invoices * 100), 1) if total_invoices > 0 else 0.0

    return {
        "status": "success",
        "metrics": {
            "total_invoices": total_invoices,
            "valid_invoices": valid_invoices,
            "failed_invoices": failed_invoices,
            "compliance_rate": compliance_rate,
            "total_corrections": total_corrections_count,
            "total_errors": sum(r.get("error_count", 0) for r in validation_report.get("results", [])),
            "financials": financials,
            "category_counts": category_counts
        },
        "corrected_payload": corrected_payload,
        "validation_report": validation_report,
        "audit_records": audit_records,
        "csv_content": csv_content,
        "summary_text": summary_text
    }
