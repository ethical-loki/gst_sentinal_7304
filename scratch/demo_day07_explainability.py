"""
Day 07 End-to-End Walkthrough Demonstration Script
File: scratch/demo_day07_explainability.py

Demonstrates:
1. Native LightGBM Tree SHAP attribution extraction.
2. Natural language compliance evidence generation.
3. Counterfactual simulation finding minimal corrective intervention P(Error | h*) < 0.05.
4. Strict read-only invoice immutability.
5. Frontend-ready JSON payload for Streamlit/React review screens.
"""

import copy
import json
import pprint
import sys
from pathlib import Path

# Configure utf-8 stdout for Windows consoles
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.ml.audit_advisor import HSNAuditAdvisor


def run_demo():
    print("=" * 80)
    print(" 🚀 GST SENTINEL: DAY 07 EXPLAINABILITY & COUNTERFACTUAL ENGINE DEMO")
    print("=" * 80)

    advisor = HSNAuditAdvisor()
    print("\n[Step 1] HSNAuditAdvisor Loaded Successfully.")

    # High-Risk Real-World Case
    sample_invoice_item = {
        "product_description": "Industrial stainless steel flow control valves with pneumatic actuator",
        "unit_price": 18500.0,
        "declared_hsn": "73072900",       # Wrongly declared under Chapter 73 (Iron/Steel fittings)
        "declared_hsn_chapter": "73",
        "supplier_gstin": "27AABCS1234F1Z5",
    }

    # Snapshot to verify immutability
    snapshot_before = copy.deepcopy(sample_invoice_item)

    print("\n[Step 2] Auditing High-Risk Misclassified Invoice Item:")
    print(f"  • Description     : {sample_invoice_item['product_description']}")
    print(f"  • Declared HSN    : {sample_invoice_item['declared_hsn']} (Chapter {sample_invoice_item['declared_hsn_chapter']})")
    print(f"  • Declared Price  : ₹{sample_invoice_item['unit_price']:,.2f}")
    print(f"  • Supplier GSTIN  : {sample_invoice_item['supplier_gstin']}")

    audit_result = advisor.review_line_item(sample_invoice_item)

    # Immutability assertion
    assert sample_invoice_item == snapshot_before, "Invoice record was mutated!"

    payload = audit_result.model_dump()

    print("\n[Step 3] Audit Evaluation Output:")
    print(f"  • Status Badge    : {payload['status_badge']}")
    print(f"  • Baseline Risk   : P(Error) = {payload['original_prediction']['error_probability']:.1%} [{payload['original_prediction']['risk_level']}]")

    print("\n  📋 Deconstructed Tree SHAP Evidence:")
    for reason in payload["human_readable_reasons"]:
        print(f"     ▸ {reason}")

    rec = payload["counterfactual_recommendation"]
    if rec:
        print("\n  💡 Minimal Corrective Counterfactual Recommendation:")
        print(f"     ▸ Recommended HSN     : {rec['recommended_hsn']}")
        print(f"     ▸ Tariff Description   : {rec['description']}")
        print(f"     ▸ Calibrated Risk Drop : {rec['risk_drop'] * 100:.1f}% (Post-Intervention Risk: {rec['calibrated_error_probability'] * 100:.1f}%)")
        print(f"     ▸ Status               : {rec['status']}")

    action = payload["suggested_action"]
    if action:
        print("\n  ⚡ One-Click Auditor Action:")
        print(f"     ▸ Action Type : {action['action_type']}")
        print(f"     ▸ Guidance    : {action['explanation']}")

    print("\n" + "=" * 80)
    print("  ✅ DAY 07 DEMONSTRATION COMPLETE - STRICT READ-ONLY INVARIANT PRESERVED")
    print("=" * 80)


if __name__ == "__main__":
    run_demo()
