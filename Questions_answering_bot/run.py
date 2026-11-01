"""
run.py — Root entrypoint for GST Sentinel QA Bot (Flan-T5 RAG Pipeline).

Usage (from Questions_answering_bot/ directory):
    python run.py                   # Start interactive QA bot
    python run.py --query "..."     # Run one-off question
    python run.py --download        # Download Flan-T5 model
    python run.py --test            # Run verification test suite
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

# Ensure src/ is on the path when running from project root
SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s"
)
logger = logging.getLogger("gst_sentinel.run")


def main():
    parser = argparse.ArgumentParser(
        description="GST Sentinel — Flan-T5 Chunk-Retrieval QA Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py                             Start the interactive QA bot
  python run.py --query "What is IMS?"      Run one-off query
  python run.py --test                      Run test_qa.py verification suite
  python run.py --download                  Download Flan-T5 model
        """
    )
    parser.add_argument("--query", "-q", type=str, default=None,
                        help="Run single query and print result")
    parser.add_argument("--domain", "-d", type=str, default="e_invoice",
                        help="Statutory domain: e_invoice, eway_bill, or ims")
    parser.add_argument("--test", action="store_true",
                        help="Run test_qa.py verification tests")
    parser.add_argument("--download", action="store_true",
                        help="Download the Flan-T5 model")
    parser.add_argument("--model", type=str, default=None,
                        help="Specify model name or directory (e.g. google/flan-t5-base)")
    args = parser.parse_args()

    if args.download:
        from download_model import download
        download()
        return

    if args.test:
        from test_qa import run_verification_tests
        run_verification_tests()
        return

    if args.query:
        from qa_engine import QAEngine
        engine = QAEngine(model_name_or_path=args.model)
        result = engine.answer_question(args.query, domain=args.domain)
        print(f"\nQuestion: {result['question']}")
        print(f"Answer:   {result['answer']}")
        print(f"Score:    {result['score']}")
        print(f"Latency:  {result['latency_seconds']}s")
        return

    # Default: interactive bot
    from qa_bot import QABot
    try:
        bot = QABot(model_name_or_path=args.model)
        bot.start()
    except FileNotFoundError as exc:
        logger.critical(str(exc))
        sys.exit(1)
    except Exception as exc:
        logger.critical(f"Fatal error: {exc}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
