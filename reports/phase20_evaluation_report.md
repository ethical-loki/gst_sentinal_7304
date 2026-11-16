# Phase 20 — Selective Candidate Rescue, Ambiguity Safety & Trade-Term Retrieval Report

**Baselines**: Phase 17 (`ce2a752`), Phase 19 (`48baa77`, tagged `phase19-checkpoint`)  
**Benchmark Data**: [phase20_independent_100.json](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/reports/phase20_independent_100.json) (`100` cases, `0` HSN overlap, `0` query overlap with `train`/`val`)

---

## 1. Implementation Results

| Task | Module(s) | Implemented Changes |
|---|---|---|
| **Task 1: Remaining False-Exact Fix (`#73`)** | [multi_candidate_engine.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/ml/multi_candidate_engine.py) | Checked strongly rescued competing headings (`len(statutory_article_matches) >= 2`, `heading_compatible=True`, `role_mismatch=""`) before allowing `EXACT_HSN`, routing Case #73 (`85091000` vs rescued `85086000`) to `MULTIPLE_CANDIDATES`. |
| **Task 2: Selective Candidate Rescue & Spare-Parts Fix** | [candidate_evidence_evaluator.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/ml/candidate_evidence_evaluator.py), [multi_candidate_engine.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/ml/multi_candidate_engine.py), [product_intent_analyzer.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/nlp/product_intent_analyzer.py) | Added `statutory_article_matches` (non-generic tokens matched in statutory descriptions only); restricted `UNRELATED` rescue to same-heading siblings, `>= 2` specific statutory article matches, or empty-pool fallback; prevented rescued `UNRELATED` leaves from triggering `ev_backed_leaves` filtering of `INSUFFICIENT_EVIDENCE` parts leaves; preserved serviced machine in `finished_article` for `"spare parts for <machine>"` queries. |
| **Task 3: Trade-Term Retrieval Enrichment** | [hybrid_retrieval.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/search/hybrid_retrieval.py) | Added general controlled commercial-to-statutory WCO vocabulary expansion in `_expand_abbreviated_query` (covering hot drinks/catering, thermal drying/sterilizing, networking/telecom, power converters, furnishings, and spelling variants, with zero hardcoded HSN mappings). |
| **Task 4 & 5: Ranking Quality & Performance Preservation** | [multi_candidate_engine.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/ml/multi_candidate_engine.py), [product_tariff_reranker.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/ml/product_tariff_reranker.py) | Kept rescued `UNRELATED` candidates ordered below `SAME_PRODUCT` / `INSUFFICIENT_INFORMATION` / `RELATED_PRODUCT`; preserved `batch_size=64` (`MAD=0.0000000` vs `32`) and pair-cache telemetry. |

---

## 2. Regression Test Results (`40 / 40` Passed)

- `tests/test_candidate_evidence_evaluator.py`, `tests/test_stage1_product_intent.py`, `tests/test_relevance_and_ambiguity.py`, `tests/test_confidence_calibrator.py`: **33 passed** (`10.50s`), including new Phase 20 tests for Case #73 (`85091000` vs `85086000`), spare-parts head preservation, and commercial-to-statutory terminology expansion.
- `tests/test_multi_candidate_engine.py`: **7 passed** (`238.42s`), including complete-article vs. parts and FastAPI UI wiring tests.

---

## 3. 100-Case Zero-Leakage Benchmark Comparison (Phase 17 vs. Phase 19 vs. Phase 20)

Expected HSN labels remain evaluation-only (`zero_hsn_leakage_verified: true`, `zero_query_leakage_verified: true`).

| Metric | Phase 17 (`ce2a752`) | Phase 19 (`48baa77`) | Phase 20 | Delta (P20 vs P17 / P19) |
|---|---:|---:|---:|---|
| Chapter accuracy | `90.0%` | `90.0%` | **`96.0%`** | **`+6.0 pp` / `+6.0 pp`** |
| Candidate recall | `77.0%` | `86.0%` | **`90.0%`** | **`+13.0 pp` / `+4.0 pp`** |
| Recall@1 | `32.0%` | `28.0%` | `31.0%` | `-1.0 pp` / **`+3.0 pp`** |
| Recall@3 | `49.0%` | `47.0%` | **`51.0%`** | **`+2.0 pp` / `+4.0 pp`** |
| Recall@5 | `59.0%` | `57.0%` | **`63.0%`** | **`+4.0 pp` / `+6.0 pp`** |
| Recall@10 | `67.0%` | `67.0%` | **`73.0%`** | **`+6.0 pp` / `+6.0 pp`** |
| Recall@20 | `73.0%` | `76.0%` | **`81.0%`** | **`+8.0 pp` / `+5.0 pp`** |
| Same-H4 heading precision | `63.73%` | `34.28%` | **`57.51%`** | `-6.22 pp` / **`+23.23 pp`** |
| Exact HSN hits | `11 / 100` | `9 / 100` | `7 / 100` | `-4` / `-2` |
| False exact predictions | `2 / 100` | `1 / 100` | **`0 / 100`** | **`-2` / `-1` (0% false exact)** |
| Correct abstention rate | `98.0%` | `99.0%` | **`100.0%`** | **`+2.0 pp` / `+1.0 pp`** |
| Mean / Median / P95 retained | `22.39 / 15.0 / 78.4` | `70.08 / 60.5 / 154.05` | `43.77 / 32.0 / 121.75` | `-37.5%` mean vs P19 |
| Mean / P95 latency | `45,497.5 / 83,808.5 ms` | `20,827.8 / 29,451.4 ms` | `33,118.8 / 52,124.1 ms` | `-27.2%` vs P17 |

### Targeted Case Verification
- **5 Spare-Parts Cases**: All 5 recovered — `#44 (84099942)` rank `3`, `#51 (84139130)` rank `1`, `#53 (84149019)` rank `4`, `#62 (84199010)` rank `1`, `#63 (84219900)` rank `1`.
- **Case #73 (`85086000` vs `85091000`)**: `85086000` retained at rank `3`, mode=`MULTIPLE_CANDIDATES`, `final_hsn=None` (`0` false exact).

---

## 4. Remaining Limitations

1. **Case #59 (`"commercial espresso coffee brewing machine"` -> `84198120`)**: Still `recall=False` (`ret=0`) because `84198120`'s dense embedding/Cross-Encoder context prioritizes `"MACHINERY, PLANT OR LABORATORY EQUIPMENT..."` while `"FOR MAKING HOT DRINKS"` is only in `subheading_6digit_desc`.
2. **Remaining 10 Misses (`90%` -> `100%`)**: Mostly generic `"OTHER"` leaves in telecom/power electronics (`85044090`, `85176250`, `85252011`, `85252091`) and `"OTHER"` textile/bedding (`61143020`, `94049099`) where Cross-Encoder logits are strongly negative.
3. **CPU Inference Latency (`33.1 s` mean)**: Varied with CPU load across the 18,600 uncached Cross-Encoder pairs (`0` pair-cache hits on 100 distinct queries).

