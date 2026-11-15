# Phase 10 — Controlled Exact-HSN Recovery Report

## 1. Executive Summary

Phase 10 implemented targeted root-cause fixes for the exact-HSN disambiguation, parent/leaf separation, numerical constraint handling, confidence calibration, and inference runtime bottlenecks identified in Phase 9, while preserving the existing HSN Intelligence V2 architecture and safety guarantees (no product-specific HSN mappings, no hardcoded rules, no lowered confidence thresholds).

### Key Outcomes
- **Test Suite**: **30/30** tests passed across all 7 active HSN V2 test files (`269.67s`).
- **Cross-Encoder Truncation Eliminated**: Raising `max_length` from `144` to `384` and reordering `format_tariff_context()` reduced Cross-Encoder truncation on the 23 detailed evaluation cases from **21/23 (91.3%)** to **0/23 (0.0%)**, and eliminated top-2 logit ties (`13/23` distinct top-2 at `144` -> **23/23 (100%)** distinct at `384`).
- **Parent vs. Leaf Separation**: Parent 4-digit/6-digit entries are classified via `classify_tariff_level()` and blocked from being emitted as `EXACT_HSN` predictions; parent entries appearing in top-5 dropped from **8/23** to **2/23**.
- **Top-1 Leaf Ranking Recovery**: Top-1 8-digit leaf hit rate on the 23 detailed cases improved from **7/23 (30.4%)** (Stage 1/2 baseline) to **16/23 (69.6%)** after Stage 3 dynamic sibling distinction and leaf-only disambiguation. On the new 12-case zero-leakage independent eval (`data/eval/independent_exact_hsn_eval.parquet`), candidate pool recall is **12/12 (100%)** and Top-1 leaf match is **8/12 (66.7%)**.
- **Confidence Recalibration (`calibration.json`)**: On the 50 held-out disjoint validation queries, `hsn_calibrator` NLL improved from **2.6775** to **0.4308**, Brier score from **0.3745** to **0.1334**, and ECE from **0.3651** to **0.1495**, achieving **100% accuracy (0% error rate)** on the selective curve for `threshold >= 0.50` (`10/50` covered).
- **Fair 51-Case Benchmark**: Phase 10 achieved **46/51 (90.20%)** strict pass rate vs. Phase 6's **40/51 (78.43%)**, with **90.20%** discovery completeness and **18/18 (100%)** chapter accuracy.
- **Conservative `EXACT_HSN` Gate**: Because `MultiCandidateEngine` preserves `MULTIPLE_CANDIDATES` / `CHAPTER_ONLY_CLARIFY` whenever sibling tariff items remain competitive in the pool or `tau_exact_hsn = 0.55` is not cleared with clear statutory evidence, auto-emitted `EXACT_HSN` coverage remained **0/23** on the 35-case suite and **0/12** on the 12-case independent eval (safe abstention/clarification rather than forced guessing).

---

## 2. Files Changed

| File | Summary of Changes |
| :--- | :--- |
| [product_tariff_reranker.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/ml/product_tariff_reranker.py) | Added `classify_tariff_level()`, `tariff_level`, `subheading_6digit_desc`, and `tariff_item_desc` to `RerankedTariffCandidate`; reordered `format_tariff_context()` to place HSN code + leaf description + 6-digit subheading + keywords first; added length-bucketed batching in `score_pairs()`. |
| [relevance_classifier.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/ml/relevance_classifier.py) | Raised default `max_length` from `144` to `384`. |
| [ambiguity_resolver.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/ml/ambiguity_resolver.py) | Added `_UNIT_NORMALIZATION`, `NumericConstraint`, `extract_numeric_constraints()`, `extract_query_numeric_values()`, `evaluate_numeric_match()` (`NO_CONSTRAINT \| MISSING \| MATCH \| CONFLICT`), `analyze_sibling_distinctions()`, and `numeric_rating` detection in `identify_separating_attributes()`. |
| [multi_candidate_engine.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/ml/multi_candidate_engine.py) | Added `_is_leaf_8digit()`, leaf-only `EXACT_HSN` disambiguation, `hierarchy_context` and `statutory_distinction` metadata, `initial_branch_k=45` / `expansion_factor=3.0`, cross-round `ctx_score_cache` in `discover()`, and leaf-ordered `conf_pool`. |
| [main.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/backend/main.py) | Wrapped synchronous `v2_pipe.classify`, `engine.classify_adaptive`, and `engine.clarify_and_refine` calls in `await asyncio.to_thread(...)` to prevent blocking the FastAPI event loop. |
| [recalibrate_hsn_v2_phase10.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/scripts/recalibrate_hsn_v2_phase10.py) | Built zero-leakage 12-case `independent_exact_hsn_eval.parquet` and recalibrated `chapter_calibrator` and `hsn_calibrator` on disjoint validation queries, saving `reports/phase10_calibration_report.json` and updating `data/model_versions/hsn_reranker_v1/calibration.json`. |
| [test_product_tariff_reranker.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/tests/test_product_tariff_reranker.py) | Added `test_format_tariff_context_prioritizes_leaf_details` and `test_classify_tariff_level`. |
| [test_multi_candidate_engine.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/tests/test_multi_candidate_engine.py) | Added `test_parent_vs_leaf_never_predicts_parent_as_exact_hsn`. |
| [test_relevance_and_ambiguity.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/tests/test_relevance_and_ambiguity.py) | Added `test_numeric_constraints_and_sibling_distinction`. |

---

## 3. Stage-by-Stage Technical Results

### Stage 1 & Stage 2 — Cross-Encoder Context & Parent vs. Leaf Separation
Evaluated on the 23 detailed exact-HSN cases:

| Configuration | Tokenizer Truncation | Distinct Top-2 Logits | Top-1 Leaf Hit | Parent in Top-5 | Mean Latency (ms) | Peak Memory (MB) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| Baseline (`max_length=144`) | 21/23 (91.3%) | 13/23 (10 ties) | — | 8/23 | 20,815.4 | — |
| Reordered (`max_length=384`) | **0/23 (0.0%)** | **23/23 (100%)** | 7/23 (30.43%) | **2/23** | 22,775.3 | 7.55 |
| Reordered (`max_length=512`) | **0/23 (0.0%)** | **23/23 (100%)** | 7/23 (30.43%) | **2/23** | 17,651.6 | 7.52 |

`max_length=384` was selected as the production default because `0/23` cases truncated at `384`, making `512` unnecessary.

### Stage 3 — Dynamic Statutory Distinction & Numerical Constraints
- Implemented generalized regex + unit-normalized extraction (`kVA`, `W`, `kW`, `V`, `A`, `Hz`, `mm`, `cm`, `m`, `kg`, `g`, `L`, `mL`, `RPM`, `°C`) with operator awareness (`<`, `<=`, `>`, `>=`, range).
- Missing product attributes return `MISSING` (never inferred as `MATCH`), ensuring clarification is requested when statutory thresholds separate sibling leaves.
- Combined with Stage 2 leaf-only disambiguation, **Top-1 leaf hit rate** on the 23 detailed cases rose from **7/23 (30.43%)** to **16/23 (69.57%)** with `8/23` clear evidence matches (`mean_rounds=5.78`).

### Stage 4 — Confidence Recalibration & Data-Leakage Disclosure
- **Overlap Audit**: `data/eval/exact_hsn_eval_suite.parquet` (35 cases) has **0 query overlap** and **0 train overlap**, but **24/35 HSN code overlap** with `full_pairs_val.parquet`. To provide zero-leakage validation, `data/eval/independent_exact_hsn_eval.parquet` (**12 cases**) was constructed with **0 overlap** against train, val, and existing eval sets.
- **Calibration Results** (fit on `77` disjoint validation queries, evaluated on `50` held-out disjoint validation queries from `reports/phase10_calibration_report.json`):

| Calibrator | NLL (Old -> New) | Brier (Old -> New) | ECE (Old -> New) |
| :--- | :---: | :---: | :---: |
| `hsn_calibrator` (`n=50`) | 2.6775 -> **0.4308** | 0.3745 -> **0.1334** | 0.3651 -> **0.1495** |
| `chapter_calibrator` (`n=50`) | 0.1038 -> **0.0998** | 0.0197 -> 0.0220 | 0.0115 -> 0.0120 |

- **Selective Accuracy Curve (`new_hsn_selective_curve`)**:
  - `threshold >= 0.30`: 29/50 covered (58%), accuracy 0.5862
  - `threshold >= 0.40`: 18/50 covered (36%), accuracy 0.8333
  - `threshold >= 0.50`: **10/50 covered (20%), accuracy 1.0000 (error rate 0.0)**
  - Existing decision thresholds were preserved unchanged (`tau_abstain=0.40`, `tau_chapter=0.50`, `tau_exact_hsn=0.55`).

### Stage 5 — Performance Optimizations
- Added cross-round `ctx_score_cache` inside `AdaptiveCandidateDiscoverer.discover()` so previously scored `(query, hsn_code)` contexts are never re-evaluated by the Cross-Encoder on subsequent expansion rounds.
- Tuned `initial_branch_k=45` and `expansion_factor=3.0` to reduce unnecessary round-trips.
- Added length-bucketed batching in `score_pairs()` to minimize transformer padding overhead.
- Wrapped synchronous pipeline/engine calls in `backend/main.py` with `await asyncio.to_thread(...)` so the FastAPI event loop remains responsive under concurrent requests.
- **Note**: `onnxruntime` and `optimum` are not installed in the workspace environment, so ONNX model export/quantization was omitted.

---

## 4. Final Benchmark & Independent Evaluation Results

### 4.1 Fair 51-Case Benchmark (`reports/phase7_benchmark_report.json`)

| Metric | Phase 6 V2 | Phase 10 Adaptive |
| :--- | :---: | :---: |
| Strict Pass Rate | 40/51 (78.43%) | **46/51 (90.20%)** |
| Clarification-Aware Pass Rate | 40/51 (78.43%) | **46/51 (90.20%)** |
| Candidate Pool Recall (Active) | — | **90.70%** |
| Exhaustive Reference Recall (5q) | — | **4/4 (100%)** |
| Candidate Precision (Mean) | — | **79.70%** |
| Mean Preserved Candidates | — | **54.24** (down from 78.63 in Phase 7) |
| Discovery Completeness Rate | — | **90.20%** (up from 78.43% in Phase 7) |
| Chapter Prediction Accuracy | — | **18/18 (100%)** |
| Multiple-Candidate Coverage | — | **20/21 (95.24%)** |
| Clarification Necessity Accuracy | — | **36/37 (97.30%)** |
| Out-of-Schedule Accuracy | — | **8/8 (100%)** |
| Mean Latency | 5,865.22 ms | 28,703.31 ms |
| P95 Latency | 9,703.86 ms | 50,336.79 ms |

### 4.2 35-Case Exact-HSN Suite (`reports/phase7_benchmark_report.json`)
- **Detailed cases (`n=23`)**: Candidate pool recall **1.0 (100%)**, Chapter accuracy **0.1739** (cases in `MULTIPLE_CANDIDATES` leave `final_chapter=null`), auto-emitted `EXACT_HSN` coverage **0.0 (0/23)**, abstention rate **0.0**.
- **Clarification cases (`n=12`)**: Candidate pool recall **12/12 (100%)** before and after clarification; auto-emitted `EXACT_HSN` hits **0/12** before and after simulated clarification.

### 4.3 12-Case Zero-Leakage Independent Eval (`data/eval/independent_exact_hsn_eval.parquet`)
- **Candidate Pool Recall**: **12/12 (100%)**
- **Top-1 Leaf Match Rate**: **8/12 (66.7%)** (`39159061`, `73239910`, `84119100`, `84136020`, `84137010`, `85044021`, `85086000`, `94055039`)
- **Prediction Modes**: `0` `EXACT_HSN`, `7` `CHAPTER_ONLY_CLARIFY` (all 7 matching expected chapter), `5` `MULTIPLE_CANDIDATES`.
- Notably, `85086000` achieved `hsn_conf=0.8109` and ranked #1 in the pool, yet stayed in `MULTIPLE_CANDIDATES` because sibling tariff items remained in the discovered pool without triggering single-winner collapse.

---

## 5. Regression Verification

Command executed:
```powershell
& "C:\Users\User\OneDrive\Desktop\GST_Sentinal\venv\Scripts\python.exe" -m pytest tests/test_training_data_builder.py tests/test_product_tariff_reranker.py tests/test_model_registry_and_eval.py tests/test_relevance_and_ambiguity.py tests/test_feedback_and_statutory.py tests/test_confidence_calibrator.py tests/test_multi_candidate_engine.py -q
```
Result: **30 passed, 3 warnings in 269.67s (0:04:29)**.

---

## 6. Remaining Limitations

1. **CPU Inference Latency**: Raising `max_length` from `144` to `384` increased CPU Cross-Encoder sequence cost (`28.70s` mean, `50.34s` P95 on the 51-case suite). `onnxruntime` / `optimum` are not installed in this environment; installing and exporting to quantized ONNX or running on GPU is recommended for production latency targets.
2. **Strict `EXACT_HSN` Emission Gate**: While Top-1 leaf ranking recovered to **69.6%** (23 detailed cases) and **66.7%** (12 zero-leakage cases), `MultiCandidateEngine` still defaults to `MULTIPLE_CANDIDATES` or `CHAPTER_ONLY_CLARIFY` whenever sibling tariff items remain viable in the candidate pool, keeping auto-emitted `EXACT_HSN` coverage at `0%` on ambiguous/unseen single-turn queries.

