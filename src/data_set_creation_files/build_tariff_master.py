import os
import re
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

RAW_INPUT_PATH = "data/raw/Final_hsn_sac_copy.xlsx"  # update path if needed
OUTPUT_PATH = "data/raw/tariff_master.parquet"

# statutory section 17 sub-section 5 rules with broad matching patterns
SECTION_17_5_RULES = [
    {
        "category": "Ineligible: Motor Vehicles",
        "prefixes": ["8702", "8703"],
        "patterns": [
            r"motor\s*car",
            r"passenger\s*car",
            r"motor\s*vehicle",
            r"passenger\s*vehicle",
            r"\bsedan\b",
            r"\bsuv\b"
        ]
    },
    {
        "category": "Ineligible: Food and Beverages",
        "prefixes": ["9963", "2106", "2201", "2202"],
        "patterns": [
            r"catering",
            r"food\s*and\s*beverage",
            r"restaurant",
            r"eating\s*service",
            r"edible\s*preparations",
            r"canteen"
        ]
    },
    {
        "category": "Ineligible: Personal Care and Healthcare",
        "prefixes": ["99972", "99931"],
        "patterns": [
            r"beauty\s*treatment",
            r"cosmetic\s*surgery",
            r"plastic\s*surgery",
            r"health\s*service"
        ]
    },
    {
        "category": "Ineligible: Club and Fitness",
        "prefixes": ["99959", "9996"],
        "patterns": [
            r"club\s*membership",
            r"fitness\s*centre",
            r"fitness\s*club",
            r"gym\b",
            r"gymnasium"
        ]
    },
    {
        "category": "Ineligible: Life and Health Insurance",
        "prefixes": ["997132", "997133"],
        "patterns": [
            r"life\s*insurance",
            r"health\s*insurance",
            r"mediclaim"
        ]
    },
    {
        "category": "Ineligible: Travel Benefits and Vacation",
        "prefixes": ["99855"],
        "patterns": [
            r"leave\s*travel",
            r"tour\s*operator",
            r"vacation\s*package"
        ]
    }
]

def clean_hsn_code(val):
    if pd.isna(val):
        return ""
    code_str = str(val).strip().replace(".", "").replace(" ", "")
    return re.sub(r"\D", "", code_str)

def clean_rate(val):
    if pd.isna(val):
        return 18.0
    try:
        val_str = str(val).replace("%", "").strip()
        num = float(val_str)
        allowed_slabs = [0.0, 5.0, 12.0, 18.0, 28.0]
        return min(allowed_slabs, key=lambda x: abs(x - num))
    except Exception:
        return 18.0

def evaluate_blocked_credit(hsn, desc):
    hsn_str = str(hsn).strip()
    desc_clean = re.sub(r"\s+", " ", str(desc)).lower()
    
    for rule in SECTION_17_5_RULES:
        for prefix in rule["prefixes"]:
            if hsn_str.startswith(prefix):
                return True, rule["category"]
                
        for pattern in rule["patterns"]:
            if re.search(pattern, desc_clean):
                return True, rule["category"]
                
    return False, "Eligible: General ITC"

def main():
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    
    if not os.path.exists(RAW_INPUT_PATH):
        raise FileNotFoundError(f"Input file not found at {RAW_INPUT_PATH}")
        
    print(f"reading input file from: {RAW_INPUT_PATH}")
    if RAW_INPUT_PATH.endswith(".xlsx") or RAW_INPUT_PATH.endswith(".xls"):
        df_raw = pd.read_excel(RAW_INPUT_PATH)
    else:
        df_raw = pd.read_csv(RAW_INPUT_PATH, dtype=str)
        
    col_map = {}
    for col in df_raw.columns:
        c_norm = re.sub(r"\s+", " ", str(col)).strip().lower()
        if any(k in c_norm for k in ["tariff", "heading", "chapter", "hsn", "item"]):
            if "desc" not in c_norm and "goods" not in c_norm:
                col_map[col] = "hsn_code"
        if any(k in c_norm for k in ["description", "goods", "desc"]):
            col_map[col] = "hsn_description"
        if "rate" in c_norm:
            col_map[col] = "standard_rate"
            
    df = df_raw.rename(columns=col_map)
    
    df["hsn_code"] = df["hsn_code"].apply(clean_hsn_code)
    df = df[df["hsn_code"] != ""].copy()
    
    df["chapter"] = df["hsn_code"].apply(lambda x: x[:2].zfill(2))
    df["hsn_description"] = df["hsn_description"].fillna("").astype(str).str.strip()
    df["standard_rate"] = df["standard_rate"].apply(clean_rate).astype(float)
    
    eval_results = [
        evaluate_blocked_credit(h, d) 
        for h, d in zip(df["hsn_code"], df["hsn_description"])
    ]
    df["is_blocked_17_5"] = [res[0] for res in eval_results]
    df["blocked_17_5_reason"] = [res[1] for res in eval_results]
    df["effective_date"] = "2017-07-01"
    
    final_cols = [
        "hsn_code",
        "chapter",
        "hsn_description",
        "standard_rate",
        "is_blocked_17_5",
        "blocked_17_5_reason",
        "effective_date"
    ]
    
    df_final = df[final_cols].drop_duplicates(subset=["hsn_code"]).reset_index(drop=True)
    
    schema = pa.schema([
        ("hsn_code", pa.string()),
        ("chapter", pa.string()),
        ("hsn_description", pa.string()),
        ("standard_rate", pa.float64()),
        ("is_blocked_17_5", pa.bool_()),
        ("blocked_17_5_reason", pa.string()),
        ("effective_date", pa.string())
    ])
    
    table = pa.Table.from_pandas(df_final, schema=schema)
    pq.write_table(table, OUTPUT_PATH, compression="snappy")
    
    print(f"successfully compiled {len(df_final)} master tariff rows into {OUTPUT_PATH}")
    print("category distribution:")
    print(df_final["blocked_17_5_reason"].value_counts())

if __name__ == "__main__":
    main()