# Phase 16 — Reliability, Candidate Precision & Complex Intent Validation Report

**Checkpoint**: `phase15-checkpoint` (commit `5eeabec`)  
**Machine-Readable Benchmark**: [phase16_benchmark_100plus.json](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/reports/phase16_benchmark_100plus.json)  
**Benchmark Script**: [benchmark_phase16_100plus.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/scripts/benchmark_phase16_100plus.py)

---

## 1. Implementation Summary & Files Modified

| Task | Module(s) | Implemented Capabilities |
|---|---|---|
| **Task 1: Intent Extraction Reliability** | [intent_extractor.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/nlp/intent_extractor.py) | Configurable `max_json_retries` (default `2`), stronger JSON repair for unterminated strings / trailing commas / unclosed brackets, mandatory `physical_product` check, `RULE_BASED_FALLBACK` using `analyze_product_intent` + statutory vocabulary grounding, `extraction_source` (`LLM` / `RULE_BASED_FALLBACK` / `HYBRID`), `raw_llm_response` preservation, `validation_errors` tracking. |
| **Task 2: Complex Product Intent** | [product_intent_analyzer.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/nlp/product_intent_analyzer.py) | Semicolon multi-article detection (`secondary_articles`), `product_form` extraction (`granules`, `powder`, `flakes`, `sheets`, etc.), `missing_critical_attributes` detection (`material`, `construction`, `capacity_or_rating`), per-attribute `confidence` and `evidence_trace` on every `AttributeRelationship`. |
| **Task 3: Candidate Precision** | [candidate_evidence_evaluator.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/ml/candidate_evidence_evaluator.py), [multi_candidate_engine.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/ml/multi_candidate_engine.py) | Added `heading_compatible`, penalized generic superordinate-only article matches (`container`, `equipment`, etc.), dynamically distinguished household/tableware storage articles from conveyance/packing containers (`role_mismatch`), and incorporated `evidence_score` into candidate ranking. |
| **Task 4: Confidence Consistency** | [confidence_calibrator.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/ml/confidence_calibrator.py), [hsn_v2_pipeline.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/ml/hsn_v2_pipeline.py), [multi_candidate_engine.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/ml/multi_candidate_engine.py) | Centralized `DEFAULT_TAU_ABSTAIN` (`0.45`), `DEFAULT_TAU_CHAPTER` (`0.70`), `DEFAULT_TAU_EXACT_HSN` (`0.65`), and `evaluate_decision_thresholds(...)` so displayed abstention reasons always agree with actual thresholds (eliminating `"0.73 below 0.40"` contradictions). |
| **Task 5: Profiling & Caching** | [multi_candidate_engine.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/ml/multi_candidate_engine.py) | Added `MultiCandidateEngine.get_instance()` singleton cache, configurable `inference_timeout_s`, and per-stage timing telemetry (`stage1_intent_ms`, `retrieval_time_ms`, `reranking_time_ms`, `stage3_evidence_ms`, `stage3_statutory_ms`). |

---

## 2. Benchmark Results (102 Master-Verified Cases, 10 Categories, 9 Active Chapters)

| Subset | Cases | Chapter Acc | Recall | Recall@5 | Recall@10 | Top-1 | Same-H4 Prec | Mat-Only | Exact Hits | False Exact | Abstain OK | Clarify Eff | Mean / P95 Lat (ms) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **`independent_12`** (`0` train/val HSN overlap) | 12 | **100.0%** | **100.0%** | 75.00% | 83.33% | 66.67% | **70.05%** | **0** | 0 (0.0%) | **0** | **100.0%** | **100.0%** | 22,497.9 / 30,033.0 |
| `benchmark_non_indep` (`73` HSN overlap) | 90 | 97.78% | 90.00% | 80.00% | 84.44% | 54.44% | 54.78% | 0 | 20 (22.22%) | 3 | 96.67% | 84.44% | — |
| **Combined `overall`** | **102** | **98.04%** | **91.18%** | **79.41%** | **84.31%** | **55.88%** | **57.97%** | **0** | **20 (19.61%)** | **3** | **97.06%** | **86.27%** | **20,048.3 / 28,378.6** |

### Category Breakdown (`102` Cases)
- `simple` (10): Chapter `100.0%`, Recall `100.0%`, Recall@5 `90.0%`, Exact `30.0%`, Abstain `100.0%`
- `multiple_materials` (10): Chapter `100.0%`, Recall `100.0%`, Recall@5 `100.0%`, Abstain `100.0%`
- `multiple_ingredients` (10): Chapter `100.0%`, Recall `80.0%`, Same-H4 Prec `96.61%`, Abstain `100.0%`
- `parenthetical` (8): Chapter `100.0%`, Recall `75.0%`, Same-H4 Prec `83.91%`, Abstain `100.0%`
- `multiple_components` (10): Chapter `100.0%`, Recall `90.0%`, Top-1 `80.0%`, Exact `50.0%`, Abstain `100.0%`
- `processing` (10): Chapter `100.0%`, Recall `90.0%`, Exact `30.0%`, Abstain `100.0%`
- `ambiguous` (10): Chapter `100.0%`, Recall `90.0%`, Clarify Eff `90.0%`, Abstain `100.0%`
- `incomplete` (8): Chapter `87.5%`, Recall `100.0%`, Recall@10 `100.0%`, Clarify Eff `100.0%`, False Exact `1` (`centrifugal pump` -> `84139120` parts)
- `similar_products` (8): Chapter `100.0%`, Recall `87.5%`, Top-1 `87.5%`, Exact `50.0%`, False Exact `1` (`hdpe jerrycan` -> `39233090`)
- `complex_commercial` (18): Chapter `94.44%`, Recall `94.44%`, Top-1 `61.11%`, Abstain `94.44%`

---

## 3. Performance Profiling (`STAGE_LATENCIES` across 102 Cases)

| Stage | Mean Latency (ms) | Share of Total |
|---|---:|---:|
| `stage1_intent_ms` (`analyze_product_intent`) | **3.34 ms** | 0.02% |
| `retrieval_time_ms` (Hybrid BM25 + Dense + RRF) | **166.95 ms** | 0.83% |
| `reranking_time_ms` (Cross-Encoder inference) | **19,740.62 ms** | **98.47%** |
| `stage3_evidence_ms` (Evidence & Profile evaluation) | **25.49 ms** | 0.13% |
| `stage3_statutory_ms` (98-chapter statutory comparison) | **102.17 ms** | 0.51% |
| **Total End-to-End Mean / P95** | **20,048.3 ms / 28,378.6 ms** | **100%** |

---

## 4. Known Limitations

1. **CPU Cross-Encoder Bottleneck (`98.5%` of latency)**: Cross-Encoder scoring over ~200+ candidates takes ~`19.7 s` per request on CPU; further latency reduction requires ONNX/INT8 quantization or GPU inference rather than architectural changes.
2. **Parts vs. Whole Machine on Short Incomplete Queries**: `"centrifugal pump"` emitted `84139120` (parts of centrifugal pumps) because `"parts"` vs. whole-article distinction did not block a parts leaf when it was the sole `SAME_PRODUCT` candidate under `841391`.
3. **Pre-existing Local 0.5B LLM Grounding Benchmark**: `tests/test_intent_extractor.py` still has pre-existing failures on `test_laptop_intent_extraction`, `test_water_bottle_unstated_attributes`, `test_intent_accuracy_benchmark_report` (`33.3%`), `test_all_terms_dropped_abstain`, and `test_out_of_schedule_materials` due to local `qwen2.5-0.5b-instruct` output / `data/intent_cache/interpretation_cache.json` entries.

