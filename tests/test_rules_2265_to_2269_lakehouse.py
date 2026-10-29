"""
Statutory Test Suite: Rules 2265, 2266, 2267, 2268, 2269 & Lakehouse Parquet Persistence.
Covers:
- Rule 2265: Recipient GSTIN state code does not match state code passed
- Rule 2266: Item Cess amount does not match calculated value (Ad-valorem calculation error)
- Rule 2267: Item State Cess amount does not match calculated value (State Cess formula mismatch)
- Rule 2268: IGST on intra-state supply is not applicable to Export/SEZ (Section 7(5) IGST Act)
- Rule 2269: Recipient state code is incorrect (Code 96 passed on domestic supply type)
- Lakehouse Parquet persistence and audit trail logging.
"""

import copy
import pytest
from decimal import Decimal
from typing import Dict, Any

from src.ingestion.schemas import (
    classify_rule_2265_diagnostic,
    classify_rule_2266_diagnostic,
    classify_rule_2267_diagnostic,
    classify_rule_2268_diagnostic,
    classify_rule_2269_diagnostic,
    LineItem,
    InvoicePayload,
    NICValidationError,
)
from src.rules.rules_engine import RulesEngine
from Template_Converters.validator import GSTValidator
from src.ingestion.storage import write_parquet, read_parquet, flatten_invoice_payload


@pytest.fixture
def clean_b2b_payload() -> Dict[str, Any]:
    return {
        "self_gstin": "27AAAAA0000A1Z5",
        "docno": "INV-2026-9901",
        "docdt": "2026-10-25",
        "document_type": "INV",
        "trancatg": "B2B",
        "igstonintra": "N",
        "reversecharge": "N",
        "supplier": {
            "legal_name": "Maharashtra Supplier Ltd",
            "gstin": "27AAAAA0000A1Z5",
            "state": "27",
            "address1": "Nariman Point",
            "loc": "Mumbai",
            "pin": "400021"
        },
        "buyer": {
            "legal_name": "Karnataka Buyer Pvt Ltd",
            "gstin": "29BBBBB0000B1Z2",
            "state": "29",
            "pos": "29",
            "address1": "MG Road",
            "loc": "Bengaluru",
            "pin": "560001"
        },
        "itemdtls": [
            {
                "slno": "1",
                "prdnm": "Special Industrial Gearbox",
                "hsn": "84834000",
                "qty": "1.00",
                "unit": "NOS",
                "unitprice": "100000.00",
                "totamt": "100000.00",
                "discount": "0.00",
                "assval": "100000.00",
                "gstrate": 18.0,
                "igstval": "18000.00",
                "cgstval": "0.00",
                "sgstval": "0.00",
                "cesrate": 12.0,
                "cesval": "12000.00",
                "cesnonadvl": "0.00",
                "statecesrate": 1.0,
                "statecesval": "1000.00",
                "statecesnonadvl": "0.00",
                "othchrg": "0.00",
                "totitemval": "131000.00"
            }
        ],
        "valdtls": {
            "assval": "100000.00",
            "cgstval": "0.00",
            "sgstval": "0.00",
            "igstval": "18000.00",
            "cesval": "12000.00",
            "stcesval": "1000.00",
            "discount": "0.00",
            "othchrg": "0.00",
            "rndoffamt": "0.00",
            "totinvval": "131000.00"
        }
    }


# ============================================================================
# 1. DIAGNOSTIC TESTS FOR RULE 2265
# ============================================================================

def test_rule_2265_diagnostic_prefix_mismatch():
    diag = classify_rule_2265_diagnostic(
        buyer_gstin="29BBBBB0000B1Z2",
        buyer_state="27"
    )
    assert not diag["is_valid"]
    assert diag["error_code"] == 2265
    assert diag["scenario"] == "PREFIX_MISMATCH"
    assert diag["rectified_state"] == "29"


def test_rule_2265_diagnostic_missing_state():
    diag = classify_rule_2265_diagnostic(
        buyer_gstin="29BBBBB0000B1Z2",
        buyer_state=""
    )
    assert not diag["is_valid"]
    assert diag["error_code"] == 2265
    assert diag["scenario"] == "RECIPIENT_STATE_MISSING"
    assert diag["rectified_state"] == "29"


def test_rule_2265_diagnostic_clean_pass():
    diag = classify_rule_2265_diagnostic(
        buyer_gstin="29BBBBB0000B1Z2",
        buyer_state="29"
    )
    assert diag["is_valid"]
    assert diag["error_code"] is None
    assert diag["rectified_state"] == "29"


# ============================================================================
# 2. DIAGNOSTIC TESTS FOR RULE 2266
# ============================================================================

def test_rule_2266_diagnostic_ad_valorem_error():
    diag = classify_rule_2266_diagnostic(
        assval=100000.00,
        cesrate=12.0,
        cesval=10000.00,
        item_slno="1"
    )
    assert not diag["is_valid"]
    assert diag["error_code"] == 2266
    assert diag["scenario"] == "AD_VALOREM_CESS_CALCULATION_ERROR"
    assert diag["rectified_cesval"] == 12000.00


def test_rule_2266_diagnostic_non_ad_valorem_in_ad_valorem():
    diag = classify_rule_2266_diagnostic(
        assval=100000.00,
        cesrate=0.0,
        cesval=500.00,
        cesnonadvl=0.0,
        item_slno="1"
    )
    assert not diag["is_valid"]
    assert diag["error_code"] == 2266
    assert diag["scenario"] == "NON_AD_VALOREM_CESS_DECLARED_AS_AD_VALOREM"
    assert diag["rectified_cesval"] == 0.0
    assert diag["rectified_cesnonadvl"] == 500.00


def test_rule_2266_diagnostic_clean_pass():
    diag = classify_rule_2266_diagnostic(
        assval=100000.00,
        cesrate=12.0,
        cesval=12000.00,
        item_slno="1"
    )
    assert diag["is_valid"]
    assert diag["error_code"] is None


def test_rule_2266_diagnostic_tolerance_pass():
    diag = classify_rule_2266_diagnostic(
        assval=100000.00,
        cesrate=12.0,
        cesval=12000.50,
        item_slno="1"
    )
    assert diag["is_valid"]


# ============================================================================
# 3. DIAGNOSTIC TESTS FOR RULE 2267
# ============================================================================

def test_rule_2267_diagnostic_formula_mismatch():
    diag = classify_rule_2267_diagnostic(
        assval=50000.00,
        statecesrate=1.0,
        statecesval=100.00,
        item_slno="1"
    )
    assert not diag["is_valid"]
    assert diag["error_code"] == 2267
    assert diag["scenario"] == "STATE_CESS_FORMULA_MISMATCH"
    assert diag["rectified_statecesval"] == 500.00


def test_rule_2267_diagnostic_non_ad_valorem_in_ad_valorem():
    diag = classify_rule_2267_diagnostic(
        assval=50000.00,
        statecesrate=0.0,
        statecesval=250.00,
        statecesnonadvl=0.0,
        item_slno="1"
    )
    assert not diag["is_valid"]
    assert diag["error_code"] == 2267
    assert diag["scenario"] == "NON_AD_VALOREM_STATE_CESS_DECLARED_AS_AD_VALOREM"
    assert diag["rectified_statecesval"] == 0.0
    assert diag["rectified_statecesnonadvl"] == 250.00


def test_rule_2267_diagnostic_clean_pass():
    diag = classify_rule_2267_diagnostic(
        assval=50000.00,
        statecesrate=1.0,
        statecesval=500.00,
        item_slno="1"
    )
    assert diag["is_valid"]
    assert diag["error_code"] is None


# ============================================================================
# 4. DIAGNOSTIC TESTS FOR RULE 2268
# ============================================================================

def test_rule_2268_diagnostic_invalid_override_export():
    diag = classify_rule_2268_diagnostic(
        igstonintra="Y",
        trancatg="EXPWP"
    )
    assert not diag["is_valid"]
    assert diag["error_code"] == 2268
    assert diag["scenario"] == "INVALID_OVERRIDE_ON_EXPORT_OR_SEZ"
    assert diag["rectified_igstonintra"] == "N"


def test_rule_2268_diagnostic_invalid_override_sez():
    diag = classify_rule_2268_diagnostic(
        igstonintra="Y",
        trancatg="SEZWP"
    )
    assert not diag["is_valid"]
    assert diag["error_code"] == 2268
    assert diag["scenario"] == "INVALID_OVERRIDE_ON_EXPORT_OR_SEZ"
    assert diag["rectified_igstonintra"] == "N"


def test_rule_2268_diagnostic_clean_pass_export():
    diag = classify_rule_2268_diagnostic(
        igstonintra="N",
        trancatg="EXPWP"
    )
    assert diag["is_valid"]
    assert diag["error_code"] is None
    assert diag["rectified_igstonintra"] == "N"


def test_rule_2268_diagnostic_clean_pass_domestic():
    diag = classify_rule_2268_diagnostic(
        igstonintra="Y",
        trancatg="B2B"
    )
    assert diag["is_valid"]
    assert diag["error_code"] is None


# ============================================================================
# 5. DIAGNOSTIC TESTS FOR RULE 2269
# ============================================================================

def test_rule_2269_diagnostic_export_code_on_domestic_b2b():
    diag = classify_rule_2269_diagnostic(
        buyer_state="96",
        trancatg="B2B",
        buyer_gstin="29BBBBB0000B1Z2"
    )
    assert not diag["is_valid"]
    assert diag["error_code"] == 2269
    assert diag["scenario"] == "EXPORT_CODE_USED_ON_DOMESTIC_TYPE"
    assert diag["rectified_state"] == "29"


def test_rule_2269_diagnostic_export_misclassified_as_domestic():
    diag = classify_rule_2269_diagnostic(
        buyer_state="96",
        trancatg="B2B",
        buyer_gstin="URP",
        is_actual_export=True
    )
    assert not diag["is_valid"]
    assert diag["error_code"] == 2269
    assert diag["scenario"] == "EXPORT_TRANSACTION_MISCLASSIFIED_AS_DOMESTIC"
    assert diag["rectified_trancatg"] == "EXPWP"


def test_rule_2269_diagnostic_clean_pass():
    diag = classify_rule_2269_diagnostic(
        buyer_state="29",
        trancatg="B2B",
        buyer_gstin="29BBBBB0000B1Z2"
    )
    assert diag["is_valid"]
    assert diag["error_code"] is None


# ============================================================================
# 6. VALIDATOR & RULES ENGINE TESTS
# ============================================================================

def test_rule_2265_validator_and_rules_engine(clean_b2b_payload):
    inv = copy.deepcopy(clean_b2b_payload)
    inv["buyer"]["state"] = "27"  # Mismatch with 29BBBBB0000B1Z2
    inv["buyer"]["pos"] = "27"

    engine_errors = RulesEngine.validate_invoice(inv)
    assert any(e.get("error_code") == 2265 for e in engine_errors)

    val_errors = GSTValidator.validate_invoice(inv)
    assert any(e.get("error_code") == 2265 for e in val_errors)


def test_rule_2266_validator_and_rules_engine(clean_b2b_payload):
    inv = copy.deepcopy(clean_b2b_payload)
    inv["itemdtls"][0]["cesrate"] = 12.0
    inv["itemdtls"][0]["cesval"] = "5000.00"  # Should be 12000.00
    inv["valdtls"]["cesval"] = "5000.00"

    engine_errors = RulesEngine.validate_invoice(inv)
    assert any(e.get("error_code") == 2266 for e in engine_errors)

    val_errors = GSTValidator.validate_invoice(inv)
    assert any(e.get("error_code") == 2266 for e in val_errors)


def test_rule_2267_validator_and_rules_engine(clean_b2b_payload):
    inv = copy.deepcopy(clean_b2b_payload)
    inv["itemdtls"][0]["statecesrate"] = 1.0
    inv["itemdtls"][0]["statecesval"] = "100.00"  # Should be 1000.00
    inv["valdtls"]["stcesval"] = "100.00"

    engine_errors = RulesEngine.validate_invoice(inv)
    assert any(e.get("error_code") == 2267 for e in engine_errors)

    val_errors = GSTValidator.validate_invoice(inv)
    assert any(e.get("error_code") == 2267 for e in val_errors)


def test_rule_2268_validator_and_rules_engine(clean_b2b_payload):
    inv = copy.deepcopy(clean_b2b_payload)
    inv["trancatg"] = "EXPWP"
    inv["igstonintra"] = "Y"
    inv["buyer"]["state"] = "96"
    inv["buyer"]["pos"] = "96"
    inv["buyer"]["gstin"] = "URP"
    inv["buyer"]["pin"] = "999999"

    engine_errors = RulesEngine.validate_invoice(inv)
    assert any(e.get("error_code") == 2268 for e in engine_errors)

    val_errors = GSTValidator.validate_invoice(inv)
    assert any(e.get("error_code") == 2268 for e in val_errors)


def test_rule_2269_validator_and_rules_engine(clean_b2b_payload):
    inv = copy.deepcopy(clean_b2b_payload)
    inv["trancatg"] = "B2B"
    inv["buyer"]["state"] = "96"  # 96 passed for domestic type
    inv["buyer"]["pos"] = "96"

    engine_errors = RulesEngine.validate_invoice(inv)
    assert any(e.get("error_code") == 2269 for e in engine_errors)

    val_errors = GSTValidator.validate_invoice(inv)
    assert any(e.get("error_code") == 2269 for e in val_errors)


# ============================================================================
# 7. PYDANTIC SCHEMA REJECTION TESTS
# ============================================================================

def test_rule_2265_pydantic_schema_rejection(clean_b2b_payload):
    inv = copy.deepcopy(clean_b2b_payload)
    inv["buyer"]["state"] = "27"
    inv["buyer"]["pin"] = "400021"
    with pytest.raises(Exception) as exc_info:
        InvoicePayload.model_validate(inv).validate_cross_model_statutory_rules()
    assert "2265" in str(exc_info.value)


def test_rule_2266_pydantic_schema_rejection(clean_b2b_payload):
    inv = copy.deepcopy(clean_b2b_payload)
    inv["itemdtls"][0]["cesrate"] = 12.0
    inv["itemdtls"][0]["cesval"] = "6000.00"
    with pytest.raises(Exception) as exc_info:
        InvoicePayload.model_validate(inv).validate_cross_model_statutory_rules()
    assert "2266" in str(exc_info.value)


def test_rule_2267_pydantic_schema_rejection(clean_b2b_payload):
    inv = copy.deepcopy(clean_b2b_payload)
    inv["itemdtls"][0]["statecesrate"] = 1.0
    inv["itemdtls"][0]["statecesval"] = "200.00"
    with pytest.raises(Exception) as exc_info:
        InvoicePayload.model_validate(inv).validate_cross_model_statutory_rules()
    assert "2267" in str(exc_info.value)


def test_rule_2268_pydantic_schema_rejection(clean_b2b_payload):
    inv = copy.deepcopy(clean_b2b_payload)
    inv["trancatg"] = "EXPWP"
    inv["igstonintra"] = "Y"
    inv["reversecharge"] = "N"
    inv["buyer"]["state"] = "96"
    inv["buyer"]["pos"] = "96"
    inv["buyer"]["gstin"] = "URP"
    inv["buyer"]["pin"] = "999999"
    with pytest.raises(Exception) as exc_info:
        InvoicePayload.model_validate(inv).validate_cross_model_statutory_rules()
    assert "2268" in str(exc_info.value)


def test_rule_2269_pydantic_schema_rejection(clean_b2b_payload):
    inv = copy.deepcopy(clean_b2b_payload)
    inv["trancatg"] = "B2B"
    inv["buyer"]["state"] = "96"
    inv["buyer"]["pos"] = "29"
    with pytest.raises(Exception) as exc_info:
        InvoicePayload.model_validate(inv).validate_cross_model_statutory_rules()
    assert "2269" in str(exc_info.value)


# ============================================================================
# 8. AUTO-CORRECTION AND AUDIT TRAIL TESTS
# ============================================================================

def test_rule_2265_auto_correct_prefix_mismatch(clean_b2b_payload):
    inv = copy.deepcopy(clean_b2b_payload)
    inv["buyer"]["state"] = "27"  # Mismatch with 29BBBBB0000B1Z2
    payload, logs = InvoicePayload.auto_correct_and_build(inv)
    assert payload.buyer.state == "29"
    assert any("2265" in l.get("category", "") for l in logs)


def test_rule_2266_auto_correct_cess_amount(clean_b2b_payload):
    inv = copy.deepcopy(clean_b2b_payload)
    inv["itemdtls"][0]["cesrate"] = 12.0
    inv["itemdtls"][0]["cesval"] = "5000.00"
    payload, logs = InvoicePayload.auto_correct_and_build(inv)
    assert float(payload.itemdtls[0].cesval) == 12000.0
    assert any("2266" in l.get("category", "") for l in logs)


def test_rule_2267_auto_correct_state_cess_amount(clean_b2b_payload):
    inv = copy.deepcopy(clean_b2b_payload)
    inv["itemdtls"][0]["statecesrate"] = 1.0
    inv["itemdtls"][0]["statecesval"] = "250.00"
    payload, logs = InvoicePayload.auto_correct_and_build(inv)
    assert float(payload.itemdtls[0].statecesval) == 1000.0
    assert any("2267" in l.get("category", "") for l in logs)


def test_rule_2268_auto_correct_invalid_override(clean_b2b_payload):
    inv = copy.deepcopy(clean_b2b_payload)
    inv["trancatg"] = "EXPWP"
    inv["igstonintra"] = "Y"
    inv["buyer"]["state"] = "96"
    inv["buyer"]["pos"] = "96"
    inv["buyer"]["gstin"] = "URP"
    inv["buyer"]["pin"] = "999999"
    payload, logs = InvoicePayload.auto_correct_and_build(inv)
    assert payload.igstonintra == "N"
    assert any("2268" in l.get("category", "") for l in logs)


def test_rule_2269_auto_correct_domestic_type_code_96(clean_b2b_payload):
    inv = copy.deepcopy(clean_b2b_payload)
    inv["trancatg"] = "B2B"
    inv["buyer"]["state"] = "96"
    payload, logs = InvoicePayload.auto_correct_and_build(inv)
    assert payload.buyer.state == "29"
    assert any("2269" in l.get("category", "") for l in logs)


# ============================================================================
# 9. LAKEHOUSE PARQUET ROUNDTRIP TEST
# ============================================================================

def test_lakehouse_roundtrip_rules_2265_to_2269(clean_b2b_payload, tmp_path):
    pq_path = tmp_path / "lakehouse_2265_2269.parquet"

    # Invoice 1: Fix Rule 2265 & 2266
    inv1 = copy.deepcopy(clean_b2b_payload)
    inv1["docno"] = "INV-2026-ROUND-1"
    inv1["buyer"]["state"] = "27"
    inv1["itemdtls"][0]["cesrate"] = 12.0
    inv1["itemdtls"][0]["cesval"] = "5000.00"

    # Invoice 2: Fix Rule 2267 & 2269
    inv2 = copy.deepcopy(clean_b2b_payload)
    inv2["docno"] = "INV-2026-ROUND-2"
    inv2["buyer"]["state"] = "96"
    inv2["itemdtls"][0]["statecesrate"] = 1.0
    inv2["itemdtls"][0]["statecesval"] = "100.00"

    # Invoice 3: Fix Rule 2268
    inv3 = copy.deepcopy(clean_b2b_payload)
    inv3["docno"] = "INV-2026-ROUND-3"
    inv3["trancatg"] = "EXPWP"
    inv3["igstonintra"] = "Y"
    inv3["buyer"]["state"] = "96"
    inv3["buyer"]["pos"] = "96"
    inv3["buyer"]["gstin"] = "URP"
    inv3["buyer"]["pin"] = "999999"

    flat_records = []
    for inv in [inv1, inv2, inv3]:
        payload, logs = InvoicePayload.auto_correct_and_build(inv)
        flat = flatten_invoice_payload(payload)
        for row in flat:
            flat_records.append(row)

    write_parquet(flat_records, str(pq_path))
    assert pq_path.exists()

    df = read_parquet(str(pq_path))
    assert len(df) == 3
    assert "buyer_state" in df.columns
    assert "transaction_category" in df.columns
