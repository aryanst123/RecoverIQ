import pytest
import numpy as np
from datetime import datetime, timezone
from domain.enums import ActionType, EvaluationArm, CaseState, PaymentStatus
from domain.models import ObservableCaseState
from policy.eligibility import CandidateActionService
from evaluation.runner import ExperimentRunner
from evaluation.metrics import CaseEvaluationResult, compute_arm_metrics
from evaluation.bootstrap import compute_bootstrap_difference_ci
from evaluation.attribution import evaluate_attribution_sensitivity
from evaluation.manifest import create_experiment_manifest, compute_file_checksum
from evaluation.policies import ControlPolicy, PlaceholderRecoverIQPolicy
from simulator.generator import SyntheticCaseGenerator

def test_randomization_deterministic_and_independent():
    # Verify that assignment is 100% deterministic given the same seed
    runner1 = ExperimentRunner(config_path="configs/evaluation.yaml")
    runner2 = ExperimentRunner(config_path="configs/evaluation.yaml")

    # Run small experiments
    runner1.dataset_size = 30
    runner2.dataset_size = 30

    res1 = runner1.run_experiment()
    res2 = runner2.run_experiment()

    arms1 = [r.arm for r in res1["case_results"]]
    arms2 = [r.arm for r in res2["case_results"]]
    assert arms1 == arms2

    # Check balanced membership across 3 arms
    counts1 = {arm: arms1.count(arm) for arm in set(arms1)}
    assert EvaluationArm.ARM_A_CONTROL.value in counts1
    assert EvaluationArm.ARM_B_BASELINE.value in counts1
    assert EvaluationArm.ARM_C_RECOVERIQ.value in counts1
    assert counts1[EvaluationArm.ARM_A_CONTROL.value] == 10
    assert counts1[EvaluationArm.ARM_B_BASELINE.value] == 10
    assert counts1[EvaluationArm.ARM_C_RECOVERIQ.value] == 10

def test_control_arm_zero_outreach_and_natural_recovery():
    runner = ExperimentRunner(config_path="configs/evaluation.yaml")
    runner.dataset_size = 60
    results = runner.run_experiment()

    ctrl_cases = [r for r in results["case_results"] if r.arm == EvaluationArm.ARM_A_CONTROL.value]
    assert len(ctrl_cases) == 20

    # Assert control NEVER takes automated interventions
    for c in ctrl_cases:
        assert c.intervention_cost == 0.0
        assert c.friction_cost == 0.0
        assert c.actions_taken == [ActionType.STOP.value]

    # In S1 (high natural recovery), natural recoveries MUST occur in control
    ctrl_metrics = results["metrics_by_arm"][EvaluationArm.ARM_A_CONTROL.value]
    assert ctrl_metrics.total_gross_recovered > 0.0
    assert ctrl_metrics.recovery_rate > 0.0

def test_symmetry_contract_enforcement():
    svc = CandidateActionService()
    now = datetime.now(timezone.utc)

    # Opted-out customer
    opt_state = ObservableCaseState(
        case_id="case_sym_01",
        payment_id="pay_01",
        customer_id="cust_01",
        customer_segment="STANDARD",
        customer_channel_preference="WHATSAPP",
        customer_opt_out=True,
        amount_due=1000.0,
        residual_amount=1000.0,
        current_state=CaseState.ACTION_EVALUATION,
        failure_code="AUTHENTICATION_FAILED",
        failure_reason="Failed",
        attempt_count=1,
        automated_action_count=0,
        hours_since_failure=1.0,
        is_terminal=False,
    )
    eligible = svc.get_eligible_actions(opt_state)
    assert eligible == [ActionType.STOP]

    # Action limit reached
    limit_state = opt_state.model_copy(update={"customer_opt_out": False, "automated_action_count": 3})
    assert svc.get_eligible_actions(limit_state) == [ActionType.STOP]

    # Normal case: P2P, Link, Reminder all available symmetrically
    normal_state = opt_state.model_copy(update={"customer_opt_out": False, "automated_action_count": 0, "residual_amount": 2000.0})
    normal_actions = svc.get_eligible_actions(normal_state)
    assert ActionType.REMINDER in normal_actions
    assert ActionType.PAYMENT_LINK in normal_actions
    assert ActionType.PROMISE_TO_PAY in normal_actions
    assert ActionType.ESCALATE in normal_actions

def test_metrics_computations():
    cases = [
        CaseEvaluationResult(
            case_id="c1",
            arm="ARM_TEST",
            starting_amount=1000.0,
            recovered_amount=1000.0,
            gross_recovered=1000.0,
            intervention_cost=3.0,
            friction_cost=0.0,
            net_recovered=997.0,
            actions_taken=["PAYMENT_LINK"],
            final_state="RECOVERED",
            recovery_timestamp=None,
            attribution_classification="ATTRIBUTED",
            safety_violations=[],
            experiment_id="exp1",
            would_recover_naturally=False,
        ),
        CaseEvaluationResult(
            case_id="c2",
            arm="ARM_TEST",
            starting_amount=500.0,
            recovered_amount=0.0,
            gross_recovered=0.0,
            intervention_cost=2.0,
            friction_cost=0.0,
            net_recovered=-2.0,
            actions_taken=["REMINDER"],
            final_state="STOPPED",
            recovery_timestamp=None,
            attribution_classification="UNRECOVERED",
            safety_violations=[],
            experiment_id="exp1",
            would_recover_naturally=False,
        ),
    ]
    metrics = compute_arm_metrics(cases, "ARM_TEST")
    assert metrics.case_count == 2
    assert metrics.total_gross_recovered == 1000.0
    assert metrics.total_cost == 5.0
    assert metrics.total_net_recovered == 995.0
    assert metrics.recovery_rate == 0.5
    assert metrics.critical_safety_violations == 0

def test_bootstrap_confidence_intervals():
    # Deterministic test: sample A strictly outperforms sample B
    sample_a = [100.0, 110.0, 105.0, 95.0, 102.0] * 20 # Mean ~ 102.4
    sample_b = [10.0, 15.0, 12.0, 8.0, 11.0] * 20      # Mean ~ 11.2

    b_res = compute_bootstrap_difference_ci(
        sample_a=sample_a,
        sample_b=sample_b,
        iterations=500,
        seed=42,
        safety_violations_arm_a=0,
    )
    assert b_res.point_estimate > 80.0
    assert b_res.lower_bound > 0.0
    assert b_res.claim_classification == "STATISTICALLY_SIGNIFICANT_POSITIVE"

    # Inconclusive case where intervals cross zero
    sample_c = [50.0, 40.0, 60.0] * 20
    sample_d = [52.0, 38.0, 58.0] * 20
    b_res_inconclusive = compute_bootstrap_difference_ci(
        sample_a=sample_c,
        sample_b=sample_d,
        iterations=500,
        seed=42,
    )
    assert b_res_inconclusive.lower_bound <= 0.0 <= b_res_inconclusive.upper_bound
    assert b_res_inconclusive.claim_classification == "INCONCLUSIVE"

def test_attribution_sensitivity_analysis():
    cases = [
        CaseEvaluationResult(
            case_id="c1",
            arm="ARM_B",
            starting_amount=1000.0,
            recovered_amount=1000.0,
            gross_recovered=1000.0,
            intervention_cost=3.0,
            friction_cost=0.0,
            net_recovered=997.0,
            actions_taken=["PAYMENT_LINK"],
            final_state="RECOVERED",
            recovery_timestamp="2026-03-01T15:00:00Z",
            attribution_classification="ATTRIBUTED",
            safety_violations=[],
            experiment_id="exp1",
        )
    ]
    times = {"c1": 6.0} # Recovered in 6 hours
    rep = evaluate_attribution_sensitivity(cases, times, windows=[24, 72, 168], primary_window=72)
    assert rep.primary_window_hours == 72
    assert rep.rankings_consistent is True
    assert rep.results_by_window[24]["ARM_B"].total_recovered == 1000.0
    assert rep.results_by_window[72]["ARM_B"].total_recovered == 1000.0

def test_experiment_manifest_generation():
    manifest = create_experiment_manifest(
        experiment_id="exp_test_01",
        experiment_name="test_run",
        seed=2026,
        dataset_size=100,
        scenario_id="S1_HIGH_NATURAL_RECOVERY",
        baseline_version="baseline-v1",
        baseline_checksum="b2b1fab7f9638e35c06952ab6a8fa3690d386b7a392d9ed4c4fa6234d0aa1754",
    )
    assert manifest.dataset_size == 100
    assert len(manifest.baseline_checksum) == 64
    assert "contract" in manifest.config_checksums

def test_holdout_generator_scale_and_reproducibility():
    gen = SyntheticCaseGenerator(seed=999888777)
    # Generate batch of cases
    cases = gen.generate_batch(50, scenario_id="S1_HIGH_NATURAL_RECOVERY")
    assert len(cases) == 50
    # Check that amounts, ids, and potential outcomes are populated
    for _, pay, _, case, pot in cases:
        assert pay.amount > 0.0
        assert case.amount_due == pay.amount
        assert isinstance(pot.y_control, bool)
