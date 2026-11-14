"""
Unit tests for Phase 4: ModelRegistry and threshold calibration.
"""

import numpy as np

from src.ml.model_registry import ModelRegistry
from src.training.evaluation_pipeline import calibrate_threshold


def test_model_registry_register_and_promote(tmp_path):
    reg = ModelRegistry(versions_dir=tmp_path)
    assert reg.get_active_model_path() is None

    reg.register_version(
        version_id="v1",
        model_path=str(tmp_path / "v1"),
        base_model="cross-encoder/ms-marco-MiniLM-L-6-v2",
        metrics={"roc_auc": 0.91},
        calibrated_threshold=0.55,
        promote=True,
    )
    assert reg.get_active_model_path() == str(tmp_path / "v1")
    assert reg.get_active_entry()["calibrated_threshold"] == 0.55
    assert len(reg.list_versions()) == 1


def test_calibrate_threshold_finds_optimal_split():
    y_true = np.array([1, 1, 1, 0, 0, 0])
    probs = np.array([0.85, 0.72, 0.65, 0.40, 0.25, 0.15])
    thresh, stats = calibrate_threshold(y_true, probs)
    assert 0.40 < thresh <= 0.65
    assert stats["f1"] == 1.0
    assert stats["accuracy"] == 1.0

