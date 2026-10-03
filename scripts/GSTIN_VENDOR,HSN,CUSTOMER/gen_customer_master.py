"""
Module: scripts/gen_customer_master.py
Description: Generates a customer master dataset of 100 customers with 70% good payers,
20% late payers, and 10% defaulters, complete with valid Modulo-36 GSTINs.
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


CUSTOMER_PREFIXES = [
    "Apex", "Blue", "Crest", "Crown", "Elite", "First", "Grand", "Horizon", 
    "Imperial", "Jade", "Kinetic", "Lunar", "Matrix", "Noble", "Omega", 
    "Prime", "Quest", "Royal", "Solar", "Terra", "Urban", "Vanguard"
]

CUSTOMER_SECTORS = [
    "Retailers", "Distributors", "Logistics", "Holdings", "Solutions", 
    "Ventures", "Trading", "Exports", "Services", "Group", "Agencies"
]

def generate_random_pan(name_initial: str) -> str:
    """Generates a valid 10-character corporate/firm PAN for customers."""
    letters = "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=3))
    digits = "".join(random.choices("0123456789", k=4))
    last_letter = random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    return f"{letters}C{name_initial}{digits}{last_letter}"

def generate_customer_master(output_csv_path: str, total_customers: int = 100):
    """
    Generates 100 customers satisfying payment behavior splits and valid structural GSTINs.
    """
    rows = []
    state_list = list(STATE_CODES.keys())
    
    # Payment behavior distribution: 70% good payers, 20% late payers, 10% defaulters
    payment_behaviors = ["GOOD_PAYER"] * 70 + ["LATE_PAYER"] * 20 + ["DEFAULTER"] * 10
    random.shuffle(payment_behaviors)
    
    used_gstins = set()
    
    for i in range(total_customers):
        customer_id = f"CUST-{i+1:03d}"
        
        prefix = random.choice(CUSTOMER_PREFIXES)
        sector = random.choice(CUSTOMER_SECTORS)
        customer_name = f"{prefix} {sector} Pvt Ltd"
        
        state_code = random.choice(state_list)
        behavior = payment_behaviors[i]
        
        # Generate 14-character base for GSTIN (GN-28)
        pan = generate_random_pan(customer_name[0].upper())
        entity_code = str(random.randint(1, 9))
        base_14 = f"{state_code}{pan}{entity_code}Z"
        
        # Build complete 15-character valid GSTIN using Modulo-36 checksum
        gstin = build_gstin(base_14)
        while gstin in used_gstins:
            entity_code = random.choice("123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ")
            base_14 = f"{state_code}{pan}{entity_code}Z"
            gstin = build_gstin(base_14)
        used_gstins.add(gstin)
        
        rows.append({
            "customer_id": customer_id,
            "customer_name": customer_name,
            "customer_gstin": gstin,
            "state_code": state_code,
            "state_name": STATE_CODES.get(state_code, "Unknown"),
            "payment_behavior": behavior,
            "credit_terms_days": 30 if behavior == "GOOD_PAYER" else (45 if behavior == "LATE_PAYER" else 90)
        })
        
    df_customers = pd.DataFrame(rows)
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_csv_path), exist_ok=True)
    
    df_customers.to_csv(output_csv_path, index=False)
    print(f"Successfully generated customer master with {len(df_customers)} customers at {output_csv_path}")

if __name__ == "__main__":
    output_file = "data/raw/masters/customer_master.csv"
    generate_customer_master(output_file)