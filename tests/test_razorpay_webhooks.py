import hmac
import hashlib
import json
import pytest
from datetime import datetime, timezone

from integrations.razorpay.webhooks import RazorpayWebhookVerifier
from integrations.razorpay.events import RazorpayEventNormalizer
from integrations.razorpay.errors import WebhookVerificationError, InvalidRequestError
from domain.enums import PaymentStatus, FailureCode
from ingestion.deduplication import WebhookDeduplicationStore

@pytest.fixture
def webhook_secret():
    return "secret_test_webhook_key_123"

@pytest.fixture
def verifier(webhook_secret):
    return RazorpayWebhookVerifier(webhook_secret=webhook_secret)

@pytest.fixture
def sample_payload():
    return {
        "entity": "event",
        "account_id": "acc_test_123",
        "event": "payment.failed",
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_test_failed_01",
                    "entity": "payment",
                    "amount": 350000, # 3,500.00 INR
                    "currency": "INR",
                    "status": "failed",
                    "order_id": "order_test_01",
                    "error_code": "BAD_REQUEST_ERROR",
                    "error_description": "Insufficient funds in customer bank account",
                    "created_at": 1772445600,
                }
            }
        },
        "created_at": 1772445600,
    }

def test_webhook_signature_valid(verifier, webhook_secret, sample_payload):
    raw_body = json.dumps(sample_payload).encode("utf-8")
    signature = hmac.new(webhook_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    parsed = verifier.parse_and_validate(raw_body, signature)
    assert parsed["event"] == "payment.failed"
    assert parsed["payload"]["payment"]["entity"]["id"] == "pay_test_failed_01"

def test_webhook_signature_invalid_rejected(verifier, sample_payload):
    raw_body = json.dumps(sample_payload).encode("utf-8")
    invalid_sig = "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"

    with pytest.raises(WebhookVerificationError):
        verifier.parse_and_validate(raw_body, invalid_sig)

def test_webhook_signature_modified_body_rejected(verifier, webhook_secret, sample_payload):
    raw_body = json.dumps(sample_payload).encode("utf-8")
    signature = hmac.new(webhook_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    # Tamper with the raw body
    tampered_body = raw_body.replace(b"350000", b"100000")

    with pytest.raises(WebhookVerificationError):
        verifier.parse_and_validate(tampered_body, signature)

def test_webhook_signature_missing_rejected(verifier, sample_payload):
    raw_body = json.dumps(sample_payload).encode("utf-8")

    with pytest.raises(WebhookVerificationError):
        verifier.parse_and_validate(raw_body, None)

def test_webhook_malformed_json_rejected(verifier, webhook_secret):
    malformed_body = b"{ unclosed_json: true, "
    signature = hmac.new(webhook_secret.encode("utf-8"), malformed_body, hashlib.sha256).hexdigest()

    with pytest.raises(WebhookVerificationError):
        verifier.parse_and_validate(malformed_body, signature)

def test_event_normalization_paise_to_rupees(sample_payload):
    norm = RazorpayEventNormalizer.normalize_webhook(sample_payload, event_id="evt_test_01")

    assert norm.provider == "razorpay"
    assert norm.provider_event_id == "evt_test_01"
    assert norm.event_type == "payment.failed"
    assert norm.payment_id == "pay_test_failed_01"
    assert norm.amount == 3500.00 # 350000 paise / 100
    assert norm.payment_status == PaymentStatus.FAILED
    assert norm.failure_code == FailureCode.INSUFFICIENT_FUNDS
    assert len(norm.raw_event_reference) == 64 # SHA-256 hash

def test_webhook_deduplication_absorbs_duplicate(sample_payload):
    store = WebhookDeduplicationStore()
    event_id = "evt_dedup_test_01"

    # First delivery
    is_dup_1, _ = store.check_and_record(event_id, event_type=sample_payload["event"])
    assert is_dup_1 is False

    # Second delivery
    is_dup_2, _ = store.check_and_record(event_id, event_type=sample_payload["event"])
    assert is_dup_2 is True
