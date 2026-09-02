import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional
import numpy as np
import yaml

from domain.enums import (
    ActionType,
    CaseState,
    EvaluationArm,
    PaymentStatus,
    ExecutionStatus,
)
from domain.models import ObservableCaseState
from simulator.generator import SyntheticCaseGenerator
from simulator.environment import SimulationEnvironment
from simulator.scenarios import get_scenario
from baseline.policy import DeterministicBaselinePolicy
from baseline.config import load_baseline_config
from policy.eligibility import CandidateActionService
from evaluation.policies import ControlPolicy, PlaceholderRecoverIQPolicy
from evaluation.metrics import (
    CaseEvaluationResult,
    ArmMetrics,
    compute_arm_metrics,
)
from evaluation.bootstrap import compute_bootstrap_difference_ci, BootstrapResult
from evaluation.attribution import evaluate_attribution_sensitivity, AttributionSensitivityReport
from evaluation.manifest import create_experiment_manifest, ExperimentManifest

class ExperimentRunner:
    """
    EXPERIMENTAL BENCHMARK RUNNER.
    Executes randomized 3-arm trials (Control vs Deterministic Baseline vs RecoverIQ),
    enforces symmetric constraints, computes primary metric (Delta Net),
    calculates 95% Bootstrap CIs, and validates secondary metrics.
    """
    def __init__(self, config_path: str = "configs/evaluation.yaml"):
        self.config_path = config_path
        self._load_config(config_path)
        self.eligibility_service = CandidateActionService(
            max_automated_actions=self.max_automated_actions,
            recovery_window_hours=self.recovery_window_hours,
            min_cooldown_hours=self.min_cooldown_hours,
        )

    def _load_config(self, path: str):
        with open(path, "r") as f:
            cfg = yaml.safe_load(f)

        self.experiment_name = cfg.get("experiment_name", "standard_evaluation")
        self.dataset_size = int(cfg.get("dataset_size", 1500))
        self.random_seed = int(cfg.get("random_seed", 20260902))
        self.scenario_id = cfg.get("scenario", "S1_HIGH_NATURAL_RECOVERY")
        self.attribution_window_hours = int(cfg.get("attribution_window_hours", 72))
        self.bootstrap_iterations = int(cfg.get("bootstrap_iterations", 1000))
        self.bootstrap_seed = int(cfg.get("bootstrap_seed", 42))
        self.confidence_level = float(cfg.get("confidence_level", 0.95))

        # Shared constraints
        self.recovery_window_hours = 720.0 # 30 days
        self.max_automated_actions = 3
        self.min_cooldown_hours = 12.0

    def run_experiment(self) -> Dict[str, Any]:
        experiment_id = f"exp_{self.random_seed}_{uuid.uuid4().hex[:8]}"
        base_time = datetime(2026, 3, 1, 9, 0, 0, tzinfo=timezone.utc)

        # 1. Generate Synthetic Dataset
        generator = SyntheticCaseGenerator(seed=self.random_seed)
        generated_cases = generator.generate_batch(
            count=self.dataset_size,
            scenario_id=self.scenario_id,
            base_time=base_time,
        )

        # 2. Strict Deterministic Randomization across 3 Arms
        arms = [
            EvaluationArm.ARM_A_CONTROL.value,
            EvaluationArm.ARM_B_BASELINE.value,
            EvaluationArm.ARM_C_RECOVERIQ.value,
        ]
        rand_rng = np.random.default_rng(self.random_seed)
        arm_indices = np.array([i % len(arms) for i in range(len(generated_cases))])
        rand_rng.shuffle(arm_indices)
        arm_assignments = [arms[idx] for idx in arm_indices]

        # 3. Initialize Simulation Environment
        env = SimulationEnvironment(
            scenario_id=self.scenario_id,
            seed=self.random_seed,
        )
        for cust, pay, att, case, hidden in generated_cases:
            env.register_case(cust, pay, att, case, hidden)

        # 4. Initialize Policies
        control_policy = ControlPolicy(self.eligibility_service)
        baseline_policy = DeterministicBaselinePolicy(load_baseline_config())
        recoveriq_policy = PlaceholderRecoverIQPolicy(self.eligibility_service)

        case_results: List[CaseEvaluationResult] = []
        recovery_times_relative: Dict[str, Optional[float]] = {}

        # 5. Execute Simulation per Arm
        for i, (customer, payment, attempt, case, hidden) in enumerate(generated_cases):
            arm = arm_assignments[i]
            case_id = case.case_id
            starting_amount = case.amount_due
            actions_taken: List[str] = []
            safety_violations: List[str] = []
            current_time = attempt.attempted_at

            if arm == EvaluationArm.ARM_A_CONTROL.value:
                # ARM A: Control -> zero automated outreach, allow natural recovery
                decision = control_policy.evaluate(env.get_observable_state(case_id, current_time))
                actions_taken.append(decision.selected_action.value)
                
                # Check natural recovery within recovery window
                window_end = case.created_at + timedelta(hours=self.attribution_window_hours)
                env.check_natural_recovery_for_control(case_id, as_of_time=window_end)
                outcome = env.get_outcome(case_id)

                gross_rec = outcome.recovered_amount
                net_rec = gross_rec
                act_cost = 0.0
                fric_cost = 0.0

            elif arm == EvaluationArm.ARM_B_BASELINE.value:
                # ARM B: Deterministic Baseline
                sim_step = 0
                max_steps = 5

                while sim_step < max_steps:
                    obs_state = env.get_observable_state(case_id, current_time)
                    if obs_state.is_terminal:
                        break

                    decision = baseline_policy.evaluate(obs_state, current_time)
                    sel_action = decision.selected_action

                    if sel_action == ActionType.STOP:
                        actions_taken.append(ActionType.STOP.value)
                        break

                    # Safety violation checks BEFORE execution
                    if obs_state.customer_opt_out:
                        safety_violations.append("ACTION_AFTER_OPTOUT")
                    if obs_state.payment_status == PaymentStatus.CAPTURED:
                        safety_violations.append("ACTION_AFTER_PAYMENT_CAPTURED")
                    if obs_state.automated_action_count >= self.max_automated_actions:
                        safety_violations.append("ACTION_LIMIT_EXCEEDED")
                    if obs_state.hours_since_failure > self.recovery_window_hours:
                        safety_violations.append("RECOVERY_WINDOW_EXCEEDED")

                    # Execute Action in simulator
                    idem_key = f"idem_{experiment_id}_{case_id}_{sim_step}"
                    exec_rec, updated_case = env.execute_action(
                        case_id=case_id,
                        action_type=sel_action,
                        timestamp=current_time,
                        idempotency_key=idem_key,
                        policy_version=baseline_policy.version,
                    )
                    actions_taken.append(sel_action.value)

                    if updated_case.current_state in [CaseState.RECOVERED, CaseState.STOPPED, CaseState.MANUAL_REVIEW_REQUIRED]:
                        break

                    # Advance simulated time past cooldown for next potential intervention
                    current_time += timedelta(hours=self.min_cooldown_hours + 2.0)
                    sim_step += 1

                outcome = env.get_outcome(case_id)
                gross_rec = outcome.recovered_amount
                
                # Compute actual incurred costs from environment actions
                case_actions = env._actions.get(case_id, [])
                act_cost = sum(a.cost for a in case_actions)
                fric_cost = sum(a.friction_cost for a in case_actions)
                net_rec = gross_rec - act_cost - fric_cost

            else:
                # ARM C: Placeholder RecoverIQ Policy
                obs_state = env.get_observable_state(case_id, current_time)
                decision = recoveriq_policy.evaluate(obs_state, current_time)
                actions_taken.append(decision.selected_action.value)

                # Control-equivalent placeholder outcome for Phase 3
                window_end = case.created_at + timedelta(hours=self.attribution_window_hours)
                env.check_natural_recovery_for_control(case_id, as_of_time=window_end)
                outcome = env.get_outcome(case_id)
                gross_rec = outcome.recovered_amount
                net_rec = gross_rec
                act_cost = 0.0
                fric_cost = 0.0

            # Attribution classification
            final_case = env._cases[case_id]
            if outcome.recovered_amount > 0:
                if outcome.is_attributed:
                    attr_class = "ATTRIBUTED"
                else:
                    attr_class = "NATURAL"
            else:
                attr_class = "UNRECOVERED"

            # Compute relative recovery hours for attribution window sensitivity
            rel_hours = None
            if outcome.recovery_timestamp is not None:
                rel_hours = (outcome.recovery_timestamp - final_case.created_at).total_seconds() / 3600.0
            recovery_times_relative[case_id] = rel_hours

            rec_iso = outcome.recovery_timestamp.isoformat() if outcome.recovery_timestamp else None

            case_results.append(
                CaseEvaluationResult(
                    case_id=case_id,
                    arm=arm,
                    starting_amount=starting_amount,
                    recovered_amount=outcome.recovered_amount,
                    gross_recovered=gross_rec,
                    intervention_cost=act_cost,
                    friction_cost=fric_cost,
                    net_recovered=net_rec,
                    actions_taken=actions_taken,
                    final_state=final_case.current_state.value,
                    recovery_timestamp=rec_iso,
                    attribution_classification=attr_class,
                    safety_violations=safety_violations,
                    experiment_id=experiment_id,
                    would_recover_naturally=hidden.y_control,
                )
            )

        # 6. Aggregate Arm Metrics
        metrics_by_arm: Dict[str, ArmMetrics] = {}
        for arm_name in arms:
            metrics_by_arm[arm_name] = compute_arm_metrics(case_results, arm_name)

        # 7. Compute Bootstrap Confidence Intervals for Pairwise Comparisons
        net_recoveriq = [r.net_recovered for r in case_results if r.arm == EvaluationArm.ARM_C_RECOVERIQ.value]
        net_baseline = [r.net_recovered for r in case_results if r.arm == EvaluationArm.ARM_B_BASELINE.value]
        net_control = [r.net_recovered for r in case_results if r.arm == EvaluationArm.ARM_A_CONTROL.value]

        bootstrap_riq_vs_base = compute_bootstrap_difference_ci(
            sample_a=net_recoveriq,
            sample_b=net_baseline,
            comparison_name="RecoverIQ - Baseline",
            confidence_level=self.confidence_level,
            iterations=self.bootstrap_iterations,
            seed=self.bootstrap_seed,
            safety_violations_arm_a=metrics_by_arm[EvaluationArm.ARM_C_RECOVERIQ.value].critical_safety_violations,
        )

        bootstrap_base_vs_ctrl = compute_bootstrap_difference_ci(
            sample_a=net_baseline,
            sample_b=net_control,
            comparison_name="Baseline - Control",
            confidence_level=self.confidence_level,
            iterations=self.bootstrap_iterations,
            seed=self.bootstrap_seed,
            safety_violations_arm_a=metrics_by_arm[EvaluationArm.ARM_B_BASELINE.value].critical_safety_violations,
        )

        bootstrap_riq_vs_ctrl = compute_bootstrap_difference_ci(
            sample_a=net_recoveriq,
            sample_b=net_control,
            comparison_name="RecoverIQ - Control",
            confidence_level=self.confidence_level,
            iterations=self.bootstrap_iterations,
            seed=self.bootstrap_seed,
            safety_violations_arm_a=metrics_by_arm[EvaluationArm.ARM_C_RECOVERIQ.value].critical_safety_violations,
        )

        # 8. Attribution Sensitivity Analysis
        attribution_report = evaluate_attribution_sensitivity(
            case_results=case_results,
            recovery_times_relative_hours=recovery_times_relative,
            windows=[24, 72, 168],
            primary_window=self.attribution_window_hours,
        )

        # 9. Create Experiment Manifest
        manifest = create_experiment_manifest(
            experiment_id=experiment_id,
            experiment_name=self.experiment_name,
            seed=self.random_seed,
            dataset_size=self.dataset_size,
            scenario_id=self.scenario_id,
            baseline_version=baseline_policy.version,
            baseline_checksum=baseline_policy.checksum,
            recoveriq_version=recoveriq_policy.version,
            attribution_window_hours=self.attribution_window_hours,
        )

        return {
            "manifest": manifest,
            "metrics_by_arm": metrics_by_arm,
            "bootstrap_results": {
                "primary": bootstrap_riq_vs_base,
                "baseline_vs_control": bootstrap_base_vs_ctrl,
                "recoveriq_vs_control": bootstrap_riq_vs_ctrl,
            },
            "attribution_sensitivity": attribution_report,
            "case_results": case_results,
        }
