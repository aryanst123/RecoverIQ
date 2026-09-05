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

class RecoverIQAdaptivePolicyV2:
    """
    RECOVERIQ ADAPTIVE DECISION ENGINE V2 (recoveriq-v2).
    Phase 10 Improved Action-Selection Policy.
    
    Key Improvements over v1:
    1. Cost-Normalized Incremental Value: Eliminates rigid INR 250 threshold;
       enforces true economic viability (E[Net] > 0).
    2. Escalation Advantage Margin: Requires ESCALATE to deliver a proven economic
       advantage margin (INR 50.0) over the best eligible non-escalation alternative,
       preventing over-escalation driven by estimation noise on high-ticket cases.
    3. Conservative Uncertainty Handling: Low confidence naturally dampens aggressive
       actions without hard-coded brittle rule trees or forced human escalation.
    4. Authoritative Cost Synchronization: Dynamically loads action and friction costs
       from CandidateActionService contract.
    5. Zero Execution Privileges: Pure decision engine returning PolicyDecision.
    """
    POLICY_VERSION = "recoveriq-v2"

    def __init__(
        self,
        model: IncrementalRecoveryModel,
        eligibility_service: Optional[CandidateActionService] = None,
        confidence_service: Optional[PolicyConfidenceService] = None,
        escalation_advantage_margin: float = 50.0,
        low_confidence_threshold: float = 0.60,
    ):
        self.model = model
        self.eligibility_service = eligibility_service or CandidateActionService()
        self.confidence_service = confidence_service or PolicyConfidenceService(
            low_confidence_threshold=low_confidence_threshold
        )
        self.escalation_advantage_margin = escalation_advantage_margin
        self.low_confidence_threshold = low_confidence_threshold
        
        # Authoritative costs dynamically loaded from CandidateActionService contract
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
            f"{self.POLICY_VERSION}_margin_{self.escalation_advantage_margin}_"
            f"conf_{self.low_confidence_threshold}_costs_{self._action_costs}"
        )
        return hashlib.sha256(content.encode()).hexdigest()

    def evaluate_case(
        self,
        state: ObservableCaseState,
        decision_time: Optional[datetime] = None,
    ) -> PolicyDecision:
        """
        Executes the Phase 10 economic decision pipeline for an observable case.
        """
        if not isinstance(state, ObservableCaseState):
            raise TypeError(f"RecoverIQAdaptivePolicyV2 only accepts ObservableCaseState, got {type(state)}")

        current_time = decision_time or datetime.now(timezone.utc)
        case_id = state.case_id

        # 1. Obtain universally eligible candidate actions from shared contract
        shared_eligible = set(self.eligibility_service.get_eligible_actions(state))

        # 2. Get ML model estimates
        pred_result = self.model.predict_action_effects(state)
        p_control = pred_result.control_probability

        # Calculate friction cost for this step
        friction = self.eligibility_service.calculate_friction(state.automated_action_count)

        # Pre-compute metrics for all actions
        raw_evals = {}
        eval_actions = [
            ActionType.STOP,
            ActionType.REMINDER,
            ActionType.PAYMENT_LINK,
            ActionType.PROMISE_TO_PAY,
            ActionType.ESCALATE,
        ]

        for act in eval_actions:
            is_contract_eligible = act in shared_eligible
            if act == ActionType.STOP:
                raw_evals[act] = {
                    "prob": p_control,
                    "tau": 0.0,
                    "exp_inc_rev": 0.0,
                    "act_cost": 0.0,
                    "friction": 0.0,
                    "exp_net": 0.0,
                    "conf_score": 1.0,
                    "contract_eligible": is_contract_eligible,
                }
                continue

            act_pred = pred_result.actions.get(act.value)
            if act_pred is not None:
                p_act = act_pred.action_probability
                tau = act_pred.incremental_probability
                exp_inc_rev = act_pred.expected_incremental_revenue
            else:
                p_act = p_control
                tau = 0.0
                exp_inc_rev = 0.0

            act_cost = self._action_costs.get(act, 0.0)
            exp_net = float(exp_inc_rev - act_cost - friction)

            conf_score, conf_status = self.confidence_service.evaluate_confidence(
                state=state,
                action_type=act,
                action_prob=p_act,
                control_prob=p_control,
            )

            raw_evals[act] = {
                "prob": p_act,
                "tau": tau,
                "exp_inc_rev": exp_inc_rev,
                "act_cost": act_cost,
                "friction": friction,
                "exp_net": exp_net,
                "conf_score": conf_score,
                "contract_eligible": is_contract_eligible,
            }

        # 3. Find best eligible non-escalation alternative for relative advantage comparison
        eligible_non_esc_nets = [
            raw_evals[a]["exp_net"]
            for a in eval_actions
            if a != ActionType.ESCALATE and raw_evals[a]["contract_eligible"] and (raw_evals[a]["exp_net"] > 0.0 or a == ActionType.STOP)
        ]
        best_non_esc_net = max(eligible_non_esc_nets) if eligible_non_esc_nets else 0.0

        # 4. Construct ActionEvaluations enforcing economic viability & escalation advantage margin
        evaluations: List[ActionEvaluation] = []
        constraints_applied: List[str] = []

        for act in eval_actions:
            d = raw_evals[act]
            is_eligible = d["contract_eligible"]
            rej_reason = None

            if not is_eligible:
                rej_reason = "INELIGIBLE_BY_SHARED_CONTRACT"
            elif act != ActionType.STOP and d["exp_net"] <= 0.0:
                is_eligible = False
                rej_reason = "NEGATIVE_OR_ZERO_EXPECTED_NET_RECOVERY"
            elif act == ActionType.ESCALATE and self.escalation_advantage_margin > 0.0:
                required_net = best_non_esc_net + self.escalation_advantage_margin
                if d["exp_net"] < required_net:
                    is_eligible = False
                    rej_reason = f"INSUFFICIENT_ESCALATION_ADVANTAGE_MARGIN_{self.escalation_advantage_margin}"
                    constraints_applied.append("ESCALATION_MARGIN_GUARD_APPLIED")

            evaluations.append(ActionEvaluation(
                action=act,
                probability=d["prob"],
                control_probability=p_control,
                incremental_probability=d["tau"],
                residual_amount=state.residual_amount,
                expected_incremental_revenue=d["exp_inc_rev"],
                action_cost=d["act_cost"],
                friction_cost=d["friction"],
                expected_net_recovery=d["exp_net"],
                eligible=is_eligible,
                rejection_reason=rej_reason,
            ))

        # 5. Filter to eligible candidates and sort by expected_net_recovery descending
        # Deterministic tie-breaking: lower action cost first (STOP > REMINDER > PAYMENT_LINK > PROMISE_TO_PAY > ESCALATE)
        eligible_candidates = [e for e in evaluations if e.eligible]
        eligible_candidates.sort(
            key=lambda e: (e.expected_net_recovery, -e.action_cost),
            reverse=True,
        )

        top_choice = eligible_candidates[0] if eligible_candidates else evaluations[0]
        selected_action = top_choice.action
        selection_reason = f"Maximized expected net recovery (INR {top_choice.expected_net_recovery:.2f})"

        # 6. Evaluate Confidence for Selected Intervention
        conf_score_final, conf_status_final = self.confidence_service.evaluate_confidence(
            state=state,
            action_type=selected_action,
            action_prob=top_choice.probability,
            control_prob=p_control,
        )

        # 7. Construct Structured Decision Trace
        trace = DecisionTrace(
            case_id=case_id,
            model_version=pred_result.model_version,
            policy_version=self.POLICY_VERSION,
            candidate_evaluations=evaluations,
            selected_action=selected_action,
            selection_reason=selection_reason,
            constraints_applied=constraints_applied,
            confidence_score=conf_score_final,
            confidence_status=conf_status_final,
            timestamp=current_time,
        )
        self.last_trace = trace

        explanation = (
            f"RecoverIQ-v2 selected {selected_action.value} ({selection_reason}). "
            f"Control: {p_control:.1%}, Action prob: {top_choice.probability:.1%}, "
            f"Uplift: {top_choice.incremental_probability:+.1%}, "
            f"Exp Net: INR {top_choice.expected_net_recovery:.2f}, "
            f"Confidence: {conf_score_final:.2f} ({conf_status_final})."
        )

        decision_id = f"dec_v2_{case_id}_{int(current_time.timestamp())}"
        return PolicyDecision(
            decision_id=decision_id,
            case_id=case_id,
            candidate_actions=list(shared_eligible),
            selected_action=selected_action,
            model_version=pred_result.model_version,
            policy_version=self.POLICY_VERSION,
            confidence=conf_score_final,
            expected_incremental_recovery=top_choice.expected_incremental_revenue,
            expected_cost=top_choice.action_cost,
            expected_friction_cost=top_choice.friction_cost,
            net_expected_value=top_choice.expected_net_recovery,
            decision_reason=explanation,
        )
