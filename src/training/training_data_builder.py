"""
src/training/training_data_builder.py
=====================================
Phase 2: Dynamic Training-Data Builder

Builds chapter-stratified Train / Validation / Test positive pairs from the
Master HSN dataset (`data/enriched_master_hsn.parquet`) using `SyntheticQueryGenerator`.

Every generated pair links a commercial/natural-language product query to its
originating statutory tariff context (`format_tariff_context`) with zero leakage
between train, val, and test HSN codes.
"""

import json
import logging
import random
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from src.ml.product_tariff_reranker import format_tariff_context
from src.ml.synthetic_query_generator import SyntheticQueryGenerator

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_MASTER_PARQUET = ROOT_DIR / "data" / "enriched_master_hsn.parquet"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "data" / "training_pairs"


class TrainingDataBuilder:
    """
    Generates stratified positive (query, tariff_context) training pairs
    from the authoritative Master HSN dataset.
    """

    def __init__(
        self,
        master_parquet: Path = DEFAULT_MASTER_PARQUET,
        output_dir: Path = DEFAULT_OUTPUT_DIR,
        seed: int = 42,
        use_llm: bool = False,
    ):
        self.master_parquet = Path(master_parquet)
        self.output_dir = Path(output_dir)
        self.seed = seed
        self.rng = random.Random(seed)
        self.query_gen = SyntheticQueryGenerator(seed=seed, use_llm=use_llm)

    def load_master_rows(self, leaf_8digit_only: bool = True) -> pd.DataFrame:
        if not self.master_parquet.exists():
            raise FileNotFoundError(f"Master parquet not found at {self.master_parquet}")
        df = pd.read_parquet(self.master_parquet)
        df["hsn_clean"] = df["hsn_code"].astype(str).str.replace(" ", "", regex=False).str.strip()
        df["chapter_clean"] = df["chapter_code"].astype(str).str.strip().str.zfill(2)
        if leaf_8digit_only:
            df = df[df["hsn_clean"].str.len() == 8].copy()
        return df.reset_index(drop=True)

    def split_by_hsn_stratified(
        self,
        df: pd.DataFrame,
        train_ratio: float = 0.80,
        val_ratio: float = 0.10,
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        Splits rows into train / val / test grouped by `hsn_clean` and stratified
        by `chapter_clean` so no HSN code appears in more than one split.
        """
        chapter_to_hsns: Dict[str, List[str]] = defaultdict(list)
        for ch, grp in df.groupby("chapter_clean"):
            hsns = sorted(grp["hsn_clean"].unique().tolist())
            self.rng.shuffle(hsns)
            chapter_to_hsns[ch] = hsns

        train_hsns, val_hsns, test_hsns = set(), set(), set()
        for ch, hsns in chapter_to_hsns.items():
            n = len(hsns)
            n_train = max(1, int(n * train_ratio))
            n_val = max(1, int(n * val_ratio)) if n >= 3 else 0
            train_hsns.update(hsns[:n_train])
            val_hsns.update(hsns[n_train : n_train + n_val])
            test_hsns.update(hsns[n_train + n_val :])

        train_df = df[df["hsn_clean"].isin(train_hsns)].reset_index(drop=True)
        val_df = df[df["hsn_clean"].isin(val_hsns)].reset_index(drop=True)
        test_df = df[df["hsn_clean"].isin(test_hsns)].reset_index(drop=True)
        return train_df, val_df, test_df

    def build_positive_pairs(
        self, df: pd.DataFrame, split_name: str, max_queries_per_row: int = 4
    ) -> pd.DataFrame:
        rows_out: List[Dict[str, Any]] = []
        for rec in df.to_dict(orient="records"):
            tariff_ctx = format_tariff_context(rec)
            if not tariff_ctx:
                continue
            generated = self.query_gen.generate_for_row(rec, max_queries=max_queries_per_row)
            for g in generated:
                rows_out.append(
                    {
                        "split": split_name,
                        "query": g.query,
                        "query_strategy": g.strategy,
                        "hsn_code": rec["hsn_clean"],
                        "chapter_code": rec["chapter_clean"],
                        "heading_4digit": str(rec.get("heading_4digit", "")),
                        "tariff_context": tariff_ctx,
                        "label": 1,
                        "relation": "SAME_PRODUCT",
                    }
                )
        return pd.DataFrame(rows_out)

    def run(
        self,
        leaf_8digit_only: bool = True,
        max_queries_per_row: int = 4,
    ) -> Dict[str, Any]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        df = self.load_master_rows(leaf_8digit_only=leaf_8digit_only)
        train_df, val_df, test_df = self.split_by_hsn_stratified(df)

        pos_train = self.build_positive_pairs(train_df, "train", max_queries_per_row)
        pos_val = self.build_positive_pairs(val_df, "val", max_queries_per_row)
        pos_test = self.build_positive_pairs(test_df, "test", max_queries_per_row)

        pos_train.to_parquet(self.output_dir / "positive_pairs_train.parquet", index=False)
        pos_val.to_parquet(self.output_dir / "positive_pairs_val.parquet", index=False)
        pos_test.to_parquet(self.output_dir / "positive_pairs_test.parquet", index=False)

        stats = {
            "source_master_rows": len(df),
            "leaf_8digit_only": leaf_8digit_only,
            "max_queries_per_row": max_queries_per_row,
            "splits": {
                "train": {
                    "unique_hsn_codes": int(pos_train["hsn_code"].nunique()),
                    "positive_pairs": len(pos_train),
                    "strategy_counts": pos_train["query_strategy"].value_counts().to_dict(),
                },
                "val": {
                    "unique_hsn_codes": int(pos_val["hsn_code"].nunique()),
                    "positive_pairs": len(pos_val),
                    "strategy_counts": pos_val["query_strategy"].value_counts().to_dict(),
                },
                "test": {
                    "unique_hsn_codes": int(pos_test["hsn_code"].nunique()),
                    "positive_pairs": len(pos_test),
                    "strategy_counts": pos_test["query_strategy"].value_counts().to_dict(),
                },
            },
        }

        with open(self.output_dir / "dataset_stats.json", "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2)

        logger.info(
            f"Built positive pairs: train={len(pos_train)}, val={len(pos_val)}, test={len(pos_test)}"
        )
        return stats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    builder = TrainingDataBuilder()
    stats = builder.run()
    print(json.dumps(stats, indent=2))

