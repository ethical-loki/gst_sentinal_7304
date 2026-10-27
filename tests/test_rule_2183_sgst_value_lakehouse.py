"""
Test Suite: NIC Error Code 2183 Statutory Compliance & Data Lakehouse SGST Value Module.
File: tests/test_rule_2183_sgst_value_lakehouse.py

Validates Indian GST e-Invoicing (NIC / IRP) Error Code 2183:
"SGST value of all items is not equal to total SGST Value"
The IRP schema strictly validates:
    ValDtls.SgstVal = sum(ItemList[i].SgstAmt)
If there is any difference between the sum of line items and the header value—even by a single paisa—
the payload is rejected.

Tests all 5 Statutory Scenarios directly within schemas, rules engine, and Data Lakehouse (src/ingestion/storage.py):
1. Header Not Recalculated After Item Edits:
   Item 1: SgstAmt = 900.00, Item 2: SgstAmt = 450.00
   Sent: ValDtls: { SgstVal: 900.00 }
   Correct: ValDtls: { SgstVal: 1350.00 }
   Fix / Reason: "Ensure ValDtls.SgstVal dynamically computes the sum of all ItemList[i].SgstAmt ($900.00 + 450.00 = 1350.00$)."

2. Decimal / Paise Rounding Mismatch:
   Item 1: SgstAmt = 41.67, Item 2: SgstAmt = 41.67, Item 3: SgstAmt = 41.67
   Sent: ValDtls: { SgstVal: 125.00 }
   Correct: ValDtls: { SgstVal: 125.01 } (or adjust line 3 SgstAmt = 41.66)
   Fix / Reason: "Sum of item SgstAmt is $125.01$, but header total was rounded to $125.00$. Line-item sum and SgstVal must match to 2 decimal places."

3. Combined Tax Passed as Single Value:
   Intra-state 18% supply (AssAmt = 10000.00). Line items split CgstAmt = 900.00, SgstAmt = 900.00.
   Sent: ValDtls: { SgstVal: 1800.00 }
   Correct: ValDtls: { CgstVal: 900.00, SgstVal: 900.00 }
   Fix / Reason: "The full 18% tax was placed entirely under SGST at the header instead of splitting it equally between CGST and SGST."

4. Item Level Populated, Header Left as 0 or Null:
   Items have valid SgstAmt amounts, but header has:
   Sent: ValDtls: { SgstVal: 0.00 } or null
   Correct: ValDtls: { SgstVal: <Sum SgstAmt of items> }
   Fix / Reason: "Header tax values in ValDtls are mandatory for intra-state supplies. SgstVal cannot be 0.00 if line items have positive SGST."

5. Inter-State Transaction Passing SGST:
   Inter-state supply (IgstVal applicable), but ERP populated partial SGST values at item level or header level.
   Sent: Inter-state transaction carrying SgstAmt or SgstVal > 0.
   Correct: Clear both item-level SgstAmt and ValDtls.SgstVal to 0.00 and pass the tax under IgstAmt / IgstVal.
   Fix / Reason: "Inter-state transactions must not carry SGST amounts."

Also tests:
- Parquet storage round-trip (write_parquet, read_parquet, append_to_parquet)
- Schema conformance to FLATTENED_INVOICE_SCHEMA
- Dict payload and Pydantic InvoicePayload model branches
- Sentinel ML Telemetry: status_badge="FLAGGED_AND_RECTIFIED", risk_level="HIGH", risk_prob >= 0.95
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
    classify_rule_2183_diagnostic,
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
def failing_scenario_1_stale_sgst_header():
    """Scenario 1: Header Not Recalculated After Item Edits (900.00 + 450.00 -> 1350.00, Header has 900.00)."""
    return {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-26-2183-SC1",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "B2B",
        "reversecharge": "N",
        "igstonintra": "N",
        "supplier": {
            "gstin": "27ABCDE1234F1Z5",
            "lglnm": "Maharashtra Industrial Tools Ltd",
            "state": "27",
            "pin": "400001",
            "loc": "Mumbai"
        },
        "buyer": {
            "gstin": "27XYZAB9876C1Z1",
            "lglnm": "Maharashtra Heavy Machines Ltd",
            "state": "27",
            "pos": "27",
            "pin": "411001",
            "loc": "Pune"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "Precision Lathe Tool Bit",
                "prddesc": "High Speed Steel Bit",
                "hsn": "8207",
                "qty": 10.0,
                "unit": "NOS",
                "unitprice": 1000.0,
                "totamt": 10000.0,
                "discount": 0.0,
                "assval": 10000.0,
                "gstrate": 18.0,
                "cgstval": 900.0,
                "sgstval": 900.0,
                "igstval": 0.0,
                "totitemval": 11800.0
            },
            {
                "item_slno": "2",
                "slno": "2",
                "prdnm": "Carbide End Mill Cutter",
                "prddesc": "4 Flute End Mill",
                "hsn": "8207",
                "qty": 5.0,
                "unit": "NOS",
                "unitprice": 1000.0,
                "totamt": 5000.0,
                "discount": 0.0,
                "assval": 5000.0,
                "gstrate": 18.0,
                "cgstval": 450.0,
                "sgstval": 450.0,
                "igstval": 0.0,
                "totitemval": 5900.0
            }
        ],
        "valdtls": {
            "AssVal": 15000.0,
            "CgstVal": 1350.0,
            "SgstVal": 900.0,  # Failing: Stale header total (900.00 instead of 1350.00)
            "IgstVal": 0.0,
            "CesVal": 0.0,
            "Discount": 0.0,
            "RndOffAmt": 0.0,
            "TotInvVal": 17250.0
        }
    }


@pytest.fixture
def failing_scenario_2_paise_rounding_mismatch():
    """Scenario 2: Decimal / Paise Rounding Mismatch (41.67 x 3 = 125.01, Header has 125.00)."""
    return {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-26-2183-SC2",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "B2B",
        "reversecharge": "N",
        "igstonintra": "N",
        "supplier": {
            "gstin": "27ABCDE1234F1Z5",
            "lglnm": "Maharashtra Components Corp",
            "state": "27",
            "pin": "400001",
            "loc": "Mumbai"
        },
        "buyer": {
            "gstin": "27XYZAB9876C1Z1",
            "lglnm": "Maharashtra Assembly Works",
            "state": "27",
            "pos": "27",
            "pin": "411001",
            "loc": "Pune"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "Micro Spring Steel Clip A",
                "prddesc": "Precision Clip Grade 1",
                "hsn": "7320",
                "qty": 1.0,
                "unit": "NOS",
                "unitprice": 462.96,
                "totamt": 462.96,
                "discount": 0.0,
                "assval": 462.96,
                "gstrate": 18.0,
                "cgstval": 41.67,
                "sgstval": 41.67,
                "igstval": 0.0,
                "totitemval": 546.30
            },
            {
                "item_slno": "2",
                "slno": "2",
                "prdnm": "Micro Spring Steel Clip B",
                "prddesc": "Precision Clip Grade 2",
                "hsn": "7320",
                "qty": 1.0,
                "unit": "NOS",
                "unitprice": 462.96,
                "totamt": 462.96,
                "discount": 0.0,
                "assval": 462.96,
                "gstrate": 18.0,
                "cgstval": 41.67,
                "sgstval": 41.67,
                "igstval": 0.0,
                "totitemval": 546.30
            },
            {
                "item_slno": "3",
                "slno": "3",
                "prdnm": "Micro Spring Steel Clip C",
                "prddesc": "Precision Clip Grade 3",
                "hsn": "7320",
                "qty": 1.0,
                "unit": "NOS",
                "unitprice": 462.96,
                "totamt": 462.96,
                "discount": 0.0,
                "assval": 462.96,
                "gstrate": 18.0,
                "cgstval": 41.67,
                "sgstval": 41.67,
                "igstval": 0.0,
                "totitemval": 546.30
            }
        ],
        "valdtls": {
            "AssVal": 1388.88,
            "CgstVal": 125.01,
            "SgstVal": 125.00,  # Failing: Rounded down to 125.00 instead of 125.01
            "IgstVal": 0.0,
            "CesVal": 0.0,
            "Discount": 0.0,
            "RndOffAmt": 0.0,
            "TotInvVal": 1638.89
        }
    }


@pytest.fixture
def failing_scenario_3_combined_tax_under_sgst():
    """Scenario 3: Combined Tax Passed as Single Value (18% tax 1800.00 passed under SgstVal alone)."""
    return {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-26-2183-SC3",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "B2B",
        "reversecharge": "N",
        "igstonintra": "N",
        "supplier": {
            "gstin": "27ABCDE1234F1Z5",
            "lglnm": "Maharashtra Automation Systems",
            "state": "27",
            "pin": "400001",
            "loc": "Mumbai"
        },
        "buyer": {
            "gstin": "27XYZAB9876C1Z1",
            "lglnm": "Maharashtra Processing Plant",
            "state": "27",
            "pos": "27",
            "pin": "411001",
            "loc": "Pune"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "Pneumatic Control Solenoid Valve",
                "prddesc": "24V Solenoid Valve 1/4 inch",
                "hsn": "8481",
                "qty": 5.0,
                "unit": "NOS",
                "unitprice": 2000.0,
                "totamt": 10000.0,
                "discount": 0.0,
                "assval": 10000.0,
                "gstrate": 18.0,
                "cgstval": 900.0,
                "sgstval": 900.0,
                "igstval": 0.0,
                "totitemval": 11800.0
            }
        ],
        "valdtls": {
            "AssVal": 10000.0,
            "CgstVal": 0.0,
            "SgstVal": 1800.0,  # Failing: Full 18% tax placed under SGST instead of splitting
            "IgstVal": 0.0,
            "CesVal": 0.0,
            "Discount": 0.0,
            "RndOffAmt": 0.0,
            "TotInvVal": 11800.0
        }
    }


@pytest.fixture
def failing_scenario_4_item_populated_header_zero():
    """Scenario 4: Item Level Populated, Header Left as 0 or Null (Items have 900.00 SGST, Header has 0.00)."""
    return {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-26-2183-SC4",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "B2B",
        "reversecharge": "N",
        "igstonintra": "N",
        "supplier": {
            "gstin": "27ABCDE1234F1Z5",
            "lglnm": "Maharashtra Electric Drives Ltd",
            "state": "27",
            "pin": "400001",
            "loc": "Mumbai"
        },
        "buyer": {
            "gstin": "27XYZAB9876C1Z1",
            "lglnm": "Maharashtra Motors Manufacturing",
            "state": "27",
            "pos": "27",
            "pin": "411001",
            "loc": "Pune"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "Variable Frequency Drive 5kW",
                "prddesc": "VFD Motor Controller",
                "hsn": "8504",
                "qty": 1.0,
                "unit": "NOS",
                "unitprice": 10000.0,
                "totamt": 10000.0,
                "discount": 0.0,
                "assval": 10000.0,
                "gstrate": 18.0,
                "cgstval": 900.0,
                "sgstval": 900.0,
                "igstval": 0.0,
                "totitemval": 11800.0
            }
        ],
        "valdtls": {
            "AssVal": 10000.0,
            "CgstVal": 900.0,
            "SgstVal": 0.0,  # Failing: Header tax values mandatory, cannot be 0.00
            "IgstVal": 0.0,
            "CesVal": 0.0,
            "Discount": 0.0,
            "RndOffAmt": 0.0,
            "TotInvVal": 10900.0
        }
    }


@pytest.fixture
def failing_scenario_5_inter_state_passing_sgst():
    """Scenario 5: Inter-State Transaction Passing SGST (Supplier MH=27, Buyer KA=29, passing SGST 900.00)."""
    return {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-26-2183-SC5",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "B2B",
        "reversecharge": "N",
        "igstonintra": "N",
        "supplier": {
            "gstin": "27ABCDE1234F1Z5",
            "lglnm": "Maharashtra Exports & Power Ltd",
            "state": "27",
            "pin": "400001",
            "loc": "Mumbai"
        },
        "buyer": {
            "gstin": "29XYZAB9876C1Z1",
            "lglnm": "Karnataka Aerospace Ltd",
            "state": "29",
            "pos": "29",
            "pin": "560001",
            "loc": "Bengaluru"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "Precision Hydraulic Valve",
                "prddesc": "High Pressure Hydraulic Valve",
                "hsn": "8481",
                "qty": 1.0,
                "unit": "NOS",
                "unitprice": 10000.0,
                "totamt": 10000.0,
                "discount": 0.0,
                "assval": 10000.0,
                "gstrate": 18.0,
                "cgstval": 900.0,
                "sgstval": 900.0,  # Failing: Inter-state transaction passing SGST
                "igstval": 0.0,
                "totitemval": 11800.0
            }
        ],
        "valdtls": {
            "AssVal": 10000.0,
            "CgstVal": 900.0,
            "SgstVal": 900.0,  # Failing: Inter-state transaction must not carry SGST
            "IgstVal": 0.0,
            "CesVal": 0.0,
            "Discount": 0.0,
            "RndOffAmt": 0.0,
            "TotInvVal": 11800.0
        }
    }


# ==============================================================================
# 1. STANDALONE DIAGNOSTIC CLASSIFICATION TESTS
# ==============================================================================

def test_diagnostic_scenario_1_stale_header():
    """Verify classification of Scenario 1: Header Not Recalculated After Item Edits."""
    diag = classify_rule_2183_diagnostic(
        header_sgst=Decimal("900.00"),
        sum_item_sgst=Decimal("1350.00"),
        items=[{"SgstAmt": Decimal("900.00")}, {"SgstAmt": Decimal("450.00")}],
        is_inter_state=False
    )
    assert diag["is_valid"] is False
    assert diag["error_code"] == 2183
    assert diag["scenario"] == "HEADER_NOT_RECALCULATED_AFTER_ITEM_EDITS"
    assert diag["scenario_name"] == "Header Not Recalculated After Item Edits"
    assert diag["action"] == "DYNAMICALLY_COMPUTE_HEADER_SGST"
    assert diag["correct_payload"]["ValDtls"]["SgstVal"] == Decimal("1350.00")
    assert "Ensure ValDtls.SgstVal dynamically computes the sum of all ItemList[i].SgstAmt ($900.00 + 450.00 = 1350.00$)." in diag["reason"]


def test_diagnostic_scenario_2_paise_rounding():
    """Verify classification of Scenario 2: Decimal / Paise Rounding Mismatch."""
    diag = classify_rule_2183_diagnostic(
        header_sgst=Decimal("125.00"),
        sum_item_sgst=Decimal("125.01"),
        items=[{"SgstAmt": Decimal("41.67")}, {"SgstAmt": Decimal("41.67")}, {"SgstAmt": Decimal("41.67")}],
        is_inter_state=False
    )
    assert diag["is_valid"] is False
    assert diag["scenario"] == "DECIMAL_PAISE_ROUNDING_MISMATCH"
    assert diag["scenario_name"] == "Decimal / Paise Rounding Mismatch"
    assert diag["action"] == "RECONCILE_PAISE_ROUNDING"
    assert diag["correct_payload"]["ValDtls"]["SgstVal"] == Decimal("125.01")
    assert "Sum of item SgstAmt is $125.01$, but header total was rounded to $125.00$. Line-item sum and SgstVal must match to 2 decimal places." in diag["reason"]


def test_diagnostic_scenario_3_combined_tax():
    """Verify classification of Scenario 3: Combined Tax Passed as Single Value."""
    diag = classify_rule_2183_diagnostic(
        header_sgst=Decimal("1800.00"),
        sum_item_sgst=Decimal("900.00"),
        sum_item_cgst=Decimal("900.00"),
        header_cgst=Decimal("0.00"),
        gst_rate=18.0,
        is_inter_state=False
    )
    assert diag["is_valid"] is False
    assert diag["scenario"] == "COMBINED_TAX_PASSED_AS_SINGLE_VALUE"
    assert diag["scenario_name"] == "Combined Tax Passed as Single Value"
    assert diag["action"] == "SPLIT_TAX_EQUALLY_CGST_SGST"
    assert diag["correct_payload"]["ValDtls"]["CgstVal"] == Decimal("900.00")
    assert diag["correct_payload"]["ValDtls"]["SgstVal"] == Decimal("900.00")
    assert "The full 18% tax was placed entirely under SGST at the header instead of splitting it equally between CGST and SGST." in diag["reason"]


def test_diagnostic_scenario_4_header_zero_or_null():
    """Verify classification of Scenario 4: Item Level Populated, Header Left as 0 or Null."""
    diag = classify_rule_2183_diagnostic(
        header_sgst=Decimal("0.00"),
        sum_item_sgst=Decimal("900.00"),
        is_inter_state=False
    )
    assert diag["is_valid"] is False
    assert diag["scenario"] == "ITEM_LEVEL_POPULATED_HEADER_ZERO_OR_NULL"
    assert diag["scenario_name"] == "Item Level Populated, Header Left as 0 or Null"
    assert diag["action"] == "POPULATE_HEADER_SGST_FROM_ITEMS"
    assert diag["correct_payload"]["ValDtls"]["SgstVal"] == Decimal("900.00")
    assert "Header tax values in ValDtls are mandatory for intra-state supplies. SgstVal cannot be 0.00 if line items have positive SGST." in diag["reason"]


def test_diagnostic_scenario_5_inter_state_passing_sgst():
    """Verify classification of Scenario 5: Inter-State Transaction Passing SGST."""
    diag = classify_rule_2183_diagnostic(
        header_sgst=Decimal("900.00"),
        sum_item_sgst=Decimal("900.00"),
        header_cgst=Decimal("900.00"),
        sum_item_cgst=Decimal("900.00"),
        is_inter_state=True,
        seller_state="27",
        buyer_pos="29"
    )
    assert diag["is_valid"] is False
    assert diag["scenario"] == "INTER_STATE_TRANSACTION_PASSING_SGST"
    assert diag["scenario_name"] == "Inter-State Transaction Passing SGST"
    assert diag["action"] == "CLEAR_SGST_PASS_IGST"
    assert diag["correct_payload"]["ValDtls"]["CgstVal"] == Decimal("0.00")
    assert diag["correct_payload"]["ValDtls"]["SgstVal"] == Decimal("0.00")
    assert diag["correct_payload"]["ValDtls"]["IgstVal"] == Decimal("1800.00")
    assert "Inter-state transactions must not carry SGST amounts. Clear both item-level SgstAmt and ValDtls.SgstVal to 0.00 and pass the tax under IgstAmt / IgstVal." in diag["reason"]


def test_diagnostic_valid_payload():
    """Verify that when header SGST equals item SGST sum, classification is VALID."""
    diag = classify_rule_2183_diagnostic(
        header_sgst=Decimal("1350.00"),
        sum_item_sgst=Decimal("1350.00"),
        is_inter_state=False
    )
    assert diag["is_valid"] is True
    assert diag["scenario"] == "VALID"
    assert diag["action"] == "NONE"


# ==============================================================================
# 2. AUTO-CORRECTION AND BUILD TESTS (InvoicePayload.auto_correct_and_build)
# ==============================================================================

def test_auto_correct_scenario_1_stale_header(failing_scenario_1_stale_sgst_header):
    """Test auto-correction of Scenario 1: updates ValDtls.SgstVal from 900.00 to 1350.00."""
    model, audit_log = InvoicePayload.auto_correct_and_build(failing_scenario_1_stale_sgst_header)
    assert float(model.valdtls.sgstval) == 1350.00
    assert float(model.valdtls.cgstval) == 1350.00
    assert float(model.valdtls.totinvval) == 17700.00
    assert any("Rule 2183" in str(entry) for entry in audit_log)
    assert any("Header Not Recalculated After Item Edits" in str(entry) for entry in audit_log)


def test_auto_correct_scenario_2_paise_rounding(failing_scenario_2_paise_rounding_mismatch):
    """Test auto-correction of Scenario 2: updates ValDtls.SgstVal from 125.00 to 125.01."""
    model, audit_log = InvoicePayload.auto_correct_and_build(failing_scenario_2_paise_rounding_mismatch)
    assert float(model.valdtls.sgstval) == 125.01
    assert any("Rule 2183" in str(entry) for entry in audit_log)
    assert any("Decimal / Paise Rounding Mismatch" in str(entry) for entry in audit_log)


def test_auto_correct_scenario_3_combined_tax(failing_scenario_3_combined_tax_under_sgst):
    """Test auto-correction of Scenario 3: splits 1800.00 into 900.00 CGST and 900.00 SGST."""
    model, audit_log = InvoicePayload.auto_correct_and_build(failing_scenario_3_combined_tax_under_sgst)
    assert float(model.valdtls.cgstval) == 900.00
    assert float(model.valdtls.sgstval) == 900.00
    assert any("Rule 2183" in str(entry) for entry in audit_log)
    assert any("Combined Tax Passed as Single Value" in str(entry) for entry in audit_log)


def test_auto_correct_scenario_4_header_zero(failing_scenario_4_item_populated_header_zero):
    """Test auto-correction of Scenario 4: populates header SgstVal from 0.00 to 900.00."""
    model, audit_log = InvoicePayload.auto_correct_and_build(failing_scenario_4_item_populated_header_zero)
    assert float(model.valdtls.sgstval) == 900.00
    assert any("Rule 2183" in str(entry) for entry in audit_log)
    assert any("Item Level Populated, Header Left as 0 or Null" in str(entry) for entry in audit_log)


def test_auto_correct_scenario_5_inter_state(failing_scenario_5_inter_state_passing_sgst):
    """Test auto-correction of Scenario 5: clears SGST/CGST and moves tax to IGST."""
    model, audit_log = InvoicePayload.auto_correct_and_build(failing_scenario_5_inter_state_passing_sgst)
    assert float(model.valdtls.sgstval) == 0.00
    assert float(model.valdtls.cgstval) == 0.00
    assert float(model.valdtls.igstval) == 1800.00
    assert any("Rule 2183" in str(entry) or "Rule 2174" in str(entry) for entry in audit_log)


# ==============================================================================
# 3. DATA LAKEHOUSE NORMALIZATION & TELEMETRY TESTS (flatten_invoice_payload)
# ==============================================================================

def test_lakehouse_scenario_1_stale_header_rectification(failing_scenario_1_stale_sgst_header):
    """Test Data Lakehouse flattening on Scenario 1: reconciles header to line-item sum 1350.00."""
    rows = flatten_invoice_payload(failing_scenario_1_stale_sgst_header)
    assert len(rows) == 2

    for r in rows:
        assert r["inv_sgst_amount"] == 1350.00
        assert r["inv_cgst_amount"] == 1350.00
        assert r["sentinel_status_badge"] == "FLAGGED_AND_RECTIFIED"
        assert r["sentinel_risk_level"] == "HIGH"
        assert r["sentinel_risk_prob"] >= 0.95
        assert "Rule 2183 Violation (Header Not Recalculated After Item Edits)" in r["sentinel_audit_reasons"]
        assert "Ensure ValDtls.SgstVal dynamically computes the sum of all ItemList[i].SgstAmt" in r["sentinel_audit_reasons"]


def test_lakehouse_scenario_2_paise_rounding_rectification(failing_scenario_2_paise_rounding_mismatch):
    """Test Data Lakehouse flattening on Scenario 2: reconciles header to line-item sum 125.01."""
    rows = flatten_invoice_payload(failing_scenario_2_paise_rounding_mismatch)
    assert len(rows) == 3

    for r in rows:
        assert r["inv_sgst_amount"] == 125.01
        assert r["sentinel_status_badge"] == "FLAGGED_AND_RECTIFIED"
        assert r["sentinel_risk_level"] == "HIGH"
        assert r["sentinel_risk_prob"] >= 0.95
        assert "Rule 2183 Violation (Decimal / Paise Rounding Mismatch)" in r["sentinel_audit_reasons"]
        assert "Sum of item SgstAmt is $125.01$, but header total was rounded to $125.00$. Line-item sum and SgstVal must match to 2 decimal places." in r["sentinel_audit_reasons"]


def test_lakehouse_scenario_3_combined_tax_rectification(failing_scenario_3_combined_tax_under_sgst):
    """Test Data Lakehouse flattening on Scenario 3: splits header tax equally into 900.00 CGST and 900.00 SGST."""
    rows = flatten_invoice_payload(failing_scenario_3_combined_tax_under_sgst)
    assert len(rows) == 1
    r = rows[0]

    assert r["inv_cgst_amount"] == 900.00
    assert r["inv_sgst_amount"] == 900.00
    assert r["sentinel_status_badge"] == "FLAGGED_AND_RECTIFIED"
    assert r["sentinel_risk_level"] == "HIGH"
    assert r["sentinel_risk_prob"] >= 0.95
    assert "Rule 2183 Violation (Combined Tax Passed as Single Value)" in r["sentinel_audit_reasons"]
    assert "The full 18% tax was placed entirely under SGST at the header instead of splitting it equally between CGST and SGST." in r["sentinel_audit_reasons"]


def test_lakehouse_scenario_4_header_zero_rectification(failing_scenario_4_item_populated_header_zero):
    """Test Data Lakehouse flattening on Scenario 4: restores header SgstVal from 0.00 to 900.00."""
    rows = flatten_invoice_payload(failing_scenario_4_item_populated_header_zero)
    assert len(rows) == 1
    r = rows[0]

    assert r["inv_sgst_amount"] == 900.00
    assert r["sentinel_status_badge"] == "FLAGGED_AND_RECTIFIED"
    assert r["sentinel_risk_level"] == "HIGH"
    assert r["sentinel_risk_prob"] >= 0.95
    assert "Rule 2183 Violation (Item Level Populated, Header Left as 0 or Null)" in r["sentinel_audit_reasons"]
    assert "Header tax values in ValDtls are mandatory for intra-state supplies. SgstVal cannot be 0.00 if line items have positive SGST." in r["sentinel_audit_reasons"]


def test_lakehouse_scenario_5_inter_state_rectification(failing_scenario_5_inter_state_passing_sgst):
    """Test Data Lakehouse flattening on Scenario 5: clears SGST/CGST and moves tax to IGST."""
    rows = flatten_invoice_payload(failing_scenario_5_inter_state_passing_sgst)
    assert len(rows) == 1
    r = rows[0]

    assert r["inv_sgst_amount"] == 0.00
    assert r["inv_cgst_amount"] == 0.00
    assert r["inv_igst_amount"] == 1800.00
    assert r["cgst_amount"] == 0.00
    assert r["sgst_amount"] == 0.00
    assert r["igst_amount"] == 1800.00
    assert r["sentinel_status_badge"] == "FLAGGED_AND_RECTIFIED"
    assert r["sentinel_risk_level"] == "HIGH"
    assert r["sentinel_risk_prob"] >= 0.95
    assert "Rule 2183 Violation" in r["sentinel_audit_reasons"] or "Rule 2174 Violation" in r["sentinel_audit_reasons"]


# ==============================================================================
# 4. PRE-API VALIDATORS INTEGRATION TESTS (validator.py & rules_engine.py)
# ==============================================================================

def test_template_validator_scenario_1_rejection(failing_scenario_1_stale_sgst_header):
    """Verify that Template_Converters.validator rejects Scenario 1 with code 2183."""
    errors = GSTValidator.validate_invoice(failing_scenario_1_stale_sgst_header)
    e2183 = [e for e in errors if e.get("error_code") == 2183]
    assert len(e2183) >= 1
    assert "Header Not Recalculated After Item Edits" in e2183[0].get("message", "")
    assert "Ensure ValDtls.SgstVal dynamically computes the sum of all ItemList[i].SgstAmt" in e2183[0].get("message", "")


def test_rules_engine_scenario_2_rejection(failing_scenario_2_paise_rounding_mismatch):
    """Verify that rules_engine.py rejects Scenario 2 with code 2183."""
    errors = RulesEngine.validate_invoice(failing_scenario_2_paise_rounding_mismatch)
    e2183 = [e for e in errors if e.get("error_code") == 2183]
    assert len(e2183) >= 1
    assert "Decimal / Paise Rounding Mismatch" in e2183[0].get("message", "")
    assert "Line-item sum and SgstVal must match to 2 decimal places." in e2183[0].get("message", "")


def test_rules_engine_scenario_3_rejection(failing_scenario_3_combined_tax_under_sgst):
    """Verify that rules_engine.py rejects Scenario 3 with code 2183."""
    errors = RulesEngine.validate_invoice(failing_scenario_3_combined_tax_under_sgst)
    e2183 = [e for e in errors if e.get("error_code") == 2183]
    assert len(e2183) >= 1
    assert "Combined Tax Passed as Single Value" in e2183[0].get("message", "")


def test_template_validator_scenario_5_rejection(failing_scenario_5_inter_state_passing_sgst):
    """Verify that Template_Converters.validator rejects Scenario 5 with code 2183 (inter-state passing SGST)."""
    errors = GSTValidator.validate_invoice(failing_scenario_5_inter_state_passing_sgst)
    e2183 = [e for e in errors if e.get("error_code") == 2183]
    assert len(e2183) >= 1
    assert "Inter-State Transaction Passing SGST" in e2183[0].get("message", "")


# ==============================================================================
# 5. PYDANTIC INVOICEPAYLOAD VALIDATION & FLATTENING TESTS
# ==============================================================================

def test_pydantic_rule_2183_validation_rejection(failing_scenario_1_stale_sgst_header):
    """Verify that InvoicePayload validation strictly rejects Rule 2183 mismatches."""
    with pytest.raises((NICValidationError, Exception)) as excinfo:
        InvoicePayload.model_validate(failing_scenario_1_stale_sgst_header)
    
    err_str = str(excinfo.value)
    assert "2183" in err_str
    assert "SGST value of items" in err_str
    assert "Header Not Recalculated After Item Edits" in err_str


def test_pydantic_rule_2183_lakehouse_flattening(failing_scenario_1_stale_sgst_header):
    """Verify that when a valid/corrected Pydantic model is passed to flatten_invoice_payload, Lakehouse handles it cleanly."""
    valid_payload = dict(failing_scenario_1_stale_sgst_header)
    valid_payload["valdtls"]["SgstVal"] = 1350.00
    valid_payload["valdtls"]["TotInvVal"] = 17700.00

    model = InvoicePayload.model_validate(valid_payload)
    rows = flatten_invoice_payload(model)
    assert len(rows) == 2
    assert rows[0]["inv_sgst_amount"] == 1350.00
    assert rows[1]["inv_sgst_amount"] == 1350.00


# ==============================================================================
# 6. PARQUET STORAGE ROUND-TRIP & FLATTENED_INVOICE_SCHEMA VALIDATION
# ==============================================================================

def test_lakehouse_parquet_roundtrip_all_scenarios(
    failing_scenario_1_stale_sgst_header,
    failing_scenario_2_paise_rounding_mismatch,
    failing_scenario_3_combined_tax_under_sgst,
    failing_scenario_4_item_populated_header_zero,
    failing_scenario_5_inter_state_passing_sgst
):
    """Test storing rectified invoices from all 5 statutory scenarios to Parquet and reading back."""
    temp_dir = tempfile.mkdtemp()
    parquet_path = os.path.join(temp_dir, "test_rule_2183_lakehouse.parquet")

    try:
        all_rows = []
        for payload in [
            failing_scenario_1_stale_sgst_header,
            failing_scenario_2_paise_rounding_mismatch,
            failing_scenario_3_combined_tax_under_sgst,
            failing_scenario_4_item_populated_header_zero,
            failing_scenario_5_inter_state_passing_sgst
        ]:
            rectified = flatten_invoice_payload(payload)
            all_rows.extend(rectified)

        # 1. Write Parquet
        write_parquet(all_rows, parquet_path)
        assert os.path.exists(parquet_path)

        # 2. Read Parquet
        df = read_parquet(parquet_path)
        assert len(df) == 8  # 2 + 3 + 1 + 1 + 1 = 8 items

        # Check Schema Conformance
        for field in FLATTENED_INVOICE_SCHEMA:
            assert field.name in df.columns, f"Missing field: {field.name}"

        # Check Telemetry across all rows
        assert (df["sentinel_status_badge"] == "FLAGGED_AND_RECTIFIED").all()
        assert (df["sentinel_risk_level"] == "HIGH").all()
        assert (df["sentinel_risk_prob"] >= 0.95).all()

        # Check individual rectified invoice SGST values
        sc1_rows = df[df["invoice_id"] == "INV-26-2183-SC1"]
        assert sc1_rows["inv_sgst_amount"].iloc[0] == 1350.00

        sc2_rows = df[df["invoice_id"] == "INV-26-2183-SC2"]
        assert sc2_rows["inv_sgst_amount"].iloc[0] == 125.01

        sc3_rows = df[df["invoice_id"] == "INV-26-2183-SC3"]
        assert sc3_rows["inv_sgst_amount"].iloc[0] == 900.00
        assert sc3_rows["inv_cgst_amount"].iloc[0] == 900.00

        sc4_rows = df[df["invoice_id"] == "INV-26-2183-SC4"]
        assert sc4_rows["inv_sgst_amount"].iloc[0] == 900.00

        sc5_rows = df[df["invoice_id"] == "INV-26-2183-SC5"]
        assert sc5_rows["inv_sgst_amount"].iloc[0] == 0.00
        assert sc5_rows["inv_cgst_amount"].iloc[0] == 0.00
        assert sc5_rows["inv_igst_amount"].iloc[0] == 1800.00

        # 3. Lakehouse Upsert: Append duplicate records and verify idempotent upsert
        append_to_parquet(all_rows, parquet_path, schema=FLATTENED_INVOICE_SCHEMA)
        df_appended = read_parquet(parquet_path)
        assert len(df_appended) == 8, "Lakehouse upsert maintains deduplicated record count"

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
