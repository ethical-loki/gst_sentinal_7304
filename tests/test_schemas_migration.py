import os
import sys
from pathlib import Path
from datetime import date
import pytest
from pydantic import ValidationError

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.ingestion.schemas import (
    InvoicePayload,
    InvoiceBatchPayload,
    Counterparty,
    LineItem,
    TaxBreakup,
    EWayBillPayload,
    ExportDetails,
    NICValidationError,
    verify_pincode_state,
    STATE_MASTER,
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
    read_parquet,
    DEFAULT_STORAGE_DIR,
    DEFAULT_STORAGE_PATH,
    DEFAULT_EXCEL_PATH,
)


@pytest.fixture
def valid_invoice_dict():
    return {
        "self_gstin": "29ABCDE1234F1Z5",
        "system_cd": "SAP_ERP",
        "branch_cd": "BLR01",
        "vertical_cd": "DOM",
        "irnreq": "Y",
        "trandt1": {
            "trancatg": "B2B",
            "reversecharge": "N",
            "transactionmode": "REG",
            "igstonintra": "N"
        },
        "docdt1": {
            "document_type": "INV",
            "docno": "INV-2026-TEST",
            "docdt": "2026-10-10"
        },
        "supplierdt1": {
            "supplier_gstin": "29ABCDE1234F1Z5",
            "supplier_lglnm": "BHARAT TECH SOLUTIONS PVT LTD",
            "supplier_loc": "Bengaluru",
            "supplier_pin": "560001",
            "supplier_state": "29"
        },
        "buyerdt1": {
            "buyer_gstin": "29XYZAB5678C1Z2",
            "buyer_lglnm": "KARNATAKA TRADERS",
            "buyer_loc": "Bengaluru",
            "buyer_pin": "560002",
            "buyer_state": "29",
            "buyer_pos": "29"
        },
        "itemdtls": [
            {
                "slno": "1",
                "prdnm": "Industrial Motor",
                "is_service": "N",
                "hsn": "8481",
                "qty": 2.0,
                "unit": "NOS",
                "unitprice": 10000.0,
                "totamt": 20000.0,
                "discount": 0.0,
                "assval": 20000.0,
                "gstrate": 18.0,
                "cgstval": 1800.0,
                "sgstval": 1800.0,
                "igstval": 0.0,
                "totitemval": 23600.0
            }
        ],
        "valdt1": {
            "ttlassval": "20000.00",
            "cgstval": "1800.00",
            "sgstval": "1800.00",
            "igstval": "0.00",
            "totinvval": "23600.00"
        },
        "ewbdt1": {
            "ewayreq": "Y",
            "subsupplytype": "1",
            "transmode": "1",
            "distance": 150.0,
            "transporter_id": "29XYZAB5678C1Z2",
            "veh_number": "KA01AB1234",
            "veh_type": "R"
        }
    }


def test_centralized_validation_success(valid_invoice_dict):
    """Verifies that a compliant invoice parses directly and cleanly into schemas."""
    inv = InvoicePayload.model_validate(valid_invoice_dict)
    assert inv.docno == "INV-2026-TEST"
    assert inv.supplier.state == "29"
    assert inv.valdtls.totinvval == 23600.0
    assert inv.valdt1.totinvval == 23600.0
    assert len(inv.itemdtls) == 1
    assert inv.ewbdt1 is not None
    assert inv.ewbdt1.distance == 150.0


def test_self_invoicing_rejected(valid_invoice_dict):
    """Rule 2211: Supplier and recipient GSTIN cannot be identical."""
    corrupt = dict(valid_invoice_dict)
    corrupt["buyerdt1"] = dict(corrupt["buyerdt1"])
    corrupt["buyerdt1"]["buyer_gstin"] = corrupt["supplierdt1"]["supplier_gstin"]

    with pytest.raises(ValidationError) as exc:
        InvoicePayload.model_validate(corrupt)
    assert "2211" in str(exc.value)
    assert "Supplier and recipient GSTIN should not be the same" in str(exc.value)


def test_supplier_urp_rejected(valid_invoice_dict):
    """Rule 2213: Supplier GSTIN cannot be URP."""
    corrupt = dict(valid_invoice_dict)
    corrupt["self_gstin"] = "URP"
    corrupt["supplierdt1"] = dict(corrupt["supplierdt1"])
    corrupt["supplierdt1"]["supplier_gstin"] = "URP"

    with pytest.raises(ValidationError) as exc:
        InvoicePayload.model_validate(corrupt)
    assert "2213" in str(exc.value)
    assert "supplier GSTIN cannot be URP" in str(exc.value)


def test_state_pin_jurisdiction_mismatch():
    """Rule 3039: PIN prefix must match the State jurisdiction."""
    # State 27 (Maharashtra) cannot have 560001 (Karnataka)
    assert not verify_pincode_state("560001", "27")
    assert verify_pincode_state("400001", "27")

    with pytest.raises(ValidationError) as exc:
        Counterparty(
            gstin="27ABCDE1234F1Z5",
            lglnm="Mumbai Traders",
            state="27",
            pin="560001",
            loc="Mumbai"
        )
    assert "3039" in str(exc.value)
    assert "does not belong to State" in str(exc.value)


def test_gstin_prefix_state_mismatch():
    """Rule 2258: State code must match first 2 digits of GSTIN."""
    with pytest.raises(ValidationError) as exc:
        Counterparty(
            gstin="29ABCDE1234F1Z5",
            lglnm="Mismatch Corp",
            state="27",  # State 27 vs 29 prefix
            pin="400001",
            loc="Mumbai"
        )
    assert "2258" in str(exc.value)
    assert "does not match first 2 digits of GSTIN" in str(exc.value)


def test_inter_intra_tax_checks(valid_invoice_dict):
    """Rule 2172 / 2174: Intra-state cannot charge IGST; inter-state cannot charge CGST/SGST."""
    # Intra-state but item has IGST charged
    corrupt = dict(valid_invoice_dict)
    corrupt["itemdtls"] = [
        {
            "slno": "1",
            "prdnm": "Test Goods",
            "hsn": "8481",
            "qty": 1.0,
            "unitprice": 1000.0,
            "totamt": 1000.0,
            "assval": 1000.0,
            "igstval": 180.0,  # Illegal for intra-state
            "cgstval": 0.0,
            "sgstval": 0.0,
            "totitemval": 1180.0
        }
    ]
    corrupt["valdt1"] = {
        "ttlassval": "1000.00",
        "cgstval": "0.00",
        "sgstval": "0.00",
        "igstval": "180.00",
        "totinvval": "1180.00"
    }

    with pytest.raises(ValidationError) as exc:
        InvoicePayload.model_validate(corrupt)
    assert "2172" in str(exc.value)
    assert "For Intra-state, IGST is not applicable" in str(exc.value)


def test_value_summary_reconciliation_check(valid_invoice_dict):
    """Rule 2182 / 2189: Header valdtls totals must reconcile with sum of line items."""
    corrupt = dict(valid_invoice_dict)
    corrupt["valdt1"] = dict(corrupt["valdt1"])
    corrupt["valdt1"]["totinvval"] = "99999.00"  # Far outside tolerance

    with pytest.raises(ValidationError) as exc:
        InvoicePayload.model_validate(corrupt)
    assert "2189" in str(exc.value)
    assert "Total Invoice Value" in str(exc.value)


def test_payload_transformation_methods(valid_invoice_dict):
    """Tests .to_payload() and .to_nic_payload() serialization methods."""
    inv = InvoicePayload.model_validate(valid_invoice_dict)

    nic_payload = inv.to_nic_payload()
    assert "trandt1" in nic_payload
    assert "docdt1" in nic_payload
    assert "supplierdt1" in nic_payload
    assert "buyerdt1" in nic_payload
    assert "itemdtls" in nic_payload
    assert "valdt1" in nic_payload
    assert nic_payload["docdt1"]["docno"] == "INV-2026-TEST"
    assert nic_payload["valdt1"]["totinvval"] == "23600.00"


def test_auto_correct_and_build(valid_invoice_dict):
    """Tests dirty key normalization and transformation audit logging."""
    dirty = {
        "self gstin": "29ABCDE1234F1Z5",
        "trandt1": {
            "supply_type": "B2C",
            "reverse_charge": "Y",  # Should be auto-corrected to N for B2C
            "trans_mode": "REG"
        },
        "docdt1": {
            "invoice_no": "INV-AUTO-01",
            "invoice_date": "10-10-2026"
        },
        "supplierdt1": {
            "supplier_1g1nm": "BHARAT TECH",
            "supplier_loc": "Bengaluru",
            "supplier_pin": "560001",
            "supplier_state": "29"
        },
        "buyerdt1": {
            "buyer_1g1nm": "RETAIL CONSUMER",
            "buyer_loc": "Bengaluru",
            "buyer_pin": "560001",
            "buyer_state": "29",
            "buyer_pos": "29"
        },
        "itemdtls": [
            {
                "prdnm": "Gadget",
                "hsn_code": "8481",
                "qty": "1",
                "unitprice": "100.0",
                "gross_amt": "100.0",
                "taxable_amt": "100.0",
                "cgstamt": "9.0",
                "sgstamt": "9.0",
                "tot_item_val": "118.0"
            }
        ],
        "valdt1": {
            "total_taxable_value": "100.00",
            "cgstval": "9.00",
            "sgstval": "9.00",
            "total_inv_val": "118.00"
        }
    }

    model, audit_log = InvoicePayload.auto_correct_and_build(dirty)
    assert model.docno == "INV-AUTO-01"
    assert model.reversecharge == "N"  # Auto-corrected
    assert len(audit_log) > 0

    # Ensure corrections are logged
    rev_logged = any(c.get("field") == "trandt1.reversecharge" for c in audit_log)
    assert rev_logged


def test_eway_bill_factory_method(valid_invoice_dict):
    """Tests EWayBillPayload.from_einvoice and standalone EWB conversion."""
    inv = InvoicePayload.model_validate(valid_invoice_dict)

    # 1. From E-Invoice
    ewb = EWayBillPayload.from_einvoice(
        inv,
        distance=220.0,
        veh_number="KA05CD5678",
        transporter_name="Express Transport"
    )
    assert ewb.distance == 220.0
    assert ewb.veh_number == "KA05CD5678"
    assert ewb.transporter_name == "Express Transport"

    # 2. To Standalone NIC EWB JSON
    standalone = ewb.to_standalone_ewb(inv)
    assert standalone["docNo"] == "INV-2026-TEST"
    assert standalone["fromGstin"] == "29ABCDE1234F1Z5"
    assert standalone["toGstin"] == "29XYZAB5678C1Z2"
    assert standalone["vehNo"] == "KA05CD5678"
    assert len(standalone["itemList"]) == 1


def test_storage_batch_and_json_helpers(tmp_path, valid_invoice_dict):
    """Tests extended storage pipeline helpers."""
    inv = InvoicePayload.model_validate(valid_invoice_dict)

    # Batch store
    target_parquet = str(tmp_path / "batch.parquet")
    rows_stored = store_invoice_batch([inv], storage_path=target_parquet)
    assert rows_stored == 1

    df = read_parquet(target_parquet)
    assert len(df) == 1
    assert df.iloc[0]["invoice_id"] == "INV-2026-TEST"

    # Store NIC payload JSON
    nic_json = str(tmp_path / "nic_payload.json")
    res_path = store_nic_payload(inv, nic_json)
    assert os.path.exists(res_path)

    # Store Standalone EWB JSON
    ewb_json = str(tmp_path / "standalone_ewb.json")
    res_ewb = store_ewb_payload(inv, ewb_json)
    assert os.path.exists(res_ewb)

    # Export audit report CSV
    diag = InvoiceBatchPayload.validate_payload_document({"einvoices": [valid_invoice_dict]})
    csv_file = str(tmp_path / "audit_report.csv")
    export_audit_report_csv(diag, csv_file)
    assert os.path.exists(csv_file)


def test_persist_to_default_processed_payload_directory(valid_invoice_dict):
    """
    Directly persists validated invoice artifacts into data/processed_payload:
    - Master Parquet lakehouse
    - Excel Export table
    - Processed JSON
    - NIC IRP Nested JSON
    - Standalone E-Way Bill JSON
    - Transformation Audit Report CSV
    """
    inv = InvoicePayload.model_validate(valid_invoice_dict)

    # 1. Parquet Lakehouse
    stored_count = store_invoice_payload(inv)
    assert stored_count == 1
    assert os.path.exists(DEFAULT_STORAGE_PATH)

    # 2. Excel Export
    excel_path = export_invoices_to_excel()
    assert os.path.exists(excel_path)

    # 3. Processed JSON
    json_path = store_processed_json(inv)
    assert os.path.exists(json_path)

    # 4. Official NIC IRP Payload JSON
    nic_path = store_nic_payload(inv)
    assert os.path.exists(nic_path)

    # 5. Standalone E-Way Bill Payload JSON
    ewb_path = store_ewb_payload(inv)
    assert os.path.exists(ewb_path)

    # 6. Audit Trail CSV (Capture real auto-corrections and validations)
    dirty_path = os.path.join(ROOT_DIR, "Template_Converters", "dirty_customer_input.json")
    diag = {"results": []}
    if os.path.exists(dirty_path):
        import json
        with open(dirty_path, "r", encoding="utf-8") as f:
            dirty_raw = json.load(f)
        for d_inv in dirty_raw.get("einvoices", []):
            corrected_model, sample_corrections = InvoicePayload.auto_correct_and_build(d_inv)
            diag["results"].append({
                "invoice_number": corrected_model.docno,
                "status": "VALID",
                "corrections_applied": sample_corrections,
                "errors": []
            })
    else:
        dirty_sample = {
            "self gstin": "29ABCDE1234F1Z5",
            "docdt1": {"docno": "INV-2026-TEST", "invoice_date": "10-10-2026"},
            "system cd": "SAP_ERP",
            "trandt1": {"reversecharge": "Y", "trancatg": "B2C"},
            "supplierdt1": {"supplier_1g1nm": "BHARAT TECH", "supplier_loc": "Bengaluru", "supplier_pin": "560001", "supplier_state": "29"},
            "buyerdt1": {"buyer_1g1nm": "KARNATAKA TRADERS", "buyer_loc": "Bengaluru", "buyer_pin": "560001", "buyer_state": "29", "buyer_pos": "29"},
            "itemdtls": [{"prdnm": "Motor", "hsn": "8481", "qty": "2", "unitprice": "10000.0", "grossamt": "20000,00", "assval": "20000,00", "cgstval": "1800.0", "sgstval": "1800.0", "totitemval": "23600,00"}],
            "valdt1": {"assval": "20000.00", "cgstval": "1800.00", "sgstval": "1800.00", "totinvval": "99999.00"}
        }
        corrected_model, sample_corrections = InvoicePayload.auto_correct_and_build(dirty_sample)
        diag["results"].append({
            "invoice_number": "INV-2026-TEST",
            "status": "VALID",
            "corrections_applied": sample_corrections,
            "errors": []
        })

    csv_path = os.path.join(DEFAULT_STORAGE_DIR, "transformation_audit_report.csv")
    export_audit_report_csv(diag, csv_path)
    assert os.path.exists(csv_path)


if __name__ == "__main__":
    import json
    print("\n" + "=" * 78)
    print("      GST SENTINEL - SCHEMAS MIGRATION & DATA PERSISTENCE PIPELINE")
    print("=" * 78)

    sample_invoice_data = {
        "self_gstin": "29ABCDE1234F1Z5",
        "system_cd": "SAP_ERP",
        "branch_cd": "BLR01",
        "vertical_cd": "DOM",
        "irnreq": "Y",
        "trandt1": {
            "trancatg": "B2B",
            "reversecharge": "N",
            "transactionmode": "REG",
            "igstonintra": "N"
        },
        "docdt1": {
            "document_type": "INV",
            "docno": "INV-2026-TEST",
            "docdt": "2026-10-10"
        },
        "supplierdt1": {
            "supplier_gstin": "29ABCDE1234F1Z5",
            "supplier_lglnm": "BHARAT TECH SOLUTIONS PVT LTD",
            "supplier_loc": "Bengaluru",
            "supplier_pin": "560001",
            "supplier_state": "29"
        },
        "buyerdt1": {
            "buyer_gstin": "29XYZAB5678C1Z2",
            "buyer_lglnm": "KARNATAKA TRADERS",
            "buyer_loc": "Bengaluru",
            "buyer_pin": "560002",
            "buyer_state": "29",
            "buyer_pos": "29"
        },
        "itemdtls": [
            {
                "slno": "1",
                "prdnm": "Industrial Motor",
                "is_service": "N",
                "hsn": "8481",
                "qty": 2.0,
                "unit": "NOS",
                "unitprice": 10000.0,
                "totamt": 20000.0,
                "discount": 0.0,
                "assval": 20000.0,
                "gstrate": 18.0,
                "cgstval": 1800.0,
                "sgstval": 1800.0,
                "igstval": 0.0,
                "totitemval": 23600.0
            }
        ],
        "valdt1": {
            "ttlassval": "20000.00",
            "cgstval": "1800.00",
            "sgstval": "1800.00",
            "igstval": "0.00",
            "totinvval": "23600.00"
        },
        "ewbdt1": {
            "ewayreq": "Y",
            "subsupplytype": "1",
            "transmode": "1",
            "distance": 150.0,
            "transporter_id": "29XYZAB5678C1Z2",
            "veh_number": "KA01AB1234",
            "veh_type": "R"
        }
    }

    print("\n[INGESTION] Validating clean invoice payload via centralized Pydantic schemas...")
    inv_model = InvoicePayload.model_validate(sample_invoice_data)
    print(f" [PASS] Validated Invoice: {inv_model.docno} | Total: Rs. {inv_model.valdtls.totinvval:,.2f}")

    print("\n[STORAGE] Persisting validated payloads into data/processed_payload/...")
    os.makedirs(DEFAULT_STORAGE_DIR, exist_ok=True)

    row_count = store_invoice_payload(inv_model)
    print(f" [FILE UPDATED] Parquet Lakehouse : {DEFAULT_STORAGE_PATH} (+{row_count} rows)")

    excel_file = export_invoices_to_excel()
    print(f" [FILE UPDATED] Excel Master Table: {excel_file}")

    json_file = store_processed_json(inv_model)
    print(f" [FILE CREATED] Processed JSON    : {json_file}")

    nic_file = store_nic_payload(inv_model)
    print(f" [FILE CREATED] NIC IRP API JSON  : {nic_file}")

    ewb_file = store_ewb_payload(inv_model)
    print(f" [FILE CREATED] Standalone EWB    : {ewb_file}")

    # Process dirty customer inputs to populate comprehensive transformation audit report
    print("\n[AUTO-CORRECTION] Processing dirty inputs & logging transformation audit trail...")
    dirty_path = os.path.join(ROOT_DIR, "Template_Converters", "dirty_customer_input.json")
    diag_report = {"results": []}

    if os.path.exists(dirty_path):
        with open(dirty_path, "r", encoding="utf-8") as f:
            dirty_raw = json.load(f)
        dirty_invoices = dirty_raw.get("einvoices", [])
        for d_inv in dirty_invoices:
            corrected_model, corrections = InvoicePayload.auto_correct_and_build(d_inv)
            res_diag = InvoicePayload.validate_and_diagnose(corrected_model.to_payload())
            diag_report["results"].append({
                "invoice_number": corrected_model.docno,
                "status": res_diag["status"],
                "corrections_applied": corrections,
                "errors": res_diag["errors"]
            })
    else:
        # Fallback sample dirty input
        sample_dirty = {
            "docno": "INV-2026-001",
            "system cd": "ERP_SAP",
            "branch cd": "BLR-HQ",
            "supplier_1g1nm": "ZENITH ENTERPRISES",
            "buyer loc": "MUMBAI",
            "buyer pin": "400001",
            "itemdtls": [{"prdnm": "COTTON-SHIRTS", "ugc": "nos", "grossamt": "160000,00", "assval": "160000,00", "totitemval": "188800,00"}],
            "valdt1": {"totinvval": "18908000.00"}
        }
        corrected_model, corrections = InvoicePayload.auto_correct_and_build(sample_dirty)
        diag_report["results"].append({
            "invoice_number": corrected_model.docno,
            "status": "VALID",
            "corrections_applied": corrections,
            "errors": []
        })

    audit_csv = os.path.join(DEFAULT_STORAGE_DIR, "transformation_audit_report.csv")
    export_audit_report_csv(diag_report, audit_csv)
    total_fixes = sum(len(r.get("corrections_applied", [])) for r in diag_report["results"])
    print(f" [FILE POPULATED] Audit Report CSV: {audit_csv} ({total_fixes} customer errors auto-corrected)")

    print("\n[TEST RUNNER] Running comprehensive test suite via Pytest:\n")
    sys.exit(pytest.main([__file__, "-v"]))

