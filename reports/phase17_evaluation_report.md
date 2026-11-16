# Phase 17 — Candidate Accuracy, Independent Validation & Inference Optimization Report

**Checkpoints**: `phase16-checkpoint` (`cafaedd`) / `phase15-checkpoint` (`5eeabec`)  
**Zero-Leakage 100-Case Benchmark**: [phase17_independent_100.json](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/reports/phase17_independent_100.json)  
**Benchmark Script**: [benchmark_phase17_independent.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/scripts/benchmark_phase17_independent.py)

---

## 1. Root-Cause Analysis & Implemented Changes

1. **Task 1 & Task 2 — Complete Article vs. Parts & False-Exact Prevention** ([candidate_evidence_evaluator.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/ml/candidate_evidence_evaluator.py), [multi_candidate_engine.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/ml/multi_candidate_engine.py)):
   - **Root Cause**: `"centrifugal pump"` previously emitted `EXACT_HSN = 84139120` (`subheading_6digit_desc = "OF PUMPS"`, `tariff_item_desc = "OF CENTRIFUGAL PUMPS"`, `statutory_description = "... - PARTS: 8413 91 - OF PUMPS: OF CENTR..."`). Parts-only items under `PARTS: ... / OF <MACHINE>` were not distinguished from complete machines.
   - **Fix**: Added universal statutory parts-hierarchy detection (`_CAND_PARTS_SUB6_RE`, `_CAND_PARTS_DESC_RE`, `_CAND_PARTS_STAT_RE` + `_CAND_OF_MACHINE_RE`) vs. query parts cues (`_QUERY_PARTS_CUES_RE`), assigning `role_mismatch="complete_article_vs_parts"` and a `-0.25` evidence penalty when the query describes a complete article, and blocking `EXACT_HSN` in `MultiCandidateEngine.classify_adaptive` whenever `top_role_mismatch == "complete_article_vs_parts"`.
   - **Verified**: `"centrifugal pump"` now routes safely to `MULTIPLE_CANDIDATES` (`28 SAME_PRODUCT leaf candidates span 3 distinct headings`) with `841370xx` complete centrifugal pumps at the top instead of `84139120`.
   - **Phase 16 3 False-Exact Analysis**: `centrifugal pump` (`84139120`) was a genuine parts-vs-machine error (fixed). The other two (`hdpe jerrycan...` -> `39233090`, and `304 grade seamless stainless steel boiler tubes, cold drawn...` -> `73044100` `COLD-DRAWN`) matched the statutory master descriptions better than the synthetic benchmark labels.

2. **Task 3 — Cross-Encoder Optimization** ([product_tariff_reranker.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/ml/product_tariff_reranker.py)):
   - **Profiling**: `CUDA: False`, `CPU threads: 4`, `onnxruntime: False`, `optimum: False`, `torch: True`. `max_length=512` vs `256` produced identical logits (`MAD=0.00000`) and similar CPU latency (`12,621.6 ms` vs `12,888.9 ms` for 64 pairs) because `score_pairs` already length-buckets batches. Dynamic `qint8` quantization on `XLMRobertaForSequenceClassification` breaks `CrossEncoder._inference` input-signature inspection.
   - **Fix**: Added an in-memory `(query, context)` pair score cache (`_pair_cache`, max 20,000 entries, `pair_cache_hits` / `pair_cache_misses` telemetry) with `0.00000` logit drift, eliminating redundant Cross-Encoder passes on repeated queries, adaptive expansion overlaps, and clarification follow-ups.

3. **Task 5 — Existing LLM Grounding Failures** ([intent_extractor.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/nlp/intent_extractor.py)):
   - **Root Causes & Fixes**:
     - `asdfghjk qwertyuiop`: Live `qwen2.5-0.5b-instruct` hallucinated `'electric appliance'` (`SUCCESS`). Added a multi-token unrecognizable gibberish guard (`len(q_toks) >= 2`, `0` vocab hits, `0` stem overlap with grounded terms, `0` out-of-schedule keywords) and cleared `grounded_terms` on `UNRECOGNIZED`.
     - `glass water bottle` & `genuine leather wallet`: `OUT_OF_SCHEDULE` was skipped when `"bottle"` matched active Ch 39 or Qwen hallucinated an active product. Added `_oos_primary_materials` handling on the primary head so explicit out-of-schedule primary materials (`glass` Ch 70, `leather` Ch 42) route to `OUT_OF_SCHEDULE`.
     - **Verified**: `test_all_terms_dropped_abstain`, `test_out_of_schedule_materials`, and `test_phase16_task1` all pass (`3 passed in 33.88s`).
     - **Remaining**: `test_laptop_intent_extraction`, `test_water_bottle_unstated_attributes`, and `test_intent_accuracy_benchmark_report` (`33.3%`) remain limited by local `qwen2.5-0.5b-instruct` 0.5B generation quality without adding hardcoded word rules.

---

## 2. 100-Case Zero-Leakage Independent Benchmark (`phase17_independent_100.json`)

- **HSN Leakage**: **`0 / 100`** (`zero_hsn_leakage_verified: true`)
- **Query Leakage**: **`0 / 100`** (`zero_query_leakage_verified: true`)
- **Chapter Accuracy**: **`90.0%`**
- **Candidate Recall**: **`77.0%`** (`Recall@5`: **`59.0%`**, `Recall@10`: **`67.0%`**, `Top-1`: **`32.0%`**)
- **Same-4-Digit Heading Precision**: **`63.73%`**
- **Exact HSN Hits**: **`11 / 100`** (`11.0%`)
- **False Exact Count**: **`2 / 100`** (`39013000` vs `39059100` on ethylene-vinyl acetate copolymer; `85091000` vs `85086000` on electric canister vacuum cleaner)
- **Correct Abstention Rate**: **`98.0%`**
- **Retained 8-Digit Candidates**: mean **`22.39`**, median **`15.0`**, P95 **`78.4`**
- **CPU Latency**: mean **`45,497.5 ms`**, P95 **`83,808.5 ms`** (`18,296` unique uncached pairs across 100 distinct queries on 4-thread CPU)

---

## 3. Regression Test Results

- `tests/test_candidate_evidence_evaluator.py`, `tests/test_stage1_product_intent.py`, `tests/test_relevance_and_ambiguity.py`, `tests/test_confidence_calibrator.py`, `tests/test_multi_candidate_engine.py`: **36 passed** (`182.29s`)
- `tests/test_intent_extractor.py -k "test_all_terms_dropped_abstain or test_out_of_schedule_materials or test_phase16_task1"`: **3 passed** (`33.88s`)

