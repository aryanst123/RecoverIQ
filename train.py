import os
import yaml
import hashlib
import json
from datetime import datetime, timezone
from models.dataset import DatasetBuilder
from models.training import TLearnerTrainer
from models.artifacts import ModelArtifactManager
from models.incremental_recovery import IncrementalRecoveryModel
from models.diagnostics import SimulatorGroundTruthDiagnostic

def main():
    print("=" * 70)
    print("RECOVERIQ — INCREMENTAL RECOVERY MODEL TRAINING")
    print("=" * 70)

    # 1. Load Configurations
    with open("configs/model.yaml", "r") as f:
        model_cfg = yaml.safe_load(f)
    with open("configs/training.yaml", "r") as f:
        train_cfg = yaml.safe_load(f)

    cfg_hash = hashlib.sha256((json.dumps(model_cfg, sort_keys=True) + json.dumps(train_cfg, sort_keys=True)).encode()).hexdigest()

    dataset_size = train_cfg.get("dataset_size", 5000)
    seed = train_cfg.get("experiment_seed", 20260902)
    scenario_id = train_cfg.get("scenario", "S5_HIGH_RECOVERY_HETEROGENEITY")
    train_split_ratio = train_cfg.get("train_split_ratio", 0.70)

    print(f"Dataset Size:         {dataset_size:,} cases")
    print(f"Experiment Seed:      {seed}")
    print(f"Scenario:             {scenario_id}")
    print(f"Train/Val Split:      {int(train_split_ratio*100)}% / {int((1-train_split_ratio)*100)}%")

    # 2. Build Dataset (randomized micro-interventions across actions)
    print("\nBuilding dataset from observable states...")
    builder = DatasetBuilder()
    full_dataset = builder.build_dataset(count=dataset_size, seed=seed, scenario_id=scenario_id)
    train_split, val_split = builder.train_validation_split(full_dataset, train_ratio=train_split_ratio, seed=seed)

    print(f"Dataset Hash:         {full_dataset.dataset_hash}")
    print(f"Train Samples:        {len(train_split.X):,}")
    print(f"Validation Samples:   {len(val_split.X):,}")
    print(f"Features:             {len(full_dataset.feature_names)}")

    # 3. Fit T-Learner Models
    print("\nFitting T-Learner calibrated probability models...")
    trainer = TLearnerTrainer(config_path="configs/model.yaml", random_seed=seed)
    models, calibration_reports = trainer.train_t_learner(train_split, val_split)

    print("\n" + "=" * 70, flush=True)
    print("VALIDATION CALIBRATION & DISCRIMINATION REPORT", flush=True)
    print("=" * 70, flush=True)
    print(f"{'Action':<16} | {'Samples':<8} | {'Positives':<9} | {'Brier':<8} | {'Log Loss':<9} | {'ROC-AUC':<8} | {'PR-AUC':<8}", flush=True)
    print("-" * 76, flush=True)
    for act_name, rep in calibration_reports.items():
        print(f"{act_name:<16} | {rep.sample_count:<8} | {rep.positive_count:<9} | {rep.brier_score:<8.4f} | {rep.log_loss_value:<9.4f} | {rep.roc_auc:<8.3f} | {rep.pr_auc:<8.3f}", flush=True)

    # 4. Save Model Artifacts
    artifact_dir = train_cfg.get("artifacts", {}).get("model_dir", "artifacts/models")
    model_version = model_cfg.get("version", "incremental-model-v1")
    schema_version = model_cfg.get("features", {}).get("schema_version", "features-v1")

    manager = ModelArtifactManager(artifact_dir=artifact_dir)
    save_path = manager.save_model(
        models=models,
        model_version=model_version,
        feature_schema_version=schema_version,
        dataset_hash=full_dataset.dataset_hash,
        config_hash=cfg_hash,
        calibration_reports=calibration_reports,
        feature_names=full_dataset.feature_names,
    )
    print(f"\n[Artifact Saved] Model package persisted to: {save_path}", flush=True)

    # 5. Offline Diagnostic Check
    print("\nRunning offline simulator-only ground truth sanity check...", flush=True)
    inc_model = IncrementalRecoveryModel(trained_models=models, model_version=model_version)
    diag = SimulatorGroundTruthDiagnostic(model=inc_model)
    diag_results = diag.evaluate_directional_sanity(count=200, seed=seed+1, scenario_id=scenario_id)

    print("\n" + "=" * 70, flush=True)
    print("SIMULATOR-ONLY COUNTERFACTUAL GROUND-TRUTH DIAGNOSTIC (200 cases)", flush=True)
    print("=" * 70, flush=True)
    print(f"{'Action':<16} | {'Mean Est Uplift':<16} | {'Mean GT Uplift':<16} | {'Correlation':<12} | {'Direction Match'}", flush=True)
    print("-" * 76, flush=True)
    for act, res in diag_results["actions"].items():
        print(f"{act:<16} | {res['mean_estimated_uplift']:<+16.4f} | {res['mean_ground_truth_uplift']:<+16.4f} | {res['correlation']:<12.3f} | {res['directional_match']}", flush=True)

    print("\nTraining and validation complete.", flush=True)

if __name__ == "__main__":
    main()
