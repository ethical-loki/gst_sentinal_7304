"""
src/ml/multi_candidate_engine.py
================================
Phase 7: Adaptive Multi-Candidate HSN Discovery & Intelligent Classification Engine.

Coordinates:
  - Adaptive candidate discovery & dynamic expansion (no fixed top-K cap)
  - Relevance evaluation via existing RelevanceClassifier (4-class)
  - Reversible, auditable candidate grouping without losing statutory records
  - Dynamic difference analysis & targeted progressive clarification
  - Independent confidence calibration (retrieval, relevance, chapter, exact HSN, distinction)
  - Decision controller (EXACT_HSN, MULTIPLE_CANDIDATES, CHAPTER_ONLY_CLARIFY,
    CLARIFY_AMBIGUOUS, INSUFFICIENT_INFORMATION, OUT_OF_SCHEDULE)
  - Non-truncating pagination, lineage audit trail, and execution metrics
"""

from __future__ import annotations

import logging
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from src.ml.ambiguity_resolver import (
    ATTRIBUTE_CUE_VOCAB,
    ModelDrivenAmbiguityResolver,
    _extract_material_tokens,
    analyze_sibling_distinctions,
    identify_separating_attributes,
)
from src.ml.confidence_calibrator import extract_query_confidence_features
from src.ml.candidate_evidence_evaluator import (
    CONTRADICTED,
    INSUFFICIENT_EVIDENCE,
    POSSIBLY_SUPPORTED,
    SUPPORTED,
    build_candidate_profile,
    consolidate_duplicate_records,
    evaluate_candidate_evidence,
)
from src.ml.product_tariff_reranker import classify_tariff_level, format_tariff_context
from src.ml.relevance_classifier import ClassifiedTariffCandidate, RelationLabel, RelevanceClassifier
from src.nlp.product_intent_analyzer import analyze_product_intent
from src.search.hybrid_retrieval import HybridHSNEngine
from src.search.statutory_master_index import StatutoryMasterIndex
from src.training.feedback_collector import FeedbackCollector

logger = logging.getLogger(__name__)


def _norm_desc(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", (text or "").lower())).strip()


def _is_leaf_8digit(c: ClassifiedTariffCandidate) -> bool:
    level = getattr(c.candidate, "tariff_level", None)
    if level:
        return level == "LEAF_8DIGIT"
    return len(str(getattr(c.candidate, "hsn_code", "") or "").strip()) >= 8


def _paginate(items: Sequence[Any], page: int = 1, page_size: Optional[int] = 20) -> Tuple[List[Any], Dict[str, Any]]:
    total = len(items)
    if page_size is None or page_size <= 0:
        return list(items), {
            "page": 1,
            "page_size": total,
            "total_candidates": total,
            "total_pages": 1 if total > 0 else 0,
            "has_next_page": False,
        }
    p = max(1, int(page))
    ps = max(1, int(page_size))
    total_pages = (total + ps - 1) // ps if total > 0 else 0
    start = (p - 1) * ps
    end = start + ps
    return list(items[start:end]), {
        "page": p,
        "page_size": ps,
        "total_candidates": total,
        "total_pages": total_pages,
        "has_next_page": end < total,
    }


@dataclass
class DiscoveryOutcome:
    qualifying_classified: List[ClassifiedTariffCandidate]
    raw_records_by_id: Dict[str, Dict[str, Any]]
    total_retrieved: int
    records_examined: int
    candidates_discarded: int
    discard_reasons: List[str]
    retrieval_sources: List[str]
    discovery_complete: bool
    stopping_reason: str
    retrieval_time_ms: float
    reranking_time_ms: float
    expansion_rounds: int
    unrelated_classified: List[ClassifiedTariffCandidate] = field(default_factory=list)


class AdaptiveCandidateDiscoverer:
    """
    Dynamically expands Layer 2 retrieval until candidate discovery stabilizes,
    all dataset records are examined, or an explicit resource budget is reached
    (in which case `discovery_complete=False` is reported honestly).
    """

    def __init__(
        self,
        hybrid_engine: HybridHSNEngine,
        classifier: RelevanceClassifier,
        initial_branch_k: int = 30,
        expansion_factor: float = 2.0,
        max_eval_budget: Optional[int] = 160,
    ):
        self.hybrid_engine = hybrid_engine
        self.classifier = classifier
        self.initial_branch_k = max(10, int(initial_branch_k))
        self.expansion_factor = max(1.5, float(expansion_factor))
        self.max_eval_budget = max_eval_budget

    def discover(
        self,
        query: str,
        exhaustive: bool = False,
        min_qualifying_relation: Tuple[RelationLabel, ...] = (
            RelationLabel.SAME_PRODUCT,
            RelationLabel.INSUFFICIENT_INFORMATION,
            RelationLabel.RELATED_PRODUCT,
        ),
        stage1_result: Optional[Dict[str, Any]] = None,
    ) -> DiscoveryOutcome:
        total_master = getattr(self.hybrid_engine, "total_records", 0)
        expanded_q, _ = self.hybrid_engine._expand_abbreviated_query(query)
        eval_query = expanded_q or query

        evaluated_map: Dict[str, ClassifiedTariffCandidate] = {}
        raw_by_id: Dict[str, Dict[str, Any]] = {}
        ctx_score_cache: Dict[str, Tuple[float, float, Any, float]] = {}
        sources_seen: Set[str] = set()
        discarded_count = 0
        discard_reasons: List[str] = []

        t_ret_ms = 0.0
        t_rerank_ms = 0.0
        rounds = 0
        branch_k = total_master if exhaustive else self.initial_branch_k
        budget = total_master if exhaustive else (self.max_eval_budget or total_master)
        stopping_reason = "stabilized"
        discovery_complete = True

        while True:
            rounds += 1
            t0 = time.perf_counter()
            try:
                pool = self.hybrid_engine.retrieve_with_lineage(
                    query, branch_k=branch_k, stage1_result=stage1_result
                )
            except TypeError:
                pool = self.hybrid_engine.retrieve_with_lineage(query, branch_k=branch_k)
            t_ret_ms += (time.perf_counter() - t0) * 1000.0

            if not pool:
                stopping_reason = "empty_retrieval_pool"
                discovery_complete = True
                break

            # Identify only newly discovered records (incremental evaluation; never re-score)
            new_rows: List[Dict[str, Any]] = []
            for idx, rec in enumerate(pool):
                rec_id = str(rec.get("source_record_id") or f"hsn_{rec.get('hsn_code', idx)}")
                if rec_id in evaluated_map or rec_id in raw_by_id:
                    continue
                if len(raw_by_id) + len(new_rows) >= budget:
                    break
                raw_by_id[rec_id] = rec
                src = str(rec.get("retrieval_source") or "hybrid")
                sources_seen.add(src)
                new_rows.append(rec)

            if not new_rows:
                if len(raw_by_id) >= total_master and total_master > 0:
                    stopping_reason = "full_dataset_examined"
                    discovery_complete = True
                else:
                    stopping_reason = "no_new_records_discovered"
                    discovery_complete = True
                break

            t1 = time.perf_counter()
            to_score: List[Dict[str, Any]] = []
            cached_results: List[Tuple[Dict[str, Any], ClassifiedTariffCandidate]] = []
            for rec in new_rows:
                ctx = format_tariff_context(rec)
                if ctx in ctx_score_cache:
                    r_score, r_logit, r_rel, r_conf = ctx_score_cache[ctx]
                    from src.ml.product_tariff_reranker import RerankedTariffCandidate, _get_field
                    hsn_c = _get_field(rec, "hsn_code", "HSN Code", "code_str")
                    code_len = rec.get("code_length") if isinstance(rec, dict) else getattr(rec, "code_length", None)
                    cloned_cand = RerankedTariffCandidate(
                        hsn_code=hsn_c,
                        chapter_code=_get_field(rec, "chapter_code", "chapter_str", "chapter"),
                        description=_get_field(rec, "statutory_description", "HSN Description", "tariff_item_desc", "description"),
                        relevance_score=r_score,
                        raw_logit=r_logit,
                        chapter_title=_get_field(rec, "chapter_title"),
                        heading_4digit_desc=_get_field(rec, "heading_4digit_desc"),
                        subheading_6digit_desc=_get_field(rec, "subheading_6digit_desc"),
                        tariff_item_desc=_get_field(rec, "tariff_item_desc"),
                        article_keywords=_get_field(rec, "article_keywords", "Article Keywords"),
                        material_keywords=_get_field(rec, "material_keywords", "Material Keywords"),
                        tariff_level=classify_tariff_level(hsn_c, code_len),
                    )
                    cached_results.append((rec, ClassifiedTariffCandidate(
                        candidate=cloned_cand, relation=r_rel, confidence=r_conf, relevance_confidence=r_conf
                    )))
                else:
                    to_score.append(rec)

            scored_pairs: List[Tuple[Dict[str, Any], ClassifiedTariffCandidate]] = list(cached_results)
            if to_score:
                newly_scored = self.classifier.classify(eval_query, to_score)
                for rec, c in zip(to_score, newly_scored):
                    ctx = format_tariff_context(rec)
                    ctx_score_cache[ctx] = (c.candidate.relevance_score, c.candidate.raw_logit, c.relation, c.confidence)
                    scored_pairs.append((rec, c))
            t_rerank_ms += (time.perf_counter() - t1) * 1000.0

            new_qualifying = 0
            new_active = 0
            for rec, c in scored_pairs:
                rec_id = str(rec.get("source_record_id") or f"hsn_{c.candidate.hsn_code}")
                c_id = rec_id
                evaluated_map[c_id] = c
                if c.relation in min_qualifying_relation:
                    new_qualifying += 1
                    if c.relation in (RelationLabel.SAME_PRODUCT, RelationLabel.INSUFFICIENT_INFORMATION):
                        new_active += 1
                else:
                    discarded_count += 1
                    if len(discard_reasons) < 10:
                        discard_reasons.append(
                            f"HSN {c.candidate.hsn_code} classified UNRELATED (score={c.confidence:.3f})"
                        )

            examined_total = len(raw_by_id)
            if total_master > 0 and examined_total >= total_master:
                stopping_reason = "full_dataset_examined"
                discovery_complete = True
                break

            has_active_pool = any(
                c.relation in (RelationLabel.SAME_PRODUCT, RelationLabel.INSUFFICIENT_INFORMATION)
                for c in evaluated_map.values()
            )
            if rounds > 1 and ((has_active_pool and new_active == 0) or new_qualifying == 0):
                stopping_reason = (
                    "expansion_tail_stabilized_zero_new_active"
                    if has_active_pool
                    else "expansion_tail_stabilized_zero_new_qualifying"
                )
                discovery_complete = True
                break

            # On round 1, allow one expansion round if 0 qualifying candidates were found at initial branch_k;
            # stop once round >= 2 still yields 0 qualifying candidates (unless exhaustive).
            if rounds >= 2 and new_qualifying == 0 and not has_active_pool and not exhaustive:
                stopping_reason = "initial_pool_no_qualifying_candidates"
                discovery_complete = True
                break

            if examined_total >= budget:
                # Resource budget hit while expansion tail was still finding qualifying records
                discovery_complete = False
                stopping_reason = (
                    f"resource_budget_reached ({examined_total}/{total_master} examined; "
                    f"last_round_new_active={new_active})"
                )
                break

            next_k = int(branch_k * self.expansion_factor)
            if next_k <= branch_k:
                next_k = branch_k + 30
            branch_k = min(next_k, total_master) if total_master > 0 else next_k

        # Re-order qualifying candidates by score descending (never truncate valid alternatives!)
        same_cands = [c for c in evaluated_map.values() if c.relation == RelationLabel.SAME_PRODUCT]
        insuff_cands = [c for c in evaluated_map.values() if c.relation == RelationLabel.INSUFFICIENT_INFORMATION]
        rel_cands = [c for c in evaluated_map.values() if c.relation == RelationLabel.RELATED_PRODUCT]

        qualifying: List[ClassifiedTariffCandidate] = list(same_cands)
        if len(same_cands) >= 5:
            # Prune weak 0.40-0.49 tail noise when >=5 SAME_PRODUCT records already exist
            for c in insuff_cands:
                if c.confidence >= 0.50:
                    qualifying.append(c)
                else:
                    discarded_count += 1
        else:
            qualifying.extend(insuff_cands)

        if not same_cands and len(insuff_cands) < 3:
            qualifying.extend(rel_cands)
        else:
            # Preserve genuinely relevant RELATED_PRODUCT alternatives separately instead of discarding them
            qualifying.extend(sorted(rel_cands, key=lambda c: c.confidence, reverse=True))

        qualifying = [c for c in qualifying if c.relation in min_qualifying_relation]
        # Order: SAME_PRODUCT first, then INSUFFICIENT_INFORMATION, then RELATED_PRODUCT (each by confidence desc)
        rel_priority = {
            RelationLabel.SAME_PRODUCT: 0,
            RelationLabel.INSUFFICIENT_INFORMATION: 1,
            RelationLabel.RELATED_PRODUCT: 2,
        }
        qualifying.sort(key=lambda c: (rel_priority.get(c.relation, 3), -c.confidence))

        # Ensure `raw_records_by_id` can also be looked up by hsn_code
        by_hsn_raw: Dict[str, Dict[str, Any]] = {}
        for rec in raw_by_id.values():
            hsn = str(rec.get("hsn_code") or "").strip()
            if hsn and hsn not in by_hsn_raw:
                by_hsn_raw[hsn] = rec

        unrelated_cands = [c for c in evaluated_map.values() if c.relation == RelationLabel.UNRELATED]
        unrelated_cands.sort(key=lambda c: -c.confidence)

        return DiscoveryOutcome(
            qualifying_classified=qualifying,
            unrelated_classified=unrelated_cands,
            raw_records_by_id=by_hsn_raw,
            total_retrieved=len(raw_by_id),
            records_examined=len(raw_by_id),
            candidates_discarded=discarded_count,
            discard_reasons=discard_reasons,
            retrieval_sources=sorted(sources_seen),
            discovery_complete=discovery_complete,
            stopping_reason=stopping_reason,
            retrieval_time_ms=round(t_ret_ms, 2),
            reranking_time_ms=round(t_rerank_ms, 2),
            expansion_rounds=rounds,
        )


def group_candidates(qualifying: Sequence[ClassifiedTariffCandidate]) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """
    Reversibly groups qualifying candidates without merging or deleting any HSN record.
    Distinguishes:
      - DUPLICATE_DESCRIPTION: identical normalized statutory description
      - SAME_HEADING_VARIANTS: multiple HSNs sharing a 4-digit heading
      - DISTINCT_INTERPRETATION: standalone heading/chapter possibility
    """
    desc_buckets: Dict[str, List[ClassifiedTariffCandidate]] = defaultdict(list)
    for c in qualifying:
        key = _norm_desc(c.candidate.description) or c.candidate.hsn_code
        desc_buckets[key].append(c)

    # First pass: assign duplicate description groups; singletons grouped by 4-digit heading
    groups: List[Dict[str, Any]] = []
    hsn_to_group: Dict[str, str] = {}
    heading_singletons: Dict[str, List[ClassifiedTariffCandidate]] = defaultdict(list)
    g_counter = 1

    for norm_txt, members in desc_buckets.items():
        if len(members) > 1:
            gid = f"grp_{g_counter:03d}"
            g_counter += 1
            hsn_list = [m.candidate.hsn_code for m in members]
            for h in hsn_list:
                hsn_to_group[h] = gid
            groups.append({
                "group_id": gid,
                "group_type": "DUPLICATE_DESCRIPTION",
                "chapter_code": members[0].candidate.chapter_code,
                "common_heading": members[0].candidate.hsn_code[:4],
                "representative_description": members[0].candidate.description[:120],
                "hsn_codes": hsn_list,
                "count": len(hsn_list),
            })
        else:
            m = members[0]
            h4 = m.candidate.hsn_code[:4] if m.candidate.hsn_code else m.candidate.chapter_code
            heading_singletons[h4].append(m)

    for h4, members in heading_singletons.items():
        gid = f"grp_{g_counter:03d}"
        g_counter += 1
        g_type = "SAME_HEADING_VARIANTS" if len(members) > 1 else "DISTINCT_INTERPRETATION"
        hsn_list = [m.candidate.hsn_code for m in members]
        for h in hsn_list:
            hsn_to_group[h] = gid
        groups.append({
            "group_id": gid,
            "group_type": g_type,
            "chapter_code": members[0].candidate.chapter_code,
            "common_heading": h4,
            "representative_description": members[0].candidate.description[:120],
            "hsn_codes": hsn_list,
            "count": len(hsn_list),
        })

    return groups, hsn_to_group


def build_targeted_clarifications(
    query: str,
    focus_candidates: Sequence[ClassifiedTariffCandidate],
    separating_attributes: Sequence[str],
    attribute_evidence: Dict[str, List[str]],
) -> List[Dict[str, Any]]:
    """
    Generates structured, evidence-based clarification questions derived strictly
    from actual statutory differences among `focus_candidates`.
    """
    if len(focus_candidates) < 2:
        return []

    questions: List[Dict[str, Any]] = []
    hsn_list = [c.candidate.hsn_code for c in focus_candidates[:8]]
    why_map = {
        "material": "GST tariff chapters and headings depend on the primary constituent material.",
        "construction": "Statutory headings separate knitted/crocheted vs woven, or cast vs forged construction.",
        "processing_state": "Tariff items distinguish raw/unworked goods from processed, coated, or finished goods.",
        "intended_use": "End-use or parent apparatus determines the specific tariff subheading.",
        "product_completeness": "Complete/assembled units are classified separately from parts and accessories.",
    }

    for idx, attr in enumerate(separating_attributes[:3], start=1):
        ev = attribute_evidence.get(attr, [])
        ev_hint = f" (observed statutory options: {', '.join(ev[:5])})" if ev else ""
        attr_label = attr.replace("_", " ")
        questions.append({
            "question_id": f"q_{attr}",
            "attribute": attr,
            "question": f"Please specify the {attr_label} of '{query}'{ev_hint}.",
            "distinguishes_hsn_codes": hsn_list,
            "why_it_matters": why_map.get(attr, "Required to distinguish competing statutory tariff items."),
            "essential": idx == 1,
        })

    # If multiple 8-digit siblings exist in the same heading without cue differences, ask subheading spec
    if not questions and len({c.candidate.hsn_code for c in focus_candidates}) > 1:
        questions.append({
            "question_id": "q_tariff_specification",
            "attribute": "statutory_specification",
            "question": f"Multiple tariff items match '{query}'. Which exact statutory specification applies?",
            "distinguishes_hsn_codes": hsn_list,
            "why_it_matters": "Statutory subheadings within the same heading differ by technical specification.",
            "essential": True,
        })

    return questions


class MultiCandidateEngine:
    """
    Phase 7 Adaptive Multi-Candidate HSN Discovery & Decision Controller.
    Reuses HybridHSNEngine, RelevanceClassifier, CalibrationBundle,
    StatutoryMasterIndex, and FeedbackCollector.
    """

    _instance: Optional["MultiCandidateEngine"] = None

    @classmethod
    def get_instance(cls) -> "MultiCandidateEngine":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(
        self,
        hybrid_engine: Optional[HybridHSNEngine] = None,
        relevance_classifier: Optional[RelevanceClassifier] = None,
        statutory_index: Optional[StatutoryMasterIndex] = None,
        feedback_collector: Optional[FeedbackCollector] = None,
        initial_branch_k: int = 45,
        max_eval_budget: Optional[int] = 250,
        inference_timeout_s: Optional[float] = None,
    ):
        self.hybrid_engine = hybrid_engine or HybridHSNEngine.get_instance()
        self.classifier = relevance_classifier or RelevanceClassifier()
        self.statutory_index = statutory_index or StatutoryMasterIndex()
        self.feedback = feedback_collector or FeedbackCollector()
        self.inference_timeout_s = inference_timeout_s
        self.discoverer = AdaptiveCandidateDiscoverer(
            hybrid_engine=self.hybrid_engine,
            classifier=self.classifier,
            initial_branch_k=initial_branch_k,
            max_eval_budget=max_eval_budget,
        )

    def classify_adaptive(
        self,
        description: str,
        confirmed_attributes: Optional[Dict[str, str]] = None,
        page: int = 1,
        page_size: Optional[int] = 20,
        exhaustive: bool = False,
        stage1_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Executes adaptive multi-candidate discovery, grouping, difference analysis,
        calibrated confidence estimation, and decision control.
        When `stage1_result` is provided, Stage 2 consumes the structured Stage 1
        intent, aliases, materials, function, and guided chapters directly.
        """
        t_total0 = time.perf_counter()
        orig = (description or "").strip()
        if not orig and isinstance(stage1_result, dict):
            orig = str(stage1_result.get("original_description") or stage1_result.get("primary_commercial_article") or "").strip()
        confirmed = dict(confirmed_attributes or {})
        effective_query = (
            f"{orig} {' '.join(str(v).strip() for v in confirmed.values() if str(v).strip())}".strip()
            if confirmed
            else orig
        )

        if not effective_query:
            return self._empty_response(orig, confirmed, page, page_size, t_total0)

        t_s1 = time.perf_counter()
        if isinstance(stage1_result, dict) and isinstance(stage1_result.get("product_intent"), dict) and not confirmed:
            pi_dict = stage1_result["product_intent"]
            from src.nlp.product_intent_analyzer import ProductIntentStructure
            product_intent = ProductIntentStructure(
                raw_description=str(pi_dict.get("raw_description") or orig),
                finished_article=str(pi_dict.get("finished_article") or stage1_result.get("primary_commercial_article") or orig),
                constituent_materials=list(pi_dict.get("constituent_materials") or []),
                ingredients_or_additives=list(pi_dict.get("ingredients_or_additives") or []),
                components_or_parts=list(pi_dict.get("components_or_parts") or []),
                packaging_or_presentation=pi_dict.get("packaging_or_presentation"),
                processing_form=pi_dict.get("processing_form"),
                function_use=pi_dict.get("function_use"),
                article_search_query=str(pi_dict.get("article_search_query") or effective_query),
                secondary_articles=list(pi_dict.get("secondary_articles") or []),
                product_form=pi_dict.get("product_form"),
                missing_critical_attributes=list(pi_dict.get("missing_critical_attributes") or []),
                intent_confidence=float(pi_dict.get("intent_confidence") or 0.85),
                product_head_noun=str(pi_dict.get("product_head_noun") or ""),
                descriptive_modifiers=list(pi_dict.get("descriptive_modifiers") or []),
                alternative_names_and_aliases=list(pi_dict.get("alternative_names_and_aliases") or []),
                article_category=str(pi_dict.get("article_category") or "finished_article"),
                attributes=list(pi_dict.get("attributes") or []),
                function_details=dict(pi_dict.get("function_details") or {}),
                relationship_graph=list(pi_dict.get("relationship_graph") or []),
                field_confidences=dict(pi_dict.get("field_confidences") or {}),
                stage2_search_representation=dict(stage1_result.get("stage2_search_representation") or pi_dict.get("stage2_search_representation") or {}),
            )
        else:
            product_intent = analyze_product_intent(effective_query)
        stage1_intent_ms = round((time.perf_counter() - t_s1) * 1000.0, 2)

        effective_stage1 = stage1_result
        if effective_stage1 is None:
            from src.nlp.stage1_chapter_analyzer import build_canonical_stage1_result
            effective_stage1 = build_canonical_stage1_result(
                effective_query,
                product_intent=product_intent,
            )

        # 1. Adaptive Discovery (dynamic expansion, guided by Stage 1)
        disc = self.discoverer.discover(effective_query, exhaustive=exhaustive, stage1_result=effective_stage1)
        consolidated = consolidate_duplicate_records(disc.qualifying_classified)

        # Dataset-driven evidence evaluation (uses enriched_master_hsn.parquet fields)
        t_ev0 = time.perf_counter()
        evidence_by_hsn: Dict[str, Dict[str, Any]] = {}
        qualifying: List[ClassifiedTariffCandidate] = []
        contradicted_reasons: List[str] = []
        contradicted_count = 0
        for c in consolidated:
            raw = disc.raw_records_by_id.get(c.candidate.hsn_code, {})
            prof = build_candidate_profile(raw, c.candidate)
            ev_res = evaluate_candidate_evidence(
                product_intent=product_intent,
                profile=prof,
                relation_value=c.relation.value,
                cross_encoder_confidence=c.confidence,
            )
            ev_dict = ev_res.to_dict()
            ev_dict["ce_relation"] = c.relation.value
            ev_dict["rescued_by_statutory_evidence"] = False
            ev_dict["rescue_reason"] = ""
            evidence_by_hsn[c.candidate.hsn_code] = ev_dict
            if ev_res.status == CONTRADICTED:
                contradicted_count += 1
                if len(contradicted_reasons) < 15:
                    contradicted_reasons.append(
                        f"HSN {c.candidate.hsn_code} CONTRADICTED: {'; '.join(ev_res.contradictions)}"
                    )
                continue
            qualifying.append(c)

        # Selective Cross-Encoder candidate rescue:
        # Preserve UNRELATED candidates ONLY when independent statutory (non-synthetic) article evidence
        # + heading compatibility hold without contradictions, generic-only matches, or parts-vs-complete mismatch.
        # Never promotes c.relation to SAME_PRODUCT or evidence_status to SUPPORTED.
        rescued_hsns: List[str] = []
        seen_qual_hsn = {c.candidate.hsn_code for c in qualifying}
        qualifying_h4s = {c.candidate.hsn_code[:4] for c in qualifying if c.candidate.hsn_code}
        unrelated_consolidated = consolidate_duplicate_records(getattr(disc, "unrelated_classified", []))
        for c in unrelated_consolidated:
            hsn = c.candidate.hsn_code
            if hsn in seen_qual_hsn or not _is_leaf_8digit(c):
                continue
            raw = disc.raw_records_by_id.get(hsn, {})
            prof = build_candidate_profile(raw, c.candidate)
            ev_res = evaluate_candidate_evidence(
                product_intent=product_intent,
                profile=prof,
                relation_value=c.relation.value,
                cross_encoder_confidence=c.confidence,
            )
            has_generic_only = "penalty=generic_superordinate_only" in ev_res.trace_summary
            has_strong_statutory_match = (
                not qualifying
                or (hsn[:4] in qualifying_h4s)
                or len(ev_res.statutory_article_matches) >= 2
            )
            if (
                ev_res.status != CONTRADICTED
                and ev_res.statutory_article_matches
                and ev_res.heading_compatible
                and not has_generic_only
                and ev_res.role_mismatch != "complete_article_vs_parts"
                and has_strong_statutory_match
            ):
                ev_dict = ev_res.to_dict()
                ev_dict["status"] = POSSIBLY_SUPPORTED
                ev_dict["ce_relation"] = c.relation.value
                ev_dict["rescued_by_statutory_evidence"] = True
                ev_dict["rescue_reason"] = (
                    f"Rescued from CE={c.relation.value} ({c.confidence:.3f}) via statutory_article={ev_res.statutory_article_matches[:3]} and heading_compat=True"
                )
                ev_dict["trace_summary"] = f"{ev_dict['trace_summary']}; rescued=selective_statutory_article"
                evidence_by_hsn[hsn] = ev_dict
                qualifying.append(c)
                seen_qual_hsn.add(hsn)
                rescued_hsns.append(hsn)

        # Order qualifying by evidence verdict -> relation priority -> unified Stage 2+3 composite score
        _ev_rank = {SUPPORTED: 0, POSSIBLY_SUPPORTED: 1, INSUFFICIENT_EVIDENCE: 2}
        _rel_rank = {
            RelationLabel.SAME_PRODUCT: 0,
            RelationLabel.INSUFFICIENT_INFORMATION: 1,
            RelationLabel.RELATED_PRODUCT: 2,
            RelationLabel.UNRELATED: 3,
        }
        _q_toks = {
            t for t in re.findall(r"\b[a-z0-9]{3,}\b", effective_query.lower())
            if t not in {"and", "the", "for", "with", "other", "from", "type", "made"}
        }

        def _composite_rank_score(c: ClassifiedTariffCandidate) -> float:
            hsn = c.candidate.hsn_code
            ev_info = evidence_by_hsn.get(hsn, {})
            raw = disc.raw_records_by_id.get(hsn, {})
            ce_conf = float(c.confidence)
            ev_score = float(ev_info.get("evidence_score", 0.0))
            rrf_norm = min(1.0, float(raw.get("rrf_score", 0.0) or 0.0) / 0.04)

            tariff_desc = str(raw.get("tariff_item_desc") or c.candidate.tariff_item_desc or "").strip().lower()
            sub6_desc = str(raw.get("subheading_6digit_desc") or "").strip().lower()
            leaf_specificity_bonus = 0.0
            if tariff_desc in {"other", "others", "- other", "-- other", "--- other", "---- other"}:
                leaf_specificity_bonus = -0.015
            elif _q_toks:
                leaf_toks = set(re.findall(r"\b[a-z0-9]{3,}\b", f"{tariff_desc} {sub6_desc}"))
                if _q_toks & leaf_toks:
                    leaf_specificity_bonus = 0.04

            return (0.58 * ce_conf) + (0.27 * ev_score) + (0.15 * rrf_norm) + leaf_specificity_bonus

        qualifying.sort(
            key=lambda c: (
                _ev_rank.get(evidence_by_hsn.get(c.candidate.hsn_code, {}).get("status", POSSIBLY_SUPPORTED), 2),
                _rel_rank.get(c.relation, 3),
                -_composite_rank_score(c),
                -c.confidence,
            )
        )

        # 2. Independent 98-chapter statutory comparison
        stage3_evidence_ms = round((time.perf_counter() - t_ev0) * 1000.0, 2)
        t_stat0 = time.perf_counter()
        best_active_score = qualifying[0].confidence if qualifying else 0.0
        comp = self.statutory_index.compare_active_vs_statutory(
            query=effective_query,
            best_active_score=best_active_score,
            reranker=self.classifier.reranker,
        )
        stage3_statutory_ms = round((time.perf_counter() - t_stat0) * 1000.0, 2)

        # 3. Separate 8-digit leaf tariff items from 4/6-digit parent headings.
        # Keep parents in hierarchy_context for explanation/clarification, never as customer-facing options when leaves exist.
        leaf_qualifying = [c for c in qualifying if _is_leaf_8digit(c)]
        parent_qualifying = [c for c in qualifying if not _is_leaf_8digit(c)]

        non_rescued_ev_backed = [
            c for c in leaf_qualifying
            if not evidence_by_hsn.get(c.candidate.hsn_code, {}).get("rescued_by_statutory_evidence")
            and evidence_by_hsn.get(c.candidate.hsn_code, {}).get("status") in (SUPPORTED, POSSIBLY_SUPPORTED)
        ]
        rescued_leaves = [
            c for c in leaf_qualifying
            if evidence_by_hsn.get(c.candidate.hsn_code, {}).get("rescued_by_statutory_evidence")
        ]
        insuff_filtered_count = 0
        if non_rescued_ev_backed:
            kept_leaves = non_rescued_ev_backed + rescued_leaves
            insuff_filtered_count = len(leaf_qualifying) - len(kept_leaves)
            qualifying_ordered = kept_leaves
        elif leaf_qualifying:
            qualifying_ordered = leaf_qualifying
        else:
            qualifying_ordered = parent_qualifying

        # Group qualifying candidates reversibly without losing any record
        groups, hsn_to_group = group_candidates(qualifying_ordered)

        # 4. Compute calibrated query-level confidences
        bundle = getattr(self.classifier, "calibration_bundle", None)
        same = [c for c in qualifying_ordered if c.relation == RelationLabel.SAME_PRODUCT]
        same_leaves = [c for c in same if _is_leaf_8digit(c)]
        same_parents = [c for c in parent_qualifying if c.relation == RelationLabel.SAME_PRODUCT]
        insuff = [c for c in qualifying_ordered if c.relation == RelationLabel.INSUFFICIENT_INFORMATION]
        related = [c for c in qualifying_ordered if c.relation == RelationLabel.RELATED_PRODUCT]

        # Dynamic statutory & numerical distinction analysis over top competing 8-digit leaves,
        # including INSUFFICIENT_INFORMATION siblings under the winning 6-digit subheading so
        # unresolved 6-digit sibling competition is never hidden by a single SAME_PRODUCT label.
        dist_pool = list(same_leaves[:20])
        if same_leaves:
            top_sub6 = same_leaves[0].candidate.hsn_code[:6]
            seen_dist_hsn = {c.candidate.hsn_code for c in dist_pool}
            for c in qualifying_ordered:
                if (
                    _is_leaf_8digit(c)
                    and c.candidate.hsn_code[:6] == top_sub6
                    and c.candidate.hsn_code not in seen_dist_hsn
                    and c.relation != RelationLabel.RELATED_PRODUCT
                ):
                    dist_pool.append(c)
                    seen_dist_hsn.add(c.candidate.hsn_code)
                    if len(dist_pool) >= 20:
                        break
        has_competing_sub6_leaves = len(dist_pool) > 1 and any(
            c.candidate.hsn_code[:6] == same_leaves[0].candidate.hsn_code[:6]
            and c.candidate.hsn_code != same_leaves[0].candidate.hsn_code
            for c in dist_pool
        ) if same_leaves else False

        dist_analysis = analyze_sibling_distinctions(dist_pool, effective_query) if dist_pool else {
            "per_candidate": [],
            "ranked_indices": [],
            "winner_idx": None,
            "winner_has_clear_evidence": False,
            "evidence_margin": 0.0,
            "missing_numeric_constraints": False,
            "distinguishing_phrases": {},
        }
        if same_leaves and dist_analysis.get("ranked_indices"):
            reordered_dist = [dist_pool[i] for i in dist_analysis["ranked_indices"]]
            same_set = {id(c) for c in same_leaves}
            head_reordered = [c for c in reordered_dist if id(c) in same_set]
            for c in same_leaves:
                if c not in head_reordered:
                    head_reordered.append(c)
            same_leaves = head_reordered
            seen_ids = {id(c) for c in same_leaves}
            qualifying_ordered = same_leaves + [c for c in qualifying_ordered if id(c) not in seen_ids]
            groups, hsn_to_group = group_candidates(qualifying_ordered)

        t_diff0 = time.perf_counter()
        focus_pool = same_leaves if len(same_leaves) >= 2 else (same if len(same) >= 2 else (same + insuff)[:12])
        sep_attrs: List[str] = []
        attr_ev: Dict[str, List[str]] = {}
        if len(focus_pool) >= 2:
            # Diversify across headings for difference analysis while keeping full pool intact
            seen_h4 = set()
            div_focus: List[ClassifiedTariffCandidate] = []
            for c in focus_pool:
                h4 = c.candidate.hsn_code[:4]
                if h4 not in seen_h4:
                    seen_h4.add(h4)
                    div_focus.append(c)
            if len(div_focus) < 2:
                div_focus = list(focus_pool[:6])
            sep_attrs, attr_ev = identify_separating_attributes(div_focus, effective_query)
            questions = build_targeted_clarifications(effective_query, div_focus, sep_attrs, attr_ev)
        else:
            questions = []
        diff_ms = round((time.perf_counter() - t_diff0) * 1000.0, 2)

        # Compute independent confidences over ordered 8-digit leaves (fallback to full pool if no leaves)
        conf_pool = [c for c in qualifying_ordered if _is_leaf_8digit(c)] or qualifying_ordered
        best_rel_conf = (
            qualifying_ordered[0].relevance_confidence
            if qualifying_ordered and qualifying_ordered[0].relevance_confidence > 0
            else best_active_score
        )
        if conf_pool and bundle is not None:
            feats = extract_query_confidence_features(
                raw_logits=[c.candidate.raw_logit for c in conf_pool],
                hsn_codes=[c.candidate.hsn_code for c in conf_pool],
                chapter_codes=[c.candidate.chapter_code for c in conf_pool],
                query=effective_query,
                rel_threshold_logit=0.97,
                is_ambiguous=len({c.candidate.hsn_code[:4] for c in same_leaves}) > 1,
            )
            chap_conf = round(float(bundle.chapter_calibrator.predict_proba_one(feats)), 4)
            hsn_conf = round(float(bundle.hsn_calibrator.predict_proba_one(feats)), 4)
        else:
            chap_conf = round(float(best_rel_conf), 4)
            hsn_conf = round(float(best_rel_conf), 4)

        distinction_conf = 0.0
        if len(leaf_qualifying) >= 2:
            distinction_conf = round(max(0.0, leaf_qualifying[0].confidence - leaf_qualifying[1].confidence), 4)
        elif len(leaf_qualifying) == 1:
            distinction_conf = 1.0

        # 5. Decision Controller (only 8-digit leaf HSNs may become EXACT_HSN)
        from src.ml.confidence_calibrator import DEFAULT_TAU_ABSTAIN, DEFAULT_TAU_EXACT_HSN

        tau_abstain = bundle.tau_abstain if bundle is not None else DEFAULT_TAU_ABSTAIN
        tau_exact = bundle.tau_exact_hsn if bundle is not None else DEFAULT_TAU_EXACT_HSN

        final_hsn: Optional[str] = None
        final_chapter: Optional[str] = None
        prediction_mode = "INSUFFICIENT_INFORMATION"
        requires_clarification = True
        clarification_reason = ""

        if comp.is_out_of_schedule and comp.best_inactive_match:
            prediction_mode = "OUT_OF_SCHEDULE"
            final_hsn = comp.best_inactive_match.get("hsn_code")
            final_chapter = comp.best_inactive_match.get("chapter")
            requires_clarification = False
            clarification_reason = comp.reason
        elif not qualifying_ordered or best_rel_conf < tau_abstain:
            prediction_mode = "INSUFFICIENT_INFORMATION"
            requires_clarification = True
            clarification_reason = (
                f"Insufficient product evidence (relevance_confidence={best_rel_conf:.2f} < {tau_abstain:.2f})."
            )
        elif not same_leaves:
            if same_parents:
                parent_chaps = {c.candidate.chapter_code for c in same_parents if c.candidate.chapter_code}
                if len(parent_chaps) == 1:
                    prediction_mode = "CHAPTER_ONLY_CLARIFY"
                    final_chapter = next(iter(parent_chaps))
                else:
                    prediction_mode = "MULTIPLE_CANDIDATES"
                requires_clarification = True
                clarification_reason = (
                    "Evidence supports parent tariff heading/subheading only; clarification needed to select an 8-digit leaf HSN."
                )
            elif len(insuff) >= 2 or len(related) >= 2:
                prediction_mode = "MULTIPLE_CANDIDATES" if len(qualifying_ordered) >= 2 else "INSUFFICIENT_INFORMATION"
                clarification_reason = "Multiple related or uncertain candidates found; clarification needed."
            else:
                prediction_mode = "INSUFFICIENT_INFORMATION"
                clarification_reason = "No 8-digit leaf candidate met the calibrated SAME_PRODUCT threshold."
        else:
            unique_headings = {c.candidate.hsn_code[:4] for c in same_leaves if c.candidate.hsn_code}
            competing_rescued = [
                c for c in qualifying_ordered
                if evidence_by_hsn.get(c.candidate.hsn_code, {}).get("rescued_by_statutory_evidence")
                and c.candidate.hsn_code[:4] != same_leaves[0].candidate.hsn_code[:4]
                and len(evidence_by_hsn.get(c.candidate.hsn_code, {}).get("statutory_article_matches") or []) >= 2
                and evidence_by_hsn.get(c.candidate.hsn_code, {}).get("heading_compatible")
                and not evidence_by_hsn.get(c.candidate.hsn_code, {}).get("role_mismatch")
            ]
            top_role_mismatch = evidence_by_hsn.get(same_leaves[0].candidate.hsn_code, {}).get("role_mismatch", "")
            if top_role_mismatch == "complete_article_vs_parts":
                prediction_mode = "MULTIPLE_CANDIDATES" if len(unique_headings) > 1 else "CHAPTER_ONLY_CLARIFY"
                final_chapter = None if len(unique_headings) > 1 else same_leaves[0].candidate.chapter_code
                requires_clarification = True
                clarification_reason = (
                    "Top-ranked candidate is a parts/accessories tariff item while the description specifies a complete article; "
                    "clarification needed to confirm complete machine vs. spare part."
                )
            elif competing_rescued:
                prediction_mode = "MULTIPLE_CANDIDATES"
                final_chapter = None
                requires_clarification = True
                clarification_reason = (
                    f"Competing statutory heading(s) {[c.candidate.hsn_code[:4] for c in competing_rescued[:3]]} "
                    "have strong independent statutory article evidence; clarification needed."
                )
            elif len(unique_headings) > 1 and distinction_conf < 0.05:
                prediction_mode = "MULTIPLE_CANDIDATES"
                final_chapter = None
                requires_clarification = True
                clarification_reason = (
                    f"{len(same_leaves)} SAME_PRODUCT leaf candidates span {len(unique_headings)} distinct headings "
                    f"with low distinction confidence ({distinction_conf:.4f}); clarification needed."
                )
            elif dist_analysis.get("missing_numeric_constraints"):
                if len(unique_headings) > 1:
                    prediction_mode = "MULTIPLE_CANDIDATES"
                    final_chapter = None
                else:
                    prediction_mode = "CHAPTER_ONLY_CLARIFY"
                    final_chapter = same_leaves[0].candidate.chapter_code
                requires_clarification = True
                clarification_reason = (
                    "Competing tariff items are separated by numerical thresholds not specified in the description."
                )
            elif dist_analysis.get("winner_has_clear_evidence") and hsn_conf >= tau_exact and (len(unique_headings) == 1 or distinction_conf >= 0.05):
                prediction_mode = "EXACT_HSN"
                final_hsn = same_leaves[0].candidate.hsn_code
                final_chapter = same_leaves[0].candidate.chapter_code
                requires_clarification = False
            elif len(unique_headings) > 1:
                prediction_mode = "MULTIPLE_CANDIDATES"
                final_chapter = None
                requires_clarification = True
                clarification_reason = (
                    f"{len(same_leaves)} SAME_PRODUCT leaf candidates span {len(unique_headings)} distinct headings."
                )
            elif len(same_leaves) > 1 or has_competing_sub6_leaves:
                prediction_mode = "CHAPTER_ONLY_CLARIFY"
                final_chapter = same_leaves[0].candidate.chapter_code
                requires_clarification = True
                clarification_reason = (
                    f"Heading {same_leaves[0].candidate.hsn_code[:4]} supported, but {max(len(same_leaves), len(dist_pool))} leaf tariff items compete without decisive statutory distinction."
                )
            elif hsn_conf >= tau_exact:
                prediction_mode = "EXACT_HSN"
                final_hsn = same_leaves[0].candidate.hsn_code
                final_chapter = same_leaves[0].candidate.chapter_code
                requires_clarification = False
            else:
                prediction_mode = "CHAPTER_ONLY_CLARIFY"
                final_chapter = same_leaves[0].candidate.chapter_code
                requires_clarification = True

        # 6. Build full non-truncated candidate records with lineage & explanations
        all_formatted: List[Dict[str, Any]] = []
        top_score = qualifying_ordered[0].confidence if qualifying_ordered else 0.0
        for rank, c in enumerate(qualifying_ordered, start=1):
            raw = disc.raw_records_by_id.get(c.candidate.hsn_code, {})
            mats = sorted(_extract_material_tokens(c.candidate.material_keywords))
            reasons = [
                f"Retrieved via {raw.get('retrieval_source', 'hybrid')} "
                f"(bm25={raw.get('bm25_score', 0.0)}, dense={raw.get('vector_score', 0.0)})",
                f"Cross-Encoder classified as {c.relation.value} (logit={c.candidate.raw_logit:.2f})",
            ]
            if rank == 1:
                reasons.append("Highest-ranked candidate in discovered pool.")
            else:
                reasons.append(f"Score delta vs top-1: {c.confidence - top_score:+.4f}.")

            ev_info = evidence_by_hsn.get(c.candidate.hsn_code, {})
            all_formatted.append({
                "rank": rank,
                "hsn_code": c.candidate.hsn_code,
                "tariff_level": getattr(c.candidate, "tariff_level", classify_tariff_level(c.candidate.hsn_code)),
                "chapter_code": c.candidate.chapter_code,
                "hsn_description": c.candidate.description,
                "heading_4digit_desc": raw.get("heading_4digit_desc") or getattr(c.candidate, "heading_4digit_desc", ""),
                "subheading_6digit_desc": raw.get("subheading_6digit_desc") or getattr(c.candidate, "subheading_6digit_desc", ""),
                "tariff_item_desc": raw.get("tariff_item_desc") or getattr(c.candidate, "tariff_item_desc", ""),
                "source_record_id": raw.get("source_record_id", f"hsn_{c.candidate.hsn_code}"),
                "retrieval_source": raw.get("retrieval_source", "hybrid"),
                "retrieval_path": raw.get("retrieval_path", "global_safeguard"),
                "chapter_allocated_slots": int(raw.get("chapter_allocated_slots") or 0),
                "bm25_score": raw.get("bm25_score"),
                "vector_score": raw.get("vector_score"),
                "rrf_score": raw.get("rrf_score"),
                "chapter_guided": bool(raw.get("chapter_guided", False)),
                "cross_chapter_discovery": bool(raw.get("cross_chapter_discovery", False)),
                "cross_chapter_reason": raw.get("cross_chapter_reason", ""),
                "retrieval_explanation": raw.get("retrieval_explanation") or reasons[0],
                "matching_attributes": list(ev_info.get("article_matches") or []) + list(ev_info.get("material_matches") or []),
                "missing_attributes": list(ev_info.get("missing_attributes") or []),
                "relevance_category": c.relation.value,
                "evidence_status": ev_info.get("status", POSSIBLY_SUPPORTED),
                "evidence_trace": ev_info,
                "retrieval_score": raw.get("rrf_score"),
                "raw_logit": round(c.candidate.raw_logit, 4),
                "relevance_confidence": c.relevance_confidence or c.confidence,
                "hsn_confidence": hsn_conf if rank == 1 else None,
                "candidate_group": hsn_to_group.get(c.candidate.hsn_code),
                "known_attributes": {
                    "material_keywords": mats[:5],
                    "confirmed_by_user": confirmed,
                },
                "uncertain_attributes": list(sep_attrs),
                "match_reasons": reasons,
                "differences": [
                    f"{k}: {', '.join(v)}" for k, v in attr_ev.items()
                ],
                "requires_clarification": requires_clarification,
            })

        paged_candidates, pagination_meta = _paginate(all_formatted, page=page, page_size=page_size)
        total_ms = round((time.perf_counter() - t_total0) * 1000.0, 2)
        guided_chaps = [
            str(c.get("chapter_code", "")).zfill(2)
            for c in (effective_stage1.get("chapter_candidates") or [])
            if isinstance(c, dict) and c.get("chapter_code")
        ]
        cross_chap_cnt = sum(1 for item in all_formatted if item.get("cross_chapter_discovery"))

        chapter_guided_list = [
            {
                "hsn_code": item["hsn_code"],
                "chapter_code": item["chapter_code"],
                "retrieval_path": item["retrieval_path"],
                "rrf_score": item["rrf_score"],
                "bm25_score": item["bm25_score"],
                "vector_score": item["vector_score"],
                "hsn_description": item["hsn_description"],
            }
            for item in all_formatted
            if "chapter_guided" in str(item.get("retrieval_path", "")) or item.get("chapter_guided")
        ][:15]

        global_safeguard_list = [
            {
                "hsn_code": item["hsn_code"],
                "chapter_code": item["chapter_code"],
                "retrieval_path": item["retrieval_path"],
                "rrf_score": item["rrf_score"],
                "bm25_score": item["bm25_score"],
                "vector_score": item["vector_score"],
                "cross_chapter_discovery": item["cross_chapter_discovery"],
                "cross_chapter_reason": item["cross_chapter_reason"],
                "hsn_description": item["hsn_description"],
            }
            for item in all_formatted
            if "global" in str(item.get("retrieval_path", "")) or item.get("cross_chapter_discovery")
        ][:15]

        chapter_allocations = {}
        for item in all_formatted:
            ch = str(item.get("chapter_code") or "").zfill(2)
            slots = int(item.get("chapter_allocated_slots") or 0)
            if ch and slots > 0 and ch not in chapter_allocations:
                chapter_allocations[ch] = slots

        return {
            "input_description": orig,
            "effective_query": effective_query,
            "confirmed_attributes": confirmed,
            "product_intent": product_intent.to_dict(),
            "stage1_handoff": {
                "received_stage1": isinstance(stage1_result, dict),
                "stage1_status": effective_stage1.get("stage1_status"),
                "primary_commercial_article": product_intent.finished_article,
                "guided_chapters": guided_chaps,
                "cross_chapter_candidates_count": cross_chap_cnt,
            },
            "stage2_retrieval_summary": {
                "chapter_guided_candidates": chapter_guided_list,
                "global_safeguard_candidates": global_safeguard_list,
                "combined_deduplicated_count": len(all_formatted),
                "chapter_allocations": chapter_allocations,
            },
            "prediction_mode": prediction_mode,
            "final_hsn": final_hsn,
            "final_chapter": final_chapter,
            "confidences": {
                "retrieval_relevance": round(float(qualifying[0].confidence), 4) if qualifying else 0.0,
                "relevance_confidence": round(float(best_rel_conf), 4),
                "chapter_confidence": chap_conf,
                "hsn_confidence": hsn_conf,
                "distinction_confidence": distinction_conf,
                "discovery_completeness": 1.0 if disc.discovery_complete else round(
                    disc.records_examined / max(getattr(self.hybrid_engine, "total_records", 1), 1), 4
                ),
            },
            "discovery": {
                "total_retrieved": disc.total_retrieved,
                "qualifying_candidates": len(all_formatted),
                "same_product_count": len(same),
                "related_product_count": len(related),
                "insufficient_info_count": len(insuff),
                "discovery_complete": disc.discovery_complete,
                "stopping_reason": disc.stopping_reason,
                "expansion_rounds": disc.expansion_rounds,
                "leaf_candidates_count": len(leaf_qualifying),
                "parent_candidates_count": len(parent_qualifying),
            },
            "hierarchy_context": {
                "leaf_candidates": len(leaf_qualifying),
                "parent_candidates": len(parent_qualifying),
                "parent_codes": [c.candidate.hsn_code for c in parent_qualifying[:20]],
            },
            "statutory_distinction": {
                "winner_has_clear_evidence": bool(dist_analysis.get("winner_has_clear_evidence")),
                "evidence_margin": float(dist_analysis.get("evidence_margin", 0.0)),
                "missing_numeric_constraints": bool(dist_analysis.get("missing_numeric_constraints")),
                "distinguishing_phrases": dist_analysis.get("distinguishing_phrases", {}),
            },
            "evidence_summary": {
                "initial_retrieved": disc.total_retrieved,
                "retained_count": len(all_formatted),
                "supported_count": sum(1 for c in all_formatted if c.get("evidence_status") == SUPPORTED),
                "possibly_supported_count": sum(1 for c in all_formatted if c.get("evidence_status") == POSSIBLY_SUPPORTED),
                "insufficient_evidence_count": sum(1 for c in all_formatted if c.get("evidence_status") == INSUFFICIENT_EVIDENCE),
                "insufficient_evidence_filtered_count": insuff_filtered_count,
                "contradicted_filtered_count": contradicted_count,
                "rescued_candidates_count": len(rescued_hsns),
                "rescued_hsn_codes": rescued_hsns[:20],
                "parent_records_excluded_count": len(parent_qualifying) if leaf_qualifying else 0,
            },
            "best_supported_candidate": all_formatted[0] if all_formatted else None,
            "categorized_candidates": {
                "same_product": [c for c in all_formatted if c["relevance_category"] == RelationLabel.SAME_PRODUCT.value],
                "related_product": [c for c in all_formatted if c["relevance_category"] == RelationLabel.RELATED_PRODUCT.value],
                "insufficient_information": [c for c in all_formatted if c["relevance_category"] == RelationLabel.INSUFFICIENT_INFORMATION.value],
            },
            "candidates": paged_candidates,
            "all_candidates_count": len(all_formatted),
            "candidate_groups": groups,
            "clarification": {
                "required": requires_clarification,
                "reason": clarification_reason,
                "separating_attributes": sep_attrs,
                "questions": questions,
            },
            "active_vs_statutory": {
                "is_out_of_schedule": comp.is_out_of_schedule,
                "best_active_score": comp.best_active_score,
                "best_inactive_score": comp.best_inactive_score,
                "best_inactive_match": comp.best_inactive_match,
                "reason": comp.reason,
            },
            "pagination": pagination_meta,
            "audit": {
                "retrieval_sources": disc.retrieval_sources,
                "candidates_discarded": disc.candidates_discarded + contradicted_count,
                "discard_reasons": (disc.discard_reasons + contradicted_reasons)[:20],
                "execution_metrics": {
                    "stage1_intent_ms": stage1_intent_ms,
                    "retrieval_time_ms": disc.retrieval_time_ms,
                    "reranking_time_ms": disc.reranking_time_ms,
                    "stage3_evidence_ms": stage3_evidence_ms,
                    "stage3_statutory_ms": stage3_statutory_ms,
                    "difference_analysis_time_ms": diff_ms,
                    "total_time_ms": total_ms,
                    "inference_timeout_s": self.inference_timeout_s,
                    "records_examined": disc.records_examined,
                    "candidates_preserved": len(all_formatted),
                },
            },
        }

    def clarify_and_refine(
        self,
        original_description: str,
        previous_confirmed: Optional[Dict[str, str]],
        new_answers: Dict[str, str],
        page: int = 1,
        page_size: Optional[int] = 20,
    ) -> Dict[str, Any]:
        """
        Progressive clarification: preserves `original_description`, merges confirmed
        user answers, re-evaluates/expands candidates, and recalculates rankings.
        """
        merged = dict(previous_confirmed or {})
        for k, v in (new_answers or {}).items():
            if v is not None and str(v).strip():
                merged[str(k)] = str(v).strip()
        return self.classify_adaptive(
            description=original_description,
            confirmed_attributes=merged,
            page=page,
            page_size=page_size,
        )

    def record_feedback(
        self,
        original_description: str,
        selected_hsn: str,
        predicted_hsn: Optional[str] = None,
        confirmed_attributes: Optional[Dict[str, str]] = None,
        rejected_alternatives: Optional[List[str]] = None,
        reason: str = "",
    ) -> str:
        """
        Logs user correction/confirmation into pending_feedback.jsonl for GST expert
        verification (never trains directly on unverified user input).
        """
        ctx = json_context = (
            f"confirmed={confirmed_attributes or {}} | rejected={rejected_alternatives or []}"
        )
        return self.feedback.record_pending_feedback(
            query=original_description,
            predicted_hsn=predicted_hsn or "",
            predicted_context=json_context,
            predicted_score=0.0,
            customer_selected_hsn=selected_hsn,
            reason=reason or "Phase 7 Multi-Candidate UI/API feedback",
        )

    def _empty_response(
        self, orig: str, confirmed: Dict[str, str], page: int, page_size: Optional[int], t0: float
    ) -> Dict[str, Any]:
        return {
            "input_description": orig,
            "effective_query": orig,
            "confirmed_attributes": confirmed,
            "prediction_mode": "INSUFFICIENT_INFORMATION",
            "final_hsn": None,
            "final_chapter": None,
            "confidences": {
                "retrieval_relevance": 0.0,
                "relevance_confidence": 0.0,
                "chapter_confidence": 0.0,
                "hsn_confidence": 0.0,
                "distinction_confidence": 0.0,
                "discovery_completeness": 1.0,
            },
            "discovery": {
                "total_retrieved": 0,
                "qualifying_candidates": 0,
                "same_product_count": 0,
                "related_product_count": 0,
                "insufficient_info_count": 0,
                "discovery_complete": True,
                "stopping_reason": "empty_query",
                "expansion_rounds": 0,
            },
            "evidence_summary": {
                "initial_retrieved": 0,
                "retained_count": 0,
                "supported_count": 0,
                "possibly_supported_count": 0,
                "insufficient_evidence_count": 0,
                "insufficient_evidence_filtered_count": 0,
                "contradicted_filtered_count": 0,
                "parent_records_excluded_count": 0,
            },
            "best_supported_candidate": None,
            "categorized_candidates": {
                "same_product": [],
                "related_product": [],
                "insufficient_information": [],
            },
            "candidates": [],
            "all_candidates_count": 0,
            "candidate_groups": [],
            "clarification": {
                "required": True,
                "reason": "Product description is empty.",
                "separating_attributes": [],
                "questions": [],
            },
            "active_vs_statutory": {},
            "pagination": {"page": 1, "page_size": page_size or 20, "total_candidates": 0, "total_pages": 0, "has_next_page": False},
            "audit": {
                "retrieval_sources": [],
                "candidates_discarded": 0,
                "discard_reasons": [],
                "execution_metrics": {
                    "total_time_ms": round((time.perf_counter() - t0) * 1000.0, 2),
                    "records_examined": 0,
                    "candidates_preserved": 0,
                },
            },
        }

