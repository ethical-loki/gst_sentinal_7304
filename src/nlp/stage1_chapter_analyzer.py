"""
src/nlp/stage1_chapter_analyzer.py
==================================
Dynamic Stage 1 Statutory Chapter Identification & Canonical Stage 1 Result Builder.

Uses `data/enriched_master_hsn.parquet` dynamically for official chapter codes,
official chapter titles, and statutory heading/article/material vocabulary.
Zero hardcoded product-to-chapter or product-to-HSN mappings.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import pandas as pd

from src.nlp.product_intent_analyzer import ProductIntentStructure, analyze_product_intent

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_MASTER_PARQUET = ROOT_DIR / "data" / "enriched_master_hsn.parquet"

_STOP = {
    "and", "or", "of", "the", "for", "with", "in", "on", "to", "from", "by",
    "a", "an", "as", "not", "other", "thereof", "articles", "parts", "goods",
    "whether", "including", "excluding", "kind", "used", "such", "similar",
}

_CHAPTER_INDEX_CACHE: Optional[List[Dict[str, Any]]] = None


def _tok(text: str) -> Set[str]:
    if not text:
        return set()
    clean = (
        text.lower()
        .replace("fibre", "fiber")
        .replace("tyre", "tire")
        .replace("aluminium", "aluminum")
        .replace("stailess", "stainless")
        .replace("vaccum", "vacuum")
        .replace("digial", "digital")
    )
    words = re.findall(r"\b[a-z0-9]{2,}\b", clean)
    out: Set[str] = set()
    for w in words:
        if w in _STOP:
            continue
        if len(w) > 4 and w.endswith("ies"):
            out.add(w[:-3] + "y")
        elif len(w) > 4 and w.endswith(("sses", "ches", "shes", "xes", "zes")):
            out.add(w[:-2])
        elif len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is", "os", "lens")):
            out.add(w[:-1])
        else:
            out.add(w)
    return out


def load_statutory_chapter_index(parquet_path: Path = DEFAULT_MASTER_PARQUET) -> List[Dict[str, Any]]:
    """Loads official chapter titles and statutory chapter vocabularies from enriched_master_hsn.parquet."""
    global _CHAPTER_INDEX_CACHE
    if _CHAPTER_INDEX_CACHE is not None:
        return _CHAPTER_INDEX_CACHE

    if not parquet_path.exists():
        logger.warning(f"Master parquet not found at {parquet_path}; returning empty chapter index.")
        _CHAPTER_INDEX_CACHE = []
        return _CHAPTER_INDEX_CACHE

    from src.ml.candidate_evidence_evaluator import extract_statutory_subject_text
    df = pd.read_parquet(parquet_path)
    chapters: List[Dict[str, Any]] = []
    for ch_val, grp in df.groupby(df["chapter_code"].astype(str).str.zfill(2)):
        titles = [str(t).strip() for t in grp["chapter_title"].dropna().unique() if str(t).strip()]
        ch_title = titles[0] if titles else f"Chapter {ch_val}"
        title_toks = _tok(ch_title)

        h4_texts = [
            extract_statutory_subject_text(t)
            for t in (grp["heading_4digit_desc"].dropna().astype(str).unique().tolist() if "heading_4digit_desc" in grp.columns else [])
        ]
        art_texts = grp["article_keywords"].dropna().astype(str).unique().tolist() if "article_keywords" in grp.columns else []
        mat_texts = grp["material_keywords"].dropna().astype(str).unique().tolist() if "material_keywords" in grp.columns else []
        stat_texts = [
            extract_statutory_subject_text(t)
            for t in (grp["statutory_description"].dropna().astype(str).unique().tolist() if "statutory_description" in grp.columns else [])
        ]

        heading_toks = _tok(" ".join(h4_texts))
        article_toks = _tok(" ".join(art_texts)) | _tok(" ".join(stat_texts))
        material_toks = _tok(" ".join(mat_texts))

        chapters.append({
            "chapter_code": str(ch_val).zfill(2),
            "chapter_title": ch_title,
            "title_tokens": title_toks,
            "heading_tokens": heading_toks,
            "article_tokens": article_toks,
            "material_tokens": material_toks,
            "record_count": int(len(grp)),
        })

    chapters.sort(key=lambda x: x["chapter_code"])
    _CHAPTER_INDEX_CACHE = chapters
    return _CHAPTER_INDEX_CACHE


def identify_relevant_chapters(
    product_intent: ProductIntentStructure,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """
    Dynamically identifies candidate tariff chapters by comparing structured product intent
    against official statutory chapter titles and chapter-level heading/article/material data.
    Never forces a single chapter when multiple chapters are plausible.
    """
    index = load_statutory_chapter_index()
    if not index:
        return []

    raw_art_toks = _tok(product_intent.finished_article) | _tok(" ".join(product_intent.alternative_names_and_aliases))
    head_toks = _tok(getattr(product_intent, "product_head_noun", "") or "")
    mat_toks = _tok(" ".join(product_intent.constituent_materials))
    # Exclude explicit constituent-material tokens (unless also the head noun) from article tokens
    # so raw-material chapters do not double-score finished goods queries in title matching.
    art_toks = (raw_art_toks - (mat_toks - head_toks)) or raw_art_toks
    fn_toks = _tok(product_intent.function_use or "")
    proc_toks = _tok(product_intent.processing_form or "")
    comp_toks = _tok(" ".join(product_intent.components_or_parts))

    scored: List[Dict[str, Any]] = []
    for ch in index:
        t_hits = sorted(art_toks & ch["title_tokens"])
        h_hits = sorted(art_toks & ch["heading_tokens"])
        a_hits = sorted(art_toks & ch["article_tokens"])
        head_t_hits = head_toks & ch["title_tokens"]
        head_h_hits = head_toks & ch["heading_tokens"]
        head_a_hits = head_toks & ch["article_tokens"]
        m_title_hits = sorted(mat_toks & ch["title_tokens"])
        m_hits = sorted(mat_toks & ch["material_tokens"])
        f_hits = sorted(fn_toks & (ch["heading_tokens"] | ch["article_tokens"]))
        p_hits = sorted(proc_toks & (ch["title_tokens"] | ch["heading_tokens"]))

        raw_score = (
            3.0 * len(t_hits)
            + 2.2 * len(h_hits)
            + 1.5 * len(a_hits)
            + 3.5 * len(head_t_hits)
            + 2.5 * len(head_h_hits)
            + 1.5 * len(head_a_hits)
            + 2.0 * len(m_title_hits)
            + 0.8 * len(m_hits)
            + 1.0 * len(f_hits)
            + 0.8 * len(p_hits)
        )
        if raw_score <= 0:
            continue

        supporting: List[str] = []
        why_parts: List[str] = []
        if t_hits or h_hits or a_hits:
            matched_art = sorted(set(t_hits + h_hits + a_hits))[:5]
            supporting.append(f"article_match: {', '.join(matched_art)}")
            why_parts.append(f"Product article terms ({', '.join(matched_art)}) match statutory headings in Chapter {ch['chapter_code']}")
        if m_title_hits or m_hits:
            matched_mat = sorted(set(m_title_hits + m_hits))[:4]
            supporting.append(f"material_match: {', '.join(matched_mat)}")
            why_parts.append(f"Constituent material ({', '.join(matched_mat)}) aligns with Chapter {ch['chapter_code']}")
        if f_hits:
            supporting.append(f"function_match: {', '.join(f_hits[:4])}")
            why_parts.append(f"Function cues ({', '.join(f_hits[:4])}) appear in Chapter {ch['chapter_code']} descriptions")
        if p_hits:
            supporting.append(f"process_match: {', '.join(p_hits[:3])}")

        limiting: List[str] = []
        if product_intent.missing_critical_attributes:
            limiting.append(f"Missing critical attribute(s): {', '.join(product_intent.missing_critical_attributes)}")
        if comp_toks & ch["heading_tokens"] and not (art_toks & ch["heading_tokens"]):
            limiting.append("Match driven partly by component/subassembly terminology; verify complete article vs. parts")

        # Normalize score to (0, 0.96] confidence
        conf = round(min(0.96, raw_score / (raw_score + 4.5)), 4)
        uncertainty = (
            "Multiple chapters remain plausible or critical attributes are unstated; confirm in Stage 2/3."
            if (limiting or conf < 0.75)
            else "Strong statutory overlap with official chapter scope; verify exact 8-digit leaf in Stage 2/3."
        )

        scored.append({
            "chapter_code": ch["chapter_code"],
            "chapter_title": ch["chapter_title"],
            "relevance_score": round(raw_score, 3),
            "confidence": conf,
            "why_relevant": "; ".join(why_parts) if why_parts else f"Lexical overlap with Chapter {ch['chapter_code']}",
            "supporting_attributes": supporting,
            "limiting_or_contradictory_evidence": limiting,
            "uncertainty_note": uncertainty,
        })

    scored.sort(key=lambda x: (-x["relevance_score"], x["chapter_code"]))
    return scored[:max(1, top_k)]


def build_canonical_stage1_result(
    description: str,
    clarification: str = "",
    product_intent: Optional[ProductIntentStructure] = None,
) -> Dict[str, Any]:
    """
    Produces the single canonical serializable Stage 1 object for UI display and
    one-click handoff into Stage 2.
    """
    pi = product_intent or analyze_product_intent(description, clarification=clarification)
    chapters = identify_relevant_chapters(pi, top_k=5)

    explicit_attrs = [a for a in pi.attributes if a.get("evidence_type") == "EXPLICIT"]
    inferred_attrs = [a for a in pi.attributes if a.get("evidence_type") == "INFERRED"]

    if not pi.finished_article:
        stage1_status = "INSUFFICIENT_PRODUCT_IDENTITY"
    elif len(chapters) > 1 or pi.missing_critical_attributes:
        stage1_status = "AMBIGUOUS_OR_INCOMPLETE"
    elif chapters:
        stage1_status = "READY_FOR_STAGE_2"
    else:
        stage1_status = "NO_ACTIVE_CHAPTER_MATCH"

    stage2_repr = dict(pi.stage2_search_representation or {})
    stage2_repr["guided_chapters"] = [c["chapter_code"] for c in chapters]

    return {
        "stage": "STAGE_1",
        "stage1_status": stage1_status,
        "original_description": description,
        "normalized_description": pi.finished_article,
        "product_intent": pi.to_dict(),
        "primary_commercial_article": pi.finished_article,
        "product_head_noun": pi.product_head_noun,
        "alternative_names_and_aliases": list(pi.alternative_names_and_aliases),
        "article_category": pi.article_category,
        "materials_and_composition": {
            "constituent_materials": list(pi.constituent_materials),
            "ingredients_or_additives": list(pi.ingredients_or_additives),
            "scope_note": "Material applies to primary article unless attached to a named component",
        },
        "components_and_relationships": {
            "components_or_parts": list(pi.components_or_parts),
            "packaging_or_presentation": pi.packaging_or_presentation,
            "relationship_graph": list(pi.relationship_graph),
        },
        "characteristics": {
            "physical_form": pi.product_form,
            "processing_state": pi.processing_form,
            "function_use": pi.function_use,
            "function_details": dict(pi.function_details),
        },
        "explicit_attributes": explicit_attrs,
        "inferred_attributes": inferred_attrs,
        "missing_attributes": list(pi.missing_critical_attributes),
        "chapter_candidates": chapters,
        "confidence_and_uncertainty": {
            "intent_confidence": pi.intent_confidence,
            "field_confidences": dict(pi.field_confidences),
            "uncertainty_reasons": (
                [f"Multiple plausible chapters ({', '.join(c['chapter_code'] for c in chapters[:3])})"]
                if len(chapters) > 1
                else []
            ) + ([f"Missing attributes: {', '.join(pi.missing_critical_attributes)}"] if pi.missing_critical_attributes else []),
        },
        "stage2_search_representation": stage2_repr,
    }

