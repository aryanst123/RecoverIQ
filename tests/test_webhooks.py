import json
import pytest
from datetime import datetime, timezone

from domain.enums import PaymentStatus, CaseState
from domain.models import Payment, RecoveryCase
from ingestion.validation import WebhookSignatureValidator, InvalidSignatureError
from ingestion.deduplication import WebhookDeduplicationStore
from ingestion.webhooks import WebhookIngestionService

def test_webhook_signature_validation():
    secret = "test_webhook_secret_xyz123"
    validator = WebhookSignatureValidator(secret=secret)
    body = '{"event":"payment.failed","id":"evt_123"}'

    valid_sig = validator.compute_signature(body)
    assert validator.verify_signature(body, valid_sig) is True

    # Tampered body fails
    tampered_body = '{"event":"payment.failed","id":"evt_124"}'
    assert validator.verify_signature(tampered_body, valid_sig) is False

    # Invalid signature string fails
    assert validator.verify_signature(body, "bad_sig_12345") is False
    assert validator.verify_signature(body, "") is False

    # validate_or_raise raises exception on mismatch
    with pytest.raises(InvalidSignatureError):
        validator.validate_or_raise(body, "invalid_sig")

def test_webhook_deduplication_store():
    store = WebhookDeduplicationStore()
    
    is_dup1, rec1 = store.check_and_record("evt_test_01", "payment.failed")
    assert is_dup1 is False
    assert rec1.duplicate_count == 0

    is_dup2, rec2 = store.check_and_record("evt_test_01", "payment.failed")
    assert is_dup2 is True
    assert rec2.duplicate_count == 1

def test_webhook_ingestion_out_of_order_protection():
    validator = WebhookSignatureValidator(secret="sec123")
    service = WebhookIngestionService(signature_validator=validator)

    now = datetime.now(timezone.utc)
    payment = Payment(
        payment_id="pay_ooo_01",
        customer_id="cust_ooo",
        amount=5000.0,
        currency="INR",
        created_at=now,
        status=PaymentStatus.CAPTURED, # Already captured!
    )
    case = RecoveryCase(
        case_id="case_ooo_01",
        payment_id="pay_ooo_01",
        customer_id="cust_ooo",
        current_state=CaseState.RECOVERED,
        amount_due=5000.0,
        residual_amount=0.0,
        created_at=now,
        last_updated_at=now,
    )
    payments_store = {"pay_ooo_01": payment}
    cases_store = {"case_ooo_01": case}

    # Stale/delayed payment.failed event arrives
    body = json.dumps({
        "event": "payment.failed",
        "id": "evt_stale_01",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_ooo_01",
                    "notes": {"case_id": "case_ooo_01"},
                }
            }
        },
    })
    sig = validator.compute_signature(body)

    res = service.process_webhook(
        raw_body=body,
        signature_header=sig,
        event_id_header="evt_stale_01",
        payments_store=payments_store,
        cases_store=cases_store,
    )

    assert res.status == "REJECTED_OUT_OF_ORDER"
    assert payment.status == PaymentStatus.CAPTURED # Protected against regression!
    assert case.current_state == CaseState.RECOVERED

def test_webhook_ingestion_capture_event_flow():
    validator = WebhookSignatureValidator(secret="sec123")
    service = WebhookIngestionService(signature_validator=validator)

    now = datetime.now(timezone.utc)
    payment = Payment(
        payment_id="pay_cap_01",
        customer_id="cust_cap",
        amount=1800.0,
        currency="INR",
        created_at=now,
        status=PaymentStatus.FAILED,
    )
    case = RecoveryCase(
        case_id="case_cap_01",
        payment_id="pay_cap_01",
        customer_id="cust_cap",
        current_state=CaseState.WAITING_FOR_OUTCOME,
        amount_due=1800.0,
        residual_amount=1800.0,
        created_at=now,
        last_updated_at=now,
    )
    payments_store = {"pay_cap_01": payment}
    cases_store = {"case_cap_01": case}

    body = json.dumps({
        "event": "payment.captured",
        "id": "evt_cap_01",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_cap_01",
                    "notes": {"case_id": "case_cap_01"},
                }
            }
        },
    })
    sig = validator.compute_signature(body)

    # First event: process
    res1 = service.process_webhook(body, sig, "evt_cap_01", payments_store, cases_store)
    assert res1.status == "PROCESSED"
    assert res1.state_mutated is True
    assert payment.status == PaymentStatus.CAPTURED
    assert case.current_state == CaseState.RECOVERED
    assert case.residual_amount == 0.0

    # Duplicate of same capture event: skip without double mutation
    res2 = service.process_webhook(body, sig, "evt_cap_01", payments_store, cases_store)
    assert res2.status == "DUPLICATE_SKIPPED"
    assert res2.duplicate_detected is True
    assert res2.state_mutated is False
