"""
GST Sentinel QA Bot — src package.

Public API:
    QABot    - main question-answering bot class
    search   - BM25 retrieval over the FTS5 index
    LongReader, AnswerSpan - Longformer reader components
"""

from .qa_bot import QABot
from .retriever import search, SearchResult
from .reader import LongReader, AnswerSpan

__all__ = ["QABot", "search", "SearchResult", "LongReader", "AnswerSpan"]
