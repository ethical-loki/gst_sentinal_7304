"""
Unit and Integration Tests for Day 8 Checklist:
- Rate Slab Checker & CBIC Tariff Standard Rate Verification
- Section 17(5) Ineligible Input Tax Credit (ITC) Detector (Clauses 17(5)(a) through 17(5)(d))
- Integration with PayloadBuilder, StatutoryRulesEngine, and Converter Service
"""

import pytest
from decimal import Decimal
from src.rules.rate_slab_checker import RateSlabChecker, rate_slab_checker, check, check_rate_slab
from src.rules.section_17_5_detector import Section175Detector, section_17_5_detector, scan
from src.rules.statutory_rules import StatutoryRulesEngine
from Template_Converters.payload_builder import PayloadBuilder


# ============================================================================
# 1. RATE SLAB CHECKER UNIT TESTS
# ============================================================================

def test_rate_mismatch_detection_critical():
    """Test rate mismatch detection (HSN 8703 declared 12%, statutory 28%, expect CRITICAL flag)."""
    res = check(12.0, "8703")
    assert res is not None
    assert res["flag"] == "RATE_SLAB_MISMATCH"
    assert res["hsn"] == "8703"
    assert res["declared_rate"] == 12.0
    assert res["statutory_rate"] == 28.0
    assert res["difference"] == 16.0
    assert res["severity"] == "CRITICAL"
    assert "Declared GST rate 12% does not match statutory rate 28% for HSN 8703" in res["message"]
    assert "Motor cars & passenger vehicles" in res["message"]


def test_rate_match_no_flag():
    """Test rate match (declared rate 28% for HSN 8703, expect no flag)."""
    res = check(28.0, "8703")
    assert res is not None
    assert res["flag"] is None
    assert res["declared_rate"] == 28.0
    assert res["statutory_rate"] == 28.0
    assert res["difference"] == 0.0
    assert res["severity"] == "LOW"
    assert "matches statutory rate" in res["message"]


def test_rate_match_within_tolerance():
    """Test rate match within 0.5% tolerance (e.g. 28.3% declared vs 28.0%)."""
    res = check(28.3, "8703")
    assert res["flag"] is None
    assert res["difference"] == 0.3


def test_rate_slab_edge_cases():
    """Test edge cases: blank rate, zero rate, missing HSN, non-existent HSN."""
    # 1. Blank rate (None and empty string)
    res_none = check(None, "8703")
    assert res_none["flag"] is None
    assert res_none["declared_rate"] is None
    assert res_none["statutory_rate"] == 28.0

    res_empty = check("", "8703")
    assert res_empty["flag"] is None
    assert res_empty["declared_rate"] is None

    # 2. Missing HSN (None and empty string)
    res_no_hsn = check(18.0, None)
    assert res_no_hsn["flag"] is None
    assert res_no_hsn["hsn"] == ""
    assert res_no_hsn["statutory_rate"] is None

    res_empty_hsn = check(18.0, "")
    assert res_empty_hsn["flag"] is None
    assert res_empty_hsn["hsn"] == ""

    # 3. Zero rate when statutory is 28% -> Mismatch
    res_zero = check(0.0, "8703")
    assert res_zero["flag"] == "RATE_SLAB_MISMATCH"
    assert res_zero["difference"] == 28.0
    assert res_zero["severity"] == "CRITICAL"

    # 4. Zero rate when statutory is 0% (e.g. wheat HSN 1001) -> Match
    res_zero_exempt = check(0.0, "1001")
    assert res_zero_exempt["flag"] is None
    assert res_zero_exempt["difference"] == 0.0

    # 5. Non-existent HSN
    res_unknown = check(18.0, "99999999")
    assert res_unknown["flag"] is None
    assert res_unknown["statutory_rate"] is None


# ============================================================================
# 2. SECTION 17(5) DETECTOR UNIT TESTS
# ============================================================================

def test_section_17_5_checklist_example():
    """Test the exact Section 17(5) output flag shape from the specification."""
    res = scan("Outdoor Catering Service for event")
    assert res is not None
    assert res["flag"] == "ITC_BLOCKED_SECTION_17_5"
    assert res["sub_clause"] == "17(5)(b)(i)"
    assert res["full_tag"] == "ITC Blocked: CGST Act Section 17(5)(b)(i)"
    assert res["matched_term"] == "outdoor catering"
    assert res["product_text"] == "Outdoor Catering Service for event"
    assert res["severity"] == "HIGH"


@pytest.mark.parametrize(
    "sub_clause,sample_text,expected_term",
    [
        ("17(5)(a)", "Supply of passenger vehicle for branch", "passenger vehicle"),
        ("17(5)(a)", "Purchase of brand new motor car for executives", "motor car"),
        ("17(5)(a)", "Operating lease for motor cab", "motor cab"),
        ("17(5)(a)", "Mining site dumper vehicle", "dumper"),
        ("17(5)(a)", "Factory internal works truck", "works truck"),
        ("17(5)(b)(i)", "Expenses on food and beverage at client meeting", "food and beverage"),
        ("17(5)(b)(i)", "Outdoor catering charges for conference", "outdoor catering"),
        ("17(5)(b)(i)", "Professional catering services vendor", "catering services"),
        ("17(5)(b)(i)", "Cafeteria food service bill", "food service"),
        ("17(5)(b)(ii)", "Annual golf club membership fee", "club membership"),
        ("17(5)(b)(ii)", "Executive health club annual package", "health club"),
        ("17(5)(b)(ii)", "Employee fitness centre membership", "fitness centre"),
        ("17(5)(b)(iii)", "Official rent a cab taxi bill", "rent a cab"),
        ("17(5)(b)(iii)", "Monthly rent-a-cab service", "rent-a-cab"),
        ("17(5)(b)(iv)", "Corporate term life insurance policy", "life insurance"),
        ("17(5)(b)(iv)", "Employee health insurance medical coverage", "health insurance"),
        ("17(5)(b)(v)", "Employee travel benefit allowance", "travel benefit"),
        ("17(5)(b)(v)", "Annual executive vacation package", "vacation package"),
        ("17(5)(b)(v)", "Staff leave travel concession reimbursement", "leave travel concession"),
        ("17(5)(b)(v)", "Claim for LTC allowance reimbursement", "ltc"),
        ("17(5)(c)", "Civil works contract for building expansion", "works contract"),
        ("17(5)(c)", "Purchase of immovable property rights", "immovable property"),
        ("17(5)(c)", "Construction of commercial warehouse facility", "construction"),
        ("17(5)(d)", "Household supplies for personal consumption", "personal consumption"),
        ("17(5)(d)", "Consumables purchased for non-business use", "non-business use"),
        ("17(5)(d)", "Goods used for personal use", "personal use"),
    ],
)
def test_all_section_17_5_sub_clauses(sub_clause, sample_text, expected_term):
    """Test all Section 17(5) sub-clauses with regex patterns."""
    res = scan(sample_text)
    assert res is not None, f"Expected match for '{sample_text}'"
    assert res["sub_clause"] == sub_clause
    assert res["flag"] == "ITC_BLOCKED_SECTION_17_5"
    assert res["severity"] == "HIGH"
    assert expected_term.lower() in res["matched_term"].lower()


def test_section_17_5_hsn_fallback():
    """Test Section 17(5)(a) triggering via HSN 8703 even if description text is generic."""
    res = scan("Standard Fleet Equipment Unit", hsn="87032110")
    assert res is not None
    assert res["sub_clause"] == "17(5)(a)"
    assert res["flag"] == "ITC_BLOCKED_SECTION_17_5"
    assert "8703" in res["matched_term"]


def test_section_17_5_clean_goods():
    """Test non-blocked goods and services return None."""
    assert scan("Intel Core i7 13700K Desktop Processor", hsn="84715000") is None
    assert scan("Cotton Textile Yarn 60s Count", hsn="52051110") is None
    assert scan("Consulting & IT implementation services", hsn="998311") is None


# ============================================================================
# 3. PAYLOAD BUILDER INTEGRATION TESTS
# ============================================================================

def test_payload_builder_rate_slab_mismatch_and_override():
    """
    Test that PayloadBuilder catches declared rate 12% on HSN 8703,
    records RATE_SLAB_MISMATCH in audit_log, and overrides gst_rate to statutory 28%.
    """
    dirty_payload = {
        "invoice_number": "INV-DAY08-01",
        "doc_date": "2026-03-15",
        "supplier_gstin": "27AABCS1429B1Z0",  # Maharashtra
        "buyer_gstin": "27AABCT2345B1Z1",  # Maharashtra Buyer
        "pos": "27",  # Intra-state POS
        "itemdtls": [
            {
                "prdnm": "Sedan Passenger Motor Car",
                "prddesc": "Brand new 1500cc passenger car",
                "hsncd": "8703",
                "qty": "1.000",
                "uqc": "NOS",
                "unitrate": "100000.00",
                "grossamt": "100000.00",
                "assamt": "100000.00",
                "gstrate": "12.00",  # Wrong rate! Statutory is 28%
            }
        ],
    }

    builder = PayloadBuilder()
    clean_payload, audit_log = builder.build_payload(dirty_payload)

    # 1. Audit log must contain RATE_SLAB_MISMATCH
    rate_entries = [entry for entry in audit_log if entry["category"] == "RATE_SLAB_MISMATCH"]
    assert len(rate_entries) > 0, "Expected RATE_SLAB_MISMATCH audit log entry"
    assert rate_entries[0]["original"] == "12.0"
    assert rate_entries[0]["corrected"] == "28.0"

    # 2. Audit log must contain ITC_BLOCKED_SECTION_17_5 (detected from text 'passenger car' or HSN '8703')
    itc_entries = [entry for entry in audit_log if entry["category"] == "ITC_BLOCKED_SECTION_17_5"]
    assert len(itc_entries) > 0, "Expected ITC_BLOCKED_SECTION_17_5 audit log entry"
    assert "17(5)(a)" in itc_entries[0]["corrected"]

    # 3. The silent wrong rate bug must be fixed: gstrate should be 28.00
    cleaned_item = clean_payload["itemdtls"][0]
    assert Decimal(cleaned_item["gstrate"]) == Decimal("28.00")

    # Intra-state: CGST = SGST = 14%
    assert Decimal(cleaned_item["cgstrt"]) == Decimal("14.00")
    assert Decimal(cleaned_item["sgstrt"]) == Decimal("14.00")
    assert Decimal(cleaned_item["cgstamt"]) == Decimal("14000.00")
    assert Decimal(cleaned_item["sgstamt"]) == Decimal("14000.00")


def test_payload_builder_outdoor_catering_itc_blocked():
    """Test Section 17(5)(b)(i) detection for outdoor catering in PayloadBuilder."""
    dirty_payload = {
        "invoice_number": "INV-DAY08-02",
        "doc_date": "2026-03-15",
        "supplier_gstin": "29AABCS1429B1Z0",
        "customer_gstin": "29AABCT2345B1Z1",
        "itemdtls": [
            {
                "prdnm": "Corporate Event Dinner",
                "prddesc": "Outdoor Catering Service for annual general meeting",
                "hsncd": "996331",
                "qty": "1.000",
                "uqc": "NOS",
                "unitrate": "50000.00",
                "grossamt": "50000.00",
                "assamt": "50000.00",
                "gstrate": "18.00",
            }
        ],
    }

    builder = PayloadBuilder()
    _, audit_log = builder.build_payload(dirty_payload)

    itc_entries = [entry for entry in audit_log if entry["category"] == "ITC_BLOCKED_SECTION_17_5"]
    assert len(itc_entries) > 0
    assert "17(5)(b)(i)" in itc_entries[0]["corrected"]
    assert "outdoor catering" in itc_entries[0]["description"].lower()


# ============================================================================
# 4. STATUTORY RULES ENGINE EVALUATION TESTS
# ============================================================================

def test_statutory_rules_engine_rule_08():
    """Test that StatutoryRulesEngine.evaluate() triggers RULE_08_RATE_SLAB_MISMATCH and RULE_08_ITC_BLOCKED_17_5."""
    engine = StatutoryRulesEngine()

    bad_sample = {
        "invoice_id": "INV-001",
        "line_item_id": "1",
        "supplier_gstin": "27AABCS1429B1Z0",
        "recipient_gstin": "27AABCT2345B1Z1",
        "supplier_state": "27",
        "declared_pos": "27",
        "declared_hsn": "8703",
        "product_name": "Executive Motor Car",
        "product_description": "Purchase of passenger vehicle",
        "quantity": 1,
        "item_taxable_value": 100000.0,
        "declared_effective_rate": 12.0,  # Statutory is 28.0
        "cgst_amount": 6000.0,
        "sgst_amount": 6000.0,
        "igst_amount": 0.0,
    }

    violations = engine.evaluate(bad_sample)
    assert "RULE_08_RATE_SLAB_MISMATCH" in violations
    assert "RULE_08_ITC_BLOCKED_17_5" in violations
