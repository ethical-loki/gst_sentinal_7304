"""
Test Suite: NIC Error Code 2185 Statutory Compliance & Data Lakehouse IGST Value Module.
File: tests/test_rule_2185_igst_value_lakehouse.py

Validates Indian GST e-Invoicing (NIC / IRP) Error Code 2185:
"IGST value of all items is not equal to total IGST Value"
The IRP schema strictly validates:
    ValDtls.IgstVal = sum(ItemList[i].IgstAmt)
If there is any difference between the sum of line items and the header value—even by a single paisa—
the payload is rejected.

Tests all 5 Statutory Scenarios directly within schemas, rules engine, and Data Lakehouse (src/ingestion/storage.py):
1. Header Not Recalculated After Item Edits:
   Item 1: IgstAmt = 1800.00, Item 2: IgstAmt = 600.00
   Sent: ValDtls: { IgstVal: 1800.00 }
   Correct: ValDtls: { IgstVal: 2400.00 }
   Fix / Reason: "Ensure ValDtls.IgstVal dynamically computes the sum of all ItemList[i].IgstAmt ($1800.00 + 600.00 = 2400.00$)."

2. Decimal / Paise Rounding Mismatch:
   Item 1: IgstAmt = 83.33, Item 2: IgstAmt = 83.33, Item 3: IgstAmt = 83.33
   Sent: ValDtls: { IgstVal: 250.00 }
   Correct: ValDtls: { IgstVal: 249.99 } (or adjust line 3 IgstAmt = 83.34)
   Fix / Reason: "Sum of item IgstAmt is $249.99$, but header total was rounded to $250.00$. Line-item sum and IgstVal must match to 2 decimal places."

3. Item Level Populated, Header Left as 0 or Null:
   Items have valid IgstAmt amounts, but header has:
   Sent: ValDtls: { IgstVal: 0.00 } or null
   Correct: ValDtls: { IgstVal: <Sum IgstAmt of items> }
   Fix / Reason: "Header tax values in ValDtls are mandatory for inter-state supplies. IgstVal cannot be 0.00 if line items have positive IGST."

4. Intra-State Supply Passing IGST in Summary:
   Local supply where items have CgstAmt = 900.00 and SgstAmt = 900.00, but ERP mapped the total tax into:
   Sent: ValDtls: { IgstVal: 1800.00 }
   Correct: ValDtls: { CgstVal: 900.00, SgstVal: 900.00, IgstVal: 0.00 }
   Fix / Reason: "For standard intra-state supplies, ValDtls.IgstVal must be 0.00 unless IgstOnIntra is set to \"Y\"."

5. Export / SEZ with Payment Miscalculation:
   Export under payment (EXPWP) where line-item IGST values do not tally up to ValDtls.IgstVal.
   Correct: Ensure sum of IgstAmt across export line items strictly matches ValDtls.IgstVal.
   Fix / Reason: "In EXPWP / SEZWP, IGST amounts must follow the exact same item-to-header aggregation rules."

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
    classify_rule_2185_diagnostic,
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
def failing_scenario_1_stale_igst_header():
    """Scenario 1: Header Not Recalculated After Item Edits (1800.00 + 600.00 -> 2400.00, Header has 1800.00)."""
    return {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-26-2185-SC1",
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
            "gstin": "29XYZAB9876C1Z1",
            "lglnm": "Karnataka Heavy Machines Ltd",
            "state": "29",
            "pos": "29",
            "pin": "560001",
            "loc": "Bengaluru"
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
                "cgstval": 0.0,
                "sgstval": 0.0,
                "igstval": 1800.0,
                "totitemval": 11800.0
            },
            {
                "item_slno": "2",
                "slno": "2",
                "prdnm": "Carbide End Mill Cutter",
                "prddesc": "4 Flute End Mill",
                "hsn": "8207",
                "qty": 1.0,
                "unit": "NOS",
                "unitprice": 3333.33,
                "totamt": 3333.33,
                "discount": 0.0,
                "assval": 3333.33,
                "gstrate": 18.0,
                "cgstval": 0.0,
                "sgstval": 0.0,
                "igstval": 600.0,
                "totitemval": 3933.33
            }
        ],
        "valdtls": {
            "AssVal": 13333.33,
            "CgstVal": 0.0,
            "SgstVal": 0.0,
            "IgstVal": 1800.0,  # Failing: Stale header total (1800.00 instead of 2400.00)
            "CesVal": 0.0,
            "Discount": 0.0,
            "RndOffAmt": 0.0,
            "TotInvVal": 15133.33
        }
    }


@pytest.fixture
def failing_scenario_2_paise_rounding_mismatch():
    """Scenario 2: Decimal / Paise Rounding Mismatch (83.33 x 3 = 249.99, Header has 250.00)."""
    return {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-26-2185-SC2",
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
            "gstin": "29XYZAB9876C1Z1",
            "lglnm": "Karnataka Assembly Works",
            "state": "29",
            "pos": "29",
            "pin": "560001",
            "loc": "Bengaluru"
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
                "cgstval": 0.0,
                "sgstval": 0.0,
                "igstval": 83.33,
                "totitemval": 546.29
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
                "cgstval": 0.0,
                "sgstval": 0.0,
                "igstval": 83.33,
                "totitemval": 546.29
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
                "cgstval": 0.0,
                "sgstval": 0.0,
                "igstval": 83.33,
                "totitemval": 546.29
            }
        ],
        "valdtls": {
            "AssVal": 1388.88,
            "CgstVal": 0.0,
            "SgstVal": 0.0,
            "IgstVal": 250.00,  # Failing: Rounded up to 250.00 instead of 249.99
            "CesVal": 0.0,
            "Discount": 0.0,
            "RndOffAmt": 0.0,
            "TotInvVal": 1638.88
        }
    }


@pytest.fixture
def failing_scenario_3_item_populated_header_zero():
    """Scenario 3: Item Level Populated, Header Left as 0 or Null (Items have 1800.00 IGST, Header has 0.00)."""
    return {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-26-2185-SC3",
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
            "gstin": "29XYZAB9876C1Z1",
            "lglnm": "Karnataka Motors Manufacturing",
            "state": "29",
            "pos": "29",
            "pin": "560001",
            "loc": "Bengaluru"
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
                "cgstval": 0.0,
                "sgstval": 0.0,
                "igstval": 1800.0,
                "totitemval": 11800.0
            }
        ],
        "valdtls": {
            "AssVal": 10000.0,
            "CgstVal": 0.0,
            "SgstVal": 0.0,
            "IgstVal": 0.0,  # Failing: Header tax values mandatory, cannot be 0.00
            "CesVal": 0.0,
            "Discount": 0.0,
            "RndOffAmt": 0.0,
            "TotInvVal": 10000.0
        }
    }


@pytest.fixture
def failing_scenario_4_intra_state_passing_igst():
    """Scenario 4: Intra-State Supply Passing IGST in Summary (Items have 900 CGST + 900 SGST, Header has 1800 IGST)."""
    return {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-26-2185-SC4",
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
            "SgstVal": 0.0,
            "IgstVal": 1800.0,  # Failing: Standard intra-state supply cannot have IgstVal > 0.00
            "CesVal": 0.0,
            "Discount": 0.0,
            "RndOffAmt": 0.0,
            "TotInvVal": 11800.0
        }
    }


@pytest.fixture
def failing_scenario_5_export_with_payment_mismatch():
    """Scenario 5: Export / SEZ with Payment Miscalculation (EXPWP with item IGST 1800.00 but header IGST 2400.00)."""
    return {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-26-2185-SC5",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "EXPWP",
        "reversecharge": "N",
        "igstonintra": "N",
        "supplier": {
            "gstin": "27ABCDE1234F1Z5",
            "lglnm": "Maharashtra Global Exporters Ltd",
            "state": "27",
            "pin": "400001",
            "loc": "Mumbai"
        },
        "buyer": {
            "gstin": "URP",
            "lglnm": "Global Aerospace GmbH",
            "state": "96",
            "pos": "96",
            "pin": "999999",
            "loc": "Frankfurt"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "Aviation Turbine Assembly Kit",
                "prddesc": "Turbine Blade Set",
                "hsn": "8411",
                "qty": 1.0,
                "unit": "SET",
                "unitprice": 10000.0,
                "totamt": 10000.0,
                "discount": 0.0,
                "assval": 10000.0,
                "gstrate": 18.0,
                "cgstval": 0.0,
                "sgstval": 0.0,
                "igstval": 1800.0,
                "totitemval": 11800.0
            }
        ],
        "valdtls": {
            "AssVal": 10000.0,
            "CgstVal": 0.0,
            "SgstVal": 0.0,
            "IgstVal": 2400.0,  # Failing: Line-item IGST is 1800.00 but header has 2400.00
            "CesVal": 0.0,
            "Discount": 0.0,
            "RndOffAmt": 0.0,
            "TotInvVal": 12400.0
        }
    }


# ==============================================================================
# 1. STANDALONE DIAGNOSTIC CLASSIFICATION TESTS
# ==============================================================================

def test_diagnostic_scenario_1_stale_header():
    """Verify classification of Scenario 1: Header Not Recalculated After Item Edits."""
    diag = classify_rule_2185_diagnostic(
        header_igst=Decimal("1800.00"),
        sum_item_igst=Decimal("2400.00"),
        items=[{"IgstAmt": Decimal("1800.00")}, {"IgstAmt": Decimal("600.00")}],
        is_inter_state=True
    )
    assert diag["is_valid"] is False
    assert diag["error_code"] == 2185
    assert diag["scenario"] == "HEADER_NOT_RECALCULATED_AFTER_ITEM_EDITS"
    assert diag["scenario_name"] == "Header Not Recalculated After Item Edits"
    assert diag["action"] == "DYNAMICALLY_COMPUTE_HEADER_IGST"
    assert diag["correct_payload"]["ValDtls"]["IgstVal"] == Decimal("2400.00")
    assert "Ensure ValDtls.IgstVal dynamically computes the sum of all ItemList[i].IgstAmt ($1800.00 + 600.00 = 2400.00$)." in diag["reason"]


def test_diagnostic_scenario_2_paise_rounding():
    """Verify classification of Scenario 2: Decimal / Paise Rounding Mismatch."""
    diag = classify_rule_2185_diagnostic(
        header_igst=Decimal("250.00"),
        sum_item_igst=Decimal("249.99"),
        items=[{"IgstAmt": Decimal("83.33")}, {"IgstAmt": Decimal("83.33")}, {"IgstAmt": Decimal("83.33")}],
        is_inter_state=True
    )
    assert diag["is_valid"] is False
    assert diag["scenario"] == "DECIMAL_PAISE_ROUNDING_MISMATCH"
    assert diag["scenario_name"] == "Decimal / Paise Rounding Mismatch"
    assert diag["action"] == "RECONCILE_PAISE_ROUNDING"
    assert diag["correct_payload"]["ValDtls"]["IgstVal"] == Decimal("249.99")
    assert "Sum of item IgstAmt is $249.99$, but header total was rounded to $250.00$. Line-item sum and IgstVal must match to 2 decimal places." in diag["reason"]


def test_diagnostic_scenario_3_header_zero_or_null():
    """Verify classification of Scenario 3: Item Level Populated, Header Left as 0 or Null."""
    diag = classify_rule_2185_diagnostic(
        header_igst=Decimal("0.00"),
        sum_item_igst=Decimal("1800.00"),
        is_inter_state=True
    )
    assert diag["is_valid"] is False
    assert diag["scenario"] == "ITEM_LEVEL_POPULATED_HEADER_ZERO_OR_NULL"
    assert diag["scenario_name"] == "Item Level Populated, Header Left as 0 or Null"
    assert diag["action"] == "POPULATE_HEADER_IGST_FROM_ITEMS"
    assert diag["correct_payload"]["ValDtls"]["IgstVal"] == Decimal("1800.00")
    assert "Header tax values in ValDtls are mandatory for inter-state supplies. IgstVal cannot be 0.00 if line items have positive IGST." in diag["reason"]


def test_diagnostic_scenario_4_intra_state_passing_igst():
    """Verify classification of Scenario 4: Intra-State Supply Passing IGST in Summary."""
    diag = classify_rule_2185_diagnostic(
        header_igst=Decimal("1800.00"),
        sum_item_igst=Decimal("0.00"),
        sum_item_cgst=Decimal("900.00"),
        sum_item_sgst=Decimal("900.00"),
        is_inter_state=False,
        seller_state="27",
        buyer_pos="27",
        igst_on_intra="N",
        trancatg="B2B"
    )
    assert diag["is_valid"] is False
    assert diag["scenario"] == "INTRA_STATE_SUPPLY_PASSING_IGST_IN_SUMMARY"
    assert diag["scenario_name"] == "Intra-State Supply Passing IGST in Summary"
    assert diag["action"] == "CLEAR_IGST_PASS_CGST_SGST"
    assert diag["correct_payload"]["ValDtls"]["CgstVal"] == Decimal("900.00")
    assert diag["correct_payload"]["ValDtls"]["SgstVal"] == Decimal("900.00")
    assert diag["correct_payload"]["ValDtls"]["IgstVal"] == Decimal("0.00")
    assert "For standard intra-state supplies, ValDtls.IgstVal must be 0.00 unless IgstOnIntra is set to \"Y\"." in diag["reason"]


def test_diagnostic_scenario_5_export_with_payment():
    """Verify classification of Scenario 5: Export / SEZ with Payment Miscalculation."""
    diag = classify_rule_2185_diagnostic(
        header_igst=Decimal("2400.00"),
        sum_item_igst=Decimal("1800.00"),
        is_inter_state=True,
        seller_state="27",
        buyer_pos="96",
        trancatg="EXPWP"
    )
    assert diag["is_valid"] is False
    assert diag["scenario"] == "EXPORT_SEZ_WITH_PAYMENT_MISCALCULATION"
    assert diag["scenario_name"] == "Export / SEZ with Payment Miscalculation"
    assert diag["action"] == "RECONCILE_EXPORT_SEZ_IGST"
    assert diag["correct_payload"]["ValDtls"]["IgstVal"] == Decimal("1800.00")
    assert "In EXPWP / SEZWP, IGST amounts must follow the exact same item-to-header aggregation rules." in diag["reason"]


def test_diagnostic_valid_payload():
    """Verify that when header IGST equals item IGST sum, classification is VALID."""
    diag = classify_rule_2185_diagnostic(
        header_igst=Decimal("2400.00"),
        sum_item_igst=Decimal("2400.00"),
        is_inter_state=True
    )
    assert diag["is_valid"] is True
    assert diag["scenario"] == "VALID"
    assert diag["action"] == "NONE"


# ==============================================================================
# 2. AUTO-CORRECTION AND BUILD TESTS (InvoicePayload.auto_correct_and_build)
# ==============================================================================

def test_auto_correct_scenario_1_stale_header(failing_scenario_1_stale_igst_header):
    """Test auto-correction of Scenario 1: updates ValDtls.IgstVal from 1800.00 to 2400.00."""
    model, audit_log = InvoicePayload.auto_correct_and_build(failing_scenario_1_stale_igst_header)
    assert float(model.valdtls.igstval) == 2400.00
    assert float(model.valdtls.totinvval) == 15733.33
    assert any("Rule 2185" in str(entry) for entry in audit_log)
    assert any("Header Not Recalculated After Item Edits" in str(entry) for entry in audit_log)


def test_auto_correct_scenario_2_paise_rounding(failing_scenario_2_paise_rounding_mismatch):
    """Test auto-correction of Scenario 2: updates ValDtls.IgstVal from 250.00 to 249.99."""
    model, audit_log = InvoicePayload.auto_correct_and_build(failing_scenario_2_paise_rounding_mismatch)
    assert float(model.valdtls.igstval) == 249.99
    assert any("Rule 2185" in str(entry) for entry in audit_log)
    assert any("Decimal / Paise Rounding Mismatch" in str(entry) for entry in audit_log)


def test_auto_correct_scenario_3_header_zero(failing_scenario_3_item_populated_header_zero):
    """Test auto-correction of Scenario 3: populates header IgstVal from 0.00 to 1800.00."""
    model, audit_log = InvoicePayload.auto_correct_and_build(failing_scenario_3_item_populated_header_zero)
    assert float(model.valdtls.igstval) == 1800.00
    assert any("Rule 2185" in str(entry) for entry in audit_log)
    assert any("Item Level Populated, Header Left as 0 or Null" in str(entry) for entry in audit_log)


def test_auto_correct_scenario_4_intra_state_igst(failing_scenario_4_intra_state_passing_igst):
    """Test auto-correction of Scenario 4: clears header IgstVal to 0.00 and routes tax to CGST/SGST."""
    model, audit_log = InvoicePayload.auto_correct_and_build(failing_scenario_4_intra_state_passing_igst)
    assert float(model.valdtls.igstval) == 0.00
    assert float(model.valdtls.cgstval) == 900.00
    assert float(model.valdtls.sgstval) == 900.00
    assert any("Rule 2185" in str(entry) for entry in audit_log)
    assert any("Intra-State Supply Passing IGST in Summary" in str(entry) for entry in audit_log)


def test_auto_correct_scenario_5_export_payment(failing_scenario_5_export_with_payment_mismatch):
    """Test auto-correction of Scenario 5: corrects header IgstVal from 2400.00 to 1800.00 for EXPWP."""
    model, audit_log = InvoicePayload.auto_correct_and_build(failing_scenario_5_export_with_payment_mismatch)
    assert float(model.valdtls.igstval) == 1800.00
    assert any("Rule 2185" in str(entry) for entry in audit_log)
    assert any("Export / SEZ with Payment Miscalculation" in str(entry) for entry in audit_log)


# ==============================================================================
# 3. DATA LAKEHOUSE NORMALIZATION & TELEMETRY TESTS (flatten_invoice_payload)
# ==============================================================================

def test_lakehouse_scenario_1_stale_header_rectification(failing_scenario_1_stale_igst_header):
    """Test Data Lakehouse flattening on Scenario 1: reconciles header to line-item sum 2400.00."""
    rows = flatten_invoice_payload(failing_scenario_1_stale_igst_header)
    assert len(rows) == 2

    for r in rows:
        assert r["inv_igst_amount"] == 2400.00
        assert r["sentinel_status_badge"] == "FLAGGED_AND_RECTIFIED"
        assert r["sentinel_risk_level"] == "HIGH"
        assert r["sentinel_risk_prob"] >= 0.95
        assert "Rule 2185 Violation (Header Not Recalculated After Item Edits)" in r["sentinel_audit_reasons"]
        assert "Ensure ValDtls.IgstVal dynamically computes the sum of all ItemList[i].IgstAmt" in r["sentinel_audit_reasons"]


def test_lakehouse_scenario_2_paise_rounding_rectification(failing_scenario_2_paise_rounding_mismatch):
    """Test Data Lakehouse flattening on Scenario 2: reconciles header to line-item sum 249.99."""
    rows = flatten_invoice_payload(failing_scenario_2_paise_rounding_mismatch)
    assert len(rows) == 3

    for r in rows:
        assert r["inv_igst_amount"] == 249.99
        assert r["sentinel_status_badge"] == "FLAGGED_AND_RECTIFIED"
        assert r["sentinel_risk_level"] == "HIGH"
        assert r["sentinel_risk_prob"] >= 0.95
        assert "Rule 2185 Violation (Decimal / Paise Rounding Mismatch)" in r["sentinel_audit_reasons"]
        assert "Sum of item IgstAmt is $249.99$, but header total was rounded to $250.00$. Line-item sum and IgstVal must match to 2 decimal places." in r["sentinel_audit_reasons"]


def test_lakehouse_scenario_3_header_zero_rectification(failing_scenario_3_item_populated_header_zero):
    """Test Data Lakehouse flattening on Scenario 3: restores header IgstVal from 0.00 to 1800.00."""
    rows = flatten_invoice_payload(failing_scenario_3_item_populated_header_zero)
    assert len(rows) == 1
    r = rows[0]

    assert r["inv_igst_amount"] == 1800.00
    assert r["sentinel_status_badge"] == "FLAGGED_AND_RECTIFIED"
    assert r["sentinel_risk_level"] == "HIGH"
    assert r["sentinel_risk_prob"] >= 0.95
    assert "Rule 2185 Violation (Item Level Populated, Header Left as 0 or Null)" in r["sentinel_audit_reasons"]
    assert "Header tax values in ValDtls are mandatory for inter-state supplies. IgstVal cannot be 0.00 if line items have positive IGST." in r["sentinel_audit_reasons"]


def test_lakehouse_scenario_4_intra_state_rectification(failing_scenario_4_intra_state_passing_igst):
    """Test Data Lakehouse flattening on Scenario 4: clears header IgstVal to 0.00 and routes tax to CGST/SGST."""
    rows = flatten_invoice_payload(failing_scenario_4_intra_state_passing_igst)
    assert len(rows) == 1
    r = rows[0]

    assert r["inv_igst_amount"] == 0.00
    assert r["inv_cgst_amount"] == 900.00
    assert r["inv_sgst_amount"] == 900.00
    assert r["sentinel_status_badge"] == "FLAGGED_AND_RECTIFIED"
    assert r["sentinel_risk_level"] == "HIGH"
    assert r["sentinel_risk_prob"] >= 0.95
    assert "Rule 2185 Violation (Intra-State Supply Passing IGST in Summary)" in r["sentinel_audit_reasons"]


def test_lakehouse_scenario_5_export_payment_rectification(failing_scenario_5_export_with_payment_mismatch):
    """Test Data Lakehouse flattening on Scenario 5: corrects header IgstVal to match export line items (1800.00)."""
    rows = flatten_invoice_payload(failing_scenario_5_export_with_payment_mismatch)
    assert len(rows) == 1
    r = rows[0]

    assert r["inv_igst_amount"] == 1800.00
    assert r["sentinel_status_badge"] == "FLAGGED_AND_RECTIFIED"
    assert r["sentinel_risk_level"] == "HIGH"
    assert r["sentinel_risk_prob"] >= 0.95
    assert "Rule 2185 Violation (Export / SEZ with Payment Miscalculation)" in r["sentinel_audit_reasons"]


# ==============================================================================
# 4. PRE-API VALIDATORS INTEGRATION TESTS (validator.py & rules_engine.py)
# ==============================================================================

def test_template_validator_scenario_1_rejection(failing_scenario_1_stale_igst_header):
    """Verify that Template_Converters.validator rejects Scenario 1 with code 2185."""
    errors = GSTValidator.validate_invoice(failing_scenario_1_stale_igst_header)
    e2185 = [e for e in errors if e.get("error_code") == 2185]
    assert len(e2185) >= 1
    assert "Header Not Recalculated After Item Edits" in e2185[0].get("message", "")
    assert "Ensure ValDtls.IgstVal dynamically computes the sum of all ItemList[i].IgstAmt" in e2185[0].get("message", "")


def test_rules_engine_scenario_2_rejection(failing_scenario_2_paise_rounding_mismatch):
    """Verify that rules_engine.py rejects Scenario 2 with code 2185."""
    errors = RulesEngine.validate_invoice(failing_scenario_2_paise_rounding_mismatch)
    e2185 = [e for e in errors if e.get("error_code") == 2185]
    assert len(e2185) >= 1
    assert "Decimal / Paise Rounding Mismatch" in e2185[0].get("message", "")
    assert "Line-item sum and IgstVal must match to 2 decimal places." in e2185[0].get("message", "")


def test_rules_engine_scenario_4_rejection(failing_scenario_4_intra_state_passing_igst):
    """Verify that rules_engine.py rejects Scenario 4 with code 2185."""
    errors = RulesEngine.validate_invoice(failing_scenario_4_intra_state_passing_igst)
    e2185 = [e for e in errors if e.get("error_code") == 2185]
    assert len(e2185) >= 1
    assert "Intra-State Supply Passing IGST in Summary" in e2185[0].get("message", "")


def test_template_validator_scenario_5_rejection(failing_scenario_5_export_with_payment_mismatch):
    """Verify that Template_Converters.validator rejects Scenario 5 with code 2185."""
    errors = GSTValidator.validate_invoice(failing_scenario_5_export_with_payment_mismatch)
    e2185 = [e for e in errors if e.get("error_code") == 2185]
    assert len(e2185) >= 1
    assert "Export / SEZ with Payment Miscalculation" in e2185[0].get("message", "")


# ==============================================================================
# 5. PYDANTIC INVOICEPAYLOAD VALIDATION & FLATTENING TESTS
# ==============================================================================

def test_pydantic_rule_2185_validation_rejection(failing_scenario_1_stale_igst_header):
    """Verify that InvoicePayload validation strictly rejects Rule 2185 mismatches."""
    with pytest.raises((NICValidationError, Exception)) as excinfo:
        InvoicePayload.model_validate(failing_scenario_1_stale_igst_header)
    
    err_str = str(excinfo.value)
    assert "2185" in err_str
    assert "IGST value of items" in err_str
    assert "Header Not Recalculated After Item Edits" in err_str


def test_pydantic_rule_2185_lakehouse_flattening(failing_scenario_1_stale_igst_header):
    """Verify that when a valid/corrected Pydantic model is passed to flatten_invoice_payload, Lakehouse handles it cleanly."""
    valid_payload = dict(failing_scenario_1_stale_igst_header)
    valid_payload["valdtls"]["IgstVal"] = 2400.00
    valid_payload["valdtls"]["TotInvVal"] = 15733.33

    model = InvoicePayload.model_validate(valid_payload)
    rows = flatten_invoice_payload(model)
    assert len(rows) == 2
    assert rows[0]["inv_igst_amount"] == 2400.00
    assert rows[1]["inv_igst_amount"] == 2400.00


# ==============================================================================
# 6. PARQUET STORAGE ROUND-TRIP & FLATTENED_INVOICE_SCHEMA VALIDATION
# ==============================================================================

def test_lakehouse_parquet_roundtrip_all_scenarios(
    failing_scenario_1_stale_igst_header,
    failing_scenario_2_paise_rounding_mismatch,
    failing_scenario_3_item_populated_header_zero,
    failing_scenario_4_intra_state_passing_igst,
    failing_scenario_5_export_with_payment_mismatch
):
    """Test storing rectified invoices from all 5 statutory scenarios to Parquet and reading back."""
    temp_dir = tempfile.mkdtemp()
    parquet_path = os.path.join(temp_dir, "test_rule_2185_lakehouse.parquet")

    try:
        all_rows = []
        for payload in [
            failing_scenario_1_stale_igst_header,
            failing_scenario_2_paise_rounding_mismatch,
            failing_scenario_3_item_populated_header_zero,
            failing_scenario_4_intra_state_passing_igst,
            failing_scenario_5_export_with_payment_mismatch
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

        # Check individual rectified invoice IGST values
        sc1_rows = df[df["invoice_id"] == "INV-26-2185-SC1"]
        assert sc1_rows["inv_igst_amount"].iloc[0] == 2400.00

        sc2_rows = df[df["invoice_id"] == "INV-26-2185-SC2"]
        assert sc2_rows["inv_igst_amount"].iloc[0] == 249.99

        sc3_rows = df[df["invoice_id"] == "INV-26-2185-SC3"]
        assert sc3_rows["inv_igst_amount"].iloc[0] == 1800.00

        sc4_rows = df[df["invoice_id"] == "INV-26-2185-SC4"]
        assert sc4_rows["inv_igst_amount"].iloc[0] == 0.00
        assert sc4_rows["inv_cgst_amount"].iloc[0] == 900.00
        assert sc4_rows["inv_sgst_amount"].iloc[0] == 900.00

        sc5_rows = df[df["invoice_id"] == "INV-26-2185-SC5"]
        assert sc5_rows["inv_igst_amount"].iloc[0] == 1800.00

        # 3. Lakehouse Upsert: Append duplicate records and verify idempotent upsert
        append_to_parquet(all_rows, parquet_path, schema=FLATTENED_INVOICE_SCHEMA)
        df_appended = read_parquet(parquet_path)
        assert len(df_appended) == 8, "Lakehouse upsert maintains deduplicated record count"

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
