"""
src/ml/synthetic_query_generator.py
===================================
Phase 2: Dynamic Synthetic Product Query Generator

Generates realistic natural-language and commercial invoice product descriptions
directly from Master HSN rows (`HSN Description`, `Article Keywords`, `Material Keywords`,
`consumer_synonyms`, etc.) without any hardcoded product rules.

Supports:
  1. Fast deterministic linguistic composition (processes all 3,900+ 8-digit rows in <2s)
  2. Optional local LLM generation (Qwen2.5-0.5B-Instruct) for richer paraphrasing
"""

import logging
import random
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

GENERIC_DESC_TOKENS = {
    "other",
    "others",
    "not elsewhere specified",
    "nes",
    "parts",
    "accessories",
    "thereof",
}


def _split_keywords(raw: Any) -> List[str]:
    """Splits comma/semicolon separated keyword strings into clean unique phrases."""
    if raw is None:
        return []
    text = str(raw).strip()
    if not text or text.lower() in ("nan", "none", "null"):
        return []
    parts = [p.strip() for p in re.split(r"[,;|]+", text)]
    seen = set()
    clean: List[str] = []
    for p in parts:
        p_norm = re.sub(r"\s+", " ", p).strip()
        if len(p_norm) >= 2 and p_norm.lower() not in seen:
            seen.add(p_norm.lower())
            clean.append(p_norm)
    return clean


def _clean_tariff_phrase(raw: Any) -> str:
    """Cleans statutory description fragments for natural query composition."""
    if raw is None:
        return ""
    text = str(raw).strip()
    if not text or text.lower() in ("nan", "none"):
        return ""
    # Remove leading dashes/bullets used in tariff schedules (e.g. "--- Of cotton")
    text = re.sub(r"^[-–—:\s]+", "", text).strip()
    if text.lower() in GENERIC_DESC_TOKENS or len(text) < 4:
        return ""
    return text


@dataclass
class GeneratedQuery:
    query: str
    strategy: str  # "article_only" | "material_article" | "nl_template" | "invoice_shorthand" | "llm"


class SyntheticQueryGenerator:
    """
    Generates diverse natural-language and commercial invoice queries
    for a single HSN tariff row.
    """

    NL_TEMPLATES = [
        "{article} made of {material}",
        "{material} {article}",
        "commercial {article} with {material}",
        "{article} containing {material} for industrial or retail supply",
    ]

    def __init__(self, seed: int = 42, use_llm: bool = False):
        self.rng = random.Random(seed)
        self.use_llm = use_llm
        self._llm_pipe = None

    def _init_llm(self):
        if self._llm_pipe is not None:
            return
        try:
            from transformers import pipeline
            self._llm_pipe = pipeline(
                "text-generation",
                model="Qwen/Qwen2.5-0.5B-Instruct",
                device="cpu",
                local_files_only=True,
            )
            logger.info("Loaded local Qwen/Qwen2.5-0.5B-Instruct for synthetic query generation.")
        except Exception as e:
            logger.warning(f"Could not load local Qwen LLM ({e}); falling back to template generation.")
            self.use_llm = False

    def generate_for_row(self, row: Dict[str, Any], max_queries: int = 5) -> List[GeneratedQuery]:
        """Generates up to `max_queries` diverse positive queries for an HSN row."""
        articles = _split_keywords(row.get("article_keywords") or row.get("Article Keywords"))
        materials = _split_keywords(row.get("material_keywords") or row.get("Material Keywords"))
        synonyms = _split_keywords(row.get("consumer_synonyms"))

        tariff_item = _clean_tariff_phrase(
            row.get("tariff_item_desc") or row.get("HSN Description")
        )
        subheading = _clean_tariff_phrase(row.get("subheading_6digit_desc"))

        candidates: List[GeneratedQuery] = []
        seen_queries = set()

        def _add(q: str, strategy: str):
            q_clean = re.sub(r"\s+", " ", q).strip(" ,.-")
            if len(q_clean) < 3:
                return
            key = q_clean.lower()
            if key not in seen_queries:
                seen_queries.add(key)
                candidates.append(GeneratedQuery(query=q_clean, strategy=strategy))

        # 1. Direct article keywords & consumer synonyms (highest precision commercial names)
        combined_articles = articles + [s for s in synonyms if s.lower() not in {a.lower() for a in articles}]
        for art in combined_articles[:2]:
            _add(art, "article_only")

        # 2. Material + Article commercial combinations
        if combined_articles and materials:
            art1 = combined_articles[0]
            mat1 = materials[0]
            if mat1.lower() not in art1.lower():
                _add(f"{mat1} {art1}", "material_article")
            else:
                _add(f"{art1} ({mat1})", "invoice_shorthand")

            if len(combined_articles) > 1 and len(materials) > 1:
                art2 = combined_articles[1]
                mat2 = materials[1]
                tmpl = self.rng.choice(self.NL_TEMPLATES)
                _add(tmpl.format(article=art2, material=mat2), "nl_template")

        # 3. Invoice shorthand with subheading / tariff context
        if combined_articles and (tariff_item or subheading):
            context_phrase = tariff_item if tariff_item and len(tariff_item) <= 70 else subheading
            if context_phrase and len(context_phrase) <= 70:
                _add(f"{combined_articles[0]} - {context_phrase.lower()}", "invoice_shorthand")

        # 4. Fallback if article_keywords were empty
        if not candidates and tariff_item:
            _add(tariff_item.lower()[:100], "tariff_desc_fallback")

        # 5. Optional LLM paraphrasing
        if self.use_llm and combined_articles:
            self._init_llm()
            if self._llm_pipe is not None:
                llm_q = self._generate_llm_paraphrase(
                    article=combined_articles[0],
                    material=materials[0] if materials else "",
                    desc=tariff_item or subheading,
                )
                if llm_q:
                    _add(llm_q, "llm")

        return candidates[:max_queries]

    def _generate_llm_paraphrase(self, article: str, material: str, desc: str) -> Optional[str]:
        prompt = (
            f"Write one short commercial invoice product description (max 12 words) for: "
            f"product='{article}', material='{material}', tariff='{desc[:80]}'. "
            f"Output only the product description:"
        )
        try:
            out = self._llm_pipe(prompt, max_new_tokens=24, do_sample=False)
            text = out[0]["generated_text"][len(prompt):].strip().splitlines()[0]
            return text.strip(" \"'.")
        except Exception:
            return None

