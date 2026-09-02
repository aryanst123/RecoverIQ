import pytest
from datetime import datetime, timezone
from domain.enums import (
    ActionType,
    CaseState,
    FailureCode,
    PaymentStatus,
    PromiseState,
    CustomerSegment,
    ChannelPreference,
)
from domain.models import ObservableCaseState, PotentialOutcome
from baseline.policy import DeterministicBaselinePolicy
from baseline.config import BaselineConfig

def create_sample_state(**kwargs) -> ObservableCaseState:
    defaults = {
        "case_id": "case_test_01",
        "payment_id": "pay_test_01",
        "customer_id": "cust_test_01",
        "customer_segment": CustomerSegment.STANDARD,
        "customer_channel_preference": ChannelPreference.WHATSAPP,
        "customer_opt_out": False,
        "amount_due": 2500.0,
        "residual_amount": 2500.0,
        "current_state": CaseState.ACTION_EVALUATION,
        "failure_code": FailureCode.AUTHENTICATION_FAILED,
        "failure_reason": "OTP expired",
        "attempt_count": 1,
        "automated_action_count": 0,
        "hours_since_failure": 2.0,
        "last_action_type": None,
        "last_action_hours_ago": None,
        "active_promise_status": None,
        "active_promise_due_hours": None,
        "payment_status": PaymentStatus.FAILED,
        "is_terminal": False,
    }
    defaults.update(kwargs)
    return ObservableCaseState(**defaults)

def test_baseline_deterministic_reproducibility():
    policy = DeterministicBaselinePolicy()
    state = create_sample_state()
    
    dec1 = policy.evaluate(state)
    dec2 = policy.evaluate(state)
    
    assert dec1.selected_action == dec2.selected_action
    assert dec1.decision_reason == dec2.decision_reason
    assert dec1.expected_cost == dec2.expected_cost
    assert dec1.candidate_actions == dec2.candidate_actions
    assert dec1.policy_version == dec2.policy_version

def test_baseline_opt_out_rule():
    policy = DeterministicBaselinePolicy()
    state = create_sample_state(customer_opt_out=True)
    decision = policy.evaluate(state)
    assert decision.selected_action == ActionType.STOP
    assert "opted out" in decision.decision_reason.lower()

def test_baseline_already_recovered_rule():
    policy = DeterministicBaselinePolicy()
    state = create_sample_state(payment_status=PaymentStatus.CAPTURED, current_state=CaseState.RECOVERED)
    decision = policy.evaluate(state)
    assert decision.selected_action == ActionType.STOP
    assert "already been captured" in decision.decision_reason.lower()

def test_baseline_action_limit_rule():
    policy = DeterministicBaselinePolicy()
    state = create_sample_state(automated_action_count=3)
    decision = policy.evaluate(state)
    assert decision.selected_action == ActionType.STOP
    assert "action limit reached" in decision.decision_reason.lower()

def test_baseline_recovery_window_expiry():
    policy = DeterministicBaselinePolicy()
    state = create_sample_state(hours_since_failure=800.0) # > 720h (30 days)
    decision = policy.evaluate(state)
    assert decision.selected_action == ActionType.STOP
    assert "exceeds recovery window" in decision.decision_reason.lower()

def test_baseline_cooldown_rule():
    policy = DeterministicBaselinePolicy()
    state = create_sample_state(
        automated_action_count=1,
        last_action_type=ActionType.REMINDER,
        last_action_hours_ago=4.0, # < 12h cooldown
    )
    decision = policy.evaluate(state)
    assert decision.selected_action == ActionType.STOP
    assert "cooldown active" in decision.decision_reason.lower()

def test_baseline_active_promise_rule():
    policy = DeterministicBaselinePolicy()
    state = create_sample_state(active_promise_status=PromiseState.PROMISE_ACCEPTED)
    decision = policy.evaluate(state)
    assert decision.selected_action == ActionType.STOP
    assert "promise to pay pending" in decision.decision_reason.lower()

def test_baseline_promise_to_pay_eligibility_insufficient_funds():
    policy = DeterministicBaselinePolicy()
    state = create_sample_state(
        failure_code=FailureCode.INSUFFICIENT_FUNDS,
        amount_due=1200.0,
        residual_amount=1200.0,
        active_promise_status=None,
    )
    decision = policy.evaluate(state)
    assert decision.selected_action == ActionType.PROMISE_TO_PAY
    assert "Promise-to-Pay" in decision.decision_reason

def test_baseline_card_expired_selects_payment_link():
    policy = DeterministicBaselinePolicy()
    state = create_sample_state(failure_code=FailureCode.CARD_EXPIRED)
    decision = policy.evaluate(state)
    assert decision.selected_action == ActionType.PAYMENT_LINK
    assert "Expired card" in decision.decision_reason

def test_baseline_engagement_flow_transitions():
    policy = DeterministicBaselinePolicy()
    
    # 1st attempt: REMINDER
    s1 = create_sample_state(
        failure_code=FailureCode.AUTHENTICATION_FAILED,
        automated_action_count=0,
    )
    d1 = policy.evaluate(s1)
    assert d1.selected_action == ActionType.REMINDER

    # 2nd attempt after cooldown: PAYMENT_LINK
    s2 = create_sample_state(
        failure_code=FailureCode.AUTHENTICATION_FAILED,
        automated_action_count=1,
        last_action_type=ActionType.REMINDER,
        last_action_hours_ago=24.0,
    )
    d2 = policy.evaluate(s2)
    assert d2.selected_action == ActionType.PAYMENT_LINK

    # 3rd attempt after cooldown: PROMISE_TO_PAY
    s3 = create_sample_state(
        failure_code=FailureCode.AUTHENTICATION_FAILED,
        automated_action_count=2,
        last_action_type=ActionType.PAYMENT_LINK,
        last_action_hours_ago=24.0,
        residual_amount=500.0,
    )
    d3 = policy.evaluate(s3)
    assert d3.selected_action == ActionType.PROMISE_TO_PAY

def test_baseline_high_value_escalation():
    policy = DeterministicBaselinePolicy()
    state = create_sample_state(
        residual_amount=8000.0,
        automated_action_count=2,
        last_action_type=ActionType.PAYMENT_LINK,
        last_action_hours_ago=24.0,
    )
    decision = policy.evaluate(state)
    assert decision.selected_action == ActionType.ESCALATE
    assert "High ticket value" in decision.decision_reason

def test_baseline_low_value_avoids_escalation():
    policy = DeterministicBaselinePolicy()
    # Residual ₹500 is below escalation threshold (₹1500)
    state = create_sample_state(
        residual_amount=500.0,
        automated_action_count=2,
        last_action_type=ActionType.PAYMENT_LINK,
        last_action_hours_ago=24.0,
        failure_code=FailureCode.GATEWAY_DOWNTIME,
    )
    decision = policy.evaluate(state)
    assert decision.selected_action != ActionType.ESCALATE

def test_baseline_blocks_potential_outcome_leakage():
    policy = DeterministicBaselinePolicy()
    pot_outcome = PotentialOutcome(
        case_id="case_leak_01",
        latent_payment_propensity=0.9,
        latent_response_propensity=0.8,
        latent_p2p_reliability=0.7,
        latent_friction_sensitivity=0.2,
        y_control=True,
        y_reminder=True,
        y_payment_link=True,
        y_promise_to_pay=True,
        y_escalate=True,
    )
    
    with pytest.raises(TypeError) as exc:
        policy.evaluate(pot_outcome)
    assert "ObservableCaseState" in str(exc.value)

def test_baseline_version_and_checksum_stability():
    cfg1 = BaselineConfig()
    cfg2 = BaselineConfig()
    assert cfg1.get_checksum() == cfg2.get_checksum()
    assert len(cfg1.get_checksum()) == 64 # SHA-256 length

    # Changing any config value alters checksum
    cfg_modified = BaselineConfig(max_automated_actions=4)
    assert cfg1.get_checksum() != cfg_modified.get_checksum()
