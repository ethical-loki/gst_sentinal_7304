import sys
sys.path.insert(0, ".")
import json
from backend.converter_service import process_converter_chat
from backend.ingestion_service import process_ingestion_chat

dirty_payload = {
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

user_msg = json.dumps(dirty_payload) + "\nwhat ever the pyalod it is having errofrs evertyhing ahs tobe prinyted right why it isnot having check this and update the bothe modules e--invcice and lake house"

print("--- 1. Testing user message with embedded payload ---")
r1 = process_converter_chat(user_msg, raw_payload=None, validation_report=None)
print("Reply lines:\n" + r1["reply"])
print("\nInteractive actions:", r1["interactive_actions"])
print("Error count in report:", r1["validation_report"]["results"][0]["error_count"])

print("\n--- 2. Testing '⚡ Auto-Fix All Compliance Errors' ---")
r2 = process_converter_chat("⚡ Auto-Fix All Compliance Errors", raw_payload=r1["updated_payload"], validation_report=r1["validation_report"])
print("Reply lines:\n" + r2["reply"])
print("Remaining errors in report:", r2["validation_report"]["results"][0]["error_count"])
print("Interactive actions:", r2["interactive_actions"])

print("\n--- 3. Testing '🚀 Generate IRN' ---")
r3 = process_converter_chat("🚀 Generate IRN", raw_payload=r2["updated_payload"], validation_report=r2["validation_report"])
print("Reply lines:\n" + r3["reply"])
print("IRN in target:", r3["updated_payload"]["einvoices"][0].get("irn"))
print("Interactive actions:", r3["interactive_actions"])

print("\n--- 4. Testing Ingestion Lakehouse Module with user message ---")
ing1 = process_ingestion_chat(user_msg, raw_payload=None, validation_report=None, sync_to_disk=False, persist_to_lakehouse=False)
print("Ingestion Reply:\n" + ing1["reply"][:300] + "...")
print("Ingestion error count:", ing1["validation_report"]["results"][0]["error_count"])

print("\nALL MODULES TEST COMPLETED SUCCESSFULLY!")
