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
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

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
    "cotton": {"cotton"},
    "wool": {"wool", "woollen", "woolen", "cashmere", "merino", "animal hair"},
    "silk": {"silk"},
    "synthetic_textile": {"synthetic", "man-made", "polyester", "viscose", "rayon", "spandex", "elastane"},
    "wood": {"wood", "wooden", "timber", "plywood", "bamboo"},
    "rubber": {"rubber", "latex", "elastomer", "vulcanised", "vulcanized"},
    "glass_ceramic": {"glass", "ceramic", "porcelain", "stoneware", "earthenware"},
    "leather": {"leather", "hide", "skin"},
    "paper": {"paper", "paperboard", "cardboard"},
}

# Compatible material pairs (e.g. synthetic_textile vs plastics share nylon/polyester terms)
_COMPATIBLE_FAMILIES: Set[frozenset] = {
    frozenset({"plastics", "synthetic_textile"}),
    frozenset({"iron_steel", "aluminium"}),  # multi-metal assemblies can appear together unless exclusive
}


def _stem(tok: str) -> str:
    t = tok.lower().strip()
    if len(t) > 4 and t.endswith("ies"):
        return t[:-3] + "y"
    if len(t) > 4 and t.endswith("es") and t[-3] in "shxz":
        return t[:-2]
    if len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
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

    art_text = " ".join([item_desc, stat_desc, sub6_desc, hd4_desc, " ".join(art_kws), " ".join(cons_syns)])
    mat_text = " ".join([" ".join(mat_kws), item_desc, stat_desc, sub6_desc, hd4_desc])

    art_tokens = _tokenize_content(art_text)
    leaf_art_tokens = _tokenize_content(f"{item_desc} {sub6_desc}")
    parent_hd_tokens = _tokenize_content(hd4_desc)
    func_clauses = re.findall(r"\b(?:for|used\s+in|designed\s+(?:for|to))\s+([a-z0-9\s]{3,40}?)(?:[,;]|$)", f"{item_desc} {sub6_desc} {hd4_desc}".lower())
    functional_tokens = _tokenize_content(" ".join(func_clauses))
    mat_tokens = _tokenize_content(" ".join(mat_kws)) | (_tokenize_content(item_desc) & {
        _stem(c) for cues in _MATERIAL_FAMILIES.values() for c in cues if " " not in c
    })
    chap_tokens = _tokenize_content(chap_title)
    mat_fams = _detect_material_families(_tokenize_content(mat_text), mat_text)
    # Strip illustrative parenthetical examples ("for example, ...") and permissive "whether or not ..." clauses
    # before computing hard statutory material contradictions so broad parent-heading examples never reject valid leaves.
    stat_mat_raw = " ".join([item_desc, stat_desc, sub6_desc, hd4_desc])
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
    c_is_parts_only = bool(
        _CAND_PARTS_SUB6_RE.match(profile.subheading_6digit_desc or "")
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
    if c_is_parts_only and not q_asks_parts:
        role_mismatch = "complete_article_vs_parts"

    # Detect generic-superordinate-only article match when query has more specific nouns
    matched_stems = {_stem(t) for m in article_matches for t in _tokenize_content(m)}
    specific_query_tokens = article_core_tokens - _BROAD_SUPERORDINATES
    generic_only_match = bool(article_matches) and bool(specific_query_tokens) and not bool(matched_stems & specific_query_tokens)

    # 4. Contradiction vs Missing Attribute detection
    contradictions: List[str] = []
    missing_attributes: List[str] = []

    if query_mat_fams and profile.statutory_material_families:
        has_compatible = False
        for qf in query_mat_fams:
            if qf in profile.statutory_material_families:
                has_compatible = True
                break
            for cf in profile.statutory_material_families:
                if frozenset({qf, cf}) in _COMPATIBLE_FAMILIES:
                    has_compatible = True
                    break
            if has_compatible:
                break
        if not has_compatible:
            contradictions.append(
                f"Material contradiction: query states {sorted(query_mat_fams)}, statutory description specifies {sorted(profile.statutory_material_families)}"
            )
    elif not query_mat_fams and profile.statutory_material_families:
        missing_attributes.append(f"material ({'/'.join(sorted(profile.statutory_material_families))})")

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
    if re.search(r"\broasted\b", proc_low) and re.search(r"\bnot\s+roasted\b|\bunroasted\b", cand_hier_low):
        contradictions.append("Process contradiction: query specifies roasted, candidate is unroasted")

    # Negative statutory phrasing check (e.g., "not containing X", "other than X"),
    # explicitly ignoring permissive "whether or not containing X" clauses.
    cand_desc_low = re.sub(
        r"\bwhether\s+or\s+not\s+containing\b",
        "optionally_containing",
        f"{profile.tariff_item_desc} {profile.statutory_description}".lower(),
    )
    neg_matches = re.findall(r"\b(?:not\s+containing|other\s+than\s+(?:of\s+)?|excluding)\s+([a-z0-9\s]{3,30}?)(?:[,;]|$)", cand_desc_low)
    query_full_low = f"{product_intent.finished_article} {query_mat_text} {' '.join(product_intent.ingredients_or_additives)}".lower()
    for neg_phrase in neg_matches:
        neg_toks = _tokenize_content(neg_phrase)
        if neg_toks and neg_toks.issubset(_tokenize_content(query_full_low)):
            contradictions.append(f"Statutory exclusion matched: '{neg_phrase.strip()}'")

    # 5. Evidence-based verdict & 5-way compatibility classification:
    # Keep primary article head-noun identity separate from modifier/material/component overlap.
    head_noun_tokens = _tokenize_content(getattr(product_intent, "product_head_noun", "") or "") - all_mat_cues - generic_stems
    alias_tokens = _tokenize_content(" ".join(getattr(product_intent, "alternative_names_and_aliases", []) or [])) - all_mat_cues - generic_stems
    primary_id_tokens = head_noun_tokens | alias_tokens
    if not primary_id_tokens and article_core_tokens:
        # Fallback: last non-generic token of finished_article acts as primary noun
        ordered_core = [t for t in (_stem(w) for w in re.findall(r"\b[a-z0-9]{2,}\b", product_intent.finished_article.lower())) if t in article_core_tokens]
        if ordered_core:
            primary_id_tokens = {ordered_core[-1]}

    leaf_specific_tokens = profile.leaf_article_tokens - all_mat_cues - generic_stems
    if primary_id_tokens:
        if leaf_specific_tokens and not (primary_id_tokens & leaf_specific_tokens):
            # Leaf/subheading explicitly names a different article than the query head noun
            # (e.g., heading lists multiple articles, while leaf specifies only one of them).
            primary_article_matched = False
        else:
            primary_article_matched = bool(primary_id_tokens & profile.article_tokens)
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
        ev_score = min(1.0, 0.65 * cross_encoder_confidence + 0.25 + (0.10 if material_matches else 0.0))
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

