import pytest
import threading
from datetime import datetime, timezone, timedelta

from domain.enums import ActionType, CaseState, PaymentStatus, CustomerSegment, ChannelPreference
from domain.models import Customer, Payment, RecoveryCase
from execution.locks import CaseLockManager
from execution.idempotency import MerchantIdempotencyService
from execution.reservation import (
    ActionReservationService,
    DuplicateReservationError,
    InvalidReservationError,
)
from execution.executor import SafeRecoveryExecutor
from safety.audit import AuditTrailService

def create_case_fixtures():
    now = datetime.now(timezone.utc)
    customer = Customer(
        customer_id="cust_exec_01",
        segment=CustomerSegment.STANDARD,
        channel_preference=ChannelPreference.WHATSAPP,
        opt_out=False,
    )
    payment = Payment(
        payment_id="pay_exec_01",
        customer_id="cust_exec_01",
        amount=3000.0,
        currency="INR",
        created_at=now,
        status=PaymentStatus.FAILED,
    )
    case = RecoveryCase(
        case_id="case_exec_01",
        payment_id="pay_exec_01",
        customer_id="cust_exec_01",
        current_state=CaseState.RECOVERY_ELIGIBLE,
        amount_due=3000.0,
        residual_amount=3000.0,
        created_at=now,
        last_updated_at=now,
        automated_action_count=0,
    )
    return customer, payment, case

def test_case_lock_manager_mutual_exclusion():
    lock_mgr = CaseLockManager()
    case_id = "case_lock_test"

    # Non-blocking acquire works
    assert lock_mgr.try_acquire_nowait(case_id) is True
    # Subsequent acquire while locked fails
    assert lock_mgr.try_acquire_nowait(case_id) is False

    lock_mgr.release_nowait(case_id)
    # Once released, acquire succeeds again
    assert lock_mgr.try_acquire_nowait(case_id) is True
    lock_mgr.release_nowait(case_id)

def test_concurrent_execution_race_condition():
    executor = SafeRecoveryExecutor()
    customer, payment, case = create_case_fixtures()

    results = []
    errors = []

    def worker():
        try:
            _, success, reason = executor.execute_policy_decision(
                case=case,
                payment=payment,
                customer=customer,
                action_type=ActionType.REMINDER,
                policy_version="1.0.0",
            )
            results.append((success, reason))
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
    assert len(results) == 2

    # Exactly one must succeed, and the other must be rejected (duplicate action / idempotency)
    successes = [r for r in results if r[0] is True]
    failures = [r for r in results if r[0] is False]
    assert len(successes) == 1
    assert len(failures) == 1
    assert case.automated_action_count == 1 # Never double counted!

def test_action_reservation_lifecycle():
    res_svc = ActionReservationService(ttl_seconds=1.0)
    now = datetime.now(timezone.utc)

    # 1. Reserve action
    res = res_svc.reserve_action("case_res_01", ActionType.REMINDER, "idem_1", "1.0.0", now=now)
    assert res.status == "RESERVED"

    # 2. Duplicate reservation for same case while active is rejected
    with pytest.raises(DuplicateReservationError):
        res_svc.reserve_action("case_res_01", ActionType.PAYMENT_LINK, "idem_2", "1.0.0", now=now)

    # 3. Validate and start executing
    active_res = res_svc.validate_and_start_executing(res.reservation_id, now=now)
    assert active_res.status == "EXECUTING"

    # 4. Confirm reservation
    res_svc.confirm_reservation(res.reservation_id)
    assert res.status == "CONFIRMED"

    # 5. After confirmation, new reservation for case is permitted
    res2 = res_svc.reserve_action("case_res_01", ActionType.PAYMENT_LINK, "idem_3", "1.0.0", now=now)
    assert res2.status == "RESERVED"

def test_expired_action_reservation_rejected():
    res_svc = ActionReservationService(ttl_seconds=10.0)
    t0 = datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc)
    t_after_expiry = datetime(2026, 3, 1, 10, 0, 15, tzinfo=timezone.utc) # 15s later

    res = res_svc.reserve_action("case_exp_01", ActionType.REMINDER, "idem_exp", "1.0.0", now=t0)
    
    with pytest.raises(InvalidReservationError) as exc:
        res_svc.validate_and_start_executing(res.reservation_id, now=t_after_expiry)
    assert "expired" in str(exc.value).lower()

def test_merchant_idempotency_service_cached_response():
    idem_svc = MerchantIdempotencyService()
    key = idem_svc.generate_key("case_idem_01", ActionType.PAYMENT_LINK, 1)

    rec1, is_new1 = idem_svc.register_or_get(key, "case_idem_01", ActionType.PAYMENT_LINK, 1)
    assert is_new1 is True
    idem_svc.mark_completed(key, "exec_123", "SUCCESS")

    rec2, is_new2 = idem_svc.register_or_get(key, "case_idem_01", ActionType.PAYMENT_LINK, 1)
    assert is_new2 is False
    assert rec2.execution_id == "exec_123"
    assert rec2.status == "SUCCESS"

def test_safe_recovery_executor_end_to_end_audit_trail():
    audit_svc = AuditTrailService()
    executor = SafeRecoveryExecutor(audit_service=audit_svc)
    customer, payment, case = create_case_fixtures()

    exec_rec, success, reason = executor.execute_policy_decision(
        case=case,
        payment=payment,
        customer=customer,
        action_type=ActionType.PAYMENT_LINK,
        policy_version="baseline-v1",
    )
    assert success is True
    assert case.current_state == CaseState.WAITING_FOR_OUTCOME
    assert case.automated_action_count == 1

    # Verify structured audit trail has records for this case
    case_audits = audit_svc.get_case_audit(case.case_id)
    assert len(case_audits) >= 1
    latest_audit = case_audits[-1]
    assert latest_audit.case_id == case.case_id
    assert latest_audit.action_type == "PAYMENT_LINK"
    assert latest_audit.execution_state == "ACTION_CONFIRMED"
