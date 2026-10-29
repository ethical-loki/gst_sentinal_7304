"""
Statutory Test Suite: Rules 2270, 2271, 2272 & Lakehouse Parquet Persistence.
Covers:
- Rule 2270: The Allowed Cancellation Time Limit is Crossed, You Cannot Cancel the IRN (>24 hours)
- Rule 2271: SHIP TO - State Code is Not Valid State Code for B2B, SEZ and Deemed Export Transactions
- Rule 2272: SHIP TO - PIN Code Cannot Be 999999 for B2B, SEZ and Deemed Export Transactions
- Pre-API validation, Pydantic schema validation, auto-correction, and Lakehouse Parquet storage.
"""

import copy
import pytest
from datetime import datetime, timedelta
from typing import Dict, Any

from src.ingestion.schemas import (
    classify_rule_2270_diagnostic,
    classify_rule_2271_diagnostic,
    classify_rule_2272_diagnostic,
    InvoicePayload,
    NICValidationError,
)
from src.rules.rules_engine import RulesEngine
from Template_Converters.validator import GSTValidator
from src.ingestion.storage import write_parquet, read_parquet, flatten_invoice_payload


@pytest.fixture
def clean_b2b_with_shipping() -> Dict[str, Any]:
    return {
        "self_gstin": "27AAAAA0000A1Z5",
        "docno": "INV-2026-SHP01",
        "docdt": "2026-10-25",
        "document_type": "INV",
        "trancatg": "B2B",
        "transactionmode": "SHP",
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
        "shipdtl": {
            "legal_name": "Karnataka Warehouse Logistics",
            "gstin": "29BBBBB0000B1Z2",
            "state": "29",
            "address1": "Electronic City",
            "loc": "Bengaluru",
            "pin": "560100"
        },
        "itemdtls": [
            {
                "slno": "1",
                "prdnm": "Precision Industrial Gearbox",
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
                "cesrate": 0.0,
                "cesval": "0.00",
                "cesnonadvl": "0.00",
                "statecesrate": 0.0,
                "statecesval": "0.00",
                "statecesnonadvl": "0.00",
                "othchrg": "0.00",
                "totitemval": "118000.00"
            }
        ],
        "valdtls": {
            "assval": "100000.00",
            "cgstval": "0.00",
            "sgstval": "0.00",
            "igstval": "18000.00",
            "cesval": "0.00",
            "stcesval": "0.00",
            "discount": "0.00",
            "othchrg": "0.00",
            "rndoffamt": "0.00",
            "totinvval": "118000.00"
        }
    }


# ============================================================================
# 1. DIAGNOSTIC TESTS FOR RULE 2270 (CANCELLATION TIME LIMIT)
# ============================================================================

def test_rule_2270_diagnostic_past_24_hours():
    gen_time = (datetime.now() - timedelta(hours=26)).strftime("%Y-%m-%d %H:%M:%S")
    diag = classify_rule_2270_diagnostic(
        generation_time=gen_time,
        irn="1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
    )
    assert not diag["is_valid"]
    assert diag["error_code"] == 2270
    assert diag["scenario"] == "PAST_24_HOURS"
    assert diag["action"] == "ISSUE_CREDIT_NOTE"
    assert "Credit Note" in diag["resolution"]


def test_rule_2270_diagnostic_within_24_hours():
    gen_time = (datetime.now() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    diag = classify_rule_2270_diagnostic(
        generation_time=gen_time,
        irn="1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
    )
    assert diag["is_valid"]
    assert diag["error_code"] is None
    assert diag["action"] == "PROCEED_WITH_CANCELLATION"


def test_rule_2270_rules_engine_cancellation():
    past_req = {
        "irn": "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        "cnl_rsn": "1",
        "cnl_rem": "Duplicate IRN entry by ERP batch",
        "hours_since_generation": 28.5
    }
    errors = RulesEngine.validate_irn_cancellation(past_req)
    assert any(e.get("code") == 2270 or e.get("error_code") == 2270 for e in errors)


def test_rule_2270_schema_cancellation_rejection():
    gen_time = (datetime.now() - timedelta(hours=30)).strftime("%Y-%m-%d %H:%M:%S")
    with pytest.raises(NICValidationError) as exc_info:
        InvoicePayload.validate_cancellation(
            generation_time=gen_time,
            irn="1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
        )
    assert exc_info.value.code == 2270
    assert "2270" in str(exc_info.value)


# ============================================================================
# 2. DIAGNOSTIC TESTS FOR RULE 2271 (SHIP-TO STATE CODE)
# ============================================================================

def test_rule_2271_diagnostic_export_country_code_in_domestic():
    diag = classify_rule_2271_diagnostic(
        ship_state="96",
        trancatg="B2B",
        ship_gstin="29BBBBB0000B1Z2",
        buyer_state="29"
    )
    assert not diag["is_valid"]
    assert diag["error_code"] == 2271
    assert diag["scenario"] == "EXPORT_COUNTRY_CODE_IN_DOMESTIC"
    assert diag["rectified_state"] == "29"


def test_rule_2271_diagnostic_alpha_code_used():
    diag = classify_rule_2271_diagnostic(
        ship_state="KA",
        trancatg="B2B"
    )
    assert not diag["is_valid"]
    assert diag["error_code"] == 2271
    assert diag["scenario"] == "ALPHA_CODE_USED"
    assert diag["rectified_state"] == "29"


def test_rule_2271_diagnostic_numeric_type_passed():
    diag = classify_rule_2271_diagnostic(
        ship_state=27,
        trancatg="B2B"
    )
    assert not diag["is_valid"]
    assert diag["error_code"] == 2271
    assert diag["scenario"] == "NUMERIC_TYPE_PASSED"
    assert diag["rectified_state"] == "27"


def test_rule_2271_diagnostic_leading_zero_omitted():
    diag = classify_rule_2271_diagnostic(
        ship_state="7",
        trancatg="B2B"
    )
    assert not diag["is_valid"]
    assert diag["error_code"] == 2271
    assert diag["scenario"] == "LEADING_ZERO_OMITTED"
    assert diag["rectified_state"] == "07"


def test_rule_2271_diagnostic_state_code_disagrees_with_gstin():
    diag = classify_rule_2271_diagnostic(
        ship_state="27",
        trancatg="B2B",
        ship_gstin="29BBBBB0000B1Z2"
    )
    assert not diag["is_valid"]
    assert diag["error_code"] == 2271
    assert diag["scenario"] == "STATE_CODE_DISAGREES_WITH_GSTIN"
    assert diag["rectified_state"] == "29"


def test_rule_2271_diagnostic_clean_pass():
    diag = classify_rule_2271_diagnostic(
        ship_state="29",
        trancatg="B2B",
        ship_gstin="29BBBBB0000B1Z2"
    )
    assert diag["is_valid"]
    assert diag["error_code"] is None
    assert diag["rectified_state"] == "29"


def test_rule_2271_diagnostic_export_permits_96():
    diag = classify_rule_2271_diagnostic(
        ship_state="96",
        trancatg="EXPWP"
    )
    assert diag["is_valid"]
    assert diag["error_code"] is None


# ============================================================================
# 3. DIAGNOSTIC TESTS FOR RULE 2272 (SHIP-TO PIN CODE)
# ============================================================================

def test_rule_2272_diagnostic_dummy_pin_domestic():
    diag = classify_rule_2272_diagnostic(
        ship_pin=999999,
        trancatg="B2B",
        buyer_pin="560001",
        ship_state="29"
    )
    assert not diag["is_valid"]
    assert diag["error_code"] == 2272
    assert diag["scenario"] == "REDUNDANT_SHIP_TO_WITH_DUMMY"
    assert diag["rectified_pin"] == 560001


def test_rule_2272_diagnostic_sez_dummy_pin():
    diag = classify_rule_2272_diagnostic(
        ship_pin="999999",
        trancatg="SEZWP",
        ship_state="24"
    )
    assert not diag["is_valid"]
    assert diag["error_code"] == 2272
    assert diag["scenario"] == "SEZ_CAMPUS_DELIVERY_DUMMY_PIN"
    assert diag["rectified_pin"] != 999999


def test_rule_2272_diagnostic_string_data_type():
    diag = classify_rule_2272_diagnostic(
        ship_pin="411001",
        trancatg="B2B"
    )
    assert not diag["is_valid"]
    assert diag["error_code"] == 2272
    assert diag["scenario"] == "STRING_DATA_TYPE_PASSED"
    assert diag["rectified_pin"] == 411001


def test_rule_2272_diagnostic_clean_pass():
    diag = classify_rule_2272_diagnostic(
        ship_pin=411001,
        trancatg="B2B"
    )
    assert diag["is_valid"]
    assert diag["error_code"] is None


def test_rule_2272_diagnostic_export_permits_dummy():
    diag = classify_rule_2272_diagnostic(
        ship_pin=999999,
        trancatg="EXPWP"
    )
    assert diag["is_valid"]
    assert diag["error_code"] is None


# ============================================================================
# 4. VALIDATOR & RULES ENGINE TESTS
# ============================================================================

def test_rule_2271_validator_and_rules_engine(clean_b2b_with_shipping):
    inv = copy.deepcopy(clean_b2b_with_shipping)
    inv["shipdtl"]["state"] = "96"  # Invalid code 96 for domestic

    engine_errors = RulesEngine.validate_invoice(inv)
    assert any(e.get("code") == 2271 or e.get("error_code") == 2271 for e in engine_errors)

    val_errors = GSTValidator.validate_invoice(inv)
    assert any(e.get("code") == 2271 or e.get("error_code") == 2271 for e in val_errors)


def test_rule_2272_validator_and_rules_engine(clean_b2b_with_shipping):
    inv = copy.deepcopy(clean_b2b_with_shipping)
    inv["shipdtl"]["pin"] = "999999"  # Dummy PIN forbidden for domestic

    engine_errors = RulesEngine.validate_invoice(inv)
    assert any(e.get("code") == 2272 or e.get("error_code") == 2272 for e in engine_errors)

    val_errors = GSTValidator.validate_invoice(inv)
    assert any(e.get("code") == 2272 or e.get("error_code") == 2272 for e in val_errors)


# ============================================================================
# 5. PYDANTIC SCHEMA REJECTION TESTS
# ============================================================================

def test_rule_2271_pydantic_schema_rejection(clean_b2b_with_shipping):
    inv = copy.deepcopy(clean_b2b_with_shipping)
    inv["shipdtl"]["state"] = "96"
    with pytest.raises(Exception) as exc_info:
        InvoicePayload.model_validate(inv).validate_cross_model_statutory_rules()
    assert "2271" in str(exc_info.value)


def test_rule_2272_pydantic_schema_rejection(clean_b2b_with_shipping):
    inv = copy.deepcopy(clean_b2b_with_shipping)
    inv["shipdtl"]["pin"] = "999999"
    with pytest.raises(Exception) as exc_info:
        InvoicePayload.model_validate(inv).validate_cross_model_statutory_rules()
    assert "2272" in str(exc_info.value)


# ============================================================================
# 6. AUTO-CORRECTION AND AUDIT TRAIL TESTS
# ============================================================================

def test_rule_2271_auto_correct_export_code_to_delivery_state(clean_b2b_with_shipping):
    inv = copy.deepcopy(clean_b2b_with_shipping)
    inv["shipdtl"]["state"] = "96"  # Foreign code passed on domestic delivery
    payload, logs = InvoicePayload.auto_correct_and_build(inv)
    assert payload.shipdtl.state == "29"
    assert any("2271" in l.get("category", "") for l in logs)


def test_rule_2271_auto_correct_alpha_to_numeric(clean_b2b_with_shipping):
    inv = copy.deepcopy(clean_b2b_with_shipping)
    inv["shipdtl"]["state"] = "KA"
    payload, logs = InvoicePayload.auto_correct_and_build(inv)
    assert payload.shipdtl.state == "29"
    assert any("2271" in l.get("category", "") for l in logs)


def test_rule_2271_auto_correct_gstin_mismatch(clean_b2b_with_shipping):
    inv = copy.deepcopy(clean_b2b_with_shipping)
    inv["shipdtl"]["gstin"] = "29BBBBB0000B1Z2"
    inv["shipdtl"]["state"] = "27"  # Mismatch with 29
    payload, logs = InvoicePayload.auto_correct_and_build(inv)
    assert payload.shipdtl.state == "29"
    assert any("2271" in l.get("category", "") or "2200" in l.get("category", "") for l in logs)


def test_rule_2272_auto_correct_dummy_pin_to_buyer_pin(clean_b2b_with_shipping):
    inv = copy.deepcopy(clean_b2b_with_shipping)
    inv["shipdtl"]["pin"] = "999999"
    payload, logs = InvoicePayload.auto_correct_and_build(inv)
    assert payload.shipdtl.pin == "560001"
    assert any("2272" in l.get("category", "") for l in logs)


def test_rule_2272_auto_correct_sez_dummy_pin(clean_b2b_with_shipping):
    inv = copy.deepcopy(clean_b2b_with_shipping)
    inv["trancatg"] = "SEZWP"
    inv["buyer"]["state"] = "24"
    inv["buyer"]["pos"] = "24"
    inv["buyer"]["pin"] = "382115"
    inv["shipdtl"]["state"] = "24"
    inv["shipdtl"]["pin"] = "999999"
    payload, logs = InvoicePayload.auto_correct_and_build(inv)
    assert payload.shipdtl.pin == "382115"
    assert any("2272" in l.get("category", "") for l in logs)


# ============================================================================
# 7. LAKEHOUSE PARQUET ROUNDTRIP TEST
# ============================================================================

def test_lakehouse_roundtrip_rules_2270_to_2272(clean_b2b_with_shipping, tmp_path):
    pq_path = tmp_path / "lakehouse_2270_2272.parquet"

    # Invoice 1: Fix Rule 2271 (Export code 96 -> 29)
    inv1 = copy.deepcopy(clean_b2b_with_shipping)
    inv1["docno"] = "INV-2026-ROUND-1"
    inv1["shipdtl"]["state"] = "96"

    # Invoice 2: Fix Rule 2272 (Dummy 999999 -> 560001)
    inv2 = copy.deepcopy(clean_b2b_with_shipping)
    inv2["docno"] = "INV-2026-ROUND-2"
    inv2["shipdtl"]["pin"] = "999999"

    # Invoice 3: Clean pass with shipping
    inv3 = copy.deepcopy(clean_b2b_with_shipping)
    inv3["docno"] = "INV-2026-ROUND-3"

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
    assert "ship_state" in df.columns or "buyer_state" in df.columns
    assert "transaction_category" in df.columns
