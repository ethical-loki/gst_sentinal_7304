import json
from backend.converter_service import auto_route_tax_split, compute_buyer_risk_profile, process_converter_chat

def test_interstate_auto_calculation():
    # User screenshot scenario:
    # Supplier: 27 (Maharashtra)
    # Buyer: 29 (Karnataka) - 29XYZAB5678C1Z2
    # POS: 29
    # Dirty input has CGST/SGST charged instead of IGST
    payload = {
        "einvoices": [{
            "docdt1": {
                "docno": "INV-2026-001",
                "docdt": "2026-10-23"
            },
            "supplierdt1": {
                "supplier_gstin": "27ABCDE1234F1Z5",
                "supplier_state": "27"
            },
            "buyerdt1": {
                "buyer_gstin": "29XYZAB5678C1Z2",
                "buyer_state": "29",
                "pos": "29"
            },
            "valdtls": {
                "assval": 10000.0,
                "cgstval": 900.0,
                "sgstval": 900.0,
                "igstval": 0.0,
                "totinvval": 11800.0
            },
            "itemdtls": [
                {
                    "itemno": 1,
                    "prdnm": "Electric Motor 5HP",
                    "hsncd": "85011013",
                    "qty": 1.0,
                    "unitrate": 10000.0,
                    "grossamt": 10000.0,
                    "assamt": 10000.0,
                    "cgstrt": 9.0,
                    "cgstval": 900.0,
                    "sgstrt": 9.0,
                    "sgstval": 900.0,
                    "igstrt": 0.0,
                    "igstval": 0.0,
                    "totitemval": 11800.0
                }
            ]
        }]
    }

    # Before auto-routing, check buyer risk profile
    inv = payload["einvoices"][0]
    b_risk_before = compute_buyer_risk_profile(inv)
    has_mismatch_before = any("Tax Split Mismatch" in f for f in b_risk_before.get("risk_factors", []))
    print(f"Before routing - Has Tax Split Mismatch: {has_mismatch_before}")
    assert has_mismatch_before, "Should have Tax Split Mismatch before routing"

    # Now run process_converter_chat (e.g. user just asks a question or opens chat)
    res = process_converter_chat("Explain compliance status", payload)
    
    # Check updated payload
    up_inv = res["updated_payload"]["einvoices"][0]
    item = up_inv["itemdtls"][0]
    
    print("\nAfter routing results:")
    print(f"Patch applied: {res['patch_applied']}")
    print(f"Patch summary: {res['patch_summary']}")
    print(f"Item IGST Rate: {item.get('igstrt')}, IGST Amt: {item.get('igstamt')}, IGST Val: {item.get('igstval')}")
    print(f"Item CGST Rate: {item.get('cgstrt')}, CGST Amt: {item.get('cgstamt')}, CGST Val: {item.get('cgstval')}")
    print(f"Valdtls: {up_inv.get('valdtls')}")
    
    b_risk_after = compute_buyer_risk_profile(up_inv)
    has_mismatch_after = any("Tax Split Mismatch" in f for f in b_risk_after.get("risk_factors", []))
    is_igst_correct = any("correctly routed through Integrated GST (IGST)" in f for f in b_risk_after.get("risk_factors", []))
    print(f"After routing - Has Tax Split Mismatch: {has_mismatch_after}")
    print(f"After routing - Is IGST Correctly routed: {is_igst_correct}")
    
    assert not has_mismatch_after, "Tax Split Mismatch should be gone!"
    assert is_igst_correct, "Should be correctly routed through IGST!"
    assert float(item.get("igstrt")) == 18.0
    assert float(item.get("cgstrt")) == 0.0
    assert float(item.get("sgstrt")) == 0.0
    assert float(item.get("igstval")) == 1800.0
    print("\n[SUCCESS] Interstate test passed!")

def test_intrastate_auto_calculation():
    # Intrastate: Supplier 27, Buyer 27, wrongly charged IGST
    payload = {
        "einvoices": [{
            "docdt1": {"docno": "INV-2026-002", "docdt": "2026-10-23"},
            "supplierdt1": {"supplier_gstin": "27ABCDE1234F1Z5", "supplier_state": "27"},
            "buyerdt1": {"buyer_gstin": "27XYZAB5678C1Z2", "buyer_state": "27", "pos": "27"},
            "valdtls": {"assval": 20000.0, "cgstval": 0.0, "sgstval": 0.0, "igstval": 3600.0, "totinvval": 23600.0},
            "itemdtls": [{
                "itemno": 1, "prdnm": "Motors", "hsncd": "85011013",
                "qty": 2.0, "unitrate": 10000.0, "grossamt": 20000.0, "assamt": 20000.0,
                "cgstrt": 0.0, "cgstval": 0.0, "sgstrt": 0.0, "sgstval": 0.0,
                "igstrt": 18.0, "igstval": 3600.0, "totitemval": 23600.0
            }]
        }]
    }
    res = process_converter_chat("Audit payload", payload)
    up_inv = res["updated_payload"]["einvoices"][0]
    item = up_inv["itemdtls"][0]
    
    print("\nIntrastate routing results:")
    print(f"Item CGST: {item.get('cgstrt')}% (Val: {item.get('cgstval')})")
    print(f"Item SGST: {item.get('sgstrt')}% (Val: {item.get('sgstval')})")
    print(f"Item IGST: {item.get('igstrt')}% (Val: {item.get('igstval')})")
    print(f"Valdtls: {up_inv.get('valdtls')}")
    
    b_risk = compute_buyer_risk_profile(up_inv)
    is_intra_correct = any("correctly routed through dual CGST + SGST" in f for f in b_risk.get("risk_factors", []))
    print(f"Is dual CGST+SGST correctly recognized: {is_intra_correct}")
    
    assert is_intra_correct
    assert float(item.get("cgstrt")) == 9.0
    assert float(item.get("sgstrt")) == 9.0
    assert float(item.get("igstrt")) == 0.0
    assert float(item.get("cgstval")) == 1800.0
    assert float(item.get("sgstval")) == 1800.0
    assert float(item.get("igstval")) == 0.0
    print("[SUCCESS] Intrastate test passed!")

if __name__ == "__main__":
    test_interstate_auto_calculation()
    test_intrastate_auto_calculation()
    print("\nALL AUTOMATIC GST TAX SPLIT TESTS PASSED SUCCESSFULLY!")

