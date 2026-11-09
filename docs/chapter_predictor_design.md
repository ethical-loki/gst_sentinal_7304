# Product-to-HSN-Chapter Prediction Module (Design Note)

## 1. Architectural Overview & Design Rationale
The HSN Chapter Predictor provides robust, local-first classification of free-text commercial product descriptions into the 98 active statutory chapters of the Harmonized System (Chapters 01–98 for goods, Chapter 99 for SAC services, excluding Chapter 77).

Rather than attempting flat classification over 19,396 fine-grained tariff lines—which suffers from severe lexical collapse and class imbalance—the system employs a **hierarchical 4-stage pipeline** with calibrated fallback and abstention:

```
[Raw Commercial Description]
           │
           ▼
Stage A: Normalization & Negation Preservation
(Expands abbreviations, strips invoice noise, protects statutory states)
           │
     ┌─────┴─────────────────────────┐
     ▼                               ▼
Stage B: BM25 Lexical           Stage C: Dense Semantic Embeddings
(Over 19,396 CBIC descriptions) (sentence-transformers / BAAI BGE)
     │                               │
     └───────────────┬───────────────┘
                     ▼
Stage E (Early): Reciprocal Rank Fusion (RRF, k=60)
(Extracts Top 10 candidate chapters + top 5 evidence lines each)
                     │
                     ▼
Stage D: Local LLM Reranking & GIR Enforcement
(Ollama Qwen2.5:7B / 3B with JSON Schema constraint)
[Fallback: Pure RRF statistical consensus if Ollama offline]
                     │
                     ▼
Stage E (Final): Mathematical Abstention Evaluation
(PREDICTED vs NEEDS_REVIEW based on margin < 0.05 & threshold < 0.55)
                     │
                     ▼
[Final ChapterPrediction Pydantic Model + Evidence + Reasoning]
```

---

## 2. Component Breakdown

### Stage A: Normalization (`normalize.py`)
- **Abbreviation Expansion**: Maps commercial invoice shorthand (`pcs`, `ltr`, `kg`, `w/`, `w/o`, `incl`, `excl`, `ss`, `ms`, `gi`, `pvc`, `hdpe`, etc.) and Indian trade colloquialisms (`atta` $\rightarrow$ `wheat flour`, `chai patti` $\rightarrow$ `tea leaves`, `chawal` $\rightarrow$ `rice`) into standard statutory terminology.
- **Statutory Negation Preservation**: Statutory terms like `"not"`, `"un"`, `"non"`, `"without"`, `"excluding"`, `"roasted"`, `"mounted"`, and `"knitted"` are strictly protected from stop-word removal.

### Stage B: BM25 Lexical Retrieval (`lexical.py`)
- Full corpus indexing over all **19,396 rows** in `Final_Copy_hsn_7304.xlsx`.
- Enriched document representations combining statutory 8-digit leaf descriptions, parent 4-digit heading texts, and official WCO chapter titles.
- Aggregates top 50 tariff lines into chapter-level candidates, ranking chapters by maximum line score and accumulated evidence.

### Stage C: Semantic Dense Retrieval (`embeddings.py`)
- Primary embedding model: `sentence-transformers/all-MiniLM-L6-v2` / `BAAI/bge-small-en-v1.5` (with fallback to `BAAI/bge-m3` via `CHAPTER_EMBEDDING_MODEL`).
- Pre-computes and caches L2-normalized vectors for all 19,396 descriptions and all 99 chapter titles to disk (`.npy` files) for sub-10ms startup.
- Evaluates query cosine similarity against both tariff lines and direct chapter titles, blending evidence into top chapter candidates.

### Stage D: Local LLM Reranker & GIR Disambiguation (`llm_rerank.py`)
- Serves local `Qwen2.5-7B-Instruct` (or `3B`) via Ollama at `http://localhost:11434`.
- Enforces strict JSON Schema constrained decoding (`Ollama format`).
- Prompts model strictly on General Interpretative Rules (GIR 1 through 6):
  - Prioritizes finished articles over raw materials (e.g. Cotton shirt $\rightarrow$ 61/62, not 52).
  - Enforces decisive legal treatment of processing states (roasted vs unroasted, cooked vs raw, mounted vs unmounted).
  - Strictly constrains output to candidate chapters from Stages B and C.

### Stage E: Fusion & Abstention Logic (`fusion.py`)
- Computes **Reciprocal Rank Fusion** ($k=60$) over lexical and semantic candidates.
- **Abstention Criteria**:
  - Flags `status = "NEEDS_REVIEW"` if top candidate confidence $< 0.55$ OR if top two chapters have a margin $< 0.05$.
  - **Zero Artificial Gates**: Ambiguity is determined purely by mathematical margin, removing the flawed `not already_clarified_inline` string-shape check.

---

## 3. Deviations & Optimizations
1. **Model Selection for CPU Efficiency**:
   - `all-MiniLM-L6-v2` / `bge-small-en-v1.5` with `max_seq_length=64` and multi-threading (`torch.set_num_threads`) was selected as the local CPU baseline to ensure fast vector precomputation and sub-50ms inference, while preserving plug-and-play support for `BAAI/bge-m3` via `CHAPTER_EMBEDDING_MODEL`.
2. **Offline Web UI**:
   - Built a self-contained, offline-first dashboard (`templates/chapter_predictor.html`) without external CDN dependencies. Includes stage-by-stage spinner, confidence meter, word-highlighted evidence table, batch CSV processing with export, and auditor feedback collection (`chapter_feedback.jsonl`).

