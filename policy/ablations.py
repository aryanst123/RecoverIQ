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

    def run_comprehensive_ablations(
        self,
        cohort: List[Any],
        env: Any,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Simulates outcomes under all 5 ablation variants to evaluate:
        - gross recovered
        - net recovered
        - mean net recovery per case
        - action cost
        - recovery rate
        - intervention efficiency
        - unnecessary intervention rate
        - critical safety violations
        """
        variant_names = [
            "A_DETERMINISTIC_BASELINE",
            "B_UPLIFT_WITHOUT_COST",
            "C_RAW_PROBABILITY_WITH_COST",
            "D_UPLIFT_WITH_COST_NO_THRESHOLD",
            "E_FULL_RECOVERIQ_STANDARD",
        ]

        variant_data = {v: {
            "gross": 0.0,
            "cost": 0.0,
            "friction": 0.0,
            "recovered_count": 0,
            "interventions_count": 0,
            "unnecessary_count": 0,
            "safety_violations": 0,
            "action_counts": {act.value: 0 for act in ActionType},
        } for v in variant_names}

        for cust, pay, att, case, hidden in cohort:
            state = env.get_observable_state(case.case_id, att.attempted_at)
            shared_eligible = set(self.eligibility.get_eligible_actions(state))
            friction = self.eligibility.calculate_friction(state.automated_action_count)
            pred = self.policy.model.predict_action_effects(state)
            amount = case.amount_due

            # 1. Variant Decisions
            # A. Baseline
            b_dec = self.baseline.evaluate(state)
            act_a = b_dec.selected_action

            # B. Uplift Without Cost (argmax tau)
            act_b = ActionType.STOP
            best_tau = 0.0
            for act in [ActionType.REMINDER, ActionType.PAYMENT_LINK, ActionType.PROMISE_TO_PAY, ActionType.ESCALATE]:
                if act in shared_eligible:
                    tau = pred.actions[act.value].incremental_probability
                    if tau > best_tau:
                        best_tau = tau
                        act_b = act

            # C. Raw Probability with Cost
            act_c = ActionType.STOP
            best_c_net = 0.0
            for act in [ActionType.REMINDER, ActionType.PAYMENT_LINK, ActionType.PROMISE_TO_PAY, ActionType.ESCALATE]:
                if act in shared_eligible:
                    p = pred.actions[act.value].action_probability
                    c_cost = self.policy._action_costs.get(act, 0.0)
                    net = (p * state.residual_amount) - c_cost - friction
                    if net > best_c_net:
                        best_c_net = net
                        act_c = act

            # D. Uplift with Cost, No Threshold
            act_d = ActionType.STOP
            best_d_net = 0.0
            for act in [ActionType.REMINDER, ActionType.PAYMENT_LINK, ActionType.PROMISE_TO_PAY, ActionType.ESCALATE]:
                if act in shared_eligible:
                    tau = pred.actions[act.value].incremental_probability
                    d_cost = self.policy._action_costs.get(act, 0.0)
                    net = (tau * state.residual_amount) - d_cost - friction
                    if net > best_d_net:
                        best_d_net = net
                        act_d = act

            # E. Full RecoverIQ Standard
            e_dec = self.policy.evaluate_case(state)
            act_e = e_dec.selected_action

            actions_map = {
                "A_DETERMINISTIC_BASELINE": act_a,
                "B_UPLIFT_WITHOUT_COST": act_b,
                "C_RAW_PROBABILITY_WITH_COST": act_c,
                "D_UPLIFT_WITH_COST_NO_THRESHOLD": act_d,
                "E_FULL_RECOVERIQ_STANDARD": act_e,
            }

            for v_name, chosen_act in actions_map.items():
                vd = variant_data[v_name]
                vd["action_counts"][chosen_act.value] += 1

                # Safety check
                if chosen_act != ActionType.STOP:
                    if state.customer_opt_out or state.automated_action_count >= 3 or state.hours_since_failure > 720.0:
                        vd["safety_violations"] += 1

                if chosen_act == ActionType.STOP:
                    recovered = hidden.y_control
                    gross = amount if recovered else 0.0
                    cost = 0.0
                    fric = 0.0
                else:
                    vd["interventions_count"] += 1
                    if hidden.y_control:
                        vd["unnecessary_count"] += 1

                    if chosen_act == ActionType.REMINDER:
                        recovered = hidden.y_reminder
                    elif chosen_act == ActionType.PAYMENT_LINK:
                        recovered = hidden.y_payment_link
                    elif chosen_act == ActionType.PROMISE_TO_PAY:
                        recovered = hidden.y_promise_to_pay
                    elif chosen_act == ActionType.ESCALATE:
                        recovered = hidden.y_escalate
                    else:
                        recovered = False

                    gross = amount if recovered else 0.0
                    cost = self.policy._action_costs.get(chosen_act, 0.0)
                    fric = friction

                if recovered:
                    vd["recovered_count"] += 1
                vd["gross"] += gross
                vd["cost"] += cost
                vd["friction"] += fric

        total = len(cohort)
        report = {}
        for v_name, vd in variant_data.items():
            total_net = vd["gross"] - vd["cost"] - vd["friction"]
            mean_net = total_net / total if total > 0 else 0.0
            rec_rate = vd["recovered_count"] / total if total > 0 else 0.0
            total_cost = vd["cost"] + vd["friction"]
            eff = (vd["gross"] / total_cost) if total_cost > 0 else 0.0
            unnec_rate = (vd["unnecessary_count"] / vd["interventions_count"]) if vd["interventions_count"] > 0 else 0.0

            report[v_name] = {
                "gross_recovered": vd["gross"],
                "net_recovered": total_net,
                "mean_net_recovered": mean_net,
                "action_cost": vd["cost"],
                "friction_cost": vd["friction"],
                "recovery_rate": rec_rate,
                "intervention_efficiency": eff,
                "unnecessary_intervention_rate": unnec_rate,
                "safety_violations": vd["safety_violations"],
                "action_distribution": {k: round((v / total) * 100.0, 1) for k, v in vd["action_counts"].items() if v > 0},
            }

        return report
