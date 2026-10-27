"""
384-D Tariff Vector Index Serialization: scripts/build_tariff_index_384.py
Generates L2-normalized 384-dimensional dense semantic embeddings for all official statutory
descriptions from data/tariff_master.parquet using offline SentenceTransformer (all-MiniLM-L6-v2).
Serializes the pre-computed binary matrix (N x 384) to data/tariff_vector_index_384.npy
alongside data/tariff_index_map.parquet for zero-latency startup.
"""

import os
import sys
import time
from pathlib import Path
import numpy as np
import pandas as pd

# Guarantee offline mode
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

TARIFF_PARQUET = ROOT_DIR / "data" / "tariff_master.parquet"
OUTPUT_INDEX_384 = ROOT_DIR / "data" / "tariff_vector_index_384.npy"
OUTPUT_INDEX_MAP = ROOT_DIR / "data" / "tariff_index_map.parquet"
LOCAL_MODEL_SNAPSHOT = (
    Path(os.environ.get("USERPROFILE", ""))
    / ".cache"
    / "huggingface"
    / "hub"
    / "models--sentence-transformers--all-MiniLM-L6-v2"
    / "snapshots"
    / "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
)


def build_384d_tariff_vector_index(
    tariff_path: Path = TARIFF_PARQUET,
    out_npy_path: Path = OUTPUT_INDEX_384,
    out_map_path: Path = OUTPUT_INDEX_MAP,
    batch_size: int = 256,
) -> np.ndarray:
    """Precomputes and serializes the 384-D normalized vector catalog."""
    if not tariff_path.exists():
        raise FileNotFoundError(f"Tariff master not found at {tariff_path}")

    from sentence_transformers import SentenceTransformer

    print("=" * 70)
    print("      ONE-TIME VECTOR SERIALIZATION: HSN CATALOG (N x 384)        ")
    print("=" * 70)

    print(f"[*] Ingesting master HSN list from {tariff_path}...")
    df = pd.read_parquet(tariff_path).reset_index(drop=True)
    total_records = len(df)
    print(f"[*] Total master HSN codes to index: {total_records:,}")

    # Use clean_description if present, else description
    if "clean_description" in df.columns:
        descriptions = df["clean_description"].fillna(df["description"]).astype(str).tolist()
    else:
        descriptions = df["description"].fillna("").astype(str).tolist()

    print(f"[*] Loading offline SentenceTransformer (all-MiniLM-L6-v2 384-D)...")
    model_source = str(LOCAL_MODEL_SNAPSHOT) if LOCAL_MODEL_SNAPSHOT.exists() else "all-MiniLM-L6-v2"
    model = SentenceTransformer(model_source)

    t0 = time.perf_counter()
    print(f"[*] Batch encoding {total_records:,} catalog descriptions (batch_size={batch_size})...")

    embeddings = model.encode(
        descriptions,
        batch_size=batch_size,
        show_progress_bar=True,
        normalize_embeddings=True,
        convert_to_numpy=True,
    ).astype(np.float32)

    # Re-verify L2 unit norm
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    embeddings = embeddings / norms

    print(f"[OK] Precomputed catalog matrix shape: {embeddings.shape} (dtype={embeddings.dtype})")
    print(f"[OK] Time elapsed for full catalog serialization: {time.perf_counter() - t0:.2f}s")

    # Serialize pre-computed binary matrix (.npy)
    out_npy_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(out_npy_path, embeddings)
    print(f"[OK] Serialized embedding matrix to {out_npy_path} ({out_npy_path.stat().st_size / 1024:.1f} KB)")

    # Serialize index map (HSN metadata)
    map_cols = [c for c in ["hsn_code", "hsn_4digit", "chapter", "heading", "description", "clean_description", "standard_rate", "is_blocked_17_5", "blocked_17_5_reason"] if c in df.columns]
    index_map_df = df[map_cols].copy()
    index_map_df["catalog_idx"] = np.arange(total_records)
    index_map_df.to_parquet(out_map_path, index=False)
    print(f"[OK] Serialized catalog index map to {out_map_path}")

    return embeddings


if __name__ == "__main__":
    build_384d_tariff_vector_index()
