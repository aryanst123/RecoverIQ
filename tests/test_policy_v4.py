"""
Unit tests for RecoverIQAdaptivePolicyV4 (Phase 12).
Tests safety invariants, dynamic programming calculations, and decision validity.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from datetime import datetime, timezone
from domain.enums import ActionType, PaymentStatus, CaseState, PromiseState, CustomerSegment, ChannelPreference, FailureCode
from domain.models import ObservableCaseState, PolicyDecision
from policy.adaptive_v4 import RecoverIQAdaptivePolicyV4
from models.artifacts import ModelArtifactManager

@pytest.fixture
def policy_v4():
    mgr = ModelArtifactManager()
    model = mgr.load_model("incremental-model-v4")
    return RecoverIQAdaptivePolicyV4(model=model)

def make_sample_state(
    case_id: str = "case_test_001",
    residual_amount: float = 2500.0,
    automated_action_count: int = 0,
    opt_out: bool = False,
    is_terminal: bool = False,
    active_promise: bool = False,
) -> ObservableCaseState:
    return ObservableCaseState(
        case_id=case_id,
        payment_id=f"pay_{case_id}",
        customer_id=f"cust_{case_id}",
        amount_due=residual_amount,
        residual_amount=residual_amount,
        customer_segment=CustomerSegment.STANDARD,
        customer_channel_preference=ChannelPreference.WHATSAPP,
        customer_opt_out=opt_out,
        failure_code=FailureCode.INSUFFICIENT_FUNDS,
        failure_reason="Insufficient funds",
        attempt_count=1,
        automated_action_count=automated_action_count,
        hours_since_failure=2.0,
        last_action_type=None,
        last_action_hours_ago=None,
        active_promise_status=PromiseState.PROMISE_ACCEPTED if active_promise else None,
        active_promise_due_hours=48.0 if active_promise else None,
        current_state=CaseState.PAYMENT_FAILED if not is_terminal else CaseState.RECOVERED,
        payment_status=PaymentStatus.FAILED,
        is_terminal=is_terminal,
    )

def test_v4_safety_opt_out(policy_v4):
    state = make_sample_state(opt_out=True)
    decision = policy_v4.evaluate_case(state)
    assert decision.selected_action == ActionType.STOP
    assert "SafetyGate" in decision.decision_reason

def test_v4_safety_terminal_state(policy_v4):
    state = make_sample_state(is_terminal=True)
    decision = policy_v4.evaluate_case(state)
    assert decision.selected_action == ActionType.STOP

def test_v4_safety_active_promise(policy_v4):
    state = make_sample_state(active_promise=True)
    decision = policy_v4.evaluate_case(state)
    assert decision.selected_action == ActionType.STOP

def test_v4_max_automated_limit(policy_v4):
    state = make_sample_state(automated_action_count=3)
    decision = policy_v4.evaluate_case(state)
    assert decision.selected_action == ActionType.STOP

def test_v4_step0_evaluation(policy_v4):
    state = make_sample_state(residual_amount=3500.0, automated_action_count=0)
    decision = policy_v4.evaluate_case(state)
    assert decision.selected_action in [ActionType.REMINDER, ActionType.PAYMENT_LINK, ActionType.PROMISE_TO_PAY, ActionType.ESCALATE]
    assert decision.policy_version == "recoveriq-v4"

def test_v4_step1_evaluation(policy_v4):
    state = make_sample_state(residual_amount=3500.0, automated_action_count=1)
    decision = policy_v4.evaluate_case(state)
    assert decision.selected_action in [ActionType.REMINDER, ActionType.PAYMENT_LINK, ActionType.PROMISE_TO_PAY, ActionType.ESCALATE, ActionType.STOP]
