"""
Module: scripts/gen_gstin_registry.py
Description: Generates the gstin_registry.csv dataset covering all vendors from vendor_master.csv
with Active status, filing behavior profiles (~85% on-time, ~10% late, ~5% QRMP), and registry verification flags.
"""

import os
import random
import pandas as pd

def generate_gstin_registry(vendor_csv_path: str, output_csv_path: str):
    """
    Reads vendor_master.csv and builds the corresponding gstin_registry.csv file
    with filing behaviors and active registration status.
    """
    if not os.path.exists(vendor_csv_path):
        raise FileNotFoundError(f"Vendor master not found at {vendor_csv_path}. Please generate it first.")
        
    print(f"Loading vendors from {vendor_csv_path}...")
    df_vendors = pd.read_csv(vendor_csv_path)
    
    registry_rows = []
    
    # Filing behavior distribution: ~85% on-time, ~10% late within next month, ~5% QRMP quarterly
    filing_behaviors = ["ON_TIME"] * 85 + ["LATE_MONTHLY"] * 10 + ["QRMP"] * 5
    
    for _, row in df_vendors.iterrows():
        gstin = row.get('vendor_gstin', row.get('gstin', ''))
        vendor_name = row.get('vendor_name', row.get('trade_name', row.get('legal_name', '')))
        vendor_type = row.get('registration_type', row.get('vendor_type', 'REGULAR'))
        reg_date = row.get('registration_date', '2023-04-01')
        
        # Assign filing behavior profile
        behavior = random.choice(filing_behaviors)
        
        # Composition vendors typically follow QRMP or quarterly patterns, regular follow monthly
        if str(vendor_type).upper() == "COMPOSITION":
            behavior = "QRMP"
            
        registry_rows.append({
            "vendor_gstin": gstin,
            "legal_name": vendor_name,
            "trade_name": vendor_name,
            "registration_status": "Active",  # GN-19
            "registration_date": reg_date,  # GN-20
            "registry_exists": True,  # GN-21
            "taxpayer_type": vendor_type,  # GN-22
            "filing_behavior": behavior,  # GN-25 to GN-27
            "average_delay_days": 0 if behavior == "ON_TIME" else (random.randint(5, 25) if behavior == "LATE_MONTHLY" else random.randint(10, 45))
        })
        
    df_registry = pd.DataFrame(registry_rows)
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_csv_path), exist_ok=True)
    
    df_registry.to_csv(output_csv_path, index=False)
    print(f"Successfully generated GSTIN registry covering {len(df_registry)} vendors at {output_csv_path}")

if __name__ == "__main__":
    vendor_input = "data/raw/masters/vendor_master.csv"
    output_file = "data/raw/masters/gstin_registry.csv"
    generate_gstin_registry(vendor_input, output_file)