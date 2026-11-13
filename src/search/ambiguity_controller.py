"""
Layer 4: Smart UI & Ambiguity Decision Engine
=============================================
Governs frontend recommendation state:
1. Auto-Lock High Confidence:
   If #1 result scores > 0.85 and leads #2 by at least 0.15, and is an 8-digit leaf,
   auto-lock as direct statutory match.
2. True Multi-Chapter Check:
   Only display MULTI-CHAPTER AMBIGUITY banner when count(distinct(chapter)) > 1.
3. Same-Chapter Variant Check:
   If all top results share the same chapter (count(distinct(chapter)) == 1),
   emit "Select specific variant/specification" with banner type "SAME_CHAPTER_VARIANT".
4. Material / Chapter Grouping:
   If results span 2+ chapters, group cards by Chapter (1 card per chapter).
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
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field
from src.search.hybrid_retrieval import SearchCandidate, HybridHSNEngine

logger = logging.getLogger(__name__)


def compute_classification_confidence(
    reranker_score: float,
    score_margin: float,
    is_8digit_leaf: bool,
    is_undecided: bool
) -> float:
    """
    Computes a single unified classification confidence value in range [0.0, 1.0].
    
    Rules:
    - If undecided (multiple plausible candidates, multi-chapter ambiguity, or missing attributes),
      confidence is strictly capped at < 0.50 (cannot report high confidence).
    - If 8-digit leaf is decided and margin is substantial, confidence scales with reranker score and margin.
    """
    if is_undecided or not is_8digit_leaf:
        base = min(reranker_score * 0.45, 0.45)
        return round(float(base), 2)

    norm_margin = min(max(score_margin, 0.0), 0.30) / 0.30
    conf = (reranker_score * 0.70) + (norm_margin * 0.30)
    return round(float(min(max(conf, 0.0), 1.0)), 2)


class UIRecommendationCard(BaseModel):
    option_id: str
    label: str
    chapter_code: str
    chapter_title: str
    hsn_code: str
    hsn_description: str
    material_keywords: str = ""
    article_keywords: str = ""
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
    banner_type: str  # "NONE" | "SAME_CHAPTER_VARIANT" | "MULTI_CHAPTER_AMBIGUITY" | "AUTO_LOCKED"
    banner_title: str
    clarification_question: Optional[str] = None
    direct_match: Optional[UIRecommendationCard] = None
    disambiguation_options: List[UIRecommendationCard] = Field(default_factory=list)
    distinct_chapters_count: int = 0
    top_candidates_count: int = 0
    descriptive_report: Optional[DescriptiveReport] = None


def disambiguate_candidate_labels(options: List[UIRecommendationCard]) -> None:
    """
    Ensures option labels strictly derive from statutory file text without inventing terms.
    If multiple options share identical descriptions, flags is_duplicate_description = True
    and allows user selection by HSN code.
    """
    desc_counts: Dict[str, int] = {}
    for opt in options:
        d_clean = opt.hsn_description.strip().lower()
        desc_counts[d_clean] = desc_counts.get(d_clean, 0) + 1

    for opt in options:
        d_clean = opt.hsn_description.strip().lower()
        opt.label = f"[{opt.hsn_code}] {opt.hsn_description}"
        if desc_counts[d_clean] > 1:
            opt.is_duplicate_description = True

        raw_desc = opt.hsn_description.strip()
        if raw_desc.endswith(("-", ":", "...", "â€¦")) or len(raw_desc) >= 195:
            opt.is_truncated = True


def format_hsn_code(code: str) -> str:
    """Formats 4, 6, or 8 digit strings into standard customs format."""
    c = str(code).replace(" ", "").strip()
    if len(c) == 8:
        return f"{c[:4]} {c[4:6]} {c[6:]}"
    elif len(c) == 6:
        return f"{c[:4]} {c[4:]}"
    elif len(c) == 4:
        return c
    return code


class SmartAmbiguityController:
    """
    Evaluates search candidates and enforces UI & GIR ambiguity guardrails.
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

        # -------------------------------------------------------------
        # Rule 1: Auto-Lock High Confidence Guardrails
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
            # Same-Chapter Variant
            banner_type = "SAME_CHAPTER_VARIANT"
            banner_title = "SELECT SPECIFIC VARIANT / SPECIFICATION"
            ch_title = top1.chapter_title
            clarif_q = f"Which specification of {q} applies under Chapter {top1.chapter_code} ({ch_title})?"

            for idx, c in enumerate(candidates[:6]):
                ui_options.append(UIRecommendationCard(
                    option_id=f"OPT_{c.hsn_code}_{idx+1}",
                    label=f"[{format_hsn_code(c.hsn_code)}] {c.statutory_description}",
                    chapter_code=c.chapter_code,
                    chapter_title=c.chapter_title,
                    hsn_code=format_hsn_code(c.hsn_code),
                    hsn_description=c.statutory_description,
                    material_keywords=c.material_keywords,
                    article_keywords=c.article_keywords,
                    score=round(c.final_score * 100.0, 1),
                    confidence_pct=round(min(c.final_score * 45.0, 45.0), 1),  # Capped because undecided
                    is_chapter_representative=(idx == 0)
                ))

        else:
            # Multi-Chapter Ambiguity
            banner_type = "MULTI_CHAPTER_AMBIGUITY"
            banner_title = "MULTI-CHAPTER AMBIGUITY DETECTED"
            clarif_q = f"What material and construction is the {q}?"

            seen_ch = set()
            for idx, c in enumerate(candidates):
                if c.chapter_code not in seen_ch:
                    seen_ch.add(c.chapter_code)
                    ui_options.append(UIRecommendationCard(
                        option_id=f"OPT_{c.hsn_code}_{len(ui_options)+1}",
                        label=f"[{format_hsn_code(c.hsn_code)}] {c.statutory_description}",
                        chapter_code=c.chapter_code,
                        chapter_title=c.chapter_title,
                        hsn_code=format_hsn_code(c.hsn_code),
                        hsn_description=c.statutory_description,
                        material_keywords=c.material_keywords,
                        article_keywords=c.article_keywords,
                        score=round(c.final_score * 100.0, 1),
                        confidence_pct=round(min(c.final_score * 40.0, 40.0), 1),
                        is_chapter_representative=True
                    ))
                if len(ui_options) >= 5:
                    break

        # Disambiguate duplicate labels
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
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    thresholds = cfg.get("thresholds", {})
                    reranker_min = float(thresholds.get("auto_lock_reranker_min", 0.85))
                    margin_min = float(thresholds.get("auto_lock_margin_min", 0.15))
            except Exception:
                pass

        clean_code1 = top1.hsn_code.replace(" ", "")
        is_8digit_leaf = (len(clean_code1) == 8)

        # Candidate is locked only if score meets threshold, margin meets threshold, is 8-digit leaf
        if score1 >= reranker_min and (top2 is None or score_margin >= margin_min) and is_8digit_leaf:
            locked_conf = compute_classification_confidence(score1, score_margin, is_8digit_leaf=True, is_undecided=False)
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
                confidence_pct=round(locked_conf * 100.0, 1),
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
        score1 = top1.final_score
        score2 = top2.final_score if top2 else 0.0
        score_margin = score1 - score2
        clean_code1 = top1.hsn_code.replace(" ", "")
        is_8digit_leaf = (len(clean_code1) == 8)

        calculated_conf = compute_classification_confidence(
            reranker_score=score1,
            score_margin=score_margin,
            is_8digit_leaf=is_8digit_leaf,
            is_undecided=is_ambiguous
        )

        # 1. Article understood as (Generic statutory derivation)
        article_desc = self._synthesize_article_understanding(q_lower, top1)

        # 2. Recommended HSN
        if not is_ambiguous:
            rec_hsn = f"{format_hsn_code(top1.hsn_code)} - {top1.statutory_description}"
            conf_level = "High" if calculated_conf >= 0.85 else "Medium"
            reasoning = (
                f"The product intent aligns decisively with {top1.chapter_title} (Chapter {top1.chapter_code}, "
                f"Heading {top1.heading_4digit}). The 8-digit tariff item '{top1.tariff_item_desc}' provides specific "
                f"classification under GIR 1 and GIR 6, leading alternatives by a decisive score margin."
            )
            missing_info = []
        else:
            rec_hsn = "Needs confirmation"
            conf_level = "Medium" if calculated_conf >= 0.35 else "Low"
            distinct_ch_names = list(dict.fromkeys(f"Chapter {c.chapter_code} ({c.chapter_title})" for c in candidates[:4]))
            reasoning = (
                f"The input '{query}' is commercially recognized but cannot be locked to a single 8-digit tariff item "
                f"without user selection. Candidates span {', '.join(distinct_ch_names)}. "
                f"Classification requires selecting the specific sub-item variant."
            )
            missing_info = self._derive_missing_info(q_lower, candidates)

        # 3. Other plausible candidates
        plausible_list: List[PlausibleCandidate] = []
        alt_cands = candidates[1:4] if not is_ambiguous else candidates[:4]
        for cand in alt_cands:
            why_apply = f"Matches commodity description under Chapter {cand.chapter_code} ({cand.heading_4digit_desc[:50]}...)"
            why_not = f"Requires confirmation that product matches specific tariff item [{format_hsn_code(cand.hsn_code)}] '{cand.tariff_item_desc}' rather than alternative subheadings."

            plausible_list.append(PlausibleCandidate(
                hsn_code=format_hsn_code(cand.hsn_code),
                description=cand.statutory_description[:90] + ("..." if len(cand.statutory_description) > 90 else ""),
                why_it_could_apply=why_apply,
                why_it_may_not=why_not
            ))

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
            confidence_score=round(calculated_conf * 100.0, 1),
            reasoning=reasoning,
            other_plausible_candidates=plausible_list,
            missing_information=missing_info,
            formatted_text=formatted_md
        )

    def _synthesize_article_understanding(self, q: str, top: SearchCandidate) -> str:
        """Generic statutory derivation of article understanding from candidate fields without product hardcoding."""
        statutory_desc = (top.statutory_description or top.tariff_item_desc or "").strip()
        if top.heading_4digit_desc and top.heading_4digit_desc.lower() not in statutory_desc.lower():
            return f"An article or commodity understood under '{top.heading_4digit_desc}' ({top.chapter_title}, Chapter {top.chapter_code}), corresponding to commercial query '{q}'."
        return f"A finished commercial commodity described as '{statutory_desc}' under {top.chapter_title} (Chapter {top.chapter_code}, Heading {top.heading_4digit})."

    def _derive_missing_info(self, q: str, candidates: List[SearchCandidate]) -> List[str]:
        """Generic derivation of missing classification parameters across competing candidate chapters/headings."""
        missing = []
        distinct_ch = sorted(list({c.chapter_code for c in candidates}))
        if len(distinct_ch) > 1:
            ch_names = [f"Chapter {ch} ({next(c.chapter_title for c in candidates if c.chapter_code == ch)})" for ch in distinct_ch]
            missing.append(f"Constituent material / physical character: query spans multiple statutory chapters ({'; '.join(ch_names)})")

        distinct_h4 = sorted(list({c.heading_4digit for c in candidates}))
        if len(distinct_ch) == 1 and len(distinct_h4) > 1:
            h4_names = [f"Heading {h} ({next(c.heading_4digit_desc for c in candidates if c.heading_4digit == h)})" for h in distinct_h4]
            missing.append(f"Heading classification: query spans multiple 4-digit headings ({'; '.join(h4_names)})")

        if not missing:
            ch0 = candidates[0]
            missing.append(f"Specific sub-item variant / specification under Chapter {ch0.chapter_code} ({ch0.chapter_title})")
        return missing


def evaluate_product_ambiguity(raw_query: str) -> AmbiguityEvaluationResult:
    """Public helper function for Step 1 Context Aggregator."""
    controller = SmartAmbiguityController()
    return controller.evaluate(raw_query)
