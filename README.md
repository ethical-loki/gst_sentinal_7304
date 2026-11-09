# GST Sentinel — HSN Chapter Predictor (Module 5)

An offline, local-first machine learning and neural retrieval system for classifying commercial product names into statutory 2-digit HSN Chapters (01–99, excluding reserved Chapter 77).

---

## 1. Quick Setup & Installation

### Step 1: Install Ollama & Pull Models
Download and install Ollama for Windows from [ollama.com](https://ollama.com).
In PowerShell, pull the local instruction model:
```powershell
ollama pull qwen2.5:7b-instruct
# Fallback for CPU-only systems:
# ollama pull qwen2.5:3b-instruct
```

### Step 2: Build Tariff & Chapter Vector Index
Build the BM25 lexical index and semantic embeddings over all 19,396 rows of `Final_Copy_hsn_7304.xlsx`:
```powershell
.\venv\Scripts\python.exe scripts\build_chapter_index.py
```
This generates pre-computed caches in `data/chapter_predictor/`:
- `bm25_index.pkl`: Lexical BM25 index over tariff descriptions & parent headings
- `tariff_embeddings.npy`: Dense L2-normalized vector matrix
- `chapter_embeddings.npy`: Dense embeddings for all 99 official chapter titles
- `tariff_metadata.json`: Tariff records and chapter titles map

### Step 3: Start the Backend Server
Start FastAPI server with Uvicorn:
```powershell
.\venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

### Step 4: Open the Chapter Predictor UI
Navigate to your web browser:
```text
http://127.0.0.1:8000/chapter-predictor
```

---

## 2. API Reference

### Single Prediction
`POST /api/chapter/predict`
```json
{
  "product_name": "Whole Roasted Coffee Beans",
  "top_k": 3
}
```

### Batch Prediction
`POST /api/chapter/batch`
- **JSON Payload**: `{"product_names": ["Microprocessor", "Rice", "Atta"]}`
- **CSV Upload**: Multipart form upload with a `.csv` file. Returns a downloadable enriched CSV with statutory chapter, confidence, and evidence lines.

### System Health
`GET /api/chapter/health`
Returns BM25 index status, vector count, and local Ollama LLM reachability.

### Auditor Feedback
`POST /api/chapter/feedback`
Records auditor verification or correction into `data/feedback/chapter_feedback.jsonl`.

