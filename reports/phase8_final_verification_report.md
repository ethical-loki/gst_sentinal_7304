# Phase 8 — Final Verification Report

**Date:** 2026-11-15  
**Git Commit:** `1c8780274c4637d46fc75c1b3e864ebae2e59c74` (`1c87802`)  
**Scope:** Verification only (no code modifications, no threshold changes, no product-specific rules).

---

## 1. Benchmark Results

### 1.1 Fair Head-to-Head Comparison on 51-Case Suite (`data/eval/generalized_test_suite.parquet`)

Command executed:
```powershell
& "C:\Users\User\OneDrive\Desktop\GST_Sentinal\venv\Scripts\python.exe" scripts/benchmark_phase7_multi_candidate.py
```
Artifact: [`reports/phase7_benchmark_report.json`](file:///c:/Users/User/OneDrive/Desktop/GST_Sentinal/reports/phase7_benchmark_report.json)

Both `HSNIntelligenceV2` (Phase 6) and `MultiCandidateEngine` (Phase 7/8) were evaluated on the identical 51-case suite under identical `_score_unified` rules:

| Metric | Phase 6 (`HSNIntelligenceV2`) | Phase 7/8 (`MultiCandidateEngine`) |
|---|---:|---:|
| Strict Pass Rate | **35 / 51 (68.63%)** | **44 / 51 (86.27%)** |
| Clarification-Aware Pass Rate | **35 / 51 (68.63%)** | **44 / 51 (86.27%)** |
| `EXACT_HSN` Predictions | 2 | 0 |
| `CHAPTER_ONLY_CLARIFY` Predictions | 14 | 15 |
| `CLARIFY_AMBIGUOUS` Predictions | 18 | 0 |
| `MULTIPLE_CANDIDATES` Predictions | 0 | 21 |
| `INSUFFICIENT_INFORMATION` (Abstentions) | 8 | 6 |
| `OUT_OF_SCHEDULE` Predictions | 9 | 9 |
| Mean Latency | 3,192.09 ms (3.19 s) | 16,553.35 ms (16.55 s) |
| P95 Latency | 5,058.17 ms (5.06 s) | 34,375.14 ms (34.38 s) |

Additional Phase 7/8 metrics on the 51-case suite:
- **Candidate Precision (mean chapter match in qualifying pool):** **82.11%** (`0.8211`)
- **Candidate Recall (active cases with expected HSN/chapter in pool):** **88.37%** (`0.8837`)
- **Exhaustive-Reference Recall (5 active queries, 600-record scan):** **4 / 4 (100%)**
- **Discovery Completeness Rate:** **86.27%** (**44 / 51 complete**; **7 / 51 incomplete** where `budget=250` was reached while active tail candidates remained)
- **Mean Preserved Qualifying Candidates:** **65.0** (mean duplicate rate `0.1694`)
- **Chapter Prediction Accuracy:** **15 / 15 (100%)**
- **Multiple-Candidate Coverage:** **21 / 21 (100%)**
- **Clarification Necessity Accuracy:** **36 / 36 (100%)**
- **Out-of-Schedule Accuracy:** **8 / 8 (100%)**

### 1.2 Unseen 35-Case Exact-HSN & Clarification Suite (`data/eval/exact_hsn_eval_suite.parquet`)

| Metric | Observed Result |
|---|---:|
| Total Unseen Cases | 35 (`23 exact_detailed`, `12 ambiguous_with_clarification`) |
| Detailed Cases — Candidate Pool Recall | **100.0%** (23 / 23) |
| Detailed Cases — Exact-HSN Coverage (`EXACT_HSN` mode) | **0.0%** (0 / 23) |
| Detailed Cases — Exact-HSN Overall Accuracy | **0.0%** (0 / 23) |
| Detailed Cases — Abstention (`INSUFFICIENT_INFORMATION`) | **0.0%** (0 / 23) |
| Detailed Cases — Chapter Accuracy (when single chapter emitted) | **17.39%** (4 / 23; remaining 19 emitted `MULTIPLE_CANDIDATES` across headings) |
| Clarification Cases — Pool Recall (Before → After) | **12 / 12 → 12 / 12 (100%)** |
| Clarification Cases — Exact-HSN Hits (Before → After) | **0 / 12 → 0 / 12** |

**Root Cause (Observed):** Diagnostic inspection of the unseen exact-HSN cases showed `chapter_confidence = 0.9915` and `relevance_confidence = 0.993–0.997`, but the Cross-Encoder assigns near-identical logits to sibling 8-digit tariff items under the same heading (`distinction_confidence = 0.0000–0.0005`, `hsn_confidence = 0.0045–0.0214 < tau_exact_hsn=0.55`). Rather than guessing an uncalibrated 8-digit leaf code, the calibrated decision controller routes these cases to `MULTIPLE_CANDIDATES` or `CHAPTER_ONLY_CLARIFY` with the true 8-digit HSN preserved in the candidate pool.

---

## 2. Dataset Quality Validation (`data/eval/exact_hsn_eval_suite.parquet`)

Command executed:
```powershell
& "C:\Users\User\OneDrive\Desktop\GST_Sentinal\venv\Scripts\python.exe" -c "..." # master + train/val/eval overlap audit
```

Observed results:
- **Gold HSN Presence in Statutory Master (`data/enriched_master_hsn.parquet`):** **35 / 35** unique gold 8-digit HSNs present (`Missing in master: 0`, `Null/empty gold HSNs: 0`).
- **Overlap with Training Queries & HSNs (`data/training_pairs/full_pairs_train.parquet`):** `hsn_overlap=0`, `query_overlap=0`.
- **Overlap with Benchmark Suites (`generalized_test_suite.parquet`, `generalized_test_large.parquet`):** `hsn_overlap=0`, `query_overlap=0`.
- **Overlap with Calibration/Validation Pairs (`data/training_pairs/full_pairs_val.parquet`):** `query_overlap=0`, **`hsn_overlap=24`** (24 of the 35 HSN codes appeared in `full_pairs_val.parquet`, though with different query text).
- **Dataset Limitation:** Cases in `exact_hsn_eval_suite.parquet` were programmatically constructed from `heading_4digit_desc`, `subheading_6digit_desc`, `tariff_item_desc`, and `material_keywords` in `enriched_master_hsn.parquet` rather than independently annotated real-world commercial invoices, and Chapter 19 had 0 remaining unused 8-digit leaf HSNs after excluding `full_pairs_train.parquet`.

---

## 3. Frontend Verification

### 3.1 Automated & Live HTTP Verification (Passed)
1. **FastAPI Server Startup:** `uvicorn backend.main:app --host 127.0.0.1 --port 8000` started cleanly (`Application startup complete`).
2. **Live HTTP Endpoints Verified (`http://127.0.0.1:8000`):**
   - `GET /` → `200 OK`; served HTML contains `adaptiveDiscoveryPanel` and `runAdaptiveDiscovery`.
   - `POST /api/v1/hsn-rag/step1-context-aggregator` (`{"product": "cotton shirt"}`, verified via FastAPI `TestClient`) → `200 OK`; existing Step 1 + V2 verification operational (`v2_mode: CLARIFY_AMBIGUOUS`).
   - `POST /api/v1/hsn-v2/classify-adaptive` (`{"description": "cotton shirt", "page": 1, "page_size": 10}`) → `200 OK`; `mode: MULTIPLE_CANDIDATES`, `total_candidates: 21`, `page 1 length: 10`, `has_next_page: True`, `candidate_groups: 10`, `separating_attributes: ['material', 'construction']`.
   - `POST /api/v1/hsn-v2/classify-adaptive` (`page: 2, page_size: 10`) → `200 OK`; `ranks: [11, 12, 13, ...]` confirming pagination across all qualifying candidates.
   - `POST /api/v1/hsn-v2/clarify-adaptive` (`{"description": "cotton shirt", "confirmed_attributes": {"construction": "knitted"}}`) → `200 OK`; `confirmed_attributes: {'construction': 'knitted'}`, `effective_query: 'cotton shirt knitted'`, `top_hsn: 61051020`, `retained_in_cand: {'construction': 'knitted'}`.
   - `POST /api/v1/hsn-v2/classify-adaptive` (`{"description": "BABIES GARMENTS AND CLOTHING ACCESSORIES"}`, verified via FastAPI `TestClient`) → `200 OK`; `discovery_complete: False`, `stopping_reason: "resource_budget_reached (250/4851 examined; last_round_new_active=1)"`.
3. **FastAPI `TestClient` + HTML Wiring (`tests/test_multi_candidate_engine.py::test_fastapi_adaptive_endpoints_and_ui_wiring`):** Passed in `pytest`.

### 3.2 Interactive Browser Screenshot Verification (Blocked)
- **Status:** **NOT COMPLETED (Blocked by environment)** — Chrome DevTools MCP (`browser` subagent) failed to connect with `ENOENT` on `C:\Users\User\AppData\Local\Google\Chrome\User Data\DevToolsActivePort` (Chrome remote debugging not enabled), and neither `playwright` nor `selenium` is installed in `venv`. Therefore, no live browser screenshots were captured.

---

## 4. Regression Verification

### 4.1 Active HSN V2 Test Suite (7 Files)
Command executed:
```powershell
& "C:\Users\User\OneDrive\Desktop\GST_Sentinal\venv\Scripts\python.exe" -m pytest tests/test_training_data_builder.py tests/test_product_tariff_reranker.py tests/test_model_registry_and_eval.py tests/test_relevance_and_ambiguity.py tests/test_feedback_and_statutory.py tests/test_confidence_calibrator.py tests/test_multi_candidate_engine.py -q
```
**Result:** **26 / 26 passed** (3 warnings: FastAPI `on_event` deprecation and `pytest.mark.slow` unregistered mark).

### 4.2 Excluded Legacy Test Files (Exact Collection Errors)
Command executed:
```powershell
& "C:\Users\User\OneDrive\Desktop\GST_Sentinal\venv\Scripts\python.exe" -m pytest tests/test_end_to_end.py tests/test_hsn_verified_knowledge_store.py tests/test_passport.py --collect-only -q
```
**Result:** 3 collection errors (pre-existing legacy module/symbol mismatches):
1. `tests/test_end_to_end.py`: `ModuleNotFoundError: No module named 'src.nlp.multilingual_processor'`
2. `tests/test_hsn_verified_knowledge_store.py`: `ImportError: cannot import name 'compute_attribute_fingerprint' from 'src.ml.hsn_verified_store'`
3. `tests/test_passport.py`: `ImportError: cannot import name 'generate_passport_id' from 'src.passport.passport_identity'`

---

## 5. Known Limitations & Production Readiness Assessment

### Known Limitations
1. **Exact 8-Digit Leaf HSN Differentiation (`0 / 23`):** Sibling 8-digit tariff items under the same heading receive nearly identical Cross-Encoder scores (`distinction_confidence ≈ 0`), causing `hsn_confidence` to remain below `tau_exact_hsn=0.55` and routing predictions to `MULTIPLE_CANDIDATES` / `CHAPTER_ONLY_CLARIFY` instead of `EXACT_HSN`.
2. **CPU Latency:** Mean latency of **16.55 s** and P95 of **34.38 s** on CPU remain too high for synchronous real-time interactive SLA without GPU acceleration or further Cross-Encoder distillation/caching.
3. **Incomplete Discovery on Very Broad Categories (`7 / 51` = 13.73%):** Broad queries (`BABIES GARMENTS...`, `T-SHIRTS...`, `WOMEN'S OR GIRLS' SUITS...`) legitimately exceed the 250-record evaluation budget and report `discovery_complete: False`.
4. **Live Browser Screenshots Not Captured:** Chrome DevTools remote debugging was unavailable in this session; only HTTP API + FastAPI `TestClient` + HTML wiring were verified.
5. **Eval Set Leakage Caveat:** `exact_hsn_eval_suite.parquet` has `hsn_overlap=24` with `full_pairs_val.parquet` (0 query overlap, 0 train overlap) and was synthetically derived from statutory columns.

### Production Readiness Assessment
**Verdict: Conditional / Experimental — NOT yet ready for unattended exact-HSN production automation; suitable for human-in-the-loop assisted classification.**
- **Ready:** Honest abstention/clarification routing (`36/36`), out-of-schedule detection (`8/8`), multi-candidate recall (`88.37%` active, `100%` on unseen exact-HSN pool), and transparent `discovery_complete` reporting.
- **Blocking for full production:** (a) Cross-Encoder fine-tuning / distinction calibration for sibling 8-digit tariff items, (b) latency optimization (GPU inference or smaller/faster reranker for <2s P95), and (c) interactive browser UI E2E verification with Chrome DevTools/Playwright enabled.

