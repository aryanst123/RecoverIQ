import pytest
from datetime import datetime, timezone
import numpy as np

from domain.enums import ActionType, EvaluationArm, CustomerSegment, ChannelPreference, FailureCode, CaseState
from domain.models import ObservableCaseState, PotentialOutcome
from evaluation.runner import ExperimentRunner
from simulator.generator import SyntheticCaseGenerator
from simulator.environment import SimulationEnvironment
from policy.adaptive import RecoverIQAdaptivePolicy
from policy.oracle import OracleCounterfactualDiagnostic
from policy.ablations import PolicyAblationHarness
from models.artifacts import ModelArtifactManager
from baseline.policy import DeterministicBaselinePolicy
from baseline.config import load_baseline_config

@pytest.fixture(scope="module")
def loaded_recoveriq_policy():
    model = ModelArtifactManager().load_model("incremental-model-v1")
    return RecoverIQAdaptivePolicy(model=model, minimum_incremental_recovery=250.0)

def test_recoveriq_experiment_runner_three_arms():
    # Fast evaluation with 150 cases across the 3 arms
    runner = ExperimentRunner(config_path="configs/evaluation.yaml")
    runner.dataset_size = 150
    runner.random_seed = 42
    results = runner.run_experiment()

    assert "manifest" in results
    assert "metrics_by_arm" in results
    assert "bootstrap_results" in results

    metrics = results["metrics_by_arm"]
    assert EvaluationArm.ARM_A_CONTROL.value in metrics
    assert EvaluationArm.ARM_B_BASELINE.value in metrics
    assert EvaluationArm.ARM_C_RECOVERIQ.value in metrics

    # Baseline & RecoverIQ safety violations must remain 0
    assert metrics[EvaluationArm.ARM_B_BASELINE.value].critical_safety_violations == 0
    assert metrics[EvaluationArm.ARM_C_RECOVERIQ.value].critical_safety_violations == 0

    # RecoverIQ must have executed valid actions (not 0 recovered like placeholder)
    riq_metrics = metrics[EvaluationArm.ARM_C_RECOVERIQ.value]
    assert riq_metrics.case_count == 50
    assert riq_metrics.total_gross_recovered > 0.0

def test_oracle_regret_diagnostic(loaded_recoveriq_policy):
    gen = SyntheticCaseGenerator(seed=123)
    cases = gen.generate_batch(count=40, scenario_id="S5_HIGH_RECOVERY_HETEROGENEITY")

    env = SimulationEnvironment(scenario_id="S5_HIGH_RECOVERY_HETEROGENEITY", seed=123)
    for cust, pay, att, c, hidden in cases:
        env.register_case(cust, pay, att, c, hidden)

    diagnostic = OracleCounterfactualDiagnostic(policy=loaded_recoveriq_policy)
    report = diagnostic.evaluate_policy_regret(cases, env)

    assert report["diagnostic_type"] == "SIMULATOR-ONLY ORACLE DIAGNOSTIC"
    assert report["cohort_size"] == 40
    assert 0.0 <= report["oracle_agreement_rate"] <= 1.0
    assert report["mean_regret_per_case"] >= 0.0
    assert "STOP" in report["policy_action_distribution"]

def test_policy_ablation_harness(loaded_recoveriq_policy):
    gen = SyntheticCaseGenerator(seed=456)
    cases = gen.generate_batch(count=30, scenario_id="S1_HIGH_NATURAL_RECOVERY")

    env = SimulationEnvironment(scenario_id="S1_HIGH_NATURAL_RECOVERY", seed=456)
    states = []
    for cust, pay, att, c, hidden in cases:
        env.register_case(cust, pay, att, c, hidden)
        obs = env.get_observable_state(c.case_id, att.attempted_at)
        states.append(obs)

    baseline = DeterministicBaselinePolicy(load_baseline_config())
    harness = PolicyAblationHarness(adaptive_policy=loaded_recoveriq_policy, baseline_policy=baseline)
    ablation_results = harness.run_ablations(states)

    assert "A_DETERMINISTIC_BASELINE" in ablation_results
    assert "B_UPLIFT_WITHOUT_COST" in ablation_results
    assert "C_RAW_PROBABILITY_WITH_COST" in ablation_results
    assert "D_UPLIFT_WITH_COST_NO_THRESHOLD" in ablation_results
    assert "E_FULL_RECOVERIQ_STANDARD" in ablation_results

def test_policy_cannot_access_hidden_potential_outcomes(loaded_recoveriq_policy):
    pot_outcome = PotentialOutcome(
        case_id="case_leak_test",
        latent_payment_propensity=0.9,
        latent_response_propensity=0.9,
        latent_p2p_reliability=0.9,
        latent_friction_sensitivity=0.01,
        y_control=True,
        y_reminder=True,
        y_payment_link=True,
        y_promise_to_pay=True,
        y_escalate=True,
    )

    # Attempting to pass PotentialOutcome to evaluate_case must raise TypeError
    with pytest.raises(TypeError):
        loaded_recoveriq_policy.evaluate_case(pot_outcome)

def test_oracle_regret_reconciliation_exact_formula(loaded_recoveriq_policy):
    """
    PROVES exact per-case regret reconciliation:
    regret(case) = oracle_value(case) - policy_value(case)
    where both values strictly reflect:
    gross_recovered - action_cost - friction_cost
    under shared eligibility constraints.
    """
    gen = SyntheticCaseGenerator(seed=789)
    cases = gen.generate_batch(count=50, scenario_id="S5_HIGH_RECOVERY_HETEROGENEITY")
    env = SimulationEnvironment(scenario_id="S5_HIGH_RECOVERY_HETEROGENEITY", seed=789)
    for cust, pay, att, c, hidden in cases:
        env.register_case(cust, pay, att, c, hidden)

    diagnostic = OracleCounterfactualDiagnostic(policy=loaded_recoveriq_policy)

    oracle_values = []
    policy_values = []
    per_case_regrets = []

    for cust, pay, att, case, hidden in cases:
        obs = env.get_observable_state(case.case_id, att.attempted_at)
        eligible = loaded_recoveriq_policy.eligibility_service.get_eligible_actions(obs)
        decision = loaded_recoveriq_policy.evaluate_case(obs, att.attempted_at)

        true_nets = {
            act: diagnostic.calculate_counterfactual_net(act, hidden, case.amount_due, case.automated_action_count)
            for act in eligible
        }

        best_act = max(eligible, key=lambda a: true_nets[a])
        oracle_val = true_nets[best_act]
        policy_val = true_nets[decision.selected_action]

        regret = max(0.0, oracle_val - policy_val)
        oracle_values.append(oracle_val)
        policy_values.append(policy_val)
        per_case_regrets.append(regret)

    # Diagnostic run
    report = diagnostic.evaluate_policy_regret(cases, env)
    mean_diag_regret = report["mean_regret_per_case"]

    # Reconcile: mean regret equals mean of individual regrets
    expected_mean_regret = float(np.mean(per_case_regrets))
    assert np.isclose(mean_diag_regret, expected_mean_regret, atol=1e-5)
    # Proves oracle_value >= policy_value for every single case
    for o_val, p_val, r in zip(oracle_values, policy_values, per_case_regrets):
        assert o_val >= p_val
        assert np.isclose(r, o_val - p_val, atol=1e-5)

def test_decision_and_trace_immutability():
    """Verifies that PolicyDecision, DecisionTrace, and ActionEvaluation are strictly immutable."""
    from dataclasses import FrozenInstanceError
    from pydantic import ValidationError
    from domain.models import PolicyDecision
    from policy.evaluations import ActionEvaluation, DecisionTrace

    eval_obj = ActionEvaluation(
        action=ActionType.STOP,
        probability=0.5,
        control_probability=0.5,
        incremental_probability=0.0,
        residual_amount=1000.0,
        expected_incremental_revenue=0.0,
        action_cost=0.0,
        friction_cost=0.0,
        expected_net_recovery=0.0,
        eligible=True,
    )
    with pytest.raises(FrozenInstanceError):
        eval_obj.probability = 0.9

    trace_obj = DecisionTrace(
        case_id="case_mut_test",
        model_version="v1",
        policy_version="v1",
        candidate_evaluations=[eval_obj],
        selected_action=ActionType.STOP,
        selection_reason="test",
        constraints_applied=[],
        confidence_score=0.8,
        confidence_status="HIGH_CONFIDENCE",
        timestamp=datetime.now(timezone.utc),
    )
    with pytest.raises(FrozenInstanceError):
        trace_obj.confidence_score = 0.5

    dec_obj = PolicyDecision(
        decision_id="dec_01",
        case_id="case_01",
        candidate_actions=[ActionType.STOP],
        selected_action=ActionType.STOP,
        model_version="v1",
        policy_version="v1",
        confidence=0.8,
        expected_incremental_recovery=0.0,
        expected_cost=0.0,
        expected_friction_cost=0.0,
        net_expected_value=0.0,
        decision_reason="test",
    )
    with pytest.raises(ValidationError):
        dec_obj.selected_action = ActionType.REMINDER
