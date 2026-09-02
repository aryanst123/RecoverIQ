from dataclasses import dataclass, asdict
from typing import List, Dict, Any
from domain.enums import ActionType

@dataclass(frozen=True)
class BaselineDecisionExplanation:
    selected_action: ActionType
    rules_triggered: List[str]
    rules_rejected: List[str]
    policy_version: str
    config_checksum: str
    decision_reason: str

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["selected_action"] = self.selected_action.value
        return d
