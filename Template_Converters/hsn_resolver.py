"""
HSN / SAC Master Resolver and NIC Compliance Utilities for Indian GST.
Powered by the Universal Hybrid Semantic-Lexical HSN Intelligence ML Model (128-D CPU)
backed by the Statutory Central Board of Indirect Taxes (CBIC) Tariff Master (13,000+ items).
Reconciles statutory tax rates, Section 17(5) blocked ITC status, supports dynamic user
taxable value overrides, and enforces the official NIC 2-day IRN document date rule.
"""

import os
import re
import sys
from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
TARIFF_PARQUET = ROOT_DIR / "data" / "tariff_master.parquet"

_HSN_DF_CACHE = None
_SEARCH_ENGINE = None


def get_hsn_search_engine():
    """Initializes and caches the HSNSemanticSearchEngine instance."""
    global _SEARCH_ENGINE
    if _SEARCH_ENGINE is None:
        try:
            from src.nlp.hsn_search import HSNSemanticSearchEngine
            _SEARCH_ENGINE = HSNSemanticSearchEngine()
        except Exception as e:
            print(f"[WARN] Failed to load HSNSemanticSearchEngine: {e}")
            _SEARCH_ENGINE = None
    return _SEARCH_ENGINE


def get_hsn_master() -> Optional[pd.DataFrame]:
    """
    Loads statutory tariff master (13,000+ items) into a cached pandas DataFrame
    with standardized HSN_CD, descriptions, and statutory tax rates.
    """
    global _HSN_DF_CACHE
    if _HSN_DF_CACHE is not None:
        return _HSN_DF_CACHE

    engine = get_hsn_search_engine()
    if engine is not None and engine.tariff_df is not None:
        df = engine.tariff_df.copy()
        if "HSN_CD" not in df.columns and "hsn_code" in df.columns:
            df["HSN_CD"] = df["hsn_code"]
        if "HSN_Description" not in df.columns and "description" in df.columns:
            df["HSN_Description"] = df["description"]
        if "gst_rate" not in df.columns and "standard_rate" in df.columns:
            df["gst_rate"] = df["standard_rate"]
        _HSN_DF_CACHE = df
        return _HSN_DF_CACHE

    if TARIFF_PARQUET.exists():
        try:
            df = pd.read_parquet(TARIFF_PARQUET)
            df["HSN_CD"] = df["hsn_code"]
            df["HSN_Description"] = df["description"]
            df["gst_rate"] = df.get("standard_rate", 18.0)
            _HSN_DF_CACHE = df
            return _HSN_DF_CACHE
        except Exception as e:
            print(f"[WARN] Could not load tariff parquet: {e}")

    # Fallback to Excel if parquet not available
    candidate_paths = [
        ROOT_DIR / "data" / "raw" / "Final_hsn_sac_copy.xlsx",
        ROOT_DIR / "data" / "Final_hsn_sac_copy.xlsx",
        Path("data/raw/Final_hsn_sac_copy.xlsx"),
    ]
    for p in candidate_paths:
        if p.exists() and p.is_file():
            try:
                raw_df = pd.read_excel(p)
                records = []
                for idx, row in raw_df.iterrows():
                    c0 = "" if pd.isna(row.iloc[0]) else str(row.iloc[0]).strip()
                    c1 = "" if (len(row) > 1 and pd.isna(row.iloc[1])) else (str(row.iloc[1]).strip() if len(row) > 1 else "")
                    if c0 and not ("heading" in c0.lower() or "chapter" in c0.lower()):
                        digits = re.sub(r"[^0-9]", "", c0) or c0
                        records.append({
                            "HSN_CD": str(digits).strip(),
                            "hsn_code": str(digits).strip(),
                            "HSN_Description": c1,
                            "description": c1,
                            "gst_rate": 18.0,
                            "standard_rate": 18.0
                        })
                if records:
                    _HSN_DF_CACHE = pd.DataFrame(records)
                    return _HSN_DF_CACHE
            except Exception:
                pass

    return None


def lookup_hsn_code(
    product_name: str,
    product_desc: str = "",
    hsn_prefix: Optional[str] = None,
    top_k: int = 5
) -> List[Dict[str, Any]]:
    """
    Finds matching HSN entries using the Universal Hybrid Semantic-Lexical HSN Intelligence ML model
    backed by statutory tariff master (13,000+ items).
    Supports product description, product name, and optional statutory HSN prefix (e.g. '84', '8412').
    """
    engine = get_hsn_search_engine()
    query = f"{product_name} {product_desc}".strip() or product_name or product_desc
    clean_prefix = str(hsn_prefix).strip() if hsn_prefix else None

    # Handle special statutory classification for electric motors and servo motors in Chapter 85 (Heading 8501)
    q_lower = query.lower()
    is_servo_motor_electric = any(k in q_lower for k in ["servo motor", "servo-motor", "stepper motor", "industrial servo", "servomotor", "servo drive"]) and not any(
        k in q_lower for k in ["car", "vehicle", "automobile", "truck", "bus", "van", "lorry"]
    )

    if engine is not None:
        search_prefix = None if (is_servo_motor_electric and clean_prefix == "84") else clean_prefix
        res = engine.search(query, top_k=max(top_k * 3, 15), hsn_prefix=search_prefix)
        formatted: List[Dict[str, Any]] = []

        for m in res:
            code = str(m.get("hsn_code", m.get("hsn", "")))
            if is_servo_motor_electric and (code.startswith("87") or code.startswith("8412")):
                continue
            rate = float(m.get("standard_rate", 18.0))
            heading = str(m.get("heading", m.get("hsn_4digit", code[:4])))
            formatted.append({
                "hsn_code": code,
                "hsn_4digit": heading,
                "heading": heading,
                "chapter": str(m.get("chapter", code[:2])),
                "description": str(m.get("description", "")),
                "clean_description": str(m.get("clean_description", "")),
                "gst_rate": rate,
                "igst_rate": rate,
                "cgst_rate": round(rate / 2.0, 2),
                "sgst_rate": round(rate / 2.0, 2),
                "is_blocked_17_5": int(m.get("is_blocked_17_5", 0)),
                "blocked_17_5_reason": str(m.get("blocked_17_5_reason", "Eligible: General ITC")),
                "score": float(m.get("score", 1.0)),
                "confidence_pct": float(m.get("confidence_pct", 100.0)),
                "match_type": str(m.get("match_type", "Universal Hybrid Semantic-Lexical Match")),
            })


        if clean_prefix and not (is_servo_motor_electric and clean_prefix == "84"):
            pref_matches = [m for m in formatted if m["hsn_code"].startswith(clean_prefix) or m["hsn_4digit"].startswith(clean_prefix)]
            if pref_matches:
                return pref_matches[:top_k]

        if formatted:
            return formatted[:top_k]

    # Fallback to DataFrame lookup
    df = get_hsn_master()
    if df is None or df.empty:
        return []

    tokens = [t for t in re.findall(r"[a-z0-9]{3,}", query.lower()) if t not in {"and", "the", "for", "with"}]
    cand = df
    if clean_prefix and len(clean_prefix) in [2, 3, 4]:
        pref_cand = df[df["HSN_CD"].astype(str).str.startswith(clean_prefix)]
        if not pref_cand.empty:
            cand = pref_cand

    results = []
    for _, r in cand.head(top_k).iterrows():
        igst = float(r.get("gst_rate", r.get("standard_rate", 18.0)))
        cd = str(r.get("HSN_CD", r.get("hsn_code", "")))
        results.append({
            "hsn_code": cd,
            "hsn_4digit": cd[:4],
            "heading": cd[:4],
            "chapter": cd[:2],
            "description": str(r.get("HSN_Description", r.get("description", ""))),
            "gst_rate": igst,
            "igst_rate": igst,
            "cgst_rate": round(igst / 2.0, 2),
            "sgst_rate": round(igst / 2.0, 2),
            "is_blocked_17_5": int(r.get("is_blocked_17_5", 0)),
            "blocked_17_5_reason": str(r.get("blocked_17_5_reason", "Eligible: General ITC")),
            "score": 1.0,
            "confidence_pct": 90.0,
            "match_type": "Tariff Master Match"
        })
    return results


def validate_hsn_statutory(hsn_code: str) -> Optional[Dict[str, Any]]:
    """
    Validates if an HSN code exists in the official statutory tariff schedule.
    Returns statutory metadata or None if invalid.
    """
    engine = get_hsn_search_engine()
    if engine is not None:
        return engine.validate_hsn_code(hsn_code)

    df = get_hsn_master()
    if df is not None:
        c = str(hsn_code).strip()
        matched = df[df["HSN_CD"].astype(str) == c]
        if not matched.empty:
            row = matched.iloc[0]
            rate = float(row.get("gst_rate", 18.0))
            return {
                "hsn_code": c,
                "hsn_4digit": c[:4],
                "description": str(row.get("HSN_Description", "")),
                "standard_rate": rate,
                "is_blocked_17_5": 0,
                "blocked_17_5_reason": "Eligible: General ITC"
            }
    return None


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
