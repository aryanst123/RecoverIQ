import pytest
import numpy as np
from datetime import datetime, timezone

from domain.enums import ActionType, FailureCode, CustomerSegment, ChannelPreference, CaseState, PaymentStatus, PromiseState
from domain.models import ObservableCaseState
from policy.adaptive import RecoverIQAdaptivePolicy
from policy.eligibility import CandidateActionService
from models.incremental_recovery import IncrementalRecoveryModel, ActionPrediction, IncrementalPredictionResult

class MockIncrementalModel:
    """Mock model with controllable action probabilities for testing policy decision logic."""
    def __init__(self, p_control: float, action_probs: dict, model_version: str = "mock-v1"):
        self.p_control = p_control
        self.action_probs = action_probs
        self.model_version = model_version

    def predict_action_effects(self, state: ObservableCaseState) -> IncrementalPredictionResult:
        predictions = {}
        for act in [ActionType.REMINDER, ActionType.PAYMENT_LINK, ActionType.PROMISE_TO_PAY, ActionType.ESCALATE]:
            p_a = self.action_probs.get(act, self.p_control)
            tau = p_a - self.p_control
            predictions[act.value] = ActionPrediction(
                action=act,
                action_probability=p_a,
                incremental_probability=tau,
                expected_incremental_revenue=float(tau * state.residual_amount),
            )
        return IncrementalPredictionResult(
            case_id=state.case_id,
            control_probability=self.p_control,
            actions=predictions,
            model_version=self.model_version,
            feature_schema_version="features-v1",
        )

def make_test_state(
    amount: float = 3000.0,
    action_count: int = 0,
    opt_out: bool = False,
    cooldown_h: float = 24.0,
    promise_status: PromiseState = None,
) -> ObservableCaseState:
    return ObservableCaseState(
        case_id="case_pol_test_01",
        payment_id="pay_pol_test_01",
        customer_id="cust_pol_test_01",
        customer_segment=CustomerSegment.STANDARD,
        customer_channel_preference=ChannelPreference.WHATSAPP,
        customer_opt_out=opt_out,
        amount_due=amount,
        residual_amount=amount,
        current_state=CaseState.RECOVERY_ELIGIBLE,
        failure_code=FailureCode.INSUFFICIENT_FUNDS,
        failure_reason="Insufficient funds",
        hours_since_failure=2.0,
        attempt_count=1,
        automated_action_count=action_count,
        last_action_type=None,
        last_action_hours_ago=cooldown_h,
        active_promise_status=promise_status,
    )

def test_policy_selects_highest_expected_net_recovery():
    # Residual = 3000
    # Control = 0.30
    # Reminder: 0.45 -> tau = +0.15 -> exp_inc_rev = 450 -> net = 450 - 2 = 448
    # Payment Link: 0.55 -> tau = +0.25 -> exp_inc_rev = 750 -> net = 750 - 3 = 747 (Highest!)
    # P2P: 0.40 -> tau = +0.10 -> exp_inc_rev = 300 -> net = 300 - 5 = 295
    # Escalate: 0.50 -> tau = +0.20 -> exp_inc_rev = 600 -> net = 600 - 100 = 500
    mock_model = MockIncrementalModel(
        p_control=0.30,
        action_probs={
            ActionType.REMINDER: 0.45,
            ActionType.PAYMENT_LINK: 0.55,
            ActionType.PROMISE_TO_PAY: 0.40,
            ActionType.ESCALATE: 0.50,
        },
    )
    policy = RecoverIQAdaptivePolicy(model=mock_model, minimum_incremental_recovery=250.0)
    state = make_test_state(amount=3000.0)

    decision = policy.evaluate_case(state)
    assert decision.selected_action == ActionType.PAYMENT_LINK
    assert "PAYMENT_LINK" in decision.decision_reason
    assert policy.last_trace is not None
    trace = policy.last_trace.to_dict()
    assert trace["selected_action"] == "PAYMENT_LINK"

def test_stop_action_selected_when_all_interventions_negative():
    # Interventions have negative uplift (annoyance/friction)
    mock_model = MockIncrementalModel(
        p_control=0.60,
        action_probs={
            ActionType.REMINDER: 0.50, # tau = -0.10
            ActionType.PAYMENT_LINK: 0.55, # tau = -0.05
            ActionType.PROMISE_TO_PAY: 0.40, # tau = -0.20
            ActionType.ESCALATE: 0.50, # tau = -0.10
        },
    )
    policy = RecoverIQAdaptivePolicy(model=mock_model)
    state = make_test_state(amount=2000.0)

    decision = policy.evaluate_case(state)
    # STOP has net recovery 0.0, which beats negative net recoveries
    assert decision.selected_action == ActionType.STOP
    assert policy.last_trace.selected_action == ActionType.STOP

def test_minimum_incremental_recovery_threshold_enforced():
    # Residual = 1000.0
    # Payment Link: tau = +0.10 -> exp_inc_rev = 100.0 (Below 250.0 threshold!)
    # All interventions are below threshold 250.0 -> must fallback to STOP
    mock_model = MockIncrementalModel(
        p_control=0.30,
        action_probs={
            ActionType.REMINDER: 0.35, # tau = 0.05 -> rev = 50
            ActionType.PAYMENT_LINK: 0.40, # tau = 0.10 -> rev = 100
            ActionType.PROMISE_TO_PAY: 0.38, # tau = 0.08 -> rev = 80
            ActionType.ESCALATE: 0.35, # tau = 0.05 -> rev = 50
        },
    )
    policy = RecoverIQAdaptivePolicy(model=mock_model, minimum_incremental_recovery=250.0)
    state = make_test_state(amount=2000.0)

    decision = policy.evaluate_case(state)
    assert decision.selected_action == ActionType.STOP

    # Check candidate rejection reasons in decision trace
    trace = policy.last_trace.to_dict()
    for cand in trace["candidate_evaluations"]:
        if cand["action"] != "STOP":
            assert cand["eligible"] is False
            assert "BELOW_THRESHOLD_250" in cand["rejection_reason"]

def test_policy_respects_customer_opt_out():
    mock_model = MockIncrementalModel(p_control=0.20, action_probs={ActionType.PAYMENT_LINK: 0.90})
    policy = RecoverIQAdaptivePolicy(model=mock_model)
    state = make_test_state(amount=5000.0, opt_out=True)

    decision = policy.evaluate_case(state)
    assert decision.selected_action == ActionType.STOP

def test_policy_respects_action_limit():
    mock_model = MockIncrementalModel(p_control=0.20, action_probs={ActionType.PAYMENT_LINK: 0.90})
    policy = RecoverIQAdaptivePolicy(model=mock_model)
    state = make_test_state(amount=5000.0, action_count=3) # Reached limit of 3

    decision = policy.evaluate_case(state)
    assert decision.selected_action == ActionType.STOP

def test_policy_respects_active_promise():
    mock_model = MockIncrementalModel(p_control=0.20, action_probs={ActionType.PROMISE_TO_PAY: 0.90})
    policy = RecoverIQAdaptivePolicy(model=mock_model)
    state = make_test_state(amount=5000.0, promise_status=PromiseState.PROMISE_ACCEPTED)

    decision = policy.evaluate_case(state)
    # Cannot propose another action while promise is active!
    assert decision.selected_action == ActionType.STOP
