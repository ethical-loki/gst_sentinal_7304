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


_SPELLING_NORMALIZATIONS = {
    "vaccum": "vacuum",
    "stailess": "stainless",
    "inflater": "inflator",
    "accessorie": "accessories",
    "apparatuse": "apparatus",
}


def normalize_statutory_spelling(text: str) -> str:
    """Safe search-time normalization for common statutory OCR/spelling variations."""
    if not text:
        return ""
    out = text
    for bad, good in _SPELLING_NORMALIZATIONS.items():
        out = re.sub(rf"\b{bad}\b", good, out, flags=re.IGNORECASE)
    return out


def _tokenize(text: str) -> List[str]:
    if not text:
        return []
    norm = normalize_statutory_spelling(text)
    words = re.findall(r"\b[a-zA-Z0-9]{2,}\b", norm.lower())
    return [w for w in words if w not in STOPWORDS]


@dataclass
class StatutoryCoverageResult:
    query: str
    is_out_of_schedule: bool
    predicted_chapter: Optional[str]
    top_statutory_matches: List[Dict[str, Any]] = field(default_factory=list)
    active_chapters: List[str] = field(default_factory=list)
    reason: str = ""


@dataclass
class StatutoryComparisonResult:
    query: str
    is_out_of_schedule: bool
    best_active_score: float
    best_inactive_score: float
    best_inactive_match: Optional[Dict[str, Any]] = None
    top_statutory_matches: List[Dict[str, Any]] = field(default_factory=list)
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

    def compare_active_vs_statutory(
        self,
        query: str,
        best_active_score: float,
        reranker: Any,
        top_k: int = 8,
        inactive_advantage_margin: float = 0.02,
    ) -> StatutoryComparisonResult:
        """
        Independently searches the complete 98-chapter statutory master, reranks
        any inactive-chapter candidates using the same Cross-Encoder `reranker`,
        and checks whether an inactive chapter contains a better-supported
        classification than the best active-chapter candidate.
        """
        statutory_matches = self.search_statutory(query, top_k=top_k)
        inactive_cands = [m for m in statutory_matches if not m["in_active_schedule"]]

        if not inactive_cands:
            return StatutoryComparisonResult(
                query=query,
                is_out_of_schedule=False,
                best_active_score=round(float(best_active_score), 4),
                best_inactive_score=0.0,
                top_statutory_matches=statutory_matches,
                reason="No stronger inactive-chapter candidate found in 98-chapter master.",
            )

        # Rerank inactive-chapter statutory candidates with the same Cross-Encoder
        formatted_rows = [
            {
                "hsn_code": m["hsn_code"],
                "chapter_code": m["chapter"],
                "chapter_title": f"Chapter {m['chapter']}",
                "statutory_description": m["description"],
            }
            for m in inactive_cands
        ]
        ranked_inactive = reranker.rerank(query, formatted_rows, normalize_sigmoid=True)
        best_inact = ranked_inactive[0]
        best_inact_score = float(best_inact.relevance_score)
        best_inact_dict = next(
            (m for m in inactive_cands if m["hsn_code"] == best_inact.hsn_code),
            inactive_cands[0],
        )
        best_inact_dict = {**best_inact_dict, "reranker_score": round(best_inact_score, 4)}

        # Inactive chapter wins only if:
        #   1) It has at least moderate statutory relevance (>= 0.40, never UNRELATED < 0.35), AND
        #   2) When active schedule already has a SAME_PRODUCT match (>= 0.725), inactive must win
        #      by a decisive margin (>= 0.15) rather than a tie/near-tie on material-ambiguous items.
        if best_inact_score < 0.40:
            is_oos = False
        elif best_active_score >= 0.725:
            is_oos = best_inact_score >= (best_active_score + 0.15)
        else:
            is_oos = best_inact_score > (best_active_score + inactive_advantage_margin)

        reason = (
            f"Inactive Chapter {best_inact_dict['chapter']} (HSN {best_inact_dict['hsn_code']}, "
            f"score={best_inact_score:.3f}) outranks best active candidate (score={best_active_score:.3f})."
            if is_oos
            else f"Active schedule (score={best_active_score:.3f}) outranks best inactive chapter "
            f"Ch {best_inact_dict['chapter']} (score={best_inact_score:.3f})."
        )

        return StatutoryComparisonResult(
            query=query,
            is_out_of_schedule=is_oos,
            best_active_score=round(float(best_active_score), 4),
            best_inactive_score=round(best_inact_score, 4),
            best_inactive_match=best_inact_dict,
            top_statutory_matches=statutory_matches,
            reason=reason,
        )
