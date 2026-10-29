import sys
import logging
from typing import Dict, Any, Optional

from config import INDEX_DB_PATH, MODEL_PATH, TOP_K, SCORE_THRESHOLD
from retriever import search, SearchResult
from reader import DynamicReader, AnswerSpan

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s"
)
logger = logging.getLogger("gst_sentinel.qa_bot")


class QABot:
    def __init__(self, score_threshold: float = SCORE_THRESHOLD):
        self.score_threshold = score_threshold
        self._validate_prerequisites()
        logger.info("Initializing dynamic neural reader pipeline...")
        self.reader = DynamicReader(model_dir=str(MODEL_PATH))
        logger.info("QA Bot successfully initialized.")

    def _validate_prerequisites(self):
        """Verifies that index database and model weights exist."""
        if not INDEX_DB_PATH.exists():
            raise FileNotFoundError(
                f"Missing index database at {INDEX_DB_PATH.resolve()}. Run 'src/build_index.py' first."
            )
        if not MODEL_PATH.exists():
            raise FileNotFoundError(
                f"Missing model cache folder at {MODEL_PATH.resolve()}. Run 'src/download_model.py' first."
            )

    def answer_question(self, question: str, top_k: Optional[int] = None) -> Dict[str, Any]:
        """
        Processes a question end-to-end:
        1. Validates input
        2. Retrieves top-k matching passages via tiered FTS5 BM25
        3. Neural reader extracts concise answer span with unanswerability rejection
        4. Selects highest-confidence answer above threshold
        """
        cleaned_q = question.strip()
        if not cleaned_q:
            return {
                "answer": "not found",
                "score": 0.0,
                "chunk_id": None,
                "section": None,
                "reason": "Empty input question"
            }

        k = top_k if top_k and top_k > 0 else TOP_K
        chunks = search(cleaned_q, k=k)
        if not chunks:
            return {
                "answer": "not found",
                "score": 0.0,
                "chunk_id": None,
                "section": None,
                "reason": "No relevant document passages matched your question"
            }

        best_span: Optional[AnswerSpan] = None
        best_chunk: Optional[SearchResult] = None
        highest_score: float = -1.0

        for chunk in chunks:
            span = self.reader.predict(question=cleaned_q, context=chunk.content)
            if span and span.answer != "not found" and span.score > highest_score:
                highest_score = span.score
                best_span = span
                best_chunk = chunk
                # Fast early exit on near-certain answer
                if highest_score >= 0.85:
                    break

        if best_span is None or best_span.score < self.score_threshold:
            ans_score = round(highest_score if highest_score > 0 else 0.0, 4)
            return {
                "answer": "not found",
                "score": ans_score,
                "chunk_id": best_chunk.chunk_id if best_chunk else None,
                "section": best_chunk.section if best_chunk else None,
                "reason": f"Information not found in documentation (confidence {ans_score} < threshold {self.score_threshold})"
            }

        return {
            "answer": best_span.answer,
            "score": round(best_span.score, 4),
            "chunk_id": best_chunk.chunk_id if best_chunk else None,
            "section": best_chunk.section if best_chunk else None,
            "start_char": best_span.start_char,
            "end_char": best_span.end_char,
            "reason": "Success"
        }

    def start(self):
        """Interactive live CLI loop."""
        print("\n" + "=" * 65)
        print(" GST Sentinel QA Bot (Live)")
        print(" Ask any question regarding E-Invoicing & IMS.")
        print(" Type 'exit' or 'quit' to terminate.")
        print("=" * 65 + "\n")

        while True:
            try:
                user_q = input("Ask a question: ").strip()
                if user_q.lower() in ("exit", "quit"):
                    print("Exiting bot. Goodbye!")
                    break

                if not user_q:
                    print("Please enter a valid question.\n")
                    continue

                res = self.answer_question(user_q)
                print(f"\nAnswer:     {res['answer']}")
                print(f"Confidence: {res['score']}")
                if res.get("section"):
                    print(f"Section:    {res['section']}")
                if res.get("chunk_id") is not None:
                    print(f"Chunk ID:   {res['chunk_id']}")
                print(f"Status:     {res['reason']}")
                print("-" * 55 + "\n")

            except (KeyboardInterrupt, EOFError):
                print("\nInterrupted. Exiting.")
                break


if __name__ == "__main__":
    try:
        bot = QABot()
        bot.start()
    except Exception as exc:
        logger.critical(f"Failed to start bot: {exc}")
        sys.exit(1)