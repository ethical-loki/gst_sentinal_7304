"""
Tariff Ingestion Pipeline: scripts/ingest_tariff.py
Parses the official CBIC master spreadsheet (data/raw/Final_hsn_sac_copy.xlsx),
cleans and normalizes HSN codes (4-digit headings, 6-digit subheadings, 8-digit tariff items),
handles statutory rates and Section 17(5) blocked ITC flags,
and serializes to high-performance columnar storage at data/tariff_master.parquet.
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
RAW_EXCEL_PATH = ROOT_DIR / "data" / "raw" / "Final_hsn_sac_copy.xlsx"
OUTPUT_PARQUET_PATH = ROOT_DIR / "data" / "tariff_master.parquet"

# Section 17(5) Blocked ITC rules
BLOCKED_17_5_CHAPTERS = {
    "8702": "Blocked: Section 17(5)(a) Passenger transport motor vehicles",
    "8703": "Blocked: Section 17(5)(a) Motor cars & passenger vehicles",
    "8711": "Blocked: Section 17(5)(a) Two-wheelers / motorcycles",
    "8903": "Blocked: Section 17(5)(b) Vessels and yachts",
    "8802": "Blocked: Section 17(5)(b) Aircraft for non-exempt purposes",
    "2106": "Blocked: Section 17(5)(b)(i) Food & beverages / catering",
    "2201": "Blocked: Section 17(5)(b)(i) Beverages / drinking water catering",
    "2202": "Blocked: Section 17(5)(b)(i) Aerated waters / non-alcoholic beverages",
}


def clean_text_description(text: object) -> str:
    """Cleans statutory text description: lowercases and normalizes whitespace."""
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return ""
    text_str = str(text).strip()
    # Strip non-printable ASCII / control characters
    text_str = re.sub(r"[\x00-\x1f\x7f-\x9f\u200b-\u200d\ufeff]", " ", text_str)
    # Standardize whitespace
    return re.sub(r"\s+", " ", text_str).strip()


def normalize_clean_description(text: str) -> str:
    """Removes punctuation and normalizes characters for n-gram feature hashing."""
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def parse_statutory_rate(val: object) -> float:
    """Parses statutory central tax rate or GST rate float from cell value."""
    if val is None or pd.isna(val):
        return 18.0  # Default standard GST slab if unspecified
    val_str = str(val).strip()
    if val_str.lower() in ("nil", "none", "null", "exempt", "0", "zero", "0.0"):
        return 0.0

    # Match percentage notation e.g. "18%" or "5 %"
    pct_m = re.search(r"(\d+(?:\.\d+)?)\s*%", val_str)
    if pct_m:
        return round(float(pct_m.group(1)), 2)

    try:
        num = float(val_str)
        # In CBIC GST notifications, central tax is listed (e.g. 0.025 = 2.5% CGST -> 5% IGST, 0.09 -> 18%)
        if 0.0 < num <= 0.20:
            return round(num * 200.0, 2)
        elif num > 1.0:
            return round(num, 2)
        elif num == 0.0:
            return 0.0
    except ValueError:
        pass
    return 18.0


def extract_hsn_codes(cell_val: object) -> List[str]:
    """Extracts all discrete HSN codes from a table cell, normalizing lengths."""
    if cell_val is None or pd.isna(cell_val):
        return []
    s = str(cell_val).strip()
    if any(h in s.lower() for h in ["heading/tariff", "chapter/head"]):
        return []

    # Strip bracketed qualifiers
    s = re.sub(r"\[.*?\]|\(.*?\)", "", s)

    # Check for range: "0101 to 0104"
    range_m = re.match(r"^(\d{2,4})\s+to\s+(\d{2,4})", s, re.IGNORECASE)
    if range_m:
        s_val = int(range_m.group(1))
        e_val = int(range_m.group(2))
        pad = len(range_m.group(1))
        return [str(n).zfill(pad) for n in range(s_val, e_val + 1)]

    # Split by commas, semicolons, newlines, slashes, or "or"
    chunks = re.split(r"[,;\n/]|\bor\b", s)
    codes: List[str] = []
    for chunk in chunks:
        # Extract contiguous digits
        cleaned = re.sub(r"[^0-9]", "", chunk)
        if len(cleaned) >= 2:
            # Pad odd-length numbers if needed
            if len(cleaned) in (3, 5, 7):
                cleaned = "0" + cleaned
            # Valid HSN lengths: 2, 4, 6, 8
            if len(cleaned) in (2, 4, 6, 8):
                codes.append(cleaned)
    return codes


def ingest_cbic_tariff(
    raw_path: Path = RAW_EXCEL_PATH,
    out_path: Path = OUTPUT_PARQUET_PATH
) -> pd.DataFrame:
    """Ingests, cleans, normalizes and serializes official CBIC tariff spreadsheet."""
    if not raw_path.exists():
        raise FileNotFoundError(f"CBIC Tariff spreadsheet not found at {raw_path}")

    print(f"[*] Reading CBIC master spreadsheet from {raw_path}...")
    raw_df = pd.read_excel(raw_path)

    col_code = raw_df.columns[0]
    col_desc = raw_df.columns[1] if len(raw_df.columns) > 1 else raw_df.columns[0]
    col_rate = raw_df.columns[2] if len(raw_df.columns) > 2 else None

    records: List[Dict] = []
    current_desc = ""
    current_rate = 18.0

    for _, row in raw_df.iterrows():
        c0 = row[col_code]
        c1 = row[col_desc]
        c2 = row[col_rate] if col_rate is not None else None

        # Check for header repetition
        if pd.notna(c0) and any(k in str(c0).lower() for k in ["heading/tariff", "chapter/head"]):
            continue

        # Forward fill description if present
        if pd.notna(c1) and str(c1).strip():
            current_desc = clean_text_description(c1)

        # Forward fill rate if present
        if pd.notna(c2) and str(c2).strip():
            current_rate = parse_statutory_rate(c2)

        if pd.isna(c0):
            continue

        codes = extract_hsn_codes(c0)
        if not codes:
            continue

        for code in codes:
            ch = code[:2].zfill(2)
            h4 = code[:4] if len(code) >= 4 else code.zfill(4)

            # Check Section 17(5)
            is_blocked = 0
            blocked_reason = "Eligible: General ITC"
            if h4 in BLOCKED_17_5_CHAPTERS:
                is_blocked = 1
                blocked_reason = BLOCKED_17_5_CHAPTERS[h4]

            records.append({
                "hsn_code": code,
                "hsn_4digit": h4,
                "chapter": ch,
                "description": current_desc,
                "clean_description": normalize_clean_description(current_desc),
                "standard_rate": float(current_rate),
                "is_blocked_17_5": int(is_blocked),
                "blocked_17_5_reason": blocked_reason,
                "effective_date": "2017-07-01",
            })

    df = pd.DataFrame(records)

    # Deduplicate by hsn_code and clean_description
    df = df.drop_duplicates(subset=["hsn_code", "clean_description"]).reset_index(drop=True)

    # Ensure 4-digit representations also exist for all 6/8-digit codes
    existing_hsn = set(df["hsn_code"])
    additional_4d_rows = []
    for _, row in df.iterrows():
        h4 = row["hsn_4digit"]
        if h4 not in existing_hsn:
            new_row = row.to_dict()
            new_row["hsn_code"] = h4
            additional_4d_rows.append(new_row)
            existing_hsn.add(h4)

    if additional_4d_rows:
        df = pd.concat([df, pd.DataFrame(additional_4d_rows)], ignore_index=True)

    # Sort deterministically
    df = df.sort_values(by=["chapter", "hsn_4digit", "hsn_code"]).reset_index(drop=True)

    # Ensure output directory exists
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Serialize to high-performance parquet
    df.to_parquet(out_path, engine="pyarrow", index=False)
    print(f"[OK] Ingestion complete. Saved {len(df)} tariff records to {out_path}")
    print(f"     Unique HSN codes: {df['hsn_code'].nunique()} | Unique 4-digit HSNs: {df['hsn_4digit'].nunique()}")
    return df


if __name__ == "__main__":
    ingest_cbic_tariff()
