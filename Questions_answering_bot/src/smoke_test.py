"""
Smoke test — validates all modules import cleanly and core utilities work.
Run from: Questions_answering_bot/src/
"""
import sys
import sqlite3
from pathlib import Path

errors = []

# 1. SQLite FTS5
try:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
    conn.close()
    print("[OK] SQLite FTS5 support")
except Exception as e:
    errors.append(f"[FAIL] SQLite FTS5: {e}")

# 2. pydantic
try:
    from pydantic import BaseModel, Field
    class _T(BaseModel):
        model_config = {"frozen": True}
        x: int = Field(...)
    _T(x=1)
    print("[OK] pydantic v2")
except Exception as e:
    errors.append(f"[FAIL] pydantic: {e}")

# 3. torch
try:
    import torch
    print(f"[OK] torch {torch.__version__} (CUDA: {torch.cuda.is_available()})")
except Exception as e:
    errors.append(f"[FAIL] torch: {e}")

# 4. transformers
try:
    import transformers
    print(f"[OK] transformers {transformers.__version__}")
except Exception as e:
    errors.append(f"[FAIL] transformers: {e}")

# 5. psutil
try:
    import psutil
    print(f"[OK] psutil {psutil.__version__}")
except Exception as e:
    errors.append(f"[FAIL] psutil: {e}")

# 6. config module
try:
    sys.path.insert(0, str(Path(__file__).parent))
    from config import (INDEX_DB_PATH, MODEL_PATH, CONTENT_PATH,
                        CHUNK_SIZE, CHUNK_OVERLAP, TOP_K, SCORE_THRESHOLD)
    print(f"[OK] config — CHUNK_SIZE={CHUNK_SIZE}, TOP_K={TOP_K}, SCORE_THRESHOLD={SCORE_THRESHOLD}")
except Exception as e:
    errors.append(f"[FAIL] config: {e}")

# 7. retriever module (no DB call)
try:
    from retriever import clean_query, SearchResult
    tokens = clean_query("What is the GST rate for essential food items?")
    assert len(tokens) > 0, "clean_query returned empty tokens"
    print(f"[OK] retriever — clean_query returned {len(tokens)} tokens: {tokens}")
except Exception as e:
    errors.append(f"[FAIL] retriever: {e}")

# 8. Index DB existence
try:
    from config import INDEX_DB_PATH
    if INDEX_DB_PATH.exists():
        size_kb = INDEX_DB_PATH.stat().st_size // 1024
        print(f"[OK] index.db exists ({size_kb} KB)")
    else:
        print(f"[WARN] index.db not found at {INDEX_DB_PATH} — run build_index.py")
except Exception as e:
    errors.append(f"[FAIL] index check: {e}")

# 9. Model directory existence
try:
    from config import MODEL_PATH
    if MODEL_PATH.exists():
        files = list(MODEL_PATH.iterdir())
        print(f"[OK] model directory exists ({len(files)} files)")
    else:
        print(f"[WARN] Model not found at {MODEL_PATH} — run download_model.py")
except Exception as e:
    errors.append(f"[FAIL] model check: {e}")

# Summary
print("\n" + "=" * 50)
if errors:
    print(f"SMOKE TEST FAILED — {len(errors)} error(s):")
    for err in errors:
        print(f"  {err}")
    sys.exit(1)
else:
    print("SMOKE TEST PASSED — all modules OK")
