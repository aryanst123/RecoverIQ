from typing import List, Dict, Any, Tuple
import numpy as np
from domain.enums import ActionType
from domain.models import ObservableCaseState, PotentialOutcome
from simulator.generator import SyntheticCaseGenerator
from simulator.environment import SimulationEnvironment
from models.incremental_recovery import IncrementalRecoveryModel

class SimulatorGroundTruthDiagnostic:
    """
    SIMULATOR-ONLY DIAGNOSTIC (OFFLINE VALIDATION ONLY).
    Compares the model's estimated causal uplift tau(a, x) against the simulator's
    counterfactual potential outcomes [Y(a) - Y(control)] across a cohort.
    This ground truth is STRICTLY forbidden in the training pipeline and is used
    here solely to assess directional sanity.
    """
    def __init__(self, model: IncrementalRecoveryModel):
        self.model = model

    def evaluate_directional_sanity(
        self,
        count: int = 500,
        seed: int = 12345,
        scenario_id: str = "S5_HIGH_RECOVERY_HETEROGENEITY",
    ) -> Dict[str, Any]:
        gen = SyntheticCaseGenerator(seed=seed)
        cases = gen.generate_batch(count=count, scenario_id=scenario_id)

        env = SimulationEnvironment(scenario_id=scenario_id, seed=seed)
        for cust, pay, att, c, hidden in cases:
            env.register_case(cust, pay, att, c, hidden)

        actions = [
            ActionType.REMINDER,
            ActionType.PAYMENT_LINK,
            ActionType.PROMISE_TO_PAY,
            ActionType.ESCALATE,
        ]
        action_uplifts = {act.value: [] for act in actions}
        gt_uplifts = {act.value: [] for act in actions}

        for cust, pay, att, case, hidden in cases:
            obs_state = env.get_observable_state(case.case_id, current_time=att.attempted_at)
            pred_result = self.model.predict_action_effects(obs_state)

            y_ctrl = 1 if hidden.y_control else 0
            for act in actions:
                est_uplift = pred_result.actions[act.value].incremental_probability
                action_uplifts[act.value].append(est_uplift)

                if act == ActionType.REMINDER:
                    y_a = 1 if hidden.y_reminder else 0
                elif act == ActionType.PAYMENT_LINK:
                    y_a = 1 if hidden.y_payment_link else 0
                elif act == ActionType.PROMISE_TO_PAY:
                    y_a = 1 if hidden.y_promise_to_pay else 0
                elif act == ActionType.ESCALATE:
                    y_a = 1 if hidden.y_escalate else 0
                else:
                    y_a = 0
                gt_uplifts[act.value].append(y_a - y_ctrl)

        action_evaluations: Dict[str, Dict[str, Any]] = {}
        for act in actions:
            estimated_uplifts = action_uplifts[act.value]
            ground_truth_uplifts = gt_uplifts[act.value]

            mean_est = float(np.mean(estimated_uplifts))
            mean_gt = float(np.mean(ground_truth_uplifts))
            std_est = float(np.std(estimated_uplifts))
            std_gt = float(np.std(ground_truth_uplifts))
            correlation = float(np.corrcoef(estimated_uplifts, ground_truth_uplifts)[0, 1]) if std_est > 0 and std_gt > 0 else 0.0

            action_evaluations[act.value] = {
                "mean_estimated_uplift": mean_est,
                "mean_ground_truth_uplift": mean_gt,
                "correlation": correlation,
                "directional_match": bool(np.sign(mean_est) == np.sign(mean_gt) or abs(mean_gt) < 0.02),
            }

        return {
            "diagnostic_type": "SIMULATOR-ONLY DIAGNOSTIC",
            "cohort_size": count,
            "scenario": scenario_id,
            "actions": action_evaluations,
        }
