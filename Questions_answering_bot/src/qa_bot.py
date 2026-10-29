import sys
import logging
import re
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
        logger.info("Initializing dynamic reader pipeline...")
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

    @staticmethod
    def sanitize_context(text: str) -> str:
        """Removes long base64 blocks and serialized JWT tokens to focus on text."""
        clean = re.sub(r"[A-Za-z0-9+/=_-]{45,}", " ", text)
        return re.sub(r"\s+", " ", clean).strip()

    def answer_question(self, question: str) -> Dict[str, Any]:
        """
        Processes a question end-to-end:
        1. Validates input
        2. Retrieves top-k matching passages
        3. Cleans noise & runs DynamicReader
        4. Selects best score and applies threshold
        """
        cleaned_q = question.strip()
        if not cleaned_q:
            return {
                "answer": "not found",
                "score": 0.0,
                "chunk_id": None,
                "reason": "Empty input"
            }

        # Step 1: Retrieve top passages
        chunks = search(cleaned_q, k=TOP_K)
        if not chunks:
            return {
                "answer": "not found",
                "score": 0.0,
                "chunk_id": None,
                "reason": "No matching passages found in index"
            }

        best_span: Optional[AnswerSpan] = None
        best_chunk_id: Optional[int] = None
        highest_score: float = -1.0

        # Step 2: Read each candidate chunk
        for chunk in chunks:
            clean_chunk = self.sanitize_context(chunk.content)
            span = self.reader.predict(question=cleaned_q, context=clean_chunk)
            
            if span and span.answer.strip().lower() != "not found":
                if span.score > highest_score:
                    highest_score = span.score
                    best_span = span
                    best_chunk_id = chunk.chunk_id

        # Step 3: Threshold validation (Generative returns score=1.0, Extractive uses threshold)
        if best_span is None or (not self.reader.is_generative and best_span.score < self.score_threshold):
            return {
                "answer": "not found",
                "score": round(highest_score if highest_score > 0 else 0.0, 4),
                "chunk_id": best_chunk_id,
                "reason": f"Confidence score below threshold ({self.score_threshold})"
            }

        return {
            "answer": best_span.answer,
            "score": round(best_span.score, 4),
            "chunk_id": best_chunk_id,
            "reason": "Success"
        }

    def start(self):
        """Interactive live CLI loop."""
        print("\n" + "=" * 65)
        print(" GST Sentinel QA Bot (Live)")
        print(" Type your question below.")
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
                print(f"\nAnswer:   {res['answer']}")
                print(f"Score:    {res['score']}")
                if res["chunk_id"] is not None:
                    print(f"Chunk ID: {res['chunk_id']}")
                print(f"Status:   {res['reason']}")
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