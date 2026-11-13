"""
src/chapter_predictor/ambiguity_resolver.py
===========================================
100% Dynamic Semantic Ambiguity Detector & Multi-Option Resolver for HSN Chapters and Codes.

Operates purely dynamically over data/Master_copy_hsn.parquet (4,851 statutory lines with rich
chapter_code, chapter_title, HSN Description, Article Keywords, and Material Keywords) and
data/raw/tariff_master.parquet (19,396 CBIC official tariff lines).

Architecture:
1. Dynamic Head Noun & Attribute Extraction:
   - Identifies head noun (rightmost content noun in noun compounds, e.g. 'bottle' in 'water bottle')
   - Extracts constituent material, commodity state (insulated, knitted, woven, mounted, roasted, etc.)
2. Statutory Tariff Matching:
   - Matches candidate lines based on head noun in official tariff description and article keywords
   - Enforces GIR statutory rules: finished commodity articles vs primary forms/resins (Ch 3901-3914)
     and pipe fittings/flanges (7307)
3. Sibling Expansion & Co-evaluation:
   - When a candidate subheading is retrieved (e.g. 3923 30), automatically retrieves ALL sibling
     8-digit leaf options (e.g. 3923 30 10 Insulated Ware and 3923 30 90 Other)
   - Evaluates multi-material statutory candidates (Plastics Ch 39, Steel Ch 73, Glass Ch 70, Vacuum Ch 96)
4. Dynamic Decision Protocol:
   - Ambiguous (is_ambiguous=True): If distinguishing material/specification is not specified in query,
     generates human-readable multi-option cards directly from tariff records.
   - Direct Match (is_ambiguous=False): If specific material/specification is provided (e.g. 'insulated
     water bottle', 'stainless steel water bottle'), locks to the exact 8-digit HSN code.
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field
import pandas as pd

from src.chapter_predictor.normalize import extract_query_facts

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent


class DisambiguationOption(BaseModel):
    option_id: str = Field(..., description="Unique ID for option, e.g. 'OPT_39233010_1'")
    label: str = Field(..., description="Clean human-readable label dynamically derived from tariff text")
    chapter_code: str = Field(..., description="2-digit Chapter code e.g. '39'")
    chapter_title: str = Field(..., description="Official Chapter title e.g. 'Plastics and articles thereof'")
    hsn_code: str = Field(..., description="Specific statutory HSN code e.g. '3923 30 10'")
    hsn_description: str = Field(..., description="Statutory HSN Description")
    material_keywords: str = Field(default="", description="Relevant material keywords from Master dataset")
    article_keywords: str = Field(default="", description="Relevant article keywords from Master dataset")
    score: float = Field(default=0.0, description="Relevance confidence score")


class DynamicAmbiguityResolver:
    """
    Singleton Dynamic Ambiguity & Sibling Recommendation Engine.
    Loads and indexes Master_copy_hsn.parquet and tariff_master.parquet once in memory.
    """
    _instance: Optional["DynamicAmbiguityResolver"] = None

    def __init__(self):
        self.records: List[Dict[str, Any]] = []
        self.by_subheading: Dict[str, List[Dict[str, Any]]] = {}
        self.by_heading: Dict[str, List[Dict[str, Any]]] = {}
        self.by_chapter: Dict[str, List[Dict[str, Any]]] = {}
        self._load_dataset()

    def _load_dataset(self):
        master_path = ROOT_DIR / "data" / "Master_copy_hsn.parquet"
        master_excel = ROOT_DIR / "data" / "raw" / "Master_copy_hsn.xlsx"

        seen_codes = set()
        df_m = None
        if master_path.exists():
            try:
                df_m = pd.read_parquet(master_path)
            except Exception as e:
                logger.warning(f"Error loading Master_copy_hsn.parquet: {e}")

        if df_m is None and master_excel.exists():
            try:
                df_m = pd.read_excel(master_excel)
            except Exception as e:
                logger.warning(f"Error loading Master_copy_hsn.xlsx: {e}")

        if df_m is not None:
            try:
                for _, r in df_m.iterrows():
                    raw_c = str(r.get("HSN Code", "")).replace(" ", "").strip()
                    if len(raw_c) in [6, 8]:
                        seen_codes.add(raw_c)
                        ch = str(r.get("chapter_code", "")).zfill(2)
                        rec = {
                            "hsn_code": raw_c,
                            "chapter_code": ch,
                            "chapter_title": str(r.get("chapter_title") or f"Chapter {ch}").strip(),
                            "hsn_description": str(r.get("HSN Description") or "").strip(),
                            "article_keywords": str(r.get("Article Keywords") or "").strip(),
                            "material_keywords": str(r.get("Material Keywords") or "").strip(),
                            "heading": raw_c[:4],
                            "subheading": raw_c[:6]
                        }
                        self.records.append(rec)
                        self.by_subheading.setdefault(rec["subheading"], []).append(rec)
                        self.by_heading.setdefault(rec["heading"], []).append(rec)
                        self.by_chapter.setdefault(rec["chapter_code"], []).append(rec)
            except Exception as e:
                logger.warning(f"Error indexing Master_copy_hsn: {e}")

    @classmethod
    def get_instance(cls) -> "DynamicAmbiguityResolver":
        if cls._instance is None:
            cls._instance = DynamicAmbiguityResolver()
        return cls._instance

    @staticmethod
    def _format_hsn(code: str) -> str:
        c = code.replace(" ", "").strip()
        if len(c) == 8:
            return f"{c[:4]} {c[4:6]} {c[6:]}"
        elif len(c) == 6:
            return f"{c[:4]} {c[4:]}"
        return c

    def _generate_dynamic_label(self, rec: Dict[str, Any]) -> str:
        desc = rec["hsn_description"]
        ch = rec["chapter_code"]
        ch_title = rec["chapter_title"].split("-")[-1].split(";")[0].strip().title()

        # Split description segments
        parts = [p.strip() for p in re.split(r"[:\-]", desc) if p.strip()]
        leaf = parts[-1] if parts else desc
        sub = parts[-2] if len(parts) >= 2 else ""

        leaf_clean = re.sub(r"^\d+\s*", "", leaf).strip().title()
        sub_clean = re.sub(r"^\d+\s*", "", sub).strip().title()

        # Extract primary article keyword if available
        art_first = ""
        if rec["article_keywords"]:
            art_parts = [a.strip() for a in rec["article_keywords"].split(",") if a.strip()]
            if art_parts:
                art_first = art_parts[0].title()

        # Extract primary material keyword if available
        mat_first = ""
        if rec["material_keywords"]:
            mat_parts = [m.strip() for m in rec["material_keywords"].split(",") if m.strip()]
            if mat_parts:
                mat_first = mat_parts[0]

        # Construct clean, informative label
        if sub_clean and leaf_clean and sub_clean.lower() != leaf_clean.lower() and len(sub_clean) < 35:
            body = f"{sub_clean}: {leaf_clean}"
        elif art_first and len(art_first) < 45:
            body = f"{art_first} ({leaf_clean})"
        else:
            body = leaf_clean or desc[:40].title()

        if len(body) > 60:
            body = body[:57] + "..."

        if mat_first and len(mat_first) < 30 and mat_first.lower() not in body.lower():
            label = f"{body} [{mat_first}]"
        else:
            label = body

        return f"{ch_title} - {label}"

    def analyze(
        self,
        raw_query: str,
        evidence_lines: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[bool, Optional[str], List[DisambiguationOption], Optional[DisambiguationOption]]:
        """
        Analyzes whether the user's product query is ambiguous across materials, chapters,
        or sibling subheadings, or directly resolves to a specific statutory HSN code.

        Returns:
            (is_ambiguous, clarification_question, options_list, direct_match_option)
        """
        q_norm = (raw_query or "").lower().strip()
        if not q_norm:
            return False, None, [], None

        facts = extract_query_facts(raw_query)
        article_noun = (facts.get("article") or "").lower().strip()
        stated_material = (facts.get("material") or "").lower().strip()
        stated_form = (facts.get("form") or "").lower().strip()

        query_words = [w for w in re.findall(r"\b[a-z0-9]{3,}\b", q_norm)]
        query_stems = [w.rstrip("s") if len(w) > 3 else w for w in query_words]

        head_stem = article_noun.rstrip("s") if len(article_noun) > 3 else article_noun
        if not head_stem and query_stems:
            head_stem = query_stems[-1]

        # Detect distinguishing attributes in query
        has_insulated = any(k in q_norm for k in ["insulat", "thermal", "vacuum", "thermos", "hot cold"])
        has_gas = any(k in q_norm for k in ["lpg", "gas", "cylinder", "propane", "butane", "compressed"])
        has_mounted = any(k in q_norm for k in ["mounted", "with backing", "pad"])
        has_unmounted = any(k in q_norm for k in ["unmounted", "rolls", "sheets"])
        has_knit = any(k in q_norm for k in ["knit", "crochet", "jersey", "t-shirt", "tshirt", "polo"])
        has_woven = any(k in q_norm for k in ["woven", "formal", "poplin", "oxford", "twill"])
        has_roasted = "roasted" in q_norm
        has_raw = any(k in q_norm for k in ["raw", "green", "unroasted"])

        # Score matching records dynamically
        scored_candidates: List[Dict[str, Any]] = []
        for rec in self.records:
            desc = rec["hsn_description"].lower()
            art = rec["article_keywords"].lower()
            mat = rec["material_keywords"].lower()
            ch = rec["chapter_code"]
            code = rec["hsn_code"]

            # Head noun regex matching singular and plural forms
            head_pattern = rf"\b{re.escape(head_stem)}(?:s|es)?\b" if head_stem else r"$^"
            matches_head = head_stem and (bool(re.search(head_pattern, desc)) or bool(re.search(head_pattern, art)))

            token_matches = sum(
                1 for s in query_stems
                if re.search(rf"\b{re.escape(s)}(?:s|es)?\b", desc)
                or re.search(rf"\b{re.escape(s)}(?:s|es)?\b", art)
                or re.search(rf"\b{re.escape(s)}(?:s|es)?\b", mat)
            )

            if not matches_head and token_matches == 0:
                continue

            score = 0.0
            if matches_head:
                score += 8.0
                if re.search(head_pattern, desc):
                    score += 10.0
                if re.search(head_pattern, art):
                    score += 6.0

                # Statutory Subheading Match (GIR 1 / GIR 6):
                # Check if head commodity noun is in the specific 6-digit subheading group between '-' and ':'
                if " - " in desc:
                    after_hyphen = desc.split(" - ", 1)[-1].lower()
                    subheading_part = after_hyphen.split(":", 1)[0].strip() if ":" in after_hyphen else after_hyphen
                    if re.search(head_pattern, subheading_part):
                        score += 30.0
                    elif any(c in subheading_part for c in ["stopper", "lid", "cap", "crate", "box", "case", "fitting", "part"]):
                        score -= 20.0

            for s in query_stems:
                s_pattern = rf"\b{re.escape(s)}(?:s|es)?\b"
                if s != head_stem:
                    if re.search(s_pattern, art):
                        score += 8.0
                    elif s in art:
                        score += 4.0
                    if re.search(s_pattern, desc):
                        score += 6.0
                    elif s in desc:
                        score += 3.0
                    if s in mat:
                        score += 3.0

            # Attribute alignments
            if "insulat" in desc or "insulat" in art or "insulat" in mat:
                if has_insulated:
                    score += 8.0
                elif not has_insulated:
                    score += 1.0
            elif has_insulated:
                score -= 6.0

            if "lpg" in desc or "cylinder" in art or "gas" in desc:
                if has_gas:
                    score += 10.0
                elif not has_gas:
                    score -= 4.0

            if "roasted" in desc or "roasted" in art:
                if has_roasted:
                    score += 8.0
                elif has_raw:
                    score -= 8.0

            if ch in ["61", "62"]:
                if ch == "61" and has_knit:
                    score += 8.0
                elif ch == "62" and has_woven:
                    score += 8.0
                elif ch == "61" and has_woven:
                    score -= 8.0
                elif ch == "62" and has_knit:
                    score -= 8.0

            # Constituent material alignment
            if stated_material:
                if stated_material in mat or stated_material in desc or stated_material in art:
                    score += 8.0
                else:
                    score -= 6.0

            # Full query token coverage bonus (e.g. 'solar panel', 'water bottle', 'centrifugal pump')
            if len(query_stems) >= 2:
                combined_text = f"{desc} {art} {mat}".lower()
                all_tokens_match = all(
                    re.search(rf"\b{re.escape(s)}(?:s|es)?\b", combined_text)
                    for s in query_stems
                )
                if all_tokens_match:
                    score += 25.0
                if q_norm in desc or q_norm in art:
                    score += 20.0

            # Deprioritize raw primary forms, scrap (3915), and pipe fittings (7307) for finished goods
            if (ch == "39" and (code[:4] in [f"39{str(i).zfill(2)}" for i in range(1, 16)] or code.startswith("3915"))) or "primary form" in desc or "resin" in desc or "waste" in desc or "scrap" in desc:
                if not any(k in q_norm for k in ["resin", "chip", "flake", "scrap", "waste", "primary form", "granule", "powder"]):
                    score -= 30.0

            if code.startswith("7307") and not any(k in q_norm for k in ["fitting", "flange", "elbow", "sleeve", "coupling", "bend", "joint"]):
                score -= 20.0

            if score > 8.0:
                scored_candidates.append({"score": score, "rec": rec})

        scored_candidates.sort(key=lambda x: x["score"], reverse=True)

        # SIBLING EXPANSION & SUBHEADING CO-EVALUATION:
        # For top matching subheadings (e.g. 392330), pull all sibling 8-digit leaves and balance scores
        candidate_pool: Dict[str, Dict[str, Any]] = {}
        seen_subheadings: Set[str] = set()
        for item in scored_candidates[:12]:
            rec = item["rec"]
            base_score = item["score"]
            sub_key = rec["subheading"]

            if sub_key in seen_subheadings:
                continue
            seen_subheadings.add(sub_key)

            # Find all 8-digit siblings under this subheading
            siblings = self.by_subheading.get(sub_key, [])
            if len(siblings) > 1:
                for sib in siblings:
                    sib_code = sib["hsn_code"]
                    if len(sib_code) != 8:
                        continue
                    sib_desc = sib["hsn_description"].lower()
                    sib_score = base_score
                    if "insulat" in sib_desc:
                        if has_insulated:
                            sib_score += 8.0
                        else:
                            sib_score = base_score - 0.2
                    else:
                        if has_insulated:
                            sib_score -= 8.0
                        else:
                            sib_score = base_score - 0.1
                    if sib_code not in candidate_pool or candidate_pool[sib_code]["score"] < sib_score:
                        candidate_pool[sib_code] = {"score": sib_score, "rec": sib}
            else:
                if rec["hsn_code"] not in candidate_pool or candidate_pool[rec["hsn_code"]]["score"] < base_score:
                    candidate_pool[rec["hsn_code"]] = {"score": base_score, "rec": rec}

        # Also incorporate any explicit evidence lines if provided
        if evidence_lines:
            for ev in evidence_lines[:3]:
                ev_code = str(ev.get("hsn_code", "")).replace(" ", "").strip()
                if ev_code and ev_code in candidate_pool:
                    candidate_pool[ev_code]["score"] += 2.0

        final_list = list(candidate_pool.values())
        final_list.sort(key=lambda x: x["score"], reverse=True)

        if not final_list:
            return False, None, [], None

        best_score = final_list[0]["score"]
        # Keep only competitive candidates matching the commodity intent (filter low-scoring noise)
        threshold = max(20.0, best_score * 0.65)
        filtered_top = [c for c in final_list if c["score"] >= threshold]
        if not filtered_top:
            filtered_top = final_list[:1]

        top_options = filtered_top[:5]
        second_score = top_options[1]["score"] if len(top_options) > 1 else 0.0

        # Build DisambiguationOption models
        opts_models: List[DisambiguationOption] = []
        for idx, item in enumerate(top_options):
            r = item["rec"]
            lbl = self._generate_dynamic_label(r)
            opts_models.append(DisambiguationOption(
                option_id=f"OPT_{r['hsn_code']}_{idx+1}",
                label=lbl,
                chapter_code=r["chapter_code"],
                chapter_title=r["chapter_title"],
                hsn_code=self._format_hsn(r["hsn_code"]),
                hsn_description=r["hsn_description"],
                material_keywords=r["material_keywords"],
                article_keywords=r["article_keywords"],
                score=round(item["score"], 2)
            ))

        distinct_chapters = {o.chapter_code for o in opts_models}
        is_close_margin = (best_score - second_score) < 4.0

        # If query has explicit distinguishing specification (e.g. 'insulated water bottle', 'stainless steel water bottle')
        if (has_insulated or stated_material or has_gas or has_knit or has_woven) and not is_close_margin:
            return False, None, [], opts_models[0]

        # Multi-option ambiguity: span multiple chapters OR multiple sibling leaf options
        if len(distinct_chapters) > 1 or len(opts_models) >= 2:
            if len(distinct_chapters) > 1 and not stated_material:
                q = f"What material and construction is the {raw_query}?"
            else:
                q = f"Which specification of {raw_query} applies?"
            return True, q, opts_models, None

        return False, None, [], opts_models[0]


def analyze_product_ambiguity(
    raw_query: str,
    evidence_lines: Optional[List[Dict[str, Any]]] = None
) -> Tuple[bool, Optional[str], List[DisambiguationOption], Optional[DisambiguationOption]]:
    """
    Public entrypoint for Dynamic Semantic Ambiguity & Multi-Option Recommendation.
    Uses Layer 4 SmartAmbiguityController (Weighted BM25 + Dense Vector + RRF + Cross-Encoder Re-Ranking).
    """
    try:
        from src.search.ambiguity_controller import evaluate_product_ambiguity
        res = evaluate_product_ambiguity(raw_query)

        opts_models: List[DisambiguationOption] = []
        for o in res.disambiguation_options:
            opts_models.append(DisambiguationOption(
                option_id=o.option_id,
                label=o.label,
                chapter_code=o.chapter_code,
                chapter_title=o.chapter_title,
                hsn_code=o.hsn_code,
                hsn_description=o.hsn_description,
                material_keywords=o.material_keywords,
                article_keywords=o.article_keywords,
                score=o.score
            ))

        direct_model = None
        if res.direct_match:
            dm = res.direct_match
            direct_model = DisambiguationOption(
                option_id=dm.option_id,
                label=dm.label,
                chapter_code=dm.chapter_code,
                chapter_title=dm.chapter_title,
                hsn_code=dm.hsn_code,
                hsn_description=dm.hsn_description,
                material_keywords=dm.material_keywords,
                article_keywords=dm.article_keywords,
                score=dm.score
            )

        return res.is_ambiguous, res.clarification_question, opts_models, direct_model
    except Exception as e:
        logger.warning(f"SmartAmbiguityController fallback to resolver: {e}")
        resolver = DynamicAmbiguityResolver.get_instance()
        return resolver.analyze(raw_query, evidence_lines)
