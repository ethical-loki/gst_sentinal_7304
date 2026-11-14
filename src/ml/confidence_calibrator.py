"""
src/ml/confidence_calibrator.py
===============================
Phase 6: Standalone Confidence Calibration Module.

Separates three independent confidence measures:
  1. `relevance_confidence`: P(candidate matches product | raw_logit)
     via Temperature Scaling or Platt Scaling (a > 0 preserves ranking).
  2. `chapter_confidence`: P(predicted 4-digit heading / 2-digit chapter is correct)
     calibrated on query-level correctness labels (never by summing candidate probs).
  3. `hsn_confidence`: P(predicted exact 8-digit HSN is correct)
     calibrated on query-level exact-HSN correctness using logit, margin,
     sibling count, heading spread, and ambiguity signals (never sibling softmax).
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np


def _sigmoid_arr(x: np.ndarray) -> np.ndarray:
    x_clipped = np.clip(x, -30.0, 30.0)
    return 1.0 / (1.0 + np.exp(-x_clipped))


def compute_calibration_metrics(
    y_true: Sequence[int] | np.ndarray,
    y_prob: Sequence[float] | np.ndarray,
    n_bins: int = 10,
) -> Dict[str, Any]:
    """Computes NLL, Brier score, Expected Calibration Error (ECE), and reliability bins."""
    yt = np.asarray(y_true, dtype=np.float64)
    yp = np.clip(np.asarray(y_prob, dtype=np.float64), 1e-6, 1.0 - 1e-6)
    n = len(yt)
    if n == 0:
        return {"n": 0, "nll": 0.0, "brier": 0.0, "ece": 0.0, "reliability_bins": []}

    nll = float(-np.mean(yt * np.log(yp) + (1.0 - yt) * np.log(1.0 - yp)))
    brier = float(np.mean((yp - yt) ** 2))

    ece = 0.0
    bins_out: List[Dict[str, Any]] = []
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    for b_idx in range(n_bins):
        lo, hi = float(edges[b_idx]), float(edges[b_idx + 1])
        if b_idx == n_bins - 1:
            mask = (yp >= lo) & (yp <= hi)
        else:
            mask = (yp >= lo) & (yp < hi)
        cnt = int(np.sum(mask))
        if cnt == 0:
            continue
        mean_conf = float(np.mean(yp[mask]))
        mean_acc = float(np.mean(yt[mask]))
        ece += (cnt / n) * abs(mean_acc - mean_conf)
        bins_out.append({
            "bin": f"[{lo:.1f},{hi:.1f}]",
            "count": cnt,
            "mean_confidence": round(mean_conf, 4),
            "empirical_accuracy": round(mean_acc, 4),
        })

    return {
        "n": n,
        "nll": round(nll, 4),
        "brier": round(brier, 4),
        "ece": round(float(ece), 4),
        "reliability_bins": bins_out,
    }


def compute_selective_curve(
    y_true: Sequence[int] | np.ndarray,
    y_prob: Sequence[float] | np.ndarray,
    thresholds: Sequence[float] = (0.3, 0.4, 0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9),
) -> List[Dict[str, Any]]:
    """Computes Coverage vs Accuracy vs Error Rate across confidence thresholds."""
    yt = np.asarray(y_true, dtype=np.float64)
    yp = np.asarray(y_prob, dtype=np.float64)
    n = max(len(yt), 1)
    curve: List[Dict[str, Any]] = []
    for tau in thresholds:
        mask = yp >= tau
        covered = int(np.sum(mask))
        cov = covered / n
        if covered > 0:
            acc = float(np.mean(yt[mask]))
            err = 1.0 - acc
        else:
            acc = 1.0
            err = 0.0
        curve.append({
            "threshold": round(float(tau), 2),
            "covered": covered,
            "coverage": round(cov, 4),
            "accuracy": round(acc, 4),
            "error_rate": round(err, 4),
        })
    return curve


@dataclass
class ScalarLogitCalibrator:
    """
    Calibrates raw Cross-Encoder logits via:
      - method='temperature': p = sigmoid(logit / T), T > 0
      - method='platt':       p = sigmoid(a * logit + b), a > 0 (ranking-preserving)
    """

    method: str = "temperature"
    scale: float = 1.0  # (1/T) for temperature, `a` for platt
    bias: float = 0.0   # 0.0 for temperature, `b` for platt

    def fit(
        self,
        raw_logits: Sequence[float] | np.ndarray,
        labels: Sequence[int] | np.ndarray,
        method: str = "temperature",
        lr: float = 0.05,
        steps: int = 800,
        l2: float = 1e-4,
    ) -> "ScalarLogitCalibrator":
        z = np.asarray(raw_logits, dtype=np.float64)
        y = np.asarray(labels, dtype=np.float64)
        self.method = method

        # Parameterize scale = exp(u) so scale > 0 is strictly guaranteed (preserves ranking)
        u = 0.0
        b = 0.0
        for _ in range(steps):
            s = math.exp(max(-4.0, min(4.0, u)))
            logits = s * z + (b if method == "platt" else 0.0)
            p = _sigmoid_arr(logits)
            err = p - y
            grad_u = float(np.mean(err * z) * s + l2 * u)
            u -= lr * grad_u
            if method == "platt":
                grad_b = float(np.mean(err) + l2 * b)
                b -= lr * grad_b

        self.scale = round(math.exp(max(-4.0, min(4.0, u))), 6)
        self.bias = round(b if method == "platt" else 0.0, 6)
        return self

    def predict_proba(self, raw_logits: Sequence[float] | np.ndarray | float) -> np.ndarray | float:
        if isinstance(raw_logits, (int, float)):
            return float(_sigmoid_arr(np.array([self.scale * float(raw_logits) + self.bias]))[0])
        z = np.asarray(raw_logits, dtype=np.float64)
        return _sigmoid_arr(self.scale * z + self.bias)


QUERY_FEATURE_NAMES = [
    "top1_logit",
    "top1_top2_margin",
    "n_siblings_same_heading",
    "n_distinct_headings_above",
    "n_distinct_chapters_above",
    "is_ambiguous",
    "query_token_count",
]


def extract_query_confidence_features(
    raw_logits: Sequence[float],
    hsn_codes: Sequence[str],
    chapter_codes: Sequence[str],
    query: str,
    rel_threshold_logit: float = 0.0,
    is_ambiguous: bool = False,
) -> Dict[str, float]:
    """
    Extracts non-product-specific structural signals for query-level
    chapter_confidence and hsn_confidence calibration.
    """
    if not raw_logits:
        return {k: 0.0 for k in QUERY_FEATURE_NAMES}

    top1_z = float(raw_logits[0])
    top2_z = float(raw_logits[1]) if len(raw_logits) > 1 else top1_z - 5.0
    margin = max(0.0, top1_z - top2_z)

    top_h4 = str(hsn_codes[0]).replace(" ", "")[:4] if hsn_codes else ""
    n_siblings = sum(
        1
        for h, z in zip(hsn_codes, raw_logits)
        if str(h).replace(" ", "")[:4] == top_h4 and z >= rel_threshold_logit
    )
    headings_above = {
        str(h).replace(" ", "")[:4]
        for h, z in zip(hsn_codes, raw_logits)
        if z >= rel_threshold_logit and h
    }
    chaps_above = {
        str(c).strip().zfill(2)
        for c, z in zip(chapter_codes, raw_logits)
        if z >= rel_threshold_logit and c
    }
    tok_cnt = len([t for t in (query or "").strip().split() if t])

    return {
        "top1_logit": top1_z,
        "top1_top2_margin": margin,
        "n_siblings_same_heading": float(max(1, n_siblings)),
        "n_distinct_headings_above": float(max(1, len(headings_above))),
        "n_distinct_chapters_above": float(max(1, len(chaps_above))),
        "is_ambiguous": 1.0 if is_ambiguous else 0.0,
        "query_token_count": float(tok_cnt),
    }


@dataclass
class LogisticFeatureCalibrator:
    """
    L2-regularized standardized logistic calibrator for query-level
    chapter_confidence and hsn_confidence.
    """

    feature_names: List[str] = field(default_factory=lambda: list(QUERY_FEATURE_NAMES))
    weights: List[float] = field(default_factory=list)
    bias: float = 0.0
    means: List[float] = field(default_factory=list)
    stds: List[float] = field(default_factory=list)
    fitted: bool = False

    def fit(
        self,
        feature_dicts: Sequence[Dict[str, float]],
        labels: Sequence[int],
        l2: float = 0.05,
        lr: float = 0.1,
        steps: int = 1000,
    ) -> "LogisticFeatureCalibrator":
        if not feature_dicts:
            return self
        X = np.array(
            [[float(d.get(name, 0.0)) for name in self.feature_names] for d in feature_dicts],
            dtype=np.float64,
        )
        y = np.asarray(labels, dtype=np.float64)
        means = np.mean(X, axis=0)
        stds = np.where(np.std(X, axis=0) > 1e-6, np.std(X, axis=0), 1.0)
        Xn = (X - means) / stds

        w = np.zeros(Xn.shape[1], dtype=np.float64)
        b = float(np.log(np.clip(np.mean(y), 0.05, 0.95) / (1.0 - np.clip(np.mean(y), 0.05, 0.95))))
        for _ in range(steps):
            p = _sigmoid_arr(Xn @ w + b)
            err = p - y
            grad_w = (Xn.T @ err) / len(y) + l2 * w
            grad_b = float(np.mean(err))
            w -= lr * grad_w
            b -= lr * grad_b

        self.means = [round(float(v), 6) for v in means]
        self.stds = [round(float(v), 6) for v in stds]
        self.weights = [round(float(v), 6) for v in w]
        self.bias = round(float(b), 6)
        self.fitted = True
        return self

    def predict_proba_one(self, feature_dict: Dict[str, float]) -> float:
        if not self.fitted:
            # Safe fallback if calibrator not yet fitted
            z = float(feature_dict.get("top1_logit", 0.0))
            return float(_sigmoid_arr(np.array([z]))[0])
        x = np.array([float(feature_dict.get(name, 0.0)) for name in self.feature_names], dtype=np.float64)
        xn = (x - np.asarray(self.means)) / np.asarray(self.stds)
        return float(_sigmoid_arr(np.array([float(xn @ np.asarray(self.weights) + self.bias)]))[0])

    def predict_proba(self, feature_dicts: Sequence[Dict[str, float]]) -> np.ndarray:
        return np.array([self.predict_proba_one(d) for d in feature_dicts], dtype=np.float64)


@dataclass
class CalibrationBundle:
    """Stores the three independent calibrated models + selective thresholds."""

    relevance_calibrator: ScalarLogitCalibrator = field(default_factory=ScalarLogitCalibrator)
    chapter_calibrator: LogisticFeatureCalibrator = field(default_factory=LogisticFeatureCalibrator)
    hsn_calibrator: LogisticFeatureCalibrator = field(default_factory=LogisticFeatureCalibrator)
    tau_abstain: float = 0.45
    tau_chapter: float = 0.70
    tau_exact_hsn: float = 0.65
    metadata: Dict[str, Any] = field(default_factory=dict)

    def save(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "relevance_calibrator": asdict(self.relevance_calibrator),
            "chapter_calibrator": asdict(self.chapter_calibrator),
            "hsn_calibrator": asdict(self.hsn_calibrator),
            "tau_abstain": self.tau_abstain,
            "tau_chapter": self.tau_chapter,
            "tau_exact_hsn": self.tau_exact_hsn,
            "metadata": self.metadata,
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path) -> "CalibrationBundle":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            relevance_calibrator=ScalarLogitCalibrator(**data["relevance_calibrator"]),
            chapter_calibrator=LogisticFeatureCalibrator(**data["chapter_calibrator"]),
            hsn_calibrator=LogisticFeatureCalibrator(**data["hsn_calibrator"]),
            tau_abstain=float(data.get("tau_abstain", 0.45)),
            tau_chapter=float(data.get("tau_chapter", 0.70)),
            tau_exact_hsn=float(data.get("tau_exact_hsn", 0.65)),
            metadata=data.get("metadata", {}),
        )

