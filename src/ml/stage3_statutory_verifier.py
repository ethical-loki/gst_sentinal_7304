"""
src/ml/stage3_statutory_verifier.py
===================================
Stage 3: Dynamic Statutory Hierarchy Verification, Conditional GIR 1-6 Evaluation,
Verified GST Rate Lookup, and Customer-Facing Final Decision Builder.

Reuses existing Stage 1/2/3 outputs without hardcoding product-to-HSN mappings.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_GST_RATES_PATH = ROOT_DIR / "data" / "raw" / "gst_rates.json"
DEFAULT_STATUTORY_RULES_PATH = ROOT_DIR / "data" / "statutory_rules.json"

_GST_RATE_CACHE: Optional[Dict[str, Dict[str, Any]]] = None
_STATUTORY_RULES_CACHE: Optional[List[Dict[str, Any]]] = None

# WCO Harmonized System Section boundaries by 2-digit chapter range (statutory structure, non-product-specific)
_WCO_SECTIONS: List[tuple[int, int, str]] = [
    (1, 5, "Section I: Live Animals; Animal Products"),
    (6, 14, "Section II: Vegetable Products"),
    (15, 15, "Section III: Animal, Vegetable or Microbial Fats and Oils"),
    (16, 24, "Section IV: Prepared Foodstuffs; Beverages, Spirits and Vinegar; Tobacco"),
    (25, 27, "Section V: Mineral Products"),
    (28, 38, "Section VI: Products of the Chemical or Allied Industries"),
    (39, 40, "Section VII: Plastics and Articles Thereof; Rubber and Articles Thereof"),
    (41, 43, "Section VIII: Raw Hides and Skins, Leather, Furskins and Articles Thereof"),
    (44, 46, "Section IX: Wood and Articles of Wood; Cork; Basketware"),
    (47, 49, "Section X: Pulp of Wood; Paper and Paperboard and Articles Thereof"),
    (50, 63, "Section XI: Textiles and Textile Articles"),
    (64, 67, "Section XII: Footwear, Headgear, Umbrellas"),
    (68, 70, "Section XIII: Articles of Stone, Plaster, Cement, Asbestos, Mica; Ceramic; Glass"),
    (71, 71, "Section XIV: Natural or Cultured Pearls, Precious Stones, Precious Metals"),
    (72, 83, "Section XV: Base Metals and Articles of Base Metal"),
    (84, 85, "Section XVI: Machinery and Mechanical Appliances; Electrical Equipment"),
    (86, 89, "Section XVII: Vehicles, Aircraft, Vessels and Associated Transport Equipment"),
    (90, 92, "Section XVIII: Optical, Photographic, Measuring, Medical Instruments; Clocks; Musical"),
    (93, 93, "Section XIX: Arms and Ammunition"),
    (94, 96, "Section XX: Miscellaneous Manufactured Articles"),
    (97, 98, "Section XXI: Works of Art, Collectors' Pieces and Antiques / Project Imports"),
]

_INCOMPLETE_UNASSEMBLED_RE = re.compile(
    r"\b(?:incomplete|unfinished|unassembled|disassembled|knocked\s*down|ckd|skd|kit|mixture|blended)\b",
    re.IGNORECASE,
)
_CONTAINER_PACKING_RE = re.compile(
    r"\b(?:case|cases|box|boxes|pouch|pouches|holster|container|packing|packaging|carton|crate)\b",
    re.IGNORECASE,
)


def chapter_to_wco_section(chapter_code: str) -> str:
    try:
        ch = int(str(chapter_code).strip())
    except ValueError:
        return "Unknown Section"
    for lo, hi, title in _WCO_SECTIONS:
        if lo <= ch <= hi:
            return title
    return "Unknown Section"


def lookup_verified_gst_rate(
    hsn_code: Optional[str],
    gst_path: Path = DEFAULT_GST_RATES_PATH,
) -> Optional[Dict[str, Any]]:
    """Returns verified GST rate metadata from gst_rates.json ONLY for exact matching HSN codes."""
    global _GST_RATE_CACHE
    if _GST_RATE_CACHE is None:
        cache: Dict[str, Dict[str, Any]] = {}
        if gst_path.exists():
            try:
                rows = json.loads(gst_path.read_text(encoding="utf-8"))
                for r in rows if isinstance(rows, list) else []:
                    if not isinstance(r, dict):
                        continue
                    code = str(r.get("code") or "").replace(" ", "").strip()
                    if not code:
                        continue
                    entry = {
                        "igst_rate": r.get("igstRate"),
                        "cgst_rate": r.get("cgstRate"),
                        "sgst_rate": r.get("sgstRate"),
                        "cess_rate": r.get("cessRate"),
                        "effective_date": str(r.get("effectiveFrom") or "").strip(),
                        "notification_ref": str(r.get("notificationRef") or "").strip(),
                        "rate_source": str(r.get("rateSource") or "").strip(),
                        "verified": True,
                    }
                    cache[code] = entry
                    if len(code) == 7:
                        cache[code.zfill(8)] = entry
            except Exception as e:
                logger.warning(f"Failed loading GST rates from {gst_path}: {e}")
        _GST_RATE_CACHE = cache

    if not hsn_code:
        return None
    norm = str(hsn_code).replace(" ", "").strip()
    return _GST_RATE_CACHE.get(norm)


def evaluate_statutory_notes(
    chapter_code: str,
    product_intent: Any,
    rules_path: Path = DEFAULT_STATUTORY_RULES_PATH,
) -> Dict[str, Any]:
    """
    Layer 2/4: Dynamically evaluates authoritative Section/Chapter Notes from statutory_rules.json
    for the candidate chapter, reporting whether each note SUPPORTS, EXCLUDES, or CONDITIONALLY
    affects the candidate, and honestly reporting missing chapter-note coverage when unavailable.
    """
    global _STATUTORY_RULES_CACHE
    if _STATUTORY_RULES_CACHE is None:
        if rules_path.exists():
            try:
                data = json.loads(rules_path.read_text(encoding="utf-8"))
                _STATUTORY_RULES_CACHE = data if isinstance(data, list) else []
            except Exception:
                _STATUTORY_RULES_CACHE = []
        else:
            _STATUTORY_RULES_CACHE = []

    ch_norm = str(chapter_code or "").zfill(2)
    q_text = " ".join([
        str(getattr(product_intent, "raw_description", "") or ""),
        str(getattr(product_intent, "finished_article", "") or ""),
        str(getattr(product_intent, "processing_form", "") or ""),
        str(getattr(product_intent, "product_form", "") or ""),
        str(getattr(product_intent, "function_use", "") or ""),
    ]).lower()
    q_tokens = set(re.findall(r"\b[a-z0-9]{2,}\b", q_text))

    evaluations: List[Dict[str, Any]] = []
    supporting_notes: List[str] = []
    for rule in _STATUTORY_RULES_CACHE:
        target_ch = str(rule.get("target_chapter") or "").zfill(2)
        if target_ch != ch_norm:
            continue
        rule_id = str(rule.get("rule_id") or "")
        note = str(rule.get("source_note") or "").strip()
        cond_forms = [str(f).lower().strip() for f in (rule.get("condition_form") or []) if str(f).strip()]
        if cond_forms:
            matched_forms = [f for f in cond_forms if f in q_tokens]
            if matched_forms:
                effect = "SUPPORTS"
                reason = f"Product attributes {matched_forms} satisfy {note} condition for Chapter {ch_norm}."
            else:
                effect = "CONDITIONAL"
                reason = f"{note} requires {cond_forms} for Chapter {ch_norm}; condition not confirmed in Stage 1."
        else:
            effect = "SUPPORTS"
            reason = f"{note} aligns with Chapter {ch_norm} scope."

        if note and note not in supporting_notes:
            supporting_notes.append(note)
        evaluations.append({
            "rule_id": rule_id,
            "source_note": note,
            "chapter_code": ch_norm,
            "effect": effect,
            "reason": reason,
        })

    return {
        "note_coverage_status": "AUTHORITATIVE_NOTES_EVALUATED" if evaluations else "NO_CHAPTER_NOTES_IN_SOURCE",
        "supporting_notes": supporting_notes,
        "note_evaluations": evaluations,
    }


def load_applicable_section_notes(
    chapter_code: str,
    rules_path: Path = DEFAULT_STATUTORY_RULES_PATH,
) -> List[str]:
    """Returns statutory section/chapter notes from statutory_rules.json matching the candidate chapter."""
    res = evaluate_statutory_notes(chapter_code, product_intent=None, rules_path=rules_path)
    return res["supporting_notes"]


def verify_statutory_hierarchy(
    raw_rec: Optional[Dict[str, Any]],
    candidate: Any,
) -> Dict[str, Any]:
    """
    Layer 1: Verifies Section -> Chapter -> Heading (4d) -> Subheading (6d) -> Tariff Item (8d)
    parent-child consistency and statutory completeness.
    """
    rec = raw_rec or {}
    hsn = str(rec.get("hsn_code") or getattr(candidate, "hsn_code", "") or "").strip()
    ch = str(rec.get("chapter_code") or getattr(candidate, "chapter_code", "") or hsn[:2]).zfill(2)
    h4 = str(rec.get("heading_4digit") or hsn[:4]).strip()
    h6 = str(rec.get("subheading_6digit") or hsn[:6]).strip()
    h4_desc = str(rec.get("heading_4digit_desc") or getattr(candidate, "heading_4digit_desc", "") or "").strip()
    h6_desc = str(rec.get("subheading_6digit_desc") or getattr(candidate, "subheading_6digit_desc", "") or "").strip()
    item_desc = str(rec.get("tariff_item_desc") or getattr(candidate, "tariff_item_desc", "") or "").strip()
    stat_desc = str(rec.get("statutory_description") or getattr(candidate, "description", "") or "").strip()

    is_leaf = len(hsn) == 8 and hsn.isdigit()
    prefix_consistent = (
        bool(hsn)
        and hsn.startswith(ch)
        and (not h4 or hsn.startswith(h4))
        and (not h6 or hsn.startswith(h6))
    )
    has_leaf_text = bool(item_desc or stat_desc)
    is_truncated = bool(rec.get("is_truncated", len(stat_desc) == 255))
    is_incomplete = bool(rec.get("is_incomplete", not bool(stat_desc)))
    is_residual = bool(rec.get("is_residual", item_desc.upper() in {"OTHER", "OTHERS"}))

    issues: List[str] = []
    if not is_leaf:
        issues.append("Not an 8-digit tariff item leaf")
    if not prefix_consistent:
        issues.append("Parent-child code prefix mismatch")
    if not has_leaf_text or is_incomplete:
        issues.append("Missing statutory tariff description")
    if is_truncated:
        issues.append("Statutory description truncated at 255 characters")

    return {
        "section": chapter_to_wco_section(ch),
        "chapter_code": ch,
        "heading_4digit": h4,
        "heading_4digit_desc": h4_desc,
        "subheading_6digit": h6,
        "subheading_6digit_desc": h6_desc,
        "tariff_item_8digit": hsn if is_leaf else None,
        "tariff_item_desc": item_desc,
        "statutory_description": stat_desc,
        "source_provenance": str(rec.get("source_provenance") or "Master_copy_hsn.xlsx"),
        "is_leaf_8digit": is_leaf,
        "prefix_consistent": prefix_consistent,
        "is_residual": is_residual,
        "is_truncated": is_truncated,
        "is_incomplete": is_incomplete,
        "hierarchy_valid": is_leaf and prefix_consistent and has_leaf_text and not is_incomplete,
        "issues": issues,
    }


def evaluate_gir_sequence(
    product_intent: Any,
    qualifying_leaves: Sequence[Any],
    evidence_by_hsn: Dict[str, Dict[str, Any]],
    raw_records_by_id: Dict[str, Dict[str, Any]],
    dist_analysis: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Layer 2: Conditionally evaluates General Interpretative Rules (GIR 1, 2, 3(a)/3(b)/3(c), 4, 5, 6)
    in legal sequence, recording applicability, legal test applied, evidence considered,
    conclusion, and reason for non-application when a rule does not trigger.
    """
    gir_steps: List[Dict[str, Any]] = []
    supporting_notes: List[str] = []
    note_eval_summary: Dict[str, Any] = {
        "note_coverage_status": "NO_CHAPTER_NOTES_IN_SOURCE",
        "supporting_notes": [],
        "note_evaluations": [],
    }

    raw_desc = str(getattr(product_intent, "raw_description", "") or "")
    finished = str(getattr(product_intent, "finished_article", "") or "")
    proc_form = str(getattr(product_intent, "processing_form", "") or "")
    pkg = str(getattr(product_intent, "packaging_or_presentation", "") or "")
    mats = list(getattr(product_intent, "constituent_materials", []) or [])
    full_q = f"{raw_desc} {finished} {proc_form} {pkg}".strip()

    if not qualifying_leaves:
        gir_steps.append({
            "rule": "GIR 1",
            "applicable": True,
            "status": "UNRESOLVED",
            "legal_test_applied": "Heading terms and applicable Section/Chapter Notes",
            "evidence_considered": [],
            "conclusion": "No 8-digit tariff item matched heading terms and legal notes with sufficient evidence.",
            "not_applied_reason": "",
            "explanation": "No 8-digit tariff item matched heading terms and legal notes with sufficient evidence.",
        })
        return {
            "gir_reasoning": gir_steps,
            "supporting_notes": supporting_notes,
            "note_evaluation": note_eval_summary,
        }

    top = qualifying_leaves[0]
    top_hsn = top.candidate.hsn_code
    top_ch = top.candidate.chapter_code
    top_ev = evidence_by_hsn.get(top_hsn, {})
    note_eval_summary = evaluate_statutory_notes(top_ch, product_intent)
    supporting_notes = list(note_eval_summary["supporting_notes"])

    # GIR 1: Always primary legal rule
    art_m = top_ev.get("statutory_article_matches") or top_ev.get("article_matches") or []
    gir1_ok = bool(top_ev.get("heading_compatible") and art_m)
    gir1_expl = (
        f"Evaluated heading {top_hsn[:4]} terms and Chapter {top_ch} notes ({note_eval_summary['note_coverage_status']}); "
        f"statutory article alignment={art_m[:3] or 'none'}, heading_compatible={bool(top_ev.get('heading_compatible'))}."
    )
    gir_steps.append({
        "rule": "GIR 1",
        "applicable": True,
        "status": "APPLIED" if gir1_ok else "PARTIAL",
        "legal_test_applied": "Classification according to terms of the headings and relevant Section/Chapter Notes",
        "evidence_considered": list(art_m[:4]) + supporting_notes[:3],
        "conclusion": f"Heading {top_hsn[:4]} supported under GIR 1" if gir1_ok else f"Heading {top_hsn[:4]} only partially supported",
        "not_applied_reason": "",
        "explanation": gir1_expl,
    })

    # GIR 2: Incomplete/unfinished/unassembled (2a) or mixtures/combinations (2b)
    has_incomplete_cue = bool(_INCOMPLETE_UNASSEMBLED_RE.search(full_q))
    has_mixture_cue = len(mats) > 1 and bool(re.search(r"\b(?:blend|blended|mix|mixture|alloy|composite|with)\b", full_q, re.IGNORECASE))
    if has_incomplete_cue or has_mixture_cue:
        gir2_expl = (
            "Evaluated GIR 2(a)/2(b) due to explicit incomplete/unassembled or multi-material mixture cues."
        )
        gir_steps.append({
            "rule": "GIR 2",
            "applicable": True,
            "status": "CONSIDERED",
            "legal_test_applied": "GIR 2(a) essential character of incomplete/unassembled article / GIR 2(b) mixtures",
            "evidence_considered": mats[:4] + ([proc_form] if proc_form else []),
            "conclusion": "Requires verifying whether article has essential character of complete good or mixture rule applies.",
            "not_applied_reason": "",
            "explanation": gir2_expl,
        })
    else:
        gir_steps.append({
            "rule": "GIR 2",
            "applicable": False,
            "status": "NOT_APPLICABLE",
            "legal_test_applied": "None",
            "evidence_considered": [],
            "conclusion": "Product is not described as incomplete, unfinished, unassembled, or a mixture.",
            "not_applied_reason": "No incomplete/unassembled or mixture cues in Stage 1 attributes.",
            "explanation": "GIR 2 not applicable: complete single-article description.",
        })

    # GIR 3(a), 3(b), 3(c): Only when multiple 4-digit headings compete
    unique_h4 = sorted({c.candidate.hsn_code[:4] for c in qualifying_leaves if getattr(c, "candidate", None)})
    if len(unique_h4) > 1:
        top_specific = bool(art_m) and not top_ev.get("role_mismatch")
        gir_steps.append({
            "rule": "GIR 3(a)",
            "applicable": True,
            "status": "APPLIED" if top_specific else "UNRESOLVED",
            "legal_test_applied": "Most specific description preferred over headings providing a more general description",
            "evidence_considered": [f"competing_headings={unique_h4[:4]}", f"top_statutory_matches={art_m[:3]}"],
            "conclusion": f"Heading {top_hsn[:4]} shows specific statutory match" if top_specific else "No single heading is strictly more specific",
            "not_applied_reason": "",
            "explanation": f"GIR 3(a) evaluated across competing headings {unique_h4[:4]}.",
        })
        if len(mats) > 1 or getattr(product_intent, "components_or_parts", []):
            gir_steps.append({
                "rule": "GIR 3(b)",
                "applicable": True,
                "status": "CONSIDERED",
                "legal_test_applied": "Essential character test for mixtures, composite goods, or sets",
                "evidence_considered": mats[:3] + list(getattr(product_intent, "components_or_parts", [])[:3]),
                "conclusion": "Essential character attribute needed if GIR 3(a) does not resolve competing headings.",
                "not_applied_reason": "",
                "explanation": "GIR 3(b) essential-character test considered for multi-material/component good.",
            })
        gir_steps.append({
            "rule": "GIR 3(c)",
            "applicable": False,
            "status": "DEFERRED",
            "legal_test_applied": "Last-in-numerical-order tie-breaker (fallback only after 3(a) and 3(b) fail)",
            "evidence_considered": [f"highest_numerical_heading={unique_h4[-1]}"],
            "conclusion": "Deferred to clarification/ambiguity rather than forcing numerical tie-break without legal exhaustion.",
            "not_applied_reason": "GIR 3(a)/3(b) must be exhausted with complete product attributes before GIR 3(c).",
            "explanation": f"GIR 3(c) not forced; competing headings {unique_h4[:4]} preserved for verification.",
        })
    else:
        gir_steps.append({
            "rule": "GIR 3",
            "applicable": False,
            "status": "NOT_APPLICABLE",
            "legal_test_applied": "None",
            "evidence_considered": [f"single_heading={unique_h4[0]}"],
            "conclusion": "Only one 4-digit heading is in contention.",
            "not_applied_reason": "Single heading candidate; GIR 3 applies only to multi-heading competition.",
            "explanation": f"GIR 3 not applicable: single heading {unique_h4[0]}.",
        })

    # GIR 4: Explicitly inactive (never approximated via vector similarity)
    gir_steps.append({
        "rule": "GIR 4",
        "applicable": False,
        "status": "INACTIVE",
        "legal_test_applied": "None (most-akin rule requires explicit statutory analogue table)",
        "evidence_considered": [],
        "conclusion": "Inactive; system abstains rather than approximating GIR 4 via semantic similarity.",
        "not_applied_reason": "No authoritative GIR 4 analogue schedule; vector similarity is not legal kinship.",
        "explanation": "GIR 4 inactive by policy.",
    })

    # GIR 5: Containers & packing materials only when applicable
    if pkg or _CONTAINER_PACKING_RE.search(full_q):
        gir_steps.append({
            "rule": "GIR 5",
            "applicable": True,
            "status": "CONSIDERED",
            "legal_test_applied": "GIR 5(a) specially shaped cases / GIR 5(b) normal packing materials",
            "evidence_considered": [pkg] if pkg else ["container/packing cue in description"],
            "conclusion": "Containers/packing do not override primary article unless specially shaped or separately presented.",
            "not_applied_reason": "",
            "explanation": "Evaluated GIR 5 container/packing-material rules.",
        })
    else:
        gir_steps.append({
            "rule": "GIR 5",
            "applicable": False,
            "status": "NOT_APPLICABLE",
            "legal_test_applied": "None",
            "evidence_considered": [],
            "conclusion": "No container or packing-material classification issue present.",
            "not_applied_reason": "No container or packaging cues detected in Stage 1.",
            "explanation": "GIR 5 not applicable.",
        })

    # GIR 6: Subheading & 8-digit tariff item comparison within the selected 4-digit heading
    same_h4_leaves = [c for c in qualifying_leaves if c.candidate.hsn_code[:4] == top_hsn[:4]]
    gir6_ok = len(same_h4_leaves) == 1 or bool(dist_analysis.get("winner_has_clear_evidence"))
    gir_steps.append({
        "rule": "GIR 6",
        "applicable": True,
        "status": "APPLIED" if gir6_ok else "AMBIGUOUS_SUBHEADINGS",
        "legal_test_applied": "Mutatis mutandis subheading comparison within the same 4-digit heading",
        "evidence_considered": [c.candidate.hsn_code for c in same_h4_leaves[:5]],
        "conclusion": (
            f"8-digit tariff item {top_hsn} verified under Heading {top_hsn[:4]}."
            if gir6_ok
            else f"{len(same_h4_leaves)} subheadings/leaves compete under Heading {top_hsn[:4]} without decisive distinction."
        ),
        "not_applied_reason": "",
        "explanation": (
            f"Compared {len(same_h4_leaves)} competing subheadings/leaves under Heading {top_hsn[:4]} "
            f"(winner_has_clear_evidence={bool(dist_analysis.get('winner_has_clear_evidence'))})."
        ),
    })

    return {
        "gir_reasoning": gir_steps,
        "supporting_notes": supporting_notes,
        "note_evaluation": note_eval_summary,
    }


def compare_competing_candidates(
    product_intent: Any,
    qualifying_leaves: Sequence[Any],
    evidence_by_hsn: Dict[str, Dict[str, Any]],
    raw_records_by_id: Dict[str, Dict[str, Any]],
    questions: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Layer 5: Compares top competing 8-digit candidates, extracts known Stage 1 attributes,
    and filters dynamic clarification questions so already-extracted attributes are not re-asked.
    """
    already_known: set[str] = set()
    if getattr(product_intent, "constituent_materials", None):
        already_known.add("material")
    if getattr(product_intent, "processing_form", None):
        already_known.update({"construction", "processing", "form"})
    if getattr(product_intent, "product_form", None):
        already_known.add("form")
    if getattr(product_intent, "function_use", None):
        already_known.add("function")

    competing_summary: List[Dict[str, Any]] = []
    for c in list(qualifying_leaves)[:5]:
        hsn = c.candidate.hsn_code
        ev = evidence_by_hsn.get(hsn, {})
        raw = raw_records_by_id.get(hsn, {})
        competing_summary.append({
            "hsn_code": hsn,
            "heading_4digit": hsn[:4],
            "tariff_item_desc": raw.get("tariff_item_desc") or getattr(c.candidate, "tariff_item_desc", ""),
            "evidence_status": ev.get("status"),
            "supporting": ev.get("statutory_article_matches") or ev.get("article_matches") or [],
            "missing_attributes": ev.get("missing_attributes") or [],
            "contradictions": ev.get("contradictions") or [],
        })

    filtered_questions: List[Dict[str, Any]] = []
    for q in questions:
        attr = str(q.get("attribute") or "").lower().strip()
        if attr in already_known:
            continue
        q_copy = dict(q)
        if not q_copy.get("why_needed") and len(competing_summary) >= 2:
            q_copy["why_needed"] = (
                f"Required to legally distinguish competing HSNs "
                f"{', '.join(item['hsn_code'] for item in competing_summary[:3])}."
            )
        filtered_questions.append(q_copy)

    return {
        "competing_candidates": competing_summary,
        "already_extracted_attributes": sorted(already_known),
        "filtered_questions": filtered_questions,
    }


def build_stage3_final_decision(
    *,
    original_description: str,
    prediction_mode: str,
    final_hsn: Optional[str],
    final_chapter: Optional[str],
    hsn_confidence: float,
    clarification_reason: str,
    product_intent: Any,
    qualifying_leaves: Sequence[Any],
    evidence_by_hsn: Dict[str, Dict[str, Any]],
    raw_records_by_id: Dict[str, Dict[str, Any]],
    dist_analysis: Dict[str, Any],
    questions: Sequence[Dict[str, Any]],
    contradicted_reasons: Sequence[str],
) -> Dict[str, Any]:
    """
    Layers 6 & 7: Maps internal decision state to the 4 canonical Stage 3 outcomes
    and builds the complete customer-facing statutory verification report.
    """
    if prediction_mode == "EXACT_HSN" and final_hsn:
        outcome = "EXACT_CLASSIFICATION"
    elif prediction_mode == "MULTIPLE_CANDIDATES":
        outcome = "MULTIPLE_CANDIDATES"
    elif prediction_mode in {"CHAPTER_ONLY_CLARIFY", "INSUFFICIENT_INFORMATION"} and questions:
        outcome = "CUSTOMER_CLARIFICATION_REQUIRED"
    elif prediction_mode == "OUT_OF_SCHEDULE":
        outcome = "ABSTAIN"
    else:
        outcome = "ABSTAIN"

    top_cand = qualifying_leaves[0] if qualifying_leaves else None
    focus_hsn = final_hsn or (top_cand.candidate.hsn_code if top_cand else None)
    focus_raw = raw_records_by_id.get(focus_hsn, {}) if focus_hsn else {}
    hierarchy = verify_statutory_hierarchy(focus_raw, top_cand.candidate if top_cand else None) if focus_hsn else {}
    gir_eval = evaluate_gir_sequence(
        product_intent, qualifying_leaves, evidence_by_hsn, raw_records_by_id, dist_analysis
    )

    # Guard: an 8-digit EXACT_CLASSIFICATION must pass hierarchy_valid
    if outcome == "EXACT_CLASSIFICATION" and not hierarchy.get("hierarchy_valid"):
        outcome = "ABSTAIN"

    focus_ev = evidence_by_hsn.get(focus_hsn, {}) if focus_hsn else {}
    gst_rate = lookup_verified_gst_rate(final_hsn) if outcome == "EXACT_CLASSIFICATION" else None
    comparison = compare_competing_candidates(
        product_intent, qualifying_leaves, evidence_by_hsn, raw_records_by_id, questions
    )

    return {
        "decision_outcome": outcome,
        "internal_prediction_mode": prediction_mode,
        "product_description": original_description,
        "final_hsn": final_hsn if outcome == "EXACT_CLASSIFICATION" else None,
        "final_chapter": final_chapter,
        "calibrated_confidence": round(float(hsn_confidence), 4),
        "decision_reason": clarification_reason or (
            f"Exact 8-digit HSN {final_hsn} verified under GIR 1 & GIR 6 with statutory support."
            if outcome == "EXACT_CLASSIFICATION"
            else "Statutory evidence insufficient for an exact 8-digit determination."
        ),
        "hierarchy_verification": hierarchy,
        "gir_reasoning": gir_eval["gir_reasoning"],
        "supporting_notes": gir_eval["supporting_notes"],
        "note_evaluation": gir_eval.get("note_evaluation", {}),
        "candidate_comparison": comparison["competing_candidates"],
        "supporting_evidence": {
            "article_matches": focus_ev.get("article_matches", []),
            "statutory_article_matches": focus_ev.get("statutory_article_matches", []),
            "material_matches": focus_ev.get("material_matches", []),
            "trace_summary": focus_ev.get("trace_summary", ""),
        },
        "contradictory_evidence": list(focus_ev.get("contradictions") or []) + list(contradicted_reasons[:5]),
        "unresolved_distinction": dist_analysis.get("distinguishing_phrases", {}),
        "clarification_questions": comparison["filtered_questions"] if outcome in {"CUSTOMER_CLARIFICATION_REQUIRED", "MULTIPLE_CANDIDATES"} else [],
        "verified_gst_rate": gst_rate,
    }
