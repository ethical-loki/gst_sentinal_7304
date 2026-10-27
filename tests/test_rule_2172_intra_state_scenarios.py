"""
Unit and Integration Tests for Indian GST e-Invoicing (NIC / IRP) Error Code 2172:
"For Intra-state transaction, IGST amount is not applicable; only CGST and SGST amounts are applicable"

Tests all 4 Statutory Scenarios:
1. Standard Intra-State Transaction:
   Seller State = "27", Buyer POS = "27", IgstAmt: 1800.00, CgstAmt: 0.00, SgstAmt: 0.00
   -> IgstAmt: 0.00, CgstAmt: 900.00, SgstAmt: 900.00
   Reason: "Same supplier state and POS means regular intra-state supply. Clear IgstAmt and split tax equally between CGST and SGST."

2. Wrong Place of Supply (Pos) Entered:
   Seller State = "27", Recipient in Karnataka (29), but payload has BuyerDtls: { Pos: "27" }
   -> BuyerDtls: { Pos: "29" }
   Reason: "If this was actually an inter-state sale to an out-of-state recipient, fix the recipient's Pos code to match the destination state."

3. Valid Exceptional Intra-State IGST Supply:
   Seller State = "27", Buyer POS = "27", IgstOnIntra: "N", IgstAmt: 1800.00
   -> IgstOnIntra: "Y", IgstAmt: 1800.00, CgstAmt: 0.00, SgstAmt: 0.00, RevChrg: "Y"
   Reason: 'If the transaction legally requires IGST on intra-state movement, set the flag "IgstOnIntra": "Y" under TranDtls.'

4. Summary vs. Item Level Mismatch:
   Line items have CGST/SGST, but invoice header total has ValDtls: { IgstVal: 1800.00 }
   -> ValDtls: { IgstVal: 0.00, CgstVal: 900.00, SgstVal: 900.00 }
   Reason: "Header total tax values in ValDtls must match the sum of item-level taxes in ItemList."
"""

from decimal import Decimal
import pytest

from src.ingestion.schemas import (
    InvoicePayload,
    classify_rule_2172_diagnostic,
    NICValidationError,
)
from Template_Converters.payload_builder import PayloadBuilder
from Template_Converters.validator import GSTValidator
from src.rules.rules_engine import RulesEngine


# ============================================================================
# 1. DIRECT UNIT TESTS FOR classify_rule_2172_diagnostic
# ============================================================================

def test_classify_scenario_1_standard_intra_state():
    """Scenario 1: Seller State == Buyer POS, regular intra supply with IGST charged."""
    diag = classify_rule_2172_diagnostic(
        seller_state="27",
        buyer_pos="27",
        buyer_state="27",
        buyer_gstin="27ABCDE1234F1Z5",
        igst_amt=Decimal("1800.00"),
        cgst_amt=Decimal("0.00"),
        sgst_amt=Decimal("0.00"),
        igstonintra="N"
    )
    assert diag["scenario"] == "STANDARD_INTRA_STATE"
    assert "Same supplier state and POS means regular intra-state supply. Clear IgstAmt and split tax equally between CGST and SGST." in diag["reason"]
    assert diag["correct_payload"]["IgstAmt"] == Decimal("0.00")
    assert diag["correct_payload"]["CgstAmt"] == Decimal("900.00")
    assert diag["correct_payload"]["SgstAmt"] == Decimal("900.00")


def test_classify_scenario_2_wrong_pos_entered():
    """Scenario 2: Seller State = 27, Recipient destination is Karnataka (29), but POS entered was 27."""
    diag = classify_rule_2172_diagnostic(
        seller_state="27",
        buyer_pos="27",
        buyer_state="29",
        buyer_gstin="29ABCDE1234F1Z5",
        igst_amt=Decimal("1800.00"),
        cgst_amt=Decimal("0.00"),
        sgst_amt=Decimal("0.00"),
        igstonintra="N"
    )
    assert diag["scenario"] == "WRONG_POS_ENTERED"
    assert diag["destination_state"] == "29"
    assert "If this was actually an inter-state sale to an out-of-state recipient, fix the recipient's Pos code to match the destination state." in diag["reason"]
    assert diag["correct_payload"]["BuyerDtls"]["Pos"] == "29"


def test_classify_scenario_3_exceptional_intra_state_igst():
    """Scenario 3: Seller State = 27, Buyer POS = 27, transaction legally requires IGST on intra-state movement."""
    diag = classify_rule_2172_diagnostic(
        seller_state="27",
        buyer_pos="27",
        buyer_state="27",
        buyer_gstin="27ABCDE1234F1Z5",
        igst_amt=Decimal("1800.00"),
        cgst_amt=Decimal("0.00"),
        sgst_amt=Decimal("0.00"),
        igstonintra="N",
        is_exceptional_intra=True
    )
    assert diag["scenario"] == "EXCEPTIONAL_INTRA_STATE_IGST"
    assert 'If the transaction legally requires IGST on intra-state movement, set the flag "IgstOnIntra": "Y" under TranDtls.' in diag["reason"]
    assert diag["correct_payload"]["TranDtls"]["IgstOnIntra"] == "Y"
    assert diag["correct_payload"]["TranDtls"]["RevChrg"] == "Y"
    assert diag["correct_payload"]["IgstAmt"] == Decimal("1800.00")
    assert diag["correct_payload"]["CgstAmt"] == Decimal("0.00")
    assert diag["correct_payload"]["SgstAmt"] == Decimal("0.00")


def test_classify_scenario_4_summary_vs_item_mismatch():
    """Scenario 4: Line items have split CGST/SGST, but header ValDtls has IgstVal > 0."""
    diag = classify_rule_2172_diagnostic(
        seller_state="27",
        buyer_pos="27",
        buyer_state="27",
        buyer_gstin="27ABCDE1234F1Z5",
        igst_amt=Decimal("0.00"),
        cgst_amt=Decimal("900.00"),
        sgst_amt=Decimal("900.00"),
        header_igst=Decimal("1800.00"),
        header_cgst=Decimal("0.00"),
        header_sgst=Decimal("0.00")
    )
    assert diag["scenario"] == "SUMMARY_VS_ITEM_MISMATCH"
    assert "Header total tax values in ValDtls must match the sum of item-level taxes in ItemList." in diag["reason"]
    assert diag["correct_payload"]["ValDtls"]["IgstVal"] == Decimal("0.00")
    assert diag["correct_payload"]["ValDtls"]["CgstVal"] == Decimal("900.00")
    assert diag["correct_payload"]["ValDtls"]["SgstVal"] == Decimal("900.00")


# ============================================================================
# 2. AUTO-CORRECTION TESTS: SCENARIO 1 (STANDARD INTRA-STATE TRANSACTION)
# ============================================================================

def test_scenario_1_auto_correct_schemas_migration():
    """InvoicePayload.auto_correct_and_build splits IGST into CGST & SGST for standard intra-state."""
    failing_payload = {
        "self_gstin": "27ABCDE1234F1Z5",
        "supplierdt1": {
            "supplier_gstin": "27ABCDE1234F1Z5",
            "supplier_state": "27",
            "supplier_lglnm": "Maharashtra Seller Ltd",
            "supplier_loc": "Mumbai",
            "supplier_pin": "400001"
        },
        "buyerdt1": {
            "buyer_gstin": "27XYZAB9876C1Z1",
            "buyer_state": "27",
            "buyer_pos": "27",
            "buyer_lglnm": "Maharashtra Buyer Ltd",
            "buyer_loc": "Pune",
            "buyer_pin": "411001"
        },
        "itemdtls": [
            {
                "slno": "1",
                "prdnm": "Industrial Machinery Part",
                "hsncd": "8481",
                "qty": "1.00",
                "unitprice": "10000.00",
                "grossamt": "10000.00",
                "assval": "10000.00",
                "gstrate": "18.00",
                "igstval": "1800.00",
                "cgstval": "0.00",
                "sgstval": "0.00",
                "totitemval": "11800.00"
            }
        ],
        "valdt1": {
            "ttlassval": "10000.00",
            "igstval": "1800.00",
            "cgstval": "0.00",
            "sgstval": "0.00",
            "totinvval": "11800.00"
        }
    }

    model, audit_log = InvoicePayload.auto_correct_and_build(failing_payload)
    item = model.itemdtls[0]

    assert Decimal(str(item.igstval)) == Decimal("0.00")
    assert Decimal(str(item.cgstval)) == Decimal("900.00")
    assert Decimal(str(item.sgstval)) == Decimal("900.00")
    assert Decimal(str(model.valdtls.igstval)) == Decimal("0.00")
    assert Decimal(str(model.valdtls.cgstval)) == Decimal("900.00")
    assert Decimal(str(model.valdtls.sgstval)) == Decimal("900.00")

    audit_entry = next((e for e in audit_log if "Same supplier state and POS means regular intra-state supply" in e["description"]), None)
    assert audit_entry is not None
    assert audit_entry["original"] == "1800.00"
    assert audit_entry["corrected"] == "0.00"


def test_scenario_1_auto_correct_payload_builder():
    """PayloadBuilder.auto_correct_and_build splits IGST into CGST & SGST for standard intra-state."""
    failing_payload = {
        "self_gstin": "27ABCDE1234F1Z5",
        "supplierdt1": {
            "supplier_gstin": "27ABCDE1234F1Z5",
            "supplier_state": "27",
            "supplier_lglnm": "Maharashtra Seller Ltd",
            "supplier_loc": "Mumbai",
            "supplier_pin": "400001"
        },
        "buyerdt1": {
            "buyer_gstin": "27XYZAB9876C1Z1",
            "buyer_state": "27",
            "pos": "27",
            "buyer_lglnm": "Maharashtra Buyer Ltd",
            "buyer_loc": "Pune",
            "buyer_pin": "411001"
        },
        "itemdtls": [
            {
                "prdnm": "Industrial Machinery Part",
                "hsncd": "8481",
                "qty": "1.00",
                "unitrate": "10000.00",
                "grossamt": "10000.00",
                "assamt": "10000.00",
                "gstrate": "18.00",
                "igstamt": "1800.00",
                "cgstamt": "0.00",
                "sgstamt": "0.00",
                "totitemval": "11800.00"
            }
        ],
        "valdt1": {
            "ttlassval": "10000.00",
            "igstval": "1800.00",
            "cgstval": "0.00",
            "sgstval": "0.00",
            "totinvval": "11800.00"
        }
    }

    out_payload, audit_log = PayloadBuilder.auto_correct_and_build(failing_payload)
    item = out_payload["itemdtls"][0]
    val = out_payload["valdt1"]

    assert Decimal(item["igstamt"]) == Decimal("0.00")
    assert Decimal(item["cgstamt"]) == Decimal("900.00")
    assert Decimal(item["sgstamt"]) == Decimal("900.00")
    assert Decimal(val["igstval"]) == Decimal("0.00")
    assert Decimal(val["cgstval"]) == Decimal("900.00")
    assert Decimal(val["sgstval"]) == Decimal("900.00")

    audit_entry = next((e for e in audit_log if "Same supplier state and POS means regular intra-state supply" in e["description"]), None)
    assert audit_entry is not None


# ============================================================================
# 3. AUTO-CORRECTION TESTS: SCENARIO 2 (WRONG POS ENTERED)
# ============================================================================

def test_scenario_2_auto_correct_schemas_migration():
    """InvoicePayload.auto_correct_and_build fixes POS to recipient destination state (29) when entered as 27."""
    payload = {
        "self_gstin": "27ABCDE1234F1Z5",
        "supplierdt1": {
            "supplier_gstin": "27ABCDE1234F1Z5",
            "supplier_state": "27",
            "supplier_lglnm": "Maharashtra Seller Ltd",
            "supplier_loc": "Mumbai",
            "supplier_pin": "400001"
        },
        "buyerdt1": {
            "buyer_gstin": "29XYZAB9876C1Z1",  # Karnataka recipient
            "buyer_state": "29",
            "buyer_pos": "27",  # Erroneously entered seller state!
            "buyer_lglnm": "Karnataka Client Pvt Ltd",
            "buyer_loc": "Bengaluru",
            "buyer_pin": "560001"
        },
        "itemdtls": [
            {
                "slno": "1",
                "prdnm": "Cloud Servers",
                "hsncd": "8471",
                "qty": "1.00",
                "unitprice": "10000.00",
                "assval": "10000.00",
                "gstrate": "18.00",
                "igstval": "1800.00"
            }
        ]
    }

    model, audit_log = InvoicePayload.auto_correct_and_build(payload)

    # POS must be auto-corrected to 29 (Karnataka)
    assert model.buyer.pos == "29"

    # Transaction is now recognized as inter-state: IGST is preserved
    item = model.itemdtls[0]
    assert Decimal(str(item.igstval)) == Decimal("1800.00")
    assert Decimal(str(item.cgstval)) == Decimal("0.00")
    assert Decimal(str(item.sgstval)) == Decimal("0.00")

    audit_entry = next((e for e in audit_log if "fix the recipient's Pos code to match the destination state" in e["description"]), None)
    assert audit_entry is not None
    assert audit_entry["original"] == "27"
    assert audit_entry["corrected"] == "29"


def test_scenario_2_auto_correct_payload_builder():
    """PayloadBuilder.auto_correct_and_build fixes POS to recipient destination state (29) when entered as 27."""
    payload = {
        "self_gstin": "27ABCDE1234F1Z5",
        "supplierdt1": {
            "supplier_gstin": "27ABCDE1234F1Z5",
            "supplier_state": "27",
            "supplier_lglnm": "Maharashtra Seller Ltd",
            "supplier_loc": "Mumbai",
            "supplier_pin": "400001"
        },
        "buyerdt1": {
            "buyer_gstin": "29XYZAB9876C1Z1",  # Karnataka recipient
            "buyer_state": "29",
            "pos": "27",  # Erroneously entered 27!
            "buyer_lglnm": "Karnataka Client Pvt Ltd",
            "buyer_loc": "Bengaluru",
            "buyer_pin": "560001"
        },
        "itemdtls": [
            {
                "prdnm": "Cloud Servers",
                "hsncd": "8471",
                "qty": "1.00",
                "unitrate": "10000.00",
                "assamt": "10000.00",
                "gstrate": "18.00",
                "igstamt": "1800.00"
            }
        ]
    }

    out_payload, audit_log = PayloadBuilder.auto_correct_and_build(payload)

    # POS must be auto-corrected to 29
    assert out_payload["buyerdt1"]["pos"] == "29"
    item = out_payload["itemdtls"][0]
    assert Decimal(item["igstamt"]) == Decimal("1800.00")
    assert Decimal(item["cgstamt"]) == Decimal("0.00")
    assert Decimal(item["sgstamt"]) == Decimal("0.00")

    audit_entry = next((e for e in audit_log if "fix the recipient's Pos code to match the destination state" in e["description"]), None)
    assert audit_entry is not None
    assert audit_entry["original"] == "27"
    assert audit_entry["corrected"] == "29"


# ============================================================================
# 4. AUTO-CORRECTION TESTS: SCENARIO 3 (VALID EXCEPTIONAL INTRA-STATE IGST SUPPLY)
# ============================================================================

def test_scenario_3_auto_correct_schemas_migration():
    """InvoicePayload.auto_correct_and_build sets IgstOnIntra='Y' and RevChrg='Y' for exceptional intra IGST."""
    payload = {
        "self_gstin": "27ABCDE1234F1Z5",
        "is_exceptional_intra_igst": True,
        "supplierdt1": {
            "supplier_gstin": "27ABCDE1234F1Z5",
            "supplier_state": "27",
            "supplier_lglnm": "Maharashtra Seller Ltd",
            "supplier_loc": "Mumbai",
            "supplier_pin": "400001"
        },
        "buyerdt1": {
            "buyer_gstin": "27XYZAB9876C1Z1",
            "buyer_state": "27",
            "buyer_pos": "27",
            "buyer_lglnm": "Maharashtra Buyer Ltd",
            "buyer_loc": "Mumbai",
            "buyer_pin": "400002"
        },
        "trandt1": {
            "trancatg": "B2B",
            "igstonintra": "N",
            "reversecharge": "N"
        },
        "itemdtls": [
            {
                "slno": "1",
                "prdnm": "Port Vessel Movement",
                "hsncd": "9965",
                "qty": "1.00",
                "unitprice": "10000.00",
                "assval": "10000.00",
                "gstrate": "18.00",
                "igstval": "1800.00"
            }
        ]
    }

    model, audit_log = InvoicePayload.auto_correct_and_build(payload)

    assert model.igstonintra == "Y"
    assert model.reversecharge == "Y"
    item = model.itemdtls[0]
    assert Decimal(str(item.igstval)) == Decimal("1800.00")
    assert Decimal(str(item.cgstval)) == Decimal("0.00")
    assert Decimal(str(item.sgstval)) == Decimal("0.00")

    audit_entry = next((e for e in audit_log if 'set the flag "IgstOnIntra": "Y" under TranDtls' in e["description"]), None)
    assert audit_entry is not None
    assert audit_entry["corrected"] == "Y"


def test_scenario_3_auto_correct_payload_builder():
    """PayloadBuilder.auto_correct_and_build sets IgstOnIntra='Y' and RevChrg='Y' for exceptional intra IGST."""
    payload = {
        "self_gstin": "27ABCDE1234F1Z5",
        "is_exceptional_intra_igst": True,
        "supplierdt1": {
            "supplier_gstin": "27ABCDE1234F1Z5",
            "supplier_state": "27",
            "supplier_lglnm": "Maharashtra Seller Ltd",
            "supplier_loc": "Mumbai",
            "supplier_pin": "400001"
        },
        "buyerdt1": {
            "buyer_gstin": "27XYZAB9876C1Z1",
            "buyer_state": "27",
            "pos": "27",
            "buyer_lglnm": "Maharashtra Buyer Ltd",
            "buyer_loc": "Mumbai",
            "buyer_pin": "400002"
        },
        "trandt1": {
            "trancatg": "B2B",
            "igstonintra": "N",
            "reversecharge": "N"
        },
        "itemdtls": [
            {
                "prdnm": "Port Vessel Movement",
                "hsncd": "9965",
                "qty": "1.00",
                "unitrate": "10000.00",
                "assamt": "10000.00",
                "gstrate": "18.00",
                "igstamt": "1800.00"
            }
        ]
    }

    out_payload, audit_log = PayloadBuilder.auto_correct_and_build(payload)

    assert out_payload["trandt1"]["igstonintra"] == "Y"
    assert out_payload["trandt1"]["reversecharge"] == "Y"
    item = out_payload["itemdtls"][0]
    assert Decimal(item["igstamt"]) == Decimal("1800.00")
    assert Decimal(item["cgstamt"]) == Decimal("0.00")
    assert Decimal(item["sgstamt"]) == Decimal("0.00")

    audit_entry = next((e for e in audit_log if 'set the flag "IgstOnIntra": "Y" under TranDtls' in e["description"]), None)
    assert audit_entry is not None


# ============================================================================
# 5. AUTO-CORRECTION TESTS: SCENARIO 4 (SUMMARY VS. ITEM LEVEL MISMATCH)
# ============================================================================

def test_scenario_4_auto_correct_schemas_migration():
    """InvoicePayload.auto_correct_and_build reconciles ValDtls when header has IgstVal but items have CGST/SGST."""
    payload = {
        "self_gstin": "27ABCDE1234F1Z5",
        "supplierdt1": {
            "supplier_gstin": "27ABCDE1234F1Z5",
            "supplier_state": "27",
            "supplier_lglnm": "Maharashtra Seller Ltd",
            "supplier_loc": "Mumbai",
            "supplier_pin": "400001"
        },
        "buyerdt1": {
            "buyer_gstin": "27XYZAB9876C1Z1",
            "buyer_state": "27",
            "buyer_pos": "27",
            "buyer_lglnm": "Maharashtra Buyer Ltd",
            "buyer_loc": "Pune",
            "buyer_pin": "411001"
        },
        "itemdtls": [
            {
                "slno": "1",
                "prdnm": "Industrial Machinery Part",
                "hsncd": "8481",
                "qty": "1.00",
                "unitprice": "10000.00",
                "grossamt": "10000.00",
                "assval": "10000.00",
                "gstrate": "18.00",
                "cgstval": "900.00",
                "sgstval": "900.00",
                "igstval": "0.00",
                "totitemval": "11800.00"
            }
        ],
        "valdt1": {
            "ttlassval": "10000.00",
            "igstval": "1800.00",  # Header mismatch!
            "cgstval": "0.00",
            "sgstval": "0.00",
            "totinvval": "11800.00"
        }
    }

    model, audit_log = InvoicePayload.auto_correct_and_build(payload)

    assert Decimal(str(model.valdtls.igstval)) == Decimal("0.00")
    assert Decimal(str(model.valdtls.cgstval)) == Decimal("900.00")
    assert Decimal(str(model.valdtls.sgstval)) == Decimal("900.00")

    audit_entry = next((e for e in audit_log if "Header total tax values in ValDtls must match the sum of item-level taxes in ItemList." in e["description"]), None)
    assert audit_entry is not None
    assert audit_entry["original"] == "1800.00"
    assert audit_entry["corrected"] == "0.00"


def test_scenario_4_auto_correct_payload_builder():
    """PayloadBuilder.auto_correct_and_build reconciles ValDtls when header has IgstVal but items have CGST/SGST."""
    payload = {
        "self_gstin": "27ABCDE1234F1Z5",
        "supplierdt1": {
            "supplier_gstin": "27ABCDE1234F1Z5",
            "supplier_state": "27",
            "supplier_lglnm": "Maharashtra Seller Ltd",
            "supplier_loc": "Mumbai",
            "supplier_pin": "400001"
        },
        "buyerdt1": {
            "buyer_gstin": "27XYZAB9876C1Z1",
            "buyer_state": "27",
            "pos": "27",
            "buyer_lglnm": "Maharashtra Buyer Ltd",
            "buyer_loc": "Pune",
            "buyer_pin": "411001"
        },
        "itemdtls": [
            {
                "prdnm": "Industrial Machinery Part",
                "hsncd": "8481",
                "qty": "1.00",
                "unitrate": "10000.00",
                "grossamt": "10000.00",
                "assamt": "10000.00",
                "gstrate": "18.00",
                "cgstamt": "900.00",
                "sgstamt": "900.00",
                "igstamt": "0.00",
                "totitemval": "11800.00"
            }
        ],
        "valdt1": {
            "ttlassval": "10000.00",
            "igstval": "1800.00",  # Header mismatch!
            "cgstval": "0.00",
            "sgstval": "0.00",
            "totinvval": "11800.00"
        }
    }

    out_payload, audit_log = PayloadBuilder.auto_correct_and_build(payload)

    assert Decimal(out_payload["valdt1"]["igstval"]) == Decimal("0.00")
    assert Decimal(out_payload["valdt1"]["cgstval"]) == Decimal("900.00")
    assert Decimal(out_payload["valdt1"]["sgstval"]) == Decimal("900.00")

    audit_entry = next((e for e in audit_log if "Header total tax values in ValDtls must match the sum of item-level taxes in ItemList." in e["description"]), None)
    assert audit_entry is not None
    assert audit_entry["original"] == "1800.00"
    assert audit_entry["corrected"] == "0.00"


# ============================================================================
# 6. VALIDATION ENGINE DIAGNOSTIC CHECKS
# ============================================================================

def test_gst_validator_diagnoses_rule_2172():
    """GSTValidator outputs Error 2172 with rich diagnostic scenario classification."""
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
            "buyer_gstin": "27XYZAB9876C1Z1",
            "buyer_state": "27",
            "pos": "27",
            "buyer_lglnm": "Maharashtra Buyer Ltd",
            "buyer_loc": "Pune",
            "buyer_pin": "411001"
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
                "igstamt": 180,  # Illegal for intra-state
                "cgstamt": 0,
                "sgstamt": 0,
                "totitemval": 1180
            }
        ]
    }

    errors = GSTValidator.validate_invoice(failing_invoice)
    err_2172 = next((e for e in errors if e.get("error_code") == 2172), None)
    assert err_2172 is not None
    assert "Standard Intra-State Transaction" in err_2172["message"]
    assert "Clear IgstAmt and split tax equally between CGST and SGST" in err_2172["message"]


def test_rules_engine_diagnoses_rule_2172():
    """RulesEngine outputs Error 2172 with rich diagnostic scenario classification."""
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
            "buyer_gstin": "27XYZAB9876C1Z1",
            "buyer_state": "27",
            "pos": "27",
            "buyer_lglnm": "Maharashtra Buyer Ltd",
            "buyer_loc": "Pune",
            "buyer_pin": "411001"
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
                "igstamt": 180,
                "cgstamt": 0,
                "sgstamt": 0,
                "totitemval": 1180
            }
        ]
    }

    errors = RulesEngine.validate_invoice(failing_invoice)
    err_2172 = next((e for e in errors if e.get("error_code") == 2172), None)
    assert err_2172 is not None
    assert "Standard Intra-State Transaction" in err_2172["message"]
    assert "Clear IgstAmt and split tax equally between CGST and SGST" in err_2172["message"]


def test_model_validate_raises_nic_2172_with_diagnostic():
    """InvoicePayload.model_validate raises ValidationError containing Error 2172 and scenario diagnostic."""
    failing_invoice = {
        "self_gstin": "27ABCDE1234F1Z5",
        "docno": "INV-2026-001",
        "docdt": "25-10-2026",
        "docdt1": {
            "document_type": "INV",
            "docno": "INV-2026-001",
            "docdt": "25-10-2026"
        },
        "supplier": {
            "gstin": "27ABCDE1234F1Z5",
            "state": "27",
            "lglnm": "Maharashtra Seller Ltd",
            "loc": "Mumbai",
            "pin": "400001"
        },
        "buyer": {
            "gstin": "27XYZAB9876C1Z1",
            "state": "27",
            "pos": "27",
            "lglnm": "Maharashtra Buyer Ltd",
            "loc": "Pune",
            "pin": "411001"
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
                "hsn": "9403",
                "qty": 1,
                "unitprice": 1000,
                "totamt": 1000,
                "assval": 1000,
                "igstval": 180,
                "cgstval": 0,
                "sgstval": 0,
                "totitemval": 1180
            }
        ],
        "valdt1": {
            "ttlassval": "1000.00",
            "igstval": "180.00",
            "cgstval": "0.00",
            "sgstval": "0.00",
            "totinvval": "1180.00"
        }
    }

    with pytest.raises(Exception) as exc_info:
        InvoicePayload.model_validate(failing_invoice)
    err_str = str(exc_info.value)
    assert "2172" in err_str
    assert "For Intra-state, IGST is not applicable" in err_str
    assert "Standard Intra-State Transaction" in err_str
    assert "Clear IgstAmt and split tax equally between CGST and SGST" in err_str
