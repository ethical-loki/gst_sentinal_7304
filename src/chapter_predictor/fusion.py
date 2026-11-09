"""
src/chapter_predictor/fusion.py
===============================
Stage E: Reciprocal Rank Fusion (RRF) & Dynamic Abstention Engine.

Features:
- Merges lexical candidate rankings (Stage B) and semantic candidate rankings (Stage C)
  using Reciprocal Rank Fusion (k=60).
- Normalizes fusion confidence scores to [0.0, 1.0].
- Applies strict mathematical abstention rules (NEEDS_REVIEW) based on confidence thresholds
  and score margins, without any artificial string-shape / parenthesis constraints.
"""

import json
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
STATUTORY_RULES_FILE = ROOT_DIR / "data" / "statutory_rules.json"
_STATUTORY_RULES_CACHE: List[Dict[str, Any]] = []


def load_statutory_rules() -> List[Dict[str, Any]]:
    """Loads statutory legal principles and priority notes dynamically from data/statutory_rules.json."""
    global _STATUTORY_RULES_CACHE
    if _STATUTORY_RULES_CACHE:
        return _STATUTORY_RULES_CACHE
    if STATUTORY_RULES_FILE.exists():
        try:
            with open(STATUTORY_RULES_FILE, "r", encoding="utf-8") as f:
                _STATUTORY_RULES_CACHE = json.load(f)
                return _STATUTORY_RULES_CACHE
        except Exception as e:
            logger.warning(f"Could not load statutory_rules.json: {e}")
    return []

DEFAULT_CONFIDENCE_THRESHOLD = 0.50
DEFAULT_MARGIN_THRESHOLD = 0.035
RRF_K = 60

# Exactly 98 valid classifiable chapters (01–99, with 77 explicitly excluded as reserved)
VALID_CLASSIFIABLE_CHAPTERS = set(f"{i:02d}" for i in range(1, 100) if i != 77)

# Domestic India-specific chapters that require explicit regulatory tokens
DOMESTIC_CHAPTER_TRIGGERS = {
    "98": {"project", "projects", "import", "imports", "baggage", "passenger", "laboratory", "chemicals", "ship", "stores"},
    "99": {"service", "services", "sac", "consultancy", "transportation", "maintenance", "software", "licence", "license"}
}


def line_level_fusion(
    bm25_lines: List[Dict[str, Any]],
    semantic_lines: List[Dict[str, Any]],
    alpha: float = 0.55,
    top_k_chapters: int = 10,
    query_text: str = "",
    query_facts: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Task 7: Article-First Evidence Scoring & Line-Level Fusion.
    - Normalizes BM25 and dense scores to [0.0, 1.0].
    - Fuses each line: score = alpha * dense + (1 - alpha) * bm25.
    - Applies Article-First evidence weighting:
        * Lines matching detected article noun or form get strong evidence boost (1.25x).
        * Lines matching constituent material alone get reduced weight (0.45x).
    - Aggregates by Chapter using sum pooling over top lines.
    - Filters strictly to the 98 allowed chapters (excluding 77).
    """
    line_scores: Dict[str, Dict[str, Any]] = {}

    # Extract article/form/material from query_facts if available
    q_article = (query_facts.get("article") or "").lower().strip() if query_facts else ""
    q_form = (query_facts.get("form") or "").lower().strip() if query_facts else ""
    q_material = (query_facts.get("material") or "").lower().strip() if query_facts else ""

    # 1. Normalize and ingest BM25 lines
    if bm25_lines:
        max_bm25 = max((l.get("score", 0.0) for l in bm25_lines), default=1.0)
        min_bm25 = min((l.get("score", 0.0) for l in bm25_lines), default=0.0)
        bm25_range = max_bm25 - min_bm25 if (max_bm25 - min_bm25) > 1e-6 else 1.0
        for l in bm25_lines:
            raw_c = l.get("hsn_raw") or l.get("hsn_code", "")
            norm_b = max(0.0, (l.get("score", 0.0) - min_bm25) / bm25_range)
            line_scores[raw_c] = {
                "hsn_raw": raw_c,
                "hsn_code": l.get("hsn_code", raw_c),
                "description": l.get("description", ""),
                "chapter": l.get("chapter", raw_c[:2]),
                "chapter_title": l.get("chapter_title", ""),
                "bm25_norm": norm_b,
                "dense_norm": 0.0
            }

    # 2. Normalize and ingest Semantic Dense lines
    if semantic_lines:
        max_dense = max((l.get("score", 0.0) for l in semantic_lines), default=1.0)
        min_dense = min((l.get("score", 0.0) for l in semantic_lines), default=0.0)
        dense_range = max_dense - min_dense if (max_dense - min_dense) > 1e-6 else 1.0
        for l in semantic_lines:
            raw_c = l.get("hsn_raw") or l.get("hsn_code", "")
            norm_d = max(0.0, (l.get("score", 0.0) - min_dense) / dense_range)
            if raw_c not in line_scores:
                line_scores[raw_c] = {
                    "hsn_raw": raw_c,
                    "hsn_code": l.get("hsn_code", raw_c),
                    "description": l.get("description", ""),
                    "chapter": l.get("chapter", raw_c[:2]),
                    "chapter_title": l.get("chapter_title", ""),
                    "bm25_norm": 0.0,
                    "dense_norm": norm_d
                }
            else:
                line_scores[raw_c]["dense_norm"] = norm_d

    # 3. Compute weighted fused line score with Article-First weighting & group by chapter
    chapter_line_map: Dict[str, List[Dict[str, Any]]] = {}
    for raw_c, item in line_scores.items():
        base_fused = alpha * item["dense_norm"] + (1.0 - alpha) * item["bm25_norm"]
        desc_lower = item["description"].lower()

        # Task 7 Article-First weighting:
        # A line counts as strong evidence only when it matches article or form term.
        # Material-only matches get reduced weight.
        line_weight = 1.0
        if q_article or q_form:
            has_article = bool(q_article and (
                re.search(rf"\b{re.escape(q_article)}\b", desc_lower) or
                any(len(w) > 3 and w in desc_lower for w in q_article.lower().split())
            ))
            has_form = bool(q_form and re.search(rf"\b{re.escape(q_form)}\b", desc_lower))
            has_material = bool(q_material and re.search(rf"\b{re.escape(q_material)}\b", desc_lower))
            if has_article or has_form:
                line_weight = 1.30  # Strong evidence bonus
            elif has_material and not (has_article or has_form):
                line_weight = 0.45  # Material-only penalty
            else:
                line_weight = 0.85

        item["line_score"] = round(base_fused * line_weight, 6)
        ch = item["chapter"]
        # Drop chapter 77 and any invalid chapter
        if ch not in VALID_CLASSIFIABLE_CHAPTERS:
            continue
        if ch not in chapter_line_map:
            chapter_line_map[ch] = []
        chapter_line_map[ch].append(item)

    # 4. Aggregate to Chapter level (sum of top 4 lines per chapter)
    chapter_candidates: List[Dict[str, Any]] = []
    q_words = set(re.findall(r"\w+", (query_text or "").lower()))

    for ch, lines in chapter_line_map.items():
        # Sort lines by score descending
        sorted_lines = sorted(lines, key=lambda x: x["line_score"], reverse=True)
        # Sum top lines so one line alone cannot dominate
        top_slice = sorted_lines[:4]
        raw_chapter_score = sum(x["line_score"] for x in top_slice)
        
        # Phase 5: State decides the family (Raw vs Worked vs Finished Article)
        form_stage = (query_facts.get("form_stage") or "").lower() if query_facts else ""
        if form_stage == "finished_article":
            if ch == "72":  # Raw iron & steel excluded for finished articles
                raw_chapter_score *= 0.10
            elif ch in ("73", "82", "83", "84", "85", "87", "69", "94", "95", "96"):
                raw_chapter_score *= 1.40
        elif form_stage == "raw":
            if ch == "73":  # Finished articles excluded for raw forms
                raw_chapter_score *= 0.10
            elif ch in ("72", "26", "25", "74", "76", "44", "41"):
                raw_chapter_score *= 1.40
        elif form_stage in ("semi-finished", "worked"):
            if ch == "73":
                raw_chapter_score *= 0.20  # Finished articles excluded for semi-finished / worked forms
            elif ch == "72":
                raw_chapter_score *= 1.40

        # Boost chapter if directly supported by statutory article/form vocabulary
        vocab_chs = set(query_facts.get("vocabulary_candidate_chapters", [])) if query_facts else set()
        if vocab_chs and ch in vocab_chs:
            raw_chapter_score *= 1.80
        elif vocab_chs and ch not in vocab_chs:
            raw_chapter_score *= 0.35  # Penalty: chapter not in head noun candidate chapters

        # Apply domestic chapter penalty for 98/99 unless triggered
        if ch in DOMESTIC_CHAPTER_TRIGGERS:
            triggers = DOMESTIC_CHAPTER_TRIGGERS[ch]
            if not (q_words & triggers):
                raw_chapter_score *= 0.35  # Penalty: require explicit evidence

        top_evidence = [
            {
                "hsn_raw": x["hsn_raw"],
                "hsn_code": x["hsn_code"],
                "description": x["description"],
                "score": round(x["line_score"], 4)
            }
            for x in sorted_lines[:3]
        ]

        title = sorted_lines[0].get("chapter_title", "")
        chapter_candidates.append({
            "chapter": ch,
            "chapter_title": title,
            "aggregated_score": raw_chapter_score,
            "evidence_lines": top_evidence
        })

    if not chapter_candidates:
        return []

    # Sort chapters by aggregated score descending
    chapter_candidates.sort(key=lambda x: x["aggregated_score"], reverse=True)
    
    # Compute confidence and competitive margin
    total_score = sum(c["aggregated_score"] for c in chapter_candidates) or 1.0
    for idx, cand in enumerate(chapter_candidates):
        share = cand["aggregated_score"] / total_score
        runner_up_score = chapter_candidates[idx + 1]["aggregated_score"] if idx + 1 < len(chapter_candidates) else 0.0
        margin = (cand["aggregated_score"] - runner_up_score) / total_score
        cand["confidence"] = round(min(1.0, max(0.1, 0.5 * share + 0.5 * min(1.0, margin / 0.10))), 4)
        cand["margin"] = round(margin, 4)

    return chapter_candidates[:top_k_chapters]


def reciprocal_rank_fusion(
    bm25_chapters: List[Dict[str, Any]],
    semantic_chapters: List[Dict[str, Any]],
    top_k: int = 10,
    k_constant: int = RRF_K,
    query_text: str = "",
    query_facts: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Computes Reciprocal Rank Fusion (RRF) over candidate chapter rankings:
      RRF_Score(ch) = sum(1.0 / (k_constant + rank_i))
    Applies statutory General Interpretative Rules (GIR) dynamically from data/statutory_rules.json.
    """
    fused_scores: Dict[str, float] = {}
    chapter_metadata: Dict[str, Dict[str, Any]] = {}
    evidence_map: Dict[str, List[Dict[str, Any]]] = {}

    # 1. Ingest Stage B (BM25) ranks
    for rank, item in enumerate(bm25_chapters):
        ch = item["chapter"]
        rrf_inc = 1.0 / (k_constant + rank + 1)
        fused_scores[ch] = fused_scores.get(ch, 0.0) + rrf_inc
        if ch not in chapter_metadata:
            chapter_metadata[ch] = {
                "chapter": ch,
                "chapter_title": item.get("chapter_title", ""),
                "bm25_score": item.get("max_score", 0.0),
                "bm25_rank": rank + 1,
                "semantic_score": 0.0,
                "semantic_rank": None
            }
        else:
            chapter_metadata[ch]["bm25_score"] = item.get("max_score", 0.0)
            chapter_metadata[ch]["bm25_rank"] = rank + 1

        for line in item.get("evidence_lines", []):
            if ch not in evidence_map:
                evidence_map[ch] = []
            if not any(x["hsn_raw"] == line["hsn_raw"] for x in evidence_map[ch]):
                evidence_map[ch].append(line)

    # 2. Ingest Stage C (Semantic embeddings) ranks
    for rank, item in enumerate(semantic_chapters):
        ch = item["chapter"]
        rrf_inc = 1.0 / (k_constant + rank + 1)
        fused_scores[ch] = fused_scores.get(ch, 0.0) + rrf_inc
        if ch not in chapter_metadata:
            chapter_metadata[ch] = {
                "chapter": ch,
                "chapter_title": item.get("chapter_title", ""),
                "bm25_score": 0.0,
                "bm25_rank": None,
                "semantic_score": item.get("max_score", 0.0),
                "semantic_rank": rank + 1
            }
        else:
            chapter_metadata[ch]["semantic_score"] = item.get("max_score", 0.0)
            chapter_metadata[ch]["semantic_rank"] = rank + 1

        for line in item.get("evidence_lines", []):
            if ch not in evidence_map:
                evidence_map[ch] = []
            if not any(x["hsn_raw"] == line["hsn_raw"] for x in evidence_map[ch]):
                evidence_map[ch].append(line)

    if not fused_scores:
        return []

    # 3. Apply Statutory GIR Priority Disambiguation dynamically from data/statutory_rules.json
    rules = load_statutory_rules()
    q_lower = (query_text or "").lower()
    detected_fam = query_facts.get("family") if query_facts else ""
    detected_form = (query_facts.get("form") or "").lower() if query_facts else ""
    vocab_candidate_chapters = set(query_facts.get("vocabulary_candidate_chapters", [])) if query_facts else set()

    for rule in rules:
        target_ch = rule.get("target_chapter")
        if target_ch in fused_scores:
            trig_fams = set(rule.get("trigger_families", []))
            cond_forms = set(rule.get("condition_form", []))
            fam_match = bool(detected_fam and detected_fam in trig_fams) or (target_ch in vocab_candidate_chapters)
            if fam_match:
                if cond_forms:
                    if detected_form in cond_forms or any(re.search(rf"\b{re.escape(cf)}\b", q_lower) for cf in cond_forms):
                        fused_scores[target_ch] += rule.get("boost", 0.016)
                else:
                    fused_scores[target_ch] += rule.get("boost", 0.016)

    # Sort by RRF score descending
    sorted_chs = sorted(fused_scores.keys(), key=lambda c: fused_scores[c], reverse=True)
    theoretical_max = 2.0 / (k_constant + 1)

    fused_results = []
    for ch in sorted_chs[:top_k]:
        raw_rrf = fused_scores[ch]
        calibrated_conf = min(1.0, max(0.0, (raw_rrf / theoretical_max) * 0.95))
        
        meta = chapter_metadata[ch]
        ev_lines = sorted(evidence_map.get(ch, []), key=lambda x: x.get("score", 0.0), reverse=True)[:5]
        
        fused_results.append({
            "chapter": ch,
            "chapter_title": meta["chapter_title"],
            "rrf_score": round(raw_rrf, 6),
            "confidence": round(calibrated_conf, 4),
            "bm25_rank": meta["bm25_rank"],
            "semantic_rank": meta["semantic_rank"],
            "bm25_score": meta["bm25_score"],
            "semantic_score": meta["semantic_score"],
            "evidence_lines": ev_lines
        })

    return fused_results


def evaluate_abstention(
    candidates: List[Dict[str, Any]],
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    margin_threshold: float = DEFAULT_MARGIN_THRESHOLD,
    lexical_winner: Optional[str] = None,
    dense_winner: Optional[str] = None,
    article_signal_chapters: Optional[List[str]] = None
) -> Tuple[str, str]:
    """
    Task 8 Agreement Gate & Strict 98-Chapter Abstention Engine.
    Evaluates whether the candidate ranking passes confidence, margin, and agreement thresholds.
    Returns: (status: 'PREDICTED' | 'NEEDS_REVIEW', reason: str)
    
    Agreement Gate Rules:
    - Return OK only when lexical winner, dense winner, and article signal reach agreement consensus.
    - If lexical and dense winners disagree AND neither matches the article signal, triggers ABSTAIN.
    - Ambiguity is strictly determined by score margin, calibrated confidence, and consensus.
    """
    if not candidates:
        return "NEEDS_REVIEW", "No matching tariff chapters found in statutory catalog."

    top = candidates[0]
    top_ch = top.get("chapter")
    
    # Check against closed 98-chapter set
    if top_ch not in VALID_CLASSIFIABLE_CHAPTERS:
        return (
            "NEEDS_REVIEW",
            f"Chapter {top_ch} is reserved or outside the official 98 classifiable chapters. Routed to review."
        )

    top_score = top.get("confidence", 0.0)

    # 1. Absolute confidence check
    if top_score < confidence_threshold:
        return (
            "NEEDS_REVIEW",
            f"Top candidate Chapter {top_ch} confidence ({top_score:.2f}) is below statutory threshold ({confidence_threshold:.2f})."
        )

    # 2. Competitive margin check
    if len(candidates) >= 2:
        second = candidates[1]
        second_score = second.get("confidence", 0.0)
        margin = top_score - second_score
        if margin < margin_threshold:
            return (
                "NEEDS_REVIEW",
                f"Close margin ({margin:.3f} < {margin_threshold}) between Chapter {top_ch} and Chapter {second.get('chapter')}."
            )

    # 3. Phase 5 Agreement Gate: Top candidate chapter must be supported by statutory article signal
    article_signals = set(article_signal_chapters or [])
    if article_signals and top_ch not in article_signals:
        return (
            "NEEDS_REVIEW",
            f"Top candidate Chapter {top_ch} conflicts with statutory candidate chapters for head noun ({sorted(list(article_signals))[:3]}). Routed to review."
        )

    # 4. Lexical vs Dense consensus check
    if lexical_winner and dense_winner:
        if lexical_winner != dense_winner:
            if article_signals:
                # If neither the lexical nor dense winner is supported by the article signal, abstain
                if lexical_winner not in article_signals and dense_winner not in article_signals:
                    return (
                        "NEEDS_REVIEW",
                        f"Signal divergence: Lexical winner (Ch {lexical_winner}) and Dense winner (Ch {dense_winner}) "
                        f"disagree with article signal ({sorted(list(article_signals))[:3]}). Routed to review."
                    )
            elif top_score < 0.65:
                # Without article signal support, disagreement between dense & lexical triggers review
                return (
                    "NEEDS_REVIEW",
                    f"Consensus gap: Lexical retrieval favors Ch {lexical_winner} while Dense retrieval favors Ch {dense_winner}."
                )

    return "PREDICTED", f"Decisive classification in Chapter {top_ch} ({top.get('chapter_title', '')}) under GIR 1."

