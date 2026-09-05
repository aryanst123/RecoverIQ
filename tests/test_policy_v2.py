import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

from domain.enums import ActionType, PaymentStatus, CaseState, CustomerSegment, FailureCode, ChannelPreference, PromiseState
from domain.models import ObservableCaseState
from policy.adaptive_v2 import RecoverIQAdaptivePolicyV2
from policy.eligibility import CandidateActionService
from models.incremental_recovery import IncrementalRecoveryModel, IncrementalPredictionResult, ActionPrediction

def create_mock_state(
    case_id: str = "case_test_001",
    residual_amount: float = 3000.0,
    segment: CustomerSegment = CustomerSegment.STANDARD,
    failure_code: FailureCode = FailureCode.AUTHENTICATION_FAILED,
    automated_action_count: int = 0,
    hours_since_failure: float = 2.0,
    last_action_hours_ago: float = None,
    customer_opt_out: bool = False,
    is_terminal: bool = False,
    payment_status: PaymentStatus = PaymentStatus.FAILED,
    current_state: CaseState = CaseState.PAYMENT_FAILED,
    active_promise_status: PromiseState = None,
) -> ObservableCaseState:
    return ObservableCaseState(
        case_id=case_id,
        payment_id="pay_test_001",
        customer_id="cust_test_001",
        amount_due=residual_amount,
        residual_amount=residual_amount,
        customer_segment=segment,
        customer_channel_preference=ChannelPreference.WHATSAPP,
        customer_opt_out=customer_opt_out,
        failure_code=failure_code,
        failure_reason="Authentication failed",
        attempt_count=1,
        automated_action_count=automated_action_count,
        hours_since_failure=hours_since_failure,
        last_action_type=None,
        last_action_hours_ago=last_action_hours_ago,
        active_promise_status=active_promise_status,
        active_promise_due_hours=None,
        current_state=current_state,
        payment_status=payment_status,
        is_terminal=is_terminal,
    )

def create_mock_model(predictions: dict, control_prob: float = 0.40) -> MagicMock:
    model = MagicMock(spec=IncrementalRecoveryModel)
    model.model_version = "mock-incremental-model"

    def predict_effects(state: ObservableCaseState) -> IncrementalPredictionResult:
        actions = {}
        for act_str, (p_act, tau) in predictions.items():
            actions[act_str] = ActionPrediction(
                action=ActionType(act_str),
                action_probability=p_act,
                incremental_probability=tau,
                expected_incremental_revenue=tau * state.residual_amount,
            )
        return IncrementalPredictionResult(
            case_id=state.case_id,
            control_probability=control_prob,
            actions=actions,
            model_version="mock-incremental-model",
            feature_schema_version="mock-features-v1",
        )

    model.predict_action_effects.side_effect = predict_effects
    return model

class TestRecoverIQAdaptivePolicyV2:
    def test_authoritative_costs_consistency(self):
        """Validates that Policy V2 uses exact authoritative costs from CandidateActionService."""
        model = create_mock_model({})
        policy = RecoverIQAdaptivePolicyV2(model=model)
        
        assert policy._action_costs[ActionType.REMINDER] == 2.0
        assert policy._action_costs[ActionType.PAYMENT_LINK] == 3.0
        assert policy._action_costs[ActionType.PROMISE_TO_PAY] == 5.0
        assert policy._action_costs[ActionType.ESCALATE] == 100.0
        assert policy._action_costs[ActionType.STOP] == 0.0
        assert policy.eligibility_service.friction_per_action == 5.0
        assert policy.eligibility_service.friction_cap == 25.0

    def test_escalation_advantage_margin_enforced(self):
        """
        Validates that ESCALATE is rejected when expected net advantage over
        the best non-escalation alternative is less than the required margin (INR 50).
        """
        # Residual amount: INR 3000
        # PAYMENT_LINK: tau = +0.20 -> Gross = 600, Cost = 3, Net = 597
        # ESCALATE: tau = +0.21 -> Gross = 630, Cost = 100, Net = 530
        # ESCALATE Net (530) < PAYMENT_LINK Net (597), so PAYMENT_LINK selected.
        preds = {
            "REMINDER": (0.50, 0.10),
            "PAYMENT_LINK": (0.60, 0.20),
            "PROMISE_TO_PAY": (0.55, 0.15),
            "ESCALATE": (0.61, 0.21),
        }
        model = create_mock_model(preds, control_prob=0.40)
        policy = RecoverIQAdaptivePolicyV2(model=model, escalation_advantage_margin=50.0)
        state = create_mock_state(residual_amount=3000.0)

        decision = policy.evaluate_case(state)
        assert decision.selected_action == ActionType.PAYMENT_LINK
        
        # Verify trace indicates escalation margin guard was applied
        esc_eval = next(e for e in policy.last_trace.candidate_evaluations if e.action == ActionType.ESCALATE)
        assert not esc_eval.eligible
        assert "INSUFFICIENT_ESCALATION_ADVANTAGE_MARGIN" in esc_eval.rejection_reason

    def test_escalation_selected_when_genuine_advantage_exceeds_margin(self):
        """
        Validates that ESCALATE IS selected when its incremental net recovery exceeds
        the best non-escalation action by at least the margin (INR 50).
        """
        # Residual amount: INR 5000
        # PAYMENT_LINK: tau = +0.10 -> Gross = 500, Cost = 3, Net = 497
        # ESCALATE: tau = +0.30 -> Gross = 1500, Cost = 100, Net = 1400
        # Delta = 1400 - 497 = 903 >= 50.0 -> ESCALATE selected!
        preds = {
            "REMINDER": (0.45, 0.05),
            "PAYMENT_LINK": (0.50, 0.10),
            "PROMISE_TO_PAY": (0.48, 0.08),
            "ESCALATE": (0.70, 0.30),
        }
        model = create_mock_model(preds, control_prob=0.40)
        policy = RecoverIQAdaptivePolicyV2(model=model, escalation_advantage_margin=50.0)
        state = create_mock_state(residual_amount=5000.0)

        decision = policy.evaluate_case(state)
        assert decision.selected_action == ActionType.ESCALATE
        assert decision.net_expected_value == 1400.0

    def test_cheap_action_selected_for_small_amount(self):
        """
        Validates that small ticket cases (e.g. INR 800) successfully select cheap actions
        (REMINDER @ INR 2) when positive net recovery exists, without being killed by
        the old Phase 9 flat INR 250 threshold.
        """
        # Residual amount: INR 800
        # REMINDER: tau = +0.10 -> Gross = 80, Cost = 2, Net = 78 > 0
        # ESCALATE: ineligible by contract (min amount for escalate = 1500)
        preds = {
            "REMINDER": (0.50, 0.10),
            "PAYMENT_LINK": (0.45, 0.05),
            "PROMISE_TO_PAY": (0.42, 0.02),
            "ESCALATE": (0.60, 0.20),
        }
        model = create_mock_model(preds, control_prob=0.40)
        policy = RecoverIQAdaptivePolicyV2(model=model)
        state = create_mock_state(residual_amount=800.0)

        decision = policy.evaluate_case(state)
        assert decision.selected_action == ActionType.REMINDER
        assert decision.net_expected_value == 78.0

    def test_hard_safety_gates_enforced(self):
        """Validates that customer opt-out, cooldown, terminal state immediately yield STOP."""
        model = create_mock_model({"REMINDER": (0.8, 0.4)})
        policy = RecoverIQAdaptivePolicyV2(model=model)

        # 1. Opt-out
        state_opt = create_mock_state(customer_opt_out=True)
        dec_opt = policy.evaluate_case(state_opt)
        assert dec_opt.selected_action == ActionType.STOP

        # 2. Cooldown (< 12 hours)
        state_cd = create_mock_state(last_action_hours_ago=4.0)
        dec_cd = policy.evaluate_case(state_cd)
        assert dec_cd.selected_action == ActionType.STOP

        # 3. Terminal state
        state_term = create_mock_state(is_terminal=True, current_state=CaseState.RECOVERED)
        dec_term = policy.evaluate_case(state_term)
        assert dec_term.selected_action == ActionType.STOP

        # 4. Max actions reached (3)
        state_max = create_mock_state(automated_action_count=3)
        dec_max = policy.evaluate_case(state_max)
        assert dec_max.selected_action == ActionType.STOP

    def test_policy_checksum_and_reproducibility(self):
        """Validates that checksum is deterministic and policy outputs are 100% reproducible."""
        model = create_mock_model({"PAYMENT_LINK": (0.7, 0.3)})
        p1 = RecoverIQAdaptivePolicyV2(model=model, escalation_advantage_margin=50.0)
        p2 = RecoverIQAdaptivePolicyV2(model=model, escalation_advantage_margin=50.0)

        assert p1.checksum == p2.checksum
        state = create_mock_state(residual_amount=2500.0)
        d1 = p1.evaluate_case(state, decision_time=datetime(2026, 3, 1, tzinfo=timezone.utc))
        d2 = p2.evaluate_case(state, decision_time=datetime(2026, 3, 1, tzinfo=timezone.utc))

        assert d1.selected_action == d2.selected_action
        assert d1.net_expected_value == d2.net_expected_value
        assert d1.decision_reason == d2.decision_reason
