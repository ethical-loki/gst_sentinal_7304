"""
Feature Hashing Tokenizer: src/models/tokenizer.py
Zero-dictionary sub-word and word feature hashing into a fixed 32,768-dimensional space.
Extracts word unigrams, word bigrams, character 3-grams, and character 4-grams
using deterministic MD5 hashing modulo 32,768.
Produces L2-normalized sparse and dense token frequency distributions.
"""

import hashlib
import math
import re
from collections import Counter
from typing import Dict, List, Optional, Tuple, Union
import numpy as np
import torch


class FeatureHashingTokenizer:
    """Zero-dictionary sub-word and word feature hashing tokenizer.

    Maps arbitrary noisy trade text into a fixed 32,768-D representation
    via deterministic MD5 hashing of word unigrams, word bigrams, character 3-grams,
    and character 4-grams.
    """

    DEFAULT_DIM: int = 32768

    def __init__(self, dim: int = DEFAULT_DIM):
        self.dim = dim

    @staticmethod
    def clean_text(text: object) -> str:
        """Strips control chars, punctuation, normalizes whitespace and lowercases."""
        if text is None or (isinstance(text, float) and math.isnan(text)):
            return ""
        if not isinstance(text, str):
            text = str(text)
        # Lowercase and replace non-alphanumeric with whitespace
        cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())
        return re.sub(r"\s+", " ", cleaned).strip()

    def extract_features(self, text: object) -> List[str]:
        """Extracts word unigrams, word bigrams, character 3-grams, and character 4-grams."""
        clean = self.clean_text(text)
        if not clean:
            return []

        words = clean.split()
        features: List[str] = []

        # 1. Word unigrams
        for w in words:
            features.append(f"w1:{w}")

            # 2. Character 3-grams & 4-grams with boundary markers
            padded_word = f"^{w}$"
            n_pad = len(padded_word)
            for i in range(n_pad - 2):
                features.append(f"c3:{padded_word[i:i+3]}")
            for i in range(n_pad - 3):
                features.append(f"c4:{padded_word[i:i+4]}")

        # 3. Word bigrams
        for i in range(len(words) - 1):
            features.append(f"w2:{words[i]}_{words[i+1]}")

        return features

    def hash_feature(self, feature: str) -> int:
        """Deterministic hashing of an individual feature string modulo self.dim."""
        digest = hashlib.md5(feature.encode("utf-8")).digest()
        # Extract 32-bit unsigned integer from first 4 bytes
        idx = int.from_bytes(digest[:4], byteorder="little")
        return idx % self.dim

    def get_feature_counts(self, text: object) -> Counter:
        """Computes bucket index counts for input text."""
        feats = self.extract_features(text)
        counts = Counter()
        for f in feats:
            idx = self.hash_feature(f)
            counts[idx] += 1.0
        return counts

    def tokenize_sparse(self, text: object) -> torch.Tensor:
        """Encodes text as an L2-normalized PyTorch sparse COO tensor of shape (dim,)."""
        counts = self.get_feature_counts(text)
        if not counts:
            # Return empty sparse tensor
            indices = torch.empty((1, 0), dtype=torch.long)
            values = torch.empty(0, dtype=torch.float32)
            return torch.sparse_coo_tensor(indices, values, (self.dim,))

        indices_list = list(counts.keys())
        values_list = [float(counts[i]) for i in indices_list]

        indices = torch.tensor([indices_list], dtype=torch.long)
        values = torch.tensor(values_list, dtype=torch.float32)

        # L2 normalize
        norm = torch.norm(values, p=2)
        if norm > 0:
            values = values / norm

        return torch.sparse_coo_tensor(indices, values, (self.dim,), check_invariants=False).coalesce()

    def tokenize(self, text: object) -> torch.Tensor:
        """Encodes text as an L2-normalized dense PyTorch FloatTensor of shape (dim,)."""
        counts = self.get_feature_counts(text)
        vec = torch.zeros(self.dim, dtype=torch.float32)
        if not counts:
            return vec

        for idx, count in counts.items():
            vec[idx] = float(count)

        norm = torch.norm(vec, p=2)
        if norm > 0:
            vec = vec / norm
        return vec

    def batch_tokenize(self, texts: List[object]) -> torch.Tensor:
        """Efficiently tokenizes a batch of texts into a dense FloatTensor of shape (B, dim)."""
        b_size = len(texts)
        batch_tensor = torch.zeros((b_size, self.dim), dtype=torch.float32)

        for i, text in enumerate(texts):
            counts = self.get_feature_counts(text)
            if not counts:
                continue
            for idx, count in counts.items():
                batch_tensor[i, idx] = float(count)

        # Vectorized L2 normalization across rows
        norms = torch.norm(batch_tensor, p=2, dim=1, keepdim=True)
        norms = torch.clamp(norms, min=1e-12)
        batch_tensor = batch_tensor / norms
        return batch_tensor
