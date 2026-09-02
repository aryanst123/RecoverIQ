from typing import List, Dict, Any, Tuple
import numpy as np
from datetime import datetime, timezone

from domain.enums import ActionType
from domain.models import ObservableCaseState, PotentialOutcome
from simulator.environment import SimulationEnvironment
from policy.adaptive import RecoverIQAdaptivePolicy

class OracleCounterfactualDiagnostic:
    """
    SIMULATOR-ONLY ORACLE DIAGNOSTIC (OFFLINE EVALUATION ONLY).
    Compares RecoverIQ's chosen policy action against the hidden counterfactual oracle
    to assess policy regret:
    regret = Net_oracle - Net_selected
    STRICT BARRIER: This oracle accesses hidden PotentialOutcome and is strictly isolated
    from the policy execution and benchmark decision paths.
    """
    def __init__(self, policy: RecoverIQAdaptivePolicy):
        self.policy = policy
        self.action_costs = policy._action_costs
        self.friction_per_action = policy.eligibility_service.friction_per_action
        self.friction_cap = policy.eligibility_service.friction_cap

    def calculate_counterfactual_net(
        self,
        action: ActionType,
        hidden: PotentialOutcome,
        amount: float,
        action_count: int,
    ) -> float:
        """Computes ground truth net recovery for a specific action under hidden counterfactuals."""
        friction = min(action_count * self.friction_per_action, self.friction_cap)
        cost = self.action_costs.get(action, 0.0)

        if action == ActionType.STOP:
            # STOP gets natural control recovery with 0 action cost and 0 friction
            recovered = hidden.y_control
            return float(amount if recovered else 0.0)
        elif action == ActionType.REMINDER:
            recovered = hidden.y_reminder
        elif action == ActionType.PAYMENT_LINK:
            recovered = hidden.y_payment_link
        elif action == ActionType.PROMISE_TO_PAY:
            recovered = hidden.y_promise_to_pay
        elif action == ActionType.ESCALATE:
            recovered = hidden.y_escalate
        else:
            recovered = False

        gross = amount if recovered else 0.0
        return float(gross - cost - friction)

    def evaluate_policy_regret(
        self,
        cases_cohort: List[Tuple[Any, Any, Any, Any, PotentialOutcome]],
        env: SimulationEnvironment,
    ) -> Dict[str, Any]:
        candidate_actions = [
            ActionType.STOP,
            ActionType.REMINDER,
            ActionType.PAYMENT_LINK,
            ActionType.PROMISE_TO_PAY,
            ActionType.ESCALATE,
        ]

        oracle_matches = 0
        regrets = []
        action_counts = {act.value: 0 for act in candidate_actions}
        oracle_action_counts = {act.value: 0 for act in candidate_actions}

        for cust, pay, att, case, hidden in cases_cohort:
            obs_state = env.get_observable_state(case.case_id, current_time=att.attempted_at)
            eligible_actions = self.policy.eligibility_service.get_eligible_actions(obs_state)
            
            decision = self.policy.evaluate_case(obs_state, decision_time=att.attempted_at)
            selected_action = decision.selected_action
            action_counts[selected_action.value] += 1

            # Compute true counterfactual net for all eligible actions
            true_nets = {}
            for act in eligible_actions:
                true_nets[act] = self.calculate_counterfactual_net(
                    action=act,
                    hidden=hidden,
                    amount=case.amount_due,
                    action_count=case.automated_action_count,
                )

            # Oracle selects the eligible action with the maximum true net recovery
            best_action = max(eligible_actions, key=lambda a: true_nets[a])
            oracle_action_counts[best_action.value] += 1

            # Exact Per-Case Regret:
            # policy_value = true counterfactual net of policy's selected action
            # oracle_value = true counterfactual net of oracle's chosen optimal action
            # regret = max(0.0, oracle_value - policy_value)
            selected_net = true_nets[selected_action]
            best_net = true_nets[best_action]
            regret = max(0.0, best_net - selected_net)
            regrets.append(regret)

            if selected_action == best_action:
                oracle_matches += 1

        total = len(cases_cohort)
        agreement_rate = float(oracle_matches / total) if total > 0 else 0.0
        mean_regret = float(np.mean(regrets)) if total > 0 else 0.0

        return {
            "diagnostic_type": "SIMULATOR-ONLY ORACLE DIAGNOSTIC",
            "cohort_size": total,
            "oracle_agreement_rate": agreement_rate,
            "mean_regret_per_case": mean_regret,
            "policy_action_distribution": {k: float(v / total) for k, v in action_counts.items()},
            "oracle_action_distribution": {k: float(v / total) for k, v in oracle_action_counts.items()},
        }
