"""
src/ml/qwen_hsn_verifier.py — Backwards Compatibility Bridge for DeepSeek-V4 HSN Verifier.

Redirects all callers to src.ml.deepseek_hsn_verifier.
"""

from src.ml.deepseek_hsn_verifier import (
    DeepSeekHSNVerifier,
    get_deepseek_hsn_verifier,
    QwenHSNVerifier,
    get_qwen_hsn_verifier,
    format_hsn,
    clean_hsn_digits
)

__all__ = [
    "DeepSeekHSNVerifier",
    "get_deepseek_hsn_verifier",
    "QwenHSNVerifier",
    "get_qwen_hsn_verifier",
    "format_hsn",
    "clean_hsn_digits"
]
