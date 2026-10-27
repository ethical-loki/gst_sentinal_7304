"""
Unit and integration tests for Reverse Charge (RevChrg) normalization in the Data Lakehouse module.
Validates all 9 statutory normalization rules:
1. RevChrg: false -> "N" (The schema does not support native JSON booleans. Replace false with "N".)
2. RevChrg: true  -> "Y" (Booleans fail validation. Replace true with "Y".)
3. RevChrg: "NO"  -> "N" (Only single uppercase character flags are allowed. Truncate "NO" to "N".)
4. RevChrg: "YES" -> "Y" (Multi-character strings fail schema length checks. Use "Y" instead of "YES".)
5. RevChrg: "n" / "y" -> "N" / "Y" (The schema is case-sensitive. Always send uppercase "Y" or "N".)
6. RevChrg: 0 / "0"   -> "N" (Numeric flags are not accepted. Map 0 to "N".)
7. RevChrg: 1 / "1"   -> "Y" (Numeric flags are not accepted. Map 1 to "Y".)
8. RevChrg: ""        -> "N" (Empty string fails pattern validation. Provide "N" as the default fallback.)
9. RevChrg: null      -> "N" (Null values are rejected for mandatory indicator fields. Default to "N".)
"""

import sys
from pathlib import Path
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.ingestion.schemas import (
    InvoicePayload,
    normalize_reverse_charge,
    get_reverse_charge_rejection_reason,
)
from src.ingestion.storage import (
    flatten_invoice_payload,
    FLATTENED_INVOICE_SCHEMA,
)
from Template_Converters.payload_builder import PayloadBuilder


@pytest.fixture
def base_invoice_dict():
    """Minimal valid invoice dictionary for testing."""
    return {
        "self_gstin": "29ABCDE1234F1Z5",
        "system_cd": "SAP_ERP",
        "branch_cd": "BLR01",
        "vertical_cd": "DOM",
        "irnreq": "Y",
        "trandt1": {
            "trancatg": "B2B",
            "reversecharge": "N",
            "transactionmode": "REG",
            "igstonintra": "N"
        },
        "docdt1": {
            "document_type": "INV",
            "docno": "INV-REV-001",
            "docdt": "24-10-2026"
        },
        "supplierdt1": {
            "supplier_gstin": "29ABCDE1234F1Z5",
            "supplier_lglnm": "BHARAT ENTERPRISES",
            "supplier_loc": "Bengaluru",
            "supplier_pin": "560001",
            "supplier_state": "29"
        },
        "buyerdt1": {
            "buyer_gstin": "29XYZAB5678C1Z2",
            "buyer_lglnm": "KARNATAKA TRADERS",
            "buyer_loc": "Bengaluru",
            "buyer_pin": "560002",
            "buyer_state": "29",
            "buyer_pos": "29"
        },
        "itemdtls": [
            {
                "slno": "1",
                "prdnm": "Fasteners",
                "hsn": "73181500",
                "qty": 10.0,
                "unit": "NOS",
                "unitprice": 100.0,
                "totamt": 1000.0,
                "assval": 1000.0,
                "gstrate": 18.0,
                "cgstval": 90.0,
                "sgstval": 90.0,
                "igstval": 0.0,
                "totitemval": 1180.0
            }
        ],
        "valdt1": {
            "ttlassval": "1000.00",
            "cgstval": "90.00",
            "sgstval": "90.00",
            "igstval": "0.00",
            "totinvval": "1180.00"
        }
    }


# ============================================================================
# 1. DIRECT FUNCTION UNIT TESTS FOR normalize_reverse_charge
# ============================================================================

def test_normalize_boolean_false():
    val, log = normalize_reverse_charge(False, field_name="RevChrg")
    assert val == "N"
    assert log is not None
    assert log["category"] == "DATA_TYPE_CORRECTION"
    assert log["original"] is False
    assert log["corrected"] == "N"
    assert log["description"] == 'The schema does not support native JSON booleans. Replace false with "N".'


def test_normalize_boolean_true():
    val, log = normalize_reverse_charge(True, field_name="RevChrg")
    assert val == "Y"
    assert log is not None
    assert log["category"] == "DATA_TYPE_CORRECTION"
    assert log["original"] is True
    assert log["corrected"] == "Y"
    assert log["description"] == 'Booleans fail validation. Replace true with "Y".'


def test_normalize_string_no():
    val, log = normalize_reverse_charge("NO", field_name="RevChrg")
    assert val == "N"
    assert log is not None
    assert log["category"] == "FORMAT_NORMALIZATION"
    assert log["original"] == "NO"
    assert log["corrected"] == "N"
    assert log["description"] == 'Only single uppercase character flags are allowed. Truncate "NO" to "N".'


def test_normalize_string_yes():
    val, log = normalize_reverse_charge("YES", field_name="RevChrg")
    assert val == "Y"
    assert log is not None
    assert log["category"] == "FORMAT_NORMALIZATION"
    assert log["original"] == "YES"
    assert log["corrected"] == "Y"
    assert log["description"] == 'Multi-character strings fail schema length checks. Use "Y" instead of "YES".'


def test_normalize_string_lowercase_n():
    val, log = normalize_reverse_charge("n", field_name="RevChrg")
    assert val == "N"
    assert log is not None
    assert log["category"] == "CASE_NORMALIZATION"
    assert log["original"] == "n"
    assert log["corrected"] == "N"
    assert log["description"] == 'The schema is case-sensitive. Always send uppercase "Y" or "N".'


def test_normalize_string_lowercase_y():
    val, log = normalize_reverse_charge("y", field_name="RevChrg")
    assert val == "Y"
    assert log is not None
    assert log["category"] == "CASE_NORMALIZATION"
    assert log["original"] == "y"
    assert log["corrected"] == "Y"
    assert log["description"] == 'The schema is case-sensitive. Always send uppercase "Y" or "N".'


def test_normalize_numeric_zero():
    for zero in (0, "0"):
        val, log = normalize_reverse_charge(zero, field_name="RevChrg")
        assert val == "N"
        assert log is not None
        assert log["category"] == "DATA_TYPE_CORRECTION"
        assert log["original"] == zero
        assert log["corrected"] == "N"
        assert log["description"] == 'Numeric flags are not accepted. Map 0 to "N".'


def test_normalize_numeric_one():
    for one in (1, "1"):
        val, log = normalize_reverse_charge(one, field_name="RevChrg")
        assert val == "Y"
        assert log is not None
        assert log["category"] == "DATA_TYPE_CORRECTION"
        assert log["original"] == one
        assert log["corrected"] == "Y"
        assert log["description"] == 'Numeric flags are not accepted. Map 1 to "Y".'


def test_normalize_empty_string():
    val, log = normalize_reverse_charge("", field_name="RevChrg")
    assert val == "N"
    assert log is not None
    assert log["category"] == "SCHEMA_VALIDATION_FALLBACK"
    assert log["original"] == ""
    assert log["corrected"] == "N"
    assert log["description"] == 'Empty string fails pattern validation. Provide "N" as the default fallback.'


def test_normalize_null():
    val, log = normalize_reverse_charge(None, field_name="RevChrg")
    assert val == "N"
    assert log is not None
    assert log["category"] == "SCHEMA_VALIDATION_FALLBACK"
    assert log["original"] is None
    assert log["corrected"] == "N"
    assert log["description"] == 'Null values are rejected for mandatory indicator fields. Default to "N".'


# ============================================================================
# 2. INGESTION PIPELINE INTEGRATION TESTS (InvoicePayload.auto_correct_and_build)
# ============================================================================

@pytest.mark.parametrize("input_val,expected_flag,expected_reason", [
    (False, "N", 'The schema does not support native JSON booleans. Replace false with "N".'),
    (True,  "Y", 'Booleans fail validation. Replace true with "Y".'),
    ("NO",  "N", 'Only single uppercase character flags are allowed. Truncate "NO" to "N".'),
    ("YES", "Y", 'Multi-character strings fail schema length checks. Use "Y" instead of "YES".'),
    ("n",   "N", 'The schema is case-sensitive. Always send uppercase "Y" or "N".'),
    ("y",   "Y", 'The schema is case-sensitive. Always send uppercase "Y" or "N".'),
    (0,     "N", 'Numeric flags are not accepted. Map 0 to "N".'),
    ("0",   "N", 'Numeric flags are not accepted. Map 0 to "N".'),
    (1,     "Y", 'Numeric flags are not accepted. Map 1 to "Y".'),
    ("1",   "Y", 'Numeric flags are not accepted. Map 1 to "Y".'),
    ("",    "N", 'Empty string fails pattern validation. Provide "N" as the default fallback.'),
    (None,  "N", 'Null values are rejected for mandatory indicator fields. Default to "N".'),
])
def test_invoice_payload_auto_correct_revchrg(base_invoice_dict, input_val, expected_flag, expected_reason):
    dirty = dict(base_invoice_dict)
    dirty["trandt1"] = dict(base_invoice_dict["trandt1"])
    # Put customer RevChrg in trandt1
    dirty["trandt1"]["RevChrg"] = input_val
    del dirty["trandt1"]["reversecharge"]

    model, audit_log = InvoicePayload.auto_correct_and_build(dirty)

    # Verify model fields and alias property
    assert model.reversecharge == expected_flag
    assert model.RevChrg == expected_flag

    # Verify NIC dictionary representation
    nic_dict = model.to_nic_dict()
    assert nic_dict["trandt1"]["reversecharge"] == expected_flag
    assert nic_dict["trandt1"]["RevChrg"] == expected_flag

    # Verify payload representation
    payload_dict = model.to_payload()
    assert payload_dict["RevChrg"] == expected_flag
    assert payload_dict["trandt1"]["RevChrg"] == expected_flag

    # Verify audit log contains expected reason
    matching_logs = [log for log in audit_log if expected_reason in log.get("description", "")]
    assert len(matching_logs) >= 1, f"Expected reason '{expected_reason}' not found in audit_log: {audit_log}"


def test_invoice_payload_root_level_revchrg(base_invoice_dict):
    """Verifies that RevChrg supplied at root level is also captured and normalized."""
    dirty = dict(base_invoice_dict)
    dirty["RevChrg"] = False
    if "trandt1" in dirty and "reversecharge" in dirty["trandt1"]:
        del dirty["trandt1"]["reversecharge"]

    model, audit_log = InvoicePayload.auto_correct_and_build(dirty)
    assert model.reversecharge == "N"
    assert model.RevChrg == "N"
    assert any("The schema does not support native JSON booleans" in l.get("description", "") for l in audit_log)


# ============================================================================
# 3. TEMPLATE CONVERTERS INTEGRATION TESTS (PayloadBuilder.auto_correct_and_build)
# ============================================================================

@pytest.mark.parametrize("input_val,expected_flag", [
    (False, "N"),
    (True,  "Y"),
    ("NO",  "N"),
    ("YES", "Y"),
    ("n",   "N"),
    ("y",   "Y"),
    (0,     "N"),
    ("0",   "N"),
    (1,     "Y"),
    ("1",   "Y"),
    ("",    "N"),
    (None,  "N"),
])
def test_payload_builder_revchrg_normalization(base_invoice_dict, input_val, expected_flag):
    dirty = dict(base_invoice_dict)
    dirty["trandt1"] = dict(base_invoice_dict["trandt1"])
    dirty["trandt1"]["RevChrg"] = input_val
    del dirty["trandt1"]["reversecharge"]

    clean_inv, audit_log = PayloadBuilder.auto_correct_and_build(dirty)
    assert clean_inv["trandt1"]["reversecharge"] == expected_flag
    assert clean_inv["trandt1"]["RevChrg"] == expected_flag
    assert clean_inv["reversecharge"] == expected_flag
    assert clean_inv["RevChrg"] == expected_flag


# ============================================================================
# 4. DATA LAKEHOUSE COLUMNAR PARQUET FLATTENING TEST
# ============================================================================

@pytest.mark.parametrize("input_val,expected_flag", [
    (False, "N"),
    (True,  "Y"),
    ("NO",  "N"),
    ("YES", "Y"),
    (0,     "N"),
    (1,     "Y"),
    ("",    "N"),
    (None,  "N"),
])
def test_data_lakehouse_parquet_flattening_revchrg(base_invoice_dict, input_val, expected_flag):
    payload = dict(base_invoice_dict)
    payload["trandt1"] = dict(base_invoice_dict["trandt1"])
    payload["trandt1"]["RevChrg"] = input_val
    del payload["trandt1"]["reversecharge"]

    rows = flatten_invoice_payload(payload)
    assert len(rows) > 0
    for row in rows:
        assert row["reverse_charge"] == expected_flag, f"Row reverse_charge {row['reverse_charge']} != {expected_flag}"


# ============================================================================
# 5. SUPPLY TYPE (SupTyp) VS REVERSE CHARGE (RevChrg) STATUTORY RULES
# ============================================================================

SUPPLY_TYPE_RULE_CASES = [
    # (SupTyp, initial_rev, expected_rev, expected_reason_substring, wthpay)
    ("SEZWP",  "Y", "N", 'SEZ supplies cannot have Reverse Charge. Set RevChrg to "N".', None),
    ("SEZWOP", "Y", "N", 'SEZ supplies cannot have Reverse Charge. Set RevChrg to "N".', None),
    ("EXPWP",  "Y", "N", 'Exports cannot be subject to Reverse Charge. Set RevChrg to "N".', "Y"),
    ("EXPWOP", "Y", "N", 'Exports under LUT/bond cannot have RCM. Set RevChrg to "N".', "N"),
    ("DEXP",   "Y", "N", 'Deemed exports do not permit recipient RCM on IRP. Set RevChrg to "N".', None),
    ("B2B",    "Y", "Y", 'If this is genuinely an RCM supply, ensure SupTyp is set to "B2B" rather than an export or SEZ type.', None),
]


@pytest.mark.parametrize("suptyp,sent_rev,expected_rev,expected_reason,wthpay", SUPPLY_TYPE_RULE_CASES)
def test_direct_get_reverse_charge_rejection_reason(suptyp, sent_rev, expected_rev, expected_reason, wthpay):
    """Verifies that get_reverse_charge_rejection_reason returns the exact statutory message."""
    reason = get_reverse_charge_rejection_reason(suptyp, wthpay=wthpay)
    assert reason == expected_reason


@pytest.mark.parametrize("suptyp,sent_rev,expected_rev,expected_reason,wthpay", SUPPLY_TYPE_RULE_CASES)
def test_invoice_payload_suptyp_revchrg_auto_correction(base_invoice_dict, suptyp, sent_rev, expected_rev, expected_reason, wthpay):
    """Verifies that InvoicePayload.auto_correct_and_build auto-corrects non-B2B RCM supplies to 'N' and preserves B2B."""
    dirty = dict(base_invoice_dict)
    dirty["trandt1"] = dict(base_invoice_dict["trandt1"])
    dirty["trandt1"]["trancatg"] = suptyp
    dirty["trandt1"]["RevChrg"] = sent_rev
    dirty["trandt1"]["reversecharge"] = sent_rev
    if wthpay:
        dirty["expdt1"] = {"wthpay": wthpay}

    model, audit_log = InvoicePayload.auto_correct_and_build(dirty)
    assert model.reversecharge == expected_rev
    assert model.RevChrg == expected_rev
    if isinstance(model.trandt1, dict):
        assert model.trandt1.get("reversecharge") == expected_rev
        assert model.trandt1.get("RevChrg") == expected_rev

    if suptyp != "B2B":
        found = any(expected_reason in l.get("description", "") for l in audit_log)
        assert found, f"Expected reason '{expected_reason}' not found in audit_log: {audit_log}"
    else:
        # For B2B, no auto-correction to 'N' should occur
        assert not any(l.get("field") == "trandt1.reversecharge" and l.get("corrected") == "N" for l in audit_log)


@pytest.mark.parametrize("suptyp,sent_rev,expected_rev,expected_reason,wthpay", SUPPLY_TYPE_RULE_CASES)
def test_payload_builder_suptyp_revchrg_auto_correction(base_invoice_dict, suptyp, sent_rev, expected_rev, expected_reason, wthpay):
    """Verifies that PayloadBuilder.auto_correct_and_build enforces Rule 2162 across supply types."""
    dirty = dict(base_invoice_dict)
    dirty["trandt1"] = dict(base_invoice_dict["trandt1"])
    dirty["trandt1"]["trancatg"] = suptyp
    dirty["trandt1"]["RevChrg"] = sent_rev
    dirty["trandt1"]["reversecharge"] = sent_rev
    if wthpay:
        dirty["expdt1"] = {"wthpay": wthpay}

    clean_inv, audit_log = PayloadBuilder.auto_correct_and_build(dirty)
    assert clean_inv["trandt1"]["reversecharge"] == expected_rev
    assert clean_inv["trandt1"]["RevChrg"] == expected_rev
    assert clean_inv["reversecharge"] == expected_rev
    assert clean_inv["RevChrg"] == expected_rev

    if suptyp != "B2B":
        found = any(expected_reason in l.get("description", "") for l in audit_log)
        assert found, f"Expected reason '{expected_reason}' not found in audit_log: {audit_log}"


def test_validator_rule_2162_rejection():
    """Verifies that validator and rules engine report Rule 2162 with exact statutory messages."""
    from Template_Converters.validator import GSTValidator
    from src.rules.rules_engine import RulesEngine

    for suptyp, sent_rev, _, expected_reason, wthpay in SUPPLY_TYPE_RULE_CASES:
        if suptyp == "B2B":
            continue
        inv = {
            "trandt1": {
                "trancatg": suptyp,
                "reversecharge": "Y",
                "RevChrg": "Y"
            },
            "expdt1": {"wthpay": wthpay} if wthpay else {}
        }
        val_errors = GSTValidator.validate_invoice(inv)
        r2162_errs = [e for e in val_errors if e.get("error_code") == 2162]
        assert len(r2162_errs) > 0, f"Validator did not flag Rule 2162 for {suptyp}"
        assert expected_reason in r2162_errs[0]["message"]

        rules_engine = RulesEngine()
        re_errors = rules_engine.validate_invoice(inv)
        re_2162_errs = [e for e in re_errors if e.get("error_code") == 2162]
        assert len(re_2162_errs) > 0, f"RulesEngine did not flag Rule 2162 for {suptyp}"
        assert expected_reason in re_2162_errs[0]["message"]
