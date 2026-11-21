# GST Sentinel — Final HSN Development Closure & Consolidated Benchmark Report

**Status:** **CORE HSN PREDICTION DEVELOPMENT COMPLETE**

All improvements strictly preserve the existing three-stage architecture (**Stage 1 Intent & Chapter Analysis -> Stage 2 Hybrid Discovery -> Stage 3 Statutory Verification & Calibrated Final Decision**) with **zero** hardcoded product-to-HSN mappings, **zero** HSN-specific exceptions, **zero** benchmark leakage, and **zero** threshold lowering (`tau_exact_hsn` unchanged).

---

## 1. Improvements Implemented Across the Cycle

1. **Phase 1 — Candidate Retrieval**
   - [src/ml/multi_candidate_engine.py](file:///c:/Users/User/OneDrive/Desktop/GST_Sentinal/src/ml/multi_candidate_engine.py): Fixed `len(raw_by_id) + len(new_rows) >= budget` double-counting bug in `AdaptiveCandidateDiscoverer.discover` so Round 1 inspects the full retrieved pool instead of truncating at half budget (`110/220`).
   - [src/chapter_predictor/normalize.py](file:///c:/Users/User/OneDrive/Desktop/GST_Sentinal/src/chapter_predictor/normalize.py) & [src/ml/candidate_evidence_evaluator.py](file:///c:/Users/User/OneDrive/Desktop/GST_Sentinal/src/ml/candidate_evidence_evaluator.py): Fixed singularization/stemming so `-us`/`-is`/`-os`/`-as` nouns (e.g., `apparatus`) are not truncated to `apparatu`.
   - [src/nlp/product_intent_analyzer.py](file:///c:/Users/User/OneDrive/Desktop/GST_Sentinal/src/nlp/product_intent_analyzer.py): Added syntactic rightmost non-generic head-noun resolution and generic-trailing fallback (e.g., `"satellite earth station uplink transceiver"` -> `"transceiver"`, `"laboratory autoclave sterilizer unit"` -> `"sterilizer"`).
   - [src/nlp/stage1_chapter_analyzer.py](file:///c:/Users/User/OneDrive/Desktop/GST_Sentinal/src/nlp/stage1_chapter_analyzer.py): Excluded explicit constituent-material tokens (when not the head noun) from article title scoring so raw-material chapters do not outscore finished-article chapters.
   - [src/search/hybrid_retrieval.py](file:///c:/Users/User/OneDrive/Desktop/GST_Sentinal/src/search/hybrid_retrieval.py): Tightened Path A chapter focus (`>= 0.50 * max_cw`, top-3 chapters) with nonlinear (`cw ** 1.5`) budget allocation (`0.95 * k_eff`) while preserving Path B 8-digit leaf global safeguard retrieval.

2. **Phase 2 — Candidate Ranking & Statutory Evidence**
   - [src/ml/candidate_evidence_evaluator.py](file:///c:/Users/User/OneDrive/Desktop/GST_Sentinal/src/ml/candidate_evidence_evaluator.py):
     - Added symmetric `parts_vs_complete_article` role detection for explicit spare-parts/component queries.
     - Prioritized explicit subheading/leaf material families (`sub_leaf_fams`) over inherited parent heading materials (e.g., `OF HARDENED PROTEIN` under Heading `3917 OF PLASTICS`), plus added `protein` and `cellulosic` statutory material families.
     - Fixed double-space bug in `other than ...` exclusion regex, preserved hyphenated terms (`t-shirt`), added `un-` prefix negation matching (`unplasticised` vs `plasticised`), and added mutually exclusive propulsion (`spark-ignition/petrol` vs `compression-ignition/diesel`), prime-mover (`wind` vs `water/steam/solar/nuclear`), and media-state (`unrecorded/recordable/blank` vs `recorded`) checks.
   - [src/ml/multi_candidate_engine.py](file:///c:/Users/User/OneDrive/Desktop/GST_Sentinal/src/ml/multi_candidate_engine.py): Updated `_composite_rank_score` to blend non-saturating `logit_norm` with `ce_conf`, `evidence_score`, stemmed hyphen-aware `leaf_specificity_bonus`, and `rrf_norm` (`0.08`), and sorted `role_mismatch` distractors behind clean role-matched candidates.

3. **Phase 3 — Stage 3 Final Decision & Calibration Scope**
   - [src/ml/multi_candidate_engine.py](file:///c:/Users/User/OneDrive/Desktop/GST_Sentinal/src/ml/multi_candidate_engine.py): Isolated role-mismatched distractors and weak off-subheading `RELATED_PRODUCT`/`INSUFFICIENT_INFORMATION` noise from `same_leaves` and `conf_pool` when a clean `SUPPORTED` leaf exists, and ensured `competing_rescued` respects material alignment when Top-1 is material-matched.

---

## 2. Consolidated Benchmark Comparison (`INDEPENDENT_100`, Zero Leakage)

Compared across the original pre-roadmap baseline ([final_hsn_validation_100.json](file:///c:/Users/User/OneDrive/Desktop/GST_Sentinal/reports/final_hsn_validation_100.json)), the Phase 6 committed baseline ([phase6_final_100.json](file:///c:/Users/User/OneDrive/Desktop/GST_Sentinal/reports/phase6_final_100.json)), and the Final Closure run ([final_closure_100.json](file:///c:/Users/User/OneDrive/Desktop/GST_Sentinal/reports/final_closure_100.json)):

| Metric | Original Baseline (`final_hsn_validation_100.json`) | Committed Baseline (`phase6_final_100.json`) | Final Closure (`final_closure_100.json`) | Delta vs Committed |
|---|---:|---:|---:|---:|
| Zero HSN & Query Leakage | `True` | `True` | **`True`** | Preserved |
| Statutory Master Chapters / Rows | 9 ch / 4,851 | 97 ch / 18,797 | **97 ch / 18,797** | Full schedule |
| Chapter Accuracy | `97.0%` | `98.0%` | **`98.0%`** | `0.0 pp` (+1.0 vs orig) |
| Candidate Recall | `91.0%` | `91.0%` | **`91.0%`** | `0.0 pp` |
| Recall@5 | `69.0%` | `65.0%` | **`66.0%`** | **`+1.0 pp`** |
| Recall@10 | `78.0%` | `78.0%` | **`79.0%`** | **`+1.0 pp`** |
| Top-1 Accuracy | `37.0%` | `39.0%` | **`42.0%`** | **`+3.0 pp`** (+5.0 vs orig) |
| Same-Heading Precision | `59.86%` | `60.63%` | `59.0%` | `-1.63 pp` |
| Exact 8-Digit HSN Coverage / Hits | `7.0%` (`7/100`) | `10.0%` (`10/100`) | **`13.0%` (`13/100`)** | **`+3 exacts (+30%)`** |
| Exact HSN Precision | `100.0%` (`7/7`) | `100.0%` (`10/10`) | **`100.0%` (`13/13`)** | **`100.0%`** |
| False Exact Predictions | `0` | `0` | **`0`** | **`0`** |
| Correct Abstention Rate | `100.0%` | `100.0%` | **`100.0%`** | **`100.0%`** |
| Median Retained 8-Digit Leaves | `27.0` | `23.5` | `25.0` | `+1.5` |
| Median / Trimmed Mean Latency* | N/A / `51,937.0 ms` | N/A / `8,216.9 ms` | **`11,900.9 ms` / `12,401.9 ms`** | Expanded Round-1 pool (`19,356` vs `14,585` CE pairs) |
| P95 Latency | `76,007.9 ms` | `12,577.8 ms` | `19,980.1 ms` | `3.8x` faster than orig |

\*Note: Raw `mean_latency_ms` in [final_closure_100.json](file:///c:/Users/User/OneDrive/Desktop/GST_Sentinal/reports/final_closure_100.json) is `256,313.9 ms` due to a single Windows OS sleep/hibernate pause during case #88 (`24,403,604.4 ms`); across the 99 active cases, mean latency is `12,401.9 ms` (`12.40 s`) and overall median is `11,900.9 ms` (`11.90 s`).

**Final 13 Exact 8-Digit Winners (`0` false exacts):**
`61099030`, `73239910`, `84138120`, `84139130`, `84159010`, `84182100`, `84322910`, `85023100`, `85044021`, `85119000`, `85152110`, `85192100`, `94031010`.

---

## 3. Additional Independently Labelled Validation Sets

1. **44-Chapter Unseen Cross-Chapter Evaluation ([eval_unseen_cross_chapter.py](file:///c:/Users/User/OneDrive/Desktop/GST_Sentinal/scripts/eval_unseen_cross_chapter.py) -> [phase6_unseen_cross_chapter_eval.json](file:///c:/Users/User/OneDrive/Desktop/GST_Sentinal/reports/phase6_unseen_cross_chapter_eval.json)):**
   - **Scope:** 44 cases across **44 distinct chapters** strictly outside the 9 legacy training chapters (`zero_legacy9_overlap=True`, `zero_train_val_100_leakage=True`).
   - **Results:** Chapter Accuracy `95.45%`, Candidate Recall `90.91%`, Recall@5 `86.36%`, Top-1 `79.55%`, Exact HSN `4 / 44` (`9.09%`, precision `100.0%`), False Exacts `0`, Correct Abstention `100.0%`, Mean Latency `11,721.7 ms`, P95 `19,270.1 ms`.

2. **20-Chapter Additional Commercial Validation ([eval_additional_commercial.py](file:///c:/Users/User/OneDrive/Desktop/GST_Sentinal/scripts/eval_additional_commercial.py) -> [final_closure_additional_commercial.json](file:///c:/Users/User/OneDrive/Desktop/GST_Sentinal/reports/final_closure_additional_commercial.json)):**
   - **Scope:** 20 newly authored realistic commercial product descriptions across **20 chapters (`04..96`)** with zero HSN or query overlap against `INDEPENDENT_100`, `full_pairs_train/val`, and `independent_exact_hsn_eval.parquet`.
   - **Results:** Chapter Accuracy `80.0%` (`16/20`), Candidate Recall `80.0%` (`16/20`), Recall@5 `70.0%`, Recall@10 `70.0%`, Top-1 `60.0%` (`12/20`), Exact HSN `3 / 20` (`15.0%` coverage: `25041020`, `86040000`, `90019010`; `100.0%` exact precision), False Exacts `0`, Correct Abstention `100.0%`, Mean Latency `11,254.2 ms`, Median `10,755.9 ms`, P95 `15,404.6 ms`.

3. **Full Automated Regression Test Suite:**
   - **13 modules (`pytest`):** **`97 passed, 0 failed, 0 skipped`** in `451.85s` (including [tests/test_final_closure_accuracy.py](file:///c:/Users/User/OneDrive/Desktop/GST_Sentinal/tests/test_final_closure_accuracy.py), [tests/test_phase5_performance.py](file:///c:/Users/User/OneDrive/Desktop/GST_Sentinal/tests/test_phase5_performance.py), and [tests/test_phase4_retrieval_and_ch98.py](file:///c:/Users/User/OneDrive/Desktop/GST_Sentinal/tests/test_phase4_retrieval_and_ch98.py)).

---

## 4. Known Limitations & Remaining Accuracy Gaps

1. **Residual `"OTHER"` Leaves & Master Text Anomalies:** Remaining recall misses in `INDEPENDENT_100` (`#16 39219099`, `#57 84191910`, `#58 84193900`, `#59 84198120`, `#72 85044090`, `#79 85176250`, `#80 85176270`, `#85 85232920`, `#89 85252091`) occur where the authoritative parquet entry uses generic residual phrasing (`"OTHER : OTHER"`, `"OTHER KITCHEN MACHINES"`, `"STATIC CONVERTERS: OTHER"` without commercial terms like `"espresso"`, `"inverter"`, `"router"`) or source typos/shifts (`"DIGIAL LOOP CARRIER"`, `"VSAT TERMINALS"`, `9502` heading `"OMITTED"`).
2. **Conservative Abstention on Identical Sibling Wording & Unstated Technical Ratings:** Many 8-digit tariff siblings share nearly identical parent text differentiated only by technical/numerical specifications omitted in short commercial queries (`tau_exact = 0.55` intentionally preserves `0` false exacts).
3. **CrossEncoder Domain Training Scope:** `hsn_reranker_v1` was trained on the original 9-chapter subset; retraining/calibrating on stratified 97-chapter statutory pairs is left as an offline data engineering upgrade outside core inference code.
4. **Operational / Environment Caveats Noted in Phase 6:** Legacy `/api/v1/hsn-rag/step1-context-aggregator` invokes a slow local LLM (`IntentExtractor`, ~124s warm fallback) whereas `/api/v1/hsn-v2/classify-adaptive` runs in `~11–15s`; `backend/main.py` keeps permissive local CORS (`allow_origins=["*"]`); interactive Chrome DevTools verification requires enabling `chrome://inspect/#remote-debugging`.
