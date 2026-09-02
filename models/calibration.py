from dataclasses import dataclass
from typing import Dict, Any, List
import numpy as np
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score, average_precision_score

@dataclass
class ModelCalibrationReport:
    action_name: str
    sample_count: int
    positive_count: int
    brier_score: float
    log_loss_value: float
    roc_auc: float
    pr_auc: float
    mean_predicted_prob: float
    observed_rate: float

def evaluate_calibration(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    action_name: str,
) -> ModelCalibrationReport:
    """
    Computes rigorous probabilistic calibration metrics:
    Brier Score, Log Loss, ROC-AUC, and PR-AUC.
    """
    n = len(y_true)
    pos = int(np.sum(y_true))

    if n == 0:
        return ModelCalibrationReport(
            action_name=action_name,
            sample_count=0,
            positive_count=0,
            brier_score=0.0,
            log_loss_value=0.0,
            roc_auc=0.5,
            pr_auc=0.0,
            mean_predicted_prob=0.0,
            observed_rate=0.0,
        )

    brier = float(brier_score_loss(y_true, y_prob))
    
    # Bound probabilities away from 0 and 1 for numerical stability in log loss
    eps = 1e-15
    clipped_probs = np.clip(y_prob, eps, 1.0 - eps)
    ll = float(log_loss(y_true, clipped_probs, labels=[0, 1]))

    # ROC-AUC and PR-AUC require at least one positive and one negative sample
    if 0 < pos < n:
        auc = float(roc_auc_score(y_true, y_prob))
        pr_auc = float(average_precision_score(y_true, y_prob))
    else:
        auc = 0.5
        pr_auc = float(pos / n) if n > 0 else 0.0

    return ModelCalibrationReport(
        action_name=action_name,
        sample_count=n,
        positive_count=pos,
        brier_score=brier,
        log_loss_value=ll,
        roc_auc=auc,
        pr_auc=pr_auc,
        mean_predicted_prob=float(np.mean(y_prob)),
        observed_rate=float(pos / n),
    )
