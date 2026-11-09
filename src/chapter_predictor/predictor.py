"""
src/chapter_predictor/predictor.py
==================================
Unified 4-Stage Product-to-HSN-Chapter Predictor.

Pipeline:
1. Stage A: Normalization (abbreviations, noise, negation preservation)
2. Stage B: BM25 Lexical Retrieval (over 19,396 statutory tariff lines)
3. Stage C: Semantic Vector Retrieval (Dense embeddings & cosine similarity)
4. Stage D: Reranking & GIR Decision (Local Ollama LLM / constrained JSON)
5. Stage E: Fusion & Abstention (RRF fusion + mathematical score margin check)
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

from src.chapter_predictor.normalize import normalize_product_name, extract_query_facts
from src.chapter_predictor.lexical import get_lexical_index, LexicalTariffIndex
from src.chapter_predictor.embeddings import get_semantic_index, SemanticTariffIndex
from src.chapter_predictor.llm_rerank import get_llm_reranker, LocalLLMReranker, LLMRerankResult
from src.chapter_predictor.fusion import (
    reciprocal_rank_fusion,
    line_level_fusion,
    evaluate_abstention,
    VALID_CLASSIFIABLE_CHAPTERS
)

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent


# =====================================================================
# PYDANTIC SCHEMAS
# =====================================================================

class ChapterAlternative(BaseModel):
    chapter: str = Field(..., description="2-digit alternative chapter code (e.g. '62', '84')")
    title: str = Field(..., description="Official WCO / CBIC title of the chapter")
    score: float = Field(..., description="Confidence or fusion score (0.0 to 1.0)")


class TariffEvidence(BaseModel):
    hsn_code: str = Field(..., description="Statutory 8-digit HSN code")
    description: str = Field(..., description="Statutory CBIC description")
    score: float = Field(..., description="Matching relevance score")


class ChapterPrediction(BaseModel):
    product_name: str
    normalized: str
    chapter: str = Field(..., description="Predicted 2-digit HSN chapter (01–99, excluding 77)")
    chapter_title: str
    confidence: float = Field(..., description="Confidence score between 0.0 and 1.0")
    status: Literal["OK", "ABSTAIN", "REJECTED", "PREDICTED", "NEEDS_REVIEW"]
    alternatives: List[ChapterAlternative] = Field(default_factory=list)
    evidence: List[TariffEvidence] = Field(default_factory=list)
    reason: str
    stage_timings_ms: Dict[str, float] = Field(default_factory=dict)
    rerank_model_used: Optional[str] = None


# =====================================================================
# CHAPTER PREDICTOR ENGINE
# =====================================================================

class ChapterPredictor:
    """
    Production-grade Product Name -> HSN Chapter Prediction Engine.
    """
    _instance: Optional["ChapterPredictor"] = None

    def __init__(self):
        self.lexical_index: LexicalTariffIndex = get_lexical_index()
        self.semantic_index: SemanticTariffIndex = get_semantic_index()
        self.llm_reranker: LocalLLMReranker = get_llm_reranker()
        self.chapter_titles: Dict[str, str] = {}
        self._load_chapter_titles()

    @classmethod
    def get_instance(cls) -> "ChapterPredictor":
        if cls._instance is None:
            cls._instance = ChapterPredictor()
        return cls._instance

    def _load_chapter_titles(self):
        titles_path = ROOT_DIR / "src" / "chapter_predictor" / "chapter_titles.json"
        if titles_path.exists():
            try:
                with open(titles_path, "r", encoding="utf-8") as f:
                    self.chapter_titles = json.load(f)
            except Exception as e:
                logger.warning(f"Could not load chapter_titles.json: {e}")

    def warmup(self):
        """Warm up lexical and semantic indexes on process startup."""
        logger.info("Warming up ChapterPredictor indexes...")
        self.lexical_index.load_or_build()
        self.semantic_index.load_or_build()
        logger.info("ChapterPredictor warm-up complete.")

    def predict(self, product_name: str, top_k: int = 3) -> ChapterPrediction:
        """
        Executes end-to-end Chapter prediction for a single product name.
        """
        timings = {}
        t_start = time.perf_counter()

        raw_name = (product_name or "").strip()
        if not raw_name:
            return ChapterPrediction(
                product_name="",
                normalized="",
                chapter="99",
                chapter_title=self.chapter_titles.get("99", "Services"),
                confidence=0.0,
                status="NEEDS_REVIEW",
                alternatives=[],
                evidence=[],
                reason="Empty product name provided.",
                stage_timings_ms={"total": 0.0}
            )

        # -------------------------------------------------------------
        # STAGE A: Normalization
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        normalized_text, tokens = normalize_product_name(raw_name)
        timings["stage_a_norm_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)

        # Immediate Abstention on Unclassifiable Generic Noise (Phase 5)
        generic_noise_tokens = {"assorted", "miscellaneous", "lot", "scrap", "mixed", "unbranded", "random", "unknown", "sample", "xyz", "abc", "item", "product", "goods", "pieces", "numbers"}
        query_word_set = set(tokens)
        if query_word_set and query_word_set.issubset(generic_noise_tokens):
            timings["total_pipeline_ms"] = round((time.perf_counter() - t_start) * 1000.0, 2)
            return ChapterPrediction(
                product_name=raw_name,
                normalized=normalized_text,
                chapter="99",
                chapter_title="Services / Unclassified",
                confidence=0.15,
                status="ABSTAIN",
                alternatives=[],
                evidence=[],
                reason="Unclassifiable generic noise query without identifiable commodity noun or material composition. Routed to review queue.",
                stage_timings_ms=timings,
                rerank_model_used="rule_abstain"
            )

        # -------------------------------------------------------------
        # STAGE B: Lexical Retrieval (BM25)
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        bm25_res = self.lexical_index.query(normalized_text, top_k_tariff=50, top_k_chapters=10)
        timings["stage_b_bm25_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)

        # -------------------------------------------------------------
        # STAGE C: Semantic Retrieval (Dense Embeddings)
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        sem_res = self.semantic_index.query(normalized_text, top_k_tariff=50, top_k_chapters=10)
        timings["stage_c_embedding_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)

        # Extract structured article, form, and material facts using curated vocabulary
        query_facts = extract_query_facts(raw_name)

        # -------------------------------------------------------------
        # STAGE E (Early): Line-Level Weighted Score Fusion with Task 7 Article-First Weighting
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        fused_candidates = line_level_fusion(
            bm25_lines=bm25_res.get("top_tariff_lines", []),
            semantic_lines=sem_res.get("top_tariff_lines", []),
            alpha=0.55,
            top_k_chapters=10,
            query_text=normalized_text,
            query_facts=query_facts
        )
        fusion_method = "line_weighted_fusion"

        # Fallback to RRF if line lists were empty
        if not fused_candidates:
            fused_candidates = reciprocal_rank_fusion(
                bm25_chapters=bm25_res.get("candidate_chapters", []),
                semantic_chapters=sem_res.get("candidate_chapters", []),
                top_k=10,
                query_text=normalized_text,
                query_facts=query_facts
            )
            fusion_method = "rrf_fusion"
        timings["stage_e_fusion_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)

        # -------------------------------------------------------------
        # STAGE D: Local LLM Reranker (GIR Disambiguation)
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        llm_out: Optional[LLMRerankResult] = None
        if fused_candidates:
            llm_out = self.llm_reranker.rerank(raw_name, fused_candidates)
        timings["stage_d_llm_rerank_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)

        # -------------------------------------------------------------
        # STAGE E (Final Decision & Task 8 Agreement Gate)
        # -------------------------------------------------------------
        rerank_model = None
        # Extract winners for Agreement Gate
        bm25_win = bm25_res.get("candidate_chapters", [{}])[0].get("chapter") if bm25_res.get("candidate_chapters") else None
        sem_win = sem_res.get("candidate_chapters", [{}])[0].get("chapter") if sem_res.get("candidate_chapters") else None
        art_signals = query_facts.get("vocabulary_candidate_chapters", [])

        if llm_out and llm_out.chapter and llm_out.chapter in VALID_CLASSIFIABLE_CHAPTERS:
            selected_chapter = llm_out.chapter
            final_conf = llm_out.confidence
            final_reason = llm_out.reason
            rerank_model = llm_out.model_used
            status = "OK" if final_conf >= 0.50 else "ABSTAIN"
        elif fused_candidates:
            top_cand = fused_candidates[0]
            selected_chapter = top_cand["chapter"]
            final_conf = top_cand["confidence"]
            raw_status, abstention_reason = evaluate_abstention(
                candidates=fused_candidates,
                lexical_winner=bm25_win,
                dense_winner=sem_win,
                article_signal_chapters=art_signals
            )
            status = "OK" if raw_status in ("OK", "PREDICTED") else "ABSTAIN"
            final_reason = (
                f"Statistical consensus from lexical and semantic tariff matching. {abstention_reason}"
            )
            rerank_model = fusion_method
        else:
            selected_chapter = "99"
            final_conf = 0.0
            status = "ABSTAIN"
            final_reason = "No matching statutory chapters retrieved."

        # Collect Evidence Tariff Lines
        evidence_lines: List[TariffEvidence] = []
        matching_cand = next((c for c in fused_candidates if c["chapter"] == selected_chapter), None)
        if matching_cand and matching_cand.get("evidence_lines"):
            for line in matching_cand["evidence_lines"][:5]:
                evidence_lines.append(TariffEvidence(
                    hsn_code=line["hsn_code"],
                    description=line["description"],
                    score=float(line.get("score", 0.0))
                ))
        elif sem_res.get("top_tariff_lines"):
            for line in sem_res["top_tariff_lines"][:3]:
                evidence_lines.append(TariffEvidence(
                    hsn_code=line["hsn_code"],
                    description=line["description"],
                    score=float(line.get("score", 0.0))
                ))

        # Collect Top-3 Alternatives (excluding the selected chapter)
        alternatives: List[ChapterAlternative] = []
        for cand in fused_candidates:
            ch_code = cand["chapter"]
            if ch_code == selected_chapter:
                continue
            alternatives.append(ChapterAlternative(
                chapter=ch_code,
                title=cand["chapter_title"] or self.chapter_titles.get(ch_code, ""),
                score=round(cand["confidence"], 3)
            ))
            if len(alternatives) >= top_k:
                break

        ch_title = self.chapter_titles.get(selected_chapter, f"Chapter {selected_chapter}")
        timings["total_pipeline_ms"] = round((time.perf_counter() - t_start) * 1000.0, 2)

        return ChapterPrediction(
            product_name=raw_name,
            normalized=normalized_text,
            chapter=selected_chapter,
            chapter_title=ch_title,
            confidence=round(final_conf, 3),
            status=status,
            alternatives=alternatives,
            evidence=evidence_lines,
            reason=final_reason,
            stage_timings_ms=timings,
            rerank_model_used=rerank_model
        )

    def predict_batch(self, product_names: List[str], top_k: int = 3) -> List[ChapterPrediction]:
        """
        Executes batch Chapter prediction for a list of product names (max 500).
        """
        results = []
        for name in product_names[:500]:
            pred = self.predict(name, top_k=top_k)
            results.append(pred)
        return results

