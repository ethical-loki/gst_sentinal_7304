"""
src/search/statutory_master_index.py
====================================
Phase 7: Complete 98-Chapter Statutory Master Index & Out-of-Schedule Detector

Maintains the dual-index separation recommended in Section 6:
  1. Complete Statutory Master (`data/tariff_master.parquet`, 19,396 rows, 98 chapters)
     used to detect whether a product belongs to an unindexed chapter.
  2. Active Classification Master (`data/enriched_master_hsn.parquet`, 4,851 rows)
     whose active chapter set is computed dynamically (never hardcoded).
"""

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import numpy as np
import pandas as pd
from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_STATUTORY_PARQUET = ROOT_DIR / "data" / "tariff_master.parquet"
DEFAULT_ACTIVE_PARQUET = ROOT_DIR / "data" / "enriched_master_hsn.parquet"
DEFAULT_STATUTORY_META_DIR = ROOT_DIR / "data" / "statutory_master"

STOPWORDS = {
    "and", "the", "for", "with", "other", "than", "not", "under", "goods",
    "articles", "thereof", "kind", "used", "like", "such", "all", "of", "in", "a", "an",
}


def _tokenize(text: str) -> List[str]:
    if not text:
        return []
    words = re.findall(r"\b[a-zA-Z0-9]{2,}\b", text.lower())
    return [w for w in words if w not in STOPWORDS]


@dataclass
class StatutoryCoverageResult:
    query: str
    is_out_of_schedule: bool
    predicted_chapter: Optional[str]
    top_statutory_matches: List[Dict[str, Any]] = field(default_factory=list)
    active_chapters: List[str] = field(default_factory=list)
    reason: str = ""


class StatutoryMasterIndex:
    """
    Full 98-chapter BM25 index over the complete CBIC/ITC-HS Tariff Master
    for accurate OUT_OF_SCHEDULE detection.
    """

    def __init__(
        self,
        statutory_parquet: Path = DEFAULT_STATUTORY_PARQUET,
        active_parquet: Path = DEFAULT_ACTIVE_PARQUET,
        meta_dir: Path = DEFAULT_STATUTORY_META_DIR,
    ):
        self.statutory_parquet = Path(statutory_parquet)
        self.active_parquet = Path(active_parquet)
        self.meta_dir = Path(meta_dir)

        if not self.statutory_parquet.exists():
            raise FileNotFoundError(f"Statutory master missing: {self.statutory_parquet}")
        if not self.active_parquet.exists():
            raise FileNotFoundError(f"Active master missing: {self.active_parquet}")

        # Dynamically derive active chapters from the active dataset
        active_df = pd.read_parquet(self.active_parquet, columns=["chapter_code"])
        self.active_chapters: Set[str] = {
            str(ch).strip().zfill(2) for ch in active_df["chapter_code"].dropna().unique()
        }

        # Load complete 98-chapter statutory master
        self.df = pd.read_parquet(self.statutory_parquet)
        self.df["chapter_clean"] = self.df["chapter"].astype(str).str.strip().str.zfill(2)
        self.df["hsn_clean"] = self.df["hsn_code"].astype(str).str.strip()
        self.records = self.df.to_dict(orient="records")

        corpus = [
            _tokenize(
                f"{r.get('clean_description') or r.get('description') or ''} "
                f"{r.get('search_text') or ''}"
            )
            for r in self.records
        ]
        self.bm25 = BM25Okapi(corpus)
        self.all_chapters: Set[str] = set(self.df["chapter_clean"].unique())

        self._save_coverage_metadata()
        logger.info(
            f"[StatutoryMasterIndex] Ready: {len(self.records)} rows across "
            f"{len(self.all_chapters)} chapters ({len(self.active_chapters)} active)."
        )

    def _save_coverage_metadata(self) -> None:
        self.meta_dir.mkdir(parents=True, exist_ok=True)
        meta = {
            "total_statutory_rows": len(self.records),
            "total_statutory_chapters": len(self.all_chapters),
            "active_chapters": sorted(self.active_chapters),
            "unindexed_chapters_count": len(self.all_chapters - self.active_chapters),
        }
        with open(self.meta_dir / "schedule_coverage.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

    def search_statutory(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        tokens = _tokenize(query)
        if not tokens:
            return []
        scores = np.array(self.bm25.get_scores(tokens))
        if len(scores) == 0:
            return []
        k = min(top_k, len(scores))
        if k == len(scores):
            top_idx = np.argsort(scores)[::-1]
        else:
            top_idx = np.argpartition(scores, -k)[-k:]
            top_idx = top_idx[np.argsort(scores[top_idx])[::-1]]

        results: List[Dict[str, Any]] = []
        for idx in top_idx:
            if scores[idx] <= 0:
                continue
            r = self.records[idx]
            rate = r.get("standard_rate")
            clean_rate = None if pd.isna(rate) else float(rate)
            results.append(
                {
                    "hsn_code": r["hsn_clean"],
                    "chapter": r["chapter_clean"],
                    "description": str(r.get("description") or r.get("hsn_description") or ""),
                    "standard_rate": clean_rate,
                    "bm25_score": round(float(scores[idx]), 4),
                    "in_active_schedule": r["chapter_clean"] in self.active_chapters,
                }
            )
        return results

    def check_schedule_coverage(
        self, query: str, top_k: int = 5, min_bm25_score: float = 4.0
    ) -> StatutoryCoverageResult:
        """
        Determines whether `query` belongs to an unindexed statutory chapter
        (OUT_OF_SCHEDULE) vs one of the active classification chapters.
        """
        matches = self.search_statutory(query, top_k=top_k)
        if not matches:
            return StatutoryCoverageResult(
                query=query,
                is_out_of_schedule=False,
                predicted_chapter=None,
                top_statutory_matches=[],
                active_chapters=sorted(self.active_chapters),
                reason="No strong statutory BM25 match found.",
            )

        top = matches[0]
        top_score = top["bm25_score"]
        any_active_in_top3 = any(m["in_active_schedule"] for m in matches[:3])

        if (not top["in_active_schedule"]) and (not any_active_in_top3) and top_score >= min_bm25_score:
            return StatutoryCoverageResult(
                query=query,
                is_out_of_schedule=True,
                predicted_chapter=top["chapter"],
                top_statutory_matches=matches,
                active_chapters=sorted(self.active_chapters),
                reason=(
                    f"Best statutory matches belong to Chapter {top['chapter']} "
                    f"(HSN {top['hsn_code']}), which is outside the {len(self.active_chapters)} "
                    f"active chapters."
                ),
            )

        return StatutoryCoverageResult(
            query=query,
            is_out_of_schedule=False,
            predicted_chapter=top["chapter"],
            top_statutory_matches=matches,
            active_chapters=sorted(self.active_chapters),
            reason=f"Covered by active chapter schedule (top statutory chapter: {top['chapter']}).",
        )
