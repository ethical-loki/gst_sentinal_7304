"""
src/ml/ambiguity_resolver.py
============================
Step 3: Attribute-Driven Dynamic Ambiguity Resolver

Identifies the specific missing attribute(s) separating competing statutory
classifications directly from the competing tariff descriptions:
  - material
  - construction
  - processing_state
  - intended_use
  - product_completeness

Never relies on hardcoded product-specific rules; asks the user only for the
missing information that can actually change the tariff classification.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from src.ml.relevance_classifier import (
    ClassifiedTariffCandidate,
    RelationLabel,
    RelevanceClassifier,
)

# Statutory linguistic cues per attribute dimension (domain-general customs terminology)
ATTRIBUTE_CUE_VOCAB: Dict[str, Set[str]] = {
    "construction": {
        "knitted", "not knitted", "crocheted", "not crocheted", "woven", "not woven",
        "nonwoven", "seamless", "welded", "moulded", "molded", "forged", "cast",
        "extruded", "laminated", "braided", "printed", "assembled", "portable",
        "hand-operated",
    },
    "processing_state": {
        "raw", "unworked", "semi-finished", "finished", "coated", "plated",
        "galvanized", "polished", "annealed", "tempered", "roasted", "dried",
        "frozen", "liquid", "powder", "granules", "sheets", "bars", "rods",
    },
    "intended_use": {
        "industrial", "domestic", "household", "kitchen", "tableware",
        "medical", "surgical", "agricultural", "packaging", "transport",
        "motor vehicles", "electrical", "construction", "office", "retail",
    },
    "product_completeness": {
        "parts", "accessories", "components", "assemblies", "subassemblies",
        "complete", "incomplete", "unassembled", "knocked down", "kits", "sets",
        "fittings", "spare",
    },
}


def _extract_material_tokens(raw: str) -> Set[str]:
    if not raw:
        return set()
    return {t.strip().lower() for t in re.split(r"[,;|]+", raw) if len(t.strip()) >= 2}


def _candidate_text(cand: Any) -> str:
    return " ".join(
        [
            str(getattr(cand, "chapter_title", "") or ""),
            str(getattr(cand, "heading_4digit_desc", "") or ""),
            str(getattr(cand, "description", "") or ""),
            str(getattr(cand, "article_keywords", "") or ""),
            str(getattr(cand, "material_keywords", "") or ""),
        ]
    ).lower()


def identify_separating_attributes(
    competing: Sequence[ClassifiedTariffCandidate],
    product_intent: str,
) -> Tuple[List[str], Dict[str, List[str]]]:
    """
    Compares competing tariff candidates to find which attribute dimensions
    actually differ across their statutory descriptions AND are missing from
    `product_intent`.
    """
    query_lower = (product_intent or "").lower()
    separating: List[str] = []
    evidence: Dict[str, List[str]] = {}

    # 1. Material check via material_keywords & chapter differences
    # Only treat material as a separating attribute if candidates span multiple chapters
    # OR their statutory descriptions themselves differ on material terms.
    unique_chaps = {c.candidate.chapter_code for c in competing if c.candidate.chapter_code}
    mat_sets = [
        _extract_material_tokens(c.candidate.material_keywords) for c in competing
    ]
    non_empty_mats = [m for m in mat_sets if m]
    if len(non_empty_mats) >= 2 and len(unique_chaps) > 1:
        union_mats = set().union(*non_empty_mats)
        common_mats = set.intersection(*non_empty_mats)
        diff_mats = sorted(
            m for m in (union_mats - common_mats) if m not in query_lower
        )
        if diff_mats:
            separating.append("material")
            evidence["material"] = diff_mats[:6]

    # 2. Construction, Processing State, Intended Use, Product Completeness
    cand_texts = [_candidate_text(c.candidate) for c in competing]
    for attr_name, cue_words in ATTRIBUTE_CUE_VOCAB.items():
        per_cand_hits: List[Set[str]] = []
        for txt in cand_texts:
            hits = {
                w for w in cue_words
                if re.search(rf"\b{re.escape(w)}\b", txt)
            }
            per_cand_hits.append(hits)

        union_hits = set().union(*per_cand_hits) if per_cand_hits else set()
        if not union_hits:
            continue
        common_hits = set.intersection(*per_cand_hits) if per_cand_hits else set()
        # Diff cues that are NOT already stated in the user's query
        diff_cues = sorted(
            w for w in (union_hits - common_hits) if not re.search(rf"\b{re.escape(w)}\b", query_lower)
        )
        if diff_cues:
            separating.append(attr_name)
            evidence[attr_name] = diff_cues[:6]

    # Fallback: if headings/chapters still differ and no specific cue matched,
    # check whether chapters differ (typically material or function)
    if not separating and len(competing) >= 2:
        chapters = {c.candidate.chapter_code for c in competing}
        if len(chapters) > 1:
            separating.append("material")
            evidence["material"] = [f"Chapter {ch}" for ch in sorted(chapters)]
        else:
            separating.append("intended_use")
            evidence["intended_use"] = [c.candidate.description[:40] for c in competing[:3]]

    return separating, evidence


@dataclass
class AmbiguityResolutionResult:
    status: str  # "CLEAR" | "AMBIGUOUS_MATERIAL" | "AMBIGUOUS_SPECIFICATION" | "INSUFFICIENT_INFORMATION" | "NO_RELEVANT_MATCH"
    selected_hsn: Optional[str] = None
    selected_chapter: Optional[str] = None
    selected_description: Optional[str] = None
    confidence: float = 0.0
    separating_attributes: List[str] = field(default_factory=list)
    attribute_evidence: Dict[str, List[str]] = field(default_factory=dict)
    same_product_candidates: List[ClassifiedTariffCandidate] = field(default_factory=list)
    insufficient_info_candidates: List[ClassifiedTariffCandidate] = field(default_factory=list)
    related_product_candidates: List[ClassifiedTariffCandidate] = field(default_factory=list)
    unrelated_candidates: List[ClassifiedTariffCandidate] = field(default_factory=list)
    clarification_question: Optional[str] = None
    clarification_options: List[str] = field(default_factory=list)
    rationale: str = ""


class ModelDrivenAmbiguityResolver:
    """
    Resolves tariff classification ambiguity using 4-class `RelevanceClassifier`
    outputs and statutory attribute-difference analysis.
    """

    def __init__(self, classifier: Optional[RelevanceClassifier] = None):
        self.classifier = classifier or RelevanceClassifier()

    def resolve(
        self,
        product_intent: str,
        tariff_rows: Sequence[Any],
    ) -> AmbiguityResolutionResult:
        classified = self.classifier.classify(product_intent, tariff_rows)
        return self.resolve_classified(product_intent, classified)

    def resolve_classified(
        self,
        product_intent: str,
        classified: Sequence[ClassifiedTariffCandidate],
    ) -> AmbiguityResolutionResult:
        same = [c for c in classified if c.relation == RelationLabel.SAME_PRODUCT]
        insuff = [c for c in classified if c.relation == RelationLabel.INSUFFICIENT_INFORMATION]
        related = [c for c in classified if c.relation == RelationLabel.RELATED_PRODUCT]
        unrelated = [c for c in classified if c.relation == RelationLabel.UNRELATED]

        # Case 1: No SAME_PRODUCT candidates
        if not same:
            if insuff:
                top_insuff = insuff[0].candidate
                sep_attrs, attr_ev = identify_separating_attributes(insuff[:4], product_intent)
                attr_phrase = ", ".join(a.replace("_", " ") for a in sep_attrs[:3]) or "material or intended use"
                options = [
                    f"HSN {c.candidate.hsn_code} ({c.candidate.chapter_title or 'Ch ' + c.candidate.chapter_code}): "
                    f"{c.candidate.description[:60]}"
                    for c in insuff[:3]
                ]
                return AmbiguityResolutionResult(
                    status="INSUFFICIENT_INFORMATION",
                    selected_hsn=top_insuff.hsn_code,
                    selected_chapter=top_insuff.chapter_code,
                    selected_description=top_insuff.description,
                    confidence=insuff[0].confidence,
                    separating_attributes=sep_attrs,
                    attribute_evidence=attr_ev,
                    insufficient_info_candidates=insuff,
                    related_product_candidates=related,
                    unrelated_candidates=unrelated,
                    clarification_question=(
                        f"Insufficient details to confirm '{product_intent}'. "
                        f"Please specify: {attr_phrase}."
                    ),
                    clarification_options=options,
                    rationale="No candidate met the calibrated SAME_PRODUCT threshold.",
                )

            return AmbiguityResolutionResult(
                status="NO_RELEVANT_MATCH",
                related_product_candidates=related,
                unrelated_candidates=unrelated,
                clarification_question=(
                    f"No matching tariff item found in the active schedule for '{product_intent}'."
                ),
                rationale="All retrieved candidates were classified as RELATED_PRODUCT or UNRELATED.",
            )

        # Case 2: Multiple SAME_PRODUCT candidates across distinct headings/chapters
        unique_headings = {
            c.candidate.hsn_code.replace(" ", "")[:4] for c in same if c.candidate.hsn_code
        }
        unique_chapters = {c.candidate.chapter_code for c in same if c.candidate.chapter_code}

        if len(unique_headings) > 1 or len(unique_chapters) > 1:
            # Diversify across distinct chapters/headings so one heading doesn't crowd out others
            diversified: List[ClassifiedTariffCandidate] = []
            seen_headings = set()
            seen_chaps = set()
            # First pass: one top candidate per distinct chapter
            for c in same:
                ch = c.candidate.chapter_code
                h4 = c.candidate.hsn_code.replace(" ", "")[:4]
                if ch not in seen_chaps:
                    seen_chaps.add(ch)
                    seen_headings.add(h4)
                    diversified.append(c)
            # Second pass: additional distinct 4-digit headings
            for c in same:
                h4 = c.candidate.hsn_code.replace(" ", "")[:4]
                if h4 not in seen_headings:
                    seen_headings.add(h4)
                    diversified.append(c)
                if len(diversified) >= 6:
                    break
            competing_pool = diversified[:6] if len(diversified) >= 2 else list(same[:6])

            sep_attrs, attr_ev = identify_separating_attributes(competing_pool, product_intent)
            attr_phrase = ", ".join(a.replace("_", " ") for a in sep_attrs[:3])
            status = (
                "AMBIGUOUS_MATERIAL"
                if (sep_attrs and sep_attrs[0] == "material")
                else "AMBIGUOUS_SPECIFICATION"
            )

            distinct_options: List[str] = []
            seen_opts = set()
            for c in competing_pool[:5]:
                mats = sorted(_extract_material_tokens(c.candidate.material_keywords))
                label_hint = (
                    f"Ch {c.candidate.chapter_code} | {', '.join(mats[:2])}"
                    if mats
                    else f"Ch {c.candidate.chapter_code} | {c.candidate.chapter_title}"
                )
                opt = f"HSN {c.candidate.hsn_code} ({label_hint}): {c.candidate.description[:55]}"
                if opt not in seen_opts:
                    seen_opts.add(opt)
                    distinct_options.append(opt)

            return AmbiguityResolutionResult(
                status=status,
                selected_hsn=same[0].candidate.hsn_code,
                selected_chapter=same[0].candidate.chapter_code,
                selected_description=same[0].candidate.description,
                confidence=same[0].confidence,
                separating_attributes=sep_attrs,
                attribute_evidence=attr_ev,
                same_product_candidates=same,
                insufficient_info_candidates=insuff,
                related_product_candidates=related,
                unrelated_candidates=unrelated,
                clarification_question=(
                    f"Multiple tariff headings apply to '{product_intent}'. "
                    f"To determine the exact HSN code, please specify: {attr_phrase}."
                ),
                clarification_options=distinct_options,
                rationale=(
                    f"{len(same)} SAME_PRODUCT candidates span {len(unique_headings)} distinct headings "
                    f"separated by [{attr_phrase}]; {len(related)} RELATED_PRODUCT and "
                    f"{len(unrelated)} UNRELATED candidates excluded."
                ),
            )

        # Case 3: Clear match (all SAME_PRODUCT candidates agree on 4-digit heading)
        top = same[0]
        return AmbiguityResolutionResult(
            status="CLEAR",
            selected_hsn=top.candidate.hsn_code,
            selected_chapter=top.candidate.chapter_code,
            selected_description=top.candidate.description,
            confidence=top.confidence,
            same_product_candidates=same,
            insufficient_info_candidates=insuff,
            related_product_candidates=related,
            unrelated_candidates=unrelated,
            rationale=(
                f"Confirmed SAME_PRODUCT match in heading {top.candidate.hsn_code[:4]}; "
                f"{len(related)} RELATED_PRODUCT and {len(unrelated)} UNRELATED candidates safely ignored."
            ),
        )
