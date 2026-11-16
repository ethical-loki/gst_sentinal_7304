# Phase 19 — Statutory Candidate Preservation & False-Exact Prevention Report

**Baseline**: Phase 17 commit `ce2a752` (tagged `phase17-checkpoint`)  
**Phase 18 Audit**: [phase18_readonly_audit.md](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/reports/phase18_readonly_audit.md) (preserved unmodified)  
**Benchmark Data**: [phase19_independent_100.json](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/reports/phase19_independent_100.json) (`100` cases, `0` HSN overlap, `0` query overlap with `train`/`val`)

---

## 1. Implementation Results

| Task | Module(s) | Implemented Changes |
|---|---|---|
| **Task 1: Fix synthetic material contradictions** | [candidate_evidence_evaluator.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/ml/candidate_evidence_evaluator.py) | Added `statutory_material_families` (computed solely from statutory descriptions `tariff_item_desc`, `statutory_description`, `subheading_6digit_desc`, `heading_4digit_desc`). Hard `Material contradiction` (`CONTRADICTED`) checks `statutory_material_families` only, while `material_families` (including synthetic `material_keywords`) continues to provide positive supporting evidence. |
| **Task 2: Safe Cross-Encoder candidate rescue** | [multi_candidate_engine.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/ml/multi_candidate_engine.py) | Preserves `UNRELATED` 8-digit leaves when independent statutory `article_matches` + `heading_compatible` hold without contradictions, generic-only matches, or parts-vs-complete mismatch. Preserves original `ce_relation` (`UNRELATED`) and sets `evidence_status=POSSIBLY_SUPPORTED`, `rescued_by_statutory_evidence=True`, `rescue_reason`, and `rescued_candidates_count` in `evidence_summary`. |
| **Task 3: Exact HSN ambiguity protection** | [multi_candidate_engine.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/ml/multi_candidate_engine.py), [confidence_calibrator.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/ml/confidence_calibrator.py) | Enforced multi-heading ambiguity check (`len(unique_headings) > 1 and distinction_confidence < 0.05`) before `winner_has_clear_evidence` can emit `EXACT_HSN`, routing tied multi-heading cases like `39013000` vs `39059100` to `MULTIPLE_CANDIDATES`. |
| **Task 4: Statutory text normalization** | [statutory_master_index.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/search/statutory_master_index.py), [product_tariff_reranker.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/ml/product_tariff_reranker.py), [candidate_evidence_evaluator.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/ml/candidate_evidence_evaluator.py) | Added search/evaluation-time spelling normalization (`vaccum -> vacuum`, `stailess -> stainless`, `inflater -> inflator`, etc.) while keeping source data and displayed descriptions intact. |
| **Task 5: Cross-Encoder batch optimization** | [product_tariff_reranker.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/ml/product_tariff_reranker.py) | Made `batch_size` configurable with `64` as default (`MAD = 0.0000000` vs `batch_size=32`, preserving exact logits and pair-cache telemetry). |

---

## 2. Regression Test Results

- `tests/test_candidate_evidence_evaluator.py`, `tests/test_stage1_product_intent.py`, `tests/test_relevance_and_ambiguity.py`, `tests/test_confidence_calibrator.py`: **32 passed** (`8.24s`), including new Phase 19 tests for Cases `#82, #98, #99`, Case `#73` spelling normalization, Case `#4` multi-heading safety, and `UNRELATED` statutory rescue.
- `tests/test_multi_candidate_engine.py`: **7 passed** (`143.88s`), including complete-article vs. parts and FastAPI UI wiring tests.
- **Total HSN Suite**: **39 / 39 passed**.
- **Batch Size Equivalence Check**: `batch_size=32` vs `batch_size=64` on 64 pairs yielded `MAD = 0.0000000` (exact score equivalence).

---

## 3. 100-Case Zero-Leakage Benchmark Comparison (Phase 17 vs. Phase 19)

Expected HSN labels remain evaluation-only and never enter prediction inputs (`zero_hsn_leakage_verified: true`, `zero_query_leakage_verified: true`).

| Metric | Phase 17 (`ce2a752`) | Phase 19 | Delta |
|---|---:|---:|---|
| Chapter accuracy | `90.0%` | **`90.0%`** | `0.0 pp` |
| Candidate recall | `77.0%` | **`86.0%`** | **`+9.0 pp`** |
| Recall@1 (Top-1) | `32.0%` | `28.0%` | `-4.0 pp` |
| Recall@3 | `49.0%` | `47.0%` | `-2.0 pp` |
| Recall@5 | `59.0%` | `57.0%` | `-2.0 pp` |
| Recall@10 | `67.0%` | **`67.0%`** | `0.0 pp` |
| Recall@20 | `73.0%` | **`76.0%`** | **`+3.0 pp`** |
| Exact HSN hits | `11 / 100` (`11.0%`) | `9 / 100` (`9.0%`) | `-2` |
| False exact predictions | `2 / 100` | **`1 / 100`** | **`-1` (Case #4 fixed)** |
| Correct abstention rate | `98.0%` | **`99.0%`** | **`+1.0 pp`** |
| Mean / Median / P95 retained | `22.39 / 15.0 / 78.4` | `70.08 / 60.5 / 154.05` | `+47.69` mean (from `UNRELATED` rescues) |
| Mean latency | `45,497.5 ms` | **`20,827.8 ms`** | **`-54.2%`** |
| P95 latency | `83,808.5 ms` | **`29,451.4 ms`** | **`-64.9%`** |

---

## 4. Remaining Limitations

1. **Broad `UNRELATED` Rescue Inflates Pool Size (`mean_retained = 70.08`) & Can Trigger `ev_backed_leaves` Filtering on Parts**:
   - Rescuing `UNRELATED` candidates across all headings whenever `article_matches` and `heading_compatible` hold increased `mean_retained` from `22.39` to `70.08` (dropping `same_heading_precision_pct` from `63.73%` to `34.28%`).
   - On 5 spare-part queries (`84099942`, `84139130`, `84149019`, `84199010`, `84219900`), rescuing 1 non-gold `UNRELATED` leaf into `ev_backed_leaves` prevented the `elif leaf_qualifying:` fallback from keeping `INSUFFICIENT_EVIDENCE` parts leaves.
2. **Remaining False Exact (`#73`: `85091000` vs `85086000`)**:
   - Even with `vaccum -> vacuum` normalization, `85086000` (`OTHER VACCUM CLEANERS`) still received `UNRELATED` from the Cross-Encoder (`85091000` remained the sole `SAME_PRODUCT` leaf, so `len(same_leaves) == 1` emitted `EXACT_HSN`). Rescued `UNRELATED` leaves under a competing heading (`8508`) are not currently included in `has_competing` ambiguity checks.
3. **Zero-Hit Retrieval (`#59`: `84198120`)**:
   - `"commercial espresso coffee brewing machine"` still misses hybrid top-250 because `84198120`'s statutory text lacks `"espresso"`/`"coffee"`.
