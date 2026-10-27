"""
Test Suite: NIC Error Code 2172 Statutory Compliance & Data Lakehouse Intra-State Supply Module.
File: tests/test_rule_2172_intra_state_lakehouse.py

Validates Indian GST e-Invoicing (NIC / IRP) Error Code 2172:
"For Intra-state transaction, IGST amount is not applicable; only CGST and SGST amounts are applicable"
Across all 4 Statutory Scenarios directly within the Data Lakehouse module (src/ingestion/storage.py):

1. Standard Intra-State Transaction:
   Seller State = "27", Buyer POS = "27"
   Sent: IgstAmt: 1800.00, CgstAmt: 0.00, SgstAmt: 0.00
   Lakehouse Rectification: IgstAmt: 0.00, CgstAmt: 900.00, SgstAmt: 900.00,
   inv_cgst_amount: 900.00, inv_sgst_amount: 900.00, inv_igst_amount: 0.00
   Reason: "Same supplier state and POS means regular intra-state supply. Clear IgstAmt and split tax equally between CGST and SGST."

2. Wrong Place of Supply (Pos) Entered:
   Seller State = "27", Recipient destination in Karnataka (29), but payload has BuyerDtls: { Pos: "27" }
   Sent: IgstAmt: 1800.00 with BuyerDtls: { Pos: "27" }
   Lakehouse Rectification: buyer_pos: "29", retain igst_amount: 1800.00, cgst_amount: 0.00, sgst_amount: 0.00
   Reason: "If this was actually an inter-state sale to an out-of-state recipient, fix the recipient's Pos code to match the destination state."

3. Valid Exceptional Intra-State IGST Supply:
   Seller State = "27", Buyer POS = "27", transaction legally requires IGST on intra-state movement, but payload has IgstOnIntra: "N"
   Sent: IgstAmt: 1800.00, IgstOnIntra: "N"
   Lakehouse Rectification: igst_on_intra: "Y", reverse_charge: "Y", retain igst_amount: 1800.00, cgst_amount: 0.00, sgst_amount: 0.00
   Reason: 'If the transaction legally requires IGST on intra-state movement, set the flag "IgstOnIntra": "Y" under TranDtls.'

4. Summary vs. Item Level Mismatch:
   Line items have CGST/SGST, but invoice header total has ValDtls: { IgstVal: 1800.00, CgstVal: 0.00, SgstVal: 0.00 }
   Lakehouse Rectification: Line items keep CGST/SGST, header reconciled to ValDtls: { IgstVal: 0.00, CgstVal: 900.00, SgstVal: 900.00 }
   Reason: "Header total tax values in ValDtls must match the sum of item-level taxes in ItemList."

Also tests:
- Parquet storage round-trip (write_parquet, read_parquet, append_to_parquet)
- Schema conformance to FLATTENED_INVOICE_SCHEMA
- Dict payload and Pydantic InvoicePayload model branches
- Sentinel ML Telemetry: status_badge="FLAGGED_AND_RECTIFIED", risk_level="HIGH", risk_prob >= 0.95
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
    classify_rule_2172_diagnostic,
    NICValidationError,
)
from src.ingestion.storage import (
    flatten_invoice_payload,
    write_parquet,
    read_parquet,
    append_to_parquet,
    store_invoice_payload,
    FLATTENED_INVOICE_SCHEMA,
)


# ==============================================================================
# FIXTURES
# ==============================================================================

@pytest.fixture
def failing_scenario_1_standard_intra():
    """Failing Scenario 1: Intra-state MH 27 -> 27 with IGST instead of CGST/SGST."""
    return {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-2026-2172-SC1",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "B2B",
        "reversecharge": "N",
        "igstonintra": "N",
        "supplier": {
            "gstin": "27ABCDE1234F1Z5",
            "lglnm": "Maharashtra Seller Supplies Pvt Ltd",
            "state": "27",
            "pin": "400001",
            "loc": "Mumbai"
        },
        "buyer": {
            "gstin": "27XYZAB9876C1Z1",
            "lglnm": "Maharashtra Buyer Engineering Ltd",
            "state": "27",
            "pos": "27",
            "pin": "411001",
            "loc": "Pune"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "Precision Industrial Gear",
                "prddesc": "Hardened alloy transmission gear",
                "hsn": "8483",
                "qty": 1.0,
                "unit": "NOS",
                "unitprice": 10000.0,
                "totamt": 10000.0,
                "assval": 10000.0,
                "gstrate": 18.0,
                "igstval": 1800.0,
                "cgstval": 0.0,
                "sgstval": 0.0,
                "totitemval": 11800.0
            }
        ],
        "valdtls": {
            "assval": 10000.0,
            "cgstval": 0.0,
            "sgstval": 0.0,
            "igstval": 1800.0,
            "totinvval": 11800.0
        }
    }


@pytest.fixture
def failing_scenario_2_wrong_pos():
    """Failing Scenario 2: Seller 27, Buyer in Karnataka 29, but POS wrongly entered as 27."""
    return {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-2026-2172-SC2",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "B2B",
        "reversecharge": "N",
        "igstonintra": "N",
        "supplier": {
            "gstin": "27ABCDE1234F1Z5",
            "lglnm": "Maharashtra Tech Solutions Ltd",
            "state": "27",
            "pin": "400001",
            "loc": "Mumbai"
        },
        "buyer": {
            "gstin": "29AABCB1234F1Z0",
            "lglnm": "Karnataka Cloud Data Center",
            "state": "29",
            "pos": "27",  # WRONG POS: entered as 27 instead of destination 29
            "pin": "560001",
            "loc": "Bangalore"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "Server Rack Unit",
                "prddesc": "Rack mount server enclosure",
                "hsn": "8471",
                "qty": 1.0,
                "unit": "NOS",
                "unitprice": 10000.0,
                "totamt": 10000.0,
                "assval": 10000.0,
                "gstrate": 18.0,
                "igstval": 1800.0,
                "cgstval": 0.0,
                "sgstval": 0.0,
                "totitemval": 11800.0
            }
        ],
        "valdtls": {
            "assval": 10000.0,
            "cgstval": 0.0,
            "sgstval": 0.0,
            "igstval": 1800.0,
            "totinvval": 11800.0
        }
    }


@pytest.fixture
def failing_scenario_3_exceptional_intra():
    """Failing Scenario 3: Valid exceptional intra-state supply requiring IGST, but IgstOnIntra is N."""
    return {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-2026-2172-SC3",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "B2B",
        "reversecharge": "N",
        "igstonintra": "N",  # Wrong: should be Y
        "is_exceptional_intra": True,
        "supplier": {
            "gstin": "27ABCDE1234F1Z5",
            "lglnm": "Maharashtra Port Handler Ltd",
            "state": "27",
            "pin": "400001",
            "loc": "Mumbai"
        },
        "buyer": {
            "gstin": "27XYZAB9876C1Z1",
            "lglnm": "Maharashtra Logistics Hub Ltd",
            "state": "27",
            "pos": "27",
            "pin": "411001",
            "loc": "Pune"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "Bonded Port Freight Service",
                "prddesc": "Customs bonded transport service",
                "hsn": "9965",
                "qty": 1.0,
                "unit": "NOS",
                "unitprice": 10000.0,
                "totamt": 10000.0,
                "assval": 10000.0,
                "gstrate": 18.0,
                "igstval": 1800.0,
                "cgstval": 0.0,
                "sgstval": 0.0,
                "totitemval": 11800.0
            }
        ],
        "valdtls": {
            "assval": 10000.0,
            "cgstval": 0.0,
            "sgstval": 0.0,
            "igstval": 1800.0,
            "totinvval": 11800.0
        }
    }


@pytest.fixture
def failing_scenario_4_summary_vs_item_mismatch():
    """Failing Scenario 4: Line items have split CGST/SGST, but header ValDtls has IGST."""
    return {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-2026-2172-SC4",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "B2B",
        "reversecharge": "N",
        "igstonintra": "N",
        "supplier": {
            "gstin": "27ABCDE1234F1Z5",
            "lglnm": "Maharashtra Retailer Ltd",
            "state": "27",
            "pin": "400001",
            "loc": "Mumbai"
        },
        "buyer": {
            "gstin": "27XYZAB9876C1Z1",
            "lglnm": "Maharashtra Consumer Corp",
            "state": "27",
            "pos": "27",
            "pin": "411001",
            "loc": "Pune"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "Commercial Desktop Computer",
                "prddesc": "Workstation PC",
                "hsn": "8471",
                "qty": 1.0,
                "unit": "NOS",
                "unitprice": 10000.0,
                "totamt": 10000.0,
                "assval": 10000.0,
                "gstrate": 18.0,
                "igstval": 0.0,
                "cgstval": 900.0,  # Line items correctly have CGST/SGST
                "sgstval": 900.0,
                "totitemval": 11800.0
            }
        ],
        "valdtls": {
            "assval": 10000.0,
            "cgstval": 0.0,  # Mismatch: header erroneously has IGST instead of CGST/SGST
            "sgstval": 0.0,
            "igstval": 1800.0,
            "totinvval": 11800.0
        }
    }


# ==============================================================================
# 1. SCENARIO 1: STANDARD INTRA-STATE TRANSACTION TESTS
# ==============================================================================

def test_lakehouse_scenario_1_dict_flattening(failing_scenario_1_standard_intra):
    """
    Scenario 1 Dict Flattening:
    Seller State = 27, Buyer POS = 27, IgstAmt: 1800.00
    -> igst_amount: 0.0, cgst_amount: 900.0, sgst_amount: 900.0
    -> inv_cgst_amount: 900.0, inv_sgst_amount: 900.0, inv_igst_amount: 0.0
    -> FLAGGED_AND_RECTIFIED badge, HIGH risk, prob >= 0.95
    """
    rows = flatten_invoice_payload(failing_scenario_1_standard_intra)
    assert len(rows) == 1
    row = rows[0]

    # Item tax amounts split equally
    assert row["igst_amount"] == 0.0
    assert row["cgst_amount"] == 900.0
    assert row["sgst_amount"] == 900.0
    assert row["total_item_value"] == 11800.0

    # Header valuation tax amounts match item sum
    assert row["inv_igst_amount"] == 0.0
    assert row["inv_cgst_amount"] == 900.0
    assert row["inv_sgst_amount"] == 900.0
    assert row["inv_total_value"] == 11800.0

    # Sentinel ML Telemetry
    assert row["sentinel_status_badge"] == "FLAGGED_AND_RECTIFIED"
    assert row["sentinel_risk_level"] == "HIGH"
    assert row["sentinel_risk_prob"] >= 0.95
    assert "Rule 2172 Violation (Standard Intra-State Transaction)" in row["sentinel_audit_reasons"]
    assert "Same supplier state and POS means regular intra-state supply" in row["sentinel_audit_reasons"]


def test_lakehouse_scenario_1_pydantic_flattening(failing_scenario_1_standard_intra):
    """Scenario 1 Pydantic Flattening: model_validate and auto_correct_and_build."""
    model, audit_log = InvoicePayload.auto_correct_and_build(failing_scenario_1_standard_intra)
    rows = flatten_invoice_payload(model)
    assert len(rows) == 1
    row = rows[0]

    assert row["igst_amount"] == 0.0
    assert row["cgst_amount"] == 900.0
    assert row["sgst_amount"] == 900.0
    assert row["inv_igst_amount"] == 0.0
    assert row["inv_cgst_amount"] == 900.0
    assert row["inv_sgst_amount"] == 900.0
    assert row["compliance_status"] == "VALID"


# ==============================================================================
# 2. SCENARIO 2: WRONG PLACE OF SUPPLY (POS) ENTERED TESTS
# ==============================================================================

def test_lakehouse_scenario_2_wrong_pos_dict_flattening(failing_scenario_2_wrong_pos):
    """
    Scenario 2 Dict Flattening:
    Seller State = 27, Recipient in Karnataka 29, but POS entered was 27.
    -> Lakehouse rectifies buyer_pos to "29"
    -> Transaction is inter-state: retains igst_amount: 1800.0, cgst: 0.0, sgst: 0.0
    -> Header: inv_igst_amount: 1800.0, inv_cgst: 0.0, inv_sgst: 0.0
    -> FLAGGED_AND_RECTIFIED badge, risk_prob >= 0.95
    """
    rows = flatten_invoice_payload(failing_scenario_2_wrong_pos)
    assert len(rows) == 1
    row = rows[0]

    # Destination state fixed to 29
    assert row["buyer_pos"] == "29"
    assert row["supplier_state"] == "27"

    # Retain full IGST for inter-state sale
    assert row["igst_amount"] == 1800.0
    assert row["cgst_amount"] == 0.0
    assert row["sgst_amount"] == 0.0
    assert row["inv_igst_amount"] == 1800.0
    assert row["inv_cgst_amount"] == 0.0
    assert row["inv_sgst_amount"] == 0.0

    # Sentinel Telemetry
    assert row["sentinel_status_badge"] == "FLAGGED_AND_RECTIFIED"
    assert row["sentinel_risk_level"] == "HIGH"
    assert row["sentinel_risk_prob"] >= 0.95
    assert "Rule 2172 Violation (Wrong Place of Supply (Pos) Entered)" in row["sentinel_audit_reasons"]
    assert "fix the recipient's Pos code to match the destination state" in row["sentinel_audit_reasons"]


def test_lakehouse_scenario_2_wrong_pos_pydantic_flattening(failing_scenario_2_wrong_pos):
    """Scenario 2 Pydantic Flattening: model handles wrong POS rectification."""
    model, audit_log = InvoicePayload.auto_correct_and_build(failing_scenario_2_wrong_pos)
    rows = flatten_invoice_payload(model)
    assert len(rows) == 1
    row = rows[0]

    assert row["buyer_pos"] == "29"
    assert row["igst_amount"] == 1800.0
    assert row["cgst_amount"] == 0.0
    assert row["sgst_amount"] == 0.0
    assert row["inv_igst_amount"] == 1800.0
    assert row["inv_cgst_amount"] == 0.0
    assert row["inv_sgst_amount"] == 0.0


# ==============================================================================
# 3. SCENARIO 3: VALID EXCEPTIONAL INTRA-STATE IGST SUPPLY TESTS
# ==============================================================================

def test_lakehouse_scenario_3_exceptional_intra_dict_flattening(failing_scenario_3_exceptional_intra):
    """
    Scenario 3 Dict Flattening:
    Seller State = 27, Buyer POS = 27, is_exceptional_intra = True, IgstOnIntra was N
    -> Lakehouse rectifies igst_on_intra to "Y" and reverse_charge to "Y"
    -> Retains igst_amount: 1800.0, cgst: 0.0, sgst: 0.0
    -> Header: inv_igst_amount: 1800.0, inv_cgst: 0.0, inv_sgst: 0.0
    -> FLAGGED_AND_RECTIFIED badge, risk_prob >= 0.95
    """
    rows = flatten_invoice_payload(failing_scenario_3_exceptional_intra)
    assert len(rows) == 1
    row = rows[0]

    # Exceptional intra-state flags set
    assert row["igst_on_intra"] == "Y"
    assert row["reverse_charge"] == "Y"

    # Retain full IGST
    assert row["igst_amount"] == 1800.0
    assert row["cgst_amount"] == 0.0
    assert row["sgst_amount"] == 0.0
    assert row["inv_igst_amount"] == 1800.0
    assert row["inv_cgst_amount"] == 0.0
    assert row["inv_sgst_amount"] == 0.0

    # Sentinel Telemetry
    assert row["sentinel_status_badge"] == "FLAGGED_AND_RECTIFIED"
    assert row["sentinel_risk_level"] == "HIGH"
    assert row["sentinel_risk_prob"] >= 0.95
    assert "Rule 2172 Violation (Valid Exceptional Intra-State IGST Supply)" in row["sentinel_audit_reasons"]
    assert 'set the flag "IgstOnIntra": "Y" under TranDtls' in row["sentinel_audit_reasons"]


def test_lakehouse_scenario_3_exceptional_intra_pydantic_flattening(failing_scenario_3_exceptional_intra):
    """Scenario 3 Pydantic Flattening: model handles exceptional intra IGST supply."""
    model, audit_log = InvoicePayload.auto_correct_and_build(failing_scenario_3_exceptional_intra)
    rows = flatten_invoice_payload(model)
    assert len(rows) == 1
    row = rows[0]

    assert row["igst_on_intra"] == "Y"
    assert row["reverse_charge"] == "Y"
    assert row["igst_amount"] == 1800.0
    assert row["cgst_amount"] == 0.0
    assert row["sgst_amount"] == 0.0
    assert row["inv_igst_amount"] == 1800.0


# ==============================================================================
# 4. SCENARIO 4: SUMMARY VS. ITEM LEVEL MISMATCH TESTS
# ==============================================================================

def test_lakehouse_scenario_4_summary_mismatch_dict_flattening(failing_scenario_4_summary_vs_item_mismatch):
    """
    Scenario 4 Dict Flattening:
    Line items have CGST: 900.0, SGST: 900.0, IGST: 0.0.
    Header ValDtls incorrectly had IGST: 1800.0, CGST: 0.0, SGST: 0.0.
    -> Line items retain CGST: 900.0, SGST: 900.0, IGST: 0.0.
    -> Header reconciled: inv_cgst_amount: 900.0, inv_sgst_amount: 900.0, inv_igst_amount: 0.0.
    -> FLAGGED_AND_RECTIFIED badge, risk_prob >= 0.95.
    -> Reason: Header total tax values in ValDtls must match the sum of item-level taxes in ItemList.
    """
    rows = flatten_invoice_payload(failing_scenario_4_summary_vs_item_mismatch)
    assert len(rows) == 1
    row = rows[0]

    # Line item taxes unchanged
    assert row["cgst_amount"] == 900.0
    assert row["sgst_amount"] == 900.0
    assert row["igst_amount"] == 0.0

    # Header taxes reconciled to match line items
    assert row["inv_cgst_amount"] == 900.0
    assert row["inv_sgst_amount"] == 900.0
    assert row["inv_igst_amount"] == 0.0
    assert row["inv_total_value"] == 11800.0

    # Sentinel Telemetry
    assert row["sentinel_status_badge"] == "FLAGGED_AND_RECTIFIED"
    assert row["sentinel_risk_level"] == "HIGH"
    assert row["sentinel_risk_prob"] >= 0.95
    assert "Rule 2172 Violation (Summary vs. Item Level Mismatch)" in row["sentinel_audit_reasons"]
    assert "Header total tax values in ValDtls must match the sum of item-level taxes in ItemList" in row["sentinel_audit_reasons"]


def test_lakehouse_scenario_4_summary_mismatch_pydantic_flattening(failing_scenario_4_summary_vs_item_mismatch):
    """Scenario 4 Pydantic Flattening: model handles header reconciliation."""
    model, audit_log = InvoicePayload.auto_correct_and_build(failing_scenario_4_summary_vs_item_mismatch)
    rows = flatten_invoice_payload(model)
    assert len(rows) == 1
    row = rows[0]

    assert row["cgst_amount"] == 900.0
    assert row["sgst_amount"] == 900.0
    assert row["igst_amount"] == 0.0
    assert row["inv_cgst_amount"] == 900.0
    assert row["inv_sgst_amount"] == 900.0
    assert row["inv_igst_amount"] == 0.0


# ==============================================================================
# 5. DATA LAKEHOUSE PARQUET PERSISTENCE ROUND-TRIP TESTS
# ==============================================================================

def test_lakehouse_parquet_persistence_roundtrip_all_scenarios(
    failing_scenario_1_standard_intra,
    failing_scenario_2_wrong_pos,
    failing_scenario_3_exceptional_intra,
    failing_scenario_4_summary_vs_item_mismatch
):
    """
    Validates complete Data Lakehouse Bronze/Silver/Gold Parquet persistence:
    1. Ingest all 4 statutory scenarios into Lakehouse Parquet storage.
    2. Verify schema conformance to FLATTENED_INVOICE_SCHEMA.
    3. Read Parquet via read_parquet and verify all columns and values.
    4. Upsert/deduplicate records via append_to_parquet.
    """
    tmp_dir = tempfile.mkdtemp(prefix="lakehouse_2172_")
    try:
        parquet_file = Path(tmp_dir) / "silver_invoices_2172.parquet"

        # 1. Flatten all 4 scenarios
        rows_sc1 = flatten_invoice_payload(failing_scenario_1_standard_intra)
        rows_sc2 = flatten_invoice_payload(failing_scenario_2_wrong_pos)
        rows_sc3 = flatten_invoice_payload(failing_scenario_3_exceptional_intra)
        rows_sc4 = flatten_invoice_payload(failing_scenario_4_summary_vs_item_mismatch)

        all_rows = rows_sc1 + rows_sc2 + rows_sc3 + rows_sc4
        assert len(all_rows) == 4

        # 2. Write to Parquet conforming to FLATTENED_INVOICE_SCHEMA
        success = write_parquet(all_rows, str(parquet_file), schema=FLATTENED_INVOICE_SCHEMA)
        assert success is True
        assert parquet_file.exists()

        # 3. Read back via read_parquet
        df = read_parquet(str(parquet_file))
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 4

        # Scenario 1 validation in DataFrame
        row_1 = df[df["invoice_id"] == "INV-2026-2172-SC1"].iloc[0]
        assert row_1["cgst_amount"] == 900.0
        assert row_1["sgst_amount"] == 900.0
        assert row_1["igst_amount"] == 0.0
        assert row_1["inv_cgst_amount"] == 900.0
        assert row_1["inv_sgst_amount"] == 900.0
        assert row_1["inv_igst_amount"] == 0.0
        assert row_1["sentinel_status_badge"] == "FLAGGED_AND_RECTIFIED"

        # Scenario 2 validation in DataFrame
        row_2 = df[df["invoice_id"] == "INV-2026-2172-SC2"].iloc[0]
        assert row_2["buyer_pos"] == "29"
        assert row_2["igst_amount"] == 1800.0
        assert row_2["cgst_amount"] == 0.0
        assert row_2["sgst_amount"] == 0.0
        assert row_2["inv_igst_amount"] == 1800.0

        # Scenario 3 validation in DataFrame
        row_3 = df[df["invoice_id"] == "INV-2026-2172-SC3"].iloc[0]
        assert row_3["igst_on_intra"] == "Y"
        assert row_3["reverse_charge"] == "Y"
        assert row_3["igst_amount"] == 1800.0

        # Scenario 4 validation in DataFrame
        row_4 = df[df["invoice_id"] == "INV-2026-2172-SC4"].iloc[0]
        assert row_4["cgst_amount"] == 900.0
        assert row_4["sgst_amount"] == 900.0
        assert row_4["igst_amount"] == 0.0
        assert row_4["inv_cgst_amount"] == 900.0
        assert row_4["inv_sgst_amount"] == 900.0
        assert row_4["inv_igst_amount"] == 0.0

        # 4. Lakehouse Upsert: Append duplicate record and verify deduplication
        append_success = append_to_parquet(rows_sc1, str(parquet_file), schema=FLATTENED_INVOICE_SCHEMA)
        assert append_success is True

        df_dedup = read_parquet(str(parquet_file))
        assert len(df_dedup) == 4, "Upsert should maintain deduplicated count of 4"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ==============================================================================
# 6. MULTI-LINE INVOICE & BATCH TESTS
# ==============================================================================

def test_lakehouse_multi_line_invoice_rule_2172():
    """Multi-item invoice where multiple items fail Rule 2172 and header is rectified."""
    multi_payload = {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-2026-2172-MULTI",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "B2B",
        "reversecharge": "N",
        "igstonintra": "N",
        "supplier": {
            "gstin": "27ABCDE1234F1Z5",
            "lglnm": "Maharashtra Mega Mills Ltd",
            "state": "27",
            "pin": "400001",
            "loc": "Mumbai"
        },
        "buyer": {
            "gstin": "27XYZAB9876C1Z1",
            "lglnm": "Maharashtra Assembly Plant",
            "state": "27",
            "pos": "27",
            "pin": "411001",
            "loc": "Pune"
        },
        "itemdtls": [
            {
                "item_slno": "1",
                "slno": "1",
                "prdnm": "Precision Bolt M10",
                "prddesc": "High tensile steel bolt",
                "hsn": "7318",
                "qty": 100.0,
                "unit": "NOS",
                "unitprice": 50.0,
                "totamt": 5000.0,
                "assval": 5000.0,
                "gstrate": 18.0,
                "igstval": 900.0,
                "cgstval": 0.0,
                "sgstval": 0.0,
                "totitemval": 5900.0
            },
            {
                "item_slno": "2",
                "slno": "2",
                "prdnm": "Precision Nut M10",
                "prddesc": "High tensile steel nut",
                "hsn": "7318",
                "qty": 100.0,
                "unit": "NOS",
                "unitprice": 50.0,
                "totamt": 5000.0,
                "assval": 5000.0,
                "gstrate": 18.0,
                "igstval": 900.0,
                "cgstval": 0.0,
                "sgstval": 0.0,
                "totitemval": 5900.0
            }
        ],
        "valdtls": {
            "assval": 10000.0,
            "cgstval": 0.0,
            "sgstval": 0.0,
            "igstval": 1800.0,
            "totinvval": 11800.0
        }
    }

    rows = flatten_invoice_payload(multi_payload)
    assert len(rows) == 2

    # Item 1
    assert rows[0]["cgst_amount"] == 450.0
    assert rows[0]["sgst_amount"] == 450.0
    assert rows[0]["igst_amount"] == 0.0
    assert rows[0]["inv_cgst_amount"] == 900.0
    assert rows[0]["inv_sgst_amount"] == 900.0
    assert rows[0]["inv_igst_amount"] == 0.0

    # Item 2
    assert rows[1]["cgst_amount"] == 450.0
    assert rows[1]["sgst_amount"] == 450.0
    assert rows[1]["igst_amount"] == 0.0
    assert rows[1]["inv_cgst_amount"] == 900.0
    assert rows[1]["inv_sgst_amount"] == 900.0
    assert rows[1]["inv_igst_amount"] == 0.0
