"""
Test Suite: NIC Error Code 2177 Statutory Compliance & Data Lakehouse UQC Module.
File: tests/test_rule_2177_uqc_lakehouse.py

Validates:
1. NIC Error Code 2177 Master List & Catalog Definitions:
   - Official 44 Unit Quantity Codes (UQC) prescribed by NIC / GSTN portal.
   - Rejection of colloquial, arbitrary, or ERP-specific abbreviations (e.g., 'KG', 'LITRE', 'PCS.', 'NO').
   - Fallback code OTH (Others) for unlisted units.
2. All Statutory Mappings:
   - "KG" / "Kg" / "KGS." -> "KGS" (GST portal requires 3-letter standard KGS)
   - "NO" / "PIECES" -> "NOS" / "PCS" (Map to either NOS or PCS)
   - "LTR" / "LITER" / "LITRE" -> "OTH" (LTR is not part of standard UQC list; convert to KLR/MLT or pass OTH)
   - "METER" / "MT" -> "MTR" (Standard unit of linear measurement is MTR)
   - "TON" / "METRIC TON" -> "TON" / "MTS" (Use MTS or TON)
   - "BNDL" / "BUNDLE" -> "BDL" (The valid 3-letter code for bundles is BDL)
   - "PACKET" / "PKT" -> "PAC" (The valid code for packs/packets is PAC)
   - Custom / non-listed units (e.g., "Ream", "Bucket") -> "OTH" (Use OTH for unlisted units)
3. Pre-API & Rules Engine Validation:
   - LineItem Pydantic field validation raising NICValidationError(2177).
   - GSTValidator & RulesEngine detecting Error 2177 with detailed statutory diagnostic.
4. Data Lakehouse Integration (src/ingestion/storage.py):
   - flatten_invoice_payload (dict and Pydantic) normalizes unit column to valid 3-letter master UQC.
   - Intercepts Rule 2177 violations with telemetry: FLAGGED_AND_RECTIFIED, HIGH risk, prob >= 0.95, and audit reason.
   - Parquet round-trip persistence (write_parquet, read_parquet, append_to_parquet) verifying schema and data.
5. Self-Healing Pipelines:
   - InvoicePayload.auto_correct_and_build logs UQC_MASTER_AUTO_ALIGNMENT.
   - PayloadBuilder.auto_correct_and_build logs UQC_MASTER_AUTO_ALIGNMENT and rectifies line item units.
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
    LineItem,
    IRN_ERRORS,
    ALLOWED_UQC,
    OFFICIAL_UQC_MASTER,
    COMMON_UQC_MAPPING,
    NICValidationError,
    classify_rule_2177_diagnostic,
    normalize_uqc_statutory,
)
from Template_Converters.error_mappings import (
    NIC_ERROR_CODES,
    ALLOWED_UQC as TC_ALLOWED_UQC,
    OFFICIAL_UQC_MASTER as TC_OFFICIAL_UQC_MASTER,
    classify_rule_2177_diagnostic as tc_classify_2177,
    normalize_uqc_statutory as tc_normalize_2177,
)
from Template_Converters.validator import GSTValidator
from Template_Converters.payload_builder import PayloadBuilder
from src.rules.rules_engine import RulesEngine
from src.ingestion.storage import (
    flatten_invoice_payload,
    write_parquet,
    read_parquet,
    append_to_parquet,
    FLATTENED_INVOICE_SCHEMA,
)


EXPECTED_44_UQC = [
    "BAG", "BAL", "BDL", "BKL", "BOU", "BOX", "BTL", "BUN", "CAN", "CBM",
    "CCM", "CMS", "CTN", "DOZ", "DRM", "GGR", "GMS", "GRS", "GYD", "KGS",
    "KLR", "KME", "MLT", "MTR", "MTS", "NOS", "PAC", "PCS", "PRS", "QTL",
    "ROL", "SET", "SQF", "SQM", "SQY", "TBS", "TGM", "THD", "TON", "TUB",
    "UGS", "UNT", "YDS", "OTH"
]


# ============================================================================
# 1. CATALOG & OFFICIAL MASTER VERIFICATION
# ============================================================================

def test_official_uqc_catalog_completeness():
    """Verify all 44 official UQCs are present in schemas and error_mappings."""
    assert len(EXPECTED_44_UQC) == 44
    assert len(ALLOWED_UQC) == 44
    assert len(TC_ALLOWED_UQC) == 44

    for code in EXPECTED_44_UQC:
        assert code in ALLOWED_UQC, f"Code {code} missing from schemas.ALLOWED_UQC"
        assert code in TC_ALLOWED_UQC, f"Code {code} missing from error_mappings.ALLOWED_UQC"
        assert code in OFFICIAL_UQC_MASTER, f"Code {code} missing from schemas.OFFICIAL_UQC_MASTER"
        assert code in TC_OFFICIAL_UQC_MASTER, f"Code {code} missing from error_mappings.OFFICIAL_UQC_MASTER"


def test_irn_error_2177_metadata():
    """Verify IRN error 2177 official definition, message, reason, and resolution."""
    for catalog in (IRN_ERRORS, NIC_ERROR_CODES):
        assert 2177 in catalog
        entry = catalog[2177]
        assert "master" in entry["message"].lower() or "not as per" in entry["message"].lower()
        assert "uqc" in entry["reason"].lower() or "unit" in entry["reason"].lower()
        assert "oth" in entry["resolution"].lower() or "standard" in entry["resolution"].lower()


@pytest.mark.parametrize("uqc_code", EXPECTED_44_UQC)
def test_all_official_44_uqcs_valid(uqc_code):
    """Verify every single official 3-letter master UQC validates as valid with zero correction needed."""
    diag = classify_rule_2177_diagnostic(uqc_code)
    assert diag["is_valid"] is True
    assert diag["rectified_uqc"] == uqc_code
    assert diag["error_code"] == 2177

    norm, norm_diag = normalize_uqc_statutory(uqc_code)
    assert norm == uqc_code
    assert norm_diag["is_valid"] is True


# ============================================================================
# 2. COLLOQUIAL / ERP ABBREVIATIONS & STATUTORY NORMALIZATION
# ============================================================================

@pytest.mark.parametrize("raw_unit,expected_target,expected_scenario", [
    # 1. Weight KG
    ("KG", "KGS", "STANDARD_WEIGHT_KG"),
    ("Kg", "KGS", "STANDARD_WEIGHT_KG"),
    ("kg", "KGS", "STANDARD_WEIGHT_KG"),
    ("KILOGRAM", "KGS", "STANDARD_WEIGHT_KG"),
    ("kilograms", "KGS", "STANDARD_WEIGHT_KG"),
    ("KG.", "KGS", "STANDARD_WEIGHT_KG"),
    ("KGS.", "KGS", "STANDARD_WEIGHT_KG"),

    # 2. Count NO & PIECES
    ("NO", "NOS", "COLLOQUIAL_COUNT_NO"),
    ("No", "NOS", "COLLOQUIAL_COUNT_NO"),
    ("NO.", "NOS", "COLLOQUIAL_COUNT_NO"),
    ("NUMBER", "NOS", "COLLOQUIAL_COUNT_NO"),
    ("numbers", "NOS", "COLLOQUIAL_COUNT_NO"),
    ("PIECES", "PCS", "COLLOQUIAL_COUNT_PIECES"),
    ("piece", "PCS", "COLLOQUIAL_COUNT_PIECES"),
    ("PC", "PCS", "COLLOQUIAL_COUNT_PIECES"),
    ("PCS.", "PCS", "COLLOQUIAL_COUNT_PIECES"),

    # 3. Non-Standard Volume Litre -> OTH
    ("LTR", "OTH", "NON_STANDARD_VOLUME_LTR"),
    ("ltr", "OTH", "NON_STANDARD_VOLUME_LTR"),
    ("LITER", "OTH", "NON_STANDARD_VOLUME_LTR"),
    ("litre", "OTH", "NON_STANDARD_VOLUME_LTR"),
    ("litres", "OTH", "NON_STANDARD_VOLUME_LTR"),
    ("L", "OTH", "NON_STANDARD_VOLUME_LTR"),

    # 4. Linear Measure Meter -> MTR
    ("METER", "MTR", "LINEAR_MEASURE_METER"),
    ("meter", "MTR", "LINEAR_MEASURE_METER"),
    ("METERS", "MTR", "LINEAR_MEASURE_METER"),
    ("METRE", "MTR", "LINEAR_MEASURE_METER"),
    ("MT", "MTR", "LINEAR_MEASURE_METER"),
    ("MT.", "MTR", "LINEAR_MEASURE_METER"),

    # 5. Weight Tonne / Metric Ton -> TON / MTS
    ("TONNE", "TON", "WEIGHT_TONNES"),
    ("tonne", "TON", "WEIGHT_TONNES"),
    ("METRIC TON", "MTS", "WEIGHT_METRIC_TON"),
    ("metric tons", "MTS", "WEIGHT_METRIC_TON"),

    # 6. Bundles -> BDL
    ("BNDL", "BDL", "PACKAGING_BUNDLE"),
    ("bundle", "BDL", "PACKAGING_BUNDLE"),
    ("BUNDLES", "BDL", "PACKAGING_BUNDLE"),

    # 7. Packs / Packets -> PAC
    ("PACKET", "PAC", "PACKAGING_PACKET"),
    ("packet", "PAC", "PACKAGING_PACKET"),
    ("PKT", "PAC", "PACKAGING_PACKET"),
    ("pkt", "PAC", "PACKAGING_PACKET"),
    ("PACK", "PAC", "PACKAGING_PACKET"),
    ("packs", "PAC", "PACKAGING_PACKET"),

    # 8. Unlisted Custom Units -> OTH
    ("Ream", "OTH", "CUSTOM_NON_LISTED_UNIT"),
    ("ream", "OTH", "CUSTOM_NON_LISTED_UNIT"),
    ("Bucket", "OTH", "CUSTOM_NON_LISTED_UNIT"),
    ("Sack", "OTH", "CUSTOM_NON_LISTED_UNIT"),
    ("Bar", "OTH", "CUSTOM_NON_LISTED_UNIT"),
    ("Cartridge", "OTH", "CUSTOM_NON_LISTED_UNIT"),
    ("XYZ", "OTH", "CUSTOM_NON_LISTED_UNIT"),
])
def test_uqc_statutory_mappings(raw_unit, expected_target, expected_scenario):
    """Verify statutory normalization correctly maps colloquial/ERP units to target master codes."""
    norm, diag = normalize_uqc_statutory(raw_unit)
    assert norm == expected_target
    assert diag["rectified_uqc"] == expected_target
    assert diag["is_valid"] is False
    assert diag["scenario"] == expected_scenario
    assert len(expected_target) == 3
    assert expected_target in EXPECTED_44_UQC


# ============================================================================
# 3. PRE-API & RULES ENGINE VALIDATION
# ============================================================================

def test_line_item_pydantic_validator_rejects_invalid_uqc():
    """Verify LineItem field validator raises NICValidationError(2177) for invalid UQC."""
    with pytest.raises((NICValidationError, Exception)) as exc_info:
        LineItem(
            slno="1",
            prdnm="Industrial Steel Cables",
            is_service="N",
            hsn="73121020",
            qty=100.0,
            unit="KG",  # Invalid, must be KGS
            unitprice=50.0,
            totamt=5000.0,
            assval=5000.0,
            gstrate=18.0,
            cgstval=0.0,
            sgstval=0.0,
            igstval=900.0,
            totitemval=5900.0
        )
    err_str = str(exc_info.value)
    assert "2177" in err_str
    assert "KG" in err_str
    assert "KGS" in err_str


def test_line_item_pydantic_validator_accepts_valid_master_uqc():
    """Verify LineItem accepts valid official master codes."""
    item = LineItem(
        slno="1",
        prdnm="Industrial Steel Cables",
        is_service="N",
        hsn="73121020",
        qty=100.0,
        unit="KGS",  # Valid official code
        unitprice=50.0,
        totamt=5000.0,
        assval=5000.0,
        gstrate=18.0,
        cgstval=0.0,
        sgstval=0.0,
        igstval=900.0,
        totitemval=5900.0
    )
    assert item.unit == "KGS"


def test_gst_validator_detects_error_2177():
    """Verify GSTValidator pre-API validation flags Error 2177 for colloquial units."""
    payload = {
        "self_gstin": "27AABCU9603R1ZX",
        "docdt1": {"docno": "INV-2177-01", "doctype": "INV", "docdt": "26/10/2026"},
        "trandt1": {"trancatg": "B2B", "regrev": "N", "reversecharge": "N", "igstonintra": "N"},
        "supplierdt1": {"supplier_gstin": "27AABCU9603R1ZX", "supplier_state": "27", "supplier_pin": "400001", "supplier_lglnm": "Supplier MH"},
        "buyerdt1": {"buyer_gstin": "27GSPMH0002G1Z2", "buyer_state": "27", "buyer_pos": "27", "buyer_pin": "400002", "buyer_lglnm": "Buyer MH"},
        "valdt1": {"ttlassval": "5000.00", "cgstval": "450.00", "sgstval": "450.00", "igstval": "0.00", "totinvval": "5900.00"},
        "itemdtls": [
            {
                "slno": "1",
                "prdnm": "Mineral Water",
                "hsncd": "22011010",
                "qty": "50.00",
                "uqc": "LTR",  # Rule 2177 violation
                "unitrate": "100.00",
                "grossamt": "5000.00",
                "assamt": "5000.00",
                "cgstrt": "9.00",
                "cgstamt": "450.00",
                "sgstrt": "9.00",
                "sgstamt": "450.00",
                "igstrt": "0.00",
                "igstamt": "0.00",
                "totitemval": "5900.00"
            }
        ]
    }

    errors = GSTValidator.validate_invoice(payload)
    err_2177 = [e for e in errors if e.get("error_code") == 2177]
    assert len(err_2177) >= 1
    assert "LTR" in err_2177[0]["message"]
    assert "OTH" in err_2177[0]["message"]


def test_rules_engine_detects_error_2177():
    """Verify RulesEngine pre-API validation flags Error 2177 for colloquial units."""
    payload = {
        "self_gstin": "27AABCU9603R1ZX",
        "docdt1": {"docno": "INV-2177-02", "doctype": "INV", "docdt": "26/10/2026"},
        "trandt1": {"trancatg": "B2B", "regrev": "N", "reversecharge": "N", "igstonintra": "N"},
        "supplierdt1": {"supplier_gstin": "27AABCU9603R1ZX", "supplier_state": "27", "supplier_pin": "400001", "supplier_lglnm": "Supplier MH"},
        "buyerdt1": {"buyer_gstin": "27GSPMH0002G1Z2", "buyer_state": "27", "buyer_pos": "27", "buyer_pin": "400002", "buyer_lglnm": "Buyer MH"},
        "valdt1": {"ttlassval": "2000.00", "cgstval": "180.00", "sgstval": "180.00", "igstval": "0.00", "totinvval": "2360.00"},
        "itemdtls": [
            {
                "slno": "1",
                "prdnm": "Cotton Fabric",
                "hsncd": "52081100",
                "qty": "20.00",
                "uqc": "METER",  # Rule 2177 violation
                "unitrate": "100.00",
                "grossamt": "2000.00",
                "assamt": "2000.00",
                "cgstrt": "9.00",
                "cgstamt": "180.00",
                "sgstrt": "9.00",
                "sgstamt": "180.00",
                "igstrt": "0.00",
                "igstamt": "0.00",
                "totitemval": "2360.00"
            }
        ]
    }

    errors = RulesEngine.validate_invoice(payload)
    err_2177 = [e for e in errors if e.get("error_code") == 2177]
    assert len(err_2177) >= 1
    assert "METER" in err_2177[0]["message"]
    assert "MTR" in err_2177[0]["message"]


# ============================================================================
# 4. SELF-HEALING & AUTO-CORRECTION PIPELINES
# ============================================================================

def test_invoice_payload_auto_correct_and_build_uqc():
    """Verify InvoicePayload.auto_correct_and_build normalizes colloquial units and logs audit entry."""
    raw_payload = {
        "docno": "INV-2177-HEAL-01",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "B2B",
        "supplier": {
            "gstin": "27AABCU9603R1ZX",
            "lglnm": "Apex Metals Ltd",
            "state": "27",
            "pin": "400001",
            "loc": "Mumbai"
        },
        "buyer": {
            "gstin": "29GSPKA0001G1Z1",
            "lglnm": "Karnataka Infra Ltd",
            "state": "29",
            "pos": "29",
            "pin": "560001",
            "loc": "Bengaluru"
        },
        "valdtls": {
            "assval": 10000.00,
            "cgstval": 0.00,
            "sgstval": 0.00,
            "igstval": 1800.00,
            "totinvval": 11800.00
        },
        "itemdtls": [
            {
                "slno": "1",
                "prdnm": "Galvanized Steel Wire",
                "hsn": "72171010",
                "qty": 100.0,
                "unit": "KG",  # Colloquial -> KGS
                "unitprice": 100.0,
                "totamt": 10000.0,
                "assval": 10000.0,
                "gstrate": 18.0,
                "igstval": 1800.0,
                "totitemval": 11800.0
            }
        ]
    }

    model, audit_log = InvoicePayload.auto_correct_and_build(raw_payload)
    assert model is not None
    assert model.itemdtls[0].unit == "KGS"

    # Audit log validation
    uqc_audits = [a for a in audit_log if a.get("category") == "UQC_MASTER_AUTO_ALIGNMENT"]
    assert len(uqc_audits) == 1
    assert uqc_audits[0]["original"] == "KG"
    assert uqc_audits[0]["corrected"] == "KGS"


def test_payload_builder_auto_correct_and_build_uqc():
    """Verify PayloadBuilder.auto_correct_and_build normalizes colloquial units and logs audit entry."""
    builder = PayloadBuilder()
    raw_payload = {
        "docdt1": {"docno": "INV-2177-BUILDER", "doctype": "INV", "docdt": "26/10/2026"},
        "trandt1": {"trancatg": "B2B", "regrev": "N", "reversecharge": "N", "igstonintra": "N"},
        "supplierdt1": {"supplier_gstin": "27AABCU9603R1ZX", "supplier_state": "27", "supplier_pin": "400001", "supplier_lglnm": "Apex Metals Ltd"},
        "buyerdt1": {"buyer_gstin": "29GSPKA0001G1Z1", "buyer_state": "29", "buyer_pos": "29", "buyer_pin": "560001", "buyer_lglnm": "Karnataka Infra Ltd"},
        "valdt1": {"ttlassval": "5000.00", "cgstval": "0.00", "sgstval": "0.00", "igstval": "900.00", "totinvval": "5900.00"},
        "itemdtls": [
            {
                "slno": "1",
                "prdnm": "Cotton T-Shirts",
                "hsncd": "61091000",
                "qty": "50.00",
                "uqc": "PIECES",  # Colloquial -> PCS
                "unitrate": "100.00",
                "grossamt": "5000.00",
                "assamt": "5000.00",
                "igstrt": "18.00",
                "igstamt": "900.00",
                "totitemval": "5900.00"
            }
        ]
    }

    clean_inv, audit_log = builder.auto_correct_and_build(raw_payload)
    assert clean_inv is not None
    corrected_item = clean_inv["itemdtls"][0]
    assert corrected_item["uqc"] == "PCS"

    uqc_logs = [l for l in audit_log if l.get("category") == "UQC_MASTER_AUTO_ALIGNMENT"]
    assert len(uqc_logs) == 1
    assert uqc_logs[0]["original"] == "PIECES"
    assert uqc_logs[0]["corrected"] == "PCS"


# ============================================================================
# 5. DATA LAKEHOUSE INTEGRATION (src/ingestion/storage.py)
# ============================================================================

def test_lakehouse_flatten_dict_rule_2177_standardization_and_telemetry():
    """Verify flatten_invoice_payload (dict) normalizes unit and attaches Sentinel ML telemetry."""
    dirty_dict = {
        "docdt1": {"docno": "INV-2177-LAKE-01", "doctype": "INV", "docdt": "26/10/2026"},
        "trandt1": {"trancatg": "B2B", "reversecharge": "N", "igstonintra": "N"},
        "supplierdt1": {"supplier_gstin": "27AABCU9603R1ZX", "supplier_state": "27", "supplier_pin": "400001", "supplier_lglnm": "Supplier MH"},
        "buyerdt1": {"buyer_gstin": "27GSPMH0002G1Z2", "buyer_state": "27", "buyer_pos": "27", "buyer_pin": "400002", "buyer_lglnm": "Buyer MH"},
        "valdt1": {"assval": 4000.0, "cgstval": 360.0, "sgstval": 360.0, "igstval": 0.0, "totinvval": 4720.0},
        "itemdtls": [
            {
                "slno": "1",
                "prdnm": "Industrial Bundles Wire",
                "hsncd": "72171010",
                "qty": 40.0,
                "uqc": "BNDL",  # Colloquial -> BDL
                "unitprice": 100.0,
                "totamt": 4000.0,
                "assval": 4000.0,
                "cgstamt": 360.0,
                "sgstamt": 360.0,
                "igstamt": 0.0,
                "totitemval": 4720.0
            }
        ]
    }

    rows = flatten_invoice_payload(dirty_dict)
    assert len(rows) == 1
    row = rows[0]

    # Lakehouse standardized unit column
    assert row["unit"] == "BDL"

    # Sentinel ML telemetry
    assert row["sentinel_status_badge"] == "FLAGGED_AND_RECTIFIED"
    assert row["sentinel_risk_level"] == "HIGH"
    assert row["sentinel_risk_prob"] >= 0.95
    assert "Rule 2177 Violation" in row["sentinel_audit_reasons"]
    assert "BNDL" in row["sentinel_audit_reasons"]
    assert "BDL" in row["sentinel_audit_reasons"]


def test_lakehouse_flatten_pydantic_rule_2177_standardization_and_telemetry():
    """Verify flatten_invoice_payload (Pydantic model) normalizes unit and attaches Sentinel telemetry."""
    # Build payload using auto_correct_and_build so Pydantic validation passes
    raw_dict = {
        "docno": "INV-2177-LAKE-02",
        "docdt": "2026-10-26",
        "document_type": "INV",
        "trancatg": "B2B",
        "supplier": {
            "gstin": "27AABCU9603R1ZX",
            "lglnm": "Apex Packaging",
            "state": "27",
            "pin": "400001",
            "loc": "Mumbai"
        },
        "buyer": {
            "gstin": "27GSPMH0002G1Z2",
            "lglnm": "Retail Mart",
            "state": "27",
            "pos": "27",
            "pin": "400002",
            "loc": "Pune"
        },
        "valdtls": {
            "assval": 2500.0,
            "cgstval": 225.0,
            "sgstval": 225.0,
            "igstval": 0.0,
            "totinvval": 2950.0
        },
        "itemdtls": [
            {
                "slno": "1",
                "prdnm": "A4 Paper Packets",
                "hsn": "48025610",
                "qty": 25.0,
                "unit": "PACKET",  # Colloquial -> PAC
                "unitprice": 100.0,
                "totamt": 2500.0,
                "assval": 2500.0,
                "gstrate": 18.0,
                "cgstval": 225.0,
                "sgstval": 225.0,
                "igstval": 0.0,
                "totitemval": 2950.0
            }
        ]
    }

    model, audit_log = InvoicePayload.auto_correct_and_build(raw_dict)
    assert model is not None

    rows = flatten_invoice_payload(model)
    assert len(rows) == 1
    row = rows[0]

    assert row["unit"] == "PAC"
    assert row["product_name"] == "A4 Paper Packets"
    assert row["hsn"] == "48025610"


def test_lakehouse_parquet_persistence_roundtrip():
    """Verify write_parquet, read_parquet, and append_to_parquet maintain schema compliance for UQC."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        parquet_file = os.path.join(tmp_dir, "uqc_master_lakehouse.parquet")

        payload_1 = {
            "docdt1": {"docno": "INV-2177-PQ-01", "doctype": "INV", "docdt": "26/10/2026"},
            "trandt1": {"trancatg": "B2B", "reversecharge": "N", "igstonintra": "N"},
            "supplierdt1": {"supplier_gstin": "27AABCU9603R1ZX", "supplier_state": "27", "supplier_pin": "400001", "supplier_lglnm": "Supplier MH"},
            "buyerdt1": {"buyer_gstin": "27GSPMH0002G1Z2", "buyer_state": "27", "buyer_pos": "27", "buyer_pin": "400002", "buyer_lglnm": "Buyer MH"},
            "valdt1": {"assval": 1000.0, "cgstval": 90.0, "sgstval": 90.0, "igstval": 0.0, "totinvval": 1180.0},
            "itemdtls": [
                {
                    "slno": "1",
                    "prdnm": "Wheat Grain",
                    "hsncd": "10011900",
                    "qty": 50.0,
                    "uqc": "KG",  # -> KGS
                    "unitprice": 20.0,
                    "totamt": 1000.0,
                    "assval": 1000.0,
                    "cgstamt": 90.0,
                    "sgstamt": 90.0,
                    "igstamt": 0.0,
                    "totitemval": 1180.0
                }
            ]
        }

        payload_2 = {
            "docdt1": {"docno": "INV-2177-PQ-02", "doctype": "INV", "docdt": "26/10/2026"},
            "trandt1": {"trancatg": "B2B", "reversecharge": "N", "igstonintra": "N"},
            "supplierdt1": {"supplier_gstin": "27AABCU9603R1ZX", "supplier_state": "27", "supplier_pin": "400001", "supplier_lglnm": "Supplier MH"},
            "buyerdt1": {"buyer_gstin": "27GSPMH0002G1Z2", "buyer_state": "27", "buyer_pos": "27", "buyer_pin": "400002", "buyer_lglnm": "Buyer MH"},
            "valdt1": {"assval": 2000.0, "cgstval": 180.0, "sgstval": 180.0, "igstval": 0.0, "totinvval": 2360.0},
            "itemdtls": [
                {
                    "slno": "1",
                    "prdnm": "Custom Plastic Buckets",
                    "hsncd": "39241010",
                    "qty": 10.0,
                    "uqc": "Bucket",  # -> OTH
                    "unitprice": 200.0,
                    "totamt": 2000.0,
                    "assval": 2000.0,
                    "cgstamt": 180.0,
                    "sgstamt": 180.0,
                    "igstamt": 0.0,
                    "totitemval": 2360.0
                }
            ]
        }

        rows_1 = flatten_invoice_payload(payload_1)
        rows_2 = flatten_invoice_payload(payload_2)

        # 1. Write initial Parquet table
        success_write = write_parquet(rows_1, parquet_file, schema=FLATTENED_INVOICE_SCHEMA)
        assert success_write is True

        # 2. Append second invoice
        success_append = append_to_parquet(rows_2, parquet_file, schema=FLATTENED_INVOICE_SCHEMA)
        assert success_append is True

        # 3. Read back & verify
        df = read_parquet(parquet_file)
        assert len(df) == 2
        assert list(df["unit"]) == ["KGS", "OTH"]
        assert list(df["sentinel_status_badge"]) == ["FLAGGED_AND_RECTIFIED", "FLAGGED_AND_RECTIFIED"]
        assert all(df["sentinel_risk_prob"] >= 0.95)
