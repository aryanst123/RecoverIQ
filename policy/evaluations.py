from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, List, Any, Optional
from domain.enums import ActionType

@dataclass
class ActionEvaluation:
    action: ActionType
    probability: float
    control_probability: float
    incremental_probability: float
    residual_amount: float
    expected_incremental_revenue: float
    action_cost: float
    friction_cost: float
    expected_net_recovery: float
    eligible: bool
    rejection_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["action"] = self.action.value
        return d

@dataclass
class DecisionTrace:
    case_id: str
    model_version: str
    policy_version: str
    candidate_evaluations: List[ActionEvaluation]
    selected_action: ActionType
    selection_reason: str
    constraints_applied: List[str]
    confidence_score: float
    confidence_status: str
    timestamp: datetime

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "model_version": self.model_version,
            "policy_version": self.policy_version,
            "candidate_evaluations": [e.to_dict() for e in self.candidate_evaluations],
            "selected_action": self.selected_action.value,
            "selection_reason": self.selection_reason,
            "constraints_applied": self.constraints_applied,
            "confidence_score": self.confidence_score,
            "confidence_status": self.confidence_status,
            "timestamp": self.timestamp.isoformat(),
        }
