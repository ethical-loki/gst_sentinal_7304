import json
import os
import pytest
from datetime import datetime, timedelta
from typing import Dict, Any

from Template_Converters.hsn_resolver import lookup_hsn_code, validate_nic_2day_rule
from Template_Converters.payload_builder import PayloadBuilder
from Template_Converters.validator import GSTValidator

from src.ingestion.converter import convert_and_validate_in_memory
from src.ingestion.schemas import InvoicePayload
from src.ingestion.generate_sample_dirty_input import get_customer_error_payload


@pytest.fixture
def raw_customer_payload() -> Dict[str, Any]:
    return get_customer_error_payload()


def test_hsn_resolution_from_master_file():
    """Verify that 'Industrial Servo Motor' resolves to Heading 8501 (85011013 / 8501) with 18% GST."""
    res = lookup_hsn_code("Industrial Servo Motor", "High torque servo motor for automation assembly line", "84")
    assert len(res) > 0
    assert res[0]["hsn_code"] in ("8501", "85011013", "85011012") or res[0]["hsn_code"].startswith("8501")
    assert res[0]["gst_rate"] == 18.0
    assert "motors" in res[0]["description"].lower()


def test_nic_2day_rule_date_validation():
    """Verify NIC 2-day rule: docdt > 2 days in past fails with Rule 2164 & 'change the date'."""
    today = datetime.now().date()
    old_date = (today - timedelta(days=5)).strftime("%Y-%m-%d")
    recent_date = (today - timedelta(days=1)).strftime("%Y-%m-%d")

    # Old date should fail
    date_err = validate_nic_2day_rule(old_date)
    assert date_err is not None
    assert date_err["error_code"] == 2164
    assert "change the date" in date_err["message"].lower()

    # Recent date should pass
    date_ok = validate_nic_2day_rule(recent_date)
    assert date_ok is None


def test_template_converters_pipeline_with_customer_payload(raw_customer_payload):
    """
    Test Template_Converters module with customer payload:
    1. HSN resolves to statutory Heading 8501 (e.g. 85011013).
    2. Taxable value option is applied.
    3. Validation fails with Rule 2164 and prompt 'change the date'.
    """
    invoice_raw = raw_customer_payload["einvoices"][0]

    # Clean & build with HSN matching and custom taxable value input of 60000.0
    clean_inv, audits = PayloadBuilder.auto_correct_and_build(invoice_raw, taxable_value_input=60000.0)

    # 1. Check HSN resolution
    item = clean_inv["itemdtls"][0]
    assert item["hsncd"] in ("8501", "85011013", "85011012") or item["hsncd"].startswith("8501")
    assert float(item["cgstrt"]) == 9.0
    assert float(item["sgstrt"]) == 9.0

    # 2. Check taxable value recalculation
    assert float(item["assamt"]) == 60000.0
    assert float(item["cgstamt"]) == 5400.0
    assert float(item["sgstamt"]) == 5400.0
    assert float(item["totitemval"]) == 70800.0
    val_sec = clean_inv.get("valdt1") or clean_inv.get("valdtls")
    assert float(val_sec["totinvval"]) == 70800.0

    # 3. Validation failure due to docdt 2026-10-10 (> 2 days from today)
    errors = GSTValidator.validate_invoice(clean_inv)
    err_codes = [e.get("error_code") for e in errors]
    assert 2164 in err_codes

    date_err = next(e for e in errors if e.get("error_code") == 2164)
    assert "change the date" in date_err.get("message", "").lower()


def test_src_ingestion_converter_with_customer_payload(raw_customer_payload):
    """
    Test src.ingestion converter with customer payload:
    1. HSN resolves to statutory Heading 8501 (85011013).
    2. Taxable value input is supported and recalculates tax math.
    3. Date older than 2 days marks status as FAILED with error 2164 and prompt 'change the date'.
    """
    result = convert_and_validate_in_memory(raw_customer_payload, taxable_value_input=50000.0)

    assert result["status"] == "success"
    val_report = result["validation_report"]
    assert val_report["failed_invoices"] >= 1

    inv_res = val_report["results"][0]
    assert inv_res["status"] == "FAILED"

    # Check that error 2164 is present with prompt
    errors = inv_res["errors"]
    has_2164 = any(e.get("error_code") == 2164 for e in errors)
    assert has_2164

    err_2164 = next(e for e in errors if e.get("error_code") == 2164)
    assert "change the date" in (err_2164.get("resolution") or "").lower() or "change the date" in err_2164.get("message", "").lower()

    # Check HSN correction was recorded in corrections_applied
    corrections = inv_res["corrections_applied"]
    hsn_cor = [c for c in corrections if c.get("category") in ("HSN_CODE_LOOKUP", "HSN_TARIFF_SCHEDULE_LOOKUP")]
    assert len(hsn_cor) > 0
    assert hsn_cor[0]["corrected"] in ("8501", "85011013", "85011012") or hsn_cor[0]["corrected"].startswith("8501")


def test_compliant_when_date_is_current(raw_customer_payload):
    """
    Verify that when docdt is set to today and buyer GSTIN is valid, NIC 2-day rule passes.
    """
    payload = json.loads(json.dumps(raw_customer_payload))
    today_str = datetime.now().strftime("%Y-%m-%d")
    payload["einvoices"][0]["docdt1"]["docdt"] = today_str

    result = convert_and_validate_in_memory(payload, taxable_value_input=50000.0)
    inv_res = result["validation_report"]["results"][0]

    # Verify error 2164 is NOT triggered
    errors = inv_res["errors"]
    err_codes = [e.get("error_code") for e in errors]
    assert 2164 not in err_codes
