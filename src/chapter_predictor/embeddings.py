"""
src/chapter_predictor/embeddings.py
===================================
Stage C: Semantic Retrieval via Local Embeddings & Vector Cache.

Features:
- Primary Model: BAAI/bge-m3
- Fallbacks: intfloat/multilingual-e5-large, BAAI/bge-small-en-v1.5, all-MiniLM-L6-v2.
- Embeds all 19,396 statutory descriptions and all 99 chapter titles once.
- Persists normalized embedding matrices to disk (.npy) and reloads on startup.
- Computes cosine similarity, retrieves top 50 tariff lines, and aggregates by chapter.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
EMBEDDINGS_CACHE_DIR = ROOT_DIR / "data" / "chapter_predictor"
TARIFF_EMBEDDINGS_FILE = EMBEDDINGS_CACHE_DIR / "tariff_embeddings.npy"
CHAPTER_EMBEDDINGS_FILE = EMBEDDINGS_CACHE_DIR / "chapter_embeddings.npy"
METADATA_FILE = EMBEDDINGS_CACHE_DIR / "tariff_metadata.json"

PREFERRED_MODELS = [
    os.environ.get("CHAPTER_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"),
    "BAAI/bge-small-en-v1.5",
    "BAAI/bge-m3",
    "intfloat/multilingual-e5-large"
]


class SemanticTariffIndex:
    """
    Semantic vector index using sentence-transformers dense embeddings.
    """
    def __init__(self, cache_dir: Path = EMBEDDINGS_CACHE_DIR):
        self.cache_dir = Path(cache_dir)
        self.model = None
        self.model_name = None
        self.tariff_embeddings: Optional[np.ndarray] = None  # shape: (N, D), L2-normalized
        self.chapter_embeddings: Optional[np.ndarray] = None  # shape: (99, D), L2-normalized
        self.chapter_codes: List[str] = []
        self.records: List[Dict[str, Any]] = []
        self.chapter_titles: Dict[str, str] = {}
        self._is_loaded = False

    def _load_model(self):
        """Loads the embedding model with graceful offline fallback."""
        if self.model is not None:
            return self.model

        from sentence_transformers import SentenceTransformer
        import torch
        try:
            torch.set_num_threads(min(8, os.cpu_count() or 4))
        except Exception:
            pass

        # Prioritize locally cached models first if offline
        for candidate in PREFERRED_MODELS:
            try:
                logger.info(f"Attempting to load embedding model: {candidate}...")
                self.model = SentenceTransformer(candidate)
                self.model.max_seq_length = 64
                self.model_name = candidate
                logger.info(f"Successfully loaded embedding model: {candidate} (max_seq_length=64)")
                return self.model
            except Exception as e:
                logger.warning(f"Could not load embedding model {candidate}: {e}")

        # Final safety fallback
        try:
            self.model = SentenceTransformer("all-MiniLM-L6-v2")
            self.model.max_seq_length = 64
            self.model_name = "all-MiniLM-L6-v2"
            return self.model
        except Exception as e:
            logger.error(f"Failed to load any sentence transformer model: {e}")
            raise RuntimeError(f"Embedding model initialization failed: {e}")

    def load_or_build(self, force_rebuild: bool = False):
        """Loads cached vectors from disk or computes and persists them."""
        if self._is_loaded and not force_rebuild:
            return

        tariff_npy = self.cache_dir / "tariff_embeddings.npy"
        chapter_npy = self.cache_dir / "chapter_embeddings.npy"
        meta_json = self.cache_dir / "tariff_metadata.json"

        if (
            tariff_npy.exists()
            and chapter_npy.exists()
            and meta_json.exists()
            and not force_rebuild
        ):
            try:
                self.tariff_embeddings = np.load(tariff_npy)
                self.chapter_embeddings = np.load(chapter_npy)
                with open(meta_json, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                    self.records = meta["records"]
                    self.chapter_titles = meta["chapter_titles"]
                    self.chapter_codes = meta["chapter_codes"]
                    self.model_name = meta.get("model_name", "unknown")
                self._is_loaded = True
                logger.info(
                    f"Loaded vector index from {self.cache_dir} "
                    f"({len(self.records)} tariff items, {len(self.chapter_codes)} chapters)"
                )
                return
            except Exception as e:
                logger.warning(f"Failed to load embedding cache: {e}. Rebuilding...")

        self.build_index()

    def build_index(self):
        """Generates embeddings for all 19,396 tariff lines + 99 chapter titles."""
        import pandas as pd
        import re

        self._load_model()

        # Load clean chapter titles
        titles_path = ROOT_DIR / "src" / "chapter_predictor" / "chapter_titles.json"
        if titles_path.exists():
            with open(titles_path, "r", encoding="utf-8") as f:
                self.chapter_titles = json.load(f)

        excel_path = ROOT_DIR / "data" / "raw" / "Final_Copy_hsn_7304.xlsx"
        if not excel_path.exists():
            excel_path = ROOT_DIR / "data" / "raw" / "HSN_SAC (1).xlsx"

        df = pd.read_excel(excel_path)
        code_col = df.columns[0]
        desc_col = df.columns[1]

        records = []
        texts_to_embed = []

        for idx, row in df.iterrows():
            raw_c = str(row[code_col]).strip()
            desc = str(row[desc_col] or "").strip()
            clean_digits = re.sub(r"\D", "", raw_c)

            if len(clean_digits) == 1:
                clean_digits = clean_digits.zfill(2)
            elif len(clean_digits) == 3:
                clean_digits = clean_digits.zfill(4)
            elif len(clean_digits) == 5:
                clean_digits = clean_digits.zfill(6)
            elif len(clean_digits) == 7:
                clean_digits = clean_digits.zfill(8)

            ch = clean_digits[:2] if len(clean_digits) >= 2 else "99"
            ch_title = self.chapter_titles.get(ch, "")

            if len(clean_digits) == 8:
                formatted_code = f"{clean_digits[:4]} {clean_digits[4:6]} {clean_digits[6:]}"
            elif len(clean_digits) == 6:
                formatted_code = f"{clean_digits[:4]} {clean_digits[4:]}"
            else:
                formatted_code = clean_digits

            rec = {
                "idx": idx,
                "hsn_raw": clean_digits,
                "hsn_code": formatted_code,
                "description": desc,
                "chapter": ch,
                "chapter_title": ch_title
            }
            records.append(rec)
            # Embedding representation: Chapter Title + Statutory Description
            text_repr = f"Chapter {ch}: {ch_title}. Tariff: {desc}".strip()
            texts_to_embed.append(text_repr)

        # 1. Embed tariff records
        logger.info(f"Encoding {len(texts_to_embed)} tariff lines with {self.model_name}...")
        tariff_vecs = self.model.encode(
            texts_to_embed,
            batch_size=128,
            show_progress_bar=True,
            normalize_embeddings=True
        )
        self.tariff_embeddings = np.array(tariff_vecs, dtype=np.float32)

        # 2. Embed all 99 chapter titles directly
        sorted_chapter_codes = sorted(self.chapter_titles.keys())
        chapter_texts = [
            f"Chapter {ch}: {self.chapter_titles[ch]}"
            for ch in sorted_chapter_codes
        ]
        logger.info(f"Encoding {len(chapter_texts)} chapter titles...")
        chapter_vecs = self.model.encode(
            chapter_texts,
            batch_size=64,
            show_progress_bar=False,
            normalize_embeddings=True
        )
        self.chapter_embeddings = np.array(chapter_vecs, dtype=np.float32)
        self.chapter_codes = sorted_chapter_codes
        self.records = records
        self._is_loaded = True

        # 3. Persist to cache
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        np.save(self.cache_dir / "tariff_embeddings.npy", self.tariff_embeddings)
        np.save(self.cache_dir / "chapter_embeddings.npy", self.chapter_embeddings)
        with open(self.cache_dir / "tariff_metadata.json", "w", encoding="utf-8") as f:
            json.dump({
                "records": self.records,
                "chapter_titles": self.chapter_titles,
                "chapter_codes": self.chapter_codes,
                "model_name": self.model_name
            }, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved vector index caches to {self.cache_dir}")

    def query(
        self,
        query_text: str,
        top_k_tariff: int = 50,
        top_k_chapters: int = 10
    ) -> Dict[str, Any]:
        """
        Stage C query execution:
        - Encodes normalized query to unit vector
        - Computes cosine similarity across tariff lines & chapter titles
        - Aggregates by chapter, keeping max score and top tariff lines
        """
        if not self._is_loaded:
            self.load_or_build()

        self._load_model()
        q_vec = self.model.encode([query_text], normalize_embeddings=True)[0]
        q_vec = np.array(q_vec, dtype=np.float32)

        # 1. Cosine similarity with tariff descriptions
        tariff_sims = np.dot(self.tariff_embeddings, q_vec)
        top_tariff_indices = np.argsort(tariff_sims)[::-1][:top_k_tariff]

        # 2. Cosine similarity with chapter titles
        chapter_title_sims = np.dot(self.chapter_embeddings, q_vec)
        ch_title_score_map = {
            self.chapter_codes[i]: float(chapter_title_sims[i])
            for i in range(len(self.chapter_codes))
        }

        # 3. Aggregate by chapter
        chapter_groups: Dict[str, Dict[str, Any]] = {}
        top_tariff_lines = []

        for rank, idx in enumerate(top_tariff_indices):
            raw_sim = float(tariff_sims[idx])
            rec = self.records[idx]
            ch = rec["chapter"]
            ch_title = self.chapter_titles.get(ch, "")

            line_item = {
                "hsn_code": rec["hsn_code"],
                "hsn_raw": rec["hsn_raw"],
                "description": rec["description"],
                "chapter": ch,
                "chapter_title": ch_title,
                "score": round(raw_sim, 4),
                "rank": rank + 1
            }
            top_tariff_lines.append(line_item)

            if ch not in chapter_groups:
                title_sim = ch_title_score_map.get(ch, 0.0)
                # Weighted blend: 75% best tariff match + 25% direct chapter title match
                blended_score = max(raw_sim, 0.75 * raw_sim + 0.25 * title_sim)
                chapter_groups[ch] = {
                    "chapter": ch,
                    "chapter_title": ch_title,
                    "max_score": blended_score,
                    "tariff_score": raw_sim,
                    "title_score": title_sim,
                    "match_count": 1,
                    "evidence_lines": [line_item]
                }
            else:
                chapter_groups[ch]["match_count"] += 1
                if len(chapter_groups[ch]["evidence_lines"]) < 5:
                    chapter_groups[ch]["evidence_lines"].append(line_item)

        # Also consider direct high-scoring chapter titles even if individual tariff lines were diffuse
        top_title_indices = np.argsort(chapter_title_sims)[::-1][:5]
        for t_idx in top_title_indices:
            ch_code = self.chapter_codes[t_idx]
            t_sim = float(chapter_title_sims[t_idx])
            if ch_code not in chapter_groups and t_sim > 0.45:
                ch_title = self.chapter_titles.get(ch_code, "")
                chapter_groups[ch_code] = {
                    "chapter": ch_code,
                    "chapter_title": ch_title,
                    "max_score": t_sim * 0.9,
                    "tariff_score": 0.0,
                    "title_score": t_sim,
                    "match_count": 0,
                    "evidence_lines": []
                }

        # Sort candidate chapters
        sorted_chapters = sorted(
            chapter_groups.values(),
            key=lambda x: x["max_score"],
            reverse=True
        )[:top_k_chapters]

        top_score = sorted_chapters[0]["max_score"] if sorted_chapters else 1.0
        for ch_data in sorted_chapters:
            ch_data["normalized_score"] = round(ch_data["max_score"] / (top_score or 1.0), 4)

        return {
            "candidate_chapters": sorted_chapters,
            "top_tariff_lines": top_tariff_lines
        }


# Module singleton
_semantic_index_instance: Optional[SemanticTariffIndex] = None

def get_semantic_index() -> SemanticTariffIndex:
    global _semantic_index_instance
    if _semantic_index_instance is None:
        _semantic_index_instance = SemanticTariffIndex()
    return _semantic_index_instance
