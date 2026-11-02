"""
Dynamic Multi-Input HSN Semantic Matcher & Tariff Intelligence Engine
File: src/nlp/hsn_intelligence.py

Specification Architecture:
Processes dynamic, batch, or multi-row invoice streams completely offline using vector geometry.

1. System Pipeline & Data Flow:
   [Master HSN Catalog (15,000+ codes)]
                    │
                    ▼ (Run once at boot / persistence)
       [Pre-computed Embedding Matrix (N × 384)]
                    │
                    │ ◄─── [Dynamic Inbound Stream (M items: array/file/payload)]
                    │                 │
                    │                 ▼
                    │      [Batch Encode: (M × 384)]
                    │                 │
                    ▼                 ▼
             [Matrix Dot-Product: (M × N)]
                            │
                            ▼
                [Row-wise Argmax & Top-k]
                            │
                            ▼
           [Structured Output: Match + Confidence]

2. Dynamic Implementation Steps:
   Phase 1: Zero-Latency Startup & Index Persistence (instant binary matrix load into RAM)
   Phase 2: Dynamic Batch Vectorization (variable sizing, strips junk chars/quantities, L2 normalized Q)
   Phase 3: Parallel Geometric Matching (S = Q · D^T in a single BLAS dot-product)
   Phase 4: Dynamic Thresholding & Guardrails:
            - Automated Match (>= 0.70): High confidence, auto-assign
            - Flag for Review (0.45 <= score < 0.70): Moderate alignment, top-3 runners-up
            - Unmapped / Fallback (< 0.45): Insufficient context, mark unclassified

3. Dynamic Ingestion Adaptors:
   - Spreadsheet Uploads (XLSX/CSV): reads description column, joins matches in vectorized blocks of 256-512
   - REST / gRPC Microservice: accepts JSON payloads, executes near real-time CPU inference
   - Database / Message Queue: asynchronous consumer worker polling and updating line items in bulk

4. Operational Guardrails:
   - Unit L2 Normalization (||v||_2 = 1)
   - Batch Chunking (blocks of 256 for batches > 1000)
   - Multi-Candidate Payload (Top-1 match + Top-3 runners-up)
   - 100% Backwards Compatibility with Day 05 HSNSemanticSearchEngine & classify_description
"""

import os

# Prevent OpenBLAS thread allocation failure on Windows
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import re
import time
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union, Set

import numpy as np
import pandas as pd
import torch

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
TARIFF_PARQUET = ROOT_DIR / "data" / "tariff_master.parquet"
INDEX_BGE_NPY = ROOT_DIR / "data" / "tariff_vector_index_bge.npy"
MAP_HIERARCHY_PARQUET = ROOT_DIR / "data" / "tariff_hierarchy_map.parquet"
INDEX_384_NPY = ROOT_DIR / "data" / "tariff_vector_index_384.npy"
INDEX_128_NPY = ROOT_DIR / "data" / "tariff_vector_index.npy"
MLP_MODEL_PATH = ROOT_DIR / "models" / "hsn_contrastive_mlp.pt"

BGE_SNAPSHOT = (
    Path(os.environ.get("USERPROFILE", ""))
    / ".cache"
    / "huggingface"
    / "hub"
    / "models--BAAI--bge-small-en-v1.5"
    / "snapshots"
    / "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"
)

CROSS_ENCODER_SNAPSHOT = (
    Path(os.environ.get("USERPROFILE", ""))
    / ".cache"
    / "huggingface"
    / "hub"
    / "models--cross-encoder--ms-marco-MiniLM-L-6-v2"
    / "snapshots"
    / "233902d25c440f23af6f7d6e94d2946bac0bee0a"
)

LOCAL_MINILM_SNAPSHOT = (
    Path(os.environ.get("USERPROFILE", ""))
    / ".cache"
    / "huggingface"
    / "hub"
    / "models--sentence-transformers--all-MiniLM-L6-v2"
    / "snapshots"
    / "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
)

from src.nlp.hsn_search import HSNSemanticSearchEngine, SearchResultList
from src.models.tokenizer import FeatureHashingTokenizer
from src.models.hsn_encoder import HSNContrastiveMLP


# ============================================================================
# PHASE 2 HELPER: JUNK CHARACTER & QUANTITY STRIPPER
# ============================================================================

# Unit and packaging tokens commonly appended to invoice line items
QUANTITY_UNIT_PATTERN = re.compile(
    r"\b\d+(\.\d+)?\s*(pcs|pc|pieces|piece|pkt|pkts|packets|packet|nos|no|units|unit|"
    r"kg|kgs|kilogram|kilograms|gms|gm|grams|gram|mtr|mtrs|meter|meters|metre|metres|"
    r"litre|litres|ltr|ltrs|dozen|doz|box|boxes|carton|cartons|ctn|bundle|bundles|"
    r"set|sets|sqft|sqm|sqmm|roll|rolls|drum|drums|can|cans|pair|pairs|bags?|btl|bottles?|"
    r"pk|pck|tin|tins|vial|vials|amp|ampoules?|gross|pack|packs)\b",
    re.IGNORECASE,
)

# Common invoice noise prefixes e.g. "Item #1:", "Sl.No. 4 -", "Line 01:"
NOISE_PREFIX_PATTERN = re.compile(
    r"^(item\s*#?\d+[:\s\-\.]*|sl\.?\s*no\.?\s*\d+[:\s\-\.]*|sr\.?\s*no\.?\s*\d+[:\s\-\.]*|"
    r"line\s*#?\d+[:\s\-\.]*|part\s*#?\s*[a-z0-9\-]+[:\s\-\.]*)",
    re.IGNORECASE,
)

# Punctuation and delimiter junk to clean
DELIMITER_JUNK_PATTERN = re.compile(r"[\t\r\n\x00-\x1f\x7f-\x9f\u200b-\u200d\ufeff]")
EXTRA_CHARS_PATTERN = re.compile(r"[#*_~\|\^<>{}\[\]\(\);:]")

# Post-nominal trade specifiers (e.g., 'servo motor ac', 'ball bearing ss', 'valve ci')
POST_NOMINAL_QUALIFIERS = {
    "ac", "dc", "ss", "ms", "gi", "pvc", "hdpe", "xlpe", "ci", "di",
    "ptfe", "fr", "fhp", "hp", "kw", "w", "v", "a", "hz", "rpm",
    "3phase", "1phase", "2phase", "phase",
}


def stem_trade_word(w: str) -> str:
    """Morphological stemmer for English trade nouns and plural specifications."""
    w = w.lower().strip()
    if len(w) <= 3:
        return w
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith("es") and len(w) > 4 and w[-3] in "shxz":
        return w[:-2]
    if w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        return w[:-1]
    return w


def stem_word_set(words) -> Set[str]:
    return {stem_trade_word(w) for w in words if len(w) >= 2}


def clean_trade_description(text: object) -> str:
    """Strips control chars, delimiters, and trailing quantities (e.g. '10 pcs', 'pkt')

    to maximize semantic signal density before vector encoding.
    """
    if text is None or (isinstance(text, float) and np.isnan(text)):
        return ""
    s = str(text).strip()
    if not s:
        return ""

    # 1. Remove non-printable control characters & zero-width tokens
    s = DELIMITER_JUNK_PATTERN.sub(" ", s)

    # 2. Strip leading line/item noise prefixes (e.g., "Item 1: ")
    s = NOISE_PREFIX_PATTERN.sub("", s)

    # 3. Strip commercial unit quantities (e.g., "10 pcs", "5.5 kg", "2 pkts")
    s = QUANTITY_UNIT_PATTERN.sub(" ", s)

    # 4. Remove special noise symbols (keep periods in numbers like 8.8 or 2.5)
    s = EXTRA_CHARS_PATTERN.sub(" ", s)

    # 5. Normalize separators: replace slashes and commas with space
    s = re.sub(r"[/\\,+=]", " ", s)

    # 6. Normalize whitespace and lowercase
    s = re.sub(r"\s+", " ", s).strip().lower()

    # Fallback if over-cleaned to empty string
    if not s:
        s = re.sub(r"\s+", " ", str(text)).strip().lower()
    return s


# ============================================================================
# TECHNIQUE 2: DEPENDENCY PARSING / HEAD-NOUN EXTRACTION
# ============================================================================

class TradeDependencyParser:
    """Lightweight Trade Phrase Dependency Parser & Linguistic Normalizer.

    Normalizes dynamic invoice queries without hardcoded product/heading lists.
    - Isolates alphanumeric part/model codes from semantic vector queries
    - Strips commercial units and packaging container noise
    - Expands standard technical trade abbreviations
    - Isolates core product head noun and modifiers
    """

    TRADE_ABBREV = {
        "assy": "assembly",
        "rr": "rear",
        "fr": "front",
        "lh": "left hand",
        "rh": "right hand",
        "strg": "steering",
        "brg": "bearing",
        "mfg": "manufacturing",
        "qty": "quantity",
        "nos": "numbers",
        "pcs": "pieces",
        "pc": "piece",
        "pvc": "polyvinyl chloride",
        "ss": "stainless steel",
        "ss304": "304 stainless steel",
        "ss316": "316 stainless steel",
        "ms": "mild steel",
        "gi": "galvanized iron",
        "ci": "cast iron",
        "bsp": "british standard pipe",
        "npt": "national pipe thread",
        "elec": "electric",
        "cyl": "cylinder",
        "pneu": "pneumatic",
        "hyd": "hydraulic",
        "smps": "power supply",
        "ups": "power supply",
        "vfd": "variable frequency drive",
        "hex": "hexagonal",
        "sq": "square",
    }

    @classmethod
    def clean_and_normalize(cls, query: str) -> Tuple[str, str, str, str, List[str]]:
        """Generic trade normalization pipeline without hardcoded product lists.

        Returns:
            (head_noun, modifiers, clean_semantic_q, clean_full_q, part_numbers)
        """
        if not query:
            return "", "", "", "", []

        t = clean_trade_description(query)

        # 1. Strip standalone & counted packaging tokens
        t = re.sub(
            r"\b(\d+\s*)?(pcs|pc|nos|no|pkts?|packets?|boxes?|box|cartons?|carton|rolls?|roll|drums?|drum|bags?|bag|units?|sets?)\b",
            " ",
            t,
            flags=re.IGNORECASE,
        )

        # 2. Strip dimensional & electrical units
        t = re.sub(
            r"\b\d+([/.]\d+)?\s*(mm|cm|m|inch|in|ft|kva|kwh|kw|hp|v|hz|amp|kg|gm|ltr|sq\s*mm|sqmm)\b",
            " ",
            t,
            flags=re.IGNORECASE,
        )

        # 3. Strip thread & grade specs
        t = re.sub(r"\bgrade\s*[\d.]+\b", " ", t, flags=re.IGNORECASE)
        t = re.sub(r"\b\d+\s*phases?\b", " ", t, flags=re.IGNORECASE)
        t = re.sub(r"\b\d+\s*cores?\b", " ", t, flags=re.IGNORECASE)
        t = re.sub(r"\b\d+\s*[-/xX]\s*\d+([.]\d+)?\b", " ", t)
        t = re.sub(r"\b[m|M]\d+\b", " ", t)

        # 4. Expand generic industrial trade abbreviations
        tokens = t.split()
        expanded_tokens = [cls.TRADE_ABBREV.get(tok.lower(), tok) for tok in tokens]
        t_full = " ".join(expanded_tokens)

        # 5. Identify part/model numbers (tokens with both letters and numbers, e.g. ms1, 6204-2rs)
        part_numbers = re.findall(r"\b(?=[a-z]*\d)[a-z0-9-]+\b", t_full, flags=re.IGNORECASE)

        # 6. Semantic query for embedding (strip part numbers so they don't hijack vector search)
        t_semantic = t_full
        for pn in part_numbers:
            t_semantic = re.sub(r"\b" + re.escape(pn) + r"\b", " ", t_semantic, flags=re.IGNORECASE)
        t_semantic = re.sub(r"[^a-zA-Z\s-]", " ", t_semantic)
        t_semantic = " ".join(t_semantic.split()).lower()
        if not t_semantic:
            t_semantic = t_full.lower()

        # 7. Extract head noun and modifiers considering post-nominal trade qualifiers
        sem_tokens = t_semantic.split()
        if sem_tokens:
            sub_noun = sem_tokens[-1]
            for i in range(len(sem_tokens) - 1, -1, -1):
                tok_lower = sem_tokens[i].lower()
                if tok_lower not in POST_NOMINAL_QUALIFIERS and len(tok_lower) > 2:
                    sub_noun = sem_tokens[i]
                    break
            head_noun = sub_noun
            modifiers = " ".join([t for t in sem_tokens if t != sub_noun])
        else:
            head_noun = t_semantic
            modifiers = ""

        return head_noun, modifiers, t_semantic, t_full.lower(), part_numbers

    @classmethod
    def expand_acronyms(cls, text: str) -> str:
        """Expands trade acronyms."""
        if not text:
            return ""
        tokens = text.split()
        expanded = [cls.TRADE_ABBREV.get(t.lower(), t) for t in tokens]
        return " ".join(expanded)

    @classmethod
    def extract_head_noun_and_modifiers(cls, query: str) -> Tuple[str, str, str]:
        """Compatibility signature returning (head_noun, modifiers, cleaned_semantic_q)."""
        head_noun, modifiers, t_sem, _, _ = cls.clean_and_normalize(query)
        return head_noun, modifiers, t_sem


# ============================================================================
# DECISION GUARDRAIL ENUMS & DATA STRUCTURES
# ============================================================================

class HSNMatchDecision(str, Enum):
    AUTOMATED_MATCH = "AUTOMATED_MATCH"    # score >= 0.70
    FLAG_FOR_REVIEW = "FLAG_FOR_REVIEW"    # 0.45 <= score < 0.70
    UNMAPPED = "UNMAPPED"                  # score < 0.45


class HSNConfidenceLevel(str, Enum):
    HIGH = "HIGH"
    MODERATE = "MODERATE"
    LOW = "LOW"


class HSNBatchItemResult(dict):
    """Structured response container for a single matched invoice item."""

    def __init__(
        self,
        query_index: int,
        raw_description: str,
        cleaned_description: str,
        decision: HSNMatchDecision,
        confidence_score: float,
        matched_hsn: Optional[str] = None,
        matched_hsn_4digit: Optional[str] = None,
        chapter: Optional[str] = None,
        official_description: Optional[str] = None,
        standard_rate: Optional[float] = None,
        is_blocked_17_5: int = 0,
        blocked_17_5_reason: str = "Eligible",
        top_match: Optional[Dict[str, Any]] = None,
        runners_up: Optional[List[Dict[str, Any]]] = None,
        match_type: str = "Semantic Vector Dot-Product",
    ):
        score_val = float(np.clip(confidence_score, 0.0, 1.0))
        pct_val = round(score_val * 100.0, 2)
        conf_level = (
            HSNConfidenceLevel.HIGH.value
            if score_val >= 0.70
            else (HSNConfidenceLevel.MODERATE.value if score_val >= 0.45 else HSNConfidenceLevel.LOW.value)
        )

        data = {
            "query_index": int(query_index),
            "raw_description": str(raw_description),
            "cleaned_description": str(cleaned_description),
            "decision": decision.value if isinstance(decision, HSNMatchDecision) else str(decision),
            "confidence_score": round(score_val, 4),
            "confidence_pct": pct_val,
            "confidence_level": conf_level,
            "matched_hsn": str(matched_hsn) if matched_hsn else None,
            "matched_hsn_4digit": str(matched_hsn_4digit) if matched_hsn_4digit else None,
            "chapter": str(chapter) if chapter else None,
            "official_description": str(official_description) if official_description else "",
            "standard_rate": float(standard_rate) if standard_rate is not None else 18.0,
            "is_blocked_17_5": int(is_blocked_17_5),
            "blocked_17_5_reason": str(blocked_17_5_reason),
            "top_match": top_match or {},
            "runners_up": runners_up or [],
            "match_type": str(match_type),
        }
        super().__init__(data)

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(f"'HSNBatchItemResult' has no attribute '{name}'")


class HSNBatchResultList(list):
    """Container holding multi-row match results along with batch-level analytics."""

    def __init__(
        self,
        matches: List[HSNBatchItemResult],
        total_items: int = 0,
        latency_ms: float = 0.0,
        embedding_dim: int = 384,
        catalog_size: int = 0,
        model_name: str = "Dynamic Multi-Input HSN Matcher",
    ):
        super().__init__(matches)
        self.matches = matches
        self.total_items = total_items or len(matches)
        self.latency_ms = round(latency_ms, 2)
        self.embedding_dim = embedding_dim
        self.catalog_size = catalog_size
        self.model_name = model_name

        # Summary statistics
        self.automated_matches = sum(1 for m in matches if m.get("decision") == HSNMatchDecision.AUTOMATED_MATCH.value)
        self.flagged_for_review = sum(1 for m in matches if m.get("decision") == HSNMatchDecision.FLAG_FOR_REVIEW.value)
        self.unmapped = sum(1 for m in matches if m.get("decision") == HSNMatchDecision.UNMAPPED.value)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_items": self.total_items,
            "automated_matches": self.automated_matches,
            "flagged_for_review": self.flagged_for_review,
            "unmapped": self.unmapped,
            "latency_ms": self.latency_ms,
            "embedding_dim": self.embedding_dim,
            "catalog_size": self.catalog_size,
            "model_name": self.model_name,
            "items": [dict(m) for m in self.matches],
        }

    def to_dataframe(self) -> pd.DataFrame:
        rows = []
        for m in self.matches:
            r = {
                "raw_description": m["raw_description"],
                "cleaned_description": m["cleaned_description"],
                "matched_hsn": m["matched_hsn"],
                "matched_hsn_4digit": m["matched_hsn_4digit"],
                "chapter": m["chapter"],
                "decision": m["decision"],
                "confidence_score": m["confidence_score"],
                "confidence_pct": m["confidence_pct"],
                "confidence_level": m["confidence_level"],
                "official_description": m["official_description"],
                "standard_rate": m["standard_rate"],
                "is_blocked_17_5": m["is_blocked_17_5"],
            }
            # Add top 3 runners-up as flat columns
            runners = m.get("runners_up", [])
            for idx in range(3):
                col_hsn = f"runner_up_{idx + 1}_hsn"
                col_score = f"runner_up_{idx + 1}_score"
                if idx < len(runners):
                    r[col_hsn] = runners[idx].get("hsn_code")
                    r[col_score] = runners[idx].get("score")
                else:
                    r[col_hsn] = None
                    r[col_score] = None
            rows.append(r)
        return pd.DataFrame(rows)


# ============================================================================
# CORE MATCHER: DYNAMIC MULTI-INPUT HSN SEMANTIC MATCHER
# ============================================================================

class DynamicHSNSemanticMatcher:
    """Core offline vector geometry engine for dynamic, multi-input, high-throughput

    HSN semantic matching.
    """

    AUTO_MATCH_THRESHOLD: float = 0.70
    REVIEW_THRESHOLD: float = 0.45
    CHUNK_SIZE_LIMIT: int = 1000
    CHUNK_BLOCK_SIZE: int = 256

    def __init__(
        self,
        tariff_parquet_path: Optional[Union[str, Path]] = None,
        index_bge_path: Optional[Union[str, Path]] = None,
        map_hierarchy_path: Optional[Union[str, Path]] = None,
        index_384_path: Optional[Union[str, Path]] = None,
        index_128_path: Optional[Union[str, Path]] = None,
        model_name_or_path: Optional[Union[str, Path]] = None,
        prefer_384d: bool = True,
        use_two_stage: bool = True,
        rerank_top_k: int = 5,
        auto_load: bool = True,
    ):
        self.tariff_path = Path(tariff_parquet_path or TARIFF_PARQUET)
        self.index_bge_path = Path(index_bge_path or INDEX_BGE_NPY)
        self.map_hierarchy_path = Path(map_hierarchy_path or MAP_HIERARCHY_PARQUET)
        self.index_384_path = Path(index_384_path or INDEX_384_NPY)
        self.index_128_path = Path(index_128_path or INDEX_128_NPY)
        self.model_path = model_name_or_path
        self.prefer_384d = prefer_384d
        self.use_two_stage = use_two_stage
        self.rerank_top_k = max(2, min(int(rerank_top_k), 20))

        # In-memory persisted matrix & catalog metadata
        self.catalog_matrix: Optional[np.ndarray] = None  # (N x D)
        self.catalog_df: Optional[pd.DataFrame] = None
        self.catalog_records: List[Dict[str, Any]] = []
        self.catalog_size: int = 0
        self.embedding_dim: int = 384
        self.active_model_type: str = "None"

        # Technique 2: Trade Dependency Parser & Head-Noun Extractor
        self.dependency_parser = TradeDependencyParser()

        # Technique 1: Two-Tier Cascade Search Data Structures
        self.heading_indices: List[int] = []
        self.leaf_indices: List[int] = []
        self.heading_records: List[Dict[str, Any]] = []
        self.leaf_records: List[Dict[str, Any]] = []
        self.heading_to_leaf_indices: Dict[str, List[int]] = {}
        self.heading_matrix: Optional[np.ndarray] = None
        self.leaf_matrix: Optional[np.ndarray] = None

        # Pre-computed tokens for fast overlap evaluation
        self.catalog_word_sets: List[set] = []

        # Model handles (loaded on demand)
        self._st_model: Any = None
        self._cross_encoder: Any = None
        self._mlp_model: Optional[HSNContrastiveMLP] = None
        self._tokenizer: Optional[FeatureHashingTokenizer] = None

        if auto_load:
            self._load_catalog_and_index()

    # ------------------------------------------------------------------------
    # PHASE 1: ZERO-LATENCY STARTUP & INDEX PERSISTENCE
    # ------------------------------------------------------------------------

    def _load_catalog_and_index(self) -> None:
        """Loads pre-computed binary vector matrix and statutory hierarchy map into RAM."""
        # 1. Load statutory metadata into RAM (prefer rich hierarchical map)
        if self.map_hierarchy_path.exists():
            self.catalog_df = pd.read_parquet(self.map_hierarchy_path).reset_index(drop=True)
        elif self.tariff_path.exists():
            self.catalog_df = pd.read_parquet(self.tariff_path).reset_index(drop=True)
        else:
            raise FileNotFoundError(f"Tariff master missing: {self.tariff_path}")

        self.catalog_records = self.catalog_df.to_dict(orient="records")
        self.catalog_size = len(self.catalog_df)

        # Pre-tokenize catalog descriptions for fast sub-millisecond lexical scoring
        self.catalog_word_sets = []
        for r in self.catalog_records:
            desc = (str(r.get("clean_description", "")) + " " + str(r.get("hierarchical_text", r.get("description", "")))).lower()
            tokens = set(re.findall(r"\b[a-z0-9]{2,}\b", desc))
            self.catalog_word_sets.append(tokens)

        # 2. Select pre-computed matrix: prefer BGE 384-D, fallback to all-MiniLM 384-D or 128-D
        loaded_npy_path = None
        if self.index_bge_path.exists():
            loaded_npy_path = self.index_bge_path
            self.active_model_type = "BAAI/bge-small-en-v1.5 + Cross-Encoder MiniLM (Two-Tier Hierarchical Cascade)"
        elif self.prefer_384d and self.index_384_path.exists():
            loaded_npy_path = self.index_384_path
            self.active_model_type = "SentenceTransformer (all-MiniLM-L6-v2 384-D)"
        elif self.index_128_path.exists():
            loaded_npy_path = self.index_128_path
            self.active_model_type = "HSNContrastiveMLP (128-D)"
        elif self.index_384_path.exists():
            loaded_npy_path = self.index_384_path
            self.active_model_type = "SentenceTransformer (all-MiniLM-L6-v2 384-D)"

        if loaded_npy_path is None or not loaded_npy_path.exists():
            raise FileNotFoundError(
                f"No vector index found at {self.index_bge_path}, {self.index_384_path}, or {self.index_128_path}. "
                "Run scripts/build_tariff_hierarchy_index.py first."
            )

        raw_matrix = np.load(loaded_npy_path).astype(np.float32)

        # Confirm shape matches catalog length
        if raw_matrix.shape[0] != self.catalog_size:
            min_len = min(raw_matrix.shape[0], self.catalog_size)
            raw_matrix = raw_matrix[:min_len]
            self.catalog_records = self.catalog_records[:min_len]
            self.catalog_word_sets = self.catalog_word_sets[:min_len]
            self.catalog_size = min_len

        self.embedding_dim = raw_matrix.shape[1]

        # Ensure unit L2 normalization: ||v|| = 1.0
        norms = np.linalg.norm(raw_matrix, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        self.catalog_matrix = raw_matrix / norms

        # Technique 1 Partition: Index Tier 1 Headings (4-digit) vs Tier 2 Leaves (8-digit)
        self.heading_indices = []
        self.leaf_indices = []
        self.heading_records = []
        self.leaf_records = []
        self.heading_to_leaf_indices = {}

        for idx, rec in enumerate(self.catalog_records):
            code_str = str(rec.get("hsn_code", "")).strip()
            if len(code_str) == 4:
                self.heading_indices.append(idx)
                self.heading_records.append(rec)
            elif len(code_str) == 8:
                leaf_pos = len(self.leaf_records)
                self.leaf_indices.append(idx)
                self.leaf_records.append(rec)
                h_parent = str(rec.get("heading", rec.get("hsn_4digit", code_str[:4]))).strip()
                if h_parent not in self.heading_to_leaf_indices:
                    self.heading_to_leaf_indices[h_parent] = []
                self.heading_to_leaf_indices[h_parent].append(leaf_pos)

        if self.heading_indices and self.catalog_matrix is not None:
            self.heading_matrix = self.catalog_matrix[self.heading_indices]
        else:
            self.heading_matrix = self.catalog_matrix

        if self.leaf_indices and self.catalog_matrix is not None:
            self.leaf_matrix = self.catalog_matrix[self.leaf_indices]
        else:
            self.leaf_matrix = self.catalog_matrix

    def _get_sentence_transformer(self) -> Any:
        """Lazy load primary Bi-Encoder (BAAI/bge-small-en-v1.5) with offline enforcement."""
        if self._st_model is None:
            from sentence_transformers import SentenceTransformer

            if BGE_SNAPSHOT.exists():
                source = str(BGE_SNAPSHOT)
            elif LOCAL_MINILM_SNAPSHOT.exists():
                source = str(LOCAL_MINILM_SNAPSHOT)
            else:
                source = "BAAI/bge-small-en-v1.5"
            self._st_model = SentenceTransformer(source)
            self._st_model.max_seq_length = 96
        return self._st_model

    def _get_cross_encoder(self) -> Any:
        """Lazy load second-stage Cross-Encoder (cross-encoder/ms-marco-MiniLM-L-6-v2) with offline enforcement."""
        if self._cross_encoder is None:
            from sentence_transformers import CrossEncoder

            source = str(CROSS_ENCODER_SNAPSHOT) if CROSS_ENCODER_SNAPSHOT.exists() else "cross-encoder/ms-marco-MiniLM-L-6-v2"
            self._cross_encoder = CrossEncoder(source, max_length=128)
        return self._cross_encoder

    def _get_mlp_model(self) -> Tuple[FeatureHashingTokenizer, HSNContrastiveMLP]:
        """Lazy load FeatureHashingTokenizer and 128-D PyTorch model."""
        if self._mlp_model is None or self._tokenizer is None:
            self._tokenizer = FeatureHashingTokenizer(dim=32768)
            self._mlp_model = HSNContrastiveMLP(input_dim=32768, hidden_dim=512, output_dim=self.embedding_dim)
            if MLP_MODEL_PATH.exists():
                sd = torch.load(MLP_MODEL_PATH, map_location="cpu")
                self._mlp_model.load_state_dict(sd)
            self._mlp_model.eval()
        return self._tokenizer, self._mlp_model

    # ------------------------------------------------------------------------
    # PHASE 2: DYNAMIC BATCH VECTORIZATION
    # ------------------------------------------------------------------------

    def vectorize_batch(
        self,
        descriptions: List[str],
        chunk_size: int = CHUNK_BLOCK_SIZE,
    ) -> Tuple[np.ndarray, List[str]]:
        """Cleans input descriptions and passes them into encoder in a vectorized batch pass.

        Produces an L2-normalized query matrix Q of size M x D.
        """
        if not descriptions:
            return np.empty((0, self.embedding_dim), dtype=np.float32), []

        # 1. Clean descriptions (strip delimiters, quantities, line noise)
        cleaned_texts = [clean_trade_description(t) for t in descriptions]
        m_items = len(cleaned_texts)

        # 2. Vectorize batch pass
        if self.embedding_dim == 384:
            model = self._get_sentence_transformer()
            # If batch > 1000 items, enforce chunking to prevent memory spikes
            if m_items > self.CHUNK_SIZE_LIMIT:
                chunks = []
                for start in range(0, m_items, chunk_size):
                    end = min(start + chunk_size, m_items)
                    c_emb = model.encode(
                        cleaned_texts[start:end],
                        batch_size=chunk_size,
                        normalize_embeddings=True,
                        show_progress_bar=False,
                        convert_to_numpy=True,
                    )
                    chunks.append(c_emb)
                q_matrix = np.vstack(chunks).astype(np.float32)
            else:
                q_matrix = model.encode(
                    cleaned_texts,
                    batch_size=min(chunk_size, max(m_items, 1)),
                    normalize_embeddings=True,
                    show_progress_bar=False,
                    convert_to_numpy=True,
                ).astype(np.float32)
        else:
            # Fallback 128-D MLP vectorizer
            tokenizer, mlp = self._get_mlp_model()
            chunks = []
            c_size = min(chunk_size, m_items)
            with torch.no_grad():
                for start in range(0, m_items, c_size):
                    end = min(start + c_size, m_items)
                    tok_batch = tokenizer.batch_tokenize(cleaned_texts[start:end])
                    z_batch = mlp(tok_batch).cpu().numpy()
                    chunks.append(z_batch)
            q_matrix = np.vstack(chunks).astype(np.float32)

        # 3. Vector Normalization: re-verify L2 unit norm (||v|| = 1.0)
        q_norms = np.linalg.norm(q_matrix, axis=1, keepdims=True)
        q_norms = np.where(q_norms == 0, 1.0, q_norms)
        q_matrix = q_matrix / q_norms

        return q_matrix, cleaned_texts

    # ------------------------------------------------------------------------
    # PHASE 3: PARALLEL GEOMETRIC MATCHING
    # ------------------------------------------------------------------------

    def compute_similarity_matrix(self, query_matrix: np.ndarray) -> np.ndarray:
        """Matrix-Matrix Multiplication: S = Q · D^T.

        Resulting matrix S has shape M x N.
        """
        if self.catalog_matrix is None:
            raise RuntimeError("Catalog matrix not initialized in RAM.")
        if query_matrix.shape[0] == 0:
            return np.empty((0, self.catalog_matrix.shape[0]), dtype=np.float32)

        # Single linear algebra operation (BLAS dot-product)
        # Q: (M x D), D^T: (D x N) -> S: (M x N)
        similarity_matrix = np.matmul(query_matrix, self.catalog_matrix.T)
        return similarity_matrix

    # ------------------------------------------------------------------------
    # PHASE 4: DYNAMIC THRESHOLDING & DECISION LOGIC
    # ------------------------------------------------------------------------

    def calibrate_confidence_score(
        self,
        raw_cosine_score: float,
        query_words: set,
        cand_idx: int,
    ) -> float:
        """Calibrates raw vector dot-product into standard operational confidence score [0.0, 1.0].

        Combines calibrated dense semantic distance with token overlap alignment.
        """
        # Baseline semantic scaling: maps [0.20, 0.55] dense cosine into [0.35, 0.90]
        s_dense_cal = np.clip((raw_cosine_score - 0.20) / (0.55 - 0.20) * 0.55 + 0.35, 0.0, 0.95)

        # Token overlap bonus
        overlap_ratio = 0.0
        if query_words and cand_idx < len(self.catalog_word_sets):
            cand_words = self.catalog_word_sets[cand_idx]
            overlap = len(query_words & cand_words)
            overlap_ratio = overlap / max(1, len(query_words))

        final_score = float(np.clip(s_dense_cal + 0.15 * overlap_ratio, 0.0, 1.0))
        return final_score

    def _rerank_candidates(
        self,
        clean_query: str,
        candidate_indices: List[int],
        raw_sim_scores: List[float],
        candidate_records: Optional[List[Dict[str, Any]]] = None,
        head_noun: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Technique 4: Cross-Encoder Joint Attention Scoring + Tree-Path Breadcrumbs (Technique 3) + GIR 3(a).

        1. Passes (query, candidate tree-path breadcrumb description) pairs into cross-encoder for joint token interactions.
        2. Evaluates head-noun prominence to overcome modifier bias (e.g. Kashmir vs Apple, SS304 vs Nipple).
        3. Computes calibrated sigmoid attention probabilities and bi-encoder confidence.
        4. Applies GIR 3(a) 0.85x down-weight penalty for residual categories ('Other...')
           unless query explicitly shares tokens with that residual line.
        """
        if candidate_records is not None:
            candidates = candidate_records
        elif candidate_indices:
            candidates = [self.catalog_records[idx] for idx in candidate_indices]
        else:
            return []

        n_cands = len(candidates)
        if n_cands == 0:
            return []

        # Step B: Joint Attention Scoring via Cross-Encoder (evaluating item tree-path breadcrumbs)
        if self.use_two_stage:
            try:
                ce = self._get_cross_encoder()
                pairs = [
                    [clean_query, str(c.get("hierarchical_text") or c.get("clean_description", c.get("description", "")))]
                    for c in candidates
                ]
                ce_logits = ce.predict(pairs)
                if head_noun and head_noun.strip() and head_noun.strip().lower() != clean_query.strip().lower():
                    head_pairs = [
                        [head_noun.strip().lower(), str(c.get("hierarchical_text") or c.get("clean_description", c.get("description", "")))]
                        for c in candidates
                    ]
                    head_logits = ce.predict(head_pairs)
                    ce_logits = np.maximum(np.array(ce_logits, dtype=np.float32), np.array(head_logits, dtype=np.float32))

                # Calibrated sigmoid for MS-MARCO MiniLM logits centered at -4.5 with scale 1.8
                ce_probs = 1.0 / (1.0 + np.exp(-(np.array(ce_logits, dtype=np.float32) + 4.5) / 1.8))
            except Exception:
                ce_probs = np.array(raw_sim_scores, dtype=np.float32)
                ce_logits = np.zeros(n_cands, dtype=np.float32)
        else:
            ce_probs = np.array(raw_sim_scores, dtype=np.float32)
            ce_logits = np.zeros(n_cands, dtype=np.float32)

        # Calibrate raw bi-encoder cosine into operational confidence scale [0.10, 0.98]
        bi_sims = np.array(raw_sim_scores, dtype=np.float32)
        cal_bi = np.clip((bi_sims - 0.30) / (0.70 - 0.30), 0.10, 0.98)

        # Joint Ensemble: 50% calibrated bi-encoder + 50% cross-encoder attention
        raw_combined = 0.50 * cal_bi + 0.50 * ce_probs

        # Step C: GIR 3(a) Residual Downweighting, Subtype Compatibility & Capacity Alignment
        q_words_3 = set(re.findall(r"\b[a-z]{3,}\b", clean_query.lower()))
        stemmed_q = stem_word_set(q_words_3)
        q_lower = clean_query.lower()

        def check_real_residual(hier_text: str) -> bool:
            parts = str(hier_text).split(" -> ")
            leaf = parts[-1].strip().rstrip(".").lower()
            return bool(re.match(r"^(other|others|other parts|not elsewhere)\b", leaf, re.I))

        reranked = []
        for idx in range(n_cands):
            c = candidates[idx]
            h_text = str(c.get("hierarchical_text", c.get("clean_description", c.get("description", ""))))
            desc_lower = (str(c.get("description", "")) + " " + h_text).lower()
            code = str(c.get("hsn_code", ""))
            is_res = bool(c.get("is_residual", False)) or check_real_residual(h_text)

            raw_dist = c.get("distinctive_tokens", "")
            if isinstance(raw_dist, (list, set)):
                dist_tokens = set(str(t).lower() for t in raw_dist)
            else:
                dist_tokens = set(str(raw_dist).lower().split())

            # Dynamic morphological token extraction under GIR 3(a)
            cand_tokens = stem_word_set(re.findall(r"\b[a-z0-9]{2,}\b", desc_lower))
            shares_token = bool(stem_word_set(dist_tokens) & stemmed_q) or bool(cand_tokens & stemmed_q)

            multiplier = 1.0
            # GIR 3(a): Specific description preferred over general/residual basket ('Other...')
            if is_res and not shares_token:
                multiplier *= 0.85

            # Dynamic token overlap specificity boost:
            # If candidate description explicitly shares distinct descriptive tokens with the query, reward specificity
            if stemmed_q and cand_tokens:
                overlap_count = len(stemmed_q & cand_tokens)
                overlap_ratio = overlap_count / max(1, len(stemmed_q))
                if overlap_ratio >= 0.5:
                    multiplier *= (1.0 + min(0.15, 0.10 * overlap_ratio))

            final_score = raw_combined[idx] * multiplier

            cat_idx = candidate_indices[idx] if idx < len(candidate_indices) else -1
            reranked.append({
                "candidate": c,
                "catalog_idx": cat_idx,
                "final_score": float(np.clip(final_score, 0.0, 1.0)),
                "raw_combined": float(raw_combined[idx]),
                "bi_sim": float(raw_sim_scores[idx]),
                "ce_prob": float(ce_probs[idx]),
                "ce_logit": float(ce_logits[idx]),
                "multiplier": float(multiplier),
                "is_residual": is_res,
                "shares_token": shares_token,
            })

        reranked.sort(key=lambda x: x["final_score"], reverse=True)
        return reranked

    def _resolve_heading_to_leaf(
        self,
        clean_query: str,
        heading_code: str,
        q_vec: Optional[np.ndarray] = None,
    ) -> Optional[Dict[str, Any]]:
        """Resolves a 4-digit chapter heading down to its most specific full 8-digit statutory tariff item."""
        leaf_candidates = [
            (idx, rec) for idx, rec in enumerate(self.catalog_records)
            if str(rec.get("hsn_4digit", "")) == heading_code and len(str(rec.get("hsn_code", ""))) == 8
        ]
        if not leaf_candidates:
            leaf_candidates = [
                (idx, rec) for idx, rec in enumerate(self.catalog_records)
                if str(rec.get("hsn_code", "")).startswith(heading_code) and len(str(rec.get("hsn_code", ""))) == 8
            ]
        if not leaf_candidates:
            return None

        leaf_indices = [idx for idx, _ in leaf_candidates]
        leaf_recs = [rec for _, rec in leaf_candidates]

        # Calculate similarity across all candidate leaves under this heading
        if self.catalog_matrix is not None:
            try:
                if q_vec is None:
                    q_emb, _ = self.vectorize_batch([clean_query])
                    q_vec = q_emb[0]
                sub_sims = np.dot(self.catalog_matrix[leaf_indices], q_vec).flatten()
                top_k_leaf = min(8, len(leaf_recs))
                top_sub_idx = np.argsort(-sub_sims)[:top_k_leaf].tolist()
                top_indices = [leaf_indices[i] for i in top_sub_idx]
                top_sims = [float(sub_sims[i]) for i in top_sub_idx]
            except Exception:
                top_indices = leaf_indices[:min(8, len(leaf_indices))]
                top_sims = [0.5] * len(top_indices)
        else:
            top_indices = leaf_indices[:min(8, len(leaf_indices))]
            top_sims = [0.5] * len(top_indices)

        # Cross-encoder joint scoring on the candidate leaves
        reranked = self._rerank_candidates(clean_query, top_indices, top_sims)
        if reranked:
            return reranked[0]["candidate"]
        return leaf_recs[0]

    def match_batch(
        self,
        items: Union[List[str], np.ndarray, pd.Series],
        top_k: int = 4,
        chunk_size: int = CHUNK_BLOCK_SIZE,
    ) -> HSNBatchResultList:
        """End-to-end dynamic batch matching pipeline.

        Accepts arbitrary input batches, computes similarity matrix, and routes
        each item through operational guardrails.
        """
        t0 = time.perf_counter()

        # Coerce inputs to list of strings
        if isinstance(items, (np.ndarray, pd.Series)):
            raw_descriptions = [str(x) for x in items.tolist()]
        elif isinstance(items, list):
            raw_descriptions = [str(x) for x in items]
        elif isinstance(items, str):
            raw_descriptions = [items]
        else:
            raw_descriptions = [str(items)]

        m_count = len(raw_descriptions)
        if m_count == 0:
            return HSNBatchResultList(
                matches=[],
                total_items=0,
                latency_ms=0.0,
                embedding_dim=self.embedding_dim,
                catalog_size=self.catalog_size,
                model_name=self.active_model_type,
            )

        # Phase 2: Vectorize batch
        q_matrix, cleaned_texts = self.vectorize_batch(raw_descriptions, chunk_size=chunk_size)

        # Phase 3: Parallel dot-product S = Q · D^T
        sim_matrix = self.compute_similarity_matrix(q_matrix)  # (M x N)

        # Phase 4: Thresholding & Multi-candidate extraction
        results: List[HSNBatchItemResult] = []
        k_candidates = max(4, top_k)

        for i in range(m_count):
            raw_q = raw_descriptions[i]
            clean_q = cleaned_texts[i]

            # Fast check: reject empty or whitespace-only descriptions upfront
            if not clean_q or not clean_q.strip():
                results.append(
                    HSNBatchItemResult(
                        query_index=i,
                        raw_description=raw_q,
                        cleaned_description="",
                        decision=HSNMatchDecision.UNMAPPED,
                        confidence_score=0.0,
                        matched_hsn=None,
                        matched_hsn_4digit=None,
                        chapter=None,
                        official_description="",
                        standard_rate=18.0,
                        is_blocked_17_5=0,
                        blocked_17_5_reason="Unmapped",
                        top_match={},
                        runners_up=[],
                        match_type="Empty Query Rejection",
                    )
                )
                continue

            # Fast check: Read-only lookup in verified store (data/hsn_verified_store.parquet)
            try:
                from src.ml.hsn_verified_store import get_hsn_verified_store
                v_store = get_hsn_verified_store()
                cached_rec = v_store.lookup(raw_q) or v_store.lookup(clean_q)
                if cached_rec:
                    code_val = str(cached_rec.get("hsn_code", ""))
                    results.append(
                        HSNBatchItemResult(
                            query_index=i,
                            raw_description=raw_q,
                            cleaned_description=clean_q,
                            decision=HSNMatchDecision.AUTOMATED_MATCH,
                            confidence_score=1.0,
                            matched_hsn=code_val,
                            matched_hsn_4digit=code_val[:4] if len(code_val) >= 4 else code_val,
                            chapter=code_val[:2] if len(code_val) >= 2 else "00",
                            official_description=str(cached_rec.get("description", "")),
                            standard_rate=float(cached_rec.get("gst_rate", 18.0)),
                            is_blocked_17_5=0,
                            blocked_17_5_reason="Eligible: General ITC",
                            top_match={
                                "hsn_code": code_val,
                                "description": str(cached_rec.get("description", "")),
                                "score": 1.0,
                                "confidence_pct": 100.0,
                                "standard_rate": float(cached_rec.get("gst_rate", 18.0)),
                            },
                            runners_up=[],
                            match_type="Verified Qwen Memory Store (<0.5ms)",
                        )
                    )
                    continue
            except Exception:
                pass

            # Fast check: direct numeric HSN input (e.g. "84818090" or "8481")
            digit_only = re.sub(r"[^0-9]", "", clean_q)
            if digit_only and len(digit_only) >= 2 and clean_q.replace(" ", "") == digit_only:
                # Direct code search
                matched_idx = -1
                for c_idx, rec in enumerate(self.catalog_records):
                    code = str(rec.get("hsn_code", ""))
                    if code.startswith(digit_only) or digit_only.startswith(code):
                        matched_idx = c_idx
                        break

                if matched_idx >= 0:
                    cand = self.catalog_records[matched_idx]
                    code_val = str(cand.get("hsn_code", ""))
                    results.append(
                        HSNBatchItemResult(
                            query_index=i,
                            raw_description=raw_q,
                            cleaned_description=clean_q,
                            decision=HSNMatchDecision.AUTOMATED_MATCH,
                            confidence_score=1.0,
                            matched_hsn=code_val,
                            matched_hsn_4digit=str(cand.get("hsn_4digit", code_val[:4])),
                            chapter=str(cand.get("chapter", code_val[:2])),
                            official_description=str(cand.get("description", "")),
                            standard_rate=float(cand.get("standard_rate", 18.0)),
                            is_blocked_17_5=int(cand.get("is_blocked_17_5", 0)),
                            blocked_17_5_reason=str(cand.get("blocked_17_5_reason", "Eligible")),
                            top_match={
                                "hsn_code": code_val,
                                "score": 1.0,
                                "description": str(cand.get("description", "")),
                                "standard_rate": float(cand.get("standard_rate", 18.0)),
                            },
                            runners_up=[],
                            match_type="Direct Numeric Tariff Match",
                        )
                    )
                    continue

            # -------------------------------------------------------------
            # MODULE 1: Pre-Processing & Linguistic Decomposition
            # -------------------------------------------------------------
            # -------------------------------------------------------------
            # MODULE 1: Pre-Processing & Linguistic Normalization
            # -------------------------------------------------------------
            head_noun, modifiers, q_sem, q_full, part_nos = self.dependency_parser.clean_and_normalize(raw_q)
            if not q_sem:
                q_sem = clean_q
            if not q_full:
                q_full = clean_q

            # -------------------------------------------------------------
            # MODULE 2: Hybrid Candidate Retrieval (Dense + Lexical)
            # Full catalog search without brittle physical heading quarantine
            # -------------------------------------------------------------
            dense_scores = sim_matrix[i]  # (N,)

            # Sparse lexical keyword recall against pre-tokenized catalog descriptions
            q_tokens = set(re.findall(r"\b[a-z0-9]{2,}\b", q_full))
            lex_scores = np.zeros(self.catalog_size, dtype=np.float32)
            if q_tokens:
                q_len = len(q_tokens)
                for c_idx, c_words in enumerate(self.catalog_word_sets):
                    if c_words:
                        overlap = len(q_tokens & c_words)
                        if overlap > 0:
                            lex_scores[c_idx] = overlap / q_len

            # Reciprocal candidate fusion: 65% dense vector semantics + 35% statutory lexical recall
            combined_scores = 0.65 * dense_scores + 0.35 * lex_scores
            pool_size = min(35, self.catalog_size)
            top_indices = np.argsort(-combined_scores)[:pool_size].tolist()
            candidates_to_rerank = [self.catalog_records[idx] for idx in top_indices]
            top_sims = [float(dense_scores[idx]) for idx in top_indices]
            candidate_headings = list(dict.fromkeys(str(c.get("heading", str(c.get("hsn_code", ""))[:4])) for c in candidates_to_rerank[:5]))

            # -------------------------------------------------------------
            # MODULE 3: Second-Stage Cross-Encoder Joint Token Reranking
            # Evaluates top candidates against dynamic hierarchical breadcrumbs
            # -------------------------------------------------------------
            reranked = self._rerank_candidates(
                q_sem,
                top_indices,
                top_sims,
                candidate_records=candidates_to_rerank,
                head_noun=head_noun,
            )

            if not reranked:
                top_item = {
                    "candidate": candidates_to_rerank[0],
                    "catalog_idx": top_indices[0] if top_indices else -1,
                    "final_score": float(top_sims[0]) if top_sims else 0.5,
                    "bi_sim": float(top_sims[0]) if top_sims else 0.5,
                    "multiplier": 1.0,
                }
                runners_ranked = []
            else:
                top_item = reranked[0]
                runners_ranked = reranked[1:]

            top_score = top_item["final_score"]
            raw_top = top_item.get("bi_sim", top_score)
            best_record = top_item["candidate"]
            best_code = str(best_record.get("hsn_code", ""))

            # -------------------------------------------------------------
            # MODULE 5: Statutory Rules & Tri-State Margin Guardrails
            # Auto-Pass (Green): Top-1 similarity >= 0.75 AND (Score_1 - Score_2) >= 0.15
            # Disambiguation / Review (Amber): 0.45 <= Top-1 < 0.75 OR (Score_1 - Score_2) < 0.15
            # Unmapped / Rejection (Red): Top-1 similarity < 0.45
            # -------------------------------------------------------------
            score_1 = top_score
            score_2 = runners_ranked[0]["final_score"] if runners_ranked else 0.0
            margin = float(score_1 - score_2)

            best_heading = str(best_record.get("hsn_4digit", best_code[:4]))
            best_rate = float(best_record.get("standard_rate", 18.0))

            # Evaluate competing classification paths (alternative Headings) and statutory tax divergence
            competing_alt_heading_score = 0.0
            competing_diff_rate_score = 0.0
            # Evaluate competing classification paths (alternative Headings) among top runners-up (top 3)
            competing_alt_heading_score = 0.0
            competing_diff_rate_score = 0.0
            for r in runners_ranked[:3]:
                r_cand = r.get("candidate", {})
                r_code = str(r_cand.get("hsn_4digit", str(r_cand.get("hsn_code", ""))[:4]))
                r_rate = float(r_cand.get("standard_rate", best_rate))
                r_score = float(r.get("final_score", 0.0))

                if r_code and r_code != best_heading and competing_alt_heading_score == 0.0:
                    competing_alt_heading_score = r_score
                if abs(r_rate - best_rate) > 0.01 and competing_diff_rate_score == 0.0:
                    competing_diff_rate_score = r_score

            if competing_alt_heading_score > 0:
                classification_margin = float(score_1 - competing_alt_heading_score)
            elif competing_diff_rate_score > 0:
                classification_margin = float(score_1 - competing_diff_rate_score)
            else:
                classification_margin = margin if margin >= 0.15 else 0.20

            if (score_1 >= 0.70 and classification_margin >= 0.10) or (score_1 >= 0.85 and margin >= 0.05):
                decision = HSNMatchDecision.AUTOMATED_MATCH
            elif score_1 >= self.REVIEW_THRESHOLD:
                decision = HSNMatchDecision.FLAG_FOR_REVIEW
            else:
                decision = HSNMatchDecision.UNMAPPED

            # Hierarchical Leaf Drilldown: ensure matched_hsn is a full 8-digit statutory tariff item
            if len(best_code) == 4 and decision != HSNMatchDecision.UNMAPPED:
                q_row_vec = q_matrix[i] if (q_matrix is not None and i < len(q_matrix)) else None
                leaf_rec = self._resolve_heading_to_leaf(q_sem, best_code, q_vec=q_row_vec)
                if leaf_rec is not None:
                    best_record = leaf_rec
                    best_code = str(best_record.get("hsn_code", best_code))

            # Build top candidate metadata
            top_cand_dict = {
                "hsn_code": best_code,
                "hsn_4digit": str(best_record.get("hsn_4digit", best_code[:4])),
                "chapter": str(best_record.get("chapter", best_code[:2])),
                "score": round(top_score, 4),
                "raw_cosine": round(raw_top, 4),
                "confidence_pct": round(top_score * 100.0, 2),
                "margin": round(margin, 4),
                "score_1": round(score_1, 4),
                "score_2": round(score_2, 4),
                "candidate_headings": candidate_headings[:3],
                "description": str(best_record.get("description", "")),
                "hierarchical_text": str(best_record.get("hierarchical_text", best_record.get("description", ""))),
                "standard_rate": float(best_record.get("standard_rate", 18.0)),
                "is_blocked_17_5": int(best_record.get("is_blocked_17_5", 0)),
                "blocked_17_5_reason": str(best_record.get("blocked_17_5_reason", "Eligible")),
                "is_residual": top_item.get("is_residual", False),
                "specificity_multiplier": top_item.get("multiplier", 1.0),
            }

            # Top-3 distinct runners-up (drilled down to 8-digit full HSN if length 4)
            runners_up = []
            seen_codes = {best_code}
            for r_info in runners_ranked:
                r_rec = r_info["candidate"]
                r_code = str(r_rec.get("hsn_code", ""))
                if len(r_code) == 4:
                    q_row_vec = q_matrix[i] if (q_matrix is not None and i < len(q_matrix)) else None
                    r_leaf = self._resolve_heading_to_leaf(q_sem, r_code, q_vec=q_row_vec)
                    if r_leaf is not None:
                        r_rec = r_leaf
                        r_code = str(r_rec.get("hsn_code", r_code))
                if r_code in seen_codes:
                    continue
                seen_codes.add(r_code)
                r_score = r_info["final_score"]
                r_raw = r_info.get("bi_sim", r_score)
                runners_up.append({
                    "hsn_code": r_code,
                    "hsn_4digit": str(r_rec.get("hsn_4digit", r_code[:4])),
                    "chapter": str(r_rec.get("chapter", r_code[:2])),
                    "score": round(r_score, 4),
                    "raw_cosine": round(r_raw, 4),
                    "confidence_pct": round(r_score * 100.0, 2),
                    "description": str(r_rec.get("description", "")),
                    "hierarchical_text": str(r_rec.get("hierarchical_text", r_rec.get("description", ""))),
                    "standard_rate": float(r_rec.get("standard_rate", 18.0)),
                    "is_blocked_17_5": int(r_rec.get("is_blocked_17_5", 0)),
                    "is_residual": r_info.get("is_residual", False),
                    "multiplier": r_info.get("multiplier", 1.0),
                })
                if len(runners_up) >= 3:
                    break

            item_res = HSNBatchItemResult(
                query_index=i,
                raw_description=raw_q,
                cleaned_description=clean_q,
                decision=decision,
                confidence_score=top_score,
                matched_hsn=best_code if decision != HSNMatchDecision.UNMAPPED else None,
                matched_hsn_4digit=str(best_record.get("hsn_4digit", best_code[:4])) if decision != HSNMatchDecision.UNMAPPED else None,
                chapter=str(best_record.get("chapter", best_code[:2])) if decision != HSNMatchDecision.UNMAPPED else None,
                official_description=str(best_record.get("description", "")),
                standard_rate=float(best_record.get("standard_rate", 18.0)),
                is_blocked_17_5=int(best_record.get("is_blocked_17_5", 0)),
                blocked_17_5_reason=str(best_record.get("blocked_17_5_reason", "Eligible")),
                top_match=top_cand_dict,
                runners_up=runners_up,
                match_type="Two-Stage BGE-Small + Cross-Encoder Rerank (GIR 3(a))" if self.use_two_stage else "Vector Dot-Product (N x 384)",
            )
            results.append(item_res)

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return HSNBatchResultList(
            matches=results,
            total_items=m_count,
            latency_ms=elapsed_ms,
            embedding_dim=self.embedding_dim,
            catalog_size=self.catalog_size,
            model_name=self.active_model_type,
        )

    def match_single(self, query: str, top_k: int = 5) -> HSNBatchItemResult:
        """Matches a single dynamic query string through the two-stage pipeline.

        Returns single HSNBatchItemResult with top candidate and runners-up.
        """
        batch_res = self.match_batch([query], top_k=top_k)
        return batch_res.matches[0]


# ============================================================================
# PHASE 3 ADAPTORS: DYNAMIC INGESTION ADAPTORS
# ============================================================================

class SpreadsheetIngestionAdaptor:
    """Ingestion Adaptor 1: Spreadsheet Uploads (XLSX / CSV).

    Reads item description column as an array; joins matched codes and confidence
    percentages as adjacent columns. Vectorized in blocks of 256–512 items.
    """

    CANDIDATE_DESC_COLS = [
        "description", "item_description", "product_description", "product_name",
        "item_name", "desc", "goods_description", "item_desc", "item", "trade_description",
    ]

    def __init__(self, matcher: DynamicHSNSemanticMatcher):
        self.matcher = matcher

    def detect_description_column(self, df: pd.DataFrame) -> str:
        """Auto-detects the item description column name in arbitrary client spreadsheets."""
        if len(df.columns) == 0:
            return "description"
        lower_cols = {str(c).strip().lower(): c for c in df.columns}
        for cand in self.CANDIDATE_DESC_COLS:
            if cand in lower_cols:
                return lower_cols[cand]
        # Fallback to first text column
        for c in df.columns:
            if df[c].dtype == object or str(df[c].dtype).startswith(("str", "object")):
                return c
        return df.columns[0]

    def process_dataframe(
        self,
        df: pd.DataFrame,
        description_col: Optional[str] = None,
        chunk_size: int = 256,
    ) -> pd.DataFrame:
        """Processes spreadsheet DataFrame, performing batch vector matching and

        joining result columns.
        """
        if len(df.columns) == 0:
            return df.copy()

        if description_col and description_col in df.columns:
            col = description_col
        else:
            col = self.detect_description_column(df)

        if col not in df.columns:
            # Create synthetic column if completely missing
            items = [""] * len(df)
        else:
            items = df[col].fillna("").astype(str).tolist()

        # Execute vectorized matching in blocks of 256–512 items
        batch_results = self.matcher.match_batch(items, chunk_size=chunk_size)

        out_df = df.copy()
        out_df["matched_hsn"] = [m["matched_hsn"] for m in batch_results]
        out_df["hsn_confidence_pct"] = [m["confidence_pct"] for m in batch_results]
        out_df["match_decision"] = [m["decision"] for m in batch_results]
        out_df["standard_gst_rate"] = [m["standard_rate"] for m in batch_results]
        out_df["official_hsn_description"] = [m["official_description"] for m in batch_results]
        out_df["runner_up_1_hsn"] = [
            m["runners_up"][0]["hsn_code"] if len(m.get("runners_up", [])) > 0 else None
            for m in batch_results
        ]
        out_df["runner_up_1_score"] = [
            m["runners_up"][0]["score"] if len(m.get("runners_up", [])) > 0 else None
            for m in batch_results
        ]
        return out_df

    def process_file(
        self,
        file_path_or_bytes: Union[str, Path, Any],
        description_col: Optional[str] = None,
        chunk_size: int = 256,
        is_excel: bool = False,
    ) -> pd.DataFrame:
        """Reads file, vectorizes, joins results, and returns augmented DataFrame."""
        if is_excel or (isinstance(file_path_or_bytes, (str, Path)) and str(file_path_or_bytes).endswith((".xlsx", ".xls"))):
            df = pd.read_excel(file_path_or_bytes)
        else:
            df = pd.read_csv(file_path_or_bytes)
        return self.process_dataframe(df, description_col=description_col, chunk_size=chunk_size)


class RESTMicroserviceAdaptor:
    """Ingestion Adaptor 2: REST / gRPC Microservice.

    Accepts JSON payloads containing an array of item strings or structured line
    items; computes dot products against in-memory matrix with near real-time latency.
    """

    def __init__(self, matcher: DynamicHSNSemanticMatcher):
        self.matcher = matcher

    def process_payload(
        self,
        payload: Union[List[str], Dict[str, Any]],
        chunk_size: int = 256,
    ) -> Dict[str, Any]:
        """Accepts either:

        - List of description strings: ["SS hex nipple", "ball valve 1 inch"]
        - Dict with 'items': {"items": ["...", "..."]}
        - Dict with line item objects: {"items": [{"id": 1, "description": "..."}, ...]}
        """
        raw_items: List[str] = []
        item_keys: List[Any] = []

        if isinstance(payload, list):
            for idx, x in enumerate(payload):
                if isinstance(x, dict):
                    desc = x.get("description") or x.get("product_name") or x.get("item_desc") or ""
                    raw_items.append(str(desc))
                    item_keys.append(x.get("id", idx))
                else:
                    raw_items.append(str(x))
                    item_keys.append(idx)
        elif isinstance(payload, dict):
            items_field = payload.get("items", payload.get("descriptions", payload.get("line_items", [])))
            return self.process_payload(items_field, chunk_size=chunk_size)

        batch_result = self.matcher.match_batch(raw_items, chunk_size=chunk_size)
        resp = batch_result.to_dict()

        # Attach original item keys if supplied
        for idx, item_res in enumerate(resp["items"]):
            if idx < len(item_keys):
                item_res["item_id"] = item_keys[idx]

        return resp


class DatabaseQueueConsumer:
    """Ingestion Adaptor 3: Database / Message Queue Asynchronous Consumer.

    Polls unprocessed invoice line items; writes back mapped HSN codes and
    confidence scores in bulk.
    """

    def __init__(self, matcher: DynamicHSNSemanticMatcher):
        self.matcher = matcher

    def process_unprocessed_batch(
        self,
        fetch_items_fn: Callable[[int], List[Dict[str, Any]]],
        write_results_fn: Callable[[List[Dict[str, Any]]], Any],
        batch_size: int = 256,
        description_key: str = "product_description",
    ) -> int:
        """Polls a batch of unprocessed items, vectorizes them, and writes back."""
        items = fetch_items_fn(batch_size)
        if not items:
            return 0

        descs = [str(it.get(description_key, it.get("description", ""))) for it in items]
        batch_results = self.matcher.match_batch(descs, chunk_size=batch_size)

        updates = []
        for orig, res in zip(items, batch_results):
            update_payload = dict(orig)
            update_payload["matched_hsn"] = res["matched_hsn"]
            update_payload["confidence_pct"] = res["confidence_pct"]
            update_payload["match_decision"] = res["decision"]
            update_payload["standard_rate"] = res["standard_rate"]
            updates.append(update_payload)

        write_results_fn(updates)
        return len(updates)


# ============================================================================
# UNIFIED HSN INTELLIGENCE ENGINE (BACKWARDS COMPATIBILITY + DYNAMIC EXTENSIONS)
# ============================================================================

class HSNIntelligenceEngine(HSNSemanticSearchEngine):
    """Module 1: Pure HSN Intelligence Engine (Statutory Vector Intelligence).

    Seamlessly integrates:
    1. Single-query hybrid semantic-lexical retrieval (Day 05 SearchResultList)
    2. Dynamic Multi-Input HSN Semantic Matcher (offline matrix dot product S = Q · D^T)
    3. Plug-and-play Ingestion Adaptors (Spreadsheet, REST, Queue).
    """

    def __init__(
        self,
        tariff_path: Optional[Union[str, Path]] = None,
        index_path: Optional[Union[str, Path]] = None,
        model_path: Optional[Union[str, Path]] = None,
        **kwargs,
    ):
        # Initialize base HSNSemanticSearchEngine for lexical-hybrid queries
        super().__init__(
            tariff_parquet_path=tariff_path,
            index_path=index_path,
            model_path=model_path,
            **kwargs,
        )

        # Initialize the Dynamic Multi-Input Geometric Matcher
        self._matcher = DynamicHSNSemanticMatcher(
            tariff_parquet_path=self.tariff_path,
            index_384_path=INDEX_384_NPY,
            index_128_path=self.index_path,
            model_name_or_path=model_path,
            auto_load=True,
        )

        # Ingestion Adaptors
        self.spreadsheet_adaptor = SpreadsheetIngestionAdaptor(self._matcher)
        self.rest_adaptor = RESTMicroserviceAdaptor(self._matcher)
        self.queue_consumer = DatabaseQueueConsumer(self._matcher)
        self._classify_cache: Dict[Tuple[str, int, Optional[str]], SearchResultList] = {}

    @property
    def matcher(self) -> DynamicHSNSemanticMatcher:
        """Direct access to the core dynamic multi-input geometric matcher."""
        return self._matcher

    def search(
        self,
        query: str,
        top_k: int = 5,
        hsn_prefix: Optional[str] = None,
    ) -> SearchResultList:
        """Dynamic hybrid retrieval using Two-Tier cascade BGE + Cross-Encoder Reranker + Trade Dependency Parser."""
        # Step 0: Sub-0.5ms Verified Qwen Memory Store Fast-Path Lookup
        try:
            from src.ml.hsn_verified_store import get_hsn_verified_store
            store = get_hsn_verified_store()
            cached = store.lookup(query)
            if cached and (not hsn_prefix or cached.get("hsn_code", "").startswith(hsn_prefix)):
                c_code = cached["hsn_code"]
                gst_val = float(cached.get("gst_rate", 18.0))
                rec = {
                    "hsn": c_code,
                    "hsn_code": c_code,
                    "hsn_4digit": c_code[:4],
                    "heading": c_code[:4],
                    "chapter": c_code[:2],
                    "description": cached.get("description", ""),
                    "clean_description": query.lower().strip(),
                    "standard_rate": gst_val,
                    "gst_rate": gst_val,
                    "is_blocked_17_5": 0,
                    "blocked_17_5_reason": "Eligible: General ITC",
                    "score": 1.0,
                    "confidence_pct": 100.0,
                    "match_type": "Verified Qwen Memory Store (<0.5ms)",
                    "reasoning": cached.get("reasoning", "")
                }
                return [rec]
        except Exception:
            pass

        t0 = time.time()
        if self._matcher is not None:
            try:
                batch_res = self._matcher.match_batch([query], top_k=top_k)
                if batch_res and len(batch_res) > 0:
                    top_item = batch_res[0]
                    matches = []
                    m_raw = top_item.get("matched_hsn")
                    m_hsn = str(m_raw or "").strip()
                    if m_hsn in ("None", "none", "nan", "") or not m_hsn.isdigit():
                        m_h4 = str(top_item.get("matched_hsn_4digit") or "").strip()
                        if m_h4 and m_h4 not in ("None", "none", "nan") and m_h4.isdigit():
                            m_hsn = m_h4
                        else:
                            import re
                            m_re = re.search(r'\b(\d{4,8})\b', str(top_item.get("official_description", "")))
                            if m_re:
                                m_hsn = m_re.group(1)
                            else:
                                m_hsn = ""

                    if m_hsn and m_hsn not in ("None", "none", "nan"):
                        h4_clean = str(top_item.get("matched_hsn_4digit") or m_hsn[:4]).strip()
                        if h4_clean in ("None", "none", "nan") or not h4_clean.isdigit():
                            h4_clean = m_hsn[:4]
                        chap_clean = str(top_item.get("chapter") or m_hsn[:2]).strip()
                        if chap_clean in ("None", "none", "nan") or not chap_clean.isdigit():
                            chap_clean = m_hsn[:2]

                        matches.append({
                            "hsn": m_hsn,
                            "hsn_code": m_hsn,
                            "hsn_4digit": h4_clean,
                            "heading": h4_clean,
                            "chapter": chap_clean,
                            "description": str(top_item.get("official_description", "")),
                            "clean_description": str(top_item.get("cleaned_description", "")),
                            "standard_rate": float(top_item.get("standard_rate", 18.0)),
                            "gst_rate": float(top_item.get("standard_rate", 18.0)),
                            "is_blocked_17_5": int(top_item.get("is_blocked_17_5", 0)),
                            "blocked_17_5_reason": str(top_item.get("blocked_17_5_reason", "Eligible: General ITC")),
                            "score": round(float(top_item.get("confidence_score", 0.9)), 4),
                            "confidence_pct": float(top_item.get("confidence_pct", 90.0)),
                            "match_type": str(top_item.get("match_type", "Two-Tier Hierarchical BGE + Cross-Encoder")),
                        })
                    for r in top_item.get("runners_up", []):
                        r_hsn = str(r.get("hsn_code", "") or "").strip()
                        if r_hsn and r_hsn not in ("None", "none", "nan") and r_hsn.isdigit() and r_hsn != m_hsn:
                            matches.append({
                                "hsn": r_hsn,
                                "hsn_code": r_hsn,
                                "hsn_4digit": str(r.get("heading", r_hsn[:4])),
                                "heading": str(r.get("heading", r_hsn[:4])),
                                "chapter": str(r.get("chapter", r_hsn[:2])),
                                "description": str(r.get("description", "")),
                                "clean_description": str(r.get("clean_description", "")),
                                "standard_rate": float(r.get("standard_rate", 18.0)),
                                "gst_rate": float(r.get("standard_rate", 18.0)),
                                "is_blocked_17_5": int(r.get("is_blocked_17_5", 0)),
                                "blocked_17_5_reason": str(r.get("blocked_17_5_reason", "Eligible: General ITC")),
                                "score": round(float(r.get("score", 0.7)), 4),
                                "confidence_pct": round(float(r.get("score", 0.7)) * 100.0, 1),
                                "match_type": "Two-Tier Hierarchical Runner-Up",
                            })
                    if matches:
                        if hsn_prefix:
                            p_clean = str(hsn_prefix).strip()
                            filtered = [m for m in matches if m["hsn_code"].startswith(p_clean)]
                            if filtered:
                                matches = filtered
                        latency = (time.time() - t0) * 1000.0
                        return SearchResultList(matches[:top_k], query=query, latency_ms=latency, model="Two-Tier Hierarchical BGE + Cross-Encoder")
            except Exception:
                pass

        return super().search(query=query, top_k=top_k, hsn_prefix=hsn_prefix)

    def classify_description(
        self,
        trade_description: str,
        top_k: int = 5,
        hsn_prefix: Optional[str] = None,
    ) -> SearchResultList:
        """Pure semantic retrieval classifying an item description into candidate statutory HSN items.

        Returns candidate HSNs, official descriptions, standard GST rates, and similarity confidence.
        (100% backwards compatible with Day 05 callers).
        """
        cache_key = (str(trade_description).strip(), int(top_k), str(hsn_prefix).strip() if hsn_prefix else None)
        if hasattr(self, "_classify_cache") and cache_key in self._classify_cache:
            return self._classify_cache[cache_key]

        res = self.search(query=trade_description, top_k=top_k, hsn_prefix=hsn_prefix)
        if not hasattr(self, "_classify_cache"):
            self._classify_cache = {}
        if len(self._classify_cache) < 2048:
            self._classify_cache[cache_key] = res
        return res

    def match_batch(
        self,
        items: Union[List[str], np.ndarray, pd.Series],
        top_k: int = 4,
        chunk_size: int = 256,
    ) -> HSNBatchResultList:
        """Dynamic Multi-Input Vector Dot-Product matching for batch/streaming invoice items."""
        return self._matcher.match_batch(items=items, top_k=top_k, chunk_size=chunk_size)

    def classify_batch(
        self,
        descriptions: List[str],
        chunk_size: int = 256,
    ) -> HSNBatchResultList:
        """Batch alias for matching multiple invoice items."""
        return self.match_batch(items=descriptions, chunk_size=chunk_size)

    def ingest_spreadsheet(
        self,
        file_or_df: Union[str, Path, pd.DataFrame],
        description_col: Optional[str] = None,
        chunk_size: int = 256,
    ) -> pd.DataFrame:
        """Dynamic Ingestion Adaptor for CSV/Excel spreadsheets."""
        if isinstance(file_or_df, pd.DataFrame):
            return self.spreadsheet_adaptor.process_dataframe(
                file_or_df, description_col=description_col, chunk_size=chunk_size
            )
        return self.spreadsheet_adaptor.process_file(
            file_or_df, description_col=description_col, chunk_size=chunk_size
        )

    def ingest_rest_payload(
        self,
        payload: Union[List[str], Dict[str, Any]],
        chunk_size: int = 256,
    ) -> Dict[str, Any]:
        """Dynamic Ingestion Adaptor for REST/JSON API payloads."""
        return self.rest_adaptor.process_payload(payload=payload, chunk_size=chunk_size)


# Convenience alias
HSNIntelligence = HSNIntelligenceEngine

_GLOBAL_INTELLIGENCE_ENGINE: Optional[HSNIntelligenceEngine] = None


def get_hsn_intelligence_engine() -> HSNIntelligenceEngine:
    """Returns singleton cached instance of HSNIntelligenceEngine."""
    global _GLOBAL_INTELLIGENCE_ENGINE
    if _GLOBAL_INTELLIGENCE_ENGINE is None:
        _GLOBAL_INTELLIGENCE_ENGINE = HSNIntelligenceEngine()
    return _GLOBAL_INTELLIGENCE_ENGINE
