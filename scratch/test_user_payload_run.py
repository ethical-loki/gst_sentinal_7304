import sys
sys.path.insert(0, ".")
from backend.converter_service import process_converter_pipeline
from backend.ingestion_service import process_ingestion_pipeline

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

print("=== CONVERTER PIPELINE ===")
res1 = process_converter_pipeline(payload, sync_to_disk=False)
rep1 = res1["validation_report"]
print("Total:", rep1.get("total_invoices"), "Valid:", rep1.get("valid_invoices"), "Failed:", rep1.get("failed_invoices"))
for r in rep1.get("results", []):
    print("Status:", r.get("status"), "Error count:", r.get("error_count"))
    for e in r.get("errors", []):
        print("  Error:", e.get("error_code"), e.get("field"), e.get("message"))
    for c in r.get("corrections_applied", []):
        print("  Correction:", c.get("category"), c.get("field"), c.get("original"), "->", c.get("corrected"))

print("\n=== INGESTION PIPELINE ===")
res2 = process_ingestion_pipeline(payload, sync_to_disk=False, persist_to_lakehouse=False)
rep2 = res2["validation_report"]
print("Total:", rep2.get("total_invoices"), "Valid:", rep2.get("valid_invoices"), "Failed:", rep2.get("failed_invoices"))
for r in rep2.get("results", []):
    print("Status:", r.get("status"), "Error count:", r.get("error_count"))
    for e in r.get("errors", []):
        print("  Error:", e.get("error_code"), e.get("field"), e.get("message"))
