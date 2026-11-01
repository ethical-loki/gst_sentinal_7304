"""
model.py — Root import shim for FlanT5Generator and models.
"""
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from model import FlanT5Generator, PROMPT_TEMPLATE

__all__ = ["FlanT5Generator", "PROMPT_TEMPLATE"]

