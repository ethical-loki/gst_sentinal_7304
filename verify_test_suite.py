"""
Comprehensive Verification Test Suite for GST Sentinel
Tests:
1. HSN/SAC Excel master lookup
2. GSTIN statutory & live verification
3. MoRTH Vahan 4.0 plate & live verification
4. Section 8 Header vs Line Items Reconciliation (+/- Rs 2 tolerance)
5. Converter service pipeline & chatbot responses
"""

import sys
from pathlib import Path
from decimal import Decimal

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure project and Template_Converters paths
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
if str(BASE_DIR / "Template_Converters") not in sys.path:
    sys.path.insert(0, str(BASE_DIR / "Template_Converters"))

from backend.converter_service import (
    get_hsn_dataframe,
    lookup_hsn_by_description,
    verify_gstin_government_portal,
    verify_vehicle_government_portal,
    process_converter_pipeline,
    process_converter_chat,
    load_default_sample_dirty
)
from validator import GSTValidator, ValidationError


def test_hsn_master():
    print("\n--- TEST 1: HSN/SAC Master Lookup ---")
    hsn_data = get_hsn_dataframe()
    assert hsn_data is not None, "Failed to load HSN_SAC.xlsx"
    df, hsn_col, desc_col = hsn_data
    print(f"Loaded HSN DataFrame: {len(df)} rows")
    
    matches = lookup_hsn_by_description("cotton yarn", top_k=2)
    print(f"Lookup 'cotton yarn': Found {len(matches)} matches")
    assert len(matches) > 0, "Expected matches for cotton yarn"
    print(f"  Match 1: [{matches[0]['hsn_code']}] {matches[0]['description']}")
    print("PASS: HSN Master Lookup")


def test_gstin_verification():
    print("\n--- TEST 2: GSTIN Verification ---")
    # Valid GSTIN for Tata Consultancy Services
    res_valid = verify_gstin_government_portal("36AAACR4849R1ZM")
    assert res_valid["is_valid"] is True, "Expected GSTIN to be valid"
    assert res_valid["state_name"] == "Telangana", f"Expected Telangana, got {res_valid['state_name']}"
    assert res_valid["pan"] == "AAACR4849R", f"Expected PAN AAACR4849R, got {res_valid['pan']}"
    print(f"Valid GSTIN (36AAACR4849R1ZM): OK -> State: {res_valid['state_name']}, Entity: {res_valid['entity_type']}")

    # Invalid Checksum (should suggest correction)
    res_invalid = verify_gstin_government_portal("36AAACR4849R1Z9")
    assert res_invalid["is_valid"] is False, "Expected checksum mismatch"
    assert res_invalid["corrected_gstin"] == "36AAACR4849R1ZM", f"Expected correction to 'M', got {res_invalid['corrected_gstin']}"
    print(f"Invalid GSTIN Checksum Auto-Correction: OK -> Suggested: {res_invalid['corrected_gstin']}")
    print("PASS: GSTIN Verification")


def test_vahan_verification():
    print("\n--- TEST 3: MoRTH Vahan Verification ---")
    # State RTO series
    res_ka = verify_vehicle_government_portal("KA01AB1234")
    assert res_ka["is_valid"] is True, "Expected KA01AB1234 to be valid"
    assert "Bangalore" in res_ka["rto_name"], f"Expected Bangalore in RTO name, got {res_ka['rto_name']}"
    print(f"KA01AB1234: OK -> {res_ka['rto_name']}, {res_ka['state']}")

    # Bharat series
    res_bh = verify_vehicle_government_portal("22BH1234AA")
    assert res_bh["is_valid"] is True, "Expected 22BH1234AA to be valid"
    print(f"22BH1234AA (BH Series): OK -> {res_bh['series_type']}")
    print("PASS: Vahan Verification")


def test_reconciliation_tolerance():
    print("\n--- TEST 4: Reconciliation +/- Rs 2 Tolerance ---")
    validator = GSTValidator()
    
    # Test invoice with Rs 1.50 rounding difference (within +/- 2 tolerance)
    inv_within_tol = {
        "docdt1": {"doc_typ": "INV", "doc_no": "TEST-01", "doc_date": "14/10/2026"},
        "sellerdtls": {"gstin": "27TUHCN2957U5ZN", "lgl_name": "Test Seller", "addr1": "Mumbai", "loc": "Mumbai", "pin": "400001", "stcd": "27"},
        "buyerdtls": {"gstin": "27TUHCN2957U5ZN", "lgl_name": "Test Buyer", "pos": "27", "addr1": "Mumbai", "loc": "Mumbai", "pin": "400001", "stcd": "27"},
        "itemdtls": [{
            "slno": "1", "prdnm": "Goods A", "hsncd": "850440", "qty": "1", "unitprice": "100.00",
            "totamt": "100.00", "assamt": "100.00", "cgstrat": "9", "cgstamt": "9.00", "sgstrat": "9", "sgstamt": "9.00",
            "totitemval": "118.00"
        }],
        "valdt1": {
            "ttlassval": "100.00",
            "cgstval": "9.00",
            "sgstval": "9.00",
            "igstval": "0.00",
            "cesval": "0.00",
            "stcesval": "0.00",
            "cesnonadval": "0.00",
            # Grand total has 1.50 round off discrepancy: 118.00 vs 119.50 (<= 2.00)
            "totinvval": "119.50"
        }
    }
    
    errs = validator.validate_invoice(inv_within_tol)
    err_codes = [e.get("code") if isinstance(e, dict) else getattr(e, "code", None) for e in errs]
    assert 2189 not in err_codes, f"Discrepancy of Rs 1.50 should be tolerated under +/- Rs 2, got errors: {errs}"
    print("Discrepancy of Rs 1.50: Permitted without error 2189 -> PASS")

    inv_exceed_tol = dict(inv_within_tol)
    inv_exceed_tol["valdt1"] = dict(inv_within_tol["valdt1"], totinvval="135.00")
    errs_exceed = validator.validate_invoice(inv_exceed_tol)
    print("Errors in exceed test:", [(e.get("code") or e.get("error_code"), e.get("field"), e.get("message")) for e in errs_exceed if isinstance(e, dict)])
    err_codes_exceed = [e.get("error_code") or e.get("code") if isinstance(e, dict) else getattr(e, "code", None) for e in errs_exceed]
    assert 2189 in err_codes_exceed, f"Discrepancy of Rs 17.00 should trigger error 2189, got: {err_codes_exceed}"
    print("Discrepancy of Rs 17.00: Properly flagged with Error 2189 -> PASS")
    print("PASS: Reconciliation Tolerance")


def test_converter_chat():
    print("\n--- TEST 5: Converter Assistant Chatbot ---")
    sample = load_default_sample_dirty()
    response = process_converter_chat(
        user_message="Verify my GSTIN 36AAACR4849R1ZM",
        raw_payload=sample
    )
    assert response["status"] == "success", "Expected success status in chat"
    reply = response["reply"]
    print(f"Chatbot reply snippet:\n{reply[:300]}...")
    assert "36AAACR4849R1ZM" in reply, "Expected GSTIN in reply"
    print("PASS: Converter Chatbot")


if __name__ == "__main__":
    print("==================================================")
    print("  RUNNING COMPLETE GST SENTINEL VERIFICATION SUITE")
    print("==================================================")
    test_hsn_master()
    test_gstin_verification()
    test_vahan_verification()
    test_reconciliation_tolerance()
    test_converter_chat()
    print("\n==================================================")
    print("  ALL 5 VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("==================================================")
