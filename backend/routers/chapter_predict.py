"""
backend/routers/chapter_predict.py
==================================
FastAPI Router for Product-to-HSN-Chapter Prediction Module.

Endpoints:
- POST /api/chapter/predict: Predict 2-digit HSN chapter for a single product name
- POST /api/chapter/batch: Predict chapters for a list of products or uploaded CSV
- GET  /api/chapter/health: Health check, index status, and LLM reachability
- POST /api/chapter/feedback: Log user corrections to data/feedback/chapter_feedback.jsonl
- GET  /chapter-predictor: Serves offline-ready Web UI
"""

import csv
import io
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from src.chapter_predictor.predictor import ChapterPredictor, ChapterPrediction

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Chapter Predictor"])

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
FEEDBACK_DIR = ROOT_DIR / "data" / "feedback"
FEEDBACK_FILE = FEEDBACK_DIR / "chapter_feedback.jsonl"


# =====================================================================
# REQUEST & RESPONSE SCHEMAS
# =====================================================================

class PredictRequest(BaseModel):
    product_name: str = Field(..., description="Commercial free-text product name")
    top_k: int = Field(default=3, ge=1, le=10, description="Number of alternative chapters to return")


class BatchPredictRequest(BaseModel):
    product_names: List[str] = Field(..., max_length=500, description="List of product descriptions (max 500)")
    top_k: int = Field(default=3, ge=1, le=10)


class FeedbackRequest(BaseModel):
    product_name: str
    predicted_chapter: str
    actual_chapter: Optional[str] = None
    is_correct: bool
    notes: Optional[str] = ""


class HealthResponse(BaseModel):
    status: str
    lexical_index_loaded: bool
    lexical_records_count: int
    semantic_index_loaded: bool
    semantic_model_name: Optional[str]
    llm_reachable: bool
    available_llm_models: List[str]
    timestamp: str


# =====================================================================
# API ENDPOINTS
# =====================================================================

@router.post("/api/chapter/predict", response_model=ChapterPrediction)
async def predict_single_chapter(req: PredictRequest):
    """
    Predicts the most likely 2-digit HSN chapter (01–99) for a single product description.
    """
    predictor = ChapterPredictor.get_instance()
    pred = predictor.predict(req.product_name, top_k=req.top_k)
    return pred


@router.post("/api/chapter/batch")
async def predict_batch_chapters(
    request: Request,
    file: Optional[UploadFile] = File(None)
):
    """
    Batch chapter prediction: accepts either JSON list of product names or a CSV file upload.
    If CSV is uploaded, returns a downloadable CSV with predicted chapters and evidence.
    """
    predictor = ChapterPredictor.get_instance()
    content_type = request.headers.get("content-type", "")

    # 1. Handle CSV file upload (multipart/form-data)
    if "multipart/form-data" in content_type:
        form = await request.form()
        uploaded_file = form.get("file")
        if not uploaded_file or not hasattr(uploaded_file, "read"):
            raise HTTPException(status_code=400, detail="No file field uploaded in form-data.")

        contents = await uploaded_file.read()
        text_stream = io.StringIO(contents.decode("utf-8", errors="ignore"))
        reader = csv.reader(text_stream)
        
        raw_items = []
        for row in reader:
            if not row:
                continue
            item = row[0].strip()
            # Skip common header rows
            if item.lower() in ("product", "product_name", "item", "description", "item_description"):
                continue
            if item:
                raw_items.append(item)
            if len(raw_items) >= 500:
                break

        if not raw_items:
            raise HTTPException(status_code=400, detail="No valid product rows found in uploaded CSV.")

        predictions = predictor.predict_batch(raw_items, top_k=3)

        # Build CSV response
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Product Name", "Normalized", "Chapter", "Chapter Title",
            "Confidence", "Status", "Top Alternative 1", "Top Alternative 2",
            "Evidence HSN", "Evidence Description", "Reason"
        ])
        for p in predictions:
            alt1 = f"{p.alternatives[0].chapter}: {p.alternatives[0].title}" if len(p.alternatives) > 0 else ""
            alt2 = f"{p.alternatives[1].chapter}: {p.alternatives[1].title}" if len(p.alternatives) > 1 else ""
            ev_hsn = p.evidence[0].hsn_code if p.evidence else ""
            ev_desc = p.evidence[0].description if p.evidence else ""
            writer.writerow([
                p.product_name, p.normalized, p.chapter, p.chapter_title,
                p.confidence, p.status, alt1, alt2, ev_hsn, ev_desc, p.reason
            ])

        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=chapter_predictions.csv"}
        )

    # 2. Handle JSON request body
    try:
        body_json = await request.json()
    except Exception:
        body_json = {}

    product_names = body_json.get("product_names", [])
    top_k = int(body_json.get("top_k", 3))

    if product_names:
        preds = predictor.predict_batch(product_names, top_k=top_k)
        return {"total": len(preds), "predictions": preds}

    raise HTTPException(status_code=400, detail="Provide either a JSON list of product_names or a CSV file upload.")


@router.get("/api/chapter/health", response_model=HealthResponse)
async def get_chapter_predictor_health():
    """
    Checks the status of the BM25 index, semantic vector matrix, and Ollama LLM connectivity.
    """
    predictor = ChapterPredictor.get_instance()
    lex_ok = predictor.lexical_index._is_loaded
    lex_count = len(predictor.lexical_index.records)
    sem_ok = predictor.semantic_index._is_loaded
    sem_model = predictor.semantic_index.model_name

    llm_up, models = predictor.llm_reranker.check_ollama_health()

    return HealthResponse(
        status="healthy" if (lex_ok or sem_ok) else "initializing",
        lexical_index_loaded=lex_ok,
        lexical_records_count=lex_count,
        semantic_index_loaded=sem_ok,
        semantic_model_name=sem_model,
        llm_reachable=llm_up,
        available_llm_models=models,
        timestamp=datetime.now(timezone.utc).isoformat()
    )


@router.post("/api/chapter/feedback")
async def record_user_feedback(req: FeedbackRequest):
    """
    Stores user evaluation / correction feedback in data/feedback/chapter_feedback.jsonl.
    """
    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "product_name": req.product_name,
        "predicted_chapter": req.predicted_chapter,
        "actual_chapter": req.actual_chapter,
        "is_correct": req.is_correct,
        "notes": req.notes or ""
    }
    with open(FEEDBACK_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return {"status": "success", "message": "Feedback recorded successfully."}


@router.get("/chapter-predictor", response_class=HTMLResponse)
async def serve_chapter_predictor_ui():
    """
    Serves the offline-ready Chapter Predictor UI screen.
    """
    ui_path = ROOT_DIR / "templates" / "chapter_predictor.html"
    if not ui_path.exists():
        ui_path = ROOT_DIR / "backend" / "templates" / "chapter_predictor.html"

    if ui_path.exists():
        with open(ui_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())

    return HTMLResponse(
        content="<h1>Chapter Predictor UI template not found. Please build templates/chapter_predictor.html</h1>",
        status_code=404
    )

