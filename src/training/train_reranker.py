"""
src/training/train_reranker.py
==============================
Phase 4: Fine-Tunes the Product-to-Tariff Cross-Encoder on Mined Positives & Hard Negatives.

Pipeline:
  1. Loads `full_pairs_train.parquet`, `full_pairs_val.parquet`, `full_pairs_test.parquet`.
  2. Trains CrossEncoder (`cross-encoder/ms-marco-MiniLM-L-6-v2` by default for fast
     local CPU training, or `BAAI/bge-reranker-v2-m3` when GPU is available).
  3. Learns the optimal calibrated sigmoid decision threshold on the validation set.
  4. Evaluates on the held-out test set and Golden/Adversarial retrieval benchmarks.
  5. Saves and promotes the versioned model via `ModelRegistry`.
"""

import argparse
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
import torch
from sentence_transformers import CrossEncoder
from torch.utils.data import DataLoader, Dataset
from transformers import get_linear_schedule_with_warmup

from src.ml.model_registry import ModelRegistry
from src.ml.product_tariff_reranker import BASELINE_RERANKER_MODEL, ProductTariffReranker
from src.training.evaluation_pipeline import evaluate_end_to_end_retrieval, evaluate_pairs

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_PAIRS_DIR = ROOT_DIR / "data" / "training_pairs"
DEFAULT_VERSIONS_DIR = ROOT_DIR / "data" / "model_versions"


class _PairDataset(Dataset):
    def __init__(self, df: pd.DataFrame):
        self.queries = df["query"].astype(str).tolist()
        self.contexts = df["tariff_context"].astype(str).tolist()
        self.labels = df["label"].astype(float).tolist()

    def __len__(self) -> int:
        return len(self.queries)

    def __getitem__(self, idx: int):
        return self.queries[idx], self.contexts[idx], self.labels[idx]


def _stratified_sample(df: pd.DataFrame, max_samples: Optional[int], seed: int = 42) -> pd.DataFrame:
    if not max_samples or max_samples <= 0 or len(df) <= max_samples:
        return df.sample(frac=1.0, random_state=seed).reset_index(drop=True)
    # Keep 50/50 positive/negative balance
    half = max_samples // 2
    pos = df[df["label"] == 1]
    neg = df[df["label"] == 0]
    pos_s = pos.sample(n=min(half, len(pos)), random_state=seed)
    neg_s = neg.sample(n=min(max_samples - len(pos_s), len(neg)), random_state=seed)
    return pd.concat([pos_s, neg_s], ignore_index=True).sample(frac=1.0, random_state=seed).reset_index(drop=True)


def train_and_evaluate(
    base_model: str = BASELINE_RERANKER_MODEL,
    version_id: str = "hsn_reranker_v1",
    pairs_dir: Path = DEFAULT_PAIRS_DIR,
    versions_dir: Path = DEFAULT_VERSIONS_DIR,
    epochs: int = 1,
    batch_size: int = 32,
    max_length: int = 192,
    lr: float = 3e-5,
    max_train_samples: int = 4000,
    max_eval_samples: int = 1500,
    run_e2e_eval: bool = True,
) -> Dict[str, Any]:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    train_df = pd.read_parquet(Path(pairs_dir) / "full_pairs_train.parquet")
    val_df = pd.read_parquet(Path(pairs_dir) / "full_pairs_val.parquet")
    test_df = pd.read_parquet(Path(pairs_dir) / "full_pairs_test.parquet")

    train_sub = _stratified_sample(train_df, max_train_samples)
    logger.info(
        f"Training '{base_model}' -> '{version_id}' on {len(train_sub)} pairs "
        f"(pos={(train_sub['label']==1).sum()}, neg={(train_sub['label']==0).sum()}) "
        f"| epochs={epochs}, batch_size={batch_size}, max_length={max_length}"
    )

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = CrossEncoder(
        base_model,
        num_labels=1,
        max_length=max_length,
        device=device,
        local_files_only=True,
    )

    dataset = _PairDataset(train_sub)

    def _collate(batch):
        qs, ctxs, lbls = zip(*batch)
        enc = model.tokenizer(
            list(qs),
            list(ctxs),
            padding=True,
            truncation=True,
            max_length=max_length,
            return_tensors="pt",
        )
        enc["labels"] = torch.tensor(lbls, dtype=torch.float32)
        return enc

    train_dataloader = DataLoader(dataset, shuffle=True, batch_size=batch_size, collate_fn=_collate)
    total_steps = len(train_dataloader) * epochs
    warmup_steps = max(5, int(total_steps * 0.1))

    output_dir = Path(versions_dir) / version_id
    output_dir.mkdir(parents=True, exist_ok=True)

    optimizer = torch.optim.AdamW(model.model.parameters(), lr=lr, weight_decay=0.01)
    scheduler = get_linear_schedule_with_warmup(
        optimizer, num_warmup_steps=warmup_steps, num_training_steps=total_steps
    )
    loss_fn = torch.nn.BCEWithLogitsLoss()

    model.model.train()
    t0 = time.perf_counter()
    global_step = 0
    for epoch in range(epochs):
        running_loss = 0.0
        for step_idx, batch in enumerate(train_dataloader, start=1):
            labels = batch.pop("labels").to(device)
            inputs = {k: v.to(device) for k, v in batch.items()}
            optimizer.zero_grad()
            logits = model.model(**inputs).logits.squeeze(-1)
            loss = loss_fn(logits, labels)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            running_loss += float(loss.item())
            global_step += 1
            if step_idx % 25 == 0 or step_idx == len(train_dataloader):
                logger.info(
                    f"Epoch {epoch + 1}/{epochs} | Step {step_idx}/{len(train_dataloader)} "
                    f"| Avg Loss: {running_loss / step_idx:.4f}"
                )

    train_time_s = time.perf_counter() - t0
    model.model.eval()
    model.save(str(output_dir))
    logger.info(f"Fine-tuning complete in {train_time_s:.1f}s. Saved to {output_dir}")

    # Load fine-tuned model via ProductTariffReranker for calibration & evaluation
    finetuned_reranker = ProductTariffReranker(
        model_name_or_path=str(output_dir),
        max_length=max_length,
        local_files_only=True,
        batch_size=32,
    )

    logger.info("Calibrating threshold on validation set...")
    val_metrics = evaluate_pairs(
        finetuned_reranker, val_df, threshold=None, max_samples=max_eval_samples
    )
    calibrated_threshold = val_metrics["calibrated_threshold"]

    logger.info(f"Evaluating on held-out test set (threshold={calibrated_threshold})...")
    test_metrics = evaluate_pairs(
        finetuned_reranker, test_df, threshold=calibrated_threshold, max_samples=max_eval_samples
    )

    e2e_metrics: Dict[str, Any] = {}
    if run_e2e_eval:
        logger.info("Running end-to-end Golden Intent + Adversarial benchmark...")
        e2e_metrics = evaluate_end_to_end_retrieval(finetuned_reranker, max_golden_queries=40)

    all_metrics = {
        "train_samples": len(train_sub),
        "epochs": epochs,
        "train_time_s": round(train_time_s, 1),
        "val_metrics": val_metrics,
        "test_metrics": test_metrics,
        "e2e_retrieval_metrics": e2e_metrics,
    }

    registry = ModelRegistry(versions_dir=versions_dir)
    registry.register_version(
        version_id=version_id,
        model_path=str(output_dir),
        base_model=base_model,
        metrics=all_metrics,
        calibrated_threshold=calibrated_threshold,
        promote=True,
    )

    report_path = ROOT_DIR / "reports" / f"phase4_training_{version_id}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(all_metrics, f, indent=2)

    return all_metrics


def main():
    parser = argparse.ArgumentParser(description="Phase 4: Fine-tune Product-to-Tariff Reranker")
    parser.add_argument("--base-model", default=BASELINE_RERANKER_MODEL)
    parser.add_argument("--version-id", default="hsn_reranker_v1")
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--max-length", type=int, default=192)
    parser.add_argument("--max-train-samples", type=int, default=4000)
    parser.add_argument("--skip-e2e", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    metrics = train_and_evaluate(
        base_model=args.base_model,
        version_id=args.version_id,
        epochs=args.epochs,
        batch_size=args.batch_size,
        max_length=args.max_length,
        max_train_samples=args.max_train_samples,
        run_e2e_eval=not args.skip_e2e,
    )
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
