from typing import Dict, List, Any, Tuple
import numpy as np

from domain.enums import ActionType
from domain.models import ObservableCaseState
from policy.adaptive import RecoverIQAdaptivePolicy
from policy.eligibility import CandidateActionService
from baseline.policy import DeterministicBaselinePolicy

class PolicyAblationHarness:
    """
    Evaluates offline policy variants to isolate the contribution of:
    - Incremental causal uplift (tau vs raw P)
    - Action costs and friction
    - Minimum threshold gating
    """
    def __init__(self, adaptive_policy: RecoverIQAdaptivePolicy, baseline_policy: DeterministicBaselinePolicy):
        self.policy = adaptive_policy
        self.baseline = baseline_policy
        self.eligibility = adaptive_policy.eligibility_service

    def run_ablations(self, states: List[ObservableCaseState]) -> Dict[str, Dict[str, float]]:
        total = len(states)
        if total == 0:
            return {}

        results = {
            "A_DETERMINISTIC_BASELINE": {act.value: 0 for act in ActionType},
            "B_UPLIFT_WITHOUT_COST": {act.value: 0 for act in ActionType},
            "C_RAW_PROBABILITY_WITH_COST": {act.value: 0 for act in ActionType},
            "D_UPLIFT_WITH_COST_NO_THRESHOLD": {act.value: 0 for act in ActionType},
            "E_FULL_RECOVERIQ_STANDARD": {act.value: 0 for act in ActionType},
        }

        for state in states:
            # Variant A: Baseline
            b_dec = self.baseline.evaluate(state)
            results["A_DETERMINISTIC_BASELINE"][b_dec.selected_action.value] += 1

            # Variant E: Full RecoverIQ Standard
            e_dec = self.policy.evaluate_case(state)
            results["E_FULL_RECOVERIQ_STANDARD"][e_dec.selected_action.value] += 1

            # Obtain model predictions
            pred = self.policy.model.predict_action_effects(state)
            shared_eligible = set(self.eligibility.get_eligible_actions(state))
            friction = self.eligibility.calculate_friction(state.automated_action_count)

            # Variant B: Uplift without Cost (argmax tau)
            best_tau_act = ActionType.STOP
            best_tau = 0.0
            for act in [ActionType.REMINDER, ActionType.PAYMENT_LINK, ActionType.PROMISE_TO_PAY, ActionType.ESCALATE]:
                if act in shared_eligible:
                    tau = pred.actions[act.value].incremental_probability
                    if tau > best_tau:
                        best_tau = tau
                        best_tau_act = act
            results["B_UPLIFT_WITHOUT_COST"][best_tau_act.value] += 1

            # Variant C: Raw Probability with Cost (P(Y|a) * amount - cost)
            best_raw_act = ActionType.STOP
            best_raw_net = 0.0
            for act in [ActionType.REMINDER, ActionType.PAYMENT_LINK, ActionType.PROMISE_TO_PAY, ActionType.ESCALATE]:
                if act in shared_eligible:
                    p = pred.actions[act.value].action_probability
                    cost = self.policy._action_costs.get(act, 0.0)
                    net = (p * state.residual_amount) - cost - friction
                    if net > best_raw_net:
                        best_raw_net = net
                        best_raw_act = act
            results["C_RAW_PROBABILITY_WITH_COST"][best_raw_act.value] += 1

            # Variant D: Uplift with Cost, No Threshold
            best_d_act = ActionType.STOP
            best_d_net = 0.0
            for act in [ActionType.REMINDER, ActionType.PAYMENT_LINK, ActionType.PROMISE_TO_PAY, ActionType.ESCALATE]:
                if act in shared_eligible:
                    tau = pred.actions[act.value].incremental_probability
                    cost = self.policy._action_costs.get(act, 0.0)
                    net = (tau * state.residual_amount) - cost - friction
                    if net > best_d_net:
                        best_d_net = net
                        best_d_act = act
            results["D_UPLIFT_WITH_COST_NO_THRESHOLD"][best_d_act.value] += 1

        # Normalize to percentage distribution
        normalized_results = {}
        for variant, counts in results.items():
            normalized_results[variant] = {k: round(v / float(total) * 100.0, 1) for k, v in counts.items() if v > 0}

        return normalized_results
