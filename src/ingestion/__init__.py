"""
GST Sentinel - Ingestion Package.
Provides centralized Pydantic v2 schemas, Lakehouse Parquet/Excel storage,
and E-Invoice & E-Way Bill transformation, auto-correction, and conversion pipelines.
"""

from src.ingestion.schemas import (
    InvoicePayload,
    InvoiceBatchPayload,
    Counterparty,
    LineItem,
    TaxBreakup,
    EWayBillPayload,
    ExportDetails,
    AuditReceipt,
    NICValidationError,
    STATE_MASTER,
    VALID_STATE_CODES,
    COUNTRY_MASTER,
    ALLOWED_UQC,
    IRN_ERRORS,
    EWB_ERRORS,
)
from src.ingestion.storage import (
    flatten_invoice_payload,
    store_invoice_payload,
    store_invoice_batch,
    store_processed_json,
    store_nic_payload,
    store_ewb_payload,
    export_invoices_to_excel,
    export_audit_report_csv,
    write_parquet,
    read_parquet,
    append_to_parquet,
    DEFAULT_STORAGE_DIR,
    DEFAULT_STORAGE_PATH,
    DEFAULT_EXCEL_PATH,
    FLATTENED_INVOICE_SCHEMA,
)
from src.ingestion.converter import (
    process_and_convert_payload,
    convert_and_validate_in_memory,
    export_csv_audit_report,
    export_text_summary_report,
    build_audit_records_and_csv,
)
from src.ingestion.generate_sample_dirty_input import (
    generate_dynamic_dirty_payload,
    generate_random_invoice,
    generate_comprehensive_dirty_payload,
    load_default_sample_dirty,
)

__all__ = [
    # Schemas
    "InvoicePayload",
    "InvoiceBatchPayload",
    "Counterparty",
    "LineItem",
    "TaxBreakup",
    "EWayBillPayload",
    "ExportDetails",
    "AuditReceipt",
    "NICValidationError",
    "STATE_MASTER",
    "VALID_STATE_CODES",
    "COUNTRY_MASTER",
    "ALLOWED_UQC",
    "IRN_ERRORS",
    "EWB_ERRORS",
    # Storage
    "flatten_invoice_payload",
    "store_invoice_payload",
    "store_invoice_batch",
    "store_processed_json",
    "store_nic_payload",
    "store_ewb_payload",
    "export_invoices_to_excel",
    "export_audit_report_csv",
    "write_parquet",
    "read_parquet",
    "append_to_parquet",
    "DEFAULT_STORAGE_DIR",
    "DEFAULT_STORAGE_PATH",
    "DEFAULT_EXCEL_PATH",
    "FLATTENED_INVOICE_SCHEMA",
    # Converter
    "process_and_convert_payload",
    "convert_and_validate_in_memory",
    "export_csv_audit_report",
    "export_text_summary_report",
    "build_audit_records_and_csv",
    # Generator
    "generate_dynamic_dirty_payload",
    "generate_random_invoice",
    "generate_comprehensive_dirty_payload",
    "load_default_sample_dirty",
]
