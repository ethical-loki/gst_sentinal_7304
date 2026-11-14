import json
import urllib.request

queries = ["laptop", "stainless steel water bottle", "aunty"]

for q in queries:
    print(f"\n==================== TESTING: '{q}' ====================")
    req_data = json.dumps({"product": q}).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:8001/api/v1/hsn-rag/step1-context-aggregator",
        data=req_data,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            cp = data.get("chapter_prediction") or {}
            print(f"Chapter: {cp.get('chapter')}")
            print(f"Status: {cp.get('status')}")
            print(f"Confidence: {cp.get('confidence')}")
            print(f"Reason: {cp.get('reason')}")
            ev = cp.get("evidence", [])
            print(f"Evidence count: {len(ev)}")
            for item in ev[:3]:
                print(f"  - HSN {item.get('hsn_code')} (Ch {item.get('chapter')}): {item.get('description')[:50]}")
            
            disam = data.get("disambiguation_data") or {}
            print(f"Ambiguity Banner: {disam.get('banner_type')}")
            print(f"Disambiguation Options count: {len(disam.get('disambiguation_options', []))}")
            for opt in disam.get("disambiguation_options", [])[:3]:
                print(f"  - Option HSN: {opt.get('hsn_code')} | Ch: {opt.get('chapter_code')} | {opt.get('hsn_description')[:50]}")
    except Exception as e:
        print(f"Error calling endpoint: {e}")
