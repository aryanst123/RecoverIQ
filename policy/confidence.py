from typing import Dict, Any, Tuple
from domain.enums import ActionType
from domain.models import ObservableCaseState

class PolicyConfidenceService:
    """
    Evaluates policy confidence for action effect estimates.
    Does NOT use raw payment probability as confidence.
    Assesses:
    1. Training sample support per action
    2. Prediction margin away from random noise
    3. Observable feature bounds (out-of-distribution detection)
    """
    def __init__(
        self,
        low_confidence_threshold: float = 0.60,
        min_support_samples: int = 50,
    ):
        self.low_confidence_threshold = low_confidence_threshold
        self.min_support_samples = min_support_samples

    def evaluate_confidence(
        self,
        state: ObservableCaseState,
        action_type: ActionType,
        action_prob: float,
        control_prob: float,
        support_sample_count: int = 500,
    ) -> Tuple[float, str]:
        """
        Returns: (confidence_score in [0, 1], confidence_status).
        """
        # 1. Support Score: penalize if action had insufficient training samples
        if support_sample_count >= self.min_support_samples:
            support_score = 1.0
        else:
            support_score = max(0.1, support_sample_count / float(self.min_support_samples))

        # 2. Margin Score: certainty of distinction from pure 50/50 noise
        prob_margin = abs(action_prob - 0.50) * 2.0 # in [0, 1]
        delta_margin = min(1.0, abs(action_prob - control_prob) * 3.0) # uplift clarity
        model_certainty = 0.5 * prob_margin + 0.5 * delta_margin

        # 3. Domain Validity Score: checks for severe distribution anomalies
        if state.residual_amount <= 0.0 or state.hours_since_failure > 720.0:
            domain_score = 0.0
        elif state.residual_amount > 500000.0: # extreme outlier amount
            domain_score = 0.5
        else:
            domain_score = 1.0

        # Composite Policy Confidence Score
        confidence = float(0.4 * support_score + 0.3 * model_certainty + 0.3 * domain_score)
        confidence = max(0.0, min(1.0, confidence))

        if confidence < self.low_confidence_threshold:
            status = "LOW_CONFIDENCE"
        elif confidence >= 0.80:
            status = "HIGH_CONFIDENCE"
        else:
            status = "MODERATE_CONFIDENCE"

        return confidence, status
