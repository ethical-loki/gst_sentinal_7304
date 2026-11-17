# Stage 1 Accuracy, Explainability & One-Click Structured Handoff to Stage 2

## 1. Summary of Changes

### Canonical Stage 1 & Dynamic Chapter Identification (`src/nlp/stage1_chapter_analyzer.py`)
- Dynamically loads official chapter codes, official chapter titles, and statutory heading/article/material vocabularies from `data/enriched_master_hsn.parquet` (`load_statutory_chapter_index`) with zero hardcoded product-to-chapter or product-to-HSN mappings.
- Implements `identify_relevant_chapters(product_intent, top_k=5)` returning multiple ranked chapter candidates with `chapter_code`, `chapter_title`, `relevance_score`, `confidence`, `why_relevant`, `supporting_attributes`, `limiting_or_contradictory_evidence`, and `uncertainty_note`.
- Implements `build_canonical_stage1_result(description, clarification="", product_intent=None)` producing the single JSON-serializable `stage1_result` payload containing `stage1_status`, `original_description`, `normalized_description`, `primary_commercial_article`, `product_head_noun`, `alternative_names_and_aliases`, `article_category`, `materials_and_composition`, `components_and_relationships`, `characteristics`, `explicit_attributes`, `inferred_attributes`, `missing_attributes`, `chapter_candidates`, `confidence_and_uncertainty`, and `stage2_search_representation`.

### Stage 2 Structured Consumption & Explainability (`src/search/hybrid_retrieval.py`, `src/ml/multi_candidate_engine.py`)
- `HybridHSNEngine.retrieve_with_lineage(..., stage1_result=None)` consumes `stage1_result["stage2_search_representation"]` and `stage1_result["chapter_candidates"]`, applies a `+0.008` RRF prior for Stage 1 guided chapters (never a hard filter), preserves cross-chapter candidates, and attaches `chapter_guided`, `cross_chapter_discovery`, `cross_chapter_reason`, and `retrieval_explanation` to each retrieved record.
- `AdaptiveCandidateDiscoverer.discover(..., stage1_result=None)` forwards `stage1_result` to `retrieve_with_lineage` (with fallback for mock test doubles).
- `MultiCandidateEngine.classify_adaptive(..., stage1_result=None)` hydrates `ProductIntentStructure` from `stage1_result["product_intent"]` when available, exposes Stage 2 explainability fields (`bm25_score`, `vector_score`, `rrf_score`, `chapter_guided`, `cross_chapter_discovery`, `cross_chapter_reason`, `retrieval_explanation`, `heading_4digit_desc`, `subheading_6digit_desc`, `tariff_item_desc`, `matching_attributes`, `missing_attributes`), and returns `stage1_handoff` summary metadata.

### API & One-Click Customer UI (`backend/main.py`, `static/index.html`, `frontend/index.html`)
- `POST /api/v1/hsn-rag/step1-context-aggregator` computes and returns `"stage1_result"` alongside existing fields.
- `POST /api/v1/hsn-v2/classify-adaptive` validates optional `"stage1_result"` (returning HTTP 400 if invalid) and passes it to `engine.classify_adaptive`.
- Both `static/index.html` and `frontend/index.html`:
  - Store `window._stage1StructuredResult = data.stage1_result || null`.
  - Render expandable Stage 1 `<details>` sections (`stage1StructuredDetails`) for Product Identity & Classification Role, Materials & Components, Characteristics & Function, Extracted Evidence & Missing Information, and Dynamic Chapter Candidates.
  - Provide the prominent **"Proceed to Stage 2 – Discover HSN Candidates"** (`id="proceedToStage2Btn"`) button calling `window.proceedToStage2()` with payload validation, duplicate-click guard (`window._stage2InFlight`), loading state, and error handling.
  - Render Stage 2 handoff banner, per-candidate expandable retrieval & hierarchy details (`bm25_score`, `vector_score`, `rrf_score`, hierarchy, `matching_attributes`, `missing_attributes`, `retrieval_explanation`, `cross_chapter_reason`), and Stage 3 verification.

## 2. Verification Results

### Test Suite (52/52 passed)
- `.\venv\Scripts\python.exe -m pytest tests/test_stage1_to_stage2_handoff.py tests/test_stage1_product_intent.py -v`: **18 passed, 0 failed**
- `.\venv\Scripts\python.exe -m pytest tests/test_candidate_evidence_evaluator.py tests/test_relevance_and_ambiguity.py tests/test_confidence_calibrator.py tests/test_multi_candidate_engine.py -v`: **34 passed, 0 failed**

### 100-Case Zero-Leakage Independent Benchmark (`scripts/benchmark_phase17_independent.py`)
| Metric | Baseline (`reports/phase20_independent_100.json`) | After (`reports/stage1_stage2_handoff_100.json`) |
| --- | ---: | ---: |
| Total Cases (Zero HSN & Query Leakage) | 100 | 100 |
| Chapter Accuracy | 96.0% | 96.0% |
| Candidate Recall | 90.0% | 89.0% |
| Recall@5 | 63.0% | 61.0% |
| Recall@10 | 73.0% | 71.0% |
| Top-1 Accuracy | 31.0% | 31.0% |
| Same-Heading Precision | 57.51% | 56.68% |
| Exact HSN Hits | 7 (7.0%) | 7 (7.0%) |
| False Exact Count | 0 | 0 |
| Correct Abstention | 100.0% | 100.0% |
| Mean Latency | 33118.8 ms | 23730.9 ms |
| P95 Latency | 52124.1 ms | 35413.4 ms |
