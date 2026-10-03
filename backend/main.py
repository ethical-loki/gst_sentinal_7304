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