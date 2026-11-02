import os
import sys
sys.path.insert(0, os.path.abspath("."))
import time
import json
import pytest

from Template_Converters.hsn_resolver import audit_and_rectify_line_item_sentinel
from src.ml.hsn_verified_store import get_hsn_verified_store
from src.ml.qwen_hsn_verifier import get_qwen_hsn_verifier
from src.ingestion.storage import flatten_invoice_payload

print("=" * 80)
print("TEST SUITE: HSN_VERIFIED_STORE.PARQUET FIRST -> THEN QWEN IN LAKEHOUSE")
print("=" * 80)

store = get_hsn_verified_store()
print(f"[INIT] hsn_verified_store.parquet loaded with {len(store.memory_cache)} records.")

# ------------------------------------------------------------------------------
# Test 1A: Existing item in store - Correct HSN & Correct Rate -> AUTO_APPROVED
# ------------------------------------------------------------------------------
t0 = time.perf_counter()
res_1a = audit_and_rectify_line_item_sentinel(
    product_name="COTTON-SHIRTS",
    product_desc="Men Casual 100% Cotton Shirt",
    declared_hsn="62052000",
    unit_price=800.0,
    declared_rate=5.0
)
dur_1a = (time.perf_counter() - t0) * 1000.0
print(f"\n[Test 1A] Pre-existing item with correct HSN & Rate ({dur_1a:.2f}ms):")
print("  Status badge:", res_1a["status_badge"])
print("  Should rectify:", res_1a["should_rectify"])
print("  Is flagged:", res_1a["is_flagged"])
print("  Reasons:", res_1a["reasons"])
assert res_1a["status_badge"] == "AUTO_APPROVED", f"Expected AUTO_APPROVED, got {res_1a['status_badge']}"
assert not res_1a["should_rectify"], "Expected should_rectify=False"
assert not res_1a["is_flagged"], "Expected is_flagged=False"
assert any("Already there in the stored file" in r for r in res_1a["reasons"]), "Expected stored file indication"
print("  => PASSED: Fast retrieval from hsn_verified_store.parquet; No error declared.")

# ------------------------------------------------------------------------------
# Test 1B: Existing item in store - Wrong HSN -> FLAGGED_AND_RECTIFIED
# ------------------------------------------------------------------------------
t0 = time.perf_counter()
res_1b = audit_and_rectify_line_item_sentinel(
    product_name="COTTON-SHIRTS",
    product_desc="Men Casual 100% Cotton Shirt",
    declared_hsn="610510",  # Knitted code entered for woven shirt
    unit_price=800.0,
    declared_rate=5.0
)
dur_1b = (time.perf_counter() - t0) * 1000.0
print(f"\n[Test 1B] Pre-existing item with WRONG HSN ({dur_1b:.2f}ms):")
print("  Status badge:", res_1b["status_badge"])
print("  Rectified HSN:", res_1b["rectified_hsn"])
print("  Statutory rate:", res_1b["statutory_rate"])
print("  Reasons:", res_1b["reasons"][:2])
assert res_1b["status_badge"] == "FLAGGED_AND_RECTIFIED"
assert res_1b["rectified_hsn"] == "62052000"
assert res_1b["statutory_rate"] == 5.0
assert any("Already there in the stored file" in r for r in res_1b["reasons"]), "Expected stored file indication"
print("  => PASSED: Fast retrieval from stored file; Corrected to 62052000 at 5.0% GST.")

# ------------------------------------------------------------------------------
# Test 1C: Existing item in store - Correct HSN but Wrong Rate -> FLAGGED_AND_RECTIFIED
# ------------------------------------------------------------------------------
t0 = time.perf_counter()
res_1c = audit_and_rectify_line_item_sentinel(
    product_name="COTTON-SHIRTS",
    product_desc="Men Casual 100% Cotton Shirt",
    declared_hsn="62052000",
    unit_price=800.0,
    declared_rate=18.0  # Mismatched 18% instead of statutory 5%
)
dur_1c = (time.perf_counter() - t0) * 1000.0
print(f"\n[Test 1C] Pre-existing item with WRONG Rate ({dur_1c:.2f}ms):")
print("  Status badge:", res_1c["status_badge"])
print("  Statutory rate:", res_1c["statutory_rate"])
assert res_1c["status_badge"] == "FLAGGED_AND_RECTIFIED"
assert res_1c["statutory_rate"] == 5.0
print("  => PASSED: Rate divergence flagged and statutory 5.0% rate enforced.")

# ------------------------------------------------------------------------------
# Test 2: Item NOT in store -> Uses Qwen layer and then stores it in parquet
# ------------------------------------------------------------------------------
new_prod_name = "Super Special Ceramic Thermal Insulator Tile"
new_prod_desc = "High-temperature refractory ceramic insulation tile"
new_declared_hsn = "69022090"

# Verify item is not initially in store
initial_lookup = store.lookup_item(new_prod_name, new_prod_desc)
print(f"\n[Test 2] Novel item initial store lookup: {initial_lookup}")

res_2 = audit_and_rectify_line_item_sentinel(
    product_name=new_prod_name,
    product_desc=new_prod_desc,
    declared_hsn=new_declared_hsn,
    unit_price=450.0,
    declared_rate=18.0
)
print("  Qwen Audit executed.")
print("  Status badge:", res_2["status_badge"])
print("  Rectified/Verified HSN:", res_2["rectified_hsn"])
print("  Statutory rate:", res_2["statutory_rate"])

# Check that it is now persisted in hsn_verified_store.parquet
after_lookup = store.lookup_item(new_prod_name, new_prod_desc)
print("  Store lookup after Qwen verification:", bool(after_lookup))
assert after_lookup is not None, "Expected newly verified item to be persisted to store"

# Second lookup should now be an ultra-fast cache hit saying "Already there in the stored file"!
t0 = time.perf_counter()
res_2_second = audit_and_rectify_line_item_sentinel(
    product_name=new_prod_name,
    product_desc=new_prod_desc,
    declared_hsn=res_2["rectified_hsn"],
    unit_price=450.0,
    declared_rate=res_2["statutory_rate"]
)
dur_second = (time.perf_counter() - t0) * 1000.0
print(f"  Second lookup latency: {dur_second:.2f}ms")
print("  Second lookup status:", res_2_second["status_badge"])
assert any("Already there in the stored file" in r for r in res_2_second["reasons"])
print("  => PASSED: Qwen verified and persisted to parquet; subsequent retrieval says 'Already there in the stored file'.")

# ------------------------------------------------------------------------------
# Test 3: Lakehouse Flattening with stored vs new items
# ------------------------------------------------------------------------------
lakehouse_payload = {
    "self_gstin": "29ABCDE1234F1Z5",
    "docno": "INV-LAKEHOUSE-001",
    "docdt": "2026-10-26",
    "supplier": {"gstin": "29ABCDE1234F1Z5", "state": "29", "pin": 560001},
    "buyer": {"gstin": "29XYZAB5678C1Z2", "state": "29", "pos": "29", "pin": 560002},
    "itemdtls": [
        {
            "item_slno": "1",
            "prdnm": "COTTON-SHIRTS",
            "prddesc": "Men Casual 100% Cotton Shirt",
            "hsn": "610510",  # Wrong -> Should rectify to 62052000 from store
            "qty": 200.0,
            "unit": "NOS",
            "unitprice": 800.0,
            "assval": 160000.0,
            "gstrate": 5.0,
            "cgstval": 4000.0,
            "sgstval": 4000.0,
            "totitemval": 168000.0,
            "is_service": "N"
        },
        {
            "item_slno": "2",
            "prdnm": "COTTON-SHIRTS",
            "prddesc": "Men Casual 100% Cotton Shirt",
            "hsn": "62052000",  # Correct & 5% -> AUTO_APPROVED
            "qty": 200.0,
            "unit": "NOS",
            "unitprice": 800.0,
            "assval": 160000.0,
            "gstrate": 5.0,
            "cgstval": 4000.0,
            "sgstval": 4000.0,
            "totitemval": 168000.0,
            "is_service": "N"
        }
    ],
    "valdtls": {
        "assval": 320000.0,
        "cgstval": 8000.0,
        "sgstval": 8000.0,
        "totinvval": 336000.0
    }
}

rows = flatten_invoice_payload(lakehouse_payload)
print("\n[Test 3] Lakehouse Flatten Payload:")
print("  Row 1 HSN:", rows[0]["hsn"], "| Badge:", rows[0]["sentinel_status_badge"])
print("  Row 2 HSN:", rows[1]["hsn"], "| Badge:", rows[1]["sentinel_status_badge"])
assert rows[0]["hsn"] == "62052000"
assert rows[0]["sentinel_status_badge"] == "FLAGGED_AND_RECTIFIED"
assert "Already there in the stored file" in rows[0]["sentinel_audit_reasons"]

assert rows[1]["hsn"] == "62052000"
assert rows[1]["sentinel_status_badge"] == "AUTO_APPROVED"
assert "Already there in the stored file" in rows[1]["sentinel_audit_reasons"]
print("  => PASSED: Lakehouse payload flattened with stored file verification telemetry.")

print("\n" + "=" * 80)
print("ALL TESTS PASSED SUCCESSFULLY! STORE FIRST THEN QWEN CONFIRMED.")
print("=" * 80)
