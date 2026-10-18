"""
Top-k Cosine Search Engine: src/nlp/hsn_search.py
Accepts raw line-item trade descriptions, tokenizes and projects into 128-D vector space,
and performs matrix-vector dot products against precomputed statutory tariff vector index.
Returns top-k candidate HSN codes, official descriptions, tax rates, and cosine similarity scores
with sub-15ms CPU inference latency.
"""

import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import numpy as np
import pandas as pd
import torch

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
TARIFF_PARQUET = ROOT_DIR / "data" / "tariff_master.parquet"
TARIFF_INDEX_NPY = ROOT_DIR / "data" / "tariff_vector_index.npy"
MODEL_PATH = ROOT_DIR / "models" / "hsn_contrastive_mlp.pt"

from src.models.tokenizer import FeatureHashingTokenizer
from src.models.hsn_encoder import HSNContrastiveMLP

# Commercial trade terminology priors mapped to statutory 4-digit HSN headings
TRADE_KEYWORDS: Dict[str, List[str]] = {
    "7307": ["nipple", "coupling", "elbow", "tee", "reducing bush", "bush", "flange", "fitting", "union", "socket weld"],
    "7306": ["welded pipe", "welded tube", "erw pipe"],
    "7304": ["seamless", "hydraulic tube", "seamless pipe"],
    "8481": ["valve", "ball valve", "check valve", "needle valve", "non return", "cock", "tap"],
    "7318": ["screw", "bolt", "nut", "washer", "allen cap", "rivet", "stud", "fastener", "lock washer"],
    "3917": ["upvc", "hdpe", "pvc pipe", "plastic pipe", "solvent weld", "coil pipe", "hose"],
    "8544": ["cable", "wire", "wiring", "conductor", "armoured cable", "power cable"],
    "8504": ["inverter", "transformer", "smps", "power supply", "converter", "rectifier"],
}


class SearchResultList(list):
    """Hybrid result container supporting both list iteration and dictionary access."""

    def __init__(
        self,
        matches: List[Dict[str, Any]],
        query: str = "",
        latency_ms: float = 0.0,
        model: str = "Contrastive MLP (128-D CPU)",
    ):
        super().__init__(matches)
        self.matches = matches
        self.query = query
        self.latency_ms = latency_ms
        self.model = model

    def __getitem__(self, item):
        if isinstance(item, str):
            if item == "matches":
                return self.matches
            elif item == "query":
                return self.query
            elif item == "latency_ms":
                return self.latency_ms
            elif item == "model":
                return self.model
            raise KeyError(f"Key '{item}' not found in SearchResultList")
        return super().__getitem__(item)

    def get(self, item: str, default: Any = None) -> Any:
        if item == "matches":
            return self.matches
        elif item == "query":
            return self.query
        elif item == "latency_ms":
            return self.latency_ms
        elif item == "model":
            return self.model
        return default


class HSNSemanticSearchEngine:
    """Sub-15ms Top-k Cosine Similarity Search Engine for Statutory HSN Retrieval."""

    def __init__(
        self,
        tariff_parquet_path: Optional[Union[str, Path]] = None,
        tariff_path: Optional[Union[str, Path]] = None,
        index_path: Optional[Union[str, Path]] = None,
        model_path: Optional[Union[str, Path]] = None,
        **kwargs,
    ):
        t_path = tariff_parquet_path or tariff_path or TARIFF_PARQUET
        self.tariff_path = Path(t_path)
        self.index_path = Path(index_path or TARIFF_INDEX_NPY)
        self.model_path = Path(model_path or MODEL_PATH)

        self.tokenizer = FeatureHashingTokenizer(dim=32768)
        self.model: Optional[HSNContrastiveMLP] = None
        self.vector_index: Optional[np.ndarray] = None
        self.tariff_df: Optional[pd.DataFrame] = None
        self.prefix_masks: Dict[str, np.ndarray] = {}

        self._load_resources()

    def _load_resources(self) -> None:
        """Loads tariff parquet metadata, numpy vector index, and PyTorch model weights."""
        if not self.tariff_path.exists():
            raise FileNotFoundError(f"Tariff master missing: {self.tariff_path}. Run scripts/ingest_tariff.py first.")
        if not self.index_path.exists():
            raise FileNotFoundError(f"Vector index missing: {self.index_path}. Run scripts/build_tariff_index.py first.")
        if not self.model_path.exists():
            raise FileNotFoundError(f"Model missing: {self.model_path}. Run scripts/train_hsn_encoder.py first.")

        # 1. Load Parquet
        self.tariff_df = pd.read_parquet(self.tariff_path).reset_index(drop=True)

        # 2. Precompute boolean masks for trade heading keywords
        self.prefix_masks = {
            prefix: (self.tariff_df["hsn_4digit"] == prefix).to_numpy()
            for prefix in TRADE_KEYWORDS
        }

        # 3. Load Vector Index (N x 128 float32)
        self.vector_index = np.load(self.index_path).astype(np.float32)

        # 4. Load Model
        self.model = HSNContrastiveMLP(input_dim=32768, hidden_dim=512, output_dim=128)
        state_dict = torch.load(self.model_path, map_location="cpu")
        self.model.load_state_dict(state_dict)
        self.model.eval()

        # Warm-up forward pass to prime CPU caches
        with torch.no_grad():
            dummy = torch.zeros(32768, dtype=torch.float32)
            _ = self.model(dummy)

    def search(self, query: str, top_k: int = 5) -> SearchResultList:
        """Performs end-to-end tokenization, forward pass, and top-k dot product search.

        Args:
            query: Raw invoice line-item text or HSN code.
            top_k: Number of statutory candidate matches to return.

        Returns:
            SearchResultList containing matches list, query string, and execution latency in ms.
        """
        t0 = time.perf_counter()

        if not query or not str(query).strip():
            return SearchResultList(
                matches=[],
                query=query,
                latency_ms=0.0,
                model="Contrastive MLP (128-D CPU)",
            )

        clean_q = str(query).strip()
        q_lower = clean_q.lower()
        matches: List[Dict[str, Any]] = []

        # Check if query is purely numeric digits (direct HSN lookup)
        is_numeric = clean_q.isdigit()

        if is_numeric:
            matched_rows = self.tariff_df[
                self.tariff_df["hsn_code"].str.startswith(clean_q)
                | self.tariff_df["hsn_4digit"].str.startswith(clean_q)
            ].head(top_k)

            for _, row in matched_rows.iterrows():
                code = str(row["hsn_code"])
                matches.append({
                    "hsn": code,
                    "hsn_code": code,
                    "hsn_4digit": str(row["hsn_4digit"]),
                    "chapter": str(row["chapter"]),
                    "description": str(row["description"]),
                    "clean_description": str(row["clean_description"]),
                    "standard_rate": float(row["standard_rate"]),
                    "is_blocked_17_5": int(row["is_blocked_17_5"]),
                    "blocked_17_5_reason": str(row["blocked_17_5_reason"]),
                    "score": 1.0,
                    "confidence_pct": 100.0,
                    "match_type": "Direct Code Match",
                })

        # If not enough matches from numeric filter, execute semantic search
        if len(matches) < top_k:
            # 1. Hashing Tokenization
            tok_vec = self.tokenizer.tokenize(clean_q)

            # 2. PyTorch Forward Pass (CPU)
            with torch.no_grad():
                z_q = self.model(tok_vec).cpu().numpy()  # (128,)

            # 3. Cosine Dot-Product against all statutory vectors
            sim_scores = np.dot(self.vector_index, z_q)

            # 4. Domain Keyword Prior Hybrid Boost
            boost = np.zeros_like(sim_scores)
            for prefix, kws in TRADE_KEYWORDS.items():
                mask = self.prefix_masks.get(prefix)
                if mask is not None:
                    for kw in kws:
                        if kw in q_lower:
                            boost[mask] += 1.0
                            break

            total_scores = sim_scores + boost

            # 5. Top-k argpartition for fast CPU retrieval
            k_fetch = min(len(total_scores), top_k + len(matches) + 5)
            part_indices = np.argpartition(-total_scores, k_fetch)[:k_fetch]
            top_indices = part_indices[np.argsort(-total_scores[part_indices])]

            seen_codes = {m["hsn_code"] for m in matches}
            for idx in top_indices:
                if len(matches) >= top_k:
                    break
                row = self.tariff_df.iloc[idx]
                code = str(row["hsn_code"])
                if code in seen_codes:
                    continue
                seen_codes.add(code)

                score = float(sim_scores[idx])
                conf_pct = round(max(0.0, min(100.0, (score + 1.0) / 2.0 * 100.0)), 1)

                matches.append({
                    "hsn": code,
                    "hsn_code": code,
                    "hsn_4digit": str(row["hsn_4digit"]),
                    "chapter": str(row["chapter"]),
                    "description": str(row["description"]),
                    "clean_description": str(row["clean_description"]),
                    "standard_rate": float(row["standard_rate"]),
                    "is_blocked_17_5": int(row["is_blocked_17_5"]),
                    "blocked_17_5_reason": str(row["blocked_17_5_reason"]),
                    "score": round(score, 4),
                    "confidence_pct": conf_pct,
                    "match_type": "Semantic Contrastive Match",
                })

        latency_ms = (time.perf_counter() - t0) * 1000.0

        return SearchResultList(
            matches=matches[:top_k],
            query=query,
            latency_ms=round(latency_ms, 2),
            model="Contrastive MLP (128-D CPU)",
        )


# Backward-compatible alias
HSNSearchEngine = HSNSemanticSearchEngine
