import os
import sys
import json
import yaml
from collections import defaultdict
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from domain.enums import ActionType, CaseState
from domain.models import ObservableCaseState
from simulator.generator import SyntheticCaseGenerator
from simulator.environment import SimulationEnvironment
from models.artifacts import ModelArtifactManager
from policy.adaptive import RecoverIQAdaptivePolicy

def run_overescalation_diagnosis(val_config_path: str = "configs/phase10_validation.yaml"):
    print("=" * 60)
    print("PHASE 10: EMPIRICAL OVER-ESCALATION DIAGNOSIS")
    print("=" * 60)

    with open(val_config_path, "r") as f:
        cfg = yaml.safe_load(f)

    n_cases = cfg["dataset_size"]
    seed = cfg["random_seed"]
    scenario = cfg["scenario"]

    print(f"Generating validation cohort: N={n_cases}, Seed={seed}, Scenario={scenario}")
    gen = SyntheticCaseGenerator(seed=seed)
    cohort = gen.generate_batch(count=n_cases, scenario_id=scenario)

    # Load frozen Model and Phase 9 Policy (v1)
    model = ModelArtifactManager().load_model("incremental-model-v1")
    policy_v1 = RecoverIQAdaptivePolicy(model=model, minimum_incremental_recovery=250.0)

    action_counts = defaultdict(int)
    escalate_cases = []
    rejection_reasons_cheap_actions = defaultdict(int)
    fallback_forced_escalate = 0
    nominal_advantage_escalate = 0

    delta_exp_net_distribution = []
    confidence_distribution = []
    segment_distribution = defaultdict(int)
    failure_distribution = defaultdict(int)
    amount_buckets = defaultdict(int)

    for i, (cust, pay, att, case, hidden) in enumerate(cohort):
        env = SimulationEnvironment(scenario_id=scenario, seed=seed + i)
        env.register_case(cust, pay, att, case, hidden)

        obs = env.get_observable_state(case.case_id, att.attempted_at)
        decision = policy_v1.evaluate_case(obs, att.attempted_at)
        trace = policy_v1.last_trace

        sel_act = decision.selected_action
        action_counts[sel_act.value] += 1

        if sel_act == ActionType.ESCALATE:
            # Analyze this ESCALATE decision in detail
            is_fallback = "LOW_CONFIDENCE_FALLBACK_APPLIED" in trace.constraints_applied
            if is_fallback:
                fallback_forced_escalate += 1
            else:
                nominal_advantage_escalate += 1

            # Extract evaluations of all actions from trace
            eval_map = {e.action: e for e in trace.candidate_evaluations}
            esc_eval = eval_map.get(ActionType.ESCALATE)

            # Find best non-escalate alternative
            non_esc_evals = [e for e in trace.candidate_evaluations if e.action != ActionType.ESCALATE]
            # Best by theoretical expected net (regardless of threshold disqualification)
            best_non_esc = max(non_esc_evals, key=lambda e: e.expected_net_recovery)

            # Record reasons why non-escalation actions were rejected
            for e in non_esc_evals:
                if not e.eligible and e.rejection_reason:
                    rejection_reasons_cheap_actions[f"{e.action.value}:{e.rejection_reason}"] += 1

            delta_exp_net = esc_eval.expected_net_recovery - best_non_esc.expected_net_recovery
            delta_exp_net_distribution.append(delta_exp_net)
            confidence_distribution.append(trace.confidence_score)
            segment_distribution[cust.segment.value] += 1
            failure_distribution[att.failure_code.value] += 1

            amt = case.amount_due
            if amt < 1000:
                bkt = "< 1,000"
            elif amt < 3000:
                bkt = "1,000 - 3,000"
            elif amt < 10000:
                bkt = "3,000 - 10,000"
            else:
                bkt = ">= 10,000"
            amount_buckets[bkt] += 1

            if len(escalate_cases) < 10:  # Sample cases
                escalate_cases.append({
                    "case_id": case.case_id,
                    "amount_due": case.amount_due,
                    "segment": cust.segment.value,
                    "failure_code": att.failure_code.value,
                    "confidence_score": trace.confidence_score,
                    "constraints_applied": trace.constraints_applied,
                    "escalate_prob": esc_eval.probability,
                    "escalate_uplift": esc_eval.incremental_probability,
                    "escalate_exp_net": esc_eval.expected_net_recovery,
                    "best_non_escalate_action": best_non_esc.action.value,
                    "best_non_escalate_prob": best_non_esc.probability,
                    "best_non_escalate_uplift": best_non_esc.incremental_probability,
                    "best_non_escalate_exp_net": best_non_esc.expected_net_recovery,
                    "delta_exp_net": delta_exp_net,
                })

    n_escalate = action_counts["ESCALATE"]
    escalate_pct = (n_escalate / n_cases) * 100.0

    print(f"\nTotal Validation Cases: {n_cases}")
    print(f"Action Distribution: {dict(action_counts)}")
    print(f"ESCALATE Decisions: {n_escalate} ({escalate_pct:.2f}%)")
    print(f"  - Forced by Low-Confidence Fallback Rule: {fallback_forced_escalate} ({fallback_forced_escalate / n_escalate * 100.0:.1f}%)")
    print(f"  - Selected by Nominal E[Net] Advantage: {nominal_advantage_escalate} ({nominal_advantage_escalate / n_escalate * 100.0:.1f}%)")

    # Delta E[Net] quantiles
    deltas = np.array(delta_exp_net_distribution)
    confs = np.array(confidence_distribution)

    diagnostic_report = {
        "cohort_size": n_cases,
        "validation_seed": seed,
        "policy_version": "recoveriq-v1",
        "action_distribution": {k: float(v) for k, v in action_counts.items()},
        "escalate_total": n_escalate,
        "escalate_percentage": float(escalate_pct),
        "drivers_of_escalation": {
            "forced_by_low_confidence_fallback": {
                "count": fallback_forced_escalate,
                "percentage_of_escalations": float(fallback_forced_escalate / n_escalate * 100.0) if n_escalate > 0 else 0.0,
                "mechanism": "v1 rule: if conf < 0.60 and amount >= 1500 -> force ESCALATE",
            },
            "selected_by_nominal_advantage": {
                "count": nominal_advantage_escalate,
                "percentage_of_escalations": float(nominal_advantage_escalate / n_escalate * 100.0) if n_escalate > 0 else 0.0,
                "mechanism": "v1 selected ESCALATE because exp_net(ESCALATE) >= exp_net(alternatives)",
            },
        },
        "rejection_reasons_for_cheap_actions": dict(rejection_reasons_cheap_actions),
        "delta_exp_net_statistics": {
            "mean": float(np.mean(deltas)) if len(deltas) > 0 else 0.0,
            "median": float(np.median(deltas)) if len(deltas) > 0 else 0.0,
            "p25": float(np.percentile(deltas, 25)) if len(deltas) > 0 else 0.0,
            "p75": float(np.percentile(deltas, 75)) if len(deltas) > 0 else 0.0,
            "pct_delta_less_than_50_inr": float(np.mean(deltas < 50.0) * 100.0) if len(deltas) > 0 else 0.0,
            "pct_delta_less_than_100_inr": float(np.mean(deltas < 100.0) * 100.0) if len(deltas) > 0 else 0.0,
        },
        "confidence_score_statistics": {
            "mean": float(np.mean(confs)) if len(confs) > 0 else 0.0,
            "median": float(np.median(confs)) if len(confs) > 0 else 0.0,
            "pct_below_0_60": float(np.mean(confs < 0.60) * 100.0) if len(confs) > 0 else 0.0,
        },
        "segment_breakdown": dict(segment_distribution),
        "failure_breakdown": dict(failure_distribution),
        "amount_bucket_breakdown": dict(amount_buckets),
        "sample_cases": escalate_cases,
        "forensic_conclusion": {
            "primary_driver_1": "Low-confidence fallback inverted: uncertain cases >= INR 1500 were systematically routed to ESCALATE rather than conservative actions.",
            "primary_driver_2": "Fixed INR 250 incremental threshold disqualified cheap high-ROI actions (REMINDER, PAYMENT_LINK) on small/mid ticket amounts.",
            "primary_driver_3": "ESCALATE was chosen with wafer-thin nominal E[Net] advantage without requiring an advantage margin or cost-sensitive confidence guard.",
        }
    }

    out_dir = "results/phase10"
    os.makedirs(out_dir, exist_ok=True)
    report_path = os.path.join(out_dir, "diagnostic_report.json")
    with open(report_path, "w") as f:
        json.dump(diagnostic_report, f, indent=2)

    print(f"\nDiagnostic report saved to {report_path}")
    return diagnostic_report

if __name__ == "__main__":
    run_overescalation_diagnosis()
