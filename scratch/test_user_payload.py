import sys
import json

sys.stdout.reconfigure(encoding='utf-8')
from backend.converter_service import process_converter_pipeline, process_converter_chat

raw_text = """{
  "einvoices": [
    {
      "self_gstin": "27TUHCN2957U5ZN",
      "system_cd": "ORACLE",
      "branch_cd": "BR24",
      "vertical_cd": "EXPORT",
      "irnreq": "Y",
      "trandt1": {
        "trancatg": "EXP",
        "reversecharge": "N",
        "transactionmode": "REG",
        "igstonintra": "N"
      },
      "docdt1": {
        "document_type": "INV",
        "docno": "INV26317808",
        "docdt": "2026-06-15"
      },
      "supplierdt1": {
        "supplier_gstin": "27TUHCN2957U5ZN",
        "supplier_lglnm": "  PRIME   SOLUTIONS  ",
        "supplier_trdnm": "ZENITH SOLUTIONS",
        "supplier_bno": "SUITE 414",
        "supplier_bnm": "KOLKATA INDUSTRIAL PARK",
        "supplier_flno": "NAA",
        "supplier_loc": "KOLKATA",
        "supplier_dst": "KOLKATA",
        "supplier_pin": "700001",
        "supplier_state": "27",
        "supplier_phone": "9234850124",
        "supplier_email": "billing@kolkatatex.com"
      },
      "buyerdt1": {
        "buyer_gstin": "URP",
        "buyer_trdnm": "KPR MILLS LTD SEZ UNIT",
        "buyer_lglnm": "KPR MILLS LTD SEZ UNIT",
        "buyer_bno": "NAA",
        "buyer_bnm": "ROAD 12, HYDERABAD",
        "buyer_flno": "NAA",
        "buyer_loc": "HYDERABAD",
        "buyer_dst": "HYDERABAD",
        "buyer_pin": "999999",
        "buyer_state": "96",
        "pos": "96",
        "buyer_phone": "9111016158",
        "buyer_email": "accounts@hyderabadcorp.com"
      },
      "itemdtls": [
        {
          "prdnm": "STEEL-ROD",
          "prddesc": "TMT High Tensile Steel Rods",
          "isservc": "N",
          "hsncd": "720839",
          "qty": "69.906",
          "uqc": "TON",
          "unitrate": "56413.71",
          "grossamt": "3943656,81",
          "discount": "",
          "othchrg": "",
          "assamt": "3943656.81",
          "taxability": "TAX",
          "cgstrt": "0.00",
          "cgstamt": "0,00",
          "sgstrt": "0.00",
          "sgstamt": "0.00",
          "igstrt": "18.00",
          "igstamt": "709858,23",
          "cessrt": "0.00",
          "cessamt": "0.00",
          "cessnonadval": "",
          "statecessrt": "0.00",
          "statecessamt": "0.00",
          "totitemval": "4653515.04"
        }
      ],
      "valdt1": {
        "ttlassval": "3943656.81",
        "cgstval": "0.0",
        "sgstval": "0.00",
        "igstval": "709858.23",
        "cesval": "0.00",
        "stcesval": "0.00",
        "cesnonadval": "0.00",
        "discval": "",
        "totinvval": "4653515.04",
        "othchrg": "0.00"
      },
      "ewbdt1": {
        "ewayreq": "N",
        "subsupplytype": "",
        "distance_of_transport": "",
        "transporter_id": "",
        "transporter_name": "",
        "mode_of_transport": "",
        "transport_doc_no": "",
        "transporter_doc_date": "",
        "veh_type": "",
        "veh_number": ""
      },
      "trancatg": "EXP",
      "buyer_gstin": "URP",
      "pos": "96",
      "buyer_state": "96",
      "buyer_pin": "999999",
      "expdt1": {
        "cntcode": "US",
        "forcur": "USD",
        "expcat": "DIR",
        "wthpay": "Y",
        "shipbno": "SB100293",
        "shipbdt": "2026-08-01",
        "port": "INMAA1"
      },
      "transactionmode": "REG",
      "supplier_gstin": "27TUHCN2957U5ZN",
      "supplier_state": "27"
    }
  ]
}"""

payload = json.loads(raw_text)

print("--- INITIAL DIAGNOSTIC FROM COPILOT ---")
rep = process_converter_pipeline(payload)
chat = process_converter_chat('Why did my invoice fail?', payload, rep['validation_report'], [])
print(chat['reply'])
print("\nInteractive Actions:", chat.get('interactive_actions'))

print("\n--- USER SELECTS 'Set Supplier PIN: 400001' ---")
chat_res = process_converter_chat('Set Supplier PIN: 400001', payload, rep['validation_report'], [])
print("Copilot Patches:", chat_res.get('patch_summary'))
print("Copilot Reply:\n", chat_res.get('reply'))

final_rep = process_converter_pipeline(chat_res['updated_payload'])
final_res = final_rep['validation_report']['results'][0]
print(f"\nFinal Invoice Status: {final_res['status']}")
print(f"Remaining Errors: {len(final_res['errors'])}")
