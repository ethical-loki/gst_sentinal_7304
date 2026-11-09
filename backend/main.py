"""
Module: backend/main.py
Description: Complete FastAPI backend serving Excel-based HSN/SAC search with
             dtype=str to preserve leading zeros, dynamic pathing, and modern UI.
"""

import os

# Prevent OpenBLAS thread allocation failure on Windows
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional, List, Dict, Any, Union, Tuple
import numpy as np
import pandas as pd
from fastapi import FastAPI, Query, HTTPException, Request, Response, UploadFile, File, Body

logger = logging.getLogger(__name__)
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

# Mount HSN Chapter Predictor Router (Module 5)
from backend.routers.chapter_predict import router as chapter_router
app.include_router(chapter_router)

# --- CONFIGURABLE FILE PATH ---
# Files should be placed in data/raw/ or data/
RAW_DATA_DIR = os.path.join("data", "raw")

# 👉 Updated to latest authoritative HSN/SAC master file
EXCEL_FILENAME = "Final_Copy_hsn_7304.xlsx"

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
async def preload_services():
    """Pre-load HSN DataFrame and QA Engine into memory on server startup so all searches are instant."""
    result = get_hsn_df()
    if result is not None:
        df, hsn_col, desc_col = result
        print(f"[OK] HSN data preloaded: {len(df)} rows | Columns: {hsn_col}, {desc_col}")
    else:
        print("[WARN] HSN Excel file not found at startup - will retry on first search.")

    try:
        from backend.qa_service import get_qa_engine
        print("[INFO] Pre-warming Multi-Domain QA Engine (Qwen2.5)...")
        get_qa_engine()
        print("[OK] Multi-Domain QA Engine preloaded and ready.")
    except Exception as e:
        print(f"[WARN] QA Engine preload deferred: {e}")

    try:
        print("[INFO] Pre-warming HSN Intelligence Engine (Module 1)...")
        get_hsn_intelligence_engine()
        print("[OK] HSN Intelligence Engine (Module 1) preloaded.")
    except Exception as e:
        print(f"[WARN] HSN Intelligence Engine preload deferred: {e}")

    try:
        print("[INFO] Pre-warming HSN Audit Sentinel (Module 2)...")
        get_hsn_audit_sentinel()
        print("[OK] HSN Audit Sentinel (Module 2) preloaded.")
    except Exception as e:
        print(f"[WARN] HSN Audit Sentinel preload deferred: {e}")

    try:
        print("[INFO] Pre-warming DeepSeek HSN Verifier (Dual-Model Neural Layer)...")
        get_hsn_deepseek_verifier()
        print("[OK] DeepSeek HSN Verifier preloaded.")
    except Exception as e:
        print(f"[WARN] DeepSeek HSN Verifier preload deferred: {e}")


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


_hsn_deepseek_verifier = None

def get_hsn_deepseek_verifier():
    global _hsn_deepseek_verifier
    if _hsn_deepseek_verifier is None:
        try:
            from src.ml.deepseek_hsn_verifier import get_deepseek_hsn_verifier
            _hsn_deepseek_verifier = get_deepseek_hsn_verifier()
            print("[OK] DeepSeekHSNVerifier (Dual-Model Neural Layer) initialized")
        except Exception as e:
            print(f"[WARN] Failed to load DeepSeekHSNVerifier: {e}")
            _hsn_deepseek_verifier = None
    return _hsn_deepseek_verifier

# Backwards compatibility alias
get_hsn_qwen_verifier = get_hsn_deepseek_verifier


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
        matches_items = res.get("matches", res) if hasattr(res, "get") else (res["matches"] if isinstance(res, dict) else res)
        for m in matches_items:
            gst_val = float(m["standard_rate"]) if m.get("standard_rate") is not None else None
            formatted.append({
                "hsn_code": m["hsn_code"],
                "hsn_4digit": m.get("hsn_4digit", m["hsn_code"][:4]),
                "chapter": m.get("chapter", m["hsn_code"][:2]),
                "description": m["description"],
                "gst_rate": gst_val,
                "igst_rate": gst_val,
                "cgst_rate": round(gst_val / 2.0, 2) if gst_val is not None else None,
                "sgst_rate": round(gst_val / 2.0, 2) if gst_val is not None else None,
                "score": m.get("score", 1.0),
                "confidence_pct": m.get("confidence_pct", 100.0),
                "match_type": m.get("match_type", "Pure Semantic Match"),
                "is_blocked_17_5": m.get("is_blocked_17_5", 0),
                "blocked_17_5_reason": m.get("blocked_17_5_reason", "Eligible")
            })
        latency_val = res.get("latency_ms") if isinstance(res, dict) else round((time.perf_counter() - t_start) * 1000.0, 2)
        return {
            "query": raw_query,
            "matches": formatted,
            "latency_ms": latency_val,
            "module": "HSNIntelligenceEngine (Pure Day 05 - Zero Historical Data Dependency)",
        }
    raise HTTPException(status_code=500, detail="HSNIntelligenceEngine could not be initialized.")


@app.post("/api/v1/hsn-intelligence/batch-match")
async def batch_match_hsn_intelligence(
    request: Request,
    chunk_size: int = Query(256, ge=32, le=1024),
    with_qwen: bool = Query(False),
    save_to_store: bool = Query(False, description="Persist Day 5 dynamic algo predictions into data/hsn_verified_store.parquet if True (default False)"),
):
    """
    Dynamic Multi-Input HSN Semantic Matcher (REST Microservice Adaptor).
    Predicts HSN codes using Day 5 offline vector geometry (S = Q · D^T).
    Stores predictions into data/hsn_verified_store.parquet for persistent auditability.
    If with_qwen=True, runs Qwen 2.5 verification on top.
    """
    engine = get_hsn_intelligence_engine()
    if engine is None:
        raise HTTPException(status_code=500, detail="HSNIntelligenceEngine could not be initialized.")
    try:
        payload = await request.json()
        resp = engine.ingest_rest_payload(payload=payload, chunk_size=chunk_size)
        items_list = resp.get("items") or resp.get("results") or []

        # Store Day 5 dynamic algo predictions in hsn_verified_store.parquet
        from src.ml.hsn_verified_store import get_hsn_verified_store
        store = get_hsn_verified_store()
        if save_to_store and items_list:
            store.upsert_algo_batch(items_list)
        resp["storage_file"] = "data/hsn_verified_store.parquet"
        resp["stored_records_total"] = len(store.get_all_records())

        if with_qwen:
            verifier = get_hsn_qwen_verifier()
            if verifier is not None:
                qwen_rep = verifier.verify_batch(items_list, save_to_store=save_to_store)
                resp["qwen_summary"] = {
                    "perfect_matches": qwen_rep["perfect_matches"],
                    "corrected_by_qwen": qwen_rep["corrected_by_qwen"],
                    "batch_latency_ms": qwen_rep["batch_latency_ms"],
                    "is_saved": qwen_rep.get("is_saved", False),
                    "storage_action": qwen_rep.get("storage_action", "AUDIT_ONLY"),
                    "model": "Qwen2.5-0.5B-Instruct"
                }
                for i, r in enumerate(items_list):
                    if i < len(qwen_rep["results"]):
                        r["qwen_verification"] = qwen_rep["results"][i]
                resp["stored_records_total"] = len(store.get_all_records())
        return resp
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch matching failed: {str(e)}")


@app.get("/api/v1/hsn-intelligence/deepseek-verify")
@app.get("/api/v1/hsn-intelligence/qwen-verify")
async def deepseek_verify_single(
    query: str = Query(..., min_length=1),
    base_hsn: Optional[str] = Query(None),
    base_rate: Optional[float] = Query(None),
    save: bool = Query(False, description="Persist verified record if true, audit-only if false")
):
    """
    DeepSeek Dual-Model Autonomous Neural Verification Layer for a single product description.
    Cross-checks Day 5 base classification against DeepSeek statutory reasoning and dynamic tariff index.
    Returns whether the prediction is a PERFECT_MATCH or CORRECTED_BY_DEEPSEEK with statutory reasoning.
    """
    verifier = get_hsn_deepseek_verifier()
    if verifier is None:
        raise HTTPException(status_code=500, detail="DeepSeek HSN Verifier could not be initialized.")
    return verifier.verify_item(query=query, base_hsn=base_hsn, base_rate=base_rate, save_to_store=save)

# Alias for backwards compatibility
qwen_verify_single = deepseek_verify_single


@app.post("/api/v1/hsn-intelligence/deepseek-verify")
@app.post("/api/v1/hsn-intelligence/qwen-verify")
async def deepseek_verify_batch(
    request: Request,
    save: bool = Query(False, description="Persist verified records to data/hsn_verified_store.parquet if true, audit-only if false")
):
    """
    Dedicated DeepSeek Dual-Model Verification Screen API.
    Audits an entire list or stream of product descriptions against DeepSeek statutory reasoning.
    Supports:
      - Option 2 (save=False): Just Audit (audits against Day 5 prediction without saving to parquet)
      - Option 3 (save=True): Save & Audit (audits against Day 5 prediction AND persists verified records)
    """
    verifier = get_hsn_deepseek_verifier()
    if verifier is None:
        raise HTTPException(status_code=500, detail="DeepSeek HSN Verifier could not be initialized.")
    try:
        body = await request.json()
    except Exception:
        body = {}

    save_flag = save
    if isinstance(body, dict) and "save" in body:
        save_flag = bool(body["save"])

    if isinstance(body, list):
        items = body
    elif isinstance(body, dict):
        if "items" in body and isinstance(body["items"], list):
            items = body["items"]
        elif "query" in body or "item_description" in body:
            single = verifier.verify_item(
                query=body.get("query") or body.get("item_description"),
                base_hsn=body.get("base_hsn") or body.get("hsn_code") or body.get("matched_hsn"),
                base_rate=body.get("base_rate") or body.get("standard_rate") or body.get("gst_rate"),
                save_to_store=save_flag
            )
            from src.ml.hsn_verified_store import get_hsn_verified_store
            store = get_hsn_verified_store()
            return {
                "total_items": 1,
                "perfect_matches": 1 if single["is_perfect_match"] else 0,
                "corrected_by_qwen": 0 if single["is_perfect_match"] else 1,
                "batch_latency_ms": single["latency_ms"],
                "is_saved": save_flag,
                "storage_action": "AUDITED_AND_SAVED" if save_flag else "AUDIT_ONLY",
                "storage_file": "data/hsn_verified_store.parquet",
                "stored_records_total": len(store.get_all_records()),
                "results": [single]
            }
        else:
            items = []
    else:
        items = []

    norm_items = []
    for it in items:
        if isinstance(it, str):
            norm_items.append({"item_description": it})
        elif isinstance(it, dict):
            norm_items.append(it)

    rep = verifier.verify_batch(norm_items, save_to_store=save_flag)

    from src.ml.hsn_verified_store import get_hsn_verified_store
    store = get_hsn_verified_store()
    rep["is_saved"] = save_flag
    rep["storage_action"] = "AUDITED_AND_SAVED" if save_flag else "AUDIT_ONLY"
    rep["storage_file"] = "data/hsn_verified_store.parquet"
    rep["stored_records_total"] = len(store.get_all_records())
    return rep


@app.post("/api/v1/hsn-intelligence/analyze-ambiguity")
async def analyze_hsn_ambiguity(request: Request):
    """
    Dedicated DeepSeek Ambiguity Analysis Endpoint (Prompt ID: HSN_AMBIGUITY_ANALYSIS v1.0.0).
    Identifies insufficient, conflicting, or unclear product information preventing reliable distinction
    between retrieved HSN candidates before making an unreliable classification decision.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    orig_desc = (
        body.get("product_description")
        or body.get("original_description")
        or body.get("query")
        or body.get("item_description")
        or ""
    )
    attrs = body.get("extracted_attributes") or body.get("attributes") or {}
    candidates = body.get("retrieved_candidates") or body.get("candidates") or []
    norm_desc = body.get("normalized_description")

    from src.ml.deepseek_ambiguity_analyzer import get_deepseek_ambiguity_analyzer
    analyzer = get_deepseek_ambiguity_analyzer()
    return analyzer.analyze_ambiguity(
        original_description=orig_desc,
        extracted_attributes=attrs,
        retrieved_candidates=candidates,
        normalized_description=norm_desc
    )


# =====================================================================
# HSN RAG APPLICATION LAYER ENDPOINTS
# =====================================================================

@app.post("/api/v1/hsn-rag/extract-attributes")
async def rag_extract_attributes(request: Request):
    """
    Stage 1: Customs Classification & Tariff Attribute Extractor.
    Extracts constituent material, processing state, function/use, and mounted state.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    desc = body.get("product_description") or body.get("query") or body.get("item_description") or ""
    from src.nlp.hsn_rag_layer import get_hsn_rag_application_layer
    rag_layer = get_hsn_rag_application_layer()
    result = rag_layer.extract_attributes(desc)
    return result.model_dump()


@app.post("/api/v1/hsn-rag/verify")
async def rag_verify_statutory(request: Request):
    """
    Stage 3: Statutory HSN & ITC-HS Legal Verification Engine.
    Adjudicates candidate headings and legal notes against extracted attributes.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    desc = body.get("product_description") or body.get("query") or ""
    raw_ext = body.get("extraction") or {}
    from src.nlp.hsn_rag_layer import get_hsn_rag_application_layer, AttributeExtractionResult
    rag_layer = get_hsn_rag_application_layer()
    extraction = AttributeExtractionResult(**raw_ext) if raw_ext else rag_layer.extract_attributes(desc)
    candidates = body.get("candidates") or body.get("retrieved_candidates") or []
    notes = body.get("statutory_notes") or body.get("retrieved_statutory_notes") or []
    clarification = body.get("customer_clarification") or body.get("clarification")

    if not candidates or not notes:
        ctx = rag_layer.retrieve_statutory_context(extraction)
        candidates = candidates or ctx["candidates"]
        notes = notes or ctx["statutory_notes"]

    result = rag_layer.verify_statutory_classification(
        product_description=desc,
        extraction=extraction,
        candidates=candidates,
        statutory_notes=notes,
        customer_clarification=clarification
    )
    return result.model_dump()


@app.post("/api/v1/hsn-rag/pipeline")
async def rag_run_pipeline(request: Request):
    """
    End-to-End HSN RAG Pipeline:
    Extraction -> Ambiguity Gatekeeper -> Context Retrieval -> Statutory Legal Verification.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    desc = body.get("product_description") or body.get("query") or body.get("item_description") or ""
    clarification = body.get("customer_clarification") or body.get("clarification")
    from src.nlp.hsn_rag_layer import get_hsn_rag_application_layer
    rag_layer = get_hsn_rag_application_layer()
    result = rag_layer.run_pipeline(desc, customer_clarification=clarification)
    return result.model_dump()


@app.post("/api/v1/hsn-rag/batch-pipeline")
async def rag_run_batch_pipeline(request: Request):
    """
    Executes Statutory RAG Pipeline across a batch of commercial descriptions:
    Extraction -> Ambiguity Gatekeeper -> Context Retrieval -> Statutory Legal Verification.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    items = body.get("items") or body.get("products") or []
    if isinstance(items, str):
        items = [items]
    from src.nlp.hsn_rag_layer import get_hsn_rag_application_layer
    rag_layer = get_hsn_rag_application_layer()
    results = []
    t0 = time.perf_counter()
    for itm in items:
        desc = itm if isinstance(itm, str) else (itm.get("item_description") or itm.get("description") or "")
        clarif = itm.get("customer_clarification") if isinstance(itm, dict) else None
        res = rag_layer.run_pipeline(desc, customer_clarification=clarif)
        results.append(res.model_dump())
    total_latency = round((time.perf_counter() - t0) * 1000.0, 2)
    return {
        "total_items": len(results),
        "batch_latency_ms": total_latency,
        "results": results
    }


# =====================================================================
# GEMINI MULTI-HEAD INTENT EXTRACTOR & 4-STAGE TAXONOMY ROUTER
# =====================================================================

@app.post("/api/v1/hsn-gemini/extract-and-predict")
@app.get("/api/v1/hsn-gemini/extract-and-predict")
async def gemini_extract_and_predict(request: Request, query: Optional[str] = None):
    """
    Google Gemini Architecture Multi-Head Intent Decomposer & 4-Stage Taxonomy Navigation Engine.
    Decomposes query across 4 linguistic heads (Syntax, Material, Manufacturing Form, End-Use Intent)
    and navigates WCO Section/Chapter -> 4-digit Heading -> 6-digit Subheading -> 8-digit Tariff Line.
    Tax rates strictly null (None) as per HSN_SAC (1).xlsx master.
    """
    text = query or ""
    if not text:
        try:
            body = await request.json()
            text = body.get("product_description") or body.get("query") or body.get("item_description") or ""
        except Exception:
            text = ""
    from src.nlp.gemini_hsn_extractor import get_gemini_hsn_extractor
    extractor = get_gemini_hsn_extractor()
    result = extractor.extract_and_predict(text)
    return result.model_dump()


@app.post("/api/v1/hsn-intelligence/unified-multi-model-audit")
async def unified_multi_model_audit(request: Request):
    """
    Unified Single-Click Multi-Model Audit:
    Computes Day 5 Base Algo + DeepSeek Neural Verifier + Statutory RAG Layer,
    and returns a unified comparison with the Final Statutory HSN Code.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    items = body.get("items") or body.get("products") or []
    if isinstance(items, str):
        items = [items]
    from src.nlp.hsn_rag_layer import get_hsn_rag_application_layer
    rag_layer = get_hsn_rag_application_layer()
    return rag_layer.run_unified_audit(items)


@app.post("/api/v1/hsn-rag/resolve-clarification")
async def resolve_clarification_three_stage(request: Request):
    """
    Three-Stage Clarification Resolution Architecture:
    [User Input] -> [Stage 1: Context Aggregator] -> [Stage 2: Vector Search Index (Top 3)] -> [Stage 3: AI Legal Selector]
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    base_product = (body.get("base_product") or body.get("product") or "").strip()
    user_clarification = (body.get("user_clarification") or body.get("clarification") or "").strip()
    existing_attributes = body.get("existing_attributes") or body.get("attributes") or None

    if not base_product or not user_clarification:
        raise HTTPException(
            status_code=400,
            detail="Both 'base_product' and 'user_clarification' are required."
        )

    from src.nlp.hsn_rag_layer import get_hsn_rag_application_layer
    rag_layer = get_hsn_rag_application_layer()
    return rag_layer.resolve_clarification_three_stage(
        base_product=base_product,
        user_clarification=user_clarification,
        existing_attributes=existing_attributes
    )


@app.post("/api/v1/hsn-rag/statutory-auditor-evaluate")
async def statutory_auditor_evaluate(request: Request):
    """
    Elite Statutory Customs Auditor (GIR 1 & GIR 6 Dynamic Output Protocol).
    Evaluates user_raw_input, context_aggregator_attributes, and vector_search_top_3_options,
    returning strictly FORMAT A (status="SUCCESS") or FORMAT B (status="NEED_CLARIFICATION").
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    user_raw_input = (body.get("user_raw_input") or body.get("product_description") or "").strip()
    context_aggregator_attributes = body.get("context_aggregator_attributes") or body.get("attributes") or {}
    vector_search_top_3_options = body.get("vector_search_top_3_options") or body.get("top_3_candidates") or []

    from src.nlp.hsn_rag_layer import get_hsn_rag_application_layer
    rag_layer = get_hsn_rag_application_layer()

    # If top 3 options were not pre-supplied, compute Stage 1 & Stage 2 automatically
    if not vector_search_top_3_options and user_raw_input:
        s1 = rag_layer.stage1_context_aggregator(user_raw_input, "", context_aggregator_attributes)
        context_aggregator_attributes = s1["aggregated_attributes"]
        s2 = rag_layer.stage2_vector_search_index(s1["master_search_string"], context_aggregator_attributes)
        vector_search_top_3_options = s2["top_3_candidates"]

    return rag_layer.evaluate_statutory_customs_auditor(
        user_raw_input=user_raw_input,
        context_aggregator_attributes=context_aggregator_attributes,
        vector_search_top_3_options=vector_search_top_3_options
    )


@app.post("/api/v1/hsn-rag/step1-context-aggregator")
async def step1_context_aggregator_endpoint(request: Request):
    """
    Step 1: Context Aggregator (Product + Material + Form + Chapter Categorization).
    Extracts base product, material composition, form/state, and Chapter 01–99.
    Also queries Chapter Predictor (BGE-M3 + BM25 + Qwen/fusion) to provide high-precision
    chapter guidance and evidence.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    base_product = (body.get("product") or body.get("base_product") or body.get("product_name") or "").strip()
    user_clarification = (body.get("clarification") or body.get("user_clarification") or "").strip()
    existing_attributes = body.get("attributes") or body.get("existing_attributes") or None

    if not base_product:
        raise HTTPException(status_code=400, detail="'product' is required.")

    from src.nlp.hsn_rag_layer import get_hsn_rag_application_layer
    rag_layer = get_hsn_rag_application_layer()
    s1 = rag_layer.stage1_context_aggregator(
        base_product=base_product,
        user_clarification=user_clarification,
        existing_attributes=existing_attributes
    )

    chapter_pred_data = None
    query_facts_data = {}
    catalogue_version = "v1.0.0-closed98"
    index_version = "bge-m3-lineage-v1"
    try:
        from src.chapter_predictor.normalize import extract_query_facts
        query_facts_data = extract_query_facts(base_product)
    except Exception as e:
        logger.warning(f"Fact extraction skipped in Step 1: {e}")

    try:
        from src.chapter_predictor.predictor import ChapterPredictor
        pred = ChapterPredictor.get_instance().predict(base_product, top_k=3)
        chapter_pred_data = pred.model_dump()
        chapter_pred_data["catalogue_version"] = catalogue_version
        chapter_pred_data["index_version"] = index_version
        chapter_pred_data["total_active_chapters"] = 98
        logger.info(
            f"[Step1-Context-Aggregator] Product: '{base_product}' -> Chapter {pred.chapter} "
            f"({pred.chapter_title[:30]}) | Status: {pred.status} | Conf: {pred.confidence:.3f} | "
            f"Catalogue: {catalogue_version} | Index: {index_version}"
        )
    except Exception as e:
        logger.warning(f"Chapter predictor enrichment skipped in Step 1: {e}")

    # Synchronize facts into aggregated_attributes
    agg_attrs = s1.get("aggregated_attributes", {})
    if query_facts_data.get("material") and not agg_attrs.get("material"):
        agg_attrs["material"] = query_facts_data["material"]
    if query_facts_data.get("form") and (not agg_attrs.get("processing_state") or agg_attrs.get("processing_state") in ("Specific Commodity", "not_applicable", "none")):
        agg_attrs["processing_state"] = query_facts_data["form"]
    if query_facts_data.get("article"):
        agg_attrs["article_noun"] = query_facts_data["article"]

    return {
        "status": "success",
        "step": 1,
        "base_product": s1.get("base_product"),
        "user_clarification": s1.get("user_clarification"),
        "aggregated_attributes": agg_attrs,
        "query_facts": {
            "product_name": base_product,
            "article_noun": query_facts_data.get("article"),
            "constituent_material": query_facts_data.get("material"),
            "commodity_form": query_facts_data.get("form"),
            "commodity_family": query_facts_data.get("family"),
            "form_stage": query_facts_data.get("form_stage")
        },
        "master_search_string": s1.get("master_search_string"),
        "chapter_prediction": chapter_pred_data,
        "catalogue_version": catalogue_version,
        "index_version": index_version
    }


@app.post("/api/v1/hsn-rag/step2-vector-search")
async def step2_vector_search_endpoint(request: Request):
    """
    Step 2: Chapter 01–99 Categorizer + Vector Search Index.
    Searches the official tariff master using semantic vector embeddings + WCO statutory terminology,
    returning the Top 3 closest official 8-digit HSN matches.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    master_search_string = (body.get("master_search_string") or body.get("query") or body.get("product") or "").strip()
    aggregated_attributes = body.get("aggregated_attributes") or body.get("attributes") or {}

    if not master_search_string:
        raise HTTPException(status_code=400, detail="'master_search_string' is required.")

    from src.nlp.hsn_rag_layer import get_hsn_rag_application_layer
    rag_layer = get_hsn_rag_application_layer()
    s2 = rag_layer.stage2_vector_search_index(
        master_search_string=master_search_string,
        aggregated_attributes=aggregated_attributes
    )

    return {
        "status": "success",
        "step": 2,
        "routed_chapter": s2.get("routed_chapter"),
        "top_3_candidates": s2.get("top_3_candidates", []),
        "search_string_used": master_search_string
    }


@app.post("/api/v1/hsn-rag/step3-statutory-auditor")
async def step3_statutory_auditor_endpoint(request: Request):
    """
    Step 3: Elite Statutory Customs Auditor (GIR 1 & GIR 6 Dynamic Evaluation Protocol).
    Locks the official 8-digit HSN code enforcing all 4 Critical Tariff Audit Rules,
    or generates FORMAT B clarification questions if disambiguation is required.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    user_raw_input = (body.get("user_raw_input") or body.get("product") or body.get("product_description") or "").strip()
    context_aggregator_attributes = body.get("context_aggregator_attributes") or body.get("attributes") or {}
    vector_search_top_3_options = body.get("vector_search_top_3_options") or body.get("top_3_candidates") or []

    if not user_raw_input:
        raise HTTPException(status_code=400, detail="'user_raw_input' is required.")

    from src.nlp.hsn_rag_layer import get_hsn_rag_application_layer
    rag_layer = get_hsn_rag_application_layer()

    # If top_3 was not provided, derive on the fly
    if not vector_search_top_3_options:
        s1 = rag_layer.stage1_context_aggregator(user_raw_input, "", context_aggregator_attributes)
        context_aggregator_attributes = s1.get("aggregated_attributes", {})
        s2 = rag_layer.stage2_vector_search_index(s1.get("master_search_string"), context_aggregator_attributes)
        vector_search_top_3_options = s2.get("top_3_candidates", [])

    eval_result = rag_layer.evaluate_statutory_customs_auditor(
        user_raw_input=user_raw_input,
        context_aggregator_attributes=context_aggregator_attributes,
        vector_search_top_3_options=vector_search_top_3_options
    )

    clarification_data = None
    if eval_result.get("status") == "NEED_CLARIFICATION":
        try:
            clarification_data = rag_layer.generate_clarification_questions(
                user_raw_input,
                eval_result.get("missing_attributes", [])
            )
        except Exception as e:
            logger.warning(f"Clarification generation fallback: {e}")

    return {
        "status": "success",
        "step": 3,
        "auditor_verdict": eval_result,
        "clarification_questions": clarification_data
    }


@app.post("/api/v1/hsn-intelligence/generate-questions")
async def generate_clarification_questions(request: Request):
    """
    Dynamic Clarification Question Generation Endpoint (Schema Version 1.0.0).
    Generates targeted, grounded customer-facing clarification questions adhering
    strictly to the 12 Mandatory Rules.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    product_desc = (
        body.get("product_description")
        or body.get("original_description")
        or body.get("query")
        or body.get("item_description")
        or ""
    )
    ambiguity_result = body.get("ambiguity_analysis") or body.get("ambiguity_result")
    candidates = body.get("retrieved_candidates") or body.get("candidates") or []

    from src.ml.dynamic_question_generator import get_dynamic_question_generator
    generator = get_dynamic_question_generator()
    return generator.generate_questions(
        product_description=product_desc,
        ambiguity_result=ambiguity_result,
        retrieved_candidates=candidates
    )


@app.post("/api/v1/hsn-intelligence/submit-clarification")
async def submit_clarification(request: Request):
    """
    Day 14: Structured Clarification Answer Submission Endpoint.
    Validates question IDs, selected option IDs, required fields, and updates
    attributes before passing into the existing HSN verification workflow.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    product_desc = str(body.get("product_description", "")).strip()
    if not product_desc:
        raise HTTPException(status_code=400, detail="product_description is required")

    answers = body.get("clarification_answers")
    if not isinstance(answers, list) or len(answers) == 0:
        raise HTTPException(status_code=400, detail="clarification_answers array is required and cannot be empty")

    clarified_attributes: Dict[str, str] = {}
    unresolved_attributes: List[str] = []
    enriched_tokens: List[str] = []
    val_str: str = ""

    for idx, ans in enumerate(answers):
        if not isinstance(ans, dict):
            raise HTTPException(status_code=400, detail=f"Answer at index {idx} must be an object")

        qid = str(ans.get("question_id", "")).strip()
        attr = str(ans.get("attribute", "")).strip()
        opt_id = str(ans.get("selected_option_id", "")).strip()
        val = ans.get("selected_value")
        free_text = ans.get("free_text")
        is_unknown = bool(ans.get("is_unknown", False))

        if not qid:
            raise HTTPException(status_code=400, detail=f"question_id is required at index {idx}")
        if not attr:
            raise HTTPException(status_code=400, detail=f"attribute is required at index {idx}")
        if not opt_id:
            raise HTTPException(status_code=400, detail=f"selected_option_id is required for question {qid}")

        # Validate option ID pattern (e.g. OPT_001, OPT_UNKNOWN, OPT_OTHER)
        import re
        if not re.match(r"^OPT_[A-Za-z0-9_]+$", opt_id) and not re.match(r"^[A-Za-z0-9_]+$", opt_id):
            raise HTTPException(status_code=400, detail=f"Invalid option identifier '{opt_id}' for question {qid}")

        # Handle Unknown / Not sure: Keep unresolved, do not treat as confirmed
        if opt_id == "OPT_UNKNOWN" or is_unknown or val == "unknown":
            is_unknown = True
            val = None
            unresolved_attributes.append(attr)
            continue

        # If 'other' was selected, free_text must be provided
        if opt_id.endswith("OTHER") or str(val).lower() == "other":
            if not free_text or not str(free_text).strip():
                raise HTTPException(
                    status_code=422,
                    detail=f"Free-text description is required when 'Other' is selected for question {qid} ({attr})"
                )
            val = str(free_text).strip()

        # Valid confirmed attribute
        val_str = str(val).strip() if val is not None else ""
        if val_str:
            clarified_attributes[attr] = val_str
            clean_word = val_str.replace("_", " ")
            if clean_word.lower() not in product_desc.lower():
                enriched_tokens.append(clean_word)

    # Build enriched product description with Day 16 Fact-Grounding Validator
    from src.ml.deepseek_description_enricher import get_deepseek_description_enricher
    enricher = get_deepseek_description_enricher()
    enrichment_out = enricher.enrich_description(
        original_description=product_desc,
        clarification_answers=answers
    )
    enriched_desc = enrichment_out.enriched_description

    # Execute existing HSN verification workflow
    from src.ml.deepseek_hsn_verifier import get_deepseek_hsn_verifier
    verifier = get_deepseek_hsn_verifier()
    if verifier is None:
        raise HTTPException(status_code=503, detail="HSN verifier service unavailable")

    cust_sugg = ", ".join([v for v in clarified_attributes.values() if v]) if clarified_attributes else (val_str or enriched_desc)
    verification_result = verifier.verify_item(
        query=enriched_desc,
        base_hsn=None,
        save_to_store=False,
        customer_suggestion=cust_sugg
    )
    verification_result["customer_suggestion"] = cust_sugg
    verification_result["enriched_description"] = enriched_desc
    verification_result["clarified_attributes"] = clarified_attributes

    # Persist or update clarification session
    session_dict = None
    try:
        from src.ml.hsn_clarification_session import get_clarification_session_manager
        mgr = get_clarification_session_manager()
        req_session_id = body.get("session_id")
        session = mgr.get_session(req_session_id) if req_session_id else mgr.create_or_get_active_session(product_desc)
        if session:
            mgr.record_answers(session.session_id, answers)
            final_status = "MANUAL_REVIEW" if verification_result.get("status") == "MANUAL_REVIEW_REQUIRED" else "COMPLETED"
            mgr.transition_status(session.session_id, "SUBMITTED", reason="Answers submitted")
            mgr.transition_status(session.session_id, final_status, reason="Verification executed")
            session.verification_result = verification_result
            session_dict = session.to_contract_dict()
    except Exception as s_err:
        logger.warning(f"Could not persist clarification session: {s_err}")

    return {
        "status": "SUCCESS",
        "product_description": product_desc,
        "enriched_description": enriched_desc,
        "clarified_attributes": clarified_attributes,
        "unresolved_attributes": unresolved_attributes,
        "verification_result": verification_result,
        "enrichment": enrichment_out.model_dump(),
        "session": session_dict
    }


@app.post("/api/v1/hsn-clarification/sessions")
async def create_or_get_clarification_session(request: Request):
    """
    Creates or retrieves an active HSN Clarification Session adhering to Data Contract v1.0.0.
    Prevents duplicate sessions from being created unintentionally.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    product_desc = str(body.get("product_description", "")).strip()
    if not product_desc:
        raise HTTPException(status_code=400, detail="product_description is required")

    from src.ml.hsn_clarification_session import get_clarification_session_manager
    manager = get_clarification_session_manager()
    session = manager.create_or_get_active_session(
        product_description=product_desc,
        ambiguity_analysis=body.get("ambiguity_analysis"),
        generated_questions=body.get("generated_questions"),
        retrieved_candidates=body.get("retrieved_candidates") or body.get("candidates")
    )
    return session.to_contract_dict()


@app.get("/api/v1/hsn-clarification/sessions/{session_id}")
async def get_clarification_session(session_id: str):
    """Retrieves an HSN Clarification Session adhering to Data Contract v1.0.0."""
    from src.ml.hsn_clarification_session import get_clarification_session_manager
    manager = get_clarification_session_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return session.to_contract_dict()


@app.post("/api/v1/hsn-clarification/sessions/{session_id}/answers")
async def record_session_answers(session_id: str, request: Request):
    """Records customer answers into an active clarification session."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    answers = body.get("customer_answers") or body.get("answers") or []
    if not isinstance(answers, list):
        raise HTTPException(status_code=400, detail="customer_answers must be a list")

    from src.ml.hsn_clarification_session import get_clarification_session_manager
    manager = get_clarification_session_manager()
    try:
        session = manager.record_answers(session_id, answers)
        return session.to_contract_dict()
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")


@app.post("/api/v1/hsn-clarification/sessions/{session_id}/submit")
async def submit_session_and_verify(session_id: str, request: Request):
    """
    Submits clarification session responses and executes the verification workflow.
    Transitions: IN_PROGRESS -> SUBMITTED -> VERIFICATION_IN_PROGRESS -> COMPLETED (or MANUAL_REVIEW).
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    answers = body.get("customer_answers") or body.get("answers")
    from src.ml.hsn_clarification_session import get_clarification_session_manager
    manager = get_clarification_session_manager()
    try:
        session, v_res = manager.submit_and_verify(session_id, answers)
        res_data = session.to_contract_dict()
        res_data["verification_result"] = v_res
        return res_data
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))


@app.post("/api/v1/hsn-intelligence/enrich-description")
async def enrich_product_description(request: Request):
    """
    Day 16: Controlled Description Enrichment Endpoint (Schema Version 1.0).
    Improves incomplete product descriptions using ONLY original customer text
    and customer-confirmed clarification answers with deterministic fact-grounding.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    prod_desc = body.get("product_description")
    if not prod_desc or not str(prod_desc).strip():
        raise HTTPException(status_code=400, detail="product_description is required")

    clarif_answers = body.get("clarification_answers") or body.get("answers")
    confirmed_attrs = body.get("confirmed_attributes")

    from src.ml.deepseek_description_enricher import get_deepseek_description_enricher
    enricher = get_deepseek_description_enricher()
    out = enricher.enrich_description(
        original_description=str(prod_desc).strip(),
        clarification_answers=clarif_answers,
        confirmed_attributes=confirmed_attrs
    )
    return out.model_dump()


@app.post("/api/v1/hsn-clarification/sessions/{session_id}/enrich-and-reclassify")
async def enrich_and_reclassify_session(session_id: str, request: Request):
    """
    Day 16: Controlled Description Enrichment and Reclassification Workflow.
    Enriches description using confirmed session answers, validates fact-grounding,
    and executes reclassification through the verified HSN Intelligence engine.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    answers = body.get("customer_answers") or body.get("answers")
    from src.ml.hsn_clarification_session import get_clarification_session_manager
    manager = get_clarification_session_manager()
    try:
        session, enrichment_data, v_res = manager.enrich_and_reclassify(session_id, answers)
        res = session.to_contract_dict()
        res["enrichment"] = enrichment_data
        res["verification_result"] = v_res
        return res
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    except RuntimeError as re_err:
        raise HTTPException(status_code=409, detail=str(re_err))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as ex:
        logger.error(f"Error in enrich-and-reclassify: {ex}")
        raise HTTPException(status_code=500, detail=str(ex))


@app.post("/api/v1/hsn-verified-store/clear")
async def clear_verified_store():
    """Deletes all records from data/hsn_verified_store.parquet and empties cache."""
    from src.ml.hsn_verified_store import get_hsn_verified_store
    store = get_hsn_verified_store()
    store.clear()
    return {
        "status": "CLEARED",
        "stored_records_total": 0,
        "message": "All records deleted from data/hsn_verified_store.parquet."
    }


@app.get("/api/v1/hsn-verified-store/records")
async def get_verified_store_records():
    """Returns all records currently in data/hsn_verified_store.parquet."""
    from src.ml.hsn_verified_store import get_hsn_verified_store
    store = get_hsn_verified_store()
    records = store.get_all_records()
    return {
        "total_records": len(records),
        "records": records,
        "storage_file": "data/hsn_verified_store.parquet"
    }


@app.post("/api/v1/hsn-intelligence/check-preexistence")
async def check_preexistence_endpoint(request: Request):
    """
    Checks if a list of item descriptions already pre-exist in the verified store (data/hsn_verified_store.parquet).
    Provides sub-0.5ms instant retrieval for previously verified items.
    """
    from src.ml.hsn_verified_store import get_hsn_verified_store
    store = get_hsn_verified_store()
    try:
        body = await request.json()
    except Exception:
        body = {}

    items = body.get("items", []) if isinstance(body, dict) else (body if isinstance(body, list) else [])

    preexisting = []
    missing = []
    results = []

    for it in items:
        desc = it if isinstance(it, str) else (it.get("item_description") or it.get("query") or it.get("description") or "")
        cached = store.lookup(desc)
        if cached:
            preexisting.append(desc)
            results.append({
                "item_description": desc,
                "exists_in_store": True,
                "is_perfect_match": cached.get("is_perfect_match", False),
                "status": cached.get("status", "PRE_EXISTING"),
                "base_hsn": cached.get("base_hsn") or cached.get("hsn_code"),
                "base_formatted": cached.get("formatted_hsn"),
                "base_description": cached.get("description", ""),
                "base_rate": cached.get("gst_rate", 18.0),
                "qwen_hsn": cached.get("hsn_code"),
                "qwen_formatted": cached.get("formatted_hsn"),
                "qwen_description": cached.get("description", ""),
                "qwen_rate": cached.get("gst_rate", 18.0),
                "reasoning": cached.get("reasoning", "Retrieved directly from persistent verified knowledge store."),
                "is_cache_hit": True,
                "latency_ms": 0.1,
                "verification_model": "Pre-Existing Verified Store Record (<0.5ms)"
            })
        else:
            missing.append(desc)
            results.append({
                "item_description": desc,
                "exists_in_store": False,
                "is_perfect_match": False,
                "status": "NOT_IN_STORE",
                "base_hsn": "—",
                "base_formatted": "—",
                "base_description": "Not yet verified in store",
                "base_rate": 18.0,
                "qwen_hsn": "—",
                "qwen_formatted": "—",
                "qwen_description": "Click 'Run Qwen AI Verification & Store' to process and save",
                "qwen_rate": 18.0,
                "reasoning": "This item is not yet recorded in data/hsn_verified_store.parquet.",
                "is_cache_hit": False,
                "latency_ms": 0.0,
                "verification_model": "None"
            })

    return {
        "total_items": len(items),
        "preexisting_count": len(preexisting),
        "missing_count": len(missing),
        "storage_file": "data/hsn_verified_store.parquet",
        "stored_records_total": len(store.get_all_records()),
        "results": results
    }


@app.get("/api/v1/hsn-intelligence/verified-store")
async def get_hsn_verified_store_records():
    """
    Returns the persistent verified knowledge store records.
    Every record represents a unique, deduplicated, Qwen-verified HSN classification.
    """
    from src.ml.hsn_verified_store import get_hsn_verified_store
    store = get_hsn_verified_store()
    records = store.get_all_records()
    perfect_count = sum(1 for r in records if r.get("is_perfect_match"))
    corrected_count = sum(1 for r in records if not r.get("is_perfect_match"))
    return {
        "total_records": len(records),
        "perfect_matches": perfect_count,
        "corrected_by_qwen": corrected_count,
        "records": records
    }


@app.delete("/api/v1/hsn-intelligence/verified-store")
async def clear_hsn_verified_store_records():
    """
    Clears the persistent verified knowledge store.
    """
    from src.ml.hsn_verified_store import get_hsn_verified_store
    store = get_hsn_verified_store()
    store.clear()
    return {"status": "cleared", "total_records": 0}


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
        fname = (file.filename or "").lower()
        is_excel = fname.endswith((".xlsx", ".xls"))
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
        engine = get_hsn_search_engine() or get_hsn_intelligence_engine()
    scorer = get_hsn_misclass_scorer()

    if engine is not None:
        try:
            res = engine.search(q_trimmed, top_k=20)
            raw_matches = res.get("matches", res) if hasattr(res, "get") else (res["matches"] if isinstance(res, dict) else res)
            formatted = []
            for m in raw_matches:
                gst_val = float(m["standard_rate"]) if m.get("standard_rate") is not None else None
                item_dict = {
                    "hsn_code": m["hsn_code"],
                    "hsn_4digit": m.get("hsn_4digit", m["hsn_code"][:4]),
                    "description": m["description"],
                    "gst_rate": gst_val,
                    "igst_rate": gst_val,
                    "cgst_rate": round(gst_val / 2.0, 2) if gst_val is not None else None,
                    "sgst_rate": round(gst_val / 2.0, 2) if gst_val is not None else None,
                    "score": m.get("score", 1.0),
                    "confidence_pct": m.get("confidence_pct", 100.0),
                    "match_type": m.get("match_type", "Semantic Match"),
                    "is_blocked_17_5": m.get("is_blocked_17_5", 0),
                    "blocked_17_5_reason": m.get("blocked_17_5_reason", "Eligible")
                }
                formatted.append(item_dict)

            latency_val = res.get("latency_ms") if isinstance(res, dict) else round((time.perf_counter() - t_start) * 1000.0, 2)
            eval_res = res if isinstance(res, dict) else {"matches": raw_matches, "latency_ms": latency_val}
            locked_code = str(locked_hsn).strip() if locked_hsn else ""
            if locked_code and mode != "intelligence" and formatted:
                eval_res, formatted = _pin_locked_hsn(eval_res, formatted, locked_code)

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

            clarification_data = None
            if formatted and not q_trimmed.isdigit() and len(q_trimmed) >= 3:
                try:
                    from src.ml.deepseek_ambiguity_analyzer import get_deepseek_ambiguity_analyzer
                    from src.ml.dynamic_question_generator import get_dynamic_question_generator
                    ambig_analyzer = get_deepseek_ambiguity_analyzer()
                    if ambig_analyzer:
                        cand_list = [
                            {"candidate_id": f"CAND_{i+1:03d}", "hsn_code": m["hsn_code"], "description": m["description"]}
                            for i, m in enumerate(formatted[:4])
                        ]
                        ambig_res = ambig_analyzer.analyze_ambiguity(
                            original_description=q_trimmed,
                            retrieved_candidates=cand_list
                        )
                        if ambig_res.get("is_ambiguous") and ambig_res.get("recommended_action") == "REQUEST_CLARIFICATION":
                            q_gen = get_dynamic_question_generator()
                            questions_res = q_gen.generate_questions(
                                product_description=q_trimmed,
                                ambiguity_result=ambig_res,
                                retrieved_candidates=cand_list
                            )
                            clarification_data = {
                                "clarification_required": True,
                                "ambiguity_analysis": ambig_res,
                                "questions_schema": questions_res
                            }
                        elif ambig_res.get("recommended_action") == "MANUAL_REVIEW":
                            clarification_data = {
                                "clarification_required": False,
                                "manual_review_required": True,
                                "ambiguity_analysis": ambig_res,
                                "questions_schema": None
                            }
                except Exception as amb_err:
                    print(f"[WARN] Error evaluating ambiguity in search: {amb_err}")

            return {
                "query": raw_query,
                "matches": formatted,
                "gatekeeper": gatekeeper_data,
                "clarification": clarification_data,
                "latency_ms": latency_val,
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
        search_mask = (
            df[hsn_col].astype(str).str.lower().str.contains(search_key, na=False, regex=False) |
            df[desc_col].astype(str).str.lower().str.contains(search_key, na=False, regex=False)
        )
        filtered = df[search_mask]

        results = []
        for _, row in filtered.head(20).iterrows():
            _sr = row.get("standard_rate") if pd.notna(row.get("standard_rate")) else row.get("gst_rate")
            igst = float(_sr) if _sr is not None and pd.notna(_sr) else None
            cgst = round(igst / 2.0, 2) if igst is not None else None
            sgst = round(igst / 2.0, 2) if igst is not None else None

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


# =========================================================================
# MODULE 4: STATUTORY QUESTION ANSWERING BOT (GOOGLE FLAN-T5 + RAG RETRIEVAL)
# =========================================================================

from backend.qa_service import ask_qa, get_sample_questions, get_system_status


@app.get("/qa", response_class=HTMLResponse)
@app.get("/qa-bot", response_class=HTMLResponse)
async def serve_qa_page():
    """Serves the modernized Statutory Question Answering Bot UI."""
    candidates = [
        BASE_DIR / "frontend" / "qa.html",
        BASE_DIR / "static" / "qa.html"
    ]
    for p in candidates:
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                return HTMLResponse(content=f.read())
    raise HTTPException(status_code=404, detail="qa.html not found in frontend or static directory.")


@app.post("/api/qa/ask")
async def api_ask_qa(request: Request):
    """
    Module 4 QA Inference Endpoint:
    Accepts question, optional top_k, optional threshold.
    Returns extracted answer span, confidence score, raw context snippet,
    and distinct separated JSON payload and content data.
    """
    try:
        body = await request.json() if (await request.body()) else {}
        question = body.get("question") or body.get("query") or ""
        domain = body.get("domain", "e_invoice")
        top_k = body.get("top_k", None)
        threshold = body.get("threshold", None)
        from starlette.concurrency import run_in_threadpool
        return await run_in_threadpool(ask_qa, question=question, domain=domain, top_k=top_k, threshold=threshold)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"QA inference error: {str(e)}")


@app.get("/api/qa/samples")
async def api_qa_samples(domain: Optional[str] = None):
    """Returns curated statutory questions for quick-select demonstration."""
    try:
        return {"status": "success", "samples": get_sample_questions(domain=domain)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving samples: {str(e)}")


@app.get("/api/qa/status")
async def api_qa_status():
    """Returns offline QA Bot system readiness, device, model, and index metrics."""
    try:
        return get_system_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error checking status: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    print("\n🚀 Starting GST Sentinel Server at http://127.0.0.1:8000 ...")
    print("👉 Statutory Question Answering Bot        : http://127.0.0.1:8000/qa")
    print("👉 GST Sentinel Ingestion & Lakehouse Portal: http://127.0.0.1:8000/ingestion")
    print("👉 E-Invoice & E-Way Converter Dashboard    : http://127.0.0.1:8000/converter")
    print("👉 HSN Code Search Engine                   : http://127.0.0.1:8000/\n")
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)


