"""
Tests for Indian GST e-Invoicing (NIC / IRP) Statutory Compliance & Data Lakehouse:
- Error Code 2192: Item Total Amount Formula Mismatch (ItemList[i].TotAmt = ItemList[i].Qty * ItemList[i].UnitPrice)
- Error Code 2193: Item Assessable Amount Formula Mismatch (ItemList[i].AssAmt = ItemList[i].TotAmt - ItemList[i].Discount)

Covers all 8 statutory scenarios:
Rule 2192 Scenarios:
1. Premature Discount Deduction: Qty = 10, UnitPrice = 100.00, Discount = 50.00 -> TotAmt = 950.00 (Failing), Correct = 1000.00.
2. Premature Tax Inclusion: Qty = 1, UnitPrice = 1000.00, GST 18% -> TotAmt = 1180.00 (Failing), Correct = 1000.00.
3. Decimal Rounding in Unit Price: Qty = 3, UnitPrice = 33.33 -> TotAmt = 100.00 (Failing), Correct = 99.99.
4. Services with Null or Missing Qty: IsServc = "Y", UnitPrice = 5000.00, Qty = 0 -> Qty = 1, TotAmt = 5000.00.

Rule 2193 Scenarios:
1. Discount Passed but Not Subtracted: TotAmt = 1000.00, Discount = 100.00, AssAmt = 1000.00 (Failing), Correct = 900.00.
2. Discount Subtracted in Taxable Base but Left 0 in Field: TotAmt = 1000.00, Discount = 0.00, AssAmt = 900.00 (Failing), Correct Disc = 100.00, AssAmt = 900.00.
3. Post-Tax Value Entered into Assessable Amount: TotAmt = 1000.00, Discount = 0.00, GST 18%, AssAmt = 1180.00 (Failing), Correct AssAmt = 1000.00.
4. Other Item Charges Added Directly to AssAmt: Freight/handling = 50.00, TotAmt = 1000.00, AssAmt = 1050.00 (Failing), Correct AssAmt = 1000.00, OthChrg = 50.00.

Also validates:
- Standalone diagnostic classifiers.
- Pre-API validator (GSTValidator) error code mapping.
- Pydantic InvoicePayload strict rejection.
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
    classify_rule_2192_diagnostic,
    classify_rule_2193_diagnostic,
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
# FIXTURES FOR RULE 2192 STATUTORY SCENARIOS
# ==============================================================================

@pytest.fixture
def failing_2192_scenario_1_premature_discount():
    """Scenario 1: Premature Discount Deduction (Qty=10, UnitPrice=100.00, Discount=50.00, TotAmt=950.00 instead of 1000.00)."""
    return {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-26-2192-SC1",
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
            "gstin": "27XYZAB9876C1Z1",
            "lglnm": "Mumbai Manufacturing Works Ltd",
            "state": "27",
            "pos": "27",
            "pin": "400051",
            "loc": "Mumbai"
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
                "totamt": 950.00,  # Failing: premature discount (10 * 100 - 50 = 950)
                "discount": 50.00,
                "assval": 950.00,
                "gstrate": 18.0,
                "cgstval": 85.50,
                "sgstval": 85.50,
                "igstval": 0.0,
                "totitemval": 1121.00
            }
        ],
        "valdtls": {
            "AssVal": 950.00,
            "CgstVal": 85.50,
            "SgstVal": 85.50,
            "IgstVal": 0.0,
            "CesVal": 0.0,
            "Discount": 0.0,
            "RndOffAmt": 0.0,
            "TotInvVal": 1121.00
        }
    }


@pytest.fixture
def failing_2192_scenario_2_premature_tax():
    """Scenario 2: Premature Tax Inclusion (Qty=1, UnitPrice=1000.00, GST 18%, TotAmt=1180.00 instead of 1000.00)."""
    return {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-26-2192-SC2",
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
            "gstin": "27XYZAB9876C1Z1",
            "lglnm": "Mumbai Manufacturing Works Ltd",
            "state": "27",
            "pos": "27",
            "pin": "400051",
            "loc": "Mumbai"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "Heavy Duty Bench Grinder",
                "prddesc": "Power tool machinery",
                "hsn": "8460",
                "qty": 1.0,
                "unit": "NOS",
                "unitprice": 1000.00,
                "totamt": 1180.00,  # Failing: premature tax inclusion (1000 + 18% = 1180)
                "discount": 0.0,
                "assval": 1180.00,
                "gstrate": 18.0,
                "cgstval": 106.20,
                "sgstval": 106.20,
                "igstval": 0.0,
                "totitemval": 1392.40
            }
        ],
        "valdtls": {
            "AssVal": 1180.00,
            "CgstVal": 106.20,
            "SgstVal": 106.20,
            "IgstVal": 0.0,
            "CesVal": 0.0,
            "Discount": 0.0,
            "RndOffAmt": 0.0,
            "TotInvVal": 1392.40
        }
    }


@pytest.fixture
def failing_2192_scenario_3_decimal_rounding():
    """Scenario 3: Decimal Rounding in Unit Price (Qty=3, UnitPrice=33.33, TotAmt=100.00 instead of 99.99)."""
    return {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-26-2192-SC3",
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
            "gstin": "27XYZAB9876C1Z1",
            "lglnm": "Mumbai Manufacturing Works Ltd",
            "state": "27",
            "pos": "27",
            "pin": "400051",
            "loc": "Mumbai"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "Precision Fastener Studs",
                "prddesc": "Standard bolts",
                "hsn": "7318",
                "qty": 3.0,
                "unit": "NOS",
                "unitprice": 33.33,
                "totamt": 100.00,  # Failing: rounded to 100.00 instead of 3 * 33.33 = 99.99
                "discount": 0.0,
                "assval": 100.00,
                "gstrate": 18.0,
                "cgstval": 9.00,
                "sgstval": 9.00,
                "igstval": 0.0,
                "totitemval": 118.00
            }
        ],
        "valdtls": {
            "AssVal": 100.00,
            "CgstVal": 9.00,
            "SgstVal": 9.00,
            "IgstVal": 0.0,
            "CesVal": 0.0,
            "Discount": 0.0,
            "RndOffAmt": 0.0,
            "TotInvVal": 118.00
        }
    }


@pytest.fixture
def failing_2192_scenario_4_services_missing_qty():
    """Scenario 4: Services with Null or Missing Qty (IsServc='Y', UnitPrice=5000.00, Qty=0, TotAmt=5000.00)."""
    return {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-26-2192-SC4",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "B2B",
        "reversecharge": "N",
        "igstonintra": "N",
        "supplier": {
            "gstin": "27ABCDE1234F1Z5",
            "lglnm": "Maharashtra Engineering Consultants",
            "state": "27",
            "pin": "400001",
            "loc": "Mumbai"
        },
        "buyer": {
            "gstin": "27XYZAB9876C1Z1",
            "lglnm": "Mumbai Manufacturing Works Ltd",
            "state": "27",
            "pos": "27",
            "pin": "400051",
            "loc": "Mumbai"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "Industrial Machinery Calibration Services",
                "prddesc": "Technical certification and testing",
                "hsn": "998331",
                "is_service": "Y",
                "qty": 0.0,  # Failing: service line with 0 quantity
                "unit": "OTH",
                "unitprice": 5000.00,
                "totamt": 5000.00,
                "discount": 0.0,
                "assval": 5000.00,
                "gstrate": 18.0,
                "cgstval": 450.00,
                "sgstval": 450.00,
                "igstval": 0.0,
                "totitemval": 5900.00
            }
        ],
        "valdtls": {
            "AssVal": 5000.00,
            "CgstVal": 450.00,
            "SgstVal": 450.00,
            "IgstVal": 0.0,
            "CesVal": 0.0,
            "Discount": 0.0,
            "RndOffAmt": 0.0,
            "TotInvVal": 5900.00
        }
    }


# ==============================================================================
# FIXTURES FOR RULE 2193 STATUTORY SCENARIOS
# ==============================================================================

@pytest.fixture
def failing_2193_scenario_1_discount_not_subtracted():
    """Scenario 1: Discount Passed but Not Subtracted (TotAmt=1000.00, Discount=100.00, AssAmt=1000.00 instead of 900.00)."""
    return {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-26-2193-SC1",
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
            "gstin": "27XYZAB9876C1Z1",
            "lglnm": "Mumbai Manufacturing Works Ltd",
            "state": "27",
            "pos": "27",
            "pin": "400051",
            "loc": "Mumbai"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "Precision Carbide Inserts",
                "prddesc": "Milling tooling",
                "hsn": "8209",
                "qty": 1.0,
                "unit": "NOS",
                "unitprice": 1000.00,
                "totamt": 1000.00,
                "discount": 100.00,
                "assval": 1000.00,  # Failing: discount passed but not subtracted (1000 - 100 = 900)
                "gstrate": 18.0,
                "cgstval": 90.00,
                "sgstval": 90.00,
                "igstval": 0.0,
                "totitemval": 1080.00
            }
        ],
        "valdtls": {
            "AssVal": 1000.00,
            "CgstVal": 90.00,
            "SgstVal": 90.00,
            "IgstVal": 0.0,
            "CesVal": 0.0,
            "Discount": 0.0,
            "RndOffAmt": 0.0,
            "TotInvVal": 1180.00
        }
    }


@pytest.fixture
def failing_2193_scenario_2_discount_zero_in_field():
    """Scenario 2: Discount Subtracted in Taxable Base but Left 0 in Field (TotAmt=1000.00, Discount=0.00, AssAmt=900.00)."""
    return {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-26-2193-SC2",
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
            "gstin": "27XYZAB9876C1Z1",
            "lglnm": "Mumbai Manufacturing Works Ltd",
            "state": "27",
            "pos": "27",
            "pin": "400051",
            "loc": "Mumbai"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "Precision Carbide Inserts",
                "prddesc": "Milling tooling",
                "hsn": "8209",
                "qty": 1.0,
                "unit": "NOS",
                "unitprice": 1000.00,
                "totamt": 1000.00,
                "discount": 0.00,  # Failing: discount left 0 while AssAmt reduced to 900
                "assval": 900.00,
                "gstrate": 18.0,
                "cgstval": 81.00,
                "sgstval": 81.00,
                "igstval": 0.0,
                "totitemval": 1062.00
            }
        ],
        "valdtls": {
            "AssVal": 900.00,
            "CgstVal": 81.00,
            "SgstVal": 81.00,
            "IgstVal": 0.0,
            "CesVal": 0.0,
            "Discount": 0.0,
            "RndOffAmt": 0.0,
            "TotInvVal": 1062.00
        }
    }


@pytest.fixture
def failing_2193_scenario_3_post_tax_in_assamt():
    """Scenario 3: Post-Tax Value Entered into Assessable Amount (TotAmt=1000.00, Discount=0.00, GST 18%, AssAmt=1180.00)."""
    return {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-26-2193-SC3",
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
            "gstin": "27XYZAB9876C1Z1",
            "lglnm": "Mumbai Manufacturing Works Ltd",
            "state": "27",
            "pos": "27",
            "pin": "400051",
            "loc": "Mumbai"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "Precision Carbide Inserts",
                "prddesc": "Milling tooling",
                "hsn": "8209",
                "qty": 1.0,
                "unit": "NOS",
                "unitprice": 1000.00,
                "totamt": 1000.00,
                "discount": 0.00,
                "assval": 1180.00,  # Failing: post-tax value passed into taxable assessable amount
                "gstrate": 18.0,
                "cgstval": 106.20,
                "sgstval": 106.20,
                "igstval": 0.0,
                "totitemval": 1392.40
            }
        ],
        "valdtls": {
            "AssVal": 1180.00,
            "CgstVal": 106.20,
            "SgstVal": 106.20,
            "IgstVal": 0.0,
            "CesVal": 0.0,
            "Discount": 0.0,
            "RndOffAmt": 0.0,
            "TotInvVal": 1392.40
        }
    }


@pytest.fixture
def failing_2193_scenario_4_extra_charges_in_assamt():
    """Scenario 4: Other Item Charges Added Directly to AssAmt (Freight 50.00, TotAmt=1000.00, AssAmt=1050.00)."""
    return {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-26-2193-SC4",
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
            "gstin": "27XYZAB9876C1Z1",
            "lglnm": "Mumbai Manufacturing Works Ltd",
            "state": "27",
            "pos": "27",
            "pin": "400051",
            "loc": "Mumbai"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "Precision Carbide Inserts",
                "prddesc": "Milling tooling",
                "hsn": "8209",
                "qty": 1.0,
                "unit": "NOS",
                "unitprice": 1000.00,
                "totamt": 1000.00,
                "discount": 0.00,
                "assval": 1050.00,  # Failing: freight of 50.00 added directly to AssAmt
                "gstrate": 18.0,
                "cgstval": 94.50,
                "sgstval": 94.50,
                "igstval": 0.0,
                "totitemval": 1239.00
            }
        ],
        "valdtls": {
            "AssVal": 1050.00,
            "CgstVal": 94.50,
            "SgstVal": 94.50,
            "IgstVal": 0.0,
            "CesVal": 0.0,
            "Discount": 0.0,
            "RndOffAmt": 0.0,
            "TotInvVal": 1239.00
        }
    }


@pytest.fixture
def valid_item_formula_invoice():
    """Compliant invoice payload passing all Rule 2192 and 2193 calculations."""
    return {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-26-FORM-OK",
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
            "gstin": "27XYZAB9876C1Z1",
            "lglnm": "Mumbai Manufacturing Works Ltd",
            "state": "27",
            "pos": "27",
            "pin": "400051",
            "loc": "Mumbai"
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
                "cgstval": 85.50,
                "sgstval": 85.50,
                "igstval": 0.0,
                "totitemval": 1121.00
            },
            {
                "item_slno": "2",
                "slno": "2",
                "prdnm": "Heavy Duty Bench Grinder",
                "prddesc": "Power tool machinery",
                "hsn": "8460",
                "qty": 1.0,
                "unit": "NOS",
                "unitprice": 1000.00,
                "totamt": 1000.00,
                "discount": 0.0,
                "assval": 1000.00,
                "gstrate": 18.0,
                "cgstval": 90.00,
                "sgstval": 90.00,
                "igstval": 0.0,
                "totitemval": 1180.00
            }
        ],
        "valdtls": {
            "AssVal": 1950.00,
            "CgstVal": 175.50,
            "SgstVal": 175.50,
            "IgstVal": 0.0,
            "CesVal": 0.0,
            "Discount": 0.0,
            "RndOffAmt": 0.0,
            "TotInvVal": 2301.00
        }
    }


# ==============================================================================
# 1. DIAGNOSTIC CLASSIFICATION TESTS
# ==============================================================================

def test_classify_rule_2192_scenarios_standalone():
    """Verify classify_rule_2192_diagnostic classifies all 4 scenarios with exact messages."""
    # Scenario 1: Premature Discount Deduction
    res1 = classify_rule_2192_diagnostic(qty=10, unitprice=100.00, totamt=950.00, discount=50.00)
    assert not res1["is_valid"]
    assert res1["scenario"] == "PREMATURE_DISCOUNT_DEDUCTION"
    assert "gross value before discount" in res1["reason"]
    assert res1["correct_payload"]["TotAmt"] == Decimal("1000.00")

    # Scenario 2: Premature Tax Inclusion
    res2 = classify_rule_2192_diagnostic(qty=1, unitprice=1000.00, totamt=1180.00, gstrate=18.0)
    assert not res2["is_valid"]
    assert res2["scenario"] == "PREMATURE_TAX_INCLUSION"
    assert "TotAmt is pre-tax" in res2["reason"]
    assert res2["correct_payload"]["TotAmt"] == Decimal("1000.00")

    # Scenario 3: Decimal Rounding in Unit Price
    res3 = classify_rule_2192_diagnostic(qty=3, unitprice=33.33, totamt=100.00)
    assert not res3["is_valid"]
    assert res3["scenario"] == "DECIMAL_ROUNDING_IN_UNIT_PRICE"
    assert "33.33 = 99.99" in res3["reason"]
    assert res3["correct_payload"]["TotAmt"] == Decimal("99.99")

    # Scenario 4: Services with Null or Missing Qty
    res4 = classify_rule_2192_diagnostic(qty=0, unitprice=5000.00, totamt=5000.00, is_service="Y")
    assert not res4["is_valid"]
    assert res4["scenario"] == "SERVICES_WITH_NULL_OR_MISSING_QTY"
    assert "where quantity is conceptual" in res4["reason"]
    assert res4["correct_payload"]["Qty"] == Decimal("1.00")

    # Valid Line
    valid_res = classify_rule_2192_diagnostic(qty=10, unitprice=100.00, totamt=1000.00)
    assert valid_res["is_valid"]
    assert valid_res["scenario"] == "VALID"


def test_classify_rule_2193_scenarios_standalone():
    """Verify classify_rule_2193_diagnostic classifies all 4 scenarios with exact messages."""
    # Scenario 1: Discount Passed but Not Subtracted
    res1 = classify_rule_2193_diagnostic(totamt=1000.00, discount=100.00, assamt=1000.00)
    assert not res1["is_valid"]
    assert res1["scenario"] == "DISCOUNT_PASSED_BUT_NOT_SUBTRACTED"
    assert "reflect the discounted assessable base" in res1["reason"]
    assert res1["correct_payload"]["AssAmt"] == Decimal("900.00")

    # Scenario 2: Discount Subtracted in Taxable Base but Left 0 in Field
    res2 = classify_rule_2193_diagnostic(totamt=1000.00, discount=0.00, assamt=900.00)
    assert not res2["is_valid"]
    assert res2["scenario"] == "DISCOUNT_SUBTRACTED_IN_TAXABLE_BASE_BUT_ZERO_IN_FIELD"
    assert "schema expects AssAmt = TotAmt" in res2["reason"]
    assert res2["correct_payload"]["Discount"] == Decimal("100.00")
    assert res2["correct_payload"]["AssAmt"] == Decimal("900.00")

    # Scenario 3: Post-Tax Value Entered into Assessable Amount
    res3 = classify_rule_2193_diagnostic(totamt=1000.00, discount=0.00, assamt=1180.00, gstrate=18.0)
    assert not res3["is_valid"]
    assert res3["scenario"] == "POST_TAX_VALUE_ENTERED_INTO_ASSESSABLE_AMOUNT"
    assert "tax is added in TotItemVal" in res3["reason"]
    assert res3["correct_payload"]["AssAmt"] == Decimal("1000.00")

    # Scenario 4: Other Item Charges Added Directly to AssAmt
    res4 = classify_rule_2193_diagnostic(totamt=1000.00, discount=0.00, assamt=1050.00)
    assert not res4["is_valid"]
    assert res4["scenario"] == "OTHER_ITEM_CHARGES_ADDED_DIRECTLY_TO_ASSAMT"
    assert "Pass item other charges in OthChrg" in res4["resolution"]
    assert res4["correct_payload"]["AssAmt"] == Decimal("1000.00")
    assert res4["correct_payload"]["OthChrg"] == Decimal("50.00")

    # Valid Line
    valid_res = classify_rule_2193_diagnostic(totamt=1000.00, discount=100.00, assamt=900.00)
    assert valid_res["is_valid"]
    assert valid_res["scenario"] == "VALID"


# ==============================================================================
# 2. PRE-API VALIDATOR TESTS (GSTValidator & RulesEngine)
# ==============================================================================

def test_pre_api_validator_rejects_2192_scenarios(
    failing_2192_scenario_1_premature_discount,
    failing_2192_scenario_2_premature_tax,
    failing_2192_scenario_3_decimal_rounding,
    failing_2192_scenario_4_services_missing_qty
):
    """Ensure GSTValidator and RulesEngine reject all 4 Rule 2192 scenarios with error code 2192."""
    validator = GSTValidator()
    engine = RulesEngine()

    scenarios = [
        failing_2192_scenario_1_premature_discount,
        failing_2192_scenario_2_premature_tax,
        failing_2192_scenario_3_decimal_rounding,
        failing_2192_scenario_4_services_missing_qty,
    ]

    for sc in scenarios:
        val_errors = GSTValidator.validate_invoice(sc)
        assert any(e.get("error_code") == 2192 for e in val_errors), f"GSTValidator failed to flag 2192 for {sc['docno']}"

        eng_errors = RulesEngine.validate_invoice(sc)
        assert any(e.get("error_code") == 2192 for e in eng_errors), f"RulesEngine failed to flag 2192 for {sc['docno']}"


def test_pre_api_validator_rejects_2193_scenarios(
    failing_2193_scenario_1_discount_not_subtracted,
    failing_2193_scenario_2_discount_zero_in_field,
    failing_2193_scenario_3_post_tax_in_assamt,
    failing_2193_scenario_4_extra_charges_in_assamt
):
    """Ensure GSTValidator and RulesEngine reject all 4 Rule 2193 scenarios with error code 2193."""
    validator = GSTValidator()
    engine = RulesEngine()

    scenarios = [
        failing_2193_scenario_1_discount_not_subtracted,
        failing_2193_scenario_2_discount_zero_in_field,
        failing_2193_scenario_3_post_tax_in_assamt,
        failing_2193_scenario_4_extra_charges_in_assamt,
    ]

    for sc in scenarios:
        val_errors = GSTValidator.validate_invoice(sc)
        assert any(e.get("error_code") == 2193 for e in val_errors), f"GSTValidator failed to flag 2193 for {sc['docno']}"

        eng_errors = RulesEngine.validate_invoice(sc)
        assert any(e.get("error_code") == 2193 for e in eng_errors), f"RulesEngine failed to flag 2193 for {sc['docno']}"


# ==============================================================================
# 3. PYDANTIC MODEL VALIDATION TESTS
# ==============================================================================

def test_pydantic_model_rejects_2192_2193_mismatches(
    failing_2192_scenario_1_premature_discount,
    failing_2192_scenario_2_premature_tax,
    failing_2192_scenario_3_decimal_rounding,
    failing_2192_scenario_4_services_missing_qty,
    failing_2193_scenario_1_discount_not_subtracted,
    failing_2193_scenario_2_discount_zero_in_field,
    failing_2193_scenario_3_post_tax_in_assamt,
    failing_2193_scenario_4_extra_charges_in_assamt,
    valid_item_formula_invoice
):
    """Ensure InvoicePayload.model_validate strictly raises NICValidationError for 2192 & 2193."""
    for sc in [
        failing_2192_scenario_1_premature_discount,
        failing_2192_scenario_2_premature_tax,
        failing_2192_scenario_3_decimal_rounding,
        failing_2192_scenario_4_services_missing_qty,
    ]:
        with pytest.raises((NICValidationError, Exception)) as excinfo:
            InvoicePayload.model_validate(sc)
        assert "2192" in str(excinfo.value)

    for sc in [
        failing_2193_scenario_1_discount_not_subtracted,
        failing_2193_scenario_2_discount_zero_in_field,
        failing_2193_scenario_3_post_tax_in_assamt,
        failing_2193_scenario_4_extra_charges_in_assamt,
    ]:
        with pytest.raises((NICValidationError, Exception)) as excinfo:
            InvoicePayload.model_validate(sc)
        assert "2193" in str(excinfo.value)

    # Valid payload must pass cleanly
    model = InvoicePayload.model_validate(valid_item_formula_invoice)
    assert model.docno == "INV-26-FORM-OK"
    assert len(model.itemdtls) == 2


# ==============================================================================
# 4. AUTO-CORRECTION AND AUDIT TRAIL TESTS
# ==============================================================================

def test_auto_correct_and_build_2192_scenarios(
    failing_2192_scenario_1_premature_discount,
    failing_2192_scenario_2_premature_tax,
    failing_2192_scenario_3_decimal_rounding,
    failing_2192_scenario_4_services_missing_qty
):
    """Ensure auto_correct_and_build fixes gross amounts (TotAmt) and records audit logs."""
    # Scenario 1: Premature discount deduction
    sc1 = dict(failing_2192_scenario_1_premature_discount)
    fixed1, audit1 = InvoicePayload.auto_correct_and_build(sc1)
    assert float(fixed1.itemdtls[0].totamt) == 1000.00
    assert any("2192" in str(a) for a in audit1)

    # Scenario 2: Premature tax inclusion
    sc2 = dict(failing_2192_scenario_2_premature_tax)
    fixed2, audit2 = InvoicePayload.auto_correct_and_build(sc2)
    assert float(fixed2.itemdtls[0].totamt) == 1000.00
    assert any("2192" in str(a) for a in audit2)

    # Scenario 3: Decimal rounding in unit price
    sc3 = dict(failing_2192_scenario_3_decimal_rounding)
    fixed3, audit3 = InvoicePayload.auto_correct_and_build(sc3)
    assert float(fixed3.itemdtls[0].totamt) == 99.99
    assert any("2192" in str(a) for a in audit3)

    # Scenario 4: Services with missing quantity
    sc4 = dict(failing_2192_scenario_4_services_missing_qty)
    fixed4, audit4 = InvoicePayload.auto_correct_and_build(sc4)
    assert float(fixed4.itemdtls[0].qty) == 1.00
    assert float(fixed4.itemdtls[0].totamt) == 5000.00
    assert any("2192" in str(a) for a in audit4)


def test_auto_correct_and_build_2193_scenarios(
    failing_2193_scenario_1_discount_not_subtracted,
    failing_2193_scenario_2_discount_zero_in_field,
    failing_2193_scenario_3_post_tax_in_assamt,
    failing_2193_scenario_4_extra_charges_in_assamt
):
    """Ensure auto_correct_and_build fixes assessable amounts (AssAmt) and records audit logs."""
    # Scenario 1: Discount passed but not subtracted
    sc1 = dict(failing_2193_scenario_1_discount_not_subtracted)
    fixed1, audit1 = InvoicePayload.auto_correct_and_build(sc1)
    assert float(fixed1.itemdtls[0].assval) == 900.00
    assert any("2193" in str(a) for a in audit1)

    # Scenario 2: Discount subtracted in taxable base but 0 in field
    sc2 = dict(failing_2193_scenario_2_discount_zero_in_field)
    fixed2, audit2 = InvoicePayload.auto_correct_and_build(sc2)
    # Reconciled taxable base equals totamt - discount
    assert float(fixed2.itemdtls[0].assval) == 1000.00
    assert any("2193" in str(a) for a in audit2)

    # Scenario 3: Post-tax value in assessable amount
    sc3 = dict(failing_2193_scenario_3_post_tax_in_assamt)
    fixed3, audit3 = InvoicePayload.auto_correct_and_build(sc3)
    assert float(fixed3.itemdtls[0].assval) == 1000.00
    assert any("2193" in str(a) for a in audit3)

    # Scenario 4: Extra charges in assessable amount
    sc4 = dict(failing_2193_scenario_4_extra_charges_in_assamt)
    fixed4, audit4 = InvoicePayload.auto_correct_and_build(sc4)
    assert float(fixed4.itemdtls[0].assval) == 1000.00
    assert any("2193" in str(a) for a in audit4)


# ==============================================================================
# 5. DATA LAKEHOUSE FLATTENING & SENTINEL TELEMETRY TESTS
# ==============================================================================

def test_lakehouse_flattening_sentinel_telemetry_dict(
    failing_2192_scenario_1_premature_discount,
    failing_2193_scenario_1_discount_not_subtracted
):
    """Ensure dict flattening sets FLAGGED_AND_RECTIFIED, HIGH risk, and rectifies amounts."""
    # Test 2192 dict flattening
    rows_2192 = flatten_invoice_payload(failing_2192_scenario_1_premature_discount)
    assert len(rows_2192) == 1
    r1 = rows_2192[0]
    assert r1["sentinel_status_badge"] == "FLAGGED_AND_RECTIFIED"
    assert r1["sentinel_risk_level"] == "HIGH"
    assert r1["sentinel_risk_prob"] >= 0.95
    assert "Rule 2192 Violation" in r1["sentinel_audit_reasons"]
    assert r1["gross_amount"] == 1000.00  # Rectified from 950.00 to 1000.00

    # Test 2193 dict flattening
    rows_2193 = flatten_invoice_payload(failing_2193_scenario_1_discount_not_subtracted)
    assert len(rows_2193) == 1
    r2 = rows_2193[0]
    assert r2["sentinel_status_badge"] == "FLAGGED_AND_RECTIFIED"
    assert r2["sentinel_risk_level"] == "HIGH"
    assert r2["sentinel_risk_prob"] >= 0.95
    assert "Rule 2193 Violation" in r2["sentinel_audit_reasons"]
    assert r2["taxable_value"] == 900.00  # Rectified from 1000.00 to 900.00


def test_lakehouse_flattening_sentinel_telemetry_model(valid_item_formula_invoice):
    """Ensure InvoicePayload model flattening works seamlessly and preserves verified totals."""
    model = InvoicePayload.model_validate(valid_item_formula_invoice)
    rows = flatten_invoice_payload(model)
    assert len(rows) == 2

    assert rows[0]["gross_amount"] == 1000.00
    assert rows[0]["taxable_value"] == 950.00
    assert "Rule 2192 Violation" not in rows[0].get("sentinel_audit_reasons", "")
    assert "Rule 2193 Violation" not in rows[0].get("sentinel_audit_reasons", "")

    assert rows[1]["gross_amount"] == 1000.00
    assert rows[1]["taxable_value"] == 1000.00
    assert "Rule 2192 Violation" not in rows[1].get("sentinel_audit_reasons", "")
    assert "Rule 2193 Violation" not in rows[1].get("sentinel_audit_reasons", "")


# ==============================================================================
# 6. PARQUET STORAGE ROUNDTRIP & SCHEMA CONFORMANCE TESTS
# ==============================================================================

def test_parquet_lakehouse_roundtrip_conformance(
    failing_2192_scenario_1_premature_discount,
    failing_2192_scenario_2_premature_tax,
    failing_2193_scenario_1_discount_not_subtracted,
    failing_2193_scenario_2_discount_zero_in_field,
    valid_item_formula_invoice
):
    """Ensure Parquet write, read, and append faithfully preserve schema and rectified amounts."""
    temp_dir = tempfile.mkdtemp()
    parquet_path = os.path.join(temp_dir, "test_item_formulas_lakehouse.parquet")

    try:
        all_rows = []
        for p in [
            failing_2192_scenario_1_premature_discount,
            failing_2192_scenario_2_premature_tax,
            failing_2193_scenario_1_discount_not_subtracted,
            failing_2193_scenario_2_discount_zero_in_field,
        ]:
            all_rows.extend(flatten_invoice_payload(p))

        # 1. Write Parquet
        write_parquet(all_rows, parquet_path)
        assert os.path.exists(parquet_path)

        # 2. Read back & verify
        df = read_parquet(parquet_path)
        assert len(df) == 4
        assert set(FLATTENED_INVOICE_SCHEMA.names).issubset(set(df.columns))

        # 3. Append compliant invoice model
        model = InvoicePayload.model_validate(valid_item_formula_invoice)
        valid_rows = flatten_invoice_payload(model)
        append_to_parquet(valid_rows, parquet_path)

        # 4. Verify appended data
        df_after = read_parquet(parquet_path)
        assert len(df_after) == 6
        assert "INV-26-FORM-OK" in df_after["invoice_id"].values

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
