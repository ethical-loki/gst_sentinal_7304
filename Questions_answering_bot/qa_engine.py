"""
qa_engine.py — Root import shim for QAEngine and MultiDomainRetriever.
"""
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from qa_engine import QAEngine
from model import FlanT5Generator
from retriever import MultiDomainRetriever, get_retriever

__all__ = ["QAEngine", "FlanT5Generator", "MultiDomainRetriever", "get_retriever"]
