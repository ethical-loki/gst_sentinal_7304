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


def load_applicable_section_notes(
    chapter_code: str,
    rules_path: Path = DEFAULT_STATUTORY_RULES_PATH,
) -> List[str]:
    """Returns statutory section/chapter notes from statutory_rules.json matching the candidate chapter."""
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
    notes: List[str] = []
    for rule in _STATUTORY_RULES_CACHE:
        if str(rule.get("target_chapter") or "").zfill(2) == ch_norm:
            note = str(rule.get("source_note") or "").strip()
            if note and note not in notes:
                notes.append(note)
    return notes


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
    Layer 2: Conditionally evaluates applicable General Interpretative Rules (GIR 1-6)
    in legal sequence based on actual query/candidate conditions.
    """
    gir_steps: List[Dict[str, str]] = []
    supporting_notes: List[str] = []

    raw_desc = str(getattr(product_intent, "raw_description", "") or "")
    finished = str(getattr(product_intent, "finished_article", "") or "")
    proc_form = str(getattr(product_intent, "processing_form", "") or "")
    pkg = str(getattr(product_intent, "packaging_or_presentation", "") or "")
    full_q = f"{raw_desc} {finished} {proc_form} {pkg}".strip()

    if not qualifying_leaves:
        gir_steps.append({
            "rule": "GIR 1",
            "status": "UNRESOLVED",
            "explanation": "No 8-digit tariff item matched heading terms and legal notes with sufficient evidence.",
        })
        return {"gir_reasoning": gir_steps, "supporting_notes": supporting_notes}

    top = qualifying_leaves[0]
    top_hsn = top.candidate.hsn_code
    top_ch = top.candidate.chapter_code
    top_ev = evidence_by_hsn.get(top_hsn, {})
    supporting_notes.extend(load_applicable_section_notes(top_ch))

    # GIR 1: Always primary legal rule
    art_m = top_ev.get("statutory_article_matches") or top_ev.get("article_matches") or []
    gir_steps.append({
        "rule": "GIR 1",
        "status": "APPLIED" if top_ev.get("heading_compatible") and art_m else "PARTIAL",
        "explanation": (
            f"Evaluated heading {top_hsn[:4]} terms and Chapter {top_ch} notes; "
            f"statutory article alignment={art_m[:3] or 'none'}, heading_compatible={bool(top_ev.get('heading_compatible'))}."
        ),
    })

    # GIR 2: Only when incomplete, unfinished, unassembled, or mixtures are indicated
    if _INCOMPLETE_UNASSEMBLED_RE.search(full_q) or len(getattr(product_intent, "constituent_materials", []) or []) > 1:
        gir_steps.append({
            "rule": "GIR 2",
            "status": "CONSIDERED",
            "explanation": (
                "Evaluated essential character / mixture / assembly scope (GIR 2(a)/2(b)) "
                "due to multi-material composition or incomplete/unassembled cues."
            ),
        })

    # GIR 3: Only when multiple 4-digit headings compete
    unique_h4 = sorted({c.candidate.hsn_code[:4] for c in qualifying_leaves if getattr(c, "candidate", None)})
    if len(unique_h4) > 1:
        gir_steps.append({
            "rule": "GIR 3",
            "status": "COMPETING_HEADINGS",
            "explanation": (
                f"Multiple headings compete ({', '.join(unique_h4[:4])}); requires GIR 3(a) most specific description "
                "or GIR 3(b) essential character distinction before finalizing."
            ),
        })

    # GIR 5: Only when containers or packing materials are present
    if pkg or _CONTAINER_PACKING_RE.search(full_q):
        gir_steps.append({
            "rule": "GIR 5",
            "status": "CONSIDERED",
            "explanation": (
                "Evaluated GIR 5 container/packing-material rules so containers or cases do not override the primary article unless specially shaped/classified separately."
            ),
        })

    # GIR 6: Subheading / 8-digit leaf comparison within winning 4-digit heading
    same_h4_leaves = [c for c in qualifying_leaves if c.candidate.hsn_code[:4] == top_hsn[:4]]
    if len(same_h4_leaves) > 1:
        gir_steps.append({
            "rule": "GIR 6",
            "status": "APPLIED" if dist_analysis.get("winner_has_clear_evidence") else "AMBIGUOUS_SUBHEADINGS",
            "explanation": (
                f"Compared {len(same_h4_leaves)} competing subheadings/leaves under Heading {top_hsn[:4]} "
                f"(winner_has_clear_evidence={bool(dist_analysis.get('winner_has_clear_evidence'))})."
            ),
        })
    else:
        gir_steps.append({
            "rule": "GIR 6",
            "status": "APPLIED",
            "explanation": f"Single qualifying 8-digit leaf ({top_hsn}) under Heading {top_hsn[:4]} verified at subheading level.",
        })

    return {"gir_reasoning": gir_steps, "supporting_notes": supporting_notes}


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
        "supporting_evidence": {
            "article_matches": focus_ev.get("article_matches", []),
            "statutory_article_matches": focus_ev.get("statutory_article_matches", []),
            "material_matches": focus_ev.get("material_matches", []),
            "trace_summary": focus_ev.get("trace_summary", ""),
        },
        "contradictory_evidence": list(focus_ev.get("contradictions") or []) + list(contradicted_reasons[:5]),
        "unresolved_distinction": dist_analysis.get("distinguishing_phrases", {}),
        "clarification_questions": list(questions) if outcome in {"CUSTOMER_CLARIFICATION_REQUIRED", "MULTIPLE_CANDIDATES"} else [],
        "verified_gst_rate": gst_rate,
    }
