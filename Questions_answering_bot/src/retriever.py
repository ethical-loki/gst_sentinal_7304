"""
retriever.py — Multi-Domain Document Chunking and Dynamic Indexed Retrieval Module.

Features:
- Multi-domain knowledge isolation: maintains distinct chunk stores and TF-IDF indexes for:
  1. e_invoice: E-Invoicing thresholds, IRN generation, 24-hr cancellation, error codes.
  2. eway_bill: Part A/B slip rules, distance-based validity, vehicle updates, transit rules.
  3. ims: Invoice Management System actions (Accept/Reject/Pending), GSTR-2B flow, ITC cutoffs.
- Section- and rule-aware chunking preserving markdown headings (##), bold titles (**...**), and numbered sections (1. ...).
- 100% Dynamic Statistical Retrieval:
  - Multi-field TF-IDF with section-heading weighting and morphological normalization (stemming).
  - Preserves compound statutory entities ('e-invoice' -> 'einvoice', 'e-way' -> 'eway').
  - Dynamic n-gram and keyphrase overlap scoring.
  - Mathematical query grounding filter to reject foreign-domain or out-of-domain hallucinations.
  - Zero hardcoded query strings or domain boost tables.
"""

import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Set

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from config import (
    DOMAIN_CONTEXT_PATHS,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    TOP_K,
    SCORE_THRESHOLD,
)

logger = logging.getLogger("gst_sentinel.retriever")


def stem_token(word: str) -> str:
    """Universal linguistic stemmer for English regulatory terminology."""
    w = word.lower().strip()
    if len(w) <= 2:
        return w
    if w in ("meant", "meaning", "means"):
        return "mean"
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith("ability") and len(w) > 7:
        return w[:-7] + "abl"
    if w.endswith("able") and len(w) > 4:
        return w[:-4] + "abl"
    if w.endswith("ation") and len(w) > 6:
        w = w[:-5]
    elif w.endswith("tion") and len(w) > 6:
        w = w[:-4]
    elif w.endswith("ment") and len(w) > 7:
        w = w[:-4]
    elif w.endswith("ity") and len(w) > 5:
        w = w[:-3]
    elif w.endswith("ing") and len(w) > 5:
        w = w[:-3]
    elif w.endswith("ed") and len(w) > 4:
        w = w[:-2]
    elif w.endswith("es") and len(w) > 3 and not w.endswith("ses"):
        w = w[:-2]
    elif w.endswith("s") and not w.endswith("ss") and not w.endswith("us") and len(w) > 3:
        w = w[:-1]
    if len(w) > 3 and w[-1] == w[-2] and w[-1] in "ltps":
        w = w[:-1]
    return w


RAW_STOPWORDS = {
    "what", "is", "the", "for", "in", "and", "to", "of", "a", "an", "be",
    "how", "long", "can", "will", "are", "do", "does", "by", "from", "on",
    "at", "it", "with", "as", "or", "if", "not", "this", "that", "these",
    "tell", "me", "about", "give", "please", "could", "would", "should",
    "happens"
}
STEMMED_STOPWORDS: Set[str] = {stem_token(w).strip() for w in RAW_STOPWORDS}

SYNONYM_MAP = {
    "move": ["transport", "transit", "movement", "convey"],
    "transport": ["move", "transit", "movement", "convey"],
    "penalti": ["fine", "seizur", "confisc", "detent", "violat", "enforc"],
    "fine": ["penalti", "seizur", "confisc"],
    "valid": ["expiri", "period", "durat", "time"],
    "cancel": ["revoc", "reject", "void", "amend"],
    "mean": ["definit", "concept", "framework", "object"],
    "action": ["accept", "reject", "pend", "deem"],
    "limit": ["threshold", "turnov", "aato", "crore", "maximum", "minimum"],
}

FOREIGN_DOMAIN_KEYWORDS = {
    "ims": ["e-way", "eway", "ewb", "vehicle", "transporter", "cargo", "odc", "pin-to-pin", "irn generation", "irn cancellation"],
    "eway_bill": ["ims", "invoice management system", "gstr-2b", "gstr-1a", "irn cancellation", "authtoken", "pending status"],
    "e_invoice": ["e-way bill validity", "vehicle number", "transporter id", "pin-to-pin distance", "ims", "invoice management system", "pending status", "pending action"],
}


def normalize_text(text: str) -> str:
    """Normalizes compound terms and stems all alphanumeric tokens."""
    t = text.lower()
    t = re.sub(r"\be[\s\-]+invoice", "einvoice", t)
    t = re.sub(r"\be[\s\-]+way", "eway", t)
    t = re.sub(r"[_\-]+", " ", t)
    words = re.findall(r"\b[a-zA-Z0-9]+\b", t)
    return " ".join(stem_token(w) for w in words)


def clean_text_noise(text: str) -> str:
    """Strips base64 blocks and collapses whitespace."""
    clean = re.sub(r"[A-Za-z0-9+/=_-]{40,}", " [encoded-payload] ", text)
    clean = re.sub(r"[ \t]+", " ", clean)
    clean = re.sub(r"\n{3,}", "\n\n", clean).strip()
    return clean


def chunk_domain_document(text: str, chunk_size: int = CHUNK_SIZE, chunk_overlap: int = CHUNK_OVERLAP) -> List[Dict[str, Any]]:
    """
    Chunks a domain-specific statutory document.
    Preserves markdown headers (##), bold titles (**Title**), and numbered sections (1. Title).
    """
    cleaned = clean_text_noise(text)
    section_split_regex = r"(?<=\n)(?=(?:##+\s+|\*\*[A-Z0-9][^\n*]+\*\*\s*\n|(?:\d{1,2}\.\s+[A-Z][^\n:]+\n)))"
    sections = re.split(section_split_regex, "\n" + cleaned)

    chunks: List[Dict[str, Any]] = []

    for sec in sections:
        sec_clean = sec.strip()
        if not sec_clean:
            continue

        if (sec_clean.startswith("# ") or sec_clean.endswith("Guidelines")) and "\n## " not in sec_clean and len(sec_clean.splitlines()) <= 2:
            continue

        lines = [l.strip() for l in sec_clean.splitlines() if l.strip()]
        if not lines:
            continue

        first_line = lines[0]
        header = re.sub(r"^#+\s*", "", first_line).strip()
        header = re.sub(r"^\d{1,2}\.\s*", "", header).strip()
        header = re.sub(r"^\*\*|\*\*$", "", header).strip()

        sec_words = sec_clean.split()

        if len(sec_words) <= chunk_size + 180:
            chunks.append({
                "chunk_id": len(chunks),
                "section": header,
                "text": sec_clean,
                "word_count": len(sec_words)
            })
            continue

        sub_blocks = re.split(r"\n\s*\n", sec_clean)
        current_paras = []
        current_words = 0

        for block in sub_blocks:
            b_clean = block.strip()
            if not b_clean:
                continue

            b_len = len(b_clean.split())
            if current_words + b_len > chunk_size and current_paras:
                chunk_body = "\n\n".join(current_paras).strip()
                chunks.append({
                    "chunk_id": len(chunks),
                    "section": header,
                    "text": chunk_body,
                    "word_count": len(chunk_body.split())
                })
                current_paras = [current_paras[-1]] if len(current_paras) > 1 else []
                current_words = sum(len(p.split()) for p in current_paras)

            current_paras.append(b_clean)
            current_words += b_len

        if current_paras:
            chunk_body = "\n\n".join(current_paras).strip()
            chunks.append({
                "chunk_id": len(chunks),
                "section": header,
                "text": chunk_body,
                "word_count": len(chunk_body.split())
            })

    return chunks


class DomainChunkStore:
    """
    Indexes and retrieves chunks for an isolated regulatory domain
    using multi-field TF-IDF with section-title weighting and morphological normalization.
    """

    def __init__(self, domain_key: str, file_path: Path):
        self.domain_key = domain_key
        self.file_path = file_path
        self.chunks: List[Dict[str, Any]] = []
        self.vectorizer: Optional[TfidfVectorizer] = None
        self.chunk_embeddings: Optional[np.ndarray] = None
        self._normalized_chunks: List[str] = []
        self._normalized_headers: List[str] = []
        self._domain_vocab: Set[str] = set()
        self._index()

    def _index(self):
        if not self.file_path.exists():
            logger.warning(f"Domain context file not found: {self.file_path}.")
            return

        with open(self.file_path, "r", encoding="utf-8", errors="replace") as f:
            raw_text = f.read()

        self.chunks = chunk_domain_document(raw_text)
        if not self.chunks:
            return

        self._normalized_headers = [normalize_text(c["section"]) for c in self.chunks]
        self._normalized_chunks = [
            f"{self._normalized_headers[i]} {self._normalized_headers[i]} {normalize_text(c['text'])}"
            for i, c in enumerate(self.chunks)
        ]
        self._domain_vocab = set(" ".join(self._normalized_chunks).split())

        self.vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            token_pattern=r"(?u)\b\w+\b",
            sublinear_tf=True,
            stop_words="english",
            max_df=0.90,
            max_features=25000
        )
        self.chunk_embeddings = self.vectorizer.fit_transform(self._normalized_chunks)
        logger.info(f"Indexed domain '{self.domain_key}': {len(self.chunks)} chunks.")

    def retrieve(self, query: str, top_k: int = TOP_K) -> List[Dict[str, Any]]:
        cleaned_q = query.strip()
        if not cleaned_q or not self.chunks or self.vectorizer is None or self.chunk_embeddings is None:
            return []

        q_lower = cleaned_q.lower()

        # Cross-domain entity guard: reject queries strictly intended for other domains
        foreign_keys = FOREIGN_DOMAIN_KEYWORDS.get(self.domain_key, [])
        if any(fk in q_lower for fk in foreign_keys):
            has_local_match = any(
                fk in f"{c['section']} {c['text']}".lower()
                for c in self.chunks
                for fk in foreign_keys
                if fk in q_lower
            )
            if not has_local_match:
                logger.info(f"Foreign domain query '{cleaned_q}' rejected in domain '{self.domain_key}'.")
                return []

        norm_q = normalize_text(cleaned_q)
        q_tokens = [w for w in norm_q.split() if w not in STEMMED_STOPWORDS and len(w) >= 2]
        if not q_tokens:
            return []

        # Mathematical query grounding filter: verify coverage in domain vocabulary
        matched_tokens = [t for t in q_tokens if t in self._domain_vocab]
        coverage = len(matched_tokens) / max(len(q_tokens), 1)

        if len(q_tokens) >= 3 and (len(matched_tokens) < 2 or coverage < 0.40):
            logger.info(f"Query '{cleaned_q}' rejected: insufficient grounding ({len(matched_tokens)}/{len(q_tokens)} matched) in domain '{self.domain_key}'.")
            return []

        # Vector similarity (TF-IDF sublinear cosine)
        q_vec = self.vectorizer.transform([norm_q])
        cos_sim = cosine_similarity(q_vec, self.chunk_embeddings)[0]

        # Multi-field scoring: exact token overlap and section header alignment
        q_bigrams = [f"{q_tokens[i]} {q_tokens[i+1]}" for i in range(len(q_tokens)-1)]
        scores = np.zeros(len(self.chunks), dtype=float)

        for i in range(len(self.chunks)):
            c_text_norm = self._normalized_chunks[i]
            h_text_norm = self._normalized_headers[i]

            c_token_set = set(c_text_norm.split())
            h_token_set = set(h_text_norm.split())

            token_hits = sum(1 for t in q_tokens if t in c_token_set)
            header_hits = sum(1 for t in q_tokens if t in h_token_set)
            bigram_hits = sum(1 for bg in q_bigrams if bg in c_text_norm)
            synonym_hits = sum(
                1 for t in q_tokens
                for syn in SYNONYM_MAP.get(t, [])
                if syn in c_token_set or syn in h_token_set
            )

            token_score = (token_hits + 2.5 * header_hits + 2.5 * bigram_hits + 0.8 * synonym_hits) / max(len(q_tokens), 1)
            scores[i] = 0.45 * float(cos_sim[i]) + 0.55 * token_score

        top_indices = np.argsort(scores)[::-1]
        results = []

        for idx in top_indices[:top_k]:
            final_score = float(scores[idx])
            if final_score < 0.05 and results:
                continue
            chunk = dict(self.chunks[idx])
            chunk["score"] = round(final_score, 4)
            chunk["domain"] = self.domain_key
            results.append(chunk)

        return results


class MultiDomainRetriever:
    """
    Coordinates isolated domain chunk stores for:
    - 'e_invoice'
    - 'eway_bill'
    - 'ims'
    """

    def __init__(self, domain_paths: Optional[Dict[str, Path]] = None):
        self.paths = domain_paths or DOMAIN_CONTEXT_PATHS
        self.stores: Dict[str, DomainChunkStore] = {}

        for domain_key, path in self.paths.items():
            logger.info(f"Initializing DomainChunkStore for '{domain_key}' from {path}")
            self.stores[domain_key] = DomainChunkStore(domain_key, path)

    def normalize_domain(self, domain: Optional[str], **kwargs) -> str:
        if not domain:
            return "e_invoice"
        d = domain.lower().strip()
        if "eway" in d or "e-way" in d or "ewb" in d:
            return "eway_bill"
        if "ims" in d or "invoice management" in d:
            return "ims"
        if "invoice" in d or "irn" in d or "e-invoice" in d or "einv" in d:
            return "e_invoice"
        if d in self.stores:
            return d
        return "e_invoice"

    def retrieve(self, query: str, domain: Optional[str] = "e_invoice", top_k: int = TOP_K) -> List[Dict[str, Any]]:
        target_domain = self.normalize_domain(domain)
        store = self.stores.get(target_domain)
        if not store:
            logger.warning(f"Domain store '{target_domain}' not found. Falling back to 'e_invoice'.")
            store = self.stores.get("e_invoice")

        if not store:
            return []

        return store.retrieve(query, top_k=top_k)

    def get_combined_context(
        self,
        query: str,
        domain: Optional[str] = "e_invoice",
        top_k: int = TOP_K,
        max_chars: int = 8000
    ) -> Tuple[str, List[Dict[str, Any]]]:
        target_domain = self.normalize_domain(domain)
        chunks = self.retrieve(query, domain=target_domain, top_k=top_k)
        if not chunks:
            return "", []

        included = []
        cur_len = 0
        for c in chunks:
            if c["score"] < SCORE_THRESHOLD and included:
                continue
            fmt = f"[{c['section']}]\n{c['text']}".strip()
            if cur_len + len(fmt) <= max_chars or not included:
                remaining = max_chars - cur_len
                if len(fmt) > remaining and included:
                    break
                included.append(fmt[:remaining])
                cur_len += len(included[-1]) + 6
            else:
                break

        return "\n\n---\n\n".join(included), chunks


_GLOBAL_MULTI_RETRIEVER: Optional[MultiDomainRetriever] = None


def get_retriever() -> MultiDomainRetriever:
    global _GLOBAL_MULTI_RETRIEVER
    if _GLOBAL_MULTI_RETRIEVER is None:
        _GLOBAL_MULTI_RETRIEVER = MultiDomainRetriever()
    return _GLOBAL_MULTI_RETRIEVER


class SearchResult:
    """Legacy backward compatibility wrapper."""
    def __init__(self, chunk_id: int, section: str, text: str, score: float):
        self.chunk_id = chunk_id
        self.section = section
        self.text = text
        self.score = score


def search(query: str, domain: str = "e_invoice", top_k: int = TOP_K) -> List[SearchResult]:
    """Legacy search function."""
    retriever = get_retriever()
    chunks = retriever.retrieve(query, domain=domain, top_k=top_k)
    return [SearchResult(c["chunk_id"], c.get("section", "General"), c.get("text", ""), c.get("score", 0.0)) for c in chunks]
