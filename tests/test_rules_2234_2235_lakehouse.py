"""
Test Suite: NIC Error Codes 2234 & 2235 Statutory Compliance & Data Lakehouse Reconciliation.
File: tests/test_rules_2234_2235_lakehouse.py

Validates Indian GST e-Invoicing (NIC / IRP) Statutory Requirements:
1. Error Code 2234:
   "Item CGST & SGST Formula Mismatch"
   - Occurs when the CgstAmt and SgstAmt calculated for a line item deviate from
     the product of the taxable amount (AssAmt) and half the tax rate (GstRt / 2)
     beyond the permitted tolerance of ±1.00.
   - Formula:
     CgstAmt = SgstAmt = (AssAmt * (GstRt / 2)) / 100  (Tolerance: ±1.00)
   Scenarios:
     - TAX_CALCULATED_ON_GROSS_INSTEAD_OF_ASSAMT: TotAmt=10000, Disc=2000, AssAmt=8000, GstRt=18 -> Cgst=720, Sgst=720
     - FULL_TAX_APPLIED_TO_BOTH_FIELDS: AssAmt=10000, GstRt=18 -> Cgst=900, Sgst=900 (not 1800)
     - RATE_VS_AMOUNT_DISCONNECT: AssAmt=10000, GstRt=12 -> Cgst=600, Sgst=600 (not 900)
     - ROUNDING_DEVIATION_EXCEEDING_ONE_RUPEE: Tax computes to 45.10, ERP sends 47.00
     - VALID: Within ±1.00 tolerance

2. Error Code 2235:
   "Item IGST Formula Mismatch"
   - Occurs when the IgstAmt calculated for a line item deviates from the product
     of the taxable amount (AssAmt) and the full tax rate (GstRt) beyond the permitted tolerance of ±1.00.
   - Formula:
     IgstAmt = (AssAmt * GstRt) / 100  (Tolerance: ±1.00)
   Scenarios:
     - TAX_CALCULATED_ON_GROSS_INSTEAD_OF_ASSAMT: TotAmt=10000, Disc=1000, AssAmt=9000, GstRt=18 -> Igst=1620
     - HALF_RATE_APPLIED_INSTEAD_OF_FULL_RATE: AssAmt=10000, GstRt=18 -> Igst=1800 (not 900)
     - TAX_RATE_MISMATCHES_TAX_AMOUNT: AssAmt=50000, GstRt=18 -> Igst=9000 (not 6000)
     - ROUNDING_DIFFERENCE_GREATER_THAN_ONE_RUPEE: Exact tax 181.20, ERP sends 183.00
     - VALID: Within ±1.00 tolerance

3. Lakehouse Data Pipeline:
   - Flattening, Parquet storage, schema verification, and round-trip reconciliation.
"""

import os
import shutil
import tempfile
from decimal import Decimal
import pytest

from src.ingestion.schemas import (
    InvoicePayload,
    classify_rule_2234_diagnostic,
    classify_rule_2235_diagnostic,
    NICValidationError,
)
from src.ingestion.storage import (
    flatten_invoice_payload,
    write_parquet,
    read_parquet,
)
from Template_Converters.validator import GSTValidator
from src.rules.rules_engine import RulesEngine


# ==============================================================================
# FIXTURES
# ==============================================================================

@pytest.fixture
def clean_intra_invoice():
    """Clean intra-state B2B invoice (Maharashtra to Maharashtra) with 18% GST."""
    return {
        "self_gstin": "27AAAAA0000A1Z5",
        "docno": "INV-2026-INTRA01",
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
                "prdnm": "Heavy Duty Industrial Motor",
                "hsncd": "85011011",
                "qty": "1.00",
                "uqc": "NOS",
                "unit": "NOS",
                "unitprice": "10000.00",
                "totamt": "10000.00",
                "discount": "2000.00",
                "assval": "8000.00",
                "gstrate": 18.0,
                "cgstval": "720.00",
                "sgstval": "720.00",
                "igstval": "0.00",
                "totitemval": "9440.00"
            }
        ],
        "valdtls": {
            "assval": "8000.00",
            "cgstval": "720.00",
            "sgstval": "720.00",
            "igstval": "0.00",
            "cesval": "0.00",
            "stcesval": "0.00",
            "discount": "0.00",
            "othchrg": "0.00",
            "rndoffamt": "0.00",
            "totinvval": "9440.00"
        }
    }


@pytest.fixture
def clean_inter_invoice():
    """Clean inter-state B2B invoice (Maharashtra to Karnataka) with 18% IGST."""
    return {
        "self_gstin": "27AAAAA0000A1Z5",
        "docno": "INV-2026-INTER01",
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
            "gstin": "29BBBBB1111B1Z2",
            "lglnm": "Karnataka Logistics Corp",
            "bnm": "Tech Park",
            "state": "29",
            "pos": "29",
            "pin": "560001",
            "loc": "Bengaluru"
        },
        "itemdtls": [
            {
                "slno": "1",
                "prdnm": "Microcontroller Circuit Board",
                "hsncd": "85423100",
                "qty": "2.00",
                "uqc": "NOS",
                "unit": "NOS",
                "unitprice": "5000.00",
                "totamt": "10000.00",
                "discount": "1000.00",
                "assval": "9000.00",
                "gstrate": 18.0,
                "cgstval": "0.00",
                "sgstval": "0.00",
                "igstval": "1620.00",
                "totitemval": "10620.00"
            }
        ],
        "valdtls": {
            "assval": "9000.00",
            "cgstval": "0.00",
            "sgstval": "0.00",
            "igstval": "1620.00",
            "cesval": "0.00",
            "stcesval": "0.00",
            "discount": "0.00",
            "othchrg": "0.00",
            "rndoffamt": "0.00",
            "totinvval": "10620.00"
        }
    }


# ==============================================================================
# RULE 2234: DIAGNOSTIC CLASSIFIER TESTS
# ==============================================================================

def test_rule_2234_scenario_1_tax_calculated_on_gross():
    """Scenario 1: Tax Calculated on Gross (TotAmt) Instead of Taxable Base (AssAmt)."""
    # TotAmt = 10000, Discount = 2000, AssAmt = 8000, GstRt = 18. Sent: Cgst=900, Sgst=900
    diag = classify_rule_2234_diagnostic(
        cgstamt=900.00,
        sgstamt=900.00,
        assamt=8000.00,
        gstrate=18.0,
        totamt=10000.00,
        discount=2000.00,
        item_slno="1"
    )
    assert diag["error_code"] == 2234
    assert diag["scenario"] == "TAX_CALCULATED_ON_GROSS_INSTEAD_OF_ASSAMT"
    assert not diag["is_valid"]
    assert diag["action"] == "RECALCULATE_ON_ASSESSABLE_VALUE"
    assert diag["expected_cgst"] == Decimal("720.00")
    assert diag["expected_sgst"] == Decimal("720.00")
    assert "discounted assessable value" in diag["reason"]


def test_rule_2234_scenario_2_full_tax_applied_to_both_fields():
    """Scenario 2: Full Tax Applied to Both Fields."""
    # AssAmt = 10000, GstRt = 18. Sent: Cgst=1800, Sgst=1800
    diag = classify_rule_2234_diagnostic(
        cgstamt=1800.00,
        sgstamt=1800.00,
        assamt=10000.00,
        gstrate=18.0,
        totamt=10000.00,
        discount=0.00,
        item_slno="1"
    )
    assert diag["error_code"] == 2234
    assert diag["scenario"] == "FULL_TAX_APPLIED_TO_BOTH_FIELDS"
    assert not diag["is_valid"]
    assert diag["action"] == "SPLIT_RATE_EQUALLY_INTO_HALVES"
    assert diag["expected_cgst"] == Decimal("900.00")
    assert diag["expected_sgst"] == Decimal("900.00")


def test_rule_2234_scenario_3_rate_vs_amount_disconnect():
    """Scenario 3: Rate vs Amount Disconnect."""
    # AssAmt = 10000, GstRt = 12. Sent: Cgst=900, Sgst=900 (reflects 18% rate)
    diag = classify_rule_2234_diagnostic(
        cgstamt=900.00,
        sgstamt=900.00,
        assamt=10000.00,
        gstrate=12.0,
        totamt=10000.00,
        discount=0.00,
        item_slno="1"
    )
    assert diag["error_code"] == 2234
    assert diag["scenario"] == "RATE_VS_AMOUNT_DISCONNECT"
    assert not diag["is_valid"]
    assert diag["action"] == "RECONCILE_RATE_AND_AMOUNTS"
    assert diag["expected_cgst"] == Decimal("600.00")
    assert diag["expected_sgst"] == Decimal("600.00")


def test_rule_2234_scenario_4_rounding_deviation_exceeding_one_rupee():
    """Scenario 4: Rounding Deviation Exceeding ₹1.00."""
    # AssAmt = 501.11, GstRt = 18% -> half rate 9% = 45.10. Sent: Cgst=47.00, Sgst=47.00
    diag = classify_rule_2234_diagnostic(
        cgstamt=47.00,
        sgstamt=47.00,
        assamt=501.11,
        gstrate=18.0,
        totamt=501.11,
        discount=0.00,
        item_slno="1"
    )
    assert diag["error_code"] == 2234
    assert diag["scenario"] == "ROUNDING_DEVIATION_EXCEEDING_ONE_RUPEE"
    assert not diag["is_valid"]
    assert diag["action"] == "ALIGN_TO_PERMITTED_TOLERANCE"
    assert diag["expected_cgst"] == Decimal("45.10")
    assert diag["expected_sgst"] == Decimal("45.10")


def test_rule_2234_valid_formula():
    """Valid Scenario: CGST and SGST equal AssAmt * (GstRt / 2) within ±1.00 tolerance."""
    diag = classify_rule_2234_diagnostic(
        cgstamt=720.00,
        sgstamt=720.00,
        assamt=8000.00,
        gstrate=18.0,
        totamt=10000.00,
        discount=2000.00,
        item_slno="1"
    )
    assert diag["error_code"] is None
    assert diag["scenario"] == "VALID"
    assert diag["is_valid"]


# ==============================================================================
# RULE 2235: DIAGNOSTIC CLASSIFIER TESTS
# ==============================================================================

def test_rule_2235_scenario_1_tax_calculated_on_gross():
    """Scenario 1: Tax Calculated on Gross (TotAmt) Instead of Taxable Base (AssAmt)."""
    # TotAmt = 10000, Discount = 1000, AssAmt = 9000, GstRt = 18. Sent: Igst=1800
    diag = classify_rule_2235_diagnostic(
        igstamt=1800.00,
        assamt=9000.00,
        gstrate=18.0,
        totamt=10000.00,
        discount=1000.00,
        item_slno="1"
    )
    assert diag["error_code"] == 2235
    assert diag["scenario"] == "TAX_CALCULATED_ON_GROSS_INSTEAD_OF_ASSAMT"
    assert not diag["is_valid"]
    assert diag["action"] == "RECALCULATE_ON_ASSESSABLE_VALUE"
    assert diag["expected_igst"] == Decimal("1620.00")
    assert "assessable value" in diag["reason"]


def test_rule_2235_scenario_2_half_rate_applied_instead_of_full_rate():
    """Scenario 2: Half Rate Applied Instead of Full Rate."""
    # AssAmt = 10000, GstRt = 18. Sent: Igst=900
    diag = classify_rule_2235_diagnostic(
        igstamt=900.00,
        assamt=10000.00,
        gstrate=18.0,
        totamt=10000.00,
        discount=0.00,
        item_slno="1"
    )
    assert diag["error_code"] == 2235
    assert diag["scenario"] == "HALF_RATE_APPLIED_INSTEAD_OF_FULL_RATE"
    assert not diag["is_valid"]
    assert diag["action"] == "APPLY_FULL_RATE_TO_IGST"
    assert diag["expected_igst"] == Decimal("1800.00")


def test_rule_2235_scenario_3_tax_rate_mismatches_tax_amount():
    """Scenario 3: Tax Rate (GstRt) Mismatches Tax Amount."""
    # AssAmt = 50000, GstRt = 18. Sent: Igst=6000 (reflects 12% rate)
    diag = classify_rule_2235_diagnostic(
        igstamt=6000.00,
        assamt=50000.00,
        gstrate=18.0,
        totamt=50000.00,
        discount=0.00,
        item_slno="1"
    )
    assert diag["error_code"] == 2235
    assert diag["scenario"] == "TAX_RATE_MISMATCHES_TAX_AMOUNT"
    assert not diag["is_valid"]
    assert diag["action"] == "RECONCILE_RATE_AND_AMOUNTS"
    assert diag["expected_igst"] == Decimal("9000.00")


def test_rule_2235_scenario_4_rounding_difference_greater_than_one_rupee():
    """Scenario 4: Rounding Difference Greater Than ₹1.00."""
    # Exact tax is 181.20, but ERP sends 183.00
    diag = classify_rule_2235_diagnostic(
        igstamt=183.00,
        assamt=1006.67,
        gstrate=18.0,
        totamt=1006.67,
        discount=0.00,
        item_slno="1"
    )
    assert diag["error_code"] == 2235
    assert diag["scenario"] == "ROUNDING_DIFFERENCE_GREATER_THAN_ONE_RUPEE"
    assert not diag["is_valid"]
    assert diag["action"] == "ALIGN_TO_PERMITTED_TOLERANCE"
    assert diag["expected_igst"] == Decimal("181.20")


def test_rule_2235_valid_formula():
    """Valid Scenario: IGST equals AssAmt * GstRt within ±1.00 tolerance."""
    diag = classify_rule_2235_diagnostic(
        igstamt=1620.00,
        assamt=9000.00,
        gstrate=18.0,
        totamt=10000.00,
        discount=1000.00,
        item_slno="1"
    )
    assert diag["error_code"] is None
    assert diag["scenario"] == "VALID"
    assert diag["is_valid"]


# ==============================================================================
# RULE 2234 & 2235: GSTVALIDATOR PRE-API VALIDATION
# ==============================================================================

def test_rule_2234_gst_validator_catches_formula_mismatch(clean_intra_invoice):
    """GSTValidator catches CGST/SGST formula mismatch (Error 2234)."""
    inv = dict(clean_intra_invoice)
    items = [dict(it) for it in inv["itemdtls"]]
    items[0]["cgstval"] = "900.00"  # Calculated on Gross (10000) instead of AssAmt (8000)
    items[0]["sgstval"] = "900.00"
    inv["itemdtls"] = items
    errors = GSTValidator.validate_invoice(inv)
    assert any(e.get("error_code") == 2234 for e in errors)


def test_rule_2235_gst_validator_catches_formula_mismatch(clean_inter_invoice):
    """GSTValidator catches IGST formula mismatch (Error 2235)."""
    inv = dict(clean_inter_invoice)
    items = [dict(it) for it in inv["itemdtls"]]
    items[0]["igstval"] = "900.00"  # Half rate applied instead of full 18%
    inv["itemdtls"] = items
    errors = GSTValidator.validate_invoice(inv)
    assert any(e.get("error_code") == 2235 for e in errors)


def test_rules_2234_2235_gst_validator_passes_valid(clean_intra_invoice, clean_inter_invoice):
    """GSTValidator produces 0 errors on clean intra and inter invoices."""
    assert len(GSTValidator.validate_invoice(clean_intra_invoice)) == 0
    assert len(GSTValidator.validate_invoice(clean_inter_invoice)) == 0


# ==============================================================================
# RULE 2234 & 2235: RULES ENGINE TESTS
# ==============================================================================

def test_rule_2234_rules_engine_catches_formula_mismatch(clean_intra_invoice):
    """RulesEngine catches CGST/SGST formula mismatch (Error 2234)."""
    inv = dict(clean_intra_invoice)
    items = [dict(it) for it in inv["itemdtls"]]
    items[0]["cgstval"] = "1800.00"  # Full tax applied to both
    items[0]["sgstval"] = "1800.00"
    inv["itemdtls"] = items
    errors = RulesEngine.validate_invoice(inv)
    assert any(e.get("error_code") == 2234 for e in errors)


def test_rule_2235_rules_engine_catches_formula_mismatch(clean_inter_invoice):
    """RulesEngine catches IGST formula mismatch (Error 2235)."""
    inv = dict(clean_inter_invoice)
    items = [dict(it) for it in inv["itemdtls"]]
    items[0]["igstval"] = "1800.00"  # Tax on gross instead of assamt 9000
    inv["itemdtls"] = items
    errors = RulesEngine.validate_invoice(inv)
    assert any(e.get("error_code") == 2235 for e in errors)


# ==============================================================================
# RULE 2234 & 2235: PYDANTIC CROSS-MODEL VALIDATION
# ==============================================================================

def test_rule_2234_pydantic_schema_rejection(clean_intra_invoice):
    """InvoicePayload.model_validate raises NIC-2234 when line item CGST/SGST deviates beyond ±1.00."""
    inv = dict(clean_intra_invoice)
    items = [dict(it) for it in inv["itemdtls"]]
    items[0]["cgstval"] = "900.00"
    items[0]["sgstval"] = "900.00"
    items[0]["totitemval"] = "9800.00"
    inv["itemdtls"] = items
    inv["valdtls"] = dict(inv["valdtls"])
    inv["valdtls"]["cgstval"] = "900.00"
    inv["valdtls"]["sgstval"] = "900.00"
    inv["valdtls"]["totinvval"] = "9800.00"
    with pytest.raises(Exception) as exc_info:
        InvoicePayload.model_validate(inv)
    err_str = str(exc_info.value)
    assert "2234" in err_str


def test_rule_2235_pydantic_schema_rejection(clean_inter_invoice):
    """InvoicePayload.model_validate raises NIC-2235 when line item IGST deviates beyond ±1.00."""
    inv = dict(clean_inter_invoice)
    items = [dict(it) for it in inv["itemdtls"]]
    items[0]["igstval"] = "900.00"
    items[0]["totitemval"] = "9900.00"
    inv["itemdtls"] = items
    inv["valdtls"] = dict(inv["valdtls"])
    inv["valdtls"]["igstval"] = "900.00"
    inv["valdtls"]["totinvval"] = "9900.00"
    with pytest.raises(Exception) as exc_info:
        InvoicePayload.model_validate(inv)
    err_str = str(exc_info.value)
    assert "2235" in err_str


# ==============================================================================
# RULE 2234 & 2235: AUTO-CORRECT AND BUILD AUDIT LOG TESTS
# ==============================================================================

def test_rule_2234_auto_correct_cgst_sgst(clean_intra_invoice):
    """auto_correct_and_build recalculates CGST/SGST on AssAmt and logs audit trail."""
    inv = dict(clean_intra_invoice)
    items = [dict(it) for it in inv["itemdtls"]]
    items[0]["cgstval"] = "900.00"  # Erroneously calculated on TotAmt 10000
    items[0]["sgstval"] = "900.00"
    inv["itemdtls"] = items
    model, audit_logs = InvoicePayload.auto_correct_and_build(inv)
    assert model.itemdtls[0].cgstval == Decimal("720.00")
    assert model.itemdtls[0].sgstval == Decimal("720.00")
    assert any("2234" in log.get("category", "") for log in audit_logs)


def test_rule_2235_auto_correct_igst(clean_inter_invoice):
    """auto_correct_and_build recalculates IGST on AssAmt and logs audit trail."""
    inv = dict(clean_inter_invoice)
    items = [dict(it) for it in inv["itemdtls"]]
    items[0]["igstval"] = "900.00"  # Half rate applied instead of full 18%
    inv["itemdtls"] = items
    model, audit_logs = InvoicePayload.auto_correct_and_build(inv)
    assert model.itemdtls[0].igstval == Decimal("1620.00")
    assert any("2235" in log.get("category", "") for log in audit_logs)


# ==============================================================================
# DATA LAKEHOUSE PARQUET RECONCILIATION
# ==============================================================================

def test_lakehouse_parquet_persistence_roundtrip(clean_intra_invoice, clean_inter_invoice):
    """Tests flattening, Parquet storage, and round-trip read for intra and inter invoices."""
    model_intra = InvoicePayload.model_validate(clean_intra_invoice)
    rows_intra = flatten_invoice_payload(model_intra)
    assert len(rows_intra) == 1
    assert float(rows_intra[0]["cgst_amount"]) == 720.00
    assert float(rows_intra[0]["sgst_amount"]) == 720.00

    model_inter = InvoicePayload.model_validate(clean_inter_invoice)
    rows_inter = flatten_invoice_payload(model_inter)
    assert len(rows_inter) == 1
    assert float(rows_inter[0]["igst_amount"]) == 1620.00

    temp_dir = tempfile.mkdtemp()
    try:
        parquet_path = os.path.join(temp_dir, "test_rules_2234_2235.parquet")
        all_rows = rows_intra + rows_inter
        write_parquet(all_rows, parquet_path)

        df = read_parquet(parquet_path)
        assert len(df) == 2

        intra_record = df[df["invoice_id"] == "INV-2026-INTRA01"].iloc[0]
        assert float(intra_record["cgst_amount"]) == 720.00
        assert float(intra_record["sgst_amount"]) == 720.00

        inter_record = df[df["invoice_id"] == "INV-2026-INTER01"].iloc[0]
        assert float(inter_record["igst_amount"]) == 1620.00
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
