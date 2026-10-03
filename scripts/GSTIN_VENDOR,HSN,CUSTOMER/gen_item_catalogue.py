"""
Module: scripts/gen_item_catalogue.py
Description: Processes data/raw/hsn_sac.xlsx using exact columns 'HSN_CD' and 'HSN_Description',
filters out Section 17(5) blocked credits, categorizes items, and outputs item_catalogue.csv.
"""

import sys
import os
import pandas as pd
import random

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from gen_reference import ALL_BLOCKED_KEYWORDS

def generate_item_catalogue(excel_path: str, output_csv_path: str, target_count: int = 120):
    """
    Reads the HSN Excel file, filters out blocked items and vague descriptions,
    samples 120 items across 7 categories, and outputs the clean catalogue CSV.
    """
    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"Source Excel file not found at: {excel_path}")
        
    print(f"Loading HSN master from {excel_path}...")
    df = pd.read_excel(excel_path)
    
    # Exact column names provided by user
    hsn_col = 'HSN_CD'
    desc_col = 'HSN_Description'
    
    if hsn_col not in df.columns or desc_col not in df.columns:
        # Fallback check for slight casing mismatches
        cols_lower = {c.lower(): c for c in df.columns}
        hsn_col = cols_lower.get('hsn_cd', hsn_col)
        desc_col = cols_lower.get('hsn_description', desc_col)
        
    if hsn_col not in df.columns or desc_col not in df.columns:
        raise KeyError(f"Expected columns '{hsn_col}' and '{desc_col}' not found in Excel file. Available columns: {list(df.columns)}")
        
    # Standardize types and strip whitespace, handling missing values
    df[hsn_col] = df[hsn_col].astype(str).str.replace(r'\D', '', regex=True)
    df[desc_col] = df[desc_col].fillna("").astype(str).str.strip()
    
    # Rename for internal processing consistency
    df = df.rename(columns={hsn_col: 'hsn_code', desc_col: 'description'})
    
    # 1. Filter valid lengths (4, 6, or 8 digits per PN-15)
    df = df[df['hsn_code'].str.len().isin([4, 6, 8])]
    
    # 2. Remove vague descriptions (PN-19)
    vague_terms = ['', 'misc', 'miscellaneous', 'goods', 'services', 'other', 'n/a', 'nan', 'nil']
    df = df[~df['description'].str.lower().isin(vague_terms)]
    
    # 3. Remove blocked-credit keywords strictly satisfying PN-20 / Section 17(5)
    def contains_blocked_keyword(desc):
        if not isinstance(desc, str):
            return False
        desc_lower = desc.lower()
        return any(kw in desc_lower for kw in ALL_BLOCKED_KEYWORDS)
        
    df = df[~df['description'].apply(contains_blocked_keyword)]

    
    print(f"Filtered clean base records: {len(df)} rows available after applying compliance rules.")
    
    if len(df) == 0:
        raise ValueError("No records left after filtering! Please check your source file and blocklist rules.")
        
    # 4. Define 7 Business Categories
    categories = [
        "IT & Software Services", 
        "Office Supplies & Stationery", 
        "Raw Materials & Hardware", 
        "Professional & Advisory Services", 
        "Packing & Logistics", 
        "Electrical & Machinery Parts", 
        "Marketing & Print Media"
    ]
    
    # Distribute rows evenly across our 7 categories for sampling
    df['category'] = [categories[i % len(categories)] for i in range(len(df))]
    
    # 5. Sample exactly target_count (120) items balanced across categories
    items_per_category = max(1, target_count // len(categories))
    sampled_dfs = []
    
    for cat in categories:
        cat_subset = df[df['category'] == cat]
        sample_n = min(items_per_category, len(cat_subset))
        if sample_n > 0:
            sampled_dfs.append(cat_subset.sample(n=sample_n, random_state=42))
            
    catalogue_df = pd.concat(sampled_dfs).head(target_count)
    
    # Pad if short of target count
    if len(catalogue_df) < target_count:
        extra_needed = target_count - len(catalogue_df)
        remaining_pool = df[~df.index.isin(catalogue_df.index)]
        if len(remaining_pool) >= extra_needed:
            extra_sample = remaining_pool.sample(n=extra_needed, random_state=42)
            catalogue_df = pd.concat([catalogue_df, extra_sample])
            
    catalogue_df = catalogue_df.reset_index(drop=True)
    catalogue_df['item_id'] = [f"ITM-{i+1:03d}" for i in range(len(catalogue_df))]
    
    # 6. Assign Pricing Boundaries and Tax Rates (PN-21, PN-39)
    prices = []
    rates = []
    for _, row in catalogue_df.iterrows():
        cat = row['category']
        if "Software" in cat or "Professional" in cat:
            prices.append(round(random.uniform(5000.0, 150000.0), 2))
            rates.append(18.0)
        elif "Raw Materials" in cat or "Electrical" in cat:
            prices.append(round(random.uniform(200.0, 25000.0), 2))
            rates.append(random.choice([5.0, 12.0, 18.0, 28.0]))
        else:
            prices.append(round(random.uniform(100.0, 5000.0), 2))
            rates.append(random.choice([5.0, 12.0, 18.0]))
            
    catalogue_df['unit_price_lower'] = [round(p * 0.9, 2) for p in prices]
    catalogue_df['unit_price_upper'] = [round(p * 1.1, 2) for p in prices]
    catalogue_df['standard_unit_price'] = prices
    catalogue_df['gst_rate'] = rates
    
    # Final column sequence
    final_columns = [
        'item_id', 'category', 'hsn_code', 'description', 
        'standard_unit_price', 'unit_price_lower', 'unit_price_upper', 'gst_rate'
    ]
    final_catalogue = catalogue_df[final_columns]
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_csv_path), exist_ok=True)
    
    # Save output
    final_catalogue.to_csv(output_csv_path, index=False)
    print(f"Successfully generated item catalogue with {len(final_catalogue)} items saved to {output_csv_path}")

if __name__ == "__main__":
    excel_file = "data/raw/HSN_SAC.xlsx"
    output_file = "data/raw/masters/item_catalogue.csv"
    generate_item_catalogue(excel_file, output_file)