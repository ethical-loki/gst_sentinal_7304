# Phase 14.1 — Candidate Quality Diagnostic Audit

**Scope & Constraint**: Read-only diagnostic audit of Phase 14 (commit `2924cf7`) across all 24 evaluation cases (`12` from `data/eval/independent_exact_hsn_eval.parquet` + `12` from `synthetic_9ch` covering all 9 active chapters: `19, 39, 61, 62, 73, 84, 85, 87, 94`). No production code, thresholds, calibration, or candidate filtering were modified.

**Machine-Readable Report**: [phase14_1_candidate_quality_audit.json](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/reports/phase14_1_candidate_quality_audit.json)  
**Audit Script**: [audit_phase14_candidate_quality.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/scripts/audit_phase14_candidate_quality.py)

---

## 1. Executive Summary & Usability Metrics (n = 24)

| Metric | Value | Notes |
|---|---:|---|
| Mean retained distinct 8-digit HSNs | **32.62** | Skewed by statutory-style multi-article queries (`62043991`: 177, `39206210`: 145) |
| Median retained distinct 8-digit HSNs | **21.0** | Typical query retains ~21 leaf candidates |
| P95 retained distinct 8-digit HSNs | **132.25** | Driven by long multi-clause statutory strings |
| Cases with `> 5` candidates | **20 / 24** (83.33%) | Only 4 cases (`19023010`, `87083000`, `87089500`, `94013000`) are ≤ 5 |
| Cases with `> 10` candidates | **18 / 24** (75.00%) | — |
| Cases with `> 20` candidates | **12 / 24** (50.00%) | — |
| Cases with `> 30` candidates | **7 / 24** (29.17%) | — |
| Gold HSN ranked **#1** (Top-1) | **54.17%** (13 / 24) | — |
| Gold HSN in **Top-3** | **79.17%** (19 / 24) | — |
| Gold HSN in **Top-5** | **83.33%** (20 / 24) | — |
| Clarification-reducible ambiguity | **79.17%** (19 / 24) | Cases where clarification is required to narrow surviving candidates |
| False rejections | **0 / 24** | **100%** candidate recall across all 24 cases |
| Exact HSN hits | **3 / 24** | `87089500`, `94013000`, `94035010` |
| Correct abstention | **22 / 24** | 2 false `EXACT_HSN` emissions: Case 13 (`19023090` vs `19023010`) and Case 15 (`39233010` vs `39233090`) |

---

## 2. Candidate Noise Breakdown (783 Total Retained 8-Digit Candidates)

| Category | Count | Share of Retained | Interpretation |
|---|---:|---:|---|
| `same_4digit_heading_siblings` | **509** | **65.0%** | Mostly genuine statutory tariff siblings under the target 4-digit heading when distinguishing specs (polymer, thickness, fiber %, alloy grade, pump type) are unstated |
| `same_chapter_different_heading` | **199** | **25.4%** | Secondary headings in the same chapter; mix of plausible adjacent headings and material-only/generic-keyword noise |
| `cross_chapter` | **75** | **9.6%** | Cross-chapter leakage, heavily concentrated in Case 4 (`62043991`: `61`) and Case 11 (`85119000`: `11`) |
| `material_only_no_article` | **52** | **6.6%** | Candidates with **zero** finished-article identity match surviving purely on material overlap (e.g., Case 5: `29`, Case 16: `12`, Case 18: `10`) |

> [!NOTE]
> `509 / 783` (65.0%) of all retained candidates are **same-4-digit heading siblings**. Not all retained candidates are noise: when a customer writes `"woven cotton shirt for men"` or `"seamless stainless steel tubes and pipes"`, multiple 8-digit tariff items genuinely exist until distinguishing statutory attributes are clarified.

---

## 3. Per-Case Candidate Analysis (All 24 Cases)

| # | Source | Customer Description (Truncated) | Stage 1 `finished_article` (Truncated) | Gold HSN | Init | Ret 8d | Sup | Pos | Same H4 | Diff H4 (Same Ch) | Cross Ch | Mat Only | False Ret | False Rej | Rank | Mode (Final HSN) | Abstained OK |
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 1 | `indep` | WASTE, PARINGS AND SCRAP, OF PLASTICS - OF OTHER PLASTICS - OF PHENOPLAST (recycled nylon-6 scrap) | WASTE, PARINGS AND SCRAP, OF PLASTICS - OF OTHER PLASTICS - OF PHENOPLAST (recycled nylon-6 scrap) | `39159061` | 203 | 24 | 7 | 17 | 22 | 2 | 0 | 1 | 2 | 0 | 1 | `CHAPTER_ONLY_CLARIFY` | True |
| 2 | `indep` | TUBES, PIPES AND HOSES, AND FITTINGS THEREFOR (FOR EXAMPLE, JOINTS, ELBOWS, FLANGES), OF PLASTICS... | `TUBES, PIPES AND HOSES, AND FITTINGS THEREFOR (` | `39173220` | 204 | 22 | 0 | 22 | 22 | 0 | 0 | 0 | 0 | 0 | 3 | `CHAPTER_ONLY_CLARIFY` | True |
| 3 | `indep` | OTHER PLATES, SHEETS, FILM, FOIL AND STRIP, OF PLASTICS, NON-CELLULAR... - OF POLY (ETHYLENE TEREPHTHALATE)... | OTHER PLATES, SHEETS, FILM, FOIL AND STRIP, OF PLASTICS, NON-CELLULAR AND NOT REINFORCED... | `39206210` | 237 | 145 | 141 | 4 | 111 | 34 | 0 | 0 | 34 | 0 | 101 | `MULTIPLE_CANDIDATES` | True |
| 4 | `indep` | WOMEN'SOR GIRLS SUITS, ENSEMBLES, JACKETS, BLAZERS, DRESSES, SKIRTS... - EMBROIDERED WITH LUCKNOW CHIKAN CRAFT (linen) | WOMEN'SOR GIRLS SUITS, ENSEMBLES, JACKETS, BLAZERS, DRESSES, SKIRTS... - EMBROIDERED | `62043991` | 247 | 177 | 23 | 154 | 83 | 33 | 61 | 0 | 94 | 0 | 113 | `MULTIPLE_CANDIDATES` | True |
| 5 | `indep` | TABLE, KITCHEN OR OTHER HOUSEHOLD ARTICLES... - UTENSILS OF GALVANISED IRON (hot-dip galvanized mild steel sheet) | TABLE, KITCHEN OR OTHER HOUSEHOLD ARTICLES... - UTENSILS OF GALVANISED IRON (hot-dip galvanized mild steel sheet) | `73239910` | 206 | 42 | 12 | 30 | 12 | 29 | 1 | 29 | 30 | 0 | 1 | `MULTIPLE_CANDIDATES` | True |
| 6 | `indep` | TURBO-JETS, TURBO-PROPELLERS AND OTHER GAS TURBINES - TURBO-JETS... (nickel-based superalloys) | TURBO-JETS, TURBO-PROPELLERS AND OTHER GAS TURBINES - TURBO-JETS... (nickel-based superalloys) | `84119100` | 163 | 20 | 0 | 20 | 13 | 7 | 0 | 0 | 7 | 0 | 1 | `CHAPTER_ONLY_CLARIFY` | True |
| 7 | `indep` | PUMPS FOR LIQUIDS... - OTHER ROTARY POSITIVE DISPLACEMENT PUMPS - SCREW TYPE PUMPS (cast iron pump casing) | `PUMPS` | `84136020` | 200 | 40 | 0 | 40 | 38 | 2 | 0 | 0 | 2 | 0 | 1 | `CHAPTER_ONLY_CLARIFY` | True |
| 8 | `indep` | PUMPS FOR LIQUIDS... - OTHER CENTRIFUGAL PUMPS - PRIMARILY DESIGNED TO HANDLE WATER (cast iron pump casing) | `PUMPS` | `84137010` | 200 | 39 | 0 | 39 | 38 | 1 | 0 | 0 | 1 | 0 | 1 | `CHAPTER_ONLY_CLARIFY` | True |
| 9 | `indep` | ELECTRICAL TRANSFORMERS, STATIC CONVERTERS (FOR EXAMPLE, RECTIFIERS) AND INDUCTORS - DIP BRIDGE RECTIFIER... | `ELECTRICAL TRANSFORMERS, STATIC CONVERTERS (` | `85044021` | 227 | 23 | 0 | 23 | 23 | 0 | 0 | 0 | 0 | 0 | 1 | `CHAPTER_ONLY_CLARIFY` | True |
| 10 | `indep` | VACUUM CLEANERS - OTHER VACCUM CLEANERS (electric suction motor) | VACUUM CLEANERS - OTHER VACCUM CLEANERS (electric suction motor) | `85086000` | 162 | 11 | 0 | 11 | 4 | 6 | 1 | 0 | 7 | 0 | 1 | `MULTIPLE_CANDIDATES` | True |
| 11 | `indep` | ELECTRICAL IGNITION OR STARTING EQUIPMENT OF A KIND USED FOR SPARK-IGNITION... (spark plug nickel/platinum alloy) | `ELECTRICAL IGNITION OR STARTING EQUIPMENT OF A KIND` | `85119000` | 203 | 37 | 0 | 37 | 9 | 17 | 11 | 0 | 28 | 0 | 8 | `CHAPTER_ONLY_CLARIFY` | True |
| 12 | `indep` | LUMINAIRES AND LIGHTING FITTINGS... - NON-ELECTRICAL LAMPS AND LIGHTING FITTINGS (brass gas jet valve) | `LUMINAIRES AND LIGHTING FITTINGS` | `94055039` | 238 | 28 | 0 | 28 | 28 | 0 | 0 | 0 | 0 | 0 | 1 | `CHAPTER_ONLY_CLARIFY` | True |
| 13 | `synth` | instant noodles made from wheat flour | `instant noodles` | `19023010` | 155 | 4 | 1 | 3 | 4 | 0 | 0 | 0 | 0 | 0 | 2 | `EXACT_HSN` (`19023090`) | **False** |
| 14 | `synth` | sweet biscuits containing cocoa | `sweet biscuits` | `19053100` | 158 | 13 | 0 | 13 | 13 | 0 | 0 | 0 | 0 | 0 | 1 | `CHAPTER_ONLY_CLARIFY` | True |
| 15 | `synth` | plastic water bottle made of polyethylene | `plastic water bottle` | `39233090` | 168 | 9 | 1 | 8 | 4 | 5 | 0 | 0 | 5 | 0 | 2 | `EXACT_HSN` (`39233010`) | **False** |
| 16 | `synth` | knitted cotton t-shirt for men | `knitted cotton t-shirt` | `61091000` | 228 | 19 | 5 | 14 | 1 | 18 | 0 | 12 | 18 | 0 | 1 | `MULTIPLE_CANDIDATES` | True |
| 17 | `synth` | knitted woollen sweater pullover | `knitted woollen sweater pullover` | `61101110` | 209 | 9 | 5 | 4 | 9 | 0 | 0 | 0 | 0 | 0 | 3 | `CHAPTER_ONLY_CLARIFY` | True |
| 18 | `synth` | woven cotton shirt for men | `woven cotton shirt` | `62052000` | 203 | 25 | 8 | 17 | 7 | 18 | 0 | 10 | 18 | 0 | 3 | `MULTIPLE_CANDIDATES` | True |
| 19 | `synth` | stainless steel screws and bolts | `stainless steel screws and bolts` | `73181500` | 160 | 14 | 13 | 1 | 14 | 0 | 0 | 0 | 0 | 0 | 4 | `CHAPTER_ONLY_CLARIFY` | True |
| 20 | `synth` | seamless stainless steel tubes and pipes | `seamless stainless steel tubes and pipes` | `73044900` | 238 | 60 | 30 | 30 | 39 | 20 | 1 | 0 | 21 | 0 | 12 | `MULTIPLE_CANDIDATES` | True |
| 21 | `synth` | brake pads for passenger motor cars | `brake pads` | `87083000` | 162 | 4 | 0 | 4 | 3 | 1 | 0 | 0 | 1 | 0 | 2 | `MULTIPLE_CANDIDATES` | True |
| 22 | `synth` | safety air bags with inflator system for motor vehicles | `safety air bags` | `87089500` | 210 | 2 | 0 | 2 | 1 | 1 | 0 | 0 | 1 | 0 | 1 | `EXACT_HSN` (`87089500`) | True |
| 23 | `synth` | swivel office chair with variable height adjustment | `swivel office chair` | `94013000` | 169 | 3 | 0 | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 1 | `EXACT_HSN` (`94013000`) | True |
| 24 | `synth` | wooden bedroom furniture bed | `wooden bedroom furniture bed` | `94035010` | 138 | 13 | 0 | 13 | 8 | 5 | 0 | 0 | 5 | 0 | 1 | `EXACT_HSN` (`94035010`) | True |

---

## 4. Evaluation Integrity Validation

| Check | Result | Details |
|---|---:|---|
| Gold HSNs in statutory master 8-digit leaves | **24 / 24** (`true`) | Every gold-standard HSN code is a valid 8-digit leaf in the statutory master |
| Query text overlap with `train` split | **0** | No exact query leakage |
| Query text overlap with `val` split | **0** | No exact query leakage |
| `independent_exact_hsn_eval` (Cases 1–12) HSN overlap with `train` | **0** | Zero HSN overlap with training |
| `independent_exact_hsn_eval` (Cases 1–12) HSN overlap with `val` | **0** | Zero HSN overlap with validation |
| All 24 cases HSN overlap with `train` / `val` | **10** / **5** | Overlap comes entirely from `synthetic_9ch` (Cases 13–24); `independent_exact_hsn_eval` is completely disjoint by both query and HSN |

---

## 5. Root Causes of Remaining Candidate Noise

1. **Material-only survival without finished-article compatibility (`52` candidates across 4 cases)**:
   - In `candidate_evidence_evaluator.py`, candidates with **zero** article-identity match (`article_matches == False`) still survive as `POSSIBLY_SUPPORTED` whenever `material_matches == True`.
   - This directly inflates unrelated same-chapter headings on material-rich queries: Case 5 (`73239910` utensils → `29` material-only rows), Case 16 (`61091000` t-shirt → `12`), Case 18 (`62052000` shirt → `10`).

2. **Stage 1 `finished_article` splitting inside parentheticals and multi-clause statutory strings**:
   - `_split_top_level_clauses` splits on `"for "` inside `(FOR EXAMPLE, ...)`, leaving malformed `finished_article` strings ending in `(` on Case 2 (`TUBES, PIPES AND HOSES, AND FITTINGS THEREFOR (`) and Case 9 (`ELECTRICAL TRANSFORMERS, STATIC CONVERTERS (`).
   - Long statutory heading strings (`62043991` listing suits, ensembles, jackets, blazers, dresses, skirts, trousers, overalls, breeches, shorts; `39206210` listing plates, sheets, film, foil, strip) match broad article sets across multiple headings and chapters (`177` and `145` retained candidates; `61` cross-chapter rows on Case 4).

3. **Unresolved residual/sibling `EXACT_HSN` emissions (2 cases)**:
   - Case 13 (`instant noodles made from wheat flour`, gold `19023010`) emitted `EXACT_HSN` = `19023090` (`Other`), even though gold `19023010` was ranked #2 among `4` candidates.
   - Case 15 (`plastic water bottle made of polyethylene`, gold `39233090`) emitted `EXACT_HSN` = `39233010`, even though gold `39233090` was ranked #2 among `9` candidates.

4. **Genuine multi-leaf tariff ambiguity (`509 / 783` = 65.0%)**:
   - Under headings such as `3920` (`111`), `6204` (`83`), `7304` (`39`), and `8413` (`38`), dozens of 8-digit tariff lines differ by thickness, polymer/alloy composition, or technical application not stated in the input. Truncating these via a fixed top-K cutoff would violate statutory completeness and introduce false rejections.

---

## 6. Ranked Recommendations (by Expected Impact)

1. **Rank 1 (High Impact — Precision without Recall Loss): Eliminate `material_only_no_article` survival**
   - Require either positive `article_identity` compatibility or explicit parent/heading compatibility before retaining a candidate as `POSSIBLY_SUPPORTED`. Material overlap alone should only act as supporting/contradicting evidence once the article/heading is plausible (unless the query itself has no identifiable finished article).
   - Expected effect: eliminates `52` false retentions across Cases 1, 5, 16, 18 (cutting Case 5 from `42` → `13`, Case 16 from `19` → `7`, Case 18 from `25` → `15`) with zero false rejections.

2. **Rank 2 (High Impact — Statutory Parsing & Cross-Chapter Noise): Ignore parentheticals when splitting `finished_article` clauses and tighten multi-noun article focus**
   - Update Stage 1 clause splitting to track parenthesis depth so `(FOR EXAMPLE, ...)` is never split mid-parenthesis, and extract the primary specific sub-clause (deepest statutory leaf noun phrase) rather than broadcasting all 10+ generic heading nouns.
   - Expected effect: fixes malformed `(` extractions (Cases 2, 9, 11) and sharply reduces cross-chapter/cross-heading inflation on Cases 3, 4, 11.

3. **Rank 3 (Medium-High Impact — Exact-HSN Calibration Safety): Guard `EXACT_HSN` emission against unresolved sibling competition**
   - Do not emit `EXACT_HSN` when `>1` distinct 8-digit siblings under the same 6-digit subheading survive without explicit distinguishing attribute evidence (e.g., `19023010` vs `19023090`, `39233010` vs `39233090`), routing instead to `MULTIPLE_CANDIDATES` / clarification.
   - Expected effect: eliminates the `2/24` false `EXACT_HSN` errors (`100%` safe abstention).

4. **Rank 4 (Medium Impact — Customer Usability): Group `same_4digit_heading_siblings` by distinguishing attribute in the UI/API**
   - Since `65.0%` of retained candidates are genuine 4-digit heading siblings, keep preserving all qualifying 8-digit leaves in the backend while presenting them grouped by distinguishing statutory attribute + clarification prompt (`79.17%` of cases are clarification-reducible).

---

## 7. Decision: Is Another Implementation Phase Justified?

**Yes — a targeted, narrow Phase 15 is justified.**

Phase 14 achieved `0` false rejections (`100%` recall) and `54.17%` Top-1 / `83.33%` Top-5 ranking across all 9 chapters, so the architecture does **not** need a broad rewrite or arbitrary top-K truncation. However, the audit uncovered three specific, universal, non-hardcoded defects that directly hurt precision and safety:
1. `52` `material_only_no_article` false retentions,
2. Parenthesis-splitting bugs and multi-noun over-broadening in Stage 1 `finished_article`, and
3. `2` false `EXACT_HSN` emissions on unresolved 6-digit sibling pairs (`190230xx`, `392330xx`).

Fixing those three universal mechanisms in Phase 15 will substantially reduce noise and raise safe abstention to `24/24` while preserving `0` false rejections.

