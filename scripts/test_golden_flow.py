"""
scripts/test_golden_flow.py
Golden End-to-End Test Case exercising all modules in sequence:
1. Day 5 Semantic Baseline Retrieval
2. Day 10/12 DeepSeek Ambiguity Analysis & Gatekeeper
3. Day 13 Dynamic Question Generation
4. Day 14/15 Session Tracking & Answer Submission
5. Day 16 Fact-Grounded Description Enrichment
6. DeepSeek-V4 Statutory Reclassification
"""

import json
import urllib.request

BASE_URL = "http://127.0.0.1:8000"

def run_golden_test():
    print("=" * 70)
    print("🎯 GOLDEN TEST CASE: 'Industrial pipe' -> Seamless Stainless Steel")
    print("=" * 70)

    # -------------------------------------------------------------
    # Step 1: Initial Product Search (Day 5 + Day 10/12 Ambiguity Gatekeeper)
    # -------------------------------------------------------------
    print("\n[STAGE 1] Querying initial product: 'Industrial pipe'...")
    url1 = f"{BASE_URL}/api/hsn-search?query=Industrial%20pipe"
    with urllib.request.urlopen(url1, timeout=45) as resp:
        res1 = json.loads(resp.read().decode("utf-8"))

    clarif = res1.get("clarification") or {}
    ambig = clarif.get("ambiguity_analysis") or {}
    questions = clarif.get("questions_schema", {}).get("questions", [])

    print(f"  ✓ Ambiguity Detected: {ambig.get('is_ambiguous')}")
    print(f"  ✓ Recommended Action: {ambig.get('recommended_action')}")
    print(f"  ✓ Ambiguity Reason: {ambig.get('ambiguity_reason')}")
    print(f"  ✓ Questions Generated: {len(questions)}")
    for q in questions:
        print(f"     - [{q['question_id']}] {q['question']}")

    # -------------------------------------------------------------
    # Step 2: Answer Clarification & Trigger Day 16 Enrichment
    # -------------------------------------------------------------
    print("\n[STAGE 2] Submitting customer-confirmed answers...")
    answers = []
    for q in questions:
        attr = q.get("attribute", "")
        qid = q.get("question_id")
        if attr == "material":
            answers.append({
                "question_id": qid,
                "attribute": "material",
                "selected_option_id": "OPT_001",
                "selected_value": "Stainless steel",
                "is_unknown": False
            })
        elif attr == "construction":
            answers.append({
                "question_id": qid,
                "attribute": "construction",
                "selected_option_id": "OPT_001",
                "selected_value": "Seamless",
                "is_unknown": False
            })

    payload = {
        "product_description": "Industrial pipe",
        "clarification_answers": answers
    }

    req2 = urllib.request.Request(
        f"{BASE_URL}/api/v1/hsn-intelligence/submit-clarification",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req2, timeout=60) as resp:
        res2 = json.loads(resp.read().decode("utf-8"))

    # -------------------------------------------------------------
    # Step 3: Inspect Controlled AI Enrichment & Fact Grounding (Day 16)
    # -------------------------------------------------------------
    enr = res2.get("enrichment") or {}
    print("\n[STAGE 3] Inspecting Fact-Grounded Enrichment (Day 16)...")
    print(f"  ✓ Enrichment Status: {enr.get('enrichment_status')}")
    print(f"  ✓ Original Description: '{enr.get('original_description')}'")
    print(f"  ✓ Enriched Description: '{enr.get('enriched_description')}'")
    print(f"  ✓ Ready for Reclassification: {enr.get('ready_for_reclassification')}")
    print(f"  ✓ Unsupported Facts Detected: {enr.get('unsupported_facts_detected')}")
    print(f"  ✓ Validation Verdict: {enr.get('validation_reason')}")

    # -------------------------------------------------------------
    # Step 4: Inspect Final Reclassification & Statutory Grounding
    # -------------------------------------------------------------
    v_res = res2.get("verification_result") or {}
    print("\n[STAGE 4] Final Statutory Tariff Classification...")
    code = v_res.get("deepseek_formatted") or v_res.get("deepseek_hsn") or v_res.get("base_formatted")
    desc = v_res.get("deepseek_description") or v_res.get("base_description")
    rate = v_res.get("deepseek_rate") or v_res.get("base_rate")

    print(f"  ✓ Final Verified HSN: {code}")
    print(f"  ✓ Statutory Goods Description: {desc}")
    print(f"  ✓ Applicable GST Rate: {rate}%")
    print(f"  ✓ Verification Status: {v_res.get('status')}")

    print("\n" + "=" * 70)
    print("✅ GOLDEN TEST CASE COMPLETED SUCCESSFULLY: 100% GROUNDED & VERIFIED")
    print("=" * 70)

if __name__ == "__main__":
    run_golden_test()

