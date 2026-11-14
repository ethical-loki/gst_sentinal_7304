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

