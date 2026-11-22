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

from src.ml.hierarchy_intelligence import get_hierarchy_intelligence
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


_NON_MATERIAL_NOISE_RE = re.compile(
    r"\b(?:specialized|component|compressor|seating|controller|drive|system|equipment|other\s+than|technical\s+composition)\b|[():]",
    re.IGNORECASE,
)


def _extract_material_tokens(raw: str) -> Set[str]:
    if not raw:
        return set()
    out: Set[str] = set()
    for part in re.split(r"[,;|]+", raw):
        clean = part.strip().lower()
        if len(clean) < 2:
            continue
        if len(clean.split()) > 3 or _NON_MATERIAL_NOISE_RE.search(clean):
            continue
        out.add(clean)
    return out


_UNIT_NORMALIZATION: Dict[str, Tuple[str, float]] = {
    "w": ("power_w", 1.0),
    "watt": ("power_w", 1.0),
    "watts": ("power_w", 1.0),
    "kw": ("power_w", 1000.0),
    "mw": ("power_w", 1_000_000.0),
    "va": ("apparent_va", 1.0),
    "kva": ("apparent_va", 1000.0),
    "mva": ("apparent_va", 1_000_000.0),
    "mm": ("length_mm", 1.0),
    "cm": ("length_mm", 10.0),
    "m": ("length_mm", 1000.0),
    "cm2": ("area_cm2", 1.0),
    "sq.cm": ("area_cm2", 1.0),
    "sqcm": ("area_cm2", 1.0),
    "g": ("mass_g", 1.0),
    "gm": ("mass_g", 1.0),
    "gram": ("mass_g", 1.0),
    "grams": ("mass_g", 1.0),
    "kg": ("mass_g", 1000.0),
    "t": ("mass_g", 1_000_000.0),
    "tonne": ("mass_g", 1_000_000.0),
    "cc": ("vol_cc", 1.0),
    "cm3": ("vol_cc", 1.0),
    "ml": ("vol_cc", 1.0),
    "l": ("vol_cc", 1000.0),
    "litre": ("vol_cc", 1000.0),
    "litres": ("vol_cc", 1000.0),
    "%": ("percent", 1.0),
    "percent": ("percent", 1.0),
    "v": ("volt", 1.0),
    "kv": ("volt", 1000.0),
    "hz": ("freq_hz", 1.0),
    "khz": ("freq_hz", 1000.0),
    "rpm": ("rpm", 1.0),
}

_UNIT_REGEX = "|".join(sorted((re.escape(u) for u in _UNIT_NORMALIZATION), key=len, reverse=True))


@dataclass(frozen=True)
class NumericConstraint:
    op: str  # "<" | "<=" | ">" | ">="
    value: float
    unit_family: str
    raw_text: str


def _parse_num(num_str: str) -> float:
    return float(num_str.replace(",", "").strip())


def extract_numeric_constraints(text: str) -> List[NumericConstraint]:
    """
    Extracts domain-general numerical range/threshold constraints preserving
    comparison operators (<, <=, >, >=) and normalized units.
    """
    if not text:
        return []
    t = text.lower()
    constraints: List[NumericConstraint] = []
    consumed_spans: List[Tuple[int, int]] = []

    def _overlaps(s: int, e: int) -> bool:
        return any(not (e <= cs or s >= ce) for cs, ce in consumed_spans)

    # 1. Compound interval: "exceeding X [unit] but not exceeding Y unit"
    pat_between = re.compile(
        rf"(?:exceeding|more than|above)\s+(\d[\d,]*(?:\.\d+)?)\s*({_UNIT_REGEX})?\s+"
        rf"(?:but\s+)?(?:not\s+exceeding|up\s+to)\s+(\d[\d,]*(?:\.\d+)?)\s*({_UNIT_REGEX})\b"
    )
    for m in pat_between.finditer(t):
        u2_raw = m.group(4)
        u1_raw = m.group(2) or u2_raw
        fam1, mult1 = _UNIT_NORMALIZATION[u1_raw]
        fam2, mult2 = _UNIT_NORMALIZATION[u2_raw]
        constraints.append(NumericConstraint(">", _parse_num(m.group(1)) * mult1, fam1, m.group(0)))
        constraints.append(NumericConstraint("<=", _parse_num(m.group(3)) * mult2, fam2, m.group(0)))
        consumed_spans.append((m.start(), m.end()))

    # 2. Single-bound phrases
    single_patterns = [
        ("<=", rf"(?:not\s+exceeding|up\s+to|at\s+most|<=)\s*(\d[\d,]*(?:\.\d+)?)\s*({_UNIT_REGEX})\b"),
        (">=", rf"(?:not\s+less\s+than|at\s+least|>=)\s*(\d[\d,]*(?:\.\d+)?)\s*({_UNIT_REGEX})\b"),
        (">=", rf"(\d[\d,]*(?:\.\d+)?)\s*({_UNIT_REGEX})\s+or\s+more\b"),
        ("<=", rf"(\d[\d,]*(?:\.\d+)?)\s*({_UNIT_REGEX})\s+or\s+less\b"),
        (">", rf"(?:exceeding|more\s+than|above|greater\s+than|>)\s*(\d[\d,]*(?:\.\d+)?)\s*({_UNIT_REGEX})\b"),
        ("<", rf"(?:less\s+than|below|under|<)\s*(\d[\d,]*(?:\.\d+)?)\s*({_UNIT_REGEX})\b"),
    ]
    for op, raw_pat in single_patterns:
        for m in re.finditer(raw_pat, t):
            if _overlaps(m.start(), m.end()):
                continue
            fam, mult = _UNIT_NORMALIZATION[m.group(2)]
            constraints.append(NumericConstraint(op, _parse_num(m.group(1)) * mult, fam, m.group(0)))
            consumed_spans.append((m.start(), m.end()))

    return constraints


def extract_query_numeric_values(query: str) -> List[Tuple[float, str, str]]:
    """Extracts explicit (canonical_value, unit_family, raw_text) from the user query."""
    if not query:
        return []
    t = query.lower()
    out: List[Tuple[float, str, str]] = []
    pat = re.compile(rf"(\d[\d,]*(?:\.\d+)?)\s*({_UNIT_REGEX})\b")
    for m in pat.finditer(t):
        fam, mult = _UNIT_NORMALIZATION[m.group(2)]
        out.append((_parse_num(m.group(1)) * mult, fam, m.group(0)))
    return out


def _check_op(val: float, op: str, bound: float) -> bool:
    if op == "<":
        return val < bound
    if op == "<=":
        return val <= bound
    if op == ">":
        return val > bound
    if op == ">=":
        return val >= bound
    return False


def evaluate_numeric_match(
    constraints: Sequence[NumericConstraint],
    query_values: Sequence[Tuple[float, str, str]],
) -> str:
    """
    Compares candidate numerical constraints against explicit query values.
    Never treats missing numerical information as a confirmed match.
    Returns: 'NO_CONSTRAINT' | 'MISSING' | 'MATCH' | 'CONFLICT'
    """
    if not constraints:
        return "NO_CONSTRAINT"
    by_family: Dict[str, List[NumericConstraint]] = {}
    for c in constraints:
        by_family.setdefault(c.unit_family, []).append(c)

    q_by_family: Dict[str, List[float]] = {}
    for val, fam, _ in query_values:
        q_by_family.setdefault(fam, []).append(val)

    saw_match = False
    for fam, fam_constraints in by_family.items():
        q_vals = q_by_family.get(fam, [])
        if not q_vals:
            continue
        # At least one explicit query value in this unit family exists
        if any(all(_check_op(qv, c.op, c.value) for c in fam_constraints) for qv in q_vals):
            saw_match = True
        else:
            return "CONFLICT"

    return "MATCH" if saw_match else "MISSING"


_STAT_STOPWORDS = {
    "other", "others", "and", "or", "of", "the", "for", "in", "with",
    "than", "not", "thereof", "similar", "articles", "article", "parts",
    "accessories", "accessory", "whether", "exceeding", "included",
    "elsewhere", "specified", "nes", "type", "types", "kind", "based",
    "incorporating", "consisting", "equipment", "apparatus", "system",
    "systems", "device", "devices", "unit", "units", "machinery",
    "machine", "machines", "appliance", "appliances", "goods", "product",
    "products", "used", "using", "containing", "without", "mainly",
    "principally", "suitable", "designed", "form", "forms", "made",
}


def _stem_stat(tok: str) -> str:
    w = (tok or "").lower().strip()
    if len(w) <= 3:
        return w
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith("es") and len(w) > 4 and w[-3] in "shxz":
        return w[:-2]
    if w.endswith("s") and not w.endswith(("ss", "us", "is", "as")):
        return w[:-1]
    return w


def _stat_tokens(text: str) -> Set[str]:
    out: Set[str] = set()
    norm = (text or "").lower()
    norm = (
        norm.replace("stailess", "stainless")
        .replace("vaccum", "vacuum")
        .replace("digial", "digital")
        .replace("regenration", "regeneration")
        .replace("acetatc", "acetate")
    )
    for tok in re.findall(r"[a-z0-9]+", norm):
        if len(tok) < 3 or tok.isdigit():
            continue
        if tok in _STAT_STOPWORDS:
            continue
        st = _stem_stat(tok)
        if st not in _STAT_STOPWORDS:
            out.add(st)
    for hy in re.findall(r"\b[a-z0-9]+-[a-z0-9]+\b", norm):
        collapsed = _stem_stat(hy.replace("-", ""))
        if len(collapsed) >= 3 and collapsed not in _STAT_STOPWORDS:
            out.add(collapsed)
    return out


def analyze_sibling_distinctions(
    competing: Sequence[ClassifiedTariffCandidate],
    query: str,
    evidence_by_hsn: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Dynamically compares sibling tariff candidates using their statutory descriptions,
    subheading/tariff item fields, keywords, and numerical constraints against
    available query evidence (zero hardcoded product/chapter rules).
    """
    if not competing:
        return {
            "per_candidate": [],
            "winner_idx": None,
            "winner_has_clear_evidence": False,
            "evidence_margin": 0.0,
            "missing_numeric_constraints": False,
            "distinguishing_phrases": {},
        }

    q_low = (query or "").lower()
    q_tokens = _stat_tokens(q_low)
    q_nums = extract_query_numeric_values(q_low)

    # Identify common prefix tokens across competing candidates to focus on diffs
    cand_token_sets: List[Set[str]] = []
    cand_leaf_texts: List[str] = []
    for c in competing:
        leaf_txt = " ".join(
            p for p in (
                getattr(c.candidate, "tariff_item_desc", ""),
                getattr(c.candidate, "subheading_6digit_desc", ""),
                c.candidate.description,
            ) if p
        )
        cand_leaf_texts.append(leaf_txt)
        cand_token_sets.append(_stat_tokens(leaf_txt))

    common_tokens = set.intersection(*cand_token_sets) if len(cand_token_sets) >= 2 else set()
    hi = get_hierarchy_intelligence()

    per_cand: List[Dict[str, Any]] = []
    any_specific_support = False
    for idx, c in enumerate(competing):
        t8 = str(getattr(c.candidate, "tariff_item_desc", "") or "").strip()
        s6 = str(getattr(c.candidate, "subheading_6digit_desc", "") or "").strip()
        h4 = str(getattr(c.candidate, "heading_4digit_desc", "") or "").strip()
        h_analysis = hi.analyze_record({
            "hsn_code": c.candidate.hsn_code,
            "heading_4digit_desc": h4,
            "subheading_6digit_desc": s6,
            "tariff_item_desc": t8,
            "statutory_description": c.candidate.description,
        })
        is_residual = t8.lower() in ("other", "others") or h_analysis.qualifying_reason == "residual_other"
        # Numerical constraints from leaf/subheading description
        constraints = extract_numeric_constraints(f"{t8} {s6} {c.candidate.description}")
        num_status = evaluate_numeric_match(constraints, q_nums)

        diff_tokens = (cand_token_sets[idx] - common_tokens) | (h_analysis.sibling_distinguishing_tokens & cand_token_sets[idx])
        # Check statutory phrase overlap against query
        matched_diff = sorted(diff_tokens & q_tokens)
        lex_ratio = len(matched_diff) / max(len(diff_tokens), 1) if diff_tokens else 0.0

        # Direct tariff_item_desc phrase boost (e.g. "POLYCARBONATES", "PISTON RINGS");
        # recover leading truncated clause from statutory_description when tariff_item_desc
        # begins mid-parenthetical (e.g. "ALCOHOL), WHETHER OR NOT...").
        t8_eval = t8
        if t8 and (")" in t8 and ("(" not in t8 or t8.index(")") < t8.index("("))) and c.candidate.description:
            stat_tail = re.split(r"\s+-\s+", c.candidate.description)[-1]
            if stat_tail:
                t8_eval = stat_tail
        t8_tokens = _stat_tokens(t8_eval)
        t8_hit_ratio = len(t8_tokens & q_tokens) / max(len(t8_tokens), 1) if (t8_tokens and not is_residual) else 0.0
        has_unmatched_t8 = bool(t8_tokens - q_tokens) and (t8_hit_ratio == 0.0) and not is_residual

        if not is_residual and (num_status == "MATCH" or lex_ratio >= 0.25 or t8_hit_ratio >= 0.5):
            any_specific_support = True

        per_cand.append({
            "index": idx,
            "hsn_code": c.candidate.hsn_code,
            "is_residual_other": is_residual,
            "numeric_status": num_status,
            "has_numeric_constraints": bool(constraints),
            "matched_diff_tokens": matched_diff,
            "has_unmatched_diff": (bool(diff_tokens - q_tokens) and not matched_diff) or has_unmatched_t8,
            "has_unmatched_t8": has_unmatched_t8,
            "lex_ratio": round(lex_ratio, 4),
            "t8_hit_ratio": round(t8_hit_ratio, 4),
            "diff_phrase": t8 or s6 or c.candidate.description[:80],
        })

    # Compute combined evidence score per candidate (preserving logit margin, role_mismatch & SUPPORTED priority)
    for item, c in zip(per_cand, competing):
        cand_logit = float(getattr(c.candidate, "raw_logit", 0.0) or 0.0)
        score = float(c.confidence) * 0.5 + max(-2.0, min(8.0, cand_logit)) * 0.12
        ev_meta = (evidence_by_hsn or {}).get(c.candidate.hsn_code, {})
        ev_status = str(ev_meta.get("status") or "")
        role_mm = str(ev_meta.get("role_mismatch") or "")
        if ev_status == "SUPPORTED":
            score += 0.30
        if role_mm == "complete_article_vs_parts":
            score -= 1.50
        elif role_mm:
            score -= 0.40

        if item["numeric_status"] == "MATCH":
            score += 1.0
        elif item["numeric_status"] == "CONFLICT":
            score -= 2.0
        score += item["lex_ratio"] * 0.6 + item["t8_hit_ratio"] * 0.6
        if item["is_residual_other"] and any_specific_support:
            score -= 0.35
        item["evidence_score"] = round(score, 4)
        item["raw_logit"] = float(getattr(c.candidate, "raw_logit", 0.0) or 0.0)
        item["sub6"] = str(c.candidate.hsn_code or "")[:6]

    ranked = sorted(per_cand, key=lambda x: x["evidence_score"], reverse=True)
    best = ranked[0]
    second_score = ranked[1]["evidence_score"] if len(ranked) >= 2 else 0.0
    margin = round(best["evidence_score"] - second_score, 4)
    logit_margin = round(best["raw_logit"] - (ranked[1]["raw_logit"] if len(ranked) >= 2 else best["raw_logit"] - 5.0), 4)

    # Check if competing candidates in the SAME winning 6-digit subheading differ by missing numerical constraints
    # (never import numerical kVA/cc bounds from unrelated sibling subheadings like diesel gensets onto wind-powered sets).
    best_sub6 = best.get("sub6", "")
    best_h4 = str(best.get("hsn_code", ""))[:4]
    same_sub6_ranked = [x for x in ranked if x.get("sub6") == best_sub6] or ranked[:4]
    same_h4_ranked = [x for x in ranked if str(x.get("hsn_code", ""))[:4] == best_h4] or ranked[:4]
    missing_num = best["numeric_status"] != "MATCH" and (
        (
            best["numeric_status"] == "MISSING"
            and best["has_numeric_constraints"]
        )
        or (
            len(same_sub6_ranked) >= 2
            and any(x["numeric_status"] == "MISSING" and x["has_numeric_constraints"] for x in same_sub6_ranked[:4])
        )
    )

    # Winner has clear evidence only if not contradicted, not missing required numeric spec,
    # and statutory leaf evidence (numeric MATCH or direct non-residual tariff_item_desc match)
    # clearly distinguishes it from competing siblings.
    has_competing_non_residual = any(
        not x["is_residual_other"] for x in same_sub6_ranked[1:]
    )
    residual_blocked = best["is_residual_other"] and has_competing_non_residual
    statutory_leaf_clear = (
        best["numeric_status"] == "MATCH"
        or (not best["is_residual_other"] and best["t8_hit_ratio"] >= 0.5 and (margin >= 0.15 or logit_margin >= 1.5))
        or (len(same_h4_ranked) == 1 and not best["is_residual_other"] and best["t8_hit_ratio"] >= 0.5)
        or (len(ranked) == 1 and best["lex_ratio"] >= 0.35)
    )
    clear_ev = (
        best["numeric_status"] != "CONFLICT"
        and not missing_num
        and not residual_blocked
        and statutory_leaf_clear
    )
    superseded_hsns: Set[str] = set()
    if clear_ev and len(ranked) >= 2:
        for cand_x in ranked[1:]:
            is_weak_residual = cand_x["is_residual_other"] and cand_x.get("sub6") == best_sub6
            is_disjoint_sibling = (
                not cand_x["is_residual_other"]
                and (not cand_x["matched_diff_tokens"] or cand_x["has_unmatched_t8"])
                and cand_x["t8_hit_ratio"] == 0.0
                and cand_x["has_unmatched_diff"]
            )
            if is_weak_residual or is_disjoint_sibling:
                superseded_hsns.add(str(cand_x.get("hsn_code") or ""))

    return {
        "per_candidate": per_cand,
        "ranked_indices": [x["index"] for x in ranked],
        "winner_idx": best["index"],
        "winner_has_clear_evidence": clear_ev,
        "evidence_margin": margin,
        "missing_numeric_constraints": missing_num,
        "statutorily_superseded_hsns": superseded_hsns,
        "distinguishing_phrases": {
            x["hsn_code"]: x["diff_phrase"] for x in ranked[:4]
        },
    }


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

    # 1. Material check via material_keywords + master-derived statutory_materials across all 97 chapters
    hi = get_hierarchy_intelligence()
    unique_chaps = {c.candidate.chapter_code for c in competing if c.candidate.chapter_code}
    mat_sets: List[Set[str]] = []
    h_analyses = []
    for c in competing:
        ha = hi.analyze_record({
            "hsn_code": c.candidate.hsn_code,
            "heading_4digit_desc": getattr(c.candidate, "heading_4digit_desc", ""),
            "subheading_6digit_desc": getattr(c.candidate, "subheading_6digit_desc", ""),
            "tariff_item_desc": getattr(c.candidate, "tariff_item_desc", ""),
            "statutory_description": c.candidate.description,
        })
        h_analyses.append(ha)
        stat_mat_hits = _stat_tokens(
            f"{getattr(c.candidate, 'tariff_item_desc', '')} {getattr(c.candidate, 'subheading_6digit_desc', '')}"
        ) & hi.corpus_material_tokens
        mat_sets.append(_extract_material_tokens(c.candidate.material_keywords) | ha.statutory_materials | stat_mat_hits)

    non_empty_mats = [m for m in mat_sets if m]
    if len(non_empty_mats) >= 2:
        union_mats = set().union(*non_empty_mats)
        common_mats = set.intersection(*non_empty_mats)
        diff_mats = sorted(
            m for m in (union_mats - common_mats) if m not in query_lower
        )
        if diff_mats and (len(unique_chaps) > 1 or any(ha.statutory_materials for ha in h_analyses)):
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

    # 3. Dynamic numerical rating/capacity/dimension distinction
    if len(competing) >= 2:
        q_nums = extract_query_numeric_values(query_lower)
        num_phrases: List[str] = []
        has_missing_num = False
        for c in competing:
            cs = extract_numeric_constraints(
                f"{getattr(c.candidate, 'tariff_item_desc', '')} "
                f"{getattr(c.candidate, 'subheading_6digit_desc', '')} "
                f"{c.candidate.description}"
            )
            if cs:
                st = evaluate_numeric_match(cs, q_nums)
                if st == "MISSING":
                    has_missing_num = True
                for nc in cs:
                    if nc.raw_text not in num_phrases:
                        num_phrases.append(nc.raw_text)
        if has_missing_num and len(num_phrases) >= 1:
            separating.append("numeric_rating")
            evidence["numeric_rating"] = num_phrases[:6]

    # Fallback: use master-derived sibling distinguishing tokens before generic fallback
    if not separating and len(competing) >= 2:
        dist_toks = sorted(
            t for ha in h_analyses for t in ha.sibling_distinguishing_tokens
            if t not in query_lower and len(t) >= 3
        )
        if dist_toks:
            separating.append("specification")
            evidence["specification"] = list(dict.fromkeys(dist_toks))[:6]
        else:
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
