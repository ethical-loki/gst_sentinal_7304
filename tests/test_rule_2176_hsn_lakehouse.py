"""
Test Suite: NIC Error Code 2176 Statutory Compliance & Data Lakehouse HSN Intelligence.
File: tests/test_rule_2176_hsn_lakehouse.py

Validates:
1. NIC Error Code 2176 Definition & Official Resolution:
   - Message: 'HSN code(s)-{0} is invalid'
   - Reason: 'Wrong HSN code is being passed'
   - Resolution: 'Pl check the HSN code being passed and Cross-check the correctness of HSN code
     on e-invoice portal. Still, if you feel it is correct, then please send the details to the
     helpdesk for verification at e-invoice system side.'
2. Format & Length Validations (must be 2, 4, 6, or 8 digits; goods/services).
3. Statutory Tariff Master Verification (CBIC schedule with 13,000+ codes).
4. Data Lakehouse Module Integration:
   - Powered by HSNIntelligenceEngine (Two-Tier BGE + Cross-Encoder + Trade Dependency Parser)
   - Lakehouse payload flattening (flatten_invoice_payload) storing rectified HSN & sentinel telemetry
   - Parquet persistence & schema compatibility
   - Self-healing auto_correct_and_build pipeline.
"""

import os
import shutil
import tempfile
from decimal import Decimal
from pathlib import Path
import pytest
import pandas as pd

from pydantic import ValidationError
from src.ingestion.schemas import (
    InvoicePayload,
    LineItem,
    IRN_ERRORS,
    NICValidationError,
    classify_rule_2176_diagnostic,
)
from Template_Converters.hsn_resolver import (
    lookup_hsn_code,
    validate_hsn_statutory,
    audit_and_rectify_line_item_sentinel,
    get_hsn_intelligence_engine,
)
from Template_Converters.error_mappings import NIC_ERROR_CODES
from Template_Converters.validator import GSTValidator
from src.rules.rules_engine import RulesEngine
from src.ingestion.storage import (
    flatten_invoice_payload,
    write_parquet,
    read_parquet,
    append_to_parquet,
)


# ==============================================================================
# FIXTURES
# ==============================================================================

@pytest.fixture
def valid_invoice_base():
    return {
        "self_gstin": "29ABCDE1234F1Z5",
        "docno": "INV-2026-2176",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "B2B",
        "reversecharge": "N",
        "igstonintra": "N",
        "supplier": {
            "gstin": "29ABCDE1234F1Z5",
            "lglnm": "Acme Industrial Supplies Pvt Ltd",
            "state": "29",
            "pin": 560001,
            "loc": "Bangalore"
        },
        "buyer": {
            "gstin": "29XYZAB5678C1Z2",
            "lglnm": "Karnataka Manufacturing Ltd",
            "state": "29",
            "pos": "29",
            "pin": 560002,
            "loc": "Bangalore"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "BACK ASSY RR SEAT MS1",
                "prddesc": "Automotive passenger rear seat assembly",
                "hsn": "94013000",
                "qty": 2.0,
                "unit": "NOS",
                "unitprice": 3500.0,
                "totamt": 7000.0,
                "discount": 0.0,
                "pretaxval": 7000.0,
                "assval": 7000.0,
                "gstrate": 18.0,
                "cgstval": 630.0,
                "sgstval": 630.0,
                "igstval": 0.0,
                "totitemval": 8260.0,
                "is_service": "N"
            }
        ],
        "valdtls": {
            "assval": 7000.0,
            "cgstval": 630.0,
            "sgstval": 630.0,
            "igstval": 0.0,
            "totinvval": 8260.0
        }
    }


# ==============================================================================
# 1. ERROR CODE 2176 DEFINITION & STATUTORY MAPPING TESTS
# ==============================================================================

def test_rule_2176_statutory_error_mappings():
    """Verifies that IRN_ERRORS and NIC_ERROR_CODES define Rule 2176 with exact statutory text."""
    err_irn = IRN_ERRORS[2176]
    err_nic = NIC_ERROR_CODES[2176]

    for err in [err_irn, err_nic]:
        assert "HSN code(s)-{0} is invalid" in err["message"]
        assert "Wrong HSN code is being passed" in err["reason"]
        assert "Cross-check the correctness of HSN code on e-invoice portal" in err["resolution"]
        assert "helpdesk for verification at e-invoice system side" in err["resolution"]


def test_classify_rule_2176_diagnostic_scenarios():
    """Verifies classify_rule_2176_diagnostic catches missing, invalid length, and non-statutory codes."""
    # Scenario A: Missing / blank
    d_blank = classify_rule_2176_diagnostic("", "industrial servo motor", "")
    assert d_blank is not None
    assert d_blank["error_code"] == 2176
    assert d_blank["diagnostic_type"] == "MISSING_HSN"
    assert "Wrong HSN code is being passed" in d_blank["reason"]
    assert "e-invoice portal" in d_blank["resolution"]
    assert d_blank["recommended_hsn"] in ["85015320", "85015290"]

    # Scenario B: Invalid length (3 digits)
    d_len3 = classify_rule_2176_diagnostic("850", "industrial servo motor", "")
    assert d_len3 is not None
    assert d_len3["error_code"] == 2176
    assert d_len3["diagnostic_type"] == "INVALID_LENGTH"
    assert d_len3["recommended_hsn"] in ["85015320", "85015290"]

    # Scenario C: Invalid length (5 digits)
    d_len5 = classify_rule_2176_diagnostic("85015", "industrial servo motor", "")
    assert d_len5 is not None
    assert d_len5["error_code"] == 2176
    assert d_len5["diagnostic_type"] == "INVALID_LENGTH"

    # Scenario D: Non-statutory fake code (8 digits not in CBIC tariff)
    d_fake = classify_rule_2176_diagnostic("99999999", "industrial servo motor", "")
    assert d_fake is not None
    assert d_fake["error_code"] == 2176
    assert d_fake["diagnostic_type"] == "NOT_IN_STATUTORY_TARIFF"
    assert "HSN code(s)-99999999 is invalid" in d_fake["message"]
    assert d_fake["recommended_hsn"] in ["85015320", "85015290"]

    # Scenario E: Valid statutory code
    d_valid = classify_rule_2176_diagnostic("85015320", "industrial servo motor", "")
    assert d_valid is None


# ==============================================================================
# 2. HSN INTELLIGENCE & SENTINEL AUTO-RECTIFICATION TESTS
# ==============================================================================

def test_hsn_intelligence_lookup_seat_and_motor():
    """Verifies lookup_hsn_code accurately maps industrial servo motor and car seat assembly without hardcoding."""
    res_motor = lookup_hsn_code("industrial servo motor", top_k=1)
    assert len(res_motor) > 0
    assert res_motor[0]["hsn_code"] in ["85015320", "85015290"]
    assert res_motor[0]["heading"] == "8501"
    assert res_motor[0]["confidence_pct"] >= 90.0

    res_seat = lookup_hsn_code("BACK ASSY RR SEAT MS1", top_k=1)
    assert len(res_seat) > 0
    assert res_seat[0]["hsn_code"] == "94013000"
    assert res_seat[0]["heading"] == "9401"
    assert res_seat[0]["confidence_pct"] >= 90.0


def test_audit_and_rectify_line_item_sentinel_rule_2176():
    """Verifies audit_and_rectify_line_item_sentinel intercepts Rule 2176 violations and auto-rectifies."""
    # Invalid HSN 99999999 on industrial servo motor
    audit_res = audit_and_rectify_line_item_sentinel(
        product_name="industrial servo motor",
        product_desc="3-phase AC servo drive",
        declared_hsn="99999999",
        unit_price=5000.0,
        supplier_gstin="29ABCDE1234F1Z5"
    )
    assert audit_res["is_flagged"] is True
    assert audit_res["should_rectify"] is True
    assert audit_res["rectified_hsn"].startswith("85015")
    assert audit_res["error_code"] == 2176
    assert audit_res["status_badge"] == "FLAGGED_AND_RECTIFIED"
    assert any("Rule 2176 Violation" in r for r in audit_res["reasons"])
    assert any("helpdesk for verification" in r for r in audit_res["reasons"])

    # Valid statutory HSN 94013000 on seat
    valid_audit = audit_and_rectify_line_item_sentinel(
        product_name="BACK ASSY RR SEAT MS1",
        product_desc="",
        declared_hsn="94013000",
        unit_price=3500.0,
        supplier_gstin="29ABCDE1234F1Z5"
    )
    assert valid_audit["is_flagged"] is False
    assert valid_audit["should_rectify"] is False
    assert valid_audit["status_badge"] == "AUTO_APPROVED"
    assert valid_audit["rectified_hsn"] == "94013000"


# ==============================================================================
# 3. DATA LAKEHOUSE INGESTION & PARQUET STORAGE TESTS
# ==============================================================================

def test_lakehouse_flatten_invoice_payload_with_rule_2176(valid_invoice_base):
    """Verifies Lakehouse flattening captures Rule 2176 rectification and populates telemetry columns."""
    payload = dict(valid_invoice_base)
    # Modify item 1 to have an invalid non-statutory HSN
    payload["itemdtls"] = [
        {
            "item_slno": "1",
            "slno": "1",
            "prdnm": "industrial servo motor",
            "prddesc": "High torque servo motor",
            "hsn": "99999999",  # Invalid HSN
            "qty": 2.0,
            "unit": "NOS",
            "unitprice": 5000.0,
            "totamt": 10000.0,
            "assval": 10000.0,
            "gstrate": 18.0,
            "cgstval": 900.0,
            "sgstval": 900.0,
            "totitemval": 11800.0,
            "is_service": "N"
        }
    ]

    rows = flatten_invoice_payload(payload)
    assert len(rows) == 1
    r = rows[0]

    # Lakehouse final HSN should be rectified to statutory 850153 subheadings
    assert r["hsn"].startswith("85015")
    assert r["sentinel_recommended_hsn"].startswith("85015")
    assert r["sentinel_status_badge"] == "FLAGGED_AND_RECTIFIED"
    assert r["sentinel_risk_prob"] >= 0.90
    assert "Rule 2176 Violation" in r["sentinel_audit_reasons"]
    assert "helpdesk for verification" in r["sentinel_audit_reasons"]


def test_lakehouse_parquet_persistence_roundtrip(valid_invoice_base):
    """Verifies that Lakehouse Parquet read/write/append maintains HSN Intelligence telemetry columns."""
    temp_dir = tempfile.mkdtemp(prefix="gst_lakehouse_test_")
    try:
        parquet_file = os.path.join(temp_dir, "invoices_silver_test.parquet")

        payload = dict(valid_invoice_base)
        payload["itemdtls"] = [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "industrial servo motor",
                "prddesc": "",
                "hsn": "99999999",
                "qty": 1.0,
                "unit": "NOS",
                "unitprice": 8000.0,
                "assval": 8000.0,
                "gstrate": 18.0,
                "cgstval": 720.0,
                "sgstval": 720.0,
                "totitemval": 9440.0,
                "is_service": "N"
            },
            {
                "item_slno": "2",
                "slno": "2",
                "prdnm": "BACK ASSY RR SEAT MS1",
                "prddesc": "",
                "hsn": "94013000",
                "qty": 1.0,
                "unit": "NOS",
                "unitprice": 3500.0,
                "assval": 3500.0,
                "gstrate": 18.0,
                "cgstval": 315.0,
                "sgstval": 315.0,
                "totitemval": 4130.0,
                "is_service": "N"
            }
        ]
        payload["valdtls"] = {
            "assval": 11500.0,
            "cgstval": 1035.0,
            "sgstval": 1035.0,
            "igstval": 0.0,
            "totinvval": 13570.0
        }

        rows = flatten_invoice_payload(payload)
        df_rows = pd.DataFrame(rows)

        # 1. Write Parquet
        write_parquet(df_rows, parquet_file)
        assert os.path.exists(parquet_file)

        # 2. Read Parquet
        read_df = read_parquet(parquet_file)
        assert len(read_df) == 2
        assert "sentinel_recommended_hsn" in read_df.columns
        assert "sentinel_status_badge" in read_df.columns
        assert "sentinel_audit_reasons" in read_df.columns

        # Item 1 rectified to 85015320
        row1 = read_df[read_df["item_slno"] == "1"].iloc[0]
        assert row1["hsn"] in ["85015320", "85015290"]
        assert row1["sentinel_status_badge"] == "FLAGGED_AND_RECTIFIED"

        # Item 2 verified 94013000 AUTO_APPROVED
        row2 = read_df[read_df["item_slno"] == "2"].iloc[0]
        assert row2["hsn"] == "94013000"
        assert row2["sentinel_status_badge"] == "AUTO_APPROVED"

        # 3. Append to Parquet
        new_row = dict(rows[1])
        new_row["invoice_id"] = "INV-2026-APPEND"
        new_row["line_item_id"] = "INV-2026-APPEND-L01"
        append_to_parquet(pd.DataFrame([new_row]), parquet_file)

        updated_df = read_parquet(parquet_file)
        assert len(updated_df) == 3

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ==============================================================================
# 4. PRE-API VALIDATION & AUTO-CORRECTION INTEGRATION TESTS
# ==============================================================================

def test_pydantic_line_item_rejects_rule_2176():
    """Verifies LineItem validation rejects invalid length or non-statutory HSN with Rule 2176."""
    # Test invalid length (3 digits)
    with pytest.raises((NICValidationError, ValidationError)) as exc_info:
        LineItem(
            slno="1",
            prdnm="industrial servo motor",
            hsn="850",
            qty=1.0,
            unit="NOS",
            unitprice=1000.0,
            totamt=1000.0,
            assval=1000.0,
            gstrate=18.0,
            totitemval=1180.0
        )
    err_str = str(exc_info.value)
    assert "2176" in err_str
    assert "HSN code(s)-850 is invalid" in err_str
    assert "Wrong HSN code is being passed" in err_str
    assert "e-invoice portal" in err_str
    assert "helpdesk" in err_str

    # Test non-statutory code (99999999)
    with pytest.raises((NICValidationError, ValidationError)) as exc_info2:
        LineItem(
            slno="1",
            prdnm="industrial servo motor",
            hsn="99999999",
            qty=1.0,
            unit="NOS",
            unitprice=1000.0,
            totamt=1000.0,
            assval=1000.0,
            gstrate=18.0,
            totitemval=1180.0
        )
    err_str2 = str(exc_info2.value)
    assert "2176" in err_str2
    assert "HSN code(s)-99999999 is invalid" in err_str2


def test_validator_and_rules_engine_flag_rule_2176(valid_invoice_base):
    """Verifies GSTValidator and RulesEngine flag Rule 2176 on raw invalid HSN."""
    bad_payload = {
        "self_gstin": "29ABCDE1234F1Z5",
        "docdt1": {"docno": "INV-2176-ERR", "document_type": "INV", "docdt": "26-10-2026"},
        "trandt1": {"trancatg": "B2B", "reversecharge": "N"},
        "supplierdt1": {"supplier_gstin": "29ABCDE1234F1Z5", "supplier_state": "29", "supplier_pin": "560001"},
        "buyerdt1": {"buyer_gstin": "29XYZAB5678C1Z2", "buyer_pos": "29", "buyer_state": "29", "buyer_pin": "560002"},
        "itemdtls": [
            {
                "slno": "1",
                "prdnm": "industrial servo motor",
                "prddesc": "Servo motor",
                "isservc": "N",
                "hsncd": "99999999",  # Invalid HSN
                "qty": "1.00",
                "uqc": "NOS",
                "unitrate": "1000.00",
                "grossamt": "1000.00",
                "discount": "0.00",
                "assamt": "1000.00",
                "cgstrt": "9.00",
                "cgstamt": "90.00",
                "sgstrt": "9.00",
                "sgstamt": "90.00",
                "igstrt": "0.00",
                "igstamt": "0.00",
                "totitemval": "1180.00"
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

    # GSTValidator check
    errors_val = GSTValidator.validate_invoice(bad_payload)
    err_2176 = [e for e in errors_val if e.get("error_code") == 2176]
    assert len(err_2176) > 0
    assert "HSN code(s)-99999999 is invalid" in err_2176[0]["message"]
    assert "helpdesk for verification" in err_2176[0]["message"] or "helpdesk for verification" in err_2176[0].get("resolution", "")

    # RulesEngine check
    errors_re = RulesEngine.validate_invoice(bad_payload)
    err_re = [e for e in errors_re if e.get("error_code") == 2176]
    assert len(err_re) > 0
    assert "HSN code(s)-99999999 is invalid" in err_re[0]["message"]


def test_auto_correct_and_build_self_heals_rule_2176(valid_invoice_base):
    """Verifies InvoicePayload.auto_correct_and_build heals invalid HSN with official Rule 2176 audit log."""
    dirty = dict(valid_invoice_base)
    dirty["itemdtls"] = [
        {
            "slno": "1",
            "prdnm": "industrial servo motor",
            "prddesc": "AC servo drive motor",
            "hsn": "99999999",  # Invalid
            "qty": "2.00",
            "unit": "NOS",
            "unitprice": "5000.00",
            "totamt": "10000.00",
            "assval": "10000.00",
            "gstrate": "18.00",
            "cgstval": "900.00",
            "sgstval": "900.00",
            "totitemval": "11800.00"
        }
    ]

    model, audit_log = InvoicePayload.auto_correct_and_build(dirty)
    assert model.itemdtls[0].hsn.startswith("85015")
    assert len(audit_log) > 0

    hsn_entries = [c for c in audit_log if "hsn" in str(c.get("field", "")).lower()]
    assert len(hsn_entries) > 0
    assert any("Rule 2176 Violation" in c["description"] for c in hsn_entries)
    assert any("helpdesk for verification" in c["description"] for c in hsn_entries)
