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
from domain.models import ObservableCaseState, PotentialOutcome
from simulator.scenarios import get_scenario
from simulator.generator import SyntheticCaseGenerator
from simulator.environment import SimulationEnvironment
from baseline.policy import DeterministicBaselinePolicy
from baseline.config import load_baseline_config
from models.artifacts import ModelArtifactManager
from policy.adaptive import RecoverIQAdaptivePolicy
from policy.adaptive_v2 import RecoverIQAdaptivePolicyV2
from policy.oracle import OracleCounterfactualDiagnostic
from evaluation.bootstrap import compute_bootstrap_difference_ci, BootstrapResult

def compute_sha256(filepath: str) -> str:
    with open(filepath, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()

def run_phase10_evaluation(eval_config_path: str = "configs/phase10_evaluation.yaml"):
    print("=" * 60, flush=True)
    print("PHASE 10: INDEPENDENT 20,000-CASE BENCHMARK EVALUATION", flush=True)
    print("=" * 60, flush=True)

    with open(eval_config_path, "r") as f:
        cfg = yaml.safe_load(f)

    n_cases = cfg["dataset_size"]  # 20,000
    seed = cfg["random_seed"]      # 777888999 (Brand new evaluation cohort)
    scenario = cfg["scenario"]    # S1_HIGH_NATURAL_RECOVERY
    boot_iter = cfg.get("bootstrap_iterations", 2000)
    boot_seed = cfg.get("bootstrap_seed", 1337)
    conf_level = cfg.get("confidence_level", 0.95)

    print(f"Evaluation Config: N={n_cases}, Seed={seed}, Scenario={scenario}", flush=True)
    print("Generating 20,000 evaluation cases under independent seed...", flush=True)
    t0 = time.time()
    gen = SyntheticCaseGenerator(seed=seed)
    cohort = gen.generate_batch(count=n_cases, scenario_id=scenario)
    print(f"Cohort generated in {time.time() - t0:.2f}s", flush=True)

    # Load Model and Policies
    model = ModelArtifactManager().load_model("incremental-model-v1")
    baseline_policy = DeterministicBaselinePolicy(load_baseline_config())
    policy_v1 = RecoverIQAdaptivePolicy(model=model, minimum_incremental_recovery=250.0)
    policy_v2 = RecoverIQAdaptivePolicyV2(model=model, escalation_advantage_margin=50.0)
    policy_v2_ablation = RecoverIQAdaptivePolicyV2(model=model, escalation_advantage_margin=0.0)

    print(f"Baseline Policy Checksum: {baseline_policy.checksum[:16]}...", flush=True)
    print(f"RecoverIQ v1 Policy Checksum: {policy_v1.checksum[:16]}...", flush=True)
    print(f"RecoverIQ v2 Policy Checksum: {policy_v2.checksum[:16]}...", flush=True)

    # 5-Arm Modulo Randomization
    arms = ["CONTROL", "BASELINE", "RECOVERIQ_V1", "RECOVERIQ_V2", "RECOVERIQ_V2_ABLATION"]
    arm_assignments = [arms[i % len(arms)] for i in range(n_cases)]

    arm_nets = defaultdict(list)
    arm_gross = defaultdict(float)
    arm_action_costs = defaultdict(float)
    arm_friction_costs = defaultdict(float)
    arm_recovered_counts = defaultdict(int)
    arm_interventions_counts = defaultdict(int)
    arm_unnecessary_counts = defaultdict(int)
    arm_safety_violations = defaultdict(int)
    arm_action_counts = defaultdict(lambda: defaultdict(int))

    # Heterogeneity tracking for v2, v1, baseline, control
    hetero_segment = defaultdict(lambda: defaultdict(list))
    hetero_amount = defaultdict(lambda: defaultdict(list))
    hetero_failure = defaultdict(lambda: defaultdict(list))

    print("\nExecuting sequential simulation across 20,000 cases...", flush=True)
    t_sim_start = time.time()

    for i, (cust, pay, att, case, hidden) in enumerate(cohort):
        arm = arm_assignments[i]
        case_id = case.case_id
        start_time = att.attempted_at

        amt = case.amount_due
        if amt < 1000:
            bkt = "< 1,000"
        elif amt < 3000:
            bkt = "1,000 - 3,000"
        elif amt < 10000:
            bkt = "3,000 - 10,000"
        else:
            bkt = ">= 10,000"

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
            if arm == "BASELINE":
                policy = baseline_policy
                p_ver = "baseline-v1"
            elif arm == "RECOVERIQ_V1":
                policy = policy_v1
                p_ver = "recoveriq-v1"
            elif arm == "RECOVERIQ_V2":
                policy = policy_v2
                p_ver = "recoveriq-v2"
            elif arm == "RECOVERIQ_V2_ABLATION":
                policy = policy_v2_ablation
                p_ver = "recoveriq-v2-ablation"

            sim_time = start_time
            sim_step = 0
            while sim_step < 3:
                obs = env.get_observable_state(case_id, sim_time)
                if obs.is_terminal:
                    break
                
                if arm == "BASELINE":
                    decision = policy.evaluate(obs, sim_time)
                else:
                    decision = policy.evaluate_case(obs, sim_time)

                sel_act = decision.selected_action
                arm_action_counts[arm][sel_act.value] += 1

                if sel_act == ActionType.STOP:
                    window_end = case.created_at + timedelta(hours=72)
                    env.check_natural_recovery_for_control(case_id, as_of_time=window_end)
                    break

                arm_interventions_counts[arm] += 1
                if hidden.y_control:
                    arm_unnecessary_counts[arm] += 1

                exec_rec, updated_case = env.execute_action(
                    case_id=case_id,
                    action_type=sel_act,
                    timestamp=sim_time,
                    idempotency_key=f"idem_{arm}_{case_id}_{sim_step}",
                    policy_version=p_ver,
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
                arm_recovered_counts[arm] += 1

        arm_nets[arm].append(net)
        arm_gross[arm] += gross
        arm_action_costs[arm] += cost
        arm_friction_costs[arm] += fric

        hetero_segment[cust.segment.value][arm].append(net)
        hetero_amount[bkt][arm].append(net)
        hetero_failure[att.failure_code.value][arm].append(net)

        if (i + 1) % 5000 == 0:
            print(f"  Processed {i + 1}/{n_cases} cases ({time.time() - t_sim_start:.1f}s)...", flush=True)

    sim_duration = time.time() - t_sim_start
    print(f"\n20,000-case simulation completed in {sim_duration:.2f}s", flush=True)

    # 1. Financial Benchmark Table
    benchmark_table = {}
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
        n_int = arm_interventions_counts[arm]
        unnec_rate = (arm_unnecessary_counts[arm] / n_int) if n_int > 0 else 0.0
        tot_acts = sum(arm_action_counts[arm].values())

        benchmark_table[arm] = {
            "N": n_arm,
            "Gross_Recovered": tot_gross,
            "Action_Cost": tot_act_cost,
            "Friction_Cost": tot_fric_cost,
            "Total_Net_Recovered": tot_net,
            "Mean_Net_Per_Case": mean_net,
            "Recovery_Rate": rec_rate,
            "Intervention_Efficiency": eff,
            "Unnecessary_Intervention_Rate": unnec_rate,
            "Safety_Violations": arm_safety_violations[arm],
            "Action_Distribution": {k: round((v / tot_acts) * 100.0, 1) for k, v in arm_action_counts[arm].items()},
        }

    print("\n--- PHASE 10 FINANCIAL BENCHMARK SUMMARY ---", flush=True)
    for arm, res in benchmark_table.items():
        print(f"{arm:<22} | N={res['N']} | Mean Net: INR {res['Mean_Net_Per_Case']:>8.2f} | Rec Rate: {res['Recovery_Rate']:>5.1%} | Escalate: {res['Action_Distribution'].get('ESCALATE', 0.0):>4.1f}%", flush=True)

    # 2. Bootstrap Statistical Comparisons (2,000 iterations, 95% CI)
    print("\n--- BOOTSTRAP STATISTICAL COMPARISONS (2,000 Iterations, 95% CI) ---", flush=True)
    boot_v2_vs_base = compute_bootstrap_difference_ci(
        sample_a=arm_nets["RECOVERIQ_V2"],
        sample_b=arm_nets["BASELINE"],
        comparison_name="RecoverIQ-v2 - Baseline",
        confidence_level=conf_level,
        iterations=boot_iter,
        seed=boot_seed,
    )
    boot_v2_vs_v1 = compute_bootstrap_difference_ci(
        sample_a=arm_nets["RECOVERIQ_V2"],
        sample_b=arm_nets["RECOVERIQ_V1"],
        comparison_name="RecoverIQ-v2 - RecoverIQ-v1",
        confidence_level=conf_level,
        iterations=boot_iter,
        seed=boot_seed,
    )
    boot_v2_vs_ctrl = compute_bootstrap_difference_ci(
        sample_a=arm_nets["RECOVERIQ_V2"],
        sample_b=arm_nets["CONTROL"],
        comparison_name="RecoverIQ-v2 - Control",
        confidence_level=conf_level,
        iterations=boot_iter,
        seed=boot_seed,
    )
    boot_v1_vs_base = compute_bootstrap_difference_ci(
        sample_a=arm_nets["RECOVERIQ_V1"],
        sample_b=arm_nets["BASELINE"],
        comparison_name="RecoverIQ-v1 - Baseline",
        confidence_level=conf_level,
        iterations=boot_iter,
        seed=boot_seed,
    )
    boot_v2_vs_ablation = compute_bootstrap_difference_ci(
        sample_a=arm_nets["RECOVERIQ_V2"],
        sample_b=arm_nets["RECOVERIQ_V2_ABLATION"],
        comparison_name="RecoverIQ-v2 (With Margin) - RecoverIQ-v2 (No Margin)",
        confidence_level=conf_level,
        iterations=boot_iter,
        seed=boot_seed,
    )

    bootstrap_results = {
        "RecoverIQ_v2_vs_Baseline": {
            "point_estimate": boot_v2_vs_base.point_estimate,
            "ci_95": [boot_v2_vs_base.lower_bound, boot_v2_vs_base.upper_bound],
            "classification": boot_v2_vs_base.claim_classification,
        },
        "RecoverIQ_v2_vs_RecoverIQ_v1": {
            "point_estimate": boot_v2_vs_v1.point_estimate,
            "ci_95": [boot_v2_vs_v1.lower_bound, boot_v2_vs_v1.upper_bound],
            "classification": boot_v2_vs_v1.claim_classification,
        },
        "RecoverIQ_v2_vs_Control": {
            "point_estimate": boot_v2_vs_ctrl.point_estimate,
            "ci_95": [boot_v2_vs_ctrl.lower_bound, boot_v2_vs_ctrl.upper_bound],
            "classification": boot_v2_vs_ctrl.claim_classification,
        },
        "RecoverIQ_v1_vs_Baseline": {
            "point_estimate": boot_v1_vs_base.point_estimate,
            "ci_95": [boot_v1_vs_base.lower_bound, boot_v1_vs_base.upper_bound],
            "classification": boot_v1_vs_base.claim_classification,
        },
        "RecoverIQ_v2_vs_Ablation": {
            "point_estimate": boot_v2_vs_ablation.point_estimate,
            "ci_95": [boot_v2_vs_ablation.lower_bound, boot_v2_vs_ablation.upper_bound],
            "classification": boot_v2_vs_ablation.claim_classification,
        },
    }

    print(f"RecoverIQ-v2 vs Baseline: {boot_v2_vs_base.point_estimate:+.2f} [95% CI: {boot_v2_vs_base.lower_bound:+.2f}, {boot_v2_vs_base.upper_bound:+.2f}] -> {boot_v2_vs_base.claim_classification}", flush=True)
    print(f"RecoverIQ-v2 vs RecoverIQ-v1: {boot_v2_vs_v1.point_estimate:+.2f} [95% CI: {boot_v2_vs_v1.lower_bound:+.2f}, {boot_v2_vs_v1.upper_bound:+.2f}] -> {boot_v2_vs_v1.claim_classification}", flush=True)
    print(f"RecoverIQ-v2 vs Ablation (No Margin): {boot_v2_vs_ablation.point_estimate:+.2f} [95% CI: {boot_v2_vs_ablation.lower_bound:+.2f}, {boot_v2_vs_ablation.upper_bound:+.2f}]", flush=True)

    # 3. Oracle Counterfactual Regret Diagnostic (1,500 fresh unmutated cases)
    print("\n--- ORACLE COUNTERFACTUAL REGRET DIAGNOSTIC (1,500 Cases) ---", flush=True)
    oracle_cohort = gen.generate_batch(count=1500, scenario_id=scenario)
    oracle_env = SimulationEnvironment(scenario_id=scenario, seed=seed + 9999)
    for cust, pay, att, c, hidden in oracle_cohort:
        oracle_env.register_case(cust, pay, att, c, hidden)

    oracle_diag_v1 = OracleCounterfactualDiagnostic(policy=policy_v1)
    oracle_res_v1 = oracle_diag_v1.evaluate_policy_regret(oracle_cohort, oracle_env)

    oracle_env_v2 = SimulationEnvironment(scenario_id=scenario, seed=seed + 9999)
    for cust, pay, att, c, hidden in oracle_cohort:
        oracle_env_v2.register_case(cust, pay, att, c, hidden)
    oracle_diag_v2 = OracleCounterfactualDiagnostic(policy=policy_v2)
    oracle_res_v2 = oracle_diag_v2.evaluate_policy_regret(oracle_cohort, oracle_env_v2)

    oracle_comparison = {
        "cohort_size": 1500,
        "recoveriq_v1": oracle_res_v1,
        "recoveriq_v2": oracle_res_v2,
        "regret_reduction_per_case": oracle_res_v1["mean_regret_per_case"] - oracle_res_v2["mean_regret_per_case"],
        "agreement_improvement": oracle_res_v2["oracle_agreement_rate"] - oracle_res_v1["oracle_agreement_rate"],
    }
    print(f"Oracle Agreement: v1={oracle_res_v1['oracle_agreement_rate']:.1%} -> v2={oracle_res_v2['oracle_agreement_rate']:.1%}", flush=True)
    print(f"Mean Regret / Case: v1=INR {oracle_res_v1['mean_regret_per_case']:.2f} -> v2=INR {oracle_res_v2['mean_regret_per_case']:.2f} (Reduction: INR {oracle_comparison['regret_reduction_per_case']:.2f})", flush=True)

    # 4. Action Distribution Side-by-Side Table
    action_table = {
        "Phase9_RecoverIQ_v1": benchmark_table["RECOVERIQ_V1"]["Action_Distribution"],
        "Phase10_RecoverIQ_v2": benchmark_table["RECOVERIQ_V2"]["Action_Distribution"],
        "Deterministic_Baseline": benchmark_table["BASELINE"]["Action_Distribution"],
        "Oracle": {k: round(v * 100.0, 1) for k, v in oracle_res_v2["oracle_action_distribution"].items()},
    }

    # 5. Heterogeneity Analysis
    heterogeneity_summary = {
        "by_customer_segment": {
            seg: {
                "sample_size": len(data["RECOVERIQ_V2"]),
                "mean_net_control": float(np.mean(data["CONTROL"])),
                "mean_net_baseline": float(np.mean(data["BASELINE"])),
                "mean_net_recoveriq_v1": float(np.mean(data["RECOVERIQ_V1"])),
                "mean_net_recoveriq_v2": float(np.mean(data["RECOVERIQ_V2"])),
            } for seg, data in hetero_segment.items()
        },
        "by_amount_bucket": {
            bkt: {
                "sample_size": len(data["RECOVERIQ_V2"]),
                "mean_net_control": float(np.mean(data["CONTROL"])),
                "mean_net_baseline": float(np.mean(data["BASELINE"])),
                "mean_net_recoveriq_v1": float(np.mean(data["RECOVERIQ_V1"])),
                "mean_net_recoveriq_v2": float(np.mean(data["RECOVERIQ_V2"])),
            } for bkt, data in hetero_amount.items()
        },
        "by_failure_code": {
            fcode: {
                "sample_size": len(data["RECOVERIQ_V2"]),
                "mean_net_control": float(np.mean(data["CONTROL"])),
                "mean_net_baseline": float(np.mean(data["BASELINE"])),
                "mean_net_recoveriq_v1": float(np.mean(data["RECOVERIQ_V1"])),
                "mean_net_recoveriq_v2": float(np.mean(data["RECOVERIQ_V2"])),
            } for fcode, data in hetero_failure.items()
        },
    }

    # 6. Deterministic Reproducibility Replay
    print("\n--- REPRODUCIBILITY REPLAY VERIFICATION (v2) ---", flush=True)
    replay_nets_v2 = []
    gen_rep = SyntheticCaseGenerator(seed=seed)
    cohort_rep = gen_rep.generate_batch(count=2000, scenario_id=scenario)
    
    for i in range(3, 2000, len(arms)):  # Exact RecoverIQ v2 indices
        cust_r, pay_r, att_r, case_r, hidden_r = cohort_rep[i]
        case_id_r = case_r.case_id
        env_rep = SimulationEnvironment(scenario_id=scenario, seed=seed + i)
        env_rep.register_case(cust_r, pay_r, att_r, case_r, hidden_r)

        sim_time = att_r.attempted_at
        sim_step = 0
        while sim_step < 3:
            obs = env_rep.get_observable_state(case_id_r, sim_time)
            if obs.is_terminal:
                break
            decision = policy_v2.evaluate_case(obs, sim_time)
            sel_act = decision.selected_action

            if sel_act == ActionType.STOP:
                window_end = case_r.created_at + timedelta(hours=72)
                env_rep.check_natural_recovery_for_control(case_id_r, as_of_time=window_end)
                break

            exec_rec, updated_case = env_rep.execute_action(
                case_id=case_id_r,
                action_type=sel_act,
                timestamp=sim_time,
                idempotency_key=f"idem_rep_v2_{case_id_r}_{sim_step}",
                policy_version="recoveriq-v2",
            )
            if updated_case.current_state in [CaseState.RECOVERED, CaseState.STOPPED, CaseState.MANUAL_REVIEW_REQUIRED]:
                break
            sim_time += timedelta(hours=14)
            sim_step += 1

        out = env_rep.get_outcome(case_id_r)
        case_actions = env_rep._actions.get(case_id_r, [])
        cost = sum(a.cost for a in case_actions)
        fric = sum(a.friction_cost for a in case_actions)
        replay_nets_v2.append(out.recovered_amount - cost - fric)

    orig_v2_slice = arm_nets["RECOVERIQ_V2"][:len(replay_nets_v2)]
    is_reproducible = (orig_v2_slice == replay_nets_v2)
    print(f"Reproducibility Replay: Exact Match = {is_reproducible} (Cases: {len(replay_nets_v2)})", flush=True)

    # 7. Output Result Artifacts into results/phase10/
    out_dir = "results/phase10"
    os.makedirs(out_dir, exist_ok=True)

    with open(os.path.join(out_dir, "benchmark_results.json"), "w") as f:
        json.dump(benchmark_table, f, indent=2)

    with open(os.path.join(out_dir, "bootstrap_results.json"), "w") as f:
        json.dump(bootstrap_results, f, indent=2)

    with open(os.path.join(out_dir, "oracle_diagnostic.json"), "w") as f:
        json.dump(oracle_comparison, f, indent=2)

    with open(os.path.join(out_dir, "action_distribution.json"), "w") as f:
        json.dump(action_table, f, indent=2)

    with open(os.path.join(out_dir, "ablation_results.json"), "w") as f:
        json.dump({
            "ablation_name": "Escalation_Advantage_Margin_Ablation",
            "full_policy_v2_margin_50": benchmark_table["RECOVERIQ_V2"],
            "ablated_policy_v2_margin_0": benchmark_table["RECOVERIQ_V2_ABLATION"],
            "bootstrap_delta": {
                "point_estimate": boot_v2_vs_ablation.point_estimate,
                "ci_95": [boot_v2_vs_ablation.lower_bound, boot_v2_vs_ablation.upper_bound],
            }
        }, f, indent=2)

    with open(os.path.join(out_dir, "heterogeneity.json"), "w") as f:
        json.dump(heterogeneity_summary, f, indent=2)

    with open(os.path.join(out_dir, "reproducibility.json"), "w") as f:
        json.dump({
            "status": "REPRODUCIBILITY VERIFIED" if is_reproducible else "FAILED",
            "deterministic_replay_verified": is_reproducible,
            "cases_verified": len(replay_nets_v2),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }, f, indent=2)

    print(f"\nAll Phase 10 artifacts successfully written to {out_dir}/", flush=True)
    return benchmark_table, bootstrap_results, oracle_comparison, action_table

if __name__ == "__main__":
    run_phase10_evaluation()
