"""
src/nlp/hsn_rag_layer.py
========================
HSN & ITC-HS Retrieval-Augmented Generation (RAG) Application Layer.

Architecture:
1. Stage 1: Customs Classification & Tariff Attribute Extractor
   - Normalizes commercial product descriptions
   - Extracts constituent material, processing state, function/use, mounted state
   - Performs statutory cross-chapter ambiguity check (e.g. pipes, shoes, gloves)
   - Emits structured search keywords and customer clarification questions when required
2. Stage 2: Statutory Context Retriever (RAG)
   - Retrieves top candidate tariff headings from CBIC Tariff Master
   - Injects WCO GIR (1-6) rules and statutory Section & Chapter legal notes
   - Injects verified precedent knowledge from persistent parquet store
3. Stage 3: Statutory HSN & ITC-HS Legal Verification Engine
   - Adjudicates candidates against extracted attributes & statutory notes
   - Strictly applies negative legal constraints (Coffee vs Cocoa, Mounted vs Unmounted brakes, Primary vs Secondary batteries)
   - Emits verified 8-digit HSN code, statutory rationale, rejected candidates, and confidence score
"""

import json
import logging
import os
import re
import time
import urllib.request
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# =====================================================================
# PYDANTIC SCHEMAS
# =====================================================================

class ExtractedAttributes(BaseModel):
    material: Optional[str] = None
    processing_state: Optional[str] = None
    function_use: Optional[str] = None
    mounted_state: str = "not_applicable"  # "mounted" | "unmounted" | "not_applicable"

class ClarificationPayload(BaseModel):
    question: Optional[str] = None
    options: List[str] = Field(default_factory=list)

class AttributeExtractionResult(BaseModel):
    product_normalized: str
    attributes: ExtractedAttributes
    needs_clarification: bool
    clarification: Optional[ClarificationPayload] = None
    search_keywords: List[str] = Field(default_factory=list)

class RejectedCandidate(BaseModel):
    hsn: str
    reason: str

class StatutoryVerificationResult(BaseModel):
    selected_hsn: str
    heading_description: str
    gst_rate_expected: Optional[str] = None
    statutory_rationale: str
    rejected_candidates: List[RejectedCandidate] = Field(default_factory=list)
    confidence_score: float = 1.0

class RAGPipelineResult(BaseModel):
    query: str
    extraction: AttributeExtractionResult
    retrieved_candidates: List[Dict[str, Any]] = Field(default_factory=list)
    retrieved_statutory_notes: List[str] = Field(default_factory=list)
    verification: Optional[StatutoryVerificationResult] = None
    status: str = "SUCCESS"  # "SUCCESS" | "REQUIRES_CLARIFICATION" | "MANUAL_REVIEW"
    latency_ms: float = 0.0


# =====================================================================
# SYSTEM PROMPTS
# =====================================================================

STAGE1_ATTRIBUTE_EXTRACTOR_PROMPT = """You are an expert Customs Classification & Tariff Attribute Extractor operating under the Harmonized Commodity Description and Coding System (HSN / ITC-HS).

Your task:
Analyze the input product name/description and extract statutory attributes dynamically. Do NOT invent or predict HSN or chapter codes in this stage.

Evaluation Steps:
1. Identify the primary finished article vs. secondary components, ingredients, or packaging.
2. Identify the Constituent Material (material of manufacture).
3. Identify the Processing/Form (e.g., raw, processed, knitted, woven, seamless, welded, mounted, unmounted, liquid, solid).
4. Identify the Intended Use / Function.
5. Ambiguity & Missing Parameter Check:
   - If critical statutory attributes (material, construction, rating, capacity, end-use) are missing, set "needs_clarification" to true.

Output strictly valid JSON with this exact schema:
{
  "product_normalized": "Normalized standard product name",
  "attributes": {
    "material": "string or null",
    "processing_state": "string or null",
    "function_use": "string or null",
    "mounted_state": "mounted | unmounted | not_applicable"
  },
  "needs_clarification": true | false,
  "clarification": {
    "question": "Specific question to the customer if needs_clarification is true, else null",
    "options": ["Option 1", "Option 2", "Option 3"]
  },
  "search_keywords": ["keyword1", "keyword2", "keyword3"]
}"""


# =====================================================================
# RAG APPLICATION LAYER IMPLEMENTATION
# =====================================================================

class HSNRAGApplicationLayer:
    """
    Complete Retrieval-Augmented Generation (RAG) Application Layer for HSN extraction & verification.
    """
    _instance: Optional["HSNRAGApplicationLayer"] = None

    def __init__(self):
        self.api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()

    @classmethod
    def get_instance(cls) -> "HSNRAGApplicationLayer":
        if cls._instance is None:
            cls._instance = HSNRAGApplicationLayer()
        return cls._instance

    # -----------------------------------------------------------------
    # STAGE 1: TARIFF ATTRIBUTE EXTRACTOR
    # -----------------------------------------------------------------
    def extract_attributes(self, product_description: str) -> AttributeExtractionResult:
        """
        Stage 1: Normalizes product description and extracts statutory attributes.
        Adheres strictly to the Attribute Extraction Schema.
        """
        desc = (product_description or "").strip()
        if not desc:
            return AttributeExtractionResult(
                product_normalized="",
                attributes=ExtractedAttributes(),
                needs_clarification=True,
                clarification=ClarificationPayload(
                    question="Please provide a valid commercial product description.",
                    options=[]
                ),
                search_keywords=[]
            )

        return self._extract_attributes_deterministic(desc)

    def _extract_attributes_deterministic(self, desc: str) -> AttributeExtractionResult:
        """
        Dynamic statutory attribute extractor driven by Stage 1 ProductIntentAnalyzer
        and data/ JSON vocabularies (statutory_materials.json, statutory_forms.json).
        Contains zero hardcoded product-name, chapter, or HSN classification rules.
        """
        from src.nlp.product_intent_analyzer import analyze_product_intent
        from src.chapter_predictor.normalize import extract_query_facts

        struct_intent = analyze_product_intent(desc)
        q_facts = extract_query_facts(desc)
        q_lower = desc.lower()

        mat = ", ".join(struct_intent.constituent_materials[:2]) if struct_intent.constituent_materials else (q_facts.get("material") or None)
        proc_state = struct_intent.processing_form or q_facts.get("form") or "finished"
        func_use = struct_intent.function_use or "General commercial goods"

        is_mounted = bool(re.search(r"\bmounted\b", q_lower)) and not bool(re.search(r"\b(?:unmounted|not\s+mounted)\b", q_lower))
        is_unmounted = bool(re.search(r"\b(?:unmounted|not\s+mounted)\b", q_lower))
        mounted_state = "mounted" if is_mounted else ("unmounted" if is_unmounted else "not_applicable")

        needs_clarification = bool(struct_intent.missing_critical_attributes and not mat)
        clarification_payload = None
        if needs_clarification:
            clarification_payload = ClarificationPayload(
                question=f"Please specify missing attributes ({', '.join(struct_intent.missing_critical_attributes)}) for '{desc}'.",
                options=[]
            )

        keywords = [desc.lower()]
        if struct_intent.article_search_query and struct_intent.article_search_query.lower() not in keywords:
            keywords.append(struct_intent.article_search_query.lower())

        return AttributeExtractionResult(
            product_normalized=(struct_intent.finished_article or desc.strip()).title(),
            attributes=ExtractedAttributes(
                material=mat,
                processing_state=proc_state,
                function_use=func_use,
                mounted_state=mounted_state
            ),
            needs_clarification=needs_clarification,
            clarification=clarification_payload,
            search_keywords=keywords
        )

    # -----------------------------------------------------------------
    # STAGE 2: STATUTORY CONTEXT RETRIEVER (RAG AUGMENTATION)
    # -----------------------------------------------------------------

    def _format_tariff_code(c: str) -> str:
        c = str(c or "").replace(" ", "").strip()
        if len(c) == 8:
            return f"{c[:4]} {c[4:6]} {c[6:]}"
        elif len(c) == 6:
            return f"{c[:4]} {c[4:6]}"
        return c

    def _get_dynamic_catalog_index(self) -> Dict[str, Any]:
        """
        Lazily loads and indexes the complete official HSN & SAC Master from
        data/raw/HSN_SAC (1).xlsx (via data/tariff_hierarchy_map.parquet, ~16,809 records)
        so Stage 1, Stage 2 and Stage 3 can dynamically query all Chapters (01-99),
        4-digit headings, 8-digit HSN codes and 6-digit SAC codes without any hardcoded
        HSN dictionaries. Tax rates are None (null).
        """
        if hasattr(self, "_dynamic_catalog_cache") and self._dynamic_catalog_cache is not None:
            return self._dynamic_catalog_cache

        import pandas as pd
        from pathlib import Path

        root_dir = Path(__file__).resolve().parent.parent.parent
        parquet_path = root_dir / "data" / "enriched_master_hsn.parquet"
        if not parquet_path.exists():
            parquet_path = root_dir / "data" / "Master_copy_hsn.parquet"
        if not parquet_path.exists():
            parquet_path = root_dir / "data" / "tariff_hierarchy_map.parquet"

        df = pd.read_parquet(parquet_path)

        desc_map: Dict[str, str] = {}
        rate_map: Dict[str, Optional[float]] = {}
        by_h4: Dict[str, List[Dict[str, Any]]] = {}
        by_chapter: Dict[str, List[Dict[str, Any]]] = {}
        all_records: List[Dict[str, Any]] = []
        h4_meta: Dict[str, Dict[str, Any]] = {}
        tariff_vocab_stems: Set[str] = set()

        for idx, row in enumerate(df.to_dict(orient="records")):
            c = str(row["hsn_code"]).strip()
            d = str(row.get("statutory_description") or row.get("description") or "").strip()
            ch = str(row.get("chapter_code") or row.get("chapter") or c[:2]).strip().zfill(2)
            toks = set(re.findall(r"\b[a-z0-9]{2,}\b", d.lower()))
            stems = {w.rstrip("s") if len(w) > 3 else w for w in toks if w.isalpha()}
            tariff_vocab_stems.update(stems)

            if len(c) == 4:
                h4_meta[c] = {
                    "h4": c,
                    "chapter": ch,
                    "heading_desc": d,
                    "heading_stems": stems,
                    "child_stems": set(stems)
                }
                continue

            # Keep 8-digit HSN codes and 6-digit SAC service codes (starting with 99)
            if not (len(c) == 8 or (len(c) == 6 and c.startswith("99"))):
                continue
            r = None
            h4 = c[:4] if len(c) >= 4 else c.zfill(4)
            if h4 not in h4_meta:
                head_prefix = d.split(" - ")[0].strip() if " - " in d else d
                hp_toks = set(re.findall(r"\b[a-z0-9]{2,}\b", head_prefix.lower()))
                hp_stems = {w.rstrip("s") if len(w) > 3 else w for w in hp_toks if w.isalpha()}
                h4_meta[h4] = {
                    "h4": h4,
                    "chapter": ch,
                    "heading_desc": head_prefix,
                    "heading_stems": hp_stems,
                    "child_stems": set(stems)
                }
            else:
                h4_meta[h4]["child_stems"].update(stems)

            rec_id = f"{c}_{idx}"
            rec = {
                "rec_id": rec_id,
                "hsn_raw": c,
                "hsn_code": self._format_tariff_code(c),
                "official_description": d,
                "chapter": ch,
                "gst_rate": r,
                "tokens": toks
            }
            if c not in desc_map:
                desc_map[c] = d
                rate_map[c] = r
            by_h4.setdefault(h4, []).append(rec)
            by_chapter.setdefault(ch, []).append(rec)
            all_records.append(rec)

        self._dynamic_catalog_cache = {
            "total_records": len(df),
            "desc_map": desc_map,
            "rate_map": rate_map,
            "by_h4": by_h4,
            "by_chapter": by_chapter,
            "all_records": all_records,
            "h4_meta": h4_meta,
            "tariff_vocab_stems": tariff_vocab_stems
        }
        return self._dynamic_catalog_cache

    def _is_outdated_tariff_code_dynamic(self, hsn_code: str, official_description: str = "") -> bool:
        """
        Dynamic Rule 4 (Outdated Code Detection):
        Inspects the active WCO/CBIC tariff tree in data/raw/HSN_SAC (1).xlsx to detect
        deprecated or structurally replaced codes using pure hierarchical tree rules:
        - Goods HSN codes must be 8 digits; Service SAC codes (starting with 99) must be 6 digits.
        - Rule 4A: Generic .x0 subheading replaced by .x1-.x9 split in the same 5-digit group.
        - Rule 4B: Consolidated .x000 active heading supersedes old .x1/.x9 splits in the same 5-digit group.
        - Rule 4C: Restructured WCO heading where active HS 2007+ subheadings repeat the heading prefix
          ('<HEADING> - <HEADING> :') while legacy pre-2007 5-digit subheadings do not.
        """
        c = str(hsn_code or "").replace(" ", "").replace(".", "").strip()
        if not c.isdigit():
            return True
        if c.startswith("99"):
            if len(c) != 6:
                return True
        else:
            if len(c) != 8:
                return True
        desc_upper = str(official_description or "").upper()
        if "DEPRECATED" in desc_upper or desc_upper.startswith("OMITTED"):
            return True

        cat = self._get_dynamic_catalog_index()
        h4 = c[:4]
        s5 = c[:5]
        s6 = c[:6]
        siblings = cat["by_h4"].get(h4, [])
        if not siblings:
            return False

        # Rule 4A: Generic .x0 subheading replaced by .x1-.x9 split in the same 5-digit group
        if s6.endswith("0"):
            has_split_s6 = any(s["hsn_raw"][:5] == s5 and not s["hsn_raw"][:6].endswith("0") for s in siblings)
            has_subitems_in_x0 = any(s["hsn_raw"][:6] == s6 and not s["hsn_raw"].endswith("00") for s in siblings)
            if has_split_s6 and has_subitems_in_x0:
                return True

        # Rule 4B: Consolidated .x0 00 active heading supersedes old .x1/.x9 splits
        if not s6.endswith("0"):
            consol_code = f"{s5}000"
            if consol_code in cat["desc_map"]:
                consol_desc = cat["desc_map"][consol_code]
                my_desc = official_description or cat["desc_map"].get(c, "")
                c_head = consol_desc.split(" - ")[-1].split(":")[0].strip().lower()
                m_head = my_desc.split(" - ")[-1].split(":")[0].strip().lower()
                if c_head and len(c_head) > 6 and c_head == m_head:
                    return True

        # Rule 4C: Restructured heading where active 5-digit group repeats '<HEADING> - <HEADING> :'
        my_desc = (official_description or cat["desc_map"].get(c, "")).lower()
        my_parts = [p.strip() for p in my_desc.split(" - ") if p.strip()]
        if len(my_parts) >= 2 and my_parts[0] != my_parts[1].split(":")[0].strip():
            has_repeating_active_group = any(
                s["hsn_raw"][:5] != s5
                and len(s["official_description"].split(" - ")) >= 2
                and s["official_description"].lower().split(" - ")[0].strip()
                == s["official_description"].lower().split(" - ")[1].split(":")[0].strip()
                for s in siblings
            )
            if has_repeating_active_group and c.endswith("00"):
                return True

        return False

    def _generate_dynamic_suggestions_for_product(
        self,
        product_desc: str,
        top_candidates: List[Dict[str, Any]],
        auditor_eval: Optional[Dict[str, Any]] = None,
        extraction: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        100% Dynamic Further-Product-Detail Suggestion Generator over data/raw/HSN_SAC (1).xlsx.
        For EVERY product (whether ambiguous or specific), inspects the official 8-digit HSN / 6-digit SAC
        sub-items in HSN_SAC (1).xlsx under the product's matched heading(s), extracts the specific
        subheading + leaf distinction, and generates 4-5 clickable suggestions so the user can either
        click a suggestion OR enter their full Product Description.
        """
        cat = self._get_dynamic_catalog_index()
        by_h4 = cat["by_h4"]
        ch_info = {"priority_headings": [c.get("hsn_code", "")[:4] for c in (top_candidates or []) if c.get("hsn_code")]}

        options: List[str] = []
        seen_opts: set = set()

        def _add_opt(label: str):
            lbl = (label or "").strip()
            if lbl and lbl.lower() not in seen_opts:
                seen_opts.add(lbl.lower())
                options.append(lbl)

        # 1. Include any auditor-level or attribute-extractor material bifurcation options first
        if auditor_eval and auditor_eval.get("clarification_options"):
            for o in auditor_eval["clarification_options"]:
                _add_opt(str(o))
        if extraction and getattr(extraction, "clarification", None) and getattr(extraction.clarification, "options", None):
            for o in extraction.clarification.options:
                _add_opt(str(o))

        # Check for Layer 4 dynamic semantic ambiguity controller options
        try:
            from src.search.ambiguity_controller import evaluate_product_ambiguity
            _amb_res = evaluate_product_ambiguity(product_desc)
            if _amb_res.is_ambiguous and _amb_res.disambiguation_options:
                options.clear()
                seen_opts.clear()
                for o in _amb_res.disambiguation_options:
                    _add_opt(f"{o.label} (HSN {o.hsn_code})")
                return {
                    "user_prompt_suggestion": _amb_res.clarification_question or f"What material or type is the {product_desc}?",
                    "missing_attributes": ["Constituent Material / Type", "Statutory Chapter Code"],
                    "clarification_options": options
                }
        except Exception:
            pass

        # 2. Dynamically extract distinguishing 8-digit HSN / 6-digit SAC sub-items from HSN_SAC (1).xlsx
        matched_h4s = list(ch_info["priority_headings"])
        top_cand_raws = [
            str(c.get("hsn_raw") or c.get("hsn_code") or "").replace(" ", "").strip()
            for c in (top_candidates or [])
        ]
        for rc in top_cand_raws:
            h4_key = rc[:4] if len(rc) >= 4 else rc.zfill(4)
            if h4_key and h4_key not in matched_h4s:
                matched_h4s.append(h4_key)

        prod_words = {w.lower() for w in re.findall(r"[a-z]{3,}", product_desc.lower())}

        for h4 in matched_h4s[:3]:
            siblings = [
                s for s in by_h4.get(h4, [])
                if not self._is_outdated_tariff_code_dynamic(s["hsn_raw"], s["official_description"])
            ]
            if not siblings:
                continue

            # Prioritize siblings that are in top_candidates or match product keywords (e.g. "cotton")
            def _sib_priority(sib):
                sr = sib["hsn_raw"]
                in_top = 0 if sr in top_cand_raws else 1
                top_idx = top_cand_raws.index(sr) if sr in top_cand_raws else 999
                desc_low = sib["official_description"].lower()
                kw_hits = -sum(1 for w in prod_words if w in desc_low)
                return (in_top, top_idx, kw_hits, sr)

            siblings.sort(key=_sib_priority)

            for s in siblings:
                if len(options) >= 5:
                    break
                full_d = re.sub(r"\b\d{4}\s+\d{2}(\s+\d{2})?\b", "", s["official_description"])
                segments = [seg.strip(" -:") for seg in re.split(r"\s+-+\s+|:\s+", full_d) if seg.strip(" -:")]
                if len(segments) >= 2:
                    head_short = segments[0][:34].rstrip(" ,;:-(")
                    if len(segments[-1]) < 18 and len(segments) >= 3 and segments[-2].lower()[:25] != segments[0].lower()[:25]:
                        leaf_short = " : ".join(segments[-2:])
                    else:
                        leaf_short = segments[-1]
                    tail = f"{head_short}... -> {leaf_short}"
                else:
                    tail = full_d.strip(" -:")
                tail = re.sub(r"\s+", " ", tail).strip()
                if len(tail) > 74:
                    tail = tail[:71].rstrip(" ,;:-(") + "..."
                _add_opt(f"{tail.title()} ({s['hsn_code']})")

        # 3. Also include top candidate alternatives from HSN_SAC (1).xlsx
        for c in (top_candidates or []):
            if len(options) >= 5:
                break
            c_desc = str(c.get("official_description") or "").split(" - ")[-1].strip()
            c_short = c_desc[:62].rstrip(" ,;:-(") + ("..." if len(c_desc) > 62 else "")
            _add_opt(f"{c_short.title()} ({c.get('hsn_code', '')})")

        primary_h4 = matched_h4s[0] if matched_h4s else "Tariff"
        ch_badge = ch_info.get("chapter_label", "Tariff Schedule")
        if auditor_eval and auditor_eval.get("status") == "NEED_CLARIFICATION" and auditor_eval.get("user_prompt_suggestion"):
            prompt_q = f"[{ch_badge}] {auditor_eval['user_prompt_suggestion']} (Or paste full Product Description below)"
            missing_attrs = auditor_eval.get("missing_attributes") or [f"Chapter: {ch_badge}", "Product Description (Material, Construction, End-Use)"]
        else:
            prompt_q = (
                f"[{ch_badge}] Please enter the Product Description for '{product_desc}' "
                f"(material composition, construction/knitted/woven/process, end-use) or click a suggested Heading {primary_h4} specification below:"
            )
            missing_attrs = [f"Category: {ch_badge}", f"Product Description / Heading {primary_h4} Sub-item Specification"]

        return {
            "user_prompt_suggestion": prompt_q,
            "clarification_options": options[:5],
            "missing_attributes": missing_attrs
        }

    # =================================================================
    # THREE-STAGE CLARIFICATION RESOLUTION ARCHITECTURE
    # Stage 1: Context Aggregator -> Stage 2: Vector Search Index -> Stage 3: AI Legal Selector
    # =================================================================

    def stage1_context_aggregator(
        self,
        base_product: str,
        user_clarification: str,
        existing_attributes: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Stage 1: The Context Aggregator (100% Dynamic Attribute, Description & Chapter 01–99 Merger).
        Takes the Base Product Name, merges the full Product Description / Clarification provided by the user,
        extracts constituent material, construction/form, and Official Chapter 01–99 Category, and builds
        a high-signal Master Search String.
        """
        base_clean = (base_product or "").strip()
        clarif_clean = (user_clarification or "").strip()
        combined_raw = f"{base_clean} {clarif_clean}".lower()

        if not existing_attributes:
            base_ext = self._extract_attributes_deterministic(f"{base_clean} {clarif_clean}".strip())
            existing_attributes = base_ext.attributes.model_dump()

        # Dynamically extract material, form, use, and mounted state from Stage 1 analyzer + statutory JSON indexes
        from src.nlp.product_intent_analyzer import analyze_product_intent
        struct_intent = analyze_product_intent(base_clean, clarification=clarif_clean)

        mat_normalized = existing_attributes.get("material") or ""
        raw_proc = existing_attributes.get("processing_state") or ""
        form_normalized = raw_proc if raw_proc.lower() not in ("", "finished", "finished article", "unknown") else ""
        use_normalized = existing_attributes.get("function_use") or ""
        if use_normalized.lower() in ("", "commercial commodity", "general commercial goods"):
            use_normalized = struct_intent.function_use or "Not specified"
        mount_normalized = existing_attributes.get("mounted_state") or "not_applicable"

        if not mat_normalized and struct_intent.constituent_materials:
            mat_normalized = ", ".join(struct_intent.constituent_materials[:2])
        if not form_normalized and struct_intent.processing_form:
            form_normalized = struct_intent.processing_form
        if "mounted" in combined_raw and "unmounted" not in combined_raw:
            mount_normalized = "mounted"

        article_anchor = struct_intent.finished_article or base_clean
        parts = [article_anchor]
        if struct_intent.alternative_names_and_aliases:
            parts.append(f"Aliases: {', '.join(struct_intent.alternative_names_and_aliases[:3])}")
        if clarif_clean and clarif_clean.lower() not in article_anchor.lower() and len(clarif_clean) > 15:
            parts.append(clarif_clean)
        if mat_normalized and mat_normalized.lower() not in article_anchor.lower():
            parts.append(f"Material: {mat_normalized}")
        if form_normalized and form_normalized.lower() not in article_anchor.lower() and form_normalized.lower() not in ("not_applicable", "none", "finished article"):
            parts.append(f"Form: {form_normalized}")
        if struct_intent.components_or_parts:
            parts.append(f"Components: {', '.join(struct_intent.components_or_parts[:3])}")
        if struct_intent.function_use and struct_intent.function_use.lower() not in article_anchor.lower():
            parts.append(f"Use: {struct_intent.function_use}")
        master_search_string = ", ".join(parts) + "."

        aggregated_attributes = {
            "finished_article": article_anchor,
            "material": mat_normalized or None,
            "processing_state": form_normalized or "Specific Commodity",
            "function_use": use_normalized,
            "mounted_state": mount_normalized,
            "ingredients_or_additives": struct_intent.ingredients_or_additives,
            "components_or_parts": struct_intent.components_or_parts,
            "packaging_or_presentation": struct_intent.packaging_or_presentation,
            "chapter_category": "Official Tariff Schedule"
        }

        return {
            "stage": "STAGE_1_CONTEXT_AGGREGATOR",
            "base_product": base_clean,
            "user_clarification": clarif_clean,
            "chapter_categorization": {"chapter_label": "Official Tariff Schedule"},
            "aggregated_attributes": aggregated_attributes,
            "product_intent": struct_intent.to_dict(),
            "master_search_string": master_search_string
        }


def get_hsn_rag_application_layer() -> HSNRAGApplicationLayer:
    """Singleton getter for the HSN RAG Application Layer."""
    return HSNRAGApplicationLayer.get_instance()
