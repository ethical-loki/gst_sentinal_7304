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


_GENERAL_PRODUCT_FORMS = (
    "granules", "powder", "flakes", "pellets", "blocks", "sheets", "plates",
    "film", "foil", "strip", "tubes", "pipes", "hoses", "rods", "bars",
    "wire", "liquid", "paste", "extract", "resin", "scrap",
)

_GARMENT_CONSTRUCTION_CUES = re.compile(
    r"\b(?:t-?shirt|shirt|trouser|pants|suit|jacket|blazer|dress|skirt|sweater|pullover|overcoat|coat|garment|apparel|fabric|cloth)\b",
    re.IGNORECASE,
)
_MACHINERY_RATING_CUES = re.compile(
    r"\b(?:motor|generator|generating\s+set|pump|boiler|transformer|compressor|turbine|engine)\b",
    re.IGNORECASE,
)
_NUMERIC_SPEC_RE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:kva|kw|w|hp|v|kv|a|amp|hz|tonnes?|kg|g|ml|l|litre|mm|cm|m)\b", re.IGNORECASE)


@dataclass
class AttributeRelationship:
    attribute_type: str
    value: str
    role: str  # FINISHED_PRODUCT | CONSTITUENT_MATERIAL | COMPONENT | INGREDIENT | ADDITIVE | ACCESSORY | PACKAGING | FUNCTION | APPLICATION | ATTRIBUTE | PROCESS | PHYSICAL_FORM | ACRONYM_OR_ALIAS
    clause_source: str = "head"
    confidence: float = 0.85
    evidence_trace: str = ""
    evidence_type: str = "EXPLICIT"  # EXPLICIT | INFERRED
    validation_status: str = "VALIDATED"  # VALIDATED | UNVERIFIED | AMBIGUOUS


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
    secondary_articles: List[str] = field(default_factory=list)
    product_form: Optional[str] = None
    missing_critical_attributes: List[str] = field(default_factory=list)
    intent_confidence: float = 0.85
    product_head_noun: str = ""
    descriptive_modifiers: List[str] = field(default_factory=list)
    alternative_names_and_aliases: List[str] = field(default_factory=list)
    article_category: str = "finished_article"  # finished_article | intermediate_material | parts_or_component
    attributes: List[Dict[str, Any]] = field(default_factory=list)
    function_details: Dict[str, Any] = field(default_factory=dict)
    relationship_graph: List[Dict[str, Any]] = field(default_factory=list)
    field_confidences: Dict[str, float] = field(default_factory=dict)
    stage2_search_representation: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_description": self.raw_description,
            "finished_article": self.finished_article,
            "product_head_noun": self.product_head_noun,
            "descriptive_modifiers": list(self.descriptive_modifiers),
            "alternative_names_and_aliases": list(self.alternative_names_and_aliases),
            "article_category": self.article_category,
            "secondary_articles": list(self.secondary_articles),
            "constituent_materials": list(self.constituent_materials),
            "ingredients_or_additives": list(self.ingredients_or_additives),
            "components_or_parts": list(self.components_or_parts),
            "packaging_or_presentation": self.packaging_or_presentation,
            "processing_form": self.processing_form,
            "product_form": self.product_form,
            "function_use": self.function_use,
            "function_details": dict(self.function_details),
            "attributes": list(self.attributes),
            "relationship_graph": list(self.relationship_graph),
            "field_confidences": dict(self.field_confidences),
            "missing_critical_attributes": list(self.missing_critical_attributes),
            "intent_confidence": round(float(self.intent_confidence), 4),
            "attribute_relationships": [asdict(r) for r in self.attribute_relationships],
            "article_search_query": self.article_search_query,
            "stage2_search_representation": dict(self.stage2_search_representation),
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

    # Detect semicolon-separated multi-article descriptions outside parentheses
    top_articles: List[str] = []
    if ";" in combined:
        mask = _paren_depth_mask(combined)
        split_pts = [i for i, ch in enumerate(combined) if ch == ";" and not mask[i]]
        if split_pts:
            prev = 0
            for sp in split_pts:
                part = combined[prev:sp].strip()
                if part:
                    top_articles.append(part)
                prev = sp + 1
            tail = combined[prev:].strip()
            if tail:
                top_articles.append(tail)
    primary_input = top_articles[0] if len(top_articles) > 1 else combined
    extra_articles = top_articles[1:] if len(top_articles) > 1 else []

    head, clauses = _split_top_level_clauses(primary_input)

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

    # Clean balanced parenthetical examples/qualifiers/acronyms/material notes from head
    # without truncating at an opening parenthesis or misclassifying acronyms as materials.
    clean_head = head.strip()
    alternative_aliases: List[str] = []
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
                    AttributeRelationship("qualifier_or_example", inner, "ATTRIBUTE", "parenthetical", confidence=0.85, evidence_trace=f"parenthetical qualifier: ({inner})")
                )
            elif is_trailing:
                # Check dynamically whether inner is a verified statutory material vs an acronym/alias/attribute
                inner_mat_fact = None
                try:
                    from src.chapter_predictor.normalize import extract_query_facts
                    inner_mat_fact = extract_query_facts(inner).get("material")
                except Exception:
                    inner_mat_fact = None
                is_mat_phrase = bool(inner_mat_fact) or bool(
                    re.search(r"\b(?:alloy|steel|iron|cotton|wool|silk|linen|plastic|resin|polymer|rubber|wood|brass|copper|aluminium|aluminum)\b", inner_low)
                )
                preceding_words = re.findall(r"[A-Za-z0-9]+", clean_head[:pm.start()])
                initials = "".join(w[0].upper() for w in preceding_words if w)
                is_acronym = (
                    (bool(re.match(r"^[A-Z0-9\-/]{2,10}$", inner)) and not is_mat_phrase)
                    or (len(inner) >= 2 and inner.upper() in initials)
                )
                if is_acronym:
                    if inner not in alternative_aliases:
                        alternative_aliases.append(inner)
                    relationships.append(
                        AttributeRelationship("acronym_or_alias", inner, "ACRONYM_OR_ALIAS", "parenthetical", confidence=0.95, evidence_trace=f"abbreviation/alias for preceding phrase: ({inner})")
                    )
                elif is_mat_phrase:
                    if inner not in constituent_materials:
                        constituent_materials.append(inner)
                    relationships.append(
                        AttributeRelationship("material_or_note", inner, "CONSTITUENT_MATERIAL", "parenthetical", confidence=0.90, evidence_trace=f"parenthetical material note: ({inner})")
                    )
                else:
                    relationships.append(
                        AttributeRelationship("parenthetical_attribute", inner, "ATTRIBUTE", "parenthetical", confidence=0.82, evidence_trace=f"parenthetical specification: ({inner})")
                    )
            else:
                # Mid-phrase parenthetical: check if it is an acronym/alias or verified material
                preceding_words = re.findall(r"[A-Za-z0-9]+", clean_head[:pm.start()])
                initials = "".join(w[0].upper() for w in preceding_words if w)
                is_mid_acronym = (
                    bool(re.match(r"^[A-Z0-9\-/]{2,10}$", inner))
                    or (len(inner) >= 2 and inner.upper() in initials)
                )
                if is_mid_acronym:
                    if inner not in alternative_aliases:
                        alternative_aliases.append(inner)
                    relationships.append(
                        AttributeRelationship("acronym_or_alias", inner, "ACRONYM_OR_ALIAS", "parenthetical", confidence=0.95, evidence_trace=f"abbreviation/alias: ({inner})")
                    )
                    if re.search(r"\b(?:hdpe|ldpe|lldpe|pvc|pp|pet|abs|ptfe)\b", inner_low) and inner not in constituent_materials:
                        constituent_materials.append(inner)
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
    # If head is purely a generic parts phrase (e.g. "spare parts", "replacement parts")
    # and a "for <machine>" use clause exists, keep the serviced machine in finished_article
    # so downstream evidence matching sees both the parts role and the target machine.
    if (
        re.match(r"^(?:spare|replacement|service)?\s*parts?(?:\s+and\s+accessories)?$", finished_article, re.IGNORECASE)
        and use_parts
    ):
        finished_article = f"{finished_article} for {use_parts[0]}"
    relationships.insert(
        0,
        AttributeRelationship(
            "finished_article",
            finished_article,
            "FINISHED_ARTICLE",
            "head",
            confidence=0.92 if clean_head else 0.70,
            evidence_trace=f"leading head phrase before top-level markers: '{finished_article[:80]}'",
        ),
    )

    # Product physical form extraction (e.g. granules, powder, sheets, pipes, liquid)
    forms_found: List[str] = []
    combined_low = combined.lower()
    for pf in _GENERAL_PRODUCT_FORMS:
        if re.search(rf"\b{re.escape(pf)}\b", combined_low):
            forms_found.append(pf)
    product_form = ", ".join(forms_found) if forms_found else None
    if product_form:
        relationships.append(
            AttributeRelationship(
                "product_form",
                product_form,
                "PRODUCT_FORM",
                "lexical",
                confidence=0.88,
                evidence_trace=f"matched physical form cue(s): {product_form}",
            )
        )

    # Multi-article detection (distinct articles joined by top-level ';' outside parentheses)
    secondary_articles: List[str] = list(extra_articles)

    # Detect missing classification-critical attributes
    missing_critical: List[str] = []
    if not constituent_materials:
        missing_critical.append("material")
    if _GARMENT_CONSTRUCTION_CUES.search(finished_article) and not processing_form:
        missing_critical.append("construction (knitted vs woven)")
    if _MACHINERY_RATING_CUES.search(finished_article) and not _NUMERIC_SPEC_RE.search(combined):
        missing_critical.append("capacity_or_rating")

    # Populate evidence_trace for relationships that lack one
    for rel in relationships:
        if not rel.evidence_trace:
            rel.evidence_trace = f"extracted via {rel.clause_source} ({rel.attribute_type})"

    # Task 2: Head noun, modifiers, and article category (finished vs intermediate vs parts)
    pre_prep_article = re.split(
        r"\s+(?:of|without|with|containing|consisting\s+of|made\s+(?:of|from))\s+",
        finished_article,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip()
    head_words = [w for w in re.findall(r"[A-Za-z0-9\-]+", pre_prep_article or finished_article) if w.lower() not in ("of", "for", "and", "or", "the", "a", "an", "with", "in", "without")]
    if not head_words:
        head_words = [w for w in re.findall(r"[A-Za-z0-9\-]+", finished_article) if w.lower() not in ("of", "for", "and", "or", "the", "a", "an", "with", "in", "without")]
    all_article_words = [w for w in re.findall(r"[A-Za-z0-9\-]+", finished_article) if w.lower() not in ("of", "for", "and", "or", "the", "a", "an", "with", "in", "without")]
    raw_head_article = str(head_facts.get("article") or "").strip()
    rightmost_head = head_words[-1] if head_words else finished_article
    _generic_trailing = {
        "unit", "units", "system", "systems", "set", "sets", "kit", "kits",
        "item", "items", "goods", "type", "types", "model", "models",
        "grade", "grades", "assembly", "assemblies", "module", "modules",
        "capacity", "rating", "size", "sizes", "weight", "duty", "service",
        "range", "output", "power", "pressure", "voltage", "speed", "use", "purpose",
    }
    _unit_tok_re = re.compile(
        r"^(?:\d+(?:\.\d+)?(?:cc|kw|kva|hp|mm|cm|m|kg|g|ml|l|v|kv|hz|a)?|kg|gm|g|mm|cm|m|inch|cc|kw|kva|hp|v|kv|hz|amp|bar|psi|cfm|lph|l|ml|litre|litres|tonnes?|gsm|seater)$",
        re.IGNORECASE,
    )
    # Strip trailing capacity/rating spec + engine/motor ("car 1200cc engine" -> head "car",
    # while "motorcycle engine 150cc" stays "engine").
    noun_src = re.sub(
        r"\s+\d+(?:\.\d+)?\s*(?:cc|kw|kva|hp|mm|cm|m|kg|g|ml|l|v|kv|hz|a)\s+(?:engine|motor)s?$",
        "",
        pre_prep_article or finished_article,
        flags=re.IGNORECASE,
    ).strip()
    stripped_spec_prime_mover = bool(noun_src and noun_src != (pre_prep_article or finished_article).strip())
    noun_src_words = [
        w for w in re.findall(r"[A-Za-z0-9\-]+", noun_src)
        if w.lower() not in ("of", "for", "and", "or", "the", "a", "an", "with", "in", "without")
    ] or head_words
    noun_candidates = [w for w in noun_src_words if w.isalpha() and len(w) >= 3 and not _unit_tok_re.match(w)]
    if not noun_candidates:
        noun_candidates = [w for w in head_words if w.isalpha() and len(w) >= 3 and not _unit_tok_re.match(w)]
    non_generic_nouns = [w for w in noun_candidates if w.lower() not in _generic_trailing]
    effective_rightmost = non_generic_nouns[-1] if non_generic_nouns else (noun_candidates[-1] if noun_candidates else rightmost_head)
    if stripped_spec_prime_mover and non_generic_nouns:
        product_head_noun = non_generic_nouns[-1]
    elif (
        raw_head_article
        and " " not in raw_head_article
        and effective_rightmost
        and effective_rightmost.isalpha()
        and len(effective_rightmost) >= 3
        and effective_rightmost.lower() not in _generic_trailing
        and effective_rightmost.lower() != raw_head_article.lower()
        and pre_prep_article.lower().rfind(effective_rightmost.lower()) > pre_prep_article.lower().rfind(raw_head_article.lower())
    ):
        product_head_noun = effective_rightmost
    elif (
        (not raw_head_article or raw_head_article.lower() in _generic_trailing or _unit_tok_re.match(raw_head_article))
        and non_generic_nouns
    ):
        product_head_noun = non_generic_nouns[-1]
    elif raw_head_article and not _unit_tok_re.match(raw_head_article) and raw_head_article.lower() not in _generic_trailing:
        product_head_noun = raw_head_article
    else:
        product_head_noun = effective_rightmost or raw_head_article or rightmost_head
    descriptive_modifiers = [w for w in all_article_words if w.lower() != product_head_noun.lower()] if len(all_article_words) > 1 else []
    if re.search(r"\b(?:parts?|spares?|components?|accessories|subassembly)\b", finished_article, re.IGNORECASE):
        article_category = "parts_or_component"
    elif product_form and any(f in product_form.lower() for f in ("granules", "powder", "flakes", "pellets", "resin", "scrap", "liquid")):
        article_category = "intermediate_material"
    else:
        article_category = "finished_article"

    # Task 4: Extensible dynamic attribute extraction with source spans & field-level evidence
    extracted_attributes: List[Dict[str, Any]] = []
    def _add_attr(name: str, val: str, role: str, span: str, conf: float = 0.88, ev_type: str = "EXPLICIT", v_status: str = "VALIDATED") -> None:
        if val:
            extracted_attributes.append({
                "name": name,
                "value": val,
                "role": role,
                "source_span": span,
                "confidence": round(float(conf), 4),
                "evidence_type": ev_type,
                "validation_status": v_status,
            })

    for m in constituent_materials:
        _add_attr("material_composition", m, "CONSTITUENT_MATERIAL", m, 0.90)
    if processing_form:
        _add_attr("manufacturing_construction", processing_form, "PROCESS", processing_form, 0.90)
    if product_form:
        _add_attr("physical_form", product_form, "PHYSICAL_FORM", product_form, 0.88)
    for m_dim in re.finditer(r"\b\d+(?:\.\d+)?\s*(?:mm|cm|m|inch|kg|g|ml|l|litre|tonnes?|cc|gsm)\b", combined, re.IGNORECASE):
        _add_attr("dimensions_measurements", m_dim.group(0), "ATTRIBUTE", m_dim.group(0), 0.95)
    for m_cap in re.finditer(r"\b\d+(?:\.\d+)?\s*(?:kva|kw|w|hp|rpm|bar|psi|cfm|lph|tonnes?\s*per\s*hour)\b", combined, re.IGNORECASE):
        _add_attr("capacity_performance", m_cap.group(0), "ATTRIBUTE", m_cap.group(0), 0.95)
    for m_elec in re.finditer(r"\b(?:ac|dc|single[- ]phase|three[- ]phase|3[- ]phase|variable\s+frequency|hydraulic|pneumatic|\d+(?:\.\d+)?\s*(?:v|kv|hz|amp|a))\b", combined, re.IGNORECASE):
        _add_attr("electrical_mechanical", m_elec.group(0), "ATTRIBUTE", m_elec.group(0), 0.90)

    # Task 5: Function & application decomposition
    use_str = "; ".join(use_parts) if use_parts else None
    packaging_str = "; ".join(packaging_parts) if packaging_parts else None
    function_details: Dict[str, Any] = {
        "action": None,
        "mechanism": None,
        "target_object": None,
        "application": use_str,
        "evidence_type": "EXPLICIT" if use_str else None,
    }
    if use_str:
        _add_attr("intended_use", use_str, "FUNCTION", use_str, 0.92)
        fn_m = re.match(r"^(controlling|regulating|driving|pumping|heating|cooling|drying|filtering|cutting|welding|lifting|measuring|converting|transmitting|protecting|cleaning|brewing)\s+(.+)$", use_str.strip(), re.IGNORECASE)
        if fn_m:
            function_details["action"] = fn_m.group(1).lower()
            function_details["target_object"] = fn_m.group(2).strip()
        else:
            function_details["action"] = use_str
    if re.search(r"\b(?:variable\s+frequency|centrifugal|rotary|compression|hydraulic|pneumatic|induction|electron\s+beam)\b", combined_low):
        mech_m = re.search(r"\b(variable\s+frequency|centrifugal|rotary|compression|hydraulic|pneumatic|induction|electron\s+beam)\b", combined_low)
        if mech_m:
            function_details["mechanism"] = mech_m.group(1)
            if not function_details["evidence_type"]:
                function_details["evidence_type"] = "INFERRED"

    # Task 6: Dynamic Entity Relationship Graph
    rel_graph: List[Dict[str, Any]] = []
    for alias in alternative_aliases:
        rel_graph.append({"source": finished_article, "relation": "ALIAS_OF", "target": alias, "confidence": 0.95, "evidence_type": "EXPLICIT", "source_span": f"({alias})"})
    for mat in constituent_materials:
        rel_graph.append({"source": finished_article, "relation": "MADE_OF", "target": mat, "confidence": 0.90, "evidence_type": "EXPLICIT", "source_span": mat})
    for ing in ingredients_or_additives:
        rel_graph.append({"source": finished_article, "relation": "CONTAINS", "target": ing, "confidence": 0.88, "evidence_type": "EXPLICIT", "source_span": ing})
    for comp in components_or_parts:
        rel_graph.append({"source": comp, "relation": "ATTACHED_TO", "target": finished_article, "confidence": 0.88, "evidence_type": "EXPLICIT", "source_span": comp})
    if use_str:
        rel_type = "CONTROLS" if (function_details.get("action") or "").startswith("control") else "USED_FOR"
        target_ent = function_details.get("target_object") or use_str
        rel_graph.append({"source": finished_article, "relation": rel_type, "target": target_ent, "confidence": 0.92, "evidence_type": "EXPLICIT", "source_span": use_str})
        rel_graph.append({"source": finished_article, "relation": "PERFORMS_FUNCTION", "target": use_str, "confidence": 0.92, "evidence_type": "EXPLICIT", "source_span": use_str})
        if function_details.get("target_object"):
            rel_graph.append({"source": finished_article, "relation": "OPERATES_ON", "target": function_details["target_object"], "confidence": 0.88, "evidence_type": "EXPLICIT", "source_span": use_str})

    intent_conf = 0.92 if (finished_article and not missing_critical) else (0.78 if finished_article else 0.45)
    field_confidences = {
        "finished_article": 0.92 if clean_head else 0.70,
        "constituent_materials": 0.90 if constituent_materials else 0.0,
        "components_or_parts": 0.88 if components_or_parts else 0.0,
        "function_use": 0.92 if use_str else 0.0,
        "processing_form": 0.90 if processing_form else 0.0,
    }

    # Task 9: Stage 2 Structured Search Representation
    stage2_repr = {
        "primary_commercial_product": finished_article,
        "product_identity_and_aliases": [finished_article] + alternative_aliases,
        "relevant_attributes": [a for a in extracted_attributes if a["role"] in ("ATTRIBUTE", "PROCESS", "PHYSICAL_FORM")],
        "constituent_materials": list(constituent_materials),
        "integrated_components": list(components_or_parts),
        "function_and_application": use_str,
        "dynamic_statutory_terms": [],
    }

    # Build article-first search query so Stage 2 retrieval anchors on product + function + verified materials
    search_parts = [finished_article]
    if alternative_aliases:
        search_parts.append(f"Aliases: {', '.join(alternative_aliases[:3])}")
    if constituent_materials:
        mat_str = ", ".join(constituent_materials[:2])
        if mat_str.lower() not in finished_article.lower():
            search_parts.append(f"Material: {mat_str}")
    if processing_form and processing_form.lower() not in finished_article.lower():
        search_parts.append(f"Form: {processing_form}")
    if components_or_parts:
        search_parts.append(f"Components: {', '.join(components_or_parts[:3])}")
    if use_str:
        search_parts.append(f"Use: {use_str}")

    return ProductIntentStructure(
        raw_description=raw,
        finished_article=finished_article,
        product_head_noun=product_head_noun,
        descriptive_modifiers=descriptive_modifiers,
        alternative_names_and_aliases=alternative_aliases,
        article_category=article_category,
        secondary_articles=secondary_articles,
        constituent_materials=constituent_materials,
        ingredients_or_additives=ingredients_or_additives,
        components_or_parts=components_or_parts,
        packaging_or_presentation=packaging_str,
        processing_form=processing_form,
        product_form=product_form,
        function_use=use_str,
        function_details=function_details,
        attributes=extracted_attributes,
        relationship_graph=rel_graph,
        field_confidences=field_confidences,
        missing_critical_attributes=missing_critical,
        intent_confidence=intent_conf,
        attribute_relationships=relationships,
        article_search_query=" | ".join(search_parts),
        stage2_search_representation=stage2_repr,
    )
