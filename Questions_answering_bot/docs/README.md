# GST Sentinel — QA Bot

A fully offline, extractive Question-Answering bot over a custom document corpus.
Uses **SQLite FTS5** (BM25) for retrieval and **Longformer** for answer extraction.

---

## Project Structure

```
Questions_answering_bot/
├── data/
│   ├── content.txt          # source document (place your text here)
│   ├── index.db             # SQLite FTS5 index (auto-generated)
│   └── qa_test.json         # labeled test questions
├── models/
│   └── longformer-squad2/   # saved model (downloaded once)
├── src/
│   ├── config.py            # paths, chunk size, top_k, score threshold
│   ├── download_model.py    # run once with internet to fetch model
│   ├── build_index.py       # chunk the file and build FTS5 index
│   ├── retriever.py         # BM25 search over the index
│   ├── reader.py            # Longformer answer extraction
│   ├── qa_bot.py            # interactive question loop
│   ├── evaluate.py          # exact match and F1 scoring
│   └── tune_benchmark.py    # latency, RAM, and parameter tuning
├── docs/
│   ├── README.md            # this file
│   ├── offline_test.md      # offline query logs
│   └── eval_report.md       # evaluation report
├── requirements.txt
└── project_plan.md
```

---

## Prerequisites

- Python **3.9–3.11**
- Virtual environment activated (`.venv311`)

```powershell
# From the GST_Sentinal root
.\.venv311\Scripts\Activate.ps1
```

---

## Setup (run in order)

### 1. Install dependencies
```bash
pip install -r Questions_answering_bot/requirements.txt
```

### 2. Add your document
Place your source text in:
```
Questions_answering_bot/data/content.txt
```

### 3. Download the model *(internet required, run once)*
```bash
cd Questions_answering_bot/src
python download_model.py
```

### 4. Build the FTS5 index
```bash
python build_index.py
```

### 5. Start the QA bot
```bash
python qa_bot.py
```

### 6. Run evaluation (optional)
```bash
python evaluate.py
```

### 7. Run tuning benchmark (optional)
```bash
python tune_benchmark.py
```

---

## Configuration

Edit `src/config.py` to adjust:

| Setting | Default | Description |
|---------|---------|-------------|
| `CHUNK_SIZE` | 2000 | Words per chunk |
| `CHUNK_OVERLAP` | 200 | Overlap words between adjacent chunks |
| `TOP_K` | 3 | BM25 results returned per query |
| `SCORE_THRESHOLD` | 0.05 | Minimum reader confidence to return an answer |

---

## Test Data Format (`data/qa_test.json`)

Each entry must have the following schema:

```json
[
  {
    "question": "What is GST?",
    "answer": "Goods and Services Tax",
    "answerable": true
  },
  {
    "question": "What is the capital of Mars?",
    "answer": null,
    "answerable": false
  }
]
```

- `"answerable": false` entries test **refusal accuracy** (bot should return `"not found"`).
- `"answer"` is a single string (not a list).

---

## Offline Usage

After running steps 1–4 once (with internet), the bot works **fully offline**.
The model is saved locally in `models/longformer-squad2/`.

---

## Performance Targets

| Metric | Target |
|--------|--------|
| Exact Match (EM) | ≥ 40% |
| Token-Level F1 | ≥ 60% |
| Response latency | < 5s per query on CPU |
| Peak RAM | < 4 GB |
