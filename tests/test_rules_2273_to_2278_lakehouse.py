"""
Statutory Test Suite: Rules 2273 to 2278 & Lakehouse Parquet Persistence.
Covers:
- Rule 2273: Dispatch from PIN code cannot be 999999
- Rule 2274: Recipient PIN code cannot be 999999 for domestic transaction
- Rule 2275: Recipient PIN code should be 999999 for Direct Export
- Rule 2276: Supplier PIN code cannot be 999999
- Rule 2278: Document number cannot be reused after IRN cancellation
- Pre-API validation, Pydantic schema cross-validation, auto-correction pipelines, and Lakehouse Parquet storage.
"""

import copy
import os
import pytest
from datetime import datetime
from typing import Dict, Any

from src.ingestion.schemas import (
    classify_rule_2273_diagnostic,
    classify_rule_2274_diagnostic,
    classify_rule_2275_diagnostic,
    classify_rule_2276_diagnostic,
    classify_rule_2278_diagnostic,
    InvoicePayload,
    NICValidationError,
)
from src.rules.rules_engine import RulesEngine
from Template_Converters.validator import GSTValidator
from src.ingestion.storage import write_parquet, read_parquet, flatten_invoice_payload


def _get_err_code(e: Any) -> Any:
    if isinstance(e, dict):
        return e.get("code") or e.get("error_code")
    return getattr(e, "code", None) or getattr(e, "error_code", None)


@pytest.fixture
def clean_b2b_fixture() -> Dict[str, Any]:
    return {
        "self_gstin": "27AAAAA0000A1Z5",
        "docno": "INV-2026-001",
        "docdt": "2026-10-25",
        "document_type": "INV",
        "trancatg": "B2B",
        "transactionmode": "REG",
        "igstonintra": "N",
        "reversecharge": "N",
        "supplier": {
            "legal_name": "Maharashtra Supplier Ltd",
            "gstin": "27AAAAA0000A1Z5",
            "state": "27",
            "address1": "Nariman Point",
            "loc": "Mumbai",
            "pin": "400001"
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
        "dispdt1": {
            "legal_name": "Dispatch Hub Mumbai",
            "address1": "Andheri East",
            "loc": "Mumbai",
            "state": "27",
            "pin": "400069"
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
            "discount": "0.00",
            "othchrg": "0.00",
            "rndoffamt": "0.00",
            "totinvval": "118000.00"
        }
    }


# ============================================================================
# 1. UNIT TESTS: DIAGNOSTIC CLASSIFIERS
# ============================================================================

def test_rule_2273_diagnostic_dummy_pin_domestic():
    """Rule 2273: Dummy PIN 999999 on domestic dispatch point."""
    res = classify_rule_2273_diagnostic(
        disp_pin=999999,
        trancatg="B2B",
        seller_pin=400705,
        disp_state="27"
    )
    assert res["is_valid"] is False
    assert res["error_code"] == 2273
    assert res["scenario"] == "DUMMY_PIN_ON_DISPATCH_POINT"
    assert res["rectified_pin"] == 400705


def test_rule_2273_diagnostic_export_transaction_dispatch_dummy():
    """Rule 2273: Dummy PIN 999999 erroneously passed on export dispatch point."""
    res = classify_rule_2273_diagnostic(
        disp_pin="999999",
        trancatg="EXPWP",
        seller_pin=400705,
        disp_state="27"
    )
    assert res["is_valid"] is False
    assert res["error_code"] == 2273
    assert res["scenario"] == "EXPORT_TRANSACTION_DISPATCH_DUMMY"
    assert res["rectified_pin"] == 400705


def test_rule_2273_diagnostic_string_data_type():
    """Rule 2273: Valid 6-digit PIN passed as string instead of integer."""
    res = classify_rule_2273_diagnostic(
        disp_pin="400705",
        trancatg="B2B"
    )
    assert res["is_valid"] is False
    assert res["error_code"] == 2273
    assert res["scenario"] == "STRING_DATA_TYPE_PASSED"
    assert res["rectified_pin"] == 400705


def test_rule_2273_diagnostic_clean_pass():
    """Rule 2273: Clean authentic dispatch PIN."""
    res = classify_rule_2273_diagnostic(
        disp_pin=400705,
        trancatg="B2B"
    )
    assert res["is_valid"] is True
    assert res["error_code"] is None
    assert res["scenario"] == "VALID"


def test_rule_2274_diagnostic_overseas_pin_domestic():
    """Rule 2274: Dummy PIN 999999 passed on domestic B2B buyer."""
    res = classify_rule_2274_diagnostic(
        buyer_pin=999999,
        trancatg="B2B",
        buyer_state="29",
        buyer_gstin="29BBBBB0000B1Z2"
    )
    assert res["is_valid"] is False
    assert res["error_code"] == 2274
    assert res["scenario"] == "OVERSEAS_PIN_ON_DOMESTIC_BUYER"
    assert res["rectified_pin"] == 560001


def test_rule_2274_diagnostic_sez_buyer_dummy_pin():
    """Rule 2274: Dummy PIN 999999 passed on SEZ buyer."""
    res = classify_rule_2274_diagnostic(
        buyer_pin="999999",
        trancatg="SEZWP",
        buyer_state="27",
        buyer_gstin="27AAACS1234A1Z5"
    )
    assert res["is_valid"] is False
    assert res["error_code"] == 2274
    assert res["scenario"] == "SEZ_BUYER_PASSED_WITH_DUMMY_PIN"
    assert res["rectified_pin"] == 400001


def test_rule_2274_diagnostic_string_data_type():
    """Rule 2274: Valid 6-digit domestic PIN passed as string."""
    res = classify_rule_2274_diagnostic(
        buyer_pin="560001",
        trancatg="B2B"
    )
    assert res["is_valid"] is False
    assert res["error_code"] == 2274
    assert res["scenario"] == "STRING_DATA_TYPE_PASSED"
    assert res["rectified_pin"] == 560001


def test_rule_2274_diagnostic_clean_pass():
    """Rule 2274: Clean authentic domestic buyer PIN."""
    res = classify_rule_2274_diagnostic(
        buyer_pin=560001,
        trancatg="B2B"
    )
    assert res["is_valid"] is True
    assert res["error_code"] is None


def test_rule_2275_diagnostic_domestic_pin_on_export():
    """Rule 2275: Domestic PIN passed on direct cross-border export."""
    res = classify_rule_2275_diagnostic(
        buyer_pin=400601,
        trancatg="EXPWP",
        buyer_state="96"
    )
    assert res["is_valid"] is False
    assert res["error_code"] == 2275
    assert res["scenario"] == "DOMESTIC_PIN_ON_EXPORT_BUYER"
    assert res["rectified_pin"] == 999999


def test_rule_2275_diagnostic_foreign_zip_passed():
    """Rule 2275: Foreign postal code 94105 passed directly into Pin field."""
    res = classify_rule_2275_diagnostic(
        buyer_pin="94105",
        trancatg="EXPWOP",
        buyer_state="96"
    )
    assert res["is_valid"] is False
    assert res["error_code"] == 2275
    assert res["scenario"] == "FOREIGN_ZIP_PASSED_DIRECTLY"
    assert res["rectified_pin"] == 999999


def test_rule_2275_diagnostic_clean_pass():
    """Rule 2275: Clean direct export recipient PIN."""
    res = classify_rule_2275_diagnostic(
        buyer_pin=999999,
        trancatg="EXPWP",
        buyer_state="96"
    )
    assert res["is_valid"] is True
    assert res["error_code"] is None


def test_rule_2276_diagnostic_dummy_pin_registered_supplier():
    """Rule 2276: Dummy PIN 999999 on registered domestic supplier."""
    res = classify_rule_2276_diagnostic(
        seller_pin=999999,
        trancatg="B2B",
        seller_state="27",
        seller_gstin="27AAAAA0000A1Z5"
    )
    assert res["is_valid"] is False
    assert res["error_code"] == 2276
    assert res["scenario"] == "DUMMY_PIN_ON_REGISTERED_SUPPLIER"
    assert res["rectified_pin"] == 400001


def test_rule_2276_diagnostic_export_supplier_dummy():
    """Rule 2276: Dummy PIN on export supplier."""
    res = classify_rule_2276_diagnostic(
        seller_pin="999999",
        trancatg="EXPWP",
        seller_state="27",
        seller_gstin="27AAAAA0000A1Z5"
    )
    assert res["is_valid"] is False
    assert res["error_code"] == 2276
    assert res["scenario"] == "EXPORT_TRANSACTION_SUPPLIER_DUMMY"
    assert res["rectified_pin"] == 400001


def test_rule_2276_diagnostic_clean_pass():
    """Rule 2276: Clean authentic supplier PIN."""
    res = classify_rule_2276_diagnostic(
        seller_pin=400601,
        trancatg="B2B",
        seller_state="27"
    )
    assert res["is_valid"] is True
    assert res["error_code"] is None


def test_rule_2278_diagnostic_cancelled_document_reuse():
    """Rule 2278: Attempting to generate an IRN with a previously cancelled docno."""
    res = classify_rule_2278_diagnostic(
        docno="INV/2026/001",
        doc_type="INV",
        is_cancelled_reuse=True,
        cancelled_doc_registry={"INV/2026/001"}
    )
    assert res["is_valid"] is False
    assert res["error_code"] == 2278
    assert res["scenario"] == "REUSING_CANCELLED_DOCUMENT_NUMBER"
    assert res["rectified_docno"] == "INV/2026/001-A"


def test_rule_2278_diagnostic_clean_pass():
    """Rule 2278: Fresh unique document number."""
    res = classify_rule_2278_diagnostic(
        docno="INV/2026/999",
        doc_type="INV",
        is_cancelled_reuse=False,
        cancelled_doc_registry={"INV/2026/001"}
    )
    assert res["is_valid"] is True
    assert res["error_code"] is None


# ============================================================================
# 2. VALIDATOR & RULES ENGINE TESTS
# ============================================================================

def test_rule_2273_validator_and_rules_engine():
    """Rule 2273: Verify dispatch pin 999999 caught by engine and validator."""
    engine = RulesEngine()
    validator = GSTValidator()

    payload = {
        "docdt1": {"docno": "INV/2026/010", "docdt": "01/01/2026", "document_type": "INV"},
        "trandt1": {"trancatg": "B2B"},
        "transactionmode": "REG",
        "supplierdt1": {"supplier_gstin": "27AAAAA0000A1Z5", "supplier_state": "27", "supplier_pin": "400001", "supplier_lglnm": "ABC Corp", "supplier_bnm": "ABC", "supplier_loc": "Mumbai"},
        "buyerdt1": {"buyer_gstin": "27BBBBB0000B1Z2", "buyer_state": "27", "buyer_pin": "400001", "buyer_pos": "27", "buyer_lglnm": "XYZ Corp", "buyer_bnm": "XYZ", "buyer_loc": "Mumbai"},
        "dispdt1": {"disp_pin": "999999", "disp_state": "27", "disp_nm": "Warehouse 1", "disp_bno": "10", "disp_bnm": "WH", "disp_loc": "Mumbai"},
        "itemdtls": [{"itemno": 1, "hsncd": "84713010", "is_service": "N", "qty": 1, "unitprice": 1000, "totamt": 1000, "assamt": 1000, "gstrt": 18, "cgstamt": 90, "sgstamt": 90, "totitemval": 1180}],
        "valdt1": {"assval": 1000, "cgstval": 90, "sgstval": 90, "totinvval": 1180}
    }

    errs_eng = engine.validate_invoice(payload)
    errs_val = validator.validate_invoice(payload)

    assert any(_get_err_code(e) == 2273 for e in errs_eng)
    assert any(_get_err_code(e) == 2273 for e in errs_val)


def test_rule_2274_validator_and_rules_engine():
    """Rule 2274: Domestic buyer pin 999999 caught by engine and validator."""
    engine = RulesEngine()
    validator = GSTValidator()

    payload = {
        "docdt1": {"docno": "INV/2026/011", "docdt": "01/01/2026", "document_type": "INV"},
        "trandt1": {"trancatg": "B2B"},
        "supplierdt1": {"supplier_gstin": "27AAAAA0000A1Z5", "supplier_state": "27", "supplier_pin": "400001", "supplier_lglnm": "ABC Corp", "supplier_bnm": "ABC", "supplier_loc": "Mumbai"},
        "buyerdt1": {"buyer_gstin": "27BBBBB0000B1Z2", "buyer_state": "27", "buyer_pin": "999999", "buyer_pos": "27", "buyer_lglnm": "XYZ Corp", "buyer_bnm": "XYZ", "buyer_loc": "Mumbai"},
        "itemdtls": [{"itemno": 1, "hsncd": "84713010", "is_service": "N", "qty": 1, "unitprice": 1000, "totamt": 1000, "assamt": 1000, "gstrt": 18, "cgstamt": 90, "sgstamt": 90, "totitemval": 1180}],
        "valdt1": {"assval": 1000, "cgstval": 90, "sgstval": 90, "totinvval": 1180}
    }

    errs_eng = engine.validate_invoice(payload)
    errs_val = validator.validate_invoice(payload)

    assert any(_get_err_code(e) == 2274 for e in errs_eng)
    assert any(_get_err_code(e) == 2274 for e in errs_val)


def test_rule_2275_validator_and_rules_engine():
    """Rule 2275: Export buyer pin not 999999 caught by engine and validator."""
    engine = RulesEngine()
    validator = GSTValidator()

    payload = {
        "docdt1": {"docno": "INV/2026/012", "docdt": "01/01/2026", "document_type": "INV"},
        "trandt1": {"trancatg": "EXPWP"},
        "supplierdt1": {"supplier_gstin": "27AAAAA0000A1Z5", "supplier_state": "27", "supplier_pin": "400001", "supplier_lglnm": "ABC Corp", "supplier_bnm": "ABC", "supplier_loc": "Mumbai"},
        "buyerdt1": {"buyer_gstin": "URP", "buyer_state": "96", "buyer_pin": "400601", "buyer_pos": "96", "buyer_lglnm": "Global Client LLC", "buyer_bnm": "Global", "buyer_loc": "London"},
        "itemdtls": [{"itemno": 1, "hsncd": "84713010", "is_service": "N", "qty": 1, "unitprice": 1000, "totamt": 1000, "assamt": 1000, "gstrt": 18, "igstamt": 180, "totitemval": 1180}],
        "valdt1": {"assval": 1000, "igstval": 180, "totinvval": 1180}
    }

    errs_eng = engine.validate_invoice(payload)
    errs_val = validator.validate_invoice(payload)

    assert any(_get_err_code(e) == 2275 for e in errs_eng)
    assert any(_get_err_code(e) == 2275 for e in errs_val)


def test_rule_2276_validator_and_rules_engine():
    """Rule 2276: Supplier pin 999999 caught by engine and validator."""
    engine = RulesEngine()
    validator = GSTValidator()

    payload = {
        "docdt1": {"docno": "INV/2026/013", "docdt": "01/01/2026", "document_type": "INV"},
        "trandt1": {"trancatg": "B2B"},
        "supplierdt1": {"supplier_gstin": "27AAAAA0000A1Z5", "supplier_state": "27", "supplier_pin": "999999", "supplier_lglnm": "ABC Corp", "supplier_bnm": "ABC", "supplier_loc": "Mumbai"},
        "buyerdt1": {"buyer_gstin": "27BBBBB0000B1Z2", "buyer_state": "27", "buyer_pin": "400001", "buyer_pos": "27", "buyer_lglnm": "XYZ Corp", "buyer_bnm": "XYZ", "buyer_loc": "Mumbai"},
        "itemdtls": [{"itemno": 1, "hsncd": "84713010", "is_service": "N", "qty": 1, "unitprice": 1000, "totamt": 1000, "assamt": 1000, "gstrt": 18, "cgstamt": 90, "sgstamt": 90, "totitemval": 1180}],
        "valdt1": {"assval": 1000, "cgstval": 90, "sgstval": 90, "totinvval": 1180}
    }

    errs_eng = engine.validate_invoice(payload)
    errs_val = validator.validate_invoice(payload)

    assert any(_get_err_code(e) == 2276 for e in errs_eng)
    assert any(_get_err_code(e) == 2276 for e in errs_val)


def test_rule_2278_validator_and_rules_engine():
    """Rule 2278: Cancelled docno reuse caught by engine and validator."""
    engine = RulesEngine()
    validator = GSTValidator()

    payload = {
        "docdt1": {"docno": "INV/2026/001", "docdt": "01/01/2026", "document_type": "INV"},
        "trandt1": {"trancatg": "B2B"},
        "is_cancelled_reuse": True,
        "cancelled_doc_registry": {"INV/2026/001"},
        "supplierdt1": {"supplier_gstin": "27AAAAA0000A1Z5", "supplier_state": "27", "supplier_pin": "400001", "supplier_lglnm": "ABC Corp", "supplier_bnm": "ABC", "supplier_loc": "Mumbai"},
        "buyerdt1": {"buyer_gstin": "27BBBBB0000B1Z2", "buyer_state": "27", "buyer_pin": "400001", "buyer_pos": "27", "buyer_lglnm": "XYZ Corp", "buyer_bnm": "XYZ", "buyer_loc": "Mumbai"},
        "itemdtls": [{"itemno": 1, "hsncd": "84713010", "is_service": "N", "qty": 1, "unitprice": 1000, "totamt": 1000, "assamt": 1000, "gstrt": 18, "cgstamt": 90, "sgstamt": 90, "totitemval": 1180}],
        "valdt1": {"assval": 1000, "cgstval": 90, "sgstval": 90, "totinvval": 1180}
    }

    errs_eng = engine.validate_invoice(payload)
    errs_val = validator.validate_invoice(payload)

    assert any(_get_err_code(e) == 2278 for e in errs_eng)
    assert any(_get_err_code(e) == 2278 for e in errs_val)


# ============================================================================
# 3. PYDANTIC SCHEMA VALIDATION TESTS
# ============================================================================

def test_rule_2273_pydantic_schema_rejection(clean_b2b_fixture):
    """Rule 2273: Schema rejects dispatch PIN 999999."""
    inv = copy.deepcopy(clean_b2b_fixture)
    inv["dispdt1"]["pin"] = "999999"
    with pytest.raises(Exception) as exc_info:
        InvoicePayload.model_validate(inv).validate_cross_model_statutory_rules()
    assert "2273" in str(exc_info.value)


def test_rule_2274_pydantic_schema_rejection(clean_b2b_fixture):
    """Rule 2274: Schema rejects domestic buyer PIN 999999."""
    inv = copy.deepcopy(clean_b2b_fixture)
    inv["buyer"]["pin"] = "999999"
    with pytest.raises(Exception) as exc_info:
        InvoicePayload.model_validate(inv).validate_cross_model_statutory_rules()
    assert "2274" in str(exc_info.value)


def test_rule_2275_pydantic_schema_rejection(clean_b2b_fixture):
    """Rule 2275: Schema rejects direct export recipient with domestic PIN."""
    inv = copy.deepcopy(clean_b2b_fixture)
    inv["trancatg"] = "EXPWP"
    inv["buyer"]["gstin"] = "URP"
    inv["buyer"]["state"] = "96"
    inv["buyer"]["pos"] = "96"
    inv["buyer"]["pin"] = "400601"
    with pytest.raises(Exception) as exc_info:
        InvoicePayload.model_validate(inv).validate_cross_model_statutory_rules()
    assert "2275" in str(exc_info.value)


def test_rule_2276_pydantic_schema_rejection(clean_b2b_fixture):
    """Rule 2276: Schema rejects supplier PIN 999999."""
    inv = copy.deepcopy(clean_b2b_fixture)
    inv["supplier"]["pin"] = "999999"
    with pytest.raises(Exception) as exc_info:
        InvoicePayload.model_validate(inv).validate_cross_model_statutory_rules()
    assert "2276" in str(exc_info.value)


def test_rule_2278_pydantic_schema_rejection(clean_b2b_fixture):
    """Rule 2278: Schema rejects cancelled document number reuse."""
    inv = copy.deepcopy(clean_b2b_fixture)
    inv["is_cancelled_reuse"] = True
    inv["cancelled_doc_registry"] = {"INV-2026-001"}
    with pytest.raises(Exception) as exc_info:
        InvoicePayload.model_validate(inv).validate_cross_model_statutory_rules()
    assert "2278" in str(exc_info.value)


# ============================================================================
# 4. AUTO-CORRECTION PIPELINE TESTS
# ============================================================================

def test_rule_2273_auto_correct_dispatch_dummy_pin(clean_b2b_fixture):
    """Auto-correction replaces dispatch 999999 with valid seller PIN."""
    inv = copy.deepcopy(clean_b2b_fixture)
    inv["dispdt1"]["pin"] = "999999"
    validated, logs = InvoicePayload.auto_correct_and_build(inv)
    assert str(validated.dispdt1.pin) in ("400001", "400705", "400069")
    assert any("2273" in l["category"] for l in logs)


def test_rule_2274_auto_correct_domestic_buyer_pin(clean_b2b_fixture):
    """Auto-correction replaces domestic buyer 999999 with state capital PIN."""
    inv = copy.deepcopy(clean_b2b_fixture)
    inv["buyer"]["pin"] = "999999"
    validated, logs = InvoicePayload.auto_correct_and_build(inv)
    assert str(validated.buyer.pin) in ("560001", "400001")
    assert any("2274" in l["category"] for l in logs)


def test_rule_2275_auto_correct_export_buyer_pin(clean_b2b_fixture):
    """Auto-correction replaces export buyer domestic PIN with 999999."""
    inv = copy.deepcopy(clean_b2b_fixture)
    inv["trancatg"] = "EXPWP"
    inv["buyer"]["gstin"] = "URP"
    inv["buyer"]["state"] = "96"
    inv["buyer"]["pos"] = "96"
    inv["buyer"]["pin"] = "400601"
    validated, logs = InvoicePayload.auto_correct_and_build(inv)
    assert str(validated.buyer.pin) == "999999"
    assert any("2275" in l["category"] for l in logs)


def test_rule_2276_auto_correct_supplier_pin(clean_b2b_fixture):
    """Auto-correction replaces supplier dummy 999999 with state PIN."""
    inv = copy.deepcopy(clean_b2b_fixture)
    inv["supplier"]["pin"] = "999999"
    validated, logs = InvoicePayload.auto_correct_and_build(inv)
    assert str(validated.supplier.pin) in ("400001", "400601")
    assert any("2276" in l["category"] for l in logs)


def test_rule_2278_auto_correct_cancelled_docno_reuse(clean_b2b_fixture):
    """Auto-correction appends revision suffix '-A' to reuse of cancelled docno."""
    inv = copy.deepcopy(clean_b2b_fixture)
    inv["is_cancelled_reuse"] = True
    inv["cancelled_doc_registry"] = {"INV-2026-001"}
    validated, logs = InvoicePayload.auto_correct_and_build(inv)
    assert validated.docno == "INV-2026-001-A"
    assert any("2278" in l["category"] for l in logs)


# ============================================================================
# 5. LAKEHOUSE PARQUET PERSISTENCE & ROUNDTRIP TEST
# ============================================================================

def test_lakehouse_roundtrip_rules_2273_to_2278(tmp_path, clean_b2b_fixture):
    """Lakehouse Parquet persistence and audit trail verification for Rules 2273-2278."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    # 1. Dispatch dummy pin 999999 (Rule 2273)
    p1 = copy.deepcopy(clean_b2b_fixture)
    p1["docno"] = "INV-2026-101"
    p1["dispdt1"]["pin"] = "999999"

    # 2. Domestic buyer pin 999999 (Rule 2274)
    p2 = copy.deepcopy(clean_b2b_fixture)
    p2["docno"] = "INV-2026-102"
    p2["buyer"]["pin"] = "999999"

    # 3. Export buyer domestic pin (Rule 2275)
    p3 = copy.deepcopy(clean_b2b_fixture)
    p3["docno"] = "INV-2026-103"
    p3["trancatg"] = "EXPWP"
    p3["buyer"]["gstin"] = "URP"
    p3["buyer"]["state"] = "96"
    p3["buyer"]["pos"] = "96"
    p3["buyer"]["pin"] = "400601"

    # 4. Supplier dummy pin 999999 (Rule 2276)
    p4 = copy.deepcopy(clean_b2b_fixture)
    p4["docno"] = "INV-2026-104"
    p4["supplier"]["pin"] = "999999"

    # 5. Cancelled docno reuse (Rule 2278)
    p5 = copy.deepcopy(clean_b2b_fixture)
    p5["docno"] = "INV-2026-001"
    p5["is_cancelled_reuse"] = True
    p5["cancelled_doc_registry"] = {"INV-2026-001"}

    test_payloads = [p1, p2, p3, p4, p5]

    records = []
    for raw in test_payloads:
        validated, logs = InvoicePayload.auto_correct_and_build(raw)
        records.append({
            "docno": validated.docno,
            "document_type": str(validated.document_type),
            "trancatg": str(validated.trancatg),
            "supplier_gstin": str(validated.supplier.gstin),
            "supplier_pin": str(validated.supplier.pin),
            "buyer_gstin": str(validated.buyer.gstin),
            "buyer_pin": str(validated.buyer.pin),
            "disp_pin": str(validated.dispdt1.pin) if validated.dispdt1 else "",
            "corrections_count": len(logs),
            "audit_trail": str([l["category"] for l in logs])
        })

    table = pa.Table.from_pylist(records)
    parquet_path = tmp_path / "lakehouse_rules_2273_to_2278.parquet"
    pq.write_table(table, parquet_path)

    assert os.path.exists(parquet_path)
    read_table = pq.read_table(parquet_path)
    df = read_table.to_pandas()

    assert len(df) == 5
    # 1. Dispatch PIN rectified
    assert df.loc[df["docno"] == "INV-2026-101", "disp_pin"].values[0] in ("400001", "400705", "400069")
    # 2. Buyer PIN rectified to 560001 or 400001
    assert df.loc[df["docno"] == "INV-2026-102", "buyer_pin"].values[0] in ("560001", "400001")
    # 3. Export PIN rectified to 999999
    assert df.loc[df["docno"] == "INV-2026-103", "buyer_pin"].values[0] == "999999"
    # 4. Supplier PIN rectified to 400001 or 400601
    assert df.loc[df["docno"] == "INV-2026-104", "supplier_pin"].values[0] in ("400001", "400601")
    # 5. Cancelled docno rectified to INV-2026-001-A
    assert "INV-2026-001-A" in df["docno"].values


def test_storage_flatten_and_telemetry(clean_b2b_fixture):
    """Verify storage.py flatten_invoice_payload enriches statutory telemetry for 2273-2278."""
    inv = copy.deepcopy(clean_b2b_fixture)
    inv["dispdt1"]["pin"] = "999999"  # Triggers 2273

    rows = flatten_invoice_payload(inv)
    assert len(rows) > 0
    row = rows[0]
    assert row["dispatch_pin"] in ("400001", "400705", "400069")
    assert row["sentinel_status_badge"] == "FLAGGED_AND_RECTIFIED"
    assert "2273" in row["sentinel_audit_reasons"]
