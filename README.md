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

---

## 3. LLM-Based Intent Extraction Stage

The pipeline features an LLM-based Intent Extraction stage that translates commercial trade names, colloquial queries, brand names, and misspellings into statutory customs tariff terminology grounded strictly in `data/raw/Master_copy_hsn.xlsx`.

### Key Policies:
- **Zero HSN Code Policy**: The language model is forbidden from producing tariff codes or digit sequences. All output terms are words only.
- **Strict Master File Grounding**: All candidate terms are verified against the 4 source columns of `Master_copy_hsn.xlsx` (`chapter_title`, `HSN Description`, `Article Keywords`, `Material Keywords`). Ungrounded terms are dropped and recorded.
- **Unstated Attributes**: Missing critical variables (material, construction, insulation, mount) are flagged as clarification prompts rather than guessed.
- **Ambiguity & Vague Query Protection**: Unrecognized/vague queries (e.g. `aunty`, `gadget`) receive `reading_confidence: unclear` and trigger an automated `ABSTAIN` state to prevent false classifications into unindexed chapters.

### How to Configure or Swap the LLM
The LLM configuration is managed in `config/intent_extraction_config.json`:

```json
{
  "model_provider": "deterministic",
  "local_model_path": "Questions_answering_bot/models/qwen2.5-0.5b-instruct",
  "model_name": "qwen2.5-0.5b-instruct",
  "embedding_model_name": "sentence-transformers/all-MiniLM-L6-v2",
  "master_excel_path": "data/raw/Master_copy_hsn.xlsx",
  "cache_dir": "data/intent_cache",
  "vocabulary_top_k": 25,
  "max_search_terms": 20,
  "temperature": 0.0,
  "max_new_tokens": 180
}
```

To switch models, change `"model_provider"`:
1. **`deterministic`** (Default for instant UI & CI): Sub-millisecond, offline, deterministic intent mapper.
2. **`local_transformers`**: Runs the local offline HuggingFace model stored in `Questions_answering_bot/models/qwen2.5-0.5b-instruct`.
3. **`ollama`**: Connects to a local Ollama instance (set `"ollama_base_url": "http://localhost:11434"`).

### Running Intent Extraction Tests
```powershell
.\venv\Scripts\pytest.exe tests/test_intent_extractor.py -s -v
```
This tests zero-tariff code leakage, strict schema validation, grounding against `Master_copy_hsn.xlsx`, and outputs separate Intent Accuracy and Retrieval Grounding Precision metrics.


