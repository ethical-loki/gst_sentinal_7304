"""
Layer 2 & Layer 3: Hybrid Retrieval & Cross-Encoder Re-Ranking Engine
=====================================================================
Implements:
- Layer 2A: Weighted BM25 (Heading 3.0x, Synonyms 2.5x, Chapter 1.5x, Sub-clause 1.0x)
- Layer 2B: Dense Vector Semantic Search (MiniLM-L6-v2 across exact Master records with SHA-256 verification)
- Layer 2C: Reciprocal Rank Fusion (RRF, k=60)
- Layer 3A: Cross-Encoder Re-Ranking (cross-encoder/ms-marco-MiniLM-L-6-v2)
- Layer 3B: File-Driven Keyword & Material Alignment (Strict column alignment, zero product-specific rules)
- Layer 3C: Dynamic Thresholding & Sibling Deduplication
"""

import os
import re
import math
import json
import hashlib
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
    """Lightweight whitespace & punctuation tokenizer with stopword suppression and hyphenated compound preservation."""
    if not text:
        return []
    clean = text.lower()
    # Expand single-character hyphenated compounds (e.g. t-shirt -> tshirts shirt, v-neck -> vneck neck)
    clean = re.sub(r"\b([a-zA-Z0-9])-([a-zA-Z0-9]+)\b", r"\1\2 \2", clean)
    words = re.findall(r"\b[a-zA-Z0-9]{2,}\b", clean)
    return [w for w in words if w not in STOPWORDS]


class HybridHSNEngine:
    """
    Singleton Hybrid HSN Retrieval & Precision Re-Ranking Engine.
    Operates strictly on the authoritative Master dataset with row-level SHA-256 integrity.
    """
    _instance: Optional["HybridHSNEngine"] = None

    def __init__(self):
        base_dir = Path(__file__).resolve().parent.parent.parent
        self.raw_master_path = base_dir / "data" / "raw" / "Master_copy_hsn.xlsx"
        self.enriched_parquet_path = base_dir / "data" / "enriched_master_hsn.parquet"

        if not self.raw_master_path.exists():
            raise FileNotFoundError(f"Master HSN file missing at {self.raw_master_path}")

        # Compute SHA-256 file hash of the authoritative Master file
        hasher = hashlib.sha256()
        with open(self.raw_master_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        self.file_hash = hasher.hexdigest()

        # Load or generate enriched dataset
        if not self.enriched_parquet_path.exists():
            from src.search.normalization import MasterHSNEnricher
            enricher = MasterHSNEnricher(raw_excel_path=self.raw_master_path)
            enricher.process()
            enricher.save(self.enriched_parquet_path)

        self.df = pd.read_parquet(self.enriched_parquet_path)
        self.records = self.df.to_dict(orient="records")
        self.total_records = len(self.records)

        # 1. Initialize BM25 Multi-Field Corpora from the exact records
        from rank_bm25 import BM25Okapi
        self.corpus_heading = [
            tokenize(f"{r.get('heading_4digit_desc', '')} {r.get('subheading_6digit_desc', '')}")
            for r in self.records
        ]
        self.corpus_synonyms = [tokenize(r.get("consumer_synonyms", "")) for r in self.records]
        self.corpus_chapter = [tokenize(r.get("chapter_title", "")) for r in self.records]
        self.corpus_subclause = [
            tokenize(
                f"{r.get('tariff_item_desc', '')} {r.get('statutory_description', '')} "
                f"{r.get('article_keywords', '')} {r.get('material_keywords', '')}"
            )
            for r in self.records
        ]

        self.bm25_heading = BM25Okapi(self.corpus_heading)
        self.bm25_synonyms = BM25Okapi(self.corpus_synonyms)
        self.bm25_chapter = BM25Okapi(self.corpus_chapter)
        self.bm25_subclause = BM25Okapi(self.corpus_subclause)

        # 2. Embedding Model for Query & Document Encoding
        from sentence_transformers import SentenceTransformer
        self.embedding_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2", local_files_only=True)

        # 3. Dense Embeddings row-for-row cache keyed by Master file hash
        cache_dir = base_dir / "data" / "intent_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_npy = cache_dir / f"master_embeddings_{self.file_hash[:16]}.npy"
        self.cache_meta = cache_dir / f"master_embeddings_meta_{self.file_hash[:16]}.json"

        if self.cache_npy.exists() and self.cache_meta.exists():
            try:
                with open(self.cache_meta, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                if meta.get("file_hash") == self.file_hash and meta.get("total_records") == self.total_records:
                    self.dense_embeddings = np.load(self.cache_npy)
                    if self.dense_embeddings.shape[0] != self.total_records:
                        raise ValueError(f"Shape mismatch: {self.dense_embeddings.shape[0]} vs {self.total_records}")
                else:
                    self._build_and_cache_dense_embeddings()
            except Exception as e:
                logger.warning(f"Failed loading cached dense embeddings ({e}). Rebuilding...")
                self._build_and_cache_dense_embeddings()
        else:
            self._build_and_cache_dense_embeddings()

        # Normalize dense embeddings
        norms = np.linalg.norm(self.dense_embeddings, axis=1, keepdims=True)
        norms[norms == 0] = 1e-10
        self.dense_embeddings = self.dense_embeddings / norms

        # 4. Cross-Encoder Model (prefer promoted V2 fine-tuned checkpoint from ModelRegistry)
        self._using_v2_reranker = False
        try:
            from sentence_transformers import CrossEncoder
            from src.ml.model_registry import ModelRegistry
            active_path = ModelRegistry().get_active_model_path()
            if active_path and Path(active_path).exists():
                self.cross_encoder = CrossEncoder(active_path, max_length=144, local_files_only=True)
                self._using_v2_reranker = True
                logger.info(f"[HybridHSNEngine] Loaded V2 fine-tuned CrossEncoder from {active_path}")
            else:
                self.cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2", local_files_only=True)
        except Exception as e:
            logger.warning(f"Cross-encoder load skipped: {e}")
            self.cross_encoder = None

        # Build corpus vocabulary frequencies for general morphological prefix expansion
        self._vocab_freq: Dict[str, int] = {}
        for bm in (self.bm25_heading, self.bm25_synonyms, self.bm25_subclause):
            for tok, freq in getattr(bm, "idf", {}).items():
                if len(tok) >= 4:
                    self._vocab_freq[tok] = self._vocab_freq.get(tok, 0) + 1

        logger.info(f"[HybridHSNEngine] Ready with {self.total_records} master records (hash: {self.file_hash[:16]}).")

    def _expand_abbreviated_query(self, raw_query: str) -> tuple[str, List[str]]:
        """
        General corpus-driven morphological prefix expansion for abbreviated tokens
        ending with a period (e.g. 'auxi.' -> 'auxiliary', 'mach.' -> 'machinery').
        Uses only the indexed tariff vocabulary; no product-specific dictionaries.
        """
        q_lower = (raw_query or "").strip().lower()
        base_tokens = tokenize(q_lower)
        prefixes = re.findall(r"\b([a-z]{3,7})\.", q_lower)
        if not prefixes or not self._vocab_freq:
            return q_lower, base_tokens

        expanded_words: List[str] = []
        extra_tokens: List[str] = []
        for pref in prefixes:
            matches = [
                w for w in self._vocab_freq
                if w.startswith(pref) and len(w) > len(pref)
            ]
            # Prefer shorter/more common statutory root forms first
            matches.sort(key=lambda w: (len(w), w))
            for m in matches[:2]:
                if m not in base_tokens and m not in extra_tokens:
                    extra_tokens.append(m)
                    expanded_words.append(m)

        expanded_q = f"{q_lower} {' '.join(expanded_words)}".strip() if expanded_words else q_lower
        return expanded_q, base_tokens + extra_tokens

    def _build_and_cache_dense_embeddings(self):
        """Builds dense embeddings for all rows in the loaded Master dataset."""
        logger.info(f"Computing row-level dense embeddings for {self.total_records} Master records...")
        texts = [
            f"{r.get('chapter_title', '')} | {r.get('heading_4digit_desc', '')} | {r.get('statutory_description', '')} | {r.get('consumer_synonyms', '')} | {r.get('material_keywords', '')}"
            for r in self.records
        ]
        self.dense_embeddings = self.embedding_model.encode(
            texts,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True
        )
        np.save(self.cache_npy, self.dense_embeddings)
        with open(self.cache_meta, "w", encoding="utf-8") as f:
            json.dump({
                "file_hash": self.file_hash,
                "total_records": self.total_records,
                "embedding_model": "sentence-transformers/all-MiniLM-L6-v2"
            }, f, indent=2)

    @classmethod
    def get_instance(cls) -> "HybridHSNEngine":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _fuse_with_scores(
        self, raw_query: str, pool_size: int = 15, branch_k: int = 20
    ):
        """
        Executes Layer 2 Hybrid Retrieval (Weighted BM25 + Dense Embeddings + RRF)
        and returns (candidate_indices, bm25_composite, cos_sims, rrf_map, clean_query).
        """
        q, q_tokens = self._expand_abbreviated_query(raw_query)
        if not q or not q_tokens:
            return [], None, None, {}, q

        # Layer 2A: Weighted BM25 Lexical Retrieval
        s_head = np.array(self.bm25_heading.get_scores(q_tokens))
        s_syn = np.array(self.bm25_synonyms.get_scores(q_tokens))
        s_chap = np.array(self.bm25_chapter.get_scores(q_tokens))
        s_sub = np.array(self.bm25_subclause.get_scores(q_tokens))

        def min_max(arr: np.ndarray) -> np.ndarray:
            denom = arr.max() - arr.min()
            if denom <= 0:
                return np.zeros_like(arr)
            return (arr - arr.min()) / denom

        bm25_composite = (
            3.0 * min_max(s_head) +
            2.5 * min_max(s_syn) +
            1.5 * min_max(s_chap) +
            1.0 * min_max(s_sub)
        )
        top_bm25_indices = np.argsort(bm25_composite)[::-1][:branch_k]

        # Layer 2B: Dense Vector Semantic Search
        q_emb = self.embedding_model.encode([q], convert_to_numpy=True, normalize_embeddings=True)[0]
        cos_sims = np.dot(self.dense_embeddings, q_emb)
        top_vector_indices = np.argsort(cos_sims)[::-1][:branch_k]

        # Layer 2C: Reciprocal Rank Fusion (RRF, k=60)
        k_rrf = 60.0
        rrf_map: Dict[int, float] = {}
        for rank, idx in enumerate(top_bm25_indices):
            rrf_map[idx] = rrf_map.get(idx, 0.0) + (1.0 / (k_rrf + rank + 1))
        for rank, idx in enumerate(top_vector_indices):
            rrf_map[idx] = rrf_map.get(idx, 0.0) + (1.0 / (k_rrf + rank + 1))

        candidate_indices = sorted(rrf_map.keys(), key=lambda i: rrf_map[i], reverse=True)[:pool_size]
        return candidate_indices, bm25_composite, cos_sims, rrf_map, q

    def retrieve_pool(
        self, raw_query: str, pool_size: int = 40, branch_k: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Returns the raw Layer 2 candidate pool (without Cross-Encoder reranking)
        for retrieval coverage diagnostics (e.g. Recall@15, Recall@40).
        """
        indices, _, _, _, _ = self._fuse_with_scores(raw_query, pool_size=pool_size, branch_k=branch_k)
        return [dict(self.records[idx]) for idx in indices]

    @staticmethod
    def _extract_stage1_representations(
        raw_query: str, stage1_result: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Extracts separate, non-diluted Stage 1 representations and chapter weights."""
        if not isinstance(stage1_result, dict):
            return {
                "primary_anchor": raw_query,
                "alias_text": "",
                "material_text": "",
                "function_text": "",
                "component_text": "",
                "chapter_weights": {},
            }

        s2_repr = stage1_result.get("stage2_search_representation") or {}
        mat_comp = stage1_result.get("materials_and_composition") or {}
        comp_rel = stage1_result.get("components_and_relationships") or {}
        chars = stage1_result.get("characteristics") or {}

        anchor = str(
            s2_repr.get("primary_commercial_product")
            or stage1_result.get("primary_commercial_article")
            or ""
        ).strip()

        # Primary anchor keeps raw_query + primary commercial article (deduplicated), never diluted with secondary fields
        anchor_terms: List[str] = []
        seen_tok: Set[str] = set()
        for part in (raw_query, anchor):
            for tok in str(part or "").split():
                tl = tok.lower()
                if tl not in seen_tok:
                    seen_tok.add(tl)
                    anchor_terms.append(tok)
        primary_anchor = " ".join(anchor_terms) if anchor_terms else raw_query

        aliases = [
            str(a).strip()
            for a in (
                stage1_result.get("alternative_names_and_aliases")
                or s2_repr.get("product_identity_and_aliases")
                or []
            )
            if str(a).strip() and str(a).strip().lower() != anchor.lower()
        ]
        materials = [
            str(m).strip()
            for m in (
                mat_comp.get("constituent_materials")
                or s2_repr.get("constituent_materials")
                or []
            )
            if str(m).strip()
        ]
        form_parts = [
            str(chars.get("physical_form") or "").strip(),
            str(chars.get("processing_state") or "").strip(),
        ]
        material_text = " ".join(materials + [p for p in form_parts if p])
        function_text = str(
            chars.get("function_use")
            or s2_repr.get("function_and_application")
            or ""
        ).strip()

        components = [
            str(c).strip()
            for c in (
                comp_rel.get("components_or_parts")
                or s2_repr.get("integrated_components")
                or []
            )
            if str(c).strip()
        ]
        rel_targets = [
            str(r.get("target") or "").strip()
            for r in (comp_rel.get("relationship_graph") or [])
            if isinstance(r, dict) and r.get("target")
        ]
        component_text = " ".join(components + rel_targets)

        chapter_weights: Dict[str, float] = {}
        for ch_item in stage1_result.get("chapter_candidates") or []:
            if isinstance(ch_item, dict) and ch_item.get("chapter_code"):
                ch_code = str(ch_item["chapter_code"]).zfill(2)
                conf = float(ch_item.get("confidence") or ch_item.get("relevance_score") or 0.5)
                chapter_weights[ch_code] = max(chapter_weights.get(ch_code, 0.0), min(1.0, conf))

        return {
            "primary_anchor": primary_anchor,
            "alias_text": " ".join(aliases[:4]),
            "material_text": material_text,
            "function_text": function_text,
            "component_text": component_text,
            "chapter_weights": chapter_weights,
        }

    def retrieve_with_lineage(
        self, raw_query: str, branch_k: int = 30, stage1_result: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Phase 7 + Structured Stage 1->2 Adaptive Retrieval:
        Uses separate weighted representations (primary anchor, aliases, materials/form,
        function, components) and two complementary retrieval paths:
          Path A: Chapter-allocated retrieval inside Stage 1 chapter_candidates
          Path B: Global safeguard retrieval across the entire statutory master
        Merges and deduplicates both pools with full provenance.
        """
        reps = self._extract_stage1_representations(raw_query, stage1_result)
        q, q_tokens = self._expand_abbreviated_query(reps["primary_anchor"])
        if not q or not q_tokens:
            return []

        def min_max(arr: np.ndarray) -> np.ndarray:
            denom = arr.max() - arr.min()
            if denom <= 0:
                return np.zeros_like(arr)
            return (arr - arr.min()) / denom

        s_head = np.array(self.bm25_heading.get_scores(q_tokens))
        s_syn = np.array(self.bm25_synonyms.get_scores(q_tokens))
        s_chap = np.array(self.bm25_chapter.get_scores(q_tokens))
        s_sub = np.array(self.bm25_subclause.get_scores(q_tokens))

        bm25_primary = (
            3.0 * min_max(s_head) +
            2.5 * min_max(s_syn) +
            1.5 * min_max(s_chap) +
            1.0 * min_max(s_sub)
        )

        # Secondary representations weighted strictly below the primary commercial article anchor
        secondary_bm25 = np.zeros_like(bm25_primary)
        for rep_text, weight in (
            (reps["alias_text"], 0.20),
            (reps["material_text"], 0.12),
            (reps["function_text"], 0.10),
            (reps["component_text"], 0.04),
        ):
            if rep_text:
                _, rep_toks = self._expand_abbreviated_query(rep_text)
                if rep_toks:
                    sec_h = min_max(np.array(self.bm25_heading.get_scores(rep_toks)))
                    sec_s = min_max(np.array(self.bm25_subclause.get_scores(rep_toks)))
                    secondary_bm25 += weight * (0.6 * sec_h + 0.4 * sec_s)

        bm25_composite = bm25_primary + secondary_bm25

        # Dense retrieval anchored on primary commercial product (plus optional alias blend)
        q_emb = self.embedding_model.encode([q], convert_to_numpy=True, normalize_embeddings=True)[0]
        cos_sims = np.dot(self.dense_embeddings, q_emb)
        if reps["alias_text"]:
            alias_q, _ = self._expand_abbreviated_query(reps["alias_text"])
            if alias_q:
                a_emb = self.embedding_model.encode([alias_q], convert_to_numpy=True, normalize_embeddings=True)[0]
                cos_sims = 0.85 * cos_sims + 0.15 * np.dot(self.dense_embeddings, a_emb)

        k_eff = min(max(1, int(branch_k)), self.total_records)
        k_rrf = 60.0

        # Path B: Global Safeguard Retrieval (full statutory master)
        top_bm25_global = np.argsort(bm25_composite)[::-1][:k_eff]
        top_vec_global = np.argsort(cos_sims)[::-1][:k_eff]
        global_bm25_set = set(int(i) for i in top_bm25_global)
        global_vec_set = set(int(i) for i in top_vec_global)

        rrf_map: Dict[int, float] = {}
        global_set: Set[int] = set()
        for rank, idx in enumerate(top_bm25_global):
            i = int(idx)
            global_set.add(i)
            rrf_map[i] = rrf_map.get(i, 0.0) + (1.0 / (k_rrf + rank + 1))
        for rank, idx in enumerate(top_vec_global):
            i = int(idx)
            global_set.add(i)
            rrf_map[i] = rrf_map.get(i, 0.0) + (1.0 / (k_rrf + rank + 1))

        # Path A: Chapter-Allocated Retrieval across Stage 1 chapter candidates
        chapter_weights: Dict[str, float] = reps["chapter_weights"]
        guided_chapters: Set[str] = set(chapter_weights.keys())
        chapter_set: Set[int] = set()
        chapter_allocations: Dict[str, int] = {}

        if chapter_weights:
            total_w = sum(chapter_weights.values()) or 1.0
            total_ch_budget = max(k_eff, len(chapter_weights) * 5)
            # Pre-index row indices per guided chapter once
            rows_by_ch: Dict[str, List[int]] = {ch: [] for ch in chapter_weights}
            for idx_r, rec_r in enumerate(self.records):
                ch_r = str(rec_r.get("chapter_code") or "").zfill(2)
                if ch_r in rows_by_ch:
                    rows_by_ch[ch_r].append(idx_r)

            for ch_code, ch_conf in sorted(chapter_weights.items(), key=lambda kv: -kv[1]):
                ch_indices = rows_by_ch.get(ch_code, [])
                if not ch_indices:
                    continue
                alloc = max(5 if k_eff >= 15 else 2, int(round(total_ch_budget * (ch_conf / total_w))))
                alloc = min(alloc, len(ch_indices))
                chapter_allocations[ch_code] = alloc

                ch_arr = np.array(ch_indices, dtype=int)
                ch_bm25_order = ch_arr[np.argsort(bm25_composite[ch_arr])[::-1][:alloc]]
                ch_vec_order = ch_arr[np.argsort(cos_sims[ch_arr])[::-1][:alloc]]

                for rank, idx in enumerate(ch_bm25_order):
                    i = int(idx)
                    chapter_set.add(i)
                    rrf_map[i] = rrf_map.get(i, 0.0) + (0.65 / (k_rrf + rank + 1)) + (0.004 * ch_conf)
                for rank, idx in enumerate(ch_vec_order):
                    i = int(idx)
                    chapter_set.add(i)
                    rrf_map[i] = rrf_map.get(i, 0.0) + (0.65 / (k_rrf + rank + 1)) + (0.004 * ch_conf)

        ordered = sorted(rrf_map.keys(), key=lambda i: rrf_map[i], reverse=True)
        out: List[Dict[str, Any]] = []
        for idx in ordered:
            rec = dict(self.records[idx])
            ch = str(rec.get("chapter_code") or "").zfill(2)
            in_b = idx in global_bm25_set and float(bm25_composite[idx]) > 0.0
            in_d = idx in global_vec_set
            in_ch_path = idx in chapter_set
            in_gl_path = idx in global_set

            if in_ch_path and in_gl_path:
                retrieval_path = "chapter_guided+global"
            elif in_ch_path:
                retrieval_path = "chapter_guided"
            else:
                retrieval_path = "global_safeguard"

            src = "bm25+dense" if (in_b and in_d) else ("bm25" if in_b else ("dense" if in_d else "chapter_allocated"))
            is_guided = bool(guided_chapters) and (ch in guided_chapters)
            is_cross = bool(guided_chapters) and (ch not in guided_chapters)
            rec["source_record_id"] = f"row_{idx}"
            rec["retrieval_source"] = src
            rec["retrieval_path"] = retrieval_path
            rec["chapter_allocated_slots"] = chapter_allocations.get(ch, 0)
            rec["bm25_score"] = round(float(bm25_composite[idx]), 4)
            rec["vector_score"] = round(float(cos_sims[idx]), 4)
            rec["rrf_score"] = round(float(rrf_map[idx]), 6)
            rec["chapter_guided"] = is_guided
            rec["cross_chapter_discovery"] = is_cross
            rec["cross_chapter_reason"] = (
                f"Cross-chapter candidate (Ch {ch}) surfaced via global safeguard ({src}) outside Stage 1 guided chapters {sorted(guided_chapters)}; requires Stage 3 verification."
                if is_cross
                else ""
            )
            rec["retrieval_explanation"] = (
                f"Path={retrieval_path}, src={src} (bm25={rec['bm25_score']}, dense={rec['vector_score']}, rrf={rec['rrf_score']})"
                + (f" [Chapter Allocated ({chapter_allocations.get(ch, 0)} slots)]" if in_ch_path else "")
                + (" [Cross-Chapter Safeguard]" if is_cross else "")
            )
            out.append(rec)
        return out

    def search(self, raw_query: str, top_k: int = 10) -> List[SearchCandidate]:
        """
        Executes Layer 2 Hybrid Retrieval + Layer 3 Re-Ranking.
        """
        candidate_indices, bm25_composite, cos_sims, rrf_map, q = self._fuse_with_scores(
            raw_query, pool_size=15, branch_k=20
        )
        if not candidate_indices:
            return []

        # Convert indices to SearchCandidate objects
        candidates: List[SearchCandidate] = []
        ce_pairs: List[List[str]] = []

        for idx in candidate_indices:
            r = self.records[idx]
            cand = SearchCandidate(
                hsn_code=str(r.get("hsn_code") or r.get("code_str") or "").strip(),
                chapter_code=str(r.get("chapter_code") or r.get("chapter_str") or "").strip(),
                chapter_title=str(r.get("chapter_title", "")).strip(),
                heading_4digit=str(r.get("heading_4digit", "")),
                heading_4digit_desc=str(r.get("heading_4digit_desc", "")),
                subheading_6digit=str(r.get("subheading_6digit", "")),
                subheading_6digit_desc=str(r.get("subheading_6digit_desc", "")),
                tariff_item_desc=str(r.get("tariff_item_desc", "")),
                statutory_description=str(r.get("statutory_description", "")),
                consumer_synonyms=str(r.get("consumer_synonyms", "")),
                article_keywords=str(r.get("article_keywords", "")),
                material_keywords=str(r.get("material_keywords", "")),
                bm25_score=float(bm25_composite[idx]),
                vector_score=float(cos_sims[idx]),
                rrf_score=float(rrf_map[idx])
            )
            candidates.append(cand)

            # Pair for Cross-Encoder: (query, candidate context)
            cand_context = (
                f"{cand.chapter_title} - {cand.heading_4digit_desc}: "
                f"{cand.statutory_description} | {cand.material_keywords} {cand.article_keywords}"
            )
            ce_pairs.append([q, cand_context])

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
        # Layer 3B: Hybrid Score Fusion & Material Keyword Alignment
        # Combines Stage 2 RRF retrieval (BM25 + Dense) with Cross-Encoder
        # and aligns statutory material keywords from the Master file.
        # -------------------------------------------------------------
        max_rrf = max((c.rrf_score for c in candidates), default=1.0)

        for cand in candidates:
            if self.cross_encoder is not None:
                if getattr(self, "_using_v2_reranker", False):
                    calibrated_prob = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, cand.cross_encoder_score))))
                else:
                    # Calibrate ms-marco logit (mean center ~ -7.5) to [0.0, 1.0]
                    calibrated_prob = 1.0 / (1.0 + math.exp(-(cand.cross_encoder_score + 7.5) / 1.5))
            else:
                calibrated_prob = max(0.0, min(1.0, cand.vector_score))

            norm_rrf = (cand.rrf_score / max_rrf) if max_rrf > 0 else 0.5
            blended_score = 0.45 * norm_rrf + 0.55 * calibrated_prob
            cand.final_score = round(float(blended_score), 4)

        # -------------------------------------------------------------
        # Layer 3C: Dynamic Thresholding & GIR Sibling Deduplication
        # Under GIR 6, 8-digit tariff items inherit subheading relevance,
        # and 6-digit subheadings yield to their concrete 8-digit children.
        # -------------------------------------------------------------
        six_digit_parents = {
            c.hsn_code.replace(" ", ""): c.final_score
            for c in candidates
            if len(c.hsn_code.replace(" ", "")) == 6 and c.final_score >= 0.40
        }
        for cand in candidates:
            c_clean = cand.hsn_code.replace(" ", "")
            if len(c_clean) == 8 and c_clean[:6] in six_digit_parents:
                cand.final_score = max(cand.final_score, round(six_digit_parents[c_clean[:6]] * 0.98, 4))

        filtered_candidates = [c for c in candidates if c.final_score >= 0.40]

        # Prefer specific 8-digit tariff items over their parent 6-digit subheadings under GIR 6
        eight_digit_prefixes = {c.hsn_code.replace(" ", "")[:6] for c in filtered_candidates if len(c.hsn_code.replace(" ", "")) == 8}
        filtered_candidates = [
            c for c in filtered_candidates
            if not (len(c.hsn_code.replace(" ", "")) == 6 and c.hsn_code.replace(" ", "") in eight_digit_prefixes)
        ]

        # Sort descending by final calibrated score
        filtered_candidates.sort(key=lambda c: c.final_score, reverse=True)

        if not filtered_candidates and candidates:
            candidates.sort(key=lambda c: c.final_score, reverse=True)
            filtered_candidates = [candidates[0]]

        return filtered_candidates[:top_k]
