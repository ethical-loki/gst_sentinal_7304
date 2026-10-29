"""
Test Suite: NIC Error Codes 2243, 2244, & 2246 Statutory Compliance & Data Lakehouse Reconciliation.
File: tests/test_rules_2243_to_2246_lakehouse.py

Coverage:
1. Error Code 2243: POS Code is Invalid
   - LEADING_ZERO_OMITTED: Pos='7' -> set Pos='07'
   - ALPHABETIC_STATE_ABBREVIATION_PASSED: Pos='KA' -> set Pos='29'
   - INVALID_OR_NON_EXISTENT_CODE: Pos='00' or '99' on standard goods -> valid state master code
   - NUMERIC_TYPE_PASSED_INSTEAD_OF_STRING: Pos=27 -> set Pos='27'
   - VALID: Official 2-digit numeric state code

2. Error Code 2244: Recipient PIN Code is Not Provided for Transaction
   - PIN_CODE_OMITTED_OR_NULL_IN_B2B: Pin=None or omitted -> valid 6-digit PIN integer (e.g., 560001)
   - EXPORT_TRANSACTION_OMITTING_DUMMY_PIN: SupTyp='EXPWP', Pin=None -> set Pin=999999
   - STRING_TYPE_PASSED_INSTEAD_OF_INTEGER: Pin='560001' -> set Pin=560001 (int)
   - NON_EXISTENT_OR_INVALID_PIN_FORMAT: Pin=12345 (5 digits) -> valid 6-digit PIN integer
   - VALID: Official 6-digit postal PIN integer (or 999999 for exports)

3. Error Code 2246: Recipient Cannot Be SEZ for Supply Type
   - SEZ_SUPPLY_TAGGED_AS_STANDARD_B2B: SupTyp='B2B', SEZ GSTIN -> set SupTyp='SEZWP' or 'SEZWOP'
   - DEEMED_EXPORT_USED_FOR_SEZ_UNIT: SupTyp='DEXP', SEZ GSTIN -> set SupTyp='SEZWP' or 'SEZWOP'
   - REGULAR_DTA_BUYER_MARKED_WITH_WRONG_GSTIN: B2B with SEZ sister GSTIN, is_dta_sale=True -> pass domestic DTA GSTIN
   - VALID: Non-SEZ recipient on B2B or SEZ recipient on SEZWP/SEZWOP

4. GSTValidator Pre-API & RulesEngine Interception
5. Pydantic Schema Cross-Model Validation Rejections
6. Auto-Correction Engine Audit Trail Assertions
7. Lakehouse Flattening, Parquet Storage & Schema Verification
"""

import copy
import os
import shutil
import tempfile
from decimal import Decimal
from pathlib import Path
import pytest
import pandas as pd

from src.ingestion.schemas import (
    InvoicePayload,
    classify_rule_2243_diagnostic,
    classify_rule_2244_diagnostic,
    classify_rule_2246_diagnostic,
    KNOWN_SEZ_BUYER_GSTINS,
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
# FIXTURES
# ==============================================================================

@pytest.fixture
def clean_b2b_invoice():
    """Clean domestic intra-state B2B invoice (Maharashtra to Maharashtra)."""
    return {
        "self_gstin": "27AAAAA0000A1Z5",
        "docno": "INV-2026-B2B01",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "B2B",
        "supplier": {
            "gstin": "27AAAAA0000A1Z5",
            "lglnm": "Apex Components Ltd",
            "bnm": "Apex House",
            "state": "27",
            "pin": "400001",
            "loc": "Mumbai"
        },
        "buyer": {
            "gstin": "27BBBBB1111B1Z2",
            "lglnm": "Zenith Retailers Pvt Ltd",
            "bnm": "Zenith Hub",
            "state": "27",
            "pos": "27",
            "pin": "411001",
            "loc": "Pune"
        },
        "itemdtls": [
            {
                "slno": "1",
                "prdnm": "Industrial Valve",
                "hsncd": "84818030",
                "qty": "10.00",
                "uqc": "NOS",
                "unit": "NOS",
                "unitprice": "1000.00",
                "totamt": "10000.00",
                "discount": "0.00",
                "assval": "10000.00",
                "gstrate": 18.0,
                "cgstval": "900.00",
                "sgstval": "900.00",
                "igstval": "0.00",
                "totitemval": "11800.00"
            }
        ],
        "valdtls": {
            "assval": "10000.00",
            "cgstval": "900.00",
            "sgstval": "900.00",
            "igstval": "0.00",
            "cesval": "0.00",
            "stcesval": "0.00",
            "discount": "0.00",
            "othchrg": "0.00",
            "rndoffamt": "0.00",
            "totinvval": "11800.00"
        }
    }


@pytest.fixture
def clean_export_invoice():
    """Clean direct export invoice (EXPWP, Recipient POS 96, Pin 999999, URP)."""
    return {
        "self_gstin": "27AAAAA0000A1Z5",
        "docno": "INV-2026-EXP01",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "EXPWP",
        "supplier": {
            "gstin": "27AAAAA0000A1Z5",
            "lglnm": "Apex Components Ltd",
            "bnm": "Apex House",
            "state": "27",
            "pin": "400001",
            "loc": "Mumbai"
        },
        "buyer": {
            "gstin": "URP",
            "lglnm": "Global Trade Logistics Inc",
            "bnm": "Harbor Blvd",
            "state": "96",
            "pos": "96",
            "pin": "999999",
            "loc": "Dubai"
        },
        "expdt1": {
            "shipbno": "SB-1234567",
            "shipbdt": "26-10-2026",
            "port": "INNSA1",
            "cntcode": "AE",
            "forcur": "AED"
        },
        "itemdtls": [
            {
                "slno": "1",
                "prdnm": "Industrial Valve",
                "hsncd": "84818030",
                "qty": "10.00",
                "uqc": "NOS",
                "unit": "NOS",
                "unitprice": "1000.00",
                "totamt": "10000.00",
                "discount": "0.00",
                "assval": "10000.00",
                "gstrate": 18.0,
                "cgstval": "0.00",
                "sgstval": "0.00",
                "igstval": "1800.00",
                "totitemval": "11800.00"
            }
        ],
        "valdtls": {
            "assval": "10000.00",
            "cgstval": "0.00",
            "sgstval": "0.00",
            "igstval": "1800.00",
            "cesval": "0.00",
            "stcesval": "0.00",
            "discount": "0.00",
            "othchrg": "0.00",
            "rndoffamt": "0.00",
            "totinvval": "11800.00"
        }
    }


# ==============================================================================
# RULE 2243: DIAGNOSTIC CLASSIFIER TESTS
# ==============================================================================

def test_rule_2243_scenario_1_leading_zero_omitted():
    """Scenario 1: Leading zero omitted from 1-digit state code (e.g. '7' -> '07')."""
    diag = classify_rule_2243_diagnostic(pos="7", trancatg="B2B")
    assert not diag["is_valid"]
    assert diag["error_code"] == 2243
    assert diag["scenario"] == "LEADING_ZERO_OMITTED"
    assert diag["rectified_pos"] == "07"
    assert "leading zero" in diag["reason"].lower()


def test_rule_2243_scenario_2_alphabetic_state_abbreviation():
    """Scenario 2: Alphabetic state abbreviation passed instead of 2-digit numeric code."""
    for abbr, exp_code in [("KA", "29"), ("DL", "07"), ("MH", "27"), ("GJ", "24"), ("TN", "33")]:
        diag = classify_rule_2243_diagnostic(pos=abbr, trancatg="B2B")
        assert not diag["is_valid"]
        assert diag["error_code"] == 2243
        assert diag["scenario"] == "ALPHABETIC_STATE_ABBREVIATION_PASSED"
        assert diag["rectified_pos"] == exp_code


def test_rule_2243_scenario_3_invalid_non_existent_code():
    """Scenario 3: Non-existent code like '00' or '99' on standard domestic transactions."""
    diag = classify_rule_2243_diagnostic(pos="00", trancatg="B2B", buyer_state="27")
    assert not diag["is_valid"]
    assert diag["error_code"] == 2243
    assert diag["scenario"] == "INVALID_OR_NON_EXISTENT_CODE"
    assert diag["rectified_pos"] == "27"


def test_rule_2243_scenario_4_numeric_type_passed():
    """Scenario 4: Numeric integer passed instead of string (e.g., Pos=27)."""
    diag = classify_rule_2243_diagnostic(pos=27, trancatg="B2B")
    assert not diag["is_valid"]
    assert diag["error_code"] == 2243
    assert diag["scenario"] == "NUMERIC_TYPE_PASSED_INSTEAD_OF_STRING"
    assert diag["rectified_pos"] == "27"


def test_rule_2243_valid():
    """Valid POS codes in GST State Master."""
    for valid_pos in ["01", "07", "24", "27", "29", "33", "37", "38", "96", "97"]:
        diag = classify_rule_2243_diagnostic(pos=valid_pos, trancatg="B2B")
        assert diag["is_valid"]
        assert diag["error_code"] is None
        assert diag["scenario"] == "VALID"


# ==============================================================================
# RULE 2244: DIAGNOSTIC CLASSIFIER TESTS
# ==============================================================================

def test_rule_2244_scenario_1_pin_omitted_in_b2b():
    """Scenario 1: PIN code omitted or null in domestic B2B transaction."""
    diag = classify_rule_2244_diagnostic(pin=None, trancatg="B2B", buyer_state="29")
    assert not diag["is_valid"]
    assert diag["error_code"] == 2244
    assert diag["scenario"] == "PIN_CODE_OMITTED_OR_NULL_IN_B2B"
    assert diag["rectified_pin"] == 560001
    assert "mandatory" in diag["reason"].lower()


def test_rule_2244_scenario_2_export_omitting_dummy_pin():
    """Scenario 2: Export transaction omitting dummy PIN 999999."""
    diag = classify_rule_2244_diagnostic(pin=None, trancatg="EXPWP")
    assert not diag["is_valid"]
    assert diag["error_code"] == 2244
    assert diag["scenario"] == "EXPORT_TRANSACTION_OMITTING_DUMMY_PIN"
    assert diag["rectified_pin"] == 999999


def test_rule_2244_scenario_3_string_type_passed():
    """Scenario 3: String type passed instead of integer."""
    diag = classify_rule_2244_diagnostic(pin="560001", trancatg="B2B")
    assert not diag["is_valid"]
    assert diag["error_code"] == 2244
    assert diag["scenario"] == "STRING_TYPE_PASSED_INSTEAD_OF_INTEGER"
    assert diag["rectified_pin"] == 560001
    assert isinstance(diag["rectified_pin"], int)


def test_rule_2244_scenario_4_non_existent_invalid_format():
    """Scenario 4: 5-digit or invalid PIN format."""
    diag = classify_rule_2244_diagnostic(pin=12345, trancatg="B2B", buyer_state="07")
    assert not diag["is_valid"]
    assert diag["error_code"] == 2244
    assert diag["scenario"] == "NON_EXISTENT_OR_INVALID_PIN_FORMAT"
    assert diag["rectified_pin"] == 110001


def test_rule_2244_valid():
    """Valid 6-digit integer PIN codes."""
    diag = classify_rule_2244_diagnostic(pin=560001, trancatg="B2B")
    assert diag["is_valid"]
    assert diag["error_code"] is None
    assert diag["scenario"] == "VALID"

    diag_exp = classify_rule_2244_diagnostic(pin=999999, trancatg="EXPWP")
    assert diag_exp["is_valid"]
    assert diag_exp["error_code"] is None


# ==============================================================================
# RULE 2246: DIAGNOSTIC CLASSIFIER TESTS
# ==============================================================================

def test_rule_2246_scenario_1_sez_tagged_as_b2b():
    """Scenario 1: SEZ supply tagged as standard B2B."""
    diag = classify_rule_2246_diagnostic(
        buyer_gstin="24AAACS0000A1Z5",
        trancatg="B2B",
        has_payment_of_tax=True
    )
    assert not diag["is_valid"]
    assert diag["error_code"] == 2246
    assert diag["scenario"] == "SEZ_SUPPLY_TAGGED_AS_STANDARD_B2B"
    assert diag["rectified_trancatg"] == "SEZWP"


def test_rule_2246_scenario_2_deemed_export_used_for_sez():
    """Scenario 2: Deemed Export ('DEXP') used for SEZ unit."""
    diag = classify_rule_2246_diagnostic(
        buyer_gstin="24AAACS0000A1Z5",
        trancatg="DEXP",
        has_payment_of_tax=True
    )
    assert not diag["is_valid"]
    assert diag["error_code"] == 2246
    assert diag["scenario"] == "DEEMED_EXPORT_USED_FOR_SEZ_UNIT"
    assert diag["rectified_trancatg"] == "SEZWP"


def test_rule_2246_scenario_3_regular_dta_marked_with_wrong_gstin():
    """Scenario 3: Regular DTA buyer entered with SEZ sister unit GSTIN by mistake."""
    diag = classify_rule_2246_diagnostic(
        buyer_gstin="24AAACS0000A1Z5",
        trancatg="B2B",
        is_dta_sale=True,
        dta_gstin="24AAACD0000A1Z5"
    )
    assert not diag["is_valid"]
    assert diag["error_code"] == 2246
    assert diag["scenario"] == "REGULAR_DTA_BUYER_MARKED_WITH_WRONG_GSTIN"
    assert diag["rectified_trancatg"] == "B2B"
    assert diag["rectified_gstin"] == "24AAACD0000A1Z5"


def test_rule_2246_valid():
    """Valid transaction categories for SEZ and non-SEZ buyers."""
    # SEZ buyer on SEZWP
    diag_sez = classify_rule_2246_diagnostic(
        buyer_gstin="24AAACS0000A1Z5",
        trancatg="SEZWP"
    )
    assert diag_sez["is_valid"]
    assert diag_sez["error_code"] is None

    # Standard non-SEZ buyer on B2B
    diag_b2b = classify_rule_2246_diagnostic(
        buyer_gstin="27BBBBB1111B1Z2",
        trancatg="B2B"
    )
    assert diag_b2b["is_valid"]
    assert diag_b2b["error_code"] is None


# ==============================================================================
# GSTVALIDATOR PRE-API VALIDATION TESTS
# ==============================================================================

def test_rule_2243_validator_catches_invalid_pos(clean_b2b_invoice):
    invoice = copy.deepcopy(clean_b2b_invoice)
    invoice["buyer"]["pos"] = "00"
    errors = GSTValidator.validate_invoice(invoice)
    assert any(e.get("error_code") == 2243 for e in errors)


def test_rule_2244_validator_catches_missing_pin(clean_b2b_invoice):
    invoice = copy.deepcopy(clean_b2b_invoice)
    invoice["buyer"]["pin"] = ""
    errors = GSTValidator.validate_invoice(invoice)
    assert any(e.get("error_code") == 2244 for e in errors)


def test_rule_2246_validator_catches_sez_tagged_b2b(clean_b2b_invoice):
    invoice = copy.deepcopy(clean_b2b_invoice)
    invoice["buyer"]["gstin"] = "24AAACS0000A1Z5"
    invoice["buyer"]["is_sez"] = True
    invoice["trancatg"] = "B2B"
    errors = GSTValidator.validate_invoice(invoice)
    assert any(e.get("error_code") == 2246 for e in errors)


def test_rules_2243_to_2246_validator_passes_valid(clean_b2b_invoice, clean_export_invoice):
    assert len(GSTValidator.validate_invoice(clean_b2b_invoice)) == 0
    assert len(GSTValidator.validate_invoice(clean_export_invoice)) == 0


# ==============================================================================
# RULES ENGINE TESTS
# ==============================================================================

def test_rule_2243_rules_engine_catches_invalid_pos(clean_b2b_invoice):
    invoice = copy.deepcopy(clean_b2b_invoice)
    invoice["buyer"]["pos"] = "KA"
    errors = RulesEngine.validate_invoice(invoice)
    assert any(e.get("error_code") == 2243 for e in errors)


def test_rule_2244_rules_engine_catches_missing_pin(clean_b2b_invoice):
    invoice = copy.deepcopy(clean_b2b_invoice)
    invoice["buyer"]["pin"] = ""
    errors = RulesEngine.validate_invoice(invoice)
    assert any(e.get("error_code") == 2244 for e in errors)


def test_rule_2246_rules_engine_catches_sez_tagged_b2b(clean_b2b_invoice):
    invoice = copy.deepcopy(clean_b2b_invoice)
    invoice["buyer"]["gstin"] = "24AAACS0000A1Z5"
    invoice["buyer"]["is_sez"] = True
    invoice["trancatg"] = "B2B"
    errors = RulesEngine.validate_invoice(invoice)
    assert any(e.get("error_code") == 2246 for e in errors)


# ==============================================================================
# PYDANTIC CROSS-MODEL REJECTION TESTS
# ==============================================================================

def test_rule_2243_pydantic_schema_rejection(clean_b2b_invoice):
    inv = copy.deepcopy(clean_b2b_invoice)
    inv["buyer"]["pos"] = "00"
    with pytest.raises(Exception) as exc_info:
        InvoicePayload.model_validate(inv).validate_cross_model_statutory_rules()
    assert "2243" in str(exc_info.value)


def test_rule_2244_pydantic_schema_rejection(clean_b2b_invoice):
    inv = copy.deepcopy(clean_b2b_invoice)
    inv["buyer"]["pin"] = 12345
    with pytest.raises(Exception) as exc_info:
        InvoicePayload.model_validate(inv).validate_cross_model_statutory_rules()
    assert "2244" in str(exc_info.value)


def test_rule_2246_pydantic_schema_rejection(clean_b2b_invoice):
    inv = copy.deepcopy(clean_b2b_invoice)
    inv["buyer"]["gstin"] = "24AAACS0000A1Z5"
    inv["buyer"]["state"] = "24"
    inv["buyer"]["pos"] = "24"
    inv["buyer"]["pin"] = 380001
    inv["buyer"]["is_sez"] = True
    inv["trancatg"] = "B2B"
    with pytest.raises(Exception) as exc_info:
        InvoicePayload.model_validate(inv).validate_cross_model_statutory_rules()
    assert "2246" in str(exc_info.value)


# ==============================================================================
# AUTO-CORRECT AND BUILD AUDIT LOG TESTS
# ==============================================================================

def test_rule_2243_auto_correct_single_digit_pos(clean_b2b_invoice):
    inv = copy.deepcopy(clean_b2b_invoice)
    inv["buyer"]["gstin"] = "07BBBBB1111B1Z2"
    inv["buyer"]["state"] = "07"
    inv["buyer"]["pos"] = "7"
    payload, audit_logs = InvoicePayload.auto_correct_and_build(inv)
    assert payload.buyer.pos == "07"
    assert any("2243" in log.get("category", "") for log in audit_logs)


def test_rule_2243_auto_correct_alpha_pos(clean_b2b_invoice):
    inv = copy.deepcopy(clean_b2b_invoice)
    inv["buyer"]["gstin"] = "29BBBBB1111B1Z2"
    inv["buyer"]["state"] = "29"
    inv["buyer"]["pos"] = "KA"
    payload, audit_logs = InvoicePayload.auto_correct_and_build(inv)
    assert payload.buyer.pos == "29"
    assert any("2243" in log.get("category", "") for log in audit_logs)


def test_rule_2244_auto_correct_missing_pin(clean_b2b_invoice):
    inv = copy.deepcopy(clean_b2b_invoice)
    inv["buyer"]["pin"] = None
    payload, audit_logs = InvoicePayload.auto_correct_and_build(inv)
    assert len(str(payload.buyer.pin)) == 6
    assert any("2244" in log.get("category", "") for log in audit_logs)


def test_rule_2246_auto_correct_sez_tagged_b2b(clean_b2b_invoice):
    inv = copy.deepcopy(clean_b2b_invoice)
    inv["buyer"]["gstin"] = "24AAACS0000A1Z5"
    inv["buyer"]["is_sez"] = True
    inv["trancatg"] = "B2B"
    payload, audit_logs = InvoicePayload.auto_correct_and_build(inv)
    assert payload.trancatg in ("SEZWP", "SEZWOP")
    assert any("2246" in log.get("category", "") for log in audit_logs)


# ==============================================================================
# DATA LAKEHOUSE PARQUET RECONCILIATION TEST
# ==============================================================================

def test_rules_2243_to_2246_lakehouse_storage_reconciliation(clean_b2b_invoice):
    """Verifies that an invoice corrected across Rules 2243, 2244, and 2246 flattens and stores properly."""
    inv = copy.deepcopy(clean_b2b_invoice)
    inv["buyer"]["pos"] = "7"  # triggers 2243 -> auto-corrects to 07
    inv["buyer"]["pin"] = ""  # triggers 2244 -> auto-corrects to 400001 (or state PIN)
    inv["buyer"]["gstin"] = "24AAACS0000A1Z5"  # triggers 2246 -> auto-corrects trancatg to SEZWP
    inv["buyer"]["is_sez"] = True
    inv["trancatg"] = "B2B"

    payload, audit_logs = InvoicePayload.auto_correct_and_build(inv)
    flattened = flatten_invoice_payload(payload)

    temp_dir = tempfile.mkdtemp()
    try:
        parquet_path = os.path.join(temp_dir, "test_rules_2243_to_2246.parquet")
        write_parquet(flattened, parquet_path)

        assert os.path.exists(parquet_path)
        df = read_parquet(parquet_path)
        assert len(df) == 1
        assert df["buyer_pos"].iloc[0] == "07"
        assert len(str(df["buyer_pin"].iloc[0])) == 6
        assert df["transaction_category"].iloc[0] in ("SEZWP", "SEZWOP")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
