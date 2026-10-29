"""
run.py — Root entrypoint for GST Sentinel QA Bot.

Usage (from Questions_answering_bot/ directory):
    python run.py              # Start interactive QA bot
    python run.py --evaluate   # Run evaluation on qa_test.json
    python run.py --build      # Re-build the FTS5 index
    python run.py --download   # Download the Longformer model
"""
import sys
import argparse
import logging
from pathlib import Path

# Ensure src/ is on the path when running from project root
SRC_DIR = Path(__file__).resolve().parent / "src"
sys.path.insert(0, str(SRC_DIR))

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s"
)


def main():
    parser = argparse.ArgumentParser(
        description="GST Sentinel — Offline Extractive QA Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py                  Start the interactive QA bot
  python run.py --evaluate       Run EM/F1 benchmark on data/qa_test.json
  python run.py --build          Rebuild the SQLite FTS5 index from data/content.txt
  python run.py --download       Download the Longformer model (requires internet)
        """
    )
    parser.add_argument("--evaluate", action="store_true",
                        help="Run evaluation on qa_test.json and write eval_report.md")
    parser.add_argument("--build", action="store_true",
                        help="Rebuild the FTS5 search index from data/content.txt")
    parser.add_argument("--download", action="store_true",
                        help="Download the Longformer model to models/longformer-squad2/")
    args = parser.parse_args()

    if args.download:
        from download_model import download_and_save
        download_and_save()
        return

    if args.build:
        from build_index import build_fts_index
        build_fts_index()
        return

    if args.evaluate:
        from evaluate import run_evaluation
        run_evaluation()
        return

    # Default: interactive bot
    from qa_bot import QABot
    try:
        bot = QABot()
        bot.start()
    except FileNotFoundError as exc:
        logging.critical(str(exc))
        sys.exit(1)
    except Exception as exc:
        logging.critical(f"Fatal error: {exc}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
