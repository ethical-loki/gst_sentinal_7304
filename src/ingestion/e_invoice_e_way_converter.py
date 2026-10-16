"""
E-Invoice & E-Way Bill Converter and Validation Engine (Ingestion Module Replica).
Exact 1-to-1 equivalent of Template_Converters/E-invoice_e_way coverter.py,
powered natively by src.ingestion.schemas and src.ingestion.storage.
"""

import sys
import os

# Delegate directly to src.ingestion.converter
from src.ingestion.converter import (
    process_and_convert_payload,
    convert_and_validate_in_memory,
    export_csv_audit_report,
    export_text_summary_report,
    build_audit_records_and_csv,
)

if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, "..", ".."))

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
