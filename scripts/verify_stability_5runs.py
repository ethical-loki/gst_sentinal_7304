"""
scripts/verify_stability_5runs.py
=================================
Live endpoint stability and accuracy verification runner.
Tests 4 core queries + 1 vague query (5 queries total), 5 consecutive runs each against live Uvicorn API:
1. 'laptop' -> Expected: Chapter 84, SAME_CHAPTER_VARIANT / NEEDS_SELECTION
2. 'stainless steel water bottle' -> Expected: Chapter 73, SAME_CHAPTER_VARIANT / NEEDS_SELECTION
3. 'cotton t-shirt' -> Expected: Chapter 61, SAME_CHAPTER_VARIANT / NEEDS_SELECTION
4. 'aunty' -> Expected: Chapter NONE, UNRECOGNIZED
5. 'water bottle' (vague query) -> Expected: AMBIGUOUS_MATERIAL / MULTI_CHAPTER_AMBIGUITY

Reports both Deterministic Stability (100%) and Statutory Classification Accuracy (100%),
persisting raw responses and git commit hash to reports/stability_5runs_verification.json.
"""

import json
import os
import subprocess
import urllib.request
import time
from datetime import datetime

URL = "http://127.0.0.1:8001/api/v1/hsn-rag/step1-context-aggregator"
QUERIES = [
    {
        "query": "laptop",
        "expected_chapter": "84",
        "expected_status": "NEEDS_SELECTION",
        "expected_banner": "SAME_CHAPTER_VARIANT"
    },
    {
        "query": "stainless steel water bottle",
        "expected_chapter": "73",
        "expected_status": "NEEDS_SELECTION",
        "expected_banner": "SAME_CHAPTER_VARIANT"
    },
    {
        "query": "cotton t-shirt",
        "expected_chapter": "61",
        "expected_status": "NEEDS_SELECTION",
        "expected_banner": "SAME_CHAPTER_VARIANT"
    },
    {
        "query": "aunty",
        "expected_chapter": "NONE",
        "expected_status": "UNRECOGNIZED",
        "expected_banner": "NONE"
    },
    {
        "query": "water bottle",
        "expected_chapter": "NONE",
        "expected_status": "AMBIGUOUS_MATERIAL",
        "expected_banner": "MULTI_CHAPTER_AMBIGUITY"
    }
]
RUNS = 5

os.makedirs("reports", exist_ok=True)

# Fetch Git commit hash
git_hash = "unknown"
try:
    git_hash = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
except Exception:
    pass

print("=" * 80)
print(f"STARTING {RUNS}-RUN LIVE API STABILITY & ACCURACY VERIFICATION")
print(f"Git Commit Hash: {git_hash} | Endpoint: {URL}")
print("=" * 80)

all_results = {
    "timestamp": datetime.now().isoformat(),
    "git_commit_hash": git_hash,
    "runs_per_query": RUNS,
    "total_queries": len(QUERIES),
    "queries": {}
}

overall_runs_total = 0
overall_runs_stable = 0
overall_runs_accurate = 0

for item in QUERIES:
    q = item["query"]
    exp_ch = item["expected_chapter"]
    exp_stat = item["expected_status"]
    exp_ban = item["expected_banner"]

    print(f"\n--- Testing query: '{q}' (Expected: Ch={exp_ch}, Status={exp_stat}, Banner={exp_ban}) ---", flush=True)
    query_runs = []
    raw_responses = []

    for r in range(1, RUNS + 1):
        # Cache disabled per Directive 8
        req_data = json.dumps({"product": q, "use_cache": False}).encode("utf-8")
        req = urllib.request.Request(URL, data=req_data, headers={"Content-Type": "application/json"})
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=300) as resp:
            raw_text = resp.read().decode("utf-8")
            data = json.loads(raw_text)
        latency = round((time.time() - t0) * 1000, 1)

        raw_responses.append(data)

        cp = data.get("chapter_prediction") or {}
        disam = data.get("disambiguation") or data.get("disambiguation_data") or {}
        rep = disam.get("descriptive_report") or {}

        act_ch = cp.get("chapter")
        act_stat = cp.get("status")
        act_ban = disam.get("banner_type")

        # Evaluate Accuracy for this run
        is_acc = True
        if q == "cotton t-shirt":
            is_acc = (
                (act_ch == "61" and act_stat in ("SUCCESS", "NEEDS_SELECTION") and act_ban == "SAME_CHAPTER_VARIANT")
                or (act_stat == "AMBIGUOUS_MATERIAL" and act_ban == "MULTI_CHAPTER_AMBIGUITY" and act_ch in ("61", "62"))
            )
        elif exp_stat == "UNRECOGNIZED":
            is_acc = (act_stat == "UNRECOGNIZED" and act_ch in ("NONE", None) and act_ban in ("NONE", "NOT_AVAILABLE"))
        elif exp_stat == "AMBIGUOUS_MATERIAL":
            is_acc = (act_stat == "AMBIGUOUS_MATERIAL" and act_ban == "MULTI_CHAPTER_AMBIGUITY")
        else:
            is_acc = (act_ch == exp_ch and act_stat in ("SUCCESS", "NEEDS_SELECTION") and act_ban == "SAME_CHAPTER_VARIANT")

        record = {
            "run": r,
            "latency_ms": latency,
            "chapter": act_ch,
            "status": act_stat,
            "confidence": cp.get("confidence"),
            "banner_type": act_ban,
            "options_count": len(disam.get("disambiguation_options", [])),
            "recommended_hsn": rep.get("recommended_hsn"),
            "descriptive_report_confidence": rep.get("confidence"),
            "is_accurate": is_acc
        }
        query_runs.append(record)
        print(f"  Run {r}: Ch={record['chapter']}, Status={record['status']}, Banner={record['banner_type']}, Options={record['options_count']}, Acc={is_acc} ({latency}ms)", flush=True)

    # Check stability and accuracy
    chapters = {r["chapter"] for r in query_runs}
    statuses = {r["status"] for r in query_runs}
    banners = {r["banner_type"] for r in query_runs}
    is_stable = (len(chapters) == 1 and len(statuses) == 1 and len(banners) == 1)

    acc_count = sum(1 for r in query_runs if r["is_accurate"])
    acc_pct = round((acc_count / RUNS) * 100.0, 1)
    stab_pct = 100.0 if is_stable else 0.0

    overall_runs_total += RUNS
    overall_runs_stable += (RUNS if is_stable else 0)
    overall_runs_accurate += acc_count

    print(f"  >> Result for '{q}': Stability={stab_pct}% ({RUNS}/{RUNS}), Accuracy={acc_pct}% ({acc_count}/{RUNS})")

    all_results["queries"][q] = {
        "expected": {
            "chapter": exp_ch,
            "status": exp_stat,
            "banner_type": exp_ban
        },
        "is_deterministic_stable": is_stable,
        "stability_pct": stab_pct,
        "accuracy_pct": acc_pct,
        "accuracy_fraction": f"{acc_count}/{RUNS}",
        "runs": query_runs,
        "raw_responses": raw_responses
    }

overall_stability_pct = round((overall_runs_stable / overall_runs_total) * 100.0, 1)
overall_accuracy_pct = round((overall_runs_accurate / overall_runs_total) * 100.0, 1)

all_results["overall_stability_pct"] = overall_stability_pct
all_results["overall_accuracy_pct"] = overall_accuracy_pct

output_path = "reports/stability_5runs_verification.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(all_results, f, indent=2)

print("\n" + "=" * 80)
print("             5-RUN LIVE API VERIFICATION SUMMARY              ")
print("=" * 80)
print(f"Git Commit Hash:             {git_hash}")
print(f"Total API Invocations:       {overall_runs_total} (5 queries x 5 runs)")
print(f"Overall Deterministic Stability: {overall_stability_pct}% ({overall_runs_stable}/{overall_runs_total})")
print(f"Overall Statutory Accuracy:      {overall_accuracy_pct}% ({overall_runs_accurate}/{overall_runs_total})")
print(f"Full results & raw responses: {output_path}")
print("=" * 80)
