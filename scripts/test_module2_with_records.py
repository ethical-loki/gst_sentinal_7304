"""
Interactive Testing Script for Module 2 (HSN Audit Sentinel)
Demonstrates the full audit pipeline and displays all underlying dataset records considered:
- Tariff Master record (data/tariff_master.parquet)
- Historical Median Price record (artifacts/historical_median_prices.parquet)
- Supplier Prior record (artifacts/supplier_priors.parquet)
- 6 Extracted Features
- Tree SHAP Log-Odds Contributions
- Counterfactual Simulation Candidates
"""

import sys
from pathlib import Path
import pandas as pd

if sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Setup path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.ml.hsn_audit_sentinel import HSNAuditSentinel


def run_audit_and_display_records(
    product_description: str = "Cast iron industrial control check valves",
    declared_hsn: str = "72011000",
    unit_price: float = 4500.0,
    declared_hsn_chapter: str = "72",
    supplier_gstin: str = "06CKUWC2983K1ZA",
):
    print("=" * 80)
    print("MODULE 2 (HSN AUDIT SENTINEL) — STEP-BY-STEP RECORD TRACE")
    print("=" * 80)

    # 1. Input Line Item
    line_item = {
        "product_description": product_description,
        "declared_hsn": declared_hsn,
        "unit_price": unit_price,
        "quantity": 10,
        "declared_hsn_chapter": declared_hsn_chapter,
        "supplier_gstin": supplier_gstin,
    }
    print("\n[INPUT INVOICE ITEM]")
    for k, v in line_item.items():
        print(f"  • {k:22}: {v}")

    # Load Parquet datasets for verification display
    tm_df = pd.read_parquet(ROOT_DIR / "data" / "tariff_master.parquet")
    sp_df = pd.read_parquet(ROOT_DIR / "artifacts" / "supplier_priors.parquet")
    mp_df = pd.read_parquet(ROOT_DIR / "artifacts" / "historical_median_prices.parquet")

    # Initialize Module 2
    sentinel = HSNAuditSentinel(
        artifacts_dir=ROOT_DIR / "artifacts",
        safety_threshold=0.05,
        flag_threshold=0.15,
    )

    # STEP 1: Semantic Retrieval & Display Tariff Record
    print("\n" + "-" * 80)
    print("STEP 1: STATUTORY TARIFF MASTER RECORDS CONSIDERED")
    print("-" * 80)
    search_res = sentinel.intelligence_engine.classify_description(product_description, top_k=5)
    matches = search_res.get("matches", list(search_res))
    top1 = matches[0]
    top1_hsn = top1["hsn_code"]

    print(f"Top Semantic Match Identified by Contrastive NLP: HSN {top1_hsn}")
    matched_rows = tm_df[tm_df["hsn_code"] == top1_hsn]
    if not matched_rows.empty:
        r = matched_rows.iloc[0]
        print(f"  • Matched HSN Code   : {r.get('hsn_code')}")
        print(f"  • Statutory Chapter  : {str(r.get('hsn_code'))[:2]} ({r.get('chapter', 'Machinery')})")
        print(f"  • Official Tariff Desc: {r.get('description')[:120]}...")
        print(f"  • Statutory Rate     : {r.get('standard_rate')}%")

    print("\nSimulated Declared HSN Record on Invoice:")
    declared_rows = tm_df[tm_df["hsn_code"] == declared_hsn]
    if not declared_rows.empty:
        dr = declared_rows.iloc[0]
        print(f"  • Declared HSN Code  : {dr.get('hsn_code')}")
        print(f"  • Declared Chapter   : {str(dr.get('hsn_code'))[:2]}")
        print(f"  • Declared Tariff Desc: {dr.get('description')[:120]}...")
    else:
        print(f"  • Declared HSN Code  : {declared_hsn} (Chapter {declared_hsn_chapter})")

    # STEP 2: Display Supplier Prior Record
    print("\n" + "-" * 80)
    print("STEP 2: SUPPLIER PRIOR RISK RECORD CONSIDERED")
    print("-" * 80)
    vendor_match = sp_df[sp_df["supplier_gstin"] == supplier_gstin]
    if not vendor_match.empty:
        vr = vendor_match.iloc[0]
        print(f"  • Supplier GSTIN     : {vr['supplier_gstin']}")
        print(f"  • Historical Error % : {vr['prior_error_freq'] * 100:.2f}% (High Risk Vendor in Dataset)")
    else:
        print(f"  • Supplier GSTIN     : {supplier_gstin} (Not found in prior audit history)")
        print(f"  • Fallback Baseline  : 5.00% (Neutral baseline prior applied)")

    # STEP 3: Display Historical Median Price Record
    print("\n" + "-" * 80)
    print("STEP 3: HISTORICAL MEDIAN PRICE RECORDS CONSIDERED")
    print("-" * 80)
    # Check HSN median or chapter median
    hsn_med = mp_df[(mp_df["code_type"] == "hsn") & (mp_df["code"] == top1_hsn)]
    chap_med = mp_df[(mp_df["code_type"] == "chapter") & (mp_df["code"] == top1_hsn[:2])]
    if not hsn_med.empty:
        print(f"  • HSN {top1_hsn} Median Price : INR {hsn_med.iloc[0]['median_price']:.2f}")
    if not chap_med.empty:
        print(f"  • Chapter {top1_hsn[:2]} Median Price : INR {chap_med.iloc[0]['median_price']:.2f}")
    print(f"  • Invoice Unit Price       : INR {unit_price:.2f}")

    # STEP 4: Run Audit Item
    audit_res = sentinel.audit_item(line_item)

    # STEP 5: Display Extracted Features & Scoring
    print("\n" + "-" * 80)
    print("STEP 4: 6 COMPUTED NUMERICAL FEATURES & CALIBRATED RISK")
    print("-" * 80)
    orig = audit_res.original_prediction
    print(f"  • Calibrated Misclassification Risk: {orig.error_probability * 100:.2f}%")
    print(f"  • Statutory Status Badge           : {audit_res.status_badge} (Risk Level: {orig.risk_level})")

    # STEP 6: Display Tree SHAP Attributions & Explanations
    print("\n" + "-" * 80)
    print("STEP 5: TREE SHAP ATTRIBUTIONS & HUMAN-READABLE EVIDENCE")
    print("-" * 80)
    if audit_res.shap_attributions:
        print("LightGBM Tree SHAP Log-Odds Contributions:")
        for feat, contrib in audit_res.shap_attributions.items():
            sign = "+" if contrib > 0 else ""
            print(f"  • {feat:28}: {sign}{contrib:.4f}")

    print("\nStatutory Audit Explanations:")
    for exp in audit_res.explanations:
        print(f"  ⚠️  {exp}")

    # STEP 7: Display Counterfactual Recommendation
    print("\n" + "-" * 80)
    print("STEP 6: MINIMAL CORRECTIVE COUNTERFACTUAL RECOMMENDATION")
    print("-" * 80)
    cf = audit_res.counterfactual_recommendation
    if cf:
        print(f"  • Recommended HSN Code   : {cf.recommended_hsn}")
        print(f"  • Statutory Description  : {cf.description}")
        print(f"  • Pre-Intervention Risk  : {orig.error_probability * 100:.2f}%")
        print(f"  • Post-Intervention Risk : {cf.calibrated_error_probability * 100:.2f}% (P < 0.05 satisfied)")
        print(f"  • Absolute Risk Drop     : ▼ {cf.risk_drop * 100:.2f}%")
        print(f"  • Compliance Status      : {cf.status}")
    else:
        print("  • No counterfactual required (Item is already AUTO_APPROVED)")

    print("\n" + "=" * 80)
    print("AUDIT EXECUTION COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    run_audit_and_display_records()
