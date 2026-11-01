with open("backend/main.py", "r", encoding="utf-8") as f:
    c = f.read()

target = '''@app.on_event("startup")
async def preload_hsn_cache():
    """Pre-load HSN DataFrame into memory on server startup so first search is instant."""
    result = get_hsn_df()
    if result is not None:
        df, hsn_col, desc_col = result
        print(f"[OK] HSN data preloaded: {len(df)} rows | Columns: {hsn_col}, {desc_col}")
    else:
        print("[WARN] HSN Excel file not found at startup - will retry on first search.")'''

replacement = '''@app.on_event("startup")
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
        print(f"[WARN] QA Engine preload deferred: {e}")'''

if target in c:
    c = c.replace(target, replacement, 1)
    with open("backend/main.py", "w", encoding="utf-8") as f:
        f.write(c)
    print("Updated startup event in main.py")
else:
    print("Target startup not found in main.py")

