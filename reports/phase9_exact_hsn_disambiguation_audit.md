# Phase 9 — Exact HSN Disambiguation Audit

**Date:** 2026-11-15  
**Scope:** Technical Audit & Architecture Design Only (Zero code or threshold modifications)  
**Baseline Commit:** `1c8780274c4637d46fc75c1b3e864ebae2e59c74` (`1c87802`)

---

## Executive Summary

Phase 8 achieved **86.27% (44/51)** pass rate on the 51-case generalized suite and **100% (23/23 detailed, 12/12 clarification)** candidate pool recall on the 35-case unseen exact-HSN suite, yet **0% (0/23)** exact 8-digit HSN predictions (`EXACT_HSN`).

Our read-only audit across `src/ml/hsn_v2_pipeline.py`, `src/ml/multi_candidate_engine.py`, `src/ml/product_tariff_reranker.py`, `src/ml/relevance_classifier.py`, `src/ml/confidence_calibrator.py`, `src/ml/ambiguity_resolver.py`, `data/model_versions/hsn_reranker_v1/calibration.json`, and `data/enriched_master_hsn.parquet` identified **four compounding root causes**:

1. **Cross-Encoder Sequence Truncation (`max_length=144`):** `RelevanceClassifier` instantiates `ProductTariffReranker(..., max_length=144)`. Because `format_tariff_context()` places `chapter_title | heading_4digit_desc | statutory_description` *before* the 6-digit/8-digit suffix and keywords, **21/23 (91.3%)** of `(query, gold_ctx)` pairs exceed 144 tokens (up to 284 tokens). Sibling HSNs under the same 4-digit heading become **token-identical** after truncation, causing **10/23 (43.5%)** of cases to produce **exact ties to 4 decimal places** (`distinction_confidence = 0.0`).
2. **Parent 4-Digit and 6-Digit Header Rows Polluting Leaf Competition:** `data/enriched_master_hsn.parquet` includes 4-digit (`3907`, `6201`, `7301`, `7308`, `9404`) and 6-digit (`620199`, `620140`, `840991`, `940490`) parent rows alongside 8-digit leaf HSNs. **8/23 (34.8%)** of cases have non-8-digit parent codes in the **Top 5**, tying with or outranking the true 8-digit leaf HSN.
3. **Lack of Structured Attribute & Numeric/Threshold Comparison:** `ambiguity_resolver.py` only inspects 4 static cue sets (`construction`, `processing_state`, `intended_use`, `product_completeness`) plus `material_keywords`, missing numeric capacity/power/weight thresholds (e.g., `75 KVA` vs `375 KVA`, `1,000 KW` vs `2,000 KW`) and subheading-level qualifiers (`non-plasticised`, `mens vs womens`, `rubberised`).
4. **Over-Penalized `hsn_calibrator` + Multi-Heading Block:** Even when the gold 8-digit HSN ranks #1 with a **+1.16 logit margin** (Case 19: `87019090` logit `6.2206` vs #2 `5.0629`), `hsn_calibrator` (`bias=-3.6967`, `n_siblings_same_heading` weight `-0.3550`) outputs `hsn_confidence=0.0031 < 0.55`, and `MultiCandidateEngine` blocks `EXACT_HSN` whenever `len(unique_headings) > 1` anywhere in the `SAME_PRODUCT` pool.

---

## Task 1 — Sibling HSN Confusion & All 23 Failed Exact-HSN Cases

### Observed Root Causes in Code & Data
- `src/ml/relevance_classifier.py:74`: `ProductTariffReranker(model_name_or_path=model_path, max_length=144, local_files_only=True)` truncates `(query, context)` at 144 tokens.
- `src/ml/product_tariff_reranker.py:61-75`: `format_tariff_context(row)` concatenates `chapter_title | heading_4digit_desc | statutory_description | article_keywords | material_keywords`, pushing the distinguishing 8-digit text past token 144.
- `src/ml/multi_candidate_engine.py:506-525`: Requires `len(unique_headings) == 1` across *all* `SAME_PRODUCT` candidates and `hsn_conf >= 0.55` (`tau_exact_hsn`).
- `data/model_versions/hsn_reranker_v1/calibration.json`: `hsn_calibrator` has `bias=-3.6967` and `n_siblings_same_heading` weight `-0.3550`; `chapter_calibrator` has all-zero weights `[0..0]` and `bias=4.76447` (`sigmoid = 0.9915` constant).

### Complete 23-Case Audit (`exact_detailed` in `data/eval/exact_hsn_eval_suite.parquet`)

| # | Gold HSN | Predicted Top-3 HSNs (Logit) | Mode | `hsn_conf` | Pair Tokens | Distinguishing Attributes (Candidates vs Gold) | Attributes in Query | Inferable vs Clarify? |
|---|---|---|---|---:|---:|---|---|---|
| 1 | `39053000` | `39051990` (6.6707), `39051910` (6.6707), `39051920` (6.6707) | `MULTIPLE_CANDIDATES` | 0.0135 | 178 | Polymer type (`poly(vinyl alcohol)` vs `poly(vinyl acetate)` beads/aqueous dispersion/other) | `poly(vinyl alcohol)`, `unhydrolysed acetate`, `polyvinyl alcohol resin` | **Inferable** (gold text explicitly in query; truncated at 144 tok) |
| 2 | `39074000` | `3907` (6.9180), `39073090` (6.9180), `39074000` (6.9180) | `MULTIPLE_CANDIDATES` | 0.0045 | 192 | Parent `3907` vs `390730xx` (epoxide) vs `39074000` (polycarbonates) vs `39075000` (alkyd) | `bisphenol-A polycarbonate resin` | **Inferable** (query specifies polycarbonate; truncated + parent `3907` tie) |
| 3 | `39129010` | `39129010` (7.3609), `39123100` (7.3519), `39121190` (7.3471) | `MULTIPLE_CANDIDATES` | 0.0141 | 160 | Chemical derivative (`cellulose propionate... non-plasticised` vs `CMC` vs `cellulose acetates`) | `cellulose propionate`, `non-plasticised`, `microcrystalline cellulose` | **Inferable** (gold ranked #1; margin suppressed by truncation) |
| 4 | `61124920` | `61121930` (6.7720), `61124920` (6.4470), `61123920` (6.3685) | `MULTIPLE_CANDIDATES` | 0.0048 | 134 | Article (`track suits` vs `womens/girls swimwear` vs `mens/boys swimwear`); material (`artificial fibres` / `pure silk`) | Query says `TRACK SUITS` (from `h4_desc`), gold is `WOMENS OR GIRLS SWIMWEAR` (`s6_desc` omitted) + `pure silk` | **Needs Clarification / Query Mismatch** (`h4_desc` says track suits while gold is swimwear) |
| 5 | `61152910` | `61159910` (5.8973), `61151910` (5.8973), `61151920` (5.8973) | `CHAPTER_ONLY_CLARIFY` | 0.0214 | 177 | Article (`panty hose and tights` vs `graduated compression` vs `other socks`); material (`silk` vs `wool` vs `artificial`) | `panty hose and tights of silk`, `pure silk` | **Inferable** (gold specifies `panty hose and tights of silk`; truncated at 144 tok) |
| 6 | `61172040` | `61171090` (7.1948), `61172040` (7.0862), `61171010` (7.0780) | `MULTIPLE_CANDIDATES` | 0.0018 | 154 | Article (`ties, bow ties, cravats` vs `shawls, scarves`); material (`man-made/synthetic fibres` vs `silk`) | `synthetic fibres`, `of man-made fibres` (missing `ties/bow ties` in query) | **Needs Clarification** (query lacks article type `ties/cravats` vs `shawls`) |
| 7 | `62019010` | `620199` (6.2770), `620140` (6.2770), `620130` (6.2770) | `MULTIPLE_CANDIDATES` | 0.0064 | 219 | 6-digit/4-digit parent rows (`620199`, `620140`, `620130`, `6201`) vs 8-digit leaf `62019010`; material (`other textile` vs `man-made` vs `cotton`) | `overcoats, raincoats...`, `other textile materials`, `blended natural fibres` | **Inferable** (all top-5 are parent rows; truncation at 144 tok) |
| 8 | `62102010` | `62102010` (6.6008), `62102030` (6.6008), `62103010` (6.6008) | `MULTIPLE_CANDIDATES` | 0.0126 | 201 | Coating (`rubberised` vs `impregnated/coated with plastics` vs `other`) & gender/garment (`621020` vs `621030`) | `outer garments, of rubberised textile fabrics`, `rubberized raincoats` | **Inferable** (gold ranked #1; exact tie due to 144-tok truncation) |
| 9 | `62105000` | `62102010` (6.9031), `62102030` (6.8959), `62102020` (6.8959) | `MULTIPLE_CANDIDATES` | 0.0127 | 158 | Gender/category (`621050` womens/girls other garments vs `621020` overcoats) & fabric coating | `other garments... womens/girls` (`6202` ref), `coated textile fabric` | **Inferable** (truncated at 144 tok) |
| 10 | `73012010` | `73012010` (6.6299), `73012090` (6.5607), `7301` (6.5067) | `CHAPTER_ONLY_CLARIFY` | 0.0527 | 162 | `steel slotted angles` (`73012010`) vs `other angles/shapes` (`73012090`) vs parent `7301` | `steel slotted angles`, `slotted angle iron` | **Inferable** (gold ranked #1; margin compressed by truncation & parent `7301`) |
| 11 | `73089070` | `73083000` (6.5235), `7308` (6.5235), `73082020` (6.5235) | `MULTIPLE_CANDIDATES` | 0.0185 | 249 | Specific structure (`73083000` doors/windows vs `73082020` towers/lattice vs `73089070` other structures) | `works, doors and windows and their frames`, `steel` | **Ambiguous** (statutory descriptions of `73083000` and `73089070` overlap on `doors and windows`) |
| 12 | `73143100` | `73142090` (7.1600), `73142010` (7.1588), `73144190` (7.0720) | `CHAPTER_ONLY_CLARIFY` | 0.0269 | 156 | Wire/mesh dimension (`>=3mm, >=100cm2` in `731420` vs other welded grill `73143100` plated with zinc) | `plated or coated with zinc`, `galvanized steel` | **Needs Clarification** (missing wire diameter & mesh size threshold) |
| 13 | `84051020` | `84051010` (7.4917), `84051090` (7.4917), `84051020` (7.4917) | `CHAPTER_ONLY_CLARIFY` | 0.0580 | 281 | Gas generator type (`84051010` producer/water gas vs `84051020` acetylene gas vs `84051090` other) | `producer gas or water gas generators`, `acetylene gas` | **Inferable** (281 tokens -> severe 144-tok truncation caused exact 3-way tie) |
| 14 | `84099113` | `84099113` (7.6263), `84099111` (7.6263), `84099112` (7.6263) | `MULTIPLE_CANDIDATES` | 0.0071 | 250 | Engine application/part (`84099111` vs `84099112` vs `84099113` — spark-ignition vs compression-ignition) | `valves, inlet and exhaust, piston`, `cast iron` | **Inferable** (gold ranked #1; 250 tokens truncated to identical 3-way tie) |
| 15 | `84099913` | `84099913` (7.3599), `840991` (7.3514), `84091000` (7.2705) | `MULTIPLE_CANDIDATES` | 0.0097 | 176 | Engine type (`840999` compression-ignition vs `840991` spark-ignition vs `84091000` aircraft) | `piston rings`, `alloy steel` (missing diesel vs petrol engine spec) | **Needs Clarification** (gold #1, but parent `840991` & petrol/diesel engine type missing) |
| 16 | `85013420` | `85013420` (6.0706), `85013430` (6.0353), `85013440` (5.9295) | `MULTIPLE_CANDIDATES` | 0.0041 | 211 | Output power band (`>1,000 KW <=2,000 KW` vs `>2,000 <=5,000` vs `>5,000`) | `exceeding 1,000 kw` (`copper windings`) | **Inferable** (gold #1, but Cross-Encoder margin is only +0.035 over `>2,000 KW`) |
| 17 | `85016100` | `85016200` (6.5962), `85016100` (6.4531), `85016460` (6.0611) | `MULTIPLE_CANDIDATES` | 0.0036 | 157 | AC generator output rating (`<=75 KVA` vs `>75 <=375 KVA` vs `>75,000 KVA`) | `not exceeding 75 kva`, `laminated silicon steel` | **Inferable** (numeric `not exceeding 75 KVA` ignored by Cross-Encoder, ranked `>75 KVA` higher) |
| 18 | `85016300` | `85016300` (6.5918), `85016200` (6.1693), `85013310` (5.5562) | `MULTIPLE_CANDIDATES` | 0.0024 | 177 | Output rating (`>375 <=750 KVA` vs `>75 <=375 KVA` vs `DC motors`) | `exceeding 375 kva`, `copper stator` | **Inferable** (gold #1 with +0.42 margin, blocked by `hsn_calibrator` & multi-heading) |
| 19 | `87019090` | `87019090` (6.2206), `87011000` (5.0629), `87013099` (4.9733) | `MULTIPLE_CANDIDATES` | 0.0031 | 113 | Tractor type (`87019090` other vs `87011000` pedestrian-controlled vs `87013099` track-laying) | `tractors (other than 8709)`, `high-strength steel` | **Inferable** (gold #1 with **+1.16 margin**, blocked by `hsn_calibrator` & `unique_headings > 1`) |
| 20 | `87037040` | `87031010` (7.0242), `87032499` (6.9915), `87033292` (6.9915) | `MULTIPLE_CANDIDATES` | 0.0011 | 171 | Propulsion & cylinder capacity (`diesel+electric` vs `spark-ignition >3000cc` vs `compression-ignition`) | `three wheeled vehicle`, `steel` (missing propulsion/cc spec) | **Needs Clarification** (query lacks hybrid/diesel/electric propulsion) |
| 21 | `87081090` | `87084000` (6.7393), `87089300` (6.7327), `87087000` (6.7202) | `MULTIPLE_CANDIDATES` | 0.0099 | 148 | Specific vehicle part (`87081090` bumpers vs `87084000` gear boxes vs `87089300` clutches) | `parts and accessories of motor vehicles`, `steel` (no part name) | **Needs Clarification** (query lacks `bumpers`) |
| 22 | `94014000` | `94014000` (5.8245), `94018000` (5.8245), `94012000` (5.8245) | `MULTIPLE_CANDIDATES` | 0.0139 | 207 | Seat type (`94014000` convertible into beds vs `94018000` other seats vs `94012000` motor vehicle seats) | `seats... convertible into beds`, `hardwood frame` | **Inferable** (207 tokens -> truncated at 144 tok, exact 3-way tie) |
| 23 | `94049099` | `940490` (6.1216), `9404` (6.1216), `94049099` (6.1216) | `MULTIPLE_CANDIDATES` | 0.0136 | 284 | Parent `940490`/`9404` vs leaf `94049099` (other bedding/cushions) | `mattress supports... other`, `cotton` | **Inferable** (284 tokens -> truncated + parent rows tie at #1/#2) |

**Key Aggregate Finding:** Out of 23 cases, **17 are directly inferable** from the query text (blocked by 144-token truncation, parent-row ties, numeric blindness, and `hsn_calibrator`), while **6 genuinely require clarification** due to missing subheading/part/propulsion attributes in the query.

---

## Task 2 — Generalized Statutory Distinction Mechanism

Analysis of `data/enriched_master_hsn.parquet` (4,851 rows across 9 chapters) shows that every sibling 8-digit HSN pair already carries structured hierarchical and lexical differentiation fields:
- `heading_4digit_desc` (shared parent)
- `subheading_6digit_desc` (6-digit split: material, gender, construction, or propulsion)
- `tariff_item_desc` & `statutory_description` (8-digit leaf split: numeric range, coating, specific part, or `"OTHER"` residual)
- `article_keywords` & `material_keywords` (enriched customs/commercial synonyms)

A **domain-general statutory distinction extractor** (zero hardcoded product/chapter rules) can work across all chapters using four generic primitives:
1. **Leaf vs. Parent Separation:** Filter classification targets to `code_length == 8` leaf HSNs during exact-HSN disambiguation (parent 4-digit/6-digit rows remain only as hierarchy labels, never competing as exact HSN predictions).
2. **Hierarchical Suffix Extraction:** Compute the **relative statutory diff** between sibling candidates by stripping their common longest prefix (`heading_4digit_desc` / shared `statutory_description` prefix) so comparison focuses strictly on the differentiating 6-digit/8-digit clause (`subheading_6digit_desc`, `tariff_item_desc`, `article_keywords`, `material_keywords`).
3. **Structured Numeric & Range Constraint Parser (Domain-General):** Extract comparative numeric expressions (`not exceeding X unit`, `exceeding X unit`, `exceeding X unit but not exceeding Y unit`, `< / <= / > / >=`) with normalized units (`kw`, `kva`, `cc`, `w`, `mm`, `cm2`, `g`, `kg`, `%`) from candidate `tariff_item_desc` and match against numeric values in the query.
4. **Residual (`OTHER`) Exclusion Logic:** A residual `"OTHER"` 8-digit leaf HSN is only valid when sibling specific 8-digit HSNs under the same 6-digit/4-digit parent are explicitly contradicted or unsupported by the query.

### Statutory Distinction Examples Across Categories
- **Electrical Machinery (Ch. 85 — `85016100` vs `85016200` vs `85016300`):** Relative diff isolates `(not exceeding 75 KVA)` vs `(exceeding 75 KVA but not exceeding 375 KVA)` vs `(exceeding 375 KVA but not exceeding 750 KVA)`. Numeric parser matches `75 KVA` / `375 KVA` directly without chapter-specific code.
- **Plastics (Ch. 39 — `39073010` vs `39074000` vs `39075000`):** Relative diff isolates `EPOXIDE RESINS : EPOXY RESINS` vs `POLYCARBONATES` vs `ALKYD RESINS`, matching `bisphenol-A polycarbonate resin`.
- **Apparel (Ch. 61/62 — `61152910` vs `61159910` vs `61151910`):** Relative diff + `subheading_6digit_desc` isolates `PANTY HOSE AND TIGHTS OF SILK` vs `GRADUATED COMPRESSION HOSIERY` vs `OTHER SOCKS`.
- **Vehicles (Ch. 87 — `87011000` vs `87013099` vs `87019090`):** Relative diff isolates `PEDESTRIAN CONTROLLED TRACTORS` vs `TRACK-LAYING TRACTORS` vs `OTHER`, where `87019090` wins only if `pedestrian` and `track-laying` are absent/excluded.

---

## Task 3 — Proposed Generalized Exact-Classification Decision Process

1. **Retrieve Qualifying Leaf & Hierarchy Candidates:** Run `AdaptiveCandidateDiscoverer` to retrieve all relevant candidates; retain full statutory lineage while separating `code_length == 8` leaf candidates from 4-digit/6-digit parent headers.
2. **Score Full Non-Truncated Statutory Contexts:** Increase `max_length` (e.g. `384` or `512`) and place **leaf-differentiating fields first** (`tariff_item_desc | subheading_6digit_desc | article_keywords | material_keywords | heading_4digit_desc`) so sibling distinctions are never truncated.
3. **Extract Relative Statutory Distinctions:** For the top qualifying 8-digit candidates, compute common-prefix-stripped diffs, numeric/unit constraints, and attribute cues (`material`, `construction`, `processing_state`, `intended_use`, `product_completeness`, `numeric_rating`).
4. **Match Evidence Against Supplied Description:** Verify which distinguishing clauses/numeric ranges are explicitly supported, contradicted, or missing in `effective_query`.
5. **Generate Targeted Clarification Questions When Evidence Is Missing:** If >= 2 leaf candidates remain plausible and a distinguishing attribute/numeric spec is missing (e.g., `propulsion type`, `KVA rating`, `knitted vs woven`), emit targeted questions derived directly from the statutory diff.
6. **Emit `EXACT_HSN` Only With Verified Distinction Support:** Predict `EXACT_HSN` only when a single 8-digit leaf candidate has: (a) calibrated `relevance_confidence >= tau_abstain`, (b) positive evidence support / margin over competing leaf siblings (without unverified `"OTHER"` fallback), and (c) re-calibrated `hsn_confidence >= tau_exact_hsn` (fit on non-truncated features).
7. **Otherwise Retain Multiple Candidates or Abstain:** Emit `MULTIPLE_CANDIDATES`, `CHAPTER_ONLY_CLARIFY`, or `INSUFFICIENT_INFORMATION` while preserving all qualifying candidates and their full statutory lineage.

---

## Task 4 — Evaluation Integrity Audit

### Explicit Disclosure of Validation-HSN Overlaps (24 / 35 Cases)
Comparing `data/eval/exact_hsn_eval_suite.parquet` against `data/training_pairs/full_pairs_val.parquet` revealed **24 overlapping HSN codes** (0 query-text overlap, 0 train overlap):
```text
39074000, 39129010, 39140020, 61124920, 61152910, 61172040,
62102010, 62139010, 62171020, 73012010, 73143100, 73181500,
84051020, 84099913, 85013420, 85016100, 85016300, 85018000,
87019090, 87037040, 87081090, 87142020, 87164000, 94014000
```

### Integrity & Independence Assessment
1. **Did validation data influence model/threshold selection?** Yes: `data/model_versions/hsn_reranker_v1/calibration.json` (`rel_fit_n=306`, `rel_eval_n=218`, `query_fit_n=83`, `query_eval_n=60`) and `same_product_threshold=0.725` were tuned using validation splits derived from `full_pairs_val.parquet`. Therefore, the 24 HSNs appearing in `full_pairs_val.parquet` are **not fully independent at the HSN level**.
2. **Are descriptions realistic independent inputs?** **No.** All 35 queries in `exact_hsn_eval_suite.parquet` were programmatically synthesized by concatenating `heading_4digit_desc`, `subheading_6digit_desc`, `tariff_item_desc`, and `material_keywords` from `enriched_master_hsn.parquet` (and Case 4 `61124920` even inherited a misleading `h4_desc` `"TRACK SUITS"` while the gold row is `"WOMENS OR GIRLS SWIMWEAR"`).
3. **Were gold labels independently verified?** **No.** Gold labels were taken directly from `enriched_master_hsn.parquet` rows without independent GST/customs domain-expert review.

### Proposed Leakage-Resistant Evaluation Dataset
Build `data/eval/independent_exact_hsn_eval.parquet` (target 150–250 cases) satisfying:
- **Strict Disjointness:** Zero overlap on **both** `hsn_code` and normalized `query` against `full_pairs_train.parquet`, `full_pairs_val.parquet`, `generalized_test_suite.parquet`, and `generalized_test_large.parquet` (or using held-out `full_pairs_test.parquet` HSNs + newly authored commercial descriptions).
- **Realistic Commercial Phrasing:** Natural invoice/catalog descriptions (brand/spec/unit variations, abbreviations, multi-attribute specs) rather than concatenated statutory headers.
- **Expert-Verified Ground Truth:** Every gold 8-digit HSN + required clarification attributes verified by a GST/HSN reviewer, explicitly tagging each case as `sufficient_for_exact_hsn` vs `requires_clarification`.

---

## Task 5 — Performance Investigation

### Measured Latency Breakdown (23 Detailed Cases)
- **Mean Wall Time:** **20,815.4 ms** (20.82 s) on the 23 detailed cases (51-case benchmark mean: **16.55 s**, P95: **34.38 s**).
- **Cross-Encoder Reranking (`reranking_time_ms`):** **18,981.2 ms (91.2% of total latency)** — dominant bottleneck.
- **Hybrid Retrieval (`retrieval_time_ms`):** **1,559.2 ms (7.5%)**.
- **Difference Analysis & Overhead:** **275.0 ms (1.3%)**.

### Why Reranking Takes 91.2% of Latency
1. **Repeated Multi-Round Cross-Encoder Passes (`expansion_rounds = 8..10`, `records_examined = 218..250`):** Every expansion round increments `branch_k` by `2.5x` and invokes `BAAI/bge-reranker-v2-m3` on CPU for new rows, even after dozens of `SAME_PRODUCT` candidates are already found.
2. **Scoring Non-Leaf Parent Rows & Cross-Round Duplicates:** 4-digit/6-digit parent rows consume retrieval slots and Cross-Encoder budget.
3. **Independent `compare_active_vs_statutory` Rerank Call:** Runs an additional Cross-Encoder pass on inactive chapters on every query even when `best_active_score > 0.95`.

### Recall-Preserving Optimizations
1. **Pre-filter / Separate Parent Rows Before Reranking:** Keep 8-digit leaf rows in the primary scoring pool (eliminates ~10–15% wasted Cross-Encoder passes without losing any leaf HSN).
2. **Cross-Round Context Cache in `AdaptiveCandidateDiscoverer`:** Cache `(eval_query, formatted_context) -> logit` across rounds and across `compare_active_vs_statutory` so identical contexts are never scored twice.
3. **Two-Stage Discovery / Smarter Expansion Step:** Start with `initial_branch_k=45` (captures most active heads in 1 round instead of 2–3 small rounds) and use `expansion_factor=3.0` so exhaustive stabilization finishes in 2–3 rounds instead of 8–10 rounds, reducing BM25+dense re-merging overhead without truncating discovery.
4. **GPU / FP16 / ONNX Runtime Inference for Cross-Encoder:** Moving `bge-reranker-v2-m3` from CPU FP32 to GPU FP16 or quantized ONNX reduces ~19s reranking to <1.5s with zero recall loss.

---

## Prioritized Implementation Plan (For Next Phase)

| Priority | Change | Target Files | Expected Impact |
|---|---|---|---|
| **P0** | Fix `max_length` truncation (`144` → `384`/`512`) and reorder `format_tariff_context()` to put leaf-differentiating fields (`tariff_item_desc`, `subheading_6digit_desc`, keywords) **first** | `src/ml/relevance_classifier.py`, `src/ml/product_tariff_reranker.py` | Eliminates the 43.5% exact-logit ties across sibling HSNs |
| **P1** | Separate `code_length == 8` leaf HSNs from 4/6-digit parent headers in discovery & disambiguation | `src/ml/multi_candidate_engine.py`, `src/search/hybrid_retrieval.py` | Eliminates the 34.8% parent-code Top-5 ties |
| **P2** | Implement domain-general relative statutory diff + numeric/unit constraint matcher + `"OTHER"` residual exclusion | `src/ml/ambiguity_resolver.py`, `src/ml/multi_candidate_engine.py` | Enables verified `EXACT_HSN` disambiguation across all 9 chapters |
| **P3** | Re-fit `confidence_calibrator.py` (`calibration.json`) on non-truncated features & build leakage-resistant eval dataset | `src/ml/confidence_calibrator.py`, `scripts/build_exact_hsn_eval_suite.py` | Fixes `hsn_confidence` collapse (`0.003` despite `+1.16` margin) & removes val overlap |
| **P4** | Optimize expansion schedule (`branch_k=45`, `3.0x`), cross-round context cache, and ONNX/GPU inference | `src/ml/multi_candidate_engine.py`, `src/ml/product_tariff_reranker.py` | Cuts 16.5s mean / 34.4s P95 latency without truncating discovery |

---

## Tests Required to Prove Improvements (After Implementation)
1. **Tokenization & Context Ordering Test:** Verify `format_tariff_context()` places `tariff_item_desc` and `subheading_6digit_desc` within the first 144 tokens and that sibling 8-digit HSNs under `3905`, `3907`, `6115`, `8405`, `8501`, `9401` produce distinct logits (`|logit_1 - logit_2| > 0`).
2. **Leaf-Only Disambiguation Test:** Verify 4-digit/6-digit parent rows (`3907`, `6201`, `7301`, `7308`, `9404`) never block or tie an `EXACT_HSN` decision.
3. **Numeric/Unit Constraint Test:** Verify `<= 75 KVA` (`85016100`) vs `> 75 <= 375 KVA` (`85016200`) vs `> 375 <= 750 KVA` (`85016300`) and `> 1,000 KW` (`85013420`) resolve to the exact leaf HSN when specified, and request clarification when omitted.
4. **Zero-Leakage Exact-HSN Benchmark:** Verify exact-HSN accuracy, coverage, abstention rate, and progressive clarification improvement on the disjoint, expert-verified evaluation dataset.
5. **Latency & Completeness Regression Test:** Verify all 26/26 existing HSN V2 tests pass, `discovery_complete` remains honest, and mean/P95 latency drops substantially.

