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
