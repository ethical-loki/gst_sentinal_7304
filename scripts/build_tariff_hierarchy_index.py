"""
Build Hierarchical Tariff Vector Index with BAAI/bge-small-en-v1.5: scripts/build_tariff_hierarchy_index.py
Encodes dynamic context-inherited hierarchical tariff entries for all 13,850 statutory codes:
[Chapter Description] > [Heading Description] > [Subheading / Tariff Item Description]
and extracts residual categorization flags (GIR 3(a)) and distinctive tokens.
"""

import os
import re
import time
from pathlib import Path
import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer

# Enforce offline mode
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

ROOT_DIR = Path(__file__).resolve().parent.parent
TARIFF_PARQUET = ROOT_DIR / "data" / "tariff_master.parquet"
OUTPUT_INDEX_NPY = ROOT_DIR / "data" / "tariff_vector_index_bge.npy"
OUTPUT_MAP_PARQUET = ROOT_DIR / "data" / "tariff_hierarchy_map.parquet"

MODEL_SNAPSHOT = Path(
    r"C:\Users\User\.cache\huggingface\hub\models--BAAI--bge-small-en-v1.5\snapshots\5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"
)

import sys
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.ingest_tariff import CHAPTER_TITLES

STOP_GENERIC_TOKENS = {
    "other", "others", "fresh", "chilled", "frozen", "prepared", "preserved",
    "including", "whether", "which", "with", "without", "than", "more", "less",
    "kind", "goods", "articles", "parts", "thereof", "suitable", "purpose",
    "edible", "crude", "pure", "raw", "semi", "wholly", "not", "elsewhere",
    "specified", "included", "nesoi", "subheading", "heading", "chapter"
}


def build_clean_heading_map(df: pd.DataFrame) -> dict:
    heading_rows = df[df["hsn_code"].str.len() == 4]
    heading_map = {}
    for _, r in heading_rows.iterrows():
        h_code = str(r["hsn_code"]).strip()
        desc = str(r["description"]).strip()
        desc = re.sub(r"^Heading\s+\d{4}\s*-\s*", "", desc, flags=re.I)
        parts = re.split(r"\s*;\s*", desc)
        primary = parts[0].strip()
        if " - " in primary:
            primary = primary.split(" - ")[0].strip()
        if ":" in primary:
            primary = primary.split(":")[0].strip()
        heading_map[h_code] = primary.title()
    return heading_map


def build_hierarchical_entry(row: pd.Series, heading_map: dict) -> tuple:
    code = str(row["hsn_code"]).strip()
    chap = str(row["chapter"]).strip()
    head = str(row["heading"]).strip()
    raw_desc = str(row["description"]).strip()

    # 1. Chapter title
    chap_title = CHAPTER_TITLES.get(chap, f"Chapter {chap}").strip()
    chap_title = chap_title.split(",")[0].strip()

    # 2. Heading title
    head_title = heading_map.get(head, f"Heading {head}").strip()

    # 3. Item description from Final_hsn_sac_copy.xlsx
    clean_desc = re.sub(r"^Heading\s+\d{4}\s*-\s*", "", raw_desc, flags=re.I)
    clean_desc_no_excl = re.sub(r"\[.*?\]", " ", clean_desc).strip()
    clean_desc_no_excl = re.sub(r"\((?:other than|except).*?\)", " ", clean_desc_no_excl, flags=re.I).strip()
    clean_desc_no_excl = re.sub(r"\s+", " ", clean_desc_no_excl).strip()

    if len(code) <= 4:
        leaf_desc = clean_desc_no_excl if clean_desc_no_excl else head_title
        h_text = f"{chap_title} -> {leaf_desc}"
        is_residual = False
        all_text = f"{leaf_desc} {head_title}".lower()
        words = re.findall(r"\b[a-zA-Z]{3,}\b", all_text)
        distinctive = list(dict.fromkeys([w for w in words if w not in STOP_GENERIC_TOKENS]))
        return h_text, is_residual, distinctive

    parts = re.split(r"\s*[:\-]\s*", clean_desc_no_excl)
    parts = [p.strip() for p in parts if p.strip()]

    leaf_parts = []
    head_lower = head_title.lower()
    for p in parts:
        p_clean = re.sub(r"\s+", " ", p).strip()
        if p_clean.lower() not in head_lower:
            leaf_parts.append(p_clean)

    if not leaf_parts:
        leaf_desc = parts[-1] if parts else clean_desc_no_excl
    else:
        leaf_desc = " -> ".join(leaf_parts)

    leaf_desc = leaf_desc.title()
    leaf_words = leaf_desc.split()
    if len(leaf_words) > 35:
        leaf_desc = " ".join(leaf_words[:35])
    if not leaf_desc.endswith("."):
        leaf_desc += "."

    h_text = f"{chap_title} -> {head_title} -> {leaf_desc}"

    is_residual = bool(re.match(r"^(other|others|other parts|not elsewhere)\b", leaf_desc.strip(), re.I))

    all_text = f"{leaf_desc} {head_title}".lower()
    words = re.findall(r"\b[a-zA-Z]{3,}\b", all_text)
    distinctive = list(dict.fromkeys([w for w in words if w not in STOP_GENERIC_TOKENS]))

    return h_text, is_residual, distinctive


def main():
    print("=" * 70)
    print("   BUILD HIERARCHICAL TARIFF VECTOR INDEX (BAAI/bge-small-en-v1.5)   ")
    print("=" * 70)

    t0 = time.time()
    df = pd.read_parquet(TARIFF_PARQUET)
    print(f"[*] Loaded tariff catalog: {len(df)} rows from {TARIFF_PARQUET}")

    heading_map = build_clean_heading_map(df)
    print(f"[*] Built clean heading hierarchy map: {len(heading_map)} headings")

    hierarchical_texts = []
    residual_flags = []
    distinctive_tokens_list = []

    print("[*] Generating dynamic context-inherited hierarchical passages...")
    for _, r in df.iterrows():
        h_text, is_res, dist = build_hierarchical_entry(r, heading_map)
        hierarchical_texts.append(h_text)
        residual_flags.append(is_res)
        distinctive_tokens_list.append(" ".join(dist))

    df["hierarchical_text"] = hierarchical_texts
    df["is_residual"] = residual_flags
    df["distinctive_tokens"] = distinctive_tokens_list

    # Print verification samples
    print("\n--- Canonical Verification Entries ---")
    for sample_code in ["08081000", "08109040", "73072100", "84818030"]:
        sub = df[df["hsn_code"] == sample_code]
        if not sub.empty:
            r = sub.iloc[0]
            print(f"HSN {r['hsn_code']}: is_residual={r['is_residual']} | text={r['hierarchical_text']}")

    model_path = str(MODEL_SNAPSHOT) if MODEL_SNAPSHOT.exists() else "BAAI/bge-small-en-v1.5"
    print(f"\n[*] Loading SentenceTransformer ({model_path})...")
    model = SentenceTransformer(model_path)
    model.max_seq_length = 96

    print(f"[*] Encoding {len(hierarchical_texts)} hierarchical tariff passages on CPU (batch_size=256, max_seq_length=96)...")
    embeddings = model.encode(
        hierarchical_texts,
        batch_size=256,
        show_progress_bar=True,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )
    embeddings = embeddings.astype(np.float32)
    print(f"[*] Embeddings generated. Shape: {embeddings.shape}, dtype: {embeddings.dtype}")

    # Verify L2 normalization
    norms = np.linalg.norm(embeddings, axis=1)
    print(f"[*] Embedding L2 norms: min={norms.min():.4f}, max={norms.max():.4f}, mean={norms.mean():.4f}")

    # Save vector index and enriched hierarchy map
    np.save(OUTPUT_INDEX_NPY, embeddings)
    print(f"[OK] Saved vector index to: {OUTPUT_INDEX_NPY} ({OUTPUT_INDEX_NPY.stat().st_size / 1e6:.1f} MB)")

    df.to_parquet(OUTPUT_MAP_PARQUET, index=False)
    print(f"[OK] Saved hierarchy map to: {OUTPUT_MAP_PARQUET} ({OUTPUT_MAP_PARQUET.stat().st_size / 1e6:.1f} MB)")

    elapsed = time.time() - t0
    print(f"[SUCCESS] Complete hierarchical tariff vector indexing finished in {elapsed:.2f} seconds.")


if __name__ == "__main__":
    main()
