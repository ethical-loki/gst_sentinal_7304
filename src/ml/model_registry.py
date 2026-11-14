"""
src/ml/model_registry.py
========================
Phase 4 / 6: Model Version Registry for Product-to-Tariff Rerankers.

Tracks trained Cross-Encoder checkpoints, validation metrics, calibrated
decision thresholds, and the currently promoted production model version.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_MODEL_VERSIONS_DIR = ROOT_DIR / "data" / "model_versions"


class ModelRegistry:
    """Manages versioned reranker models and calibrated thresholds."""

    def __init__(self, versions_dir: Path = DEFAULT_MODEL_VERSIONS_DIR):
        self.versions_dir = Path(versions_dir)
        self.versions_dir.mkdir(parents=True, exist_ok=True)
        self.registry_file = self.versions_dir / "registry.json"
        self._data = self._load()

    def _load(self) -> Dict[str, Any]:
        if self.registry_file.exists():
            with open(self.registry_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"active_version": None, "versions": {}}

    def _save(self) -> None:
        with open(self.registry_file, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)

    def register_version(
        self,
        version_id: str,
        model_path: str,
        base_model: str,
        metrics: Dict[str, Any],
        calibrated_threshold: float = 0.5,
        promote: bool = True,
    ) -> Dict[str, Any]:
        entry = {
            "version_id": version_id,
            "model_path": str(model_path),
            "base_model": base_model,
            "calibrated_threshold": float(calibrated_threshold),
            "metrics": metrics,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._data["versions"][version_id] = entry
        if promote or self._data.get("active_version") is None:
            self._data["active_version"] = version_id
        self._save()
        logger.info(f"Registered model version '{version_id}' (active={self._data['active_version']})")
        return entry

    def get_active_entry(self) -> Optional[Dict[str, Any]]:
        active_id = self._data.get("active_version")
        if not active_id:
            return None
        return self._data["versions"].get(active_id)

    def get_active_model_path(self) -> Optional[str]:
        entry = self.get_active_entry()
        return entry["model_path"] if entry else None

    def list_versions(self) -> List[Dict[str, Any]]:
        return list(self._data.get("versions", {}).values())

