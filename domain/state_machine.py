from typing import Set, Dict
from domain.enums import CaseState, PromiseState

class InvalidStateTransitionError(Exception):
    pass

class TerminalStateViolationError(Exception):
    pass

# Explicit set of terminal states
TERMINAL_CASE_STATES: Set[CaseState] = {
    CaseState.RECOVERED,
    CaseState.STOPPED,
    CaseState.UNRECOVERABLE,
    CaseState.MANUAL_REVIEW_REQUIRED,
}

TERMINAL_PROMISE_STATES: Set[PromiseState] = {
    PromiseState.PROMISE_FULFILLED,
    PromiseState.PROMISE_MISSED,
    PromiseState.PROMISE_EXPIRED,
}

# Valid forward transitions for recovery cases
VALID_CASE_TRANSITIONS: Dict[CaseState, Set[CaseState]] = {
    CaseState.PAYMENT_FAILED: {
        CaseState.RECOVERY_ELIGIBLE,
        CaseState.STOPPED,
        CaseState.UNRECOVERABLE,
    },
    CaseState.RECOVERY_ELIGIBLE: {
        CaseState.ACTION_EVALUATION,
        CaseState.STOPPED,
        CaseState.RECOVERED,
    },
    CaseState.ACTION_EVALUATION: {
        CaseState.ACTION_RESERVED,
        CaseState.STOPPED,
        CaseState.RECOVERED,
        CaseState.MANUAL_REVIEW_REQUIRED,
    },
    CaseState.ACTION_RESERVED: {
        CaseState.ACTION_EXECUTING,
        CaseState.EXECUTION_UNKNOWN,
        CaseState.STOPPED,
    },
    CaseState.ACTION_EXECUTING: {
        CaseState.ACTION_CONFIRMED,
        CaseState.EXECUTION_UNKNOWN,
        CaseState.STOPPED,
    },
    CaseState.ACTION_CONFIRMED: {
        CaseState.WAITING_FOR_OUTCOME,
        CaseState.STOPPED,
        CaseState.RECOVERED,
    },
    CaseState.WAITING_FOR_OUTCOME: {
        CaseState.OUTCOME_RECONCILIATION,
        CaseState.RECOVERED,
        CaseState.RE_EVALUATE,
        CaseState.STOPPED,
    },
    CaseState.OUTCOME_RECONCILIATION: {
        CaseState.RECOVERED,
        CaseState.RE_EVALUATE,
        CaseState.STOPPED,
        CaseState.UNRECOVERABLE,
        CaseState.MANUAL_REVIEW_REQUIRED,
    },
    CaseState.RE_EVALUATE: {
        CaseState.RECOVERY_ELIGIBLE,
        CaseState.STOPPED,
        CaseState.RECOVERED,
        CaseState.MANUAL_REVIEW_REQUIRED,
    },
    CaseState.EXECUTION_UNKNOWN: {
        CaseState.OUTCOME_RECONCILIATION,
        CaseState.ACTION_CONFIRMED,
        CaseState.MANUAL_REVIEW_REQUIRED,
        CaseState.STOPPED,
    },
    # Terminal states have no outbound transitions
    CaseState.RECOVERED: set(),
    CaseState.STOPPED: set(),
    CaseState.UNRECOVERABLE: set(),
    CaseState.MANUAL_REVIEW_REQUIRED: set(),
}

VALID_PROMISE_TRANSITIONS: Dict[PromiseState, Set[PromiseState]] = {
    PromiseState.PROMISE_PROPOSED: {
        PromiseState.PROMISE_ACCEPTED,
        PromiseState.PROMISE_EXPIRED,
    },
    PromiseState.PROMISE_ACCEPTED: {
        PromiseState.PROMISE_DUE,
        PromiseState.PROMISE_FULFILLED,
        PromiseState.PROMISE_EXPIRED,
    },
    PromiseState.PROMISE_DUE: {
        PromiseState.PROMISE_FULFILLED,
        PromiseState.PROMISE_MISSED,
        PromiseState.PROMISE_EXPIRED,
    },
    # Terminal states
    PromiseState.PROMISE_FULFILLED: set(),
    PromiseState.PROMISE_MISSED: set(),
    PromiseState.PROMISE_EXPIRED: set(),
}

class CaseStateMachine:
    @staticmethod
    def is_terminal(state: CaseState) -> bool:
        return state in TERMINAL_CASE_STATES

    @staticmethod
    def can_transition(from_state: CaseState, to_state: CaseState) -> bool:
        if CaseStateMachine.is_terminal(from_state):
            return False
        return to_state in VALID_CASE_TRANSITIONS.get(from_state, set())

    @staticmethod
    def transition(from_state: CaseState, to_state: CaseState) -> CaseState:
        if CaseStateMachine.is_terminal(from_state):
            raise TerminalStateViolationError(
                f"Cannot transition from terminal state {from_state.value} to {to_state.value}"
            )
        allowed = VALID_CASE_TRANSITIONS.get(from_state, set())
        if to_state not in allowed:
            raise InvalidStateTransitionError(
                f"Invalid transition from {from_state.value} to {to_state.value}. Allowed: {[s.value for s in allowed]}"
            )
        return to_state

class PromiseStateMachine:
    @staticmethod
    def is_terminal(state: PromiseState) -> bool:
        return state in TERMINAL_PROMISE_STATES

    @staticmethod
    def can_transition(from_state: PromiseState, to_state: PromiseState) -> bool:
        if PromiseStateMachine.is_terminal(from_state):
            return False
        return to_state in VALID_PROMISE_TRANSITIONS.get(from_state, set())

    @staticmethod
    def transition(from_state: PromiseState, to_state: PromiseState) -> PromiseState:
        if PromiseStateMachine.is_terminal(from_state):
            raise TerminalStateViolationError(
                f"Cannot transition from terminal promise state {from_state.value} to {to_state.value}"
            )
        allowed = VALID_PROMISE_TRANSITIONS.get(from_state, set())
        if to_state not in allowed:
            raise InvalidStateTransitionError(
                f"Invalid promise transition from {from_state.value} to {to_state.value}. Allowed: {[s.value for s in allowed]}"
            )
        return to_state
