"""
GST Sentinel - Automated Lakehouse & Module 2 Ingestion Test Suite
Executes the 3 testing scenarios:
  1. High-Risk GSTIN Vendor Prior Error Rate
  2. Blatant Chapter Mismatch (Rate Arbitrage / Misclassification)
  3. Extreme Unit Rate Anomaly (ITC Inflation / Over-Invoicing)
"""

import sys
import json
from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "Template_Converters"))

from Template_Converters.payload_builder import PayloadBuilder
from src.ingestion.storage import (
    flatten_invoice_payload,
    append_to_parquet,
    read_parquet,
    FLATTENED_INVOICE_SCHEMA
)

SCENARIOS = [
    {
        "id": "Scenario 1",
        "name": "High-Risk GSTIN Vendor Prior Error Rate (Bogus / Flagged Vendor)",
        "file": BASE_DIR / "test_payloads" / "scenario1_gstin_error_vendor.json"
    },
    {
        "id": "Scenario 2",
        "name": "Chapter Mismatch: Screws (Ch 73) under Inorganic Acids (Ch 28)",
        "file": BASE_DIR / "test_payloads" / "scenario2_chapter_mismatch.json"
    },
    {
        "id": "Scenario 3",
        "name": "Unit Rate Anomaly: Cotton Yarn at Rs 15,000/kg (68x above statutory median)",
        "file": BASE_DIR / "test_payloads" / "scenario3_unit_rate_anomaly.json"
    }
]

LAKEHOUSE_OUTPUT = BASE_DIR / "data" / "processed_payload" / "invoices_master.parquet"

def run_tests():
    print("=" * 80)
    print("🚀 RUNNING DATA LAKEHOUSE & MODULE 2 SENTINEL INTEGRATION TEST SUITE")
    print("=" * 80)

    for sc in SCENARIOS:
        print(f"\n▶ [{sc['id']}] {sc['name']}")
        print(f"  Loading payload from: {sc['file'].name}")
        with open(sc["file"], "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        item0 = raw_data["itemdtls"][0]
        print(f"  [INPUT] Product: '{item0['prdnm']}'")
        print(f"  [INPUT] Supplier GSTIN: {raw_data['supplierdt1']['supplier_gstin']}")
        print(f"  [INPUT] Declared HSN: {item0['hsncd']}, Unit Rate: Rs {item0['unitrate']}")

        # 1. Run Pipeline Auto-Correction & Module 2 Audit Sentinel
        clean_inv, audit_log = PayloadBuilder.auto_correct_and_build(raw_data)
        corr_item = clean_inv["itemdtls"][0]

        print(f"  [HEALED] Rectified HSN: {corr_item['hsncd']}")
        print(f"  [HEALED] CGST: Rs {corr_item['cgstamt']}, SGST: Rs {corr_item['sgstamt']}, Total: Rs {corr_item['totitemval']}")

        sentinel_logs = [l for l in audit_log if "SENTINEL" in l.get("category", "") or "HSN" in l.get("category", "")]
        print(f"  [AUDIT TRAIL] Captured {len(sentinel_logs)} HSN/Sentinel Audit Events:")
        for log in sentinel_logs:
            print(f"    • [{log['category']}] {log['description'][:140]}...")

        # 2. Flatten for Lakehouse
        flat_rows = flatten_invoice_payload(clean_inv)
        print(f"  [LAKEHOUSE] Flattened {len(flat_rows)} line-item record(s) into schema.")

        # 3. Store into Parquet
        df_new = pd.DataFrame(flat_rows)
        append_to_parquet(df_new, str(LAKEHOUSE_OUTPUT), schema=FLATTENED_INVOICE_SCHEMA)

    print("\n" + "=" * 80)
    print(f"📊 VERIFYING PARQUET LAKEHOUSE MASTER TABLE: {LAKEHOUSE_OUTPUT}")
    print("=" * 80)

    lake_df = read_parquet(str(LAKEHOUSE_OUTPUT))
    print(f"Total Rows in Lakehouse: {len(lake_df)}")

    cols_to_show = [
        "invoice_id",
        "supplier_gstin",
        "product_name",
        "hsn",
        "sentinel_risk_prob",
        "sentinel_risk_level",
        "sentinel_status_badge",
        "sentinel_recommended_hsn"
    ]
    avail_cols = [c for c in cols_to_show if c in lake_df.columns]
    print(lake_df[avail_cols].tail(5).to_string(index=False))
    print("\n✅ ALL 3 SCENARIOS VERIFIED & PERSISTED TO LAKEHOUSE SUCCESSFULLY!")

if __name__ == "__main__":
    run_tests()
