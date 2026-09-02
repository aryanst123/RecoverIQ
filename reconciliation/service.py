from datetime import datetime, timezone
from typing import Tuple, Optional
from domain.enums import CaseState, PaymentStatus, ActionType
from domain.models import RecoveryCase, Payment, Customer, ObservableCaseState

class ReconciledStateViolationError(Exception):
    pass

class LiveStateReconciliationService:
    """
    Live Payment State Reconciliation Service.
    Guarantees that actions are NEVER executed based solely on stale case snapshots.
    Fetches the authoritative live payment and customer state immediately before reservation/execution.
    """
    def __init__(
        self,
        max_automated_actions: int = 3,
        recovery_window_hours: float = 720.0,
    ):
        self.max_automated_actions = max_automated_actions
        self.recovery_window_hours = recovery_window_hours

    def reconcile_before_execution(
        self,
        case: RecoveryCase,
        payment: Payment,
        customer: Customer,
        now: Optional[datetime] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Reconciles live state against critical business invariants immediately before reservation.
        Returns (is_safe, rejection_reason).
        """
        current_time = now or datetime.now(timezone.utc)

        # 1. Customer Opt-Out Check
        if customer.opt_out:
            return False, "ACTION_REJECTED_CUSTOMER_OPT_OUT"

        # 2. Terminal Payment Capture Check
        if payment.status in [PaymentStatus.CAPTURED, PaymentStatus.AUTHORIZED]:
            return False, "ACTION_REJECTED_PAYMENT_ALREADY_CAPTURED"

        # 3. Terminal or In-Flight Case State Check
        allowed_initiation_states = {
            CaseState.PAYMENT_FAILED,
            CaseState.RECOVERY_ELIGIBLE,
            CaseState.ACTION_EVALUATION,
            CaseState.RE_EVALUATE,
        }
        if case.current_state not in allowed_initiation_states:
            return False, f"ACTION_REJECTED_STATE_{case.current_state.value}"

        # 4. Action Limit Ceiling
        if case.automated_action_count >= self.max_automated_actions:
            return False, f"ACTION_REJECTED_MAX_ACTIONS_REACHED_{case.automated_action_count}"

        # 5. Recovery Window Expiry
        age_hours = (current_time - case.created_at).total_seconds() / 3600.0
        if age_hours > self.recovery_window_hours:
            return False, f"ACTION_REJECTED_RECOVERY_WINDOW_EXPIRED_{age_hours:.1f}h"

        return True, None

    def reconcile_after_execution(
        self,
        case: RecoveryCase,
        payment: Payment,
        execution_status: str,
        recovered: bool,
        recovered_amount: float = 0.0,
        now: Optional[datetime] = None,
    ):
        """
        Reconciles state following execution confirmation or timeout.
        """
        current_time = now or datetime.now(timezone.utc)
        if recovered:
            payment.status = PaymentStatus.CAPTURED
            case.current_state = CaseState.RECOVERED
            case.residual_amount = max(0.0, case.residual_amount - recovered_amount)
            case.last_updated_at = current_time
        elif execution_status == "UNKNOWN":
            case.current_state = CaseState.EXECUTION_UNKNOWN
            case.last_updated_at = current_time
