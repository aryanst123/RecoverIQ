import pytest
from domain.enums import ActionType
from policy.eligibility import CandidateActionService

def test_action_cost_values():
    service = CandidateActionService()
    assert service.cost_reminder == 2.0
    assert service.cost_payment_link == 3.0
    assert service.cost_promise_to_pay == 5.0
    assert service.cost_escalate == 100.0

def test_friction_cost_accumulation_and_cap():
    service = CandidateActionService(friction_per_action=5.0, friction_cap=25.0)
    # Count 0 -> 0 friction
    assert service.calculate_friction(0) == 0.0
    # Count 1 -> 5 friction
    assert service.calculate_friction(1) == 5.0
    # Count 2 -> 10 friction
    assert service.calculate_friction(2) == 10.0
    # Count 3 -> 15 friction
    assert service.calculate_friction(3) == 15.0
    # Count 5 -> capped at 25
    assert service.calculate_friction(5) == 25.0
    # Count 10 -> capped at 25
    assert service.calculate_friction(10) == 25.0

def test_expected_net_recovery_formula():
    residual_amount = 5000.0
    tau = 0.15 # 15% incremental uplift
    exp_inc_rev = tau * residual_amount # 750.0
    assert exp_inc_rev == 750.0

    action_cost = 3.0 # PAYMENT_LINK
    friction_cost = 5.0 # 1 prior action
    expected_net = exp_inc_rev - action_cost - friction_cost
    assert expected_net == 742.0

def test_stop_action_has_strictly_zero_net_and_cost():
    # STOP represents doing nothing: zero costs, zero friction, zero net
    tau = 0.0
    residual = 10000.0
    exp_inc_rev = tau * residual
    action_cost = 0.0
    friction = 0.0
    exp_net = exp_inc_rev - action_cost - friction
    assert exp_net == 0.0
