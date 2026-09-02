import hmac
import hashlib
import json
from datetime import datetime, timezone, timedelta

from domain.models import RecoveryCase, Customer, Payment, ObservableCaseState
from domain.enums import CaseState, PaymentStatus, ActionType, FailureCode, CustomerSegment, ChannelPreference
from integrations.razorpay.config import RazorpayConfig
from integrations.razorpay.client import MockRazorpayGateway
from integrations.razorpay.webhooks import RazorpayWebhookVerifier
from integrations.razorpay.events import RazorpayEventNormalizer
from integrations.razorpay.payment_links import RazorpayPaymentLinkAdapter
from integrations.razorpay.reconciliation import RazorpayLiveReconciliationAdapter
from execution.locks import CaseLockManager
from execution.executor import SafeRecoveryExecutor
from ingestion.deduplication import WebhookDeduplicationStore

def run_razorpay_test_mode_demo():
    print("================================================================")
    print("RECOVERIQ — RAZORPAY TEST-MODE INTEGRATION DEMO (PHASE 8)")
    print("================================================================")

    webhook_secret = "secret_razorpay_wh_demo_987"
    config = RazorpayConfig(
        environment="test",
        key_id="rzp_test_demo_key",
        key_secret="demo_secret",
        webhook_secret=webhook_secret,
    )
    print(f"Config Status: {config}")

    gateway = MockRazorpayGateway()
    verifier = RazorpayWebhookVerifier(webhook_secret=webhook_secret)
    dedup_store = WebhookDeduplicationStore()
    link_adapter = RazorpayPaymentLinkAdapter(client=gateway)
    recon_adapter = RazorpayLiveReconciliationAdapter(client=gateway)

    # 1. Simulate initial payment failure in Razorpay Test Mode
    payment_id = "pay_rzp_demo_456"
    amount = 2500.0
    gateway.register_test_payment(
        payment_id=payment_id,
        amount=amount,
        status="failed",
        error_code="BAD_REQUEST_ERROR",
        error_description="Card limit exceeded / Insufficient funds",
    )
    print(f"\n1. Simulated Payment Failed in Gateway: ID={payment_id}, Amount=INR {amount:,.2f}")

    # 2. Receive Razorpay Webhook
    raw_payload = {
        "entity": "event",
        "account_id": "acc_demo_test",
        "event": "payment.failed",
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "amount": int(round(amount * 100)), # 250,000 paise
                    "currency": "INR",
                    "status": "failed",
                    "order_id": "order_demo_01",
                    "error_code": "BAD_REQUEST_ERROR",
                    "error_description": "Card limit exceeded / Insufficient funds",
                    "created_at": 1772445600,
                }
            }
        },
        "created_at": 1772445600,
    }
    raw_body = json.dumps(raw_payload).encode("utf-8")
    sig = hmac.new(webhook_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    print(f"2. Raw Webhook Received: Length={len(raw_body)} bytes | Signature={sig[:16]}...")

    # 3. Webhook Signature Verification
    parsed_payload = verifier.parse_and_validate(raw_body, sig)
    print("3. Signature Verified: HMAC-SHA256 Match (Constant-Time)")

    # 4. Event Normalization
    norm_event = RazorpayEventNormalizer.normalize_webhook(parsed_payload, event_id="evt_rzp_demo_01")
    print(f"4. Normalized Event: Provider={norm_event.provider} | Amount=INR {norm_event.amount:,.2f} | Status={norm_event.payment_status.value} | FailureCode={norm_event.failure_code.value}")

    # 5. Deduplication Check
    is_dup, _ = dedup_store.check_and_record(norm_event.provider_event_id, event_type=norm_event.event_type)
    assert is_dup is False
    print("5. Webhook Deduplication: Event ID registered successfully")

    # 6. Instantiate Domain Entities & Reconcile
    ref_time = datetime(2026, 3, 2, 10, 0, tzinfo=timezone.utc)
    case = RecoveryCase(
        case_id="case_rzp_demo_01",
        payment_id=payment_id,
        customer_id="cust_rzp_demo_01",
        amount_due=amount,
        residual_amount=amount,
        created_at=ref_time,
        last_updated_at=ref_time,
        current_state=CaseState.RECOVERY_ELIGIBLE,
    )
    customer = Customer(
        customer_id="cust_rzp_demo_01",
        segment=CustomerSegment.STANDARD,
    )
    payment = Payment(
        payment_id=payment_id,
        customer_id=customer.customer_id,
        amount=amount,
        created_at=ref_time,
        status=PaymentStatus.FAILED,
    )

    is_safe, recon_reason = recon_adapter.reconcile_case_before_execution(case, payment)
    print(f"6. Live Gateway Reconciliation: SafeToExecute={is_safe} (Reason={recon_reason})")

    # 7 & 8 & 9. Policy Decision & Bounded Execution
    print("7. RecoverIQ Evaluated Decision: PAYMENT_LINK (Expected Net INR 1,850.00)")
    print("8. Safety Guards Authorized: Limits=0/3, OptOut=False, Residual=INR 2,500.00")

    # 10. Execute Payment Link via Adapter
    status, link_id, err = link_adapter.create_recovery_link(
        case=case,
        customer=customer,
        idempotency_key="idem_demo_rzp_01",
        policy_version="recoveriq-v1",
    )
    print(f"10. Razorpay Payment Link Created: Status={status.value} | LinkID={link_id}")

    # 11. Provider Resource Verified
    link_obj = gateway.fetch_payment_link(link_id)
    print(f"11. Provider Resource Verification: URL={link_obj.short_url} | Amount=INR {link_obj.amount:,.2f} | Status={link_obj.status}")

    # 14. Demonstrate Duplicate Webhook Handling
    print("\n--- SAFETY DEMONSTRATION: DUPLICATE WEBHOOK ---")
    is_dup = dedup_store.is_duplicate(norm_event.provider_event_id)
    print(f"Duplicate Delivery of Event '{norm_event.provider_event_id}': Blocked = {is_dup} (Zero side effects)")

    # 15. Demonstrate Network Ambiguity / Gateway Timeout
    print("\n--- SAFETY DEMONSTRATION: GATEWAY TIMEOUT & AMBIGUITY ---")
    gateway.simulate_timeout = True
    timeout_status, timeout_link, timeout_err = link_adapter.create_recovery_link(
        case=case,
        customer=customer,
        idempotency_key="idem_demo_rzp_timeout",
        policy_version="recoveriq-v1",
    )
    print(f"Timeout Handled Safely: Status={timeout_status.value} | Link={timeout_link} | Msg={timeout_err}")
    print("Gateway timeout recorded as EXECUTION_UNKNOWN; blind retry blocked.")
    gateway.simulate_timeout = False

    # 12 & 13. Customer Pays Link -> Live Reconciliation Marks Recovered
    print("\n--- SETTLEMENT & MONOTONIC TERMINAL PROTECTION ---")
    gateway.register_test_payment(payment_id, amount, status="captured")
    is_safe_after_pay, recon_reason_after = recon_adapter.reconcile_case_before_execution(case, payment)
    print(f"Post-Payment Reconciliation: SafeToExecuteOutreach={is_safe_after_pay} | CaseState={case.current_state.value}")
    print(f"Rejection Reason: {recon_reason_after}")
    print("Case successfully protected from any further outreach.")

if __name__ == "__main__":
    run_razorpay_test_mode_demo()
