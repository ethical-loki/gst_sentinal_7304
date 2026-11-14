"""
src/ml/ambiguity_resolver.py
============================
Phase 5: Model-Driven Ambiguity Resolver

Replaces naive chapter-number counting with semantic relationship-driven resolution:
  - Only `SAME_PRODUCT` candidates participate in material/specification ambiguity.
  - `RELATED_PRODUCT` candidates (e.g. machinery/components) are ignored for ambiguity.
  - `INSUFFICIENT_INFORMATION` triggers clarification or expert review.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set

from src.ml.relevance_classifier import (
    ClassifiedTariffCandidate,
    RelationLabel,
    RelevanceClassifier,
)


def _extract_material_tokens(raw: str) -> Set[str]:
    if not raw:
        return set()
    return {t.strip().lower() for t in re.split(r"[,;|]+", raw) if len(t.strip()) >= 2}


@dataclass
class AmbiguityResolutionResult:
    status: str  # "CLEAR" | "AMBIGUOUS_MATERIAL" | "INSUFFICIENT_INFORMATION" | "NO_RELEVANT_MATCH"
    selected_hsn: Optional[str] = None
    selected_chapter: Optional[str] = None
    selected_description: Optional[str] = None
    confidence: float = 0.0
    same_product_candidates: List[ClassifiedTariffCandidate] = field(default_factory=list)
    insufficient_info_candidates: List[ClassifiedTariffCandidate] = field(default_factory=list)
    related_product_candidates: List[ClassifiedTariffCandidate] = field(default_factory=list)
    clarification_question: Optional[str] = None
    clarification_options: List[str] = field(default_factory=list)
    rationale: str = ""


class ModelDrivenAmbiguityResolver:
    """
    Resolves tariff classification ambiguity using `RelevanceClassifier` states
    rather than simple chapter-number counting.
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

        # Case 1: No SAME_PRODUCT candidates
        if not same:
            if insuff:
                top_insuff = insuff[0].candidate
                options = [
                    f"{c.candidate.chapter_title or 'Ch ' + c.candidate.chapter_code}: "
                    f"{c.candidate.description[:60]}"
                    for c in insuff[:3]
                ]
                return AmbiguityResolutionResult(
                    status="INSUFFICIENT_INFORMATION",
                    selected_hsn=top_insuff.hsn_code,
                    selected_chapter=top_insuff.chapter_code,
                    selected_description=top_insuff.description,
                    confidence=insuff[0].confidence,
                    insufficient_info_candidates=insuff,
                    related_product_candidates=related,
                    clarification_question=(
                        f"Insufficient details to confirm '{product_intent}'. "
                        "Please specify the primary material, construction, or intended use."
                    ),
                    clarification_options=options,
                    rationale="No candidate met the calibrated SAME_PRODUCT threshold.",
                )

            return AmbiguityResolutionResult(
                status="NO_RELEVANT_MATCH",
                related_product_candidates=related,
                clarification_question=(
                    f"No matching tariff item found in the active schedule for '{product_intent}'."
                ),
                rationale="All retrieved candidates were classified as RELATED_PRODUCT or irrelevant.",
            )

        # Case 2: Multiple SAME_PRODUCT candidates across distinct headings/chapters
        unique_headings = {
            c.candidate.hsn_code.replace(" ", "")[:4] for c in same if c.candidate.hsn_code
        }
        unique_chapters = {c.candidate.chapter_code for c in same if c.candidate.chapter_code}

        if len(unique_headings) > 1 or len(unique_chapters) > 1:
            # Check if they differ by material keywords or chapter context
            distinct_options: List[str] = []
            seen_opts = set()
            for c in same[:4]:
                mats = sorted(_extract_material_tokens(c.candidate.material_keywords))
                mat_label = ", ".join(mats[:3]) if mats else c.candidate.chapter_title
                opt = f"HSN {c.candidate.hsn_code} ({mat_label}): {c.candidate.description[:55]}"
                if opt not in seen_opts:
                    seen_opts.add(opt)
                    distinct_options.append(opt)

            return AmbiguityResolutionResult(
                status="AMBIGUOUS_MATERIAL",
                selected_hsn=same[0].candidate.hsn_code,
                selected_chapter=same[0].candidate.chapter_code,
                selected_description=same[0].candidate.description,
                confidence=same[0].confidence,
                same_product_candidates=same,
                insufficient_info_candidates=insuff,
                related_product_candidates=related,
                clarification_question=(
                    f"Multiple valid tariff classifications apply to '{product_intent}'. "
                    "Which material or specification matches your product?"
                ),
                clarification_options=distinct_options,
                rationale=(
                    f"{len(same)} SAME_PRODUCT candidates span {len(unique_headings)} distinct headings; "
                    f"{len(related)} RELATED_PRODUCT distractors excluded from ambiguity."
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
            rationale=(
                f"Confirmed SAME_PRODUCT match in heading {top.candidate.hsn_code[:4]}; "
                f"{len(related)} RELATED_PRODUCT candidates safely ignored."
            ),
        )

