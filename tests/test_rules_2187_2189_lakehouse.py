"""
Test Suite: NIC Error Codes 2187 and 2189 Statutory Compliance & Data Lakehouse Reconciliation.
File: tests/test_rules_2187_2189_lakehouse.py

Validates Indian GST e-Invoicing (NIC / IRP) Error Code 2187:
"State Cess Value of all items must be equal to total State CessValue"
Formula:
    ValDtls.StCesVal = sum(ItemList[i].StateCesAmt + ItemList[i].StateCesNonAdvlAmt)

Validates Indian GST e-Invoicing (NIC / IRP) Error Code 2189:
"Total Invoice Value is not matching with calculated value"
Formula:
    ValDtls.TotInvVal = sum(ItemList[i].TotItemVal) + ValDtls.OthChrg - ValDtls.Discount + ValDtls.RndOffAmt
Tolerance:
    Within +/- 1.00 tolerance limit.
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
    classify_rule_2187_diagnostic,
    classify_rule_2189_diagnostic,
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
# FIXTURES FOR RULE 2187 SCENARIOS
# ==============================================================================

@pytest.fixture
def failing_2187_scenario_1_recalc():
    """Scenario 1: Header Not Recalculated After Item Edits (100.00 + 50.00 = 150.00, Header = 100.00)."""
    return {
        "self_gstin": "32ABCDE1234F1Z5",
        "docno": "INV-26-2187-SC1",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "B2B",
        "supplier": {
            "gstin": "32ABCDE1234F1Z5",
            "lglnm": "Kerala Flood Cess Attracting Corp",
            "state": "32",
            "pin": "682001",
            "loc": "Kochi"
        },
        "buyer": {
            "gstin": "32XYZAB9876C1Z1",
            "lglnm": "Kochi Wholesale Distributors",
            "state": "32",
            "pos": "32",
            "pin": "682016",
            "loc": "Ernakulam"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "Kerala Specialized Product A",
                "hsn": "2202",
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
                "cesval": 0.0,
                "statecesval": 100.0,
                "totitemval": 11900.0
            },
            {
                "item_slno": "2",
                "slno": "2",
                "prdnm": "Kerala Specialized Product B",
                "hsn": "2202",
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
                "cesval": 0.0,
                "statecesval": 50.0,
                "totitemval": 5950.0
            }
        ],
        "valdtls": {
            "AssVal": 15000.0,
            "CgstVal": 1350.0,
            "SgstVal": 1350.0,
            "IgstVal": 0.0,
            "CesVal": 0.0,
            "StCesVal": 100.0,  # Failing: 100.00 instead of 150.00
            "Discount": 0.0,
            "OthChrg": 0.0,
            "RndOffAmt": 0.0,
            "TotInvVal": 17850.0
        }
    }


@pytest.fixture
def failing_2187_scenario_2_central_vs_state_confusion():
    """Scenario 2: State Cess vs Central Cess Field Confusion (StateCesAmt = 200.00 passed under CesVal = 200.00, StCesVal = 0.00)."""
    return {
        "self_gstin": "32ABCDE1234F1Z5",
        "docno": "INV-26-2187-SC2",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "B2B",
        "supplier": {
            "gstin": "32ABCDE1234F1Z5",
            "lglnm": "Kerala Specialty Goods Ltd",
            "state": "32",
            "pin": "682001",
            "loc": "Kochi"
        },
        "buyer": {
            "gstin": "32XYZAB9876C1Z1",
            "lglnm": "Ernakulam Trading Co",
            "state": "32",
            "pos": "32",
            "pin": "682016",
            "loc": "Ernakulam"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "State Cess Item",
                "hsn": "2202",
                "qty": 1.0,
                "unit": "NOS",
                "unitprice": 20000.0,
                "totamt": 20000.0,
                "discount": 0.0,
                "assval": 20000.0,
                "gstrate": 18.0,
                "cgstval": 1800.0,
                "sgstval": 1800.0,
                "igstval": 0.0,
                "cesval": 0.0,
                "statecesval": 200.0,
                "totitemval": 23800.0
            }
        ],
        "valdtls": {
            "AssVal": 20000.0,
            "CgstVal": 1800.0,
            "SgstVal": 1800.0,
            "IgstVal": 0.0,
            "CesVal": 200.0,    # Failing: Passed under Central Cess
            "StCesVal": 0.0,    # Failing: 0.00 under State Cess
            "Discount": 0.0,
            "OthChrg": 0.0,
            "RndOffAmt": 0.0,
            "TotInvVal": 23800.0
        }
    }


@pytest.fixture
def failing_2187_scenario_3_non_ad_valorem_omitted():
    """Scenario 3: Specific (Non-Ad-Valorem) State Cess Omitted (StateCesAmt = 100.00, StateCesNonAdvlAmt = 25.00, Header = 100.00)."""
    return {
        "self_gstin": "32ABCDE1234F1Z5",
        "docno": "INV-26-2187-SC3",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "B2B",
        "supplier": {
            "gstin": "32ABCDE1234F1Z5",
            "lglnm": "Kerala Mineral Water Ltd",
            "state": "32",
            "pin": "682001",
            "loc": "Kochi"
        },
        "buyer": {
            "gstin": "32XYZAB9876C1Z1",
            "lglnm": "Kochi Retail Hub",
            "state": "32",
            "pos": "32",
            "pin": "682016",
            "loc": "Ernakulam"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "Mineral Water Specific Levy",
                "hsn": "2201",
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
                "cesval": 0.0,
                "statecesval": 100.0,
                "statecesnonadvl": 25.0,
                "totitemval": 11925.0
            }
        ],
        "valdtls": {
            "AssVal": 10000.0,
            "CgstVal": 900.0,
            "SgstVal": 900.0,
            "IgstVal": 0.0,
            "CesVal": 0.0,
            "StCesVal": 100.0,  # Failing: Specific State Cess omitted (100.00 instead of 125.00)
            "Discount": 0.0,
            "OthChrg": 0.0,
            "RndOffAmt": 0.0,
            "TotInvVal": 11925.0
        }
    }


@pytest.fixture
def failing_2187_scenario_4_paise_truncation():
    """Scenario 4: Decimal / Paise Truncation (33.33 x 3 = 99.99, Header = 100.00)."""
    return {
        "self_gstin": "32ABCDE1234F1Z5",
        "docno": "INV-26-2187-SC4",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "B2B",
        "supplier": {
            "gstin": "32ABCDE1234F1Z5",
            "lglnm": "Kerala Beverage Distribution Ltd",
            "state": "32",
            "pin": "682001",
            "loc": "Kochi"
        },
        "buyer": {
            "gstin": "32XYZAB9876C1Z1",
            "lglnm": "Kerala Retail Outlet",
            "state": "32",
            "pos": "32",
            "pin": "682016",
            "loc": "Ernakulam"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "Item Part 1",
                "hsn": "2202",
                "qty": 1.0,
                "unit": "NOS",
                "unitprice": 3333.0,
                "totamt": 3333.0,
                "discount": 0.0,
                "assval": 3333.0,
                "gstrate": 18.0,
                "cgstval": 299.97,
                "sgstval": 299.97,
                "igstval": 0.0,
                "cesval": 0.0,
                "statecesval": 33.33,
                "totitemval": 3966.27
            },
            {
                "item_slno": "2",
                "slno": "2",
                "prdnm": "Item Part 2",
                "hsn": "2202",
                "qty": 1.0,
                "unit": "NOS",
                "unitprice": 3333.0,
                "totamt": 3333.0,
                "discount": 0.0,
                "assval": 3333.0,
                "gstrate": 18.0,
                "cgstval": 299.97,
                "sgstval": 299.97,
                "igstval": 0.0,
                "cesval": 0.0,
                "statecesval": 33.33,
                "totitemval": 3966.27
            },
            {
                "item_slno": "3",
                "slno": "3",
                "prdnm": "Item Part 3",
                "hsn": "2202",
                "qty": 1.0,
                "unit": "NOS",
                "unitprice": 3334.0,
                "totamt": 3334.0,
                "discount": 0.0,
                "assval": 3334.0,
                "gstrate": 18.0,
                "cgstval": 300.06,
                "sgstval": 300.06,
                "igstval": 0.0,
                "cesval": 0.0,
                "statecesval": 33.33,
                "totitemval": 3967.45
            }
        ],
        "valdtls": {
            "AssVal": 10000.0,
            "CgstVal": 900.0,
            "SgstVal": 900.0,
            "IgstVal": 0.0,
            "CesVal": 0.0,
            "StCesVal": 100.0,  # Failing: 100.00 instead of 99.99
            "Discount": 0.0,
            "OthChrg": 0.0,
            "RndOffAmt": 0.0,
            "TotInvVal": 11900.0
        }
    }


# ==============================================================================
# FIXTURES FOR RULE 2189 SCENARIOS
# ==============================================================================

@pytest.fixture
def failing_2189_scenario_1_double_discount():
    """Scenario 1: Item-Level Discount Subtracted Again at Header."""
    return {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-26-2189-SC1",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "B2B",
        "supplier": {
            "gstin": "27ABCDE1234F1Z5",
            "lglnm": "Maharashtra Industrial Tools Ltd",
            "state": "27",
            "pin": "400001",
            "loc": "Mumbai"
        },
        "buyer": {
            "gstin": "27XYZAB9876C1Z1",
            "lglnm": "Pune Machinery Distributors",
            "state": "27",
            "pos": "27",
            "pin": "411001",
            "loc": "Pune"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "Precision Lathe Tool",
                "hsn": "8466",
                "qty": 1.0,
                "unit": "NOS",
                "unitprice": 10000.0,
                "totamt": 10000.0,
                "discount": 1000.0,  # Item discount already deducted
                "assval": 9000.0,
                "gstrate": 18.0,
                "cgstval": 810.0,
                "sgstval": 810.0,
                "igstval": 0.0,
                "cesval": 0.0,
                "totitemval": 10620.0
            }
        ],
        "valdtls": {
            "AssVal": 9000.0,
            "CgstVal": 810.0,
            "SgstVal": 810.0,
            "IgstVal": 0.0,
            "CesVal": 0.0,
            "StCesVal": 0.0,
            "Discount": 1000.0,  # Failing: Subtracted again at header!
            "OthChrg": 0.0,
            "RndOffAmt": 0.0,
            "TotInvVal": 9620.0  # Discrepancy: Expected 10620.00
        }
    }


@pytest.fixture
def failing_2189_scenario_2_other_charges_omitted():
    """Scenario 2: Other Charges (OthChrg) Left Out of Total (Items = 10000.00, OthChrg = 500.00, TotInvVal = 10000.00)."""
    return {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-26-2189-SC2",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "B2B",
        "supplier": {
            "gstin": "27ABCDE1234F1Z5",
            "lglnm": "Maharashtra Logistics Supplies",
            "state": "27",
            "pin": "400001",
            "loc": "Mumbai"
        },
        "buyer": {
            "gstin": "27XYZAB9876C1Z1",
            "lglnm": "Nashik Retail Merchants",
            "state": "27",
            "pos": "27",
            "pin": "422001",
            "loc": "Nashik"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "Corrugated Cartons",
                "hsn": "4819",
                "qty": 10.0,
                "unit": "NOS",
                "unitprice": 1000.0,
                "totamt": 10000.0,
                "discount": 0.0,
                "assval": 10000.0,
                "gstrate": 0.0,
                "cgstval": 0.0,
                "sgstval": 0.0,
                "igstval": 0.0,
                "cesval": 0.0,
                "totitemval": 10000.0
            }
        ],
        "valdtls": {
            "AssVal": 10000.0,
            "CgstVal": 0.0,
            "SgstVal": 0.0,
            "IgstVal": 0.0,
            "CesVal": 0.0,
            "StCesVal": 0.0,
            "Discount": 0.0,
            "OthChrg": 500.0,
            "RndOffAmt": 0.0,
            "TotInvVal": 10000.0  # Failing: Omitted 500.00 other charges (should be 10500.00)
        }
    }


@pytest.fixture
def failing_2189_scenario_3_rounding_inversion():
    """Scenario 3: Rounding Off (RndOffAmt) Arithmetic Inversion (Pre-round 11800.40, Round -0.40, Payload RndOffAmt = 0.40)."""
    return {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-26-2189-SC3",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "B2B",
        "supplier": {
            "gstin": "27ABCDE1234F1Z5",
            "lglnm": "Maharashtra Equipment Corp",
            "state": "27",
            "pin": "400001",
            "loc": "Mumbai"
        },
        "buyer": {
            "gstin": "27XYZAB9876C1Z1",
            "lglnm": "Thane Industrial Hub",
            "state": "27",
            "pos": "27",
            "pin": "400601",
            "loc": "Thane"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "Precision Component",
                "hsn": "8466",
                "qty": 1.0,
                "unit": "NOS",
                "unitprice": 10000.34,
                "totamt": 10000.34,
                "discount": 0.0,
                "assval": 10000.34,
                "gstrate": 18.0,
                "cgstval": 900.03,
                "sgstval": 900.03,
                "igstval": 0.0,
                "cesval": 0.0,
                "totitemval": 11800.40
            }
        ],
        "valdtls": {
            "AssVal": 10000.34,
            "CgstVal": 900.03,
            "SgstVal": 900.03,
            "IgstVal": 0.0,
            "CesVal": 0.0,
            "StCesVal": 0.0,
            "Discount": 0.0,
            "OthChrg": 0.0,
            "RndOffAmt": 0.40,      # Failing: Positive 0.40 instead of -0.40
            "TotInvVal": 11800.00
        }
    }


@pytest.fixture
def failing_2189_scenario_4_totitemval_discrepancy():
    """Scenario 4: Total Item Value (TotItemVal) Formula Discrepancy (AssAmt = 10000, IgstAmt = 1800, TotItemVal passed as 10000.00)."""
    return {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-26-2189-SC4",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "B2B",
        "supplier": {
            "gstin": "27ABCDE1234F1Z5",
            "lglnm": "Maharashtra High-Tech Systems",
            "state": "27",
            "pin": "400001",
            "loc": "Mumbai"
        },
        "buyer": {
            "gstin": "29XYZAB9876C1Z1",
            "lglnm": "Bengaluru Systems Pvt Ltd",
            "state": "29",
            "pos": "29",
            "pin": "560001",
            "loc": "Bengaluru"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "High-Tech Controller",
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
                "cesval": 0.0,
                "totitemval": 10000.0  # Failing: Missing taxes (10000.00 instead of 11800.00)
            }
        ],
        "valdtls": {
            "AssVal": 10000.0,
            "CgstVal": 0.0,
            "SgstVal": 0.0,
            "IgstVal": 1800.0,
            "CesVal": 0.0,
            "StCesVal": 0.0,
            "Discount": 0.0,
            "OthChrg": 0.0,
            "RndOffAmt": 0.0,
            "TotInvVal": 10000.0  # Repercussion of wrong TotItemVal
        }
    }


# ==============================================================================
# 1. DIAGNOSTIC CLASSIFICATION TESTS
# ==============================================================================

def test_classify_rule_2187_scenarios_standalone():
    """Verify classify_rule_2187_diagnostic classifies all 4 scenarios with exact statutory text."""
    # Scenario 1: Header Not Recalculated After Item Edits
    res1 = classify_rule_2187_diagnostic(
        header_stcess="100.00",
        sum_item_stcess="150.00",
        items=[{"StateCesAmt": 100.00}, {"StateCesAmt": 50.00}]
    )
    assert not res1["is_valid"]
    assert res1["error_code"] == 2187
    assert res1["scenario"] == "HEADER_NOT_RECALCULATED_AFTER_ITEM_EDITS"
    assert "Dynamically aggregate item-level State Cess amounts" in res1["reason"]
    assert res1["correct_payload"]["ValDtls"]["StCesVal"] == Decimal("150.00")

    # Scenario 2: State Cess vs Central Cess Field Confusion
    res2 = classify_rule_2187_diagnostic(
        header_stcess="0.00",
        header_cess="200.00",
        items=[{"StateCesAmt": 200.00, "CesAmt": 0.00}],
        sum_item_stcess="200.00",
        sum_item_cess="0.00"
    )
    assert not res2["is_valid"]
    assert res2["scenario"] == "STATE_CESS_VS_CENTRAL_CESS_FIELD_CONFUSION"
    assert "Keep Central Compensation Cess (CesVal) separate from State Cess (StCesVal)" in res2["reason"]
    assert res2["correct_payload"]["ValDtls"]["StCesVal"] == Decimal("200.00")
    assert res2["correct_payload"]["ValDtls"]["CesVal"] == Decimal("0.00")

    # Scenario 3: Specific (Non-Ad-Valorem) State Cess Omitted
    res3 = classify_rule_2187_diagnostic(
        header_stcess="100.00",
        sum_item_stcesad="100.00",
        sum_item_stcesnonad="25.00",
        items=[{"StateCesAmt": 100.00, "StateCesNonAdvlAmt": 25.00}]
    )
    assert not res3["is_valid"]
    assert res3["scenario"] == "SPECIFIC_NON_AD_VALOREM_STATE_CESS_OMITTED"
    assert "ValDtls.StCesVal must include both rate-based and quantity-based State Cess" in res3["reason"]
    assert res3["correct_payload"]["ValDtls"]["StCesVal"] == Decimal("125.00")

    # Scenario 4: Decimal / Paise Truncation
    res4 = classify_rule_2187_diagnostic(
        header_stcess="100.00",
        sum_item_stcess="99.99",
        items=[{"StateCesAmt": 33.33}, {"StateCesAmt": 33.33}, {"StateCesAmt": 33.33}]
    )
    assert not res4["is_valid"]
    assert res4["scenario"] == "DECIMAL_PAISE_TRUNCATION"
    assert "Header total must match the item-level sum to 2 decimal places" in res4["reason"]
    assert res4["correct_payload"]["ValDtls"]["StCesVal"] == Decimal("99.99")

    # Valid Case
    res_ok = classify_rule_2187_diagnostic(
        header_stcess="150.00",
        sum_item_stcess="150.00",
        items=[{"StateCesAmt": 100.00}, {"StateCesAmt": 50.00}]
    )
    assert res_ok["is_valid"]
    assert res_ok["scenario"] == "VALID"


def test_classify_rule_2189_scenarios_standalone():
    """Verify classify_rule_2189_diagnostic classifies all 4 scenarios with exact statutory text."""
    # Scenario 1: Item-Level Discount Subtracted Again at Header
    res1 = classify_rule_2189_diagnostic(
        totinvval="9500.00",
        sum_totitem="10000.00",
        othchrg="0.00",
        discount="500.00",
        rndoffamt="0.00",
        items=[{"AssAmt": 10000.00, "Discount": 500.00, "TotItemVal": 10000.00}]
    )
    assert not res1["is_valid"]
    assert res1["error_code"] == 2189
    assert res1["scenario"] == "ITEM_LEVEL_DISCOUNT_SUBTRACTED_AGAIN_AT_HEADER"
    assert "Subtracting discounts at both item and header levels causes TotInvVal to fall short" in res1["reason"]
    assert res1["correct_payload"]["ValDtls"]["Discount"] == Decimal("0.00")
    assert res1["correct_payload"]["ValDtls"]["TotInvVal"] == Decimal("10000.00")

    # Scenario 2: Other Charges (OthChrg) Left Out of Total
    res2 = classify_rule_2189_diagnostic(
        totinvval="10000.00",
        sum_totitem="10000.00",
        othchrg="500.00",
        discount="0.00",
        rndoffamt="0.00",
        items=[{"TotItemVal": 10000.00}]
    )
    assert not res2["is_valid"]
    assert res2["scenario"] == "OTHER_CHARGES_LEFT_OUT_OF_TOTAL"
    assert "Freight, packing, or handling charges added to ValDtls.OthChrg must be added to TotInvVal" in res2["reason"]
    assert res2["correct_payload"]["ValDtls"]["TotInvVal"] == Decimal("10500.00")

    # Scenario 3: Rounding Off (RndOffAmt) Arithmetic Inversion
    res3 = classify_rule_2189_diagnostic(
        totinvval="11800.00",
        sum_totitem="11800.40",
        othchrg="0.00",
        discount="0.00",
        rndoffamt="0.40",
        items=[{"TotItemVal": 11800.40}]
    )
    assert not res3["is_valid"]
    assert res3["scenario"] == "ROUNDING_OFF_ARITHMETIC_INVERSION"
    assert "If rounding down, RndOffAmt must be negative (-0.40)" in res3["reason"]
    assert res3["correct_payload"]["ValDtls"]["RndOffAmt"] == Decimal("-0.40")
    assert res3["correct_payload"]["ValDtls"]["TotInvVal"] == Decimal("11800.00")

    # Scenario 4: Total Item Value (TotItemVal) Formula Discrepancy
    res4 = classify_rule_2189_diagnostic(
        totinvval="10000.00",
        sum_totitem="10000.00",
        othchrg="0.00",
        discount="0.00",
        rndoffamt="0.00",
        items=[{"AssAmt": 10000.00, "IgstAmt": 1800.00, "TotItemVal": 10000.00}]
    )
    assert not res4["is_valid"]
    assert res4["scenario"] == "TOTAL_ITEM_VALUE_FORMULA_DISCREPANCY"
    assert "TotItemVal for each line must equal AssAmt + Taxes + Cess + Item-level Other Charges" in res4["reason"]
    assert res4["correct_payload"]["ValDtls"]["TotInvVal"] == Decimal("11800.00")

    # Valid Case (within +/- 1.00 tolerance)
    res_ok = classify_rule_2189_diagnostic(
        totinvval="11800.00",
        sum_totitem="11800.00",
        othchrg="0.00",
        discount="0.00",
        rndoffamt="0.00",
        items=[{"AssAmt": 10000.00, "IgstAmt": 1800.00, "TotItemVal": 11800.00}]
    )
    assert res_ok["is_valid"]
    assert res_ok["scenario"] == "VALID"


# ==============================================================================
# 2. PRE-API VALIDATOR TESTS (GSTValidator & RulesEngine)
# ==============================================================================

def test_pre_api_validator_rule_2187_scenarios(
    failing_2187_scenario_1_recalc,
    failing_2187_scenario_2_central_vs_state_confusion,
    failing_2187_scenario_3_non_ad_valorem_omitted,
    failing_2187_scenario_4_paise_truncation,
):
    """Ensure both GSTValidator and RulesEngine reject Rule 2187 scenarios."""
    scenarios = [
        failing_2187_scenario_1_recalc,
        failing_2187_scenario_2_central_vs_state_confusion,
        failing_2187_scenario_3_non_ad_valorem_omitted,
        failing_2187_scenario_4_paise_truncation,
    ]
    for sc in scenarios:
        val_errors = GSTValidator.validate_invoice(sc)
        assert any(e.get("error_code") == 2187 for e in val_errors), f"GSTValidator failed to flag 2187 on {sc.get('docno')}"

        eng_errors = RulesEngine.validate_invoice(sc)
        assert any(e.get("error_code") == 2187 for e in eng_errors), f"RulesEngine failed to flag 2187 on {sc.get('docno')}"


def test_pre_api_validator_rule_2189_scenarios(
    failing_2189_scenario_1_double_discount,
    failing_2189_scenario_2_other_charges_omitted,
    failing_2189_scenario_3_rounding_inversion,
    failing_2189_scenario_4_totitemval_discrepancy,
):
    """Ensure both GSTValidator and RulesEngine reject Rule 2189 scenarios."""
    scenarios = [
        failing_2189_scenario_1_double_discount,
        failing_2189_scenario_2_other_charges_omitted,
        failing_2189_scenario_3_rounding_inversion,
        failing_2189_scenario_4_totitemval_discrepancy,
    ]

    for sc in scenarios:
        val_errors = GSTValidator.validate_invoice(sc)
        assert any(e.get("error_code") == 2189 for e in val_errors), f"GSTValidator failed to flag 2189 on {sc.get('docno')}"

        eng_errors = RulesEngine.validate_invoice(sc)
        assert any(e.get("error_code") == 2189 for e in eng_errors), f"RulesEngine failed to flag 2189 on {sc.get('docno')}"


# ==============================================================================
# 3. STORAGE & PARQUET TESTS
# ==============================================================================

def test_parquet_storage_roundtrip_2187_and_2189():
    """Verify Lakehouse Parquet storage serializes and reads 2187/2189 data cleanly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pq_path = os.path.join(tmpdir, "invoices_test.parquet")
        sample_rows = [
            {
                "docno": "INV-TEST-2187",
                "docdt": "2026-10-26",
                "document_type": "INV",
                "trancatg": "B2B",
                "supplier_gstin": "32ABCDE1234F1Z5",
                "buyer_gstin": "32XYZAB9876C1Z1",
                "totinvval": 17850.0,
                "stcesval": 150.0,
                "cesval": 0.0,
                "assval": 15000.0,
                "cgstval": 1350.0,
                "sgstval": 1350.0,
                "igstval": 0.0,
            },
            {
                "docno": "INV-TEST-2189",
                "docdt": "2026-10-26",
                "document_type": "INV",
                "trancatg": "B2B",
                "supplier_gstin": "27ABCDE1234F1Z5",
                "buyer_gstin": "27XYZAB9876C1Z1",
                "totinvval": 10500.0,
                "stcesval": 0.0,
                "cesval": 0.0,
                "assval": 10000.0,
                "cgstval": 0.0,
                "sgstval": 0.0,
                "igstval": 0.0,
            }
        ]
        df_orig = pd.DataFrame(sample_rows)
        write_parquet(df_orig, pq_path)
        assert os.path.exists(pq_path)

        df_read = read_parquet(pq_path)
        assert len(df_read) == 2
        assert df_read.iloc[0]["docno"] == "INV-TEST-2187"
        assert float(df_read.iloc[0]["stcesval"]) == 150.0
        assert df_read.iloc[1]["docno"] == "INV-TEST-2189"
        assert float(df_read.iloc[1]["totinvval"]) == 10500.0
