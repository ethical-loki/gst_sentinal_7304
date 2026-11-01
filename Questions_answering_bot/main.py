"""
main.py — Main CLI entrypoint and API server for GST Sentinel Question Answering Bot.

Usage:
    # 1. Interactive CLI mode
    python main.py

    # 2. Single query mode
    python main.py --query "What is the validity of the auth token?"

    # 3. Optional REST API server
    python main.py --serve --port 8000
"""

import sys
import argparse
import logging
from pathlib import Path

# Fix Windows console UTF-8 encoding (e.g. Rupee symbol ₹)
if sys.platform == "win32":
    import io
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Add src/ directory to Python path
SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from qa_engine import QAEngine
from config import CONTEXT_PATH, TOP_K, FALLBACK_RESPONSE

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s"
)
logger = logging.getLogger("gst_sentinel.main")


def start_interactive_cli(engine: QAEngine):
    """Interactive command-line loop."""
    print("\n" + "=" * 65)
    print(" GST Sentinel QA Bot (Google Flan-T5 + Chunk Retrieval)")
    print(" GST Regulatory Documentation: E-Invoice & IMS Data")
    print(" Type 'exit' or 'quit' to exit.")
    print("=" * 65 + "\n")

    while True:
        try:
            query = input("Ask a question: ").strip()
            if query.lower() in ("exit", "quit", "q"):
                print("Exiting bot. Goodbye!")
                break

            if not query:
                print("Error: Input cannot be empty. Please ask a question.\n")
                continue

            result = engine.answer_question(query)
            print(f"\nAnswer:     {result['answer']}")
            print(f"Relevance:  {result['score']}")
            if result.get("retrieved_chunks"):
                top_chunk = result["retrieved_chunks"][0]
                print(f"Section:    {top_chunk['section']} (Chunk #{top_chunk['chunk_id']})")
            print(f"Latency:    {result['latency_seconds']}s")
            print("-" * 55 + "\n")

        except (KeyboardInterrupt, EOFError):
            print("\nSession ended. Exiting.")
            break
        except Exception as e:
            logger.error(f"Inference error: {e}", exc_info=True)
            print(f"\nError processing query: {e}\n")


def create_api_app(engine: QAEngine):
    """Creates a FastAPI app instance for HTTP serving."""
    try:
        from fastapi import FastAPI, HTTPException
        from pydantic import BaseModel, Field
    except ImportError:
        logger.error("FastAPI or Pydantic is not installed. Please run: pip install fastapi uvicorn")
        sys.exit(1)

    app = FastAPI(
        title="GST Sentinel QA Bot API",
        description="Flan-T5 RAG QA service for GST e-Invoice and IMS documentation",
        version="2.0.0"
    )

    class QuestionRequest(BaseModel):
        question: str = Field(..., description="GST domain question", min_length=2)
        domain: str = Field(default="e_invoice", description="Target domain: e_invoice, eway_bill, or ims")
        top_k: int = Field(default=TOP_K, description="Number of context chunks to retrieve", ge=1, le=10)

    class QuestionResponse(BaseModel):
        question: str
        domain: str = "e_invoice"
        answer: str
        score: float
        retrieved_chunks: list
        latency_seconds: float
        status: str

    @app.post("/qa", response_model=QuestionResponse)
    @app.post("/ask", response_model=QuestionResponse)
    def ask_question(req: QuestionRequest):
        if not req.question.strip():
            raise HTTPException(status_code=400, detail="Question cannot be blank.")
        try:
            return engine.answer_question(req.question, domain=req.domain, top_k=req.top_k)
        except Exception as exc:
            logger.error(f"Error handling /qa request: {exc}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(exc))

    @app.get("/health")
    def health_check():
        return {"status": "ok", "model": engine.generator.model_name}

    return app


def main():
    parser = argparse.ArgumentParser(
        description="GST Sentinel — Flan-T5 Chunk-Retrieval QA Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--query", "-q", type=str, default=None,
                        help="Run QA on a single question and print output")
    parser.add_argument("--domain", "-d", type=str, default="e_invoice",
                        help="Statutory domain (e_invoice, eway_bill, ims)")
    parser.add_argument("--context", "-c", type=str, default=None,
                        help="Path to context documentation file (default: context.txt)")
    parser.add_argument("--top_k", "-k", type=int, default=TOP_K,
                        help="Number of retrieved chunks (default: 3)")
    parser.add_argument("--model", "-m", type=str, default=None,
                        help="Flan-T5 model identifier or directory")
    parser.add_argument("--serve", action="store_true",
                        help="Start FastAPI HTTP server on --host and --port")
    parser.add_argument("--host", type=str, default="0.0.0.0",
                        help="Host to bind HTTP server (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000,
                        help="Port to bind HTTP server (default: 8000)")

    args = parser.parse_args()

    # Initialize Engine once at startup
    context_path = Path(args.context) if args.context else CONTEXT_PATH
    try:
        engine = QAEngine(
            context_path=context_path,
            model_name_or_path=args.model,
            top_k=args.top_k
        )
    except Exception as exc:
        logger.critical(f"Failed to initialize QAEngine: {exc}", exc_info=True)
        sys.exit(1)

    # 1. Single query mode
    if args.query:
        result = engine.answer_question(args.query, domain=args.domain)
        print(f"\nQuestion: {result['question']}")
        print(f"Answer:   {result['answer']}")
        print(f"Score:    {result['score']}")
        print(f"Latency:  {result['latency_seconds']}s")
        return

    # 2. HTTP Server mode
    if args.serve:
        import uvicorn
        app = create_api_app(engine)
        logger.info(f"Starting server on http://{args.host}:{args.port}...")
        uvicorn.run(app, host=args.host, port=args.port)
        return

    # 3. Default: Interactive CLI loop
    start_interactive_cli(engine)


if __name__ == "__main__":
    main()

