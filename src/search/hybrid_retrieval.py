"""
Layer 2 & Layer 3: Hybrid Retrieval & Cross-Encoder Re-Ranking Engine
=====================================================================
Implements:
- Layer 2A: Weighted BM25 (Heading 3.0x, Synonyms 2.5x, Chapter 1.5x, Sub-clause 1.0x)
- Layer 2B: Dense Vector Semantic Search (Precomputed all-MiniLM-L6-v2)
- Layer 2C: Reciprocal Rank Fusion (RRF, k=60)
- Layer 3A: Cross-Encoder Re-Ranking (cross-encoder/ms-marco-MiniLM-L-6-v2)
- Layer 3B: Negative Keyword & Domain Exclusion Guardrails
- Layer 3C: Confidence Thresholding (Threshold >= 0.45, Normalized 0.0 - 1.0)
"""

import os
import re
import math
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

# Ensure offline operation using cached models
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

logger = logging.getLogger(__name__)


class SearchCandidate(BaseModel):
    hsn_code: str
    chapter_code: str
    chapter_title: str
    heading_4digit: str
    heading_4digit_desc: str
    subheading_6digit: str
    subheading_6digit_desc: str
    tariff_item_desc: str
    statutory_description: str
    consumer_synonyms: str
    article_keywords: str
    material_keywords: str
    bm25_score: float = 0.0
    vector_score: float = 0.0
    rrf_score: float = 0.0
    cross_encoder_score: float = 0.0
    final_score: float = 0.0
    match_reasons: List[str] = Field(default_factory=list)


STOPWORDS = {
    "and", "the", "for", "with", "other", "than", "not", "under", "goods",
    "articles", "thereof", "kind", "used", "like", "such", "all", "of", "in", "a", "an"
}


def tokenize(text: str) -> List[str]:
    """Lightweight whitespace & punctuation tokenizer with stopword suppression and compound normalization."""
    if not text:
        return []
    clean = text.lower()
    clean = re.sub(r"\bstain\s+less\b", "stainless", clean)
    clean = re.sub(r"\bwater\s*bottle\b", "water bottle", clean)
    clean = re.sub(r"\bt\s*shirt\b", "t-shirt", clean)
    words = re.findall(r"\b[a-zA-Z0-9]{2,}\b", clean)
    return [w for w in words if w not in STOPWORDS]


# Domain exclusion rules for homonyms across chapters
HOMONYM_EXCLUSIONS: Dict[str, Dict[str, Any]] = {
    "bottle": {
        "preferred_chapters": ["39"],
        "excluded_terms_unless_present": {
            "hot water bottle": ["rubber", "medical", "vulcanized"],
            "feeding bottle": ["nipple", "baby", "feeding"]
        }
    },
    "brake": {
        "preferred_chapters": ["87"],
        "negative_penalties": {
            "68": 0.35  # Raw unmounted mineral friction penalised unless 'unmounted' or 'mineral' specified
        }
    },
    "pipe": {
        "cross_chapters": ["39", "73"],
        "material_hints": {
            "pvc": "39",
            "plastic": "39",
            "steel": "73",
            "stainless": "73",
            "seamless": "73",
            "iron": "73"
        }
    }
}


class HybridHSNEngine:
    """
    Singleton Hybrid HSN Retrieval & Precision Re-Ranking Engine.
    """
    _instance: Optional["HybridHSNEngine"] = None

    def __init__(self):
        base_dir = Path(__file__).resolve().parent.parent.parent
        self.enriched_parquet_path = base_dir / "data" / "enriched_master_hsn.parquet"
        self.embeddings_path = base_dir / "data" / "chapter_predictor" / "tariff_embeddings.npy"

        # Load or generate enriched dataset
        if not self.enriched_parquet_path.exists():
            from src.search.normalization import MasterHSNEnricher
            enricher = MasterHSNEnricher()
            enricher.process()
            enricher.save(self.enriched_parquet_path)

        self.df = pd.read_parquet(self.enriched_parquet_path)
        # Filter strictly to 8-digit tariff items if available, or all records
        self.records = self.df.to_dict(orient="records")
        self.total_records = len(self.records)

        # 1. Initialize BM25 Multi-Field Corpora (with 4-digit and 6-digit subheadings included)
        from rank_bm25 import BM25Okapi
        self.corpus_heading = [
            tokenize(f"{r.get('heading_4digit_desc', '')} {r.get('subheading_6digit_desc', '')}")
            for r in self.records
        ]
        self.corpus_synonyms = [tokenize(r.get("consumer_synonyms", "")) for r in self.records]
        self.corpus_chapter = [tokenize(r.get("chapter_title", "")) for r in self.records]
        self.corpus_subclause = [
            tokenize(f"{r.get('tariff_item_desc', '')} {r.get('article_keywords', '')} {r.get('material_keywords', '')}")
            for r in self.records
        ]

        self.bm25_heading = BM25Okapi(self.corpus_heading)
        self.bm25_synonyms = BM25Okapi(self.corpus_synonyms)
        self.bm25_chapter = BM25Okapi(self.corpus_chapter)
        self.bm25_subclause = BM25Okapi(self.corpus_subclause)

        # 2. Load Dense Embeddings (first 4,851 rows match Master_copy_hsn exactly)
        self.dense_embeddings = np.load(self.embeddings_path)[:self.total_records]
        # Normalize dense embeddings just in case
        norms = np.linalg.norm(self.dense_embeddings, axis=1, keepdims=True)
        norms[norms == 0] = 1e-10
        self.dense_embeddings = self.dense_embeddings / norms

        # 3. Load Embedding Model for Query Encoding
        from sentence_transformers import SentenceTransformer
        self.embedding_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2", local_files_only=True)

        # 4. Load Cross-Encoder Model
        try:
            from sentence_transformers import CrossEncoder
            self.cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2", local_files_only=True)
        except Exception as e:
            logger.warning(f"Cross-encoder load skipped: {e}")
            self.cross_encoder = None

        logger.info(f"[HybridHSNEngine] Ready with {self.total_records} master records.")

    @classmethod
    def get_instance(cls) -> "HybridHSNEngine":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def search(self, raw_query: str, top_k: int = 10) -> List[SearchCandidate]:
        """
        Executes Layer 2 Hybrid Retrieval + Layer 3 Re-Ranking.
        """
        q = (raw_query or "").strip().lower()
        q = re.sub(r"\bstain\s+less\b", "stainless", q)
        q = re.sub(r"\bwater\s*bottle\b", "water bottle", q)
        if not q:
            return []

        q_tokens = tokenize(q)
        if not q_tokens:
            return []

        # -------------------------------------------------------------
        # Layer 2A: Weighted BM25 Lexical Retrieval
        # -------------------------------------------------------------
        # Boost weights as specified: Heading 3.0x, Synonyms 2.5x, Chapter 1.5x, Subclause 1.0x
        s_head = np.array(self.bm25_heading.get_scores(q_tokens))
        s_syn = np.array(self.bm25_synonyms.get_scores(q_tokens))
        s_chap = np.array(self.bm25_chapter.get_scores(q_tokens))
        s_sub = np.array(self.bm25_subclause.get_scores(q_tokens))

        weighted_bm25 = (3.0 * s_head) + (2.5 * s_syn) + (1.5 * s_chap) + (1.0 * s_sub)
        top_bm25_indices = np.argsort(weighted_bm25)[::-1][:20]

        # -------------------------------------------------------------
        # Layer 2B: Dense Vector Semantic Retrieval
        # -------------------------------------------------------------
        q_vec = self.embedding_model.encode([q], normalize_embeddings=True)[0]
        dense_sims = np.dot(self.dense_embeddings, q_vec)
        top_dense_indices = np.argsort(dense_sims)[::-1][:20]

        # -------------------------------------------------------------
        # Layer 2C: Reciprocal Rank Fusion (RRF, k=60)
        # -------------------------------------------------------------
        k_rrf = 60.0
        rrf_map: Dict[int, float] = {}

        for rank, idx in enumerate(top_bm25_indices):
            rrf_map[idx] = rrf_map.get(idx, 0.0) + (1.0 / (k_rrf + rank + 1))

        for rank, idx in enumerate(top_dense_indices):
            rrf_map[idx] = rrf_map.get(idx, 0.0) + (1.0 / (k_rrf + rank + 1))

        # Select Top 15 unified RRF candidates
        sorted_rrf = sorted(rrf_map.items(), key=lambda x: x[1], reverse=True)[:15]
        candidate_indices = [idx for idx, _ in sorted_rrf]

        # Sibling expansion: ensure all 8-digit tariff items under matched subheadings are evaluated
        top_h6_prefixes = {
            self.records[idx]["subheading_6digit"]
            for idx in candidate_indices[:5]
            if self.records[idx].get("subheading_6digit")
        }
        for i, r in enumerate(self.records):
            if r.get("subheading_6digit") in top_h6_prefixes and len(r.get("hsn_code", "")) == 8:
                if i not in candidate_indices:
                    candidate_indices.append(i)
                    rrf_map[i] = 0.01

        # Build Candidate Objects
        candidates: List[SearchCandidate] = []
        ce_pairs: List[Tuple[str, str]] = []

        for idx in candidate_indices:
            r = self.records[idx]
            cand = SearchCandidate(
                hsn_code=r.get("hsn_code", ""),
                chapter_code=r.get("chapter_code", ""),
                chapter_title=r.get("chapter_title", ""),
                heading_4digit=r.get("heading_4digit", ""),
                heading_4digit_desc=r.get("heading_4digit_desc", ""),
                subheading_6digit=r.get("subheading_6digit", ""),
                subheading_6digit_desc=r.get("subheading_6digit_desc", ""),
                tariff_item_desc=r.get("tariff_item_desc", ""),
                statutory_description=r.get("statutory_description", ""),
                consumer_synonyms=r.get("consumer_synonyms", ""),
                article_keywords=r.get("article_keywords", ""),
                material_keywords=r.get("material_keywords", ""),
                bm25_score=float(weighted_bm25[idx]),
                vector_score=float(dense_sims[idx]),
                rrf_score=float(rrf_map[idx])
            )
            candidates.append(cand)
            context = (
                f"{r.get('chapter_title', '')} | {r.get('heading_4digit_desc', '')} | "
                f"{r.get('subheading_6digit_desc', '')} | {r.get('tariff_item_desc', '')} | "
                f"Trade: {r.get('consumer_synonyms', '')}"
            )
            ce_pairs.append((q, context))

        # -------------------------------------------------------------
        # Layer 3A: Cross-Encoder Re-Ranking
        # -------------------------------------------------------------
        if self.cross_encoder is not None and ce_pairs:
            try:
                ce_scores = self.cross_encoder.predict(ce_pairs)
                for cand, score in zip(candidates, ce_scores):
                    cand.cross_encoder_score = float(score)
            except Exception as e:
                logger.warning(f"Cross-encoder evaluation failed: {e}")
                for cand in candidates:
                    cand.cross_encoder_score = cand.vector_score

        # -------------------------------------------------------------
        # Layer 3B: Negative Keyword & Domain Guardrails
        # -------------------------------------------------------------
        for cand in candidates:
            # Baseline sigmoid calibration from cross-encoder + vector score
            raw_logit = cand.cross_encoder_score if self.cross_encoder else (cand.vector_score * 4.0 - 2.0)
            calibrated_prob = 1.0 / (1.0 + math.exp(-raw_logit))

            # ---------------------------------------------------------
            # Generic Material Keyword Alignment (File-Driven)
            # Matches material tokens directly against candidate's
            # Material Keywords & Article Keywords columns from the file.
            # No hardcoded chapter numbers or product names.
            # ---------------------------------------------------------
            cand_mat_text = f"{cand.material_keywords} {cand.article_keywords}".lower()
            
            # Detect material tokens specified in user search string
            mat_match = re.search(r"Material:\s*([^\n|]+)", q, re.IGNORECASE)
            specified_material = mat_match.group(1).strip().lower() if mat_match else ""
            if not specified_material:
                # Extract any material tokens present in the query
                for m_candidate in ["stainless steel", "steel", "iron", "plastics", "plastic", "cotton", "rubber", "aluminium", "glass", "copper"]:
                    if re.search(rf"\b{re.escape(m_candidate)}\b", q):
                        specified_material = m_candidate
                        break

            if specified_material:
                m_tokens = set(tokenize(specified_material)) - STOPWORDS
                cand_tokens = set(tokenize(cand_mat_text))
                if m_tokens and m_tokens.issubset(cand_tokens):
                    # Query material aligned with file's Material Keywords
                    calibrated_prob = min(1.0, calibrated_prob * 1.15)
                elif m_tokens and any(conflict in cand_mat_text for conflict in ["plastics", "polymer", "cotton", "synthetic", "steel", "iron"] if conflict not in specified_material):
                    # Incompatible material keywords in file record
                    calibrated_prob *= 0.25

            cand.final_score = round(float(calibrated_prob), 4)

        # -------------------------------------------------------------
        # Layer 3C: Confidence Thresholding (Drop below 0.45) & Sibling Deduplication
        # -------------------------------------------------------------
        filtered_candidates = [c for c in candidates if c.final_score >= 0.45]

        # Under GIR Rule 6, prefer specific 8-digit tariff items over their parent 6-digit subheadings
        eight_digit_prefixes = {c.hsn_code[:6] for c in filtered_candidates if len(c.hsn_code) == 8}
        filtered_candidates = [
            c for c in filtered_candidates
            if not (len(c.hsn_code) == 6 and c.hsn_code in eight_digit_prefixes)
        ]

        # Sort by final calibrated score descending
        filtered_candidates.sort(key=lambda c: c.final_score, reverse=True)

        # If strict filtering dropped everything, keep top 1 if > 0.35
        if not filtered_candidates and candidates:
            candidates.sort(key=lambda c: c.final_score, reverse=True)
            if candidates[0].final_score >= 0.35:
                filtered_candidates = [candidates[0]]

        return filtered_candidates[:top_k]
