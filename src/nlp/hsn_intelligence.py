"""
HSN Intelligence Engine (Up to Day 05): src/nlp/hsn_intelligence.py
Independent, pure semantic-lexical tariff intelligence module.
Evaluates line-item trade descriptions against the statutory tariff master using
in-house 128-D contrastive embeddings and sub-word lexical matching.
COMPLETELY INDEPENDENT: Has ZERO dependency on historical pricing or vendor priors.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import numpy as np

from src.nlp.hsn_search import HSNSemanticSearchEngine, SearchResultList

ROOT_DIR = Path(__file__).resolve().parent.parent.parent


class HSNIntelligenceEngine(HSNSemanticSearchEngine):
    """
    Module 1: Pure HSN Intelligence Engine (Up to Day 05).
    Performs objective trade description classification against 13,000+ statutory HSN items.
    Operates strictly on semantic text without historical pricing or vendor bias.
    """

    def __init__(
        self,
        tariff_path: Optional[Union[str, Path]] = None,
        index_path: Optional[Union[str, Path]] = None,
        model_path: Optional[Union[str, Path]] = None,
        **kwargs,
    ):
        super().__init__(
            tariff_parquet_path=tariff_path,
            index_path=index_path,
            model_path=model_path,
            **kwargs,
        )

    def classify_description(
        self,
        trade_description: str,
        top_k: int = 5,
        hsn_prefix: Optional[str] = None,
    ) -> SearchResultList:
        """
        Pure semantic retrieval classifying an item description into candidate statutory HSN items.
        Returns candidate HSNs, official descriptions, standard GST rates, and similarity confidence.
        """
        return self.search(query=trade_description, top_k=top_k, hsn_prefix=hsn_prefix)


# Convenience alias
HSNIntelligence = HSNIntelligenceEngine
