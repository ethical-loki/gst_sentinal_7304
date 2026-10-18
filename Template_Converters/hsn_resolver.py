"""
HSN / SAC Master Resolver and NIC Compliance Utilities for Indian GST.
Matches product descriptions against Final_hsn_sac_copy.xlsx tariff schedules,
reconciles statutory tax rates, supports dynamic user taxable value overrides,
and enforces the official NIC 2-day IRN document date rule.
"""

import os
import re
from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union

_HSN_DF_CACHE = None

def get_hsn_master():
    """
    Loads Final_hsn_sac_copy.xlsx into a cached pandas DataFrame with standardized
    HSN_CD, descriptions, and tax rates.
    """
    global _HSN_DF_CACHE
    if _HSN_DF_CACHE is not None:
        return _HSN_DF_CACHE

    candidate_paths = [
        Path("data/raw/Final_hsn_sac_copy.xlsx"),
        Path("data/Final_hsn_sac_copy.xlsx"),
        Path("Final_hsn_sac_copy.xlsx"),
        Path(__file__).resolve().parent.parent / "data" / "raw" / "Final_hsn_sac_copy.xlsx",
        Path(__file__).resolve().parent.parent / "data" / "Final_hsn_sac_copy.xlsx",
        Path(__file__).resolve().parent / "Final_hsn_sac_copy.xlsx",
    ]

    hsn_file = None
    for p in candidate_paths:
        if p.exists() and p.is_file():
            hsn_file = p
            break

    if not hsn_file:
        return None

    try:
        import pandas as pd
        raw_df = pd.read_excel(hsn_file)

        records = []
        current_desc = ""
        current_rate = None

        for idx, row in raw_df.iterrows():
            c0 = "" if pd.isna(row.iloc[0]) else str(row.iloc[0]).strip()
            c1 = "" if (len(row) > 1 and pd.isna(row.iloc[1])) else (str(row.iloc[1]).strip() if len(row) > 1 else "")
            c2 = row.iloc[2] if len(row) > 2 else None

            if "heading/Tariff item" in c0 or "Chapter/Head" in c0:
                continue

            if pd.notna(c2):
                current_rate = c2
            if c1:
                current_desc = c1
            elif c1 == "" and c0 == "":
                continue

            if c0:
                parsed_igst = 18.0
                parsed_cgst = 9.0
                parsed_sgst = 9.0

                if current_rate is not None:
                    r_str = str(current_rate).strip()
                    if r_str.lower() in ["nil", "none", "null", "0"]:
                        parsed_igst, parsed_cgst, parsed_sgst = 0.0, 0.0, 0.0
                    else:
                        try:
                            val = float(r_str)
                            if val <= 1.0:
                                parsed_cgst = round(val * 100, 3)
                                parsed_sgst = parsed_cgst
                                parsed_igst = round(val * 200, 3)
                            else:
                                parsed_igst = round(val, 2)
                                parsed_cgst = round(val / 2.0, 2)
                                parsed_sgst = parsed_cgst
                        except ValueError:
                            pct_m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*%", r_str)
                            if pct_m:
                                p_val = float(pct_m.group(1))
                                parsed_igst = p_val
                                parsed_cgst = round(p_val / 2.0, 2)
                                parsed_sgst = parsed_cgst

                digits_list = re.findall(r"\b\d+\b", c0)
                main_code = digits_list[0] if digits_list else re.sub(r"[^0-9]", "", c0) or c0
                if len(main_code) in [1, 3]:
                    main_code = main_code.zfill(len(main_code) + 1)

                records.append({
                    "HSN_CD": str(main_code).strip(),
                    "raw_code": c0,
                    "HSN_Description": current_desc,
                    "gst_rate": parsed_igst,
                    "igst_rate": parsed_igst,
                    "cgst_rate": parsed_cgst,
                    "sgst_rate": parsed_sgst,
                    "_search_desc": f"{c0} {main_code} {current_desc}".lower()
                })

        df = pd.DataFrame(records)
        _HSN_DF_CACHE = df
        return _HSN_DF_CACHE
    except Exception as e:
        print(f"[ERROR] Failed to load HSN master Excel: {e}")
        return None


def lookup_hsn_code(product_name: str, product_desc: str = "", hsn_prefix: Optional[str] = None, top_k: int = 5) -> List[Dict[str, Any]]:
    """
    Finds matching HSN entries from Final_hsn_sac_copy.xlsx based on product description,
    product name, and optional HSN prefix (e.g. '84').
    """
    df = get_hsn_master()
    if df is None or df.empty:
        return []

    combined = f"{product_name} {product_desc}".lower()
    raw_tokens = re.findall(r"[a-z0-9]{3,}", combined)
    stop_words = {
        "and", "the", "for", "with", "all", "other", "than", "not", "put", "up",
        "any", "nos", "pcs", "set", "item", "product", "goods", "supply", "inv",
        "standard", "regular", "unit", "pack", "batch", "rate", "code", "line"
    }
    tokens = [t for t in raw_tokens if t not in stop_words]
    if not tokens:
        tokens = [combined[:20]]

    cand = df
    clean_prefix = str(hsn_prefix).strip() if hsn_prefix else ""
    if clean_prefix and len(clean_prefix) in [2, 3, 4]:
        pref_cand = df[df["HSN_CD"].str.startswith(clean_prefix)]
        if not pref_cand.empty:
            cand = pref_cand

    key_terms = {"motor", "engine", "servo", "valve", "pump", "actuator", "drive", "compressor"}

    def compute_score(row):
        text = str(row["_search_desc"])
        s = 0
        for t in tokens:
            if t in text:
                s += 3 if t in key_terms else 1
        if clean_prefix and str(row["HSN_CD"]).startswith(clean_prefix):
            s += 5
        return s

    scores = cand.apply(compute_score, axis=1)
    matches = cand[scores > 0].copy()
    if matches.empty and not cand.equals(df):
        # Fallback to whole df if prefix yielded no token hits
        scores = df.apply(compute_score, axis=1)
        matches = df[scores > 0].copy()

    if matches.empty:
        return []

    matches["score"] = scores[scores > 0]
    matches = matches.sort_values(by=["score"], ascending=False)

    results = []
    for _, r in matches.head(top_k).iterrows():
        igst = float(r.get("igst_rate", r.get("gst_rate", 18.0)))
        results.append({
            "hsn_code": str(r["HSN_CD"]),
            "description": str(r["HSN_Description"]),
            "gst_rate": igst,
            "igst_rate": igst,
            "cgst_rate": float(r.get("cgst_rate", round(igst / 2.0, 2))),
            "sgst_rate": float(r.get("sgst_rate", round(igst / 2.0, 2))),
            "score": int(r["score"])
        })
    return results


def validate_nic_2day_rule(docdt: Union[str, date, datetime], reference_date: Optional[Union[str, date]] = None) -> Optional[Dict[str, Any]]:
    """
    Enforces the NIC e-Invoice rule: Document date cannot be more than 2 days prior
    to the current date / generation date.
    Returns compliance error dict if violation is detected, None if compliant.
    """
    inv_date = None
    if isinstance(docdt, (datetime, date)):
        inv_date = docdt if isinstance(docdt, date) else docdt.date()
    elif isinstance(docdt, str) and docdt.strip():
        s = docdt.strip()
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%d.%m.%Y"):
            try:
                inv_date = datetime.strptime(s, fmt).date()
                break
            except ValueError:
                continue

    if not inv_date:
        return None

    ref_d = date.today()
    if reference_date:
        if isinstance(reference_date, (datetime, date)):
            ref_d = reference_date if isinstance(reference_date, date) else reference_date.date()
        elif isinstance(reference_date, str):
            for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
                try:
                    ref_d = datetime.strptime(reference_date.strip(), fmt).date()
                    break
                except ValueError:
                    continue

    days_diff = (ref_d - inv_date).days
    if days_diff > 2:
        return {
            "error_code": 2164,
            "field": "docdt1.docdt",
            "message": f"Document date '{inv_date.strftime('%Y-%m-%d')}' is more than 2 days old ({days_diff} days ago). As per NIC rule, IRN cannot be generated or changed for invoices older than 2 days. Prompt: change the date.",
            "reason": f"NIC Rule: IRN generation/modification is strictly restricted when invoice date is older than 2 days (exceeded by {days_diff - 2} days).",
            "resolution": "Please change the document date (docdt) to within the last 2 days of current date (Prompt: change the date)."
        }

    return None
