# Project Plan — GST Sentinel QA Bot

## Objective
Build a fully offline, extractive QA bot over a custom GST/HSN document corpus
using BM25 retrieval (SQLite FTS5) and Longformer for answer extraction.

---

## Architecture

```
User Question
     │
     ▼
┌──────────────┐
│  Retriever   │  BM25 (SQLite FTS5) → top-k chunks
└──────┬───────┘
       │ context
       ▼
┌──────────────┐
│    Reader    │  Longformer → extract answer span
└──────┬───────┘
       │
       ▼
   Answer Text
```

---

## Implementation Phases

### Day 1 — Environment & Data
- [x] Python 3.11.9 virtual environment (`.venv311`)
- [x] Install torch, transformers, sentencepiece, scikit-learn
- [x] Verify SQLite FTS5 support
- [ ] Populate `data/content.txt` with source document

### Day 2 — Retrieval Pipeline
- [ ] Implement `build_index.py` — chunk and index content
- [ ] Implement `retriever.py` — BM25 search via FTS5
- [ ] Unit test: query returns relevant chunks

### Day 3 — Reader & QA Loop
- [ ] Download Longformer model (`download_model.py`)
- [ ] Implement `reader.py` — extractive span prediction
- [ ] Implement `qa_bot.py` — interactive loop

### Day 4 — Evaluation
- [ ] Create labeled `qa_test.json` (≥20 questions)
- [ ] Implement `evaluate.py` — EM and F1 metrics
- [ ] Run evaluation and document results in `eval_report.md`

### Day 5 — Offline Test & Docs
- [ ] Disconnect internet, verify full offline operation
- [ ] Document in `offline_test.md`
- [ ] Finalize `README.md`

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| SQLite FTS5 for retrieval | Zero external dependencies, built into Python stdlib |
| Longformer (4096 tokens) | Handles long contexts better than BERT-base |
| Character-level chunking | Simpler and language-agnostic |
| Porter ASCII tokenizer | Better recall on stemmed GST terminology |

---

## Success Criteria
- EM ≥ 40% on labeled test set
- F1 ≥ 60% on labeled test set
- Bot responds in < 5 seconds on CPU
- Works fully offline after initial setup
