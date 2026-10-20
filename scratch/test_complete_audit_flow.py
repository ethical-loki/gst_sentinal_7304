import sys
sys.path.insert(0, ".")
import json
from backend.converter_service import (
    process_converter_pipeline,
    calculate_gstin_checksum,
    STATE_MASTER,
    match_and_patch_product_hsns
)

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

pipe = process_converter_pipeline(payload, sync_to_disk=False)
res = pipe["validation_report"]["results"][0]
print(f"Total Errors Found: {res['error_count']}")
for e in res["errors"]:
    print(f" - Error {e['error_code']} ({e['field']}): {e['message']}")
