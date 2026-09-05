import os
import sys
import json
import yaml
import hashlib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.calibration import CalibratedClassifierCV

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from domain.enums import ActionType
from models.features import FeaturePipeline
from models.dataset import DatasetBuilder
from models.calibration import evaluate_calibration
from models.artifacts import ModelArtifactManager

def train_and_persist_model_v3(
    train_size: int = 10000,
    train_seed: int = 42,
    scenario_id: str = "S1_HIGH_NATURAL_RECOVERY",
):
    print("=" * 70, flush=True)
    print("TRAINING AND SERIALIZING INCREMENTAL-MODEL-V3", flush=True)
    print("=" * 70, flush=True)

    feature_pipeline = FeaturePipeline()
    feature_names = feature_pipeline.get_feature_names()
    actions = ["CONTROL", "REMINDER", "PAYMENT_LINK", "PROMISE_TO_PAY", "ESCALATE"]

    # 1. Build Training Dataset
    print(f"Generating Training Dataset (N={train_size}, Seed={train_seed}, Scenario={scenario_id})...", flush=True)
    db = DatasetBuilder(feature_pipeline=feature_pipeline)
    train_split = db.build_dataset(count=train_size, seed=train_seed, scenario_id=scenario_id)

    # 2. Build Validation Dataset for Calibration Verification
    val_split = db.build_dataset(count=2000, seed=train_seed + 1000, scenario_id=scenario_id)

    X_train = train_split.X
    A_train = np.array(train_split.A)
    Y_train = train_split.Y.astype(int)

    trained_models = {}
    calib_reports = {}

    for act in actions:
        print(f"Fitting calibrated classifier for arm: {act}...", flush=True)
        mask_train = (A_train == act)
        X_act = X_train[mask_train]
        Y_act = Y_train[mask_train]

        # Use Scaler + LogisticRegression + Isotonic Calibration
        base_pipe = Pipeline([
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(C=0.5, max_iter=1000, random_state=train_seed, solver="lbfgs"))
        ])

        calibrated_clf = CalibratedClassifierCV(estimator=base_pipe, method="isotonic", cv=3)
        calibrated_clf.fit(X_act, Y_act)
        trained_models[act] = calibrated_clf

        # Evaluate calibration on val split
        mask_val = np.array([a == act for a in val_split.A])
        if np.sum(mask_val) > 0:
            y_val_prob = calibrated_clf.predict_proba(val_split.X[mask_val])[:, 1]
            cal_rep = evaluate_calibration(
                y_true=val_split.Y[mask_val],
                y_prob=y_val_prob,
                action_name=act
            )
            calib_reports[act] = cal_rep
            bias = cal_rep.mean_predicted_prob - cal_rep.observed_rate
            print(f"  [{act}] Brier: {cal_rep.brier_score:.4f}, MeanPred: {cal_rep.mean_predicted_prob:.3f}, ObsRate: {cal_rep.observed_rate:.3f}, Bias: {bias:+.4f}")

    # 3. Persist via ModelArtifactManager
    mgr = ModelArtifactManager()
    cfg_str = json.dumps({"scenario": scenario_id, "model": "calibrated_t_learner", "method": "isotonic", "C": 0.5})
    config_hash = hashlib.sha256(cfg_str.encode()).hexdigest()

    saved_path = mgr.save_model(
        models=trained_models,
        model_version="incremental-model-v3",
        feature_schema_version="features-v1",
        dataset_hash=train_split.dataset_hash,
        config_hash=config_hash,
        calibration_reports=calib_reports,
        feature_names=feature_names,
    )
    print(f"\nModel incremental-model-v3 successfully saved to: {saved_path}", flush=True)
    return saved_path

if __name__ == "__main__":
    train_and_persist_model_v3()
