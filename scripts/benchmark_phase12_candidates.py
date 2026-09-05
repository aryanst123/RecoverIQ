"""
Phase 12 Candidate Benchmarking & Model Selection Script
Trains and evaluates candidate V4 policies against Baseline and V3 on isolated validation set.
"""
import os
import sys
import json
from datetime import timedelta
from collections import defaultdict
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from domain.enums import ActionType, CaseState
from simulator.generator import SyntheticCaseGenerator
from simulator.environment import SimulationEnvironment
from baseline.policy import DeterministicBaselinePolicy
from baseline.config import load_baseline_config
from models.artifacts import ModelArtifactManager
from policy.adaptive_v3 import RecoverIQAdaptivePolicyV3

# Define Candidate V4 Policy
from domain.models import ObservableCaseState, PolicyDecision
from policy.evaluations import ActionEvaluation
from policy.eligibility import CandidateActionService
from typing import Dict, List, Optional
from datetime import datetime, timezone

class RecoverIQAdaptivePolicyV4:
    def __init__(self, model, candidate_service: Optional[CandidateActionService] = None):
        self.version = "recoveriq-v4"
        self.model = model
        self.eligibility_service = candidate_service or CandidateActionService()
        self._action_costs = {
            ActionType.STOP: 0.0,
            ActionType.REMINDER: 2.0,
            ActionType.PAYMENT_LINK: 3.0,
            ActionType.PROMISE_TO_PAY: 5.0,
            ActionType.ESCALATE: 100.0,
        }
        self.checksum = "v4_stage_aware_dp_policy"

    def evaluate_case(self, state: ObservableCaseState, decision_time: Optional[datetime] = None) -> PolicyDecision:
        current_time = decision_time or datetime.now(timezone.utc)
        
        # 1. Hard Safety Gate Checks
        if state.customer_opt_out:
            return self._build_terminal_decision(state, ActionType.STOP, "SafetyGate: Customer opt-out active", current_time)
        if state.is_terminal:
            return self._build_terminal_decision(state, ActionType.STOP, "SafetyGate: Case in terminal state", current_time)
        if state.active_promise_status is not None:
            return self._build_terminal_decision(state, ActionType.STOP, "SafetyGate: Active promise to pay pending verification", current_time)
        if state.automated_action_count >= 3:
            return self._build_terminal_decision(state, ActionType.STOP, "SafetyGate: Maximum automated attempts reached (3)", current_time)

        # 2. Universal Eligibility from domain contract
        shared_eligible = set(self.eligibility_service.get_eligible_actions(state))

        # 3. Predict calibrated action probabilities from calibrated model
        pred_result = self.model.predict_action_effects(state)
        p_control = pred_result.control_probability

        step = state.automated_action_count
        amount = state.residual_amount
        current_friction = self.eligibility_service.calculate_friction(step)

        # Stage-conditioned degradation factors based on empirical sequence dependence
        # Stage 1 conditional response factor ~ 0.82; Stage 2 ~ 0.70
        stage_discount = 1.0 if step == 0 else (0.82 if step == 1 else 0.70)

        action_probs: Dict[ActionType, float] = {
            ActionType.STOP: p_control if step == 0 else 0.0,
            ActionType.REMINDER: (pred_result.actions[ActionType.REMINDER.value].action_probability if ActionType.REMINDER.value in pred_result.actions else p_control) * stage_discount,
            ActionType.PAYMENT_LINK: (pred_result.actions[ActionType.PAYMENT_LINK.value].action_probability if ActionType.PAYMENT_LINK.value in pred_result.actions else p_control) * stage_discount,
            ActionType.PROMISE_TO_PAY: (pred_result.actions[ActionType.PROMISE_TO_PAY.value].action_probability if ActionType.PROMISE_TO_PAY.value in pred_result.actions else p_control) * stage_discount,
            ActionType.ESCALATE: pred_result.actions[ActionType.ESCALATE.value].action_probability if ActionType.ESCALATE.value in pred_result.actions else p_control,
        }

        # 4. Sequential Dynamic Programming Backward Induction
        # Correctly modeling: After a failed attempt, posterior natural recovery is 0.0.
        action_evals: Dict[ActionType, ActionEvaluation] = {}
        continuation_values: Dict[ActionType, float] = {}

        # First compute Stage 2 terminal continuation value
        f2 = self.eligibility_service.calculate_friction(2)
        v2_star = max(
            0.0,  # STOP value after prior failure
            action_probs[ActionType.REMINDER] * 0.70 * amount - self._action_costs[ActionType.REMINDER] - f2,
            action_probs[ActionType.PAYMENT_LINK] * 0.70 * amount - self._action_costs[ActionType.PAYMENT_LINK] - f2,
            (action_probs[ActionType.ESCALATE] * amount - self._action_costs[ActionType.ESCALATE] - f2) if (amount >= 1500) else -9999.0
        )

        # Compute Stage 1 continuation value
        f1 = self.eligibility_service.calculate_friction(1)
        v1_star = max(
            0.0,  # STOP value after prior failure
            action_probs[ActionType.REMINDER] * 0.82 * (amount - self._action_costs[ActionType.REMINDER] - f1) + (1.0 - action_probs[ActionType.REMINDER] * 0.82) * (v2_star - self._action_costs[ActionType.REMINDER] - f1),
            action_probs[ActionType.PAYMENT_LINK] * 0.82 * (amount - self._action_costs[ActionType.PAYMENT_LINK] - f1) + (1.0 - action_probs[ActionType.PAYMENT_LINK] * 0.82) * (v2_star - self._action_costs[ActionType.PAYMENT_LINK] - f1),
            (action_probs[ActionType.ESCALATE] * amount - self._action_costs[ActionType.ESCALATE] - f1) if (amount >= 1500) else -9999.0
        )

        for act in [ActionType.STOP, ActionType.REMINDER, ActionType.PAYMENT_LINK, ActionType.PROMISE_TO_PAY, ActionType.ESCALATE]:
            is_eligible = act in shared_eligible
            p_act = action_probs[act]
            tau = p_act - p_control
            cost = self._action_costs.get(act, 0.0)

            if not is_eligible:
                continuation_values[act] = -9999.0
                action_evals[act] = ActionEvaluation(
                    action=act, probability=p_act, control_probability=p_control,
                    incremental_probability=tau, residual_amount=amount,
                    expected_incremental_revenue=tau * amount, action_cost=cost,
                    friction_cost=current_friction, expected_net_recovery=-9999.0,
                    eligible=False, rejection_reason="Not eligible under contract rules",
                )
                continue

            if act == ActionType.STOP:
                # Natural recovery is available only at step 0; after failure, STOP yields 0
                exp_net = (p_control * amount) if step == 0 else 0.0
            elif act == ActionType.ESCALATE:
                exp_net = p_act * amount - cost - current_friction
            else:
                if step == 0:
                    exp_net = p_act * (amount - cost) + (1.0 - p_act) * (v1_star - cost)
                elif step == 1:
                    exp_net = p_act * (amount - cost - current_friction) + (1.0 - p_act) * (v2_star - cost - current_friction)
                else:
                    exp_net = p_act * amount - cost - current_friction

            continuation_values[act] = exp_net
            action_evals[act] = ActionEvaluation(
                action=act, probability=p_act, control_probability=p_control,
                incremental_probability=tau, residual_amount=amount,
                expected_incremental_revenue=tau * amount, action_cost=cost,
                friction_cost=current_friction, expected_net_recovery=exp_net,
                eligible=True,
            )

        eligible_acts = [act for act in continuation_values if action_evals[act].eligible]
        best_action = max(eligible_acts, key=lambda a: continuation_values[a]) if eligible_acts else ActionType.STOP

        chosen_eval = action_evals[best_action]
        tau_chosen = chosen_eval.incremental_probability
        expected_inc_rev = max(0.0, tau_chosen * amount)

        return PolicyDecision(
            decision_id=f"dec_v4_{state.case_id}_{step}",
            case_id=state.case_id,
            candidate_actions=list(shared_eligible),
            selected_action=best_action,
            model_version=self.model.model_version,
            policy_version=self.version,
            confidence=0.95,
            expected_incremental_recovery=expected_inc_rev,
            expected_cost=chosen_eval.action_cost,
            expected_friction_cost=chosen_eval.friction_cost,
            net_expected_value=chosen_eval.expected_net_recovery,
            decision_reason=f"V4_SequentialDP: {best_action.value} maximizes stage-conditional continuation value",
        )

    def _build_terminal_decision(self, state: ObservableCaseState, action: ActionType, reason: str, t: datetime) -> PolicyDecision:
        return PolicyDecision(
            decision_id=f"dec_v4_{state.case_id}_{state.automated_action_count}",
            case_id=state.case_id,
            candidate_actions=[action],
            selected_action=action,
            model_version=self.model.model_version,
            policy_version=self.version,
            confidence=1.0,
            expected_incremental_recovery=0.0,
            expected_cost=0.0,
            expected_friction_cost=0.0,
            net_expected_value=0.0,
            decision_reason=reason,
        )


print("Loading models and preparing validation simulation (N=5,000, seed=555444333)...", flush=True)
model_mgr = ModelArtifactManager()
model_v3 = model_mgr.load_model("incremental-model-v3")

baseline_policy = DeterministicBaselinePolicy(load_baseline_config())
policy_v3 = RecoverIQAdaptivePolicyV3(model=model_v3)
policy_v4 = RecoverIQAdaptivePolicyV4(model=model_v3)

gen_val = SyntheticCaseGenerator(seed=555444333)
val_cohort = gen_val.generate_batch(count=5000, scenario_id="S1_HIGH_NATURAL_RECOVERY")

candidates = {
    "BASELINE": baseline_policy,
    "RECOVERIQ_V3": policy_v3,
    "RECOVERIQ_V4": policy_v4,
}

val_results = {}

for name, pol in candidates.items():
    print(f"Evaluating {name} on validation cohort...", flush=True)
    nets = []
    gross_list = []
    cost_list = []
    fric_list = []
    rec_flags = []
    act_counts = defaultdict(int)

    for i, (cust, pay, att, case, hidden) in enumerate(val_cohort):
        c_cust = cust.model_copy(deep=True)
        c_pay = pay.model_copy(deep=True)
        c_att = att.model_copy(deep=True)
        c_case = case.model_copy(deep=True)
        
        env = SimulationEnvironment(scenario_id="S1_HIGH_NATURAL_RECOVERY", seed=555444333 + i)
        env.register_case(c_cust, c_pay, c_att, c_case, hidden)
        t_sim = c_att.attempted_at

        for s in range(3):
            obs = env.get_observable_state(c_case.case_id, t_sim)
            if obs.is_terminal: break
            dec = pol.evaluate(obs, t_sim) if name == "BASELINE" else pol.evaluate_case(obs, t_sim)
            act = dec.selected_action
            act_counts[act.value] += 1
            if act == ActionType.STOP:
                env.check_natural_recovery_for_control(c_case.case_id, as_of_time=c_case.created_at + timedelta(hours=72))
                break
            exec_r, upd_c = env.execute_action(c_case.case_id, act, t_sim, f"{name}_{i}_{s}", policy_version=name.lower())
            if upd_c.current_state in [CaseState.RECOVERED, CaseState.STOPPED, CaseState.MANUAL_REVIEW_REQUIRED]: break
            t_sim += timedelta(hours=14)

        outcome = env.get_outcome(c_case.case_id)
        acts = env._actions.get(c_case.case_id, [])
        c_act = sum(a.cost for a in acts)
        c_fric = sum(a.friction_cost for a in acts)
        gross = outcome.recovered_amount
        net = gross - c_act - c_fric
        gross_list.append(gross)
        cost_list.append(c_act)
        fric_list.append(c_fric)
        nets.append(net)
        rec_flags.append(1 if outcome.recovered_amount > 0 else 0)

    tot_acts = sum(act_counts.values()) or 1
    val_results[name] = {
        "N": len(val_cohort),
        "mean_net_recovery": round(float(np.mean(nets)), 2),
        "mean_gross_recovery": round(float(np.mean(gross_list)), 2),
        "mean_action_cost": round(float(np.mean(cost_list)), 2),
        "mean_friction_cost": round(float(np.mean(fric_list)), 2),
        "recovery_rate_pct": round(float(np.mean(rec_flags)) * 100, 2),
        "action_percentages": {k: round(v / tot_acts * 100, 2) for k, v in sorted(act_counts.items())},
        "escalation_pct": round(act_counts.get("ESCALATE", 0) / tot_acts * 100, 2),
    }

print("\n--- VALIDATION RESULTS ---")
print(json.dumps(val_results, indent=2))

with open("results/phase12/validation_results.json", "w") as f:
    json.dump(val_results, f, indent=2)

print("\n[Artifact Saved] results/phase12/validation_results.json")
