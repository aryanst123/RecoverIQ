from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
import numpy as np

from domain.enums import ActionType
from domain.models import ObservableCaseState
from models.features import FeaturePipeline

@dataclass
class ActionPrediction:
    action: ActionType
    action_probability: float
    incremental_probability: float # tau(a, x) = P(Y=1|a,x) - P(Y=1|control,x)
    expected_incremental_revenue: float # tau(a, x) * residual_amount

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["action"] = self.action.value
        return d

@dataclass
class IncrementalPredictionResult:
    case_id: str
    control_probability: float
    actions: Dict[str, ActionPrediction]
    model_version: str
    feature_schema_version: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "control_probability": self.control_probability,
            "actions": {k: v.to_dict() for k, v in self.actions.items()},
            "model_version": self.model_version,
            "feature_schema_version": self.feature_schema_version,
        }

class IncrementalRecoveryModel:
    """
    T-LEARNER INCREMENTAL RECOVERY MODEL.
    Consumes ObservableCaseState, predicts P(Y=1 | a, x) and P(Y=1 | control, x),
    and derives the causal uplift tau(a, x) and expected incremental recovery value.
    Preserves negative treatment effects. Purely predictive with ZERO execution privileges.
    """
    def __init__(
        self,
        trained_models: Dict[str, Any],
        feature_pipeline: Optional[FeaturePipeline] = None,
        model_version: str = "incremental-model-v1",
        feature_schema_version: str = "features-v1",
    ):
        self.models = trained_models
        self.pipeline = feature_pipeline or FeaturePipeline()
        self.model_version = model_version
        self.feature_schema_version = feature_schema_version

    def predict_action_effects(self, state: ObservableCaseState) -> IncrementalPredictionResult:
        """
        Estimates action-specific incremental uplift for an observable case.
        """
        if not isinstance(state, ObservableCaseState):
            raise TypeError(f"IncrementalRecoveryModel only accepts ObservableCaseState, got {type(state)}")

        # Extract 1D feature vector
        x = self.pipeline.extract_features(state).reshape(1, -1)

        # 1. Predict P(Y=1 | control, x)
        control_model = self.models.get("CONTROL")
        if control_model is not None:
            p_control = float(control_model.predict_proba(x)[0, 1])
        else:
            p_control = 0.50 # Fallback uninformative prior if model missing

        action_predictions: Dict[str, ActionPrediction] = {}
        eval_actions = [
            ActionType.REMINDER,
            ActionType.PAYMENT_LINK,
            ActionType.PROMISE_TO_PAY,
            ActionType.ESCALATE,
        ]

        for act in eval_actions:
            model = self.models.get(act.value)
            if model is not None:
                p_act = float(model.predict_proba(x)[0, 1])
            else:
                p_act = p_control

            # Incremental effect: tau(a, x) = P(Y=1|a, x) - P(Y=1|control, x)
            # CRITICAL: Preserve negative effects! Do not clip to 0.
            delta_p = p_act - p_control
            expected_inc_rev = float(delta_p * state.residual_amount)

            action_predictions[act.value] = ActionPrediction(
                action=act,
                action_probability=p_act,
                incremental_probability=delta_p,
                expected_incremental_revenue=expected_inc_rev,
            )

        return IncrementalPredictionResult(
            case_id=state.case_id,
            control_probability=p_control,
            actions=action_predictions,
            model_version=self.model_version,
            feature_schema_version=self.feature_schema_version,
        )
