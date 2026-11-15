# Phase 15 — Universal HSN Intent Precision and Exact Classification Safety Report

**Baseline**: Phase 14.1 Diagnostic Audit ([phase14_1_candidate_quality_audit.json](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/reports/phase14_1_candidate_quality_audit.json), commit `0fbc613`)  
**Machine-Readable Report**: [phase15_evaluation_report.json](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/reports/phase15_evaluation_report.json)  
**Evaluation Script**: [evaluate_phase15.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/scripts/evaluate_phase15.py)

---

## 1. Summary of Implemented Changes (All Universal, Zero Hardcoding)

1. **Priority 1 — Article Identity Protection** ([candidate_evidence_evaluator.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/ml/candidate_evidence_evaluator.py)):
   - Included `heading_4digit_desc` in `build_candidate_profile` article vocabulary so incomplete `article_keywords` or `"Other"` leaf descriptions still receive statutory heading evidence.
   - Removed the fallback that treated pure material tokens as `article_core_tokens` when a query has no non-material article noun.
   - Blocked `material_only_no_article` candidates (when the query states a finished article and the candidate has article vocabulary with zero match) from being promoted to `POSSIBLY_SUPPORTED`, classifying them as `INSUFFICIENT_EVIDENCE` (preserved automatically if no article-matched candidate exists in the pool).

2. **Priority 2 — Stage 1 Parenthesis & Multi-Noun Extraction** ([product_intent_analyzer.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/nlp/product_intent_analyzer.py)):
   - Added `_paren_depth_mask` so `_split_top_level_clauses` never splits inside balanced parentheses (eliminating `(` truncations on `(FOR EXAMPLE, ...)`).
   - Extracted parenthetical examples/qualifiers and trailing material notes into typed `attribute_relationships` / `constituent_materials` without polluting `finished_article`.
   - Focused multi-segment statutory chains (`HEADING, A, B, C - SPECIFIC ARTICLE - OF MATERIAL`) on the specific article segment while preserving the broader heading as `STATUTORY_HEADING_CONTEXT`.

3. **Priority 3 — Exact HSN Decision Safety** ([ambiguity_resolver.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/ml/ambiguity_resolver.py), [multi_candidate_engine.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/ml/multi_candidate_engine.py)):
   - Updated `analyze_sibling_distinctions` so synthetic `article_keywords`/`material_keywords` overlap (`lex_ratio`) alone cannot grant `winner_has_clear_evidence = True` when competing 8-digit leaves exist without numeric match or direct statutory `tariff_item_desc` match, and blocked residual `"OTHER"` winners when a non-residual sibling also competes.
   - Updated `MultiCandidateEngine.classify_adaptive` so `dist_pool` includes `INSUFFICIENT_INFORMATION` 8-digit siblings under the winning 6-digit subheading, preventing a single `SAME_PRODUCT` label from masking unresolved sibling competition (`19023090` vs `19023010`, `39233010` vs `39233090`).

---

## 2. Phase 14.1 vs Phase 15 Comparison (Exact Same 24 Baseline Cases)

| Metric | Phase 14.1 Baseline (`n=24`) | Phase 15 (`n=24`) | Delta |
|---|---:|---:|---|
| Candidate recall (0 false rejections) | **100.0%** (`0` rejected) | **100.0%** (`0` rejected) | Preserved |
| `material_only_no_article` count | `52` | **`0`** | **-100%** |
| False retention (outside target 4-digit heading) | `274` | **`223`** | **-18.6%** |
| Same-4-digit-heading precision | `65.00%` | **`69.74%`** | **+4.74 pp** |
| Mean distinct 8-digit candidates | `32.62` | **`30.71`** | **-1.91** |
| Median distinct 8-digit candidates | `21.0` | **`15.0`** | **-28.6%** |
| P95 distinct 8-digit candidates | `132.25` | `132.25` | Unchanged |
| Gold HSN Top-1 / Top-3 / Top-5 | `54.17%` / `79.17%` / `83.33%` | **`54.17%` / `79.17%` / `83.33%`** | Preserved |
| False `EXACT_HSN` emissions | `2` | **`0`** | **-100%** |
| Correct abstention rate | `91.67%` (`22/24`) | **`100.0%` (`24/24`)** | **+8.33 pp** |
| Exact HSN hits | `3` (`12.50%`) | `2` (`8.33%`) | `-1` (`94013000` now abstains safely due to `94013100` wood vs other) |
| Mean / P95 latency (ms) | — | `23614.9` / `36389.1` | — |

---

## 3. Stratified Evaluation Across All 42 Cases (9 Active Chapters)

Chapters covered: `19, 39, 61, 62, 73, 84, 85, 87, 94`.

| Subset | Cases | Recall | Same-H4 Prec | Mat-Only | Mean / Med / P95 Ret | Top-1 / Top-3 / Top-5 | Exact Hits | False Exact | Abstain OK | Mean / P95 Lat (ms) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `independent_12` (0 train/val overlap) | 12 | 100.0% | 70.05% | 0 | 48.42 / 27.5 / 156.7 | 66.67% / 75.00% / 75.00% | 0 (0.0%) | **0** | **100.0%** | 27647.2 / 37207.1 |
| `synthetic_12` (11 HSN overlap) | 12 | 100.0% | 68.59% | 0 | 13.00 / 9.0 / 35.25 | 41.67% / 83.33% / 91.67% | 2 (16.67%) | **0** | **100.0%** | 19582.7 / 26599.0 |
| `unseen_18` (2 per chapter; 17 HSN overlap) | 18 | 100.0% | 41.26% | 0 | 23.83 / 11.0 / 66.3 | 88.89% / 94.44% / 94.44% | 7 (38.89%) | **0** | **100.0%** | 19197.1 / 27371.0 |
| **Combined `all_42`** | **42** | **100.0%** | **59.26%** | **0** | **27.76 / 14.0 / 99.9** | **69.05% / 85.71% / 88.10%** | **9 (21.43%)** | **0** | **100.0%** | **21721.6 / 35529.1** |

---

## 4. Evaluation Integrity

- **Statutory master verification**: `42 / 42` gold HSN codes exist as 8-digit leaf records in `data/enriched_master_hsn.parquet` (`all_42_in_master_8digit: true`).
- **Query leakage**: `0 / 42` queries appear in `full_pairs_train.parquet` or `full_pairs_val.parquet`.
- **HSN overlap**:
  - `independent_12`: **`0 / 12`** HSN overlap with train or val.
  - `synthetic_12`: `11 / 12` HSN overlap with train or val.
  - `unseen_18`: `17 / 18` HSN overlap with train or val (unseen query text covering all 9 active chapters).

