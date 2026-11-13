"""
scripts/generate_data_quality_report.py
======================================
Generates an audit report on data quality issues in data/raw/Master_copy_hsn.xlsx:
1. Truncated descriptions (words cut off mid-spelling, trailing punctuation artifacts).
2. Duplicate labels/descriptions across different HSN codes (e.g. 8471 30 10 vs 8471 30 90).
3. Missing or empty fields across source columns.
4. Chapter and Heading coverage statistics.
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Any
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
MASTER_FILE = ROOT_DIR / "data" / "raw" / "Master_copy_hsn.xlsx"
OUTPUT_REPORT = ROOT_DIR / "reports" / "data_quality_report.md"


def analyze_data_quality():
    if not MASTER_FILE.exists():
        raise FileNotFoundError(f"Master file not found at {MASTER_FILE}")

    df = pd.read_excel(MASTER_FILE)
    total_rows = len(df)

    # 1. Truncated Descriptions
    # Look for: trailing dashes, cut-off words (like 'PROCESSIN', 'N ETWO R KS', trailing colons)
    truncated_records = []
    known_cutoffs = [
        r"[A-Z]{3,}\s*-\s*$",  # trailing dash
        r"\bPROCESSIN$",       # processin instead of processing
        r"\bAPPARAT\b",        # apparat instead of apparatus
        r"\bEQUIPM\b",         # equipm instead of equipment
        r"\bMACHIN\b",         # machin instead of machine
        r"\bCONNEC\b",         # connec instead of connector
        r":\s*$",              # trailing colon with nothing after
        r"-\s*$"               # trailing hyphen
    ]

    for idx, r in df.iterrows():
        code = str(r["HSN Code"]).strip()
        desc = str(r.get("HSN Description") or "").strip()
        is_trunc = False
        reasons = []

        for pat in known_cutoffs:
            if re.search(pat, desc):
                is_trunc = True
                reasons.append(f"Matched pattern '{pat}'")

        # Also check if last word is in incomplete state
        words = desc.split()
        if words:
            last_w = words[-1].strip(".,;:()")
            if last_w.isupper() and len(last_w) >= 6 and last_w not in (
                "OTHER", "INCLUDED", "SPECIFIED", "PIECES", "PARTS", "THEREFOR",
                "THEREWITH", "UNITS", "MACHINES", "APPARATUS", "SYSTEMS", "GOODS",
                "ARTICLES", "MATERIAL", "PRODUCTS", "DEVICES", "VEHICLES"
            ):
                # Common truncation endings
                if last_w.endswith(("IN", "TI", "ME", "CON")):
                    if last_w not in ("RESIN", "PROTEIN", "TIN", "COTTON", "NYLON", "IRON", "SILICON", "TEFLON"):
                        is_trunc = True
                        reasons.append(f"Suspect truncated trailing token: '{last_w}'")

        if is_trunc:
            truncated_records.append({
                "hsn_code": code,
                "chapter": str(r.get("chapter_code")),
                "description": desc,
                "reasons": reasons
            })

    # 2. Duplicate Descriptions across Different HSN codes
    # Group by stripped description
    desc_to_codes: Dict[str, List[str]] = {}
    for idx, r in df.iterrows():
        code = str(r["HSN Code"]).strip()
        desc = str(r.get("HSN Description") or "").strip().upper()
        if len(desc) > 10:
            desc_to_codes.setdefault(desc, []).append(code)

    duplicate_groups = {
        desc: codes for desc, codes in desc_to_codes.items() if len(codes) > 1 and len(set(codes)) > 1
    }

    # 3. Missing or Empty Fields
    cols_to_check = ["HSN Code", "chapter_code", "chapter_title", "HSN Description", "Article Keywords", "Material Keywords"]
    missing_counts = {col: int(df[col].isna().sum()) for col in cols_to_check if col in df.columns}

    # 4. Chapter Coverage
    df["h4"] = df["HSN Code"].astype(str).str.strip().str[:4]
    chapter_stats = []
    for ch, group in df.groupby("chapter_code"):
        h4_count = group["h4"].nunique()
        lines_count = len(group)
        title = group["chapter_title"].iloc[0]
        chapter_stats.append({
            "chapter": str(ch),
            "title": title,
            "headings_count": h4_count,
            "lines_count": lines_count
        })

    # Build Markdown Report
    os.makedirs(OUTPUT_REPORT.parent, exist_ok=True)
    with open(OUTPUT_REPORT, "w", encoding="utf-8") as f:
        f.write("# Master Tariff Dataset Quality Audit Report\n\n")
        f.write(f"**Source File**: `data/raw/Master_copy_hsn.xlsx`  \n")
        f.write(f"**Total Tariff Lines**: {total_rows}  \n")
        f.write(f"**Total Active Chapters**: {len(chapter_stats)}  \n\n")

        f.write("## 1. Executive Summary\n\n")
        f.write(f"- **Truncated Descriptions Identified**: {len(truncated_records)} rows  \n")
        f.write(f"- **Duplicate Description Groups (Shared text across different codes)**: {len(duplicate_groups)} groups affecting {sum(len(c) for c in duplicate_groups.values())} rows  \n")
        f.write(f"- **Missing Value Count**: {sum(missing_counts.values())}  \n\n")

        f.write("## 2. Chapter & Heading Coverage\n\n")
        f.write("| Chapter | Chapter Title | Unique 4-Digit Headings | Total Tariff Lines |\n")
        f.write("| :--- | :--- | :--- | :--- |\n")
        for cs in sorted(chapter_stats, key=lambda x: int(x["chapter"])):
            f.write(f"| Ch {cs['chapter']} | {cs['title']} | {cs['headings_count']} | {cs['lines_count']} |\n")
        f.write("\n")

        f.write("## 3. Duplicate Description Collision Analysis\n\n")
        f.write("When two distinct 8-digit tariff items share the exact same statutory description, the decision engine must disambiguate them using keyword attributes rather than confusing the user with identical cards.\n\n")
        f.write("| Colliding Codes | Shared Statutory Description | Disambiguation Strategy |\n")
        f.write("| :--- | :--- | :--- |\n")
        for desc, codes in list(duplicate_groups.items())[:20]:
            short_desc = (desc[:65] + "...") if len(desc) > 65 else desc
            f.write(f"| `{', '.join(codes[:4])}` | {short_desc} | Disambiguate via `Article Keywords` & 8-digit leaf spec |\n")
        f.write("\n")

        f.write("## 4. Notable Truncated Statutory Text Entries\n\n")
        f.write("The following rows in the Master Excel file were clipped or truncated during source ingestion:\n\n")
        f.write("| HSN Code | Chapter | Truncated Description Snippet | Diagnostic Notes |\n")
        f.write("| :--- | :--- | :--- | :--- |\n")
        for tr in truncated_records[:25]:
            snippet = (tr['description'][-60:]) if len(tr['description']) > 60 else tr['description']
            reasons_str = "; ".join(tr["reasons"])
            f.write(f"| `{tr['hsn_code']}` | Ch {tr['chapter']} | `...{snippet}` | {reasons_str} |\n")
        f.write("\n")

        f.write("## 5. Field Completeness\n\n")
        f.write("| Field Name | Missing Records | Status |\n")
        f.write("| :--- | :--- | :--- |\n")
        for col, count in missing_counts.items():
            status = "✅ Complete" if count == 0 else f"⚠️ {count} Missing"
            f.write(f"| `{col}` | {count} | {status} |\n")
        f.write("\n")

    print(f"Data quality report successfully written to {OUTPUT_REPORT}")
    return len(truncated_records), len(duplicate_groups)


if __name__ == "__main__":
    analyze_data_quality()

