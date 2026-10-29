"""
Tests for Indian GST E-Invoicing Rules 2247, 2248, and 2255:
1. Rule 2247: Recipient Should Be SEZ for Transaction (TranDtls.SupTyp SEZWP/SEZWOP but buyer is DTA).
2. Rule 2248: Recipient Has to Be URP in Case of Export Transactions (EXPWP/EXPWOP requires literal "URP").
3. Rule 2255: Requested Payload is Empty (HTTP transport layer, Content-Type, stream truncation, encryption failure).

Covers:
- Statutory Scenarios & Diagnostic Classifiers
- GSTValidator & RulesEngine Pre-API Validations
- Pydantic Ingestion Cross-Model Validations
- Auto-Correction & Audit Trail Generation
- Lakehouse Parquet Storage Reconciliation
"""

import copy
import os
import shutil
import tempfile
import pytest
from decimal import Decimal

from Template_Converters.validator import GSTValidator
from src.rules.rules_engine import RulesEngine
from src.ingestion.schemas import (
    InvoicePayload,
    classify_rule_2247_diagnostic,
    classify_rule_2248_diagnostic,
    classify_rule_2255_diagnostic,
    validate_irp_transport_request,
    KNOWN_SEZ_BUYER_GSTINS,
)
from src.ingestion.storage import (
    flatten_invoice_payload,
    write_parquet,
    read_parquet,
)


@pytest.fixture
def clean_b2b_invoice():
    """A standard clean domestic B2B invoice (Maharashtra -> Maharashtra)."""
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
def clean_sez_invoice():
    """A standard clean SEZ invoice with payment of tax (SEZWP)."""
    return {
        "self_gstin": "27AAAAA0000A1Z5",
        "docno": "INV-2026-SEZ01",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "SEZWP",
        "supplier": {
            "gstin": "27AAAAA0000A1Z5",
            "lglnm": "Apex Components Ltd",
            "bnm": "Apex House",
            "state": "27",
            "pin": "400001",
            "loc": "Mumbai"
        },
        "buyer": {
            "gstin": "24AAACS0000A1Z5",  # Known SEZ GSTIN
            "lglnm": "Gujarat Port SEZ Developer Unit",
            "bnm": "Special Economic Zone",
            "state": "24",
            "pos": "24",
            "pin": "380001",
            "loc": "Ahmedabad",
            "is_sez": True
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


@pytest.fixture
def clean_export_invoice():
    """A standard clean direct export invoice (EXPWP, POS 96, Pin 999999, URP)."""
    return {
        "self_gstin": "27AAAAA0000A1Z5",
        "docno": "INV-2026-EXP01",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "EXPWP",
        "supplier": {
            "gstin": "27AAAAA0000A1Z5",
            "lglnm": "Apex International Exporters Ltd",
            "bnm": "Apex Towers",
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
            "shipbno": "SB-9876543",
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
# RULE 2247: DIAGNOSTIC CLASSIFIER TESTS
# ==============================================================================

def test_rule_2247_scenario_1_domestic_sale_misclassified_as_sez():
    """Scenario 1: Domestic sale to regular DTA taxpayer misclassified as SEZWP."""
    diag = classify_rule_2247_diagnostic(
        buyer_gstin="27BBBBB1111B1Z2",
        trancatg="SEZWP",
        is_sez_buyer=False
    )
    assert not diag["is_valid"]
    assert diag["error_code"] == 2247
    assert diag["scenario"] == "DOMESTIC_SALE_MISCLASSIFIED_AS_SEZ"
    assert diag["rectified_trancatg"] == "B2B"
    assert "domestic taxpayer (dta)" in diag["reason"].lower()


def test_rule_2247_scenario_2_wrong_entity_gstin_for_sez_buyer():
    """Scenario 2: DTA HQ GSTIN passed, but SEZ branch GSTIN exists."""
    diag = classify_rule_2247_diagnostic(
        buyer_gstin="27BBBBB1111B1Z2",
        trancatg="SEZWP",
        is_sez_buyer=False,
        sez_gstin="24AAACS0000A1Z5"
    )
    assert not diag["is_valid"]
    assert diag["error_code"] == 2247
    assert diag["scenario"] == "WRONG_ENTITY_GSTIN_SELECTED_FOR_SEZ_BUYER"
    assert diag["rectified_gstin"] == "24AAACS0000A1Z5"


def test_rule_2247_scenario_3_portal_sync_lag():
    """Scenario 3: Buyer recently granted SEZ status with portal sync lag."""
    diag = classify_rule_2247_diagnostic(
        buyer_gstin="27BBBBB1111B1Z2",
        trancatg="SEZWP",
        is_sez_buyer=False,
        is_portal_sync_lag=True
    )
    assert not diag["is_valid"]
    assert diag["error_code"] == 2247
    assert diag["scenario"] == "SEZ_STATUS_RECENTLY_GRANTED_PORTAL_SYNC_LAG"
    assert diag["action"] == "REFRESH_GSTN_PORTAL_CACHE"


def test_rule_2247_valid_cases():
    """Valid SEZ transactions and non-SEZ categories."""
    # Known SEZ GSTIN
    diag1 = classify_rule_2247_diagnostic(buyer_gstin="24AAACS0000A1Z5", trancatg="SEZWP")
    assert diag1["is_valid"]
    assert diag1["error_code"] is None

    # Flagged SEZ Buyer
    diag2 = classify_rule_2247_diagnostic(buyer_gstin="27XXXXX0000X1Z1", trancatg="SEZWOP", is_sez_buyer=True)
    assert diag2["is_valid"]

    # Non-SEZ category (B2B)
    diag3 = classify_rule_2247_diagnostic(buyer_gstin="27BBBBB1111B1Z2", trancatg="B2B")
    assert diag3["is_valid"]


# ==============================================================================
# RULE 2248: DIAGNOSTIC CLASSIFIER TESTS
# ==============================================================================

def test_rule_2248_scenario_1_domestic_gstin_passed_in_export():
    """Scenario 1: Domestic 15-character GSTIN passed in export payload."""
    diag = classify_rule_2248_diagnostic(
        buyer_gstin="27AAAAA0000A1Z5",
        trancatg="EXPWP",
        is_export=True
    )
    assert not diag["is_valid"]
    assert diag["error_code"] == 2248
    assert diag["scenario"] == "DOMESTIC_GSTIN_PASSED_IN_EXPORT_PAYLOAD"
    assert diag["rectified_gstin"] == "URP"


def test_rule_2248_scenario_2_overseas_tax_id_passed():
    """Scenario 2: Overseas Tax ID / EIN / VAT passed in buyer GSTIN."""
    diag = classify_rule_2248_diagnostic(
        buyer_gstin="US-EIN-987654321",
        trancatg="EXPWP",
        is_export=True
    )
    assert not diag["is_valid"]
    assert diag["error_code"] == 2248
    assert diag["scenario"] == "OVERSEAS_TAX_ID_VAT_OR_EIN_PASSED"
    assert diag["rectified_gstin"] == "URP"


def test_rule_2248_scenario_3_field_passed_as_null_or_blank():
    """Scenario 3: BuyerDtls.Gstin passed as null or blank."""
    for empty_val in [None, "", "   ", "null", "None"]:
        diag = classify_rule_2248_diagnostic(
            buyer_gstin=empty_val,
            trancatg="EXPWP",
            is_export=True
        )
        assert not diag["is_valid"]
        assert diag["error_code"] == 2248
        assert diag["scenario"] == "FIELD_PASSED_AS_NULL_OR_BLANK_STRING"
        assert diag["rectified_gstin"] == "URP"


def test_rule_2248_scenario_4_domestic_sale_misclassified_as_export():
    """Scenario 4: Domestic sale misclassified as export."""
    diag = classify_rule_2248_diagnostic(
        buyer_gstin="27BBBBB1111B1Z2",
        trancatg="EXPWP",
        is_export=True,
        is_domestic_sale=True
    )
    assert not diag["is_valid"]
    assert diag["error_code"] == 2248
    assert diag["scenario"] == "DOMESTIC_SALE_MISCLASSIFIED_AS_EXPORT"
    assert diag["rectified_trancatg"] == "B2B"
    assert diag["rectified_gstin"] == "27BBBBB1111B1Z2"


def test_rule_2248_valid_cases():
    """Valid export recipient with URP and non-export transactions."""
    diag_exp = classify_rule_2248_diagnostic(buyer_gstin="URP", trancatg="EXPWP", is_export=True)
    assert diag_exp["is_valid"]
    assert diag_exp["error_code"] is None

    diag_b2b = classify_rule_2248_diagnostic(buyer_gstin="27BBBBB1111B1Z2", trancatg="B2B", is_export=False)
    assert diag_b2b["is_valid"]


# ==============================================================================
# RULE 2255: DIAGNOSTIC CLASSIFIER & TRANSPORT INTEGRITY TESTS
# ==============================================================================

def test_rule_2255_scenario_1_empty_request_body():
    """Scenario 1: HTTP POST sent with empty dict, string, or zero-byte body."""
    for empty_body in [{}, "", None, b"", "{}", b"{}"]:
        diag = classify_rule_2255_diagnostic(raw_body=empty_body)
        assert not diag["is_valid"]
        assert diag["error_code"] == 2255
        assert diag["scenario"] == "EMPTY_REQUEST_BODY"


def test_rule_2255_scenario_2_missing_or_incorrect_content_type():
    """Scenario 2: Header sent as Content-Type: text/plain or missing."""
    diag = classify_rule_2255_diagnostic(
        payload={"docno": "INV01"},
        content_type="text/plain"
    )
    assert not diag["is_valid"]
    assert diag["error_code"] == 2255
    assert diag["scenario"] == "MISSING_OR_INCORRECT_CONTENT_TYPE_HEADER"


def test_rule_2255_scenario_3_premature_stream_flush():
    """Scenario 3: HTTP client stream closed prematurely or zero-byte content-length."""
    diag = classify_rule_2255_diagnostic(
        payload={"docno": "INV01"},
        content_type="application/json",
        content_length=0,
        is_stream_closed_early=True
    )
    assert not diag["is_valid"]
    assert diag["error_code"] == 2255
    assert diag["scenario"] == "PREMATURE_STREAM_FLUSH_OR_CLOSE"


def test_rule_2255_scenario_4_encryption_failure():
    """Scenario 4: Encryption wrapper returned empty string."""
    diag = classify_rule_2255_diagnostic(
        payload={"docno": "INV01"},
        content_type="application/json",
        encrypted_data="",
        is_encryption_failed=True
    )
    assert not diag["is_valid"]
    assert diag["error_code"] == 2255
    assert diag["scenario"] == "ENCRYPTION_FAILURE_PRODUCING_EMPTY_BUFFER"


def test_rule_2255_valid_transport():
    """Valid HTTP request payload and headers."""
    res = validate_irp_transport_request(
        body={"docno": "INV01", "self_gstin": "27AAAAA0000A1Z5"},
        headers={"Content-Type": "application/json", "Content-Length": "128"},
        encrypted_data="eyJhbGciOi..."
    )
    assert res["is_valid"]
    assert res["error_code"] is None


# ==============================================================================
# GSTVALIDATOR PRE-API VALIDATION TESTS
# ==============================================================================

def test_rule_2247_validator_catches_dta_on_sez(clean_b2b_invoice):
    """GSTValidator catches non-SEZ buyer GSTIN on SEZWP transaction."""
    inv = copy.deepcopy(clean_b2b_invoice)
    inv["trancatg"] = "SEZWP"
    inv["buyer"]["gstin"] = "27BBBBB1111B1Z2"
    inv["buyer"]["is_sez"] = False
    errors = GSTValidator.validate_invoice(inv)
    assert any(e.get("error_code") == 2247 for e in errors)


def test_rule_2248_validator_catches_domestic_gstin_on_export(clean_export_invoice):
    """GSTValidator catches domestic GSTIN on direct export transaction."""
    inv = copy.deepcopy(clean_export_invoice)
    inv["buyer"]["gstin"] = "27AAAAA0000A1Z5"
    errors = GSTValidator.validate_invoice(inv)
    assert any(e.get("error_code") == 2248 for e in errors)


def test_rule_2255_validator_catches_empty_payload():
    """GSTValidator catches completely empty payload."""
    errors_empty_dict = GSTValidator.validate_invoice({})
    assert any(e.get("error_code") == 2255 for e in errors_empty_dict)

    errors_none = GSTValidator.validate_invoice(None)
    assert any(e.get("error_code") == 2255 for e in errors_none)


def test_rules_2247_2248_2255_validator_passes_valid(clean_b2b_invoice, clean_sez_invoice, clean_export_invoice):
    """GSTValidator passes valid B2B, SEZ, and Export payloads."""
    assert len(GSTValidator.validate_invoice(clean_b2b_invoice)) == 0
    assert len(GSTValidator.validate_invoice(clean_sez_invoice)) == 0
    assert len(GSTValidator.validate_invoice(clean_export_invoice)) == 0


# ==============================================================================
# RULES ENGINE VALIDATION TESTS
# ==============================================================================

def test_rule_2247_rules_engine_catches_dta_on_sez(clean_b2b_invoice):
    inv = copy.deepcopy(clean_b2b_invoice)
    inv["trancatg"] = "SEZWOP"
    inv["buyer"]["gstin"] = "27BBBBB1111B1Z2"
    inv["buyer"]["is_sez"] = False
    errors = RulesEngine.validate_invoice(inv)
    assert any(e.get("error_code") == 2247 for e in errors)


def test_rule_2248_rules_engine_catches_overseas_ein_on_export(clean_export_invoice):
    inv = copy.deepcopy(clean_export_invoice)
    inv["buyer"]["gstin"] = "US-EIN-987654321"
    errors = RulesEngine.validate_invoice(inv)
    assert any(e.get("error_code") == 2248 for e in errors)


def test_rule_2255_rules_engine_catches_empty_payload():
    errors = RulesEngine.validate_invoice({})
    assert any(e.get("error_code") == 2255 for e in errors)


# ==============================================================================
# PYDANTIC CROSS-MODEL REJECTION TESTS
# ==============================================================================

def test_rule_2247_pydantic_schema_rejection(clean_b2b_invoice):
    """Pydantic cross-model validation rejects domestic buyer on SEZ transaction."""
    inv = copy.deepcopy(clean_b2b_invoice)
    inv["trancatg"] = "SEZWP"
    inv["buyer"]["gstin"] = "27BBBBB1111B1Z2"
    inv["buyer"]["is_sez"] = False
    with pytest.raises(Exception) as exc_info:
        InvoicePayload.model_validate(inv).validate_cross_model_statutory_rules()
    assert "2247" in str(exc_info.value)


def test_rule_2248_pydantic_schema_rejection(clean_export_invoice):
    """Pydantic cross-model validation rejects export transaction without URP."""
    inv = copy.deepcopy(clean_export_invoice)
    inv["buyer"]["gstin"] = "27BBBBB1111B1Z2"
    with pytest.raises(Exception) as exc_info:
        InvoicePayload.model_validate(inv).validate_cross_model_statutory_rules()
    assert "2248" in str(exc_info.value)


# ==============================================================================
# AUTO-CORRECT AND BUILD AUDIT LOG TESTS
# ==============================================================================

def test_rule_2247_auto_correct_domestic_sale_misclassified_as_sez(clean_b2b_invoice):
    """auto_correct_and_build corrects misclassified SEZWP to B2B when buyer is DTA."""
    inv = copy.deepcopy(clean_b2b_invoice)
    inv["trancatg"] = "SEZWP"
    inv["buyer"]["gstin"] = "27BBBBB1111B1Z2"
    inv["buyer"]["is_sez"] = False

    payload, audit_logs = InvoicePayload.auto_correct_and_build(inv)
    assert payload.trancatg == "B2B"
    assert any("2247" in log.get("category", "") for log in audit_logs)


def test_rule_2247_auto_correct_wrong_entity_gstin(clean_b2b_invoice):
    """auto_correct_and_build applies sez_gstin when DTA GSTIN was passed."""
    inv = copy.deepcopy(clean_b2b_invoice)
    inv["trancatg"] = "SEZWP"
    inv["buyer"]["gstin"] = "27BBBBB1111B1Z2"
    inv["buyer"]["is_sez"] = False
    inv["sez_gstin"] = "24AAACS0000A1Z5"

    payload, audit_logs = InvoicePayload.auto_correct_and_build(inv)
    assert payload.buyer.gstin == "24AAACS0000A1Z5"
    assert any("2247" in log.get("category", "") for log in audit_logs)


def test_rule_2248_auto_correct_domestic_gstin_to_urp(clean_export_invoice):
    """auto_correct_and_build corrects domestic GSTIN to URP for export transaction."""
    inv = copy.deepcopy(clean_export_invoice)
    inv["buyer"]["gstin"] = "27AAAAA0000A1Z5"

    payload, audit_logs = InvoicePayload.auto_correct_and_build(inv)
    assert payload.buyer.gstin == "URP"
    assert any("2248" in log.get("category", "") for log in audit_logs)


def test_rule_2248_auto_correct_overseas_ein_to_urp(clean_export_invoice):
    """auto_correct_and_build corrects overseas tax ID to URP for export."""
    inv = copy.deepcopy(clean_export_invoice)
    inv["buyer"]["gstin"] = "US-EIN-987654321"

    payload, audit_logs = InvoicePayload.auto_correct_and_build(inv)
    assert payload.buyer.gstin == "URP"
    assert any("2248" in log.get("category", "") for log in audit_logs)


def test_rule_2248_auto_correct_domestic_sale_misclassified_as_export(clean_b2b_invoice):
    """auto_correct_and_build changes domestic sale misclassified as export to B2B."""
    inv = copy.deepcopy(clean_b2b_invoice)
    inv["trancatg"] = "EXPWP"
    inv["is_domestic_sale"] = True

    payload, audit_logs = InvoicePayload.auto_correct_and_build(inv)
    assert payload.trancatg == "B2B"
    assert payload.buyer.gstin == "27BBBBB1111B1Z2"
    assert any("2248" in log.get("category", "") for log in audit_logs)


# ==============================================================================
# DATA LAKEHOUSE PARQUET RECONCILIATION TEST
# ==============================================================================

def test_rules_2247_2248_lakehouse_storage_reconciliation(clean_export_invoice):
    """Verifies that an invoice corrected under Rule 2248 properly persists in Parquet Lakehouse."""
    inv = copy.deepcopy(clean_export_invoice)
    inv["buyer"]["gstin"] = "US-EIN-987654321"  # triggers Rule 2248 -> corrected to URP

    payload, audit_logs = InvoicePayload.auto_correct_and_build(inv)
    flattened = flatten_invoice_payload(payload)

    temp_dir = tempfile.mkdtemp()
    try:
        parquet_path = os.path.join(temp_dir, "test_rules_2247_2248.parquet")
        write_parquet(flattened, parquet_path)

        assert os.path.exists(parquet_path)
        df = read_parquet(parquet_path)
        assert len(df) == 1
        assert df["buyer_gstin"].iloc[0] == "URP"
        assert df["transaction_category"].iloc[0] == "EXPWP"
        assert df["buyer_pos"].iloc[0] == "96"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
