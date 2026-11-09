import urllib.parse
import urllib.request
import json
import time
import sys

BASE_URL = 'http://127.0.0.1:8000'

test_cases = [
    {
        'category': 'Industrial Pressure Piping',
        'query': 'Forged Carbon Steel Welded Flange Class 300 2 inch',
        'lang': 'en'
    },
    {
        'category': 'Mechanical Power Transmission (Hindi Script)',
        'query': 'हेलिकल रिडक्शन गियर बॉक्स 1400 rpm अनुपात 15:1',
        'lang': 'hi'
    },
    {
        'category': 'Renewable Power Equipment (Hinglish)',
        'query': 'Solar on-grid inverter 5kW 3 phase supply ke liye',
        'lang': 'hi-Latn'
    }
]

print("==================== LIVE UI / API DEMO & TEST ====================")

for tc in test_cases:
    query = tc['query']
    lang = tc['lang']
    cat = tc['category']
    print(f"\n>>> TEST CASE: [{cat}]")
    print(f"Query: \"{query}\" (Language Mode: {lang})")
    
    # 1. LAYER 1: Dynamic Prediction Algorithm
    t0 = time.perf_counter()
    search_url = f"{BASE_URL}/api/v1/hsn-intelligence/search?query=" + urllib.parse.quote(query) + f"&lang={lang}&top_k=3"
    req = urllib.request.Request(search_url)
    with urllib.request.urlopen(req) as resp:
        search_res = json.loads(resp.read().decode('utf-8'))
    t_l1 = (time.perf_counter() - t0) * 1000
    
    matches = search_res.get('matches', [])
    top_m = matches[0] if matches else {}
    pred_hsn = top_m.get('hsn_code', 'N/A')
    pred_desc = top_m.get('description', 'N/A')
    pred_conf = top_m.get('confidence', 0.0)
    match_type = top_m.get('match_type', 'Algorithm')
    
    print(f"--- [LAYER 1: DYNAMIC PREDICTION ALGORITHM] ({t_l1:.2f} ms) ---")
    print(f"Match Source: {match_type}")
    print(f"Top Candidate HSN: {pred_hsn} | Confidence: {pred_conf:.4f}")
    print(f"Candidate Description: {pred_desc[:75]}...")
    
    # 2. LAYER 2: Qwen Verification Layer
    t0 = time.perf_counter()
    verify_url = f"{BASE_URL}/api/v1/hsn-intelligence/qwen-verify?query=" + urllib.parse.quote(query) + f"&base_hsn={pred_hsn}&base_rate=18.0&lang={lang}"
    req = urllib.request.Request(verify_url)
    with urllib.request.urlopen(req) as resp:
        verify_res = json.loads(resp.read().decode('utf-8'))
    t_l2 = (time.perf_counter() - t0) * 1000
    
    status = verify_res.get('status')
    ver_hsn = verify_res.get('verified_hsn')
    ver_rate = verify_res.get('verified_gst_rate')
    reason = verify_res.get('reasoning', '')
    
    print(f"--- [LAYER 2: QWEN VERIFICATION LAYER] ({t_l2:.2f} ms) ---")
    print(f"Verification Status: {status}")
    print(f"Verified Statutory HSN: {ver_hsn} (GST Rate: {ver_rate}%)")
    print(f"Statutory Rationale: {reason[:120]}...")
    
    # 3. VERIFY PERSISTENT REUSE (Step 0 Cache)
    t0 = time.perf_counter()
    req = urllib.request.Request(search_url)
    with urllib.request.urlopen(req) as resp:
        repeat_res = json.loads(resp.read().decode('utf-8'))
    t_cache = (time.perf_counter() - t0) * 1000
    repeat_top = repeat_res.get('matches', [])[0] if repeat_res.get('matches') else {}
    print(f"--- [STEP 0: PERSISTENT CACHE REUSE] ({t_cache:.2f} ms) ---")
    print(f"Source: {repeat_top.get('match_type')} | Stored HSN: {repeat_top.get('hsn_code')}")

