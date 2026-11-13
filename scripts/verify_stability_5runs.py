import json
import os
import urllib.request
import time

URL = "http://127.0.0.1:8001/api/v1/hsn-rag/step1-context-aggregator"
QUERIES = ["laptop", "stainless steel water bottle", "cotton t-shirt", "aunty"]
RUNS = 5

os.makedirs("reports", exist_ok=True)
all_results = {}

print(f"Starting {RUNS}-run stability verification on {len(QUERIES)} core benchmark queries...")

for q in QUERIES:
    print(f"\n--- Testing query: '{q}' ---")
    query_runs = []
    for r in range(1, RUNS + 1):
        req_data = json.dumps({"product": q}).encode("utf-8")
        req = urllib.request.Request(URL, data=req_data, headers={"Content-Type": "application/json"})
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        latency = round((time.time() - t0) * 1000, 1)
        
        cp = data.get("chapter_prediction") or {}
        disam = data.get("disambiguation") or data.get("disambiguation_data") or {}
        rep = disam.get("descriptive_report") or {}
        
        record = {
            "run": r,
            "latency_ms": latency,
            "chapter": cp.get("chapter"),
            "status": cp.get("status"),
            "confidence": cp.get("confidence"),
            "banner_type": disam.get("banner_type"),
            "options_count": len(disam.get("disambiguation_options", [])),
            "recommended_hsn": rep.get("recommended_hsn"),
            "descriptive_report_confidence": rep.get("confidence")
        }
        query_runs.append(record)
        print(f"Run {r}: Ch={record['chapter']}, Status={record['status']}, Conf={record['confidence']}, Banner={record['banner_type']}, Options={record['options_count']}, Latency={latency}ms")
    
    # Check deterministic consistency
    chapters = {r["chapter"] for r in query_runs}
    statuses = {r["status"] for r in query_runs}
    banners = {r["banner_type"] for r in query_runs}
    is_stable = (len(chapters) == 1 and len(statuses) == 1 and len(banners) == 1)
    
    all_results[q] = {
        "is_deterministic_stable": is_stable,
        "runs": query_runs
    }

output_path = "reports/stability_5runs_verification.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(all_results, f, indent=2)

print(f"\n[DONE] Stability results successfully saved to {output_path}")
