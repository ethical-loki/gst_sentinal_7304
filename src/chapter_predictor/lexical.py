"""
src/chapter_predictor/lexical.py
================================
Stage B: BM25 Lexical Retrieval with Chapter-Level Score Aggregation.

Features:
- Indexes all 19,396 statutory descriptions from Final_Copy_hsn_7304.xlsx,
  enriched with parent 4-digit heading descriptions and official chapter titles.
- Retrieves top 50 statutory tariff lines matching query tokens.
- Aggregates results by 2-digit chapter code (01–99), keeping the top score per chapter
  and preserving the top 5 tariff lines per candidate chapter as evidence.
"""

import json
import logging
import math
import pickle
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_INDEX_CACHE_PATH = ROOT_DIR / "data" / "chapter_predictor" / "bm25_index.pkl"


def stem_token(t: str) -> str:
    """Lightweight algorithmic stemmer for BM25 lexical matching."""
    if t.endswith("ies") and len(t) > 4:
        return t[:-3] + "y"
    if t.endswith("oes") and len(t) > 4:
        return t[:-2]
    if t.endswith("es") and len(t) > 3 and t[-3] in "shxz":
        return t[:-2]
    if t.endswith("s") and not t.endswith("ss") and len(t) > 3:
        return t[:-1]
    return t


def tokenize_corpus_text(text: str) -> List[str]:
    """
    Tokenizes text for BM25 indexing (lowercased, alphanumeric tokens, length >= 2)
    with stemming applied internally inside BM25 as per Task 2.
    """
    return [stem_token(t) for t in re.findall(r"\b[a-z0-9]{2,}\b", (text or "").lower())]


class SimpleBM25Okapi:
    """
    High-performance self-contained BM25Okapi implementation.
    Zero external C-dependency issues, fully serializable with pickle.
    """
    def __init__(self, corpus: List[List[str]], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.corpus_size = len(corpus)
        self.doc_lens = [len(doc) for doc in corpus]
        self.avg_doc_len = sum(self.doc_lens) / (self.corpus_size or 1)
        self.doc_freqs: List[Dict[str, int]] = []
        self.idf: Dict[str, float] = {}
        self._initialize(corpus)

    def _initialize(self, corpus: List[List[str]]):
        df_counts: Dict[str, int] = {}
        for doc in corpus:
            freqs: Dict[str, int] = {}
            for term in doc:
                freqs[term] = freqs.get(term, 0) + 1
            self.doc_freqs.append(freqs)
            for term in freqs:
                df_counts[term] = df_counts.get(term, 0) + 1

        for term, freq in df_counts.items():
            # Standard Lucene/Okapi smoothed IDF formula
            self.idf[term] = math.log((self.corpus_size - freq + 0.5) / (freq + 0.5) + 1.0)

    def get_scores(self, query_tokens: List[str]) -> List[float]:
        scores = [0.0] * self.corpus_size
        for term in query_tokens:
            if term not in self.idf:
                continue
            idf_val = self.idf[term]
            for idx in range(self.corpus_size):
                tf = self.doc_freqs[idx].get(term, 0)
                if tf > 0:
                    denom = tf + self.k1 * (1.0 - self.b + self.b * (self.doc_lens[idx] / self.avg_doc_len))
                    scores[idx] += idf_val * (tf * (self.k1 + 1.0)) / denom
        return scores


class LexicalTariffIndex:
    """
    BM25 index over all statutory tariff lines from Final_Copy_hsn_7304.xlsx,
    aggregated at the chapter level.
    """
    def __init__(self, cache_path: Path = DEFAULT_INDEX_CACHE_PATH):
        self.cache_path = Path(cache_path)
        self.bm25: Optional[Any] = None
        self.records: List[Dict[str, Any]] = []
        self.chapter_titles: Dict[str, str] = {}
        self._is_loaded = False

    def load_or_build(self, force_rebuild: bool = False):
        """Loads cached BM25 index from disk or builds from Excel."""
        if self._is_loaded and not force_rebuild:
            return

        if self.cache_path.exists() and not force_rebuild:
            try:
                with open(self.cache_path, "rb") as f:
                    data = pickle.load(f)
                    self.bm25 = data["bm25"]
                    self.records = data["records"]
                    self.chapter_titles = data["chapter_titles"]
                    self._is_loaded = True
                    logger.info(f"Loaded BM25 index from {self.cache_path} ({len(self.records)} records)")
                    return
            except Exception as e:
                logger.warning(f"Could not load BM25 cache: {e}. Rebuilding...")

        self.build_index()

    def build_index(self):
        """Builds BM25 index from raw spreadsheet + chapter titles."""
        import pandas as pd

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

        # First pass: map 4-digit headings to their statutory parent texts
        heading_parent_text: Dict[str, str] = {}
        for _, row in df.iterrows():
            raw_c = str(row[code_col]).strip()
            raw_d = str(row[desc_col] or "").strip()
            clean_digits = re.sub(r"\D", "", raw_c)
            # 4 digits (or 3 digits with dropped leading zero)
            if len(clean_digits) == 3:
                clean_digits = clean_digits.zfill(4)
            if len(clean_digits) == 4:
                heading_parent_text[clean_digits] = raw_d

        records = []
        corpus_tokenized = []

        for idx, row in df.iterrows():
            raw_c = str(row[code_col]).strip()
            desc = str(row[desc_col] or "").strip()
            clean_digits = re.sub(r"\D", "", raw_c)

            # Normalize to 2, 4, 6, 8 digits
            if len(clean_digits) == 1:
                clean_digits = clean_digits.zfill(2)
            elif len(clean_digits) == 3:
                clean_digits = clean_digits.zfill(4)
            elif len(clean_digits) == 5:
                clean_digits = clean_digits.zfill(6)
            elif len(clean_digits) == 7:
                clean_digits = clean_digits.zfill(8)

            ch = clean_digits[:2] if len(clean_digits) >= 2 else "99"
            h4 = clean_digits[:4] if len(clean_digits) >= 4 else clean_digits.zfill(4)
            ch_title = self.chapter_titles.get(ch, "")
            parent_text = heading_parent_text.get(h4, "")

            # Format formatted HSN (e.g. "0901 21 10")
            if len(clean_digits) == 8:
                formatted_code = f"{clean_digits[:4]} {clean_digits[4:6]} {clean_digits[6:]}"
            elif len(clean_digits) == 6:
                formatted_code = f"{clean_digits[:4]} {clean_digits[4:]}"
            else:
                formatted_code = clean_digits

            # Enriched text for BM25: full description + parent heading + chapter title
            combined_text = f"{clean_digits} {desc} {parent_text} {ch_title}".strip()
            tokens = tokenize_corpus_text(combined_text)

            rec = {
                "idx": idx,
                "hsn_raw": clean_digits,
                "hsn_code": formatted_code,
                "description": desc,
                "parent_heading": h4,
                "parent_heading_text": parent_text,
                "chapter": ch,
                "chapter_title": ch_title
            }
            records.append(rec)
            corpus_tokenized.append(tokens)

        # Build BM25 index
        try:
            from rank_bm25 import BM25Okapi
            self.bm25 = BM25Okapi(corpus_tokenized)
        except ImportError:
            self.bm25 = SimpleBM25Okapi(corpus_tokenized)

        self.records = records
        self._is_loaded = True

        # Save cache
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.cache_path, "wb") as f:
                pickle.dump({
                    "bm25": self.bm25,
                    "records": self.records,
                    "chapter_titles": self.chapter_titles
                }, f, protocol=pickle.HIGHEST_PROTOCOL)
            logger.info(f"Saved BM25 index to {self.cache_path} ({len(self.records)} records)")
        except Exception as e:
            logger.warning(f"Could not cache BM25 index: {e}")

    def query(
        self,
        query_text: str,
        top_k_tariff: int = 50,
        top_k_chapters: int = 10
    ) -> Dict[str, Any]:
        """
        Stage B query execution:
        - BM25 scoring over all 19,396 records
        - Retrieves top_k_tariff lines
        - Aggregates by chapter, keeping max score and top tariff lines
        """
        if not self._is_loaded:
            self.load_or_build()

        q_tokens = tokenize_corpus_text(query_text)
        if not q_tokens or not self.bm25:
            return {"candidate_chapters": [], "top_tariff_lines": []}

        # Calculate BM25 scores
        scores = self.bm25.get_scores(q_tokens)

        # Get top indices
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k_tariff]

        # Aggregate by chapter
        chapter_groups: Dict[str, Dict[str, Any]] = {}
        top_tariff_lines = []

        for rank, idx in enumerate(top_indices):
            raw_score = float(scores[idx])
            if raw_score <= 0.0:
                continue

            rec = self.records[idx]
            ch = rec["chapter"]
            ch_title = self.chapter_titles.get(ch, rec.get("chapter_title", ""))

            line_item = {
                "hsn_code": rec["hsn_code"],
                "hsn_raw": rec["hsn_raw"],
                "description": rec["description"],
                "chapter": ch,
                "chapter_title": ch_title,
                "score": round(raw_score, 4),
                "rank": rank + 1
            }
            top_tariff_lines.append(line_item)

            if ch not in chapter_groups:
                chapter_groups[ch] = {
                    "chapter": ch,
                    "chapter_title": ch_title,
                    "max_score": raw_score,
                    "sum_score": raw_score,
                    "match_count": 1,
                    "evidence_lines": [line_item]
                }
            else:
                chapter_groups[ch]["sum_score"] += raw_score
                chapter_groups[ch]["match_count"] += 1
                if len(chapter_groups[ch]["evidence_lines"]) < 5:
                    chapter_groups[ch]["evidence_lines"].append(line_item)

        # Sort candidate chapters by max_score
        sorted_chapters = sorted(
            chapter_groups.values(),
            key=lambda x: (x["max_score"], x["sum_score"]),
            reverse=True
        )[:top_k_chapters]

        # Normalize scores to 0.0 - 1.0 relative to top candidate
        top_score = sorted_chapters[0]["max_score"] if sorted_chapters else 1.0
        for ch_data in sorted_chapters:
            ch_data["normalized_score"] = round(ch_data["max_score"] / (top_score or 1.0), 4)

        return {
            "query_tokens": q_tokens,
            "candidate_chapters": sorted_chapters,
            "top_tariff_lines": top_tariff_lines
        }


# Module singleton
_lexical_index_instance: Optional[LexicalTariffIndex] = None

def get_lexical_index() -> LexicalTariffIndex:
    global _lexical_index_instance
    if _lexical_index_instance is None:
        _lexical_index_instance = LexicalTariffIndex()
    return _lexical_index_instance

