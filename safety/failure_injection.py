from __future__ import annotations
import json
import threading
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from execution.executor import SafeRecoveryExecutor

from domain.enums import (
    ActionType,
    CaseState,
    PaymentStatus,
    CustomerSegment,
    ChannelPreference,
    FailureCode,
)
from domain.models import Customer, Payment, RecoveryCase
from ingestion.webhooks import WebhookIngestionService, WebhookProcessingResult

class DeterministicFailureInjector:
    """
    FAILURE INJECTION TEST HARNESS.
    Deterministically simulates the 13 critical production failure scenarios:
    F1  - Invalid Webhook Signature
    F2  - Duplicate Webhook Ingestion
    F3  - Out-of-Order Webhook Event (regressing captured state)
    F4  - Stale Payment State during execution
    F5  - Concurrent Action Requests (lock contention)
    F6  - Downstream Execution Timeout
    F7  - Ambiguous Execution State
    F8  - Duplicate Execution Request (Idempotency token hit)
    F9  - Payment Recovered Immediately Before Execution
    F10 - Customer Opt-Out Immediately Before Execution
    F11 - Action Limit Exceeded Ceiling
    F12 - Recovery Window Expired
    F13 - Human Escalation Routing Failure
    """
    def __init__(self, executor: SafeRecoveryExecutor, webhook_service: WebhookIngestionService):
        self.executor = executor
        self.webhook_service = webhook_service

    def test_f1_invalid_signature(self) -> WebhookProcessingResult:
        body = json.dumps({"event": "payment.failed", "id": "evt_f1"})
        return self.webhook_service.process_webhook(
            raw_body=body,
            signature_header="invalid_tampered_signature_hex",
            event_id_header="evt_f1",
            payments_store={},
            cases_store={},
        )

    def test_f2_duplicate_webhook(self) -> Tuple[WebhookProcessingResult, WebhookProcessingResult]:
        body = json.dumps({"event": "payment.captured", "id": "evt_f2", "payload": {"payment": {"entity": {"id": "pay_f2"}}}})
        sig = self.webhook_service.signature_validator.compute_signature(body)
        p = Payment(payment_id="pay_f2", customer_id="c_f2", amount=1000.0, created_at=datetime.now(timezone.utc), status=PaymentStatus.FAILED)
        store = {"pay_f2": p}

        first_res = self.webhook_service.process_webhook(body, sig, "evt_f2", store, {})
        dup_res = self.webhook_service.process_webhook(body, sig, "evt_f2", store, {})
        return first_res, dup_res

    def test_f3_out_of_order_webhook(self) -> WebhookProcessingResult:
        # Payment is already captured; stale failed event arrives
        body = json.dumps({"event": "payment.failed", "id": "evt_f3", "payload": {"payment": {"entity": {"id": "pay_f3"}}}})
        sig = self.webhook_service.signature_validator.compute_signature(body)
        p = Payment(payment_id="pay_f3", customer_id="c_f3", amount=1000.0, created_at=datetime.now(timezone.utc), status=PaymentStatus.CAPTURED)
        return self.webhook_service.process_webhook(body, sig, "evt_f3", {"pay_f3": p}, {})

    def test_f5_concurrent_action_requests(self, case: RecoveryCase, payment: Payment, customer: Customer) -> Tuple[bool, bool]:
        # Launch 2 parallel threads attempting to reserve/execute for the same case
        results = []

        def worker():
            _, success, _ = self.executor.execute_policy_decision(
                case=case,
                payment=payment,
                customer=customer,
                action_type=ActionType.REMINDER,
                policy_version="1.0.0",
            )
            results.append(success)

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Exactly one should succeed, the other rejected due to idempotency or reservation lock
        return results[0], results[1]

    def test_f6_f7_execution_timeout(self, case: RecoveryCase, payment: Payment, customer: Customer):
        return self.executor.execute_policy_decision(
            case=case,
            payment=payment,
            customer=customer,
            action_type=ActionType.PAYMENT_LINK,
            policy_version="1.0.0",
            simulate_timeout=True,
        )

    def test_f8_duplicate_execution_request(self, case: RecoveryCase, payment: Payment, customer: Customer):
        # Execute once with explicit idempotency key
        idem_key = f"idem_f8_{case.case_id}"
        res1 = self.executor.execute_policy_decision(
            case=case,
            payment=payment,
            customer=customer,
            action_type=ActionType.REMINDER,
            policy_version="1.0.0",
            idempotency_key=idem_key,
        )
        # Attempt identical logical execution immediately
        res2 = self.executor.execute_policy_decision(
            case=case,
            payment=payment,
            customer=customer,
            action_type=ActionType.REMINDER,
            policy_version="1.0.0",
            idempotency_key=idem_key,
        )
        return res1, res2

    def test_f9_payment_recovered_before_execution(self, case: RecoveryCase, payment: Payment, customer: Customer):
        # Stale state: payment was captured out of band
        payment.status = PaymentStatus.CAPTURED
        return self.executor.execute_policy_decision(
            case=case,
            payment=payment,
            customer=customer,
            action_type=ActionType.REMINDER,
            policy_version="1.0.0",
        )

    def test_f10_opt_out_before_execution(self, case: RecoveryCase, payment: Payment, customer: Customer):
        customer.opt_out = True
        return self.executor.execute_policy_decision(
            case=case,
            payment=payment,
            customer=customer,
            action_type=ActionType.REMINDER,
            policy_version="1.0.0",
        )

    def test_f11_action_limit_exceeded(self, case: RecoveryCase, payment: Payment, customer: Customer):
        case.automated_action_count = 3
        return self.executor.execute_policy_decision(
            case=case,
            payment=payment,
            customer=customer,
            action_type=ActionType.REMINDER,
            policy_version="1.0.0",
        )

    def test_f12_recovery_window_expired(self, case: RecoveryCase, payment: Payment, customer: Customer):
        old_time = datetime.now(timezone.utc) - timedelta(days=35)
        case.created_at = old_time
        return self.executor.execute_policy_decision(
            case=case,
            payment=payment,
            customer=customer,
            action_type=ActionType.REMINDER,
            policy_version="1.0.0",
        )

    def test_f13_escalation_failure(self, case: RecoveryCase, payment: Payment, customer: Customer):
        return self.executor.execute_policy_decision(
            case=case,
            payment=payment,
            customer=customer,
            action_type=ActionType.ESCALATE,
            policy_version="1.0.0",
            simulate_escalation_failure=True,
        )
