import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import json
import pytest
from src.ml.qwen_hsn_verifier import get_qwen_hsn_verifier
from Template_Converters.hsn_resolver import audit_and_rectify_line_item_sentinel
from backend.converter_service import process_converter_pipeline, process_converter_chat

def test_qwen_verifier_cotton_shirt():
    verifier = get_qwen_hsn_verifier()
    
    # 1. Declared wrong HSN 610510
    res_wrong = verifier.verify_item("COTTON-SHIRTS Men Casual 100% Cotton Shirt", base_hsn="610510", base_rate=5.0)
    print("\n--- TEST 1: Wrong HSN 610510 ---")
    print("Status:", res_wrong["status"])
    print("Qwen HSN:", res_wrong["qwen_hsn"])
    print("Qwen Rate:", res_wrong["qwen_rate"])
    print("Reasoning:", res_wrong["reasoning"])
    assert res_wrong["status"] == "CORRECTED_BY_QWEN"
    assert res_wrong["qwen_hsn"] == "62052000"
    assert res_wrong["qwen_rate"] == 5.0
    assert res_wrong["is_perfect_match"] is False

    # 2. Declared correct HSN 62052000 with correct rate 5.0
    res_correct = verifier.verify_item("COTTON-SHIRTS Men Casual 100% Cotton Shirt", base_hsn="62052000", base_rate=5.0)
    print("\n--- TEST 2: Correct HSN 62052000 & 5.0% ---")
    print("Status:", res_correct["status"])
    print("Qwen HSN:", res_correct["qwen_hsn"])
    print("Qwen Rate:", res_correct["qwen_rate"])
    print("is_perfect_match:", res_correct["is_perfect_match"])
    assert res_correct["status"] == "PERFECT_MATCH"
    assert res_correct["qwen_hsn"] == "62052000"
    assert res_correct["is_perfect_match"] is True

    # 3. Declared correct HSN 62052000 but wrong rate 18.0
    res_wrong_rate = verifier.verify_item("COTTON-SHIRTS Men Casual 100% Cotton Shirt", base_hsn="62052000", base_rate=18.0)
    print("\n--- TEST 3: Correct HSN 62052000 but wrong rate 18.0% ---")
    print("Status:", res_wrong_rate["status"])
    print("Qwen Rate:", res_wrong_rate["qwen_rate"])
    assert res_wrong_rate["status"] == "CORRECTED_BY_QWEN"
    assert res_wrong_rate["qwen_rate"] == 5.0
    assert res_wrong_rate["is_perfect_match"] is False


def test_audit_sentinel_rectification():
    # 1. With wrong HSN 610510
    audit_wrong = audit_and_rectify_line_item_sentinel(
        product_name="COTTON-SHIRTS",
        product_desc="Men Casual 100% Cotton Shirt",
        declared_hsn="610510",
        unit_price=800.0,
        supplier_gstin="27AAACR4849R1ZH",
        declared_rate=5.0
    )
    print("\n--- TEST 4: Sentinel with 610510 ---")
    print("should_rectify:", audit_wrong["should_rectify"])
    print("rectified_hsn:", audit_wrong["rectified_hsn"])
    print("statutory_rate:", audit_wrong["statutory_rate"])
    assert audit_wrong["should_rectify"] is True
    assert audit_wrong["rectified_hsn"] == "62052000"
    assert audit_wrong["statutory_rate"] == 5.0

    # 2. With corrected HSN 62052000 & 5.0%
    audit_correct = audit_and_rectify_line_item_sentinel(
        product_name="COTTON-SHIRTS",
        product_desc="Men Casual 100% Cotton Shirt",
        declared_hsn="62052000",
        unit_price=800.0,
        supplier_gstin="27AAACR4849R1ZH",
        declared_rate=5.0
    )
    print("\n--- TEST 5: Sentinel with 62052000 & 5.0% ---")
    print("should_rectify:", audit_correct["should_rectify"])
    print("is_flagged:", audit_correct["is_flagged"])
    print("status_badge:", audit_correct["status_badge"])
    assert audit_correct["should_rectify"] is False
    assert audit_correct["is_flagged"] is False
    assert audit_correct["status_badge"] == "QWEN_VERIFIED_PERFECT"


def test_pipeline_hsn_validation():
    # Construct realistic invoice matching user screenshot
    payload = {
        "einvoices": [
            {
                "docdt1": {
                    "docno": "INV-SHIRT-001",
                    "docdt": "2026-10-31"
                },
                "trandt1": {
                    "trancatg": "B2B",
                    "regrev": "N"
                },
                "supplierdt1": {
                    "supplier_gstin": "27AAACR4849R1ZH",
                    "supplier_legal_name": "ABC TEXTILES PVT LTD",
                    "supplier_address1": "100 Cotton Mill Rd",
                    "supplier_place": "Mumbai",
                    "supplier_state": "27",
                    "supplier_pincode": "400001"
                },
                "buyerdt1": {
                    "buyer_gstin": "27BBBCE2208R1Z1",
                    "buyer_legal_name": "XYZ RETAIL STORES",
                    "buyer_address1": "200 Fashion Ave",
                    "buyer_place": "Pune",
                    "buyer_state": "27",
                    "buyer_pincode": "411001",
                    "pos": "27"
                },
                "itemdtls": [
                    {
                        "item_index": 1,
                        "prdnm": "COTTON-SHIRTS",
                        "prddesc": "Men Casual 100% Cotton Shirt",
                        "hsncd": "610510",
                        "qty": "200.000",
                        "uqc": "NOS",
                        "unitprice": "800.00",
                        "grossamt": "160000.00",
                        "discount": "0.00",
                        "assamt": "160000.00",
                        "gstrate": "5.00",
                        "cgstrt": "2.50",
                        "cgstamt": "4000.00",
                        "sgstrt": "2.50",
                        "sgstamt": "4000.00",
                        "totitemval": "168000.00"
                    }
                ],
                "valdt1": {
                    "assval": "160000.00",
                    "cgstval": "4000.00",
                    "sgstval": "4000.00",
                    "totinvval": "168000.00"
                }
            }
        ]
    }

    # Step 1: Check wrong HSN 610510 in pipeline
    chat_res = process_converter_chat(
        user_message="Explain Errors",
        raw_payload=payload
    )
    print("\n--- TEST 6: Chat guidance with wrong HSN 610510 ---")
    print("Reply snippet:", chat_res["reply"][:300])
    assert "62052000" in chat_res["reply"]
    assert any("Set HSN: 62052000" in act for act in chat_res["interactive_actions"])

    # Step 2: Apply correct HSN 62052000 via Copilot
    chat_fix = process_converter_chat(
        user_message="Set HSN: 62052000, Rate: 800.00, Qty: 200.0, Unit: NOS, Taxable Value: 160000.00",
        raw_payload=payload
    )
    print("\n--- TEST 7: Chat fix with correct HSN 62052000 ---")
    print("Patch applied:", chat_fix["patch_applied"])
    assert chat_fix["patch_applied"] is True

    # Step 3: Now check re-validated payload
    up_payload = chat_fix["updated_payload"]
    re_chat = process_converter_chat(
        user_message="Explain Errors",
        raw_payload=up_payload
    )
    print("\n--- TEST 8: Re-check after HSN 62052000 applied ---")
    # Should NOT have "Wrong / Misclassified HSN Code Detected" anymore!
    print("Does reply contain Wrong HSN Code Detected?", "Wrong / Misclassified HSN Code Detected" in re_chat["reply"])
    assert "Wrong / Misclassified HSN Code Detected" not in re_chat["reply"]

if __name__ == "__main__":
    test_qwen_verifier_cotton_shirt()
    test_audit_sentinel_rectification()
    test_pipeline_hsn_validation()
    print("\n================ ALL TESTS PASSED SUCCESSFULLY! ================\n")
