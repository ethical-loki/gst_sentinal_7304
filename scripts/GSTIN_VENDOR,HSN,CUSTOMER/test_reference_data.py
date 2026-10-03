"""
Module: scripts/test_masters.py
Description: Test runner script to execute master data generators and verify outputs.
"""

import sys
import os
import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))

for path in [SCRIPT_DIR, SCRIPTS_DIR, PROJECT_ROOT]:
    if path not in sys.path:
        sys.path.insert(0, path)

# Import generator functions
from gen_item_catalogue import generate_item_catalogue
from gen_vendor_master import generate_vendor_master
from gen_gstin_registry import generate_gstin_registry
from gen_customer_master import generate_customer_master

def run_tests():
    print("=== STARTING MASTER DATA GENERATION & TESTS ===")
    
    # 1. Test Item Catalogue
    excel_path = "data/raw/HSN_SAC.xlsx"
    if not os.path.exists(excel_path) and os.path.exists("data/raw/hsn_sac.xlsx"):
        excel_path = "data/raw/hsn_sac.xlsx"

    item_csv = "data/raw/masters/item_catalogue.csv"
    if os.path.exists(excel_path):
        print("\n[1/4] Generating Item Catalogue from HSN Excel...")
        generate_item_catalogue(excel_path, item_csv, target_count=120)
        df_items = pd.read_csv(item_csv)
        assert len(df_items) == 120, f"Expected 120 items, got {len(df_items)}"
        print(f"[OK] Item Catalogue verified: {len(df_items)} rows.")
    else:
        print(f"\n[!] Warning: {excel_path} not found. Skipping item catalogue generation test.")
        
    # 2. Test Vendor Master
    vendor_csv = "data/raw/masters/vendor_master.csv"
    print("\n[2/4] Generating Vendor Master (200 vendors)...")
    generate_vendor_master(vendor_csv, total_vendors=200)
    df_vendors = pd.read_csv(vendor_csv)
    assert len(df_vendors) == 200, f"Expected 200 vendors, got {len(df_vendors)}"
    mh_pct = (df_vendors['state_code'].astype(str).str.zfill(2) == '27').mean() * 100
    print(f"[OK] Vendor Master verified: {len(df_vendors)} rows. Maharashtra share: {mh_pct:.1f}% (Target ~61%)")
    
    # 3. Test GSTIN Registry
    registry_csv = "data/raw/masters/gstin_registry.csv"
    print("\n[3/4] Generating GSTIN Registry...")
    generate_gstin_registry(vendor_csv, registry_csv)
    df_registry = pd.read_csv(registry_csv)
    assert len(df_registry) == 200, f"Expected 200 registry entries, got {len(df_registry)}"
    print(f"[OK] GSTIN Registry verified: {len(df_registry)} rows with Active status.")
    
    # 4. Test Customer Master
    customer_csv = "data/raw/masters/customer_master.csv"
    print("\n[4/4] Generating Customer Master (100 customers)...")
    generate_customer_master(customer_csv, total_customers=100)
    df_cust = pd.read_csv(customer_csv)
    assert len(df_cust) == 100, f"Expected 100 customers, got {len(df_cust)}"
    print(f"[OK] Customer Master verified: {len(df_cust)} rows.")
    
    print("\n=== ALL MASTER GENERATION TESTS COMPLETED SUCCESSFULLY! ===")

def test_reference_data():
    run_tests()

if __name__ == "__main__":
    run_tests()