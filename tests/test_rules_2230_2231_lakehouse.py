"""
Test Suite: NIC Error Codes 2230 & 2231 Statutory Compliance & Data Lakehouse Reconciliation.
File: tests/test_rules_2230_2231_lakehouse.py

Validates Indian GST e-Invoicing (NIC / IRP) Statutory Requirements:
1. Error Code 2230:
   "IRN Cannot Be Cancelled Because Active E-Way Bill Exists"
   - Occurs when attempting to call Cancel IRN API for an invoice that already has an active, valid E-Way Bill.
   - Enforces strict dependency ordering: an invoice cannot be deleted/cancelled while an active transport
     document (E-Way Bill) authorizing movement of goods is active on the network.
   Scenarios:
     - ATTEMPTING_TO_CANCEL_IRN_DIRECTLY_WHILE_EWAY_BILL_IS_ACTIVE
     - EWAY_BILL_ALREADY_GENERATED_BY_TRANSPORTER_OR_COUNTERPARTY
     - CANCELLATION_WINDOW_LAPSED_OVER_24_HOURS
     - VALID (No active EWB, within 24 hours)

2. Error Code 2231:
   "Cannot Generate e-Invoice as Supplier GSTIN is SEZ"
   - Under Notification No. 13/2020 – Central Tax, SEZ units are explicitly exempt from mandatory e-invoicing.
   Scenarios:
     - SEZ_UNIT_ATTEMPTING_OUTBOUND_IRN_GENERATION
     - DTA_ENTITY_INVOICING_TO_SEZ_UNIT (Misrouted Flags)
     - MULTI_GSTIN_SETUP_TRIGGERING_WRONG_ENTITY
     - VALID (Regular DTA supplier or DTA supplying to SEZ with SEZWP/SEZWOP)

3. Exemption Master Table (E_INVOICE_EXEMPT_ENTITIES):
   - SEZ Units, Banking/Insurance/NBFCs, GTAs, Passenger Transport, Multiplex/Movie Theatres, Supplies TO SEZ.

4. Lakehouse Data Pipeline:
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
    classify_rule_2230_diagnostic,
    classify_rule_2231_diagnostic,
    E_INVOICE_EXEMPT_ENTITIES,
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
def clean_valid_invoice():
    """A standard clean intra-state invoice with valid seller, buyer, and line items."""
    return {
        "self_gstin": "27AAAAA0000A1Z5",
        "docno": "INV-2026-VAL30",
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
            "gstin": "27BBBBB1111B1Z2",
            "lglnm": "Zenith Retail Distributors",
            "bnm": "Zenith Trade Towers",
            "state": "27",
            "pos": "27",
            "pin": "411001",
            "loc": "Pune"
        },
        "itemdtls": [
            {
                "slno": "1",
                "prdnm": "High Performance Server Blade",
                "hsncd": "84713010",
                "qty": "2.00",
                "uqc": "NOS",
                "unit": "NOS",
                "unitprice": "50000.00",
                "totamt": "100000.00",
                "discount": "0.00",
                "assval": "100000.00",
                "gstrate": 18.0,
                "cgstval": "9000.00",
                "sgstval": "9000.00",
                "igstval": "0.00",
                "totitemval": "118000.00"
            }
        ],
        "valdtls": {
            "assval": "100000.00",
            "cgstval": "9000.00",
            "sgstval": "9000.00",
            "igstval": "0.00",
            "cesval": "0.00",
            "stcesval": "0.00",
            "discount": "0.00",
            "othchrg": "0.00",
            "rndoffamt": "0.00",
            "totinvval": "118000.00"
        }
    }


# ==============================================================================
# RULE 2230: DIAGNOSTIC CLASSIFIER TESTS
# ==============================================================================

def test_rule_2230_scenario_1_direct_cancellation_while_ewb_active():
    """Scenario 1: Calling /Cancel on IRN directly while linked E-Way Bill is active."""
    diag = classify_rule_2230_diagnostic(
        has_active_ewb=True,
        ewb_number="121000987654",
        irn="3b2c01928475a9fbc83726154e2d1c0b3a4f5e6d7c8b9a0f1e2d3c4b5a6f7e8d",
        hours_since_generation=4.5,
        generated_by_transporter=False,
        cancel_reason_code="1",
        cancel_remarks="Data entry error in invoice",
    )
    assert diag["error_code"] == 2230
    assert diag["scenario"] == "ATTEMPTING_TO_CANCEL_IRN_DIRECTLY_WHILE_EWAY_BILL_IS_ACTIVE"
    assert not diag["is_valid"]
    assert diag["action"] == "CANCEL_EWAY_BILL_FIRST"
    assert "sequential_workflow" in diag
    assert len(diag["sequential_workflow"]) == 2
    assert diag["sequential_workflow"][0]["api"] == "/CancelEwb"
    assert diag["sequential_workflow"][1]["api"] == "/CancelIrn"
    assert diag["step_1_cancel_ewb_payload"]["ewbNo"] == 121000987654
    assert diag["step_2_cancel_irn_payload"]["Irn"] == "3b2c01928475a9fbc83726154e2d1c0b3a4f5e6d7c8b9a0f1e2d3c4b5a6f7e8d"


def test_rule_2230_scenario_2_transporter_generated_ewb():
    """Scenario 2: Transporter generated Part-B / EWB on portal blocking cancellation."""
    diag = classify_rule_2230_diagnostic(
        has_active_ewb=True,
        ewb_number="121000987654",
        irn="3b2c01928475a9fbc83726154e2d1c0b3a4f5e6d7c8b9a0f1e2d3c4b5a6f7e8d",
        hours_since_generation=6.0,
        generated_by_transporter=True,
        cancel_reason_code="2",
        cancel_remarks="Data entry error",
    )
    assert diag["error_code"] == 2230
    assert diag["scenario"] == "EWAY_BILL_ALREADY_GENERATED_BY_TRANSPORTER_OR_COUNTERPARTY"
    assert not diag["is_valid"]
    assert diag["action"] == "CANCEL_TRANSPORTER_EWB_PRIOR_TO_IRN_CANCELLATION"
    assert "transporter" in diag["reason"].lower()


def test_rule_2230_scenario_3_cancellation_window_lapsed_over_24h():
    """Scenario 3: Attempting cancellation after 24 hours of IRN generation."""
    diag = classify_rule_2230_diagnostic(
        has_active_ewb=False,
        irn="3b2c01928475a9fbc83726154e2d1c0b3a4f5e6d7c8b9a0f1e2d3c4b5a6f7e8d",
        hours_since_generation=26.5,
        cancel_reason_code="3",
        cancel_remarks="Order cancelled by buyer",
    )
    assert diag["error_code"] == 2230
    assert diag["scenario"] == "CANCELLATION_WINDOW_LAPSED_OVER_24_HOURS"
    assert not diag["is_valid"]
    assert diag["action"] == "ISSUE_CREDIT_NOTE_CRN"
    assert diag["suggested_doc_type"] == "CRN"
    assert "24 hours" in diag["reason"]


def test_rule_2230_valid_direct_cancellation():
    """Valid Scenario: No active EWB and within 24-hour statutory window."""
    diag = classify_rule_2230_diagnostic(
        has_active_ewb=False,
        irn="3b2c01928475a9fbc83726154e2d1c0b3a4f5e6d7c8b9a0f1e2d3c4b5a6f7e8d",
        hours_since_generation=3.0,
        cancel_reason_code="1",
        cancel_remarks="Duplicate entry",
    )
    assert diag["error_code"] is None
    assert diag["scenario"] == "VALID"
    assert diag["is_valid"]
    assert diag["action"] == "CALL_CANCEL_IRN_API"
    assert diag["cancel_irn_payload"]["Irn"] == "3b2c01928475a9fbc83726154e2d1c0b3a4f5e6d7c8b9a0f1e2d3c4b5a6f7e8d"
    assert diag["cancel_irn_payload"]["CnlRsn"] == "1"


# ==============================================================================
# RULE 2230: VALIDATOR & RULES ENGINE CANCELLATION CHECKS
# ==============================================================================

def test_rule_2230_gst_validator_cancellation():
    """Tests GSTValidator.validate_irn_cancellation with active EWB and lapsed window."""
    # 1. Active EWB -> Error 2230
    req_active_ewb = {
        "Irn": "a" * 64,
        "CnlRsn": "1",
        "CnlRem": "Order cancelled",
        "has_active_ewb": True,
        "ewb_number": "121000987654",
        "hours_since_generation": 2.0,
    }
    errors = GSTValidator.validate_irn_cancellation(req_active_ewb)
    assert any(e.get("error_code") == 2230 for e in errors)

    # 2. Lapsed window (> 24h) -> Error 2230
    req_lapsed = {
        "Irn": "a" * 64,
        "CnlRsn": "3",
        "CnlRem": "Order cancelled",
        "has_active_ewb": False,
        "hours_since_generation": 30.0,
    }
    errors = GSTValidator.validate_irn_cancellation(req_lapsed)
    assert any(e.get("error_code") == 2230 for e in errors)

    # 3. Valid cancellation within 24h and no active EWB -> 0 errors
    req_valid = {
        "Irn": "b" * 64,
        "CnlRsn": "2",
        "CnlRem": "Data entry mistake corrected",
        "has_active_ewb": False,
        "hours_since_generation": 5.0,
    }
    errors = GSTValidator.validate_irn_cancellation(req_valid)
    assert len(errors) == 0


def test_rule_2230_rules_engine_cancellation():
    """Tests RulesEngine.validate_irn_cancellation with transporter EWB."""
    req_transporter = {
        "Irn": "c" * 64,
        "CnlRsn": "4",
        "CnlRem": "Transporter error",
        "has_active_ewb": True,
        "ewb_number": "999888777666",
        "generated_by_transporter": True,
        "hours_since_generation": 1.0,
    }
    errors = RulesEngine.validate_irn_cancellation(req_transporter)
    assert any(e.get("error_code") == 2230 for e in errors)


# ==============================================================================
# RULE 2231: DIAGNOSTIC CLASSIFIER TESTS
# ==============================================================================

def test_rule_2231_scenario_1_sez_outbound_generation():
    """Scenario 1: SEZ Unit Attempting Outbound IRN Generation."""
    diag = classify_rule_2231_diagnostic(
        supplier_gstin="27AAACS1234A1Z5",
        is_supplier_sez=True,
        trancatg="B2B",
    )
    assert diag["error_code"] == 2231
    assert diag["scenario"] == "SEZ_UNIT_ATTEMPTING_OUTBOUND_IRN_GENERATION"
    assert not diag["is_valid"]
    assert diag["action"] == "DO_NOT_PUSH_SEZ_OUTBOUND_TO_IRP"
    assert diag["irnreq"] == "N"
    assert "Notification No. 13/2020" in diag["reason"]


def test_rule_2231_scenario_2_dta_invoicing_to_sez_misrouted():
    """Scenario 2: DTA Entity Invoicing to SEZ Unit (Misrouted Flags)."""
    diag = classify_rule_2231_diagnostic(
        supplier_gstin="27AAAAA0000A1Z5",
        is_supplier_sez=True,
        trancatg="SEZWP",
        is_dta_to_sez=True,
    )
    assert diag["error_code"] == 2231
    assert diag["scenario"] == "DTA_ENTITY_INVOICING_TO_SEZ_UNIT"
    assert not diag["is_valid"]
    assert diag["action"] == "SET_SUPPLY_TYPE_SEZWP_OR_SEZWOP"
    assert "DTA units selling to SEZ must generate e-Invoices" in diag["reason"]


def test_rule_2231_scenario_3_multi_gstin_setup():
    """Scenario 3: Multi-GSTIN Setup Triggering Wrong Entity."""
    diag = classify_rule_2231_diagnostic(
        supplier_gstin="27AAACS1234A1Z5",
        is_supplier_sez=True,
        is_multi_gstin_setup=True,
    )
    assert diag["error_code"] == 2231
    assert diag["scenario"] == "MULTI_GSTIN_SETUP_TRIGGERING_WRONG_ENTITY"
    assert not diag["is_valid"]
    assert diag["action"] == "FILTER_SEZ_GSTIN_IN_INTEGRATION_MIDDLEWARE"
    assert diag["irnreq"] == "N"


def test_rule_2231_valid_dta_outbound_to_sez():
    """Valid Scenario: DTA unit supplying to SEZ unit under SEZWP (Not exempt, IRN required)."""
    diag = classify_rule_2231_diagnostic(
        supplier_gstin="27AAAAA0000A1Z5",
        is_supplier_sez=False,
        trancatg="SEZWP",
        is_dta_to_sez=True,
    )
    assert diag["error_code"] is None
    assert diag["scenario"] == "VALID"
    assert diag["is_valid"]


def test_rule_2231_valid_regular_taxpayer():
    """Valid Scenario: Standard regular taxpayer supplier."""
    diag = classify_rule_2231_diagnostic(
        supplier_gstin="27AAAAA0000A1Z5",
        is_supplier_sez=False,
        trancatg="B2B",
    )
    assert diag["error_code"] is None
    assert diag["is_valid"]


# ==============================================================================
# RULE 2231: EXEMPTION MASTER TABLE TESTS
# ==============================================================================

def test_exemption_master_table_entries():
    """Verifies statutory exemption entries under Notification 13/2020-CT."""
    assert "SEZ_UNIT" in E_INVOICE_EXEMPT_ENTITIES
    assert E_INVOICE_EXEMPT_ENTITIES["SEZ_UNIT"]["must_generate_irn"] == "No"
    assert "13/2020" in E_INVOICE_EXEMPT_ENTITIES["SEZ_UNIT"]["notification"]

    assert "BANKING_INSURANCE_NBFC" in E_INVOICE_EXEMPT_ENTITIES
    assert E_INVOICE_EXEMPT_ENTITIES["BANKING_INSURANCE_NBFC"]["must_generate_irn"] == "No"

    assert "GTA" in E_INVOICE_EXEMPT_ENTITIES
    assert E_INVOICE_EXEMPT_ENTITIES["GTA"]["must_generate_irn"] == "No"

    assert "PASSENGER_TRANSPORT" in E_INVOICE_EXEMPT_ENTITIES
    assert E_INVOICE_EXEMPT_ENTITIES["PASSENGER_TRANSPORT"]["must_generate_irn"] == "No"

    assert "MULTIPLEX_THEATRE" in E_INVOICE_EXEMPT_ENTITIES
    assert E_INVOICE_EXEMPT_ENTITIES["MULTIPLEX_THEATRE"]["must_generate_irn"] == "No"

    assert "DTA_TO_SEZ" in E_INVOICE_EXEMPT_ENTITIES
    assert E_INVOICE_EXEMPT_ENTITIES["DTA_TO_SEZ"]["must_generate_irn"] == "Yes"


# ==============================================================================
# RULE 2231: PRE-API VALIDATOR TESTS
# ==============================================================================

def test_rule_2231_gst_validator_catches_sez_supplier(clean_valid_invoice):
    """GSTValidator catches SEZ supplier flag and emits Error 2231."""
    inv = dict(clean_valid_invoice)
    inv["is_supplier_sez"] = True
    errors = GSTValidator.validate_invoice(inv)
    assert any(e.get("error_code") == 2231 for e in errors)


def test_rule_2231_rules_engine_catches_sez_supplier(clean_valid_invoice):
    """RulesEngine catches SEZ supplier flag and emits Error 2231."""
    inv = dict(clean_valid_invoice)
    inv["supplier"] = dict(inv["supplier"])
    inv["supplier"]["is_supplier_sez"] = True
    errors = RulesEngine.validate_invoice(inv)
    assert any(e.get("error_code") == 2231 for e in errors)


def test_rule_2231_pydantic_schema_rejection(clean_valid_invoice):
    """InvoicePayload cross-model validation raises validation error (NIC-2231) for SEZ supplier."""
    inv = dict(clean_valid_invoice)
    inv["is_supplier_sez"] = True
    with pytest.raises(Exception) as exc_info:
        InvoicePayload.model_validate(inv)
    err_str = str(exc_info.value)
    assert "2231" in err_str
    assert "13/2020" in err_str


def test_rule_2231_auto_correct_and_build(clean_valid_invoice):
    """auto_correct_and_build detects SEZ supplier, sets irnreq='N', and logs audit trail."""
    inv = dict(clean_valid_invoice)
    inv["is_supplier_sez"] = True
    model, audit_logs = InvoicePayload.auto_correct_and_build(inv)
    assert model.irnreq == "N"
    assert any("2231" in log.get("category", "") for log in audit_logs)


# ==============================================================================
# DATA LAKEHOUSE PARQUET RECONCILIATION
# ==============================================================================

def test_lakehouse_parquet_persistence_roundtrip(clean_valid_invoice):
    """Tests flattening, Parquet storage, and round-trip read with statutory columns."""
    model = InvoicePayload.model_validate(clean_valid_invoice)
    rows = flatten_invoice_payload(model)
    row = rows[0] if isinstance(rows, list) else rows

    assert row["invoice_id"] == "INV-2026-VAL30"
    assert row["supplier_gstin"] == "27AAAAA0000A1Z5"
    assert float(row["inv_total_value"]) == 118000.00
    assert float(row["inv_cgst_amount"]) == 9000.00
    assert float(row["inv_sgst_amount"]) == 9000.00

    temp_dir = tempfile.mkdtemp()
    try:
        parquet_path = os.path.join(temp_dir, "test_rules_2230_2231.parquet")
        write_parquet(rows, parquet_path)

        df = read_parquet(parquet_path)
        assert len(df) == 1
        assert df["invoice_id"].iloc[0] == "INV-2026-VAL30"
        assert df["supplier_gstin"].iloc[0] == "27AAAAA0000A1Z5"
        assert float(df["inv_total_value"].iloc[0]) == 118000.00
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

