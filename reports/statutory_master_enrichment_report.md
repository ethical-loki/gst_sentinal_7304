# Statutory Master Data Quality Audit & Enrichment Report

## 1. Root-Cause Audit of Statutory Master Pipeline (`src/search/normalization.py`, `data/raw/Master_copy_hsn.xlsx`)
- **255-Character Excel Truncation:** `data/raw/Master_copy_hsn.xlsx` (4,851 rows) had **1,066 rows** truncated at 255 characters in `HSN Description`. Because `MasterHSNEnricher` split `:` / `-` on the truncated string, 8-digit `tariff_item_desc` was frequently populated with a truncated copy of the 4-digit heading or became empty (`39` empty rows), while leaf clauses (`WALKIE TALKIE SET`, `DRYERS`, `WATER HEATERS`, `DIGIAL LOOP CARRIER SYSTEM`) were lost.
- **Empty `consumer_synonyms`:** `COMMERCIAL_SYNONYMS_MAP` in `src/search/normalization.py` is `{}` (neutralized), leaving `consumer_synonyms` empty across `4,592` rows in the prior parquet and `4,851` rows after clean regeneration (which also caused `BM25Okapi` `ZeroDivisionError` when all documents were empty — now guarded in `src/search/hybrid_retrieval.py`).
- **Stale Dense Embedding Cache Key:** `HybridHSNEngine` previously keyed `master_embeddings_*.npy` solely on `Master_copy_hsn.xlsx`'s SHA-256, ignoring updates to `data/enriched_master_hsn.parquet`.

## 2. Authoritative Source Audit for the 7 Retrieval Failures

| Case | Expected HSN | Prior `tariff_item_desc` (Truncated) | Authoritative Source (`data/raw/itc_hs_codes.json`) | Enriched Outcome |
| --- | --- | --- | --- | --- |
| #16 | `39219099` | `OTHER` (len=79) | `OTHER PLATES, SHEETS, FILM, FOIL AND STRIP, OF PLASTICS - OTHER : OTHER : OTHER` | Genuinely residual (`is_residual=True`) |
| #57 | `84191910` | Truncated 255-char heading copy | `...INSTANTANEOUS OR STORAGE WATER HEATERS, NON-ELECTRIC - INSTANTANEOUS GAS WATER HEATERS : OTHER: DOMESTIC TYPE` (len=550) | **Recovered (`recall=True, rank=37`)** |
| #58 | `84193900` | Truncated 255-char heading copy | `...DRYERS: OTHER` (len=509); `subheading_6digit_desc='DRYERS - OTHER'` | Untruncated & indexed |
| #59 | `84198120` | Truncated 255-char heading copy | `...FOR MAKING HOT DRINKS OR FOR COOKING OR HEATING FOOD: OTHER KITCHEN MACHINES` (len=610) | Untruncated & indexed |
| #72 | `85044090` | `OTHER` (len=108) | `ELECTRICAL TRANSFORMERS, STATIC CONVERTERS (FOR EXAMPLE, RECTIFIERS) AND INDUCTORS -STATIC CONVERTERS: OTHER` | `subheading_6digit_desc='STATIC CONVERTERS'`, `is_residual=True` |
| #79 | `85176250` | Truncated 255-char heading copy | `...INCLUDING SWITCHING AND ROUTING APPARATUS: --- DIGIAL LOOP CARRIER SYSTEM (DLC)` (len=742) | Untruncated & indexed |
| #88 | `85252011` | Truncated 255-char heading copy | `...TWO WAY RADIO COMMUNICATION EQUIPMENT: WALKIE TALKIE SET` (len=403) | **Recovered to Rank #1 (`recall=True, rank=1`)** |

## 3. Source-Supported Enrichment & Validation (`src/search/normalization.py`, `src/search/hybrid_retrieval.py`)
- **Authoritative Restoration (`MasterHSNEnricher`):** Restored **1,172** records from `data/raw/itc_hs_codes.json` (`source_provenance="Master_copy_hsn.xlsx + itc_hs_codes.json"`), reducing 255-char truncated records from **1,066 → 30** and empty leaf descriptions from **39 → 2**.
- **Tariff Metadata:** Joined `effective_date` (`2025-09-22`) and `notification_ref` from `data/raw/gst_rates.json`.
- **Hierarchy & Residual Integrity:** Extracted `subheading_6digit_desc` and `tariff_item_desc` cleanly from untruncated statutory text, flagging `is_residual`, `is_truncated`, and `is_incomplete` without fabricating descriptions or altering genuine `"OTHER"` categories (`1,055` rows).
- **Dynamic Cache Invalidation & Empty-Corpus Guard:** `HybridHSNEngine` now hashes both `Master_copy_hsn.xlsx` and `enriched_master_hsn.parquet` for `master_embeddings_*.npy`, and safely skips `BM25Okapi` when a field corpus is empty.
- **Validation (`validate_enriched_master`):** Verified `4,851` rows, `0` invalid/missing codes, `0` duplicates, `30` remaining 255-char rows, and `['2025-09-22']` effective date.

## 4. Verification & Benchmark Comparison
- **Test Suite:** `69 passed, 0 failed` (`tests/test_statutory_master_enrichment.py` + full HSN regression suite).
- **100-Case Zero-Leakage Independent Benchmark** ([master_enrichment_100.json](file:///c:/Users/User/OneDrive/Desktop/GST_Sentinal/reports/master_enrichment_100.json)):

| Metric | Prior (`stage2_perf_opt_100.json`) | Enriched Master (`master_enrichment_100.json`) |
| --- | ---: | ---: |
| Candidate Recall | `89.0%` | **`91.0%`** (`+2.0%`) |
| Recall@1 (Top-1) | `31.0%` | **`36.0%`** (`+5.0%`) |
| Recall@5 / @10 / @20 | `62.0%` / `71.0%` / `80.0%` | **`67.0%` / `75.0%` / `83.0%`** |
| Chapter Accuracy | `95.0%` | **`97.0%`** (`+2.0%`) |
| Same-Heading Precision | `58.88%` | `58.73%` |
| Exact HSN Hits | `6` (`6.0%`) | **`7`** (`7.0%`) |
| False Exact Predictions | `0` | **`0`** |
| Correct Abstention | `100.0%` | **`100.0%`** |
| Mean / P95 Latency | `31.02s` / `66.34s` | **`27.92s` / `41.42s`** |
| CrossEncoder Evaluations | `19,200` | `19,024` |
