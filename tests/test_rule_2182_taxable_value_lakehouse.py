"""
Test Suite: NIC Error Code 2182 Statutory Compliance & Data Lakehouse Taxable Value Module.
File: tests/test_rule_2182_taxable_value_lakehouse.py

Validates Indian GST e-Invoicing (NIC / IRP) Error Code 2182:
"Taxable value of items != total taxable value"
The IRP schema enforces strict mathematical equality:
    ValDtls.AssVal = sum(ItemList[i].AssAmt)
If there is a difference—even of a few paise due to unmanaged decimal truncation or pre-tax discounts—
the IRP rejects the request with code 2182.

Tests all 4 Statutory Scenarios directly within schemas, rules engine, and Data Lakehouse (src/ingestion/storage.py):
1. Header Not Updated After Item Edits:
   Item 1: AssAmt = 5000.00, Item 2: AssAmt = 3000.00
   Sent: ValDtls: { AssVal: 5000.00 }
   Correct: ValDtls: { AssVal: 8000.00 }
   Fix / Reason: "Ensure ValDtls.AssVal dynamically recalculates the sum of all ItemList[i].AssAmt (5000 + 3000 = 8000) before sending."

2. Pre-tax Discount Deducted Twice:
   Item 1: TotAmt = 10000, Discount = 1000, AssAmt = 9000
   Sent: ValDtls: { Discount: 1000, AssVal: 8000 }
   Correct: ValDtls: { Discount: 1000, AssVal: 9000 }
   Fix / Reason: "In e-Invoicing, AssVal must equal the sum of item assessable values (AssAmt), which already account for item-level discounts. Deducting the discount again at ValDtls.AssVal causes a mismatch."

3. Paise / Decimal Rounding Issue:
   Item 1: AssAmt = 333.33, Item 2: AssAmt = 333.33, Item 3: AssAmt = 333.33 (Sum = 999.99)
   Sent: ValDtls: { AssVal: 1000.00 }
   Correct: ValDtls: { AssVal: 999.99 } (or adjust last item AssAmt = 333.34)
   Fix / Reason: "The sum of item AssAmt is 999.99, but the header was rounded up to 1000.00. Line-item totals and header assessable values must be identical to 2 decimal places."

4. Gross Total (TotAmt) Used Instead of AssAmt:
   Item 1: TotAmt = 10000, Discount = 500, AssAmt = 9500
   Sent: ValDtls: { AssVal: 10000.00 }
   Correct: ValDtls: { AssVal: 9500.00 }
   Fix / Reason: "AssVal must strictly equal the sum of AssAmt (net taxable value), not TotAmt (gross value before discount)."

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
    classify_rule_2182_diagnostic,
    NICValidationError,
)
from src.ingestion.storage import (
    flatten_invoice_payload,
    write_parquet,
    read_parquet,
    append_to_parquet,
    store_invoice_payload,
    FLATTENED_INVOICE_SCHEMA,
)


# ==============================================================================
# FIXTURES FOR 4 STATUTORY SCENARIOS
# ==============================================================================

@pytest.fixture
def failing_scenario_1_stale_header():
    """Scenario 1: Header Not Updated After Item Edits (5000 + 3000 -> 8000, Header has 5000)."""
    return {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-26-2182-SC1",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "B2B",
        "reversecharge": "N",
        "igstonintra": "N",
        "supplier": {
            "gstin": "27ABCDE1234F1Z5",
            "lglnm": "Maharashtra Alpha Supplier Ltd",
            "state": "27",
            "pin": "400001",
            "loc": "Mumbai"
        },
        "buyer": {
            "gstin": "27XYZAB9876C1Z1",
            "lglnm": "Maharashtra Beta Purchaser Ltd",
            "state": "27",
            "pos": "27",
            "pin": "411001",
            "loc": "Pune"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "Heavy Duty Industrial Shaft",
                "prddesc": "Shaft Component 50mm",
                "hsn": "8483",
                "qty": 1.0,
                "unit": "NOS",
                "unitprice": 5000.0,
                "totamt": 5000.0,
                "discount": 0.0,
                "assval": 5000.0,
                "gstrate": 18.0,
                "cgstval": 450.0,
                "sgstval": 450.0,
                "igstval": 0.0,
                "totitemval": 5900.0
            },
            {
                "item_slno": "2",
                "slno": "2",
                "prdnm": "Precision Ball Bearing Assembly",
                "prddesc": "Bearing Unit 25mm",
                "hsn": "8482",
                "qty": 1.0,
                "unit": "NOS",
                "unitprice": 3000.0,
                "totamt": 3000.0,
                "discount": 0.0,
                "assval": 3000.0,
                "gstrate": 18.0,
                "cgstval": 270.0,
                "sgstval": 270.0,
                "igstval": 0.0,
                "totitemval": 3540.0
            }
        ],
        "valdtls": {
            "AssVal": 5000.00,  # FAILING: Stale header not updated after Item 2 added (5000 + 3000 = 8000)
            "CgstVal": 720.00,
            "SgstVal": 720.00,
            "IgstVal": 0.00,
            "CesVal": 0.00,
            "StCesVal": 0.00,
            "Discount": 0.00,
            "OthChrg": 0.00,
            "RndOffAmt": 0.00,
            "TotInvVal": 9440.00
        }
    }


@pytest.fixture
def failing_scenario_2_double_discount():
    """Scenario 2: Pre-tax Discount Deducted Twice (TotAmt=10000, Disc=1000, AssAmt=9000, Header AssVal=8000)."""
    return {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-26-2182-SC2",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "B2B",
        "reversecharge": "N",
        "igstonintra": "N",
        "supplier": {
            "gstin": "27ABCDE1234F1Z5",
            "lglnm": "Maharashtra Equipment Works",
            "state": "27",
            "pin": "400001",
            "loc": "Mumbai"
        },
        "buyer": {
            "gstin": "27XYZAB9876C1Z1",
            "lglnm": "Maharashtra Retail Partners",
            "state": "27",
            "pos": "27",
            "pin": "411001",
            "loc": "Pune"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "Commercial Air Compressor",
                "prddesc": "Air compressor 2HP 50L",
                "hsn": "8414",
                "qty": 1.0,
                "unit": "NOS",
                "unitprice": 10000.0,
                "totamt": 10000.0,
                "discount": 1000.0,
                "assval": 9000.0,  # Item level AssAmt already net of 1000 discount
                "gstrate": 18.0,
                "cgstval": 810.0,
                "sgstval": 810.0,
                "igstval": 0.0,
                "totitemval": 10620.0
            }
        ],
        "valdtls": {
            "Discount": 1000.00,
            "AssVal": 8000.00,  # FAILING: Deducted 1000 discount again from 9000 -> 8000
            "CgstVal": 810.00,
            "SgstVal": 810.00,
            "IgstVal": 0.00,
            "CesVal": 0.00,
            "StCesVal": 0.00,
            "OthChrg": 0.00,
            "RndOffAmt": 0.00,
            "TotInvVal": 10620.00
        }
    }


@pytest.fixture
def failing_scenario_3_paise_rounding():
    """Scenario 3: Paise / Decimal Rounding Issue (3 items x 333.33 = 999.99, Header AssVal=1000.00)."""
    return {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-26-2182-SC3",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "B2B",
        "reversecharge": "N",
        "igstonintra": "N",
        "supplier": {
            "gstin": "27ABCDE1234F1Z5",
            "lglnm": "Maharashtra Textile Fabrics",
            "state": "27",
            "pin": "400001",
            "loc": "Mumbai"
        },
        "buyer": {
            "gstin": "27XYZAB9876C1Z1",
            "lglnm": "Maharashtra Garment Studio",
            "state": "27",
            "pos": "27",
            "pin": "411001",
            "loc": "Pune"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "Cotton Fabric Roll A",
                "prddesc": "100% woven cotton grade A",
                "hsn": "5208",
                "qty": 1.0,
                "unit": "MTR",
                "unitprice": 333.33,
                "totamt": 333.33,
                "discount": 0.0,
                "assval": 333.33,
                "gstrate": 5.0,
                "cgstval": 8.33,
                "sgstval": 8.33,
                "igstval": 0.0,
                "totitemval": 349.99
            },
            {
                "item_slno": "2",
                "slno": "2",
                "prdnm": "Cotton Fabric Roll B",
                "prddesc": "100% woven cotton grade B",
                "hsn": "5208",
                "qty": 1.0,
                "unit": "MTR",
                "unitprice": 333.33,
                "totamt": 333.33,
                "discount": 0.0,
                "assval": 333.33,
                "gstrate": 5.0,
                "cgstval": 8.33,
                "sgstval": 8.33,
                "igstval": 0.0,
                "totitemval": 349.99
            },
            {
                "item_slno": "3",
                "slno": "3",
                "prdnm": "Cotton Fabric Roll C",
                "prddesc": "100% woven cotton grade C",
                "hsn": "5208",
                "qty": 1.0,
                "unit": "MTR",
                "unitprice": 333.33,
                "totamt": 333.33,
                "discount": 0.0,
                "assval": 333.33,
                "gstrate": 5.0,
                "cgstval": 8.33,
                "sgstval": 8.33,
                "igstval": 0.0,
                "totitemval": 349.99
            }
        ],
        "valdtls": {
            "AssVal": 1000.00,  # FAILING: Rounded to 1000.00 instead of 999.99 (1 paise rounding discrepancy)
            "CgstVal": 25.00,
            "SgstVal": 25.00,
            "IgstVal": 0.00,
            "CesVal": 0.00,
            "StCesVal": 0.00,
            "Discount": 0.00,
            "OthChrg": 0.00,
            "RndOffAmt": 0.00,
            "TotInvVal": 1050.00
        }
    }


@pytest.fixture
def failing_scenario_4_gross_total_used():
    """Scenario 4: Gross Total (TotAmt) Used Instead of AssAmt (TotAmt=10000, Disc=500, AssAmt=9500, Header AssVal=10000)."""
    return {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-26-2182-SC4",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "B2B",
        "reversecharge": "N",
        "igstonintra": "N",
        "supplier": {
            "gstin": "27ABCDE1234F1Z5",
            "lglnm": "Maharashtra Electricals Ltd",
            "state": "27",
            "pin": "400001",
            "loc": "Mumbai"
        },
        "buyer": {
            "gstin": "27XYZAB9876C1Z1",
            "lglnm": "Maharashtra Power Systems",
            "state": "27",
            "pos": "27",
            "pin": "411001",
            "loc": "Pune"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "High Voltage Switchgear",
                "prddesc": "Switchgear unit 11kV",
                "hsn": "8537",
                "qty": 1.0,
                "unit": "NOS",
                "unitprice": 10000.0,
                "totamt": 10000.0,
                "discount": 500.0,
                "assval": 9500.0,  # Net assessable amount is 9500
                "gstrate": 18.0,
                "cgstval": 855.0,
                "sgstval": 855.0,
                "igstval": 0.0,
                "totitemval": 11210.0
            }
        ],
        "valdtls": {
            "AssVal": 10000.00,  # FAILING: Gross TotAmt passed instead of net AssAmt (9500.00)
            "CgstVal": 855.00,
            "SgstVal": 855.00,
            "IgstVal": 0.00,
            "CesVal": 0.00,
            "StCesVal": 0.00,
            "Discount": 0.00,
            "OthChrg": 0.00,
            "RndOffAmt": 0.00,
            "TotInvVal": 11710.00
        }
    }


# ==============================================================================
# 1. DIRECT UNIT TESTS FOR classify_rule_2182_diagnostic
# ==============================================================================

def test_classify_2182_valid_equality():
    """Verify that when header AssVal exactly equals sum of item AssAmt, status is VALID."""
    diag = classify_rule_2182_diagnostic(
        header_assval=8000.00,
        sum_item_assamt=8000.00,
    )
    assert diag["is_valid"] is True
    assert diag["scenario"] == "VALID"
    assert diag["action"] == "NONE"
    assert diag["correct_payload"]["ValDtls"]["AssVal"] == Decimal("8000.00")


def test_classify_2182_scenario_1_stale_header():
    """Verify Scenario 1: Header Not Updated After Item Edits (5000 + 3000 -> 8000)."""
    items = [
        {"AssAmt": 5000.00, "TotAmt": 5000.00, "Discount": 0.0},
        {"AssAmt": 3000.00, "TotAmt": 3000.00, "Discount": 0.0}
    ]
    diag = classify_rule_2182_diagnostic(
        header_assval=5000.00,
        sum_item_assamt=8000.00,
        items=items
    )
    assert diag["is_valid"] is False
    assert diag["error_code"] == 2182
    assert diag["scenario"] == "HEADER_NOT_UPDATED_AFTER_ITEM_EDITS"
    assert diag["scenario_name"] == "Header Not Updated After Item Edits"
    assert diag["action"] == "DYNAMICALLY_RECALCULATE_HEADER_ASSVAL"
    assert diag["correct_payload"]["ValDtls"]["AssVal"] == Decimal("8000.00")
    assert "Ensure ValDtls.AssVal dynamically recalculates the sum of all ItemList[i].AssAmt" in diag["reason"]
    assert "5000 + 3000 = 8000" in diag["reason"]


def test_classify_2182_scenario_2_double_discount():
    """Verify Scenario 2: Pre-tax Discount Deducted Twice."""
    items = [
        {"AssAmt": 9000.00, "TotAmt": 10000.00, "Discount": 1000.00}
    ]
    diag = classify_rule_2182_diagnostic(
        header_assval=8000.00,
        sum_item_assamt=9000.00,
        sum_item_totamt=10000.00,
        header_discount=1000.00,
        items=items
    )
    assert diag["is_valid"] is False
    assert diag["error_code"] == 2182
    assert diag["scenario"] == "PRE_TAX_DISCOUNT_DEDUCTED_TWICE"
    assert diag["scenario_name"] == "Pre-tax Discount Deducted Twice"
    assert diag["action"] == "REVERT_DOUBLE_DISCOUNT"
    assert diag["correct_payload"]["ValDtls"]["AssVal"] == Decimal("9000.00")
    assert diag["correct_payload"]["ValDtls"]["Discount"] == Decimal("1000.00")
    assert "In e-Invoicing, AssVal must equal the sum of item assessable values (AssAmt)" in diag["reason"]
    assert "Deducting the discount again at ValDtls.AssVal causes a mismatch." in diag["reason"]


def test_classify_2182_scenario_3_paise_rounding():
    """Verify Scenario 3: Paise / Decimal Rounding Issue (333.33 x 3 = 999.99 vs 1000.00)."""
    items = [
        {"AssAmt": 333.33, "TotAmt": 333.33, "Discount": 0.0},
        {"AssAmt": 333.33, "TotAmt": 333.33, "Discount": 0.0},
        {"AssAmt": 333.33, "TotAmt": 333.33, "Discount": 0.0}
    ]
    diag = classify_rule_2182_diagnostic(
        header_assval=1000.00,
        sum_item_assamt=999.99,
        items=items
    )
    assert diag["is_valid"] is False
    assert diag["error_code"] == 2182
    assert diag["scenario"] == "PAISE_DECIMAL_ROUNDING_ISSUE"
    assert diag["scenario_name"] == "Paise / Decimal Rounding Issue"
    assert diag["action"] == "RECONCILE_PAISE_DECIMAL_ROUNDING"
    assert diag["correct_payload"]["ValDtls"]["AssVal"] == Decimal("999.99")
    assert "The sum of item AssAmt is 999.99, but the header was rounded up to 1000.00" in diag["reason"]
    assert "Line-item totals and header assessable values must be identical to 2 decimal places." in diag["reason"]


def test_classify_2182_scenario_4_gross_total_used():
    """Verify Scenario 4: Gross Total (TotAmt) Used Instead of AssAmt (10000 vs 9500)."""
    items = [
        {"AssAmt": 9500.00, "TotAmt": 10000.00, "Discount": 500.00}
    ]
    diag = classify_rule_2182_diagnostic(
        header_assval=10000.00,
        sum_item_assamt=9500.00,
        sum_item_totamt=10000.00,
        sum_item_discount=500.00,
        items=items
    )
    assert diag["is_valid"] is False
    assert diag["error_code"] == 2182
    assert diag["scenario"] == "GROSS_TOTAL_USED_AS_ASSVAL"
    assert diag["scenario_name"] == "Gross Total (TotAmt) Used Instead of AssAmt"
    assert diag["action"] == "USE_NET_ASSESSABLE_VALUE"
    assert diag["correct_payload"]["ValDtls"]["AssVal"] == Decimal("9500.00")
    assert "AssVal must strictly equal the sum of AssAmt (net taxable value), not TotAmt (gross value before discount)." in diag["reason"]


# ==============================================================================
# 2. DATA LAKEHOUSE (storage.py) FLATTENING & RECONCILIATION TESTS
# ==============================================================================

def test_lakehouse_scenario_1_stale_header_rectification(failing_scenario_1_stale_header):
    """Test Data Lakehouse flattening on Scenario 1: dynamically recalculates header AssVal to 8000.00."""
    rows = flatten_invoice_payload(failing_scenario_1_stale_header)
    assert len(rows) == 2

    # Both rows must receive the reconciled invoice-level assessable value
    for r in rows:
        assert r["inv_taxable_value"] == 8000.00
        assert r["sentinel_status_badge"] == "FLAGGED_AND_RECTIFIED"
        assert r["sentinel_risk_level"] == "HIGH"
        assert r["sentinel_risk_prob"] >= 0.95
        assert "Rule 2182 Violation (Header Not Updated After Item Edits)" in r["sentinel_audit_reasons"]
        assert "Ensure ValDtls.AssVal dynamically recalculates the sum of all ItemList[i].AssAmt (5000 + 3000 = 8000) before sending." in r["sentinel_audit_reasons"]


def test_lakehouse_scenario_2_double_discount_rectification(failing_scenario_2_double_discount):
    """Test Data Lakehouse flattening on Scenario 2: restores net assessable value 9000.00."""
    rows = flatten_invoice_payload(failing_scenario_2_double_discount)
    assert len(rows) == 1
    r = rows[0]

    assert r["inv_taxable_value"] == 9000.00
    assert r["sentinel_status_badge"] == "FLAGGED_AND_RECTIFIED"
    assert r["sentinel_risk_level"] == "HIGH"
    assert r["sentinel_risk_prob"] >= 0.95
    assert "Rule 2182 Violation (Pre-tax Discount Deducted Twice)" in r["sentinel_audit_reasons"]
    assert "In e-Invoicing, AssVal must equal the sum of item assessable values (AssAmt)" in r["sentinel_audit_reasons"]


def test_lakehouse_scenario_3_paise_rounding_rectification(failing_scenario_3_paise_rounding):
    """Test Data Lakehouse flattening on Scenario 3: reconciles header to line-item sum 999.99."""
    rows = flatten_invoice_payload(failing_scenario_3_paise_rounding)
    assert len(rows) == 3

    for r in rows:
        assert r["inv_taxable_value"] == 999.99
        assert r["sentinel_status_badge"] == "FLAGGED_AND_RECTIFIED"
        assert r["sentinel_risk_level"] == "HIGH"
        assert r["sentinel_risk_prob"] >= 0.95
        assert "Rule 2182 Violation (Paise / Decimal Rounding Issue)" in r["sentinel_audit_reasons"]
        assert "The sum of item AssAmt is 999.99, but the header was rounded up to 1000.00" in r["sentinel_audit_reasons"]


def test_lakehouse_scenario_4_gross_total_rectification(failing_scenario_4_gross_total_used):
    """Test Data Lakehouse flattening on Scenario 4: switches header AssVal from 10000.00 to 9500.00."""
    rows = flatten_invoice_payload(failing_scenario_4_gross_total_used)
    assert len(rows) == 1
    r = rows[0]

    assert r["inv_taxable_value"] == 9500.00
    assert r["sentinel_status_badge"] == "FLAGGED_AND_RECTIFIED"
    assert r["sentinel_risk_level"] == "HIGH"
    assert r["sentinel_risk_prob"] >= 0.95
    assert "Rule 2182 Violation (Gross Total (TotAmt) Used Instead of AssAmt)" in r["sentinel_audit_reasons"]
    assert "AssVal must strictly equal the sum of AssAmt (net taxable value), not TotAmt (gross value before discount)." in r["sentinel_audit_reasons"]


# ==============================================================================
# 3. PYDANTIC INVOICEPAYLOAD VALIDATION & FLATTENING TESTS
# ==============================================================================

def test_pydantic_rule_2182_validation_rejection(failing_scenario_1_stale_header):
    """Verify that InvoicePayload validation strictly rejects Rule 2182 mismatches."""
    with pytest.raises((NICValidationError, Exception)) as excinfo:
        InvoicePayload.model_validate(failing_scenario_1_stale_header)
    
    err_str = str(excinfo.value)
    assert "2182" in err_str
    assert "Taxable value of items" in err_str
    assert "Header Not Updated After Item Edits" in err_str


def test_pydantic_rule_2182_lakehouse_flattening(failing_scenario_1_stale_header):
    """Verify that when a valid/corrected Pydantic model is passed to flatten_invoice_payload, Lakehouse handles it cleanly."""
    valid_payload = dict(failing_scenario_1_stale_header)
    valid_payload["valdtls"]["AssVal"] = 8000.00

    model = InvoicePayload.model_validate(valid_payload)
    rows = flatten_invoice_payload(model)
    assert len(rows) == 2
    assert rows[0]["inv_taxable_value"] == 8000.00
    assert rows[1]["inv_taxable_value"] == 8000.00


# ==============================================================================
# 4. PARQUET STORAGE ROUND-TRIP & FLATTENED_INVOICE_SCHEMA VALIDATION
# ==============================================================================

def test_lakehouse_parquet_roundtrip_all_scenarios(
    failing_scenario_1_stale_header,
    failing_scenario_2_double_discount,
    failing_scenario_3_paise_rounding,
    failing_scenario_4_gross_total_used
):
    """Test storing rectified invoices from all 4 statutory scenarios to Parquet and reading back."""
    temp_dir = tempfile.mkdtemp()
    parquet_path = os.path.join(temp_dir, "test_rule_2182_lakehouse.parquet")

    try:
        all_rows = []
        for payload in [
            failing_scenario_1_stale_header,
            failing_scenario_2_double_discount,
            failing_scenario_3_paise_rounding,
            failing_scenario_4_gross_total_used
        ]:
            rectified = flatten_invoice_payload(payload)
            all_rows.extend(rectified)

        # 1. Write Parquet
        write_parquet(all_rows, parquet_path)
        assert os.path.exists(parquet_path)

        # 2. Read Parquet
        df = read_parquet(parquet_path)
        assert len(df) == 7  # 2 + 1 + 3 + 1 = 7 items

        # Check Schema Conformance
        for field in FLATTENED_INVOICE_SCHEMA:
            assert field.name in df.columns, f"Missing field: {field.name}"

        # Check Telemetry across all rows
        assert (df["sentinel_status_badge"] == "FLAGGED_AND_RECTIFIED").all()
        assert (df["sentinel_risk_level"] == "HIGH").all()
        assert (df["sentinel_risk_prob"] >= 0.95).all()

        # Check individual rectified invoice assessable values
        sc1_rows = df[df["invoice_id"] == "INV-26-2182-SC1"]
        assert sc1_rows["inv_taxable_value"].iloc[0] == 8000.00

        sc2_rows = df[df["invoice_id"] == "INV-26-2182-SC2"]
        assert sc2_rows["inv_taxable_value"].iloc[0] == 9000.00

        sc3_rows = df[df["invoice_id"] == "INV-26-2182-SC3"]
        assert sc3_rows["inv_taxable_value"].iloc[0] == 999.99

        sc4_rows = df[df["invoice_id"] == "INV-26-2182-SC4"]
        assert sc4_rows["inv_taxable_value"].iloc[0] == 9500.00

        # 3. Lakehouse Upsert: Append duplicate records and verify idempotent upsert
        append_to_parquet(all_rows, parquet_path, schema=FLATTENED_INVOICE_SCHEMA)
        df_appended = read_parquet(parquet_path)
        assert len(df_appended) == 7, "Lakehouse upsert maintains deduplicated record count"

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
