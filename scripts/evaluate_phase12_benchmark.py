"""
Phase 12 Independent Benchmark Evaluation Script (N=20,000, Seed: 444555666)
Evaluates all 6 arms: Control, Baseline, RecoverIQ V1, V2, V3, and V4.
Computes 2,000 bootstrap replicates for statistical confidence intervals.
"""
import os
import sys
import json
import yaml
import hashlib
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Tuple
from collections import defaultdict
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from domain.enums import ActionType, PaymentStatus, CaseState, PromiseState, CustomerSegment, ChannelPreference, FailureCode
from domain.models import ObservableCaseState
from simulator.generator import SyntheticCaseGenerator
from simulator.environment import SimulationEnvironment
from baseline.policy import DeterministicBaselinePolicy
from baseline.config import load_baseline_config
from models.artifacts import ModelArtifactManager
from policy.adaptive import RecoverIQAdaptivePolicy
from policy.adaptive_v2 import RecoverIQAdaptivePolicyV2
from policy.adaptive_v3 import RecoverIQAdaptivePolicyV3
from policy.adaptive_v4 import RecoverIQAdaptivePolicyV4
from evaluation.bootstrap import compute_bootstrap_difference_ci, BootstrapResult

def run_phase12_evaluation(config_path: str = "configs/phase12_evaluation.yaml"):
    print("=" * 70, flush=True)
    print("PHASE 12: INDEPENDENT 20,000-CASE BENCHMARK EVALUATION", flush=True)
    print("=" * 70, flush=True)

    out_dir = "results/phase12"
    os.makedirs(out_dir, exist_ok=True)

    with open(config_path, "r") as f:
        cfg = yaml.safe_load(f)

    n_cases = cfg["dataset_size"]  # 20,000
    seed = cfg["random_seed"]      # 444555666
    scenario = cfg["scenario"]    # S1_HIGH_NATURAL_RECOVERY
    boot_iter = cfg.get("bootstrap_iterations", 2000)
    boot_seed = cfg.get("bootstrap_seed", 998877)
    conf_level = cfg.get("confidence_level", 0.95)

    print(f"Evaluation Config: N={n_cases}, Seed={seed}, Scenario={scenario}", flush=True)
    print("Generating 20,000 evaluation cases under independent seed...", flush=True)
    t0 = time.time()
    gen = SyntheticCaseGenerator(seed=seed)
    cohort = gen.generate_batch(count=n_cases, scenario_id=scenario)
    print(f"Cohort generated in {time.time() - t0:.2f}s", flush=True)

    # Load Models and Policies
    model_mgr = ModelArtifactManager()
    model_v1 = model_mgr.load_model("incremental-model-v1")
    model_v3 = model_mgr.load_model("incremental-model-v3")
    model_v4 = model_mgr.load_model("incremental-model-v4")

    baseline_policy = DeterministicBaselinePolicy(load_baseline_config())
    policy_v1 = RecoverIQAdaptivePolicy(model=model_v1, minimum_incremental_recovery=250.0)
    policy_v2 = RecoverIQAdaptivePolicyV2(model=model_v1, escalation_advantage_margin=50.0)
    policy_v3 = RecoverIQAdaptivePolicyV3(model=model_v3)
    policy_v4 = RecoverIQAdaptivePolicyV4(model=model_v4)

    # 6-Arm Modulo Assignment
    arms = ["CONTROL", "BASELINE", "RECOVERIQ_V1", "RECOVERIQ_V2", "RECOVERIQ_V3", "RECOVERIQ_V4"]
    arm_assignments = [arms[i % len(arms)] for i in range(n_cases)]

    arm_nets = defaultdict(list)
    arm_gross = defaultdict(float)
    arm_action_costs = defaultdict(float)
    arm_friction_costs = defaultdict(float)
    arm_recovered_counts = defaultdict(int)
    arm_interventions_counts = defaultdict(int)
    arm_unnecessary_counts = defaultdict(int)
    arm_action_counts = defaultdict(lambda: defaultdict(int))
    oracle_nets = []

    print("\nExecuting sequential multi-step simulation across 20,000 cases...", flush=True)
    t_sim_start = time.time()

    for i, (cust, pay, att, case, hidden) in enumerate(cohort):
        arm = arm_assignments[i]
        case_id = case.case_id
        start_time = att.attempted_at
        amt = case.amount_due

        costs_dict = {"CONTROL": 0.0, "REMINDER": 2.0, "PAYMENT_LINK": 3.0, "PROMISE_TO_PAY": 5.0, "ESCALATE": 100.0}
        opt_net = max(
            (amt if hidden.y_control else 0.0) - costs_dict["CONTROL"],
            (amt if hidden.y_reminder else 0.0) - costs_dict["REMINDER"],
            (amt if hidden.y_payment_link else 0.0) - costs_dict["PAYMENT_LINK"],
            (amt if hidden.y_promise_to_pay else 0.0) - costs_dict["PROMISE_TO_PAY"],
            (amt if hidden.y_escalate else 0.0) - costs_dict["ESCALATE"],
        )
        oracle_nets.append(opt_net)

        env = SimulationEnvironment(scenario_id=scenario, seed=seed + i)
        env.register_case(cust, pay, att, case, hidden)

        if arm == "CONTROL":
            window_end = case.created_at + timedelta(hours=72)
            env.check_natural_recovery_for_control(case_id, as_of_time=window_end)
            outcome = env.get_outcome(case_id)
            gross = outcome.recovered_amount
            net = gross
            cost = 0.0
            fric = 0.0
            arm_action_counts["CONTROL"]["STOP"] += 1
            if outcome.recovered_amount > 0:
                arm_recovered_counts["CONTROL"] += 1
        else:
            if arm == "BASELINE": policy = baseline_policy; p_ver = "baseline-v1"
            elif arm == "RECOVERIQ_V1": policy = policy_v1; p_ver = "recoveriq-v1"
            elif arm == "RECOVERIQ_V2": policy = policy_v2; p_ver = "recoveriq-v2"
            elif arm == "RECOVERIQ_V3": policy = policy_v3; p_ver = "recoveriq-v3"
            elif arm == "RECOVERIQ_V4": policy = policy_v4; p_ver = "recoveriq-v4"

            sim_time = start_time
            for sim_step in range(3):
                obs = env.get_observable_state(case_id, sim_time)
                if obs.is_terminal: break
                dec = policy.evaluate(obs, sim_time) if arm == "BASELINE" else policy.evaluate_case(obs, sim_time)
                sel_act = dec.selected_action
                arm_action_counts[arm][sel_act.value] += 1
                if sel_act == ActionType.STOP:
                    window_end = case.created_at + timedelta(hours=72)
                    env.check_natural_recovery_for_control(case_id, as_of_time=window_end)
                    break
                arm_interventions_counts[arm] += 1
                if hidden.y_control:
                    arm_unnecessary_counts[arm] += 1
                exec_rec, updated_case = env.execute_action(
                    case_id=case_id, action_type=sel_act, timestamp=sim_time,
                    idempotency_key=f"idem_{arm}_{case_id}_{sim_step}", policy_version=p_ver
                )
                if updated_case.current_state in [CaseState.RECOVERED, CaseState.STOPPED, CaseState.MANUAL_REVIEW_REQUIRED]:
                    break
                sim_time += timedelta(hours=14)

            outcome = env.get_outcome(case_id)
            case_actions = env._actions.get(case_id, [])
            gross = outcome.recovered_amount
            cost = sum(a.cost for a in case_actions)
            fric = sum(a.friction_cost for a in case_actions)
            net = gross - cost - fric
            if outcome.recovered_amount > 0:
                arm_recovered_counts[arm] += 1

        arm_nets[arm].append(net)
        arm_gross[arm] += gross
        arm_action_costs[arm] += cost
        arm_friction_costs[arm] += fric

        if (i + 1) % 5000 == 0:
            print(f"  Processed {i + 1}/{n_cases} cases ({time.time() - t_sim_start:.1f}s)...", flush=True)

    sim_duration = time.time() - t_sim_start
    print(f"\n20,000-case simulation completed in {sim_duration:.2f}s", flush=True)

    # 1. Benchmark Table
    benchmark_table = {}
    mean_oracle_net = float(np.mean(oracle_nets))

    for arm in arms:
        n_arm = len(arm_nets[arm])
        tot_gross = arm_gross[arm]
        tot_act_cost = arm_action_costs[arm]
        tot_fric_cost = arm_friction_costs[arm]
        tot_net = sum(arm_nets[arm])
        mean_net = tot_net / n_arm
        rec_rate = arm_recovered_counts[arm] / n_arm
        tot_cost = tot_act_cost + tot_fric_cost
        eff = (tot_gross / tot_cost) if tot_cost > 0 else 0.0
        tot_actions = sum(arm_action_counts[arm].values())
        action_pcts = {
            act: round((cnt / tot_actions) * 100.0, 1) if tot_actions > 0 else 0.0
            for act, cnt in arm_action_counts[arm].items()
        }

        benchmark_table[arm] = {
            "cases": n_arm,
            "mean_net_recovery": round(mean_net, 2),
            "mean_gross_recovery": round(tot_gross / n_arm, 2),
            "mean_action_cost": round(tot_act_cost / n_arm, 2),
            "mean_friction_cost": round(tot_fric_cost / n_arm, 2),
            "total_mean_cost": round(tot_cost / n_arm, 2),
            "recovery_rate_pct": round(rec_rate * 100.0, 2),
            "efficiency_ratio": round(eff, 2),
            "unnecessary_interventions_pct": round((arm_unnecessary_counts[arm] / n_arm) * 100.0, 2) if n_arm > 0 else 0.0,
            "mean_regret_vs_oracle": round(mean_oracle_net - mean_net, 2),
            "action_counts": dict(arm_action_counts[arm]),
            "action_percentages": action_pcts,
        }

    # 2. Bootstrap Statistical Testing (2,000 replicates)
    print("\nComputing 2,000 bootstrap replicates for statistical confidence intervals...", flush=True)
    comparisons = [
        ("RECOVERIQ_V4", "BASELINE"),
        ("RECOVERIQ_V4", "RECOVERIQ_V3"),
        ("RECOVERIQ_V4", "CONTROL"),
        ("RECOVERIQ_V3", "BASELINE"),
        ("RECOVERIQ_V3", "RECOVERIQ_V1"),
        ("BASELINE", "CONTROL"),
    ]

    bootstrap_results = {}
    for arm_a, arm_b in comparisons:
        arr_a = list(arm_nets[arm_a])
        arr_b = list(arm_nets[arm_b])
        res: BootstrapResult = compute_bootstrap_difference_ci(
            sample_a=arr_a,
            sample_b=arr_b,
            comparison_name=f"{arm_a} - {arm_b}",
            confidence_level=conf_level,
            iterations=boot_iter,
            seed=boot_seed,
        )
        is_sig = (res.lower_bound > 0 and res.upper_bound > 0) or (res.lower_bound < 0 and res.upper_bound < 0)
        bootstrap_results[f"{arm_a}_vs_{arm_b}"] = {
            "mean_diff": round(res.point_estimate, 2),
            "ci_lower": round(res.lower_bound, 2),
            "ci_upper": round(res.upper_bound, 2),
            "claim_classification": res.claim_classification,
            "is_statistically_significant": is_sig,
            "confidence_level": conf_level,
        }
        sig_str = "SIGNIFICANT" if is_sig else "NOT SIGNIFICANT"
        print(f"  {arm_a} vs {arm_b}: Diff = INR {res.point_estimate:+.2f}/case | 95% CI: [{res.lower_bound:+.2f}, {res.upper_bound:+.2f}] | {res.claim_classification} ({sig_str})", flush=True)

    # 3. Stress Tests across S2 to S6
    print("\nExecuting Stress Tests across Scenarios S2 to S6 (1,000 cases each)...", flush=True)
    stress_scenarios = [
        "S2_LOW_NATURAL_RECOVERY",
        "S3_WEAK_INTERVENTION_EFFECT",
        "S4_STRONG_INTERVENTION_EFFECT",
        "S5_HIGH_RECOVERY_HETEROGENEITY",
        "S6_HIGH_EVENT_FAILURE_RATE",
    ]
    stress_results = {}

    for scen_id in stress_scenarios:
        gen_s = SyntheticCaseGenerator(seed=888111 + len(stress_results))
        cohort_s = gen_s.generate_batch(count=1000, scenario_id=scen_id)
        scen_nets = defaultdict(list)

        for j, (cust, pay, att, case, hidden) in enumerate(cohort_s):
            for test_arm, pol in [("BASELINE", baseline_policy), ("RECOVERIQ_V4", policy_v4), ("CONTROL", None)]:
                c_cust = cust.model_copy(deep=True)
                c_pay = pay.model_copy(deep=True)
                c_att = att.model_copy(deep=True)
                c_case = case.model_copy(deep=True)

                env_s = SimulationEnvironment(scenario_id=scen_id, seed=999000 + j)
                env_s.register_case(c_cust, c_pay, c_att, c_case, hidden)
                case_id = c_case.case_id

                if test_arm == "CONTROL":
                    window_end = c_case.created_at + timedelta(hours=72)
                    env_s.check_natural_recovery_for_control(case_id, as_of_time=window_end)
                    scen_nets["CONTROL"].append(env_s.get_outcome(case_id).recovered_amount)
                else:
                    sim_t = c_att.attempted_at
                    for s_step in range(3):
                        obs = env_s.get_observable_state(case_id, sim_t)
                        if obs.is_terminal: break
                        dec = pol.evaluate(obs, sim_t) if test_arm == "BASELINE" else pol.evaluate_case(obs, sim_t)
                        if dec.selected_action == ActionType.STOP:
                            window_end = c_case.created_at + timedelta(hours=72)
                            env_s.check_natural_recovery_for_control(case_id, as_of_time=window_end)
                            break
                        exec_r, upd_c = env_s.execute_action(case_id, dec.selected_action, sim_t, f"id_{j}_{s_step}", policy_version=test_arm.lower())
                        if upd_c.current_state in [CaseState.RECOVERED, CaseState.STOPPED, CaseState.MANUAL_REVIEW_REQUIRED]: break
                        sim_t += timedelta(hours=14)
                    
                    outcome = env_s.get_outcome(case_id)
                    acts = env_s._actions.get(case_id, [])
                    scen_nets[test_arm].append(outcome.recovered_amount - sum(a.cost + a.friction_cost for a in acts))

        stress_results[scen_id] = {
            "CONTROL_mean_net": round(float(np.mean(scen_nets["CONTROL"])), 2),
            "BASELINE_mean_net": round(float(np.mean(scen_nets["BASELINE"])), 2),
            "RECOVERIQ_V4_mean_net": round(float(np.mean(scen_nets["RECOVERIQ_V4"])), 2),
            "V4_vs_Baseline_diff": round(float(np.mean(scen_nets["RECOVERIQ_V4"]) - np.mean(scen_nets["BASELINE"])), 2),
        }
        print(f"  [{scen_id}] V4: INR {stress_results[scen_id]['RECOVERIQ_V4_mean_net']:.2f} vs Baseline: INR {stress_results[scen_id]['BASELINE_mean_net']:.2f} (Diff: {stress_results[scen_id]['V4_vs_Baseline_diff']:+.2f})", flush=True)

    final_output = {
        "evaluation_metadata": {
            "phase": "Phase 12",
            "date": datetime.now(timezone.utc).isoformat(),
            "evaluation_seed": seed,
            "dataset_size": n_cases,
            "scenario": scenario,
            "bootstrap_iterations": boot_iter,
            "confidence_level": conf_level,
            "duration_seconds": round(sim_duration, 2),
        },
        "financial_benchmark": benchmark_table,
        "bootstrap_hypothesis_testing": bootstrap_results,
        "stress_test_benchmarks": stress_results,
    }

    with open(os.path.join(out_dir, "phase12_benchmark_results.json"), "w") as f:
        json.dump(final_output, f, indent=2)

    print(f"\n[Artifact Saved] {out_dir}/phase12_benchmark_results.json")
    print("Phase 12 Benchmark Complete!", flush=True)
    return final_output

if __name__ == "__main__":
    run_phase12_evaluation()
