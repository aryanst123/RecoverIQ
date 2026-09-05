import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

from domain.enums import ActionType, PaymentStatus, CaseState, CustomerSegment, FailureCode, ChannelPreference, PromiseState
from domain.models import ObservableCaseState
from policy.adaptive_v3 import RecoverIQAdaptivePolicyV3
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

def create_mock_model(predictions: dict, control_prob: float = 0.50) -> MagicMock:
    model = MagicMock(spec=IncrementalRecoveryModel)
    model.model_version = "incremental-model-v3"
    model.feature_schema_version = "features-v1"

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
            model_version="incremental-model-v3",
            feature_schema_version="features-v1",
        )

    model.predict_action_effects.side_effect = predict_effects
    return model

class TestRecoverIQAdaptivePolicyV3:
    def test_authoritative_costs_and_checksum(self):
        """Validates that Policy V3 dynamically loads authoritative costs and computes checksum."""
        model = create_mock_model({})
        policy = RecoverIQAdaptivePolicyV3(model=model)
        
        assert policy._action_costs[ActionType.REMINDER] == 2.0
        assert policy._action_costs[ActionType.PAYMENT_LINK] == 3.0
        assert policy._action_costs[ActionType.PROMISE_TO_PAY] == 5.0
        assert policy._action_costs[ActionType.ESCALATE] == 100.0
        assert policy._action_costs[ActionType.STOP] == 0.0
        assert len(policy.checksum) == 64

    def test_continuation_value_prevents_step0_over_escalation(self):
        """
        Validates that on Step 0, Policy V3 selects a cheap action (e.g., PAYMENT_LINK)
        instead of immediately escalating, because the continuation value of trying
        the link first and preserving escalation for unresolved cases dominates.
        """
        # Case: INR 3,000, Step 0
        # Control: P = 0.50
        # PAYMENT_LINK: P = 0.60, Cost = 3
        # ESCALATE: P = 0.77, Cost = 100
        preds = {
            "REMINDER": (0.54, 0.04),
            "PAYMENT_LINK": (0.60, 0.10),
            "PROMISE_TO_PAY": (0.58, 0.08),
            "ESCALATE": (0.77, 0.27),
        }
        model = create_mock_model(preds, control_prob=0.50)
        policy = RecoverIQAdaptivePolicyV3(model=model)
        state = create_mock_state(residual_amount=3000.0, automated_action_count=0)

        decision = policy.evaluate_case(state)
        # Dynamic continuation value of PAYMENT_LINK dominates immediate ESCALATE
        assert decision.selected_action == ActionType.PAYMENT_LINK
        assert decision.policy_version == "recoveriq-v3"

    def test_step2_escalation_when_justified(self):
        """
        Validates that on Step 2 (final attempt), Policy V3 selects ESCALATE
        when incremental recovery justifies the INR 100 cost.
        """
        # Case: INR 5,000, Step 2 (prior 2 attempts failed)
        # Control: P = 0.50
        # ESCALATE: P = 0.75 (tau = +0.25 -> incremental revenue = 1,250 >> 100 + friction)
        preds = {
            "REMINDER": (0.52, 0.02),
            "PAYMENT_LINK": (0.55, 0.05),
            "PROMISE_TO_PAY": (0.53, 0.03),
            "ESCALATE": (0.75, 0.25),
        }
        model = create_mock_model(preds, control_prob=0.50)
        policy = RecoverIQAdaptivePolicyV3(model=model)
        state = create_mock_state(residual_amount=5000.0, automated_action_count=2)

        decision = policy.evaluate_case(state)
        assert decision.selected_action == ActionType.ESCALATE

    def test_safety_gate_opt_out(self):
        """Ensures customer opt-out immediately returns STOP."""
        model = create_mock_model({})
        policy = RecoverIQAdaptivePolicyV3(model=model)
        state = create_mock_state(customer_opt_out=True)

        decision = policy.evaluate_case(state)
        assert decision.selected_action == ActionType.STOP
        assert "Customer opt-out" in decision.decision_reason

    def test_safety_gate_active_promise(self):
        """Ensures active promise immediately returns STOP."""
        model = create_mock_model({})
        policy = RecoverIQAdaptivePolicyV3(model=model)
        state = create_mock_state(active_promise_status=PromiseState.PROMISE_ACCEPTED)

        decision = policy.evaluate_case(state)
        assert decision.selected_action == ActionType.STOP
        assert "Active promise" in decision.decision_reason

    def test_safety_gate_max_attempts(self):
        """Ensures reaching max attempts (3) immediately returns STOP."""
        model = create_mock_model({})
        policy = RecoverIQAdaptivePolicyV3(model=model)
        state = create_mock_state(automated_action_count=3)

        decision = policy.evaluate_case(state)
        assert decision.selected_action == ActionType.STOP
        assert "Maximum automated attempts" in decision.decision_reason
