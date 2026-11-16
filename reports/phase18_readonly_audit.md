# Phase 18 — Read-Only Candidate Discovery & Ranking Audit

**Baseline Preserved**: Phase 17 commit `ce2a752` (read-only audit; zero source files modified)  
**Benchmark Data**: [phase17_independent_100.json](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/reports/phase17_independent_100.json) (`100` cases, `0` HSN overlap, `0` query overlap with `train`/`val`)

---

## 1. Executive Summary

Across the 100-case zero-leakage independent benchmark (`ce2a752`):
- **Chapter Accuracy**: **`90.0%`** (`90/100`; 8 of the 10 chapter misses occurred when `0` candidates were retained)
- **Candidate Recall**: **`77.0%`** (`77/100`; `23` missed cases)
- **Recall@K**: **@1 `32.0%`**, **@3 `49.0%`**, **@5 `59.0%`**, **@10 `67.0%`**, **@20 `73.0%`**
- **Exact HSN Hits**: **`11/100` (`11.0%`)** | **False Exact**: **`2/100` (`2.0%`)** | **Correct Abstention**: **`98.0%`**
- **Retained Pool Size**: mean **`22.39`**, median **`15.0`**, P95 **`78.4`** (`63.7%` same-4-digit heading siblings)
- **Latency (4-thread CPU)**: mean **`45,497.5 ms`**, P95 **`83,808.5 ms`** (`18,296` unique uncached pairs)

Four primary root causes explain nearly all gaps:
1. **Cross-Encoder `UNRELATED` False Rejections (`17/23` misses)**: All 17 were retrieved in top-250 (`in_raw_250=True`), but the Cross-Encoder scored unseen 8-digit leaves (especially `"OTHER"` leaves, technical synonyms like `"walkie talkie"` / `"ethernet router"`, and the master typo `"VACCUM CLEANERS"`) as `UNRELATED` (`logit -1.52 to -5.90`).
2. **False `CONTRADICTED` from Synthetic `material_keywords` (`3/23` misses)**: `build_candidate_profile` treats non-exhaustive synthetic `material_keywords` as exclusive material requirements (`#82`, `#98`, `#99`).
3. **Hybrid Retrieval Omissions (`2/23` misses)**: Generic statutory text without trade synonyms (`#58` tray dryer, `#59` espresso coffee machine) missed hybrid top-250.
4. **CPU Cross-Encoder Throughput (`98.5%` of latency)**: Tokenization is only `50.0 ms` per 128 pairs, while FP32 CPU forward pass takes `41,076.2 ms` at `batch_size=32` (`34,952.5 ms` at `batch_size=64`, `-14.9%`).

---

## 2. Missing Candidate Case-by-Case Analysis (23 / 100 Cases)

| # | Gold HSN | Ret | In Raw-250 | CE Relation (Logit) | Evidence if Same | Root Cause Category |
|---:|---|---:|:---:|---|---|---|
| 8 | `39159079` | 8 | Yes | `UNRELATED` (`-1.75`) | `POSSIBLY_SUPPORTED` | **CE False Rejection** (residual `"OTHERS"` scrap) |
| 9 | `39172990` | 7 | Yes | `UNRELATED` (`-1.52`) | `POSSIBLY_SUPPORTED` | **CE False Rejection** (`"OTHER"` polymer pipe) |
| 16 | `39219099` | 111 | Yes | `UNRELATED` (`-3.00`) | `SUPPORTED` | **CE False Rejection** (`OTHER : OTHER : OTHER`) |
| 23 | `61143020` | 25 | Yes | `INSUFFICIENT_INFO` (`-0.14`) | `SUPPORTED` | **Expansion / Filter Cutoff** (`INSUFFICIENT_INFO` dropped when `SUPPORTED` exists) |
| 27 | `62019010` | 9 | Yes | `UNRELATED` (`-1.63`) | `POSSIBLY_SUPPORTED` | **CE False Rejection** (`trench coat` vs `OVERCOATS...`) |
| 30 | `62044990` | 16 | Yes | `UNRELATED` (`-1.98`) | `POSSIBLY_SUPPORTED` | **CE False Rejection** (`OTHER` silk dress) |
| 31 | `62044999` | 10 | Yes | `UNRELATED` (`-1.67`) | `SUPPORTED` | **CE False Rejection** (`OTHER` ramie dress) |
| 57 | `84191910` | 31 | Yes | `UNRELATED` (`-4.31`) | `POSSIBLY_SUPPORTED` | **CE False Rejection** (`solar thermal water heater`) |
| 58 | `84193900` | 1 | **No** | — | `INSUFFICIENT_EVIDENCE` | **Retrieval Miss** (`industrial tray dryer` not in generic `84193900` text) |
| 59 | `84198120` | 0 | **No** | — | `INSUFFICIENT_EVIDENCE` | **Retrieval Miss** (`espresso coffee brewing` not in generic `84198120` text) |
| 61 | `84198970` | 0 | Yes | `UNRELATED` (`-5.12`) | `POSSIBLY_SUPPORTED` | **CE False Rejection** (`autoclave sterilizer`) |
| 66 | `84323900` | 29 | Yes | `UNRELATED` (`-1.65`) | `POSSIBLY_SUPPORTED` | **CE False Rejection** (`seed drill planter` vs `OTHER`) |
| 72 | `85044090` | 0 | Yes | `UNRELATED` (`-5.86`) | `INSUFFICIENT_EVIDENCE` | **CE False Rejection** (`dc power supply inverter`) |
| 73 | `85086000` | 3 | Yes | `UNRELATED` (`-2.13`) | `POSSIBLY_SUPPORTED` | **CE False Rejection + Master Typo** (`OTHER VACCUM CLEANERS`) |
| 79 | `85176250` | 0 | Yes | `UNRELATED` (`-4.19`) | `INSUFFICIENT_EVIDENCE` | **CE False Rejection** (`optical fibre multiplexer`) |
| 80 | `85176270` | 0 | Yes | `UNRELATED` (`-3.23`) | `POSSIBLY_SUPPORTED` | **CE False Rejection** (`ethernet router` vs `TELEPHONE SETS`) |
| 82 | `85182290` | 0 | Yes | `RELATED_PRODUCT` (`-0.68`) | `CONTRADICTED` | **False `CONTRADICTED`** (synthetic `material_keywords`: `copper_brass, plastics` vs `wood`) |
| 85 | `85232920` | 3 | Yes | `UNRELATED` (`-2.78`) | `POSSIBLY_SUPPORTED` | **CE False Rejection** (`blank magnetic stripe smart card`) |
| 88 | `85252011` | 0 | Yes | `UNRELATED` (`-5.06`) | `POSSIBLY_SUPPORTED` | **CE False Rejection** (`walkie talkie` vs `RADIOTELEPHONY`) |
| 89 | `85252091` | 0 | Yes | `UNRELATED` (`-5.90`) | `INSUFFICIENT_EVIDENCE` | **CE False Rejection** (`satellite earth station`) |
| 94 | `87032291` | 10 | Yes | `UNRELATED` (`-4.07`) | `POSSIBLY_SUPPORTED` | **CE False Rejection** (`sedan car 1200cc` vs `MOTOR CARS...`) |
| 98 | `94049099` | 8 | Yes | `INSUFFICIENT_INFO` (`+0.92`) | `CONTRADICTED` | **False `CONTRADICTED`** (synthetic `material_keywords`: `plastics, rubber, synthetic_textile` vs `cotton`) |
| 99 | `94051020` | 9 | Yes | `INSUFFICIENT_INFO` (`+0.57`) | `CONTRADICTED` | **False `CONTRADICTED`** (synthetic `material_keywords`: `plastics` vs `copper_brass`) |

---

## 3. Ranking Metrics & Failure Patterns

- **Recall@K**: `Recall@1 = 32.0%` (`32/100`), `Recall@3 = 49.0%` (`49/100`), `Recall@5 = 59.0%` (`59/100`), `Recall@10 = 67.0%` (`67/100`), `Recall@20 = 73.0%` (`73/100`), `Overall Recall = 77.0%` (`77/100`).
- **Chapter Accuracy**: `90.0%` (`90/100`). Outside the `8` zero-candidate cases (`ret=0`), only `2` cases missed top-1 chapter (`#41`: `84` vs `87` on motorcycle engine `150cc`; `#56`: `84` vs `85` on instantaneous gas water heater).
- **Primary Ranking Failure Patterns**:
  1. **Zero-candidate collapses (`8/100`)**: Cross-Encoder `UNRELATED` thresholding rejects all retrieved items on unseen technical terms (`#59, #61, #72, #79, #80, #88, #89`) or synthetic `material_keywords` contradictions (`#82`).
  2. **Residual `"OTHER"` / `"OTHERS"` demotion**: Generic `"OTHER"` 8-digit leaves under the correct 4/6-digit heading receive negative Cross-Encoder logits even when their parent heading matches (`#8, #9, #16, #30, #31, #66`).
  3. **Parent vs. Leaf Separation**: Parent headings (`parent_records_excluded_count`) are cleanly excluded from customer-facing lists when leaves exist; no parent leakage into top-K leaf ranks was observed.

---

## 4. False Exact Root-Cause Investigations (2 / 100 Cases)

1. **Case #4: `"vinyl acetate ethylene copolymer emulsion resin"` (`39013000` emitted vs `39059100` expected)**
   - **Trace**: `44` candidates retained (`15` `SUPPORTED`, `29` `POSSIBLY_SUPPORTED`, `8` parents excluded). `hsn_confidence = 0.6925`, `distinction_confidence = 0.0015` (virtually tied Cross-Encoder score!).
   - **Root Cause (Decision & Distinction Logic)**: `analyze_sibling_distinctions` saw `39013000` (`tariff_item_desc = "VINYL ACETATE COPOLYMERS"`, `t8_hit_ratio = 1.0`) vs `39059100` (`"COPOLYMERS"`) and set `winner_has_clear_evidence = True` (`margin = 0.1771 >= 0.15`), ignoring that `3901` (ethylene-predominant) vs `3905` (vinyl-acetate-predominant) are **two distinct 4-digit headings** both `SUPPORTED` (`distinction_confidence = 0.0015`) when monomer weight % is unstated!
2. **Case #73: `"electric canister vacuum cleaner for home"` (`85091000` emitted vs `85086000` expected)**
   - **Trace**: `3` candidates retained (`hsn_confidence = 0.6325`, `winner_has_clear_evidence = False`).
   - **Root Cause (Master Data Typo + CE Rejection)**: In `enriched_master_hsn.parquet`, `85086000` is spelled **`VACCUM CLEANERS - OTHER VACCUM CLEANERS`** (`VACCUM`). Because of that spelling error, the Cross-Encoder scored `85086000` `UNRELATED` (`logit = -2.13`) and dropped it, leaving legacy HS-2002 `85091000` (`CONTAINED ELECTRIC MOTOR VACUUM CLEANERS...`) as the sole `SAME_PRODUCT` leaf (`len(same_leaves) == 1`).

---

## 5. Candidate Noise Breakdown (2,239 Total Retained 8-Digit Candidates)

- **Same-4-digit heading siblings**: **`1,427` (`63.7%`)** — genuine statutory tariff siblings under the target heading (e.g. `3920` sheets/films: `77–111` items; `8525` transmitters: `130` items).
- **Different heading / cross-chapter**: **`812` (`36.3%`)** — concentrated in broad polymer/steel/apparel queries (`39219099`: `111`, `73061100`: `105`, `85251020`: `130`).
- **Material-only without article**: **`0`** (Phase 15–17 protection held at `0` across all 100 cases).

---

## 6. Performance Profiling (`ProductTariffReranker`)

Measured on `128` pairs (`cpu_count=8`, `torch_threads=4`, `CUDA=False`, `onnxruntime=False`):
- **Tokenization (`128` pairs, `max_length=512`)**: **`50.0 ms`** (`0.39 ms/pair`, ~`0.14%` of runtime)
- **Model Inference (`128` pairs)**:
  - `batch_size = 16`: `35,863.3 ms` (`280.2 ms/pair`)
  - `batch_size = 32` (current default): `41,076.2 ms` (`320.9 ms/pair`)
  - `batch_size = 64`: **`34,952.5 ms`** (`273.1 ms/pair` — **`14.9%` faster** than `32` with identical logits)
- **In-Memory Pair Cache (`128` pairs)**: **`0.364 ms`** (`~96,000x` speedup on hits; `0 / 18,296` hits during single-pass 100 distinct queries)
- **Memory (`tracemalloc`)**: `py_curr = 2,335.4 MB`, `py_peak = 2,431.9 MB`

---

## 7. Prioritized Implementation Recommendations (Phase 19)

1. **P1 (High Impact — Recall `+3%`, Zero Recall Loss): Restrict Material Contradictions to Statutory Descriptions**
   - In `build_candidate_profile`, compute `material_families` for contradiction checking ONLY from statutory fields (`heading_4digit_desc`, `subheading_6digit_desc`, `tariff_item_desc`, `statutory_description`), never from noisy synthetic `material_keywords`. Fixes `#82`, `#98`, `#99` immediately.
2. **P2 (High Impact — Recall `+8–14%`): Evidence-Backed Rescue of `UNRELATED` Candidates with Strong Statutory Article/Heading Match**
   - When `AdaptiveCandidateDiscoverer` finds `0` qualifying candidates (`ret=0`) OR when a retrieved leaf passes `SUPPORTED`/`POSSIBLY_SUPPORTED` statutory article+heading checks (`#8, #9, #16, #27, #30, #31, #61, #66, #73, #80, #85, #88, #94`) despite a negative Cross-Encoder logit on unseen `"OTHER"` / typo (`VACCUM`) records, rescue it as `INSUFFICIENT_INFORMATION` / `RELATED_PRODUCT` instead of silently dropping it.
3. **P3 (Medium-High Impact — False Exact Prevention): Block `EXACT_HSN` Across Competing `SUPPORTED` Headings (`#4`)**
   - In `MultiCandidateEngine` / `analyze_sibling_distinctions`, if `len(unique_headings) > 1` among `SAME_PRODUCT` leaves (`3901` vs `3905`) or `distinction_confidence < 0.02`, do NOT emit `EXACT_HSN` even when `winner_has_clear_evidence` is True; route to `MULTIPLE_CANDIDATES`.
4. **P4 (Medium Impact — Typo Normalization + Latency `-15%`)**:
   - Normalize known statutory OCR/master typos (`vaccum` -> `vacuum`) in query/context formatting, and change `ProductTariffReranker` default `batch_size` from `32` to `64` (`-14.9%` CPU inference time with zero score change).

---

## 8. Risks & Regression Tests Required

- **Risks**: Rescuing `UNRELATED` candidates too aggressively could re-introduce cross-chapter noise; gating rescue strictly on positive statutory `article_matches` + `heading_compatible` (or `ret=0` fallback) prevents noise explosion.
- **Required Regression Tests**:
  1. `material_keywords`-only mismatch (`#82`, `#98`, `#99`) must NOT trigger `CONTRADICTED` when `statutory_description` is material-neutral (`OTHER`).
  2. Multi-heading `SUPPORTED` tie (`39013000` vs `39059100` on `"vinyl acetate ethylene copolymer emulsion resin"`) must route to `MULTIPLE_CANDIDATES`, not `EXACT_HSN`.
  3. `"electric canister vacuum cleaner for home"` must retain `85086000` despite `"VACCUM"` in statutory text.
  4. All existing `36` HSN regression tests + `100`-case zero-leakage benchmark must pass with improved recall and `0` false-exact errors.

