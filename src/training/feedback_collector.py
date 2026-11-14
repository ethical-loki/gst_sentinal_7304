"""
src/training/feedback_collector.py
==================================
Phase 6: Verified Feedback Collector & Continuous Learning Pipeline

Keeps unconfirmed customer flags/predictions strictly separate from GST-expert
verified classifications:
  1. `record_pending_feedback(...)` logs raw user/customer rejections & model
     predictions to `data/verified_feedback/pending_feedback.jsonl` (never used for training).
  2. `confirm_expert_correction(...)` records an expert-verified correction and
     converts it into hard-negative + positive training pairs in
     `data/verified_feedback/verified_pairs.parquet`.
  3. `export_retraining_dataset(...)` merges verified feedback pairs into the
     main training set (`full_pairs_train.parquet`) for periodic fine-tuning.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from src.ml.product_tariff_reranker import format_tariff_context

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_FEEDBACK_DIR = ROOT_DIR / "data" / "verified_feedback"
DEFAULT_PAIRS_DIR = ROOT_DIR / "data" / "training_pairs"


class FeedbackCollector:
    """Manages pending feedback and expert-verified hard-negative training pairs."""

    def __init__(self, feedback_dir: Path = DEFAULT_FEEDBACK_DIR):
        self.feedback_dir = Path(feedback_dir)
        self.feedback_dir.mkdir(parents=True, exist_ok=True)
        self.pending_path = self.feedback_dir / "pending_feedback.jsonl"
        self.verified_log_path = self.feedback_dir / "verified_corrections.jsonl"
        self.verified_pairs_path = self.feedback_dir / "verified_pairs.parquet"

    def record_pending_feedback(
        self,
        query: str,
        predicted_hsn: str,
        predicted_context: str,
        predicted_score: float,
        customer_selected_hsn: Optional[str] = None,
        reason: str = "",
    ) -> str:
        """
        Records an unconfirmed customer rejection or selection for expert review.
        Never enters the training set until verified by a GST expert.
        """
        feedback_id = str(uuid.uuid4())[:12]
        record = {
            "feedback_id": feedback_id,
            "status": "PENDING_EXPERT_REVIEW",
            "query": query.strip(),
            "predicted_hsn": str(predicted_hsn).strip(),
            "predicted_context": predicted_context,
            "predicted_score": float(predicted_score),
            "customer_selected_hsn": str(customer_selected_hsn).strip() if customer_selected_hsn else None,
            "reason": reason,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(self.pending_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
        logger.info(f"Logged pending feedback {feedback_id} for query='{query}'")
        return feedback_id

    def confirm_expert_correction(
        self,
        query: str,
        incorrect_row: Optional[Dict[str, Any]],
        correct_row: Optional[Dict[str, Any]],
        expert_id: str,
        notes: str = "",
    ) -> int:
        """
        Records an expert-verified correction and emits verified training pairs:
          - (query, incorrect_tariff_context) -> label=0, relation=RELATED_PRODUCT
          - (query, correct_tariff_context)   -> label=1, relation=SAME_PRODUCT
        Returns the number of new verified training pairs appended.
        """
        correction_id = str(uuid.uuid4())[:12]
        now = datetime.now(timezone.utc).isoformat()
        new_pairs: List[Dict[str, Any]] = []

        if incorrect_row is not None:
            inc_ctx = format_tariff_context(incorrect_row)
            if inc_ctx:
                new_pairs.append(
                    {
                        "split": "train",
                        "query": query.strip(),
                        "query_strategy": "expert_feedback_hard_negative",
                        "hsn_code": str(
                            incorrect_row.get("hsn_code") or incorrect_row.get("HSN Code") or ""
                        ).strip(),
                        "chapter_code": str(
                            incorrect_row.get("chapter_code") or incorrect_row.get("chapter") or ""
                        )
                        .strip()
                        .zfill(2),
                        "heading_4digit": str(incorrect_row.get("heading_4digit", "")),
                        "tariff_context": inc_ctx,
                        "label": 0,
                        "relation": "RELATED_PRODUCT",
                        "negative_type": "expert_rejected",
                        "positive_hsn_ref": str(
                            (correct_row or {}).get("hsn_code")
                            or (correct_row or {}).get("HSN Code")
                            or ""
                        ).strip(),
                        "dense_sim": 1.0,
                    }
                )

        if correct_row is not None:
            cor_ctx = format_tariff_context(correct_row)
            if cor_ctx:
                new_pairs.append(
                    {
                        "split": "train",
                        "query": query.strip(),
                        "query_strategy": "expert_feedback_positive",
                        "hsn_code": str(
                            correct_row.get("hsn_code") or correct_row.get("HSN Code") or ""
                        ).strip(),
                        "chapter_code": str(
                            correct_row.get("chapter_code") or correct_row.get("chapter") or ""
                        )
                        .strip()
                        .zfill(2),
                        "heading_4digit": str(correct_row.get("heading_4digit", "")),
                        "tariff_context": cor_ctx,
                        "label": 1,
                        "relation": "SAME_PRODUCT",
                        "negative_type": "none",
                        "positive_hsn_ref": str(
                            correct_row.get("hsn_code") or correct_row.get("HSN Code") or ""
                        ).strip(),
                        "dense_sim": 1.0,
                    }
                )

        if not new_pairs:
            return 0

        audit_entry = {
            "correction_id": correction_id,
            "expert_id": expert_id,
            "query": query.strip(),
            "incorrect_hsn": (incorrect_row or {}).get("hsn_code") or (incorrect_row or {}).get("HSN Code"),
            "correct_hsn": (correct_row or {}).get("hsn_code") or (correct_row or {}).get("HSN Code"),
            "notes": notes,
            "pairs_added": len(new_pairs),
            "verified_at": now,
        }
        with open(self.verified_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(audit_entry) + "\n")

        new_df = pd.DataFrame(new_pairs)
        if self.verified_pairs_path.exists():
            existing_df = pd.read_parquet(self.verified_pairs_path)
            combined = pd.concat([existing_df, new_df], ignore_index=True)
        else:
            combined = new_df
        combined.to_parquet(self.verified_pairs_path, index=False)
        logger.info(f"Expert '{expert_id}' verified correction {correction_id}: +{len(new_pairs)} pairs.")
        return len(new_pairs)

    def merge_into_training_set(
        self,
        base_train_parquet: Path = DEFAULT_PAIRS_DIR / "full_pairs_train.parquet",
        output_parquet: Optional[Path] = None,
        verified_weight_multiplier: int = 2,
    ) -> Path:
        """
        Merges expert-verified feedback pairs into the main training set for
        periodic fine-tuning, repeating verified pairs by `verified_weight_multiplier`.
        """
        base_df = pd.read_parquet(base_train_parquet)
        if self.verified_pairs_path.exists():
            ver_df = pd.read_parquet(self.verified_pairs_path)
            if not ver_df.empty:
                repeated = pd.concat([ver_df] * max(1, verified_weight_multiplier), ignore_index=True)
                merged = pd.concat([base_df, repeated], ignore_index=True)
            else:
                merged = base_df
        else:
            merged = base_df

        merged = merged.sample(frac=1.0, random_state=42).reset_index(drop=True)
        dest = Path(output_parquet or (self.feedback_dir / "merged_train_with_feedback.parquet"))
        merged.to_parquet(dest, index=False)
        logger.info(f"Exported merged training dataset ({len(merged)} rows) -> {dest}")
        return dest

    def list_pending_feedback(
        self, status: str = "PENDING_EXPERT_REVIEW"
    ) -> List[Dict[str, Any]]:
        """Lists customer feedback entries filtered by status."""
        if not self.pending_path.exists():
            return []
        entries: List[Dict[str, Any]] = []
        with open(self.pending_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if not status or rec.get("status") == status:
                    entries.append(rec)
        return entries

    def approve_pending_feedback(
        self,
        feedback_id: str,
        expert_id: str,
        incorrect_row: Optional[Dict[str, Any]],
        correct_row: Dict[str, Any],
        notes: str = "",
    ) -> int:
        """
        GST expert verifies a pending customer flag, promoting it to the
        verified training dataset and marking the pending record VERIFIED.
        """
        if not self.pending_path.exists():
            raise FileNotFoundError(f"No pending feedback file at {self.pending_path}")

        records: List[Dict[str, Any]] = []
        target_rec: Optional[Dict[str, Any]] = None
        with open(self.pending_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if rec.get("feedback_id") == feedback_id:
                    target_rec = rec
                records.append(rec)

        if target_rec is None:
            raise ValueError(f"Pending feedback_id '{feedback_id}' not found.")

        pairs_added = self.confirm_expert_correction(
            query=target_rec["query"],
            incorrect_row=incorrect_row,
            correct_row=correct_row,
            expert_id=expert_id,
            notes=notes,
        )

        target_rec["status"] = "VERIFIED"
        target_rec["verified_by"] = expert_id
        target_rec["verified_at"] = datetime.now(timezone.utc).isoformat()
        with open(self.pending_path, "w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec) + "\n")

        return pairs_added

    def run_retraining_lifecycle(
        self,
        new_version_name: str,
        base_train_parquet: Path = DEFAULT_PAIRS_DIR / "full_pairs_train.parquet",
        val_parquet: Path = DEFAULT_PAIRS_DIR / "full_pairs_val.parquet",
        test_parquet: Path = DEFAULT_PAIRS_DIR / "full_pairs_test.parquet",
        registry: Optional[Any] = None,
        trainer_fn: Optional[Any] = None,
        epochs: int = 1,
        batch_size: int = 16,
        min_auc_delta: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Step 8 end-to-end continuous improvement lifecycle:
          Verified training dataset -> Model retraining -> Held-out evaluation ->
          Approved deployment (ModelRegistry promotion only if no regression).
        Refuses to run if no expert-verified pairs exist.
        """
        if not self.verified_pairs_path.exists():
            raise ValueError(
                "No expert-verified training pairs found. Never train directly on unverified customer feedback."
            )
        ver_df = pd.read_parquet(self.verified_pairs_path)
        if ver_df.empty:
            raise ValueError(
                "Verified training pairs dataset is empty. Expert verification is required before retraining."
            )

        merged_train = self.merge_into_training_set(base_train_parquet=base_train_parquet)

        if registry is None:
            from src.ml.model_registry import ModelRegistry
            registry = ModelRegistry()

        active = registry.get_active()
        prev_auc = float((active or {}).get("metrics", {}).get("test_roc_auc", 0.0))

        if trainer_fn is None:
            from src.training.train_reranker import train_and_evaluate
            trainer_fn = train_and_evaluate

        train_result = trainer_fn(
            train_path=merged_train,
            val_path=val_parquet,
            test_path=test_parquet,
            version_name=new_version_name,
            epochs=epochs,
            batch_size=batch_size,
            promote=False,
        )
        new_auc = float(train_result.get("test_metrics", {}).get("roc_auc", 0.0))

        approved = new_auc >= (prev_auc + min_auc_delta)
        if approved:
            registry.promote(new_version_name)
            status = "PROMOTED"
        else:
            status = "REJECTED_REGRESSION"

        return {
            "status": status,
            "promoted": approved,
            "new_version_name": new_version_name,
            "verified_pairs_count": int(len(ver_df)),
            "merged_train_path": str(merged_train),
            "previous_test_auc": round(prev_auc, 4),
            "new_test_auc": round(new_auc, 4),
            "threshold": train_result.get("calibrated_threshold"),
        }

