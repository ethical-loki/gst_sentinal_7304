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
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
import torch

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
TARIFF_PARQUET = ROOT_DIR / "data" / "tariff_master.parquet"
TARIFF_INDEX_NPY = ROOT_DIR / "data" / "tariff_vector_index.npy"
MODEL_PATH = ROOT_DIR / "models" / "hsn_contrastive_mlp.pt"

from src.models.tokenizer import FeatureHashingTokenizer
from src.models.hsn_encoder import HSNContrastiveMLP


class HSNSearchEngine:
    """Sub-15ms Top-k Cosine Similarity Search Engine for Statutory HSN Retrieval."""

    def __init__(
        self,
        tariff_path: Optional[Path] = None,
        index_path: Optional[Path] = None,
        model_path: Optional[Path] = None,
    ):
        self.tariff_path = tariff_path or TARIFF_PARQUET
        self.index_path = index_path or TARIFF_INDEX_NPY
        self.model_path = model_path or MODEL_PATH

        self.tokenizer = FeatureHashingTokenizer(dim=32768)
        self.model: Optional[HSNContrastiveMLP] = None
        self.vector_index: Optional[np.ndarray] = None
        self.tariff_df: Optional[pd.DataFrame] = None

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

        # 2. Load Vector Index (N x 128 float32)
        self.vector_index = np.load(self.index_path).astype(np.float32)

        # 3. Load Model
        self.model = HSNContrastiveMLP(input_dim=32768, hidden_dim=512, output_dim=128)
        state_dict = torch.load(self.model_path, map_location="cpu")
        self.model.load_state_dict(state_dict)
        self.model.eval()

        # Warm-up forward pass to prime CPU caches
        with torch.no_grad():
            dummy = torch.zeros(32768, dtype=torch.float32)
            _ = self.model(dummy)

    def search(self, query: str, top_k: int = 5) -> Dict[str, Any]:
        """Performs end-to-end tokenization, forward pass, and top-k dot product search.

        Args:
            query: Raw invoice line-item text or HSN code.
            top_k: Number of statutory candidate matches to return.

        Returns:
            Dictionary containing matches list, query string, and execution latency in ms.
        """
        t0 = time.perf_counter()

        if not query or not query.strip():
            return {
                "query": query,
                "matches": [],
                "latency_ms": 0.0,
                "model": "Contrastive MLP (128-D CPU)",
            }

        clean_q = query.strip()
        matches: List[Dict[str, Any]] = []

        # Check if query is purely numeric digits (direct HSN lookup)
        is_numeric = clean_q.isdigit()

        if is_numeric:
            # Direct code filter
            matched_rows = self.tariff_df[
                self.tariff_df["hsn_code"].str.startswith(clean_q)
                | self.tariff_df["hsn_4digit"].str.startswith(clean_q)
            ].head(top_k)

            for _, row in matched_rows.iterrows():
                matches.append({
                    "hsn_code": str(row["hsn_code"]),
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
            # Both z_q and self.vector_index are unit normalized, dot product = cosine similarity
            sim_scores = np.dot(self.vector_index, z_q)

            # 4. Top-k argpartition / argsort
            top_indices = np.argsort(sim_scores)[::-1]

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
                # Convert cosine score [-1, 1] to human-friendly percentage [0, 100]
                conf_pct = round(max(0.0, min(100.0, (score + 1.0) / 2.0 * 100.0)), 1)

                matches.append({
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

        return {
            "query": query,
            "matches": matches[:top_k],
            "latency_ms": round(latency_ms, 2),
            "model": "Contrastive MLP (128-D CPU)",
        }
