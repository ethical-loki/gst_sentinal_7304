"""
Test Suite: NIC Error Codes 2232 & 2233 Statutory Compliance & Data Lakehouse Reconciliation.
File: tests/test_rules_2232_2233_lakehouse.py

Validates Indian GST e-Invoicing (NIC / IRP) Statutory Requirements:
1. Error Code 2232:
   "POS is Incorrect for Export Transaction"
   - Occurs when an Export transaction (SupTyp is EXP, EXPWP, or EXPWOP) is sent
     with a Place of Supply (BuyerDtls.Pos) other than the designated "Other Country" state code "96".
   - Under Section 11 of the IGST Act, the Place of Supply for cross-border exports lies outside India.
     The GST system mandates using code "96" for Place of Supply and Recipient State Code in all direct export payloads.
   Scenarios:
     - SELLER_OWN_STATE_PASSED_AS_POS: "SupTyp": "EXPWP", "BuyerDtls": { "Pos": "27" } -> Pos: "96", StateCode: "96"
     - PORT_GATEWAY_STATE_CODE_PASSED_AS_POS: Export via Nhava Sheva (MH), "BuyerDtls": { "Pos": "27" } -> Pos: "96"
     - NUMERIC_VALUE_PASSED_INSTEAD_OF_STRING: "BuyerDtls": { "Pos": 96 } -> Pos: "96"
     - WRONG_SUPPLY_TYPE_SELECTED_FOR_DOMESTIC_SUPPLY: B2B sale misclassified as EXPWP -> Switch to B2B
     - VALID: "BuyerDtls": { "Pos": "96", "StateCode": "96" }

2. Error Code 2233:
   "Duplicate Sl Numbers Are Not Allowed in Line Items"
   - Occurs when the item serial number field (ItemList[i].SlNo) contains duplicate values across line items.
   - Every line item inside the ItemList array must have a strictly unique serial number.
   Scenarios:
     - HARDCODED_ONE_ON_ALL_LINE_ITEMS: Item 1: "1", Item 2: "1" -> rectified: ["1", "2"]
     - MERGED_BATCHES_CARRYING_PARENT_SERIAL_NUMBER: Sub-lines or batch splits sharing parent SlNo -> rectified: ["1", "2"]
     - NON_STRING_SPACE_ARTIFACTS_CAUSING_COLLISION: "10" and " 10" whitespace collision -> rectified: ["1", "2"]
     - VALID: Strictly unique sequential SlNos ("1", "2", "3", etc.)

3. Lakehouse Data Pipeline:
   - Flattening, Parquet storage, schema verification, and round-trip reconciliation.
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
    classify_rule_2232_diagnostic,
    classify_rule_2233_diagnostic,
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
def clean_export_invoice():
    """A standard clean direct export invoice with IGST payment (EXPWP)."""
    return {
        "self_gstin": "27AAAAA0000A1Z5",
        "docno": "EXP-2026-VAL01",
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
            "lglnm": "Global Trade Partners Inc",
            "bnm": "Global Gateway",
            "state": "96",
            "pos": "96",
            "pin": "999999",
            "loc": "New York"
        },
        "expdt1": {
            "shipbno": "SB-1234567",
            "shipbdt": "26-10-2026",
            "port": "INNSA1",
            "cntcode": "US",
            "forcur": "USD"
        },
        "itemdtls": [
            {
                "slno": "1",
                "prdnm": "Precision Engineered Turbine Component",
                "hsncd": "84069000",
                "qty": "5.00",
                "uqc": "NOS",
                "unit": "NOS",
                "unitprice": "20000.00",
                "totamt": "100000.00",
                "discount": "0.00",
                "assval": "100000.00",
                "gstrate": 18.0,
                "cgstval": "0.00",
                "sgstval": "0.00",
                "igstval": "18000.00",
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


@pytest.fixture
def clean_multi_item_invoice():
    """A standard domestic B2B invoice with 3 distinct sequential line items."""
    return {
        "self_gstin": "27AAAAA0000A1Z5",
        "docno": "INV-2026-MULTI01",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "B2B",
        "supplier": {
            "gstin": "27AAAAA0000A1Z5",
            "lglnm": "Acme Technologies Private Limited",
            "bnm": "Acme Industrial Complex",
            "state": "27",
            "pin": "400001",
            "loc": "Mumbai"
        },
        "buyer": {
            "gstin": "29BBBBB1111B1Z2",
            "lglnm": "Zenith Retail Distributors",
            "bnm": "Zenith Trade Towers",
            "state": "29",
            "pos": "29",
            "pin": "560001",
            "loc": "Bengaluru"
        },
        "itemdtls": [
            {
                "slno": "1",
                "prdnm": "Microcontroller Unit Alpha",
                "hsncd": "85423100",
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
            },
            {
                "slno": "2",
                "prdnm": "Embedded Flash Memory Chip",
                "hsncd": "85423200",
                "qty": "20.00",
                "uqc": "NOS",
                "unit": "NOS",
                "unitprice": "500.00",
                "totamt": "10000.00",
                "discount": "0.00",
                "assval": "10000.00",
                "gstrate": 18.0,
                "cgstval": "0.00",
                "sgstval": "0.00",
                "igstval": "1800.00",
                "totitemval": "11800.00"
            },
            {
                "slno": "3",
                "prdnm": "High Precision Voltage Regulator",
                "hsncd": "85423900",
                "qty": "50.00",
                "uqc": "NOS",
                "unit": "NOS",
                "unitprice": "200.00",
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
            "assval": "30000.00",
            "cgstval": "0.00",
            "sgstval": "0.00",
            "igstval": "5400.00",
            "cesval": "0.00",
            "stcesval": "0.00",
            "discount": "0.00",
            "othchrg": "0.00",
            "rndoffamt": "0.00",
            "totinvval": "35400.00"
        }
    }


# ==============================================================================
# RULE 2232: DIAGNOSTIC CLASSIFIER TESTS
# ==============================================================================

def test_rule_2232_scenario_1_seller_own_state_passed_as_pos():
    """Scenario 1: Seller's Own State Passed as POS (e.g. SupTyp='EXPWP', BuyerDtls.Pos='27')."""
    diag = classify_rule_2232_diagnostic(
        pos="27",
        trancatg="EXPWP",
        seller_state="27",
    )
    assert diag["error_code"] == 2232
    assert diag["scenario"] == "SELLER_OWN_STATE_PASSED_AS_POS"
    assert not diag["is_valid"]
    assert diag["action"] == "SET_EXPORT_POS_TO_96"
    assert diag["rectified_pos"] == "96"
    assert diag["rectified_state"] == "96"
    assert "96" in diag["resolution"]


def test_rule_2232_scenario_2_port_gateway_state_code_passed_as_pos():
    """Scenario 2: Port / Gateway State Code Passed as POS (e.g. Nhava Sheva MH '27')."""
    diag = classify_rule_2232_diagnostic(
        pos="27",
        trancatg="EXPWP",
        seller_state="24",  # Gujarat seller exporting via Mumbai port
        port="INNSA1",
        is_gateway_port_used=True,
    )
    assert diag["error_code"] == 2232
    assert diag["scenario"] == "PORT_GATEWAY_STATE_CODE_PASSED_AS_POS"
    assert not diag["is_valid"]
    assert diag["action"] == "SET_EXPORT_POS_TO_96"
    assert diag["rectified_pos"] == "96"
    assert "exit port's location does not determine POS" in diag["reason"]


def test_rule_2232_scenario_3_numeric_value_passed_instead_of_string():
    """Scenario 3: Numeric Value Passed Instead of String (e.g. BuyerDtls.Pos=96)."""
    diag = classify_rule_2232_diagnostic(
        pos=96,
        trancatg="EXPWP",
    )
    assert diag["error_code"] == 2232
    assert diag["scenario"] == "NUMERIC_VALUE_PASSED_INSTEAD_OF_STRING"
    assert not diag["is_valid"]
    assert diag["action"] == "ENQUOTE_NUMERIC_POS"
    assert diag["rectified_pos"] == "96"
    assert "2-character string" in diag["reason"]


def test_rule_2232_scenario_4_wrong_supply_type_selected_for_domestic_supply():
    """Scenario 4: Standard domestic B2B sale accidentally tagged as 'EXPWP' with local Pos."""
    diag = classify_rule_2232_diagnostic(
        pos="27",
        trancatg="EXPWP",
        is_domestic_misclassified_as_export=True,
        recipient_state="27",
    )
    assert diag["error_code"] == 2232
    assert diag["scenario"] == "WRONG_SUPPLY_TYPE_SELECTED_FOR_DOMESTIC_SUPPLY"
    assert not diag["is_valid"]
    assert diag["action"] == "CHANGE_SUPPLY_TYPE_TO_B2B"
    assert diag["rectified_trancatg"] == "B2B"
    assert diag["rectified_pos"] == "27"


def test_rule_2232_valid_export_pos():
    """Valid Scenario: POS is '96' (Other Country) for export transaction."""
    diag = classify_rule_2232_diagnostic(
        pos="96",
        trancatg="EXPWP",
    )
    assert diag["error_code"] is None
    assert diag["scenario"] == "VALID"
    assert diag["is_valid"]
    assert diag["rectified_pos"] == "96"


# ==============================================================================
# RULE 2233: DIAGNOSTIC CLASSIFIER TESTS
# ==============================================================================

def test_rule_2233_scenario_1_hardcoded_one_on_all_line_items():
    """Scenario 1: Hardcoded '1' on all line items in ERP extraction."""
    items = [
        {"slno": "1", "prdnm": "Item Alpha"},
        {"slno": "1", "prdnm": "Item Beta"},
        {"slno": "1", "prdnm": "Item Gamma"},
    ]
    diag = classify_rule_2233_diagnostic(items=items)
    assert diag["error_code"] == 2233
    assert diag["scenario"] == "HARDCODED_ONE_ON_ALL_LINE_ITEMS"
    assert not diag["is_valid"]
    assert diag["action"] in ("REINDEX_SEQUENTIALLY", "GENERATE_SEQUENTIAL_SERIAL_NUMBERS")
    assert diag["duplicate_slnos"] == ["1"]
    assert diag["rectified_slnos"] == ["1", "2", "3"]


def test_rule_2233_scenario_2_merged_batches_carrying_parent_slno():
    """Scenario 2: Merged batches carrying parent serial number."""
    items = [
        {"slno": "1", "prdnm": "Pharma Formulation", "batch_no": "B101"},
        {"slno": "1", "prdnm": "Pharma Formulation", "batch_no": "B102"},
        {"slno": "2", "prdnm": "Syringe Pack", "batch_no": "S001"},
    ]
    diag = classify_rule_2233_diagnostic(items=items, is_batch_split=True)
    assert diag["error_code"] == 2233
    assert diag["scenario"] == "MERGED_BATCHES_CARRYING_PARENT_SERIAL_NUMBER"
    assert not diag["is_valid"]
    assert diag["action"] == "REINDEX_BATCH_SUB_LINES"
    assert diag["duplicate_slnos"] == ["1"]
    assert diag["rectified_slnos"] == ["1", "2", "3"]


def test_rule_2233_scenario_3_non_string_space_artifacts_causing_collision():
    """Scenario 3: Non-string or whitespace artifacts causing collision ('10' vs ' 10')."""
    items = [
        {"slno": "10", "prdnm": "Widget A"},
        {"slno": " 10", "prdnm": "Widget B"},
    ]
    diag = classify_rule_2233_diagnostic(items=items, has_whitespace_artifacts=True)
    assert diag["error_code"] == 2233
    assert diag["scenario"] == "NON_STRING_SPACE_ARTIFACTS_CAUSING_COLLISION"
    assert not diag["is_valid"]
    assert diag["action"] == "NORMALIZE_AND_REINDEX_SEQUENTIALLY"
    assert diag["rectified_slnos"] == ["1", "2"]


def test_rule_2233_valid_unique_serial_numbers():
    """Valid Scenario: All line items have unique sequential serial numbers."""
    items = [
        {"slno": "1", "prdnm": "Item 1"},
        {"slno": "2", "prdnm": "Item 2"},
        {"slno": "3", "prdnm": "Item 3"},
    ]
    diag = classify_rule_2233_diagnostic(items=items)
    assert diag["error_code"] is None
    assert diag["scenario"] == "VALID"
    assert diag["is_valid"]
    assert len(diag["duplicate_slnos"]) == 0


# ==============================================================================
# RULE 2232 & 2233: GSTVALIDATOR PRE-API TESTS
# ==============================================================================

def test_rule_2232_gst_validator_catches_invalid_export_pos(clean_export_invoice):
    """GSTValidator catches export transaction with seller's own state code as POS (Error 2232)."""
    inv = dict(clean_export_invoice)
    inv["buyer"] = dict(inv["buyer"])
    inv["buyer"]["pos"] = "27"  # Domestic state instead of 96
    errors = GSTValidator.validate_invoice(inv)
    assert any(e.get("error_code") == 2232 for e in errors)


def test_rule_2232_gst_validator_catches_numeric_pos(clean_export_invoice):
    """GSTValidator catches export transaction with numeric POS (e.g. 96 integer) (Error 2232)."""
    inv = dict(clean_export_invoice)
    inv["buyer"] = dict(inv["buyer"])
    inv["buyer"]["pos"] = 96  # Integer instead of "96"
    errors = GSTValidator.validate_invoice(inv)
    assert any(e.get("error_code") == 2232 for e in errors)


def test_rule_2233_gst_validator_catches_duplicate_slnos(clean_multi_item_invoice):
    """GSTValidator catches duplicate serial numbers across line items (Error 2233)."""
    inv = dict(clean_multi_item_invoice)
    items = [dict(it) for it in inv["itemdtls"]]
    items[1]["slno"] = "1"  # Duplicate of item 0
    inv["itemdtls"] = items
    errors = GSTValidator.validate_invoice(inv)
    assert any(e.get("error_code") == 2233 for e in errors)


def test_rules_2232_2233_gst_validator_passes_valid(clean_export_invoice, clean_multi_item_invoice):
    """GSTValidator produces 0 errors for clean valid export and multi-item invoices."""
    assert len(GSTValidator.validate_invoice(clean_export_invoice)) == 0
    assert len(GSTValidator.validate_invoice(clean_multi_item_invoice)) == 0


# ==============================================================================
# RULE 2232 & 2233: RULES ENGINE TESTS
# ==============================================================================

def test_rule_2232_rules_engine_catches_invalid_export_pos(clean_export_invoice):
    """RulesEngine catches export transaction with gateway port state code as POS (Error 2232)."""
    inv = dict(clean_export_invoice)
    inv["buyer"] = dict(inv["buyer"])
    inv["buyer"]["pos"] = "27"
    inv["is_gateway_port_used"] = True
    errors = RulesEngine.validate_invoice(inv)
    assert any(e.get("error_code") == 2232 for e in errors)


def test_rule_2233_rules_engine_catches_duplicate_slnos(clean_multi_item_invoice):
    """RulesEngine catches duplicate serial numbers in line items (Error 2233)."""
    inv = dict(clean_multi_item_invoice)
    items = [dict(it) for it in inv["itemdtls"]]
    items[0]["slno"] = "1"
    items[1]["slno"] = "1"
    items[2]["slno"] = "1"
    inv["itemdtls"] = items
    errors = RulesEngine.validate_invoice(inv)
    assert any(e.get("error_code") == 2233 for e in errors)


# ==============================================================================
# RULE 2232 & 2233: PYDANTIC SCHEMA CROSS-MODEL VALIDATION
# ==============================================================================

def test_rule_2232_pydantic_schema_rejection(clean_export_invoice):
    """InvoicePayload.model_validate raises NIC-2232 when export has domestic POS."""
    inv = dict(clean_export_invoice)
    inv["buyer"] = dict(inv["buyer"])
    inv["buyer"]["pos"] = "27"
    with pytest.raises(Exception) as exc_info:
        InvoicePayload.model_validate(inv)
    err_str = str(exc_info.value)
    assert "2232" in err_str
    assert "Place of Supply" in err_str or "Rule 2232" in err_str


def test_rule_2233_pydantic_schema_rejection(clean_multi_item_invoice):
    """InvoicePayload.model_validate raises NIC-2233 when line items have duplicate SlNo."""
    inv = dict(clean_multi_item_invoice)
    items = [dict(it) for it in inv["itemdtls"]]
    items[1]["slno"] = "1"
    inv["itemdtls"] = items
    with pytest.raises(Exception) as exc_info:
        InvoicePayload.model_validate(inv)
    err_str = str(exc_info.value)
    assert "2233" in err_str
    assert "Rule 2233" in err_str or "Duplicate" in err_str


# ==============================================================================
# RULE 2232 & 2233: AUTO-CORRECT AND BUILD AUDIT LOG TESTS
# ==============================================================================

def test_rule_2232_auto_correct_export_pos(clean_export_invoice):
    """auto_correct_and_build auto-corrects export POS to '96' and logs audit trail."""
    inv = dict(clean_export_invoice)
    inv["buyer"] = dict(inv["buyer"])
    inv["buyer"]["pos"] = "27"  # Seller state MH
    model, audit_logs = InvoicePayload.auto_correct_and_build(inv)
    assert model.buyer.pos == "96"
    assert model.buyer.state == "96"
    assert any("2232" in log.get("category", "") for log in audit_logs)


def test_rule_2232_auto_correct_domestic_misclassified_as_export(clean_export_invoice):
    """auto_correct_and_build switches EXPWP to B2B when domestic sale was misclassified."""
    inv = dict(clean_export_invoice)
    inv["buyer"] = dict(inv["buyer"])
    inv["buyer"]["pos"] = "27"
    inv["buyer"]["gstin"] = "27BBBBB1111B1Z2"
    inv["buyer"]["state"] = "27"
    inv["is_domestic_misclassified_as_export"] = True
    model, audit_logs = InvoicePayload.auto_correct_and_build(inv)
    assert model.trancatg == "B2B"
    assert model.buyer.pos == "27"
    assert any("2232" in log.get("category", "") for log in audit_logs)


def test_rule_2233_auto_correct_duplicate_slnos(clean_multi_item_invoice):
    """auto_correct_and_build normalizes duplicate line items to sequential SlNos ('1', '2', '3')."""
    inv = dict(clean_multi_item_invoice)
    items = [dict(it) for it in inv["itemdtls"]]
    items[0]["slno"] = "1"
    items[1]["slno"] = "1"
    items[2]["slno"] = "1"
    inv["itemdtls"] = items
    model, audit_logs = InvoicePayload.auto_correct_and_build(inv)
    slnos = [it.slno for it in model.itemdtls]
    assert slnos == ["1", "2", "3"]
    assert any("2233" in log.get("category", "") for log in audit_logs)


# ==============================================================================
# DATA LAKEHOUSE PARQUET RECONCILIATION
# ==============================================================================

def test_lakehouse_parquet_persistence_roundtrip(clean_export_invoice, clean_multi_item_invoice):
    """Tests flattening, Parquet storage, and round-trip read for export and multi-item invoices."""
    model_exp = InvoicePayload.model_validate(clean_export_invoice)
    rows_exp = flatten_invoice_payload(model_exp)
    assert len(rows_exp) == 1
    assert rows_exp[0]["buyer_pos"] == "96"
    assert rows_exp[0]["item_slno"] == "1"

    model_multi = InvoicePayload.model_validate(clean_multi_item_invoice)
    rows_multi = flatten_invoice_payload(model_multi)
    assert len(rows_multi) == 3
    assert [r["item_slno"] for r in rows_multi] == ["1", "2", "3"]

    temp_dir = tempfile.mkdtemp()
    try:
        parquet_path = os.path.join(temp_dir, "test_rules_2232_2233.parquet")
        all_rows = rows_exp + rows_multi
        write_parquet(all_rows, parquet_path)

        df = read_parquet(parquet_path)
        assert len(df) == 4
        # Export record check
        exp_record = df[df["invoice_id"] == "EXP-2026-VAL01"].iloc[0]
        assert exp_record["buyer_pos"] == "96"
        assert exp_record["transaction_category"] == "EXPWP"
        assert float(exp_record["inv_igst_amount"]) == 18000.00

        # Multi-item records check
        multi_records = df[df["invoice_id"] == "INV-2026-MULTI01"]
        assert len(multi_records) == 3
        assert list(multi_records["item_slno"]) == ["1", "2", "3"]
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
