"""
Comprehensive Statutory Test Suite for Rules 2258, 2259, 2260, 2261, and 2262:
- Rule 2258: Supplier GSTIN state code does not match state code passed
- Rule 2259: Invalid supplier state code
- Rule 2260: The recipient state code is invalid
- Rule 2261: The recipient state code is incorrect for export transaction
- Rule 2262: For Intra-state supply, IGST cannot be charged (IgstOnIntra error)
"""

import copy
import pytest
from decimal import Decimal
from typing import Dict, Any

from Template_Converters.validator import GSTValidator
from src.rules.rules_engine import RulesEngine
from src.ingestion.schemas import (
    InvoicePayload,
    NICValidationError,
    classify_rule_2258_diagnostic,
    classify_rule_2259_diagnostic,
    classify_rule_2260_diagnostic,
    classify_rule_2261_diagnostic,
    classify_rule_2262_diagnostic,
)
from src.ingestion.storage import (
    flatten_invoice_payload,
    write_parquet,
    read_parquet,
)


@pytest.fixture
def clean_b2b_invoice() -> Dict[str, Any]:
    """A standard clean domestic intra-state B2B invoice (Maharashtra -> Maharashtra)."""
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
            "lglnm": "Precision Instruments Ltd",
            "bnm": "MIDC Tech Park",
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
def clean_inter_state_invoice() -> Dict[str, Any]:
    """A standard clean domestic inter-state B2B invoice (Maharashtra -> Karnataka)."""
    return {
        "self_gstin": "27AAAAA0000A1Z5",
        "docno": "INV-2026-INTER01",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "B2B",
        "igstonintra": "N",
        "supplier": {
            "gstin": "27AAAAA0000A1Z5",
            "lglnm": "Apex Components Ltd",
            "bnm": "Apex House",
            "state": "27",
            "pin": "400001",
            "loc": "Mumbai"
        },
        "buyer": {
            "gstin": "29BBBBB1111B1Z2",
            "lglnm": "Karnataka Electronics Ltd",
            "bnm": "Electronic City",
            "state": "29",
            "pos": "29",
            "pin": "560100",
            "loc": "Bengaluru"
        },
        "itemdtls": [
            {
                "slno": "1",
                "prdnm": "Microcontroller Kit",
                "hsncd": "85423100",
                "qty": "5.00",
                "uqc": "NOS",
                "unit": "NOS",
                "unitprice": "2000.00",
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


@pytest.fixture
def clean_export_invoice() -> Dict[str, Any]:
    """A standard clean direct export invoice (Maharashtra -> Overseas)."""
    return {
        "self_gstin": "27AAAAA0000A1Z5",
        "docno": "EXP-2026-001",
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
            "lglnm": "Global Imports LLC",
            "bnm": "Trade Tower 101",
            "state": "96",
            "pos": "96",
            "pin": "999999",
            "loc": "New York"
        },
        "expdt1": {
            "shipbno": "SB-123456",
            "shipbdt": "26-10-2026",
            "port": "INBOM1",
            "cntcode": "US",
            "forcur": "USD"
        },
        "itemdtls": [
            {
                "slno": "1",
                "prdnm": "Precision CNC Parts",
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
# RULE 2258: SUPPLIER GSTIN STATE CODE MISMATCH
# ==============================================================================

def test_rule_2258_diagnostic_prefix_mismatch():
    diag = classify_rule_2258_diagnostic(
        supplier_gstin="27AAAAA0000A1Z5",
        supplier_state="29"
    )
    assert diag["error_code"] == 2258
    assert diag["scenario"] == "PREFIX_MISMATCH"
    assert not diag["is_valid"]
    assert diag["rectified_state"] == "27"
    assert "SellerDtls" in diag["correct_payload"]


def test_rule_2258_diagnostic_missing_state():
    diag = classify_rule_2258_diagnostic(
        supplier_gstin="27AAAAA0000A1Z5",
        supplier_state=None
    )
    assert diag["error_code"] == 2258
    assert diag["scenario"] == "SUPPLIER_STATE_MISSING"
    assert diag["rectified_state"] == "27"


def test_rule_2258_diagnostic_clean_pass():
    diag = classify_rule_2258_diagnostic(
        supplier_gstin="27AAAAA0000A1Z5",
        supplier_state="27"
    )
    assert diag["is_valid"]
    assert diag["error_code"] is None
    assert diag["scenario"] == "VALID"


# ==============================================================================
# RULE 2259: INVALID SUPPLIER STATE CODE
# ==============================================================================

def test_rule_2259_diagnostic_alphabetic():
    diag = classify_rule_2259_diagnostic(supplier_state="MH", supplier_gstin="27AAAAA0000A1Z5")
    assert diag["error_code"] == 2259
    assert diag["scenario"] == "ALPHABETIC_STATE_CODE_PASSED"
    assert diag["rectified_state"] == "27"


def test_rule_2259_diagnostic_numeric_type():
    diag = classify_rule_2259_diagnostic(supplier_state=27, supplier_gstin="27AAAAA0000A1Z5")
    assert diag["error_code"] == 2259
    assert diag["scenario"] == "NUMERIC_TYPE_PASSED_INSTEAD_OF_STRING"
    assert diag["rectified_state"] == "27"


def test_rule_2259_diagnostic_leading_zero():
    diag = classify_rule_2259_diagnostic(supplier_state="7", supplier_gstin="07AAAAA0000A1Z5")
    assert diag["error_code"] == 2259
    assert diag["scenario"] == "LEADING_ZERO_OMITTED"
    assert diag["rectified_state"] == "07"


def test_rule_2259_diagnostic_non_existent():
    diag = classify_rule_2259_diagnostic(supplier_state="00", supplier_gstin="27AAAAA0000A1Z5")
    assert diag["error_code"] == 2259
    assert diag["scenario"] == "NON_EXISTENT_STATE_CODE"
    assert diag["rectified_state"] == "27"


def test_rule_2259_diagnostic_omitted():
    diag = classify_rule_2259_diagnostic(supplier_state="", supplier_gstin="27AAAAA0000A1Z5")
    assert diag["error_code"] == 2259
    assert diag["scenario"] == "STATE_CODE_OMITTED_OR_NULL"
    assert diag["rectified_state"] == "27"


def test_rule_2259_diagnostic_clean_pass():
    diag = classify_rule_2259_diagnostic(supplier_state="27", supplier_gstin="27AAAAA0000A1Z5")
    assert diag["is_valid"]
    assert diag["error_code"] is None


# ==============================================================================
# RULE 2260: THE RECIPIENT STATE CODE IS INVALID
# ==============================================================================

def test_rule_2260_diagnostic_alphabetic():
    diag = classify_rule_2260_diagnostic(buyer_state="KA", buyer_gstin="29BBBBB1111B1Z2")
    assert diag["error_code"] == 2260
    assert diag["scenario"] == "ALPHABETIC_STATE_CODE_PASSED"
    assert diag["rectified_state"] == "29"


def test_rule_2260_diagnostic_numeric_type():
    diag = classify_rule_2260_diagnostic(buyer_state=29, buyer_gstin="29BBBBB1111B1Z2")
    assert diag["error_code"] == 2260
    assert diag["scenario"] == "NUMERIC_TYPE_PASSED_INSTEAD_OF_STRING"
    assert diag["rectified_state"] == "29"


def test_rule_2260_diagnostic_leading_zero():
    diag = classify_rule_2260_diagnostic(buyer_state="9", buyer_gstin="09BBBBB1111B1Z2")
    assert diag["error_code"] == 2260
    assert diag["scenario"] == "LEADING_ZERO_OMITTED"
    assert diag["rectified_state"] == "09"


def test_rule_2260_diagnostic_non_existent():
    diag = classify_rule_2260_diagnostic(buyer_state="00", buyer_gstin="29BBBBB1111B1Z2")
    assert diag["error_code"] == 2260
    assert diag["scenario"] == "NON_EXISTENT_OR_INVALID_STATE_CODE"
    assert diag["rectified_state"] == "29"


def test_rule_2260_diagnostic_clean_pass():
    diag = classify_rule_2260_diagnostic(buyer_state="29", buyer_gstin="29BBBBB1111B1Z2")
    assert diag["is_valid"]
    assert diag["error_code"] is None


# ==============================================================================
# RULE 2261: RECIPIENT STATE CODE INCORRECT FOR EXPORT
# ==============================================================================

def test_rule_2261_diagnostic_domestic_in_export():
    diag = classify_rule_2261_diagnostic(
        buyer_state="27",
        trancatg="EXPWP",
        is_export=True,
        buyer_gstin="URP"
    )
    assert diag["error_code"] == 2261
    assert diag["scenario"] == "DOMESTIC_STATE_CODE_IN_EXPORT"
    assert diag["rectified_state"] == "96"


def test_rule_2261_diagnostic_omitted_in_export():
    diag = classify_rule_2261_diagnostic(
        buyer_state=None,
        trancatg="EXPWP",
        is_export=True,
        buyer_gstin="URP"
    )
    assert diag["error_code"] == 2261
    assert diag["scenario"] == "EXPORT_STATE_CODE_OMITTED_OR_NULL"
    assert diag["rectified_state"] == "96"


def test_rule_2261_diagnostic_domestic_sale_misclassified():
    diag = classify_rule_2261_diagnostic(
        buyer_state="27",
        trancatg="EXPWP",
        is_export=True,
        is_domestic_sale=True,
        buyer_gstin="27BBBBB1111B1Z2"
    )
    assert diag["error_code"] == 2261
    assert diag["scenario"] == "DOMESTIC_SALE_MISCLASSIFIED_AS_EXPORT"
    assert diag["rectified_trancatg"] == "B2B"
    assert diag["rectified_state"] == "27"


def test_rule_2261_diagnostic_clean_pass():
    diag = classify_rule_2261_diagnostic(
        buyer_state="96",
        trancatg="EXPWP",
        is_export=True,
        buyer_gstin="URP"
    )
    assert diag["is_valid"]
    assert diag["error_code"] is None


# ==============================================================================
# RULE 2262: FOR INTRA-STATE SUPPLY, IGST CANNOT BE CHARGED
# ==============================================================================

def test_rule_2262_diagnostic_misapplied_flag():
    diag = classify_rule_2262_diagnostic(
        igstonintra="Y",
        seller_state="27",
        pos="29",
        is_actual_intra=False
    )
    assert diag["error_code"] == 2262
    assert diag["scenario"] == "MISAPPLIED_FLAG_ON_INTER_STATE_SALE"
    assert diag["rectified_igstonintra"] == "N"
    assert diag["rectified_pos"] == "29"


def test_rule_2262_diagnostic_intra_with_incorrect_pos():
    diag = classify_rule_2262_diagnostic(
        igstonintra="Y",
        seller_state="27",
        pos="29",
        is_actual_intra=True
    )
    assert diag["error_code"] == 2262
    assert diag["scenario"] == "INTRA_STATE_SALE_WITH_INCORRECT_POS"
    assert diag["rectified_igstonintra"] == "Y"
    assert diag["rectified_pos"] == "27"


def test_rule_2262_diagnostic_clean_pass_exceptional_intra():
    diag = classify_rule_2262_diagnostic(
        igstonintra="Y",
        seller_state="27",
        pos="27",
        is_actual_intra=False
    )
    assert diag["is_valid"]
    assert diag["error_code"] is None


def test_rule_2262_diagnostic_clean_pass_standard_inter_state():
    diag = classify_rule_2262_diagnostic(
        igstonintra="N",
        seller_state="27",
        pos="29",
        is_actual_intra=False
    )
    assert diag["is_valid"]
    assert diag["error_code"] is None


# ==============================================================================
# VALIDATOR & RULES ENGINE TESTS
# ==============================================================================

def test_rule_2258_validator_and_rules_engine(clean_b2b_invoice):
    inv = copy.deepcopy(clean_b2b_invoice)
    inv["supplier"]["state"] = "29"  # Mismatch with 27AAAAA0000A1Z5

    val_errors = GSTValidator.validate_invoice(inv)
    assert any(e.get("error_code") == 2258 for e in val_errors)

    engine_errors = RulesEngine.validate_invoice(inv)
    assert any(e.get("error_code") == 2258 for e in engine_errors)


def test_rule_2259_validator_and_rules_engine(clean_b2b_invoice):
    inv = copy.deepcopy(clean_b2b_invoice)
    inv["supplier"]["state"] = "MH"

    val_errors = GSTValidator.validate_invoice(inv)
    assert any(e.get("error_code") == 2259 for e in val_errors)

    engine_errors = RulesEngine.validate_invoice(inv)
    assert any(e.get("error_code") == 2259 for e in engine_errors)


def test_rule_2260_validator_and_rules_engine(clean_inter_state_invoice):
    inv = copy.deepcopy(clean_inter_state_invoice)
    inv["buyer"]["state"] = "KA"

    val_errors = GSTValidator.validate_invoice(inv)
    assert any(e.get("error_code") == 2260 for e in val_errors)

    engine_errors = RulesEngine.validate_invoice(inv)
    assert any(e.get("error_code") == 2260 for e in engine_errors)


def test_rule_2261_validator_and_rules_engine(clean_export_invoice):
    inv = copy.deepcopy(clean_export_invoice)
    inv["buyer"]["state"] = "27"  # Domestic state in export

    val_errors = GSTValidator.validate_invoice(inv)
    assert any(e.get("error_code") == 2261 for e in val_errors)

    engine_errors = RulesEngine.validate_invoice(inv)
    assert any(e.get("error_code") == 2261 for e in engine_errors)


def test_rule_2262_validator_and_rules_engine(clean_inter_state_invoice):
    inv = copy.deepcopy(clean_inter_state_invoice)
    inv["igstonintra"] = "Y"  # Seller state 27 != buyer pos 29

    val_errors = GSTValidator.validate_invoice(inv)
    assert any(e.get("error_code") == 2262 for e in val_errors)

    engine_errors = RulesEngine.validate_invoice(inv)
    assert any(e.get("error_code") == 2262 for e in engine_errors)


# ==============================================================================
# PYDANTIC SCHEMA CROSS-MODEL VALIDATION REJECTION TESTS
# ==============================================================================

def test_rule_2258_pydantic_schema_rejection(clean_b2b_invoice):
    inv = copy.deepcopy(clean_b2b_invoice)
    inv["supplier"]["state"] = "29"
    inv["supplier"]["pin"] = "560001"
    with pytest.raises(Exception) as exc_info:
        InvoicePayload.model_validate(inv).validate_cross_model_statutory_rules()
    assert "2258" in str(exc_info.value)


def test_rule_2259_pydantic_schema_rejection(clean_b2b_invoice):
    inv = copy.deepcopy(clean_b2b_invoice)
    inv["supplier"]["state"] = "00"
    with pytest.raises(Exception) as exc_info:
        InvoicePayload.model_validate(inv).validate_cross_model_statutory_rules()
    assert "2259" in str(exc_info.value)


def test_rule_2260_pydantic_schema_rejection(clean_inter_state_invoice):
    inv = copy.deepcopy(clean_inter_state_invoice)
    inv["buyer"]["state"] = "00"
    with pytest.raises(Exception) as exc_info:
        InvoicePayload.model_validate(inv).validate_cross_model_statutory_rules()
    assert "2260" in str(exc_info.value)


def test_rule_2261_pydantic_schema_rejection(clean_export_invoice):
    inv = copy.deepcopy(clean_export_invoice)
    inv["buyer"]["state"] = "27"
    with pytest.raises(Exception) as exc_info:
        InvoicePayload.model_validate(inv).validate_cross_model_statutory_rules()
    assert "2261" in str(exc_info.value)


def test_rule_2262_pydantic_schema_rejection(clean_inter_state_invoice):
    inv = copy.deepcopy(clean_inter_state_invoice)
    inv["igstonintra"] = "Y"
    inv["reversecharge"] = "Y"  # Pass 2294 to test 2262
    with pytest.raises(Exception) as exc_info:
        InvoicePayload.model_validate(inv).validate_cross_model_statutory_rules()
    assert "2262" in str(exc_info.value)


# ==============================================================================
# AUTO-CORRECTION AND BUILD AUDIT LOG TESTS
# ==============================================================================

def test_rule_2258_auto_correct_prefix_mismatch(clean_b2b_invoice):
    inv = copy.deepcopy(clean_b2b_invoice)
    inv["supplier"]["state"] = "29"  # Mismatch with 27 GSTIN

    corrected, audit = InvoicePayload.auto_correct_and_build(inv)
    assert corrected.supplier.state == "27"
    categories = [entry["category"] for entry in audit]
    assert any("2258" in c for c in categories)


def test_rule_2259_auto_correct_alpha_supplier_state(clean_b2b_invoice):
    inv = copy.deepcopy(clean_b2b_invoice)
    inv["supplier"]["state"] = "MH"

    corrected, audit = InvoicePayload.auto_correct_and_build(inv)
    assert corrected.supplier.state == "27"
    categories = [entry["category"] for entry in audit]
    assert any("2259" in c for c in categories)


def test_rule_2260_auto_correct_leading_zero_buyer_state(clean_inter_state_invoice):
    inv = copy.deepcopy(clean_inter_state_invoice)
    inv["buyer"]["state"] = "9"
    inv["buyer"]["gstin"] = "09BBBBB1111B1Z2"
    inv["buyer"]["pos"] = "09"
    inv["buyer"]["pin"] = "201301"

    corrected, audit = InvoicePayload.auto_correct_and_build(inv)
    assert corrected.buyer.state == "09"
    categories = [entry["category"] for entry in audit]
    assert any("2260" in c for c in categories)


def test_rule_2261_auto_correct_domestic_in_export(clean_export_invoice):
    inv = copy.deepcopy(clean_export_invoice)
    inv["buyer"]["state"] = "27"

    corrected, audit = InvoicePayload.auto_correct_and_build(inv)
    assert corrected.buyer.state == "96"
    assert corrected.buyer.pos == "96"
    categories = [entry["category"] for entry in audit]
    assert any("2261" in c for c in categories)


def test_rule_2262_auto_correct_misapplied_igstonintra(clean_inter_state_invoice):
    inv = copy.deepcopy(clean_inter_state_invoice)
    inv["igstonintra"] = "Y"  # Seller state 27 != buyer pos 29

    corrected, audit = InvoicePayload.auto_correct_and_build(inv)
    assert corrected.igstonintra == "N"
    categories = [entry["category"] for entry in audit]
    assert any("2262" in c for c in categories)


# ==============================================================================
# LAKEHOUSE PARQUET STORAGE TESTS
# ==============================================================================

def test_lakehouse_roundtrip_rules_2258_to_2262(tmp_path, clean_b2b_invoice, clean_inter_state_invoice, clean_export_invoice):
    pq_path = tmp_path / "lakehouse_rules_2258_to_2262.parquet"

    # Auto-correct and build
    m_b2b, _ = InvoicePayload.auto_correct_and_build(clean_b2b_invoice)
    m_inter, _ = InvoicePayload.auto_correct_and_build(clean_inter_state_invoice)
    m_exp, _ = InvoicePayload.auto_correct_and_build(clean_export_invoice)

    flat_records = []
    for model in (m_b2b, m_inter, m_exp):
        flat = flatten_invoice_payload(model)
        for row in flat:
            row["sentinel_audit_reasons"] = "Rules 2258-2262 statutory validation passed"
            flat_records.append(row)

    write_parquet(flat_records, str(pq_path))
    assert pq_path.exists()

    df = read_parquet(str(pq_path))
    assert len(df) == 3
    assert "supplier_state" in df.columns
    assert "buyer_state" in df.columns
    assert "transaction_category" in df.columns
