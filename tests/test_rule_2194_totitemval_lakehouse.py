"""
Tests for Indian GST e-Invoicing (NIC / IRP) Statutory Compliance & Data Lakehouse:
- Error Code 2194: Total Item Value Formula Mismatch
  Formula: ItemList[i].TotItemVal = AssAmt + CgstAmt + SgstAmt + IgstAmt + CesAmt + CesNonAdvlAmt + StateCesAmt + StateCesNonAdvlAmt + OthChrg
  Permitted tolerance: +/- 1.00

Covers all 5 statutory scenarios:
1. Tax Left Out of Item Total:
   AssAmt = 10000.00, IgstAmt = 1800.00 -> TotItemVal = 10000.00 (Failing), Correct = 11800.00.
2. Gross Total (TotAmt) Used When Discount Exists:
   TotAmt = 1000.00, Discount = 100.00, AssAmt = 900.00, IgstAmt = 162.00 -> TotItemVal = 1162.00 (Failing), Correct = 1062.00.
3. Line-Level Other Charges (OthChrg) Omitted:
   AssAmt = 5000.00, IgstAmt = 900.00, OthChrg = 150.00 -> TotItemVal = 5900.00 (Failing), Correct = 6050.00.
4. Cess Amounts Not Included:
   AssAmt = 100000.00, IgstAmt = 28000.00, CesAmt = 12000.00 -> TotItemVal = 128000.00 (Failing), Correct = 140000.00.
5. Decimal / Paise Rounding Discrepancy (> ₹1.00):
   Item sum = 1180.85, but ERP sends TotItemVal = 1182.00 (Failing, diff 1.15 > 1.00), Correct = 1180.85.

Also validates:
- Standalone diagnostic classifiers (classify_rule_2194_diagnostic).
- Pre-API validator (GSTValidator & RulesEngine) error code mapping.
- Pydantic InvoicePayload strict rejection with NICValidationError(2194).
- InvoicePayload.auto_correct_and_build auto-rectification and audit trail logging.
- Data Lakehouse flattening (flatten_invoice_payload) with Sentinel ML telemetry.
- PyArrow Parquet storage round-trip (write, read, append) adhering to FLATTENED_INVOICE_SCHEMA.
"""

import os
import shutil
import tempfile
from decimal import Decimal
from pathlib import Path
import pytest
import pandas as pd

from src.ingestion.schemas import (
    InvoicePayload,
    LineItem,
    classify_rule_2194_diagnostic,
    NICValidationError,
)
from src.ingestion.storage import (
    flatten_invoice_payload,
    write_parquet,
    read_parquet,
    append_to_parquet,
    FLATTENED_INVOICE_SCHEMA,
)
from Template_Converters.validator import GSTValidator
from src.rules.rules_engine import RulesEngine


# ==============================================================================
# FIXTURES FOR ALL 5 STATUTORY SCENARIOS
# ==============================================================================

@pytest.fixture
def failing_2194_scenario_1_tax_left_out():
    """Scenario 1: Tax Left Out of Item Total (AssAmt=10000.00, IgstAmt=1800.00, TotItemVal=10000.00 instead of 11800.00)."""
    return {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-26-2194-SC1",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "B2B",
        "reversecharge": "N",
        "igstonintra": "N",
        "supplier": {
            "gstin": "27ABCDE1234F1Z5",
            "lglnm": "Maharashtra Industrial Tools Corp",
            "state": "27",
            "pin": "400001",
            "loc": "Mumbai"
        },
        "buyer": {
            "gstin": "29XYZAB9876C1Z1",
            "lglnm": "Karnataka Heavy Machinery Ltd",
            "state": "29",
            "pos": "29",
            "pin": "560001",
            "loc": "Bengaluru"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "High Torque Spindle Motor",
                "prddesc": "CNC tooling equipment",
                "hsn": "8466",
                "qty": 1.0,
                "unit": "NOS",
                "unitprice": 10000.00,
                "totamt": 10000.00,
                "discount": 0.00,
                "assval": 10000.00,
                "gstrate": 18.0,
                "cgstval": 0.0,
                "sgstval": 0.0,
                "igstval": 1800.00,
                "totitemval": 10000.00  # Failing: taxes omitted from total item value
            }
        ],
        "valdtls": {
            "AssVal": 10000.00,
            "CgstVal": 0.0,
            "SgstVal": 0.0,
            "IgstVal": 1800.00,
            "CesVal": 0.0,
            "Discount": 0.0,
            "RndOffAmt": 0.0,
            "TotInvVal": 11800.00
        }
    }


@pytest.fixture
def failing_2194_scenario_2_gross_total_used():
    """Scenario 2: Gross Total (TotAmt) Used When Discount Exists (TotAmt=1000.00, Disc=100.00, AssAmt=900.00, Igst=162.00, TotItemVal=1162.00 instead of 1062.00)."""
    return {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-26-2194-SC2",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "B2B",
        "reversecharge": "N",
        "igstonintra": "N",
        "supplier": {
            "gstin": "27ABCDE1234F1Z5",
            "lglnm": "Maharashtra Industrial Tools Corp",
            "state": "27",
            "pin": "400001",
            "loc": "Mumbai"
        },
        "buyer": {
            "gstin": "29XYZAB9876C1Z1",
            "lglnm": "Karnataka Heavy Machinery Ltd",
            "state": "29",
            "pos": "29",
            "pin": "560001",
            "loc": "Bengaluru"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "Precision Milling Cutters",
                "prddesc": "Milling tooling",
                "hsn": "8207",
                "qty": 1.0,
                "unit": "NOS",
                "unitprice": 1000.00,
                "totamt": 1000.00,
                "discount": 100.00,
                "assval": 900.00,
                "gstrate": 18.0,
                "cgstval": 0.0,
                "sgstval": 0.0,
                "igstval": 162.00,
                "totitemval": 1162.00  # Failing: derived from pre-discount 1000 + 162 instead of 900 + 162 = 1062
            }
        ],
        "valdtls": {
            "AssVal": 900.00,
            "CgstVal": 0.0,
            "SgstVal": 0.0,
            "IgstVal": 162.00,
            "CesVal": 0.0,
            "Discount": 0.0,
            "RndOffAmt": 0.0,
            "TotInvVal": 1062.00
        }
    }


@pytest.fixture
def failing_2194_scenario_3_line_othchrg_omitted():
    """Scenario 3: Line-Level Other Charges (OthChrg) Omitted (AssAmt=5000.00, Igst=900.00, OthChrg=150.00, TotItemVal=5900.00 instead of 6050.00)."""
    return {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-26-2194-SC3",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "B2B",
        "reversecharge": "N",
        "igstonintra": "N",
        "supplier": {
            "gstin": "27ABCDE1234F1Z5",
            "lglnm": "Maharashtra Industrial Tools Corp",
            "state": "27",
            "pin": "400001",
            "loc": "Mumbai"
        },
        "buyer": {
            "gstin": "29XYZAB9876C1Z1",
            "lglnm": "Karnataka Heavy Machinery Ltd",
            "state": "29",
            "pos": "29",
            "pin": "560001",
            "loc": "Bengaluru"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "Industrial Bearing Assembly",
                "prddesc": "Precision ball bearings",
                "hsn": "8482",
                "qty": 5.0,
                "unit": "NOS",
                "unitprice": 1000.00,
                "totamt": 5000.00,
                "discount": 0.00,
                "assval": 5000.00,
                "gstrate": 18.0,
                "cgstval": 0.0,
                "sgstval": 0.0,
                "igstval": 900.00,
                "othchrg": 150.00,
                "totitemval": 5900.00  # Failing: packaging/other charges omitted from TotItemVal (5000 + 900 = 5900 instead of 6050)
            }
        ],
        "valdtls": {
            "AssVal": 5000.00,
            "CgstVal": 0.0,
            "SgstVal": 0.0,
            "IgstVal": 900.00,
            "CesVal": 0.0,
            "OthChrg": 150.00,
            "Discount": 0.0,
            "RndOffAmt": 0.0,
            "TotInvVal": 6050.00
        }
    }


@pytest.fixture
def failing_2194_scenario_4_cess_amounts_not_included():
    """Scenario 4: Cess Amounts Not Included (AssAmt=100000.00, Igst=28000.00, CesAmt=12000.00, TotItemVal=128000.00 instead of 140000.00)."""
    return {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-26-2194-SC4",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "B2B",
        "reversecharge": "N",
        "igstonintra": "N",
        "supplier": {
            "gstin": "27ABCDE1234F1Z5",
            "lglnm": "Maharashtra Industrial Tools Corp",
            "state": "27",
            "pin": "400001",
            "loc": "Mumbai"
        },
        "buyer": {
            "gstin": "29XYZAB9876C1Z1",
            "lglnm": "Karnataka Heavy Machinery Ltd",
            "state": "29",
            "pos": "29",
            "pin": "560001",
            "loc": "Bengaluru"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "Luxury High-End Motor Car Component",
                "prddesc": "Automotive luxury assembly",
                "hsn": "8703",
                "qty": 1.0,
                "unit": "NOS",
                "unitprice": 100000.00,
                "totamt": 100000.00,
                "discount": 0.00,
                "assval": 100000.00,
                "gstrate": 28.0,
                "cgstval": 0.0,
                "sgstval": 0.0,
                "igstval": 28000.00,
                "cesrate": 12.0,
                "cesval": 12000.00,
                "totitemval": 128000.00  # Failing: Cess omitted from TotItemVal (100000 + 28000 = 128000 instead of 140000)
            }
        ],
        "valdtls": {
            "AssVal": 100000.00,
            "CgstVal": 0.0,
            "SgstVal": 0.0,
            "IgstVal": 28000.00,
            "CesVal": 12000.00,
            "Discount": 0.0,
            "RndOffAmt": 0.0,
            "TotInvVal": 140000.00
        }
    }


@pytest.fixture
def failing_2194_scenario_5_decimal_rounding_exceeded():
    """Scenario 5: Decimal / Paise Rounding Discrepancy (> ₹1.00) (Calculated=1180.85, Sent TotItemVal=1182.00, diff 1.15 > 1.00)."""
    return {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-26-2194-SC5",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "B2B",
        "reversecharge": "N",
        "igstonintra": "N",
        "supplier": {
            "gstin": "27ABCDE1234F1Z5",
            "lglnm": "Maharashtra Industrial Tools Corp",
            "state": "27",
            "pin": "400001",
            "loc": "Mumbai"
        },
        "buyer": {
            "gstin": "29XYZAB9876C1Z1",
            "lglnm": "Karnataka Heavy Machinery Ltd",
            "state": "29",
            "pos": "29",
            "pin": "560001",
            "loc": "Bengaluru"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "Precision Gauging Sensor",
                "prddesc": "Calibration sensor",
                "hsn": "9031",
                "qty": 1.0,
                "unit": "NOS",
                "unitprice": 1000.72,
                "totamt": 1000.72,
                "discount": 0.00,
                "assval": 1000.72,
                "gstrate": 18.0,
                "cgstval": 0.0,
                "sgstval": 0.0,
                "igstval": 180.13,
                "totitemval": 1182.00  # Failing: ERP sends 1182.00 when sum is 1180.85 (deviation 1.15 exceeds ±1.00)
            }
        ],
        "valdtls": {
            "AssVal": 1000.72,
            "CgstVal": 0.0,
            "SgstVal": 0.0,
            "IgstVal": 180.13,
            "CesVal": 0.0,
            "Discount": 0.0,
            "RndOffAmt": 0.0,
            "TotInvVal": 1180.85
        }
    }


@pytest.fixture
def valid_rule_2194_invoice():
    """Compliant invoice payload passing all Rule 2194 item value reconciliations."""
    return {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-26-2194-OK",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "B2B",
        "reversecharge": "N",
        "igstonintra": "N",
        "supplier": {
            "gstin": "27ABCDE1234F1Z5",
            "lglnm": "Maharashtra Industrial Tools Corp",
            "state": "27",
            "pin": "400001",
            "loc": "Mumbai"
        },
        "buyer": {
            "gstin": "29XYZAB9876C1Z1",
            "lglnm": "Karnataka Heavy Machinery Ltd",
            "state": "29",
            "pos": "29",
            "pin": "560001",
            "loc": "Bengaluru"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "Precision Drill Bit Set",
                "prddesc": "Industrial cutting tools",
                "hsn": "8207",
                "qty": 10.0,
                "unit": "SET",
                "unitprice": 100.00,
                "totamt": 1000.00,
                "discount": 50.00,
                "assval": 950.00,
                "gstrate": 18.0,
                "cgstval": 0.0,
                "sgstval": 0.0,
                "igstval": 171.00,
                "othchrg": 20.00,
                "totitemval": 1141.00  # Valid: 950.00 + 171.00 + 20.00 = 1141.00
            },
            {
                "item_slno": "2",
                "slno": "2",
                "prdnm": "Heavy Duty Bench Grinder",
                "prddesc": "Power tool machinery",
                "hsn": "8460",
                "qty": 1.0,
                "unit": "NOS",
                "unitprice": 2000.00,
                "totamt": 2000.00,
                "discount": 0.0,
                "assval": 2000.00,
                "gstrate": 18.0,
                "cgstval": 0.0,
                "sgstval": 0.0,
                "igstval": 360.00,
                "totitemval": 2360.50  # Valid: within allowed ±1.00 tolerance (2360.00 + 0.50)
            }
        ],
        "valdtls": {
            "AssVal": 2950.00,
            "CgstVal": 0.0,
            "SgstVal": 0.0,
            "IgstVal": 531.00,
            "CesVal": 0.0,
            "OthChrg": 20.00,
            "Discount": 0.0,
            "RndOffAmt": 0.50,
            "TotInvVal": 3501.50
        }
    }


# ==============================================================================
# 1. DIAGNOSTIC CLASSIFICATION TESTS
# ==============================================================================

def test_classify_rule_2194_scenarios_standalone():
    """Verify classify_rule_2194_diagnostic classifies all 5 scenarios with exact statutory messages."""
    # Scenario 1: Tax Left Out of Item Total
    res1 = classify_rule_2194_diagnostic(
        totitemval=10000.00,
        assamt=10000.00,
        igstamt=1800.00
    )
    assert not res1["is_valid"]
    assert res1["scenario"] == "TAX_LEFT_OUT_OF_ITEM_TOTAL"
    assert "post-tax gross item total" in res1["reason"]
    assert res1["correct_payload"]["TotItemVal"] == Decimal("11800.00")

    # Scenario 2: Gross Total (TotAmt) Used When Discount Exists
    res2 = classify_rule_2194_diagnostic(
        totitemval=1162.00,
        assamt=900.00,
        totamt=1000.00,
        discount=100.00,
        igstamt=162.00
    )
    assert not res2["is_valid"]
    assert res2["scenario"] == "GROSS_TOTAL_USED_WHEN_DISCOUNT_EXISTS"
    assert "must be derived from AssAmt" in res2["reason"]
    assert res2["correct_payload"]["TotItemVal"] == Decimal("1062.00")

    # Scenario 3: Line-Level Other Charges (OthChrg) Omitted
    res3 = classify_rule_2194_diagnostic(
        totitemval=5900.00,
        assamt=5000.00,
        igstamt=900.00,
        othchrg=150.00
    )
    assert not res3["is_valid"]
    assert res3["scenario"] == "LINE_LEVEL_OTHER_CHARGES_OMITTED"
    assert "charges in OthChrg must be added" in res3["reason"]
    assert res3["correct_payload"]["TotItemVal"] == Decimal("6050.00")

    # Scenario 4: Cess Amounts Not Included
    res4 = classify_rule_2194_diagnostic(
        totitemval=128000.00,
        assamt=100000.00,
        igstamt=28000.00,
        cesamt=12000.00
    )
    assert not res4["is_valid"]
    assert res4["scenario"] == "CESS_AMOUNTS_NOT_INCLUDED"
    assert "Both ad-valorem Cess" in res4["reason"]
    assert res4["correct_payload"]["TotItemVal"] == Decimal("140000.00")

    # Scenario 5: Decimal / Paise Rounding Discrepancy (> ₹1.00)
    res5 = classify_rule_2194_diagnostic(
        totitemval=1182.00,
        assamt=1000.72,
        igstamt=180.13
    )
    assert not res5["is_valid"]
    assert res5["scenario"] == "DECIMAL_PAISE_ROUNDING_DISCREPANCY"
    assert "tolerance is strictly ±1.00" in res5["reason"]
    assert res5["correct_payload"]["TotItemVal"] == Decimal("1180.85")

    # Valid check: within ±1.00 tolerance
    res_valid = classify_rule_2194_diagnostic(
        totitemval=1181.00,
        assamt=1000.72,
        igstamt=180.13
    )
    assert res_valid["is_valid"]
    assert res_valid["scenario"] == "VALID"
    assert res_valid["totitemval"] == Decimal("1181.00")


# ==============================================================================
# 2. PRE-API VALIDATOR TESTS (GSTValidator & RulesEngine)
# ==============================================================================

def test_pre_api_validator_rejects_2194_scenarios(
    failing_2194_scenario_1_tax_left_out,
    failing_2194_scenario_2_gross_total_used,
    failing_2194_scenario_3_line_othchrg_omitted,
    failing_2194_scenario_4_cess_amounts_not_included,
    failing_2194_scenario_5_decimal_rounding_exceeded
):
    """Ensure GSTValidator and RulesEngine reject all 5 Rule 2194 scenarios with error code 2194."""
    scenarios = [
        failing_2194_scenario_1_tax_left_out,
        failing_2194_scenario_2_gross_total_used,
        failing_2194_scenario_3_line_othchrg_omitted,
        failing_2194_scenario_4_cess_amounts_not_included,
        failing_2194_scenario_5_decimal_rounding_exceeded,
    ]

    for sc in scenarios:
        val_errors = GSTValidator.validate_invoice(sc)
        assert any(e.get("error_code") == 2194 for e in val_errors), f"GSTValidator failed to flag 2194 for {sc['docno']}"

        eng_errors = RulesEngine.validate_invoice(sc)
        assert any(e.get("error_code") == 2194 for e in eng_errors), f"RulesEngine failed to flag 2194 for {sc['docno']}"


# ==============================================================================
# 3. PYDANTIC MODEL VALIDATION TESTS
# ==============================================================================

def test_pydantic_model_rejects_2194_mismatches(
    failing_2194_scenario_1_tax_left_out,
    failing_2194_scenario_2_gross_total_used,
    failing_2194_scenario_3_line_othchrg_omitted,
    failing_2194_scenario_4_cess_amounts_not_included,
    failing_2194_scenario_5_decimal_rounding_exceeded
):
    """Ensure Pydantic InvoicePayload & LineItem strictly raise validation error 2194 on non-compliant payloads."""
    scenarios = [
        failing_2194_scenario_1_tax_left_out,
        failing_2194_scenario_2_gross_total_used,
        failing_2194_scenario_3_line_othchrg_omitted,
        failing_2194_scenario_4_cess_amounts_not_included,
        failing_2194_scenario_5_decimal_rounding_exceeded,
    ]

    for sc in scenarios:
        with pytest.raises(Exception) as excinfo:
            InvoicePayload.model_validate(sc)
        assert "2194" in str(excinfo.value), f"Expected 2194 in exception message for {sc['docno']}"

        with pytest.raises(Exception) as excinfo_line:
            LineItem.model_validate(sc["itemdtls"][0])
        assert "2194" in str(excinfo_line.value)


# ==============================================================================
# 4. AUTO-CORRECTION AND AUDIT TRAIL LOGGING TESTS
# ==============================================================================

def test_auto_correct_and_build_rectifies_2194_scenarios(
    failing_2194_scenario_1_tax_left_out,
    failing_2194_scenario_2_gross_total_used,
    failing_2194_scenario_3_line_othchrg_omitted,
    failing_2194_scenario_4_cess_amounts_not_included,
    failing_2194_scenario_5_decimal_rounding_exceeded
):
    """Ensure InvoicePayload.auto_correct_and_build rectifies TotItemVal and records audit trail entries."""
    scenarios_expected = [
        (failing_2194_scenario_1_tax_left_out, Decimal("11800.00"), "TAX_LEFT_OUT_OF_ITEM_TOTAL"),
        (failing_2194_scenario_2_gross_total_used, Decimal("1062.00"), "GROSS_TOTAL_USED_WHEN_DISCOUNT_EXISTS"),
        (failing_2194_scenario_3_line_othchrg_omitted, Decimal("6050.00"), "LINE_LEVEL_OTHER_CHARGES_OMITTED"),
        (failing_2194_scenario_4_cess_amounts_not_included, Decimal("140000.00"), "CESS_AMOUNTS_NOT_INCLUDED"),
        (failing_2194_scenario_5_decimal_rounding_exceeded, Decimal("1180.85"), "DECIMAL_PAISE_ROUNDING_DISCREPANCY"),
    ]

    for sc, expected_val, expected_scen in scenarios_expected:
        model, audit_log = InvoicePayload.auto_correct_and_build(sc)
        assert model is not None, f"Failed to auto-correct {sc['docno']}"

        # Verify audit log
        log_entry = next((e for e in audit_log if e["category"] == "RULE_2194_TOTITEMVAL_RECONCILIATION"), None)
        assert log_entry is not None, f"No Rule 2194 audit entry found for {sc['docno']}"
        assert log_entry["scenario"] == expected_scen
        assert log_entry["corrected"] == str(expected_val)

        # Verify model value
        assert Decimal(str(model.itemdtls[0].totitemval)) == expected_val


# ==============================================================================
# 5. DATA LAKEHOUSE FLATTENING & SENTINEL TELEMETRY TESTS
# ==============================================================================

def test_flatten_invoice_payload_dict_rectifies_2194(
    failing_2194_scenario_1_tax_left_out,
    failing_2194_scenario_2_gross_total_used,
    failing_2194_scenario_3_line_othchrg_omitted,
    failing_2194_scenario_4_cess_amounts_not_included,
    failing_2194_scenario_5_decimal_rounding_exceeded
):
    """Ensure flatten_invoice_payload (dict branch) rectifies TotItemVal and assigns Sentinel risk telemetry."""
    scenarios_expected = [
        (failing_2194_scenario_1_tax_left_out, 11800.00),
        (failing_2194_scenario_2_gross_total_used, 1062.00),
        (failing_2194_scenario_3_line_othchrg_omitted, 6050.00),
        (failing_2194_scenario_4_cess_amounts_not_included, 140000.00),
        (failing_2194_scenario_5_decimal_rounding_exceeded, 1180.85),
    ]

    for sc, expected_val in scenarios_expected:
        rows = flatten_invoice_payload(sc)
        assert len(rows) == 1
        row = rows[0]
        assert row["sentinel_status_badge"] == "FLAGGED_AND_RECTIFIED"
        assert row["sentinel_risk_level"] == "HIGH"
        assert row["sentinel_risk_prob"] >= 0.95
        assert "Rule 2194 Violation" in row["sentinel_audit_reasons"]
        assert row["total_item_value"] == expected_val


def test_flatten_invoice_payload_model_rectifies_2194(
    failing_2194_scenario_1_tax_left_out,
    failing_2194_scenario_3_line_othchrg_omitted
):
    """Ensure flatten_invoice_payload (Pydantic model branch) handles models cleanly."""
    model1, _ = InvoicePayload.auto_correct_and_build(failing_2194_scenario_1_tax_left_out)
    rows1 = flatten_invoice_payload(model1)
    assert len(rows1) == 1
    assert rows1[0]["total_item_value"] == 11800.00

    model3, _ = InvoicePayload.auto_correct_and_build(failing_2194_scenario_3_line_othchrg_omitted)
    rows3 = flatten_invoice_payload(model3)
    assert len(rows3) == 1
    assert rows3[0]["total_item_value"] == 6050.00


# ==============================================================================
# 6. PYARROW PARQUET STORAGE ROUND-TRIP TESTS
# ==============================================================================

def test_lakehouse_parquet_persistence_roundtrip(
    valid_rule_2194_invoice,
    failing_2194_scenario_1_tax_left_out,
    failing_2194_scenario_3_line_othchrg_omitted
):
    """Verify PyArrow Parquet storage round-trip (write, read, append) preserves all columns under FLATTENED_INVOICE_SCHEMA."""
    temp_dir = tempfile.mkdtemp()
    parquet_path = os.path.join(temp_dir, "test_rule_2194.parquet")

    try:
        # 1. Flatten valid invoice
        rows_valid = flatten_invoice_payload(valid_rule_2194_invoice)
        write_parquet(rows_valid, parquet_path)
        assert os.path.exists(parquet_path)

        # Read back and verify columns
        df1 = read_parquet(parquet_path)
        assert len(df1) == 2
        assert set(FLATTENED_INVOICE_SCHEMA.names).issubset(set(df1.columns))

        # 2. Append rectified rows
        rows_sc1 = flatten_invoice_payload(failing_2194_scenario_1_tax_left_out)
        rows_sc3 = flatten_invoice_payload(failing_2194_scenario_3_line_othchrg_omitted)
        append_to_parquet(rows_sc1, parquet_path)
        append_to_parquet(rows_sc3, parquet_path)

        df2 = read_parquet(parquet_path)
        assert len(df2) == 4  # 2 + 1 + 1

        sc1_row = df2[df2["invoice_id"] == "INV-26-2194-SC1"].iloc[0]
        assert sc1_row["total_item_value"] == 11800.00
        assert sc1_row["sentinel_status_badge"] == "FLAGGED_AND_RECTIFIED"

        sc3_row = df2[df2["invoice_id"] == "INV-26-2194-SC3"].iloc[0]
        assert sc3_row["total_item_value"] == 6050.00
        assert sc3_row["other_charges"] == 150.00
        assert sc3_row["sentinel_status_badge"] == "FLAGGED_AND_RECTIFIED"

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ==============================================================================
# 7. VALID INVOICE COMPLIANCE TESTS
# ==============================================================================

def test_valid_invoice_clean_pass(valid_rule_2194_invoice):
    """Verify fully compliant invoice passes all validators and lakehouse flattening without Rule 2194 flags."""
    # Pre-API validators
    val_errs = GSTValidator.validate_invoice(valid_rule_2194_invoice)
    assert not any(e.get("error_code") == 2194 for e in val_errs)

    eng_errs = RulesEngine.validate_invoice(valid_rule_2194_invoice)
    assert not any(e.get("error_code") == 2194 for e in eng_errs)

    # Pydantic Model
    model = InvoicePayload(**valid_rule_2194_invoice)
    assert model.docno == "INV-26-2194-OK"

    # Auto-correct should not generate any Rule 2194 violations
    _, audit_log = InvoicePayload.auto_correct_and_build(valid_rule_2194_invoice)
    assert not any(e["category"] == "RULE_2194_TOTITEMVAL_RECONCILIATION" for e in audit_log)

    # Lakehouse Flattening
    rows = flatten_invoice_payload(valid_rule_2194_invoice)
    assert len(rows) == 2
    for r in rows:
        assert r["sentinel_status_badge"] in ("AUTO_APPROVED", "VERIFIED", "FLAGGED_AND_RECTIFIED")
        assert "Rule 2194" not in r["sentinel_audit_reasons"]

    assert rows[0]["total_item_value"] == 1141.00
    assert rows[1]["total_item_value"] == 2360.50
