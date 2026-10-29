"""
Test Suite: NIC Error Codes 2213, 2227, and 2228 Statutory Compliance & Data Lakehouse Reconciliation.
File: tests/test_rules_2213_2227_2228_lakehouse.py

Validates Indian GST e-Invoicing (NIC / IRP):
1. Error Code 2213:
   "The supplier GSTIN cannot be URP" (SellerDtls.Gstin)
   Scenarios:
     - SUPPLIER_MARKED_AS_URP_BY_MISTAKE
     - REVERSE_CHARGE_RCM_INWARD_INVOICE_UPLOAD
     - TESTING_WITH_DUMMY_DATA

2. Error Code 2227:
   "For Sl. No {0}, SGST and CGST amounts are not equal" (ItemList[i].CgstAmt vs ItemList[i].SgstAmt)
   Formula:
     ItemList[i].CgstAmt = ItemList[i].SgstAmt = (ItemList[i].AssAmt * (GstRt / 2)) / 100
   Scenarios:
     - UNEQUAL_TAX_SPLIT
     - ASYMMETRIC_ROUNDING_ACROSS_TAXES
     - ACCIDENTAL_ZERO_IN_ONE_COMPONENT

3. Error Code 2228:
   "Item list cannot be empty" (ItemList / itemdtls)
   Scenarios:
     - EMPTY_ARRAY_PASSED
     - NULL_ARRAY_PASSED
     - ERP_DATA_EXTRACTION_GLITCH
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
    classify_rule_2213_diagnostic,
    classify_rule_2227_diagnostic,
    classify_rule_2228_diagnostic,
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
    """A standard clean intra-state invoice with valid seller, equal CGST/SGST, and valid line items."""
    return {
        "self_gstin": "27AAAAA0000A1Z5",
        "docno": "INV-2026-VAL01",
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
                "cesval": "0.00",
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
            "othchrg": "0.00",
            "discount": "0.00",
            "rndoffamt": "0.00",
            "totinvval": "118000.00"
        }
    }


# ==============================================================================
# 1. DIAGNOSTIC CLASSIFIER UNIT TESTS: RULE 2213
# ==============================================================================

class TestRule2213Diagnostics:
    """Tests for classify_rule_2213_diagnostic across all statutory scenarios."""

    def test_valid_supplier_gstin(self):
        diag = classify_rule_2213_diagnostic("27AAAAA0000A1Z5")
        assert diag["is_valid"] is True
        assert diag["scenario"] == "VALID"
        assert diag["error_code"] is None

    def test_scenario_1_supplier_marked_as_urp_by_mistake(self):
        diag = classify_rule_2213_diagnostic("URP", supplier_state="27")
        assert diag["is_valid"] is False
        assert diag["error_code"] == 2213
        assert diag["scenario"] == "SUPPLIER_MARKED_AS_URP_BY_MISTAKE"
        assert diag["action"] == "PASS_ACTIVE_SELLER_GSTIN"
        assert diag["rectified_gstin"] == "27AAAAA0000A1Z5"
        assert "active, 15-character registered GSTIN" in diag["reason"]

    def test_scenario_2_rcm_inward_upload(self):
        diag = classify_rule_2213_diagnostic("URP", is_rcm_inward=True)
        assert diag["is_valid"] is False
        assert diag["error_code"] == 2213
        assert diag["scenario"] == "REVERSE_CHARGE_RCM_INWARD_INVOICE_UPLOAD"
        assert diag["action"] == "DO_NOT_UPLOAD_TO_IRP"
        assert diag["irnreq"] == "N"
        assert "GSTR-3B" in diag["reason"]

    def test_scenario_3_testing_with_dummy_data(self):
        diag = classify_rule_2213_diagnostic("URP", is_dummy_testing=True, supplier_state="29")
        assert diag["is_valid"] is False
        assert diag["error_code"] == 2213
        assert diag["scenario"] == "TESTING_WITH_DUMMY_DATA"
        assert diag["action"] == "USE_SANDBOX_ACTIVE_GSTIN"
        assert diag["rectified_gstin"] == "29AAAAA0000A1Z5"
        assert "sandbox" in diag["resolution"]


# ==============================================================================
# 2. DIAGNOSTIC CLASSIFIER UNIT TESTS: RULE 2227
# ==============================================================================

class TestRule2227Diagnostics:
    """Tests for classify_rule_2227_diagnostic across all statutory scenarios."""

    def test_valid_equal_tax_split(self):
        diag = classify_rule_2227_diagnostic(
            cgstamt="900.00",
            sgstamt="900.00",
            assamt="10000.00",
            gstrate="18.00"
        )
        assert diag["is_valid"] is True
        assert diag["scenario"] == "VALID"
        assert diag["error_code"] is None

    def test_scenario_1_unequal_tax_split(self):
        diag = classify_rule_2227_diagnostic(
            cgstamt="1000.00",
            sgstamt="800.00",
            assamt="10000.00",
            gstrate="18.00"
        )
        assert diag["is_valid"] is False
        assert diag["error_code"] == 2227
        assert diag["scenario"] == "UNEQUAL_TAX_SPLIT"
        assert diag["action"] == "SPLIT_TAX_IDENTICALLY"
        assert diag["correct_payload"]["CgstAmt"] == Decimal("900.00")
        assert diag["correct_payload"]["SgstAmt"] == Decimal("900.00")

    def test_scenario_2_asymmetric_rounding(self):
        # Difference is 0.01 (<= 0.05)
        diag = classify_rule_2227_diagnostic(
            cgstamt="41.67",
            sgstamt="41.66",
            assamt="462.94",
            gstrate="18.00"
        )
        assert diag["is_valid"] is False
        assert diag["error_code"] == 2227
        assert diag["scenario"] == "ASYMMETRIC_ROUNDING_ACROSS_TAXES"
        assert diag["action"] == "ROUND_TAXES_EQUALLY"
        assert diag["correct_payload"]["CgstAmt"] == Decimal("41.67")
        assert diag["correct_payload"]["SgstAmt"] == Decimal("41.67")

    def test_scenario_3_accidental_zero(self):
        diag = classify_rule_2227_diagnostic(
            cgstamt="900.00",
            sgstamt="0.00",
            assamt="10000.00",
            gstrate="18.00"
        )
        assert diag["is_valid"] is False
        assert diag["error_code"] == 2227
        assert diag["scenario"] == "ACCIDENTAL_ZERO_IN_ONE_COMPONENT"
        assert diag["action"] == "POPULATE_MATCHING_INTRA_TAX_COMPONENT"
        assert diag["correct_payload"]["CgstAmt"] == Decimal("900.00")
        assert diag["correct_payload"]["SgstAmt"] == Decimal("900.00")


# ==============================================================================
# 3. DIAGNOSTIC CLASSIFIER UNIT TESTS: RULE 2228
# ==============================================================================

class TestRule2228Diagnostics:
    """Tests for classify_rule_2228_diagnostic across all statutory scenarios."""

    def test_valid_item_list(self):
        diag = classify_rule_2228_diagnostic([{"slno": "1", "prdnm": "Widget"}])
        assert diag["is_valid"] is True
        assert diag["scenario"] == "VALID"
        assert diag["item_count"] == 1

    def test_scenario_1_empty_array(self):
        diag = classify_rule_2228_diagnostic([])
        assert diag["is_valid"] is False
        assert diag["error_code"] == 2228
        assert diag["scenario"] == "EMPTY_ARRAY_PASSED"
        assert diag["action"] == "ADD_LINE_ITEM_OBJECT"
        assert "at least 1 line item" in diag["reason"]

    def test_scenario_2_null_array(self):
        diag = classify_rule_2228_diagnostic(None)
        assert diag["is_valid"] is False
        assert diag["error_code"] == 2228
        assert diag["scenario"] == "NULL_ARRAY_PASSED"
        assert diag["action"] == "PROVIDE_NON_NULL_ITEM_LIST"
        assert "mandatory array field" in diag["reason"]

    def test_scenario_3_erp_glitch(self):
        diag = classify_rule_2228_diagnostic([], is_erp_extraction_glitch=True)
        assert diag["is_valid"] is False
        assert diag["error_code"] == 2228
        assert diag["scenario"] == "ERP_DATA_EXTRACTION_GLITCH"
        assert diag["action"] == "AWAIT_LINE_ITEMS_COMMIT_BEFORE_DISPATCH"
        assert "backend serialization waits" in diag["reason"]


# ==============================================================================
# 4. PRE-API VALIDATOR INTEGRATION TESTS (GSTValidator & RulesEngine)
# ==============================================================================

class TestPreApiValidators2213_2227_2228:
    """Validates pre-API rejection codes 2213, 2227, 2228 without false code shadowing."""

    def test_rule_2213_rejection_no_shadowing_by_2289(self, clean_valid_invoice):
        """CRITICAL: Ensure URP is caught by Rule 2213 and not shadowed by length check (2289)."""
        inv = dict(clean_valid_invoice)
        inv["self_gstin"] = "URP"
        inv["supplier"] = dict(clean_valid_invoice["supplier"])
        inv["supplier"]["gstin"] = "URP"

        # Validate with GSTValidator
        errs = GSTValidator.validate_invoice(inv)
        err_codes = [e.get("error_code") if isinstance(e, dict) else e.code for e in errs]
        assert 2213 in err_codes, f"Expected 2213 in error codes, got {err_codes}"
        assert 2289 not in err_codes, f"Rule 2213 was incorrectly shadowed by 2289: {err_codes}"

        # Validate with RulesEngine
        engine = RulesEngine()
        re_errs = engine.validate_invoice(inv)
        re_codes = [e.get("error_code") if isinstance(e, dict) else e.code for e in re_errs]
        assert 2213 in re_codes, f"RulesEngine did not produce 2213: {re_codes}"

    def test_rule_2213_rcm_inward_invoice(self, clean_valid_invoice):
        inv = dict(clean_valid_invoice)
        inv["self_gstin"] = "URP"
        inv["supplier"] = dict(clean_valid_invoice["supplier"])
        inv["supplier"]["gstin"] = "URP"
        inv["is_rcm_inward"] = True

        errs = GSTValidator.validate_invoice(inv)
        err_codes = [e.get("error_code") if isinstance(e, dict) else e.code for e in errs]
        assert 2213 in err_codes
        # Verify diagnostic reason mentions GSTR-3B / RCM
        err_2213 = next(e for e in errs if (e.get("error_code") if isinstance(e, dict) else e.code) == 2213)
        msg_str = err_2213.get("message") if isinstance(err_2213, dict) else err_2213.message
        assert "GSTR-3B" in msg_str or "RCM" in msg_str

    def test_rule_2227_unequal_cgst_sgst(self, clean_valid_invoice):
        inv = dict(clean_valid_invoice)
        inv["itemdtls"] = [
            {
                "slno": "1",
                "prdnm": "Server Blade",
                "hsncd": "84713010",
                "qty": "1.00",
                "unitprice": "10000.00",
                "totamt": "10000.00",
                "discount": "0.00",
                "assval": "10000.00",
                "gstrate": 18.0,
                "cgstval": "1000.00",  # Unequal! (1000 vs 800)
                "sgstval": "800.00",
                "igstval": "0.00",
                "totitemval": "11800.00"
            }
        ]

        errs = GSTValidator.validate_invoice(inv)
        err_codes = [e.get("error_code") if isinstance(e, dict) else e.code for e in errs]
        assert 2227 in err_codes

    def test_rule_2227_asymmetric_rounding(self, clean_valid_invoice):
        inv = dict(clean_valid_invoice)
        inv["itemdtls"] = [
            {
                "slno": "1",
                "prdnm": "Hardware Widget",
                "hsncd": "84713010",
                "qty": "1.00",
                "unitprice": "462.94",
                "totamt": "462.94",
                "discount": "0.00",
                "assval": "462.94",
                "gstrate": 18.0,
                "cgstval": "41.67",  # 41.67 vs 41.66
                "sgstval": "41.66",
                "igstval": "0.00",
                "totitemval": "546.27"
            }
        ]

        errs = GSTValidator.validate_invoice(inv)
        err_codes = [e.get("error_code") if isinstance(e, dict) else e.code for e in errs]
        assert 2227 in err_codes

    def test_rule_2228_empty_item_list(self, clean_valid_invoice):
        inv = dict(clean_valid_invoice)
        inv["itemdtls"] = []

        errs = GSTValidator.validate_invoice(inv)
        err_codes = [e.get("error_code") if isinstance(e, dict) else e.code for e in errs]
        assert 2228 in err_codes

    def test_rule_2228_null_item_list(self, clean_valid_invoice):
        inv = dict(clean_valid_invoice)
        inv["itemdtls"] = None
        inv["is_null_array"] = True

        errs = GSTValidator.validate_invoice(inv)
        err_codes = [e.get("error_code") if isinstance(e, dict) else e.code for e in errs]
        assert 2228 in err_codes

    def test_rule_2228_erp_glitch(self, clean_valid_invoice):
        inv = dict(clean_valid_invoice)
        inv["itemdtls"] = []
        inv["is_erp_extraction_glitch"] = True

        errs = GSTValidator.validate_invoice(inv)
        err_codes = [e.get("error_code") if isinstance(e, dict) else e.code for e in errs]
        assert 2228 in err_codes
        err_2228 = next(e for e in errs if (e.get("error_code") if isinstance(e, dict) else e.code) == 2228)
        msg_str = err_2228.get("message") if isinstance(err_2228, dict) else err_2228.message
        assert "backend serialization waits" in msg_str

    def test_clean_valid_invoice_passes_without_errors(self, clean_valid_invoice):
        errs = GSTValidator.validate_invoice(clean_valid_invoice)
        assert len(errs) == 0, f"Expected 0 errors for clean invoice, got: {errs}"


# ==============================================================================
# 5. AUTO-CORRECTION AND LAKEHOUSE STORAGE TESTS
# ==============================================================================

class TestAutoCorrectionAndLakehouseParquet:
    """Validates automatic correction and Parquet storage round-trip fidelity."""

    def test_auto_correct_and_build_rectifies_urp_and_tax_split(self, clean_valid_invoice):
        dirty = dict(clean_valid_invoice)
        dirty["self_gstin"] = "URP"
        dirty["supplier"] = dict(clean_valid_invoice["supplier"])
        dirty["supplier"]["gstin"] = "URP"
        dirty["supplier"]["state"] = "27"
        # Make taxes unequal in item
        dirty["itemdtls"][0]["cgstval"] = "1000.00"
        dirty["itemdtls"][0]["sgstval"] = "800.00"

        payload, audit_log = InvoicePayload.auto_correct_and_build(dirty)

        # 1. Supplier GSTIN should be rectified to active registered GSTIN (27AAAAA0000A1Z5)
        assert payload.supplier.gstin != "URP"
        assert payload.supplier.gstin == "27AAAAA0000A1Z5"
        assert payload.self_gstin == "27AAAAA0000A1Z5"

        # 2. Taxes should be equalized to 9000.00 (or statutory rate split)
        itm = payload.itemdtls[0]
        assert itm.cgstval == itm.sgstval

        # 3. Audit trail should contain NIC_RULE_2213 and NIC_RULE_2227 entries
        categories = [log["category"] for log in audit_log]
        assert any("2213" in c for c in categories), f"Audit log did not record 2213: {categories}"
        assert any("2227" in c for c in categories), f"Audit log did not record 2227: {categories}"

    def test_auto_correct_and_build_handles_empty_item_list(self, clean_valid_invoice):
        dirty = dict(clean_valid_invoice)
        dirty["itemdtls"] = []

        payload, audit_log = InvoicePayload.auto_correct_and_build(dirty)
        assert len(payload.itemdtls) >= 1
        categories = [log["category"] for log in audit_log]
        assert any("2228" in c for c in categories), f"Audit log did not record 2228: {categories}"

    def test_lakehouse_parquet_storage_roundtrip(self, clean_valid_invoice):
        """Validates storing clean invoice payload to Parquet and reading back with schema compliance."""
        payload, _ = InvoicePayload.auto_correct_and_build(clean_valid_invoice)

        with tempfile.TemporaryDirectory() as tmpdir:
            pq_path = Path(tmpdir) / "test_rules_2213_2227_2228.parquet"
            flattened = flatten_invoice_payload(payload)

            # Write to parquet
            write_parquet(flattened, pq_path)
            assert pq_path.exists()

            # Read back
            df = read_parquet(pq_path)
            assert len(df) == 1
            assert df["invoice_id"].iloc[0] == "INV-2026-VAL01"
            assert df["supplier_gstin"].iloc[0] == "27AAAAA0000A1Z5"
            assert float(df["inv_total_value"].iloc[0]) == 118000.00
            assert float(df["inv_cgst_amount"].iloc[0]) == float(df["inv_sgst_amount"].iloc[0])
