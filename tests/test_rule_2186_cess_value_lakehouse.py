"""
Test Suite: NIC Error Code 2186 Statutory Compliance & Data Lakehouse Cess Value Module.
File: tests/test_rule_2186_cess_value_lakehouse.py

Validates Indian GST e-Invoicing (NIC / IRP) Error Code 2186:
"Cess value of all items is not equal to total Cess Value"
The e-Invoice schema strictly validates:
    ValDtls.CesVal = sum(ItemList[i].CesAmt + ItemList[i].CesNonAdvlAmt)
If the line-item Cess total deviates from the header value by even a single paisa,
the request is strictly rejected.

Tests all 5 Statutory Scenarios directly within schemas, rules engine, and Data Lakehouse (src/ingestion/storage.py):
1. Header Not Recalculated After Item Edits:
   Item 1: CesAmt = 1200.00, Item 2: CesAmt = 400.00
   Sent: ValDtls: { "CesVal": 1200.00 }
   Correct: ValDtls: { "CesVal": 1600.00 }
   Fix / Reason: "Ensure ValDtls.CesVal dynamically sums both ad-valorem Cess (CesAmt) and non-ad-valorem Cess (CesNonAdvlAmt) across all line items ($1200.00 + 400.00 = 1600.00$)."

2. Ad-Valorem vs Non-Ad-Valorem Cess Omission:
   Item 1 has ad-valorem Cess CesAmt = 1000.00 and specific Cess CesNonAdvlAmt = 200.00. Header has:
   Sent: ValDtls: { "CesVal": 1000.00 }
   Correct: ValDtls: { "CesVal": 1200.00 }
   Fix / Reason: "ValDtls.CesVal represents the aggregate Cess total. It must include both percentage-based Cess (CesAmt) and fixed/quantity-based Cess (CesNonAdvlAmt)."

3. State Cess Mixed with Central Cess:
   Item has CesAmt = 500.00 and StateCesAmt = 100.00. Header has:
   Sent: ValDtls: { "CesVal": 600.00, "StCesVal": 0.00 }
   Correct: ValDtls: { "CesVal": 500.00, "StCesVal": 100.00 }
   Fix / Reason: "Do not merge State Cess (Kerala Flood Cess / State Cess) into GST Compensation Cess. Keep them in their distinct fields (CesVal vs StCesVal)."

4. Decimal / Paise Rounding Mismatch:
   Item 1: CesAmt = 33.33, Item 2: CesAmt = 33.33, Item 3: CesAmt = 33.33
   Sent: ValDtls: { "CesVal": 100.00 }
   Correct: ValDtls: { "CesVal": 99.99 } (or adjust line 3 CesAmt = 33.34)
   Fix / Reason: "Sum of item CesAmt is $99.99$, but the header was rounded up to $100.00$. Line-item sum and CesVal must match to 2 decimal places."

5. Cess Populated at Line Item but 0/Null at Header:
   Line items carry positive Cess (CesAmt > 0), but header summary passes:
   Sent: ValDtls: { "CesVal": 0.00 } or null
   Correct: ValDtls: { "CesVal": <Sum Cess Item of> }
   Fix / Reason: "If any line item carries Cess, ValDtls.CesVal must reflect the non-zero total. If no goods attract Cess, leave both item and header fields as 0.00."

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
    classify_rule_2186_diagnostic,
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
def failing_scenario_1_stale_cess_header():
    """Scenario 1: Header Not Recalculated After Item Edits (1200.00 + 400.00 -> 1600.00, Header has 1200.00)."""
    return {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-26-2186-SC1",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "B2B",
        "reversecharge": "N",
        "igstonintra": "N",
        "supplier": {
            "gstin": "27ABCDE1234F1Z5",
            "lglnm": "Maharashtra Luxury Automobiles Ltd",
            "state": "27",
            "pin": "400001",
            "loc": "Mumbai"
        },
        "buyer": {
            "gstin": "27XYZAB9876C1Z1",
            "lglnm": "Mumbai Corporate Fleet Services",
            "state": "27",
            "pos": "27",
            "pin": "400051",
            "loc": "Mumbai"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "Luxury SUV Component Tier 1",
                "prddesc": "Automotive Cess Attracting Part A",
                "hsn": "8703",
                "qty": 1.0,
                "unit": "NOS",
                "unitprice": 10000.0,
                "totamt": 10000.0,
                "discount": 0.0,
                "assval": 10000.0,
                "gstrate": 28.0,
                "cgstval": 1400.0,
                "sgstval": 1400.0,
                "igstval": 0.0,
                "cesval": 1200.0,  # Ad-valorem Cess Item 1
                "cesnonadval": 0.0,
                "totitemval": 14000.0
            },
            {
                "item_slno": "2",
                "slno": "2",
                "prdnm": "Luxury SUV Component Tier 2",
                "prddesc": "Automotive Cess Attracting Part B",
                "hsn": "8703",
                "qty": 1.0,
                "unit": "NOS",
                "unitprice": 5000.0,
                "totamt": 5000.0,
                "discount": 0.0,
                "assval": 5000.0,
                "gstrate": 28.0,
                "cgstval": 700.0,
                "sgstval": 700.0,
                "igstval": 0.0,
                "cesval": 400.0,  # Ad-valorem Cess Item 2
                "cesnonadval": 0.0,
                "totitemval": 6800.0
            }
        ],
        "valdtls": {
            "AssVal": 15000.0,
            "CgstVal": 2100.0,
            "SgstVal": 2100.0,
            "IgstVal": 0.0,
            "CesVal": 1200.0,  # Failing: Stale Header has 1200.00 instead of 1600.00
            "Discount": 0.0,
            "RndOffAmt": 0.0,
            "TotInvVal": 20400.0
        }
    }


@pytest.fixture
def failing_scenario_2_non_ad_valorem_omission():
    """Scenario 2: Ad-Valorem vs Non-Ad-Valorem Cess Omission (Ad-valorem = 1000.00, Specific = 200.00, Header = 1000.00)."""
    return {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-26-2186-SC2",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "B2B",
        "reversecharge": "N",
        "igstonintra": "N",
        "supplier": {
            "gstin": "27ABCDE1234F1Z5",
            "lglnm": "Maharashtra Tobacco Products Corp",
            "state": "27",
            "pin": "400001",
            "loc": "Mumbai"
        },
        "buyer": {
            "gstin": "27XYZAB9876C1Z1",
            "lglnm": "Pune Wholesale Distributors",
            "state": "27",
            "pos": "27",
            "pin": "411001",
            "loc": "Pune"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "Cigarette Rolls Special Filter",
                "prddesc": "Tobacco Product Subject to Both Cesses",
                "hsn": "2402",
                "qty": 10.0,
                "unit": "THD",
                "unitprice": 1000.0,
                "totamt": 10000.0,
                "discount": 0.0,
                "assval": 10000.0,
                "gstrate": 28.0,
                "cgstval": 1400.0,
                "sgstval": 1400.0,
                "igstval": 0.0,
                "cesval": 1000.0,      # Ad-valorem Cess
                "cesnonadval": 200.0,  # Non-Ad-Valorem / Specific Cess
                "totitemval": 14000.0
            }
        ],
        "valdtls": {
            "AssVal": 10000.0,
            "CgstVal": 1400.0,
            "SgstVal": 1400.0,
            "IgstVal": 0.0,
            "CesVal": 1000.0,  # Failing: Omitted specific Cess (1000.00 instead of 1200.00)
            "Discount": 0.0,
            "RndOffAmt": 0.0,
            "TotInvVal": 13800.0
        }
    }


@pytest.fixture
def failing_scenario_3_state_cess_mixed():
    """Scenario 3: State Cess Mixed with Central Cess (CesAmt = 500.00, StateCesAmt = 100.00, Header CesVal = 600.00, StCesVal = 0.00)."""
    return {
        "self_gstin": "32ABCDE1234F1Z5",
        "docno": "INV-26-2186-SC3",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "B2B",
        "reversecharge": "N",
        "igstonintra": "N",
        "supplier": {
            "gstin": "32ABCDE1234F1Z5",
            "lglnm": "Kerala Specialty Goods Ltd",
            "state": "32",
            "pin": "682001",
            "loc": "Kochi"
        },
        "buyer": {
            "gstin": "32XYZAB9876C1Z1",
            "lglnm": "Kochi Retail Enterprises",
            "state": "32",
            "pos": "32",
            "pin": "682016",
            "loc": "Ernakulam"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "High-End Aerated Beverage",
                "prddesc": "Attracts Central Cess & Kerala Flood Cess",
                "hsn": "2202",
                "qty": 100.0,
                "unit": "BTL",
                "unitprice": 100.0,
                "totamt": 10000.0,
                "discount": 0.0,
                "assval": 10000.0,
                "gstrate": 28.0,
                "cgstval": 1400.0,
                "sgstval": 1400.0,
                "igstval": 0.0,
                "cesval": 500.0,        # Central Compensation Cess
                "statecesval": 100.0,   # State Cess (Kerala Flood Cess)
                "totitemval": 13400.0
            }
        ],
        "valdtls": {
            "AssVal": 10000.0,
            "CgstVal": 1400.0,
            "SgstVal": 1400.0,
            "IgstVal": 0.0,
            "CesVal": 600.0,   # Failing: Mixed State Cess into CesVal (600.00 instead of 500.00)
            "StCesVal": 0.0,   # Failing: Left StCesVal as 0.00
            "Discount": 0.0,
            "RndOffAmt": 0.0,
            "TotInvVal": 13400.0
        }
    }


@pytest.fixture
def failing_scenario_4_paise_rounding_mismatch():
    """Scenario 4: Decimal / Paise Rounding Mismatch (33.33 * 3 = 99.99, Header = 100.00)."""
    return {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-26-2186-SC4",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "B2B",
        "reversecharge": "N",
        "igstonintra": "N",
        "supplier": {
            "gstin": "27ABCDE1234F1Z5",
            "lglnm": "Maharashtra Precision Tobacco Parts Ltd",
            "state": "27",
            "pin": "400001",
            "loc": "Mumbai"
        },
        "buyer": {
            "gstin": "27XYZAB9876C1Z1",
            "lglnm": "Nagpur Allied Trading Corp",
            "state": "27",
            "pos": "27",
            "pin": "440001",
            "loc": "Nagpur"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "Cess Item Unit 1",
                "prddesc": "Grade A Sample",
                "hsn": "2402",
                "qty": 1.0,
                "unit": "NOS",
                "unitprice": 333.33,
                "totamt": 333.33,
                "discount": 0.0,
                "assval": 333.33,
                "gstrate": 28.0,
                "cgstval": 46.67,
                "sgstval": 46.67,
                "igstval": 0.0,
                "cesval": 33.33,  # Line 1 Cess
                "totitemval": 460.00
            },
            {
                "item_slno": "2",
                "slno": "2",
                "prdnm": "Cess Item Unit 2",
                "prddesc": "Grade B Sample",
                "hsn": "2402",
                "qty": 1.0,
                "unit": "NOS",
                "unitprice": 333.33,
                "totamt": 333.33,
                "discount": 0.0,
                "assval": 333.33,
                "gstrate": 28.0,
                "cgstval": 46.67,
                "sgstval": 46.67,
                "igstval": 0.0,
                "cesval": 33.33,  # Line 2 Cess
                "totitemval": 460.00
            },
            {
                "item_slno": "3",
                "slno": "3",
                "prdnm": "Cess Item Unit 3",
                "prddesc": "Grade C Sample",
                "hsn": "2402",
                "qty": 1.0,
                "unit": "NOS",
                "unitprice": 333.33,
                "totamt": 333.33,
                "discount": 0.0,
                "assval": 333.33,
                "gstrate": 28.0,
                "cgstval": 46.67,
                "sgstval": 46.67,
                "igstval": 0.0,
                "cesval": 33.33,  # Line 3 Cess (Sum = 99.99)
                "totitemval": 460.00
            }
        ],
        "valdtls": {
            "AssVal": 999.99,
            "CgstVal": 140.01,
            "SgstVal": 140.01,
            "IgstVal": 0.0,
            "CesVal": 100.00,  # Failing: Rounded up to 100.00 instead of 99.99
            "Discount": 0.0,
            "RndOffAmt": 0.0,
            "TotInvVal": 1380.01
        }
    }


@pytest.fixture
def failing_scenario_5_item_populated_header_zero():
    """Scenario 5: Cess Populated at Line Item but 0/Null at Header (Item has 1200.00 Cess, Header has 0.00)."""
    return {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-26-2186-SC5",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "B2B",
        "reversecharge": "N",
        "igstonintra": "N",
        "supplier": {
            "gstin": "27ABCDE1234F1Z5",
            "lglnm": "Maharashtra High-End Machinery Ltd",
            "state": "27",
            "pin": "400001",
            "loc": "Mumbai"
        },
        "buyer": {
            "gstin": "27XYZAB9876C1Z1",
            "lglnm": "Mumbai Industrial Operations Corp",
            "state": "27",
            "pos": "27",
            "pin": "400051",
            "loc": "Mumbai"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "Luxury High-Displacement Engine",
                "prddesc": "Automotive Engine Subject to GST Cess",
                "hsn": "8703",
                "qty": 1.0,
                "unit": "NOS",
                "unitprice": 10000.0,
                "totamt": 10000.0,
                "discount": 0.0,
                "assval": 10000.0,
                "gstrate": 28.0,
                "cgstval": 1400.0,
                "sgstval": 1400.0,
                "igstval": 0.0,
                "cesval": 1200.0,  # Item has positive Cess
                "totitemval": 14000.0
            }
        ],
        "valdtls": {
            "AssVal": 10000.0,
            "CgstVal": 1400.0,
            "SgstVal": 1400.0,
            "IgstVal": 0.0,
            "CesVal": 0.0,  # Failing: Header Cess left as 0.00 while items carry Cess
            "Discount": 0.0,
            "RndOffAmt": 0.0,
            "TotInvVal": 12800.0
        }
    }


@pytest.fixture
def valid_cess_invoice_payload():
    """Valid payload: ValDtls.CesVal strictly equals sum(ItemList[i].CesAmt + ItemList[i].CesNonAdvlAmt)."""
    return {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-26-2186-OK",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "B2B",
        "reversecharge": "N",
        "igstonintra": "N",
        "supplier": {
            "gstin": "27ABCDE1234F1Z5",
            "lglnm": "Maharashtra High-End Machinery Ltd",
            "state": "27",
            "pin": "400001",
            "loc": "Mumbai"
        },
        "buyer": {
            "gstin": "27XYZAB9876C1Z1",
            "lglnm": "Mumbai Industrial Operations Corp",
            "state": "27",
            "pos": "27",
            "pin": "400051",
            "loc": "Mumbai"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "Luxury SUV Component Part 1",
                "prddesc": "Automotive Cess Attracting Part 1",
                "hsn": "8703",
                "qty": 1.0,
                "unit": "NOS",
                "unitprice": 10000.0,
                "totamt": 10000.0,
                "discount": 0.0,
                "assval": 10000.0,
                "gstrate": 28.0,
                "cgstval": 1400.0,
                "sgstval": 1400.0,
                "igstval": 0.0,
                "cesval": 1200.0,
                "cesnonadval": 200.0,
                "totitemval": 14200.0
            },
            {
                "item_slno": "2",
                "slno": "2",
                "prdnm": "Luxury SUV Component Part 2",
                "prddesc": "Automotive Cess Attracting Part 2",
                "hsn": "8703",
                "qty": 1.0,
                "unit": "NOS",
                "unitprice": 5000.0,
                "totamt": 5000.0,
                "discount": 0.0,
                "assval": 5000.0,
                "gstrate": 28.0,
                "cgstval": 700.0,
                "sgstval": 700.0,
                "igstval": 0.0,
                "cesval": 400.0,
                "cesnonadval": 0.0,
                "totitemval": 6800.0
            }
        ],
        "valdtls": {
            "AssVal": 15000.0,
            "CgstVal": 2100.0,
            "SgstVal": 2100.0,
            "IgstVal": 0.0,
            "CesVal": 1800.0,  # Exactly 1200 + 200 + 400 = 1800.00
            "Discount": 0.0,
            "RndOffAmt": 0.0,
            "TotInvVal": 21000.0
        }
    }


# ==============================================================================
# 1. DIAGNOSTIC CLASSIFICATION TESTS
# ==============================================================================

def test_classify_rule_2186_scenarios_standalone():
    """Verify classify_rule_2186_diagnostic classifies all 5 scenarios with precision."""
    # Scenario 1: Header Not Recalculated After Item Edits
    res1 = classify_rule_2186_diagnostic(
        header_cess="1200.00",
        sum_item_cess="1600.00",
        items=[{"CesAmt": 1200.00}, {"CesAmt": 400.00}]
    )
    assert not res1["is_valid"]
    assert res1["error_code"] == 2186
    assert res1["scenario"] == "HEADER_NOT_RECALCULATED_AFTER_ITEM_EDITS"
    assert "Ensure ValDtls.CesVal dynamically sums both ad-valorem Cess" in res1["reason"]
    assert res1["correct_payload"]["ValDtls"]["CesVal"] == Decimal("1600.00")

    # Scenario 2: Ad-Valorem vs Non-Ad-Valorem Cess Omission
    res2 = classify_rule_2186_diagnostic(
        header_cess="1000.00",
        items=[{"CesAmt": 1000.00, "CesNonAdvlAmt": 200.00}],
        sum_item_cesad="1000.00",
        sum_item_cesnonad="200.00",
    )
    assert not res2["is_valid"]
    assert res2["scenario"] == "AD_VALOREM_VS_NON_AD_VALOREM_CESS_OMISSION"
    assert "aggregate Cess total" in res2["reason"]
    assert res2["correct_payload"]["ValDtls"]["CesVal"] == Decimal("1200.00")

    # Scenario 3: State Cess Mixed with Central Cess
    res3 = classify_rule_2186_diagnostic(
        header_cess="600.00",
        header_stcess="0.00",
        items=[{"CesAmt": 500.00, "StateCesAmt": 100.00}],
        sum_item_cess="500.00",
        sum_item_stcess="100.00",
    )
    assert not res3["is_valid"]
    assert res3["scenario"] == "STATE_CESS_MIXED_WITH_CENTRAL_CESS"
    assert "Do not merge State Cess" in res3["reason"]
    assert res3["correct_payload"]["ValDtls"]["CesVal"] == Decimal("500.00")
    assert res3["correct_payload"]["ValDtls"]["StCesVal"] == Decimal("100.00")

    # Scenario 4: Decimal / Paise Rounding Mismatch
    res4 = classify_rule_2186_diagnostic(
        header_cess="100.00",
        sum_item_cess="99.99",
        items=[{"CesAmt": 33.33}, {"CesAmt": 33.33}, {"CesAmt": 33.33}]
    )
    assert not res4["is_valid"]
    assert res4["scenario"] == "DECIMAL_PAISE_ROUNDING_MISMATCH"
    assert "Line-item sum and CesVal must match to 2 decimal places" in res4["reason"]
    assert res4["correct_payload"]["ValDtls"]["CesVal"] == Decimal("99.99")

    # Scenario 5: Cess Populated at Line Item but 0/Null at Header
    res5 = classify_rule_2186_diagnostic(
        header_cess="0.00",
        sum_item_cess="1200.00",
        items=[{"CesAmt": 1200.00}]
    )
    assert not res5["is_valid"]
    assert res5["scenario"] == "CESS_POPULATED_LINE_ITEM_ZERO_HEADER"
    assert "If any line item carries Cess, ValDtls.CesVal must reflect the non-zero total" in res5["reason"]
    assert res5["correct_payload"]["ValDtls"]["CesVal"] == Decimal("1200.00")

    # Valid Case
    res_ok = classify_rule_2186_diagnostic(
        header_cess="1600.00",
        sum_item_cess="1600.00",
        items=[{"CesAmt": 1200.00}, {"CesAmt": 400.00}]
    )
    assert res_ok["is_valid"]
    assert res_ok["scenario"] == "VALID"


# ==============================================================================
# 2. AUTO-CORRECT & BUILD TESTS
# ==============================================================================

def test_auto_correct_and_build_rule_2186_scenarios(
    failing_scenario_1_stale_cess_header,
    failing_scenario_2_non_ad_valorem_omission,
    failing_scenario_3_state_cess_mixed,
    failing_scenario_4_paise_rounding_mismatch,
    failing_scenario_5_item_populated_header_zero
):
    """Ensure auto_correct_and_build detects Rule 2186, logs audit trail, and fixes ValDtls.CesVal."""
    # Test Scenario 1
    scen1_copy = dict(failing_scenario_1_stale_cess_header)
    fixed1, audit1 = InvoicePayload.auto_correct_and_build(scen1_copy)
    assert float(fixed1.valdtls.cesval) == 1600.0
    assert any("2186" in str(a) for a in audit1)

    # Test Scenario 2
    scen2_copy = dict(failing_scenario_2_non_ad_valorem_omission)
    fixed2, audit2 = InvoicePayload.auto_correct_and_build(scen2_copy)
    assert float(fixed2.valdtls.cesval) == 1200.0
    assert any("2186" in str(a) for a in audit2)

    # Test Scenario 3
    scen3_copy = dict(failing_scenario_3_state_cess_mixed)
    fixed3, audit3 = InvoicePayload.auto_correct_and_build(scen3_copy)
    assert float(fixed3.valdtls.cesval) == 500.0
    assert float(fixed3.valdtls.stcesval) == 100.0
    assert any("2186" in str(a) for a in audit3)

    # Test Scenario 4
    scen4_copy = dict(failing_scenario_4_paise_rounding_mismatch)
    fixed4, audit4 = InvoicePayload.auto_correct_and_build(scen4_copy)
    assert float(fixed4.valdtls.cesval) == 99.99
    assert any("2186" in str(a) for a in audit4)

    # Test Scenario 5
    scen5_copy = dict(failing_scenario_5_item_populated_header_zero)
    fixed5, audit5 = InvoicePayload.auto_correct_and_build(scen5_copy)
    assert float(fixed5.valdtls.cesval) == 1200.0
    assert any("2186" in str(a) for a in audit5)


# ==============================================================================
# 3. PRE-API VALIDATOR TESTS (GSTValidator & RulesEngine)
# ==============================================================================

def test_pre_api_validator_rejects_rule_2186_scenarios(
    failing_scenario_1_stale_cess_header,
    failing_scenario_2_non_ad_valorem_omission,
    failing_scenario_3_state_cess_mixed,
    failing_scenario_4_paise_rounding_mismatch,
    failing_scenario_5_item_populated_header_zero,
    valid_cess_invoice_payload
):
    """Ensure both GSTValidator and RulesEngine reject all 5 failing scenarios with Error Code 2186."""
    scenarios = [
        failing_scenario_1_stale_cess_header,
        failing_scenario_2_non_ad_valorem_omission,
        failing_scenario_3_state_cess_mixed,
        failing_scenario_4_paise_rounding_mismatch,
        failing_scenario_5_item_populated_header_zero,
    ]

    for sc in scenarios:
        val_errors = GSTValidator.validate_invoice(sc)
        assert any(e.get("error_code") == 2186 for e in val_errors), f"GSTValidator failed to flag 2186 for {sc['docno']}"

        re_errors = RulesEngine.validate_invoice(sc)
        assert any(e.get("error_code") == 2186 for e in re_errors), f"RulesEngine failed to flag 2186 for {sc['docno']}"

    # Valid payload must pass cleanly
    val_ok = GSTValidator.validate_invoice(valid_cess_invoice_payload)
    assert not any(e.get("error_code") == 2186 for e in val_ok)

    re_ok = RulesEngine.validate_invoice(valid_cess_invoice_payload)
    assert not any(e.get("error_code") == 2186 for e in re_ok)


# ==============================================================================
# 4. PYDANTIC MODEL STATUTORY VALIDATION TESTS
# ==============================================================================

def test_pydantic_model_rejects_rule_2186_scenarios(
    failing_scenario_1_stale_cess_header,
    failing_scenario_2_non_ad_valorem_omission,
    failing_scenario_3_state_cess_mixed,
    failing_scenario_4_paise_rounding_mismatch,
    failing_scenario_5_item_populated_header_zero,
    valid_cess_invoice_payload
):
    """Ensure InvoicePayload pydantic model strictly rejects Rule 2186 violations and accepts valid."""
    scenarios = [
        failing_scenario_1_stale_cess_header,
        failing_scenario_2_non_ad_valorem_omission,
        failing_scenario_3_state_cess_mixed,
        failing_scenario_4_paise_rounding_mismatch,
        failing_scenario_5_item_populated_header_zero,
    ]

    for sc in scenarios:
        with pytest.raises((NICValidationError, Exception)) as exc_info:
            InvoicePayload.model_validate(sc)
        assert "2186" in str(exc_info.value)

    # Valid payload should pass validation
    model = InvoicePayload.model_validate(valid_cess_invoice_payload)
    assert model.docno == "INV-26-2186-OK"
    assert float(model.valdtls.cesval) == 1800.0


# ==============================================================================
# 5. DATA LAKEHOUSE FLATTENING & SENTINEL TELEMETRY TESTS
# ==============================================================================

def test_lakehouse_flattening_sentinel_telemetry_dict(failing_scenario_1_stale_cess_header):
    """Ensure dict flattening sets FLAGGED_AND_RECTIFIED, HIGH risk, and rectifies inv_cess_amount."""
    rows = flatten_invoice_payload(failing_scenario_1_stale_cess_header)
    assert len(rows) == 2

    for r in rows:
        assert r["sentinel_status_badge"] == "FLAGGED_AND_RECTIFIED"
        assert r["sentinel_risk_level"] == "HIGH"
        assert r["sentinel_risk_prob"] >= 0.95
        assert "Rule 2186 Violation" in r["sentinel_audit_reasons"]
        assert r["inv_cess_amount"] == 1600.0  # Rectified from 1200.00 to 1600.00


def test_lakehouse_flattening_sentinel_telemetry_model(valid_cess_invoice_payload):
    """Ensure InvoicePayload model flattening works seamlessly and preserves verified Cess totals."""
    model = InvoicePayload.model_validate(valid_cess_invoice_payload)
    rows = flatten_invoice_payload(model)
    assert len(rows) == 2

    for r in rows:
        assert r["inv_cess_amount"] == 1800.0
        assert "Rule 2186 Violation" not in r.get("sentinel_audit_reasons", "")
        assert r["sentinel_status_badge"] in ("AUTO_APPROVED", "VERIFIED", "FLAGGED_AND_RECTIFIED")


# ==============================================================================
# 6. PARQUET STORAGE ROUNDTRIP & SCHEMA CONFORMANCE TESTS
# ==============================================================================

def test_parquet_lakehouse_roundtrip_conformance(valid_cess_invoice_payload, failing_scenario_1_stale_cess_header):
    """Ensure write_parquet, read_parquet, and append_to_parquet conform strictly to FLATTENED_INVOICE_SCHEMA."""
    temp_dir = tempfile.mkdtemp()
    parquet_path = os.path.join(temp_dir, "test_invoices_2186.parquet")

    try:
        rows_valid = flatten_invoice_payload(valid_cess_invoice_payload)
        rows_rectified = flatten_invoice_payload(failing_scenario_1_stale_cess_header)
        all_rows = rows_valid + rows_rectified

        # Write Parquet with explicit schema
        success_write = write_parquet(all_rows, parquet_path, schema=FLATTENED_INVOICE_SCHEMA)
        assert success_write is True
        assert os.path.exists(parquet_path)

        # Read back Parquet as DataFrame
        df_read = read_parquet(parquet_path)
        assert isinstance(df_read, pd.DataFrame)
        assert len(df_read) == 4
        assert "inv_cess_amount" in df_read.columns
        assert "sentinel_status_badge" in df_read.columns

        # Verify values in Parquet match schema
        valid_subset = df_read[df_read["invoice_id"] == "INV-26-2186-OK"]
        assert len(valid_subset) == 2
        assert (valid_subset["inv_cess_amount"] == 1800.0).all()

        rectified_subset = df_read[df_read["invoice_id"] == "INV-26-2186-SC1"]
        assert len(rectified_subset) == 2
        assert (rectified_subset["inv_cess_amount"] == 1600.0).all()
        assert (rectified_subset["sentinel_status_badge"] == "FLAGGED_AND_RECTIFIED").all()

        # Append to Parquet with distinct invoice ID
        append_payload = dict(valid_cess_invoice_payload)
        append_payload["docno"] = "INV-26-2186-APPEND"
        append_rows = flatten_invoice_payload(append_payload)
        success_append = append_to_parquet(append_rows, parquet_path, schema=FLATTENED_INVOICE_SCHEMA)
        assert success_append is True

        df_after_append = read_parquet(parquet_path)
        assert len(df_after_append) == 6

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
