import os
import sys
import json
import yaml
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from domain.enums import ActionType, PaymentStatus, CaseState, PromiseState
from domain.models import ObservableCaseState, PotentialOutcome
from simulator.scenarios import get_scenario
from simulator.generator import SyntheticCaseGenerator
from simulator.environment import SimulationEnvironment
from baseline.policy import DeterministicBaselinePolicy
from baseline.config import load_baseline_config
from models.features import FeaturePipeline
from models.dataset import DatasetBuilder
from sklearn.linear_model import LogisticRegression
from sklearn.calibration import CalibratedClassifierCV

def run_sequential_validation():
    print("=" * 70, flush=True)
    print("PHASE 11: SEQUENTIAL MULTI-STEP POLICY BENCHMARK ON VALIDATION SET", flush=True)
    print("=" * 70, flush=True)

    val_config_path = "configs/phase11_validation.yaml"
    with open(val_config_path, "r") as f:
        val_cfg = yaml.safe_load(f)

    n_val = val_cfg["dataset_size"]
    val_seed = val_cfg["random_seed"]
    scenario_id = val_cfg["scenario"]

    # 1. Train candidate models under DGP (10,000 training cases, seed 42)
    print("1. Training candidate causal ML models...", flush=True)
    db = DatasetBuilder()
    split_train = db.build_dataset(count=10000, seed=42, scenario_id=scenario_id)
    feature_pipeline = FeaturePipeline()
    feature_names = feature_pipeline.get_feature_names()

    X_train = split_train.X
    A_train = np.array(split_train.A)
    Y_train = split_train.Y.astype(int)

    actions = ["CONTROL", "REMINDER", "PAYMENT_LINK", "PROMISE_TO_PAY", "ESCALATE"]
    costs = {"CONTROL": 0.0, "REMINDER": 2.0, "PAYMENT_LINK": 3.0, "PROMISE_TO_PAY": 5.0, "ESCALATE": 100.0}

    # Model B: Calibrated Multi-Model (Isotonic/Sigmoid)
    models_b = {}
    for act in actions:
        mask = (A_train == act)
        base_clf = LogisticRegression(C=0.5, max_iter=1000, random_state=42)
        calib = CalibratedClassifierCV(estimator=base_clf, method='isotonic', cv=3)
        calib.fit(X_train[mask], Y_train[mask])
        models_b[act] = calib

    # 2. Sequential Simulation on Validation Set (5,000 cases, seed 555444333)
    gen = SyntheticCaseGenerator(seed=val_seed)
    cohort = gen.generate_batch(count=n_val, scenario_id=scenario_id)

    baseline_policy = DeterministicBaselinePolicy(load_baseline_config())

    # Candidate Policies:
    # 1. Baseline
    # 2. RecoverIQ v1 (as-is)
    # 3. RecoverIQ v2 (as-is)
    # 4. RecoverIQ Causal Dynamic: Calibrated probabilities + step-aware continuation value
    #    (If automated_action_count == 0, compare expected net of immediate escalation vs sequential cheap action + fallback)
    from models.artifacts import ModelArtifactManager
    mgr = ModelArtifactManager()
    model_v1 = mgr.load_model("incremental-model-v1")
    from policy.adaptive import RecoverIQAdaptivePolicy
    from policy.adaptive_v2 import RecoverIQAdaptivePolicyV2

    policy_v1 = RecoverIQAdaptivePolicy(model=model_v1, minimum_incremental_recovery=250.0)
    policy_v2 = RecoverIQAdaptivePolicyV2(model=model_v1, escalation_advantage_margin=50.0)

    # Let's test a sequence of causal policy architectures:
    def evaluate_causal_greedy(obs: ObservableCaseState, models_dict):
        x = feature_pipeline.extract_features(obs).reshape(1, -1)
        p_c = float(models_dict["CONTROL"].predict_proba(x)[0, 1])
        p_rem = float(models_dict["REMINDER"].predict_proba(x)[0, 1])
        p_link = float(models_dict["PAYMENT_LINK"].predict_proba(x)[0, 1])
        p_p2p = float(models_dict["PROMISE_TO_PAY"].predict_proba(x)[0, 1])
        p_esc = float(models_dict["ESCALATE"].predict_proba(x)[0, 1])

        amt = obs.residual_amount
        # Expected Net for each action
        net_stop = p_c * amt
        net_rem = p_rem * amt - 2.0
        net_link = p_link * amt - 3.0
        net_p2p = p_p2p * amt - 5.0
        net_esc = p_esc * amt - 100.0

        scores = [
            (net_stop, ActionType.STOP),
            (net_rem, ActionType.REMINDER),
            (net_link, ActionType.PAYMENT_LINK),
            (net_p2p, ActionType.PROMISE_TO_PAY),
            (net_esc, ActionType.ESCALATE),
        ]
        scores.sort(key=lambda s: s[0], reverse=True)
        return scores[0][1]

    def evaluate_causal_continuation(obs: ObservableCaseState, models_dict):
        """
        Causal Continuation Policy:
        Accounts for sequential dynamic options.
        On step 0/1: If a cheap action (e.g. PAYMENT_LINK) has high success probability,
        the expected value of trying PAYMENT_LINK first and escalating only if it fails is:
          E[Net_sequential] = P_link * (Amt - 3) + (1 - P_link) * (P_esc * (Amt - 100) - 3)
          whereas immediate escalation gives:
          E[Net_immediate_esc] = P_esc * Amt - 100.
        Comparing these two:
          E[Net_sequential] - E[Net_immediate_esc] = (P_link + (1-P_link)*P_esc - P_esc)*Amt - 3 - (1-P_link)*100 + 100
                                                  = P_link * (1 - P_esc) * Amt + P_link * 100 - 3.
        Notice that because P_link > 0 and (1 - P_esc) >= 0 and 100 > 3, trying the cheap action first
        DOMINATES immediate escalation in multi-step recovery!
        """
        x = feature_pipeline.extract_features(obs).reshape(1, -1)
        p_c = float(models_dict["CONTROL"].predict_proba(x)[0, 1])
        p_rem = float(models_dict["REMINDER"].predict_proba(x)[0, 1])
        p_link = float(models_dict["PAYMENT_LINK"].predict_proba(x)[0, 1])
        p_p2p = float(models_dict["PROMISE_TO_PAY"].predict_proba(x)[0, 1])
        p_esc = float(models_dict["ESCALATE"].predict_proba(x)[0, 1])

        amt = obs.residual_amount
        attempt = obs.automated_action_count

        # Incremental uplift over control
        tau_rem = max(0.0, p_rem - p_c)
        tau_link = max(0.0, p_link - p_c)
        tau_p2p = max(0.0, p_p2p - p_c)
        tau_esc = max(0.0, p_esc - p_c)

        if attempt >= 2:
            # Last chance step: choose between best action and stop
            net_stop = 0.0
            net_link = tau_link * amt - 3.0
            net_esc = tau_esc * amt - 100.0
            if net_esc > max(net_stop, net_link):
                return ActionType.ESCALATE
            elif net_link > net_stop:
                return ActionType.PAYMENT_LINK
            else:
                return ActionType.STOP

        # Step 0 or 1: Choose between automated actions
        # Compare automated actions based on incremental uplift efficiency (tau / cost)
        candidates = [
            (tau_link * amt - 3.0, ActionType.PAYMENT_LINK),
            (tau_rem * amt - 2.0, ActionType.REMINDER),
            (tau_p2p * amt - 5.0, ActionType.PROMISE_TO_PAY),
        ]
        candidates.sort(key=lambda c: c[0], reverse=True)
        best_net, best_act = candidates[0]

        if best_net > 0:
            return best_act
        else:
            return ActionType.STOP

    test_policies = {
        "CONTROL": None,
        "BASELINE": baseline_policy,
        "RECOVERIQ_V1": policy_v1,
        "RECOVERIQ_V2": policy_v2,
        "RECOVERIQ_CAUSAL_GREEDY": "greedy",
        "RECOVERIQ_CAUSAL_DYNAMIC": "continuation",
    }

    results = {}
    for pol_name, pol_obj in test_policies.items():
        nets = []
        gross_tot = 0.0
        cost_tot = 0.0
        fric_tot = 0.0
        rec_count = 0
        action_counts = defaultdict(int)

        for i, (cust, pay, att, case, hidden) in enumerate(cohort):
            case_id = case.case_id
            start_time = att.attempted_at

            env = SimulationEnvironment(scenario_id=scenario_id, seed=val_seed + i)
            env.register_case(cust, pay, att, case, hidden)

            if pol_name == "CONTROL":
                window_end = case.created_at + timedelta(hours=72)
                env.check_natural_recovery_for_control(case_id, as_of_time=window_end)
                outcome = env.get_outcome(case_id)
                gross = outcome.recovered_amount
                net = gross
                cost = 0.0
                fric = 0.0
                action_counts["STOP"] += 1
                if outcome.recovered_amount > 0:
                    rec_count += 1
            else:
                sim_time = start_time
                sim_step = 0
                while sim_step < 3:
                    obs = env.get_observable_state(case_id, sim_time)
                    if obs.is_terminal:
                        break

                    if pol_name == "BASELINE":
                        decision = pol_obj.evaluate(obs, sim_time)
                        sel_act = decision.selected_action
                    elif pol_name in ["RECOVERIQ_V1", "RECOVERIQ_V2"]:
                        decision = pol_obj.evaluate_case(obs, sim_time)
                        sel_act = decision.selected_action
                    elif pol_name == "RECOVERIQ_CAUSAL_GREEDY":
                        sel_act = evaluate_causal_greedy(obs, models_b)
                    elif pol_name == "RECOVERIQ_CAUSAL_DYNAMIC":
                        sel_act = evaluate_causal_continuation(obs, models_b)

                    action_counts[sel_act.value] += 1

                    if sel_act == ActionType.STOP:
                        window_end = case.created_at + timedelta(hours=72)
                        env.check_natural_recovery_for_control(case_id, as_of_time=window_end)
                        break

                    exec_rec, updated_case = env.execute_action(
                        case_id=case_id,
                        action_type=sel_act,
                        timestamp=sim_time,
                        idempotency_key=f"idem_{pol_name}_{case_id}_{sim_step}",
                        policy_version="test",
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
                if outcome.recovered_amount > 0:
                    rec_count += 1

            nets.append(net)
            gross_tot += gross
            cost_tot += cost
            fric_tot += fric

        mean_net = float(np.mean(nets))
        results[pol_name] = {
            "mean_net": round(mean_net, 2),
            "mean_gross": round(gross_tot / n_val, 2),
            "mean_cost": round((cost_tot + fric_tot) / n_val, 2),
            "recovery_rate": round((rec_count / n_val) * 100.0, 1),
            "action_counts": dict(action_counts),
        }
        print(f"\n[{pol_name}]")
        print(f"  Mean Net Recovery:  INR {mean_net:.2f} / case")
        print(f"  Recovery Rate:      {results[pol_name]['recovery_rate']}%")
        print(f"  Mean Total Cost:    INR {results[pol_name]['mean_cost']:.2f}")
        print(f"  Action Counts:      {dict(action_counts)}")

    with open("results/phase11/sequential_validation_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\n[Artifact Saved] results/phase11/sequential_validation_results.json", flush=True)

if __name__ == "__main__":
    run_sequential_validation()
