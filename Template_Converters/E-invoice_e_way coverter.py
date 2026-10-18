"""
E-Invoice & E-Way Bill Converter and Validation Engine.
Indian GST Compliance (NIC e-Invoice & e-Way Bill APIs).

Converts raw, dirty customer input JSON payloads (with OCR/typo keys, formatting anomalies,
and calculation issues), auto-corrects them into the standard NIC schema, validates against
all official IRN & EWB rules, and exports results into multiple human & machine file formats:

1. corrected_payload.json      : Clean, compliant JSON payload ready for NIC IRP API submission.
2. validation_report.json      : Structured JSON audit report with all details.
3. correction_audit_report.csv : Tabular Excel-compatible CSV of all customer errors & fixes.
4. audit_summary.txt           : Human-readable text audit report.
"""

import sys
import os
import json
import csv
from typing import Dict, Any

try:
    from .error_mappings import IRN_ERRORS, EWB_ERRORS
    from .payload_builder import PayloadBuilder
    from .validator import GSTValidator
except ImportError:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    from error_mappings import IRN_ERRORS, EWB_ERRORS
    from payload_builder import PayloadBuilder
    from validator import GSTValidator

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def export_csv_audit_report(validation_report: Dict[str, Any], output_csv_path: str):
    """
    Exports all customer mistakes and auto-corrections into a clean,
    Excel-compatible CSV spreadsheet.
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

    with open(output_csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(headers)

        for res in validation_report.get("results", []):
            inv_no = res.get("invoice_number", "")
            status = res.get("status", "")

            # 1. Write all auto-corrections applied
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

            # 2. Write any remaining compliance errors
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


def export_text_summary_report(validation_report: Dict[str, Any], output_txt_path: str):
    """
    Exports a clean, formatted text audit summary file for human reading.
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

    with open(output_txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def process_and_convert_payload(
    input_file: str,
    output_corrected_file: str = "corrected_payload.json",
    output_validation_report_file: str = "validation_report.json",
    output_csv_file: str = "correction_audit_report.csv",
    output_txt_file: str = "audit_summary.txt",
    taxable_value_input: Optional[Union[float, Decimal, Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Main pipeline entry point:
    1. Reads customer input payload file.
    2. Auto-corrects dirty keys, normalizes values, matches HSN from Final_hsn_sac_copy.xlsx,
       applies statutory tax rates, recalculates tax math (supporting user taxable value option),
       and builds an exhaustive transformation audit trail.
    3. Runs comprehensive NIC IRN and EWB validation checks (including the 2-day IRN rule).
    4. Exports clean JSON, validation report, Excel-compatible CSV, and formatted text summary.
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

    # Step 1: Auto-correct and build clean payload + transformation audit trail
    print("[PROCESSING] Normalizing dirty keys, formats, matching HSN, and re-calculating tax math...")
    corrected_payload, transformation_audits = PayloadBuilder.convert_payload_document_with_audit(
        raw_data, taxable_value_input=taxable_value_input
    )

    # Step 2: Validate against official NIC business rules
    print("[VALIDATING] Checking against official NIC IRN & EWB compliance rules...")
    validation_report = GSTValidator.validate_payload_document(corrected_payload)

    # Step 3: Merge Transformation Audit Log into Validation Report
    for idx, res in enumerate(validation_report["results"]):
        audit = transformation_audits[idx] if idx < len(transformation_audits) else {}
        corrections = audit.get("corrections", [])
        res["corrections_applied_count"] = len(corrections)
        res["corrections_applied"] = corrections

    # Step 4: Write Outputs in all file formats
    with open(output_corrected_file, "w", encoding="utf-8") as f:
        json.dump(corrected_payload, f, indent=2)
    print(f"[FILE GENERATED] Clean NIC Payload (JSON)  : {output_corrected_file}")

    with open(output_validation_report_file, "w", encoding="utf-8") as f:
        json.dump(validation_report, f, indent=2)
    print(f"[FILE GENERATED] Validation Report (JSON)  : {output_validation_report_file}")

    export_csv_audit_report(validation_report, output_csv_file)
    print(f"[FILE GENERATED] Audit Report (Excel/CSV)  : {output_csv_file}")

    export_text_summary_report(validation_report, output_txt_file)
    print(f"[FILE GENERATED] Audit Summary (Text File) : {output_txt_file}")

    # Step 5: Clean High-Level Terminal Status
    total = validation_report["total_invoices"]
    valid = validation_report["valid_invoices"]
    failed = validation_report["failed_invoices"]
    print(f"\n=== Completed Pipeline: Total: {total} | Valid: {valid} | Errors: {failed} ===")
    print(f"All details and corrections have been logged to the generated files above.\n")

    return {
        "corrected_payload": corrected_payload,
        "validation_report": validation_report
    }


if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    default_input = os.path.join(current_dir, "dirty_customer_input.json")
    default_corrected = os.path.join(current_dir, "corrected_payload.json")
    default_report = os.path.join(current_dir, "validation_report.json")
    default_csv = os.path.join(current_dir, "correction_audit_report.csv")
    default_txt = os.path.join(current_dir, "audit_summary.txt")

    if not os.path.exists(default_input):
        from generate_sample_dirty_input import generate_dirty_input_file
        generate_dirty_input_file(default_input)

    input_path = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else default_input
    output_path = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else default_corrected
    report_path = sys.argv[3] if len(sys.argv) > 3 and not sys.argv[3].startswith("--") else default_report
    csv_path = sys.argv[4] if len(sys.argv) > 4 and not sys.argv[4].startswith("--") else default_csv
    txt_path = sys.argv[5] if len(sys.argv) > 5 and not sys.argv[5].startswith("--") else default_txt

    cli_tax_input = None
    for arg in sys.argv[1:]:
        if arg.startswith("--taxable-value="):
            try:
                cli_tax_input = float(arg.split("=")[1])
            except ValueError:
                pass
    if cli_tax_input is None and len(sys.argv) > 6:
        try:
            cli_tax_input = float(sys.argv[6])
        except ValueError:
            pass

    process_and_convert_payload(
        input_path, output_path, report_path, csv_path, txt_path, taxable_value_input=cli_tax_input
    )