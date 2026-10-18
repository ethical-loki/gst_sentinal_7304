"""
Module: backend/main.py
Description: Complete FastAPI backend serving Excel-based HSN/SAC search with
             dtype=str to preserve leading zeros, dynamic pathing, and modern UI.
"""

import os
import json
import time
from pathlib import Path
from typing import Optional, List, Dict, Any, Union
import pandas as pd
from fastapi import FastAPI, Query, HTTPException, Request, Response
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


def get_hsn_search_engine():
    global _hsn_search_engine
    if _hsn_search_engine is None:
        try:
            from src.nlp.hsn_search import HSNSearchEngine
            _hsn_search_engine = HSNSearchEngine()
            print("[OK] HSNSearchEngine initialized with Contrastive MLP (128-D CPU)")
        except Exception as e:
            # Not yet ready or weights still training
            _hsn_search_engine = None
    return _hsn_search_engine


@app.get("/api/hsn-search")
async def search_hsn(
    query: str = Query("", min_length=0),
    q: Optional[str] = Query(None)
):
    """
    Search HSN codes and descriptions via In-House Contrastive Semantic HSN Encoder.
    Accepts either ?query= or ?q= parameter.
    Returns top candidate statutory items with confidence percentage, Section 17(5) flag,
    statutory tax rates, and exact CPU execution latency in milliseconds.
    """
    t_start = time.perf_counter()
    raw_query = q if q is not None else query
    q_trimmed = raw_query.strip()
    if not q_trimmed:
        return {"query": raw_query, "matches": [], "latency_ms": 0.0, "model": "None"}

    # 1. Attempt High-Performance Contrastive Semantic Search
    engine = get_hsn_search_engine()
    if engine is not None:
        try:
            res = engine.search(q_trimmed, top_k=20)
            formatted = []
            for m in res["matches"]:
                gst_val = float(m.get("standard_rate", 18.0))
                formatted.append({
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
                })
            return {
                "query": raw_query,
                "matches": formatted,
                "latency_ms": res.get("latency_ms", round((time.perf_counter() - t_start) * 1000.0, 2)),
                "model": res.get("model", "Contrastive MLP (128-D CPU)")
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
        "report": ("validation_report.json", "application/json"),
        "csv": ("correction_audit_report.csv", "text/csv; charset=utf-8"),
        "summary": ("audit_summary.txt", "text/plain; charset=utf-8")
    }

    if file_type not in file_map:
        raise HTTPException(status_code=400, detail=f"Invalid file type requested. Options: {list(file_map.keys())}")

    filename, media_type = file_map[file_type]
    file_path = TEMPLATE_CONVERTERS_DIR / filename

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
