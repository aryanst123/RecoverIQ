import hashlib
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any

from domain.enums import ActionType, FailureCode, CustomerSegment
from domain.models import ObservableCaseState, PolicyDecision
from policy.eligibility import CandidateActionService
from policy.evaluations import ActionEvaluation, DecisionTrace
from policy.confidence import PolicyConfidenceService
from models.incremental_recovery import IncrementalRecoveryModel

class RecoverIQAdaptivePolicy:
    """
    RECOVERIQ ADAPTIVE DECISION ENGINE (recoveriq-v1).
    Dynamically selects interventions to maximize causal net expected recovery:
    E[Net] = tau(a, X) * residual_amount - action_cost(a) - friction_cost(a)
    Enforces shared eligibility, minimum incremental threshold (INR 250),
    low-confidence fallback (< 0.60), and structured decision tracing.
    Zero execution privileges. Purely deterministic given input state and model.
    """
    POLICY_VERSION = "recoveriq-v1"

    def __init__(
        self,
        model: IncrementalRecoveryModel,
        eligibility_service: Optional[CandidateActionService] = None,
        confidence_service: Optional[PolicyConfidenceService] = None,
        minimum_incremental_recovery: float = 250.0,
        low_confidence_threshold: float = 0.60,
    ):
        self.model = model
        self.eligibility_service = eligibility_service or CandidateActionService()
        self.confidence_service = confidence_service or PolicyConfidenceService(
            low_confidence_threshold=low_confidence_threshold
        )
        self.minimum_incremental_recovery = minimum_incremental_recovery
        self.low_confidence_threshold = low_confidence_threshold
        self._action_costs = {
            ActionType.REMINDER: self.eligibility_service.cost_reminder,
            ActionType.PAYMENT_LINK: self.eligibility_service.cost_payment_link,
            ActionType.PROMISE_TO_PAY: self.eligibility_service.cost_promise_to_pay,
            ActionType.ESCALATE: self.eligibility_service.cost_escalate,
            ActionType.STOP: 0.0,
        }
        self.checksum = self._compute_policy_checksum()

    def _compute_policy_checksum(self) -> str:
        content = (
            f"{self.POLICY_VERSION}_min_thresh_{self.minimum_incremental_recovery}_"
            f"conf_{self.low_confidence_threshold}_costs_{self._action_costs}"
        )
        return hashlib.sha256(content.encode()).hexdigest()

    def evaluate_case(
        self,
        state: ObservableCaseState,
        decision_time: Optional[datetime] = None,
    ) -> PolicyDecision:
        """
        Executes the full economic decision pipeline for an observable case.
        """
        if not isinstance(state, ObservableCaseState):
            raise TypeError(f"RecoverIQAdaptivePolicy only accepts ObservableCaseState, got {type(state)}")

        current_time = decision_time or datetime.now(timezone.utc)
        case_id = state.case_id

        # 1. Obtain universally eligible candidate actions from shared contract
        shared_eligible = set(self.eligibility_service.get_eligible_actions(state))

        # 2. Get ML model estimates
        pred_result = self.model.predict_action_effects(state)
        p_control = pred_result.control_probability

        # Calculate friction cost for this step
        friction = self.eligibility_service.calculate_friction(state.automated_action_count)

        evaluations: List[ActionEvaluation] = []
        eval_actions = [
            ActionType.STOP,
            ActionType.REMINDER,
            ActionType.PAYMENT_LINK,
            ActionType.PROMISE_TO_PAY,
            ActionType.ESCALATE,
        ]

        for act in eval_actions:
            is_contract_eligible = act in shared_eligible
            rejection_reason: Optional[str] = None

            if act == ActionType.STOP:
                # STOP has zero intervention cost, zero friction, zero incremental revenue
                evaluations.append(ActionEvaluation(
                    action=ActionType.STOP,
                    probability=p_control,
                    control_probability=p_control,
                    incremental_probability=0.0,
                    residual_amount=state.residual_amount,
                    expected_incremental_revenue=0.0,
                    action_cost=0.0,
                    friction_cost=0.0,
                    expected_net_recovery=0.0,
                    eligible=is_contract_eligible,
                    rejection_reason=None if is_contract_eligible else "INELIGIBLE_BY_SHARED_CONTRACT",
                ))
                continue

            # Retrieve action-specific prediction
            act_pred = pred_result.actions.get(act.value)
            if act_pred is not None:
                p_act = act_pred.action_probability
                tau = act_pred.incremental_probability # May be negative!
                exp_inc_rev = act_pred.expected_incremental_revenue
            else:
                p_act = p_control
                tau = 0.0
                exp_inc_rev = 0.0

            act_cost = self._action_costs.get(act, 0.0)
            exp_net = float(exp_inc_rev - act_cost - friction)

            # Check Minimum Incremental Recovery Threshold (INR 250)
            is_action_eligible = is_contract_eligible
            if is_action_eligible and exp_inc_rev < self.minimum_incremental_recovery:
                is_action_eligible = False
                rejection_reason = f"EXPECTED_INCREMENTAL_REVENUE_BELOW_THRESHOLD_{self.minimum_incremental_recovery}"
            elif not is_contract_eligible:
                rejection_reason = "INELIGIBLE_BY_SHARED_CONTRACT"

            evaluations.append(ActionEvaluation(
                action=act,
                probability=p_act,
                control_probability=p_control,
                incremental_probability=tau,
                residual_amount=state.residual_amount,
                expected_incremental_revenue=exp_inc_rev,
                action_cost=act_cost,
                friction_cost=friction,
                expected_net_recovery=exp_net,
                eligible=is_action_eligible,
                rejection_reason=rejection_reason,
            ))

        # 3. Filter to eligible candidates
        eligible_candidates = [e for e in evaluations if e.eligible]

        # 4. Sort eligible candidates by expected_net_recovery descending
        # Deterministic tie-breaking: lower action cost first (STOP > REMINDER > PAYMENT_LINK > PROMISE_TO_PAY > ESCALATE)
        eligible_candidates.sort(
            key=lambda e: (e.expected_net_recovery, -e.action_cost),
            reverse=True,
        )

        top_choice = eligible_candidates[0] if eligible_candidates else evaluations[0]
        selected_action = top_choice.action
        selection_reason = f"Maximized expected net recovery (INR {top_choice.expected_net_recovery:.2f})"
        constraints_applied = []

        # 5. Check Policy Confidence for selected intervention
        conf_score, conf_status = self.confidence_service.evaluate_confidence(
            state=state,
            action_type=selected_action,
            action_prob=top_choice.probability,
            control_prob=p_control,
        )

        # Low-confidence fallback handling
        if selected_action != ActionType.STOP and conf_score < self.low_confidence_threshold:
            constraints_applied.append("LOW_CONFIDENCE_FALLBACK_APPLIED")
            # If high value stuck case, escalate safely if eligible; otherwise conservative STOP
            if state.residual_amount >= 1500.0 and ActionType.ESCALATE in shared_eligible:
                selected_action = ActionType.ESCALATE
                selection_reason = f"Low confidence ({conf_score:.2f} < {self.low_confidence_threshold}); routed to ESCALATE for human review"
            else:
                selected_action = ActionType.STOP
                selection_reason = f"Low confidence ({conf_score:.2f} < {self.low_confidence_threshold}); routed to conservative STOP"

        # 6. Construct Structured Decision Trace
        trace = DecisionTrace(
            case_id=case_id,
            model_version=pred_result.model_version,
            policy_version=self.POLICY_VERSION,
            candidate_evaluations=evaluations,
            selected_action=selected_action,
            selection_reason=selection_reason,
            constraints_applied=constraints_applied,
            confidence_score=conf_score,
            confidence_status=conf_status,
            timestamp=current_time,
        )
        self.last_trace = trace

        explanation = (
            f"RecoverIQ selected {selected_action.value} ({selection_reason}). "
            f"Control baseline: {p_control:.1%}, Action prob: {top_choice.probability:.1%}, "
            f"Uplift tau: {top_choice.incremental_probability:+.1%}, "
            f"Exp Net: INR {top_choice.expected_net_recovery:.2f}, "
            f"Confidence: {conf_score:.2f} ({conf_status})."
        )

        decision_id = f"dec_{case_id}_{int(current_time.timestamp())}"
        return PolicyDecision(
            decision_id=decision_id,
            case_id=case_id,
            candidate_actions=list(shared_eligible),
            selected_action=selected_action,
            model_version=pred_result.model_version,
            policy_version=self.POLICY_VERSION,
            confidence=conf_score,
            expected_incremental_recovery=top_choice.expected_incremental_revenue,
            expected_cost=top_choice.action_cost,
            expected_friction_cost=top_choice.friction_cost,
            net_expected_value=top_choice.expected_net_recovery,
            decision_reason=explanation,
        )
