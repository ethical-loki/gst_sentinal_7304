"""
Test suite for Ingestion E-Invoice & E-Way Bill Converter Engine and AI Copilot.
Validates parity with Template_Converters/E-invoice_e_way coverter.py,
native Pydantic v2 schemas, Lakehouse Parquet/Excel persistence, and interactive Copilot.
"""

import os
import sys
import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.ingestion.schemas import InvoicePayload, InvoiceBatchPayload
from src.ingestion.converter import (
    process_and_convert_payload,
    convert_and_validate_in_memory,
    export_csv_audit_report,
    export_text_summary_report,
    build_audit_records_and_csv,
)
from src.ingestion.storage import (
    DEFAULT_STORAGE_DIR,
    DEFAULT_STORAGE_PATH,
    DEFAULT_EXCEL_PATH,
    read_parquet,
)
from backend.ingestion_service import (
    process_ingestion_pipeline,
    process_ingestion_chat,
    load_default_sample_dirty,
    generate_random_dirty,
    get_configured_endpoints_info,
    verify_gstin_government_portal,
    verify_vahan_vehicle_portal,
    PROCESSED_DIR,
)
from backend.main import app


@pytest.fixture
def sample_dirty_file(tmp_path):
    dirty_json = {
        "einvoices": [
            {
                "self gstin": "29ABCDE1234F1Z5",
                "system cd": "SAP_ERP",
                "branch cd": "BLR01",
                "vertical cd": "DOM",
                "trandt1": {
                    "trancatg": "B2C",
                    "reversecharge": "Y",
                    "transactionmode": "REG"
                },
                "docdt1": {
                    "document_type": "INV",
                    "docno": "INV-INGEST-001",
                    "docdt": "15/10/2026"
                },
                "supplierdt1": {
                    "supplier_gstin": "29ABCDE1234F1Z5",
                    "supplier_1g1nm": "BHARAT ENTERPRISES",
                    "supplier_loc": "Bengaluru",
                    "supplier_pin": "560001",
                    "supplier_state": "29"
                },
                "buyerdt1": {
                    "buyer_gstin": "URP",
                    "buyer_1g1nm": "RETAIL CONSUMER",
                    "buyer_loc": "Bengaluru",
                    "buyer_pin": "560001",
                    "buyer_state": "29",
                    "buyer_pos": "29"
                },
                "itemdtls": [
                    {
                        "slno": "1",
                        "prdnm": "Industrial Motor",
                        "hsn": "8481",
                        "qty": "2",
                        "unitprice": "10000.0",
                        "totamt": "20000,00",
                        "discount": "0.00",
                        "assval": "20000,00",
                        "gstrate": "18.0",
                        "cgstval": "1800,00",
                        "sgstval": "1800,00",
                        "igstval": "0.00",
                        "totitemval": "23600,00"
                    }
                ],
                "valdt1": {
                    "ttlassval": "20000.00",
                    "cgstval": "1800.00",
                    "sgstval": "1800.00",
                    "igstval": "0.00",
                    "totinvval": "99999.00"
                }
            }
        ]
    }
    file_path = tmp_path / "test_dirty.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(dirty_json, f, indent=2)
    return str(file_path)


def test_converter_engine_end_to_end(sample_dirty_file, tmp_path):
    """Verifies that src.ingestion.converter generates all 4 files and updates Lakehouse."""
    out_corrected = str(tmp_path / "corrected_payload.json")
    out_report = str(tmp_path / "validation_report.json")
    out_csv = str(tmp_path / "correction_audit_report.csv")
    out_txt = str(tmp_path / "audit_summary.txt")

    result = process_and_convert_payload(
        sample_dirty_file,
        out_corrected,
        out_report,
        out_csv,
        out_txt,
        persist_to_lakehouse=True
    )

    assert result["status"] == "success"
    assert os.path.exists(out_corrected)
    assert os.path.exists(out_report)
    assert os.path.exists(out_csv)
    assert os.path.exists(out_txt)

    with open(out_corrected, "r", encoding="utf-8") as f:
        c_data = json.load(f)
    assert "einvoices" in c_data or "docno" in c_data

    with open(out_report, "r", encoding="utf-8") as f:
        r_data = json.load(f)
    assert r_data["total_invoices"] == 1
    assert r_data["valid_invoices"] == 1
    assert r_data["failed_invoices"] == 0

    # Auto-corrections check: comma decimals replaced and reverse charge corrected
    res0 = r_data["results"][0]
    assert res0["corrections_applied_count"] > 0


def test_convert_and_validate_in_memory_direct():
    """Verifies convert_and_validate_in_memory with direct dictionary payload."""
    dirty_inv = {
        "self gstin": "29ABCDE1234F1Z5",
        "docdt1": {"docno": "INV-MEM-001", "invoice_date": "2026-10-15"},
        "trandt1": {"trancatg": "B2B", "reversecharge": "N"},
        "supplierdt1": {
            "supplier_gstin": "29ABCDE1234F1Z5",
            "supplier_1g1nm": "SUPPLIER TECH",
            "supplier_loc": "Bengaluru",
            "supplier_pin": "560001",
            "supplier_state": "29"
        },
        "buyerdt1": {
            "buyer_gstin": "29XYZAB5678C1Z2",
            "buyer_1g1nm": "BUYER CORP",
            "buyer_loc": "Bengaluru",
            "buyer_pin": "560002",
            "buyer_state": "29",
            "pos": "29"
        },
        "itemdtls": [
            {
                "prdnm": "Widget",
                "hsn": "8481",
                "qty": "5",
                "unitprice": "100.0",
                "grossamt": "500,00",
                "assval": "500,00",
                "cgstval": "45.0",
                "sgstval": "45.0",
                "totitemval": "590,00"
            }
        ],
        "valdt1": {"assval": "500.0", "cgstval": "45.0", "sgstval": "45.0", "totinvval": "590.0"}
    }
    res = convert_and_validate_in_memory(dirty_inv)
    assert res["status"] == "success"
    assert res["metrics"]["valid_invoices"] == 1
    assert res["metrics"]["total_invoices"] == 1
    assert len(res["audit_records"]) > 0


def test_process_ingestion_pipeline():
    """Verifies process_ingestion_pipeline produces all outputs and syncs to disk."""
    sample = load_default_sample_dirty()
    result = process_ingestion_pipeline(sample, sync_to_disk=True, persist_to_lakehouse=True)

    assert result["status"] in ["VALID", "NEEDS_ATTENTION", "success"]
    assert "clean_payload" in result
    assert "validation_report" in result
    assert "metrics" in result
    assert "audit_records" in result
    assert "summary_text" in result
    assert "csv_content" in result
    assert result["lakehouse_rows_persisted"] > 0

    assert (PROCESSED_DIR / "invoices_master.parquet").exists()
    assert (PROCESSED_DIR / "invoices_export.xlsx").exists()
    assert (PROCESSED_DIR / "transformation_audit_report.csv").exists()


def test_process_ingestion_chat_intent_and_patches():
    """
    Verifies that process_ingestion_chat answers questions, accepts patches,
    and updates both inputs and outputs.
    """
    sample = load_default_sample_dirty()

    # 1. Ask explanation question
    q_res = process_ingestion_chat("Why did my invoice fail?", sample, None, [])
    assert q_res["status"] == "success"
    assert "reply" in q_res
    assert isinstance(q_res["quick_prompts"], list)

    # 2. Apply patch: Set Category to B2B
    p_res = process_ingestion_chat("Set Category: B2B", sample, None, [])
    assert p_res["status"] == "success"
    assert p_res["patch_applied"] is True
    assert "updated_payload" in p_res
    assert "clean_payload" in p_res
    assert "validation_report" in p_res
    assert "metrics" in p_res
    assert p_res["lakehouse_updated"] is True

    # 3. Apply patch: Supply GSTIN
    p_res2 = process_ingestion_chat("My GSTIN is 29ABCDE1234F1ZW", p_res["updated_payload"], p_res["validation_report"], [])
    assert p_res2["status"] == "success"
    assert p_res2["patch_applied"] is True

    # 4. Apply patch: Rebalance tax math
    p_res3 = process_ingestion_chat("Rebalance tax math and invoice value", p_res2["updated_payload"], p_res2["validation_report"], [])
    assert p_res3["status"] == "success"
    assert p_res3["patch_applied"] is True


def test_fastapi_ingestion_endpoints():
    """Verifies all FastAPI /api/ingestion endpoints via TestClient."""
    client = TestClient(app)

    # 1. GET /api/ingestion/sample
    r_sample = client.get("/api/ingestion/sample")
    assert r_sample.status_code == 200
    assert r_sample.json()["status"] == "success"
    sample_payload = r_sample.json()["payload"]

    # 2. POST /api/ingestion/process
    r_proc = client.post("/api/ingestion/process", json={"payload": sample_payload})
    assert r_proc.status_code == 200
    data = r_proc.json()
    assert "validation_report" in data
    assert "metrics" in data
    assert "clean_payload" in data

    # 3. POST /api/ingestion/chat
    r_chat = client.post("/api/ingestion/chat", json={
        "message": "Set Category: B2B",
        "payload": sample_payload,
        "chat_history": []
    })
    assert r_chat.status_code == 200
    chat_data = r_chat.json()
    assert chat_data["status"] == "success"
    assert "updated_payload" in chat_data
    assert "reply" in chat_data

    # 4. POST /api/ingestion/generate
    r_gen = client.post("/api/ingestion/generate", json={"count": 2})
    assert r_gen.status_code == 200
    assert r_gen.json()["count"] == 2

    # 5. GET /api/ingestion/endpoints
    r_ep = client.get("/api/ingestion/endpoints")
    assert r_ep.status_code == 200
    assert "modules" in r_ep.json()

    # 6. GET /api/ingestion/verify-gstin/29ABCDE1234F1Z5
    r_gst = client.get("/api/ingestion/verify-gstin/29ABCDE1234F1Z5")
    assert r_gst.status_code == 200
    assert "is_valid" in r_gst.json()

    # 7. GET /api/ingestion/verify-vehicle/KA01AB1234
    r_veh = client.get("/api/ingestion/verify-vehicle/KA01AB1234")
    assert r_veh.status_code == 200
    assert r_veh.json()["is_valid"] is True

    # 8. GET /api/ingestion/download/corrected
    r_dl = client.get("/api/ingestion/download/corrected")
    assert r_dl.status_code == 200
    assert r_dl.headers["content-type"] == "application/json"

    # 9. GET /api/ingestion/download/parquet
    r_dl_p = client.get("/api/ingestion/download/parquet")
    assert r_dl_p.status_code == 200
