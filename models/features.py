from typing import Dict, List, Any, Optional
import numpy as np
from domain.enums import FailureCode, CustomerSegment, ChannelPreference, ActionType, PromiseState
from domain.models import ObservableCaseState

# Forbidden leakage keywords that must NEVER enter feature matrix X
FORBIDDEN_FEATURE_PATTERNS = [
    "latent",
    "potential",
    "counterfactual",
    "y_control",
    "y_reminder",
    "y_payment_link",
    "y_promise_to_pay",
    "y_escalate",
    "recovered_amount",
    "recovery_timestamp",
    "final_state",
    "ground_truth",
    "scenario",
    "future",
    "case_id",
    "payment_id",
    "customer_id",
]

FEATURE_METADATA: Dict[str, Dict[str, Any]] = {
    "amount_due": {"source": "Payment", "available_at": "payment_failure", "allowed": True},
    "residual_amount": {"source": "RecoveryCase", "available_at": "case_creation", "allowed": True},
    "hours_since_failure": {"source": "RecoveryCase", "available_at": "decision_time", "allowed": True},
    "attempt_count": {"source": "PaymentAttempt", "available_at": "decision_time", "allowed": True},
    "automated_action_count": {"source": "RecoveryCase", "available_at": "decision_time", "allowed": True},
    "last_action_hours_ago": {"source": "RecoveryAction", "available_at": "decision_time", "allowed": True},
}

class FeaturePipeline:
    """
    STRICT OBSERVABLE FEATURE EXTRACTION PIPELINE.
    Transforms an ObservableCaseState into an immutable numeric feature vector.
    Enforces that zero latent, future, or counterfactual attributes can enter the model.
    """
    def __init__(self):
        self.schema_version = "features-v1"
        self._build_feature_index()

    def _build_feature_index(self):
        self.numeric_names = [
            "amount_due",
            "residual_amount",
            "hours_since_failure",
            "attempt_count",
            "automated_action_count",
            "last_action_hours_ago",
        ]
        
        self.failure_codes = [fc.value for fc in FailureCode]
        self.segments = [seg.value for seg in CustomerSegment]
        self.channels = [chan.value for chan in ChannelPreference]
        self.last_actions = ["NONE"] + [act.value for act in ActionType if act != ActionType.STOP]
        self.promise_statuses = ["NONE", "PROMISE_PROPOSED", "PROMISE_ACCEPTED", "PROMISE_DUE"]

        self.feature_names: List[str] = list(self.numeric_names)
        for fc in self.failure_codes:
            self.feature_names.append(f"fail_{fc}")
        for seg in self.segments:
            self.feature_names.append(f"seg_{seg}")
        for chan in self.channels:
            self.feature_names.append(f"chan_{chan}")
        for act in self.last_actions:
            self.feature_names.append(f"last_act_{act}")
        for ps in self.promise_statuses:
            self.feature_names.append(f"p2p_{ps}")

        self._audit_feature_names()

    def _audit_feature_names(self):
        """Audits feature names against the forbidden leakage barrier."""
        for fn in self.feature_names:
            lower = fn.lower()
            for forbidden in FORBIDDEN_FEATURE_PATTERNS:
                if forbidden in lower:
                    raise ValueError(f"LEAKAGE AUDIT FAILURE: Feature name '{fn}' violates forbidden term '{forbidden}'")

    def get_feature_names(self) -> List[str]:
        return list(self.feature_names)

    def extract_features(self, state: ObservableCaseState) -> np.ndarray:
        """
        Extracts the 1D numeric feature vector for a single ObservableCaseState.
        Guarantees deterministic ordering and zero leakage.
        """
        if not isinstance(state, ObservableCaseState):
            raise TypeError(f"FeaturePipeline only accepts ObservableCaseState, got {type(state)}")

        features = []

        # 1. Numeric features (imputed cleanly if None)
        features.append(float(state.amount_due))
        features.append(float(state.residual_amount))
        features.append(float(state.hours_since_failure))
        features.append(float(state.attempt_count))
        features.append(float(state.automated_action_count))
        # Impute missing last_action_hours_ago with -1.0 (indicating no prior action)
        features.append(float(state.last_action_hours_ago if state.last_action_hours_ago is not None else -1.0))

        # 2. Failure code one-hot
        current_fc = state.failure_code.value
        for fc in self.failure_codes:
            features.append(1.0 if current_fc == fc else 0.0)

        # 3. Customer segment one-hot
        current_seg = state.customer_segment.value
        for seg in self.segments:
            features.append(1.0 if current_seg == seg else 0.0)

        # 4. Channel preference one-hot
        current_chan = state.customer_channel_preference.value
        for chan in self.channels:
            features.append(1.0 if current_chan == chan else 0.0)

        # 5. Last action type one-hot
        current_last_act = state.last_action_type.value if state.last_action_type else "NONE"
        for act in self.last_actions:
            features.append(1.0 if current_last_act == act else 0.0)

        # 6. Active promise status one-hot
        current_ps = state.active_promise_status.value if state.active_promise_status else "NONE"
        for ps in self.promise_statuses:
            features.append(1.0 if current_ps == ps else 0.0)

        return np.array(features, dtype=np.float32)

    def extract_batch(self, states: List[ObservableCaseState]) -> np.ndarray:
        return np.array([self.extract_features(s) for s in states], dtype=np.float32)
