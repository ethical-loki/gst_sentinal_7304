"""
Module: backend/main.py
Description: Complete FastAPI backend serving Excel-based HSN/SAC search with
             dtype=str to preserve leading zeros, dynamic pathing, and modern UI.
"""

import os
import pandas as pd
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

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
# Files should be placed in data/raw/
RAW_DATA_DIR = os.path.join("data", "raw")

# 👉 CHANGE THIS if your actual Excel filename is different (e.g., "GST_Master.xlsx")
EXCEL_FILENAME = "HSN_SAC.xlsx"

# Full dynamic path computation
HSN_EXCEL_PATH = os.path.join(RAW_DATA_DIR, EXCEL_FILENAME)

# Cached DataFrame variable to avoid reading Excel from disk on every search request
_hsn_df_cache = None


def get_hsn_df():
    """Load the HSN Excel file into memory (cached after first read)."""
    global _hsn_df_cache
    if _hsn_df_cache is not None:
        return _hsn_df_cache

    abs_path = os.path.abspath(HSN_EXCEL_PATH)
    if not os.path.exists(abs_path):
        return None

    try:
        # Read Excel once into memory with dtype=str to preserve leading zeros
        df = pd.read_excel(abs_path, dtype=str)
        df.columns = df.columns.str.strip()

        hsn_col = 'HSN_CD' if 'HSN_CD' in df.columns else df.columns[0]
        desc_col = 'HSN_Description' if 'HSN_Description' in df.columns else df.columns[1]

        df[hsn_col] = df[hsn_col].fillna('').astype(str).str.strip()
        df[desc_col] = df[desc_col].fillna('').astype(str).str.strip()

        # Precompute lowercase search columns for fast string matching
        df['_search_hsn'] = df[hsn_col].str.lower()
        df['_search_desc'] = df[desc_col].str.lower()

        _hsn_df_cache = (df, hsn_col, desc_col)
        return _hsn_df_cache
    except Exception as e:
        print(f"[ERROR] Error loading HSN Excel file: {str(e)}")
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


@app.get("/api/hsn-search")
async def search_hsn(query: str = Query("", min_length=0)):
    """Search HSN codes and descriptions using exact column names HSN_CD and HSN_Description."""
    q_trimmed = query.strip()
    if not q_trimmed:
        return {"query": query, "matches": []}

    hsn_data = get_hsn_df()
    if hsn_data is None:
        abs_path = os.path.abspath(HSN_EXCEL_PATH)
        return {"error": f"File not found at {abs_path}", "matches": []}

    try:
        df, hsn_col, desc_col = hsn_data
        q = q_trimmed.lower()

        # Fast literal string search
        filtered = df[
            df['_search_hsn'].str.contains(q, na=False, regex=False) |
            df['_search_desc'].str.contains(q, na=False, regex=False)
        ]

        results = []
        for _, row in filtered.head(20).iterrows():
            results.append({
                "hsn_code": str(row[hsn_col]),
                "description": str(row[desc_col]),
                "gst_rate": 18.0
            })

        return {"query": query, "matches": results}

    except Exception as e:
        print(f"[ERROR] EXCEPTION: {str(e)}")
        return {"error": str(e), "matches": []}


@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Serves the modernized interactive HSN auto-suggest UI from static/index.html."""
    html_path = os.path.abspath(os.path.join(STATIC_DIR, "index.html"))
    if not os.path.exists(html_path):
        return HTMLResponse(
            "<h2>Frontend not found. Place index.html in the static/ folder.</h2>",
            status_code=404
        )
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())
from pathlib import Path
import json
import pandas as pd
from fastapi import HTTPException, Request, Response
from fastapi.responses import HTMLResponse, FileResponse

# Define root directory based on backend/main.py location
BASE_DIR = Path(__file__).resolve().parent.parent

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


if __name__ == "__main__":
    import uvicorn
    print("\n🚀 Starting GST Sentinel Server at http://127.0.0.1:8000 ...")
    print("👉 E-Invoice & E-Way Converter Dashboard: http://127.0.0.1:8000/converter")
    print("👉 HSN Code Search Engine               : http://127.0.0.1:8000/\n")
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
