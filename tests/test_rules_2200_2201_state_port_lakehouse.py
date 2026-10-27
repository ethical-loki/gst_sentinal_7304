"""
Comprehensive Test Suite for NIC / GST e-Invoicing Compliance:
Error Code 2200 (Invalid State Code in Dispatch or Ship Details) and
Error Code 2201 (Invalid Port Code for Export Transactions).

Validates:
1. classify_rule_2200_diagnostic (4 statutory scenarios + clean pass)
2. classify_rule_2201_diagnostic (4 statutory scenarios + clean pass)
3. Pre-API Validator Engine (GSTValidator.validate_invoice)
4. Rules Engine (RulesEngine.validate_invoice)
5. Pydantic Model Ingestion & Auto-Correction (InvoicePayload.auto_correct_and_build)
6. Data Lakehouse Parquet Flattening & Sentinel Telemetry (flatten_invoice_payload)
"""

import os
import tempfile
import pytest
import pyarrow as pa
import pyarrow.parquet as pq

from src.ingestion.schemas import (
    classify_rule_2200_diagnostic,
    classify_rule_2201_diagnostic,
    STATE_ALPHA_TO_CODE,
    ICEGATE_PORT_MASTER,
    CITY_TO_PORT_MAP,
    Counterparty,
    ExportDetails,
    LineItem,
    TaxBreakup,
    InvoicePayload,
)
from Template_Converters.validator import GSTValidator
from src.rules.rules_engine import RulesEngine
from src.ingestion.storage import flatten_invoice_payload, FLATTENED_INVOICE_SCHEMA


# ==============================================================================
# 1. RULE 2200 DIAGNOSTIC UNIT TESTS
# ==============================================================================

class TestRule2200Diagnostic:
    """Tests all 4 statutory scenarios for Error 2200."""

    def test_scenario_1_leading_zero_omitted(self):
        """Scenario 1: DispDtls.Stcd = '7' -> Rectified to '07' (Delhi)."""
        diag = classify_rule_2200_diagnostic(stcd="7", section="DispDtls")
        assert not diag["is_valid"]
        assert diag["error_code"] == 2200
        assert diag["scenario"] == "LEADING_ZERO_OMITTED"
        assert diag["rectified_stcd"] == "07"
        assert "Delhi" in diag["reason"] or "state code is '07'" in diag["reason"]

    def test_scenario_2_alpha_code_used(self):
        """Scenario 2: ShipDtls.Stcd = 'MH' or 'KA' -> Rectified to '27' or '29'."""
        diag_mh = classify_rule_2200_diagnostic(stcd="MH", section="ShipDtls")
        assert not diag_mh["is_valid"]
        assert diag_mh["error_code"] == 2200
        assert diag_mh["scenario"] == "ALPHA_CODE_USED"
        assert diag_mh["rectified_stcd"] == "27"
        assert "Maharashtra" in diag_mh["reason"]

        diag_ka = classify_rule_2200_diagnostic(stcd="KA", section="ShipDtls")
        assert not diag_ka["is_valid"]
        assert diag_ka["rectified_stcd"] == "29"

    def test_scenario_3_state_code_disagrees_with_gstin(self):
        """Scenario 3: ShipDtls.Gstin = '29BBBBB0000B1Z2', Stcd = '27' -> Rectified to '29'."""
        diag = classify_rule_2200_diagnostic(
            stcd="27",
            gstin="29BBBBB0000B1Z2",
            section="ShipDtls"
        )
        assert not diag["is_valid"]
        assert diag["error_code"] == 2200
        assert diag["scenario"] == "STATE_CODE_DISAGREES_WITH_GSTIN"
        assert diag["rectified_stcd"] == "29"
        assert "must match the first two digits" in diag["reason"]

    def test_scenario_4_invalid_or_non_existent_code(self):
        """Scenario 4: DispDtls.Stcd = '00' or '99' -> Invalid for physical goods movement."""
        diag_00 = classify_rule_2200_diagnostic(stcd="00", pin="560001", section="DispDtls")
        assert not diag_00["is_valid"]
        assert diag_00["error_code"] == 2200
        assert diag_00["scenario"] == "INVALID_OR_NON_EXISTENT_CODE"
        assert diag_00["rectified_stcd"] == "29"  # Inferred from Karnataka PIN 560001
        assert "'00' is invalid" in diag_00["reason"]

        diag_99 = classify_rule_2200_diagnostic(stcd="99", gstin="27AAAAA0000A1Z5", section="DispDtls")
        assert not diag_99["is_valid"]
        assert diag_99["rectified_stcd"] == "27"  # Inferred from GSTIN
        assert "'99' is reserved" in diag_99["reason"]

    def test_valid_state_code(self):
        """Clean pass: Valid 2-digit state code."""
        diag = classify_rule_2200_diagnostic(stcd="27", gstin="27AAAAA0000A1Z5", section="DispDtls")
        assert diag["is_valid"]
        assert diag["error_code"] is None
        assert diag["scenario"] == "VALID"
        assert diag["rectified_stcd"] == "27"


# ==============================================================================
# 2. RULE 2201 DIAGNOSTIC UNIT TESTS
# ==============================================================================

class TestRule2201Diagnostic:
    """Tests all 4 statutory scenarios for Error 2201."""

    def test_scenario_1_informal_or_city_name_used(self):
        """Scenario 1: ExpDtls.Port = 'MUMBAI' -> Rectified to 'INBOM1'."""
        diag = classify_rule_2201_diagnostic(port="MUMBAI", trancatg="EXPWP", transmode="1")
        assert not diag["is_valid"]
        assert diag["error_code"] == 2201
        assert diag["scenario"] == "INFORMAL_OR_CITY_NAME_USED"
        assert diag["rectified_port"] == "INBOM1"
        assert "Port codes must be standard 6-character" in diag["reason"]

    def test_scenario_2_air_sea_port_code_confusion(self):
        """Scenario 2: Nhava Sheva (INNSA1 sea port) sent with air cargo (transmode='4')."""
        diag = classify_rule_2201_diagnostic(port="INNSA1", trancatg="EXPWP", transmode="4")
        assert not diag["is_valid"]
        assert diag["error_code"] == 2201
        assert diag["scenario"] == "AIR_SEA_PORT_CODE_CONFUSION"
        assert diag["rectified_port"] == "INBOM4"  # Air Cargo Complex, Mumbai
        assert "Air shipment passed with seaport code" in diag["reason"]

    def test_scenario_3_wrong_format_spacing_special_chars(self):
        """Scenario 3: ExpDtls.Port = 'IN-NSA-1' or 'innsa1' -> Rectified to 'INNSA1'."""
        diag_hyphen = classify_rule_2201_diagnostic(port="IN-NSA-1", trancatg="EXPWP")
        assert not diag_hyphen["is_valid"]
        assert diag_hyphen["error_code"] == 2201
        assert diag_hyphen["scenario"] == "WRONG_FORMAT_SPACING_SPECIAL_CHARS"
        assert diag_hyphen["rectified_port"] == "INNSA1"

        diag_lower = classify_rule_2201_diagnostic(port="innsa1", trancatg="EXPWP")
        assert not diag_lower["is_valid"]
        assert diag_lower["rectified_port"] == "INNSA1"

    def test_scenario_4_port_code_provided_for_domestic_supply(self):
        """Scenario 4: Domestic B2B transaction containing dummy export details with port code."""
        diag = classify_rule_2201_diagnostic(port="INBOM1", trancatg="B2B", is_export=False)
        assert not diag["is_valid"]
        assert diag["error_code"] == 2201
        assert diag["scenario"] == "PORT_CODE_PROVIDED_FOR_DOMESTIC_SUPPLY"
        assert diag["omit_expdtls"] is True
        assert "ExpDtls (including Port) is only applicable for Export" in diag["reason"]

    def test_valid_export_port(self):
        """Clean pass: Valid 6-character ICEGATE port code for ocean cargo."""
        diag = classify_rule_2201_diagnostic(port="INBOM1", trancatg="EXPWP", transmode="1", is_export=True)
        assert diag["is_valid"]
        assert diag["error_code"] is None
        assert diag["scenario"] == "VALID"
        assert diag["rectified_port"] == "INBOM1"


# ==============================================================================
# 3. PRE-API VALIDATOR & RULES ENGINE TESTS
# ==============================================================================

class TestValidatorAndRulesEngine:
    """Tests GSTValidator and RulesEngine pre-API validation for Rules 2200 & 2201."""

    def test_validator_rule_2200_dispatch_and_ship_state(self):
        invoice = {
            "self_gstin": "27AAAAA0000A1Z5",
            "docdt1": {
                "document_type": "INV",
                "docno": "INV-2200-01",
                "docdt": "26/10/2026"
            },
            "trandt1": {"trancatg": "B2B", "reversecharge": "N"},
            "supplierdt1": {
                "supplier_gstin": "27AAAAA0000A1Z5",
                "supplier_lglnm": "Acme Supplier Corp",
                "supplier_bnm": "Acme Tower",
                "supplier_loc": "Mumbai",
                "supplier_pin": "400001",
                "supplier_state": "27"
            },
            "buyerdt1": {
                "buyer_gstin": "29BBBBB0000B1Z2",
                "buyer_lglnm": "Beta Buyer Ltd",
                "buyer_bnm": "Beta Plaza",
                "buyer_loc": "Bengaluru",
                "buyer_pin": "560001",
                "buyer_state": "29",
                "pos": "29"
            },
            "dispdt1": {
                "disp_gstin": "27AAAAA0000A1Z5",
                "disp_trdnm": "Acme Dispatch",
                "disp_bnm": "Warehouse 1",
                "disp_loc": "Delhi",
                "disp_pin": "110001",
                "disp_state": "7"  # Failing: Leading zero omitted
            },
            "shipdtl": {
                "ship_gstin": "29BBBBB0000B1Z2",
                "ship_lglnm": "Beta Shipping",
                "ship_bnm": "Plant 2",
                "ship_loc": "Bengaluru",
                "ship_pin": "560001",
                "ship_state": "MH"  # Failing: Alpha code used
            },
            "itemdtls": [{
                "slno": "1",
                "hsncd": "84713010",
                "qty": 1.0,
                "unitrate": 1000.0,
                "grossamt": 1000.0,
                "assamt": 1000.0,
                "igstrt": 18.0,
                "igstamt": 180.0,
                "totitemval": 1180.0
            }],
            "valdt1": {
                "ttlassval": 1000.0,
                "igstval": 180.0,
                "totinvval": 1180.0
            }
        }

        # Pre-API validator
        errors = GSTValidator.validate_invoice(invoice)
        err_codes = [e["error_code"] if isinstance(e, dict) else getattr(e, "code", e) for e in errors]
        assert 2200 in err_codes

        # Rules Engine
        engine_errors = RulesEngine.validate_invoice(invoice)
        engine_err_codes = [e["error_code"] if isinstance(e, dict) else getattr(e, "code", e) for e in engine_errors]
        assert 2200 in engine_err_codes

    def test_validator_rule_2201_export_port(self):
        invoice = {
            "self_gstin": "27AAAAA0000A1Z5",
            "docdt1": {
                "document_type": "INV",
                "docno": "INV-2201-01",
                "docdt": "26/10/2026"
            },
            "trandt1": {"trancatg": "EXPWP", "reversecharge": "N"},
            "supplierdt1": {
                "supplier_gstin": "27AAAAA0000A1Z5",
                "supplier_lglnm": "Acme Supplier Corp",
                "supplier_bnm": "Acme Tower",
                "supplier_loc": "Mumbai",
                "supplier_pin": "400001",
                "supplier_state": "27"
            },
            "buyerdt1": {
                "buyer_gstin": "URP",
                "buyer_lglnm": "Overseas Client Inc",
                "buyer_bnm": "Overseas Tower",
                "buyer_loc": "Dubai",
                "buyer_pin": "999999",
                "buyer_state": "96",
                "pos": "96"
            },
            "expdt1": {
                "port": "MUMBAI",  # Failing: Informal city name
                "cntcode": "AE",
                "forcur": "AED",
                "expcat": "DIR",
                "wthpay": "Y"
            },
            "itemdtls": [{
                "slno": "1",
                "hsncd": "84713010",
                "qty": 1.0,
                "unitrate": 1000.0,
                "grossamt": 1000.0,
                "assamt": 1000.0,
                "igstrt": 18.0,
                "igstamt": 180.0,
                "totitemval": 1180.0
            }],
            "valdt1": {
                "ttlassval": 1000.0,
                "igstval": 180.0,
                "totinvval": 1180.0
            }
        }

        errors = GSTValidator.validate_invoice(invoice)
        err_codes = [e["error_code"] if isinstance(e, dict) else getattr(e, "code", e) for e in errors]
        assert 2201 in err_codes

        engine_errors = RulesEngine.validate_invoice(invoice)
        engine_err_codes = [e["error_code"] if isinstance(e, dict) else getattr(e, "code", e) for e in engine_errors]
        assert 2201 in engine_err_codes


# ==============================================================================
# 4. PYDANTIC MODEL AUTO-CORRECTION TESTS
# ==============================================================================

class TestModelAutoCorrection:
    """Tests InvoicePayload.auto_correct_and_build for Rules 2200 and 2201."""

    def test_auto_correct_rule_2200_and_2201(self):
        raw_payload = {
            "docno": "INV-AUTOCORR-01",
            "docdt": "2026-10-26",
            "document_type": "INV",
            "trancatg": "EXPWP",
            "supplier": {
                "gstin": "27AAAAA0000A1Z5",
                "lglnm": "Acme Supplier Corp",
                "state": "27",
                "pin": "400001",
                "loc": "Mumbai"
            },
            "buyer": {
                "gstin": "URP",
                "lglnm": "Global Client LLC",
                "state": "96",
                "pos": "96",
                "pin": "999999",
                "loc": "London"
            },
            "dispdt1": {
                "stcd": "7",  # Failing: single-digit Delhi
                "nm": "Delhi Hub",
                "loc": "Delhi",
                "pin": "110001"
            },
            "shipdtl": {
                "gstin": "27AAAAA0000A1Z5",
                "stcd": "MH",  # Failing: alpha MH
                "lglnm": "Mumbai Port Warehouse",
                "loc": "Mumbai",
                "pin": "400001"
            },
            "expdt1": {
                "port": "IN-NSA-1",  # Failing: formatted port with hyphens
                "cntcode": "GB",
                "forcur": "GBP"
            },
            "itemdtls": [{
                "slno": "1",
                "hsn": "84713010",
                "qty": 2.0,
                "unitprice": 500.0,
                "totamt": 1000.0,
                "assval": 1000.0,
                "gstrate": 18.0,
                "igstval": 180.0,
                "totitemval": 1180.0
            }],
            "valdtls": {
                "assval": 1000.0,
                "igstval": 180.0,
                "totinvval": 1180.0
            }
        }

        payload, audit_trail = InvoicePayload.auto_correct_and_build(raw_payload)

        # Rule 2200 State Code Rectifications
        assert payload.dispdt1.state == "07"
        assert payload.shipdtl.state == "27"

        # Rule 2201 Port Code Rectification
        assert payload.expdt1.port == "INNSA1"

        # Audit Trail categories
        audit_categories = [entry["category"] for entry in audit_trail]
        assert "RULE_2200_STATE_CODE_RECONCILIATION" in audit_categories
        assert "RULE_2201_PORT_CODE_RECONCILIATION" in audit_categories

    def test_auto_correct_domestic_supply_dropping_expdtls(self):
        """Domestic B2B invoice with dummy export port drops ExpDtls entirely."""
        raw_payload = {
            "docno": "INV-DOM-01",
            "docdt": "2026-10-26",
            "document_type": "INV",
            "trancatg": "B2B",
            "supplier": {
                "gstin": "27AAAAA0000A1Z5",
                "lglnm": "Acme Supplier Corp",
                "state": "27",
                "pin": "400001",
                "loc": "Mumbai"
            },
            "buyer": {
                "gstin": "29BBBBB0000B1Z2",
                "lglnm": "Beta Buyer Ltd",
                "state": "29",
                "pos": "29",
                "pin": "560001",
                "loc": "Bengaluru"
            },
            "expdt1": {
                "port": "INBOM1",  # Erroneous for domestic B2B
                "cntcode": "IN"
            },
            "itemdtls": [{
                "slno": "1",
                "hsn": "84713010",
                "qty": 1.0,
                "unitprice": 1000.0,
                "totamt": 1000.0,
                "assval": 1000.0,
                "gstrate": 18.0,
                "igstval": 180.0,
                "totitemval": 1180.0
            }],
            "valdtls": {
                "assval": 1000.0,
                "igstval": 180.0,
                "totinvval": 1180.0
            }
        }

        payload, audit_trail = InvoicePayload.auto_correct_and_build(raw_payload)
        assert payload.expdt1 is None

        audit_categories = [entry["category"] for entry in audit_trail]
        assert "RULE_2201_PORT_CODE_RECONCILIATION" in audit_categories


# ==============================================================================
# 5. DATA LAKEHOUSE PARQUET STORAGE & TELEMETRY TESTS
# ==============================================================================

class TestLakehouseParquetStorage:
    """Tests flatten_invoice_payload and Parquet lakehouse roundtrip with pyarrow."""

    def test_lakehouse_dict_flattening_with_telemetry(self):
        payload_dict = {
            "docdt1": {
                "docno": "INV-LAKE-DICT-01",
                "docdt": "26/10/2026",
                "document_type": "INV"
            },
            "trandt1": {"trancatg": "EXPWP", "reversecharge": "N"},
            "supplierdt1": {
                "supplier_gstin": "27AAAAA0000A1Z5",
                "supplier_lglnm": "Acme Supplier Corp",
                "supplier_state": "27",
                "supplier_pin": "400001",
                "supplier_loc": "Mumbai"
            },
            "buyerdt1": {
                "buyer_gstin": "URP",
                "buyer_lglnm": "Foreign Buyer",
                "buyer_state": "96",
                "pos": "96",
                "buyer_pin": "999999",
                "buyer_loc": "London"
            },
            "dispdt1": {
                "stcd": "7",  # Delhi leading zero omitted
                "dispatch_name": "Delhi Logistics Center",
                "pin": "110001"
            },
            "shipdtl": {
                "gstin": "27AAAAA0000A1Z5",
                "stcd": "MH",  # Maharashtra alpha code
                "ship_name": "Nhava Sheva Yard",
                "pin": "400001"
            },
            "expdt1": {
                "port": "MUMBAI",  # City name used instead of port code
                "cntcode": "GB",
                "shipbno": "SB-1234567",
                "shipbdt": "26/10/2026"
            },
            "itemdtls": [{
                "slno": "1",
                "hsncd": "84713010",
                "prdnm": "Industrial Router",
                "qty": 5.0,
                "unitrate": 2000.0,
                "grossamt": 10000.0,
                "assamt": 10000.0,
                "igstrt": 18.0,
                "igstamt": 1800.0,
                "totitemval": 11800.0
            }],
            "valdt1": {
                "ttlassval": 10000.0,
                "igstval": 1800.0,
                "totinvval": 11800.0
            }
        }

        rows = flatten_invoice_payload(payload_dict)
        assert len(rows) == 1
        r = rows[0]

        # Sentinel Telemetry
        assert r["sentinel_status_badge"] == "FLAGGED_AND_RECTIFIED"
        assert r["sentinel_risk_level"] == "HIGH"
        assert r["sentinel_risk_prob"] >= 0.95
        assert "Rule 2200 Violation" in r["sentinel_audit_reasons"]
        assert "Rule 2201 Violation" in r["sentinel_audit_reasons"]

        # Rectified fields in Lakehouse row
        assert r["dispatch_state"] == "07"
        assert r["ship_state"] == "27"
        assert r["export_port"] == "INBOM1"

        # Verify Parquet table serialization conforms strictly to FLATTENED_INVOICE_SCHEMA
        table = pa.Table.from_pylist(rows, schema=FLATTENED_INVOICE_SCHEMA)
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            pq.write_table(table, tmp_path)
            read_back = pq.read_table(tmp_path)
            assert read_back.num_rows == 1
            assert read_back.column("dispatch_state")[0].as_py() == "07"
            assert read_back.column("ship_state")[0].as_py() == "27"
            assert read_back.column("export_port")[0].as_py() == "INBOM1"
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_lakehouse_model_flattening_with_telemetry(self):
        # Direct unrectified model construction to test model branch telemetry & auto-rectification
        disp = Counterparty.model_construct(
            state="00",  # Invalid state code 00
            nm="Warehouse 00",
            trdnm="Warehouse 00",
            lglnm="Warehouse 00",
            pin="400001",
            loc="Mumbai",
            gstin="URP"
        )
        ship = Counterparty.model_construct(
            gstin="27AAAAA0000A1Z5",
            state="99",  # Invalid physical state code 99
            lglnm="Shipyard 99",
            trdnm="Shipyard 99",
            nm="Shipyard 99",
            pin="400001",
            loc="Mumbai"
        )
        exp = ExportDetails.model_construct(
            port="innsa1",  # Lowercase port
            cntcode="SG",
            forcur="SGD"
        )
        buyer = Counterparty.model_construct(
            gstin="URP",
            lglnm="Foreign Buyer",
            trdnm="Foreign Buyer",
            state="96",
            pos="96",
            pin="999999",
            loc="Singapore"
        )
        supplier = Counterparty.model_construct(
            gstin="27AAAAA0000A1Z5",
            lglnm="Acme Supplier Corp",
            trdnm="Acme Supplier Corp",
            state="27",
            pin="400001",
            loc="Mumbai"
        )
        item = LineItem.model_construct(
            slno="1",
            hsn="84713010",
            prdnm="Fiber Cable",
            is_service="N",
            qty=10.0,
            unit="NOS",
            unitprice=100.0,
            totamt=1000.0,
            assval=1000.0,
            gstrate=18.0,
            igstval=180.0,
            cgstval=0.0,
            sgstval=0.0,
            cesrate=0.0,
            cesval=0.0,
            statecesrate=0.0,
            statecesval=0.0,
            othchrg=0.0,
            totitemval=1180.0
        )
        val = TaxBreakup.model_construct(
            assval=1000.0,
            cgstval=0.0,
            sgstval=0.0,
            igstval=180.0,
            cesval=0.0,
            totinvval=1180.0
        )
        payload = InvoicePayload.model_construct(
            self_gstin="27AAAAA0000A1Z5",
            docno="INV-LK-MDL-01",
            docdt="2026-10-26",
            document_type="INV",
            trancatg="EXPWP",
            supplier=supplier,
            buyer=buyer,
            dispdt1=disp,
            shipdtl=ship,
            expdt1=exp,
            itemdtls=[item],
            valdtls=val
        )

        rows = flatten_invoice_payload(payload)
        assert len(rows) == 1
        r = rows[0]

        assert r["sentinel_status_badge"] == "FLAGGED_AND_RECTIFIED"
        assert r["sentinel_risk_level"] == "HIGH"
        assert r["sentinel_risk_prob"] >= 0.95
        assert "Rule 2200 Violation" in r["sentinel_audit_reasons"]
        assert "Rule 2201 Violation" in r["sentinel_audit_reasons"]

        # Rectified fields
        assert r["dispatch_state"] == "27"  # Inferred from supplier/pin
        assert r["ship_state"] == "27"      # Inferred from GSTIN
        assert r["export_port"] == "INNSA1"

    def test_clean_pass_invoice_lakehouse(self):
        """Compliant invoice has no Rule 2200/2201 flags."""
        clean_dict = {
            "docdt1": {
                "docno": "INV-CLEAN-01",
                "docdt": "26/10/2026",
                "document_type": "INV"
            },
            "trandt1": {"trancatg": "EXPWP", "reversecharge": "N"},
            "supplierdt1": {
                "supplier_gstin": "27AAAAA0000A1Z5",
                "supplier_lglnm": "Acme Supplier Corp",
                "supplier_state": "27",
                "supplier_pin": "400001",
                "supplier_loc": "Mumbai"
            },
            "buyerdt1": {
                "buyer_gstin": "URP",
                "buyer_lglnm": "Overseas Partner",
                "buyer_state": "96",
                "pos": "96",
                "buyer_pin": "999999",
                "buyer_loc": "Tokyo"
            },
            "dispdt1": {
                "stcd": "27",
                "nm": "Mumbai Dispatch",
                "pin": "400001"
            },
            "shipdtl": {
                "gstin": "27AAAAA0000A1Z5",
                "stcd": "27",
                "ship_name": "Nhava Sheva Terminal",
                "pin": "400001"
            },
            "expdt1": {
                "port": "INBOM1",
                "cntcode": "JP"
            },
            "itemdtls": [{
                "slno": "1",
                "hsncd": "84713010",
                "prdnm": "Storage Array",
                "qty": 1.0,
                "unitrate": 5000.0,
                "grossamt": 5000.0,
                "assamt": 5000.0,
                "igstrt": 18.0,
                "igstamt": 900.0,
                "totitemval": 5900.0
            }],
            "valdt1": {
                "ttlassval": 5000.0,
                "igstval": 900.0,
                "totinvval": 5900.0
            }
        }

        rows = flatten_invoice_payload(clean_dict)
        assert len(rows) == 1
        r = rows[0]
        assert "Rule 2200" not in r["sentinel_audit_reasons"]
        assert "Rule 2201" not in r["sentinel_audit_reasons"]
        assert r["dispatch_state"] == "27"
        assert r["ship_state"] == "27"
        assert r["export_port"] == "INBOM1"
