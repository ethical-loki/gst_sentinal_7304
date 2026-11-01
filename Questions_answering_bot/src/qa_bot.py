"""
qa_bot.py — Interactive CLI and programmatic QA bot interface for GST Sentinel.
"""

import sys
import logging
from typing import Dict, Any, Optional

from config import CONTEXT_PATH, TOP_K, FALLBACK_RESPONSE
from qa_engine import QAEngine

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s"
)
logger = logging.getLogger("gst_sentinel.qa_bot")


class QABot:
    """
    Customer-facing GST Sentinel QA Bot powered by Flan-T5 and Chunk Retrieval.
    """

    def __init__(
        self,
        context_path: Optional[str] = None,
        model_name_or_path: Optional[str] = None,
        top_k: int = TOP_K
    ):
        self.engine = QAEngine(
            context_path=context_path,
            model_name_or_path=model_name_or_path,
            top_k=top_k
        )
        logger.info("QA Bot successfully initialized with Flan-T5 & Chunk Retrieval.")

    def answer_question(self, question: str, domain: Optional[str] = "e_invoice", top_k: Optional[int] = None) -> Dict[str, Any]:
        """Processes question through the RAG pipeline."""
        return self.engine.answer_question(question, domain=domain, top_k=top_k)

    def start(self):
        """Interactive live CLI loop."""
        print("\n" + "=" * 65)
        print(" GST Sentinel QA Bot (LLM & Grounded Multi-Domain RAG)")
        print(" Domains supported: 'e_invoice', 'eway_bill', 'ims'")
        print(" Command: switch domain with '/domain <name>' (e.g. /domain ims)")
        print(" Type 'exit' or 'quit' to terminate.")
        print("=" * 65 + "\n")

        current_domain = "e_invoice"

        while True:
            try:
                user_q = input(f"[{current_domain}] Ask a question: ").strip()
                if user_q.lower() in ("exit", "quit"):
                    print("Exiting bot. Goodbye!")
                    break

                if user_q.startswith("/domain"):
                    parts = user_q.split()
                    if len(parts) > 1:
                        current_domain = self.engine.retriever.normalize_domain(parts[1])
                        print(f"Switched active domain to: '{current_domain}'\n")
                    else:
                        print(f"Current domain: '{current_domain}'. Available: e_invoice, eway_bill, ims\n")
                    continue

                if not user_q:
                    print("Please enter a valid question.\n")
                    continue

                res = self.answer_question(user_q, domain=current_domain)
                print(f"\nAnswer:     {res['answer']}")
                print(f"Confidence: {res['score']}")
                if res.get("retrieved_chunks"):
                    top_chunk = res["retrieved_chunks"][0]
                    print(f"Top Source: [{top_chunk.get('section', 'General')}] (Chunk #{top_chunk['chunk_id']})")
                print(f"Latency:    {res.get('latency_seconds', 0)}s")
                print(f"Status:     {res.get('status', 'success')}")
                print("-" * 55 + "\n")

            except (KeyboardInterrupt, EOFError):
                print("\nInterrupted. Exiting.")
                break


if __name__ == "__main__":
    try:
        bot = QABot()
        bot.start()
    except Exception as exc:
        logger.critical(f"Failed to start bot: {exc}", exc_info=True)
        sys.exit(1)
