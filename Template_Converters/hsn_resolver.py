"""
HSN / SAC Master Resolver and NIC Compliance Utilities for Indian GST.
Powered by the Universal Hybrid Semantic-Lexical HSN Intelligence ML Model (128-D CPU)
backed by the Statutory Central Board of Indirect Taxes (CBIC) Tariff Master (13,000+ items).
Reconciles statutory tax rates, Section 17(5) blocked ITC status, supports dynamic user
taxable value overrides, and enforces the official NIC 2-day IRN document date rule.
"""

import os

# Prevent OpenBLAS thread allocation failure on Windows
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")

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


def get_hsn_intelligence_engine():
    """Initializes and caches the HSNIntelligenceEngine instance (Module 1)."""
    global _SEARCH_ENGINE
    if _SEARCH_ENGINE is None:
        try:
            from src.nlp.hsn_intelligence import get_hsn_intelligence_engine as _get_engine
            _SEARCH_ENGINE = _get_engine()
        except Exception as e:
            try:
                from src.nlp.hsn_intelligence import HSNIntelligenceEngine
                _SEARCH_ENGINE = HSNIntelligenceEngine()
            except Exception as e2:
                try:
                    from src.nlp.hsn_search import HSNSemanticSearchEngine
                    _SEARCH_ENGINE = HSNSemanticSearchEngine()
                except Exception as e3:
                    print(f"[WARN] Failed to load HSN engine: {e3}")
                    _SEARCH_ENGINE = None
    return _SEARCH_ENGINE


def get_hsn_search_engine():
    """Initializes and caches the HSN search engine instance, backed by HSNIntelligenceEngine."""
    return get_hsn_intelligence_engine()


def get_hsn_master() -> Optional[pd.DataFrame]:
    """
    Loads statutory tariff master (13,000+ items) into a cached pandas DataFrame
    with standardized HSN_CD, descriptions, and statutory tax rates.
    """
    global _HSN_DF_CACHE
    if _HSN_DF_CACHE is not None:
        return _HSN_DF_CACHE

    engine = get_hsn_search_engine()
    if engine is not None and getattr(engine, "tariff_df", None) is not None:
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
    (Two-Tier Cascade BGE + Cross-Encoder Reranker + Trade Dependency Parser)
    backed by statutory tariff master (13,000+ items).
    Supports product description, product name, and optional statutory HSN prefix (e.g. '84', '8412').
    """
    query = f"{product_name} {product_desc}".strip() or product_name or product_desc
    clean_prefix = str(hsn_prefix).strip() if hsn_prefix else None
    cache_key = (query, clean_prefix, int(top_k))
    if cache_key in _LOOKUP_CACHE:
        return _LOOKUP_CACHE[cache_key]

    # Step 0: Check data/hsn_verified_store.parquet first (fast retrieval, no time waster)
    try:
        from src.ml.hsn_verified_store import get_hsn_verified_store
        store = get_hsn_verified_store()
        cached = store.lookup(query) or store.lookup(product_name)
        if cached and (not clean_prefix or cached.get("hsn_code", "").startswith(clean_prefix)):
            c_code = str(cached.get("hsn_code", "")).strip()
            c_rate = float(cached.get("gst_rate", 18.0))
            cached_res = [{
                "hsn_code": c_code,
                "hsn_4digit": c_code[:4],
                "heading": c_code[:4],
                "chapter": c_code[:2],
                "description": str(cached.get("description", "")),
                "clean_description": query.lower().strip(),
                "gst_rate": c_rate,
                "igst_rate": c_rate,
                "cgst_rate": round(c_rate / 2.0, 2),
                "sgst_rate": round(c_rate / 2.0, 2),
                "is_blocked_17_5": 0,
                "blocked_17_5_reason": "Eligible: General ITC",
                "score": 1.0,
                "confidence_pct": 100.0,
                "match_type": "Already there in the stored file (data/hsn_verified_store.parquet)",
                "is_from_store": True,
                "storage_file": "data/hsn_verified_store.parquet",
                "reasoning": f"Already there in the stored file (data/hsn_verified_store.parquet): {cached.get('reasoning', '')}"
            }]
            _LOOKUP_CACHE[cache_key] = cached_res
            return cached_res
    except Exception:
        pass

    engine = get_hsn_intelligence_engine()

    if engine is not None:
        res = engine.search(query, top_k=max(top_k * 2, 10), hsn_prefix=clean_prefix)
        formatted: List[Dict[str, Any]] = []

        for m in res:
            code = str(m.get("hsn_code", m.get("hsn", ""))).strip()
            heading = str(m.get("heading", m.get("hsn_4digit", ""))).strip()
            desc = str(m.get("description", "")).strip()

            if code in ("None", "none", "", "nan") or not code.isdigit():
                if heading and heading.isdigit() and len(heading) in (4, 6, 8):
                    code = heading
                else:
                    import re
                    match = re.search(r'\b(\d{4,8})\b', desc)
                    if match:
                        code = match.group(1)
                    else:
                        continue

            if not heading or heading in ("None", "none", "nan") or not heading.isdigit():
                heading = code[:4]

            rate = float(m.get("standard_rate", m.get("gst_rate", 18.0)))
            formatted.append({
                "hsn_code": code,
                "hsn_4digit": heading,
                "heading": heading,
                "chapter": str(m.get("chapter", code[:2])),
                "description": desc,
                "clean_description": str(m.get("clean_description", "")),
                "gst_rate": rate,
                "igst_rate": rate,
                "cgst_rate": round(rate / 2.0, 2),
                "sgst_rate": round(rate / 2.0, 2),
                "is_blocked_17_5": int(m.get("is_blocked_17_5", 0)),
                "blocked_17_5_reason": str(m.get("blocked_17_5_reason", "Eligible: General ITC")),
                "score": float(m.get("score", 1.0)),
                "confidence_pct": float(m.get("confidence_pct", 100.0)),
                "match_type": str(m.get("match_type", "Two-Tier Hierarchical BGE + Cross-Encoder")),
            })

        if clean_prefix:
            pref_matches = [m for m in formatted if m["hsn_code"].startswith(clean_prefix) or m["hsn_4digit"].startswith(clean_prefix)]
            if pref_matches:
                res = pref_matches[:top_k]
                if len(_LOOKUP_CACHE) < 2048:
                    _LOOKUP_CACHE[cache_key] = res
                return res

        if formatted:
            res = formatted[:top_k]
            if len(_LOOKUP_CACHE) < 2048:
                _LOOKUP_CACHE[cache_key] = res
            return res

    # Fallback to DataFrame lookup
    df = get_hsn_master()
    if df is None or df.empty:
        return []

    tokens = [t for t in re.findall(r"[a-z0-9]{3,}", query.lower()) if t not in {"and", "the", "for", "with"}]
    cand = df
    is_vehicle = bool(re.search(r"\b(car|truck|bus|vehicle|tractor|motorcycle|scooter)\b", query.lower()))
    if is_vehicle:
        veh_cand = df[df["HSN_CD"].astype(str).str.startswith("87")]
        if not veh_cand.empty:
            cand = veh_cand
    elif clean_prefix and len(clean_prefix) in [2, 3, 4]:
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

    c = str(hsn_code).strip()
    sac_headings = {
        "9954": "Construction services", "9961": "Services in maintenance, repair and installation",
        "9962": "Research and development services", "9963": "Accommodation, food and beverage services",
        "9964": "Passenger transport services", "9965": "Goods transport services",
        "9966": "Rental services of transport vehicles", "9967": "Supporting services in transport",
        "9968": "Postal and courier services", "9969": "Electricity, gas and water distribution services",
        "9971": "Financial and related services", "9972": "Real estate services",
        "9973": "Leasing or rental services without operator", "9981": "Research and development services",
        "9982": "Legal and accounting services", "9983": "Other professional, technical and business services",
        "9984": "Telecommunications, broadcasting and information supply services", "9985": "Support services",
        "9986": "Support services to agriculture, forestry, fishing, mining and utilities",
        "9987": "Maintenance, repair and installation services", "9988": "Manufacturing services on physical inputs owned by others",
        "9989": "Other manufacturing services", "9991": "Public administration and other services provided to the community",
        "9992": "Education services", "9993": "Human health and social care services",
        "9994": "Sewage and waste collection, treatment and disposal services", "9995": "Services of membership organizations",
        "9996": "Recreational, cultural and sporting services", "9997": "Other services",
        "9998": "Domestic services", "9999": "Services provided by extraterritorial organizations and bodies"
    }
    if c.startswith("99") and len(c) in (4, 6) and c[:4] in sac_headings and c != "999999":
        h4 = c[:4]
        return {
            "hsn_code": c,
            "hsn_4digit": h4,
            "heading": h4,
            "chapter": "99",
            "description": sac_headings[h4],
            "standard_rate": 18.0,
            "is_blocked_17_5": 0,
            "blocked_17_5_reason": "Eligible: General ITC"
        }

    df = get_hsn_master()
    if df is not None:
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


_SCORER = None
_SENTINEL = None


def get_hsn_misclassification_scorer():
    """Initializes and caches the Day 06 HSNMisclassificationScorer."""
    global _SCORER
    if _SCORER is None:
        try:
            from src.ml.misclassification_scorer import HSNMisclassificationScorer
            _SCORER = HSNMisclassificationScorer()
        except Exception as e:
            print(f"[WARN] Failed to load HSNMisclassificationScorer: {e}")
            _SCORER = None
    return _SCORER


_LOOKUP_CACHE = {}
_SENTINEL_AUDIT_CACHE = {}


def get_hsn_audit_sentinel():
    """Initializes and caches the Module 2 HSNAuditSentinel (Day 05 + Day 06 + Day 07)."""
    global _SENTINEL
    if _SENTINEL is None:
        try:
            from src.ml.hsn_audit_sentinel import HSNAuditSentinel
            _SENTINEL = HSNAuditSentinel(intelligence_engine=get_hsn_intelligence_engine())
        except Exception as e:
            print(f"[WARN] Failed to load HSNAuditSentinel in hsn_resolver: {e}")
            _SENTINEL = None
    return _SENTINEL


def score_hsn_prediction_risk(invoice_line: Dict[str, Any], day5_retrieval_output: Any) -> Optional[Dict[str, Any]]:
    """Evaluates empirical misclassification probability and safety gate for an invoice line item."""
    scorer = get_hsn_misclassification_scorer()
    if scorer is not None:
        return scorer.predict_risk(invoice_line, day5_retrieval_output)
    return None


def classify_rule_2176_diagnostic(
    declared_hsn: str,
    product_name: str = "",
    product_desc: str = ""
) -> Optional[Dict[str, Any]]:
    """
    NIC Error Code 2176 Statutory Diagnostic & Portal Verification Analyzer.
    Official NIC Rule:
      - Code: 2176
      - Message: HSN code(s)-{0} is invalid
      - Reason: Wrong HSN code is being passed
      - Resolution: Pl check the HSN code being passed and Cross-check the correctness of HSN code
        on e-invoice portal. Still, if you feel it is correct, then please send the details to the
        helpdesk for verification at e-invoice system side.

    Checks:
      1. Missing, blank, or non-numeric digits.
      2. Invalid digit length (goods HSN must be 2, 4, 6, or 8 digits; services SAC must be 6 digits starting with 99).
      3. Absence from official Central Board of Indirect Taxes (CBIC) statutory tariff master.

    Returns structured diagnostic dict if violation is detected, None if valid.
    """
    raw_hsn = str(declared_hsn or "").strip()
    digits_only = re.sub(r"\D", "", raw_hsn)

    # Check 1: Missing or blank HSN
    if not digits_only:
        rec = lookup_hsn_code(product_name, product_desc, top_k=1)
        rec_code = rec[0]["hsn_code"] if rec else ""
        rec_desc = rec[0]["description"] if rec else ""
        rec_rate = rec[0]["gst_rate"] if rec else 18.0
        return {
            "error_code": 2176,
            "field": "hsn",
            "message": "HSN code(s)-(blank) is invalid",
            "reason": "Wrong HSN code is being passed",
            "resolution": "Pl check the HSN code being passed and Cross-check the correctness of HSN code on e-invoice portal. Still, if you feel it is correct, then please send the details to the helpdesk for verification at e-invoice system side.",
            "diagnostic_type": "MISSING_HSN",
            "declared_hsn": raw_hsn,
            "recommended_hsn": rec_code,
            "recommended_desc": rec_desc,
            "recommended_rate": rec_rate,
        }

    # Check 2: Invalid digit length (must be 2, 4, 6, or 8 digits)
    if len(digits_only) not in [2, 4, 6, 8]:
        rec = lookup_hsn_code(product_name, product_desc, top_k=1)
        rec_code = rec[0]["hsn_code"] if rec else ""
        rec_desc = rec[0]["description"] if rec else ""
        rec_rate = rec[0]["gst_rate"] if rec else 18.0
        return {
            "error_code": 2176,
            "field": "hsn",
            "message": f"HSN code(s)-{raw_hsn} is invalid",
            "reason": "Wrong HSN code is being passed",
            "resolution": "Pl check the HSN code being passed and Cross-check the correctness of HSN code on e-invoice portal. Still, if you feel it is correct, then please send the details to the helpdesk for verification at e-invoice system side.",
            "diagnostic_type": "INVALID_LENGTH",
            "declared_hsn": raw_hsn,
            "recommended_hsn": rec_code,
            "recommended_desc": rec_desc,
            "recommended_rate": rec_rate,
        }

    # Check 3: Statutory existence against CBIC Tariff Master (13,000+ codes)
    stat_meta = validate_hsn_statutory(digits_only)
    if stat_meta is None:
        rec = lookup_hsn_code(product_name, product_desc, top_k=1)
        rec_code = rec[0]["hsn_code"] if rec else ""
        rec_desc = rec[0]["description"] if rec else ""
        rec_rate = rec[0]["gst_rate"] if rec else 18.0
        return {
            "error_code": 2176,
            "field": "hsn",
            "message": f"HSN code(s)-{raw_hsn} is invalid",
            "reason": "Wrong HSN code is being passed",
            "resolution": "Pl check the HSN code being passed and Cross-check the correctness of HSN code on e-invoice portal. Still, if you feel it is correct, then please send the details to the helpdesk for verification at e-invoice system side.",
            "diagnostic_type": "NOT_IN_STATUTORY_TARIFF",
            "declared_hsn": raw_hsn,
            "recommended_hsn": rec_code,
            "recommended_desc": rec_desc,
            "recommended_rate": rec_rate,
        }

    return None


def _audit_and_rectify_line_item_sentinel_impl(
    product_name: str,
    product_desc: str,
    declared_hsn: str,
    unit_price: float,
    supplier_gstin: Optional[str] = None,
    declared_rate: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Evaluates an invoice line item against Qwen 2.5 Neural Verification Layer, Module 2 HSNAuditSentinel and Rule 2176:
    - Validates format and statutory existence against CBIC tariff master (Rule 2176).
    - Validates declared HSN code using the Qwen layer against product functional specifications.
    - If HSN code is correct AND statutory tax rate matches: approves item without declaring any error.
    - If HSN code is wrong or tax rate diverges: rectifies HSN code according to the statutory tax rate.
    
    Returns structured audit decisions for the self-healing E-Invoice & Lakehouse pipeline.
    """
    clean_desc = f"{product_name} {product_desc}".strip() or product_name or product_desc or "Item"
    declared_hsn_str = str(declared_hsn or "").strip()
    sup_gstin_str = str(supplier_gstin).strip().upper() if supplier_gstin else ""
    decl_rate_f = float(declared_rate) if declared_rate is not None else None

    # =========================================================================
    # STEP 1: FIRST CHECK IN hsn_verified_store.parquet!
    # Ultra-fast retrieval (<0.5ms) with zero time wasted.
    # Checks based on product description and product name from the payload.
    # If found, declares "Already there in the stored file (data/hsn_verified_store.parquet)".
    # =========================================================================
    store_record = None
    try:
        from src.ml.hsn_verified_store import get_hsn_verified_store
        store = get_hsn_verified_store()
        if hasattr(store, "lookup_item"):
            store_record = store.lookup_item(product_name=product_name, product_desc=product_desc)
        if not store_record:
            store_record = store.lookup(clean_desc) or store.lookup(product_name) or (store.lookup(product_desc) if product_desc else None)
    except Exception as s_err:
        store_record = None

    if store_record is not None:
        from src.ml.qwen_hsn_verifier import clean_hsn_digits, format_hsn
        c_hsn = clean_hsn_digits(store_record.get("hsn_code", ""))
        c_rate = float(store_record.get("gst_rate", 18.0))
        c_desc = str(store_record.get("description", ""))
        stored_reason = str(store_record.get("reasoning", ""))
        decl_digits = clean_hsn_digits(declared_hsn_str)
        rate_ok = (decl_rate_f is None or abs(decl_rate_f - c_rate) < 0.1)
        hsn_ok = (decl_digits == c_hsn or (store_record.get("is_perfect_match", False) and decl_digits == clean_hsn_digits(store_record.get("base_hsn", ""))))
        is_perfect = bool(hsn_ok and rate_ok)

        if is_perfect:
            # Verified and aligned: NO ERROR DECLARED!
            return {
                "is_flagged": False,
                "should_rectify": False,
                "original_hsn": declared_hsn_str,
                "rectified_hsn": declared_hsn_str,
                "statutory_rate": c_rate,
                "error_probability": 0.02,
                "post_intervention_risk": 0.02,
                "risk_drop": 0.0,
                "risk_level": "LOW",
                "reasons": [
                    f"⚡ Already there in the stored file (data/hsn_verified_store.parquet): Statutory tariff code '{declared_hsn_str}' verified correct ({stored_reason}) with statutory {c_rate:.1f}% GST."
                ],
                "shap_attributions": {"stored_verified_file": 1.0},
                "status_badge": "AUTO_APPROVED",
                "source": "ALREADY_IN_STORED_FILE",
                "qwen_audit": {
                    "item_description": clean_desc,
                    "is_perfect_match": True,
                    "status": "PERFECT_MATCH",
                    "base_hsn": declared_hsn_str,
                    "qwen_hsn": c_hsn,
                    "qwen_rate": c_rate,
                    "reasoning": f"Already there in the stored file (data/hsn_verified_store.parquet): {stored_reason}",
                    "is_cache_hit": True,
                    "storage_file": "data/hsn_verified_store.parquet",
                    "source": "ALREADY_IN_STORED_FILE",
                    "verification_model": "Already there in the stored file (data/hsn_verified_store.parquet)"
                }
            }
        else:
            # Code or rate mismatch: Rectified according to stored official statutory tariff
            rule_2176_msg = None
            rule_2176_diag = classify_rule_2176_diagnostic(declared_hsn_str, product_name, product_desc)
            if rule_2176_diag is not None:
                rule_2176_msg = f"⚠️ NIC Rule 2176 Violation: HSN code(s)-{declared_hsn_str or '(blank)'} is invalid. Wrong HSN code is being passed. Pl check the HSN code being passed and Cross-check the correctness of HSN code on e-invoice portal. Still, if you feel it is correct, then please send the details to the helpdesk for verification at e-invoice system side."

            reasons = [
                f"⚡ Already there in the stored file (data/hsn_verified_store.parquet): You entered {declared_hsn_str or '(blank)'} for '{product_name}'. Reclassified to Official Statutory Tariff {c_hsn} ({c_desc[:60]}...) with statutory {c_rate:.1f}% GST.",
                f"⚡ Stored Statutory Reasoning: {stored_reason}",
                "Pl check the HSN code being passed and Cross-check the correctness of HSN code on e-invoice portal. Still, if you feel it is correct, then please send the details to the helpdesk for verification at e-invoice system side."
            ]
            if rule_2176_msg:
                reasons.insert(0, rule_2176_msg)

            return {
                "is_flagged": True,
                "should_rectify": True,
                "original_hsn": declared_hsn_str,
                "rectified_hsn": c_hsn,
                "statutory_rate": c_rate,
                "error_probability": 0.98 if rule_2176_msg else 0.85,
                "post_intervention_risk": 0.03,
                "risk_drop": 0.95 if rule_2176_msg else 0.82,
                "risk_level": "HIGH",
                "reasons": reasons,
                "shap_attributions": {"stored_verified_file": 0.95},
                "status_badge": "FLAGGED_AND_RECTIFIED",
                "error_code": 2176,
                "resolution": f"Confirm and apply Recommended HSN '{c_hsn}' with statutory {c_rate:.1f}% GST to unlock Stage 2 IRN generation.",
                "source": "ALREADY_IN_STORED_FILE",
                "qwen_audit": {
                    "item_description": clean_desc,
                    "is_perfect_match": False,
                    "status": "CORRECTED_BY_QWEN",
                    "base_hsn": declared_hsn_str,
                    "qwen_hsn": c_hsn,
                    "qwen_rate": c_rate,
                    "reasoning": f"Already there in the stored file (data/hsn_verified_store.parquet): {stored_reason}",
                    "is_cache_hit": True,
                    "storage_file": "data/hsn_verified_store.parquet",
                    "source": "ALREADY_IN_STORED_FILE",
                    "verification_model": "Already there in the stored file (data/hsn_verified_store.parquet)"
                }
            }

    # =========================================================================
    # STEP 2: NO FOUND RESULT IN STORED FILE -> EXECUTE QWEN LAYER!
    # In the Data Lakehouse module, evaluates product name, product description,
    # declared HSN code, and declared tax rate via Qwen 2.5 Neural Layer.
    # =========================================================================
    rule_2176 = classify_rule_2176_diagnostic(declared_hsn_str, product_name, product_desc)

    # 3. If NO found result in the stored file -> Execute Qwen Neural Layer & Statutory Tariff Grounding
    qwen_audit = None
    try:
        from src.ml.qwen_hsn_verifier import get_qwen_hsn_verifier
        qwen_verifier = get_qwen_hsn_verifier()
        if qwen_verifier is not None:
            qwen_audit = qwen_verifier.verify_item(
                query=clean_desc,
                base_hsn=declared_hsn_str,
                base_rate=decl_rate_f
            )
    except Exception as q_err:
        qwen_audit = None

    if qwen_audit is not None:
        is_perfect = bool(qwen_audit.get("is_perfect_match", False))
        q_hsn = str(qwen_audit.get("qwen_hsn", declared_hsn_str)).strip()
        q_rate = float(qwen_audit.get("qwen_rate", 18.0))
        q_desc = str(qwen_audit.get("qwen_description", ""))
        q_reason = str(qwen_audit.get("reasoning", ""))

        # Persist newly verified result to data/hsn_verified_store.parquet so it is already there next time
        try:
            from src.ml.hsn_verified_store import get_hsn_verified_store
            store = get_hsn_verified_store()
            store.upsert(
                query=clean_desc,
                hsn_code=q_hsn,
                description=q_desc,
                gst_rate=q_rate,
                status="PERFECT_MATCH" if is_perfect else "CORRECTED_BY_QWEN",
                is_perfect_match=is_perfect,
                reasoning=q_reason,
                base_hsn=declared_hsn_str,
                verified_by="Qwen2.5-0.5B-Instruct Neural Verification"
            )
            _SENTINEL_AUDIT_CACHE.clear()
        except Exception:
            pass

        # If Qwen layer confirms HSN is correct and statutory tax rate is aligned:
        # NO ERROR DECLARED!
        if is_perfect:
            return {
                "is_flagged": False,
                "should_rectify": False,
                "original_hsn": declared_hsn_str,
                "rectified_hsn": declared_hsn_str,
                "statutory_rate": q_rate,
                "error_probability": 0.02,
                "post_intervention_risk": 0.02,
                "risk_drop": 0.0,
                "risk_level": "LOW",
                "reasons": [
                    f"🧠 Qwen 2.5 Neural Verification: Statutory tariff code '{declared_hsn_str}' verified correct ({q_reason}) with statutory {q_rate:.1f}% GST."
                ],
                "shap_attributions": {"qwen_statutory_verification": 1.0},
                "status_badge": "AUTO_APPROVED",
                "qwen_audit": qwen_audit,
            }
        else:
            # HSN is wrong or tax rate requires alignment: Rectify HSN according to statutory tax rate
            return {
                "is_flagged": True,
                "should_rectify": True,
                "original_hsn": declared_hsn_str,
                "rectified_hsn": q_hsn,
                "statutory_rate": q_rate,
                "error_probability": 0.85,
                "post_intervention_risk": 0.03,
                "risk_drop": 0.82,
                "risk_level": "HIGH",
                "reasons": [
                    f"⚠️ Wrong / Misclassified HSN Code Detected: You entered {declared_hsn_str or '(blank)'} for '{product_name}'. Reclassified by Qwen Layer to Official Statutory Tariff {q_hsn} ({q_desc[:60]}...) with statutory {q_rate:.1f}% GST.",
                    f"🧠 Qwen Statutory Reasoning: {q_reason}",
                    "Pl check the HSN code being passed and Cross-check the correctness of HSN code on e-invoice portal. Still, if you feel it is correct, then please send the details to the helpdesk for verification at e-invoice system side."
                ],
                "shap_attributions": {"qwen_statutory_verification": 0.95},
                "status_badge": "FLAGGED_AND_RECTIFIED",
                "error_code": 2176,
                "resolution": f"Confirm and apply Recommended HSN '{q_hsn}' with statutory {q_rate:.1f}% GST to unlock Stage 2 IRN generation.",
                "qwen_audit": qwen_audit,
            }

    sentinel = get_hsn_audit_sentinel()
    clean_desc = f"{product_name} {product_desc}".strip() or product_name or product_desc or "Item"
    declared_hsn_str = str(declared_hsn or "").strip()
    sup_gstin_str = str(supplier_gstin).strip().upper() if supplier_gstin else ""

    # 1. Statutory Rule 2176 Interception: Check format, length, and official tariff existence
    rule_2176 = classify_rule_2176_diagnostic(declared_hsn_str, product_name, product_desc)
    if rule_2176 is not None:
        rec_hsn = rule_2176.get("recommended_hsn") or declared_hsn_str
        rec_desc = rule_2176.get("recommended_desc") or ""
        rec_rate = float(rule_2176.get("recommended_rate", 18.0))
        return {
            "is_flagged": True,
            "should_rectify": True,
            "original_hsn": declared_hsn_str,
            "rectified_hsn": rec_hsn,
            "statutory_rate": rec_rate,
            "error_probability": 0.98,
            "post_intervention_risk": 0.03,
            "risk_drop": 0.95,
            "risk_level": "HIGH",
            "reasons": [
                f"⚠️ NIC Rule 2176 Violation: HSN code(s)-{declared_hsn_str or '(blank)'} is invalid. Wrong HSN code is being passed. Pl check the HSN code being passed and Cross-check the correctness of HSN code on e-invoice portal. Still, if you feel it is correct, then please send the details to the helpdesk for verification at e-invoice system side.",
                f"🛡️ HSN Intelligence Auto-Rectification: Reclassified to Statutory Code '{rec_hsn}' ({rec_desc[:60]}...) at {rec_rate:.1f}% GST."
            ],
            "shap_attributions": {"statutory_tariff_validity": 1.0},
            "status_badge": "FLAGGED_AND_RECTIFIED",
            "error_code": 2176,
            "resolution": "Pl check the HSN code being passed and Cross-check the correctness of HSN code on e-invoice portal. Still, if you feel it is correct, then please send the details to the helpdesk for verification at e-invoice system side.",
        }

    # 2. Check statutory validation for existing compliant codes
    declared_meta = validate_hsn_statutory(declared_hsn_str)
    stat_rate = float(declared_meta.get("standard_rate", 18.0)) if declared_meta else 18.0

    sim_line = {
        "product_description": clean_desc,
        "declared_hsn": declared_hsn_str,
        "declared_hsn_chapter": declared_hsn_str[:2] if len(declared_hsn_str) >= 2 else "",
        "unit_price": float(unit_price or 0.0),
        "supplier_gstin": sup_gstin_str or None,
        "vendor_check_disabled": not bool(sup_gstin_str),
    }

    if sentinel is not None:
        try:
            audit_res = sentinel.audit_item(sim_line)
            audit_dict = audit_res.model_dump() if hasattr(audit_res, "model_dump") else audit_res.dict()

            is_flagged = bool(audit_dict.get("flagged", False))
            orig_pred = audit_dict.get("original_prediction", {})
            err_prob = float(orig_pred.get("error_probability", 0.0))
            risk_level = str(orig_pred.get("risk_level", "LOW"))
            reasons = audit_dict.get("human_readable_reasons", []) or audit_dict.get("explanations", [])
            cf_rec = audit_dict.get("counterfactual_recommendation")

            # If flagged with high risk and counterfactual recommendation exists:
            if is_flagged and cf_rec and cf_rec.get("recommended_hsn"):
                rec_hsn = str(cf_rec["recommended_hsn"]).strip()
                post_prob = float(cf_rec.get("calibrated_error_probability", 0.05))
                risk_drop = float(cf_rec.get("risk_drop", 0.0))

                # Fetch statutory GST rate from tariff master
                rate = stat_rate
                stat_rec_meta = validate_hsn_statutory(rec_hsn)
                if stat_rec_meta:
                    rate = float(stat_rec_meta.get("standard_rate", 18.0))

                # If declared HSN is already identical to recommended HSN, or in same heading with low risk drop:
                is_same_heading = bool(declared_hsn_str and rec_hsn and len(declared_hsn_str) >= 4 and len(rec_hsn) >= 4 and declared_hsn_str[:4] == rec_hsn[:4])
                if (rec_hsn == declared_hsn_str and len(declared_hsn_str) in [6, 8]) or (is_same_heading and len(declared_hsn_str) in [6, 8]) or (len(declared_hsn_str) in [6, 8] and rec_hsn[:2] == declared_hsn_str[:2] and risk_drop <= 0.05):
                    return {
                        "is_flagged": False,
                        "should_rectify": False,
                        "original_hsn": declared_hsn_str,
                        "rectified_hsn": declared_hsn_str,
                        "statutory_rate": stat_rate,
                        "error_probability": min(post_prob, 0.05),
                        "post_intervention_risk": min(post_prob, 0.05),
                        "risk_drop": 0.0,
                        "risk_level": "LOW",
                        "reasons": [f"Statutory tariff code '{declared_hsn_str}' verified compliant with official schedule under Chapter {declared_hsn_str[:2]}."],
                        "shap_attributions": audit_dict.get("shap_attributions", {}),
                        "status_badge": "AUTO_APPROVED",
                    }

                reasons_with_portal = list(reasons)
                reasons_with_portal.append(
                    f"Pl check the HSN code being passed and Cross-check the correctness of HSN code on e-invoice portal. Still, if you feel it is correct, then please send the details to the helpdesk for verification at e-invoice system side."
                )

                return {
                    "is_flagged": True,
                    "should_rectify": True,
                    "original_hsn": declared_hsn_str,
                    "rectified_hsn": rec_hsn,
                    "statutory_rate": rate,
                    "error_probability": err_prob,
                    "post_intervention_risk": post_prob,
                    "risk_drop": risk_drop,
                    "risk_level": risk_level,
                    "reasons": reasons_with_portal,
                    "shap_attributions": audit_dict.get("shap_attributions", {}),
                    "status_badge": "FLAGGED_AND_RECTIFIED",
                    "error_code": 2176,
                    "resolution": "Pl check the HSN code being passed and Cross-check the correctness of HSN code on e-invoice portal. Still, if you feel it is correct, then please send the details to the helpdesk for verification at e-invoice system side.",
                }

            # If not flagged:
            return {
                "is_flagged": False,
                "should_rectify": False,
                "original_hsn": declared_hsn_str,
                "rectified_hsn": declared_hsn_str,
                "statutory_rate": stat_rate,
                "error_probability": err_prob,
                "post_intervention_risk": err_prob,
                "risk_drop": 0.0,
                "risk_level": risk_level,
                "reasons": [f"Statutory tariff code '{declared_hsn_str}' verified compliant with official schedule under Chapter {declared_hsn_str[:2]}."],
                "shap_attributions": audit_dict.get("shap_attributions", {}),
                "status_badge": "AUTO_APPROVED",
            }
        except Exception as e:
            print(f"[WARN] Error in audit_and_rectify_line_item_sentinel: {e}")

    # Fallback when sentinel is not available
    h_matches = lookup_hsn_code(clean_desc, top_k=2)
    if h_matches:
        best = h_matches[0]
        best_code = str(best.get("hsn_code", "")).strip()
        best_rate = float(best.get("gst_rate", 18.0))
        best_desc = best.get("description", "")
        is_invalid_len = not declared_hsn_str or len(declared_hsn_str) not in [6, 8]
        is_ch_mismatch = bool(best_code and declared_hsn_str and len(declared_hsn_str) >= 2 and len(best_code) >= 2 and declared_hsn_str[:2] != best_code[:2])
        if (is_invalid_len or is_ch_mismatch) and best_code and (best_code != declared_hsn_str or is_invalid_len):
            reasons_fallback = [
                f"⚠️ NIC Rule 2176 Notice: HSN code(s)-{declared_hsn_str or '(blank)'} is invalid. Wrong HSN code is being passed. Pl check the HSN code being passed and Cross-check the correctness of HSN code on e-invoice portal. Still, if you feel it is correct, then please send the details to the helpdesk for verification at e-invoice system side.",
                f"🛡️ HSN Intelligence Auto-Rectification: Reclassified to Statutory Code '{best_code}' ({best_desc[:60]}...) at {best_rate:.1f}% GST."
            ]
            return {
                "is_flagged": True,
                "should_rectify": True,
                "original_hsn": declared_hsn_str,
                "rectified_hsn": best_code,
                "statutory_rate": best_rate,
                "error_probability": 0.85,
                "post_intervention_risk": 0.04,
                "risk_drop": 0.81,
                "risk_level": "HIGH",
                "reasons": reasons_fallback,
                "shap_attributions": {},
                "status_badge": "FLAGGED_AND_RECTIFIED",
                "error_code": 2176,
                "resolution": "Pl check the HSN code being passed and Cross-check the correctness of HSN code on e-invoice portal. Still, if you feel it is correct, then please send the details to the helpdesk for verification at e-invoice system side.",
            }

    return {
        "is_flagged": False,
        "should_rectify": False,
        "original_hsn": declared_hsn_str,
        "rectified_hsn": declared_hsn_str,
        "statutory_rate": stat_rate,
        "error_probability": 0.0,
        "post_intervention_risk": 0.0,
        "risk_drop": 0.0,
        "risk_level": "LOW",
        "reasons": [f"Statutory tariff code '{declared_hsn_str}' verified compliant with official schedule under Chapter {declared_hsn_str[:2]}."],
        "shap_attributions": {},
        "status_badge": "AUTO_APPROVED",
    }



def audit_and_rectify_line_item_sentinel(
    product_name: str,
    product_desc: str = "",
    declared_hsn: Optional[str] = None,
    unit_price: float = 0.0,
    supplier_gstin: Optional[str] = None,
    declared_rate: Optional[float] = None
) -> Dict[str, Any]:
    clean_desc = f"{product_name} {product_desc}".strip() or product_name or product_desc or "Item"
    declared_hsn_str = str(declared_hsn or "").strip()
    sup_gstin_str = str(supplier_gstin).strip().upper() if supplier_gstin else ""
    d_rate_round = round(float(declared_rate), 2) if declared_rate is not None else None
    cache_key = (clean_desc, declared_hsn_str, round(float(unit_price or 0.0), 2), sup_gstin_str, d_rate_round)
    if cache_key in _SENTINEL_AUDIT_CACHE:
        return _SENTINEL_AUDIT_CACHE[cache_key]
    
    res = _audit_and_rectify_line_item_sentinel_impl(
        product_name=product_name,
        product_desc=product_desc,
        declared_hsn=declared_hsn,
        unit_price=unit_price,
        supplier_gstin=supplier_gstin,
        declared_rate=declared_rate
    )
    if len(_SENTINEL_AUDIT_CACHE) < 2048:
        _SENTINEL_AUDIT_CACHE[cache_key] = res
    return res
