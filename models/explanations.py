from typing import Dict, List, Any, Tuple
import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression

class ModelExplanationService:
    """
    Interprets underlying logistic regression weights and identifies top feature drivers
    for each recovery action without using an LLM.
    """
    def __init__(self, trained_models: Dict[str, Any], feature_names: List[str]):
        self.models = trained_models
        self.feature_names = feature_names

    def get_action_coefficients(self, action_name: str) -> List[Tuple[str, float]]:
        """
        Extracts feature names and their corresponding logistic regression coefficients.
        """
        model = self.models.get(action_name)
        if model is None:
            return []

        # Handle CalibratedClassifierCV wrapper or direct Pipeline
        estimator = model
        if isinstance(model, CalibratedClassifierCV):
            # Extract underlying calibrated classifier
            if hasattr(model, "calibrated_classifiers_") and len(model.calibrated_classifiers_) > 0:
                first_cal = model.calibrated_classifiers_[0]
                if hasattr(first_cal, "estimator"):
                    estimator = first_cal.estimator
            elif hasattr(model, "estimator"):
                estimator = model.estimator

        # Extract classifier from Pipeline if present
        clf = estimator
        if hasattr(estimator, "named_steps"):
            clf = estimator.named_steps.get("clf", estimator)

        if not hasattr(clf, "coef_"):
            return []

        coefs = clf.coef_[0]
        results = []
        for fn, c in zip(self.feature_names, coefs):
            results.append((fn, float(c)))

        # Sort by absolute magnitude descending
        results.sort(key=lambda x: abs(x[1]), reverse=True)
        return results

    def get_top_drivers(self, action_name: str, top_k: int = 5) -> Dict[str, List[Tuple[str, float]]]:
        """
        Returns top positive and top negative feature drivers for an action.
        """
        coefs = self.get_action_coefficients(action_name)
        positive = [c for c in coefs if c[1] > 0]
        negative = [c for c in coefs if c[1] < 0]

        return {
            "top_positive_drivers": positive[:top_k],
            "top_negative_drivers": sorted(negative, key=lambda x: x[1])[:top_k],
        }
