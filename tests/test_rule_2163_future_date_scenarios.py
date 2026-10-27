"""
Comprehensive test suite for NIC Rule 2163 (Document Date Future Date & Timezone Scenarios).
Validates all 5 statutory future date scenarios specified by NIC:
1. Tomorrow / Future Date:
   Sent: "Dt": "26/10/2026" (Server on 25/10/2026) -> Valid: "25/10/2026"
   Reason: Document date cannot exceed the current server calendar day. Set to today's date or earlier.
2. Swapped Day/Month Format:
   Sent: "Dt": "11/02/2026" (Intended 11 Feb 2026, evaluated as 02 Nov 2026) -> Valid: "11/02/2026"
   Reason: System parses strictly as DD/MM/YYYY. Sending MM/DD/YYYY where month > current month causes a future date error.
3. Timezone / UTC Desynchronization:
   Sent: "Dt": "26/10/2026" (Server running in UTC+00:00 shifts clock past midnight early) -> Valid: "25/10/2026"
   Reason: Ensure ERP date-formatting logic runs in IST (Indian Standard Time). UTC offsets can push the date 1 day ahead prematurely.
4. Wrong Fiscal Year Selected:
   Sent: "Dt": "25/10/2027" (Typo in year field) -> Valid: "25/10/2026"
   Reason: Check ERP auto-numbering or manual date entry logic for accidental next-year increments.
5. Pre-dated Draft Invoices:
   Sent: "Dt": "28/10/2026" (Advance invoicing attempted) -> Valid: "25/10/2026"
   Reason: Generate IRN only on or after the actual invoice issue date. Advance dates must wait until that day arrives.
"""

from datetime import date, timedelta
from typing import Dict, Any
import pytest

from src.ingestion.schemas import (
    InvoicePayload,
    get_ist_today,
    get_ist_now,
    classify_future_date_diagnostic,
    parse_date_universal,
)
from Template_Converters.payload_builder import PayloadBuilder
from Template_Converters.validator import GSTValidator
from src.rules.rules_engine import RulesEngine


FIXED_SERVER_TODAY = date(2026, 10, 25)


@pytest.fixture
def base_invoice_dict() -> Dict[str, Any]:
    """Base minimal valid invoice dictionary."""
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
            "docno": "INV-2026-DT01",
            "docdt": "25-10-2026"
        },
        "supplierdt1": {
            "supplier_gstin": "29ABCDE1234F1Z5",
            "supplier_lglnm": "BHARAT ENTERPRISES",
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
                "prdnm": "Fasteners",
                "hsn": "73181500",
                "qty": 10.0,
                "unit": "NOS",
                "unitprice": 100.0,
                "totamt": 1000.0,
                "assval": 1000.0,
                "gstrate": 18.0,
                "cgstval": 90.0,
                "sgstval": 90.0,
                "igstval": 0.0,
                "totitemval": 1180.0
            }
        ],
        "valdt1": {
            "ttlassval": "1000.00",
            "cgstval": "90.00",
            "sgstval": "90.00",
            "igstval": "0.00",
            "totinvval": "1180.00"
        }
    }


# ============================================================================
# 1. DIRECT DIAGNOSTIC FUNCTION UNIT TESTS
# ============================================================================

def test_scenario_1_tomorrow_future_date():
    """Tomorrow / Future Date: Dt='26/10/2026' on server 25/10/2026."""
    sent_date = date(2026, 10, 26)
    diag = classify_future_date_diagnostic(sent_date, raw_str="26/10/2026", server_today=FIXED_SERVER_TODAY, is_utc_context=False)
    assert diag["scenario"] == "FUTURE_DATE"
    assert diag["valid_date"] == FIXED_SERVER_TODAY
    assert diag["valid_str"] == "25/10/2026"
    assert diag["reason"] == "Document date cannot exceed the current server calendar day. Set to today's date or earlier."


def test_scenario_2_swapped_day_month_format():
    """Swapped Day/Month Format: Dt='11/02/2026' evaluated as 02 Nov 2026 > Oct."""
    # When evaluated erroneously as MM/DD/YYYY, day becomes 2 and month becomes 11 (02 Nov 2026)
    sent_date = date(2026, 11, 2)
    diag = classify_future_date_diagnostic(sent_date, raw_str="11/02/2026", server_today=FIXED_SERVER_TODAY)
    assert diag["scenario"] == "SWAPPED_DAY_MONTH"
    assert diag["valid_date"] == date(2026, 2, 11)  # Strict DD/MM/YYYY: 11 Feb 2026
    assert diag["valid_str"] == "11/02/2026"
    assert diag["reason"] == "System parses strictly as DD/MM/YYYY. Sending MM/DD/YYYY where month > current month causes a future date error."


def test_scenario_3_timezone_utc_desynchronization():
    """Timezone / UTC Desynchronization: Dt='26/10/2026' with UTC context."""
    sent_date = date(2026, 10, 26)
    diag = classify_future_date_diagnostic(sent_date, raw_str="26/10/2026", server_today=FIXED_SERVER_TODAY, is_utc_context=True)
    assert diag["scenario"] == "TIMEZONE_DESYNC"
    assert diag["valid_date"] == FIXED_SERVER_TODAY
    assert diag["valid_str"] == "25/10/2026"
    assert diag["reason"] == "Ensure ERP date-formatting logic runs in IST (Indian Standard Time). UTC offsets can push the date 1 day ahead prematurely."


def test_scenario_4_wrong_fiscal_year_selected():
    """Wrong Fiscal Year Selected: Dt='25/10/2027' typo in year field."""
    sent_date = date(2027, 10, 25)
    diag = classify_future_date_diagnostic(sent_date, raw_str="25/10/2027", server_today=FIXED_SERVER_TODAY)
    assert diag["scenario"] == "WRONG_FISCAL_YEAR"
    assert diag["valid_date"] == date(2026, 10, 25)
    assert diag["valid_str"] == "25/10/2026"
    assert diag["reason"] == "Check ERP auto-numbering or manual date entry logic for accidental next-year increments."


def test_scenario_5_predated_draft_invoices():
    """Pre-dated Draft Invoices: Dt='28/10/2026' advance invoicing attempted."""
    sent_date = date(2026, 10, 28)
    diag = classify_future_date_diagnostic(sent_date, raw_str="28/10/2026", server_today=FIXED_SERVER_TODAY)
    assert diag["scenario"] == "PREDATED_DRAFT_INVOICE"
    assert diag["valid_date"] == FIXED_SERVER_TODAY
    assert diag["valid_str"] == "25/10/2026"
    assert diag["reason"] == "Generate IRN only on or after the actual invoice issue date. Advance dates must wait until that day arrives."


# ============================================================================
# 2. STRICT DD/MM/YYYY PARSING
# ============================================================================

def test_strict_parsing_of_swapped_string():
    """Verifies that parse_date_universal strictly parses '11/02/2026' as 11-Feb-2026, not 02-Nov-2026."""
    dt = parse_date_universal("11/02/2026")
    assert dt == date(2026, 2, 11)  # Strict DD/MM/YYYY: 11th Feb


# ============================================================================
# 3. INVOICE PAYLOAD AUTO_CORRECT_AND_BUILD INTEGRATION TESTS
# ============================================================================

def test_invoice_payload_auto_correct_future_date(base_invoice_dict):
    """Verifies InvoicePayload.auto_correct_and_build heals tomorrow date with exact reason."""
    dirty = dict(base_invoice_dict)
    dirty["docdt1"] = dict(base_invoice_dict["docdt1"])
    tomorrow = get_ist_today() + timedelta(days=1)
    dirty["docdt1"]["docdt"] = tomorrow.strftime("%d-%m-%Y")

    model, audit_log = InvoicePayload.auto_correct_and_build(dirty)
    today_ist = get_ist_today()
    assert model.docdt <= today_ist
    assert any("Document date cannot exceed the current server calendar day" in l.get("description", "") for l in audit_log)


def test_invoice_payload_auto_correct_wrong_year(base_invoice_dict):
    """Verifies InvoicePayload.auto_correct_and_build heals typo in year with exact reason."""
    dirty = dict(base_invoice_dict)
    dirty["docdt1"] = dict(base_invoice_dict["docdt1"])
    dirty["docdt1"]["docdt"] = "25-10-2027"

    model, audit_log = InvoicePayload.auto_correct_and_build(dirty)
    today_ist = get_ist_today()
    assert model.docdt.year == today_ist.year
    assert any("Check ERP auto-numbering or manual date entry logic for accidental next-year increments." in l.get("description", "") for l in audit_log)


def test_invoice_payload_auto_correct_predated_draft(base_invoice_dict):
    """Verifies InvoicePayload.auto_correct_and_build heals advance draft invoice."""
    dirty = dict(base_invoice_dict)
    dirty["docdt1"] = dict(base_invoice_dict["docdt1"])
    dirty["docdt1"]["docdt"] = "28-10-2026"

    model, audit_log = InvoicePayload.auto_correct_and_build(dirty)
    today_ist = get_ist_today()
    assert model.docdt <= today_ist
    assert any("Generate IRN only on or after the actual invoice issue date" in l.get("description", "") for l in audit_log)


def test_invoice_payload_dt_alias(base_invoice_dict):
    """Verifies that 'Dt' key at root or in docdt1 is recognized and healed."""
    dirty = dict(base_invoice_dict)
    dirty["Dt"] = "25/10/2027"
    if "docdt1" in dirty and "docdt" in dirty["docdt1"]:
        del dirty["docdt1"]["docdt"]

    model, audit_log = InvoicePayload.auto_correct_and_build(dirty)
    today_ist = get_ist_today()
    assert model.docdt.year == today_ist.year


# ============================================================================
# 4. PAYLOAD BUILDER AUTO_CORRECT_AND_BUILD INTEGRATION TESTS
# ============================================================================

def test_payload_builder_auto_correct_future_date(base_invoice_dict):
    """Verifies PayloadBuilder.auto_correct_and_build heals tomorrow date with exact reason."""
    dirty = dict(base_invoice_dict)
    dirty["docdt1"] = dict(base_invoice_dict["docdt1"])
    tomorrow = get_ist_today() + timedelta(days=1)
    dirty["docdt1"]["docdt"] = tomorrow.strftime("%d-%m-%Y")

    clean_inv, audit_log = PayloadBuilder.auto_correct_and_build(dirty)
    today_ist = get_ist_today()
    expected_str = today_ist.strftime("%d-%m-%Y")
    assert clean_inv["docdt1"]["docdt"] == expected_str
    assert any("Document date cannot exceed the current server calendar day" in l.get("description", "") for l in audit_log)


def test_payload_builder_auto_correct_utc_desync(base_invoice_dict):
    """Verifies PayloadBuilder.auto_correct_and_build with UTC context records exact timezone reason."""
    dirty = dict(base_invoice_dict)
    dirty["docdt1"] = dict(base_invoice_dict["docdt1"])
    tomorrow = get_ist_today() + timedelta(days=1)
    dirty["docdt1"]["docdt"] = tomorrow.strftime("%d-%m-%Y")
    dirty["is_utc_context"] = True

    clean_inv, audit_log = PayloadBuilder.auto_correct_and_build(dirty)
    assert any("Ensure ERP date-formatting logic runs in IST (Indian Standard Time)" in l.get("description", "") for l in audit_log)


def test_payload_builder_auto_correct_wrong_year(base_invoice_dict):
    """Verifies PayloadBuilder.auto_correct_and_build heals 2027 typo to 2026."""
    dirty = dict(base_invoice_dict)
    dirty["docdt1"] = dict(base_invoice_dict["docdt1"])
    dirty["docdt1"]["docdt"] = "25-10-2027"

    clean_inv, audit_log = PayloadBuilder.auto_correct_and_build(dirty)
    assert any("Check ERP auto-numbering or manual date entry logic for accidental next-year increments." in l.get("description", "") for l in audit_log)


def test_payload_builder_auto_correct_predated_draft(base_invoice_dict):
    """Verifies PayloadBuilder.auto_correct_and_build heals advance draft invoice."""
    dirty = dict(base_invoice_dict)
    dirty["docdt1"] = dict(base_invoice_dict["docdt1"])
    dirty["docdt1"]["docdt"] = "28-10-2026"

    clean_inv, audit_log = PayloadBuilder.auto_correct_and_build(dirty)
    assert any("Generate IRN only on or after the actual invoice issue date" in l.get("description", "") for l in audit_log)


# ============================================================================
# 5. PRE-API VALIDATOR & RULES ENGINE REPORTING FOR RULE 2163
# ============================================================================

def test_validator_and_rules_engine_rule_2163_rejections():
    """Verifies GSTValidator and RulesEngine flag Rule 2163 with exact diagnostic reason."""
    tomorrow = get_ist_today() + timedelta(days=1)
    inv_tomorrow = {
        "docdt1": {
            "document_type": "INV",
            "docno": "INV-001",
            "docdt": tomorrow.strftime("%d-%m-%Y")
        }
    }
    val_errors = GSTValidator.validate_invoice(inv_tomorrow)
    r2163 = [e for e in val_errors if e.get("error_code") == 2163]
    assert len(r2163) > 0
    assert "Document date cannot exceed the current server calendar day" in r2163[0]["message"]

    re = RulesEngine()
    re_errors = re.validate_invoice(inv_tomorrow)
    re_r2163 = [e for e in re_errors if e.get("error_code") == 2163]
    assert len(re_r2163) > 0
    assert "Document date cannot exceed the current server calendar day" in re_r2163[0]["message"]


def test_validator_utc_desync_reason():
    """Verifies GSTValidator reports UTC offset reason when UTC context flag is present."""
    tomorrow = get_ist_today() + timedelta(days=1)
    inv_utc = {
        "docdt1": {
            "document_type": "INV",
            "docno": "INV-001",
            "docdt": tomorrow.strftime("%d-%m-%Y")
        },
        "is_utc_context": True
    }
    val_errors = GSTValidator.validate_invoice(inv_utc)
    r2163 = [e for e in val_errors if e.get("error_code") == 2163]
    assert len(r2163) > 0
    assert "Ensure ERP date-formatting logic runs in IST (Indian Standard Time)" in r2163[0]["message"]
