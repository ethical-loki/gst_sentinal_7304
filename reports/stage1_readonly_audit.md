# Stage 1 Read-Only Audit — Universal Dynamic Product Intelligence

**Scope**: Read-only audit of Stage 1 (`src/nlp/intent_extractor.py`, `src/nlp/product_intent_analyzer.py`, `src/nlp/hsn_rag_layer.py`, `src/chapter_predictor/normalize.py`, `src/search/hybrid_retrieval.py`). Zero source files were modified.

---

## 1. Root-Cause Analysis of the VFD Failure

Tested live with `"Variable Frequency Drive (VFD) for controlling AC motor speed"` and `"VFD for controlling AC motor speed"`:

1. **Why `VFD` was classified as `CONSTITUENT_MATERIAL`**:
   - In [product_intent_analyzer.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/nlp/product_intent_analyzer.py#L305-L333), `_split_top_level_clauses` splits at `"for "`, leaving `head = "Variable Frequency Drive (VFD)"`. Because `(VFD)` is at the end of `head` (`pm.end() == len(clean_head)` -> `is_trailing = True`), `analyze_product_intent` unconditionally appends `VFD` to `constituent_materials` as `AttributeRelationship("material_or_note", "VFD", "CONSTITUENT_MATERIAL", "parenthetical")`.
   - Consequently, `article_search_query` becomes `"Variable Frequency Drive | Material: VFD | Use: controlling AC motor speed"`, and [hsn_rag_layer.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/nlp/hsn_rag_layer.py#L1612-L1630) emits `master_search_string = "Variable Frequency Drive, Material: VFD, Use: controlling AC motor speed."`.
2. **Why `extract_query_facts` confused the controlled object (`motor`) with the finished product**:
   - In [normalize.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/chapter_predictor/normalize.py#L294-L324), `extract_query_facts` selects the **rightmost** matched noun across the entire query (`"motor"` in `"for controlling AC motor speed"`), overwriting the primary commercial product (`drive` / `VFD`).
3. **Why the motor-control function was lost in Stage 2 search & distorted by Qwen2.5-0.5B**:
   - In [intent_extractor.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/nlp/intent_extractor.py#L1216-L1276), `synthesized_search_string` builds `synth_parts` from `primary_anchor`, `Material`, `Construction`, and `Terms`, **omitting `intended_use`** (`"controlling AC motor speed"`).
   - On `"VFD for controlling AC motor speed"`, `TransformersLLMClient` (`qwen2.5-0.5b-instruct`) hallucinated `physical_product="electric motor"`, `finished_article="voltage regulator"`, `intended_use="power control"`, and unstated terms `["iron or steel", "fixed, variable, adjustable"]`.
4. **Why Stage 1 Latency Reached 82–97s per Query (up to 303.8s with retries)**:
   - Live CPU inference of `TransformersLLMClient` (`qwen2.5-0.5b-instruct`, `max_new_tokens=180`, FP32 on CPU) took **`82,356.6 ms`** on `"Variable Frequency Drive (VFD) for controlling AC motor speed"` and **`97,417.8 ms`** on `"VFD for controlling AC motor speed"`, whereas deterministic structural analysis took **`8.8–93.4 ms`** (`~1,000x–9,000x` faster). Retries (`max_json_retries=2`) + repeated calls push single-request Stage 1 latency over `300,000 ms`.

---

## 2. Exact Source Files and Lines Requiring Changes

| File | Lines | Issue |
|---|---|---|
| [product_intent_analyzer.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/nlp/product_intent_analyzer.py) | `99–148`, `305–333`, `370–445` | Trailing parenthetical `(VFD)` misclassified as `CONSTITUENT_MATERIAL`; lacks general `ACRONYM_OR_ALIAS` role, extensible attribute extraction, function decomposition (`action`, `mechanism`, `target_object`, `application`, `evidence_type`), entity relationship graph (`CONTROLS`, `POWERS`, `MADE_OF`, `PART_OF`, `USED_FOR`, `OPERATES_ON`, etc.), and field-level confidence/evidence/validation_status. |
| [normalize.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/chapter_predictor/normalize.py) | `263–324` | Rightmost noun scan matches `"motor"` inside `"for controlling AC motor speed"` instead of prioritizing the head clause before `"for"` / `"used for"` / `"intended for"`. |
| [intent_extractor.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/nlp/intent_extractor.py) | `143–168`, `183–236`, `687–724`, `1085–1280` | `synthesized_search_string` omits `intended_use` / function and components; CPU `qwen2.5-0.5b-instruct` takes 82–97s/query without configurable timeout or fast structural-first mode; `IntentExtractionResult` lacks structured Stage 2 search fields, entity relationship graph, and field-level confidence. |
| [hsn_rag_layer.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/nlp/hsn_rag_layer.py) | `1556–1652` | Contains hardcoded `material_patterns`/`form_patterns` regex lists alongside `analyze_product_intent`; passes `Material: VFD` into `master_search_string`. |
| [hybrid_retrieval.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/search/hybrid_retrieval.py) | `177–215` | Contains `_COMMERCIAL_TO_STATUTORY_TERMS` (18 manually maintained commercial-to-statutory entries from Phase 20) — must be removed per Task 8 in favor of dynamic corpus/embedding retrieval. |

---

## 3. Complete List of Remaining Manually Maintained Terminology / Rules

1. [hybrid_retrieval.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/search/hybrid_retrieval.py#L178-L198): `_COMMERCIAL_TO_STATUTORY_TERMS` (18 entries: `espresso`, `coffee`, `brewing`, `tray dryer`, `router`, `vaccum`, etc.) — **remove in Task 8**.
2. [hsn_rag_layer.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/nlp/hsn_rag_layer.py#L1557-L1601): `material_patterns` (19 regexes) and `form_patterns` (12 regexes) — **replace with dynamic `data/statutory_materials.json` / `ProductIntentStructure`**.
3. [statutory_master_index.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/search/statutory_master_index.py#L31-L43): `_SPELLING_NORMALIZATIONS` (5 entries) and `STOPWORDS`.
4. [intent_extractor.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/nlp/intent_extractor.py#L238-L335): `TestDoubleDeterministicLLMClient` (test double) and lines `928–965` `out_of_schedule_indicators` (scope guard against `Master_copy_hsn.xlsx` non-loaded chapters).
5. [candidate_evidence_evaluator.py](file:///C:/Users/User/OneDrive/Desktop/GST_Sentinal/src/ml/candidate_evidence_evaluator.py#L61-L103): `_MATERIAL_FAMILIES`, `_BROAD_SUPERORDINATES`, `_GENERIC_MODIFIERS` (general WCO taxonomy classes).
6. Data-driven JSON indexes in `data/`: `statutory_materials.json`, `statutory_forms.json`, `tariff_head_noun_index.json`, `article_form_vocabulary.json` (used by `src/chapter_predictor/normalize.py`).

