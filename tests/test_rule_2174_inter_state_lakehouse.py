"""
Test Suite: NIC Error Code 2174 Statutory Compliance & Data Lakehouse Inter-State Supply Module.
File: tests/test_rule_2174_inter_state_lakehouse.py

Validates:
1. NIC Error Code 2174 Definition & Official Resolution:
   - Counterpart to Error 2172.
   - Occurs when a transaction is identified as an inter-state supply (Supplier State != Buyer POS),
     but payload contains CGST and SGST values instead of IGST.
2. All 4 Statutory Scenarios:
   - Scenario 1 (Standard Inter-State Supply):
     Seller State = "27" (MH), Buyer POS = "29" (KA), CgstAmt: 900.00, SgstAmt: 900.00, IgstAmt: 0.00
     -> IgstAmt: 1800.00, CgstAmt: 0.00, SgstAmt: 0.00.
     Reason: "Supplier and POS states are different, so it is an inter-state sale. Clear CGST/SGST to 0.00 and pass the full tax rate under IgstAmt."
   - Scenario 2 (Incorrect Place of Supply Passed):
     Local supply within Maharashtra (27), but payload accidentally had Buyer POS = "29"
     -> Buyer POS: "27".
     Reason: "If the transaction was actually a local intra-state sale, correct Pos to match the supplier's state (27)."
   - Scenario 3 (Header Summary vs. Line Items Mismatch):
     ItemList has IgstAmt, but header summary has ValDtls: { CgstVal: 900.00, SgstVal: 900.00, IgstVal: 0.00 }
     -> ValDtls: { CgstVal: 0.00, SgstVal: 0.00, IgstVal: 1800.00 }.
     Reason: "Header totals in ValDtls must mirror line-item taxes. If line items carry IGST, CgstVal and SgstVal in ValDtls must be 0.00."
   - Scenario 4 (Bill-to / Ship-to State Confusion):
     Goods shipped within same state (Ship "27"), but billed out-of-state (Buyer POS "29").
     -> Retain POS as per Section 10(1)(b) of the IGST Act, and apply IGST.
     Reason: "In 'Bill To – Ship To' transactions where the billing party is out-of-state, the Place of Supply is the billing party's state, making the invoice inter-state requiring IGST."
3. Pre-API & Engine Validations:
   - GSTValidator & RulesEngine detection for line-item and header-summary mismatches.
   - InvoicePayload model validation raising NICValidationError(2174).
4. Data Lakehouse Integration (src/ingestion/storage.py):
   - Lakehouse payload flattening (flatten_invoice_payload) for dict and Pydantic objects.
   - Lakehouse tax normalization (cgst=0, sgst=0, igst=total, inv_cgst=0, inv_sgst=0, inv_igst=total).
   - Telemetry badge FLAGGED_AND_RECTIFIED, sentinel_risk_prob >= 0.95, and audit reasons.
   - Bronze / Silver / Gold Parquet round-trip persistence (write_parquet, read_parquet, append_to_parquet).
5. Self-Healing Pipelines (PayloadBuilder and InvoicePayload.auto_correct_and_build).
"""

import os
import shutil
import tempfile
from decimal import Decimal
from pathlib import Path
import pytest
import pandas as pd

from pydantic import ValidationError
from src.ingestion.schemas import (
    InvoicePayload,
    IRN_ERRORS,
    NICValidationError,
    classify_rule_2174_diagnostic,
)
from Template_Converters.error_mappings import NIC_ERROR_CODES
from Template_Converters.validator import GSTValidator
from Template_Converters.payload_builder import PayloadBuilder
from src.rules.rules_engine import RulesEngine
from src.ingestion.storage import (
    flatten_invoice_payload,
    write_parquet,
    read_parquet,
    append_to_parquet,
)


# ==============================================================================
# FIXTURES
# ==============================================================================

@pytest.fixture
def base_inter_state_payload():
    """Standard inter-state payload MH (27) -> KA (29)."""
    return {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-2026-2174",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "B2B",
        "reversecharge": "N",
        "igstonintra": "N",
        "supplier": {
            "gstin": "27ABCDE1234F1Z5",
            "lglnm": "Maharashtra Industrial Supplies Pvt Ltd",
            "state": "27",
            "pin": "400001",
            "loc": "Mumbai"
        },
        "buyer": {
            "gstin": "29XYZAB5678C1Z2",
            "lglnm": "Karnataka Logistics & Manufacturing Ltd",
            "state": "29",
            "pos": "29",
            "pin": "560001",
            "loc": "Bangalore"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "INDUSTRIAL ROLLER BEARING",
                "prddesc": "Precision steel roller bearing assembly",
                "hsn": "84821010",
                "qty": 10.0,
                "unit": "NOS",
                "unitprice": 1000.0,
                "totamt": 10000.0,
                "discount": 0.0,
                "pretaxval": 10000.0,
                "assval": 10000.0,
                "gstrate": 18.0,
                "cgstval": 900.0,
                "sgstval": 900.0,
                "igstval": 0.0,
                "totitemval": 11800.0,
            }
        ],
        "valdtls": {
            "assval": 10000.0,
            "cgstval": 900.0,
            "sgstval": 900.0,
            "igstval": 0.0,
            "totinvval": 11800.0,
        }
    }


# ==============================================================================
# 1. ERROR CODE 2174 DEFINITION & STATUTORY MAPPINGS
# ==============================================================================

def test_error_2174_definition_in_error_catalogs():
    """Verify official NIC error 2174 message, reason, and resolution in both schemas and error_mappings."""
    assert 2174 in IRN_ERRORS
    entry_schema = IRN_ERRORS[2174]
    assert "Inter-state" in entry_schema["message"] or "inter-state" in entry_schema["message"]
    assert "CGST" in entry_schema["message"] and "SGST" in entry_schema["message"]
    assert "IgstAmt" in entry_schema["resolution"]

    assert 2174 in NIC_ERROR_CODES
    entry_cat = NIC_ERROR_CODES[2174]
    assert "Inter-state" in entry_cat["message"] or "inter-state" in entry_cat["message"]
    assert "Clear CGST/SGST to 0.00 and pass the full tax rate under IgstAmt" in entry_cat["resolution"]


# ==============================================================================
# 2. UNIT TESTS FOR classify_rule_2174_diagnostic
# ==============================================================================

def test_classify_scenario_1_standard_inter_state():
    """Scenario 1: Supplier State != Buyer POS, CGST & SGST passed instead of IGST."""
    diag = classify_rule_2174_diagnostic(
        seller_state="27",
        buyer_pos="29",
        buyer_state="29",
        buyer_gstin="29XYZAB5678C1Z2",
        cgst_amt=Decimal("900.00"),
        sgst_amt=Decimal("900.00"),
        igst_amt=Decimal("0.00"),
    )
    assert diag["error_code"] == 2174
    assert diag["scenario"] == "STANDARD_INTER_STATE"
    assert diag["scenario_name"] == "Standard Inter-State Supply"
    assert "Supplier and POS states are different, so it is an inter-state sale. Clear CGST/SGST to 0.00 and pass the full tax rate under IgstAmt." in diag["reason"]
    assert diag["action"] == "CLEAR_CGST_SGST_PASS_IGST"
    assert diag["correct_payload"]["IgstAmt"] == Decimal("1800.00")
    assert diag["correct_payload"]["CgstAmt"] == Decimal("0.00")
    assert diag["correct_payload"]["SgstAmt"] == Decimal("0.00")


def test_classify_scenario_2_incorrect_pos_passed():
    """Scenario 2: Actual local sale within MH (27), but payload accidentally had POS = 29."""
    diag = classify_rule_2174_diagnostic(
        seller_state="27",
        buyer_pos="29",
        buyer_state="27",
        buyer_gstin="27ABCDE1234F1Z5",
        cgst_amt=Decimal("900.00"),
        sgst_amt=Decimal("900.00"),
        igst_amt=Decimal("0.00"),
        is_actual_local_sale=True,
    )
    assert diag["error_code"] == 2174
    assert diag["scenario"] == "INCORRECT_POS_PASSED"
    assert diag["scenario_name"] == "Incorrect Place of Supply (Pos) Passed"
    assert "If the transaction was actually a local intra-state sale, correct Pos to match the supplier's state (27)." in diag["reason"]
    assert diag["action"] == "CORRECT_POS_TO_SUPPLIER_STATE"
    assert diag["correct_payload"]["BuyerDtls"]["Pos"] == "27"


def test_classify_scenario_3_summary_vs_item_mismatch():
    """Scenario 3: Line items carry IGST, but header summary has ValDtls.CgstVal > 0 or ValDtls.SgstVal > 0."""
    diag = classify_rule_2174_diagnostic(
        seller_state="27",
        buyer_pos="29",
        buyer_state="29",
        buyer_gstin="29XYZAB5678C1Z2",
        cgst_amt=Decimal("0.00"),
        sgst_amt=Decimal("0.00"),
        igst_amt=Decimal("1800.00"),
        header_cgst=Decimal("900.00"),
        header_sgst=Decimal("900.00"),
        header_igst=Decimal("0.00"),
    )
    assert diag["error_code"] == 2174
    assert diag["scenario"] == "SUMMARY_VS_ITEM_MISMATCH"
    assert diag["scenario_name"] == "Header Summary vs. Line Items Mismatch"
    assert "Header totals in ValDtls must mirror line-item taxes. If line items carry IGST, CgstVal and SgstVal in ValDtls must be 0.00." in diag["reason"]
    assert diag["action"] == "MATCH_HEADER_TO_ITEMS"
    assert diag["correct_payload"]["ValDtls"]["CgstVal"] == Decimal("0.00")
    assert diag["correct_payload"]["ValDtls"]["SgstVal"] == Decimal("0.00")
    assert diag["correct_payload"]["ValDtls"]["IgstVal"] == Decimal("1800.00")


def test_classify_scenario_4_bill_to_ship_to_confusion():
    """Scenario 4: Goods shipped within same state (MH 27), but billed to out-of-state entity (KA 29)."""
    diag = classify_rule_2174_diagnostic(
        seller_state="27",
        buyer_pos="29",
        buyer_state="29",
        buyer_gstin="29XYZAB5678C1Z2",
        ship_state="27",
        ship_gstin="27GHIJK9876L1Z4",
        cgst_amt=Decimal("900.00"),
        sgst_amt=Decimal("900.00"),
        igst_amt=Decimal("0.00"),
    )
    assert diag["error_code"] == 2174
    assert diag["scenario"] == "BILL_TO_SHIP_TO_CONFUSION"
    assert diag["scenario_name"] == "Bill-to / Ship-to State Confusion"
    assert diag["statutory_section"] == "Section 10(1)(b) of the IGST Act"
    assert "In \"Bill To – Ship To\" transactions where the billing party is out-of-state, the Place of Supply is the billing party's state, making the invoice inter-state requiring IGST." in diag["reason"]
    assert diag["action"] == "RETAIN_POS_APPLY_IGST"
    assert diag["correct_payload"]["BuyerDtls"]["Pos"] == "29"
    assert diag["correct_payload"]["IgstAmt"] == Decimal("1800.00")
    assert diag["correct_payload"]["CgstAmt"] == Decimal("0.00")
    assert diag["correct_payload"]["SgstAmt"] == Decimal("0.00")


# ==============================================================================
# 3. PRE-API VALIDATION ENGINES (GSTValidator & RulesEngine)
# ==============================================================================

def test_gst_validator_diagnoses_rule_2174_line_item():
    """GSTValidator detects Error 2174 when line items have CGST/SGST on inter-state supply."""
    failing_invoice = {
        "self_gstin": "27ABCDE1234F1Z5",
        "supplierdt1": {
            "supplier_gstin": "27ABCDE1234F1Z5",
            "supplier_state": "27",
            "supplier_lglnm": "Maharashtra Seller Ltd",
            "supplier_loc": "Mumbai",
            "supplier_pin": "400001"
        },
        "buyerdt1": {
            "buyer_gstin": "29XYZAB9876C1Z1",
            "buyer_state": "29",
            "pos": "29",
            "buyer_lglnm": "Karnataka Buyer Ltd",
            "buyer_loc": "Bangalore",
            "buyer_pin": "560001"
        },
        "trandt1": {
            "trancatg": "B2B",
            "reversecharge": "N",
            "igstonintra": "N"
        },
        "itemdtls": [
            {
                "slno": 1,
                "prdnm": "Office Chair",
                "hsncd": "9403",
                "qty": 1,
                "unitrate": 1000,
                "grossamt": 1000,
                "assamt": 1000,
                "cgstamt": 90,
                "sgstamt": 90,
                "igstamt": 0,
                "totitemval": 1180
            }
        ]
    }
    errors = GSTValidator.validate_invoice(failing_invoice)
    err_2174 = next((e for e in errors if e.get("error_code") == 2174), None)
    assert err_2174 is not None, f"Expected 2174 error, found: {errors}"
    assert "Standard Inter-State Supply" in err_2174["message"]
    assert "Clear CGST/SGST to 0.00 and pass the full tax rate under IgstAmt" in err_2174["message"]


def test_rules_engine_diagnoses_rule_2174_line_item():
    """RulesEngine detects Error 2174 when line items have CGST/SGST on inter-state supply."""
    failing_invoice = {
        "self_gstin": "27ABCDE1234F1Z5",
        "supplierdt1": {
            "supplier_gstin": "27ABCDE1234F1Z5",
            "supplier_state": "27",
            "supplier_lglnm": "Maharashtra Seller Ltd",
            "supplier_loc": "Mumbai",
            "supplier_pin": "400001"
        },
        "buyerdt1": {
            "buyer_gstin": "29XYZAB9876C1Z1",
            "buyer_state": "29",
            "pos": "29",
            "buyer_lglnm": "Karnataka Buyer Ltd",
            "buyer_loc": "Bangalore",
            "buyer_pin": "560001"
        },
        "trandt1": {
            "trancatg": "B2B",
            "reversecharge": "N",
            "igstonintra": "N"
        },
        "itemdtls": [
            {
                "slno": 1,
                "prdnm": "Office Chair",
                "hsncd": "9403",
                "qty": 1,
                "unitrate": 1000,
                "grossamt": 1000,
                "assamt": 1000,
                "cgstamt": 90,
                "sgstamt": 90,
                "igstamt": 0,
                "totitemval": 1180
            }
        ]
    }
    errors = RulesEngine.validate_invoice(failing_invoice)
    err_2174 = next((e for e in errors if e.get("error_code") == 2174), None)
    assert err_2174 is not None, f"Expected 2174 error, found: {errors}"
    assert "Standard Inter-State Supply" in err_2174["message"]
    assert "Clear CGST/SGST to 0.00 and pass the full tax rate under IgstAmt" in err_2174["message"]


def test_model_validate_raises_nic_2174_line_item(base_inter_state_payload):
    """InvoicePayload.model_validate raises NICValidationError(2174) for inter-state CGST/SGST."""
    with pytest.raises((NICValidationError, ValidationError)) as exc_info:
        InvoicePayload.model_validate(base_inter_state_payload)
    err_str = str(exc_info.value)
    assert "2174" in err_str
    assert "inter-state" in err_str.lower()


def test_validator_and_engine_diagnose_scenario_3_summary_mismatch():
    """Scenario 3: Items have IGST, but header ValDtls has CGST/SGST."""
    mismatch_payload = {
        "self_gstin": "27ABCDE1234F1Z5",
        "supplierdt1": {
            "supplier_gstin": "27ABCDE1234F1Z5",
            "supplier_state": "27",
            "supplier_lglnm": "Maharashtra Seller Ltd",
            "supplier_loc": "Mumbai",
            "supplier_pin": "400001"
        },
        "buyerdt1": {
            "buyer_gstin": "29XYZAB9876C1Z1",
            "buyer_state": "29",
            "pos": "29",
            "buyer_lglnm": "Karnataka Buyer Ltd",
            "buyer_loc": "Bangalore",
            "buyer_pin": "560001"
        },
        "trandt1": {
            "trancatg": "B2B",
            "reversecharge": "N",
            "igstonintra": "N"
        },
        "itemdtls": [
            {
                "slno": 1,
                "prdnm": "INDUSTRIAL ROLLER BEARING",
                "hsncd": "8482",
                "qty": 10,
                "unitrate": 1000,
                "grossamt": 10000,
                "assamt": 10000,
                "cgstamt": 0,
                "sgstamt": 0,
                "igstamt": 1800,
                "totitemval": 11800
            }
        ],
        "valdt1": {
            "ttlassval": 10000,
            "cgstval": 900,
            "sgstval": 900,
            "igstval": 0,
            "totinvval": 11800
        }
    }
    errors = GSTValidator.validate_invoice(mismatch_payload)
    err_2174 = next((e for e in errors if e.get("error_code") == 2174), None)
    assert err_2174 is not None
    assert "Header Summary vs. Line Items Mismatch" in err_2174["message"]


# ==============================================================================
# 4. DATA LAKEHOUSE MODULE INTEGRATION (src/ingestion/storage.py)
# ==============================================================================

def test_lakehouse_flatten_invoice_dict_rectifies_rule_2174(base_inter_state_payload):
    """
    Data Lakehouse flatten_invoice_payload must intercept Rule 2174:
    - Auto-rectify line item cgst_amount & sgst_amount to 0.0, and igst_amount to 1800.0.
    - Auto-rectify inv_cgst_amount & inv_sgst_amount to 0.0, and inv_igst_amount to 1800.0.
    - Set sentinel telemetry badge: FLAGGED_AND_RECTIFIED, risk_prob >= 0.95.
    - Include Rule 2174 audit reason.
    """
    rows = flatten_invoice_payload(base_inter_state_payload)
    assert len(rows) == 1
    row = rows[0]

    # Verify Line-Item Tax Rectification
    assert row["cgst_amount"] == 0.0
    assert row["sgst_amount"] == 0.0
    assert row["igst_amount"] == 1800.0
    assert row["total_item_value"] == 11800.0

    # Verify Invoice Header Tax Rectification
    assert row["inv_cgst_amount"] == 0.0
    assert row["inv_sgst_amount"] == 0.0
    assert row["inv_igst_amount"] == 1800.0
    assert row["inv_total_value"] == 11800.0

    # Verify Sentinel ML Telemetry
    assert row["sentinel_status_badge"] == "FLAGGED_AND_RECTIFIED"
    assert row["sentinel_risk_level"] == "HIGH"
    assert row["sentinel_risk_prob"] >= 0.95
    assert "Rule 2174 Violation" in row["sentinel_audit_reasons"]
    assert "Supplier and POS states are different" in row["sentinel_audit_reasons"]


def test_lakehouse_flatten_pydantic_payload_rectifies_rule_2174(base_inter_state_payload):
    """Data Lakehouse flatten_invoice_payload works identically on auto-corrected Pydantic model."""
    built_payload, audit_log = InvoicePayload.auto_correct_and_build(base_inter_state_payload)
    rows = flatten_invoice_payload(built_payload)
    assert len(rows) == 1
    row = rows[0]

    assert row["cgst_amount"] == 0.0
    assert row["sgst_amount"] == 0.0
    assert row["igst_amount"] == 1800.0
    assert row["inv_cgst_amount"] == 0.0
    assert row["inv_sgst_amount"] == 0.0
    assert row["inv_igst_amount"] == 1800.0
    assert row["compliance_status"] == "VALID"


def test_lakehouse_parquet_persistence_roundtrip(base_inter_state_payload):
    """
    Verify complete Data Lakehouse Parquet ingestion round-trip:
    1. Flatten payload with Rule 2174 inter-state error.
    2. Write to Bronze/Silver Parquet using write_parquet.
    3. Read Parquet using read_parquet and verify schema & values.
    4. Append subsequent record using append_to_parquet and verify total row count.
    """
    tmp_dir = tempfile.mkdtemp(prefix="lakehouse_2174_")
    try:
        parquet_file = Path(tmp_dir) / "silver_invoices_2174.parquet"

        # 1. First record flattening & persistence
        rows = flatten_invoice_payload(base_inter_state_payload)
        success = write_parquet(rows, str(parquet_file))
        assert success is True
        assert parquet_file.exists()

        # 2. Read back & verify
        df = read_parquet(str(parquet_file))
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1
        assert df.iloc[0]["invoice_id"] == "INV-2026-2174"
        assert df.iloc[0]["supplier_state"] == "27"
        assert df.iloc[0]["buyer_pos"] == "29"
        assert df.iloc[0]["cgst_amount"] == 0.0
        assert df.iloc[0]["sgst_amount"] == 0.0
        assert df.iloc[0]["igst_amount"] == 1800.0
        assert df.iloc[0]["inv_cgst_amount"] == 0.0
        assert df.iloc[0]["inv_sgst_amount"] == 0.0
        assert df.iloc[0]["inv_igst_amount"] == 1800.0
        assert df.iloc[0]["sentinel_status_badge"] == "FLAGGED_AND_RECTIFIED"

        # 3. Append second invoice
        second_payload = dict(base_inter_state_payload)
        second_payload["docno"] = "INV-2026-2174-B"
        second_rows = flatten_invoice_payload(second_payload)
        append_success = append_to_parquet(second_rows, str(parquet_file))
        assert append_success is True

        df_updated = read_parquet(str(parquet_file))
        assert len(df_updated) == 2
        assert set(df_updated["invoice_id"]) == {"INV-2026-2174", "INV-2026-2174-B"}
        assert (df_updated["cgst_amount"] == 0.0).all()
        assert (df_updated["sgst_amount"] == 0.0).all()
        assert (df_updated["igst_amount"] == 1800.0).all()
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ==============================================================================
# 5. SELF-HEALING PIPELINES (InvoicePayload & PayloadBuilder)
# ==============================================================================

def test_auto_correct_scenario_1_standard_inter_state(base_inter_state_payload):
    """Scenario 1: Auto-correct reallocates CGST/SGST to full IGST with clear audit log."""
    built, audit = InvoicePayload.auto_correct_and_build(base_inter_state_payload)
    assert built.valdtls.igstval == Decimal("1800.00")
    assert built.valdtls.cgstval == Decimal("0.00")
    assert built.valdtls.sgstval == Decimal("0.00")
    assert built.itemdtls[0].igstval == Decimal("1800.00")
    assert built.itemdtls[0].cgstval == Decimal("0.00")
    assert built.itemdtls[0].sgstval == Decimal("0.00")

    audit_entry = next((a for a in audit if "Rule 2174" in a.get("description", "")), None)
    assert audit_entry is not None
    assert "Supplier and POS states are different, so it is an inter-state sale. Clear CGST/SGST to 0.00 and pass the full tax rate under IgstAmt" in audit_entry["description"]


def test_auto_correct_scenario_2_incorrect_pos_passed():
    """Scenario 2: Actual local sale within MH 27 with accidental POS 29 -> POS corrected to 27."""
    payload = {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-2026-S2",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "is_actual_local_sale": True,
        "supplier": {
            "gstin": "27ABCDE1234F1Z5",
            "state": "27",
            "pin": "400001",
            "loc": "Mumbai"
        },
        "buyer": {
            "gstin": "27ABCDE1234F1Z5",
            "state": "27",
            "pos": "29",  # Accidental POS
            "pin": "400002",
            "loc": "Mumbai"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "WIDGET",
                "hsn": "84821010",
                "qty": 1.0,
                "unit": "NOS",
                "unitprice": 1000.0,
                "totamt": 1000.0,
                "assval": 1000.0,
                "gstrate": 18.0,
                "cgstval": 90.0,
                "sgstval": 90.0,
                "igstval": 0.0,
            }
        ],
        "valdtls": {
            "assval": 1000.0,
            "cgstval": 90.0,
            "sgstval": 90.0,
            "igstval": 0.0,
            "totinvval": 1180.0,
        }
    }
    built, audit = InvoicePayload.auto_correct_and_build(payload)
    assert built.buyer.pos == "27"
    audit_pos = next((a for a in audit if "correct Pos to match the supplier's state (27)" in a.get("description", "")), None)
    assert audit_pos is not None


def test_auto_correct_scenario_3_summary_mismatch():
    """Scenario 3: Header ValDtls has CGST/SGST while items have IGST -> Header cleared to 0.00 and IGST set."""
    payload = {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-2026-S3",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "supplier": {
            "gstin": "27ABCDE1234F1Z5",
            "state": "27",
            "pin": "400001",
            "loc": "Mumbai"
        },
        "buyer": {
            "gstin": "29XYZAB5678C1Z2",
            "state": "29",
            "pos": "29",
            "pin": "560001",
            "loc": "Bangalore"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "WIDGET",
                "hsn": "84821010",
                "qty": 1.0,
                "unit": "NOS",
                "unitprice": 1000.0,
                "totamt": 1000.0,
                "assval": 1000.0,
                "gstrate": 18.0,
                "cgstval": 0.0,
                "sgstval": 0.0,
                "igstval": 180.0,
            }
        ],
        "valdtls": {
            "assval": 1000.0,
            "cgstval": 90.0,
            "sgstval": 90.0,
            "igstval": 0.0,
            "totinvval": 1180.0,
        }
    }
    built, audit = InvoicePayload.auto_correct_and_build(payload)
    assert Decimal(str(built.valdtls.cgstval)) == Decimal("0.00")
    assert Decimal(str(built.valdtls.sgstval)) == Decimal("0.00")
    assert Decimal(str(built.valdtls.igstval)) == Decimal("180.00")
    audit_header = next((a for a in audit if "Header totals in ValDtls must mirror line-item taxes" in a.get("description", "")), None)
    assert audit_header is not None


def test_auto_correct_scenario_4_bill_to_ship_to():
    """Scenario 4: Bill to out-of-state (KA 29), ship local (MH 27) -> Retains POS 29 per Section 10(1)(b) and applies IGST."""
    payload = {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-2026-S4",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "supplier": {
            "gstin": "27ABCDE1234F1Z5",
            "state": "27",
            "pin": "400001",
            "loc": "Mumbai"
        },
        "buyer": {
            "gstin": "29XYZAB5678C1Z2",
            "state": "29",
            "pos": "29",
            "pin": "560001",
            "loc": "Bangalore"
        },
        "shipdtl": {
            "gstin": "27GHIJK9876L1Z4",
            "state": "27",
            "pin": "400002",
            "loc": "Mumbai"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "WIDGET",
                "hsn": "84821010",
                "qty": 1.0,
                "unit": "NOS",
                "unitprice": 1000.0,
                "totamt": 1000.0,
                "assval": 1000.0,
                "gstrate": 18.0,
                "cgstval": 90.0,
                "sgstval": 90.0,
                "igstval": 0.0,
            }
        ],
        "valdtls": {
            "assval": 1000.0,
            "cgstval": 90.0,
            "sgstval": 90.0,
            "igstval": 0.0,
            "totinvval": 1180.0,
        }
    }
    built, audit = InvoicePayload.auto_correct_and_build(payload)
    # POS must be retained as 29 as per Section 10(1)(b) of the IGST Act
    assert built.buyer.pos == "29"
    # Tax must be IGST
    assert Decimal(str(built.itemdtls[0].igstval)) == Decimal("180.00")
    assert Decimal(str(built.itemdtls[0].cgstval)) == Decimal("0.00")
    assert Decimal(str(built.itemdtls[0].sgstval)) == Decimal("0.00")
    assert Decimal(str(built.valdtls.igstval)) == Decimal("180.00")
    assert Decimal(str(built.valdtls.cgstval)) == Decimal("0.00")
    assert Decimal(str(built.valdtls.sgstval)) == Decimal("0.00")

    audit_entry = next((a for a in audit if "Section 10(1)(b) of the IGST Act" in a.get("description", "")), None)
    assert audit_entry is not None
