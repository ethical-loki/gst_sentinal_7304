"""
Module: scripts/gen_reference.py
Description: Generates Day 1 reference data, masters, and registries (vendor, customer, item catalogue, gstin registry).
"""

import os
import random
import pandas as pd
from datetime import datetime, timedelta

# State and UT GST Codes
STATE_CODES = {
    "01": "Jammu and Kashmir",
    "02": "Himachal Pradesh",
    "03": "Punjab",
    "04": "Chandigarh",
    "05": "Uttarakhand",
    "06": "Haryana",
    "07": "Delhi",
    "08": "Rajasthan",
    "09": "Uttar Pradesh",
    "10": "Bihar",
    "11": "Sikkim",
    "12": "Arunachal Pradesh",
    "13": "Nagaland",
    "14": "Manipur",
    "15": "Mizoram",
    "16": "Tripura",
    "17": "Meghalaya",
    "18": "Assam",
    "19": "West Bengal",
    "20": "Jharkhand",
    "21": "Odisha",
    "22": "Chhattisgarh",
    "23": "Madhya Pradesh",
    "24": "Gujarat",
    "25": "Dadra and Nagar Haveli and Daman and Diu",
    "26": "Dadra and Nagar Haveli",
    "27": "Maharashtra",
    "28": "Andhra Pradesh (Old)",
    "29": "Karnataka",
    "30": "Goa",
    "31": "Lakshadweep",
    "32": "Kerala",
    "33": "Tamil Nadu",
    "34": "Puducherry",
    "35": "Andaman and Nicobar Islands",
    "36": "Telangana",
    "37": "Andhra Pradesh",
    "38": "Ladakh",
    "97": "Other Territory",
    "99": "Centre Jurisdiction"
}

# Section 17(5) blocked credit keywords for goods and services filtering
ALL_BLOCKED_KEYWORDS = [
    "motor vehicle", "car", "conveyance", "aircraft", "vessel", "yacht",
    "food", "beverages", "outdoor catering", "catering", "beauty treatment",
    "health services", "cosmetic", "plastic surgery", "life insurance",
    "health insurance", "club membership", "gym membership", "travel benefit",
    "vacation", "ltc", "lta", "works contract", "construction", "building",
    "personal consumption", "free sample", "gift", "stolen", "destroyed",
    "written off", "lost"
]


def generate_reference_data():
    print("Generating Day 1 reference data and masters...")
    os.makedirs("data/raw/masters", exist_ok=True)
    
    # 1. Item Catalogue (100-150 items, no HSN/SAC, no blocked items in clean data)
    categories = ["Raw Materials", "Consumables", "IT Hardware", "Office Supplies", "Freight Services", "Legal Services"]
    blocked_keywords_clean = [] # Clean items have no blocked credit keywords
    
    items = []
    item_id = 1
    for cat in categories:
        for i in range(25):
            rate = random.choice([0, 5, 12, 18, 28])
            item_type = "service" if "Services" in cat else "goods"
            price_min = round(random.uniform(100.0, 5000.0), 2)
            price_max = round(price_min * random.uniform(1.2, 2.0), 2)
            items.append({
                "item_id": f"ITM-{item_id:04d}",
                "description": f"{cat} Item {i+1} Standard Grade",
                "item_type": item_type,
                "rate": rate,
                "price_min": price_min,
                "price_max": price_max,
                "vendor_category": cat,
                "itc_eligible": "N" if rate == 0 else "Y",
                "capital_goods_flag": "Y" if "Hardware" in cat else "N",
                "blocked_credit_flag": "N" # Clean catalogue contains zero blocked items
            })
            item_id += 1
            
    df_items = pd.DataFrame(items)
    df_items.to_csv("data/raw/masters/item_catalogue.csv", index=False)
    print(f"Generated item_catalogue.csv with {len(df_items)} items.")

    # 2. Vendor Master (150-250 vendors, 60% Maharashtra, 95% regular, 5% composition)
    state_codes = ["27", "27", "27", "27", "27", "27", "29", "33", "07", "24"] # ~60% Maharashtra (27)
    vendors = []
    registry_rows = []
    
    for v_idx in range(1, 201):
        v_id = f"VEND-{v_idx:04d}"
        state_code = random.choice(state_codes)
        pan_chars = "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=5))
        pan = f"ABCDE{pan_chars}1F"
        gstin = f"{state_code}ABCDE{pan_chars}1F1Z{random.choice(['A', 'B', '5', '9'])}"
        
        reg_type = "COMPOSITION" if v_idx <= 10 else "REGULAR"
        
        vendors.append({
            "vendor_id": v_id,
            "trade_name": f"Vendor Enterprise {v_idx}",
            "legal_name": f"Vendor Enterprise {v_idx} Pvt Ltd",
            "gstin": gstin,
            "pan": pan[:10],
            "state_code": state_code,
            "vendor_type": reg_type,
            "vendor_category": random.choice(categories),
            "payment_terms": random.choice([15, 30, 45, 60]),
            "address": f"Plot {v_idx}, Industrial Area, State {state_code}"
        })
        
        registry_rows.append({
            "gstin": gstin,
            "legal_name": f"Vendor Enterprise {v_idx} Pvt Ltd",
            "status": "Active",
            "registration_type": reg_type,
            "registration_date": "01-04-2023",
            "cancellation_date": "",
            "filing_behaviour": "on-time" if random.random() < 0.85 else ("late" if random.random() < 0.95 else "QRMP"),
            "filing_frequency": "QRMP" if reg_type == "COMPOSITION" else "Monthly",
            "last_filed_period": "022025"
        })
        
    df_vendors = pd.DataFrame(vendors)
    df_vendors.to_csv("data/raw/masters/vendor_master.csv", index=False)
    
    df_registry = pd.DataFrame(registry_rows)
    df_registry.to_csv("data/raw/masters/gstin_registry.csv", index=False)
    print(f"Generated vendor_master.csv ({len(df_vendors)} rows) and gstin_registry.csv.")

    # 3. Customer Master (80-120 customers: 70% good, 20% late, 3-5 defaulters)
    customers = []
    for c_idx in range(1, 101):
        tier = "good" if c_idx <= 70 else ("late" if c_idx <= 95 else "defaulter")
        state_code = random.choice(state_codes)
        pan_chars = "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=5))
        gstin = f"{state_code}XYZAB{pan_chars}1Z{random.randint(1, 9)}"
        
        customers.append({
            "customer_id": f"CUST-{c_idx:04d}",
            "trade_name": f"Client Partner {c_idx}",
            "gstin": gstin,
            "state_code": state_code,
            "credit_terms_days": random.choice([15, 30, 45]),
            "behavior_tier": tier
        })
        
    df_cust = pd.DataFrame(customers)
    df_cust.to_csv("data/raw/masters/customer_master.csv", index=False)
    print(f"Generated customer_master.csv with {len(df_cust)} customers.")

if __name__ == "__main__":
    generate_reference_data()