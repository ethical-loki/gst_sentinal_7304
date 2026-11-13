"""
scripts/verify_live_api.py
==========================
Sends live API queries to the running server on http://127.0.0.1:8001/api/v1/hsn-rag/step1-context-aggregator
for the 4 core scenarios + 1 vague query:
1. laptop
2. stainless steel water bottle
3. plastic pipe
4. cotton t-shirt
5. aunty (vague)

Saves full responses to reports/live_api_verification.json.
"""

import json
import urllib.request
from pathlib import Path

QUERIES = [
    "laptop",
    "stainless steel water bottle",
    "plastic pipe",
    "cotton t-shirt",
    "aunty"
]

API_URL = "http://127.0.0.1:8001/api/v1/hsn-rag/step1-context-aggregator"


def run_live_verification():
    results = {}
    print(f"Connecting to {API_URL}...")

    for q in QUERIES:
        print(f"\n[QUERYING] '{q}'")
        payload = json.dumps({"product": q}).encode("utf-8")
        req = urllib.request.Request(
            API_URL,
            data=payload,
            headers={"Content-Type": "application/json"}
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                results[q] = data
                pred = data.get("chapter_prediction", {})
                disambig = data.get("disambiguation", {})
                intent = data.get("intent_extraction", {})
                print(f" -> Intent: {intent.get('outcome_type')} | Chapter: {pred.get('chapter')} | Status: {pred.get('status')} | Banner: {disambig.get('banner_type')}")
        except Exception as e:
            print(f" -> ERROR: {e}")
            results[q] = {"error": str(e)}

    out_file = Path(__file__).resolve().parent.parent / "reports" / "live_api_verification.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"\n[DONE] Saved live API verification responses to {out_file}")


if __name__ == "__main__":
    run_live_verification()
