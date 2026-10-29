"""
Test Suite: NIC Error Codes 2238, 2239, 2240, & 2242 Statutory Compliance & Data Lakehouse Reconciliation.
File: tests/test_rules_2238_to_2242_lakehouse.py

Coverage:
1. Error Code 2238: Quantity is Not Passed for Item
   - SERVICE_LINE_ITEM_WITHOUT_QUANTITY: IsServc='Y', Qty omitted/null -> set Qty=1.00, Unit='OTH'
   - PASSING_EMPTY_STRING_INSTEAD_OF_NUMBER: Qty='' -> positive numeric quantity
   - ZERO_QUANTITY_PASSED: Qty=0 -> non-zero measurable quantity
   - VALID: Positive numeric quantity

2. Error Code 2239: Unit Quantity Code (UQC) is Not Passed for Item
   - OMITTED_FOR_SERVICE_LINE: IsServc='Y', Unit omitted/null -> set Unit='OTH'
   - EMPTY_STRING_PASSED: Unit='' -> set Unit='NOS'
   - ERP_MASTER_FIELD_UNMAPPED: ERP internal unit unmapped -> map to standard 3-letter UQC
   - VALID: Official 3-letter master UQC

3. Error Code 2240: GST Rate of Tax is Incorrect or Not As Notified
   - SINGLE_COMPONENT_PASSED_INSTEAD_OF_COMBINED_RATE: e.g. GstRt=9.0 -> combined rate 18.0
   - PERCENTAGE_SYMBOL_OR_STRING_SENT: GstRt='18%' -> numeric float 18.0
   - ARBITRARY_NON_NOTIFIED_TAX_SLAB: GstRt=15.0 -> align to nearest notified slab (18.0)
   - CESS_RATE_ADDED_TO_GST_RATE: GstRt=40.0, CesRt=12.0 -> separate GstRt=28.0, CesRt=12.0
   - VALID: Official notified GST rate slab

4. Error Code 2242: Recipient POS is Incorrect for Transaction Type
   - DOMESTIC_SALE_PASSED_WITH_POS_96: B2B with Pos='96' -> buyer's actual Indian state code
   - EXPORT_TRANSACTION_MISCLASSIFIED_AS_B2B: Overseas client with Pos='96', sent as B2B -> switch to EXPWP
   - SEZ_SUPPLY_PASSED_WITH_POS_96: SEZ unit with Pos='96' -> physical state of SEZ unit
   - VALID: Domestic transaction with valid Indian state code

5. GSTValidator Pre-API & RulesEngine Interception
6. Pydantic Schema Cross-Model Validation Rejections
7. Auto-Correction Engine Audit Trail Assertions
8. Lakehouse Flattening, Parquet Storage & Schema Verification
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
    classify_rule_2238_diagnostic,
    classify_rule_2239_diagnostic,
    classify_rule_2240_diagnostic,
    classify_rule_2242_diagnostic,
    NOTIFIED_GST_RATES,
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
def clean_service_invoice():
    """Clean service invoice (isservc='Y', HSN 998311, Qty=1, Unit=OTH)."""
    return {
        "self_gstin": "27AAAAA0000A1Z5",
        "docno": "INV-2026-SRV01",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "B2B",
        "supplier": {
            "gstin": "27AAAAA0000A1Z5",
            "lglnm": "Apex IT Consulting Ltd",
            "bnm": "Apex Tech Park",
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
                "prdnm": "Software Consulting Services",
                "hsncd": "998311",
                "isservc": "Y",
                "qty": "1.00",
                "uqc": "OTH",
                "unit": "OTH",
                "unitprice": "50000.00",
                "totamt": "50000.00",
                "discount": "0.00",
                "assval": "50000.00",
                "gstrate": 18.0,
                "cgstval": "4500.00",
                "sgstval": "4500.00",
                "igstval": "0.00",
                "totitemval": "59000.00"
            }
        ],
        "valdtls": {
            "assval": "50000.00",
            "cgstval": "4500.00",
            "sgstval": "4500.00",
            "igstval": "0.00",
            "cesval": "0.00",
            "stcesval": "0.00",
            "discount": "0.00",
            "othchrg": "0.00",
            "rndoffamt": "0.00",
            "totinvval": "59000.00"
        }
    }


# ==============================================================================
# RULE 2238: DIAGNOSTIC CLASSIFIER TESTS
# ==============================================================================

def test_rule_2238_scenario_1_service_without_qty():
    diag = classify_rule_2238_diagnostic(
        qty=None,
        is_service="Y",
        item_slno="1",
        prdnm="Legal Advisory Services"
    )
    assert not diag["is_valid"]
    assert diag["error_code"] == 2238
    assert diag["scenario"] == "SERVICE_LINE_ITEM_WITHOUT_QUANTITY"
    assert diag["rectified_qty"] == 1.0
    assert diag["rectified_unit"] == "OTH"
    assert "service" in diag["reason"].lower()


def test_rule_2238_scenario_2_empty_string_qty():
    diag = classify_rule_2238_diagnostic(
        qty="",
        is_service="N",
        item_slno="1",
        prdnm="Machinery Spare"
    )
    assert not diag["is_valid"]
    assert diag["error_code"] == 2238
    assert diag["scenario"] == "PASSING_EMPTY_STRING_INSTEAD_OF_NUMBER"
    assert diag["rectified_qty"] == 1.0


def test_rule_2238_scenario_3_zero_qty():
    diag = classify_rule_2238_diagnostic(
        qty=0,
        is_service="N",
        item_slno="1",
        prdnm="Machinery Spare"
    )
    assert not diag["is_valid"]
    assert diag["error_code"] == 2238
    assert diag["scenario"] == "ZERO_QUANTITY_PASSED"
    assert diag["rectified_qty"] == 1.0


def test_rule_2238_valid():
    diag = classify_rule_2238_diagnostic(
        qty=15.5,
        is_service="N",
        item_slno="1",
        prdnm="Machinery Spare"
    )
    assert diag["is_valid"]
    assert diag["error_code"] is None
    assert diag["scenario"] == "VALID"


# ==============================================================================
# RULE 2239: DIAGNOSTIC CLASSIFIER TESTS
# ==============================================================================

def test_rule_2239_scenario_1_omitted_for_service():
    diag = classify_rule_2239_diagnostic(
        unit=None,
        is_service="Y",
        item_slno="1",
        prdnm="Consulting"
    )
    assert not diag["is_valid"]
    assert diag["error_code"] == 2239
    assert diag["scenario"] == "OMITTED_FOR_SERVICE_LINE"
    assert diag["rectified_unit"] == "OTH"


def test_rule_2239_scenario_2_empty_string():
    diag = classify_rule_2239_diagnostic(
        unit="",
        is_service="N",
        item_slno="1",
        prdnm="Bearings"
    )
    assert not diag["is_valid"]
    assert diag["error_code"] == 2239
    assert diag["scenario"] == "EMPTY_STRING_PASSED"
    assert diag["rectified_unit"] == "NOS"


def test_rule_2239_scenario_3_erp_unmapped():
    diag = classify_rule_2239_diagnostic(
        unit="PIECES",
        is_service="N",
        item_slno="1",
        prdnm="Bearings"
    )
    assert not diag["is_valid"]
    assert diag["error_code"] == 2239
    assert diag["scenario"] == "ERP_MASTER_FIELD_UNMAPPED"
    assert diag["rectified_unit"] in ("PCS", "NOS", "OTH")


def test_rule_2239_valid():
    diag = classify_rule_2239_diagnostic(
        unit="KGS",
        is_service="N",
        item_slno="1",
        prdnm="Chemical Powder"
    )
    assert diag["is_valid"]
    assert diag["error_code"] is None
    assert diag["scenario"] == "VALID"


# ==============================================================================
# RULE 2240: DIAGNOSTIC CLASSIFIER TESTS
# ==============================================================================

def test_rule_2240_scenario_1_single_component():
    diag = classify_rule_2240_diagnostic(
        gstrate=9.0,
        item_slno="1"
    )
    assert not diag["is_valid"]
    assert diag["error_code"] == 2240
    assert diag["scenario"] == "SINGLE_COMPONENT_PASSED_INSTEAD_OF_COMBINED_RATE"
    assert diag["rectified_gstrate"] == 18.0


def test_rule_2240_scenario_2_percentage_string():
    diag = classify_rule_2240_diagnostic(
        gstrate="18%",
        item_slno="1"
    )
    assert not diag["is_valid"]
    assert diag["error_code"] == 2240
    assert diag["scenario"] == "PERCENTAGE_SYMBOL_OR_STRING_SENT"
    assert diag["rectified_gstrate"] == 18.0


def test_rule_2240_scenario_3_cess_added_to_gst():
    diag = classify_rule_2240_diagnostic(
        gstrate=40.0,
        cesrt=12.0,
        item_slno="1"
    )
    assert not diag["is_valid"]
    assert diag["error_code"] == 2240
    assert diag["scenario"] == "CESS_RATE_ADDED_TO_GST_RATE"
    assert diag["rectified_gstrate"] == 28.0
    assert diag["rectified_cesrt"] == 12.0


def test_rule_2240_scenario_4_arbitrary_slab():
    diag = classify_rule_2240_diagnostic(
        gstrate=15.0,
        item_slno="1"
    )
    assert not diag["is_valid"]
    assert diag["error_code"] == 2240
    assert diag["scenario"] == "ARBITRARY_NON_NOTIFIED_TAX_SLAB"
    assert diag["rectified_gstrate"] in (12.0, 18.0)


def test_rule_2240_valid():
    for slab in NOTIFIED_GST_RATES:
        diag = classify_rule_2240_diagnostic(gstrate=slab, item_slno="1")
        assert diag["is_valid"]
        assert diag["error_code"] is None


# ==============================================================================
# RULE 2242: DIAGNOSTIC CLASSIFIER TESTS
# ==============================================================================

def test_rule_2242_scenario_1_domestic_sale_pos_96():
    diag = classify_rule_2242_diagnostic(
        pos="96",
        trancatg="B2B",
        buyer_state="27",
        buyer_gstin="27BBBBB1111B1Z2"
    )
    assert not diag["is_valid"]
    assert diag["error_code"] == 2242
    assert diag["scenario"] == "DOMESTIC_SALE_PASSED_WITH_POS_96"
    assert diag["rectified_pos"] == "27"


def test_rule_2242_scenario_2_export_misclassified_as_b2b():
    diag = classify_rule_2242_diagnostic(
        pos="96",
        trancatg="B2B",
        buyer_gstin="URP",
        is_export_overseas=True
    )
    assert not diag["is_valid"]
    assert diag["error_code"] == 2242
    assert diag["scenario"] == "EXPORT_TRANSACTION_MISCLASSIFIED_AS_B2B"
    assert diag["rectified_trancatg"] == "EXPWP"
    assert diag["rectified_pos"] == "96"


def test_rule_2242_scenario_3_sez_supply_pos_96():
    diag = classify_rule_2242_diagnostic(
        pos="96",
        trancatg="SEZWP",
        buyer_state="24",
        is_sez=True
    )
    assert not diag["is_valid"]
    assert diag["error_code"] == 2242
    assert diag["scenario"] == "SEZ_SUPPLY_PASSED_WITH_POS_96"
    assert diag["rectified_pos"] == "24"


def test_rule_2242_valid_domestic():
    diag = classify_rule_2242_diagnostic(
        pos="27",
        trancatg="B2B",
        buyer_state="27"
    )
    assert diag["is_valid"]
    assert diag["error_code"] is None


# ==============================================================================
# GSTVALIDATOR PRE-API VALIDATION TESTS
# ==============================================================================

def test_rule_2238_validator_catches_zero_qty(clean_b2b_invoice):
    invoice = copy.deepcopy(clean_b2b_invoice)
    invoice["itemdtls"][0]["qty"] = 0
    errors = GSTValidator.validate_invoice(invoice)
    assert any(e.get("error_code") == 2238 for e in errors)


def test_rule_2239_validator_catches_empty_uqc(clean_b2b_invoice):
    invoice = copy.deepcopy(clean_b2b_invoice)
    invoice["itemdtls"][0]["uqc"] = ""
    invoice["itemdtls"][0]["unit"] = ""
    errors = GSTValidator.validate_invoice(invoice)
    assert any(e.get("error_code") == 2239 for e in errors)


def test_rule_2240_validator_catches_invalid_slab(clean_b2b_invoice):
    invoice = copy.deepcopy(clean_b2b_invoice)
    invoice["itemdtls"][0]["gstrate"] = 15.0
    errors = GSTValidator.validate_invoice(invoice)
    assert any(e.get("error_code") == 2240 for e in errors)


def test_rule_2242_validator_catches_pos_96_domestic(clean_b2b_invoice):
    invoice = copy.deepcopy(clean_b2b_invoice)
    invoice["buyer"]["pos"] = "96"
    errors = GSTValidator.validate_invoice(invoice)
    assert any(e.get("error_code") == 2242 for e in errors)


def test_rules_2238_to_2242_validator_passes_valid(clean_b2b_invoice, clean_service_invoice):
    assert len(GSTValidator.validate_invoice(clean_b2b_invoice)) == 0
    assert len(GSTValidator.validate_invoice(clean_service_invoice)) == 0


# ==============================================================================
# RULES ENGINE TESTS
# ==============================================================================

def test_rule_2238_rules_engine_catches_zero_qty(clean_b2b_invoice):
    invoice = copy.deepcopy(clean_b2b_invoice)
    invoice["itemdtls"][0]["qty"] = 0
    errors = RulesEngine.validate_invoice(invoice)
    assert any(e.get("error_code") == 2238 for e in errors)


def test_rule_2239_rules_engine_catches_missing_unit(clean_b2b_invoice):
    invoice = copy.deepcopy(clean_b2b_invoice)
    invoice["itemdtls"][0]["uqc"] = ""
    invoice["itemdtls"][0]["unit"] = ""
    errors = RulesEngine.validate_invoice(invoice)
    assert any(e.get("error_code") == 2239 for e in errors)


def test_rule_2240_rules_engine_catches_invalid_slab(clean_b2b_invoice):
    invoice = copy.deepcopy(clean_b2b_invoice)
    invoice["itemdtls"][0]["gstrate"] = 10.0
    errors = RulesEngine.validate_invoice(invoice)
    assert any(e.get("error_code") == 2240 for e in errors)


def test_rule_2242_rules_engine_catches_pos_96_domestic(clean_b2b_invoice):
    invoice = copy.deepcopy(clean_b2b_invoice)
    invoice["buyer"]["pos"] = "96"
    errors = RulesEngine.validate_invoice(invoice)
    assert any(e.get("error_code") == 2242 for e in errors)


# ==============================================================================
# PYDANTIC CROSS-MODEL REJECTION TESTS
# ==============================================================================

def test_rule_2238_pydantic_schema_rejection(clean_b2b_invoice):
    inv = copy.deepcopy(clean_b2b_invoice)
    inv["itemdtls"][0]["qty"] = 0
    with pytest.raises(Exception) as exc_info:
        InvoicePayload.model_validate(inv).validate_cross_model_statutory_rules()
    assert "2238" in str(exc_info.value)


def test_rule_2239_pydantic_schema_rejection(clean_b2b_invoice):
    inv = copy.deepcopy(clean_b2b_invoice)
    inv["itemdtls"][0]["unit"] = ""
    with pytest.raises(Exception) as exc_info:
        InvoicePayload.model_validate(inv).validate_cross_model_statutory_rules()
    assert "2239" in str(exc_info.value)


def test_rule_2240_pydantic_schema_rejection(clean_b2b_invoice):
    inv = copy.deepcopy(clean_b2b_invoice)
    inv["itemdtls"][0]["gstrate"] = 15.0
    with pytest.raises(Exception) as exc_info:
        InvoicePayload.model_validate(inv).validate_cross_model_statutory_rules()
    assert "2240" in str(exc_info.value)


def test_rule_2242_pydantic_schema_rejection(clean_b2b_invoice):
    inv = copy.deepcopy(clean_b2b_invoice)
    inv["buyer"]["pos"] = "96"
    with pytest.raises(Exception) as exc_info:
        InvoicePayload.model_validate(inv).validate_cross_model_statutory_rules()
    assert "2242" in str(exc_info.value)


# ==============================================================================
# AUTO-CORRECT AND BUILD AUDIT LOG TESTS
# ==============================================================================

def test_rule_2238_auto_correct_service_qty(clean_service_invoice):
    inv = copy.deepcopy(clean_service_invoice)
    inv["itemdtls"][0]["qty"] = 0
    payload, audit_logs = InvoicePayload.auto_correct_and_build(inv)
    assert float(payload.itemdtls[0].qty) == 1.0
    assert any("2238" in log.get("category", "") for log in audit_logs)


def test_rule_2239_auto_correct_unmapped_unit(clean_b2b_invoice):
    inv = copy.deepcopy(clean_b2b_invoice)
    inv["itemdtls"][0]["uqc"] = "PIECES"
    inv["itemdtls"][0]["unit"] = "PIECES"
    payload, audit_logs = InvoicePayload.auto_correct_and_build(inv)
    assert payload.itemdtls[0].unit in ("PCS", "NOS")
    assert any("2239" in log.get("category", "") for log in audit_logs)


def test_rule_2240_auto_correct_rate_format(clean_b2b_invoice):
    inv = copy.deepcopy(clean_b2b_invoice)
    inv["itemdtls"][0]["gstrate"] = "18%"
    payload, audit_logs = InvoicePayload.auto_correct_and_build(inv)
    assert payload.itemdtls[0].gstrate == 18.0
    assert any("2240" in log.get("category", "") for log in audit_logs)


def test_rule_2242_auto_correct_pos_96(clean_b2b_invoice):
    inv = copy.deepcopy(clean_b2b_invoice)
    inv["buyer"]["pos"] = "96"
    payload, audit_logs = InvoicePayload.auto_correct_and_build(inv)
    assert payload.buyer.pos == "27"
    assert any("2242" in log.get("category", "") for log in audit_logs)


# ==============================================================================
# DATA LAKEHOUSE PARQUET RECONCILIATION TEST
# ==============================================================================

def test_rules_2238_to_2242_lakehouse_storage_reconciliation(clean_b2b_invoice):
    """Verifies that an invoice corrected across Rules 2238, 2239, 2240, and 2242 flattens and stores properly."""
    inv = copy.deepcopy(clean_b2b_invoice)
    inv["buyer"]["pos"] = "96"  # triggers 2242 -> auto-corrects to 27
    inv["itemdtls"][0]["qty"] = "0"  # triggers 2238 -> auto-corrects to 1.00
    inv["itemdtls"][0]["uqc"] = "PIECES"  # triggers 2239 -> auto-corrects to PCS
    inv["itemdtls"][0]["gstrate"] = "18%"  # triggers 2240 -> auto-corrects to 18.0

    payload, audit_logs = InvoicePayload.auto_correct_and_build(inv)
    flattened = flatten_invoice_payload(payload)

    temp_dir = tempfile.mkdtemp()
    try:
        parquet_path = os.path.join(temp_dir, "test_rules_2238_to_2242.parquet")
        write_parquet(flattened, parquet_path)

        assert os.path.exists(parquet_path)
        df = read_parquet(parquet_path)
        assert len(df) == 1
        assert df["buyer_pos"].iloc[0] == "27"
        assert df["unit"].iloc[0] in ("PCS", "NOS")
        assert float(df["gst_rate"].iloc[0]) == 18.0
        assert float(df["quantity"].iloc[0]) == 1.0
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
