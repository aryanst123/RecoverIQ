from typing import Optional, List, Dict, Any
from domain.enums import ActionType, CaseState, PaymentStatus
from domain.models import RecoveryCase, Payment, Customer

class SafetyInvariantViolation(Exception):
    """Raised whenever a safety invariant is violated."""
    pass

class SafetyGuard:
    """
    Evaluates and enforces the 10 core safety invariants of RecoverIQ.
    """
    @staticmethod
    def assert_no_action_after_terminal_recovery(payment: Payment, case: RecoveryCase, action_type: ActionType):
        """Invariant 1: No automated action after terminal recovery."""
        if action_type != ActionType.STOP:
            if payment.status in [PaymentStatus.CAPTURED, PaymentStatus.AUTHORIZED]:
                raise SafetyInvariantViolation(
                    f"INVARIANT 1 VIOLATION: Cannot execute action {action_type.value} on captured payment {payment.payment_id}"
                )
            if case.current_state in [CaseState.RECOVERED, CaseState.STOPPED, CaseState.UNRECOVERABLE]:
                raise SafetyInvariantViolation(
                    f"INVARIANT 1 VIOLATION: Cannot execute action {action_type.value} on case {case.case_id} in terminal state {case.current_state.value}"
                )

    @staticmethod
    def assert_has_valid_reservation(reservation_id: Optional[str]):
        """Invariant 2: No execution without reservation."""
        if not reservation_id:
            raise SafetyInvariantViolation("INVARIANT 2 VIOLATION: Execution attempted without a valid reservation ID")

    @staticmethod
    def assert_no_action_after_opt_out(customer: Customer, action_type: ActionType):
        """Invariant 4: No action after customer opt-out."""
        if customer.opt_out and action_type != ActionType.STOP:
            raise SafetyInvariantViolation(
                f"INVARIANT 4 VIOLATION: Customer {customer.customer_id} has opted out; cannot execute {action_type.value}"
            )

    @staticmethod
    def assert_within_action_limit(current_action_count: int, max_limit: int, action_type: ActionType):
        """Invariant 5: No action beyond maximum automated actions."""
        if action_type != ActionType.STOP and current_action_count >= max_limit:
            raise SafetyInvariantViolation(
                f"INVARIANT 5 VIOLATION: Case has reached max action limit ({current_action_count}/{max_limit})"
            )

    @staticmethod
    def assert_within_recovery_window(age_hours: float, max_window_hours: float, action_type: ActionType):
        """Invariant 6: No action outside recovery window."""
        if action_type != ActionType.STOP and age_hours > max_window_hours:
            raise SafetyInvariantViolation(
                f"INVARIANT 6 VIOLATION: Case age ({age_hours:.1f}h) exceeds recovery window ({max_window_hours:.1f}h)"
            )

    @staticmethod
    def assert_no_regression_from_terminal_payment(current_status: PaymentStatus, incoming_status: PaymentStatus):
        """Invariant 9: Out-of-order events cannot regress terminal payment state."""
        if current_status == PaymentStatus.CAPTURED and incoming_status in [PaymentStatus.FAILED, PaymentStatus.CREATED]:
            raise SafetyInvariantViolation(
                f"INVARIANT 9 VIOLATION: Cannot regress payment from CAPTURED to {incoming_status.value}"
            )
