import os
# Ensure OpenBLAS and OpenMP thread pools do not exhaust memory on Windows
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")

import sys
import json
from pathlib import Path
import pytest
import pandas as pd
from datetime import date
from pydantic import ValidationError

# Ensure project root is in sys.path when running script directly
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.ingestion.schemas import (
    InvoicePayload,
    Counterparty,
    LineItem,
    TaxBreakup,
    EWayBillPayload,
    AuditReceipt
)
from src.ingestion.storage import (
    flatten_invoice_payload,
    write_parquet,
    read_parquet,
    append_to_parquet,
    store_invoice_payload,
    store_processed_json,
    export_invoices_to_excel,
    DEFAULT_STORAGE_DIR,
    DEFAULT_STORAGE_PATH,
    DEFAULT_EXCEL_PATH,
    FLATTENED_INVOICE_SCHEMA
)


@pytest.fixture
def sample_raw_invoice_dict():
    return {
        "self_gstin": "29ABCDE1234F1Z5",
        "system_cd": "SAP_ERP",
        "branch_cd": "BLR01",
        "vertical_cd": "DOM",
        "irnreq": "Y",
        "trandt1": {
            "trancatg": "B2B",
            "reversecharge": "N",
            "transactionmode": "REGULAR_TRANSIT",
            "igstonintra": "N"
        },
        "docdt1": {
            "document_type": "INV",
            "docno": "INV-2026-B2B",
            "docdt": "2026-10-10"
        },
        "supplierdt1": {
            "supplier_gstin": "29ABCDE1234F1Z5",
            "supplier_lglnm": "  BHARAT TECH SOLUTIONS PVT LTD  ",
            "supplier_trdnm": "BHARAT TECH",
            "supplier_bno": "104",
            "supplier_bnm": "Cyber Towers",
            "supplier_flno": "4th Floor",
            "supplier_loc": "Bengaluru",
            "supplier_dst": "Bengaluru",
            "supplier_pin": "560001",
            "supplier_state": "29",
            "supplier_phone": "9876543210",
            "supplier_email": "accounts@bharattech.in"
        },
        "buyerdt1": {
            "buyer_gstin": "29XYZAB5678C1Z2",
            "buyer_lglnm": "APEX COMMERCE ENTERPRISES",
            "buyer_trdnm": "APEX COMMERCE",
            "buyer_pos": "29",
            "buyer_bno": "55",
            "buyer_bnm": "MG Road Commercial Plaza",
            "buyer_loc": "Bengaluru",
            "buyer_dst": "Bengaluru",
            "buyer_pin": "560001",
            "buyer_state": "29"
        },
        "itemdtls": [
            {
                "slno": "1",
                "prdnm": "Industrial Servo Motor",
                "prddesc": "High torque servo motor for automation line",
                "is_service": "N",
                "hsn": "8481",
                "qty": 5,
                "unit": "NOS",
                "unitprice": 10000.0,
                "totamt": 50000.0,
                "discount": 0.0,
                "pretaxval": 50000.0,
                "assval": 50000.0,
                "gstrate": 18.0,
                "igstval": 0.0,
                "cgstval": 4500.0,
                "sgstval": 4500.0,
                "totitemval": 59000.0
            }
        ],
        "valdtls": {
            "assval": 50000.0,
            "cgstval": 4500.0,
            "sgstval": 4500.0,
            "igstval": 0.0,
            "totinvval": 59000.0
        },
        "ewbdt1": {
            "ewayreq": "Y",
            "subsupplytype": "1",
            "transmode": "1",
            "distance": "120",
            "transporter_name": "FastTrack Logistics",
            "transdocno": "LR-998822",
            "transdocdt": "2026-10-10",
            "veh_number": "KA01AB1234",
            "veh_type": "R"
        }
    }


def test_valid_payload_parsing(sample_raw_invoice_dict):
    payload = InvoicePayload.model_validate(sample_raw_invoice_dict)
    assert payload.docno == "INV-2026-B2B"
    assert payload.supplier.lglnm == "BHARAT TECH SOLUTIONS PVT LTD"
    assert payload.buyer.gstin == "29XYZAB5678C1Z2"
    assert len(payload.itemdtls) == 1
    assert payload.itemdtls[0].hsn == "8481"
    assert payload.ewbdt1.distance == 120.0


def test_corrupt_gstin_fails():
    with pytest.raises(ValidationError) as exc:
        Counterparty(
            gstin="INVALID_GSTIN_123",
            lglnm="Test Corp",
            state="29",
            pin="560001"
        )
    assert "Invalid GSTIN format" in str(exc.value)


def test_corrupt_pincode_fails():
    with pytest.raises(ValidationError) as exc:
        Counterparty(
            gstin="29ABCDE1234F1Z5",
            lglnm="Test Corp",
            state="29",
            pin="56000"
        )
    assert "[NIC-2244]" in str(exc.value) or "6-digit postal code" in str(exc.value)


def test_corrupt_hsn_fails():
    with pytest.raises(ValidationError) as exc:
        LineItem(
            slno="1",
            prdnm="Test Goods",
            hsn="1",
            qty=10,
            unitprice=100.0,
            totamt=1000.0,
            pretaxval=1000.0,
            assval=1000.0,
            gstrate=18.0,
            totitemval=1180.0
        )
    assert "[NIC-2176]" in str(exc.value) or "Wrong HSN code" in str(exc.value)


def test_parquet_roundtrip_storage(tmp_path, sample_raw_invoice_dict):
    payload = InvoicePayload.model_validate(sample_raw_invoice_dict)
    rows = flatten_invoice_payload(payload)
    df = pd.DataFrame(rows)

    target_file = str(tmp_path / "test_invoice.parquet")
    write_parquet(df, target_file, schema=FLATTENED_INVOICE_SCHEMA)

    df_recovered = read_parquet(target_file)
    assert len(df_recovered) == 1
    assert df_recovered.iloc[0]["invoice_id"] == "INV-2026-B2B"
    assert df_recovered.iloc[0]["hsn"] in ("8481", "85015320", "85015290")
    assert df_recovered.iloc[0]["total_item_value"] == 59000.0


def test_store_invoice_and_export_to_excel(tmp_path, sample_raw_invoice_dict):
    parquet_target = str(tmp_path / "invoices_master.parquet")
    excel_target = str(tmp_path / "invoices_export.xlsx")

    payload = InvoicePayload.model_validate(sample_raw_invoice_dict)

    # 1. verify initial store
    count1 = store_invoice_payload(payload, storage_path=parquet_target)
    assert count1 == 1

    # 2. verify storing a second distinct invoice
    import copy
    sample_raw_2 = copy.deepcopy(sample_raw_invoice_dict)
    sample_raw_2["docdt1"]["docno"] = "INV-2026-B2B-02"
    payload2 = InvoicePayload.model_validate(sample_raw_2)
    count2 = store_invoice_payload(payload2, storage_path=parquet_target)
    assert count2 == 1

    # verify idempotency: storing existing invoice does not create duplicates
    store_invoice_payload(payload, storage_path=parquet_target)

    df_parquet = read_parquet(parquet_target)
    assert len(df_parquet) == 2

    # 3. verify excel export
    out_excel = export_invoices_to_excel(
        parquet_path=parquet_target,
        excel_path=excel_target
    )
    assert os.path.exists(out_excel)

    df_excel = pd.read_excel(out_excel, sheet_name="Invoices", dtype={"hsn": str})
    assert len(df_excel) == 2
    assert set(df_excel["invoice_id"].tolist()) == {"INV-2026-B2B", "INV-2026-B2B-02"}
    assert df_excel.iloc[0]["hsn"] in ("8481", "85015320", "85015290")


def test_store_to_processed_payload_directory(sample_raw_invoice_dict):
    """
    Validates end-to-end persistence directly into data/processed_payload:
    - Stores flattened invoice into data/processed_payload/invoices_master.parquet
    - Exports formatted table into data/processed_payload/invoices_export.xlsx
    - Stores validated JSON into data/processed_payload/<docno>_processed.json
    """
    payload = InvoicePayload.model_validate(sample_raw_invoice_dict)

    # 1. Store to default processed_payload parquet path
    count = store_invoice_payload(payload)
    assert count == 1
    assert os.path.exists(DEFAULT_STORAGE_PATH)

    df_parquet = read_parquet(DEFAULT_STORAGE_PATH)
    assert len(df_parquet) >= 1
    recent_row = df_parquet[df_parquet["invoice_id"] == "INV-2026-B2B"].iloc[-1]
    assert recent_row["invoice_id"] == "INV-2026-B2B"
    assert recent_row["supplier_gstin"] == "29ABCDE1234F1Z5"
    assert recent_row["hsn"] in ("8481", "85015320", "85015290")
    assert recent_row["total_item_value"] == 59000.0

    # 2. Export to default processed_payload Excel path
    excel_path = export_invoices_to_excel()
    assert os.path.exists(excel_path)
    df_excel = pd.read_excel(excel_path, sheet_name="Invoices", dtype={"hsn": str})
    assert len(df_excel) >= 1
    assert "INV-2026-B2B" in df_excel["invoice_id"].values

    # 3. Store processed JSON representation into data/processed_payload
    json_path = store_processed_json(payload)
    assert os.path.exists(json_path)
    with open(json_path, "r", encoding="utf-8") as f:
        saved_json = json.load(f)
    assert saved_json["docno"] == "INV-2026-B2B"
    assert saved_json["supplier"]["gstin"] == "29ABCDE1234F1Z5"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))

