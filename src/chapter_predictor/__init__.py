"""
src/chapter_predictor/__init__.py
==================================
Shared text normalization and ambiguity-resolution helpers used by Stage 1.
"""

from src.chapter_predictor.normalize import normalize_product_name, extract_query_facts

__all__ = [
    "normalize_product_name",
    "extract_query_facts",
]

