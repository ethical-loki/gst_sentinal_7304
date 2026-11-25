"""
Module: backend/main.py
Description: Complete FastAPI backend serving Excel-based HSN/SAC search with
             dtype=str to preserve leading zeros, dynamic pathing, and modern UI.
"""

import os

# Offline transformers & optimal thread allocation
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
os.environ.setdefault("MKL_NUM_THREADS", "4")
os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "4")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")

import asyncio
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

@app.on_event('startup')
async def preload_services():
    logger.info('[INFO] Core Three-Stage HSN Engine configured for on-demand lazy initialization.')

_hsn_v2_pipeline = None


def get_hsn_v2_pipeline():
    global _hsn_v2_pipeline
    if _hsn_v2_pipeline is None:
        try:
            from src.ml.hsn_v2_pipeline import HSNIntelligenceV2
            _hsn_v2_pipeline = HSNIntelligenceV2()
            print("[OK] HSNIntelligenceV2 pipeline initialized")
        except Exception as e:
            print(f"[WARN] Failed to load HSNIntelligenceV2: {e}")
            _hsn_v2_pipeline = None
    return _hsn_v2_pipeline


@app.post("/api/v1/hsn-rag/step1-context-aggregator")
def step1_context_aggregator_endpoint(body: Dict[str, Any] = Body(default={})):
    """
    Step 1: Context Aggregator (Product + Material + Form + Chapter Categorization).
    Extracts base product, material composition, form/state, and active Master Chapters.
    """
    base_product = (body.get("product") or body.get("base_product") or body.get("product_name") or "").strip()
    user_clarification = (body.get("clarification") or body.get("user_clarification") or "").strip()
    existing_attributes = body.get("attributes") or body.get("existing_attributes") or None
    use_cache = bool(body.get("use_cache", True))

    if not base_product:
        raise HTTPException(status_code=400, detail="'product' is required.")

    from src.nlp.hsn_rag_layer import get_hsn_rag_application_layer
    rag_layer = get_hsn_rag_application_layer()
    s1 = rag_layer.stage1_context_aggregator(
        base_product=base_product,
        user_clarification=user_clarification,
        existing_attributes=existing_attributes
    )

    # --- Intent Extraction Stage (Vocabulary Retrieval + LLM Translation + File Grounding) ---
    intent_data = None
    product_intent = s1.get("product_intent") or {}
    search_query_for_retrieval = product_intent.get("article_search_query") or base_product
    try:
        from src.nlp.intent_extractor import get_intent_extractor
        extractor = get_intent_extractor()
        intent_res = extractor.extract_intent(base_product, use_cache=use_cache)
        intent_data = intent_res.model_dump()
        if intent_res.synthesized_search_string:
            search_query_for_retrieval = intent_res.synthesized_search_string
    except Exception as ie_err:
        logger.warning(f"Intent extraction skipped in Step 1: {ie_err}")

    chapter_pred_data = None
    query_facts_data = {}
    catalogue_version = "v2.0.0-dynamic-statutory"
    index_version = "bge-m3-lineage-v1"
    try:
        from src.chapter_predictor.normalize import extract_query_facts
        query_facts_data = extract_query_facts(base_product)
    except Exception as e:
        logger.warning(f"Fact extraction skipped in Step 1: {e}")

    # --- Layer 4: Smart UI & Ambiguity Decision Engine (Hybrid Retrieval + Cross-Encoder) ---
    disambiguation_data = {
        "is_ambiguous": False,
        "banner_type": "NONE",
        "banner_title": "",
        "clarification_question": None,
        "disambiguation_options": [],
        "direct_match": None,
        "distinct_chapters_count": 0,
        "descriptive_report": None
    }
    try:
        from src.search.ambiguity_controller import evaluate_product_ambiguity
        _eval_res = evaluate_product_ambiguity(search_query_for_retrieval)
        disambiguation_data = {
            "is_ambiguous": _eval_res.is_ambiguous,
            "banner_type": _eval_res.banner_type,
            "banner_title": _eval_res.banner_title,
            "clarification_question": _eval_res.clarification_question,
            "disambiguation_options": [o.model_dump() for o in _eval_res.disambiguation_options],
            "direct_match": _eval_res.direct_match.model_dump() if _eval_res.direct_match else None,
            "distinct_chapters_count": _eval_res.distinct_chapters_count,
            "descriptive_report": _eval_res.descriptive_report.model_dump() if _eval_res.descriptive_report else None
        }
    except Exception as _ar_e:
        logger.warning(f"Layer 4 ambiguity controller skipped in Step 1 for '{base_product}': {_ar_e}")

    from src.search.hybrid_retrieval import HybridHSNEngine
    engine = HybridHSNEngine.get_instance()
    active_master_chapters = {
        str(r.get("chapter_code") or r.get("chapter") or "").strip().zfill(2)
        for r in getattr(engine, "records", [])
        if str(r.get("chapter_code") or r.get("chapter") or "").strip()
    }
    try:
        if disambiguation_data.get("direct_match") and (
            not active_master_chapters
            or disambiguation_data["direct_match"].get("chapter_code") in active_master_chapters
        ):
            dm = disambiguation_data["direct_match"]
            chapter_pred_data = {
                "product_name": base_product,
                "normalized": base_product.lower(),
                "chapter": dm.get("chapter_code", ""),
                "chapter_title": dm.get("chapter_title", ""),
                "confidence": 0.99,
                "status": "OK",
                "alternatives": [],
                "evidence": [
                    {
                        "chapter": dm.get("chapter_code", ""),
                        "chapter_title": dm.get("chapter_title", ""),
                        "hsn_code": dm.get("hsn_code", ""),
                        "description": dm.get("hsn_description", ""),
                        "score": dm.get("score", 1.0)
                    }
                ],
                "reason": f"High-confidence statutory classification in Chapter {dm.get('chapter_code')}",
                "catalogue_version": catalogue_version,
                "index_version": index_version,
                "total_active_chapters": len(active_master_chapters)
            }
        elif disambiguation_data.get("disambiguation_options"):
            valid_opts = [
                o for o in disambiguation_data["disambiguation_options"]
                if not active_master_chapters or o.get("chapter_code") in active_master_chapters
            ]
            disambiguation_data["disambiguation_options"] = valid_opts
            if valid_opts:
                first_opt = valid_opts[0]
                desc_rep = disambiguation_data.get("descriptive_report") or {}
                calculated_conf = float(desc_rep.get("confidence_score", 45.0)) / 100.0

                opt_chaps = {o.get("chapter_code") for o in valid_opts if o.get("chapter_code")}
                if len(opt_chaps) > 1:
                    status = "AMBIGUOUS_MATERIAL"
                    banner_type = "MULTI_CHAPTER_AMBIGUITY"
                else:
                    status = "NEEDS_SELECTION"
                    banner_type = "SAME_CHAPTER_VARIANT"

                disambiguation_data["banner_type"] = banner_type
                chapter_pred_data = {
                    "product_name": base_product,
                    "normalized": base_product.lower(),
                    "chapter": first_opt.get("chapter_code", "NONE"),
                    "chapter_title": first_opt.get("chapter_title", "Multiple Candidates"),
                    "confidence": min(calculated_conf, 0.49),
                    "status": status,
                    "alternatives": [],
                    "evidence": [
                        {
                            "chapter": o.get("chapter_code", ""),
                            "chapter_title": o.get("chapter_title", ""),
                            "hsn_code": o.get("hsn_code", ""),
                            "description": o.get("hsn_description", ""),
                            "score": o.get("score", 1.0)
                        }
                        for o in valid_opts[:5]
                    ],
                    "reason": f"Status: {status}. Multiple candidate tariff items identified under GIR compliance. User selection required to finalize 8-digit HSN code.",
                    "catalogue_version": catalogue_version,
                    "index_version": index_version,
                    "total_active_chapters": len(active_master_chapters)
                }
            else:
                disambiguation_data["is_ambiguous"] = False
                disambiguation_data["banner_type"] = "NONE"

        if chapter_pred_data is None:
            cands = engine.search(search_query_for_retrieval, top_k=5)
            valid_cands = [
                c for c in cands
                if not active_master_chapters or c.chapter_code in active_master_chapters
            ]
            if valid_cands and valid_cands[0].final_score >= 0.20:
                top_cand = valid_cands[0]
                chapter_pred_data = {
                    "product_name": base_product,
                    "normalized": base_product.lower(),
                    "chapter": top_cand.chapter_code,
                    "chapter_title": top_cand.chapter_title,
                    "confidence": min(round(top_cand.final_score, 2), 0.49),
                    "status": "NEEDS_SELECTION",
                    "alternatives": [],
                    "evidence": [
                        {
                            "chapter": c.chapter_code,
                            "chapter_title": c.chapter_title,
                            "hsn_code": c.hsn_code,
                            "description": c.hsn_description,
                            "score": round(c.final_score, 4)
                        }
                        for c in valid_cands[:5]
                    ],
                    "reason": "Status: NEEDS_SELECTION. Multiple candidate tariff items identified under GIR compliance. User selection required to finalize 8-digit HSN code.",
                    "catalogue_version": catalogue_version,
                    "index_version": index_version,
                    "total_active_chapters": len(active_master_chapters)
                }
            else:
                chapter_pred_data = {
                    "product_name": base_product,
                    "normalized": base_product.lower(),
                    "chapter": "NONE",
                    "chapter_title": "Not in Statutory Master Schedule",
                    "confidence": 0.0,
                    "status": "UNRECOGNIZED",
                    "alternatives": [],
                    "evidence": [],
                    "reason": f"Product '{base_product}' did not match any active entries across the {len(active_master_chapters)}-chapter statutory tariff master.",
                    "catalogue_version": catalogue_version,
                    "index_version": index_version,
                    "total_active_chapters": len(active_master_chapters)
                }

        # Handle distinct outcome types from Intent Extraction (UNRECOGNIZED, OUT_OF_SCHEDULE, AMBIGUOUS_MATERIAL)
        if intent_data and (intent_data.get("outcome_type") == "UNRECOGNIZED" or intent_data.get("reading_confidence") == "unclear"):
            chapter_pred_data["status"] = "UNRECOGNIZED"
            chapter_pred_data["confidence"] = 0.0
            chapter_pred_data["chapter"] = "NONE"
            chapter_pred_data["chapter_title"] = "Unrecognized Query"
            unrec_reason = (
                f"Query '{base_product}' is too vague or unrecognized under statutory customs tariff. "
                f"Clarification required."
            )
            chapter_pred_data["reason"] = unrec_reason
            disambiguation_data["is_ambiguous"] = False
            disambiguation_data["banner_type"] = "NONE"
            disambiguation_data["direct_match"] = None
            disambiguation_data["disambiguation_options"] = []
            disambiguation_data["descriptive_report"] = {
                "article_understood_as": f"Query '{base_product}' is unrecognized.",
                "recommended_hsn": "Needs confirmation",
                "confidence": "Low",
                "confidence_score": 0.0,
                "reasoning": unrec_reason,
                "other_plausible_candidates": [],
                "missing_information": ["Product constituent material, intended function, or standard trade denomination."],
                "verification_note": "Codes should be checked against the current official CBIC/GST HSN schedule before filing or invoicing.",
                "formatted_text": (
                    f"Article understood as: Query '{base_product}' is unrecognized.\n\n"
                    f"Recommended HSN: Needs confirmation\n"
                    f"Confidence: Low\n"
                    f"Reasoning: {unrec_reason}\n\n"
                    f"Missing information that would change the result (if any): Product constituent material, intended function, or standard trade denomination.\n\n"
                    f"Verification note: Codes should be checked against the current official CBIC/GST HSN schedule before filing or invoicing."
                )
            }
        elif intent_data and intent_data.get("outcome_type") == "OUT_OF_SCHEDULE":
            chapter_pred_data["status"] = "OUT_OF_SCHEDULE"
            chapter_pred_data["confidence"] = 0.0
            chapter_pred_data["chapter"] = "NONE"
            chapter_pred_data["chapter_title"] = "Out of Schedule"
            chapter_pred_data["reason"] = (
                intent_data.get("error_message") or
                f"Product '{base_product}' falls outside the {len(active_master_chapters)} active statutory chapters."
            )
            disambiguation_data["direct_match"] = None
            disambiguation_data["is_ambiguous"] = False
            disambiguation_data["banner_type"] = "NOT_AVAILABLE"
            disambiguation_data["descriptive_report"] = {
                "article_understood_as": f"Commodity ('{base_product}') identified outside active statutory schedule.",
                "recommended_hsn": "None (Chapter outside active schedule)",
                "confidence": "Low",
                "confidence_score": 0.0,
                "reasoning": intent_data.get("error_message") or "Statutory classification falls outside loaded schedule.",
                "other_plausible_candidates": [],
                "missing_information": [f"Target chapter not present in active {len(active_master_chapters)}-chapter dataset"],
                "verification_note": "Codes should be checked against the current official CBIC/GST HSN schedule before filing or invoicing."
            }
        elif intent_data and intent_data.get("outcome_type") == "AMBIGUOUS_MATERIAL":
            chapter_pred_data["status"] = "AMBIGUOUS_MATERIAL"
            chapter_pred_data["confidence"] = 0.40
            chapter_pred_data["chapter"] = "NONE"
            chapter_pred_data["chapter_title"] = "Material Ambiguity"
            disambiguation_data["direct_match"] = None
            disambiguation_data["is_ambiguous"] = True
            disambiguation_data["banner_type"] = "MULTI_CHAPTER_AMBIGUITY"
            disambiguation_data["banner_title"] = "CONSTITUENT MATERIAL REQUIRED"
            disambiguation_data["clarification_question"] = f"What material and construction is the {base_product}?"
        else:
            rep = disambiguation_data.get("descriptive_report") or {}
            if not disambiguation_data.get("disambiguation_options") and (rep.get("confidence") == "Low" or "Unrecognized commercial query" in str(rep.get("article_understood_as"))):
                chapter_pred_data["status"] = "UNRECOGNIZED"
                chapter_pred_data["confidence"] = min(chapter_pred_data.get("confidence", 0.0), 0.35)
                chapter_pred_data["reason"] = (
                    f"Query '{base_product}' is unrecognized or confidence threshold (0.50) is not met. "
                    f"Requires customer clarification or manual review."
                )

        # Enforce strict membership in loaded statutory master dataset chapters
        if active_master_chapters and chapter_pred_data.get("chapter") not in active_master_chapters:
            if chapter_pred_data.get("status") == "AMBIGUOUS_MATERIAL":
                disambiguation_data["is_ambiguous"] = True
                disambiguation_data["banner_type"] = "MULTI_CHAPTER_AMBIGUITY"
            else:
                out_status = "OUT_OF_SCHEDULE" if (intent_data and intent_data.get("outcome_type") == "OUT_OF_SCHEDULE") else "UNRECOGNIZED"
                chapter_pred_data["status"] = out_status
                chapter_pred_data["chapter"] = "NONE"
                chapter_pred_data["chapter_title"] = "Not in Statutory Master Schedule"
                chapter_pred_data["confidence"] = 0.0
                chapter_pred_data["evidence"] = []
                chapter_pred_data["alternatives"] = []
                chapter_pred_data["reason"] = (
                    f"Product '{base_product}' could not be resolved to an active chapter in the "
                    f"{len(active_master_chapters)}-chapter statutory tariff master."
                )
                disambiguation_data["direct_match"] = None
                disambiguation_data["is_ambiguous"] = False
                disambiguation_data["banner_type"] = "NOT_AVAILABLE"

        # Final banner check: MULTI_CHAPTER_AMBIGUITY ONLY when options span > 1 distinct chapters
        if chapter_pred_data.get("status") in ("UNRECOGNIZED", "OUT_OF_SCHEDULE"):
            disambiguation_data["disambiguation_options"] = []
            disambiguation_data["banner_type"] = "NONE" if chapter_pred_data.get("status") == "UNRECOGNIZED" else "NOT_AVAILABLE"
            disambiguation_data["is_ambiguous"] = False
            if not disambiguation_data.get("descriptive_report"):
                disambiguation_data["descriptive_report"] = {
                    "article_understood_as": f"An item ('{base_product}') queried by user.",
                    "recommended_hsn": "None (Not resolved in statutory master)",
                    "confidence": "Low",
                    "confidence_score": 0.0,
                    "reasoning": (
                        f"The queried product '{base_product}' did not match an active tariff item across the "
                        f"{len(active_master_chapters)}-chapter statutory master dataset."
                    ),
                    "other_plausible_candidates": [],
                    "missing_information": [
                        "Provide constituent material, functional application, or statutory commodity description."
                    ],
                    "verification_note": "Codes should be checked against the current official CBIC/GST HSN schedule before filing or invoicing."
                }
        else:
            final_opts = disambiguation_data.get("disambiguation_options", [])
            final_opt_chaps = {o.get("chapter_code") for o in final_opts if o.get("chapter_code")}
            if len(final_opt_chaps) > 1:
                disambiguation_data["banner_type"] = "MULTI_CHAPTER_AMBIGUITY"
            elif len(final_opt_chaps) == 1:
                disambiguation_data["banner_type"] = "SAME_CHAPTER_VARIANT"
            elif chapter_pred_data.get("status") == "AMBIGUOUS_MATERIAL":
                disambiguation_data["banner_type"] = "MULTI_CHAPTER_AMBIGUITY"
            elif disambiguation_data.get("banner_type") not in ("NOT_AVAILABLE", "NONE"):
                disambiguation_data["banner_type"] = "NOT_AVAILABLE"

        logger.info(
            f"[Step1-Context-Aggregator] Product: '{base_product}' -> Chapter {chapter_pred_data.get('chapter')} "
            f"({str(chapter_pred_data.get('chapter_title', ''))[:30]})"
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

    # Synchronize with HSN Intelligence V2 (Phases 1-7)
    v2_verification = None
    try:
        v2_pipe = get_hsn_v2_pipeline()
        if v2_pipe is not None:
            v2_res = v2_pipe.classify(base_product)
            v2_verification = {
                "status": v2_res.status,
                "prediction_mode": v2_res.prediction_mode,
                "selected_hsn": v2_res.selected_hsn,
                "selected_chapter": v2_res.selected_chapter,
                "selected_description": v2_res.selected_description,
                "confidence": v2_res.confidence,
                "relevance_confidence": v2_res.relevance_confidence,
                "chapter_confidence": v2_res.chapter_confidence,
                "hsn_confidence": v2_res.hsn_confidence,
                "abstention_reason": v2_res.abstention_reason,
                "separating_attributes": v2_res.separating_attributes,
                "clarification_question": v2_res.clarification_question,
                "clarification_options": v2_res.clarification_options,
                "statutory_matches": v2_res.statutory_matches,
                "active_vs_statutory": v2_res.active_vs_statutory,
                "rationale": v2_res.rationale,
            }
            if v2_res.status == "OUT_OF_SCHEDULE" and chapter_pred_data.get("status") in ("UNRECOGNIZED", "OUT_OF_SCHEDULE", "NEEDS_SELECTION"):
                chapter_pred_data["status"] = "OUT_OF_SCHEDULE"
                chapter_pred_data["chapter"] = "NONE"
                chapter_pred_data["chapter_title"] = f"Out of Active Schedule (Statutory Ch {v2_res.selected_chapter})"
                chapter_pred_data["reason"] = v2_res.rationale
    except Exception as e:
        logger.warning(f"HSNIntelligenceV2 sync skipped: {e}")

    from src.nlp.stage1_chapter_analyzer import build_canonical_stage1_result
    canonical_stage1 = build_canonical_stage1_result(
        description=base_product,
        clarification=user_clarification,
    )

    return {
        "status": "success",
        "step": 1,
        "base_product": s1.get("base_product"),
        "user_clarification": s1.get("user_clarification"),
        "aggregated_attributes": agg_attrs,
        "product_intent": product_intent,
        "stage1_result": canonical_stage1,
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
        "disambiguation": disambiguation_data,
        "intent_extraction": intent_data,
        "v2_verification": v2_verification,
        "catalogue_version": catalogue_version,
        "index_version": index_version
    }


@app.post("/api/v1/hsn-v2/classify")
async def classify_hsn_v2(payload: dict):
    product = (payload.get("product") or payload.get("query") or "").strip()
    if not product:
        raise HTTPException(status_code=400, detail="Product description is required.")
    v2_pipe = get_hsn_v2_pipeline()
    if v2_pipe is None:
        raise HTTPException(status_code=503, detail="HSNIntelligenceV2 pipeline unavailable.")
    res = await asyncio.to_thread(v2_pipe.classify, product)
    return {
        "status": res.status,
        "prediction_mode": res.prediction_mode,
        "query": res.query,
        "selected_hsn": res.selected_hsn,
        "selected_chapter": res.selected_chapter,
        "selected_description": res.selected_description,
        "confidence": res.confidence,
        "relevance_confidence": res.relevance_confidence,
        "chapter_confidence": res.chapter_confidence,
        "hsn_confidence": res.hsn_confidence,
        "abstention_reason": res.abstention_reason,
        "separating_attributes": res.separating_attributes,
        "clarification_question": res.clarification_question,
        "clarification_options": res.clarification_options,
        "statutory_matches": res.statutory_matches,
        "active_vs_statutory": res.active_vs_statutory,
        "rationale": res.rationale,
    }


@app.post("/api/v1/hsn-v2/feedback")
async def submit_hsn_v2_feedback(payload: dict):
    query = (payload.get("query") or "").strip()
    predicted_hsn = (payload.get("predicted_hsn") or "").strip()
    if not query or not predicted_hsn:
        raise HTTPException(status_code=400, detail="Both query and predicted_hsn are required.")
    from src.training.feedback_collector import FeedbackCollector
    fc = FeedbackCollector()
    fid = fc.record_pending_feedback(
        query=query,
        predicted_hsn=predicted_hsn,
        predicted_context=str(payload.get("predicted_context") or ""),
        predicted_score=float(payload.get("predicted_score") or 0.0),
        customer_selected_hsn=payload.get("customer_selected_hsn"),
        reason=str(payload.get("reason") or "Flagged from UI"),
    )
    return {"status": "recorded", "feedback_id": fid}


_multi_candidate_engine = None


def get_multi_candidate_engine():
    global _multi_candidate_engine
    if _multi_candidate_engine is None:
        from src.ml.multi_candidate_engine import MultiCandidateEngine
        v2 = get_hsn_v2_pipeline()
        if v2 is not None:
            _multi_candidate_engine = MultiCandidateEngine(
                hybrid_engine=v2.hybrid_engine,
                relevance_classifier=v2.classifier,
                statutory_index=v2.statutory_index,
                feedback_collector=v2.feedback,
            )
        else:
            _multi_candidate_engine = MultiCandidateEngine()
    return _multi_candidate_engine


@app.post("/api/v1/hsn-v2/classify-adaptive")
async def classify_hsn_v2_adaptive(payload: dict):
    stage1_result = payload.get("stage1_result")
    if stage1_result is not None:
        if not isinstance(stage1_result, dict) or not (
            stage1_result.get("primary_commercial_article")
            or stage1_result.get("product_intent")
            or stage1_result.get("original_description")
        ):
            raise HTTPException(
                status_code=400,
                detail="Invalid stage1_result payload: must include primary_commercial_article, product_intent, or original_description.",
            )
    product = (
        payload.get("product")
        or payload.get("query")
        or payload.get("description")
        or (stage1_result.get("original_description") if isinstance(stage1_result, dict) else "")
        or ""
    ).strip()
    if not product:
        raise HTTPException(status_code=400, detail="Product description is required.")
    engine = get_multi_candidate_engine()
    return await asyncio.to_thread(
        engine.classify_adaptive,
        description=product,
        confirmed_attributes=payload.get("confirmed_attributes"),
        page=int(payload.get("page") or 1),
        page_size=int(payload["page_size"]) if payload.get("page_size") is not None else 20,
        exhaustive=bool(payload.get("exhaustive", False)),
        stage1_result=stage1_result,
    )


@app.post("/api/v1/hsn-v2/clarify-adaptive")
async def clarify_hsn_v2_adaptive(payload: dict):
    orig = (
        payload.get("original_description")
        or payload.get("description")
        or payload.get("product")
        or payload.get("query")
        or ""
    ).strip()
    if not orig:
        raise HTTPException(status_code=400, detail="original_description is required.")
    engine = get_multi_candidate_engine()
    return await asyncio.to_thread(
        engine.clarify_and_refine,
        original_description=orig,
        previous_confirmed=payload.get("previous_confirmed") or payload.get("confirmed_attributes"),
        new_answers=payload.get("new_answers") or {},
        page=int(payload.get("page") or 1),
        page_size=int(payload["page_size"]) if payload.get("page_size") is not None else 20,
    )



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

if __name__ == "__main__":
    import uvicorn
    print("\n🚀 Starting GST Sentinel Server at http://127.0.0.1:8000 ...")
    print("👉 HSN Code Search Engine                   : http://127.0.0.1:8000/\n")
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
