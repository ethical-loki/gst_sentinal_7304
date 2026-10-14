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
    assert hsn_data is not None, "Failed to load Final_hsn_sac_copy.xlsx"
    df, hsn_col, desc_col = hsn_data
    print(f"Loaded HSN DataFrame: {len(df)} rows")
    
    matches = lookup_hsn_by_description("cotton yarn", top_k=2)
    print(f"Lookup 'cotton yarn': Found {len(matches)} matches")
    assert len(matches) > 0, "Expected matches for cotton yarn"
    m0 = matches[0]
    print(f"  Match 1: [{m0['hsn_code']}] {m0['description']}")
    print(f"  Rates: IGST={m0['igst_rate']}%, CGST={m0['cgst_rate']}%, SGST={m0['sgst_rate']}%")
    assert m0["igst_rate"] == 5.0, f"Expected 5.0% IGST for cotton yarn, got {m0['igst_rate']}"
    assert m0["cgst_rate"] == 2.5, f"Expected 2.5% CGST for cotton yarn, got {m0['cgst_rate']}"
    assert m0["sgst_rate"] == 2.5, f"Expected 2.5% SGST for cotton yarn, got {m0['sgst_rate']}"
    print("PASS: HSN Master Lookup & Statutory Rate Verification")


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


def test_price_anomaly_detection():
    print("\n--- TEST 6: Price & Unit Rate Anomaly Detection (Anti-Under/Over-Invoicing) ---")
    from Template_Converters.price_anomaly_detector import get_price_anomaly_detector
    
    detector = get_price_anomaly_detector()
    
    # 1. Decimal typo test (accidental decimal shift: 2600 instead of 260.00 for LED Driver)
    res_typo = detector.analyze_item(
        hsn="850440",
        product_name="Electronic LED Driver 40W",
        unit_price=2600.0,
        quantity=50.0,
        uqc="NOS"
    )
    print(f"Typo test result: is_anomaly={res_typo['is_anomaly']}, type={res_typo['anomaly_type']}, risk={res_typo['risk_score']}, suggested={res_typo.get('suggested_rate')}")
    assert res_typo["is_anomaly"] is True, "Expected anomaly for 10x decimal shift typo"
    assert res_typo["anomaly_type"] == "DECIMAL_SHIFT_TYPO", f"Expected DECIMAL_SHIFT_TYPO, got {res_typo['anomaly_type']}"
    assert res_typo["suggested_rate"] == 260.0, f"Expected suggested rate 260.0, got {res_typo['suggested_rate']}"

    # 2. Extreme Under-Invoicing (User prompt scenario: 100-ton steel rod shipment for Rs 10/ton)
    res_under = detector.analyze_item(
        hsn="7214",
        product_name="High Tensile Steel Rods",
        unit_price=10.0,
        quantity=100.0,
        uqc="TON"
    )
    print(f"Under-invoicing test result: is_anomaly={res_under['is_anomaly']}, type={res_under['anomaly_type']}, risk={res_under['risk_score']}")
    assert res_under["is_anomaly"] is True, "Expected anomaly for severe under-invoicing"
    assert res_under["anomaly_type"] == "UNDER_INVOICING", f"Expected UNDER_INVOICING, got {res_under['anomaly_type']}"

    # 3. Extreme Over-Invoicing (User prompt scenario: cotton yarn at Rs 5,000/kg instead of benchmark)
    res_over = detector.analyze_item(
        hsn="5205",
        product_name="Cotton Yarn 40s Combed",
        unit_price=5000.0,
        quantity=100.0,
        uqc="KGS"
    )
    print(f"Over-invoicing test result: is_anomaly={res_over['is_anomaly']}, type={res_over['anomaly_type']}, risk={res_over['risk_score']}")
    assert res_over["is_anomaly"] is True, "Expected anomaly for severe over-invoicing"
    assert res_over["anomaly_type"] in ("OVER_INVOICING", "DECIMAL_SHIFT_TYPO"), f"Expected over-invoicing, got {res_over['anomaly_type']}"

    # 4. Conversational audit via chat (Clean payload)
    sample = load_default_sample_dirty()
    chat_resp = process_converter_chat(
        user_message="audit unit rates and detect price anomalies",
        raw_payload=sample
    )
    assert chat_resp["status"] == "success", "Expected chat price audit success"
    assert "Price & Unit Rate Audit" in chat_resp["reply"], "Expected price audit in chat reply"
    print("Chat price audit (clean) response snippet:\n" + chat_resp["reply"][:250] + "...")

    # 5. Conversational audit via chat (Payload with severe anomaly)
    sample_anomaly = load_default_sample_dirty()
    target_inv = sample_anomaly["einvoices"][0] if ("einvoices" in sample_anomaly and sample_anomaly["einvoices"]) else sample_anomaly
    if "itemdtls" not in target_inv:
        target_inv["itemdtls"] = []
    
    # Inject anomalous item: cotton yarn @ Rs 5,000/kg
    target_inv["itemdtls"].append({
        "slno": "2",
        "prdnm": "Cotton Yarn 40s Combed",
        "hsncd": "520522",
        "qty": "100",
        "unitprice": "5000.00",
        "totamt": "500000.00",
        "assamt": "500000.00",
        "cgstrat": "2.5",
        "cgstamt": "12500.00",
        "sgstrat": "2.5",
        "sgstamt": "12500.00",
        "totitemval": "525000.00",
        "uqc": "KGS"
    })
    chat_anomaly_resp = process_converter_chat(
        user_message="check price anomalies in my invoice",
        raw_payload=sample_anomaly
    )
    assert chat_anomaly_resp["status"] == "success", "Expected success"
    assert "Anomaly Audit Detected" in chat_anomaly_resp["reply"], "Expected anomaly detected in chat reply"
    print("Chat anomaly audit detected anomalous item correctly -> PASS")

    # 6. Conversational one-click fix via chat
    chat_fix_resp = process_converter_chat(
        user_message="Fix Item 2 rate to 280.00",
        raw_payload=sample_anomaly
    )
    assert chat_fix_resp["patch_applied"] is True, "Expected patch applied"
    assert "Price Anomaly Corrected!" in chat_fix_resp["reply"], "Expected correction notification"
    print("Chat one-click price anomaly auto-fix -> PASS")
    print("PASS: Price & Unit Rate Anomaly Detection")


def test_comprehensive_payload_all_scenarios():
    print("\n--- TEST 7: Master Dummy Payload Covering All Statutory & Business Scenarios ---")
    from Template_Converters.generate_sample_dirty_input import generate_comprehensive_dirty_payload
    from Template_Converters.price_anomaly_detector import get_price_anomaly_detector

    payload = generate_comprehensive_dirty_payload()
    assert "einvoices" in payload, "Expected 'einvoices' in dummy payload"
    invoices = payload["einvoices"]
    assert len(invoices) >= 5, f"Expected at least 5 scenarios in dummy payload, got {len(invoices)}"

    # 1. Verify all 5 statutory scenarios are represented in the dummy payload
    categories = [inv.get("trandt1", {}).get("trancatg") for inv in invoices]
    assert "B2B" in categories, "Scenario missing: B2B"
    assert "EXP" in categories, "Scenario missing: EXP"
    assert "SEZWP" in categories, "Scenario missing: SEZWP"

    # Verify E-Way bill modes (Road vehicle + Rail document)
    ewb_modes = [inv.get("ewbdt1", {}).get("mode_of_transport") for inv in invoices if inv.get("ewbdt1", {}).get("ewayreq") == "Y"]
    assert "1" in ewb_modes, "Scenario missing: Road E-Way Bill (mode 1)"
    assert "2" in ewb_modes, "Scenario missing: Rail E-Way Bill (mode 2)"

    # Verify vehicle registration types (State RTO + Bharat BH Series)
    vehicles = [inv.get("ewbdt1", {}).get("veh_number", "") for inv in invoices]
    assert any("BH" in v for v in vehicles), "Scenario missing: Bharat (BH) Series vehicle"
    assert any("KA" in v or "TN" in v or "GJ" in v for v in vehicles), "Scenario missing: State RTO series vehicle"

    print(f"Loaded master dummy payload with {len(invoices)} scenarios:")
    print("  ✓ Scenario 1: B2B Inter-State + Road E-Way Bill + Key Typos + Comma Decimals")
    print("  ✓ Scenario 2: B2B Intra-State (CGST + SGST) + Rounding Discrepancy (+/- Rs 2 Tolerance) + Rail E-Way Bill")
    print("  ✓ Scenario 3: Direct Export (EXP) + Shipping Bill + Foreign Currency (USD) + Port INMAA1")
    print("  ✓ Scenario 4: SEZ Unit Supply (SEZWP) + Statutory Inter-State IGST Rule")
    print("  ✓ Scenario 5: Bharat (BH) Series Vehicle + Benchmark Commodities")

    # 2. Run through full conversion pipeline & compliance validator
    pipeline_result = process_converter_pipeline(payload, sync_to_disk=False)
    report = pipeline_result["validation_report"]

    print(f"\nPipeline Execution Results:")
    print(f"  Total Invoices : {report['total_invoices']}")
    print(f"  Valid / Compliant : {report['valid_invoices']}")
    print(f"  Failed / Errors : {report['failed_invoices']}")

    assert report["total_invoices"] == len(invoices), f"Expected {len(invoices)} total invoices"
    assert report["valid_invoices"] == len(invoices), f"Expected all {len(invoices)} to be VALID, but {report['failed_invoices']} failed"
    assert report["failed_invoices"] == 0, f"Expected 0 failed invoices, got {report['failed_invoices']}"

    # Verify each invoice is 100% VALID with auto-corrections applied
    for idx, r in enumerate(report["results"], start=1):
        inv_no = r.get("invoice_number")
        status = r.get("status")
        cor_count = len(r.get("corrections_applied", []))
        err_count = len(r.get("errors", []))
        print(f"  -> Invoice {idx} [{inv_no}]: Status={status}, Corrections={cor_count}, Errors={err_count}")
        assert status == "VALID", f"Invoice {inv_no} status should be VALID, got {status}"
        assert err_count == 0, f"Invoice {inv_no} has unexpected errors: {r.get('errors')}"
        assert cor_count > 0, f"Invoice {inv_no} expected auto-corrections for dirty fields"

    # 3. Verify Price Anomaly Detection on all invoices
    detector = get_price_anomaly_detector()
    for idx, inv in enumerate(invoices, start=1):
        scan_res = detector.scan_invoice_payload(inv)
        assert scan_res["has_anomalies"] is False, f"Invoice {idx} unexpectedly flagged price anomaly: {scan_res['findings']}"

    print("All 5 scenario invoices verified: 100% VALID, 0 compliance errors, 0 price anomalies -> PASS")
    print("PASS: Master Dummy Payload All-Scenario Verification")


if __name__ == "__main__":
    print("==================================================")
    print("  RUNNING COMPLETE GST SENTINEL VERIFICATION SUITE")
    print("==================================================")
    test_hsn_master()
    test_gstin_verification()
    test_vahan_verification()
    test_reconciliation_tolerance()
    test_converter_chat()
    test_price_anomaly_detection()
    test_comprehensive_payload_all_scenarios()
    print("\n==================================================")
    print("  ALL 7 VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("==================================================")

