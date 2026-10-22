import sys
from pathlib import Path
sys.path.insert(0, str(Path('.').resolve()))

from backend.converter_service import process_converter_chat
from Template_Converters.price_anomaly_detector import PriceAnomalyDetector
from Template_Converters.payload_builder import process_payload

test_payload = {
  "docno": "INV-2026-OUT-01",
  "docdt": "2026-10-22",
  "document_type": "INV",
  "trancatg": "B2B",
  "transactionmode": "REG",
  "self_gstin": "27ABCDE1234F1ZO",
  "supplierdt1": {
    "supplier_gstin": "27ABCDE1234F1ZO",
    "supplier_lglnm": "Apex Industrial Safety Gear Ltd",
    "supplier_bno": "Suite 401",
    "supplier_bnm": "Sterling Commercial Complex",
    "supplier_loc": "Mumbai",
    "supplier_dst": "Mumbai",
    "supplier_state": "27",
    "supplier_pin": "400001"
  },
  "buyerdt1": {
    "buyer_gstin": "29XYZAB5678C1Z2",
    "buyer_lglnm": "Karnataka Infrastructure & Mining Corp",
    "buyer_bno": "Plot 12",
    "buyer_bnm": "Electronic City Tech Park",
    "buyer_loc": "Bengaluru",
    "buyer_dst": "Bengaluru",
    "buyer_state": "29",
    "buyer_pos": "29",
    "buyer_pin": "560001"
  },
  "itemdtls": [
    {
      "prdnm": "Industrial Protective Safety Helmet",
      "prddesc": "Standard ABS industrial hard hat headgear",
      "hsncd": "65061010",
      "qty": 10.0,
      "unitprice": 85000.0,
      "uqc": "NOS",
      "assamt": 850000.0,
      "igstrt": 18.0,
      "igstamt": 153000.0,
      "totitemval": 1003000.0
    }
  ],
  "valdt1": {
    "ttlassval": 850000.0,
    "igstval": 153000.0,
    "totinvval": 1003000.0
  }
}

print("=== 1. Testing Initial Screening of HSN 65061010 ===")
builder_res = process_payload(test_payload)
errs = builder_res.get("validation_report", {}).get("errors", [])
print(f"Total NIC statutory errors: {len(errs)}")
for e in errs:
    print(f"  - Error {e.get('error_code')} ({e.get('field')}): {e.get('message')}")

hsn_errs = [e for e in errs if "65061010" in str(e) or "2176" in str(e.get("error_code"))]
print(f"False HSN 2176 errors on 65061010: {len(hsn_errs)} (Must be 0!)")
assert len(hsn_errs) == 0, f"Expected 0 false HSN errors, found {len(hsn_errs)}"

print("\n=== 2. Testing AI Price Outlier Detection ===")
p_scan = PriceAnomalyDetector.scan_invoice_payload(test_payload)
print(f"AI Price Anomaly Count: {p_scan.get('anomaly_count')}")
print(f"Has Anomalies: {p_scan.get('has_anomalies')}")
assert p_scan.get("has_anomalies") is True
assert p_scan.get("anomaly_count") >= 1

print("\n=== 3. Testing IRN Generation Block when Price Anomaly Exists ===")
irn_attempt = process_converter_chat("🚀 Generate IRN", raw_payload=test_payload, validation_report={"errors": []})
print("IRN Generation Response snippet:")
print(irn_attempt["reply"][:250])
assert "IRN Generation Blocked" in irn_attempt["reply"]
assert "AI Price Anomaly" in irn_attempt["reply"]
print("--> IRN Generation correctly BLOCKED because of Price Anomaly!")

print("\n=== 4. Testing Unit Rate / Unit / HSN Alignment ===")
# User applies new rate (e.g. 500.00) with Unit 'NOS'
update_attempt = process_converter_chat(
    "Set HSN: 65061010, Rate: 500.00, Qty: 10.0, Unit: NOS, Taxable Value: 5000.00",
    raw_payload=test_payload,
    validation_report={"errors": []}
)
updated_inv = update_attempt["updated_payload"]
item0 = updated_inv["itemdtls"][0]
print(f"Updated item HSN: {item0.get('hsncd')}")
print(f"Updated item Unit Rate: ₹{item0.get('unitprice')}")
print(f"Updated item Unit (UQC): {item0.get('uqc')}")
print(f"Updated item Taxable Value: ₹{item0.get('assamt')}")
print(f"Updated item Line Total: ₹{item0.get('totitemval')}")
print(f"Updated Invoice Total: ₹{updated_inv.get('valdt1', {}).get('totinvval')}")

assert float(item0.get("unitprice")) == 500.0
assert item0.get("uqc") == "NOS"
assert float(item0.get("assamt")) == 5000.0

print("\n=== 5. Testing Price Anomaly Count After Price Update ===")
p_scan_after = PriceAnomalyDetector.scan_invoice_payload(updated_inv)
print(f"AI Price Anomaly Count: {p_scan_after.get('anomaly_count')} (Must be 0)")
assert p_scan_after.get("anomaly_count") == 0

print("\n=== 6. Testing IRN Generation with 0 Price Anomalies and 0 Errors ===")
irn_success = process_converter_chat("🚀 Generate IRN", raw_payload=updated_inv, validation_report={"errors": []})
print("IRN Generation Response snippet:")
print(irn_success["reply"][:250])
assert "IRN Generated Successfully" in irn_success["reply"]
assert irn_success["updated_payload"].get("irn") is not None
print(f"Generated IRN: {irn_success['updated_payload'].get('irn')[:24]}...")
print("\nALL VERIFICATIONS PASSED SUCCESSFULLY!")
