"""
Module: scripts/gstr2b/gen_gstr2b.py
Description: Generates clean GSTR-2B data files (b2b, b2ba, cdnr, cdnra) from purchase books.
Excludes composition vendors and applies filing timing rules.
"""

import os
import pandas as pd
from datetime import datetime

def generate_gstr2b():
    print("Generating clean GSTR-2B files...")
    os.makedirs("data/interim", exist_ok=True)
    os.makedirs("data/raw/gstr2b", exist_ok=True)

    # Load masters and books
    registry_df = pd.read_csv("data/raw/masters/gstin_registry.csv")
    gstin_col = 'vendor_gstin' if 'vendor_gstin' in registry_df.columns else 'gstin'
    type_col = 'taxpayer_type' if 'taxpayer_type' in registry_df.columns else ('registration_type' if 'registration_type' in registry_df.columns else 'vendor_type')
    
    comp_gstins = set(registry_df[registry_df[type_col].astype(str).str.upper() == 'COMPOSITION'][gstin_col])
    
    b2b_df = pd.read_csv("data/raw/books/books_b2b.csv")
    b2ba_df = pd.read_csv("data/raw/books/books_b2ba.csv")
    cdn_df = pd.read_csv("data/raw/books/books_cdn.csv")
    cdna_df = pd.read_csv("data/raw/books/books_cdna.csv")

    # 1. GSTR-2B B2B (Exclude composition)
    gstr2b_b2b = b2b_df[~b2b_df['counter_party_gstin'].isin(comp_gstins)].copy()
    gstr2b_b2b['gstr2b_period'] = gstr2b_b2b['fp']
    gstr2b_b2b.to_csv("data/interim/gstr2b_b2b.csv", index=False)
    gstr2b_b2b.to_csv("data/raw/gstr2b/gstr2b_b2b.csv", index=False)
    print(f"Generated gstr2b_b2b with {len(gstr2b_b2b)} rows.")

    # 2. GSTR-2B B2BA
    gstr2b_b2ba = b2ba_df[~b2ba_df['counter_party_gstin'].isin(comp_gstins)].copy()
    gstr2b_b2ba['gstr2b_period'] = gstr2b_b2ba['fp'] if 'fp' in gstr2b_b2ba.columns else gstr2b_b2ba['tax_period']
    gstr2b_b2ba.to_csv("data/interim/gstr2b_b2ba.csv", index=False)
    gstr2b_b2ba.to_csv("data/raw/gstr2b/gstr2b_b2ba.csv", index=False)
    print(f"Generated gstr2b_b2ba with {len(gstr2b_b2ba)} rows.")

    # 3. GSTR-2B CDNR
    gstr2b_cdnr = cdn_df[~cdn_df['counter_party_gstin'].isin(comp_gstins)].copy()
    gstr2b_cdnr['gstr2b_period'] = gstr2b_cdnr['fp']
    gstr2b_cdnr.to_csv("data/interim/gstr2b_cdnr.csv", index=False)
    gstr2b_cdnr.to_csv("data/raw/gstr2b/gstr2b_cdnr.csv", index=False)
    print(f"Generated gstr2b_cdnr with {len(gstr2b_cdnr)} rows.")

    # 4. GSTR-2B CDNRA
    gstr2b_cdnra = cdna_df[~cdna_df['counter_party_gstin'].isin(comp_gstins)].copy()
    gstr2b_cdnra['gstr2b_period'] = gstr2b_cdnra['fp']
    gstr2b_cdnra.to_csv("data/interim/gstr2b_cdnra.csv", index=False)
    gstr2b_cdnra.to_csv("data/raw/gstr2b/gstr2b_cdnra.csv", index=False)
    print(f"Generated gstr2b_cdnra with {len(gstr2b_cdnra)} rows.")

if __name__ == "__main__":
    generate_gstr2b()