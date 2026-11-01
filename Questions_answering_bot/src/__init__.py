"""
GST Sentinel QA Bot — src package.

Public API:
    QAEngine, QABot - main question-answering engines
    MultiDomainRetriever, get_retriever, search, SearchResult - multi-domain retrieval
    FlanT5Generator, SmartGenerator, GeminiClient, LocalSmartSynthesizer - neural & smart generators
    LongReader, AnswerSpan - reader components
"""

from .qa_engine import QAEngine
from .qa_bot import QABot
from .retriever import MultiDomainRetriever, get_retriever, search, SearchResult
from .model import FlanT5Generator, SmartGenerator, GeminiClient, LocalSmartSynthesizer
from .reader import LongReader, AnswerSpan

__all__ = [
    "QAEngine",
    "QABot",
    "MultiDomainRetriever",
    "get_retriever",
    "search",
    "SearchResult",
    "FlanT5Generator",
    "SmartGenerator",
    "GeminiClient",
    "LocalSmartSynthesizer",
    "LongReader",
    "AnswerSpan",
]
