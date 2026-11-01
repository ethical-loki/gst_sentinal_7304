"""
qa_engine.py — Multi-Domain RAG Question Answering pipeline orchestrator.

Coordinates:
1. MultiDomainRetriever with isolated chunk indexes for 'e_invoice', 'eway_bill', and 'ims'.
2. Smart Generator (Google Gemini Free-Tier Cloud LLM + Local Grounded Synthesizer + Flan-T5).
3. Input validation, domain selection, and unanswerability handling.
"""

import logging
import time
from pathlib import Path
from typing import Dict, Any, Optional, List

from config import TOP_K, FALLBACK_RESPONSE, SCORE_THRESHOLD
from retriever import MultiDomainRetriever, get_retriever
from model import QwenGenerator, FlanT5Generator, SmartGenerator

logger = logging.getLogger("gst_sentinel.qa_engine")


class QAEngine:
    """
    Multi-Domain RAG Question Answering Engine.
    Restricts search and inference to the user's targeted statutory domain.
    """

    def __init__(
        self,
        retriever: Optional[MultiDomainRetriever] = None,
        generator: Optional[QwenGenerator] = None,
        top_k: int = TOP_K,
        model_name_or_path: Optional[str] = None,
        context_path: Optional[str] = None,
        **kwargs
    ):
        self.top_k = top_k

        # Initialize Multi-Domain Retriever
        if retriever is not None:
            self.retriever = retriever
        else:
            logger.info("Initializing MultiDomainRetriever...")
            self.retriever = get_retriever()

        # Initialize Generator
        if generator is not None:
            self.generator = generator
        else:
            logger.info("Initializing Qwen2.5-Instruct / Smart Generator...")
            self.generator = QwenGenerator(model_name_or_path=model_name_or_path)

        logger.info("Multi-Domain QAEngine successfully initialized.")

    def answer_question(
        self,
        question: str,
        domain: Optional[str] = "e_invoice",
        top_k: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Executes end-to-end domain-isolated QA flow:
        1. Normalizes domain key ('e_invoice', 'eway_bill', 'ims').
        2. Retrieves top-k chunks strictly from that domain's chunk store.
        3. Formats prompt and executes generative extraction.
        4. Returns structured response dictionary.
        """
        start_time = time.time()
        cleaned_q = question.strip() if question else ""
        norm_domain = self.retriever.normalize_domain(domain)

        if not cleaned_q:
            return {
                "question": question,
                "domain": norm_domain,
                "answer": FALLBACK_RESPONSE,
                "score": 0.0,
                "retrieved_chunks": [],
                "latency_seconds": round(time.time() - start_time, 3),
                "status": "empty_query"
            }

        k = top_k if top_k and top_k > 0 else self.top_k
        combined_context, chunks = self.retriever.get_combined_context(
            query=cleaned_q,
            domain=norm_domain,
            top_k=k
        )

        top_score = chunks[0]["score"] if chunks else 0.0

        # Reject if below confidence threshold or completely irrelevant
        if not chunks or top_score < SCORE_THRESHOLD:
            logger.info(f"Query '{cleaned_q}' yielded no relevant chunks in domain '{norm_domain}' (top_score={top_score}).")
            return {
                "question": cleaned_q,
                "domain": norm_domain,
                "answer": FALLBACK_RESPONSE,
                "score": round(top_score, 4),
                "retrieved_chunks": [],
                "latency_seconds": round(time.time() - start_time, 3),
                "status": "no_relevant_context"
            }

        # Generate response using Qwen / Smart Generator
        generated_answer = self.generator.generate(
            question=cleaned_q,
            context=combined_context,
            chunks=chunks
        )

        elapsed = round(time.time() - start_time, 3)

        return {
            "question": cleaned_q,
            "domain": norm_domain,
            "answer": generated_answer,
            "score": round(top_score, 4),
            "retrieved_chunks": [
                {
                    "chunk_id": c["chunk_id"],
                    "section": c.get("section", "General"),
                    "domain": c.get("domain", norm_domain),
                    "score": c.get("score", 0.0),
                    "text": c.get("text", ""),
                    "snippet": (c["text"][:160] + "...") if len(c.get("text", "")) > 160 else c.get("text", "")
                }
                for c in chunks
            ],
            "latency_seconds": elapsed,
            "status": "success" if generated_answer != FALLBACK_RESPONSE else "fallback"
        }
