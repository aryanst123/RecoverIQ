import os
import sys
import json
import numpy as np
from datetime import datetime, timezone
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evaluation.runner import ExperimentRunner
from domain.enums import EvaluationArm, ActionType
from simulator.generator import SyntheticCaseGenerator
from simulator.environment import SimulationEnvironment
from models.artifacts import ModelArtifactManager
from baseline.policy import DeterministicBaselinePolicy
from baseline.config import load_baseline_config
from policy.adaptive import RecoverIQAdaptivePolicy
from policy.oracle import OracleCounterfactualDiagnostic
from policy.ablations import PolicyAblationHarness

def main():
    print("=== 1. RUNNING PHASE 6 3-ARM BENCHMARK ===")
    runner = ExperimentRunner(config_path="configs/evaluation.yaml")
    results = runner.run_experiment()

    metrics = results["metrics_by_arm"]
    ctrl = metrics[EvaluationArm.ARM_A_CONTROL.value]
    base = metrics[EvaluationArm.ARM_B_BASELINE.value]
    riq = metrics[EvaluationArm.ARM_C_RECOVERIQ.value]

    print("\n--- BENCHMARK RESULTS ---")
    print(f"CONTROL: Total Net: INR {ctrl.total_net_recovered:,.2f} | Mean Net: INR {ctrl.mean_net_recovered:.2f} | Recovery Rate: {ctrl.recovery_rate:.1%} | Efficiency: {ctrl.intervention_efficiency:.2f} | Unnecessary: {ctrl.unnecessary_intervention_rate:.1%} | Violations: {ctrl.critical_safety_violations}")
    print(f"BASELINE: Total Net: INR {base.total_net_recovered:,.2f} | Mean Net: INR {base.mean_net_recovered:.2f} | Recovery Rate: {base.recovery_rate:.1%} | Efficiency: {base.intervention_efficiency:.2f} | Unnecessary: {base.unnecessary_intervention_rate:.1%} | Violations: {base.critical_safety_violations}")
    print(f"RECOVERIQ: Total Net: INR {riq.total_net_recovered:,.2f} | Mean Net: INR {riq.mean_net_recovered:.2f} | Recovery Rate: {riq.recovery_rate:.1%} | Efficiency: {riq.intervention_efficiency:.2f} | Unnecessary: {riq.unnecessary_intervention_rate:.1%} | Violations: {riq.critical_safety_violations}")

    boot_primary = results["bootstrap_results"]["primary"]
    print(f"\nPRIMARY DELTA (RecoverIQ - Baseline): Mean Diff: INR {boot_primary.point_estimate:.2f} | 95% CI: [{boot_primary.lower_bound:.2f}, {boot_primary.upper_bound:.2f}] | Classification: {boot_primary.claim_classification}")

    boot_base_ctrl = results["bootstrap_results"]["baseline_vs_control"]
    print(f"BASELINE VS CONTROL DELTA: Mean Diff: INR {boot_base_ctrl.point_estimate:.2f} | 95% CI: [{boot_base_ctrl.lower_bound:.2f}, {boot_base_ctrl.upper_bound:.2f}] | Classification: {boot_base_ctrl.claim_classification}")

    print("\n=== 2. ACTION DISTRIBUTION & HETEROGENEITY ===")
    model = ModelArtifactManager().load_model("incremental-model-v1")
    policy = RecoverIQAdaptivePolicy(model=model, minimum_incremental_recovery=250.0)
    baseline = DeterministicBaselinePolicy(load_baseline_config())

    gen = SyntheticCaseGenerator(seed=20260902)
    cohort = gen.generate_batch(count=1500, scenario_id="S1_HIGH_NATURAL_RECOVERY")
    env = SimulationEnvironment(scenario_id="S1_HIGH_NATURAL_RECOVERY", seed=20260902)
    for cust, pay, att, c, hidden in cohort:
        env.register_case(cust, pay, att, c, hidden)

    actions_riq = defaultdict(int)
    actions_base = defaultdict(int)
    hetero_segment = defaultdict(lambda: defaultdict(int))
    hetero_failure = defaultdict(lambda: defaultdict(int))
    hetero_amount = defaultdict(lambda: defaultdict(int))

    states = []
    for cust, pay, att, c, hidden in cohort:
        st = env.get_observable_state(c.case_id, att.attempted_at)
        states.append(st)

        # Baseline decision
        b_dec = baseline.evaluate(st)
        actions_base[b_dec.selected_action.value] += 1

        # RecoverIQ decision
        r_dec = policy.evaluate_case(st)
        r_act = r_dec.selected_action.value
        actions_riq[r_act] += 1

        # Heterogeneity logging
        seg = st.customer_segment.value
        hetero_segment[seg][r_act] += 1

        fc = st.failure_code.value
        hetero_failure[fc][r_act] += 1

        amt = st.residual_amount
        if amt < 1000:
            bucket = "< 1,000"
        elif amt < 3000:
            bucket = "1,000 - 3,000"
        elif amt < 10000:
            bucket = "3,000 - 10,000"
        else:
            bucket = ">= 10,000"
        hetero_amount[bucket][r_act] += 1

    total_n = len(cohort)
    print("\n--- ACTION DISTRIBUTION (%) ---")
    print("Action | Baseline | RecoverIQ")
    for act in ["STOP", "REMINDER", "PAYMENT_LINK", "PROMISE_TO_PAY", "ESCALATE"]:
        bp = (actions_base[act] / total_n) * 100.0
        rp = (actions_riq[act] / total_n) * 100.0
        print(f"{act:15} | {bp:7.1f}% | {rp:7.1f}%")

    print("\n--- HETEROGENEITY: RECOVERIQ BY CUSTOMER SEGMENT (%) ---")
    for seg, counts in hetero_segment.items():
        tot = sum(counts.values())
        print(f"{seg:12}: " + ", ".join(f"{k}: {(v/tot)*100.0:.1f}%" for k, v in counts.items()))

    print("\n--- HETEROGENEITY: RECOVERIQ BY AMOUNT BUCKET (%) ---")
    for bkt, counts in hetero_amount.items():
        tot = sum(counts.values())
        print(f"{bkt:15}: " + ", ".join(f"{k}: {(v/tot)*100.0:.1f}%" for k, v in counts.items()))

    print("\n=== 3. POLICY ABLATIONS (COMPREHENSIVE METRICS) ===")
    ablation_harness = PolicyAblationHarness(adaptive_policy=policy, baseline_policy=baseline)
    ablation_results = ablation_harness.run_comprehensive_ablations(cohort, env)
    for variant, metrics_dict in ablation_results.items():
        print(f"\n[{variant}]")
        print(f"  Gross Recovered: INR {metrics_dict['gross_recovered']:,.2f}")
        print(f"  Total Net Recovered: INR {metrics_dict['net_recovered']:,.2f}")
        print(f"  Mean Net / Case: INR {metrics_dict['mean_net_recovered']:.2f}")
        print(f"  Action Cost: INR {metrics_dict['action_cost']:,.2f} | Friction Cost: INR {metrics_dict['friction_cost']:,.2f}")
        print(f"  Recovery Rate: {metrics_dict['recovery_rate']:.1%}")
        print(f"  Intervention Efficiency: {metrics_dict['intervention_efficiency']:.2f}")
        print(f"  Unnecessary Intervention Rate: {metrics_dict['unnecessary_intervention_rate']:.1%}")
        print(f"  Safety Violations: {metrics_dict['safety_violations']}")
        print(f"  Action Dist (%): {metrics_dict['action_distribution']}")

    print("\n=== 4. SIMULATOR-ONLY ORACLE DIAGNOSTIC & REGRET ===")
    oracle_diag = OracleCounterfactualDiagnostic(policy=policy)
    oracle_report = oracle_diag.evaluate_policy_regret(cohort, env)
    print(f"Diagnostic Type: {oracle_report['diagnostic_type']}")
    print(f"Cohort Size: {oracle_report['cohort_size']}")
    print(f"Oracle Top-Action Agreement Rate: {oracle_report['oracle_agreement_rate']:.1%}")
    print(f"Mean Policy Regret Per Case: INR {oracle_report['mean_regret_per_case']:.2f}")
    print(f"Oracle Action Dist: {oracle_report['oracle_action_distribution']}")
    print(f"Policy Action Dist: {oracle_report['policy_action_distribution']}")

if __name__ == "__main__":
    main()
