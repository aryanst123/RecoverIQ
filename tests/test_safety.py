import pytest
from datetime import datetime, timezone, timedelta

from domain.enums import ActionType, CaseState, PaymentStatus, CustomerSegment, ChannelPreference, FailureCode
from domain.models import Customer, Payment, RecoveryCase
from execution.executor import SafeRecoveryExecutor
from ingestion.webhooks import WebhookIngestionService
from safety.guards import SafetyGuard, SafetyInvariantViolation
from safety.failure_injection import DeterministicFailureInjector
from safety.audit import AuditTrailService

def create_fixtures(suffix: str = "01"):
    now = datetime.now(timezone.utc)
    customer = Customer(
        customer_id=f"cust_safe_{suffix}",
        segment=CustomerSegment.STANDARD,
        channel_preference=ChannelPreference.WHATSAPP,
        opt_out=False,
    )
    payment = Payment(
        payment_id=f"pay_safe_{suffix}",
        customer_id=f"cust_safe_{suffix}",
        amount=2500.0,
        currency="INR",
        created_at=now,
        status=PaymentStatus.FAILED,
    )
    case = RecoveryCase(
        case_id=f"case_safe_{suffix}",
        payment_id=f"pay_safe_{suffix}",
        customer_id=f"cust_safe_{suffix}",
        current_state=CaseState.RECOVERY_ELIGIBLE,
        amount_due=2500.0,
        residual_amount=2500.0,
        created_at=now,
        last_updated_at=now,
        automated_action_count=0,
    )
    return customer, payment, case

def test_safety_invariant_1_no_action_after_terminal_recovery():
    customer, payment, case = create_fixtures()
    payment.status = PaymentStatus.CAPTURED
    with pytest.raises(SafetyInvariantViolation) as exc:
        SafetyGuard.assert_no_action_after_terminal_recovery(payment, case, ActionType.REMINDER)
    assert "INVARIANT 1" in str(exc.value)

def test_safety_invariant_2_no_execution_without_reservation():
    with pytest.raises(SafetyInvariantViolation) as exc:
        SafetyGuard.assert_has_valid_reservation(reservation_id=None)
    assert "INVARIANT 2" in str(exc.value)

def test_safety_invariant_4_no_action_after_opt_out():
    customer, payment, case = create_fixtures()
    customer.opt_out = True
    with pytest.raises(SafetyInvariantViolation) as exc:
        SafetyGuard.assert_no_action_after_opt_out(customer, ActionType.PAYMENT_LINK)
    assert "INVARIANT 4" in str(exc.value)

def test_safety_invariant_5_no_action_beyond_limit():
    with pytest.raises(SafetyInvariantViolation) as exc:
        SafetyGuard.assert_within_action_limit(3, 3, ActionType.REMINDER)
    assert "INVARIANT 5" in str(exc.value)

def test_safety_invariant_6_no_action_outside_recovery_window():
    with pytest.raises(SafetyInvariantViolation) as exc:
        SafetyGuard.assert_within_recovery_window(721.0, 720.0, ActionType.REMINDER)
    assert "INVARIANT 6" in str(exc.value)

def test_safety_invariant_9_no_regression_from_terminal_payment():
    with pytest.raises(SafetyInvariantViolation) as exc:
        SafetyGuard.assert_no_regression_from_terminal_payment(PaymentStatus.CAPTURED, PaymentStatus.FAILED)
    assert "INVARIANT 9" in str(exc.value)

def test_failure_injection_suite_f1_to_f13():
    executor = SafeRecoveryExecutor()
    wh_service = WebhookIngestionService()
    injector = DeterministicFailureInjector(executor, wh_service)

    # F1: Invalid Webhook Signature
    f1_res = injector.test_f1_invalid_signature()
    assert f1_res.status == "REJECTED_SIGNATURE"

    # F2: Duplicate Webhook
    f2_first, f2_dup = injector.test_f2_duplicate_webhook()
    assert f2_first.status == "PROCESSED"
    assert f2_dup.status == "DUPLICATE_SKIPPED"
    assert f2_dup.duplicate_detected is True

    # F3: Out-of-Order Webhook Event
    f3_res = injector.test_f3_out_of_order_webhook()
    assert f3_res.status == "REJECTED_OUT_OF_ORDER"

    # F6 & F7: Execution Timeout & Ambiguous State
    c6, p6, cs6 = create_fixtures("f6")
    exec_rec, success, stop_reason = injector.test_f6_f7_execution_timeout(cs6, p6, c6)
    assert success is False
    assert cs6.current_state == CaseState.MANUAL_REVIEW_REQUIRED
    assert cs6.terminal_reason == "EXECUTION_TIMEOUT_UNRESOLVED"

    # F8: Duplicate Execution Request
    c8, p8, cs8 = create_fixtures("f8")
    e1, e2 = injector.test_f8_duplicate_execution_request(cs8, p8, c8)
    assert e1[1] is True  # First succeeded
    assert e2[1] is False # Duplicate rejected
    assert e2[2] == "DUPLICATE_ACTION_BLOCKED"

    # F9: Payment Recovered Before Execution
    c9, p9, cs9 = create_fixtures("f9")
    e_rec, success, reason = injector.test_f9_payment_recovered_before_execution(cs9, p9, c9)
    assert success is False
    assert "ACTION_REJECTED" in reason

    # F10: Opt-Out Before Execution
    c10, p10, cs10 = create_fixtures("f10")
    e_rec, success, reason = injector.test_f10_opt_out_before_execution(cs10, p10, c10)
    assert success is False
    assert "OPT_OUT" in reason

    # F11: Action Limit Exceeded
    c11, p11, cs11 = create_fixtures("f11")
    e_rec, success, reason = injector.test_f11_action_limit_exceeded(cs11, p11, c11)
    assert success is False
    assert "MAX_ACTIONS" in reason

    # F12: Recovery Window Expired
    c12, p12, cs12 = create_fixtures("f12")
    e_rec, success, reason = injector.test_f12_recovery_window_expired(cs12, p12, c12)
    assert success is False
    assert "RECOVERY_WINDOW" in reason

    # F13: Escalation Failure
    c13, p13, cs13 = create_fixtures("f13")
    e_rec, success, reason = injector.test_f13_escalation_failure(cs13, p13, c13)
    assert success is False
    assert cs13.current_state == CaseState.MANUAL_REVIEW_REQUIRED
    assert cs13.terminal_reason == "ESCALATION_FAILURE"

def test_f4_out_of_band_payment_capture_reconciliation():
    """
    F4: Payment becomes CAPTURED out-of-band on gateway before automated outreach.
    Authoritative reconciliation MUST detect capture, transition case to RECOVERED,
    block subsequent recovery outreach, create ZERO downstream side-effects, and log audit event.
    """
    import server
    c = server.state.cases["case_DEMO_OVERRIDE"]
    assert c.current_state == CaseState.RECOVERY_ELIGIBLE

    req = server.FailureInjectionRequest(scenario_type="F4_OUT_OF_BAND_CAPTURE")
    res = server.trigger_failure_injection(req)

    assert res["execution_blocked"] is True
    assert res["case_state"] == "RECOVERED"
    assert res["residual_amount"] == 0.0
    assert res["payment_status"] == "CAPTURED"
    assert res["downstream_actions_created"] == 0

    # Verify subsequent direct execution attempt against the case is blocked
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        server.execute_case_action(c.case_id, server.ExecuteActionRequest(action_type="PAYMENT_LINK"))
    assert exc.value.status_code == 400

    # Verify structured audit event exists
    audits = server.state.audit_logger.get_case_audit(c.case_id)
    assert any(a.event_type == "ACTION_REJECTED_RECONCILIATION" for a in audits)

def test_f5_concurrent_execution_race_condition():
    """
    F5: Two simultaneous execution requests for the same recovery case.
    Case lock & reservation service MUST allow exactly ONE execution, reject the other,
    increment action count by exactly 1, create 1 side-effect, and prevent race duplication.
    """
    import server
    req = server.FailureInjectionRequest(scenario_type="F5_CONCURRENT_RACE")
    res = server.trigger_failure_injection(req)

    assert res["concurrent_requests"] == 2
    assert res["successful_executions"] == 1
    assert res["blocked_executions"] == 1
    assert "Race condition contained: 1 executed / 1 blocked" in res["safety_action"]
