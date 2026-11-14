"""
src/ml/hard_negative_miner.py
=============================
Phase 3: Dynamic Hard-Negative Miner with Ambiguity Safeguard

Uses the existing dense embedding index (all-MiniLM-L6-v2) over the Master HSN
dataset to mine confusing tariff descriptions for every positive (query, HSN) pair.

Safeguard (Section 3):
  Does NOT blindly treat every non-matching HSN row as a negative. Neighbouring
  tariff rows in the same 4-digit heading OR sharing significant article keyword
  overlap are filtered out as potentially valid/ambiguous alternatives rather than
  corrupting the training set with false negatives.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd

from src.ml.product_tariff_reranker import format_tariff_context

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_MASTER_PARQUET = ROOT_DIR / "data" / "enriched_master_hsn.parquet"
DEFAULT_PAIRS_DIR = ROOT_DIR / "data" / "training_pairs"


def _keyword_tokens(raw: Any) -> Set[str]:
    """Extracts normalized lowercase multi-word phrases & tokens from keyword columns."""
    if raw is None:
        return set()
    text = str(raw).strip().lower()
    if not text or text in ("nan", "none", "null"):
        return set()
    phrases = {p.strip() for p in re.split(r"[,;|]+", text) if len(p.strip()) >= 2}
    return phrases


def is_ambiguous_neighbor(
    pos_row: Dict[str, Any],
    cand_row: Dict[str, Any],
    article_overlap_threshold: float = 0.30,
) -> Tuple[bool, str]:
    """
    Safeguard check: returns (True, reason) if `cand_row` could legitimately
    classify the same product under different conditions and should NOT be
    used as a hard negative.
    """
    pos_hsn = str(pos_row.get("hsn_clean", "")).strip()
    cand_hsn = str(cand_row.get("hsn_clean", "")).strip()

    if pos_hsn == cand_hsn:
        return True, "exact_same_hsn"

    # Same 4-digit heading often represents sibling material/size/grade variants
    if len(pos_hsn) >= 4 and len(cand_hsn) >= 4 and pos_hsn[:4] == cand_hsn[:4]:
        return True, "same_4digit_heading"

    # High overlap in curated article keywords indicates potential co-classification
    pos_art = _keyword_tokens(pos_row.get("article_keywords") or pos_row.get("Article Keywords"))
    cand_art = _keyword_tokens(cand_row.get("article_keywords") or cand_row.get("Article Keywords"))
    if pos_art and cand_art:
        intersection = pos_art & cand_art
        union = pos_art | cand_art
        jaccard = len(intersection) / len(union) if union else 0.0
        if jaccard >= article_overlap_threshold or len(intersection) >= 2:
            return True, "article_keyword_overlap"

    return False, "safe_negative"


class HardNegativeMiner:
    """
    Mines hard negatives from the Master HSN corpus using dense semantic similarity
    with statutory/keyword ambiguity filtering.
    """

    def __init__(
        self,
        master_parquet: Path = DEFAULT_MASTER_PARQUET,
        pairs_dir: Path = DEFAULT_PAIRS_DIR,
        embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        local_files_only: bool = True,
    ):
        self.master_parquet = Path(master_parquet)
        self.pairs_dir = Path(pairs_dir)
        self.embedding_model_name = embedding_model_name
        self.local_files_only = local_files_only
        self._embedder = None

        self.master_df = self._load_master()
        self.master_records = self.master_df.to_dict(orient="records")
        self.hsn_to_record: Dict[str, Dict[str, Any]] = {
            r["hsn_clean"]: r for r in self.master_records
        }
        self.master_contexts = [format_tariff_context(r) for r in self.master_records]
        self.doc_embeddings: Optional[np.ndarray] = None

    def _load_master(self) -> pd.DataFrame:
        df = pd.read_parquet(self.master_parquet)
        self._full_master_len = len(df)
        df["hsn_clean"] = df["hsn_code"].astype(str).str.replace(" ", "", regex=False).str.strip()
        df["chapter_clean"] = df["chapter_code"].astype(str).str.strip().str.zfill(2)
        df["_orig_idx"] = np.arange(len(df))
        df = df[df["hsn_clean"].str.len() == 8].drop_duplicates(subset=["hsn_clean"]).reset_index(drop=True)
        self._source_row_indices = df["_orig_idx"].to_numpy()
        return df.drop(columns=["_orig_idx"])

    def _get_embedder(self):
        if self._embedder is None:
            import os
            os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
            from sentence_transformers import SentenceTransformer
            self._embedder = SentenceTransformer(
                self.embedding_model_name,
                device="cpu",
                local_files_only=self.local_files_only,
            )
        return self._embedder

    def build_doc_index(self) -> np.ndarray:
        if self.doc_embeddings is None:
            # Fast path: reuse precomputed MiniLM embeddings from HybridHSNEngine cache
            cache_dir = ROOT_DIR / "data" / "intent_cache"
            if self.master_parquet == DEFAULT_MASTER_PARQUET and cache_dir.exists():
                for npy_path in sorted(cache_dir.glob("master_embeddings_*.npy")):
                    try:
                        full_embs = np.load(npy_path)
                        if full_embs.shape[0] == self._full_master_len:
                            sub_embs = full_embs[self._source_row_indices]
                            norms = np.linalg.norm(sub_embs, axis=1, keepdims=True)
                            norms[norms == 0] = 1e-10
                            self.doc_embeddings = sub_embs / norms
                            logger.info(
                                f"Loaded cached doc embeddings from {npy_path.name}: {self.doc_embeddings.shape}"
                            )
                            return self.doc_embeddings
                    except Exception as e:
                        logger.warning(f"Failed loading cached embeddings {npy_path}: {e}")

            embedder = self._get_embedder()
            logger.info(f"Encoding {len(self.master_contexts)} master tariff contexts...")
            self.doc_embeddings = embedder.encode(
                self.master_contexts,
                batch_size=64,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
        return self.doc_embeddings

    def encode_queries(self, queries: List[str]) -> np.ndarray:
        embedder = self._get_embedder()
        return embedder.encode(
            queries,
            batch_size=64,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )

    def mine_for_split(
        self,
        pos_df: pd.DataFrame,
        negatives_per_positive: int = 2,
        top_k_search: int = 25,
    ) -> Tuple[pd.DataFrame, Dict[str, int]]:
        """
        Mines hard negatives for every row in `pos_df` and returns a combined
        DataFrame (positives + hard negatives) along with mining statistics.
        """
        doc_embs = self.build_doc_index()
        queries = pos_df["query"].astype(str).tolist()
        logger.info(f"Encoding {len(queries)} queries for hard-negative mining...")
        q_embs = self.encode_queries(queries)

        # Similarity matrix: (N_queries, N_master)
        sim_matrix = np.dot(q_embs, doc_embs.T)

        neg_rows: List[Dict[str, Any]] = []
        stats = {
            "total_positives": len(pos_df),
            "total_negatives_mined": 0,
            "cross_chapter_negatives": 0,
            "same_chapter_diff_heading_negatives": 0,
            "skipped_same_hsn": 0,
            "skipped_same_heading_safeguard": 0,
            "skipped_keyword_overlap_safeguard": 0,
        }

        pos_records = pos_df.to_dict(orient="records")
        for row_idx, pos_item in enumerate(pos_records):
            pos_hsn = str(pos_item["hsn_code"]).strip()
            pos_ch = str(pos_item["chapter_code"]).strip().zfill(2)
            pos_master = self.hsn_to_record.get(pos_hsn, pos_item)

            sims = sim_matrix[row_idx]
            # Fast partial sort for top_k_search candidates
            top_indices = np.argpartition(sims, -top_k_search)[-top_k_search:]
            top_indices = top_indices[np.argsort(sims[top_indices])[::-1]]

            cross_chapter_cands: List[Tuple[int, float]] = []
            same_chapter_cands: List[Tuple[int, float]] = []

            for cand_idx in top_indices:
                cand_rec = self.master_records[cand_idx]
                ambiguous, reason = is_ambiguous_neighbor(pos_master, cand_rec)
                if ambiguous:
                    if reason == "exact_same_hsn":
                        stats["skipped_same_hsn"] += 1
                    elif reason == "same_4digit_heading":
                        stats["skipped_same_heading_safeguard"] += 1
                    elif reason == "article_keyword_overlap":
                        stats["skipped_keyword_overlap_safeguard"] += 1
                    continue

                cand_ch = cand_rec["chapter_clean"]
                score = float(sims[cand_idx])
                if cand_ch != pos_ch:
                    cross_chapter_cands.append((cand_idx, score))
                else:
                    same_chapter_cands.append((cand_idx, score))

            # Prioritize at least 1 cross-chapter distractor (e.g. Product vs Machinery)
            # then fill remaining slots with highest-similarity safe negatives
            selected: List[Tuple[int, float, str]] = []
            if cross_chapter_cands:
                idx0, s0 = cross_chapter_cands.pop(0)
                selected.append((idx0, s0, "cross_chapter"))

            remaining_pool = [
                (i, s, "cross_chapter") for i, s in cross_chapter_cands
            ] + [
                (i, s, "same_chapter_diff_heading") for i, s in same_chapter_cands
            ]
            remaining_pool.sort(key=lambda x: x[1], reverse=True)

            for item_sel in remaining_pool:
                if len(selected) >= negatives_per_positive:
                    break
                selected.append(item_sel)

            for cand_idx, sim_score, neg_type in selected:
                cand_rec = self.master_records[cand_idx]
                neg_rows.append(
                    {
                        "split": pos_item["split"],
                        "query": pos_item["query"],
                        "query_strategy": pos_item.get("query_strategy", ""),
                        "hsn_code": cand_rec["hsn_clean"],
                        "chapter_code": cand_rec["chapter_clean"],
                        "heading_4digit": str(cand_rec.get("heading_4digit", "")),
                        "tariff_context": self.master_contexts[cand_idx],
                        "label": 0,
                        "relation": "RELATED_PRODUCT",
                        "negative_type": neg_type,
                        "positive_hsn_ref": pos_hsn,
                        "dense_sim": round(sim_score, 4),
                    }
                )
                stats["total_negatives_mined"] += 1
                if neg_type == "cross_chapter":
                    stats["cross_chapter_negatives"] += 1
                else:
                    stats["same_chapter_diff_heading_negatives"] += 1

        pos_out = pos_df.copy()
        pos_out["negative_type"] = "none"
        pos_out["positive_hsn_ref"] = pos_out["hsn_code"]
        pos_out["dense_sim"] = 1.0

        neg_df = pd.DataFrame(neg_rows)
        combined = pd.concat([pos_out, neg_df], ignore_index=True)
        combined = combined.sample(frac=1.0, random_state=42).reset_index(drop=True)
        return combined, stats

    def run(self, negatives_per_positive: int = 2) -> Dict[str, Any]:
        all_stats: Dict[str, Any] = {"negatives_per_positive": negatives_per_positive, "splits": {}}
        for split in ("train", "val", "test"):
            pos_path = self.pairs_dir / f"positive_pairs_{split}.parquet"
            if not pos_path.exists():
                raise FileNotFoundError(f"Missing {pos_path}; run Phase 2 TrainingDataBuilder first.")
            pos_df = pd.read_parquet(pos_path)
            combined_df, split_stats = self.mine_for_split(
                pos_df, negatives_per_positive=negatives_per_positive
            )
            out_path = self.pairs_dir / f"full_pairs_{split}.parquet"
            combined_df.to_parquet(out_path, index=False)
            all_stats["splits"][split] = split_stats
            logger.info(
                f"[{split}] Saved {len(combined_df)} total pairs "
                f"({split_stats['total_positives']} pos + {split_stats['total_negatives_mined']} hard neg) -> {out_path}"
            )

        with open(self.pairs_dir / "hard_negative_stats.json", "w", encoding="utf-8") as f:
            json.dump(all_stats, f, indent=2)
        return all_stats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    miner = HardNegativeMiner()
    stats = miner.run(negatives_per_positive=2)
    print(json.dumps(stats, indent=2))

