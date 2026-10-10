import sys
import json

sys.stdout.reconfigure(encoding='utf-8')

from backend.converter_service import process_converter_pipeline, process_converter_chat

dirty_inv = {
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
                "docno": "INV-2026-8801",
                "docdt": "2026-10-10"
            },
            "supplierdt1": {
                "supplier_gstin": "29ABCDE1234F1Z",
                "supplier_lglnm": "  ACME   GLOBAL TRADERS  ",
                "supplier_trdnm": "ACME TRADERS",
                "supplier_bno": "12",
                "supplier_bnm": "Brigade Road",
                "supplier_flno": "3rd Fl",
                "supplier_loc": "Bengaluru",
                "supplier_dst": "Bengaluru",
                "supplier_pin": "560001",
                "supplier_state": "29",
                "supplier_phone": "9876543210",
                "supplier_email": "tax@acme.com"
            },
            "buyerdt1": {
                "buyer_gstin": "27ABCDE9999F1Z5",
                "buyer_lglnm": "Apex Retailers Mumbai",
                "buyer_trdnm": "Apex Retail",
                "buyer_bno": "88",
                "buyer_bnm": "Nariman Point",
                "buyer_flno": "9th Fl",
                "buyer_loc": "Mumbai",
                "buyer_dst": "Mumbai",
                "buyer_pin": "560001",
                "buyer_state": "27",
                "pos": "27",
                "buyer_phone": "9123456780",
                "buyer_email": "finance@apex.com"
            },
            "itemdtls": [
                {
                    "itemno": "1",
                    "prdnm": "COTTON SHIRTS",
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
                "totinvval": "150000.00"
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

print("=====================================================================")
print("CASE 0: INITIAL AUDIT & AUTOMATIC VALUE NORMALIZATION")
print("=====================================================================")
init_report = process_converter_pipeline(dirty_inv)
res0 = init_report['validation_report']['results'][0]
print(f"Overall Status: {res0['status']}")
print(f"Auto-Corrections Applied ({len(res0['corrections_applied'])}):")
for c in res0['corrections_applied']:
    print(f"  ✓ [{c['field']}] '{c['original']}' -> '{c['corrected']}' ({c['description']})")

print(f"\nRemaining Compliance Errors ({len(res0['errors'])}):")
for e in res0['errors']:
    print(f"  ✗ [NIC Code {e['error_code']}] {e['field']}: {e['message']}")

print("\n=====================================================================")
print("CASE 1: AGENTIC INTERACTION - CATEGORY RESOLUTION")
print("=====================================================================")
c1 = process_converter_chat("Why did my invoice fail?", dirty_inv, init_report['validation_report'], [])
print("Copilot Asks:")
print(c1['reply'])
print("Action Chips:", c1.get('interactive_actions'))

c1_ans = process_converter_chat("Set Category: B2B", dirty_inv, init_report['validation_report'], [])
payload1 = c1_ans['updated_payload']
print("\nUser selects 'Set Category: B2B'")
print("Copilot Applied Patches:", c1_ans['patch_summary'])

print("\n=====================================================================")
print("CASE 2: SUPPLIER GSTIN & CHECKSUM VERIFICATION")
print("=====================================================================")
c2 = process_converter_chat("My GSTIN is 29ABCDE1234F1ZW", payload1, c1_ans.get('validation_report'), [])
payload2 = c2['updated_payload']
print("User sends: 'My GSTIN is 29ABCDE1234F1ZW'")
print("Copilot Result:")
print(c2['reply'])
print("Copilot Applied Patches:", c2['patch_summary'])

print("\n=====================================================================")
print("CASE 3: RECIPIENT PIN CODE & STATE ALIGNMENT")
print("=====================================================================")
c3 = process_converter_chat("Fix state and pin code mismatch", payload2, c2.get('validation_report'), [])
payload3 = c3['updated_payload']
print("User clicks: 'Fix state and pin code mismatch'")
print("Copilot Applied Patches:", c3['patch_summary'])

print("\n=====================================================================")
print("CASE 4: TAX MATH & TOTAL INVOICE VALUATION REBALANCE")
print("=====================================================================")
c4 = process_converter_chat("Rebalance tax math and invoice value", payload3, c3.get('validation_report'), [])
payload4 = c4['updated_payload']
print("User clicks: 'Rebalance tax math and invoice value'")
print("Copilot Applied Patches:", c4['patch_summary'])

print("\n=====================================================================")
print("CASE 5: FINAL LIVE NIC PIPELINE RE-AUDIT VERIFICATION")
print("=====================================================================")
final_report = process_converter_pipeline(payload4)
res_final = final_report['validation_report']['results'][0]
print(f"Final Invoice Status: {res_final['status']}")
print(f"Final Errors Count: {len(res_final['errors'])}")
if len(res_final['errors']) == 0:
    print(">>> 100% COMPLIANT & READY FOR IRP NIC PORTAL INGESTION! <<<")
else:
    for e in res_final['errors']:
        print("Remaining error:", e['field'], e['message'])
