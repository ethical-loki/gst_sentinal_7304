import urllib.request
import json
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


def post_chat(msg, payload, validation_report=None):
    body = {
        "message": msg,
        "payload": payload,
        "validation_report": validation_report,
        "chat_history": []
    }
    req = urllib.request.Request(
        'http://localhost:8000/api/ingestion/chat',
        data=json.dumps(body).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode('utf-8'))

print("=== TEST 1: CHAT WITH HSN MISCLASSIFICATION SCENARIO ===")
sc1_payload = {
    "einvoices": [
        {
            "docdt1": { "docno": "INV-TEST-SCENARIO-1" },
            "supplierdt1": { "supplier_gstin": "29ABCDE1234F1Z5" },
            "buyerdt1": { "buyer_gstin": "27AAACG0561F1Z1", "pos": "27" },
            "itemdtls": [
                {
                    "itemno": 1,
                    "prdnm": "Textile Spinning Frame Part",
                    "prddesc": "Textile Ring Spinning Machine Parts",
                    "hsncd": "84451900",
                    "unitrate": 150000.0,
                    "totamt": 150000.0,
                    "assamt": 150000.0,
                    "igstamt": 27000.0,
                    "totitemval": 177000.0
                }
            ],
            "valdt1": {
                "assval": 150000.0,
                "igstval": 27000.0,
                "totinvval": 177000.0
            }
        }
    ]
}

res1 = post_chat("Why did my invoice fail?", sc1_payload)
print("Reply 1:")
print(res1.get("reply", "")[:500])
print("\nInteractive Actions 1:", res1.get("interactive_actions"))
print("Quick Prompts 1:", res1.get("quick_prompts"))

print("\n=== TEST 2: APPLY HSN RECOMMENDATION VIA CHAT ===")
res2 = post_chat("Accept & Apply Recommended HSN 84451910", sc1_payload)
print("Patch applied:", res2.get("patch_applied"))
print("Reply 2:")
print(res2.get("reply", "")[:350])
print("Updated HSN in payload:", res2.get("updated_payload", {}).get("einvoices", [{}])[0].get("itemdtls", [{}])[0].get("hsncd"))
