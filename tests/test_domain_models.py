import pytest
from datetime import datetime, timezone, timedelta
from domain.enums import (
    ActionType,
    CaseState,
    PromiseState,
    ExecutionStatus,
    RecoveryStatus,
    PaymentStatus,
    FailureCode,
    CustomerSegment,
    ChannelPreference,
)
from domain.models import (
    Customer,
    Payment,
    PaymentAttempt,
    RecoveryCase,
    RecoveryAction,
    Promise,
    PolicyDecision,
    Execution,
    RecoveryOutcome,
)
from domain.state_machine import (
    CaseStateMachine,
    PromiseStateMachine,
    InvalidStateTransitionError,
    TerminalStateViolationError,
    TERMINAL_CASE_STATES,
    TERMINAL_PROMISE_STATES,
)

def test_case_state_machine_valid_lifecycle():
    state = CaseState.PAYMENT_FAILED
    state = CaseStateMachine.transition(state, CaseState.RECOVERY_ELIGIBLE)
    state = CaseStateMachine.transition(state, CaseState.ACTION_EVALUATION)
    state = CaseStateMachine.transition(state, CaseState.ACTION_RESERVED)
    state = CaseStateMachine.transition(state, CaseState.ACTION_EXECUTING)
    state = CaseStateMachine.transition(state, CaseState.ACTION_CONFIRMED)
    state = CaseStateMachine.transition(state, CaseState.WAITING_FOR_OUTCOME)
    state = CaseStateMachine.transition(state, CaseState.OUTCOME_RECONCILIATION)
    state = CaseStateMachine.transition(state, CaseState.RECOVERED)
    assert state == CaseState.RECOVERED
    assert CaseStateMachine.is_terminal(state)

def test_case_state_machine_terminal_violation():
    for term_state in TERMINAL_CASE_STATES:
        assert CaseStateMachine.is_terminal(term_state)
        with pytest.raises(TerminalStateViolationError):
            CaseStateMachine.transition(term_state, CaseState.ACTION_EVALUATION)

def test_case_state_machine_invalid_jump():
    with pytest.raises(InvalidStateTransitionError):
        # Cannot jump directly from PAYMENT_FAILED to ACTION_EXECUTING
        CaseStateMachine.transition(CaseState.PAYMENT_FAILED, CaseState.ACTION_EXECUTING)

def test_promise_state_machine_valid_lifecycle():
    pstate = PromiseState.PROMISE_PROPOSED
    pstate = PromiseStateMachine.transition(pstate, PromiseState.PROMISE_ACCEPTED)
    pstate = PromiseStateMachine.transition(pstate, PromiseState.PROMISE_DUE)
    pstate = PromiseStateMachine.transition(pstate, PromiseState.PROMISE_FULFILLED)
    assert pstate == PromiseState.PROMISE_FULFILLED
    assert PromiseStateMachine.is_terminal(pstate)

def test_promise_state_machine_terminal_violation():
    for term_state in TERMINAL_PROMISE_STATES:
        assert PromiseStateMachine.is_terminal(term_state)
        with pytest.raises(TerminalStateViolationError):
            PromiseStateMachine.transition(term_state, PromiseState.PROMISE_ACCEPTED)

def test_recovery_case_creation_and_fields():
    now = datetime.now(timezone.utc)
    case = RecoveryCase(
        case_id="case_001",
        payment_id="pay_001",
        customer_id="cust_001",
        amount_due=2450.0,
        residual_amount=2450.0,
        created_at=now,
        last_updated_at=now,
        automated_action_count=0,
    )
    assert case.amount_due == 2450.0
    assert case.current_state == CaseState.PAYMENT_FAILED
    assert case.automated_action_count == 0
