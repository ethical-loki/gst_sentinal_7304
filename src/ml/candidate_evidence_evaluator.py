"""
src/ml/candidate_evidence_evaluator.py
======================================
Dataset-Driven Universal HSN Candidate Profile & Evidence Evaluator.

Uses the actual `data/enriched_master_hsn.parquet` schema:
  - hsn_code, code_length, chapter_code, chapter_title
  - heading_4digit, heading_4digit_desc
  - subheading_6digit, subheading_6digit_desc
  - tariff_item_8digit, tariff_item_desc, statutory_description
  - consumer_synonyms, article_keywords, material_keywords

Evaluates every retrieved candidate against Stage 1 `ProductIntentStructure`
with traceable, evidence-based outcomes:
  - SUPPORTED
  - POSSIBLY_SUPPORTED
  - CONTRADICTED
  - INSUFFICIENT_EVIDENCE

Design rules:
  - 100% general across all 9 active chapters (no product-specific HSN rules).
  - Never reject a candidate merely because a material/attribute was unstated.
  - Distinguish missing attributes from explicit statutory contradictions.
  - Consolidate duplicate rows without merging distinct 8-digit HSN codes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from src.ml.hierarchy_intelligence import (
    extract_statutory_exclusions,
    get_hierarchy_intelligence,
)
from src.nlp.product_intent_analyzer import ProductIntentStructure

SUPPORTED = "SUPPORTED"
POSSIBLY_SUPPORTED = "POSSIBLY_SUPPORTED"
CONTRADICTED = "CONTRADICTED"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

_STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "for", "with", "in", "on", "at", "to",
    "from", "by", "is", "are", "was", "were", "be", "been", "as", "other",
    "not", "no", "including", "excluding", "nes", "elsewhere", "specified",
    "included", "thereof", "parts", "articles", "goods", "products", "made",
}

# Generic qualifiers/demographics/modifiers that must NOT serve as standalone article identity proof
_GENERIC_MODIFIERS = {
    "women", "woman", "men", "man", "girl", "boy", "infant", "child", "children",
    "household", "kitchen", "table", "industrial", "commercial", "domestic",
    "electric", "electrical", "manual", "automatic", "portable", "general",
    "type", "kind", "size", "shape", "new", "used", "suitable", "similar",
    "item", "items", "fitting", "fittings", "accessory", "accessories",
    "material", "non", "less", "more", "weight", "containing", "whether", "exceeding",
    "retail", "pack", "packet", "prepared", "preparation", "preparations",
    "knitted", "crocheted", "knit", "woven", "seamless", "welded", "forged",
    "cast", "molded", "moulded", "extruded", "roasted", "unroasted", "instant",
    "dried", "dehydrated", "frozen", "chilled", "laminated", "coated", "plated",
}

# Broad superordinate nouns that alone are weaker than specific commercial article nouns
_BROAD_SUPERORDINATES = {
    "container", "equipment", "device", "machine", "machinery", "system",
    "unit", "ware", "product", "accessory", "appliance", "apparatus", "tool",
}

# General WCO tariff qualifier words and prepositional clause starters that qualify a parent heading
# rather than naming a distinct article at the subheading/leaf level.
_LEAF_QUALIFIER_TOKENS = _GENERIC_MODIFIERS | {
    "flexible", "rigid", "plain", "cellular", "unreinforced", "reinforced",
    "galvanised", "galvanized", "polished", "unworked", "capacity", "cylinder",
    "cc", "kw", "kva", "hp", "volt", "volts", "watt", "watts", "ampere",
    "kg", "gram", "grams", "mm", "cm", "inch", "litres", "liter", "between",
    "upto", "below", "above", "minimum", "maximum", "thickness", "width",
    "length", "diameter", "power", "rating", "speed", "pressure", "temperature",
    "phase", "single", "three", "ac", "dc", "but", "having", "fitted",
}
_LEAF_QUALIFIER_PREFIX_RE = re.compile(
    r"^\s*(?:of|for|with|without|containing|exceeding|not\s+exceeding|other\s+than|whether|in|on|by|having|fitted|powered|operated|designed|used|made|from)\b",
    re.IGNORECASE,
)

_HOUSEHOLD_ROLE_RE = re.compile(
    r"\b(?:household|kitchenware|tableware|kitchen|domestic|toilet\s+articles|food\s+storage|lunch\s+box|storage\s+container)\b",
    re.IGNORECASE,
)
_CONVEYANCE_ROLE_RE = re.compile(
    r"\b(?:conveyance\s+or\s+packing\s+of\s+goods|packing\s+of\s+goods|shipping|cargo|freight|industrial\s+packaging)\b",
    re.IGNORECASE,
)
_QUERY_PARTS_CUES_RE = re.compile(
    r"\b(?:part|parts|spare|spares|component|components|accessory|accessories|"
    r"subassembly|impeller|casing|rotor|stator|seal|gasket|valve|blade|nozzle|"
    r"pad|pads|lining|inflator|radiator|clutch|piston|ring|rings|bearing|shaft|gear|housing|bracket|filter)\b",
    re.IGNORECASE,
)
_CAND_PARTS_SUB6_RE = re.compile(r"^\s*parts(?:\s+and\s+accessories|\s+of\b|\s+suitable\b|$)", re.IGNORECASE)
_CAND_PARTS_DESC_RE = re.compile(r"^\s*(?:parts\s+(?:of|for|and\s+accessories|suitable\s+for)|parts\s*$)", re.IGNORECASE)
_CAND_PARTS_STAT_RE = re.compile(r"(?:^|-\s*)parts\b(?:\s*:|\s*-|\s+of\b|\s+for\b|\s+and\s+accessories)", re.IGNORECASE)
_CAND_OF_MACHINE_RE = re.compile(r"^\s*of\s+[a-z]", re.IGNORECASE)

# Broad mutually-exclusive material families derived from WCO tariff structure
_MATERIAL_FAMILIES: Dict[str, Set[str]] = {
    "plastics": {"plastic", "plastics", "polymer", "polymers", "pvc", "hdpe", "ldpe", "polyethylene", "polypropylene", "polystyrene", "polycarbonate", "abs", "acrylic", "vinyl", "nylon", "resin"},
    "iron_steel": {"iron", "steel", "stainless", "cast iron", "wrought iron", "alloy steel", "carbon steel", "mild steel", "ferro"},
    "aluminium": {"aluminium", "aluminum"},
    "copper_brass": {"copper", "brass", "bronze"},
    "base_metal": {
        "base metal", "nickel", "lead", "zinc", "tin", "tungsten", "molybdenum",
        "tantalum", "magnesium", "cobalt", "bismuth", "cadmium", "titanium",
        "zirconium", "antimony", "manganese", "beryllium", "chromium",
        "germanium", "vanadium", "cermet", "cermets",
    },
    "cotton": {"cotton"},
    "wool": {"wool", "woollen", "woolen", "cashmere", "merino", "animal hair"},
    "silk": {"silk"},
    "synthetic_textile": {"synthetic", "man-made", "polyester", "viscose", "rayon", "spandex", "elastane"},
    "vegetable_textile": {"linen", "flax", "ramie", "hemp", "jute", "coir", "sisal"},
    "wood": {"wood", "wooden", "timber", "plywood", "bamboo"},
    "rubber": {"rubber", "latex", "elastomer", "vulcanised", "vulcanized"},
    "glass_ceramic": {"glass", "ceramic", "porcelain", "stoneware", "earthenware"},
    "leather": {"leather", "raw hide", "raw hides", "raw skin", "raw skins", "furskin", "furskins", "composition leather", "suede"},
    "paper": {"paper", "paperboard", "cardboard"},
    "protein": {"protein", "casein", "gelatin", "gelatine", "collagen", "albumin"},
    "cellulosic": {"cellulose", "cellulosic", "cellophane", "nitrocellulose", "cellulose acetate"},
}

# Compatible material pairs (e.g. synthetic_textile vs plastics share nylon/polyester terms)
_COMPATIBLE_FAMILIES: Set[frozenset] = {
    frozenset({"plastics", "synthetic_textile"}),
    frozenset({"iron_steel", "aluminium"}),  # multi-metal assemblies can appear together unless exclusive
    frozenset({"base_metal", "iron_steel"}),
    frozenset({"base_metal", "aluminium"}),
    frozenset({"base_metal", "copper_brass"}),
}


@lru_cache(maxsize=16384)
def _stem(tok: str) -> str:
    t = tok.lower().strip()
    if len(t) > 4 and t.endswith("ies"):
        return t[:-3] + "y"
    if len(t) > 4 and t.endswith("es") and t[-3] in "shxz":
        return t[:-2]
    if len(t) > 3 and t.endswith("s") and not t.endswith(("ss", "us", "is", "os", "as")):
        return t[:-1]
    return t


def _tokenize_content(text: str) -> Set[str]:
    if not text:
        return set()
    norm = re.sub(r"\bvaccum\b", "vacuum", re.sub(r"\bstailess\b", "stainless", text.lower()))
    raw = re.findall(r"\b[a-z0-9]{2,}\b", norm)
    return {_stem(w) for w in raw if w not in _STOPWORDS}


def _split_kw_list(raw: str) -> List[str]:
    if not raw or str(raw).lower() == "nan":
        return []
    return [p.strip().lower() for p in re.split(r"[,;|]+", str(raw)) if p.strip()]


def _detect_material_families(tokens: Set[str], raw_text: str = "") -> Set[str]:
    low = (raw_text or "").lower()
    found: Set[str] = set()
    for fam, cues in _MATERIAL_FAMILIES.items():
        for cue in cues:
            if " " in cue:
                if cue in low:
                    found.add(fam)
                    break
            elif _stem(cue) in tokens or cue in tokens:
                found.add(fam)
                break
    return found


@dataclass
class CandidateProfile:
    hsn_code: str
    code_length: int
    chapter_code: str
    chapter_title: str
    statutory_description: str
    tariff_item_desc: str
    subheading_6digit_desc: str
    heading_4digit_desc: str
    article_keywords: List[str] = field(default_factory=list)
    material_keywords: List[str] = field(default_factory=list)
    consumer_synonyms: List[str] = field(default_factory=list)
    article_tokens: Set[str] = field(default_factory=set)
    leaf_article_tokens: Set[str] = field(default_factory=set)
    parent_heading_tokens: Set[str] = field(default_factory=set)
    functional_tokens: Set[str] = field(default_factory=set)
    material_tokens: Set[str] = field(default_factory=set)
    chapter_tokens: Set[str] = field(default_factory=set)
    material_families: Set[str] = field(default_factory=set)
    statutory_material_families: Set[str] = field(default_factory=set)
    is_qualifying_only_leaf: bool = False
    qualifying_reason: str = ""
    inherited_parent_articles: Set[str] = field(default_factory=set)
    explicit_exclusions: Set[str] = field(default_factory=set)
    contradictory_sibling_articles: Set[str] = field(default_factory=set)
    sibling_shared_tokens: Set[str] = field(default_factory=set)
    sibling_distinguishing_tokens: Set[str] = field(default_factory=set)


@dataclass
class CandidateEvidenceResult:
    status: str  # SUPPORTED | POSSIBLY_SUPPORTED | CONTRADICTED | INSUFFICIENT_EVIDENCE
    compatibility_level: str = "INSUFFICIENT_EVIDENCE"  # DIRECT_COMPATIBILITY | PARTIAL_COMPATIBILITY | RELATED_DIFFERENT_ARTICLE | EXPLICIT_CONTRADICTION | INSUFFICIENT_EVIDENCE
    primary_article_matched: bool = False
    article_matches: List[str] = field(default_factory=list)
    statutory_article_matches: List[str] = field(default_factory=list)
    material_matches: List[str] = field(default_factory=list)
    chapter_compatible: bool = False
    heading_compatible: bool = False
    role_mismatch: str = ""
    contradictions: List[str] = field(default_factory=list)
    missing_attributes: List[str] = field(default_factory=list)
    evidence_score: float = 0.0
    trace_summary: str = ""
    hierarchy_intelligence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "compatibility_level": self.compatibility_level,
            "primary_article_matched": self.primary_article_matched,
            "article_matches": list(self.article_matches),
            "statutory_article_matches": list(self.statutory_article_matches),
            "material_matches": list(self.material_matches),
            "chapter_compatible": self.chapter_compatible,
            "heading_compatible": self.heading_compatible,
            "role_mismatch": self.role_mismatch,
            "contradictions": list(self.contradictions),
            "missing_attributes": list(self.missing_attributes),
            "evidence_score": round(float(self.evidence_score), 4),
            "trace_summary": self.trace_summary,
            "hierarchy_intelligence": dict(self.hierarchy_intelligence),
        }


_PROFILE_CACHE: Dict[Tuple[str, str, str, str, str], CandidateProfile] = {}


def build_candidate_profile(raw_rec: Optional[Dict[str, Any]], candidate: Any) -> CandidateProfile:
    """
    Normalizes and caches a candidate profile from `enriched_master_hsn.parquet` fields,
    separating leaf-level article identity, parent-heading scope, and functional/material limitations.
    """
    rec = raw_rec or {}
    hsn = str(getattr(candidate, "hsn_code", None) or rec.get("hsn_code") or "").strip()
    code_len = int(rec.get("code_length") or len(hsn) or 8)
    chap_code = str(getattr(candidate, "chapter_code", None) or rec.get("chapter_code") or hsn[:2]).strip().zfill(2)
    chap_title = str(getattr(candidate, "chapter_title", None) or rec.get("chapter_title") or "").strip()
    stat_desc = str(getattr(candidate, "description", None) or rec.get("statutory_description") or "").strip()
    item_desc = str(getattr(candidate, "tariff_item_desc", None) or rec.get("tariff_item_desc") or stat_desc).strip()
    sub6_desc = str(getattr(candidate, "subheading_6digit_desc", None) or rec.get("subheading_6digit_desc") or "").strip()
    hd4_desc = str(getattr(candidate, "heading_4digit_desc", None) or rec.get("heading_4digit_desc") or "").strip()

    art_kws = _split_kw_list(getattr(candidate, "article_keywords", None) or rec.get("article_keywords") or "")
    mat_kws = _split_kw_list(getattr(candidate, "material_keywords", None) or rec.get("material_keywords") or "")
    cons_syns = _split_kw_list(rec.get("consumer_synonyms") or "")

    cache_key = (hsn, stat_desc, item_desc, sub6_desc, hd4_desc)
    cached = _PROFILE_CACHE.get(cache_key)
    if cached is not None and not art_kws and not mat_kws and not cons_syns:
        return cached

    hi = get_hierarchy_intelligence()
    h_intel = hi.analyze_record({
        "hsn_code": hsn,
        "chapter_code": chap_code,
        "heading_4digit": hsn[:4] if len(hsn) >= 4 else "",
        "subheading_6digit": hsn[:6] if len(hsn) >= 6 else "",
        "heading_4digit_desc": hd4_desc,
        "subheading_6digit_desc": sub6_desc,
        "tariff_item_desc": item_desc,
        "statutory_description": stat_desc,
        "is_residual": bool(rec.get("is_residual", False)),
    })

    # Strip explicit exclusion clauses before extracting positive statutory article tokens
    pos_item, _, _, _ = extract_statutory_exclusions(item_desc)
    pos_stat, _, _, _ = extract_statutory_exclusions(stat_desc)
    pos_sub6, _, _, _ = extract_statutory_exclusions(sub6_desc)
    pos_hd4, _, _, _ = extract_statutory_exclusions(hd4_desc)

    art_text = " ".join([pos_item or item_desc, pos_stat or stat_desc, pos_sub6 or sub6_desc, pos_hd4 or hd4_desc, " ".join(art_kws), " ".join(cons_syns)])
    mat_text = " ".join([" ".join(mat_kws), pos_item or item_desc, pos_stat or stat_desc, pos_sub6 or sub6_desc, pos_hd4 or hd4_desc])

    leaf_art_tokens = _tokenize_content(f"{pos_item or item_desc} {pos_sub6 or sub6_desc}")
    raw_art_tokens = _tokenize_content(art_text)
    # Remove explicit exclusions and contradictory sibling-exclusive nouns unless owned at leaf/sub6 level
    art_tokens = (
        (raw_art_tokens - h_intel.explicit_exclusions - h_intel.contradictory_sibling_articles)
        | leaf_art_tokens
        | h_intel.inherited_parent_articles
    )
    parent_hd_tokens = _tokenize_content(pos_hd4 or hd4_desc) - h_intel.explicit_exclusions
    func_clauses = re.findall(r"\b(?:for|used\s+in|designed\s+(?:for|to))\s+([a-z0-9\s]{3,40}?)(?:[,;]|$)", f"{item_desc} {sub6_desc} {hd4_desc}".lower())
    functional_tokens = _tokenize_content(" ".join(func_clauses))
    dynamic_mat_cues = {
        _stem(c) for cues in _MATERIAL_FAMILIES.values() for c in cues if " " not in c
    } | hi.corpus_material_tokens
    mat_tokens = _tokenize_content(" ".join(mat_kws)) | (_tokenize_content(item_desc) & dynamic_mat_cues) | h_intel.statutory_materials
    chap_tokens = _tokenize_content(chap_title)
    mat_fams = _detect_material_families(_tokenize_content(mat_text), mat_text)
    stat_mat_raw = " ".join([pos_item or item_desc, pos_stat or stat_desc, pos_sub6 or sub6_desc, pos_hd4 or hd4_desc])
    stat_mat_text = re.sub(r"\(\s*for\s+example[^)]*\)", " ", stat_mat_raw, flags=re.IGNORECASE)
    stat_mat_text = re.sub(r"\bwhether\s+or\s+not\b[^,;)]*", " ", stat_mat_text, flags=re.IGNORECASE)
    stat_mat_fams = _detect_material_families(_tokenize_content(stat_mat_text), stat_mat_text)

    prof = CandidateProfile(
        hsn_code=hsn,
        code_length=code_len,
        chapter_code=chap_code,
        chapter_title=chap_title,
        statutory_description=stat_desc,
        tariff_item_desc=item_desc,
        subheading_6digit_desc=sub6_desc,
        heading_4digit_desc=hd4_desc,
        article_keywords=art_kws,
        material_keywords=mat_kws,
        consumer_synonyms=cons_syns,
        article_tokens=art_tokens,
        leaf_article_tokens=leaf_art_tokens,
        parent_heading_tokens=parent_hd_tokens,
        functional_tokens=functional_tokens,
        material_tokens=mat_tokens,
        chapter_tokens=chap_tokens,
        material_families=mat_fams,
        statutory_material_families=stat_mat_fams,
        is_qualifying_only_leaf=h_intel.is_qualifying_only_leaf,
        qualifying_reason=h_intel.qualifying_reason,
        inherited_parent_articles=set(h_intel.inherited_parent_articles),
        explicit_exclusions=set(h_intel.explicit_exclusions),
        contradictory_sibling_articles=set(h_intel.contradictory_sibling_articles),
        sibling_shared_tokens=set(h_intel.sibling_shared_tokens),
        sibling_distinguishing_tokens=set(h_intel.sibling_distinguishing_tokens),
    )
    if len(_PROFILE_CACHE) < 10000 and not art_kws and not mat_kws and not cons_syns:
        _PROFILE_CACHE[cache_key] = prof
    return prof


def evaluate_candidate_evidence(
    product_intent: ProductIntentStructure,
    profile: CandidateProfile,
    relation_value: str,
    cross_encoder_confidence: float,
) -> CandidateEvidenceResult:
    """
    Evaluates candidate applicability using Stage 1 ProductIntentStructure and
    the candidate's normalized statutory profile.
    """
    head_tokens = _tokenize_content(product_intent.finished_article)
    # Remove pure material tokens and generic modifiers when checking core article identity
    all_mat_cues = {_stem(c) for cues in _MATERIAL_FAMILIES.values() for c in cues if " " not in c}
    generic_stems = {_stem(g) for g in _GENERIC_MODIFIERS}
    article_core_tokens = head_tokens - all_mat_cues - generic_stems
    if not article_core_tokens:
        article_core_tokens = head_tokens - all_mat_cues

    # 1. Article identity matching (deduplicated by canonical stem; no generic-modifier phrase inflation)
    article_matches: List[str] = []
    seen_art_stems: Set[str] = set()
    art_phrase_pool = profile.article_keywords + profile.consumer_synonyms
    head_low = product_intent.finished_article.lower()
    for phrase in art_phrase_pool:
        if not phrase:
            continue
        p_toks = _tokenize_content(phrase) - all_mat_cues - generic_stems
        if phrase in head_low or (p_toks and p_toks.issubset(article_core_tokens)):
            canon = " ".join(sorted(p_toks)) if p_toks else phrase
            if canon not in seen_art_stems:
                seen_art_stems.add(canon)
                article_matches.append(phrase)
    for tok in sorted(article_core_tokens & profile.article_tokens):
        if tok not in seen_art_stems and not any(tok in _tokenize_content(m) for m in article_matches):
            seen_art_stems.add(tok)
            article_matches.append(tok)

    statutory_only_tokens = _tokenize_content(
        f"{profile.tariff_item_desc} {profile.statutory_description} {profile.subheading_6digit_desc} {profile.heading_4digit_desc}"
    )
    statutory_article_matches = sorted((article_core_tokens - _BROAD_SUPERORDINATES) & statutory_only_tokens)

    # 2. Material & composition matching (evaluated separately from article identity)
    query_mat_text = " ".join(product_intent.constituent_materials)
    query_mat_tokens = _tokenize_content(query_mat_text) | (head_tokens & all_mat_cues)
    query_mat_fams = _detect_material_families(query_mat_tokens, f"{product_intent.finished_article} {query_mat_text}")

    material_matches: List[str] = []
    seen_mat_stems: Set[str] = set()
    for tok in sorted(query_mat_tokens & profile.material_tokens):
        if tok not in seen_mat_stems:
            seen_mat_stems.add(tok)
            material_matches.append(tok)
    for kw in profile.material_keywords:
        if kw and kw in f"{head_low} {query_mat_text.lower()}":
            kw_stem = _stem(kw)
            if kw_stem not in seen_mat_stems:
                seen_mat_stems.add(kw_stem)
                material_matches.append(kw)
    if not material_matches and query_mat_fams and profile.material_families:
        for fam in sorted(query_mat_fams & profile.material_families):
            material_matches.append(fam)

    # 3. Chapter & heading compatibility (supporting evidence only, never standalone proof)
    intent_all_tokens = _tokenize_content(
        f"{product_intent.finished_article} {query_mat_text} {product_intent.processing_form or ''} {product_intent.function_use or ''}"
    )
    chapter_compatible = bool(intent_all_tokens & profile.chapter_tokens) or bool(article_matches)
    heading_tokens = _tokenize_content(f"{profile.heading_4digit_desc} {profile.subheading_6digit_desc}")
    heading_compatible = bool(article_core_tokens & heading_tokens) or bool(article_matches)

    # Functional role alignment: distinguish household/storage articles vs conveyance/packing containers
    query_role_text = f"{product_intent.raw_description} {product_intent.finished_article} {product_intent.function_use or ''}"
    cand_role_text = f"{profile.heading_4digit_desc} {profile.subheading_6digit_desc} {profile.statutory_description}"
    q_household = bool(_HOUSEHOLD_ROLE_RE.search(query_role_text))
    q_conveyance = bool(_CONVEYANCE_ROLE_RE.search(query_role_text))
    c_household = bool(_HOUSEHOLD_ROLE_RE.search(cand_role_text))
    c_conveyance = bool(_CONVEYANCE_ROLE_RE.search(cand_role_text))
    role_mismatch = ""
    if q_household and not q_conveyance and c_conveyance and not c_household:
        role_mismatch = "household_storage_vs_conveyance_packing"
    elif q_conveyance and not q_household and c_household and not c_conveyance:
        role_mismatch = "conveyance_packing_vs_household_storage"

    # Complete-article vs spare-part role protection (universal across machinery/apparatus)
    q_asks_parts = bool(_QUERY_PARTS_CUES_RE.search(query_role_text))
    leaf_low = (profile.tariff_item_desc or "").strip().lower()
    # Standalone separately-presented sub-units classified under a parent "PARTS" subheading
    # (e.g. "SEPARATELY PRESENTED INDOOR UNITS OR OUTDOOR UNITS") are valid leaf matches for "unit" queries
    # as long as the leaf description itself does not start with "OF ..." or name "PARTS".
    leaf_explicit_standalone_unit = bool(
        not _CAND_PARTS_DESC_RE.match(leaf_low)
        and not _CAND_OF_MACHINE_RE.match(leaf_low)
        and re.search(r"\bseparately\s+presented\b", leaf_low)
        and re.search(r"\bunit(?:s)?\b", query_role_text.lower())
        and re.search(r"\bunit(?:s)?\b", leaf_low)
    )
    c_is_parts_only = bool(
        (
            _CAND_PARTS_SUB6_RE.match(profile.subheading_6digit_desc or "")
            and not leaf_explicit_standalone_unit
        )
        or _CAND_PARTS_DESC_RE.match(profile.tariff_item_desc or "")
        or (
            _CAND_PARTS_STAT_RE.search(profile.statutory_description or "")
            and (
                _CAND_OF_MACHINE_RE.match(profile.subheading_6digit_desc or "")
                or _CAND_OF_MACHINE_RE.match(profile.tariff_item_desc or "")
            )
        )
        or (
            _CAND_PARTS_DESC_RE.match(profile.heading_4digit_desc or "")
            and not q_asks_parts
        )
    )
    q_explicit_parts = bool(
        re.search(
            r"\b(?:part|parts|spare|spares|component|components|accessory|accessories|subassembly)\b",
            query_role_text,
            re.IGNORECASE,
        )
    )
    if c_is_parts_only and not q_asks_parts:
        role_mismatch = "complete_article_vs_parts"
    elif (
        q_explicit_parts
        and not c_is_parts_only
        and not re.search(
            r"\bparts?(?:\s+thereof|\s+of|\s+for|\s+and\s+accessories)?\b",
            f"{profile.heading_4digit_desc} {profile.subheading_6digit_desc} {profile.tariff_item_desc}",
            re.IGNORECASE,
        )
    ):
        role_mismatch = "parts_vs_complete_article"

    # Detect generic-superordinate-only article match when query has more specific nouns
    matched_stems = {_stem(t) for m in article_matches for t in _tokenize_content(m)}
    specific_query_tokens = article_core_tokens - _BROAD_SUPERORDINATES
    generic_only_match = bool(article_matches) and bool(specific_query_tokens) and not bool(matched_stems & specific_query_tokens)

    # 4. Contradiction vs Missing Attribute detection
    contradictions: List[str] = []
    missing_attributes: List[str] = []

    if query_mat_fams and profile.statutory_material_families:
        # Heading clauses with permissive "any material or of X" (e.g. Heading 9404 bedding stuffed
        # with "any material or of cellular rubber or plastics") do not contradict non-plastic/rubber leaves
        # unless the 6-digit subheading or 8-digit tariff item itself mandates a specific material.
        sub_leaf_txt = f"{profile.subheading_6digit_desc} {profile.tariff_item_desc}".strip()
        sub_leaf_fams = _detect_material_families(_tokenize_content(sub_leaf_txt), sub_leaf_txt)
        permissive_any_mat = (
            not sub_leaf_fams
            and bool(re.search(r"\bany\s+material\b", profile.heading_4digit_desc or "", re.IGNORECASE))
        )
        # When subheading/leaf explicitly declares material families (e.g. 391710 "OF HARDENED PROTEIN"
        # under Heading 3917 "OF PLASTICS"), test compatibility against leaf-level families first.
        target_cand_fams = sub_leaf_fams if sub_leaf_fams else profile.statutory_material_families
        has_compatible = permissive_any_mat
        if not has_compatible:
            for qf in query_mat_fams:
                if qf in target_cand_fams:
                    has_compatible = True
                    break
                for cf in target_cand_fams:
                    if frozenset({qf, cf}) in _COMPATIBLE_FAMILIES:
                        has_compatible = True
                        break
                if has_compatible:
                    break
        if not has_compatible:
            contradictions.append(
                f"Material contradiction: query states {sorted(query_mat_fams)}, statutory description specifies {sorted(target_cand_fams)}"
            )
    elif not query_mat_fams and profile.statutory_material_families:
        missing_attributes.append(f"material ({'/'.join(sorted(profile.statutory_material_families))})")

    # Chapter 98 (Special Import Regimes: 9801 Project Imports, 9802 Lab Chemicals,
    # 9803 Baggage, 9804 Personal Use by Post/Air, 9805 Ship/Aircraft Stores) requires explicit regime cues.
    hsn4 = str(profile.hsn_code or "").strip()[:4]
    if profile.chapter_code == "98" and hsn4 in {"9801", "9802", "9803", "9804", "9805"}:
        full_q_low = f"{product_intent.raw_description or ''} {product_intent.finished_article or ''} {product_intent.packaging_or_presentation or ''} {product_intent.function_use or ''}".lower()
        regime_patterns = {
            "9801": r"\b(?:project\s+import|initial\s+setting\s+up|substantial\s+expansion|power\s+project)\b",
            "9802": r"\b(?:laboratory\s+chemical|500\s*g|500\s*ml)\b",
            "9803": r"\b(?:baggage|passenger|crew)\b",
            "9804": r"\b(?:personal\s+use|imported\s+by\s+post|postal\s+import)\b",
            "9805": r"\b(?:stores\s+on\s+board|vessel|aircraft\s+stores)\b",
        }
        if not re.search(regime_patterns[hsn4], full_q_low):
            contradictions.append(
                f"Chapter 98 special-provision regime (Heading {hsn4}) requires explicit import regime confirmation not present in description"
            )

    # Processing / construction contradiction checks (e.g. knitted vs not knitted or crocheted)
    proc_low = f"{product_intent.processing_form or ''} {product_intent.finished_article}".lower()
    cand_hier_low = f"{profile.chapter_title} {profile.heading_4digit_desc} {profile.subheading_6digit_desc} {profile.tariff_item_desc} {profile.statutory_description}".lower()
    if re.search(r"\b(?:knitted|crocheted|knit)\b", proc_low) and not re.search(r"\bnot\s+knitted\b", proc_low):
        if re.search(r"\bnot\s+knitted(?:\s+or\s+crocheted)?\b", cand_hier_low) or re.search(r"\bwoven\b", cand_hier_low):
            contradictions.append("Construction contradiction: query specifies knitted/crocheted, candidate is not knitted / woven")
    elif re.search(r"\b(?:woven|not\s+knitted)\b", proc_low):
        if re.search(r"\bknitted\s+or\s+crocheted\b", cand_hier_low) and not re.search(r"\bnot\s+knitted\b", cand_hier_low):
            contradictions.append("Construction contradiction: query specifies woven/not knitted, candidate is knitted or crocheted")
    if re.search(r"\bseamless\b", proc_low) and re.search(r"\bwelded\b", cand_hier_low) and not re.search(r"\bseamless\b", cand_hier_low):
        contradictions.append("Construction contradiction: query specifies seamless, candidate is welded")
    elif re.search(r"\bwelded\b", proc_low) and not re.search(r"\bseamless\b", proc_low) and re.search(r"\bseamless\b", cand_hier_low) and not re.search(r"\bwelded\b", cand_hier_low):
        contradictions.append("Construction contradiction: query specifies welded, candidate is seamless")
    if re.search(r"\bflexible\b", proc_low) and not re.search(r"\brigid\b", proc_low) and re.search(r"\brigid\b", cand_hier_low) and not re.search(r"\bflexible\b", cand_hier_low):
        contradictions.append("Form contradiction: query specifies flexible, candidate is rigid")
    elif re.search(r"\brigid\b", proc_low) and not re.search(r"\bflexible\b", proc_low) and re.search(r"\bflexible\b", cand_hier_low) and not re.search(r"\brigid\b", cand_hier_low):
        contradictions.append("Form contradiction: query specifies rigid, candidate is flexible")
    if re.search(r"\broasted\b", proc_low) and re.search(r"\bnot\s+roasted\b|\bunroasted\b", cand_hier_low):
        contradictions.append("Process contradiction: query specifies roasted, candidate is unroasted")
    q_full_state = f"{proc_low} {product_intent.raw_description or ''}".lower()
    if re.search(r"\b(?:unrecorded|blank|recordable)\b", q_full_state) and re.search(r"\brecorded\b", cand_hier_low) and not re.search(r"\bunrecorded|recordable|blank\b", cand_hier_low):
        contradictions.append("State contradiction: query specifies unrecorded/blank/recordable media, candidate specifies recorded media")
    elif re.search(r"\brecorded\b", q_full_state) and not re.search(r"\bunrecorded|recordable|blank\b", q_full_state) and re.search(r"\bunrecorded\b", cand_hier_low) and not re.search(r"\brecorded\b", cand_hier_low):
        contradictions.append("State contradiction: query specifies recorded media, candidate specifies unrecorded media")

    # Mutually-exclusive prime-mover / power-source contradiction (e.g. wind vs water/steam/solar/nuclear)
    _power_sources = {
        "wind": r"\bwind[-\s]*powered\b|\bwind\s+turbine\b|\bwindmill\b",
        "water_hydro": r"\bwater\s+turbine\b|\bhydro[-\s]*electric\b|\bhydraulic\s+turbine\b",
        "steam": r"\bsteam\s+turbine\b|\bvapor\s+turbine\b",
        "solar": r"\bsolar\b|\bphotovoltaic\b",
        "nuclear": r"\bnuclear\s+reactor\b",
    }
    q_pm = {k for k, pat in _power_sources.items() if re.search(pat, q_full_state)}
    c_pm = {k for k, pat in _power_sources.items() if re.search(pat, cand_hier_low)}
    if q_pm and c_pm and not (q_pm & c_pm):
        contradictions.append(
            f"Power-source contradiction: query specifies {sorted(q_pm)}, candidate specifies {sorted(c_pm)}"
        )

    # Statutory engine/propulsion type contradiction (spark-ignition/petrol vs compression-ignition/diesel)
    _cand_pos_eng = re.sub(r"\bother\s+than\s+spark[-\s]*ignition\b|\bnot\s+spark[-\s]*ignition\b", " ", cand_hier_low)
    q_spark = bool(re.search(r"\b(?:petrol|gasoline|spark[-\s]*ignition)\b", f"{proc_low} {product_intent.raw_description or ''}".lower()))
    q_diesel = bool(re.search(r"\b(?:diesel|compression[-\s]*ignition)\b", f"{proc_low} {product_intent.raw_description or ''}".lower()))
    c_spark = bool(re.search(r"\b(?:spark[-\s]*ignition|petrol|gasoline)\b", _cand_pos_eng))
    c_diesel = bool(re.search(r"\b(?:compression[-\s]*ignition|diesel)\b", cand_hier_low))
    if q_spark and not q_diesel and c_diesel and not c_spark:
        contradictions.append("Propulsion contradiction: query specifies spark-ignition/petrol, candidate specifies diesel/compression-ignition")
    elif q_diesel and not q_spark and c_spark and not c_diesel:
        contradictions.append("Propulsion contradiction: query specifies diesel/compression-ignition, candidate specifies spark-ignition/petrol")

    # Generic negated-attribute check (e.g., "non-circular" vs "circular", "unplasticised" vs "plasticised")
    query_neg_source = f"{proc_low} {product_intent.raw_description or ''}".lower()
    cand_pos_low = re.sub(r"\b(?:non[-\s]+|not\s+|un)([a-z]{4,})\b", " ", cand_hier_low)
    _neg_stop = {"this", "that", "with", "from", "than", "more", "less", "such", "other", "none"}
    neg_attrs: Set[str] = set()
    for neg_attr in re.findall(r"\bnon[-\s]+([a-z]{4,})\b", query_neg_source):
        if neg_attr not in _neg_stop:
            neg_attrs.add(neg_attr)
    for neg_attr in re.findall(r"\bun([a-z]{5,}(?:ed|ised|ized|able|ible|bleached|worked|alloyed))\b", query_neg_source):
        if neg_attr not in _neg_stop:
            neg_attrs.add(neg_attr)
    for neg_attr in sorted(neg_attrs):
        if re.search(rf"\b{re.escape(neg_attr)}\b", cand_pos_low):
            contradictions.append(
                f"Attribute contradiction: query specifies un/non-{neg_attr}, candidate specifies {neg_attr}"
            )

    # Negative statutory phrasing check (e.g., "not containing X", "other than T-shirts"),
    # explicitly ignoring permissive "whether or not containing X" clauses.
    cand_desc_low = re.sub(
        r"\bwhether\s+or\s+not\s+containing\b",
        "optionally_containing",
        f"{profile.tariff_item_desc} {profile.statutory_description}".lower(),
    )
    neg_matches = re.findall(r"\b(?:not\s+containing|other\s+than(?:\s+of)?|excluding)\s+([a-z0-9\-\s]{3,40}?)(?:[,;\)]|$)", cand_desc_low)
    query_full_low = f"{product_intent.finished_article} {query_mat_text} {' '.join(product_intent.ingredients_or_additives)}".lower()
    _q_hyphen_words = {_stem(t.replace("-", "")) for t in re.findall(r"\b[a-z0-9]+-[a-z0-9]+\b", query_full_low)}
    # Strip hyphenated tokens from base tokenization so "t-shirt" -> "tshirt" (not plain "shirt")
    q_full_no_hyphen = re.sub(r"\b[a-z0-9]+-[a-z0-9]+\b", " ", query_full_low)
    q_full_toks = _tokenize_content(q_full_no_hyphen) | _q_hyphen_words
    for neg_phrase in neg_matches:
        neg_clean = neg_phrase.strip()
        _neg_hw = {_stem(t.replace("-", "")) for t in re.findall(r"\b[a-z0-9]+-[a-z0-9]+\b", neg_clean)}
        _neg_no_hyphen = re.sub(r"\b[a-z0-9]+-[a-z0-9]+\b", " ", neg_clean)
        neg_toks = _tokenize_content(_neg_no_hyphen) | _neg_hw
        if neg_toks and neg_toks.issubset(q_full_toks):
            contradictions.append(f"Statutory exclusion matched: '{neg_clean}'")

    # 5. Evidence-based verdict & 5-way compatibility classification:
    # Combine master-derived corpus qualifier/material vocabularies with structural seeds
    hi = get_hierarchy_intelligence()
    dynamic_mat_cues = all_mat_cues | hi.corpus_material_tokens
    dynamic_qual_tokens = _LEAF_QUALIFIER_TOKENS | hi.corpus_qualifier_tokens

    head_noun_tokens = _tokenize_content(getattr(product_intent, "product_head_noun", "") or "") - dynamic_mat_cues - generic_stems
    alias_tokens = _tokenize_content(" ".join(getattr(product_intent, "alternative_names_and_aliases", []) or [])) - dynamic_mat_cues - generic_stems
    primary_id_tokens = head_noun_tokens | alias_tokens
    if not primary_id_tokens and article_core_tokens:
        ordered_core = [t for t in (_stem(w) for w in re.findall(r"\b[a-z0-9]{2,}\b", product_intent.finished_article.lower())) if t in article_core_tokens]
        if ordered_core:
            primary_id_tokens = {ordered_core[-1]}
    if any(t.endswith("ing") and len(t) > 5 for t in primary_id_tokens):
        cand_vocab = profile.article_tokens | profile.inherited_parent_articles | profile.leaf_article_tokens
        for t in list(primary_id_tokens):
            if t.endswith("ing") and len(t) > 5 and (t[:-3] + "e") in cand_vocab:
                primary_id_tokens.add(t[:-3] + "e")

    # Statutory explicit exclusion against primary article identity
    excluded_id_hits = sorted(primary_id_tokens & profile.explicit_exclusions)
    if excluded_id_hits and not (primary_id_tokens & profile.leaf_article_tokens):
        contradictions.append(
            f"Explicit statutory exclusion matched for primary article {excluded_id_hits}"
        )

    leaf_specific_tokens = {
        t for t in (profile.leaf_article_tokens - dynamic_mat_cues - dynamic_qual_tokens)
        if not t.isdigit()
    }
    leaf_introduced_tokens = leaf_specific_tokens - profile.inherited_parent_articles
    leaf_clauses_are_qualifiers = profile.is_qualifying_only_leaf or all(
        (
            not cl
            or cl.upper() in {"OTHER", "OTHERS"}
            or bool(_LEAF_QUALIFIER_PREFIX_RE.match(cl))
        )
        for cl in (profile.tariff_item_desc.strip(), profile.subheading_6digit_desc.strip())
    )
    if primary_id_tokens:
        # Guard against sibling-exclusive contradictory articles (preventing blind parent inheritance)
        if (primary_id_tokens & profile.contradictory_sibling_articles) and not (
            primary_id_tokens & (profile.leaf_article_tokens | profile.inherited_parent_articles)
        ):
            primary_article_matched = False
        elif leaf_introduced_tokens and not leaf_clauses_are_qualifiers and not (primary_id_tokens & leaf_specific_tokens) and not (article_core_tokens & leaf_introduced_tokens):
            primary_article_matched = False
        else:
            primary_article_matched = bool(
                primary_id_tokens & (profile.article_tokens | profile.inherited_parent_articles)
            )
    else:
        primary_article_matched = bool(article_matches)
    # Parts-role alignment: when Stage 1 identifies a part/component/accessory (`q_asks_parts` or head_noun=='part')
    # and the statutory item is explicitly a parts subheading/leaf (`c_is_parts_only`) for a matched machine/article,
    # parts-identity compatibility holds even though 'parts' is filtered from general content stopwords.
    if not primary_article_matched and q_asks_parts and article_matches and (
        c_is_parts_only
        or any("part" in m.lower() for m in article_matches)
        or bool(re.search(r"\bparts\s+thereof\b", profile.statutory_description or "", re.IGNORECASE))
    ):
        primary_article_matched = True
    head_is_broad = bool(head_noun_tokens) and head_noun_tokens.issubset(_BROAD_SUPERORDINATES)
    modifier_only_match = bool(article_matches) and not primary_article_matched

    has_article_query = bool(article_core_tokens)
    has_cand_article_vocab = bool(profile.article_tokens or profile.article_keywords or profile.consumer_synonyms)
    material_only_no_article = bool(material_matches) and not article_matches and has_article_query and has_cand_article_vocab

    if contradictions:
        status = CONTRADICTED
        compatibility_level = "EXPLICIT_CONTRADICTION"
        ev_score = 0.0
    elif (
        article_matches
        and primary_article_matched
        and not generic_only_match
        and not role_mismatch
        and (material_matches or not query_mat_fams)
        and not missing_attributes
        and relation_value == "SAME_PRODUCT"
    ):
        status = SUPPORTED
        compatibility_level = "DIRECT_COMPATIBILITY"
        propulsion_bonus = 0.05 if ((q_spark and c_spark and not c_diesel) or (q_diesel and c_diesel and not c_spark)) else 0.0
        ev_score = min(1.0, 0.65 * cross_encoder_confidence + 0.25 + (0.10 if material_matches else 0.0) + propulsion_bonus)
    elif (article_matches and (primary_article_matched or head_is_broad or relation_value in ("SAME_PRODUCT", "INSUFFICIENT_INFORMATION"))) or (
        material_matches and not material_only_no_article and (primary_article_matched or not has_article_query)
    ):
        status = POSSIBLY_SUPPORTED
        compatibility_level = "PARTIAL_COMPATIBILITY"
        ev_score = min(0.95, 0.60 * cross_encoder_confidence + (0.20 if primary_article_matched else 0.08) + (0.10 if material_matches else 0.0))
        if modifier_only_match and not head_is_broad:
            ev_score = max(0.0, ev_score - 0.10)
        if generic_only_match:
            ev_score = max(0.0, ev_score - 0.15)
        if role_mismatch == "complete_article_vs_parts":
            ev_score = max(0.0, ev_score - 0.25)
        elif role_mismatch:
            ev_score = max(0.0, ev_score - 0.15)
    elif modifier_only_match or material_only_no_article:
        status = INSUFFICIENT_EVIDENCE
        compatibility_level = "RELATED_DIFFERENT_ARTICLE"
        ev_score = max(0.0, 0.40 * cross_encoder_confidence)
    else:
        status = INSUFFICIENT_EVIDENCE
        compatibility_level = "INSUFFICIENT_EVIDENCE"
        ev_score = max(0.0, 0.50 * cross_encoder_confidence)

    trace_parts = [
        f"compat={compatibility_level}",
        f"primary_head_match={primary_article_matched}",
        f"article_match={article_matches[:3] or 'none'}",
        f"material_match={material_matches[:3] or 'none'}",
        f"chapter_compat={chapter_compatible}",
        f"heading_compat={heading_compatible}",
    ]
    if modifier_only_match:
        trace_parts.append("guard=modifier_only_no_head_noun")
    if material_only_no_article:
        trace_parts.append("guard=material_only_no_article")
    if generic_only_match:
        trace_parts.append("penalty=generic_superordinate_only")
    if role_mismatch:
        trace_parts.append(f"role_mismatch={role_mismatch}")
    if missing_attributes:
        trace_parts.append(f"missing={missing_attributes}")
    if contradictions:
        trace_parts.append(f"contradictions={contradictions}")

    return CandidateEvidenceResult(
        status=status,
        compatibility_level=compatibility_level,
        primary_article_matched=primary_article_matched,
        article_matches=article_matches[:6],
        statutory_article_matches=statutory_article_matches[:6],
        material_matches=material_matches[:6],
        chapter_compatible=chapter_compatible,
        heading_compatible=heading_compatible,
        role_mismatch=role_mismatch,
        contradictions=contradictions,
        missing_attributes=missing_attributes,
        evidence_score=ev_score,
        trace_summary="; ".join(trace_parts),
        hierarchy_intelligence={
            "is_qualifying_only_leaf": profile.is_qualifying_only_leaf,
            "qualifying_reason": profile.qualifying_reason,
            "inherited_parent_articles": sorted(profile.inherited_parent_articles)[:10],
            "sibling_shared_tokens": sorted(profile.sibling_shared_tokens)[:10],
            "sibling_distinguishing_tokens": sorted(profile.sibling_distinguishing_tokens)[:10],
            "explicit_exclusions": sorted(profile.explicit_exclusions)[:8],
            "contradictory_sibling_articles": sorted(profile.contradictory_sibling_articles)[:8],
        },
    )


def consolidate_duplicate_records(candidates: Sequence[Any]) -> List[Any]:
    """
    Consolidates duplicate records sharing the same `hsn_code` without merging
    distinct 8-digit tariff items.
    """
    seen_hsn: Dict[str, Any] = {}
    ordered: List[Any] = []
    for item in candidates:
        hsn = str(getattr(getattr(item, "candidate", item), "hsn_code", "") or "").strip()
        if not hsn:
            continue
        if hsn not in seen_hsn:
            seen_hsn[hsn] = item
            ordered.append(item)
    return ordered

