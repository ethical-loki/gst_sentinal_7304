"""
Module: backend/qa_service.py
Description: Production QA Bot integration service for GST Sentinel.
             Connects SQLite FTS5 BM25 retrieval and Longformer extractive reader
             with dedicated payload formatting and context extraction.
"""

import sys
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

# Root paths
BASE_DIR = Path(__file__).resolve().parent.parent
QA_BOT_DIR = BASE_DIR / "Questions_answering_bot"
QA_SRC_DIR = QA_BOT_DIR / "src"

# Ensure QA Bot src is on sys.path
if str(QA_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(QA_SRC_DIR))

_qa_bot_instance = None


def get_qa_bot():
    """Lazy-load the QABot instance so server startup remains instant."""
    global _qa_bot_instance
    if _qa_bot_instance is None:
        from qa_bot import QABot
        print("[INFO] Initializing GST Sentinel QA Bot (Longformer + FTS5)...")
        _qa_bot_instance = QABot()
        print("[OK] GST Sentinel QA Bot ready.")
    return _qa_bot_instance


def get_sample_questions() -> List[Dict[str, str]]:
    """Returns curated realistic statutory GST, E-Invoice, and IMS questions."""
    return [
        {
            "category": "Authentication",
            "question": "What is the validity of the auth token?",
            "tag": "Token Validity"
        },
        {
            "category": "Authentication",
            "question": "How long will the Auth Token be active since the first successful login?",
            "tag": "Auth Expiry"
        },
        {
            "category": "Invoice & RCM",
            "question": "Can a supplier amend an invoice from FCM to RCM?",
            "tag": "FCM to RCM"
        },
        {
            "category": "E-Way Bill",
            "question": "In case of export transactions for goods, when is e-way bill required?",
            "tag": "Export EWB"
        },
        {
            "category": "IMS Management",
            "question": "What actions can recipient taxpayer take on invoices in IMS?",
            "tag": "IMS Actions"
        },
        {
            "category": "GSTR-2B & IMS",
            "question": "Is it mandatory to recompute GSTR 2B?",
            "tag": "Recompute 2B"
        }
    ]


def get_system_status() -> Dict[str, Any]:
    """Returns telemetry and readiness info for the QA engine."""
    from config import INDEX_DB_PATH, MODEL_PATH, CONTENT_PATH, CHUNK_SIZE, CHUNK_OVERLAP, TOP_K, SCORE_THRESHOLD
    import sqlite3
    import torch

    index_exists = INDEX_DB_PATH.exists()
    model_exists = MODEL_PATH.exists()
    content_exists = CONTENT_PATH.exists()

    total_chunks = 0
    if index_exists:
        try:
            conn = sqlite3.connect(f"{INDEX_DB_PATH.resolve().as_uri()}?mode=ro", uri=True)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM passages;")
            total_chunks = cur.fetchone()[0]
            conn.close()
        except Exception:
            total_chunks = 0

    return {
        "status": "ready" if (index_exists and model_exists) else "degraded",
        "offline_mode": True,
        "device": "cuda" if torch.cuda.is_available() else "cpu",
        "model_name": "valhalla/longformer-base-4096-finetuned-squadv1",
        "max_context_tokens": 2048,
        "index": {
            "path": str(INDEX_DB_PATH.name),
            "exists": index_exists,
            "total_chunks": total_chunks,
            "size_kb": round(INDEX_DB_PATH.stat().st_size / 1024, 1) if index_exists else 0
        },
        "content_source": {
            "path": str(CONTENT_PATH.name),
            "exists": content_exists,
            "size_kb": round(CONTENT_PATH.stat().st_size / 1024, 1) if content_exists else 0
        },
        "hyperparameters": {
            "chunk_size": CHUNK_SIZE,
            "chunk_overlap": CHUNK_OVERLAP,
            "top_k": TOP_K,
            "score_threshold": SCORE_THRESHOLD
        }
    }


def ask_qa(
    question: str,
    top_k: Optional[int] = None,
    threshold: Optional[float] = None
) -> Dict[str, Any]:
    """
    Executes complete QA retrieval and extraction pipeline, returning:
    - Dedicated extracted answer
    - Structured JSON payload
    - Source content text with answer character offsets
    - All retrieved candidate passages with BM25 ranking
    """
    from config import TOP_K, SCORE_THRESHOLD
    from retriever import search

    t0 = time.perf_counter()
    cleaned = question.strip()

    effective_k = int(top_k) if top_k and top_k > 0 else TOP_K
    effective_thresh = float(threshold) if threshold is not None else SCORE_THRESHOLD

    if not cleaned:
        lat = round((time.perf_counter() - t0) * 1000, 2)
        payload = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "query": "",
            "answer": "not found",
            "score": 0.0,
            "confidence_pct": "0.0%",
            "chunk_id": None,
            "status": "empty_input",
            "reason": "Empty input question provided",
            "latency_ms": lat,
            "model": "valhalla/longformer-base-4096-finetuned-squadv1",
            "device": "cpu"
        }
        return {
            "question": "",
            "answer": "not found",
            "score": 0.0,
            "confidence_pct": "0.0%",
            "chunk_id": None,
            "status": "empty_input",
            "reason": "Please enter a valid GST question.",
            "latency_ms": lat,
            "payload": payload,
            "content": None,
            "retrieved_chunks": []
        }

    # 1. Tiered BM25 Retrieval via SQLite FTS5
    chunks = search(cleaned, k=effective_k)
    if not chunks:
        lat = round((time.perf_counter() - t0) * 1000, 2)
        payload = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "query": cleaned,
            "answer": "not found",
            "score": 0.0,
            "confidence_pct": "0.0%",
            "chunk_id": None,
            "status": "retrieval_miss",
            "reason": "No relevant document passages matched your question.",
            "latency_ms": lat,
            "model": "valhalla/longformer-base-4096-finetuned-squadv1",
            "retrieval": {
                "engine": "SQLite FTS5 BM25",
                "top_k": effective_k,
                "chunks_found": 0
            }
        }
        return {
            "question": cleaned,
            "answer": "not found",
            "score": 0.0,
            "confidence_pct": "0.0%",
            "chunk_id": None,
            "status": "retrieval_miss",
            "reason": "No relevant document passages found matching the question.",
            "latency_ms": lat,
            "payload": payload,
            "content": None,
            "retrieved_chunks": []
        }

    # 2. Neural Extractive Reader
    bot = get_qa_bot()
    best_span = None
    best_chunk = None
    highest_score = -1.0

    chunks_data = []
    for c in chunks:
        span = bot.reader.predict(question=cleaned, context=c.content)
        span_score = round(span.score, 4) if span else 0.0

        if span and span.answer != "not found" and span.score > highest_score:
            highest_score = span.score
            best_span = span
            best_chunk = c

        chunks_data.append({
            "chunk_id": c.chunk_id,
            "section": c.section,
            "bm25_score": c.bm25_score,
            "snippet": c.snippet,
            "reader_score": span_score,
            "extracted_preview": span.answer if span and span.answer != "not found" else None,
            "full_content": c.content,
            "is_selected_answer": False
        })

    # Mark the best chunk in chunks_data
    if best_chunk and best_span and best_span.answer != "not found":
        for cd in chunks_data:
            if cd["chunk_id"] == best_chunk.chunk_id:
                cd["is_selected_answer"] = True

    lat = round((time.perf_counter() - t0) * 1000, 2)

    # 3. Apply Confidence Threshold
    if best_span is None or best_span.answer == "not found" or best_span.score < effective_thresh:
        ans_score = round(highest_score if highest_score > 0 else 0.0, 4)
        pct = f"{round(ans_score * 100, 2)}%"
        payload = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "query": cleaned,
            "answer": "not found",
            "score": ans_score,
            "confidence_pct": pct,
            "chunk_id": best_chunk.chunk_id if best_chunk else None,
            "status": "below_threshold",
            "reason": f"Information not found in documentation (confidence {ans_score} < threshold {effective_thresh}).",
            "latency_ms": lat,
            "model": "valhalla/longformer-base-4096-finetuned-squadv1",
            "threshold": effective_thresh,
            "retrieval": {
                "engine": "SQLite FTS5 BM25",
                "top_k": effective_k,
                "chunks_found": len(chunks)
            }
        }
        return {
            "question": cleaned,
            "answer": "not found",
            "score": ans_score,
            "confidence_pct": pct,
            "chunk_id": best_chunk.chunk_id if best_chunk else None,
            "status": "below_threshold",
            "reason": f"Information not found in documentation (confidence {ans_score} < threshold {effective_thresh}).",
            "latency_ms": lat,
            "payload": payload,
            "content": {
                "chunk_id": best_chunk.chunk_id if best_chunk else None,
                "text": best_chunk.content if best_chunk else "",
                "highlight_start": None,
                "highlight_end": None,
            } if best_chunk else None,
            "retrieved_chunks": chunks_data
        }

    # 4. Success Response
    score_val = round(best_span.score, 4)
    pct = f"{round(score_val * 100, 2)}%"
    payload = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "query": cleaned,
        "answer": best_span.answer,
        "score": score_val,
        "confidence_pct": pct,
        "chunk_id": best_chunk.chunk_id,
        "section": best_chunk.section,
        "span": {
            "start_char": best_span.start_char,
            "end_char": best_span.end_char,
            "length_chars": len(best_span.answer)
        },
        "status": "success",
        "reason": "Statutory answer span extracted successfully.",
        "latency_ms": lat,
        "model": "valhalla/longformer-base-4096-finetuned-squadv1",
        "threshold": effective_thresh,
        "retrieval": {
            "engine": "SQLite FTS5 BM25",
            "top_k": effective_k,
            "matched_chunk_id": best_chunk.chunk_id,
            "total_candidates": len(chunks)
        }
    }

    return {
        "question": cleaned,
        "answer": best_span.answer,
        "score": score_val,
        "confidence_pct": pct,
        "chunk_id": best_chunk.chunk_id,
        "section": best_chunk.section,
        "status": "success",
        "reason": "Extracted with high confidence from statutory corpus.",
        "latency_ms": lat,
        "payload": payload,
        "content": {
            "chunk_id": best_chunk.chunk_id,
            "text": best_chunk.content,
            "highlight_start": best_span.start_char,
            "highlight_end": best_span.end_char,
            "exact_answer": best_span.answer
        },
        "retrieved_chunks": chunks_data
    }
