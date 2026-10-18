"""
Tariff Vector Index Precomputation: scripts/build_tariff_index.py
Encodes all official statutory descriptions from data/tariff_master.parquet
using the trained CPU contrastive encoder (models/hsn_contrastive_mlp.pt).
Persists the precomputed dense matrix (N x 128) to data/tariff_vector_index.npy.
"""

import sys
import time
from pathlib import Path
import numpy as np
import pandas as pd
import torch

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.models.tokenizer import FeatureHashingTokenizer
from src.models.hsn_encoder import HSNContrastiveMLP

TARIFF_PARQUET = ROOT_DIR / "data" / "tariff_master.parquet"
MODEL_PATH = ROOT_DIR / "models" / "hsn_contrastive_mlp.pt"
OUTPUT_INDEX_PATH = ROOT_DIR / "data" / "tariff_vector_index.npy"


def build_tariff_vector_index(
    tariff_path: Path = TARIFF_PARQUET,
    model_path: Path = MODEL_PATH,
    out_path: Path = OUTPUT_INDEX_PATH,
    batch_size: int = 128,
) -> np.ndarray:
    """Encodes all official tariff descriptions and persists an N x 128 vector matrix."""
    if not tariff_path.exists():
        raise FileNotFoundError(f"Tariff master parquet not found at {tariff_path}")
    if not model_path.exists():
        raise FileNotFoundError(f"Trained model weights not found at {model_path}. Run scripts/train_hsn_encoder.py first.")

    print("=" * 65)
    print("        PRECOMPUTING TARIFF DENSE VECTOR INDEX (128-D)        ")
    print("=" * 65)

    print(f"[*] Loading tariff master from {tariff_path}...")
    df = pd.read_parquet(tariff_path)
    total_records = len(df)
    print(f"[*] Total statutory tariff records to encode: {total_records}")

    print(f"[*] Loading trained contrastive encoder from {model_path}...")
    model = HSNContrastiveMLP(input_dim=32768, hidden_dim=512, output_dim=128)
    model.load_state_dict(torch.load(model_path, map_location="cpu"))
    model.eval()

    tokenizer = FeatureHashingTokenizer(dim=32768)

    # Use description or clean_description
    descriptions = df["description"].fillna("").astype(str).tolist()

    t0 = time.perf_counter()
    all_embeddings: list = []

    with torch.no_grad():
        for i in range(0, total_records, batch_size):
            batch_texts = descriptions[i : i + batch_size]
            batch_tokens = tokenizer.batch_tokenize(batch_texts)
            z_batch = model(batch_tokens)  # (B, 128)
            all_embeddings.append(z_batch.cpu().numpy())

    index_matrix = np.vstack(all_embeddings).astype(np.float32)

    # Verify unit hypersphere normalization
    norms = np.linalg.norm(index_matrix, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-3), "Embeddings are not unit normalized!"

    print(f"[OK] Precomputed {index_matrix.shape[0]} vectors of dimension {index_matrix.shape[1]}")
    print(f"     Time elapsed: {time.perf_counter() - t0:.2f}s")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(out_path, index_matrix)
    print(f"[OK] Persisted dense index matrix to {out_path} ({out_path.stat().st_size / 1024:.1f} KB)")

    return index_matrix


if __name__ == "__main__":
    build_tariff_vector_index()
