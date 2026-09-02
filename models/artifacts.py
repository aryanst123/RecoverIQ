import os
import json
import pickle
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from dataclasses import asdict

from models.calibration import ModelCalibrationReport
from models.incremental_recovery import IncrementalRecoveryModel

class ModelArtifactManager:
    """
    Persists and loads trained incremental recovery models along with complete provenance metadata.
    """
    def __init__(self, artifact_dir: str = "artifacts/models"):
        self.artifact_dir = artifact_dir
        os.makedirs(artifact_dir, exist_ok=True)

    def save_model(
        self,
        models: Dict[str, Any],
        model_version: str,
        feature_schema_version: str,
        dataset_hash: str,
        config_hash: str,
        calibration_reports: Dict[str, ModelCalibrationReport],
        feature_names: list,
    ) -> str:
        version_dir = os.path.join(self.artifact_dir, model_version)
        os.makedirs(version_dir, exist_ok=True)

        # 1. Save binary models
        models_path = os.path.join(version_dir, "models.pkl")
        with open(models_path, "wb") as f:
            pickle.dump({"models": models, "feature_names": feature_names}, f)

        # 2. Save metadata JSON
        metadata = {
            "model_version": model_version,
            "feature_schema_version": feature_schema_version,
            "dataset_hash": dataset_hash,
            "config_hash": config_hash,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "calibration": {k: asdict(v) for k, v in calibration_reports.items()},
            "feature_count": len(feature_names),
        }
        meta_path = os.path.join(version_dir, "metadata.json")
        with open(meta_path, "w") as f:
            json.dump(metadata, f, indent=2)

        return version_dir

    def load_model(self, model_version: str) -> IncrementalRecoveryModel:
        version_dir = os.path.join(self.artifact_dir, model_version)
        models_path = os.path.join(version_dir, "models.pkl")
        meta_path = os.path.join(version_dir, "metadata.json")

        if not os.path.exists(models_path) or not os.path.exists(meta_path):
            raise FileNotFoundError(f"Model artifacts for version {model_version} not found in {version_dir}")

        with open(models_path, "rb") as f:
            data = pickle.load(f)

        with open(meta_path, "r") as f:
            meta = json.load(f)

        return IncrementalRecoveryModel(
            trained_models=data["models"],
            model_version=meta.get("model_version", model_version),
            feature_schema_version=meta.get("feature_schema_version", "features-v1"),
        )
