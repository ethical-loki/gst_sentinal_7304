"""
scripts/build_chapter_index.py
==============================
One-time offline index builder for the HSN Chapter Predictor.
Builds and persists:
1. data/chapter_predictor/bm25_index.pkl (BM25 over 19,396 statutory rows)
2. data/chapter_predictor/tariff_embeddings.npy (Dense L2-normalized vector embeddings)
3. data/chapter_predictor/chapter_embeddings.npy (Dense embeddings for all 99 chapter titles)
4. data/chapter_predictor/tariff_metadata.json (Indexed records and chapter titles)
"""

import sys
import time
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.chapter_predictor.lexical import get_lexical_index
from src.chapter_predictor.embeddings import get_semantic_index
from src.chapter_predictor.predictor import ChapterPredictor


def main():
    print("=" * 80)
    print("BUILDING CHAPTER PREDICTOR INDEXES (Final_Copy_hsn_7304.xlsx)")
    print("=" * 80)

    # 1. Build BM25 Index
    t0 = time.perf_counter()
    print("\n[Step 1/2] Building BM25 Lexical Index...")
    lexical = get_lexical_index()
    lexical.build_index()
    bm25_sec = round(time.perf_counter() - t0, 2)
    print(f"[OK] BM25 Index built and saved in {bm25_sec}s ({len(lexical.records)} records)")

    # 2. Build Dense Embedding Vectors
    t0 = time.perf_counter()
    print("\n[Step 2/2] Building Semantic Dense Embeddings...")
    semantic = get_semantic_index()
    semantic.build_index()
    embed_sec = round(time.perf_counter() - t0, 2)
    print(f"[OK] Semantic Embeddings built and saved in {embed_sec}s")
    print(f"      Tariff matrix shape: {semantic.tariff_embeddings.shape}")
    print(f"      Chapter title matrix shape: {semantic.chapter_embeddings.shape}")

    # 3. Quick Verification Test
    print("\n[Verification] Running test predictions on canonical items...")
    predictor = ChapterPredictor.get_instance()
    test_items = [
        "Whole Roasted Coffee Beans",
        "Microprocessor",
        "Cotton shirt without sleeves",
        "Frozen prawns",
        "Stainless steel line pipe"
    ]
    for item in test_items:
        pred = predictor.predict(item)
        print(f"  {item:35s} -> Chapter {pred.chapter} ({pred.chapter_title[:40]}) | Conf: {pred.confidence:.2f} | Status: {pred.status}")

    print("\n[SUCCESS] Chapter Predictor index construction complete!")


if __name__ == "__main__":
    main()

