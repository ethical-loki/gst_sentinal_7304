import urllib.request
import json

payload = {
  "einvoices": [
    {
      "self_gstin": "29ABCDE1234F1Z",
      "system_cd": "SAP_ERP",
      "branch_cd": "BLR01",
      "vertical_cd": "DOM",
      "irnreq": "Y",
      "trandt1": {
        "trancatg": "B2B",
        "reversecharge": "N",
        "transactionmode": "REGULAR_TRANSIT",
        "igstonintra": "N"
      },
      "docdt1": {
        "document_type": "INV",
        "docno": "INV-2026-B2B01",
        "docdt": "2026-10-10"
      },
      "supplierdt1": {
        "supplier_gstin": "29ABCDE1234F1Z",
        "supplier_lglnm": "  BHARAT   TECH SOLUTIONS PVT LTD  ",
        "supplier_trdnm": "BHARAT TECH",
        "supplier_bno": "104",
        "supplier_bnm": "Cyber Towers",
        "supplier_flno": "4th Floor",
        "supplier_loc": "Bengaluru",
        "supplier_dst": "Bengaluru",
        "supplier_pin": "400001",
        "supplier_state": "29",
        "supplier_phone": "9876543210",
        "supplier_email": "accounts@bharattech.in"
      },
      "buyerdt1": {
        "buyer_gstin": "URP",
        "buyer_lglnm": "APEX COMMERCE ENTERPRISES",
        "buyer_trdnm": "APEX COMMERCE",
        "buyer_pos": "29",
        "buyer_bno": "55",
        "buyer_bnm": "MG Road Commercial Plaza",
        "buyer_loc": "Bengaluru",
        "buyer_dst": "Bengaluru",
        "buyer_pin": "560001",
        "buyer_state": "29"
      },
      "itemdtls": [
        {
          "slno": "1",
          "prdnm": "Industrial Servo Motor",
          "prddesc": "High torque servo motor for automation assembly line",
          "is_service": "N",
          "hsn": "84",
          "qty": 5,
          "unit": "NOS",
          "unitprice": 10000.0,
          "totamt": 50000.0,
          "discount": 0.0,
          "pretaxval": 50000.0,
          "assval": 50000.0,
          "gstrate": 18.0,
          "igstval": 0.0,
          "cgstval": 4500.0,
          "sgstval": 4500.0,
          "cesrate": 0.0,
          "cesval": 0.0,
          "cesnonadvl": 0.0,
          "statecesrate": 0.0,
          "statecesval": 0.0,
          "statecesnonadvl": 0.0,
          "othchrg": 0.0,
          "totitemval": 59000.0
        }
      ],
      "valdtls": {
        "assval": 50000.0,
        "cgstval": 4500.0,
        "sgstval": 4500.0,
        "igstval": 0.0,
        "cesval": 0.0,
        "stcesval": 0.0,
        "discount": 0.0,
        "othchrg": 0.0,
        "rndoffamt": 0.0,
        "totinvval": 99999.0
      },
      "ewbdt1": {
        "ewayreq": "Y",
        "subsupplytype": "1",
        "transmode": "1",
        "distance": "120",
        "transporter_id": "",
        "transporter_name": "FastTrack Logistics",
        "transdocno": "LR-998822",
        "transdocdt": "2026-10-10",
        "veh_number": "",
        "veh_type": "R"
      }
    }
  ]
}

def call_api(endpoint, data):
    req = urllib.request.Request(
        f"http://127.0.0.1:8001{endpoint}",
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

print("=== 1. Calling Pipeline Transformation on User Payload ===")
pipe_res = call_api("/api/converter/process", {"payload": payload})
print("Pipeline status:", pipe_res.get("status"))
inv0 = pipe_res["corrected_payload"]["einvoices"][0]
print("Transformed Supplier GSTIN:", inv0.get("supplierdt1", {}).get("supplier_gstin"))
print("Transformed HSN:", inv0.get("itemdtls", [{}])[0].get("hsn_code"))
print("Transformed Total:", inv0.get("valdtls", {}).get("totinvval"))
print("Validation failed_invoices:", pipe_res["validation_report"]["failed_invoices"])

print("\n=== 2. Testing Chat Copilot with User Typing 'My GSTIN is 29ABCDE1234F1Z5' ===")
chat_res = call_api("/api/converter/chat", {
    "message": "My GSTIN is 29ABCDE1234F1Z5",
    "payload": payload,
    "validation_report": pipe_res["validation_report"],
    "chat_history": []
})
print("Chat status:", chat_res.get("status"))
print("Patch applied:", chat_res.get("patch_applied"))
print("Patch summary:", chat_res.get("patch_summary"))
inv_chat = chat_res["updated_payload"]["einvoices"][0]
print("Updated Supplier GSTIN in payload:", inv_chat.get("supplier_gstin") or inv_chat.get("self_gstin"))
print("Updated supplierdt1 GSTIN:", inv_chat.get("supplierdt1", {}).get("supplier_gstin"))
assert inv_chat.get("supplierdt1", {}).get("supplier_gstin") == "29ABCDE1234F1ZW"
print(">>> Verified: User typing 29ABCDE1234F1Z5 is auto-rectified and applied to 29ABCDE1234F1ZW!")

print("\n=== 3. Testing Chat Copilot with 'Set HSN: 85011013' ===")
chat_hsn = call_api("/api/converter/chat", {
    "message": "Set HSN: 85011013",
    "payload": chat_res["updated_payload"],
    "validation_report": chat_res.get("validation_report"),
    "chat_history": []
})
print("HSN Patch applied:", chat_hsn.get("patch_applied"))
item = chat_hsn["updated_payload"]["einvoices"][0]["itemdtls"][0]
print("Updated item keys: hsn =", item.get("hsn"), ", hsn_code =", item.get("hsn_code"), ", hsncd =", item.get("hsncd"))
assert item.get("hsn") == "85011013"
print(">>> Verified: HSN code 85011013 is updated in itemdtls!")

print("\n=== 4. Testing Chat Copilot with 'Change date to Today (2026-10-20)' ===")
chat_date = call_api("/api/converter/chat", {
    "message": "Change date to Today (2026-10-20)",
    "payload": chat_hsn["updated_payload"],
    "validation_report": chat_hsn.get("validation_report"),
    "chat_history": []
})
print("Date Patch applied:", chat_date.get("patch_applied"))
docdt = chat_date["updated_payload"]["einvoices"][0]["docdt1"]["docdt"]
print("Updated docdt:", docdt)
assert docdt == "2026-10-20"
print(">>> Verified: Document Date is updated to 2026-10-20!")

print("\n=== 5. Testing Chat Copilot with 'Set Supplier PIN: 560001' ===")
chat_pin = call_api("/api/converter/chat", {
    "message": "Set Supplier PIN: 560001",
    "payload": chat_date["updated_payload"],
    "validation_report": chat_date.get("validation_report"),
    "chat_history": []
})
print("PIN Patch applied:", chat_pin.get("patch_applied"))
pin = chat_pin["updated_payload"]["einvoices"][0]["supplierdt1"]["supplier_pin"]
print("Updated supplier_pin:", pin)
assert pin == "560001"
print(">>> Verified: Supplier PIN is updated to 560001!")

print("\n=== ALL LIVE HTTP ENDPOINTS PASSED WITH USER PAYLOAD! ===")
