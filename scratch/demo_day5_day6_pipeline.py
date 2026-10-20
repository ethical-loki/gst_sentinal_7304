"""
Day 05 & Day 06 End-to-End Walkthrough Demonstration Script
File: scratch/demo_day5_day6_pipeline.py

Demonstrates:
1. Day 05: Contrastive MLP Semantic Search Engine (Retrieving Top-K statutory HSN codes)
2. Day 06: LightGBM Misclassification Scorer & Platt Calibrator (Evaluating Auto-File Safety)
3. Three Real-World Cases:
   - Case 1: Clean, Compliant Stainless Steel Hardware (🟢 Safe to Auto-File)
   - Case 2: Chapter Mismatch - Industrial Servo Motor declared as Ch. 84 (🔴 Blocked / High Risk)
   - Case 3: Noisy Alphanumeric Serial Description with Extreme Outlier Price (🔴 Blocked)
"""

import sys
from pathlib import Path

# Configure utf-8 stdout for Windows consoles
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.nlp.hsn_search import HSNSemanticSearchEngine
from src.ml.misclassification_scorer import HSNMisclassificationScorer


def run_pipeline_demo():
    print("=" * 78)
    print(" 🚀 GST SENTINEL: DAY 05 & DAY 06 END-TO-END PIPELINE DEMONSTRATION")
    print("=" * 78)

    # 1. Initialize Day 05 Retrieval Engine & Day 06 Gatekeeper Scorer
    print("\n[Step 1] Initializing Production Models...")
    day5_engine = HSNSemanticSearchEngine()
    day6_scorer = HSNMisclassificationScorer()
    print("  -> Day 05 Search Engine Ready (Contrastive MLP: 32k -> 512 -> 128-D)")
    print("  -> Day 06 Safety Gatekeeper Ready (LightGBM + Platt Calibrator)")

    # 2. Define 3 Real-World Invoicing Scenarios
    test_cases = [
        {
            "name": "Case 1: Standard Compliant Stainless Steel Fitting",
            "invoice_line": {
                "product_description": "1/2 inch stainless steel hex nipple fitting",
                "unit_price": 120.0,
                "supplier_gstin": "27CLEAN1234F1Z1",
                "declared_hsn_chapter": "73",  # Chapter 73 = Articles of iron/steel
                "declared_hsn": "7307",
            },
        },
        {
            "name": "Case 2: Industrial Servo Motor with Chapter Mismatch",
            "invoice_line": {
                "product_description": "High torque servo motor for automation assembly line",
                "unit_price": 10000.0,
                "supplier_gstin": "29AAACR4849R1ZH",
                "declared_hsn_chapter": "84",  # Vendor wrongly entered Ch. 84 (Mechanical)
                "declared_hsn": "84",
            },
        },
        {
            "name": "Case 3: Noisy Serial Garbage Text & Price Outlier",
            "invoice_line": {
                "product_description": "XYZ-999-SER-SERIAL-NO-9812498214-NOISE-TEXT-UNKNOWN-ITEM",
                "unit_price": 9999999.0,      # Absurd price outlier
                "supplier_gstin": "27UNKNOWNVENDOR",
                "declared_hsn_chapter": "85",
                "declared_hsn": "85",
            },
        },
    ]

    # 3. Execute Day 05 Retrieval + Day 06 Gatekeeper for each case
    for idx, case in enumerate(test_cases, 1):
        line = case["invoice_line"]
        desc = line["product_description"]
        print("\n" + "-" * 78)
        print(f"📌 [{idx}/3] {case['name']}")
        print(f"   • Input Description : \"{desc}\"")
        print(f"   • Declared Chapter  : Chapter {line['declared_hsn_chapter']} (Entered HSN: '{line['declared_hsn']}')")
        print(f"   • Declared Price    : ₹{line['unit_price']:,.2f}")
        print(f"   • Supplier GSTIN    : {line['supplier_gstin']}")

        # DAY 05: SEMANTIC RETRIEVAL
        retrieval_output = day5_engine.search(desc, top_k=2)
        top1 = retrieval_output[0]
        top2 = retrieval_output[1] if len(retrieval_output) > 1 else None

        print("\n   🔍 [Day 05 Search Engine Output]:")
        print(f"      Top-1 Match      : HSN {top1['hsn_code']} (Chapter {top1.get('chapter', top1['hsn_code'][:2])})")
        print(f"      Description      : {top1['description'][:65]}...")
        print(f"      Similarity Score : {top1['score']:.4f} (Margin to #2: {(top1['score'] - top2['score']) if top2 else 0.0:.4f})")
        print(f"      Statutory Tax    : GST {top1.get('standard_rate', 18.0)}%")

        # DAY 06: SAFETY GATEKEEPER & CALIBRATION
        risk = day6_scorer.predict_risk(line, retrieval_output)
        error_pct = risk["error_probability"] * 100.0

        if risk["risk_level"] == "LOW" and risk["is_safe_to_autofile"]:
            status_pill = "🟢 SAFE TO AUTO-FILE"
        elif risk["risk_level"] == "MEDIUM":
            status_pill = "🟡 REVIEW RECOMMENDED"
        else:
            status_pill = "🔴 BLOCKED / HIGH RISK"

        print("\n   🛡️ [Day 06 Gatekeeper Decision]:")
        print(f"      Gatekeeper Status: {status_pill}")
        print(f"      Calibrated Risk  : {error_pct:.2f}% Misclassification Error Probability")
        print(f"      Safe to File?    : {risk['is_safe_to_autofile']}")
        print("      Audit Factors    :")
        for factor in risk["risk_factors"]:
            print(f"        • {factor}")

    print("\n" + "=" * 78)
    print(" ✅ DAY 05 & DAY 06 DEMONSTRATION RUN FINISHED SUCCESSFULLY!")
    print("=" * 78 + "\n")


if __name__ == "__main__":
    run_pipeline_demo()
