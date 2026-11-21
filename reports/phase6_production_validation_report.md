# Phase 6 — Production Validation & Final Benchmark Report

## 1. Full 100-Case Zero-Leakage Benchmark (`INDEPENDENT_100`, Full 97-Chapter Master)

Verified via `scripts/benchmark_phase17_independent.py` (`reports/phase6_final_100.json`), compared against prior baseline (`reports/final_hsn_validation_100.json`):

| Metric | Baseline (`final_hsn_validation_100.json`) | Final Phase 6 (`phase6_final_100.json`) | Delta |
|---|---:|---:|---:|
| Zero HSN & Query Leakage | `True` | `True` | Preserved |
| Statutory Master Coverage | 9 Chapters (4,851 rows) | 97 Goods Chapters (18,797 rows) | +88 Chapters |
| Chapter Accuracy | `97.0%` | **`98.0%`** | **+1.0 pp** |
| Candidate Recall | `91.0%` | **`91.0%`** | Preserved at 97-ch scale |
| Recall@5 | `69.0%` | `65.0%` | -4.0 pp |
| Recall@10 | `78.0%` | **`78.0%`** | Preserved |
| Top-1 Accuracy | `37.0%` | **`39.0%`** | **+2.0 pp** |
| Same-Heading Precision | `59.86%` | **`60.63%`** | **+0.77 pp** |
| Exact 8-Digit HSN Hits | `7 / 100` (`7.0%`) | **`10 / 100` (`10.0%`)** | **+3 exacts (+42.9%)** |
| False Exact Count | `0` | **`0`** | **Zero false exacts** |
| Correct Abstention Rate | `100.0%` | **`100.0%`** | **100% safe abstention** |
| Mean Retained 8-Digit Candidates | `35.33` | `27.99` | Cleaner precision |
| Mean End-to-End Latency | `51,937.0 ms` (`51.94 s`) | **`8,216.9 ms` (`8.22 s`)** | **6.32x faster** |
| P95 End-to-End Latency | `76,007.9 ms` (`76.01 s`) | **`12,577.8 ms` (`12.58 s`)** | **6.04x faster** |
| CrossEncoder Pairs Scored (100 cases) | `19,024` | `14,585` | `-23.3%` pairs |

Exact 8-digit HSN winners (`10 / 100`, 0 false exacts):
`61099030`, `73239910`, `84138120`, `84159010`, `84182100`, `84322910`, `85044021`, `85152110`, `85192100`, `94031010`.

Missing recall cases (`9 / 100`):
`#30 (62044990)`, `#58 (84193900)`, `#59 (84198120)`, `#61 (84198970)`, `#72 (85044090)`, `#79 (85176250)`, `#80 (85176270)`, `#87 (85251020)`, `#89 (85252091)`.

---

## 2. Unseen Cross-Chapter Generalization (`data/eval/independent_exact_hsn_eval.parquet`)

Executed `scripts/eval_unseen_cross_chapter.py` (`reports/phase6_unseen_cross_chapter_eval.json`) across **44 distinct unseen chapters** strictly outside the 9 legacy training chapters (`19, 39, 61, 62, 73, 84, 85, 87, 94`) and verified zero overlap with `full_pairs_train.parquet`, `full_pairs_val.parquet`, and `INDEPENDENT_100`:

- **Total Cases / Distinct Unseen Chapters:** `44` / `44` (`zero_legacy9_overlap=True`, `zero_train_val_100_leakage=True`)
- **Chapter Accuracy:** `95.45%`
- **Candidate Recall:** `97.73%`
- **Recall@5:** `90.91%`
- **Top-1 Accuracy:** `79.55%`
- **Exact 8-Digit HSN Hits:** `3 / 44` (`6.82%`)
- **False Exact Count:** `0` (`100.0%` correct abstention)
- **Mean Latency / P95 Latency:** `7,969.3 ms` (`7.97 s`) / `13,021.3 ms` (`13.02 s`)

---

## 3. Regression & Performance Test Suite

Executed across 12 test modules (`pytest`):
- **Total:** **`94 passed, 0 failed`** in `345.16s` (`tests/test_phase5_performance.py`, `tests/test_phase4_retrieval_and_ch98.py`, `tests/test_candidate_evidence_evaluator.py`, `tests/test_hierarchy_intelligence.py`, `tests/test_confidence_calibrator.py`, `tests/test_relevance_and_ambiguity.py`, `tests/test_stage3_statutory_verifier.py`, `tests/test_article_identity_compatibility.py`, `tests/test_stage1_product_intent.py`, `tests/test_stage1_to_stage2_handoff.py`, `tests/test_statutory_master_enrichment.py`, `tests/test_multi_candidate_engine.py`).

---

## 4. Live HTTP E2E, UI Contract, & Operational/Security Audit

### Live FastAPI Validation (`http://127.0.0.1:8000`)
- **`GET /`:** HTTP `200 OK`; verified strict three-screen sequential UI DOM elements (`stepCard1Tracker`, `stepCard2Tracker`, `stepCard3Tracker`, `Proceed to Stage 3`, `/api/v1/hsn-rag/step1-context-aggregator`, `/api/v1/hsn-v2/classify-adaptive`, `/api/v1/hsn-v2/clarify-adaptive`).
- **Invalid/Malformed Input Error Handling:** `4 / 4` invalid requests (empty `product`, malformed `stage1_result`, empty `original_description`, empty feedback payload) cleanly returned HTTP `400 Bad Request`.
- **Flow A (Exact Classification + GST Rate):** `"household compression type refrigerator"` -> Stage 1 returned Chapter `84` (`conf=0.8069`) -> Stage 2/3 (`14.74s`) returned `EXACT_HSN 84182100` (`calibrated_confidence=0.7766`, `verified_gst_rate: igst=18%, cgst=9%, sgst=9%, Notification No. 09/2025-CT(Rate)`).
- **Flow B (Clarification Loop):** `"water bottle"` -> `INSUFFICIENT_INFORMATION` (`9.69s`) -> `POST /api/v1/hsn-v2/clarify-adaptive` with `{"material": "stainless steel"}` -> updated cleanly to `MULTIPLE_CANDIDATES` (`11.11s`, HTTP `200 OK`). Notice that statutory `"bottle"` matches in Heading `8422` (`MACHINERY FOR CLEANING OR DRYING BOTTLES`) outranked Heading `7323` (`HOUSEHOLD ARTICLES OF IRON OR STEEL`) after clarification because `7323` statutory text does not contain `"bottle"`.

### Security, Logging & Browser Validation Findings
- **Security Scan (`backend/`):** No hardcoded API keys or credentials (`GSTIN_API_KEY` and `VAHAN_API_KEY` are read from environment variables), no `eval()`, `exec()`, `shell=True`, or stack traces leaked to clients. Note: `backend/main.py:48` configures `allow_origins=["*"]` with `allow_credentials=True` for local development; restrict `allow_origins` before public production deployment.
- **Operational Latency Caveat (`step1-context-aggregator`):** Warm HTTP calls to legacy `POST /api/v1/hsn-rag/step1-context-aggregator` took `124.43s` because `backend/main.py` invokes a slow local LLM (`IntentExtractor`, which fails JSON parsing and falls back to `RULE_BASED_FALLBACK`) plus full `HSNIntelligenceV2.classify`, whereas canonical Stage 2/3 `classify-adaptive` runs in `8–15s`. Legacy `backend/main.py:919` also contains an older 9-chapter fallback message string.
- **Chrome Browser Automation Block:** Interactive Chrome DevTools validation could not connect because Chrome remote debugging (`chrome://inspect/#remote-debugging` / `DevToolsActivePort`) was not active in the host environment. Live HTTP API and UI HTML/JS contract verification passed directly against the running FastAPI server.
