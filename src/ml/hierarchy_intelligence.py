"""
src/ml/hierarchy_intelligence.py
================================
Phase 2: Master-Derived Dynamic Hierarchy Intelligence.

Dynamically analyzes parent -> subheading -> tariff-item relationships and
sibling trees directly from the enriched statutory master (`data/enriched_master_hsn.parquet`)
without relying exclusively on manual qualifier/material word lists and without
blindly inheriting full parent descriptions.

Derives for any tariff record:
1. Article identity inherited from positive (non-excluded) parent headings.
2. Attributes introduced at subheading and leaf levels.
3. Shared vocabulary among sibling tariff items under the same heading/subheading.
4. Distinguishing vocabulary between sibling tariff items.
5. Explicit statutory exclusions (`excluding ...`, `other than ...`, `except ...`)
   and contradictory sibling-exclusive article identities.
6. Qualifying-only leaf detection (residual `OTHER`, syntactic prepositional/numeric
   modifiers, and corpus-derived cross-chapter qualifying terms).
"""

from __future__ import annotations

from functools import lru_cache
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_ENRICHED_PARQUET = ROOT_DIR / "data" / "enriched_master_hsn.parquet"

_HIERARCHY_STOPWORDS: Set[str] = {
    "a", "an", "and", "or", "of", "the", "for", "with", "without", "in", "on", "to",
    "from", "by", "as", "at", "into", "onto", "per", "not", "no", "nor", "but", "if",
    "than", "that", "this", "those", "these", "their", "its", "such", "same", "more",
    "less", "whether", "having", "containing", "including", "excluding", "except",
    "other", "others", "elsewhere", "specified", "included", "nes", "thereof", "therefor",
    "similar", "kind", "used", "use", "like", "articles", "goods", "items", "products",
    "heading", "headings", "subheading", "chapter", "note", "notes", "section", "all",
    "any", "each", "exceeding", "above", "below", "under", "between", "within", "both",
    "either", "neither", "wholly", "mainly", "principally", "primarily", "designed",
    "suitable", "put", "up", "retail", "sale", "form", "forms", "based", "type", "types",
    "weight", "calculated", "basis", "total", "one", "two", "three", "four", "five",
    "purpose", "purposes", "ratio", "proportion",
}

_SYNTACTIC_QUALIFIER_PREFIX_RE = re.compile(
    r"^\s*(?:"
    r"of|for|with|without|having|containing|consisting\s+of|in|by|on|at|from|"
    r"exceeding|not\s+exceeding|up\s+to|more\s+than|less\s+than|above|below|under|"
    r"other\s+than|whether|suitable\s+for|designed\s+for|principally|primarily|"
    r"specially\s+designed|put\s+up|mounted\s+on|worked|unworked|fitted\s+with|"
    r"less\s+than|greater\s+than|not\s+less\s+than|at\s+least|"
    r"[<>]=?\s*\d|\d[\d.,]*\s*(?:%|percent|kg|g|gm|mm|cm|m|l|ml|cc|v|kv|w|kw|mw|va|kva|hz|rpm|hp)"
    r")\b",
    re.IGNORECASE,
)

# Short structural grammar seeds only; domain qualifiers are learned from the master corpus.
_STRUCTURAL_GRAMMAR_SEEDS: Set[str] = {
    "other", "others", "type", "types", "grade", "grades", "capacity", "size", "sizes",
    "weight", "weights", "bulk", "packing", "packings", "retail", "domestic", "household",
    "industrial", "commercial", "agricultural", "automatic", "manual", "portable",
    "electric", "electrical", "electronic", "mechanical", "hydraulic", "pneumatic",
    "parts", "part", "accessories", "accessory", "components", "component",
    "complete", "incomplete", "unassembled", "assembled", "mounted", "unmounted",
    "single", "multiple", "double", "plain", "rigid", "flexible", "hollow", "solid",
}

_EXCLUSION_CLAUSE_RE = re.compile(
    r"\b(?:excluding|other\s+than|except|not\s+including|does\s+not\s+include|not\s+elsewhere\s+specified)\b"
    r"(?:(?!\s+-\s+|\s+--\s+|;|:|\.).)*?(?=\s+-\s+|\s+--\s+|;|:|\.|\)|$)",
    re.IGNORECASE,
)

_MATERIAL_PREP_RE = re.compile(
    r"\b(?:of|made\s+of|outer\s+soles\s+of|uppers\s+of|composed\s+of)\s+"
    r"([a-z][a-z\s,-]{2,32}?)(?=\s*(?:,|;|:|\)|or\b|and\b|with\b|not\b|whether\b|for\b|in\b|to\b|of\b|$))",
    re.IGNORECASE,
)


@lru_cache(maxsize=8192)
def _stem_token(tok: str) -> str:
    w = (tok or "").lower().strip()
    if len(w) <= 3:
        return w
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith("ves") and len(w) > 4:
        return w[:-3] + "f"
    if w.endswith("ses") and len(w) > 4:
        return w[:-2]
    if w.endswith("s") and not w.endswith(("ss", "us", "is", "as")):
        return w[:-1]
    return w


def _tokenize(text: str, *, stemmed: bool = True) -> List[str]:
    if not text:
        return []
    raw = re.findall(r"[a-zA-Z][a-zA-Z0-9-]{1,}", text.lower())
    out: List[str] = []
    for tok in raw:
        for part in tok.split("-"):
            if len(part) < 2 or part.isdigit():
                continue
            st = _stem_token(part) if stemmed else part
            if part in _HIERARCHY_STOPWORDS or st in _HIERARCHY_STOPWORDS:
                continue
            out.append(st)
    return out


def extract_statutory_exclusions(text: str) -> Tuple[str, List[str], Set[str], Set[str]]:
    """
    Separates positive statutory text from explicit exclusion clauses such as:
    - `(EXCLUDING FURNACES, OVENS AND OTHER EQUIPMENT OF HEADING 8514)`
    - `(OTHER THAN THOSE OF HEADING 8702)`
    - `EXCLUDING LIVERS AND ROES`

    Returns:
        positive_text: input with exclusion spans removed
        excluded_clauses: raw matched exclusion strings
        excluded_tokens: stemmed content tokens appearing inside exclusions
        excluded_headings: 4/6-digit headings explicitly excluded
    """
    if not text:
        return "", [], set(), set()

    excluded_clauses: List[str] = []
    excluded_tokens: Set[str] = set()
    excluded_headings: Set[str] = set()
    spans_to_remove: List[Tuple[int, int]] = []

    # Check parenthetical exclusions first so balanced parentheses stay contained
    for pm in re.finditer(r"\(([^()]{4,220})\)", text):
        inner = pm.group(1).strip()
        if re.match(r"^(?:excluding|other\s+than|except|not\s+including)\b", inner, re.IGNORECASE):
            excluded_clauses.append(inner)
            spans_to_remove.append((pm.start(), pm.end()))

    # Build intermediate text without parenthetical exclusions before checking inline clauses
    masked_chars = list(text)
    for s, e in spans_to_remove:
        for i in range(s, e):
            masked_chars[i] = " "
    masked = "".join(masked_chars)

    for m in _EXCLUSION_CLAUSE_RE.finditer(masked):
        full_m = m.group(0).strip()
        # Skip boilerplate WCO phrase "not elsewhere specified or included"
        if re.match(r"^not\s+elsewhere\s+specified", full_m, re.IGNORECASE):
            continue
        # Bound exclusion span right after "of heading XXXX" so sibling lists after "-" don't leak in
        hm = re.search(r"\bheading\s+\d{4}(?:\s+(?:to|or)\s+\d{4})*", full_m, re.IGNORECASE)
        if hm:
            end_pos = m.start() + hm.end()
            excluded_clauses.append(full_m[:hm.end()].strip())
            spans_to_remove.append((m.start(), end_pos))
        else:
            excluded_clauses.append(full_m)
            spans_to_remove.append((m.start(), m.end()))

    for clause in excluded_clauses:
        for h in re.findall(r"\b(\d{4}(?:\.\d{2})?)\b", clause):
            excluded_headings.add(h.replace(".", ""))
        # Remove cross-reference filler words before tokenizing excluded items
        cleaned_clause = re.sub(
            r"\b(?:goods|articles|equipment|apparatus|products|machinery|those|ones|items|of|heading|headings|chapter)\b",
            " ",
            clause,
            flags=re.IGNORECASE,
        )
        excluded_tokens.update(_tokenize(cleaned_clause))

    final_chars = list(text)
    for s, e in spans_to_remove:
        for i in range(s, min(e, len(final_chars))):
            final_chars[i] = " "
    positive_text = re.sub(r"\s+", " ", "".join(final_chars)).strip(" -:;,")
    return positive_text, excluded_clauses, excluded_tokens, excluded_headings


def _is_participial_state_modifier(tok: str) -> bool:
    """Generic English participial/adjectival morphology for state modifiers (not commodity nouns)."""
    return bool(
        re.match(r"^[a-z]{4,}(?:ed|ated|ised|ized|packed|grade)$", tok or "")
    )


def _extract_pre_clause_head_tokens(text: str, drop_participles: bool = False) -> Set[str]:
    """
    Extracts concrete head noun tokens appearing BEFORE secondary modifier clauses
    (`WITH`, `WHETHER`, `FOR`, `OF`, `EXCLUDING`, `OTHER THAN`) in subheading/leaf text.
    """
    pos_text, _, _, _ = extract_statutory_exclusions(text)
    if not pos_text:
        return set()
    primary = re.split(
        r"\b(?:whether\s+or\s+not|with\s+or\s+without|fitted\s+with|having|containing|suitable\s+for|designed\s+for|not\s+exceeding|exceeding)\b",
        pos_text,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    toks = set(_tokenize(primary))
    if drop_participles:
        toks = {t for t in toks if not _is_participial_state_modifier(t)}
    return toks


@dataclass
class TariffHierarchyAnalysis:
    hsn_code: str
    inherited_parent_articles: Set[str] = field(default_factory=set)
    leaf_added_attributes: Dict[str, Any] = field(default_factory=dict)
    sibling_shared_tokens: Set[str] = field(default_factory=set)
    sibling_distinguishing_tokens: Set[str] = field(default_factory=set)
    explicit_exclusions: Set[str] = field(default_factory=set)
    excluded_headings: Set[str] = field(default_factory=set)
    contradictory_sibling_articles: Set[str] = field(default_factory=set)
    is_qualifying_only_leaf: bool = False
    qualifying_reason: str = "distinct_article_introduced"
    statutory_materials: Set[str] = field(default_factory=set)


class MasterHierarchyIntelligence:
    """
    Master-derived hierarchy and sibling distinction analyzer built directly from
    `data/enriched_master_hsn.parquet` (or an arbitrary DataFrame in tests).
    """

    def __init__(self, df: Optional[pd.DataFrame] = None, parquet_path: Path = DEFAULT_ENRICHED_PARQUET):
        if df is not None:
            self.df = df.copy()
        elif parquet_path.exists():
            cols = [
                "hsn_code", "code_length", "chapter_code", "heading_4digit",
                "heading_4digit_desc", "subheading_6digit", "subheading_6digit_desc",
                "tariff_item_desc", "statutory_description", "material_keywords", "is_residual",
            ]
            avail = pd.read_parquet(parquet_path)
            keep = [c for c in cols if c in avail.columns]
            self.df = avail[keep].copy()
        else:
            self.df = pd.DataFrame()

        self.corpus_qualifier_tokens: Set[str] = set(_STRUCTURAL_GRAMMAR_SEEDS)
        self.corpus_material_tokens: Set[str] = set()
        self._heading_groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._heading_parent_desc: Dict[str, str] = {}
        self._sub6_desc: Dict[str, str] = {}
        self._h4_shared_tokens: Dict[str, Set[str]] = {}
        self._h4_sibling_branch_articles: Dict[str, Dict[str, Set[str]]] = {}
        self._record_by_hsn: Dict[str, Dict[str, Any]] = {}
        self._analysis_cache: Dict[str, TariffHierarchyAnalysis] = {}

        if not self.df.empty:
            self._build_from_master()

    def _build_from_master(self) -> None:
        prep_chaps: Dict[str, Set[str]] = defaultdict(set)
        all_chaps: Dict[str, Set[str]] = defaultdict(set)
        mat_chaps: Dict[str, Set[str]] = defaultdict(set)

        for row in self.df.to_dict(orient="records"):
            hsn = str(row.get("hsn_code") or "").strip()
            if not hsn:
                continue
            ch = str(row.get("chapter_code") or hsn[:2]).strip().zfill(2)
            code_len = int(row.get("code_length") or len(hsn))
            h4 = str(row.get("heading_4digit") or hsn[:4]).strip()
            h6 = str(row.get("subheading_6digit") or (hsn[:6] if code_len >= 6 else h4)).strip()
            t8_desc = str(row.get("tariff_item_desc") or "").strip()
            s6_desc = str(row.get("subheading_6digit_desc") or "").strip()
            h4_desc = str(row.get("heading_4digit_desc") or "").strip()
            stat_desc = str(row.get("statutory_description") or "").strip()
            mat_kw = str(row.get("material_keywords") or "").strip()

            rec = {
                "hsn_code": hsn,
                "code_length": code_len,
                "chapter_code": ch,
                "heading_4digit": h4,
                "subheading_6digit": h6,
                "heading_4digit_desc": h4_desc,
                "subheading_6digit_desc": s6_desc,
                "tariff_item_desc": t8_desc,
                "statutory_description": stat_desc,
                "material_keywords": mat_kw,
                "is_residual": bool(row.get("is_residual", False)),
            }
            self._record_by_hsn[hsn] = rec
            if code_len == 4 and stat_desc:
                self._heading_parent_desc[h4] = h4_desc or stat_desc
            elif h4 and h4 not in self._heading_parent_desc and h4_desc:
                self._heading_parent_desc[h4] = h4_desc
            if code_len == 6 and (t8_desc or s6_desc):
                self._sub6_desc[h6] = s6_desc or t8_desc
            elif code_len == 8 and h6 and h6 not in self._sub6_desc and s6_desc:
                self._sub6_desc[h6] = s6_desc
            if code_len >= 6:
                self._heading_groups[h4].append(rec)

            # Learn master-derived qualifier and material distributions across chapters
            for seg in (t8_desc, s6_desc):
                if not seg:
                    continue
                pos_seg, _, _, _ = extract_statutory_exclusions(seg)
                toks = set(_tokenize(pos_seg))
                for t in toks:
                    all_chaps[t].add(ch)
                if _SYNTACTIC_QUALIFIER_PREFIX_RE.match(pos_seg):
                    for t in toks:
                        prep_chaps[t].add(ch)
                for mm in _MATERIAL_PREP_RE.finditer(pos_seg.lower()):
                    phrase = mm.group(1).strip()
                    p_toks = _tokenize(phrase)
                    # Reject generic non-material syntactic complements (e.g., "a kind", "heading", "liquid")
                    if 1 <= len(p_toks) <= 3 and not any(
                        bad in phrase for bad in ("heading", "chapter", "kind", "purpose", "capacity", "weight", "length", "width", "size", "use", "retail")
                    ):
                        for mt in p_toks:
                            mat_chaps[mt].add(ch)

        # Tokens appearing predominantly in prepositional/qualifying leaf clauses across >=4 chapters
        min_qual_chaps = 4 if len({r["chapter_code"] for r in self._record_by_hsn.values()}) >= 5 else 2
        for tok, p_chs in prep_chaps.items():
            if len(p_chs) >= min_qual_chaps:
                self.corpus_qualifier_tokens.add(tok)

        min_mat_chaps = 4 if len({r["chapter_code"] for r in self._record_by_hsn.values()}) >= 5 else 1
        for tok, m_chs in mat_chaps.items():
            if len(m_chs) >= min_mat_chaps and tok not in _HIERARCHY_STOPWORDS:
                self.corpus_material_tokens.add(tok)

        # Compute sibling shared tokens and branch-specific articles per 4-digit heading
        for h4, children in self._heading_groups.items():
            leaves = [r for r in children if r["code_length"] == 8] or children
            h4_pos_text, _, _, _ = extract_statutory_exclusions(self._heading_parent_desc.get(h4, ""))
            h4_toks = set(_tokenize(h4_pos_text))
            # Leading primary heading subject tokens (first sentence/clause of heading before '-' / ';')
            h4_lead_clause = re.split(r"[;-]", h4_pos_text, maxsplit=1)[0]
            h4_lead_toks = set(_tokenize(h4_lead_clause))

            doc_freq: Counter = Counter()
            branch_articles: Dict[str, Set[str]] = defaultdict(set)

            for r in leaves:
                leaf_pos, _, _, _ = extract_statutory_exclusions(r["tariff_item_desc"])
                sub6_pos, _, _, _ = extract_statutory_exclusions(r["subheading_6digit_desc"])
                toks = set(_tokenize(leaf_pos)) | set(_tokenize(sub6_pos))
                for t in toks:
                    doc_freq[t] += 1

                # Concrete branch nouns appearing at sub6 primary head (if not a syntactic qualifier/PARTS/OTHER),
                # or at direct 8d leaf when no sub6 hierarchy clause exists,
                # or in an intermediate " - CLAUSE :" inside statutory_description when sub6 itself is "OF COTTON"/"OTHER".
                sub6_is_qual = (
                    not sub6_pos
                    or sub6_pos.strip().upper() in ("OTHER", "OTHERS", "PARTS", "PARTS AND ACCESSORIES")
                    or bool(_SYNTACTIC_QUALIFIER_PREFIX_RE.match(sub6_pos))
                )
                head_toks: Set[str] = set()
                if not sub6_is_qual:
                    head_toks = _extract_pre_clause_head_tokens(sub6_pos, drop_participles=True)
                else:
                    stat_pos, _, _, _ = extract_statutory_exclusions(r["statutory_description"])
                    if " - " in stat_pos:
                        mid_seg = stat_pos.split(" - ", 1)[1]
                        if leaf_pos and mid_seg.upper().endswith(leaf_pos.upper()):
                            mid_seg = mid_seg[: len(mid_seg) - len(leaf_pos)]
                        for part in mid_seg.split(":"):
                            p_clean = part.strip(" -:")
                            if (
                                p_clean
                                and p_clean.upper() not in ("OTHER", "OTHERS", "PARTS", "PARTS AND ACCESSORIES")
                                and not _SYNTACTIC_QUALIFIER_PREFIX_RE.match(p_clean)
                            ):
                                head_toks |= _extract_pre_clause_head_tokens(p_clean, drop_participles=True)
                    if (
                        not head_toks
                        and not sub6_pos
                        and not _SYNTACTIC_QUALIFIER_PREFIX_RE.match(leaf_pos)
                        and not r["is_residual"]
                    ):
                        head_toks = _extract_pre_clause_head_tokens(leaf_pos, drop_participles=True)

                branch_key = r["subheading_6digit"] if len(r["subheading_6digit"]) == 6 else r["hsn_code"]
                for ht in head_toks:
                    if (
                        ht not in self.corpus_qualifier_tokens
                        and ht not in self.corpus_material_tokens
                        and (not h4_toks or ht in h4_toks or len(leaves) >= 2)
                    ):
                        branch_articles[branch_key].add(ht)

            thresh = max(2, (len(leaves) + 1) // 2) if len(leaves) >= 2 else 999
            shared = {t for t, cnt in doc_freq.items() if cnt >= thresh}
            self._h4_shared_tokens[h4] = shared
            self._h4_sibling_branch_articles[h4] = dict(branch_articles)

    def analyze_record(self, rec_or_fields: Dict[str, Any]) -> TariffHierarchyAnalysis:
        hsn = str(rec_or_fields.get("hsn_code") or "").strip()
        if hsn and hsn in self._analysis_cache and rec_or_fields is self._record_by_hsn.get(hsn):
            return self._analysis_cache[hsn]

        # Merge passed fields with authoritative stored record ONLY when compatible (don't inject mismatched parent headings on synthetic records)
        stored = self._record_by_hsn.get(hsn, {})
        caller_t8 = str(rec_or_fields.get("tariff_item_desc") or "").strip()
        caller_stat = str(rec_or_fields.get("statutory_description") or "").strip()
        stored_t8 = str(stored.get("tariff_item_desc") or "").strip()
        synthetic_override = bool(
            stored
            and rec_or_fields is not stored
            and not rec_or_fields.get("heading_4digit_desc")
            and caller_t8
            and stored_t8
            and caller_t8.lower() != stored_t8.lower()
        )
        if synthetic_override:
            stored = {}

        h4 = str(rec_or_fields.get("heading_4digit") or stored.get("heading_4digit") or hsn[:4]).strip()
        h6 = str(rec_or_fields.get("subheading_6digit") or stored.get("subheading_6digit") or (hsn[:6] if len(hsn) >= 6 else h4)).strip()

        h4_desc = str(rec_or_fields.get("heading_4digit_desc") or stored.get("heading_4digit_desc") or ("" if synthetic_override else self._heading_parent_desc.get(h4, ""))).strip()
        s6_desc = str(rec_or_fields.get("subheading_6digit_desc") or stored.get("subheading_6digit_desc") or ("" if synthetic_override else self._sub6_desc.get(h6, ""))).strip()
        t8_desc = str(caller_t8 or stored_t8).strip()
        stat_desc = str(caller_stat or stored.get("statutory_description") or "").strip()

        # 1. Explicit exclusions across all hierarchy levels
        pos_h4, _, ex_tok_4, ex_h_4 = extract_statutory_exclusions(h4_desc)
        pos_s6, _, ex_tok_6, ex_h_6 = extract_statutory_exclusions(s6_desc)
        pos_t8, _, ex_tok_8, ex_h_8 = extract_statutory_exclusions(t8_desc)
        pos_stat, _, ex_tok_stat, ex_h_stat = extract_statutory_exclusions(stat_desc)

        # Positive parent subject tokens (including untruncated statutory heading prefix) must not be marked excluded
        # merely because an exclusion says e.g. "excluding fish fillets" (fish is positive; fillet is excluded).
        h4_positive_subject = _extract_pre_clause_head_tokens(pos_h4 or pos_stat)
        own_pos_tokens = set(_tokenize(pos_t8)) | set(_tokenize(pos_s6))

        explicit_exclusions = (ex_tok_4 | ex_tok_6 | ex_tok_8 | ex_tok_stat) - h4_positive_subject - own_pos_tokens
        explicit_exclusions = {
            t for t in explicit_exclusions
            if t not in self.corpus_qualifier_tokens and t not in self.corpus_material_tokens
        }
        excluded_headings = ex_h_4 | ex_h_6 | ex_h_8 | ex_h_stat

        # 2. Sibling shared vs distinguishing vocabulary & contradictory sibling articles
        sibling_shared = set(self._h4_shared_tokens.get(h4, set()))
        branch_key = h6 if len(h6) == 6 else hsn
        branch_map = self._h4_sibling_branch_articles.get(h4, {})

        # Ancestral branch clauses specific to this record (non-qualifying intermediate hierarchy segments only)
        stat_parent_part = pos_stat
        if pos_t8 and pos_stat.upper().endswith(pos_t8.upper()) and len(pos_stat) > len(pos_t8):
            stat_parent_part = pos_stat[: len(pos_stat) - len(pos_t8)].strip(" -:;")
        mid_toks: Set[str] = set()
        if " - " in stat_parent_part:
            stat_mid_clause = stat_parent_part.split(" - ", 1)[1].strip(" -:")
            for part in stat_mid_clause.split(":"):
                p_clean = part.strip(" -:")
                if (
                    p_clean
                    and p_clean.upper() not in ("OTHER", "OTHERS", "PARTS", "PARTS AND ACCESSORIES")
                    and not _SYNTACTIC_QUALIFIER_PREFIX_RE.match(p_clean)
                ):
                    mid_toks |= _extract_pre_clause_head_tokens(p_clean, drop_participles=True)

        sub6_is_qual = (
            not pos_s6
            or pos_s6.strip().upper() in ("OTHER", "OTHERS", "PARTS", "PARTS AND ACCESSORIES")
            or bool(_SYNTACTIC_QUALIFIER_PREFIX_RE.match(pos_s6))
        )
        own_branch_articles = (set() if synthetic_override else set(branch_map.get(branch_key, set()))) | mid_toks
        if not sub6_is_qual:
            own_branch_articles |= _extract_pre_clause_head_tokens(pos_s6, drop_participles=True)
        own_branch_articles -= self.corpus_qualifier_tokens | self.corpus_material_tokens

        leaf_for_check = pos_t8 or t8_desc
        leaf_norm = re.sub(r"[^a-z0-9\s]", "", leaf_for_check.lower()).strip()
        is_residual = bool(rec_or_fields.get("is_residual")) or leaf_norm in ("other", "others", "all other", "other goods")
        leaf_head_direct = (
            _extract_pre_clause_head_tokens(leaf_for_check, drop_participles=True)
            - self.corpus_qualifier_tokens
            - self.corpus_material_tokens
        ) if (not pos_s6 and leaf_for_check and not is_residual and not _SYNTACTIC_QUALIFIER_PREFIX_RE.match(leaf_for_check)) else set()
        if leaf_head_direct:
            own_branch_articles |= leaf_head_direct

        other_branch_articles: Set[str] = set()
        if not synthetic_override:
            for bk, toks in branch_map.items():
                if bk != branch_key:
                    other_branch_articles.update(toks)

        h4_all_pos_toks = set(_tokenize(pos_h4)) - self.corpus_qualifier_tokens - self.corpus_material_tokens
        # Reject sibling heading nouns (`h4_all_pos_toks`) when THIS branch's non-qualifying sub6
        # (or direct concrete leaf with no sub6) explicitly selects a narrower commodity subset from the heading
        # (e.g., `73181600: NUTS` vs `bolt`/`screw`).
        own_claims_h4_subset = (
            ((not sub6_is_qual) or bool(leaf_head_direct))
            and bool(own_branch_articles & h4_all_pos_toks)
        )

        contradictory_siblings = {
            t for t in other_branch_articles
            if t not in own_branch_articles
            and t not in own_pos_tokens
            and t not in sibling_shared
            and t not in self.corpus_qualifier_tokens
            and t not in self.corpus_material_tokens
            and (own_claims_h4_subset or t not in h4_all_pos_toks)
        }

        # 3. Parent article identity inherited WITHOUT blind inheritance of sibling-exclusive or excluded articles
        parent_raw_tokens = set(_tokenize(pos_h4)) | set(_tokenize(pos_s6)) | set(_tokenize(stat_parent_part)) | mid_toks
        inherited_parent_articles = {
            t for t in parent_raw_tokens
            if (
                t in own_branch_articles
                or (
                    t not in explicit_exclusions
                    and t not in contradictory_siblings
                    and t not in self.corpus_qualifier_tokens
                    and t not in self.corpus_material_tokens
                )
            )
        }

        # 4. Qualifying-only leaf vs new article identity introduced at leaf level
        leaf_for_check = pos_t8 or t8_desc
        leaf_norm = re.sub(r"[^a-z0-9\s]", "", leaf_for_check.lower()).strip()
        is_residual = bool(rec_or_fields.get("is_residual")) or leaf_norm in ("other", "others", "all other", "other goods")
        leaf_toks = set(_tokenize(pos_t8))
        novel_leaf_nouns = {
            t for t in leaf_toks
            if t not in self.corpus_qualifier_tokens
            and t not in self.corpus_material_tokens
            and t not in inherited_parent_articles
            and t not in set(_tokenize(pos_h4))
            and t not in set(_tokenize(pos_s6))
        }

        if is_residual:
            is_qual_only = True
            qual_reason = "residual_other"
        elif _SYNTACTIC_QUALIFIER_PREFIX_RE.match(leaf_for_check):
            # Prepositional/numeric clause: still check whether an entirely new article noun was explicitly added after `of/for/with`
            if re.match(r"^\s*(?:of|in|by|with|without|exceeding|not\s+exceeding|up\s+to|other\s+than)\b", leaf_for_check, re.IGNORECASE) and not novel_leaf_nouns:
                is_qual_only = True
                qual_reason = "syntactic_qualifier_clause"
            elif re.match(r"^\s*(?:of\s+a\s+capacity|of\s+an?\s+(?:power|output|weight|thrust|cylinder|length|width|thickness|diameter|voltage))\b", leaf_for_check, re.IGNORECASE):
                is_qual_only = True
                qual_reason = "numeric_constraint_only"
            elif not novel_leaf_nouns:
                is_qual_only = True
                qual_reason = "syntactic_qualifier_clause"
            else:
                is_qual_only = True if re.match(r"^\s*(?:for|suitable\s+for|designed\s+for|with)\b", leaf_for_check, re.IGNORECASE) else False
                qual_reason = "syntactic_qualifier_clause" if is_qual_only else "distinct_article_introduced"
        elif leaf_toks and not novel_leaf_nouns:
            # If the leaf starts directly with a concrete article noun selected from an enumerated
            # multi-article parent (rather than a qualifier/state modifier), treat it as specifying
            # a distinct article rather than qualifying-only.
            leaf_head_nouns = (
                _extract_pre_clause_head_tokens(leaf_for_check, drop_participles=True)
                - self.corpus_qualifier_tokens
                - self.corpus_material_tokens
            ) if not _SYNTACTIC_QUALIFIER_PREFIX_RE.match(leaf_for_check) else set()
            parent_comma_items = len(re.split(r"[,;]", pos_h4 or "")) if pos_h4 else 0
            if leaf_head_nouns and parent_comma_items >= 3 and not (leaf_head_nouns & h4_all_pos_toks):
                is_qual_only = False
                qual_reason = "distinct_article_introduced"
            elif leaf_head_nouns and parent_comma_items >= 3 and len(leaf_head_nouns) < len(h4_all_pos_toks):
                is_qual_only = False
                qual_reason = "distinct_article_introduced"
            else:
                is_qual_only = True
                qual_reason = "corpus_qualifier_only"
        else:
            is_qual_only = False
            qual_reason = "distinct_article_introduced"

        # 5. Attributes introduced at subheading/leaf + distinguishing tokens vs siblings
        stat_materials = {
            t for t in (set(_tokenize(pos_s6)) | leaf_toks)
            if t in self.corpus_material_tokens
        }
        distinguishing = (
            (leaf_toks | set(_tokenize(pos_s6)))
            - sibling_shared
            - inherited_parent_articles
        )
        added_modifiers = sorted(
            t for t in (leaf_toks | set(_tokenize(pos_s6)))
            if (t in self.corpus_qualifier_tokens or t not in inherited_parent_articles)
            and t not in stat_materials
        )

        analysis = TariffHierarchyAnalysis(
            hsn_code=hsn,
            inherited_parent_articles=inherited_parent_articles,
            leaf_added_attributes={
                "materials": sorted(stat_materials),
                "modifiers": added_modifiers[:12],
                "sub6_clause": pos_s6,
                "leaf_clause": pos_t8,
            },
            sibling_shared_tokens=sibling_shared,
            sibling_distinguishing_tokens=distinguishing,
            explicit_exclusions=explicit_exclusions,
            excluded_headings=excluded_headings,
            contradictory_sibling_articles=contradictory_siblings,
            is_qualifying_only_leaf=is_qual_only,
            qualifying_reason=qual_reason,
            statutory_materials=stat_materials,
        )
        if hsn and rec_or_fields is self._record_by_hsn.get(hsn):
            self._analysis_cache[hsn] = analysis
        return analysis


_DEFAULT_HIERARCHY_INTEL: Optional[MasterHierarchyIntelligence] = None


def get_hierarchy_intelligence(parquet_path: Path = DEFAULT_ENRICHED_PARQUET) -> MasterHierarchyIntelligence:
    global _DEFAULT_HIERARCHY_INTEL
    if _DEFAULT_HIERARCHY_INTEL is None:
        _DEFAULT_HIERARCHY_INTEL = MasterHierarchyIntelligence(parquet_path=parquet_path)
    return _DEFAULT_HIERARCHY_INTEL
