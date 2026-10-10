import sys
import json

sys.stdout.reconfigure(encoding='utf-8')
from backend.converter_service import process_converter_pipeline

test_payload = {
  "einvoices": [
    {
      "self_gstin": "29ABCDE1234F1Z",
      "system_cd": "SAP_ERP",
      "branch_cd": "BLR01",
      "vertical_cd": "DOM",
      "irnreq": "Y",
      "trandt1": {
        "trancatg": "EX",
        "reversecharge": "N",
        "transactionmode": "REG",
        "igstonintra": "N"
      },
      "docdt1": {
        "document_type": "INV",
        "docno": "INV-2026-9901",
        "docdt": "2026-10-10"
      },
      "supplierdt1": {
        "supplier_gstin": "29ABCDE1234F1Z",
        "supplier_lglnm": "  ACME   GLOBAL TRADERS PVT LTD  ",
        "supplier_trdnm": "ACME TRADERS",
        "supplier_bno": "12",
        "supplier_bnm": "Brigade Road",
        "supplier_flno": "3rd Fl",
        "supplier_loc": "Bengaluru",
        "supplier_dst": "Bengaluru",
        "supplier_pin": "560001",
        "supplier_state": "29",
        "supplier_phone": "9876543210",
        "supplier_email": "billing@acmetraders.com"
      },
      "buyerdt1": {
        "buyer_gstin": "27ABCDE9999F1Z5",
        "buyer_lglnm": "Apex Retailers Mumbai",
        "buyer_trdnm": "Apex Superstores",
        "buyer_bno": "88",
        "buyer_bnm": "Nariman Point",
        "buyer_flno": "9th Fl",
        "buyer_loc": "Mumbai",
        "buyer_dst": "Mumbai",
        "buyer_pin": "560001",
        "buyer_state": "27",
        "pos": "27",
        "buyer_phone": "9123456780",
        "buyer_email": "finance@apexretail.com"
      },
      "itemdtls": [
        {
          "itemno": "1",
          "prdnm": "Cotton Shirts Men",
          "prddesc": "Men Casual Cotton Shirt",
          "isservc": "N",
          "hsncd": "610510",
          "qty": "100.000",
          "uqc": "NOS",
          "unitrate": "1000.00",
          "grossamt": "100000,00",
          "discount": "0.00",
          "othchrg": "0.00",
          "assamt": "100000.00",
          "taxability": "TAX",
          "cgstrt": "0.00",
          "cgstamt": "0.00",
          "sgstrt": "0.00",
          "sgstamt": "0.00",
          "igstrt": "18.00",
          "igstamt": "18000,00",
          "cessrt": "0.00",
          "cessamt": "0.00",
          "statecessrt": "0.00",
          "statecessamt": "0.00",
          "totitemval": "118000,00"
        }
      ],
      "valdtls1": {
        "assval": "100000.00",
        "cgstval": "0.00",
        "sgstval": "0.00",
        "igstval": "18000.00",
        "cessval": "0.00",
        "stcessval": "0.00",
        "discount": "0.00",
        "othchrg": "0.00",
        "rndoffamt": "0.00",
        "totinvval": "999999.00"
      },
      "ewaydtls1": {
        "ewayreq": "Y",
        "transporter_id": "27ABCDE9999F1Z5",
        "transporter_name": "VRL Logistics",
        "trans_doc_no": "LR-998822",
        "trans_doc_dt": "10-10-2026",
        "mode_of_transport": "1",
        "dist": "980",
        "veh_number": "KA 01 AB 1234",
        "veh_type": "R"
      }
    }
  ]
}

res = process_converter_pipeline(test_payload)
r = res['validation_report']['results'][0]
print(f"Status: {r['status']}")
print(f"Auto-Corrections Count: {len(r['corrections_applied'])}")
print(f"Compliance Errors Count: {len(r['errors'])}")
for err in r['errors']:
    print(f"  * [Code {err['error_code']}] {err['field']}: {err['message']}")
