from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple
from domain.enums import (
    ActionType,
    CaseState,
    ExecutionStatus,
    PaymentStatus,
)
from domain.models import (
    RecoveryCase,
    Payment,
    Customer,
    Execution,
)
from execution.locks import CaseLockManager
from execution.idempotency import MerchantIdempotencyService
from execution.reservation import (
    ActionReservationService,
    ActionReservation,
    DuplicateReservationError,
    InvalidReservationError,
)
from reconciliation.service import LiveStateReconciliationService
from safety.guards import SafetyGuard, SafetyInvariantViolation
from safety.audit import AuditTrailService

class SafeRecoveryExecutor:
    """
    BOUNDED EXECUTION ENGINE.
    Orchestrates the complete safety lifecycle:
    Lock -> Live Reconciliation -> Invariant Guards -> Idempotency ->
    Reservation -> Execution -> Reconciliation -> Audit Trail.
    """
    def __init__(
        self,
        lock_manager: Optional[CaseLockManager] = None,
        reservation_service: Optional[ActionReservationService] = None,
        idempotency_service: Optional[MerchantIdempotencyService] = None,
        reconciliation_service: Optional[LiveStateReconciliationService] = None,
        audit_service: Optional[AuditTrailService] = None,
        max_automated_actions: int = 3,
        recovery_window_hours: float = 720.0,
    ):
        self.lock_manager = lock_manager or CaseLockManager()
        self.reservation_service = reservation_service or ActionReservationService()
        self.idempotency_service = idempotency_service or MerchantIdempotencyService()
        self.reconciliation_service = reconciliation_service or LiveStateReconciliationService(
            max_automated_actions=max_automated_actions,
            recovery_window_hours=recovery_window_hours,
        )
        self.audit_service = audit_service or AuditTrailService()
        self.max_automated_actions = max_automated_actions
        self.recovery_window_hours = recovery_window_hours

    def execute_policy_decision(
        self,
        case: RecoveryCase,
        payment: Payment,
        customer: Customer,
        action_type: ActionType,
        policy_version: str,
        idempotency_key: Optional[str] = None,
        now: Optional[datetime] = None,
        simulate_timeout: bool = False,
        simulate_failure: bool = False,
        simulate_escalation_failure: bool = False,
    ) -> Tuple[Execution, bool, Optional[str]]:
        """
        Executes an action with full safety guarantees.
        Returns: (Execution, success_bool, rejection_or_stop_reason).
        """
        current_time = now or datetime.now(timezone.utc)
        case_id = case.case_id

        # 1. Acquire Case Lock
        with self.lock_manager.acquire(case_id):
            # Check Merchant-Side Idempotency First:
            # If this exact logical request was already executed, return the cached result.
            seq = case.automated_action_count + 1
            idem_key = idempotency_key or self.idempotency_service.generate_key(case_id, action_type, seq)
            existing_record = self.idempotency_service.get_record(idem_key)
            if existing_record:
                self.audit_service.log(
                    case_id=case_id,
                    actor="SafeRecoveryExecutor",
                    event_type="DUPLICATE_ACTION_BLOCKED",
                    policy_version=policy_version,
                    action_type=action_type.value,
                    idempotency_key=idem_key,
                    rejection_reason="Duplicate logical execution blocked by idempotency token",
                    now=current_time,
                )
                exec_rec = Execution(
                    execution_id=existing_record.execution_id or f"exec_dup_{case_id}",
                    action_id="",
                    case_id=case_id,
                    status=ExecutionStatus(existing_record.status),
                    idempotency_key=idem_key,
                    created_at=existing_record.created_at,
                    updated_at=current_time,
                    error_message="Duplicate submission returned cached result",
                )
                return exec_rec, False, "DUPLICATE_ACTION_BLOCKED"

            # Register new idempotency token
            self.idempotency_service.register_or_get(idem_key, case_id, action_type, seq)

            # 2. Live Payment State Reconciliation immediately before action
            is_safe, rejection_reason = self.reconciliation_service.reconcile_before_execution(
                case=case,
                payment=payment,
                customer=customer,
                now=current_time,
            )
            if not is_safe:
                self.audit_service.log(
                    case_id=case_id,
                    actor="SafeRecoveryExecutor",
                    event_type="ACTION_REJECTED_RECONCILIATION",
                    policy_version=policy_version,
                    action_type=action_type.value,
                    observed_payment_state=payment.status.value,
                    rejection_reason=rejection_reason,
                    now=current_time,
                )
                exec_rec = Execution(
                    execution_id=f"exec_rej_{case_id}_{int(current_time.timestamp())}",
                    action_id="",
                    case_id=case_id,
                    status=ExecutionStatus.FAILED,
                    idempotency_key="",
                    created_at=current_time,
                    updated_at=current_time,
                    error_message=rejection_reason,
                )
                return exec_rec, False, rejection_reason

            # 3. Check Safety Invariants (Guard assertions)
            try:
                SafetyGuard.assert_no_action_after_terminal_recovery(payment, case, action_type)
                SafetyGuard.assert_no_action_after_opt_out(customer, action_type)
                SafetyGuard.assert_within_action_limit(case.automated_action_count, self.max_automated_actions, action_type)
                age_h = (current_time - case.created_at).total_seconds() / 3600.0
                SafetyGuard.assert_within_recovery_window(age_h, self.recovery_window_hours, action_type)
            except SafetyInvariantViolation as siv:
                reason = str(siv)
                self.audit_service.log(
                    case_id=case_id,
                    actor="SafeRecoveryExecutor",
                    event_type="SAFETY_INVARIANT_VIOLATION",
                    policy_version=policy_version,
                    action_type=action_type.value,
                    observed_payment_state=payment.status.value,
                    rejection_reason=reason,
                    now=current_time,
                )
                exec_rec = Execution(
                    execution_id=f"exec_siv_{case_id}_{int(current_time.timestamp())}",
                    action_id="",
                    case_id=case_id,
                    status=ExecutionStatus.FAILED,
                    idempotency_key="",
                    created_at=current_time,
                    updated_at=current_time,
                    error_message=reason,
                )
                return exec_rec, False, reason

            # STOP action handling
            if action_type == ActionType.STOP:
                case.current_state = CaseState.STOPPED
                case.last_updated_at = current_time
                case.terminal_reason = "POLICY_STOPPED"
                self.audit_service.log(
                    case_id=case_id,
                    actor="SafeRecoveryExecutor",
                    event_type="ACTION_STOPPED",
                    policy_version=policy_version,
                    action_type="STOP",
                    observed_payment_state=payment.status.value,
                    now=current_time,
                )
                exec_rec = Execution(
                    execution_id=f"exec_stop_{case_id}_{int(current_time.timestamp())}",
                    action_id="",
                    case_id=case_id,
                    status=ExecutionStatus.SUCCESS,
                    idempotency_key=f"idem_stop_{case_id}",
                    created_at=current_time,
                    updated_at=current_time,
                )
                return exec_rec, True, "POLICY_STOPPED"



            # 5. Atomic Action Reservation
            try:
                reservation = self.reservation_service.reserve_action(
                    case_id=case_id,
                    action_type=action_type,
                    idempotency_key=idem_key,
                    policy_version=policy_version,
                    now=current_time,
                )
            except DuplicateReservationError as dre:
                self.audit_service.log(
                    case_id=case_id,
                    actor="SafeRecoveryExecutor",
                    event_type="DUPLICATE_RESERVATION_BLOCKED",
                    policy_version=policy_version,
                    action_type=action_type.value,
                    rejection_reason=str(dre),
                    now=current_time,
                )
                exec_rec = Execution(
                    execution_id=f"exec_res_err_{case_id}",
                    action_id="",
                    case_id=case_id,
                    status=ExecutionStatus.FAILED,
                    idempotency_key=idem_key,
                    created_at=current_time,
                    updated_at=current_time,
                    error_message=str(dre),
                )
                return exec_rec, False, "DUPLICATE_RESERVATION_BLOCKED"

            # State transition: ACTION_RESERVED
            case.current_state = CaseState.ACTION_RESERVED
            case.last_updated_at = current_time

            # 6. Validate and Transition to ACTION_EXECUTING
            self.reservation_service.validate_and_start_executing(reservation.reservation_id, now=current_time)
            case.current_state = CaseState.ACTION_EXECUTING
            case.last_updated_at = current_time

            # 7. Execute Downstream Action (with ambiguous timeout handling)
            exec_id = f"exec_{reservation.reservation_id}"
            
            # Handle Ambiguous Timeout (F6 / F7)
            if simulate_timeout:
                case.current_state = CaseState.EXECUTION_UNKNOWN
                case.last_updated_at = current_time
                self.idempotency_service.mark_completed(idem_key, exec_id, "UNKNOWN")

                # RECONCILIATION FOR AMBIGUOUS EXECUTION
                # Do NOT retry blindly! Reconcile live payment and external state.
                self.audit_service.log(
                    case_id=case_id,
                    actor="SafeRecoveryExecutor",
                    event_type="EXECUTION_TIMEOUT_AMBIGUOUS",
                    policy_version=policy_version,
                    action_type=action_type.value,
                    reservation_id=reservation.reservation_id,
                    idempotency_key=idem_key,
                    execution_state="EXECUTION_UNKNOWN",
                    now=current_time,
                )

                # If ambiguous execution cannot be verified externally, route to MANUAL_REVIEW_REQUIRED
                case.current_state = CaseState.MANUAL_REVIEW_REQUIRED
                case.terminal_reason = "EXECUTION_TIMEOUT_UNRESOLVED"
                self.reservation_service.release_or_cancel(reservation.reservation_id)

                exec_rec = Execution(
                    execution_id=exec_id,
                    action_id="",
                    case_id=case_id,
                    status=ExecutionStatus.TIMEOUT,
                    idempotency_key=idem_key,
                    created_at=current_time,
                    updated_at=current_time,
                    error_message="Execution timed out; routed to MANUAL_REVIEW_REQUIRED",
                )
                return exec_rec, False, "EXECUTION_TIMEOUT_UNRESOLVED"

            # Handle Escalation Failure (F13)
            if action_type == ActionType.ESCALATE and simulate_escalation_failure:
                case.current_state = CaseState.MANUAL_REVIEW_REQUIRED
                case.terminal_reason = "ESCALATION_FAILURE"
                case.last_updated_at = current_time
                self.reservation_service.release_or_cancel(reservation.reservation_id)
                self.idempotency_service.mark_completed(idem_key, exec_id, "FAILED")

                self.audit_service.log(
                    case_id=case_id,
                    actor="SafeRecoveryExecutor",
                    event_type="ESCALATION_FAILURE",
                    policy_version=policy_version,
                    action_type="ESCALATE",
                    reservation_id=reservation.reservation_id,
                    rejection_reason="ESCALATION_FAILURE: Human routing dispatch failed",
                    now=current_time,
                )
                exec_rec = Execution(
                    execution_id=exec_id,
                    action_id="",
                    case_id=case_id,
                    status=ExecutionStatus.FAILED,
                    idempotency_key=idem_key,
                    created_at=current_time,
                    updated_at=current_time,
                    error_message="ESCALATION_FAILURE",
                )
                return exec_rec, False, "ESCALATION_FAILURE"

            # Regular execution failure
            if simulate_failure:
                case.current_state = CaseState.RE_EVALUATE
                case.last_updated_at = current_time
                self.reservation_service.release_or_cancel(reservation.reservation_id)
                self.idempotency_service.mark_completed(idem_key, exec_id, "FAILED")

                exec_rec = Execution(
                    execution_id=exec_id,
                    action_id="",
                    case_id=case_id,
                    status=ExecutionStatus.FAILED,
                    idempotency_key=idem_key,
                    created_at=current_time,
                    updated_at=current_time,
                    error_message="Provider execution rejected",
                )
                return exec_rec, False, "EXECUTION_FAILED"

            # 8. Successful Execution Confirmation: ACTION_CONFIRMED -> WAITING_FOR_OUTCOME
            self.reservation_service.confirm_reservation(reservation.reservation_id)
            case.automated_action_count += 1
            case.current_state = CaseState.ACTION_CONFIRMED
            case.current_state = CaseState.WAITING_FOR_OUTCOME
            case.last_updated_at = current_time

            self.idempotency_service.mark_completed(idem_key, exec_id, "SUCCESS")

            # 9. Audit Trail Logging
            self.audit_service.log(
                case_id=case_id,
                actor="SafeRecoveryExecutor",
                event_type="ACTION_EXECUTED_SUCCESS",
                policy_version=policy_version,
                action_type=action_type.value,
                reservation_id=reservation.reservation_id,
                idempotency_key=idem_key,
                execution_state="ACTION_CONFIRMED",
                observed_payment_state=payment.status.value,
                now=current_time,
            )

            exec_rec = Execution(
                execution_id=exec_id,
                action_id=f"act_{case_id}_{case.automated_action_count}",
                case_id=case_id,
                status=ExecutionStatus.SUCCESS,
                idempotency_key=idem_key,
                created_at=current_time,
                updated_at=current_time,
            )
            return exec_rec, True, None
