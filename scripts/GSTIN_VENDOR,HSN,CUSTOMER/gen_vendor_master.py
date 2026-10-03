"""
Module: scripts/gen_vendor_master.py
Description: Generates a vendor master dataset of 200 vendors with 61% Maharashtra distribution,
95% regular / 5% composition types, valid Modulo-36 GSTINs, and payment terms.
"""

import sys
import os
import random
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from gen_reference import STATE_CODES
from gstin_utils import build_gstin


# Sample company name components for realistic generation
COMPANY_PREFIXES = [
    "Apex", "Zenith", "Vanguard", "Pioneer", "Sterling", "Quantum", "Nexus", 
    "Delta", "Omega", "Sigma", "Titan", "Global", "Prime", "Vertex", "Nova", 
    "Alpha", "Infra", "Swift", "Apex", "Dynamic", "Stellar", "Summit"
]

COMPANY_SECTORS = [
    "Logistics", "Technologies", "Enterprises", "Solutions", "Industries", 
    "Supplies", "Hardware", "Consultancy", "Services", "Distributors", 
    "Associates", "Systems", "Components", "Trading Co", "Infotech"
]

def generate_random_pan(vendor_type_char: str, name_initial: str) -> str:
    """Generates a valid 10-character PAN based on vendor type and name."""
    # 4th character: C (Company), F (Firm), P (Individual)
    letters = "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=3))
    digits = "".join(random.choices("0123456789", k=4))
    last_letter = random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    return f"{letters}{vendor_type_char}{name_initial}{digits}{last_letter}"

def generate_vendor_master(output_csv_path: str, total_vendors: int = 200):
    """
    Generates 200 vendors satisfying geographic distribution, registration types,
    valid structural GSTINs, and payment terms.
    """
    rows = []
    
    # State codes pool for the remaining 39% non-Maharashtra vendors
    other_states = [code for code in STATE_CODES.keys() if code != "27"]
    
    # Calculate exact counts for 61% Maharashtra distribution
    mh_count = int(total_vendors * 0.61) # 122 vendors
    other_count = total_vendors - mh_count # 78 vendors
    
    state_allocation = ["27"] * mh_count + random.choices(other_states, k=other_count)
    random.shuffle(state_allocation)
    
    # Allocation for 95% Regular and 5% Composition
    vendor_types = ["REGULAR"] * int(total_vendors * 0.95) + ["COMPOSITION"] * (total_vendors - int(total_vendors * 0.95))
    random.shuffle(vendor_types)
    
    payment_terms_options = [15, 30, 45, 60]
    
    used_gstins = set()
    
    for i in range(total_vendors):
        vendor_id = f"VND-{i+1:03d}"
        
        # Name generation
        prefix = random.choice(COMPANY_PREFIXES)
        sector = random.choice(COMPANY_SECTORS)
        suffix = random.choice(["Pvt Ltd", "LLP", "Brothers", "Corp", "Partners", "Enterprises", ""])
        vendor_name = f"{prefix} {sector} {suffix}".strip()
        
        state_code = state_allocation[i]
        v_type = vendor_types[i]
        
        # Determine PAN character based on entity type (GN-08)
        pan_type_char = "C" if ("Pvt Ltd" in vendor_name or "Corp" in vendor_name) else "F"
        name_initial = vendor_name[0].upper()
        
        # Generate 14-character base for GSTIN
        # Format: State Code (2) + PAN (10) + Entity Code (1) + 'Z' (1)
        pan = generate_random_pan(pan_type_char, name_initial)
        entity_code = str(random.randint(1, 9))
        base_14 = f"{state_code}{pan}{entity_code}Z"
        
        # Build complete 15-character valid GSTIN using Modulo-36 checksum
        gstin = build_gstin(base_14)
        while gstin in used_gstins:
            # Ensure unique GSTIN
            entity_code = random.choice("123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ")
            base_14 = f"{state_code}{pan}{entity_code}Z"
            gstin = build_gstin(base_14)
        used_gstins.add(gstin)
        
        # Registration date (before FY 2024-25, e.g., between 2020 and 2023)
        reg_year = random.randint(2020, 2023)
        reg_month = random.randint(1, 12)
        reg_day = random.randint(1, 28)
        reg_date = f"{reg_year}-{reg_month:02d}-{reg_day:02d}"
        
        payment_terms = random.choice(payment_terms_options)
        
        rows.append({
            "vendor_id": vendor_id,
            "vendor_name": vendor_name,
            "vendor_gstin": gstin,
            "state_code": state_code,
            "state_name": STATE_CODES.get(state_code, "Unknown"),
            "registration_type": v_type,
            "registration_date": reg_date,
            "payment_terms_days": payment_terms
        })
        
    df_vendors = pd.DataFrame(rows)
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_csv_path), exist_ok=True)
    
    df_vendors.to_csv(output_csv_path, index=False)
    print(f"Successfully generated vendor master with {len(df_vendors)} vendors at {output_csv_path}")

if __name__ == "__main__":
    output_file = "data/raw/masters/vendor_master.csv"
    generate_vendor_master(output_file)