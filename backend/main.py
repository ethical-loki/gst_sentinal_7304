"""
Module: backend/main.py
Description: Complete FastAPI backend serving Excel-based HSN/SAC search with
             dtype=str to preserve leading zeros, dynamic pathing, and modern UI.
"""

import os
import json
import time
from pathlib import Path
from typing import Optional, List, Dict, Any, Union, Tuple
import numpy as np
import pandas as pd
from fastapi import FastAPI, Query, HTTPException, Request, Response, UploadFile, File, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

# Define root directory based on backend/main.py location
BASE_DIR = Path(__file__).resolve().parent.parent

app = FastAPI(title="GST_Sentinel HSN Auto-Suggest API")

# Serve /static directory for CSS/JS/HTML assets
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "static")
STATIC_DIR_ABS = os.path.abspath(STATIC_DIR)

if os.path.isdir(STATIC_DIR_ABS):
    app.mount("/static", StaticFiles(directory=STATIC_DIR_ABS), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- CONFIGURABLE FILE PATH ---
# Files should be placed in data/raw/ or data/
RAW_DATA_DIR = os.path.join("data", "raw")

# 👉 Updated to latest HSN/SAC master file
EXCEL_FILENAME = "Final_hsn_sac_copy.xlsx"

# Full dynamic path computation
HSN_EXCEL_PATH = os.path.join(RAW_DATA_DIR, EXCEL_FILENAME)


def get_hsn_df():
    """Load the HSN Excel file into memory via converter_service (cached after first read)."""
    try:
        from backend.converter_service import get_hsn_dataframe
        return get_hsn_dataframe()
    except Exception as e:
        print(f"[ERROR] Error loading HSN Excel file via converter_service: {str(e)}")
        return None


@app.on_event("startup")
async def preload_hsn_cache():
    """Pre-load HSN DataFrame into memory on server startup so first search is instant."""
    result = get_hsn_df()
    if result is not None:
        df, hsn_col, desc_col = result
        print(f"[OK] HSN data preloaded: {len(df)} rows | Columns: {hsn_col}, {desc_col}")
    else:
        print("[WARN] HSN Excel file not found at startup - will retry on first search.")


_hsn_search_engine = None
_hsn_misclass_scorer = None
_hsn_audit_advisor = None


def get_hsn_search_engine():
    global _hsn_search_engine
    if _hsn_search_engine is None:
        try:
            from src.nlp.hsn_search import HSNSearchEngine
            _hsn_search_engine = HSNSearchEngine()
            print("[OK] HSNSearchEngine initialized with Contrastive MLP (128-D CPU)")
        except Exception as e:
            _hsn_search_engine = None
    return _hsn_search_engine


def get_hsn_misclass_scorer():
    global _hsn_misclass_scorer
    if _hsn_misclass_scorer is None:
        try:
            from src.ml.misclassification_scorer import HSNMisclassificationScorer
            _hsn_misclass_scorer = HSNMisclassificationScorer()
            print("[OK] HSNMisclassificationScorer initialized with Platt Calibrator")
        except Exception as e:
            print(f"[WARN] Failed to load HSNMisclassificationScorer in backend/main.py: {e}")
            _hsn_misclass_scorer = None
    return _hsn_misclass_scorer


_hsn_intelligence_engine = None
_hsn_audit_sentinel = None


def get_hsn_intelligence_engine():
    global _hsn_intelligence_engine
    if _hsn_intelligence_engine is None:
        try:
            from src.nlp.hsn_intelligence import HSNIntelligenceEngine
            _hsn_intelligence_engine = HSNIntelligenceEngine()
            print("[OK] HSNIntelligenceEngine (Module 1: Pure Day 05 Semantic Intelligence) initialized")
        except Exception as e:
            print(f"[WARN] Failed to load HSNIntelligenceEngine: {e}")
            _hsn_intelligence_engine = None
    return _hsn_intelligence_engine


def get_hsn_audit_sentinel():
    global _hsn_audit_sentinel
    if _hsn_audit_sentinel is None:
        try:
            from src.ml.hsn_audit_sentinel import HSNAuditSentinel
            _hsn_audit_sentinel = HSNAuditSentinel()
            print("[OK] HSNAuditSentinel (Module 2: Day 05 + Day 06 + Day 07 Compliance Sentinel) initialized")
        except Exception as e:
            print(f"[WARN] Failed to load HSNAuditSentinel: {e}")
            _hsn_audit_sentinel = None
    return _hsn_audit_sentinel


def get_hsn_audit_advisor():
    global _hsn_audit_advisor
    if _hsn_audit_advisor is None:
        try:
            from src.ml.audit_advisor import HSNAuditAdvisor
            _hsn_audit_advisor = HSNAuditAdvisor()
            print("[OK] HSNAuditAdvisor initialized with Tree SHAP and Counterfactual Generator")
        except Exception as e:
            print(f"[WARN] Failed to load HSNAuditAdvisor in backend/main.py: {e}")
            _hsn_audit_advisor = None
    return _hsn_audit_advisor


@app.get("/api/v1/hsn-intelligence/search")
async def search_hsn_intelligence(
    query: str = Query("", min_length=0),
    q: Optional[str] = Query(None),
    top_k: int = Query(20, ge=1, le=50),
    hsn_prefix: Optional[str] = Query(None),
):
    """
    Module 1: Pure HSN Intelligence Semantic Search Engine (Up to Day 05).
    Zero dependency on historical pricing, zero vendor bias, pure trade text to statutory tariff classification.
    """
    t_start = time.perf_counter()
    raw_query = q if q is not None else query
    q_trimmed = raw_query.strip()
    if not q_trimmed:
        return {"query": raw_query, "matches": [], "latency_ms": 0.0, "module": "HSNIntelligenceEngine (Pure Day 05)"}

    engine = get_hsn_intelligence_engine() or get_hsn_search_engine()
    if engine is not None:
        res = engine.search(q_trimmed, top_k=top_k, hsn_prefix=hsn_prefix)
        formatted = []
        for m in res["matches"]:
            gst_val = float(m.get("standard_rate", 18.0))
            formatted.append({
                "hsn_code": m["hsn_code"],
                "hsn_4digit": m.get("hsn_4digit", m["hsn_code"][:4]),
                "chapter": m.get("chapter", m["hsn_code"][:2]),
                "description": m["description"],
                "gst_rate": gst_val,
                "igst_rate": gst_val,
                "cgst_rate": round(gst_val / 2.0, 2),
                "sgst_rate": round(gst_val / 2.0, 2),
                "score": m.get("score", 1.0),
                "confidence_pct": m.get("confidence_pct", 100.0),
                "match_type": m.get("match_type", "Pure Semantic Match"),
                "is_blocked_17_5": m.get("is_blocked_17_5", 0),
                "blocked_17_5_reason": m.get("blocked_17_5_reason", "Eligible")
            })
        return {
            "query": raw_query,
            "matches": formatted,
            "latency_ms": res.get("latency_ms", round((time.perf_counter() - t_start) * 1000.0, 2)),
            "module": "HSNIntelligenceEngine (Pure Day 05 - Zero Historical Data Dependency)",
        }
    raise HTTPException(status_code=500, detail="HSNIntelligenceEngine could not be initialized.")


@app.post("/api/v1/hsn-intelligence/batch-match")
async def batch_match_hsn_intelligence(
    request: Request,
    chunk_size: int = Query(256, ge=32, le=1024),
):
    """
    Dynamic Multi-Input HSN Semantic Matcher (REST Microservice Adaptor).
    Processes arbitrary batches of item descriptions or structured invoice lines completely offline using vector geometry.
    Computes parallel BLAS dot-products against the pre-computed in-memory matrix (N x 384) with sub-50ms CPU latency.
    """
    engine = get_hsn_intelligence_engine()
    if engine is None:
        raise HTTPException(status_code=500, detail="HSNIntelligenceEngine could not be initialized.")
    try:
        payload = await request.json()
        resp = engine.ingest_rest_payload(payload=payload, chunk_size=chunk_size)
        return resp
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch matching failed: {str(e)}")


@app.post("/api/v1/hsn-intelligence/upload-spreadsheet")
async def upload_spreadsheet_hsn_intelligence(
    file: UploadFile = File(...),
    description_col: Optional[str] = Query(None),
    chunk_size: int = Query(256, ge=32, le=1024),
):
    """
    Dynamic Spreadsheet Ingestion Adaptor (CSV / Excel).
    Reads uploaded item descriptions, runs batch vector matching in blocks of 256-512,
    and returns structured JSON with matched HSN codes, confidence percentages, and runners-up.
    """
    engine = get_hsn_intelligence_engine()
    if engine is None:
        raise HTTPException(status_code=500, detail="HSNIntelligenceEngine could not be initialized.")
    try:
        contents = await file.read()
        is_excel = file.filename.endswith((".xlsx", ".xls"))
        import io
        stream = io.BytesIO(contents)
        augmented_df = engine.spreadsheet_adaptor.process_file(
            stream, description_col=description_col, chunk_size=chunk_size, is_excel=is_excel
        )
        # Convert NaN to None for JSON serialization
        clean_records = augmented_df.replace({np.nan: None}).to_dict(orient="records")
        return {
            "filename": file.filename,
            "total_rows": len(clean_records),
            "rows": clean_records,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Spreadsheet processing failed: {str(e)}")



def _pin_locked_hsn(res: Any, formatted: List[Dict[str, Any]], locked_code: str):
    """
    Re-orders retrieval candidates so the user-locked HSN is the top-1 candidate.
    The gatekeeper and counterfactual engine then evaluate that exact HSN, instead of
    whichever candidate happens to fit the simulated unit price / chapter best.
    If the locked HSN is not in the retrieved set, it is fetched from the tariff master
    and given the lowest retrieved similarity score (conservative).

    Returns:
        (eval_res, formatted) - candidate payload for scoring and re-ordered UI matches.
    """
    raw_matches = list(res.get("matches", []) or [])
    raw_idx = next((i for i, m in enumerate(raw_matches) if str(m.get("hsn_code", "")).strip() == locked_code), None)
    fmt_idx = next((i for i, m in enumerate(formatted) if str(m.get("hsn_code", "")).strip() == locked_code), None)

    if raw_idx is not None and fmt_idx is not None:
        raw_matches.insert(0, raw_matches.pop(raw_idx))
        formatted = list(formatted)
        formatted.insert(0, formatted.pop(fmt_idx))
    else:
        desc = f"HSN {locked_code}"
        gst_val = 18.0
        hsn_data = get_hsn_df()
        if hsn_data is not None:
            df, hsn_col, desc_col = hsn_data
            hit = df[df[hsn_col].astype(str).str.strip() == locked_code]
            if not hit.empty:
                row = hit.iloc[0]
                desc = str(row[desc_col])
                try:
                    gst_val = float(row.get("igst_rate", row.get("gst_rate", 18.0)))
                except (TypeError, ValueError):
                    gst_val = 18.0
        scores = [float(m.get("score", 0.0)) for m in raw_matches] or [0.5]
        low_score = min(scores)
        raw_matches.insert(0, {
            "hsn_code": locked_code,
            "hsn_4digit": locked_code[:4],
            "chapter": locked_code[:2],
            "description": desc,
            "score": low_score,
            "standard_rate": gst_val,
        })
        formatted = [{
            "hsn_code": locked_code,
            "hsn_4digit": locked_code[:4],
            "description": desc,
            "gst_rate": gst_val,
            "igst_rate": gst_val,
            "cgst_rate": round(gst_val / 2.0, 2),
            "sgst_rate": round(gst_val / 2.0, 2),
            "score": low_score,
            "confidence_pct": round(low_score * 100.0, 1),
            "match_type": "User-Locked HSN",
            "is_blocked_17_5": 0,
            "blocked_17_5_reason": "Eligible",
        }] + [m for m in formatted if str(m.get("hsn_code", "")).strip() != locked_code]

    formatted[0]["is_locked"] = True
    eval_res = {"matches": raw_matches, "latency_ms": res.get("latency_ms", 0.0)}
    return eval_res, formatted


@app.get("/api/hsn-search")
async def search_hsn(
    query: str = Query("", min_length=0),
    q: Optional[str] = Query(None),
    unit_price: Optional[float] = Query(None),
    chapter: Optional[str] = Query(None),
    supplier_gstin: Optional[str] = Query(None),
    mode: str = Query("sentinel", description="Operation mode: 'intelligence' (pure Day 05) or 'sentinel' (Day 05+06+07 audit)"),
    locked_hsn: Optional[str] = Query(None, description="HSN pinned by the user; always evaluated as the top-1 candidate"),
):
    """
    Unified HSN Search & Compliance Gateway.
    - If mode == 'intelligence': Pure Day 05 semantic search with zero historical data dependency.
    - If mode == 'sentinel': Full Day 05 + 06 + 07 Audit Sentinel with Gatekeeper & Counterfactual Recommendations.
    """
    t_start = time.perf_counter()
    raw_query = q if q is not None else query
    q_trimmed = raw_query.strip()
    if not q_trimmed:
        return {"query": raw_query, "matches": [], "gatekeeper": None, "latency_ms": 0.0, "model": "None"}

    # 1. Attempt High-Performance Contrastive Semantic Search
    if mode == "intelligence":
        engine = get_hsn_intelligence_engine() or get_hsn_search_engine()
    else:
        engine = get_hsn_search_engine()
    scorer = get_hsn_misclass_scorer()

    if engine is not None:
        try:
            res = engine.search(q_trimmed, top_k=20)
            formatted = []
            for m in res["matches"]:
                gst_val = float(m.get("standard_rate", 18.0))
                item_dict = {
                    "hsn_code": m["hsn_code"],
                    "hsn_4digit": m.get("hsn_4digit", m["hsn_code"][:4]),
                    "description": m["description"],
                    "gst_rate": gst_val,
                    "igst_rate": gst_val,
                    "cgst_rate": round(gst_val / 2.0, 2),
                    "sgst_rate": round(gst_val / 2.0, 2),
                    "score": m.get("score", 1.0),
                    "confidence_pct": m.get("confidence_pct", 100.0),
                    "match_type": m.get("match_type", "Semantic Match"),
                    "is_blocked_17_5": m.get("is_blocked_17_5", 0),
                    "blocked_17_5_reason": m.get("blocked_17_5_reason", "Eligible")
                }
                formatted.append(item_dict)

            # Locked HSN anchoring: the HSN the user highlighted stays the evaluated
            # candidate, so changing unit price / chapter can never swap it out.
            eval_res = res
            locked_code = str(locked_hsn).strip() if locked_hsn else ""
            if locked_code and mode != "intelligence" and formatted:
                eval_res, formatted = _pin_locked_hsn(res, formatted, locked_code)

            # Day 06 & 07 Gatekeeper Evaluation on Top-1 Candidate (only in 'sentinel' mode)
            gatekeeper_data = None
            if mode != "intelligence" and scorer is not None and formatted:
                top1_code = formatted[0]["hsn_code"]
                sup_clean = str(supplier_gstin).strip().upper() if supplier_gstin else ""
                vendor_check_enabled = bool(sup_clean)
                simulated_line = {
                    "product_description": q_trimmed,
                    "unit_price": float(unit_price) if unit_price is not None else 1000.0,
                    "declared_hsn_chapter": str(chapter).strip() if chapter else top1_code[:2],
                    # No GSTIN -> vendor-history signal disabled (model receives neutral prior)
                    "supplier_gstin": sup_clean or None,
                    "vendor_check_disabled": not vendor_check_enabled,
                }
                if locked_code:
                    simulated_line["locked_hsn"] = top1_code
                try:
                    risk_res = scorer.predict_risk(simulated_line, eval_res)
                    is_safe = risk_res["is_safe_to_autofile"]
                    gatekeeper_data = {
                        "predicted_hsn": risk_res["predicted_hsn"],
                        "error_probability": risk_res["error_probability"],
                        "error_probability_pct": round(risk_res["error_probability"] * 100.0, 1),
                        "is_safe_to_autofile": is_safe,
                        "risk_level": risk_res["risk_level"],
                        "status_badge": "AUTO_APPROVED" if is_safe else "FLAGGED",
                        "risk_factors": risk_res["risk_factors"],
                        "features": {k: float(v) for k, v in risk_res.get("features", {}).items()},
                        "locked_hsn": top1_code if locked_code else None,
                        "vendor_check_enabled": vendor_check_enabled,
                    }

                    # Extract benchmark dataset records considered
                    top1_code_str = str(top1_code)
                    chap_str = top1_code_str[:2]
                    med_p = scorer.hsn_medians.get(top1_code_str, scorer.chapter_medians.get(chap_str, scorer.global_median_price))
                    sup_prior_val = scorer.supplier_priors.get(sup_clean, scorer.default_prior) if vendor_check_enabled else scorer.default_prior
                    gatekeeper_data["records_considered"] = {
                        "matched_tariff": {
                            "hsn_code": top1_code_str,
                            "chapter": chap_str,
                            "source": "data/tariff_master.parquet",
                            "standard_rate": formatted[0].get("gst_rate", 18.0),
                            "description": formatted[0].get("description", "")
                        },
                        "historical_price": {
                            "median_price": round(float(med_p), 2),
                            "invoice_unit_price": float(simulated_line["unit_price"]),
                            "source": "artifacts/historical_median_prices.parquet"
                        },
                        "supplier_prior": {
                            "enabled": vendor_check_enabled,
                            "supplier_gstin": sup_clean or None,
                            "prior_error_pct": round(float(sup_prior_val) * 100.0, 2),
                            "source": "artifacts/supplier_priors.parquet",
                            "is_known_in_dataset": vendor_check_enabled and sup_clean in scorer.supplier_priors
                        }
                    }

                    # Day 07 Explainability & Counterfactual enrichment
                    sentinel = get_hsn_audit_sentinel()
                    if sentinel is not None:
                        audit_res = sentinel.audit_item(simulated_line, candidates=eval_res)
                        audit_dict = audit_res.model_dump() if hasattr(audit_res, "model_dump") else audit_res.dict()
                        gatekeeper_data["explanations"] = audit_dict.get("explanations", [])
                        gatekeeper_data["human_readable_reasons"] = audit_dict.get("human_readable_reasons", [])
                        gatekeeper_data["counterfactual_recommendation"] = audit_dict.get("counterfactual_recommendation")
                        gatekeeper_data["suggested_action"] = audit_dict.get("suggested_action")
                        # Sync human_readable_reasons into risk_factors for backward compatibility
                        if gatekeeper_data["human_readable_reasons"]:
                            gatekeeper_data["risk_factors"] = gatekeeper_data["human_readable_reasons"]

                    # Attach gatekeeper result to top-1 item
                    formatted[0]["gatekeeper"] = gatekeeper_data
                except Exception as sc_err:
                    print(f"[WARN] Error running HSNMisclassificationScorer: {sc_err}")

            model_name = (
                "HSNIntelligenceEngine (Pure Day 05 Semantic Search)"
                if mode == "intelligence"
                else "HSNAuditSentinel (Day 05 Search + Day 06 Gatekeeper + Day 07 SHAP & Counterfactuals)"
            )
            return {
                "query": raw_query,
                "matches": formatted,
                "gatekeeper": gatekeeper_data,
                "latency_ms": res.get("latency_ms", round((time.perf_counter() - t_start) * 1000.0, 2)),
                "model": model_name,
                "mode": mode,
            }
        except Exception as e:
            print(f"[WARN] HSNSearchEngine execution error: {e}, falling back to literal index")

    # 2. Fallback to literal search
    hsn_data = get_hsn_df()
    if hsn_data is None:
        abs_path = os.path.abspath(HSN_EXCEL_PATH)
        return {"error": f"File not found at {abs_path}", "matches": [], "latency_ms": 0.0}

    try:
        df, hsn_col, desc_col = hsn_data
        search_key = q_trimmed.lower()

        # Fast literal string search across HSN code and description
        filtered = df[
            df['_search_hsn'].str.contains(search_key, na=False, regex=False) |
            df['_search_desc'].str.contains(search_key, na=False, regex=False)
        ]

        results = []
        for _, row in filtered.head(20).iterrows():
            igst = float(row.get("igst_rate", row.get("gst_rate", 18.0)))
            cgst = float(row.get("cgst_rate", round(igst / 2.0, 2)))
            sgst = float(row.get("sgst_rate", round(igst / 2.0, 2)))

            results.append({
                "hsn_code": str(row[hsn_col]),
                "description": str(row[desc_col]),
                "gst_rate": igst,
                "igst_rate": igst,
                "cgst_rate": cgst,
                "sgst_rate": sgst,
                "score": 1.0,
                "confidence_pct": 100.0,
                "match_type": "Literal Match"
            })

        lat = round((time.perf_counter() - t_start) * 1000.0, 2)
        return {"query": raw_query, "matches": results, "latency_ms": lat, "model": "Literal String Index"}

    except Exception as e:
        print(f"[ERROR] EXCEPTION: {str(e)}")
        return {"error": str(e), "matches": [], "latency_ms": 0.0}


@app.post("/api/v1/audit/hsn-explain")
async def audit_hsn_explain(payload: Dict[str, Any]):
    """
    Day 07 Explainability & Counterfactual Recommendation endpoint for an invoice line item.
    Returns status badge (FLAGGED / AUTO_APPROVED), deconstructed Tree SHAP evidence,
    and minimal corrective counterfactual recommendation.
    """
    advisor = get_hsn_audit_advisor()
    if advisor is None:
        raise HTTPException(status_code=500, detail="HSNAuditAdvisor not available.")
    try:
        res = advisor.review_line_item(payload)
        return res.model_dump() if hasattr(res, "model_dump") else res.dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Audit evaluation error: {str(e)}")


@app.post("/api/v1/audit/invoice")
async def audit_invoice(payload: Dict[str, Any]):
    """
    Day 07 Invoice-level audit endpoint evaluating all draft line items.
    """
    advisor = get_hsn_audit_advisor()
    if advisor is None:
        raise HTTPException(status_code=500, detail="HSNAuditAdvisor not available.")
    try:
        report = advisor.review_invoice(payload)
        return report.model_dump() if hasattr(report, "model_dump") else report.dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Invoice audit error: {str(e)}")


# =========================================================================
# MODULE 2: HSN AUDIT SENTINEL DEDICATED ENDPOINTS
# =========================================================================

@app.post("/api/v1/audit-sentinel/audit-item")
async def audit_sentinel_item(payload: Dict[str, Any]):
    """
    Module 2: HSN Audit Sentinel item-level compliance & risk gatekeeper.
    Orchestrates Day 05 retrieval + Day 06 scoring + Day 07 Tree SHAP + Day 07 Counterfactuals.
    """
    sentinel = get_hsn_audit_sentinel()
    if sentinel is None:
        raise HTTPException(status_code=500, detail="HSNAuditSentinel not available.")
    try:
        res = sentinel.audit_item(payload)
        return res.model_dump() if hasattr(res, "model_dump") else res.dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"HSNAuditSentinel error: {str(e)}")


@app.post("/api/v1/audit-sentinel/audit-invoice")
async def audit_sentinel_invoice(payload: Dict[str, Any]):
    """
    Module 2: HSN Audit Sentinel invoice-level compliance review across all items.
    """
    sentinel = get_hsn_audit_sentinel()
    if sentinel is None:
        raise HTTPException(status_code=500, detail="HSNAuditSentinel not available.")
    try:
        report = sentinel.audit_invoice(payload)
        return report.model_dump() if hasattr(report, "model_dump") else report.dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"HSNAuditSentinel invoice error: {str(e)}")


@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Serves the modernized interactive HSN auto-suggest UI from frontend or static directory."""
    candidates = [
        BASE_DIR / "frontend" / "index.html",
        BASE_DIR / "static" / "index.html"
    ]
    for p in candidates:
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                return HTMLResponse(content=f.read())
    return HTMLResponse(
        "<h2>Frontend not found. Place index.html in frontend/ or static/ directory.</h2>",
        status_code=404
    )

# Import converter service
from backend.converter_service import (
    load_default_sample_dirty,
    generate_random_dirty,
    process_converter_pipeline,
    process_converter_chat,
    get_configured_endpoints_info,
    verify_gstin_government_portal,
    verify_vehicle_government_portal,
    verify_vahan_vehicle_portal,
    TEMPLATE_CONVERTERS_DIR
)




# =========================================================================
# TEMPLATE CONVERTER & AUDITOR ENDPOINTS
# =========================================================================

@app.get("/converter", response_class=HTMLResponse)
async def serve_converter_page():
    """Serves the high-performance Template Converter & Compliance Auditor dashboard UI."""
    candidates = [
        BASE_DIR / "frontend" / "converter.html",
        BASE_DIR / "static" / "converter.html"
    ]
    for p in candidates:
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                return HTMLResponse(content=f.read())
    raise HTTPException(status_code=404, detail="converter.html not found in frontend or static directory.")


@app.get("/api/converter/sample")
async def get_sample_dirty_payload():
    """Returns sample dirty customer input payload for interactive demonstration."""
    try:
        sample_data = load_default_sample_dirty()
        return {"status": "success", "payload": sample_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading sample payload: {str(e)}")


@app.get("/api/converter/endpoints")
async def get_module_endpoints():
    """
    Returns active URLs, authentication headers, and statuses for
    all connected verification modules (GSTIN, Vahan Vehicle, NIC Engine).
    """
    try:
        return get_configured_endpoints_info()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving module endpoints: {str(e)}")


@app.get("/api/converter/verify-gstin/{gstin}")
async def verify_gstin_endpoint(gstin: str):
    """Live verification of GSTIN against configured portal / Modulo-36 checksum."""
    try:
        return verify_gstin_government_portal(gstin.strip())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error verifying GSTIN: {str(e)}")


@app.get("/api/converter/verify-vehicle/{veh_num}")
async def verify_vehicle_endpoint(veh_num: str):
    """Verification of Vehicle Number against MoRTH format / Live API."""
    try:
        return verify_vahan_vehicle_portal(veh_num.strip())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error verifying vehicle: {str(e)}")



@app.post("/api/converter/generate")
async def generate_random_dirty_payload(request: Request):
    """
    Generates a batch of randomized invoices with clean schema keys and
    realistic dirty field values (comma decimals, unpadded states, etc.).
    """
    try:
        body = await request.json() if (await request.body()) else {}
        count = int(body.get("count", 1))
        dirty_payload = generate_random_dirty(count=count)
        return {
            "status": "success",
            "count": count,
            "payload": dirty_payload
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating random payload: {str(e)}")


@app.post("/api/converter/process")
async def process_payload(request: Request):
    """
    Converts and validates dirty payload, applying auto-corrections,
    checking NIC compliance rules, and returning all 4 output reports and metrics.
    """
    try:
        body = await request.json()
        # Accept either {"payload": {...}} or raw JSON dict/list directly
        raw_payload = body.get("payload") if isinstance(body, dict) and "payload" in body else body

        if not raw_payload:
            raise HTTPException(status_code=400, detail="Empty payload provided.")

        result = process_converter_pipeline(raw_payload, sync_to_disk=True)
        return result
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON syntax: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing conversion: {str(e)}")


@app.post("/api/converter/chat")
async def chat_with_converter_copilot(request: Request):
    """
    AI Compliance Assistant & Copilot for E-Invoice and E-Way Bill operations.
    Answers compliance queries, explains validation errors in plain English,
    accepts user corrections (GSTIN, PAN, PIN, Vehicle, etc.), patches payload,
    and returns live re-validation status.
    """
    try:
        body = await request.json()
        message = body.get("message", "").strip()
        raw_payload = body.get("payload")
        validation_report = body.get("validation_report")
        chat_history = body.get("chat_history", [])

        if not raw_payload:
            # Fallback to default dirty sample if none in editor
            raw_payload = load_default_sample_dirty()

        response = process_converter_chat(
            user_message=message,
            raw_payload=raw_payload,
            validation_report=validation_report,
            chat_history=chat_history
        )
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error in compliance copilot: {str(e)}")


@app.get("/api/converter/download/{file_type}")
async def download_converted_file(file_type: str):
    """
    Downloads any of the 4 canonical output files produced by the pipeline:
    - corrected   -> corrected_payload.json
    - report      -> validation_report.json
    - csv         -> correction_audit_report.csv
    - summary     -> audit_summary.txt
    """
    file_map = {
        "corrected": ("corrected_payload.json", "application/json"),
        "json": ("corrected_payload.json", "application/json"),
        "report": ("validation_report.json", "application/json"),
        "csv": ("correction_audit_report.csv", "text/csv; charset=utf-8"),
        "summary": ("audit_summary.txt", "text/plain; charset=utf-8")
    }

    if file_type not in file_map:
        raise HTTPException(status_code=400, detail=f"Invalid file type requested. Options: {list(file_map.keys())}")

    filename, media_type = file_map[file_type]
    file_path = TEMPLATE_CONVERTERS_DIR / filename
    if not file_path.exists():
        cand = BASE_DIR / "data" / "processed_payload" / filename
        if cand.exists():
            file_path = cand

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File {filename} has not been generated yet. Run a conversion first.")

    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type=media_type
    )


# =========================================================================
# GST SENTINEL INGESTION & RAW DATA LAKEHOUSE ENDPOINTS
# =========================================================================

from backend.ingestion_service import (
    list_raw_files_metadata,
    get_raw_file_records,
    get_processed_lakehouse_records,
    get_audit_trail_records,
    run_live_validation,
    persist_invoice_pipeline,
    get_dashboard_summary_stats,
    process_ingestion_pipeline,
    process_ingestion_chat,
    PROCESSED_DIR
)
from src.ingestion.generate_sample_dirty_input import (
    generate_dynamic_dirty_payload as generate_ingestion_dirty_payload_fn,
    load_default_sample_dirty as load_ingestion_sample_dirty_fn,
)


@app.get("/ingestion", response_class=HTMLResponse)
@app.get("/lakehouse", response_class=HTMLResponse)
async def serve_ingestion_page():
    """Serves the modernized GST Sentinel Data Ingestion & Lakehouse Explorer dashboard UI."""
    candidates = [
        BASE_DIR / "frontend" / "ingestion.html",
        BASE_DIR / "static" / "ingestion.html",
        BASE_DIR / "src" / "ui" / "ingestion.html"
    ]
    for p in candidates:
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                return HTMLResponse(content=f.read())
    raise HTTPException(status_code=404, detail="ingestion.html not found in frontend or static directory.")


@app.get("/api/ingestion/stats")
async def get_ingestion_stats():
    """Returns top-level KPI metrics for the ingestion dashboard."""
    try:
        return get_dashboard_summary_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error computing dashboard stats: {str(e)}")


@app.get("/api/ingestion/raw-files")
async def get_raw_files_list():
    """Returns metadata for all data files located in data/raw/."""
    try:
        return list_raw_files_metadata()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing raw files: {str(e)}")


@app.get("/api/ingestion/raw-data")
async def get_raw_data_content(
    filename: str = Query(..., description="Name of the file in data/raw/"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=5, le=100),
    search: str = Query("", description="Search term across columns"),
    sort_by: Optional[str] = Query(None),
    sort_dir: str = Query("asc")
):
    """Returns paginated, searchable, sorted records from any data/raw/ dataset."""
    try:
        return get_raw_file_records(
            filename=filename,
            page=page,
            page_size=page_size,
            search_query=search,
            sort_by=sort_by,
            sort_dir=sort_dir
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading raw data: {str(e)}")


@app.get("/api/ingestion/lakehouse-master")
async def get_lakehouse_master_content(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=5, le=100),
    search: str = Query("")
):
    """Returns paginated records from data/processed_payload/invoices_master.parquet."""
    try:
        return get_processed_lakehouse_records(page=page, page_size=page_size, search_query=search)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading lakehouse master: {str(e)}")


@app.get("/api/ingestion/audit-trail")
async def get_audit_trail_content(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=10, le=200),
    search: str = Query(""),
    category: str = Query("")
):
    """Returns parsed records from data/processed_payload/transformation_audit_report.csv."""
    try:
        return get_audit_trail_records(
            page=page,
            page_size=page_size,
            search_query=search,
            error_category=category
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading audit trail: {str(e)}")


@app.get("/api/ingestion/sample-payload")
async def get_sample_ingestion_payload(invoice_index: int = Query(0, ge=0, le=10)):
    """Loads realistic dirty customer payload from dirty_customer_input.json."""
    sample_path = BASE_DIR / "Template_Converters" / "dirty_customer_input.json"
    if not sample_path.exists():
        sample_path = BASE_DIR / "dirty_customer_input.json"

    if sample_path.exists():
        with open(sample_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        invoices = data.get("einvoices", [])
        if invoices:
            idx = min(invoice_index, len(invoices) - 1)
            return {"status": "success", "invoice_index": idx, "total_available": len(invoices), "payload": invoices[idx]}

    # Fallback dirty sample
    fallback = {
        "self gstin": "29AAACR4849R1ZH",
        "system cd": "ERP_SAP",
        "branch cd": "BLR-HQ",
        "vertical cd": "DOMESTIC",
        "trandt1": {"trancatg": "B2B", "reversecharge": "N"},
        "docdt1": {"docno": "INV-2026-001", "invoice_date": "2026-09-15"},
        "supplierdt1": {
            "supplier_gstin": "29AAACR4849R1ZH",
            "supplier_lginm": "  ZENITH   ENTERPRISES PVT LTD  ",
            "supplier_loc": "BENGALURU",
            "supplier_pin": "560001",
            "supplier state": "29"
        },
        "buyerdt1": {
            "buyer_gstin": "27TUHCN2957U5ZN",
            "buyer_lglnm": "MAHARASHTRA INDUSTRIAL DISTRIBUTORS",
            "buyer loc": "MUMBAI",
            "buyer pin": "400001",
            "buyer state": "27",
            "pos": "27"
        },
        "itemdtls": [
            {
                "prdnm": "COTTON-SHIRTS",
                "hsn": "6205",
                "ugc": "nos",
                "qty": "100",
                "unit_rate": "1600.00",
                "grossamt": "160000,00",
                "discount": "0.0",
                "assval": "160000,00",
                "igstval": "28800,00",
                "totitemval": "188800,00"
            }
        ],
        "valdt1": {"assval": 160000.0, "igstval": 28800.0, "totinvval": "188800,00"}
    }
    return {"status": "success", "invoice_index": 0, "total_available": 1, "payload": fallback}


@app.get("/api/ingestion/sample")
async def get_sample_ingestion_dirty_payload():
    """Returns full sample dirty customer input payload for interactive demonstration."""
    try:
        sample_data = load_ingestion_sample_dirty_fn()
        return {"status": "success", "payload": sample_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading sample payload: {str(e)}")


@app.post("/api/ingestion/process")
async def process_ingestion_endpoint(request: Request):
    """
    Ingestion Converter Pipeline:
    Auto-corrects dirty customer keys and formats, validates NIC IRN/EWB compliance rules
    via native Pydantic v2 schemas, persists to Parquet Lakehouse & Excel, and returns
    all 4 canonical reports and executive metrics.
    """
    try:
        body = await request.json()
        raw_payload = body.get("payload") if isinstance(body, dict) and "payload" in body else body

        if not raw_payload:
            raise HTTPException(status_code=400, detail="Empty payload provided.")

        # 2-Stage Layer: Stage 1 UI passes persist_to_lakehouse=False; defaults to True for full test & pipeline compatibility
        persist_lakehouse = body.get("persist_to_lakehouse", True) if isinstance(body, dict) else True
        result = process_ingestion_pipeline(raw_payload, sync_to_disk=True, persist_to_lakehouse=persist_lakehouse)
        result["stage"] = "STAGE_2_PERSISTED" if persist_lakehouse else "STAGE_1_VALIDATED"
        return result
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON syntax: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing ingestion conversion: {str(e)}")


@app.post("/api/ingestion/validate")
async def validate_ingestion_payload(request: Request):
    """Validates raw customer invoice payload via Pydantic v2 schemas and outputs auto-corrections."""
    try:
        body = await request.json()
        payload = body.get("payload") if (isinstance(body, dict) and "payload" in body) else body
        if not payload:
            raise HTTPException(status_code=400, detail="No payload provided.")
        return run_live_validation(payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Validation failed: {str(e)}")


@app.post("/api/ingestion/persist")
async def persist_ingestion_payload(request: Request):
    """Validates, auto-corrects, and persists invoice into Lakehouse Parquet, Excel, JSON, and CSV."""
    try:
        body = await request.json()
        payload = body.get("payload") if (isinstance(body, dict) and "payload" in body) else body
        force = body.get("force", False) if isinstance(body, dict) else False
        if not payload:
            raise HTTPException(status_code=400, detail="No payload provided.")
        return persist_invoice_pipeline(payload, require_100_percent_compliant=not force)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Persistence failed: {str(e)}")


@app.post("/api/ingestion/generate")
@app.post("/api/ingestion/generate-dirty")
async def generate_dirty_ingestion_payload(request: Request):
    """Generates random realistic dirty invoices with comma decimals, unaligned keys, and status codes."""
    try:
        body = await request.json() if (await request.body()) else {}
        count = int(body.get("count", 1))
        dirty_payload = generate_ingestion_dirty_payload_fn(count=count)
        return {
            "status": "success",
            "count": count,
            "payload": dirty_payload
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating random payload: {str(e)}")


@app.post("/api/ingestion/chat")
async def chat_with_ingestion_copilot(request: Request):
    """
    AI Compliance Assistant & Copilot for GST Ingestion.
    Answers compliance queries, explains validation errors in plain English,
    accepts user corrections (GSTIN, PAN, PIN, Vehicle, etc.), patches payload,
    re-validates, synchronizes Ingestion Lakehouse Parquet/Excel, and returns live status.
    """
    try:
        body = await request.json()
        message = body.get("message", "").strip()
        raw_payload = body.get("payload")
        validation_report = body.get("validation_report")
        chat_history = body.get("chat_history", [])

        if not raw_payload:
            raw_payload = load_default_sample_dirty()

        response = process_ingestion_chat(
            user_message=message,
            raw_payload=raw_payload,
            validation_report=validation_report,
            chat_history=chat_history,
            sync_to_disk=True,
            persist_to_lakehouse=True
        )
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error in compliance copilot: {str(e)}")


@app.get("/api/ingestion/endpoints")
async def get_ingestion_endpoints():
    """Returns active portal URLs, API credentials status, and integration engines for ingestion dashboard."""
    return get_configured_endpoints_info()


@app.get("/api/ingestion/verify-gstin/{gstin}")
async def verify_gstin_ingestion(gstin: str):
    """Live verification of GSTIN against configured portal / Modulo-36 checksum."""
    try:
        return verify_gstin_government_portal(gstin.strip())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error verifying GSTIN: {str(e)}")


@app.get("/api/ingestion/verify-vehicle/{veh_num}")
async def verify_vehicle_ingestion(veh_num: str):
    """Verification of Vehicle Number against MoRTH format / Live API."""
    try:
        return verify_vahan_vehicle_portal(veh_num.strip())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error verifying vehicle: {str(e)}")


@app.get("/api/ingestion/download/{file_type}")
async def download_ingestion_file(file_type: str):
    """Downloads processed lakehouse, canonical converter outputs, and audit files."""
    file_map = {
        # Canonical Converter Files
        "corrected": (PROCESSED_DIR / "corrected_payload.json", "corrected_payload.json", "application/json"),
        "report": (PROCESSED_DIR / "validation_report.json", "validation_report.json", "application/json"),
        "csv": (PROCESSED_DIR / "correction_audit_report.csv", "correction_audit_report.csv", "text/csv; charset=utf-8"),
        "summary": (PROCESSED_DIR / "audit_summary.txt", "audit_summary.txt", "text/plain; charset=utf-8"),
        # Lakehouse & Audit Files
        "parquet": (PROCESSED_DIR / "invoices_master.parquet", "invoices_master.parquet", "application/octet-stream"),
        "excel": (PROCESSED_DIR / "invoices_export.xlsx", "invoices_export.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        "audit_csv": (PROCESSED_DIR / "transformation_audit_report.csv", "transformation_audit_report.csv", "text/csv; charset=utf-8"),
        "nic_json": (PROCESSED_DIR / "corrected_payload.json", "nic_irp_payload.json", "application/json"),
        "ewb_json": (PROCESSED_DIR / "INV-2026-TEST_standalone_ewb.json", "standalone_ewb.json", "application/json")
    }

    if file_type not in file_map:
        raise HTTPException(status_code=400, detail=f"Invalid file type. Available: {list(file_map.keys())}")

    path, name, media_type = file_map[file_type]
    if not path.exists():
        # Fallback to alternate filenames if available
        if file_type in ["csv", "audit_csv"]:
            for cand_csv in [
                PROCESSED_DIR / "transformation_audit_report.csv",
                PROCESSED_DIR / "correction_audit_report.csv",
                BASE_DIR / "Template_Converters" / "correction_audit_report.csv"
            ]:
                if cand_csv.exists() and cand_csv.stat().st_size > 0:
                    path = cand_csv
                    break
        elif file_type == "nic_json":
            cand = list(PROCESSED_DIR.glob("*_nic_irp.json"))
            if cand:
                path = cand[0]
        elif file_type == "ewb_json":
            cand = list(PROCESSED_DIR.glob("*_standalone_ewb.json"))
            if cand:
                path = cand[0]

    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File {name} not found on disk. Run ingestion pipeline first.")

    return FileResponse(path=str(path), filename=name, media_type=media_type)


if __name__ == "__main__":
    import uvicorn
    print("\n🚀 Starting GST Sentinel Server at http://127.0.0.1:8000 ...")
    print("👉 GST Sentinel Ingestion & Lakehouse Portal: http://127.0.0.1:8000/ingestion")
    print("👉 E-Invoice & E-Way Converter Dashboard    : http://127.0.0.1:8000/converter")
    print("👉 HSN Code Search Engine                   : http://127.0.0.1:8000/\n")
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
