import hashlib
import json
import os
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import Dict, Any

def compute_file_checksum(filepath: str) -> str:
    """Computes SHA-256 checksum of a file on disk."""
    if not os.path.exists(filepath):
        return "file_not_found"
    with open(filepath, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()

@dataclass
class ExperimentManifest:
    experiment_id: str
    experiment_name: str
    timestamp: str
    seed: int
    dataset_size: int
    scenario_id: str
    simulator_version: str
    baseline_version: str
    baseline_checksum: str
    recoveriq_version: str
    attribution_window_hours: int
    config_checksums: Dict[str, str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

def create_experiment_manifest(
    experiment_id: str,
    experiment_name: str,
    seed: int,
    dataset_size: int,
    scenario_id: str,
    baseline_version: str,
    baseline_checksum: str,
    recoveriq_version: str = "recoveriq-v0-placeholder",
    attribution_window_hours: int = 72,
    config_paths: Dict[str, str] = None,
) -> ExperimentManifest:
    if config_paths is None:
        config_paths = {
            "contract": "configs/experiment_contract.yaml",
            "costs": "configs/costs.yaml",
            "policy": "configs/policy.yaml",
            "simulator": "configs/simulator.yaml",
            "evaluation": "configs/evaluation.yaml",
        }

    checksums = {k: compute_file_checksum(v) for k, v in config_paths.items()}

    return ExperimentManifest(
        experiment_id=experiment_id,
        experiment_name=experiment_name,
        timestamp=datetime.now(timezone.utc).isoformat(),
        seed=seed,
        dataset_size=dataset_size,
        scenario_id=scenario_id,
        simulator_version="1.0.0",
        baseline_version=baseline_version,
        baseline_checksum=baseline_checksum,
        recoveriq_version=recoveriq_version,
        attribution_window_hours=attribution_window_hours,
        config_checksums=checksums,
    )
