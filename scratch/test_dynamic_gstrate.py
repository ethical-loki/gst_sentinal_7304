import json
from decimal import Decimal
from backend.converter_service import auto_route_tax_split, process_converter_chat
from Template_Converters.payload_builder import process_payload

def test_dynamic_rates():
    test_rates = [0.25, 3.0, 5.0, 12.0, 18.0, 28.0]
    
    print("=== Testing auto_route_tax_split with different gstrate values ===")
    for rate in test_rates:
        # 1. Interstate (27 -> 29)
        inv_inter = {
            "supplierdt1": {"supplier_gstin": "27ABCDE1234F1Z5", "supplier_state": "27"},
            "buyerdt1": {"buyer_gstin": "29XYZAB5678C1Z2", "buyer_state": "29", "pos": "29"},
            "valdtls": {"assval": 10000.0, "totinvval": 10000.0},
            "itemdtls": [{
                "prdnm": "Test Goods", "gstrate": rate,
                "assamt": 10000.0, "totitemval": 10000.0
            }]
        }
        res_inter = auto_route_tax_split(inv_inter)
        it_inter = inv_inter["itemdtls"][0]
        expected_igst_amt = round(10000.0 * (rate / 100.0), 2)
        expected_tot = round(10000.0 + expected_igst_amt, 2)
        
        assert float(it_inter["igstrt"]) == rate, f"Expected igstrt {rate}, got {it_inter['igstrt']}"
        assert float(it_inter["cgstrt"]) == 0.0
        assert float(it_inter["sgstrt"]) == 0.0
        assert float(it_inter["igstamt"]) == expected_igst_amt
        assert float(it_inter["totitemval"]) == expected_tot
        assert float(inv_inter["valdtls"]["igstval"]) == expected_igst_amt
        assert float(inv_inter["valdtls"]["totinvval"]) == expected_tot
        print(f"[PASS] Interstate {rate}%: IGST={expected_igst_amt}, Total={expected_tot}")
        
        # 2. Intrastate (27 -> 27)
        inv_intra = {
            "supplierdt1": {"supplier_gstin": "27ABCDE1234F1Z5", "supplier_state": "27"},
            "buyerdt1": {"buyer_gstin": "27XYZAB5678C1Z2", "buyer_state": "27", "pos": "27"},
            "valdtls": {"assval": 10000.0, "totinvval": 10000.0},
            "itemdtls": [{
                "prdnm": "Test Goods", "gstrate": rate,
                "assamt": 10000.0, "totitemval": 10000.0
            }]
        }
        res_intra = auto_route_tax_split(inv_intra)
        it_intra = inv_intra["itemdtls"][0]
        half_rate = round(rate / 2.0, 3)
        expected_half_amt = round(10000.0 * (half_rate / 100.0), 2)
        expected_tot_intra = round(10000.0 + (expected_half_amt * 2), 2)
        
        assert float(it_intra["cgstrt"]) == half_rate
        assert float(it_intra["sgstrt"]) == half_rate
        assert float(it_intra["igstrt"]) == 0.0
        assert float(it_intra["cgstamt"]) == expected_half_amt
        assert float(it_intra["sgstamt"]) == expected_half_amt
        assert float(it_intra["totitemval"]) == expected_tot_intra
        assert float(inv_intra["valdtls"]["cgstval"]) == expected_half_amt
        assert float(inv_intra["valdtls"]["sgstval"]) == expected_half_amt
        assert float(inv_intra["valdtls"]["totinvval"]) == expected_tot_intra
        print(f"[PASS] Intrastate {rate}%: CGST={expected_half_amt}, SGST={expected_half_amt}, Total={expected_tot_intra}")

    print("\n=== Testing Chat Command: 'Set GST rate: 5%' ===")
    chat_payload = {
        "einvoices": [{
            "docdt1": {"docno": "INV-001", "docdt": "2026-10-23"},
            "supplierdt1": {"supplier_gstin": "27ABCDE1234F1Z5", "supplier_state": "27"},
            "buyerdt1": {"buyer_gstin": "29XYZAB5678C1Z2", "buyer_state": "29", "pos": "29"},
            "valdtls": {"assval": 10000.0, "totinvval": 11800.0},
            "itemdtls": [{
                "itemno": 1, "prdnm": "Item", "hsncd": "85011013", "qty": 1.0, "unitrate": 10000.0,
                "grossamt": 10000.0, "assamt": 10000.0, "igstrt": 18.0, "igstamt": 1800.0, "totitemval": 11800.0
            }]
        }]
    }
    chat_res = process_converter_chat("Set GST rate: 5%", chat_payload)
    up_it = chat_res["updated_payload"]["einvoices"][0]["itemdtls"][0]
    up_val = chat_res["updated_payload"]["einvoices"][0]["valdtls"]
    assert float(up_it["igstrt"]) == 5.0
    assert float(up_it["igstval"]) == 500.0
    assert float(up_it["totitemval"]) == 10500.0
    assert float(up_val["totinvval"]) == 10500.0
    print(f"[PASS] Chat dynamically updated rate to 5%: IGST=500.0, Total=10500.0")

    print("\n=== Testing payload_builder.py with raw input containing gstrate: 12 ===")
    raw_input = {
        "docno": "INV-12PCT",
        "docdt": "2026-10-23",
        "self_gstin": "27ABCDE1234F1Z5",
        "buyer_gstin": "29XYZAB5678C1Z2",
        "pos": "29",
        "itemdtls": [{
            "prdnm": "Special Equipment",
            "hsncd": "85011013",
            "qty": "1.0",
            "unitrate": "10000.00",
            "gstrate": "12.0"
        }]
    }
    from Template_Converters.payload_builder import PayloadBuilder
    built, audit_log = PayloadBuilder.auto_correct_and_build(raw_input)
    b_it = built["itemdtls"][0]
    assert float(b_it["igstrt"]) == 12.0, f"Expected 12.0 in built payload, got {b_it['igstrt']}"
    assert float(b_it["igstamt"]) == 1200.0
    assert float(b_it["totitemval"]) == 11200.0
    print(f"[PASS] payload_builder respected gstrate: 12.0 -> IGST=1200.0, Total=11200.0")

    print("\nALL DYNAMIC GSTRATE TESTS COMPLETED SUCCESSFULLY!")

if __name__ == "__main__":
    test_dynamic_rates()
