import sys
import os
sys.path.insert(0, os.path.abspath("."))
from datetime import datetime
from Template_Converters.hsn_resolver import audit_and_rectify_line_item_sentinel
from backend.converter_service import lookup_hsn_by_description, process_converter_chat

print("--- TEST 1: Motor Car HSN Resolution ---")
res = audit_and_rectify_line_item_sentinel(
    product_name="Luxury Passenger Motor Car",
    product_desc="Motor car for personal executive transit",
    declared_hsn="87032291",
    unit_price=2500000.0,
    supplier_gstin="27ABCDE1234F1ZO"
)
print(f"audit_and_rectify_line_item_sentinel -> is_flagged: {res.get('is_flagged')}, should_rectify: {res.get('should_rectify')}, rectified_hsn: {res.get('rectified_hsn')}, status_badge: {res.get('status_badge')}")
assert res.get("is_flagged") is False, "Should NOT flag valid 87032291 motor car!"
assert res.get("rectified_hsn") == "87032291", "Should retain 87032291!"

print("\n--- TEST 2: lookup_hsn_by_description for Motor Car ---")
matches = lookup_hsn_by_description("Luxury Passenger Motor Car", "Motor car for personal executive transit", top_k=3)
print(f"Matches count: {len(matches)}")
if matches:
    print(f"Top match: {matches[0]['hsn_code']} - {matches[0]['description'][:60]}")
    assert not matches[0]['hsn_code'].startswith("8501"), "Should NOT match electric motor 8501 for motor car!"

print("\n--- TEST 3: process_converter_chat with 87032291 personal use car ---")
sample_payload = {
    "docno": "INV-2026-001",
    "docdt": datetime.now().strftime("%Y-%m-%d"),
    "trancatg": "B2B",
    "supplier_gstin": "27ABCDE1234F1ZO",
    "supplier_state": "27",
    "supplier_pin": "400001",
    "buyer_gstin": "29XYZAB5678C1Z2",
    "buyer_state": "29",
    "buyer_pin": "560001",
    "pos": "29",
    "items": [
        {
            "prdnm": "Luxury Passenger Motor Car",
            "prddesc": "Motor car for personal executive transit",
            "hsncd": "87032291",
            "qty": 1.0,
            "unitrate": 2500000.0,
            "assval": 2500000.0
        }
    ]
}
chat_res = process_converter_chat("Audit this invoice", sample_payload)
print(f"Chat reply starts with:\n{chat_res.get('reply')[:200]}...")
print(f"Interactive actions: {chat_res.get('interactive_actions')}")
assert not any("85011013" in str(a) for a in chat_res.get("interactive_actions", [])), "Should NOT recommend 85011013!"
assert "85011013" not in chat_res.get("reply", ""), "Should NOT mention 85011013 in reply!"

print("\n--- TEST 4: Invalid docno (starts with 0 / blank) triggers editable docno suggestion ---")
bad_docno_payload = dict(sample_payload)
bad_docno_payload["docno"] = "0INV-BAD"
bad_docno_payload["docdt1"] = {"docno": "0INV-BAD", "docdt": datetime.now().strftime("%Y-%m-%d")}

chat_docno_res = process_converter_chat("Check this invoice", bad_docno_payload)
print(f"Actions for bad docno: {chat_docno_res.get('interactive_actions')}")
assert any("Set Invoice No:" in a for a in chat_docno_res.get("interactive_actions", [])), "Should prompt to Set Invoice No!"

print("\n--- TEST 5: Apply Set Invoice No intent ---")
patch_docno_res = process_converter_chat("Set Invoice No: INV-2026-FINAL", bad_docno_payload)
print(f"Patch applied: {patch_docno_res.get('patch_applied')}")
print(f"Patch summary: {patch_docno_res.get('patch_summary')}")
updated_inv = patch_docno_res.get("updated_payload", bad_docno_payload)
if "einvoices" in updated_inv:
    updated_inv = updated_inv["einvoices"][0]
print(f"Updated docno in payload: {updated_inv.get('docno')} | docdt1: {updated_inv.get('docdt1', {}).get('docno')}")
assert updated_inv.get("docno") == "INV-2026-FINAL", "docno should be updated to INV-2026-FINAL!"

print("\n✅ ALL TESTS PASSED SUCCESSFULLY!")
