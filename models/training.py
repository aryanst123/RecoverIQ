import hashlib
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple
import numpy as np
import yaml
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.calibration import CalibratedClassifierCV

from domain.enums import ActionType
from models.dataset import DatasetSplit
from models.calibration import ModelCalibrationReport, evaluate_calibration

class TLearnerTrainer:
    """
    Trains treatment-specific models (T-Learner architecture):
    Separate calibrated probability models for:
    P(Y=1 | X, A=control)
    P(Y=1 | X, A=reminder)
    P(Y=1 | X, A=payment_link)
    P(Y=1 | X, A=promise_to_pay)
    P(Y=1 | X, A=escalate)
    """
    def __init__(
        self,
        config_path: str = "configs/model.yaml",
        random_seed: int = 42,
    ):
        self.config_path = config_path
        self.random_seed = random_seed
        self._load_config(config_path)

    def _load_config(self, path: str):
        try:
            with open(path, "r") as f:
                self.config = yaml.safe_load(f)
        except Exception:
            self.config = {
                "version": "incremental-model-v1",
                "hyperparameters": {"max_iter": 1000, "C": 1.0, "class_weight": "balanced"},
            }
        self.version = self.config.get("version", "incremental-model-v1")
        self.hyperparams = self.config.get("hyperparameters", {})

    def train_t_learner(
        self,
        train_data: DatasetSplit,
        val_data: Optional[DatasetSplit] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, ModelCalibrationReport]]:
        """
        Fits separate calibrated probability estimators for each action arm.
        Returns: (trained_models_dict, validation_calibration_reports).
        """
        actions = ["CONTROL", "REMINDER", "PAYMENT_LINK", "PROMISE_TO_PAY", "ESCALATE"]
        models: Dict[str, Any] = {}
        calibration_reports: Dict[str, ModelCalibrationReport] = {}

        for act in actions:
            train_mask = np.array([a == act for a in train_data.A])
            X_act = train_data.X[train_mask]
            Y_act = train_data.Y[train_mask]

            if len(X_act) == 0:
                continue

            # Standard pipeline: Scaler + LogisticRegression
            base_model = Pipeline([
                ("scaler", StandardScaler()),
                ("clf", LogisticRegression(
                    max_iter=int(self.hyperparams.get("max_iter", 1000)),
                    C=float(self.hyperparams.get("C", 1.0)),
                    solver=self.hyperparams.get("solver", "lbfgs"),
                    class_weight=self.hyperparams.get("class_weight", "balanced"),
                    random_state=self.random_seed,
                ))
            ])

            # Check if both classes are present in training split
            if len(np.unique(Y_act)) > 1:
                # Use CalibratedClassifierCV with sigmoid (Platt scaling) for calibrated probabilities
                calibrated_model = CalibratedClassifierCV(
                    estimator=base_model,
                    method="sigmoid",
                    cv=3 if len(X_act) >= 30 else "prefit",
                )
                if len(X_act) >= 30:
                    calibrated_model.fit(X_act, Y_act)
                else:
                    base_model.fit(X_act, Y_act)
                    calibrated_model = base_model
            else:
                base_model.fit(X_act, Y_act)
                calibrated_model = base_model

            models[act] = calibrated_model

            # Evaluate calibration on validation data if provided
            if val_data is not None:
                val_mask = np.array([a == act for a in val_data.A])
                X_val_act = val_data.X[val_mask]
                Y_val_act = val_data.Y[val_mask]

                if len(X_val_act) > 0:
                    val_probs = calibrated_model.predict_proba(X_val_act)[:, 1]
                    report = evaluate_calibration(Y_val_act, val_probs, action_name=act)
                    calibration_reports[act] = report

        return models, calibration_reports
