import os
import sys
import json
import yaml
import time
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from typing import Dict, List, Any, Tuple, Optional
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from domain.enums import ActionType, CaseState, CustomerSegment
from domain.models import ObservableCaseState, PolicyDecision
from simulator.generator import SyntheticCaseGenerator
from simulator.environment import SimulationEnvironment
from models.artifacts import ModelArtifactManager
from models.incremental_recovery import IncrementalRecoveryModel
from policy.eligibility import CandidateActionService
from policy.confidence import PolicyConfidenceService
from policy.evaluations import ActionEvaluation, DecisionTrace
from models.incremental_recovery import IncrementalPredictionResult

class CachedIncrementalRecoveryModel:
    def __init__(self, inner_model: IncrementalRecoveryModel):
        self.inner_model = inner_model
        self._cache: Dict[Tuple, IncrementalPredictionResult] = {}
        self.model_version = inner_model.model_version

    def predict_action_effects(self, state: ObservableCaseState) -> IncrementalPredictionResult:
        cache_key = (
            state.case_id,
            state.automated_action_count,
            round(state.residual_amount, 2),
            round(state.hours_since_failure, 2),
            state.active_promise_status.value if state.active_promise_status else None,
            state.last_action_type.value if state.last_action_type else None,
        )
        if cache_key in self._cache:
            return self._cache[cache_key]
        res = self.inner_model.predict_action_effects(state)
        self._cache[cache_key] = res
        return res

class ParameterizedPolicy:
    """
    Candidate policy for validation tuning.
    Explores candidate mechanisms cleanly without mutating production code.
    """
    def __init__(
        self,
        model: Any,
        mechanism_name: str,
        escalation_margin: float = 0.0,
        min_escalation_confidence: float = 0.0,
        cost_uncertainty_lambda: float = 0.0,
        use_cost_relative_viability: bool = True,
        low_confidence_threshold: float = 0.60,
    ):
        self.model = model
        self.mechanism_name = mechanism_name
        self.escalation_margin = escalation_margin
        self.min_escalation_confidence = min_escalation_confidence
        self.cost_uncertainty_lambda = cost_uncertainty_lambda
        self.use_cost_relative_viability = use_cost_relative_viability
        self.low_confidence_threshold = low_confidence_threshold
        
        self.eligibility_service = CandidateActionService()
        self.confidence_service = PolicyConfidenceService(low_confidence_threshold=low_confidence_threshold)
        self._action_costs = {
            ActionType.REMINDER: self.eligibility_service.cost_reminder,
            ActionType.PAYMENT_LINK: self.eligibility_service.cost_payment_link,
            ActionType.PROMISE_TO_PAY: self.eligibility_service.cost_promise_to_pay,
            ActionType.ESCALATE: self.eligibility_service.cost_escalate,
            ActionType.STOP: 0.0,
        }

    def evaluate_case(self, state: ObservableCaseState, decision_time=None) -> PolicyDecision:
        shared_eligible = set(self.eligibility_service.get_eligible_actions(state))
        pred_result = self.model.predict_action_effects(state)
        p_control = pred_result.control_probability
        friction = self.eligibility_service.calculate_friction(state.automated_action_count)

        # 1. Pre-calculate metrics for all actions
        raw_evals = {}
        eval_actions = [
            ActionType.STOP,
            ActionType.REMINDER,
            ActionType.PAYMENT_LINK,
            ActionType.PROMISE_TO_PAY,
            ActionType.ESCALATE,
        ]

        for act in eval_actions:
            is_contract_eligible = act in shared_eligible
            if act == ActionType.STOP:
                raw_evals[act] = {
                    "prob": p_control,
                    "tau": 0.0,
                    "exp_inc_rev": 0.0,
                    "act_cost": 0.0,
                    "friction": 0.0,
                    "exp_net": 0.0,
                    "exp_net_adj": 0.0,
                    "conf_score": 1.0,
                    "contract_eligible": is_contract_eligible,
                }
                continue

            act_pred = pred_result.actions.get(act.value)
            if act_pred is not None:
                p_act = act_pred.action_probability
                tau = act_pred.incremental_probability
                exp_inc_rev = act_pred.expected_incremental_revenue
            else:
                p_act = p_control
                tau = 0.0
                exp_inc_rev = 0.0

            act_cost = self._action_costs.get(act, 0.0)
            exp_net = float(exp_inc_rev - act_cost - friction)

            conf_score, conf_status = self.confidence_service.evaluate_confidence(
                state=state,
                action_type=act,
                action_prob=p_act,
                control_prob=p_control,
            )

            # Optional cost-weighted uncertainty adjustment
            if self.cost_uncertainty_lambda > 0.0:
                uncertainty_penalty = self.cost_uncertainty_lambda * act_cost * (1.0 - conf_score)
                exp_net_adjusted = exp_net - uncertainty_penalty
            else:
                exp_net_adjusted = exp_net

            raw_evals[act] = {
                "prob": p_act,
                "tau": tau,
                "exp_inc_rev": exp_inc_rev,
                "act_cost": act_cost,
                "friction": friction,
                "exp_net": exp_net,
                "exp_net_adj": exp_net_adjusted,
                "conf_score": conf_score,
                "contract_eligible": is_contract_eligible,
            }

        # Find best eligible non-escalation alternative
        eligible_non_esc_nets = [
            raw_evals[a]["exp_net_adj"]
            for a in eval_actions
            if a != ActionType.ESCALATE and raw_evals[a]["contract_eligible"] and (not self.use_cost_relative_viability or raw_evals[a]["exp_net_adj"] > 0.0 or a == ActionType.STOP)
        ]
        best_non_esc_net = max(eligible_non_esc_nets) if eligible_non_esc_nets else 0.0

        # Construct final ActionEvaluation objects
        evaluations: List[ActionEvaluation] = []
        for act in eval_actions:
            d = raw_evals[act]
            is_eligible = d["contract_eligible"]
            rej_reason = None

            if not is_eligible:
                rej_reason = "INELIGIBLE_BY_SHARED_CONTRACT"
            elif act != ActionType.STOP and self.use_cost_relative_viability and d["exp_net_adj"] <= 0.0:
                is_eligible = False
                rej_reason = "NEGATIVE_OR_ZERO_EXPECTED_NET_RECOVERY"
            elif act == ActionType.ESCALATE:
                if self.min_escalation_confidence > 0.0 and d["conf_score"] < self.min_escalation_confidence:
                    is_eligible = False
                    rej_reason = f"CONFIDENCE_BELOW_ESCALATION_GATE_{self.min_escalation_confidence}"
                elif self.escalation_margin > 0.0 and d["exp_net_adj"] < (best_non_esc_net + self.escalation_margin):
                    is_eligible = False
                    rej_reason = f"INSUFFICIENT_ESCALATION_ADVANTAGE_MARGIN_{self.escalation_margin}"

            evaluations.append(ActionEvaluation(
                action=act,
                probability=d["prob"],
                control_probability=p_control,
                incremental_probability=d["tau"],
                residual_amount=state.residual_amount,
                expected_incremental_revenue=d["exp_inc_rev"],
                action_cost=d["act_cost"],
                friction_cost=d["friction"],
                expected_net_recovery=d["exp_net_adj"],
                eligible=is_eligible,
                rejection_reason=rej_reason,
            ))

        # Filter and sort
        final_eligible = [e for e in evaluations if e.eligible]
        final_eligible.sort(
            key=lambda e: (e.expected_net_recovery, -e.action_cost),
            reverse=True,
        )

        top_choice = final_eligible[0] if final_eligible else evaluations[0]
        selected_action = top_choice.action
        selection_reason = f"Selected {selected_action.value} with adjusted E[Net] INR {top_choice.expected_net_recovery:.2f}"

        conf_score_final, _ = self.confidence_service.evaluate_confidence(
            state=state,
            action_type=selected_action,
            action_prob=top_choice.probability,
            control_prob=p_control,
        )

        return PolicyDecision(
            decision_id=f"dec_{state.case_id}",
            case_id=state.case_id,
            candidate_actions=list(shared_eligible),
            selected_action=selected_action,
            model_version=pred_result.model_version,
            policy_version="recoveriq-v2-candidate",
            confidence=conf_score_final,
            expected_incremental_recovery=top_choice.expected_incremental_revenue,
            expected_cost=top_choice.action_cost,
            expected_friction_cost=top_choice.friction_cost,
            net_expected_value=top_choice.expected_net_recovery,
            decision_reason=selection_reason,
        )

def evaluate_candidate_policy(policy: ParameterizedPolicy, scenario: str, seed: int, n_cases: int):
    # Always generate a fresh, unmutated cohort for each candidate run
    gen = SyntheticCaseGenerator(seed=seed)
    cohort = gen.generate_batch(count=n_cases, scenario_id=scenario)

    nets = []
    gross_tot = 0.0
    act_cost_tot = 0.0
    fric_tot = 0.0
    rec_count = 0
    int_count = 0
    unnec_count = 0
    act_dist = defaultdict(int)
    segment_nets = defaultdict(list)

    for i, (cust, pay, att, case, hidden) in enumerate(cohort):
        env = SimulationEnvironment(scenario_id=scenario, seed=seed + i)
        env.register_case(cust, pay, att, case, hidden)
        case_id = case.case_id

        sim_time = att.attempted_at
        sim_step = 0
        while sim_step < 3:
            obs = env.get_observable_state(case_id, sim_time)
            if obs.is_terminal:
                break
            decision = policy.evaluate_case(obs, sim_time)
            sel_act = decision.selected_action
            act_dist[sel_act.value] += 1

            if sel_act == ActionType.STOP:
                env.check_natural_recovery_for_control(case_id, as_of_time=case.created_at + timedelta(hours=72))
                break

            int_count += 1
            if hidden.y_control:
                unnec_count += 1

            exec_rec, updated_case = env.execute_action(
                case_id=case_id,
                action_type=sel_act,
                timestamp=sim_time,
                idempotency_key=f"idem_val_{case_id}_{sim_step}",
                policy_version="val-candidate",
            )
            if updated_case.current_state in [CaseState.RECOVERED, CaseState.STOPPED, CaseState.MANUAL_REVIEW_REQUIRED]:
                break
            sim_time += timedelta(hours=14)
            sim_step += 1

        outcome = env.get_outcome(case_id)
        case_actions = env._actions.get(case_id, [])
        gross = outcome.recovered_amount
        cost = sum(a.cost for a in case_actions)
        fric = sum(a.friction_cost for a in case_actions)
        net = gross - cost - fric

        nets.append(net)
        gross_tot += gross
        act_cost_tot += cost
        fric_tot += fric
        if outcome.recovered_amount > 0:
            rec_count += 1
        segment_nets[cust.segment.value].append(net)

    n = len(cohort)
    mean_net = float(np.mean(nets))
    rec_rate = float(rec_count / n)
    unnec_rate = float(unnec_count / int_count) if int_count > 0 else 0.0
    tot_actions = sum(act_dist.values())
    act_pcts = {k: float(v / tot_actions * 100.0) for k, v in act_dist.items()}
    
    seg_means = [np.mean(vals) for vals in segment_nets.values() if len(vals) > 0]
    seg_std = float(np.std(seg_means)) if len(seg_means) > 0 else 0.0

    return {
        "n_cases": n,
        "total_net": float(sum(nets)),
        "mean_net_per_case": mean_net,
        "gross_recovery": float(gross_tot),
        "action_cost": float(act_cost_tot),
        "friction_cost": float(fric_tot),
        "recovery_rate": rec_rate,
        "unnecessary_intervention_rate": unnec_rate,
        "action_distribution": act_pcts,
        "segment_mean_std": seg_std,
    }

def run_validation_tuning(val_config_path: str = "configs/phase10_validation.yaml"):
    print("=" * 60, flush=True)
    print("PHASE 10: VALIDATION HYPERPARAMETER TUNING & MECHANISM SELECTION", flush=True)
    print("=" * 60, flush=True)

    with open(val_config_path, "r") as f:
        cfg = yaml.safe_load(f)

    n_cases = cfg["dataset_size"]
    seed = cfg["random_seed"]
    scenario = cfg["scenario"]

    print(f"Loading Validation Cohort: N={n_cases}, Seed={seed}, Scenario={scenario}", flush=True)
    gen = SyntheticCaseGenerator(seed=seed)
    cohort = gen.generate_batch(count=n_cases, scenario_id=scenario)
    raw_model = ModelArtifactManager().load_model("incremental-model-v1")
    model = CachedIncrementalRecoveryModel(raw_model)

    # Define Candidate Grid
    candidates = [
        # Clean Economic Baseline (no margin, pure E[Net]>0)
        {"name": "Clean_Economic_Baseline", "margin": 0.0, "conf_gate": 0.0, "lambda": 0.0},
        
        # Escalation Margin Exploration
        {"name": "Margin_INR_25", "margin": 25.0, "conf_gate": 0.0, "lambda": 0.0},
        {"name": "Margin_INR_50", "margin": 50.0, "conf_gate": 0.0, "lambda": 0.0},
        {"name": "Margin_INR_75", "margin": 75.0, "conf_gate": 0.0, "lambda": 0.0},
        {"name": "Margin_INR_100", "margin": 100.0, "conf_gate": 0.0, "lambda": 0.0},
        {"name": "Margin_INR_150", "margin": 150.0, "conf_gate": 0.0, "lambda": 0.0},
        {"name": "Margin_INR_200", "margin": 200.0, "conf_gate": 0.0, "lambda": 0.0},
        {"name": "Margin_INR_300", "margin": 300.0, "conf_gate": 0.0, "lambda": 0.0},
        
        # Confidence Gate Exploration
        {"name": "ConfGate_0.60", "margin": 0.0, "conf_gate": 0.60, "lambda": 0.0},
        {"name": "ConfGate_0.70", "margin": 0.0, "conf_gate": 0.70, "lambda": 0.0},
        {"name": "ConfGate_0.80", "margin": 0.0, "conf_gate": 0.80, "lambda": 0.0},
        
        # Cost-Weighted Uncertainty Exploration
        {"name": "Uncertainty_Lambda_0.5", "margin": 0.0, "conf_gate": 0.0, "lambda": 0.5},
        {"name": "Uncertainty_Lambda_1.0", "margin": 0.0, "conf_gate": 0.0, "lambda": 1.0},
        {"name": "Uncertainty_Lambda_2.0", "margin": 0.0, "conf_gate": 0.0, "lambda": 2.0},
        
        # Synergistic Composites
        {"name": "Composite_Margin50_Lambda1.0", "margin": 50.0, "conf_gate": 0.0, "lambda": 1.0},
        {"name": "Composite_Margin75_Lambda1.0", "margin": 75.0, "conf_gate": 0.0, "lambda": 1.0},
        {"name": "Composite_Margin100_Lambda1.0", "margin": 100.0, "conf_gate": 0.0, "lambda": 1.0},
        {"name": "Composite_Margin150_Lambda1.0", "margin": 150.0, "conf_gate": 0.0, "lambda": 1.0},
    ]

    results = []
    print(f"\nEvaluating {len(candidates)} candidate configurations on validation cohort...", flush=True)

    for idx, c in enumerate(candidates):
        cand_name = c["name"]
        t_start_cand = time.time()
        policy = ParameterizedPolicy(
            model=model,
            mechanism_name=cand_name,
            escalation_margin=c["margin"],
            min_escalation_confidence=c["conf_gate"],
            cost_uncertainty_lambda=c["lambda"],
            use_cost_relative_viability=True,
        )
        res = evaluate_candidate_policy(policy, scenario, seed, n_cases)
        duration = time.time() - t_start_cand
        
        # Apply Mandatory Stability & Non-Pathology Filters
        is_pathological = False
        rejection_reasons = []

        # Rejection 1: Collapsing to non-adaptive policy (e.g. single action > 85%)
        max_action_pct = max(res["action_distribution"].values()) if res["action_distribution"] else 0.0
        if max_action_pct > 85.0:
            is_pathological = True
            rejection_reasons.append(f"Action collapse: dominant action represents {max_action_pct:.1f}% > 85%")

        # Rejection 2: Unnecessary intervention rate > 55%
        if res["unnecessary_intervention_rate"] > 0.55:
            is_pathological = True
            rejection_reasons.append(f"Unnecessary intervention rate {res['unnecessary_intervention_rate']:.3f} > 0.55")

        # Rejection 3: Non-adaptive action space (< 3 actions used)
        non_zero_actions = [k for k, v in res["action_distribution"].items() if v > 1.0]
        if len(non_zero_actions) < 3:
            is_pathological = True
            rejection_reasons.append(f"Insufficient action diversity: only {len(non_zero_actions)} actions > 1%")

        cand_result = {
            "name": cand_name,
            "parameters": c,
            "metrics": res,
            "is_valid": not is_pathological,
            "rejection_reasons": rejection_reasons,
            "eval_time_sec": round(duration, 2),
        }
        results.append(cand_result)

        print(f"[{idx+1}/{len(candidates)}] {cand_name:<32} -> Mean Net: INR {res['mean_net_per_case']:.2f}/case | Escalate: {res['action_distribution'].get('ESCALATE', 0.0):.1f}% | Valid: {not is_pathological} ({duration:.1f}s)", flush=True)

    # Sort valid candidates by mean_net_per_case descending
    valid_candidates = [r for r in results if r["is_valid"]]
    valid_candidates.sort(key=lambda r: r["metrics"]["mean_net_per_case"], reverse=True)

    if not valid_candidates:
        print("ERROR: No valid non-pathological candidate found!", flush=True)
        best_cand = results[0]
    else:
        best_cand = valid_candidates[0]

    print("\n" + "=" * 60, flush=True)
    print(f"SELECTED POLICY CONFIGURATION: {best_cand['name']}", flush=True)
    print(f"Validation Mean Net: INR {best_cand['metrics']['mean_net_per_case']:.2f}/case", flush=True)
    print(f"Action Distribution: {best_cand['metrics']['action_distribution']}", flush=True)
    print(f"Parameters: {best_cand['parameters']}", flush=True)
    print("=" * 60, flush=True)

    selection_record = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "validation_dataset_size": n_cases,
        "validation_seed": seed,
        "selected_configuration": best_cand["name"],
        "selected_parameters": best_cand["parameters"],
        "selected_metrics": best_cand["metrics"],
        "selection_rationale": (
            f"Maximizes validation Net Recovery (INR {best_cand['metrics']['mean_net_per_case']:.2f}/case) "
            f"while strictly satisfying stability, non-pathology, and diversity constraints. "
            f"Escalate frequency is disciplined to {best_cand['metrics']['action_distribution'].get('ESCALATE', 0.0):.1f}%."
        ),
        "all_candidates": results,
    }

    out_dir = "results/phase10"
    os.makedirs(out_dir, exist_ok=True)
    sel_path = os.path.join(out_dir, "validation_selection.json")
    with open(sel_path, "w") as f:
        json.dump(selection_record, f, indent=2)

    print(f"Validation selection artifact saved to {sel_path}", flush=True)
    return selection_record

if __name__ == "__main__":
    run_validation_tuning()
