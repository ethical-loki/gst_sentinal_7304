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
    raw = re.findall(r"\b[a-z0-9]{2,}\b", text.lower())
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
    material_tokens: Set[str] = field(default_factory=set)
    chapter_tokens: Set[str] = field(default_factory=set)
    material_families: Set[str] = field(default_factory=set)


@dataclass
class CandidateEvidenceResult:
    status: str  # SUPPORTED | POSSIBLY_SUPPORTED | CONTRADICTED | INSUFFICIENT_EVIDENCE
    article_matches: List[str] = field(default_factory=list)
    material_matches: List[str] = field(default_factory=list)
    chapter_compatible: bool = False
    contradictions: List[str] = field(default_factory=list)
    missing_attributes: List[str] = field(default_factory=list)
    evidence_score: float = 0.0
    trace_summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "article_matches": list(self.article_matches),
            "material_matches": list(self.material_matches),
            "chapter_compatible": self.chapter_compatible,
            "contradictions": list(self.contradictions),
            "missing_attributes": list(self.missing_attributes),
            "evidence_score": round(float(self.evidence_score), 4),
            "trace_summary": self.trace_summary,
        }


def build_candidate_profile(raw_rec: Optional[Dict[str, Any]], candidate: Any) -> CandidateProfile:
    """
    Normalizes a candidate profile from `enriched_master_hsn.parquet` fields.
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

    art_text = " ".join([item_desc, stat_desc, sub6_desc, " ".join(art_kws), " ".join(cons_syns)])
    mat_text = " ".join([" ".join(mat_kws), item_desc, stat_desc, sub6_desc, hd4_desc])

    art_tokens = _tokenize_content(art_text)
    mat_tokens = _tokenize_content(" ".join(mat_kws)) | (_tokenize_content(item_desc) & {
        _stem(c) for cues in _MATERIAL_FAMILIES.values() for c in cues if " " not in c
    })
    chap_tokens = _tokenize_content(chap_title)
    mat_fams = _detect_material_families(_tokenize_content(mat_text), mat_text)

    return CandidateProfile(
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
        material_tokens=mat_tokens,
        chapter_tokens=chap_tokens,
        material_families=mat_fams,
    )


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
    # Remove pure material tokens from head_tokens when checking article-noun overlap
    all_mat_cues = {_stem(c) for cues in _MATERIAL_FAMILIES.values() for c in cues if " " not in c}
    article_core_tokens = head_tokens - all_mat_cues
    if not article_core_tokens:
        article_core_tokens = head_tokens

    # 1. Article identity matching (Article Keywords + consumer synonyms + statutory descriptions)
    article_matches: List[str] = []
    art_phrase_pool = profile.article_keywords + profile.consumer_synonyms
    head_low = product_intent.finished_article.lower()
    for phrase in art_phrase_pool:
        if phrase and (phrase in head_low or any(_stem(w) in article_core_tokens for w in phrase.split() if len(w) >= 3)):
            if phrase not in article_matches:
                article_matches.append(phrase)
    for tok in sorted(article_core_tokens & profile.article_tokens):
        if tok not in article_matches:
            article_matches.append(tok)

    # 2. Material & composition matching
    query_mat_text = " ".join(product_intent.constituent_materials)
    query_mat_tokens = _tokenize_content(query_mat_text) | (head_tokens & all_mat_cues)
    query_mat_fams = _detect_material_families(query_mat_tokens, f"{product_intent.finished_article} {query_mat_text}")

    material_matches: List[str] = sorted(query_mat_tokens & profile.material_tokens)
    for kw in profile.material_keywords:
        if kw and kw in f"{head_low} {query_mat_text.lower()}" and kw not in material_matches:
            material_matches.append(kw)

    # 3. Chapter compatibility (supporting evidence only, never standalone proof)
    intent_all_tokens = _tokenize_content(
        f"{product_intent.finished_article} {query_mat_text} {product_intent.processing_form or ''} {product_intent.function_use or ''}"
    )
    chapter_compatible = bool(intent_all_tokens & profile.chapter_tokens) or bool(article_matches)

    # 4. Contradiction vs Missing Attribute detection
    contradictions: List[str] = []
    missing_attributes: List[str] = []

    if query_mat_fams and profile.material_families:
        # Check if ALL query material families conflict with ALL candidate material families
        has_compatible = False
        for qf in query_mat_fams:
            if qf in profile.material_families:
                has_compatible = True
                break
            for cf in profile.material_families:
                if frozenset({qf, cf}) in _COMPATIBLE_FAMILIES:
                    has_compatible = True
                    break
            if has_compatible:
                break
        if not has_compatible:
            contradictions.append(
                f"Material contradiction: query states {sorted(query_mat_fams)}, candidate specifies {sorted(profile.material_families)}"
            )
    elif not query_mat_fams and profile.material_families:
        # Missing information is NEVER treated as a contradiction
        missing_attributes.append(f"material ({'/'.join(sorted(profile.material_families))})")

    # Negative statutory phrasing check (e.g., "not containing X", "other than X")
    cand_desc_low = f"{profile.tariff_item_desc} {profile.statutory_description}".lower()
    neg_matches = re.findall(r"\b(?:not\s+containing|other\s+than\s+(?:of\s+)?|excluding)\s+([a-z0-9\s]{3,30}?)(?:[,;]|$)", cand_desc_low)
    query_full_low = f"{product_intent.finished_article} {query_mat_text} {' '.join(product_intent.ingredients_or_additives)}".lower()
    for neg_phrase in neg_matches:
        neg_toks = _tokenize_content(neg_phrase)
        if neg_toks and neg_toks.issubset(_tokenize_content(query_full_low)):
            contradictions.append(f"Statutory exclusion matched: '{neg_phrase.strip()}'")

    # 5. Evidence-based verdict
    if contradictions:
        status = CONTRADICTED
        ev_score = 0.0
    elif article_matches and (material_matches or not query_mat_fams) and not missing_attributes and relation_value == "SAME_PRODUCT":
        status = SUPPORTED
        ev_score = min(1.0, 0.65 * cross_encoder_confidence + 0.25 + (0.10 if material_matches else 0.0))
    elif article_matches or relation_value in ("SAME_PRODUCT", "RELATED_PRODUCT"):
        status = POSSIBLY_SUPPORTED
        ev_score = min(0.95, 0.60 * cross_encoder_confidence + (0.20 if article_matches else 0.05) + (0.10 if material_matches else 0.0))
    else:
        status = INSUFFICIENT_EVIDENCE
        ev_score = max(0.0, 0.50 * cross_encoder_confidence)

    trace_parts = [
        f"article_match={article_matches[:3] or 'none'}",
        f"material_match={material_matches[:3] or 'none'}",
        f"chapter_compat={chapter_compatible}",
    ]
    if missing_attributes:
        trace_parts.append(f"missing={missing_attributes}")
    if contradictions:
        trace_parts.append(f"contradictions={contradictions}")

    return CandidateEvidenceResult(
        status=status,
        article_matches=article_matches[:6],
        material_matches=material_matches[:6],
        chapter_compatible=chapter_compatible,
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

