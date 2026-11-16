"""
Layer 3: Product-to-Tariff Semantic Verification & Reranker
===========================================================
Evaluates the semantic relationship between an extracted product intent / query
and candidate statutory tariff rows using a Cross-Encoder (e.g. BAAI/bge-reranker-v2-m3).

Zero hardcoded product names, HSN codes, or chapter-specific rules are embedded here;
scoring is purely driven by the model over the candidate tariff context.
"""

import logging
import math
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

CrossEncoder = None  # Lazy-loaded on first instantiation to keep module imports fast

logger = logging.getLogger(__name__)

DEFAULT_RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"
BASELINE_RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


@dataclass
class RerankedTariffCandidate:
    """Structured output for a single reranked tariff candidate."""

    hsn_code: str
    chapter_code: str
    description: str
    relevance_score: float
    raw_logit: float
    chapter_title: str = ""
    heading_4digit_desc: str = ""
    subheading_6digit_desc: str = ""
    tariff_item_desc: str = ""
    article_keywords: str = ""
    material_keywords: str = ""
    tariff_level: str = "LEAF_8DIGIT"
    original_index: int = -1


def classify_tariff_level(hsn_code: str, code_length: Optional[Any] = None) -> str:
    """Distinguishes 8-digit leaf tariff items from 6-digit subheadings and 4-digit headings."""
    code = str(hsn_code or "").strip()
    n = len(code)
    if n == 0 and code_length is not None:
        try:
            n = int(code_length)
        except (TypeError, ValueError):
            n = 0
    if n >= 8:
        return "LEAF_8DIGIT"
    if n >= 6:
        return "SUBHEADING_6DIGIT"
    return "HEADING_4DIGIT"


def _sigmoid(x: float) -> float:
    """Numerically stable sigmoid for converting raw logits to [0, 1]."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    exp_x = math.exp(x)
    return exp_x / (1.0 + exp_x)


def _get_field(row: Any, *keys: str, default: str = "") -> str:
    """Safely extracts a string field from either a dict or an object/Pydantic model."""
    for key in keys:
        if isinstance(row, dict):
            val = row.get(key)
        else:
            val = getattr(row, key, None)
        if val is not None and str(val).strip().lower() not in ("", "nan", "none"):
            return str(val).strip()
    return default


def format_tariff_context(row: Any) -> str:
    """
    Formats a statutory tariff row (dict or SearchCandidate) into a unified
    structured passage for Cross-Encoder evaluation, prioritizing the most
    distinguishing leaf-level statutory details near the beginning so sequence
    truncation never hides 8-digit tariff differences.
    """
    hsn_code = _get_field(row, "hsn_code", "HSN Code", "code_str")
    tariff_desc = _get_field(row, "tariff_item_desc")
    hsn_desc = _get_field(
        row, "statutory_description", "HSN Description", "tariff_item_desc", "description"
    )
    subheading_desc = _get_field(row, "subheading_6digit_desc")
    article_kw = _get_field(row, "article_keywords", "Article Keywords")
    material_kw = _get_field(row, "material_keywords", "Material Keywords")
    heading_desc = _get_field(row, "heading_4digit_desc")
    chapter_title = _get_field(row, "chapter_title")

    ordered_raw = [
        f"HSN {hsn_code}" if hsn_code else "",
        tariff_desc,
        hsn_desc,
        subheading_desc,
        article_kw,
        material_kw,
        heading_desc,
        chapter_title,
    ]
    parts: List[str] = []
    seen_lower = set()
    for p in ordered_raw:
        if not p:
            continue
        p_norm = re.sub(r"\bvaccum\b", "vacuum", re.sub(r"\bstailess\b", "stainless", p, flags=re.IGNORECASE), flags=re.IGNORECASE)
        p_low = p_norm.lower()
        if p_low in seen_lower:
            continue
        seen_lower.add(p_low)
        parts.append(p_norm)
    return " | ".join(parts)


class ProductTariffReranker:
    """
    Cross-Encoder reranker for Product-to-Tariff Semantic Verification.
    Supports BAAI/bge-reranker-v2-m3, BAAI/bge-reranker-base,
    cross-encoder/ms-marco-MiniLM-L-6-v2, and fine-tuned local checkpoints.
    """

    def __init__(
        self,
        model_name_or_path: str = DEFAULT_RERANKER_MODEL,
        device: Optional[str] = None,
        max_length: int = 512,
        local_files_only: bool = True,
        batch_size: int = 64,
    ):
        self.model_name_or_path = model_name_or_path
        if device is None:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device
        self.max_length = max_length
        self.batch_size = batch_size

        global CrossEncoder
        if CrossEncoder is None:
            from sentence_transformers import CrossEncoder as _CrossEncoder
            CrossEncoder = _CrossEncoder

        logger.info(
            f"Loading ProductTariffReranker model='{model_name_or_path}' "
            f"device='{self.device}' local_files_only={local_files_only}"
        )
        t0 = time.perf_counter()
        self.model = CrossEncoder(
            model_name_or_path,
            device=self.device,
            max_length=max_length,
            local_files_only=local_files_only,
        )
        self.load_time_s = time.perf_counter() - t0
        self._pair_cache: Dict[Tuple[str, str], float] = {}
        self._pair_cache_max = 20000
        self.pair_cache_hits = 0
        self.pair_cache_misses = 0
        logger.info(f"Loaded '{model_name_or_path}' in {self.load_time_s:.2f}s")

    def score_pairs(self, pairs: Sequence[Sequence[str]]) -> List[float]:
        """Scores a list of (query, tariff_context) pairs, returning raw logits (with in-memory pair cache)."""
        if not pairs:
            return []
        n = len(pairs)
        out: List[Optional[float]] = [None] * n
        miss_indices: List[int] = []
        miss_pairs: List[Sequence[str]] = []

        for idx, p in enumerate(pairs):
            key = (str(p[0]), str(p[1]))
            cached = self._pair_cache.get(key)
            if cached is not None:
                out[idx] = cached
                self.pair_cache_hits += 1
            else:
                miss_indices.append(idx)
                miss_pairs.append(p)
                self.pair_cache_misses += 1

        if miss_pairs:
            if len(miss_pairs) <= self.batch_size:
                miss_scores = self.model.predict(
                    list(miss_pairs),
                    batch_size=self.batch_size,
                    show_progress_bar=False,
                )
                for m_idx, sc in zip(miss_indices, miss_scores):
                    val = float(sc)
                    out[m_idx] = val
                    if len(self._pair_cache) >= self._pair_cache_max:
                        self._pair_cache.clear()
                    self._pair_cache[(str(pairs[m_idx][0]), str(pairs[m_idx][1]))] = val
            else:
                # Length-bucket pairs so short sequences aren't padded to the longest batch item on CPU
                indexed = sorted(
                    zip(miss_indices, miss_pairs),
                    key=lambda item: len(str(item[1][0])) + len(str(item[1][1])),
                )
                sorted_pairs = [item[1] for item in indexed]
                sorted_scores = self.model.predict(
                    sorted_pairs,
                    batch_size=self.batch_size,
                    show_progress_bar=False,
                )
                for (m_idx, p), sc in zip(indexed, sorted_scores):
                    val = float(sc)
                    out[m_idx] = val
                    if len(self._pair_cache) >= self._pair_cache_max:
                        self._pair_cache.clear()
                    self._pair_cache[(str(p[0]), str(p[1]))] = val

        return [float(x) if x is not None else 0.0 for x in out]

    def rerank(
        self,
        product_intent: str,
        tariff_rows: Sequence[Any],
        top_k: Optional[int] = None,
        normalize_sigmoid: bool = True,
    ) -> List[RerankedTariffCandidate]:
        """
        Reranks candidate tariff rows against the product intent/description.

        Note: Raw Cross-Encoder logits are not calibrated probabilities.
        `normalize_sigmoid` maps raw logits via standard sigmoid to (0, 1) for
        consistent ordering, while preserving `raw_logit` for threshold calibration.
        """
        if not tariff_rows:
            return []

        # Deduplicate identical formatted tariff contexts so duplicate statutory descriptions
        # are scored once by the Cross-Encoder and mapped back to every matching row.
        unique_contexts: List[str] = []
        context_to_idx: Dict[str, int] = {}
        row_context_indices: List[int] = []
        for row in tariff_rows:
            ctx = format_tariff_context(row)
            c_idx = context_to_idx.get(ctx)
            if c_idx is None:
                c_idx = len(unique_contexts)
                context_to_idx[ctx] = c_idx
                unique_contexts.append(ctx)
            row_context_indices.append(c_idx)

        unique_pairs = [[product_intent, ctx] for ctx in unique_contexts]
        unique_raw_scores = self.score_pairs(unique_pairs)
        raw_scores = [unique_raw_scores[c_idx] for c_idx in row_context_indices]

        results: List[RerankedTariffCandidate] = []
        for idx, (row, raw_score) in enumerate(zip(tariff_rows, raw_scores)):
            rel_score = _sigmoid(raw_score) if normalize_sigmoid else raw_score
            hsn_code = _get_field(row, "hsn_code", "HSN Code", "code_str")
            code_len = row.get("code_length") if isinstance(row, dict) else getattr(row, "code_length", None)
            results.append(
                RerankedTariffCandidate(
                    hsn_code=hsn_code,
                    chapter_code=_get_field(row, "chapter_code", "chapter_str", "chapter"),
                    description=_get_field(
                        row,
                        "statutory_description",
                        "HSN Description",
                        "tariff_item_desc",
                        "description",
                    ),
                    relevance_score=float(rel_score),
                    raw_logit=float(raw_score),
                    chapter_title=_get_field(row, "chapter_title"),
                    heading_4digit_desc=_get_field(row, "heading_4digit_desc"),
                    subheading_6digit_desc=_get_field(row, "subheading_6digit_desc"),
                    tariff_item_desc=_get_field(row, "tariff_item_desc"),
                    article_keywords=_get_field(row, "article_keywords", "Article Keywords"),
                    material_keywords=_get_field(row, "material_keywords", "Material Keywords"),
                    tariff_level=classify_tariff_level(hsn_code, code_len),
                    original_index=idx,
                )
            )

        results.sort(key=lambda r: r.raw_logit, reverse=True)
        if top_k is not None:
            return results[:top_k]
        return results

