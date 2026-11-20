# Phase 1 — Statutory Master Coverage & Data Quality Report

- **Source Authority:** CBIC / DGFT ITC-HS & GST Council Schedule
- **Publication Version:** ITC-HS 2022 + Notification No. 09/2025-CT(Rate)
- **Distinct Effective Dates:** 2025-09-22
- **Total Goods HSN Records:** 18797 across 97 chapters (Chapters 01–98; WCO-reserved Chapter 77 empty)
- **Total SAC Service Records (Chapter 99, separated):** 600
- **Invalid/Corrupted Format Codes:** 0
- **Duplicate Codes After Deduplication:** 0
- **Missing Statutory Descriptions:** 9
- **Remaining Truncated (255-char) Statutory Descriptions:** 94
- **Missing 4-digit Parent Heading Rows:** 34
- **Direct-to-8d Rows Without Explicit 6-digit Row:** 4386
- **Incomplete Records (flagged explicitly, never fabricated):** 137
- **Residual (`OTHER`) Leaf Records:** 3829
- **Legal-Note Coverage:** 11 / 97 goods chapters have partial digitized rules loaded (`data/statutory_rules.json`); 86 chapters are explicitly flagged `NO_AUTHORITATIVE_NOTES_LOADED`.

## Chapter-Wise Coverage Table

| Ch | Sec | Schedule | Total | 4d | 6d | 8d | Missing Desc | Trunc 255 | Missing 4d Parent | Incomplete | Residual | Notes Count | Note Status |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 01 | Section I | HSN_GOODS | 80 | 6 | 14 | 60 | 0 | 0 | 1 | 1 | 18 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 02 | Section I | HSN_GOODS | 84 | 10 | 4 | 70 | 0 | 0 | 0 | 0 | 7 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 03 | Section I | HSN_GOODS | 551 | 9 | 141 | 401 | 0 | 1 | 0 | 1 | 87 | 1 | PARTIAL_AUTHORITATIVE_NOTES_LOADED |
| 04 | Section I | HSN_GOODS | 86 | 10 | 19 | 57 | 0 | 0 | 0 | 0 | 23 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 05 | Section I | HSN_GOODS | 98 | 11 | 14 | 73 | 1 | 2 | 0 | 3 | 26 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 06 | Section II | HSN_GOODS | 38 | 4 | 6 | 28 | 0 | 0 | 0 | 0 | 9 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 07 | Section II | HSN_GOODS | 150 | 14 | 22 | 114 | 0 | 0 | 0 | 0 | 22 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 08 | Section II | HSN_GOODS | 181 | 14 | 36 | 131 | 0 | 0 | 0 | 0 | 33 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 09 | Section II | HSN_GOODS | 206 | 10 | 44 | 152 | 0 | 0 | 0 | 0 | 29 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 10 | Section II | HSN_GOODS | 127 | 14 | 30 | 83 | 0 | 0 | 0 | 0 | 37 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 11 | Section II | HSN_GOODS | 58 | 9 | 6 | 43 | 0 | 0 | 0 | 0 | 8 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 12 | Section II | HSN_GOODS | 192 | 14 | 31 | 147 | 0 | 2 | 0 | 2 | 43 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 13 | Section II | HSN_GOODS | 89 | 2 | 4 | 83 | 0 | 0 | 0 | 0 | 16 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 14 | Section II | HSN_GOODS | 33 | 4 | 2 | 27 | 1 | 0 | 0 | 1 | 7 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 15 | Section III | HSN_GOODS | 191 | 22 | 37 | 132 | 1 | 0 | 0 | 1 | 54 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 16 | Section IV | HSN_GOODS | 75 | 5 | 23 | 47 | 0 | 0 | 0 | 0 | 9 | 2 | PARTIAL_AUTHORITATIVE_NOTES_LOADED |
| 17 | Section IV | HSN_GOODS | 58 | 4 | 13 | 41 | 0 | 1 | 0 | 1 | 13 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 18 | Section IV | HSN_GOODS | 22 | 6 | 1 | 15 | 0 | 0 | 0 | 0 | 2 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 19 | Section IV | HSN_GOODS | 51 | 5 | 9 | 37 | 0 | 1 | 0 | 1 | 14 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 20 | Section IV | HSN_GOODS | 114 | 19 | 11 | 84 | 0 | 0 | 0 | 0 | 18 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 21 | Section IV | HSN_GOODS | 58 | 7 | 7 | 44 | 0 | 1 | 0 | 1 | 11 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 22 | Section IV | HSN_GOODS | 123 | 9 | 17 | 97 | 4 | 0 | 0 | 4 | 21 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 23 | Section IV | HSN_GOODS | 90 | 9 | 11 | 70 | 0 | 1 | 0 | 1 | 16 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 24 | Section IV | HSN_GOODS | 65 | 4 | 9 | 52 | 0 | 1 | 0 | 1 | 10 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 25 | Section V | HSN_GOODS | 265 | 29 | 38 | 198 | 0 | 3 | 0 | 3 | 47 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 26 | Section V | HSN_GOODS | 118 | 21 | 14 | 83 | 0 | 0 | 0 | 0 | 23 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 27 | Section V | HSN_GOODS | 179 | 16 | 21 | 142 | 0 | 1 | 0 | 1 | 26 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 28 | Section VI | HSN_GOODS | 526 | 53 | 77 | 396 | 1 | 0 | 0 | 1 | 105 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 29 | Section VI | HSN_GOODS | 1515 | 42 | 174 | 1299 | 0 | 4 | 0 | 4 | 286 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 30 | Section VI | HSN_GOODS | 341 | 47 | 25 | 269 | 0 | 1 | 0 | 1 | 42 | 1 | PARTIAL_AUTHORITATIVE_NOTES_LOADED |
| 31 | Section VI | HSN_GOODS | 46 | 5 | 5 | 36 | 0 | 0 | 0 | 0 | 11 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 32 | Section VI | HSN_GOODS | 382 | 15 | 27 | 340 | 0 | 4 | 0 | 4 | 77 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 33 | Section VI | HSN_GOODS | 158 | 7 | 16 | 135 | 0 | 3 | 0 | 3 | 32 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 34 | Section VI | HSN_GOODS | 83 | 7 | 10 | 66 | 0 | 2 | 0 | 2 | 25 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 35 | Section VI | HSN_GOODS | 52 | 7 | 7 | 38 | 0 | 0 | 0 | 0 | 15 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 36 | Section VI | HSN_GOODS | 43 | 6 | 6 | 31 | 0 | 0 | 0 | 0 | 11 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 37 | Section VI | HSN_GOODS | 141 | 7 | 29 | 105 | 0 | 4 | 0 | 4 | 29 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 38 | Section VI | HSN_GOODS | 399 | 27 | 36 | 336 | 0 | 3 | 0 | 3 | 71 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 39 | Section VII | HSN_GOODS | 577 | 26 | 84 | 467 | 0 | 2 | 0 | 2 | 156 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 40 | Section VII | HSN_GOODS | 240 | 20 | 40 | 180 | 0 | 1 | 0 | 1 | 61 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 41 | Section VIII | HSN_GOODS | 92 | 11 | 14 | 67 | 0 | 0 | 0 | 0 | 19 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 42 | Section VIII | HSN_GOODS | 94 | 6 | 15 | 73 | 0 | 0 | 0 | 0 | 20 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 43 | Section VIII | HSN_GOODS | 32 | 4 | 4 | 24 | 0 | 0 | 0 | 0 | 5 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 44 | Section IX | HSN_GOODS | 478 | 21 | 52 | 405 | 0 | 1 | 3 | 4 | 106 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 45 | Section IX | HSN_GOODS | 16 | 4 | 2 | 10 | 0 | 0 | 0 | 0 | 5 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 46 | Section IX | HSN_GOODS | 23 | 2 | 1 | 20 | 0 | 0 | 0 | 0 | 9 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 47 | Section X | HSN_GOODS | 32 | 7 | 2 | 23 | 0 | 0 | 0 | 0 | 1 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 48 | Section X | HSN_GOODS | 289 | 23 | 38 | 228 | 0 | 2 | 0 | 2 | 56 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 49 | Section X | HSN_GOODS | 60 | 11 | 11 | 38 | 0 | 0 | 0 | 0 | 13 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 50 | Section XI | HSN_GOODS | 63 | 7 | 18 | 38 | 0 | 0 | 11 | 11 | 9 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 51 | Section XI | HSN_GOODS | 146 | 14 | 27 | 105 | 0 | 0 | 3 | 3 | 33 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 52 | Section XI | HSN_GOODS | 563 | 12 | 82 | 469 | 0 | 1 | 0 | 1 | 92 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 53 | Section XI | HSN_GOODS | 105 | 11 | 15 | 79 | 0 | 1 | 0 | 1 | 26 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 54 | Section XI | HSN_GOODS | 303 | 8 | 35 | 260 | 0 | 3 | 0 | 3 | 49 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 55 | Section XI | HSN_GOODS | 310 | 16 | 51 | 243 | 0 | 0 | 0 | 0 | 56 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 56 | Section XI | HSN_GOODS | 86 | 9 | 12 | 65 | 0 | 0 | 0 | 0 | 23 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 57 | Section XI | HSN_GOODS | 141 | 5 | 22 | 114 | 0 | 1 | 0 | 1 | 36 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 58 | Section XI | HSN_GOODS | 140 | 11 | 23 | 106 | 0 | 0 | 0 | 0 | 26 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 59 | Section XI | HSN_GOODS | 106 | 11 | 19 | 76 | 0 | 0 | 0 | 0 | 26 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 60 | Section XI | HSN_GOODS | 66 | 8 | 4 | 54 | 0 | 0 | 1 | 1 | 7 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 61 | Section XI | HSN_GOODS | 290 | 17 | 49 | 224 | 0 | 0 | 0 | 0 | 37 | 1 | PARTIAL_AUTHORITATIVE_NOTES_LOADED |
| 62 | Section XI | HSN_GOODS | 434 | 17 | 83 | 334 | 0 | 0 | 0 | 0 | 109 | 1 | PARTIAL_AUTHORITATIVE_NOTES_LOADED |
| 63 | Section XI | HSN_GOODS | 168 | 10 | 20 | 138 | 0 | 0 | 0 | 0 | 25 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 64 | Section XII | HSN_GOODS | 100 | 6 | 20 | 74 | 0 | 3 | 0 | 3 | 32 | 1 | PARTIAL_AUTHORITATIVE_NOTES_LOADED |
| 65 | Section XII | HSN_GOODS | 29 | 7 | 5 | 17 | 0 | 0 | 0 | 0 | 3 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 66 | Section XII | HSN_GOODS | 13 | 3 | 1 | 9 | 0 | 0 | 0 | 0 | 4 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 67 | Section XII | HSN_GOODS | 25 | 4 | 6 | 15 | 0 | 0 | 0 | 0 | 6 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 68 | Section XIII | HSN_GOODS | 154 | 15 | 22 | 117 | 0 | 3 | 0 | 3 | 33 | 2 | PARTIAL_AUTHORITATIVE_NOTES_LOADED |
| 69 | Section XIII | HSN_GOODS | 110 | 14 | 18 | 78 | 0 | 0 | 0 | 0 | 29 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 70 | Section XIII | HSN_GOODS | 178 | 23 | 25 | 130 | 0 | 0 | 0 | 0 | 52 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 71 | Section XIV | HSN_GOODS | 227 | 20 | 27 | 180 | 0 | 0 | 1 | 1 | 51 | 1 | PARTIAL_AUTHORITATIVE_NOTES_LOADED |
| 72 | Section XV | HSN_GOODS | 666 | 29 | 105 | 532 | 0 | 3 | 0 | 3 | 154 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 73 | Section XV | HSN_GOODS | 404 | 26 | 65 | 313 | 0 | 2 | 0 | 2 | 123 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 74 | Section XV | HSN_GOODS | 165 | 19 | 21 | 125 | 0 | 1 | 0 | 1 | 34 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 75 | Section XV | HSN_GOODS | 40 | 8 | 5 | 27 | 0 | 0 | 0 | 0 | 3 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 76 | Section XV | HSN_GOODS | 138 | 16 | 22 | 100 | 0 | 1 | 0 | 1 | 31 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 78 | Section XV | HSN_GOODS | 35 | 6 | 5 | 24 | 0 | 0 | 0 | 0 | 8 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 79 | Section XV | HSN_GOODS | 35 | 7 | 5 | 23 | 0 | 0 | 0 | 0 | 6 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 80 | Section XV | HSN_GOODS | 35 | 14 | 5 | 16 | 0 | 0 | 1 | 1 | 3 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 81 | Section XV | HSN_GOODS | 134 | 14 | 16 | 104 | 0 | 0 | 0 | 0 | 37 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 82 | Section XV | HSN_GOODS | 136 | 15 | 23 | 98 | 0 | 1 | 0 | 1 | 23 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 83 | Section XV | HSN_GOODS | 85 | 11 | 12 | 62 | 0 | 0 | 0 | 0 | 17 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 84 | Section XVI | HSN_GOODS | 1526 | 87 | 217 | 1222 | 0 | 12 | 0 | 12 | 329 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 85 | Section XVI | HSN_GOODS | 1095 | 49 | 121 | 925 | 0 | 7 | 0 | 7 | 210 | 1 | PARTIAL_AUTHORITATIVE_NOTES_LOADED |
| 86 | Section XVII | HSN_GOODS | 62 | 9 | 9 | 44 | 0 | 0 | 0 | 0 | 13 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 87 | Section XVII | HSN_GOODS | 336 | 16 | 50 | 270 | 1 | 1 | 0 | 2 | 47 | 1 | PARTIAL_AUTHORITATIVE_NOTES_LOADED |
| 88 | Section XVII | HSN_GOODS | 51 | 7 | 4 | 40 | 0 | 0 | 0 | 0 | 7 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 89 | Section XVII | HSN_GOODS | 51 | 8 | 5 | 38 | 0 | 0 | 0 | 0 | 12 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 90 | Section XVIII | HSN_GOODS | 398 | 34 | 65 | 299 | 0 | 6 | 6 | 12 | 76 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 91 | Section XVIII | HSN_GOODS | 99 | 14 | 15 | 70 | 0 | 0 | 0 | 0 | 25 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 92 | Section XVIII | HSN_GOODS | 37 | 9 | 1 | 27 | 0 | 1 | 0 | 1 | 7 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 93 | Section XIX | HSN_GOODS | 33 | 7 | 3 | 23 | 0 | 1 | 0 | 1 | 8 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 94 | Section XX | HSN_GOODS | 138 | 6 | 20 | 112 | 0 | 1 | 0 | 1 | 38 | 1 | PARTIAL_AUTHORITATIVE_NOTES_LOADED |
| 95 | Section XX | HSN_GOODS | 112 | 8 | 11 | 93 | 0 | 1 | 0 | 1 | 24 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 96 | Section XX | HSN_GOODS | 149 | 20 | 24 | 105 | 0 | 2 | 0 | 2 | 31 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 97 | Section XXI | HSN_GOODS | 52 | 6 | 7 | 39 | 0 | 0 | 0 | 0 | 14 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 98 | Section XXI-IN | SPECIAL_PROVISIONS | 27 | 5 | 1 | 21 | 0 | 1 | 7 | 8 | 1 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
| 99 | SAC | SAC_SERVICES | 600 | 31 | 569 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | NO_AUTHORITATIVE_NOTES_LOADED |
