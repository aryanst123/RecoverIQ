import hashlib
import json
from dataclasses import dataclass, asdict
from typing import Dict
import yaml

from domain.enums import ActionType

@dataclass(frozen=True)
class BaselineConfig:
    version: str = "baseline-v1"
    recovery_window_hours: float = 720.0 # 30 days
    max_automated_actions: int = 3
    min_cooldown_hours: float = 12.0
    min_amount_for_escalate: float = 1500.0
    min_amount_for_p2p: float = 250.0
    
    # Action costs (experimental simulation parameters)
    cost_reminder: float = 2.0
    cost_payment_link: float = 3.0
    cost_promise_to_pay: float = 5.0
    cost_escalate: float = 100.0
    
    # Friction parameters
    friction_per_action: float = 5.0
    friction_cap: float = 25.0

    def get_action_cost(self, action: ActionType) -> float:
        mapping = {
            ActionType.REMINDER: self.cost_reminder,
            ActionType.PAYMENT_LINK: self.cost_payment_link,
            ActionType.PROMISE_TO_PAY: self.cost_promise_to_pay,
            ActionType.ESCALATE: self.cost_escalate,
            ActionType.STOP: 0.0,
        }
        return mapping.get(action, 0.0)

    def calculate_friction(self, automated_action_count: int) -> float:
        return min(automated_action_count * self.friction_per_action, self.friction_cap)

    def get_checksum(self) -> str:
        """Returns a deterministic SHA256 checksum of the baseline configuration."""
        data = asdict(self)
        canonical = json.dumps(data, sort_keys=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

def load_baseline_config(
    policy_path: str = "configs/policy.yaml",
    costs_path: str = "configs/costs.yaml",
) -> BaselineConfig:
    """Loads shared policy and cost parameters to ensure symmetry."""
    try:
        with open(policy_path, "r") as f:
            p_cfg = yaml.safe_load(f).get("safety", {})
        with open(costs_path, "r") as f:
            c_cfg = yaml.safe_load(f)

        action_costs = c_cfg.get("action_costs", {})
        friction_costs = c_cfg.get("friction_costs", {})

        return BaselineConfig(
            version="baseline-v1",
            recovery_window_hours=float(p_cfg.get("recovery_window_days", 30)) * 24.0,
            max_automated_actions=int(p_cfg.get("max_automated_actions", 3)),
            min_cooldown_hours=float(p_cfg.get("min_cooldown_hours_between_actions", 12.0)),
            min_amount_for_escalate=1500.0,
            min_amount_for_p2p=float(p_cfg.get("minimum_expected_incremental_recovery", 250.0)),
            cost_reminder=float(action_costs.get("REMINDER", 2.0)),
            cost_payment_link=float(action_costs.get("PAYMENT_LINK", 3.0)),
            cost_promise_to_pay=float(action_costs.get("PROMISE_TO_PAY", 5.0)),
            cost_escalate=float(action_costs.get("ESCALATE", 100.0)),
            friction_per_action=float(friction_costs.get("per_previous_automated_action", 5.0)),
            friction_cap=float(friction_costs.get("cap", 25.0)),
        )
    except Exception:
        # Fallback to default canonical config if file load fails
        return BaselineConfig()
