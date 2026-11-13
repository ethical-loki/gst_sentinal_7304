"""
Layer 4: Smart UI & Ambiguity Decision Engine
=============================================
Governs frontend recommendation state:
1. Auto-Lock High Confidence:
   If #1 result scores > 0.85 and leads #2 by at least 0.15, auto-lock as direct statutory match.
2. True Multi-Chapter Check:
   Only display MULTI-CHAPTER AMBIGUITY banner when count(distinct(chapter)) > 1.
3. Same-Chapter Variant Check:
   If all top results share the same chapter (count(distinct(chapter)) == 1),
   emit "Select specific variant/specification" with banner type "SAME_CHAPTER_VARIANT".
4. Material / Chapter Grouping:
   If results span 2+ chapters, group cards by Chapter (1 card per chapter) to avoid redundant duplicates.
5. Descriptive Evaluation Protocol:
   Outputs the structured report:
   - Article understood as
   - Recommended HSN
   - Confidence (High / Medium / Low)
   - Reasoning
   - Other plausible candidates (why it applies vs why it may not)
   - Missing information
   - Verification note
"""

import re
import math
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field
from src.search.hybrid_retrieval import SearchCandidate, HybridHSNEngine

logger = logging.getLogger(__name__)


class UIRecommendationCard(BaseModel):
    option_id: str
    label: str
    chapter_code: str
    chapter_title: str
    hsn_code: str
    hsn_description: str
    material_keywords: Optional[str] = ""
    article_keywords: Optional[str] = ""
    score: float
    confidence_pct: float
    is_chapter_representative: bool = False
    is_duplicate_description: bool = False
    is_truncated: bool = False


class PlausibleCandidate(BaseModel):
    hsn_code: str
    description: str
    why_it_could_apply: str
    why_it_may_not: str


class DescriptiveReport(BaseModel):
    article_understood_as: str
    recommended_hsn: str
    confidence: str  # "High" | "Medium" | "Low"
    confidence_score: float
    reasoning: str
    other_plausible_candidates: List[PlausibleCandidate] = Field(default_factory=list)
    missing_information: List[str] = Field(default_factory=list)
    verification_note: str = "Codes should be checked against the current official CBIC/GST HSN schedule before filing or invoicing."
    formatted_text: str = ""


class AmbiguityEvaluationResult(BaseModel):
    query: str
    is_ambiguous: bool
    banner_type: str  # "NONE" | "AUTO_LOCKED" | "SAME_CHAPTER_VARIANT" | "MULTI_CHAPTER_AMBIGUITY"
    banner_title: str
    clarification_question: Optional[str] = None
    direct_match: Optional[UIRecommendationCard] = None
    disambiguation_options: List[UIRecommendationCard] = Field(default_factory=list)
    distinct_chapters_count: int = 0
    top_candidates_count: int = 0
    descriptive_report: Optional[DescriptiveReport] = None


def disambiguate_candidate_labels(options: List[UIRecommendationCard]) -> None:
    """
    Ensures that every candidate card has a distinct, readable label derived
    strictly from statutory file columns (hsn_code, hsn_description, tariff_item_desc).
    No synthetic or invented trade names are added.
    Flags duplicate and truncated descriptions for user review.
    """
    from collections import Counter
    desc_counts = Counter(opt.hsn_description for opt in options)
    duplicates = {d for d, cnt in desc_counts.items() if cnt > 1}

    for opt in options:
        # Check if description appears truncated in the statutory file
        if opt.hsn_description.endswith(("PROCESSIN", "-", ":", ",")) or len(opt.hsn_description) > 200:
            opt.is_truncated = True

        if opt.hsn_description in duplicates:
            opt.is_duplicate_description = True
            opt.label = f"[{opt.hsn_code}] {opt.hsn_description}"


def format_hsn_code(code: str) -> str:
    """Formats 8-digit HSN code into standard statutory groups: 'XXXX XX XX'."""
    clean = str(code).replace(" ", "").strip()
    if len(clean) == 8:
        return f"{clean[:4]} {clean[4:6]} {clean[6:]}"
    elif len(clean) == 6:
        return f"{clean[:4]} {clean[4:]}"
    return clean


class SmartAmbiguityController:
    """
    Evaluates candidate predictions and drives Layer 4 Smart UI behavior.
    """

    def __init__(self, hybrid_engine: Optional[HybridHSNEngine] = None):
        self.engine = hybrid_engine or HybridHSNEngine.get_instance()

    def evaluate(self, user_query: str) -> AmbiguityEvaluationResult:
        q = (user_query or "").strip()
        candidates = self.engine.search(q, top_k=10)

        if not candidates:
            empty_report = DescriptiveReport(
                article_understood_as=f"Unrecognized commercial query: '{q}'.",
                recommended_hsn="Needs confirmation",
                confidence="Low",
                confidence_score=0.0,
                reasoning="No matching tariff heading or trade synonym found within the statutory master file.",
                missing_information=["Product constituent material, intended function, or standard trade denomination."],
                formatted_text=f"Article understood as: Query '{q}' is unrecognized.\n\nRecommended HSN: Needs confirmation\nConfidence: Low\nReasoning: No matching tariff item found."
            )
            return AmbiguityEvaluationResult(
                query=q,
                is_ambiguous=False,
                banner_type="NONE",
                banner_title="No matching tariff line found",
                clarification_question=None,
                direct_match=None,
                disambiguation_options=[],
                distinct_chapters_count=0,
                top_candidates_count=0,
                descriptive_report=empty_report
            )

        top1 = candidates[0]
        top2 = candidates[1] if len(candidates) > 1 else None
        score1 = top1.final_score
        score2 = top2.final_score if top2 else 0.0
        score_margin = score1 - score2

        # -------------------------------------------------------------
        # Rule 1: Auto-Lock High Confidence Guardrails
        # Thresholds read dynamically from config/intent_extraction_config.json
        # Requires:
        # 1. Reranker score >= auto_lock_reranker_min (config)
        # 2. Score margin >= auto_lock_margin_min (config)
        # 3. 8-digit leaf match (length == 8)
        # 4. No multi-material ambiguity on unstated queries
        # -------------------------------------------------------------
        direct_card, is_locked = self._evaluate_auto_lock(q, candidates)
        if is_locked and direct_card:
            report = self._build_descriptive_report(
                query=q,
                is_ambiguous=False,
                top1=top1,
                top2=top2,
                candidates=candidates
            )

            return AmbiguityEvaluationResult(
                query=q,
                is_ambiguous=False,
                banner_type="AUTO_LOCKED",
                banner_title="High-Confidence Statutory Classification Locked",
                clarification_question=None,
                direct_match=direct_card,
                disambiguation_options=[],
                distinct_chapters_count=1,
                top_candidates_count=1,
                descriptive_report=report
            )

        # -------------------------------------------------------------
        # Multi-Candidate Ambiguity Resolution
        # -------------------------------------------------------------
        distinct_chapters = list(dict.fromkeys(c.chapter_code for c in candidates))
        distinct_count = len(distinct_chapters)

        ui_options: List[UIRecommendationCard] = []

        if distinct_count == 1:
            # ---------------------------------------------------------
            # Rule 2: Same-Chapter Variant Check
            # count(distinct(chapter)) == 1 -> SAME-CHAPTER VARIANT
            # ---------------------------------------------------------
            banner_type = "SAME_CHAPTER_VARIANT"
            banner_title = "SELECT SPECIFIC VARIANT / SPECIFICATION"
            ch_title = top1.chapter_title
            clarif_q = f"Which specification of {q} applies under Chapter {top1.chapter_code} ({ch_title})?"

            for idx, c in enumerate(candidates[:6]):
                label_txt = f"{c.chapter_title} - {c.tariff_item_desc}" if c.tariff_item_desc else c.chapter_title
                ui_options.append(UIRecommendationCard(
                    option_id=f"OPT_{c.hsn_code}_{idx+1}",
                    label=label_txt,
                    chapter_code=c.chapter_code,
                    chapter_title=c.chapter_title,
                    hsn_code=format_hsn_code(c.hsn_code),
                    hsn_description=c.statutory_description,
                    material_keywords=c.material_keywords,
                    article_keywords=c.article_keywords,
                    score=round(c.final_score * 100.0, 1),
                    confidence_pct=round(c.final_score * 100.0, 1),
                    is_chapter_representative=(idx == 0)
                ))

        else:
            # ---------------------------------------------------------
            # Rule 3: True Multi-Chapter Check
            # count(distinct(chapter)) > 1 -> Group by Chapter first
            # ---------------------------------------------------------
            banner_type = "MULTI_CHAPTER_AMBIGUITY"
            banner_title = "MULTI-CHAPTER AMBIGUITY DETECTED"
            clarif_q = f"What material and construction is the {q}?"

            seen_ch = set()
            for idx, c in enumerate(candidates):
                if c.chapter_code not in seen_ch:
                    seen_ch.add(c.chapter_code)
                    label_txt = f"{c.chapter_title} - {c.tariff_item_desc}" if c.tariff_item_desc else c.chapter_title
                    ui_options.append(UIRecommendationCard(
                        option_id=f"OPT_{c.hsn_code}_{len(ui_options)+1}",
                        label=label_txt,
                        chapter_code=c.chapter_code,
                        chapter_title=c.chapter_title,
                        hsn_code=format_hsn_code(c.hsn_code),
                        hsn_description=c.statutory_description,
                        material_keywords=c.material_keywords,
                        article_keywords=c.article_keywords,
                        score=round(c.final_score * 100.0, 1),
                        confidence_pct=round(c.final_score * 100.0, 1),
                        is_chapter_representative=True
                    ))
                if len(ui_options) >= 5:
                    break

        # Disambiguate identical labels (e.g. 8471 30 10 vs 8471 30 90)
        disambiguate_candidate_labels(ui_options)

        report = self._build_descriptive_report(
            query=q,
            is_ambiguous=True,
            top1=top1,
            top2=top2,
            candidates=candidates
        )

        return AmbiguityEvaluationResult(
            query=q,
            is_ambiguous=True,
            banner_type=banner_type,
            banner_title=banner_title,
            clarification_question=clarif_q,
            direct_match=None,
            disambiguation_options=ui_options,
            distinct_chapters_count=distinct_count,
            top_candidates_count=len(candidates),
            descriptive_report=report
        )

    def _evaluate_auto_lock(self, q: str, candidates: List[SearchCandidate]) -> Tuple[Optional[UIRecommendationCard], bool]:
        """Evaluates auto-lock guardrails (reranker >= 0.85, margin >= 0.15, 8-digit leaf, no material ambiguity)."""
        if not candidates:
            return None, False
        top1 = candidates[0]
        top2 = candidates[1] if len(candidates) > 1 else None
        score1 = top1.final_score
        score2 = top2.final_score if top2 else 0.0
        score_margin = score1 - score2

        config_path = Path(__file__).resolve().parent.parent.parent / "config" / "intent_extraction_config.json"
        reranker_min = 0.85
        margin_min = 0.15
        if config_path.exists():
            try:
                import json
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    thresholds = cfg.get("thresholds", {})
                    reranker_min = float(thresholds.get("auto_lock_reranker_min", 0.85))
                    margin_min = float(thresholds.get("auto_lock_margin_min", 0.15))
            except Exception:
                pass

        clean_code1 = top1.hsn_code.replace(" ", "")
        is_8digit_leaf = (len(clean_code1) == 8)
        multi_material_keywords = ["bottle", "pipe", "tube", "gloves", "tank", "box", "container"]
        explicit_materials = ["steel", "stainless", "plastic", "cotton", "glass", "rubber", "iron", "copper", "wood"]
        is_ambiguous_mat = (
            any(re.search(rf"\b{a}\b", q.lower()) for a in multi_material_keywords)
            and not any(re.search(rf"\b{m}\b", q.lower()) for m in explicit_materials)
        )

        if score1 >= reranker_min and (top2 is None or score_margin >= margin_min) and is_8digit_leaf and not is_ambiguous_mat:
            direct_card = UIRecommendationCard(
                option_id=f"OPT_{top1.hsn_code}_AUTO",
                label=f"[{format_hsn_code(top1.hsn_code)}] {top1.statutory_description}",
                chapter_code=top1.chapter_code,
                chapter_title=top1.chapter_title,
                hsn_code=format_hsn_code(top1.hsn_code),
                hsn_description=top1.statutory_description,
                material_keywords=top1.material_keywords,
                article_keywords=top1.article_keywords,
                score=round(score1 * 100.0, 1),
                confidence_pct=round(score1 * 100.0, 1),
                is_chapter_representative=True
            )
            return direct_card, True
        return None, False

    def _build_descriptive_report(
        self,
        query: str,
        is_ambiguous: bool,
        top1: SearchCandidate,
        top2: Optional[SearchCandidate],
        candidates: List[SearchCandidate]
    ) -> DescriptiveReport:
        """
        Builds the structured descriptive report complying strictly with user requirements.
        """
        q_lower = query.lower()

        # 1. Article understood as
        article_desc = self._synthesize_article_understanding(q_lower, top1)

        # 2. Recommended HSN
        if not is_ambiguous:
            rec_hsn = f"{format_hsn_code(top1.hsn_code)} - {top1.statutory_description}"
            conf_level = "High" if top1.final_score >= 0.85 else "Medium"
            reasoning = (
                f"The product intent unequivocally aligns with {top1.chapter_title} (Chapter {top1.chapter_code}, "
                f"Heading {top1.heading_4digit}). The specific form '{top1.tariff_item_desc}' provides the most "
                f"specific statutory classification under GIR 1 & GIR 3(a), clearly distinguishing it from generic residual lines."
            )
            missing_info = []
        else:
            rec_hsn = "Needs confirmation"
            conf_level = "Medium" if len({c.chapter_code for c in candidates}) == 1 else "Low"
            distinct_ch_names = list(dict.fromkeys(f"Chapter {c.chapter_code} ({c.chapter_title})" for c in candidates[:4]))
            reasoning = (
                f"The input '{query}' is commercially valid but lacks specific technical bifurcation parameters. "
                f"Candidates span {', '.join(distinct_ch_names)}. Classification cannot be forced without customer "
                f"selection of the exact constituent material or specification."
            )
            missing_info = self._derive_missing_info(q_lower, candidates)

        # 3. Other plausible candidates
        plausible_list: List[PlausibleCandidate] = []
        alt_cands = candidates[1:4] if not is_ambiguous else candidates[:4]
        for cand in alt_cands:
            why_apply = f"Matches commodity function under Chapter {cand.chapter_code} ({cand.heading_4digit_desc[:50]}...)"
            why_not = f"Requires confirmation that product is specifically '{cand.tariff_item_desc}' rather than other variants."
            if cand.chapter_code == "39" and "steel" in q_lower:
                why_not = "Excluded if the item is manufactured from stainless steel or iron."
            elif cand.chapter_code == "73" and "plastic" in q_lower:
                why_not = "Excluded if the item is made of plastic."

            plausible_list.append(PlausibleCandidate(
                hsn_code=format_hsn_code(cand.hsn_code),
                description=cand.statutory_description[:90] + ("..." if len(cand.statutory_description) > 90 else ""),
                why_it_could_apply=why_apply,
                why_it_may_not=why_not
            ))

        # Format raw markdown/text
        md_lines = [
            f"Article understood as: {article_desc}\n",
            f"Recommended HSN: {rec_hsn}",
            f"Confidence: {conf_level}",
            f"Reasoning: {reasoning}\n",
            "Other plausible candidates (if any):"
        ]
        for p in plausible_list:
            md_lines.append(f"- [{p.hsn_code}] - [{p.description}] - [{p.why_it_could_apply}] - [{p.why_it_may_not}]")

        if missing_info:
            md_lines.append(f"\nMissing information that would change the result (if any): {'; '.join(missing_info)}")

        md_lines.append("\nVerification note: Codes should be checked against the current official CBIC/GST HSN schedule before filing or invoicing.")
        formatted_md = "\n".join(md_lines)

        return DescriptiveReport(
            article_understood_as=article_desc,
            recommended_hsn=rec_hsn,
            confidence=conf_level,
            confidence_score=round(top1.final_score * 100.0, 1),
            reasoning=reasoning,
            other_plausible_candidates=plausible_list,
            missing_information=missing_info,
            formatted_text=formatted_md
        )

    def _synthesize_article_understanding(self, q: str, top: SearchCandidate) -> str:
        """Generates clear, intent-grounded 1-2 sentence understanding."""
        if "bottle" in q:
            if "steel" in q or "stainless" in q:
                return "A finished stainless steel drinking container or flask, intended for personal hydration, kitchen, or household liquid transport."
            elif "insulated" in q:
                return "A finished insulated drinking bottle manufactured with double-wall thermal retention, designed for temperature-controlled liquid storage."
            return "A portable finished liquid bottle designed for holding drinking water or beverages for everyday consumer use."
        elif "pipe" in q or "tube" in q:
            if "steel" in q or "stainless" in q:
                return "A hollow structural conduit or industrial pipe manufactured from stainless steel, designed for fluid conveyance or engineering applications."
            return "A cylindrical conduit designed for liquid, gas, or electrical conveyance, whose statutory classification depends strictly on its material."
        elif "shirt" in q or "t-shirt" in q:
            if "knit" in q:
                return "A knitted garment worn on the upper body, classified under Chapter 61."
            elif "woven" in q:
                return "A woven garment worn on the upper body, classified under Chapter 62."
            return "An article of apparel worn on the upper body, typically made of cotton, bifurcating between knitted (Ch 61) and woven (Ch 62) construction."
        elif "pump" in q:
            return "A mechanical device designed to move liquids by centrifugal displacement, classified under industrial machinery (Chapter 84)."
        return f"A finished commercial article identified as '{q}', whose primary function relates to {top.chapter_title} (Chapter {top.chapter_code})."

    def _derive_missing_info(self, q: str, candidates: List[SearchCandidate]) -> List[str]:
        """Derives exact missing parameters needed to finalize classification."""
        missing = []
        distinct_ch = {c.chapter_code for c in candidates}
        if "61" in distinct_ch and "62" in distinct_ch:
            missing.append("Fabric construction: whether the shirt is knitted/crocheted (Chapter 61) or woven (Chapter 62)")
        if "39" in distinct_ch and "73" in distinct_ch:
            missing.append("Constituent material: whether manufactured of plastics/polymer (Chapter 39) or stainless steel/iron (Chapter 73)")
        if any(c.hsn_code.startswith("392330") for c in candidates):
            missing.append("Thermal insulation: whether the bottle is standard non-insulated plastic (3923 30 90) or insulated ware (3923 30 10)")
        if not missing:
            missing.append(f"Specific sub-item variant under Chapter {candidates[0].chapter_code} ({candidates[0].chapter_title})")
        return missing


def evaluate_product_ambiguity(raw_query: str) -> AmbiguityEvaluationResult:
    """Public helper function for Step 1 Context Aggregator."""
    controller = SmartAmbiguityController()
    return controller.evaluate(raw_query)
