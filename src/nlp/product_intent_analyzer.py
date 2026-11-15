"""
src/nlp/product_intent_analyzer.py
==================================
Universal Stage 1 Product Intent & Attribute Relationship Analyzer.

Decomposes ANY commercial product description into:
  - finished_article: Primary commercial article being classified
  - constituent_materials: Primary structural/constituent material(s)
  - ingredients_or_additives: Secondary ingredients, seasonings, coatings, flavourings
  - components_or_parts: Sub-components, attachments, fittings, accessories
  - packaging_or_presentation: Retail packet, pouch, bulk, set, kit, etc.
  - processing_form: Manufacturing/processing state (instant, knitted, woven, welded, etc.)
  - function_use: Stated end-use or application
  - attribute_relationships: Typed lineage of how each attribute relates to the finished article
  - article_search_query: Article-first search string for Stage 2 retrieval

Design rule: 100% general linguistic + statutory-index decomposition.
Zero product-specific HSN mappings or product-name classification rules.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# General English/trade clause markers that introduce supporting attributes
# rather than the primary finished commercial article.
_INGREDIENT_MARKERS = (
    "made from",
    "made with",
    "made of",
    "prepared from",
    "prepared with",
    "containing",
    "contains",
    "seasoned with",
    "flavoured with",
    "flavored with",
    "coated with",
    "filled with",
    "stuffed with",
    "topped with",
    "enriched with",
    "with added",
)

_COMPONENT_MARKERS = (
    "fitted with",
    "equipped with",
    "incorporating",
    "integrated with",
    "complete with",
    "along with",
    "including",
    "mounted on",
    "mounted with",
    "powered by",
    "driven by",
)

_PACKAGING_MARKERS = (
    "packed in",
    "packaged in",
    "put up in",
    "put up for",
    "in a ",
    "in ",
)

_USE_MARKERS = (
    "intended for",
    "used for",
    "designed for",
    "suitable for",
    "for use in",
    "for ",
)

_PACKAGING_NOUNS = re.compile(
    r"\b(?:retail\s+pack(?:et|s|aging)?|individual\s+pack(?:et|s)?|pack(?:et|s|ing)?|"
    r"sachet(?:s)?|pouch(?:es)?|carton(?:s)?|box(?:es)?|bottle(?:s)?|jar(?:s)?|"
    r"tin(?:s)?|can(?:s)?|drum(?:s)?|bag(?:s)?|blister|bulk|kit|set)\b",
    re.IGNORECASE,
)

_GENERAL_PROCESS_CUES = (
    "instant", "pre-cooked", "precooked", "cooked", "uncooked", "raw", "roasted",
    "dried", "dehydrated", "frozen", "chilled", "smoked", "fermented",
    "knitted", "crocheted", "woven", "non-woven", "nonwoven", "felted",
    "seamless", "welded", "forged", "cast", "molded", "moulded", "extruded",
    "laminated", "coated", "galvanized", "galvanised", "plated", "anodized",
    "portable", "cordless", "automatic", "semi-automatic", "manual", "electric",
    "hydraulic", "pneumatic", "digital", "centrifugal", "rotary", "submersible",
)


@dataclass
class AttributeRelationship:
    attribute_type: str
    value: str
    role: str  # FINISHED_ARTICLE | CONSTITUENT_MATERIAL | INGREDIENT_OR_ADDITIVE | COMPONENT_OR_PART | PACKAGING_OR_PRESENTATION | PROCESSING_FORM | INTENDED_USE
    clause_source: str = "head"


@dataclass
class ProductIntentStructure:
    raw_description: str
    finished_article: str
    constituent_materials: List[str] = field(default_factory=list)
    ingredients_or_additives: List[str] = field(default_factory=list)
    components_or_parts: List[str] = field(default_factory=list)
    packaging_or_presentation: Optional[str] = None
    processing_form: Optional[str] = None
    function_use: Optional[str] = None
    attribute_relationships: List[AttributeRelationship] = field(default_factory=list)
    article_search_query: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_description": self.raw_description,
            "finished_article": self.finished_article,
            "constituent_materials": list(self.constituent_materials),
            "ingredients_or_additives": list(self.ingredients_or_additives),
            "components_or_parts": list(self.components_or_parts),
            "packaging_or_presentation": self.packaging_or_presentation,
            "processing_form": self.processing_form,
            "function_use": self.function_use,
            "attribute_relationships": [asdict(r) for r in self.attribute_relationships],
            "article_search_query": self.article_search_query,
        }


def _paren_depth_mask(text: str) -> List[bool]:
    """Returns a per-character boolean mask: True when inside parentheses (...)."""
    mask: List[bool] = []
    depth = 0
    for ch in text:
        if ch == "(":
            depth += 1
            mask.append(True)
        elif ch == ")":
            mask.append(depth > 0)
            if depth > 0:
                depth -= 1
        else:
            mask.append(depth > 0)
    return mask


def _split_top_level_clauses(text: str) -> Tuple[str, List[Tuple[str, str]]]:
    """
    Splits a commercial description into:
      1. The leading head phrase (candidate finished article + direct modifiers)
      2. A list of (marker, trailing_clause_text) tuples in order of appearance.
    Never splits inside balanced parentheses (e.g. "(for example, ...)").
    """
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if not cleaned:
        return "", []

    all_markers = sorted(
        set(_INGREDIENT_MARKERS + _COMPONENT_MARKERS + _PACKAGING_MARKERS + _USE_MARKERS + ("with",)),
        key=len,
        reverse=True,
    )
    pattern = re.compile(
        r"\b(" + "|".join(re.escape(m.strip()) for m in all_markers) + r")\b",
        re.IGNORECASE,
    )

    in_paren = _paren_depth_mask(cleaned)
    matches = [m for m in pattern.finditer(cleaned) if not in_paren[m.start()]]
    if not matches:
        return cleaned, []

    head = cleaned[: matches[0].start()].strip(" ,;-")
    clauses: List[Tuple[str, str]] = []
    for idx, m in enumerate(matches):
        start_val = m.end()
        end_val = matches[idx + 1].start() if idx + 1 < len(matches) else len(cleaned)
        marker = m.group(1).lower().strip()
        val = cleaned[start_val:end_val].strip(" ,;-")
        if val:
            clauses.append((marker, val))

    # If head became empty (e.g. query starts with "for ..." or "in ..."), keep full text as head
    if not head:
        head = cleaned
    return head, clauses


def _split_items(clause_text: str) -> List[str]:
    parts = re.split(r"\s*(?:,|&|\band\b|\bplus\b)\s*", clause_text, flags=re.IGNORECASE)
    return [p.strip(" .;") for p in parts if p and p.strip(" .;")]


def analyze_product_intent(description: str, clarification: str = "") -> ProductIntentStructure:
    """
    Universally decomposes a product description (and optional user clarification)
    into finished_article vs supporting materials, ingredients, components, and packaging.
    """
    raw = (description or "").strip()
    clar = (clarification or "").strip()
    combined = f"{raw} {clar}".strip() if clar else raw
    if not combined:
        return ProductIntentStructure(raw_description="", finished_article="")

    head, clauses = _split_top_level_clauses(combined)

    constituent_materials: List[str] = []
    ingredients_or_additives: List[str] = []
    components_or_parts: List[str] = []
    packaging_parts: List[str] = []
    use_parts: List[str] = []
    relationships: List[AttributeRelationship] = []

    # Check head against dynamic statutory material & fact indexes if available
    head_facts: Dict[str, Any] = {}
    try:
        from src.chapter_predictor.normalize import extract_query_facts
        head_facts = extract_query_facts(head)
    except Exception:
        head_facts = {}

    if head_facts.get("material"):
        mat = str(head_facts["material"]).strip()
        if mat and mat not in constituent_materials:
            constituent_materials.append(mat)
            relationships.append(AttributeRelationship("material", mat, "CONSTITUENT_MATERIAL", "head"))

    # Classify each trailing clause by its grammatical marker & content
    for marker, val in clauses:
        m_low = marker.lower()
        if any(m_low == mk.strip() for mk in _USE_MARKERS):
            use_parts.append(val)
            relationships.append(AttributeRelationship("intended_use", val, "INTENDED_USE", marker))
        elif any(m_low == mk.strip() for mk in _PACKAGING_MARKERS) or _PACKAGING_NOUNS.search(val):
            # Distinguish packaging ("in retail packet") from material/component
            if _PACKAGING_NOUNS.search(val) or m_low in ("packed in", "packaged in", "put up in", "put up for"):
                packaging_parts.append(val)
                relationships.append(AttributeRelationship("packaging", val, "PACKAGING_OR_PRESENTATION", marker))
            elif m_low in ("in", "in a"):
                # e.g. "in stainless steel" -> constituent material
                for item in _split_items(val):
                    if item not in constituent_materials:
                        constituent_materials.append(item)
                        relationships.append(AttributeRelationship("material", item, "CONSTITUENT_MATERIAL", marker))
        elif any(m_low == mk.strip() for mk in _COMPONENT_MARKERS):
            for item in _split_items(val):
                if _PACKAGING_NOUNS.search(item):
                    packaging_parts.append(item)
                    relationships.append(AttributeRelationship("packaging", item, "PACKAGING_OR_PRESENTATION", marker))
                elif item not in components_or_parts:
                    components_or_parts.append(item)
                    relationships.append(AttributeRelationship("component", item, "COMPONENT_OR_PART", marker))
        elif any(m_low == mk.strip() for mk in _INGREDIENT_MARKERS):
            # "made from/of X" can be primary constituent material (e.g. "made of stainless steel")
            # or base ingredient (e.g. "made from wheat flour")
            for item in _split_items(val):
                if m_low in ("made of", "made from", "made with"):
                    if item not in constituent_materials:
                        constituent_materials.append(item)
                        relationships.append(AttributeRelationship("material_or_base", item, "CONSTITUENT_MATERIAL", marker))
                else:
                    if item not in ingredients_or_additives:
                        ingredients_or_additives.append(item)
                        relationships.append(AttributeRelationship("ingredient_or_additive", item, "INGREDIENT_OR_ADDITIVE", marker))
        elif m_low == "with":
            for item in _split_items(val):
                if _PACKAGING_NOUNS.search(item):
                    packaging_parts.append(item)
                    relationships.append(AttributeRelationship("packaging", item, "PACKAGING_OR_PRESENTATION", marker))
                else:
                    # "with X" could be an additive/seasoning or an attached component/feature
                    if item not in ingredients_or_additives:
                        ingredients_or_additives.append(item)
                        relationships.append(AttributeRelationship("accompanying_attribute", item, "INGREDIENT_OR_ADDITIVE", marker))

    # Extract processing form cues from combined description (head prioritized)
    proc_found: List[str] = []
    if head_facts.get("form"):
        proc_found.append(str(head_facts["form"]).strip())
    low_head = head.lower()
    for cue in _GENERAL_PROCESS_CUES:
        if re.search(rf"\b{re.escape(cue)}\b", low_head):
            if cue not in [p.lower() for p in proc_found]:
                proc_found.append(cue)

    processing_form = ", ".join(proc_found) if proc_found else None
    if processing_form:
        relationships.append(AttributeRelationship("processing_form", processing_form, "PROCESSING_FORM", "head"))

    # Clean balanced parenthetical examples/qualifiers/material notes from head
    # without truncating at an opening parenthesis.
    clean_head = head.strip()
    paren_spans = list(re.finditer(r"\(([^()]+)\)", clean_head))
    if paren_spans:
        kept_parts: List[str] = []
        last_idx = 0
        for pm in paren_spans:
            kept_parts.append(clean_head[last_idx:pm.start()])
            inner = pm.group(1).strip()
            inner_low = inner.lower()
            is_example_or_excl = bool(
                re.match(r"^(?:for\s+example|e\.g\.|such\s+as|including|other\s+than)\b", inner_low)
            )
            is_trailing = pm.end() == len(clean_head)
            if is_example_or_excl:
                relationships.append(
                    AttributeRelationship("qualifier_or_example", inner, "QUALIFIER_OR_EXAMPLE", "parenthetical")
                )
            elif is_trailing:
                if inner not in constituent_materials:
                    constituent_materials.append(inner)
                relationships.append(
                    AttributeRelationship("material_or_note", inner, "CONSTITUENT_MATERIAL", "parenthetical")
                )
            else:
                kept_parts.append(pm.group(0))
            last_idx = pm.end()
        kept_parts.append(clean_head[last_idx:])
        clean_head = re.sub(r"\s+", " ", "".join(kept_parts)).strip(" ,;-")

    # If head is a multi-segment statutory chain ("HEADING, A, B, C - SPECIFIC ARTICLE - OF MATERIAL"),
    # focus finished_article on the specific article segment when the first segment is a broad list.
    if " - " in clean_head:
        segs = [s.strip(" ,;") for s in clean_head.split(" - ") if s.strip(" ,;")]
        if len(segs) >= 2 and segs[0].count(",") >= 3:
            _qualifier_prefix = re.compile(
                r"^(?:of\s+|other\b|parts\b|embroidered\b|unbleached\b|bleached\b|dyed\b|printed\b)",
                re.IGNORECASE,
            )
            specific = None
            for seg in reversed(segs[1:]):
                if not _qualifier_prefix.match(seg):
                    specific = seg
                    break
            if specific:
                relationships.append(
                    AttributeRelationship("statutory_heading_context", segs[0], "STATUTORY_HEADING_CONTEXT", "head")
                )
                clean_head = specific

    finished_article = clean_head or head.strip() or combined
    relationships.insert(0, AttributeRelationship("finished_article", finished_article, "FINISHED_ARTICLE", "head"))

    packaging_str = "; ".join(packaging_parts) if packaging_parts else None
    use_str = "; ".join(use_parts) if use_parts else None

    # Build article-first search query so Stage 2 retrieval anchors on the finished commercial article
    search_parts = [finished_article]
    if constituent_materials:
        mat_str = ", ".join(constituent_materials[:2])
        if mat_str.lower() not in finished_article.lower():
            search_parts.append(f"Material: {mat_str}")
    if processing_form and processing_form.lower() not in finished_article.lower():
        search_parts.append(f"Form: {processing_form}")
    if use_str:
        search_parts.append(f"Use: {use_str}")

    return ProductIntentStructure(
        raw_description=raw,
        finished_article=finished_article,
        constituent_materials=constituent_materials,
        ingredients_or_additives=ingredients_or_additives,
        components_or_parts=components_or_parts,
        packaging_or_presentation=packaging_str,
        processing_form=processing_form,
        function_use=use_str,
        attribute_relationships=relationships,
        article_search_query=" | ".join(search_parts),
    )
