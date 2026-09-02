import json
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass

from domain.enums import PaymentStatus, CaseState
from domain.models import Payment, RecoveryCase
from ingestion.validation import WebhookSignatureValidator, InvalidSignatureError
from ingestion.deduplication import WebhookDeduplicationStore
from safety.guards import SafetyGuard, SafetyInvariantViolation
from safety.audit import AuditTrailService

@dataclass
class WebhookProcessingResult:
    status: str # PROCESSED, DUPLICATE_SKIPPED, REJECTED_SIGNATURE, REJECTED_OUT_OF_ORDER, ERROR
    message: str
    duplicate_detected: bool = False
    state_mutated: bool = False
    event_id: Optional[str] = None

class WebhookIngestionService:
    """
    Razorpay Webhook Receiver & Safety Processor.
    Handles HMAC validation, event ID deduplication, out-of-order protection, and live reconciliation.
    """
    def __init__(
        self,
        signature_validator: Optional[WebhookSignatureValidator] = None,
        deduplication_store: Optional[WebhookDeduplicationStore] = None,
        audit_service: Optional[AuditTrailService] = None,
    ):
        self.signature_validator = signature_validator or WebhookSignatureValidator()
        self.deduplication_store = deduplication_store or WebhookDeduplicationStore()
        self.audit_service = audit_service or AuditTrailService()

    def process_webhook(
        self,
        raw_body: str,
        signature_header: str,
        event_id_header: str,
        payments_store: Dict[str, Payment],
        cases_store: Dict[str, RecoveryCase],
        now: Optional[datetime] = None,
    ) -> WebhookProcessingResult:
        current_time = now or datetime.now(timezone.utc)

        # 1. Webhook Signature Validation (HMAC-SHA256 over raw body)
        if not self.signature_validator.verify_signature(raw_body, signature_header):
            self.audit_service.log(
                case_id="unknown",
                actor="WebhookIngestionService",
                event_type="WEBHOOK_REJECTED_SIGNATURE",
                policy_version="1.0.0",
                rejection_reason="Invalid HMAC-SHA256 signature",
                now=current_time,
            )
            return WebhookProcessingResult(
                status="REJECTED_SIGNATURE",
                message="Invalid HMAC-SHA256 signature",
                duplicate_detected=False,
                state_mutated=False,
                event_id=event_id_header,
            )

        # Parse JSON payload
        try:
            payload = json.loads(raw_body)
        except Exception as e:
            return WebhookProcessingResult(
                status="ERROR",
                message=f"Malformed JSON body: {str(e)}",
                duplicate_detected=False,
                state_mutated=False,
                event_id=event_id_header,
            )

        event_type = payload.get("event", "unknown")
        event_id = event_id_header or payload.get("id", f"evt_{int(current_time.timestamp())}")

        # 2. Webhook Event Deduplication
        is_dup, _ = self.deduplication_store.check_and_record(
            event_id=event_id,
            event_type=event_type,
            payload_summary={"event": event_type},
            now=current_time,
        )
        if is_dup:
            self.audit_service.log(
                case_id=payload.get("payload", {}).get("payment", {}).get("entity", {}).get("notes", {}).get("case_id", "unknown"),
                actor="WebhookIngestionService",
                event_type="WEBHOOK_DUPLICATE_DETECTED",
                policy_version="1.0.0",
                metadata={"event_id": event_id, "duplicate_detected": True},
                now=current_time,
            )
            return WebhookProcessingResult(
                status="DUPLICATE_SKIPPED",
                message=f"Event {event_id} has already been processed",
                duplicate_detected=True,
                state_mutated=False,
                event_id=event_id,
            )

        # Extract payment data
        pay_entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
        payment_id = pay_entity.get("id")
        case_id = pay_entity.get("notes", {}).get("case_id")

        if not payment_id or payment_id not in payments_store:
            return WebhookProcessingResult(
                status="PROCESSED",
                message=f"Webhook event {event_type} acknowledged; payment {payment_id} not managed in local registry",
                duplicate_detected=False,
                state_mutated=False,
                event_id=event_id,
            )

        payment = payments_store[payment_id]
        case = cases_store.get(case_id) if case_id else None

        # 3. Out-Of-Order Event Handling & Terminal State Protection
        # e.g., payment.failed arrives when payment is already CAPTURED
        if event_type == "payment.failed":
            if payment.status == PaymentStatus.CAPTURED:
                self.audit_service.log(
                    case_id=case_id or "unknown",
                    actor="WebhookIngestionService",
                    event_type="WEBHOOK_OUT_OF_ORDER_DROPPED",
                    policy_version="1.0.0",
                    rejection_reason="Received payment.failed for already CAPTURED payment; dropping regression event",
                    now=current_time,
                )
                return WebhookProcessingResult(
                    status="REJECTED_OUT_OF_ORDER",
                    message="Stale payment.failed event rejected: payment already captured",
                    duplicate_detected=False,
                    state_mutated=False,
                    event_id=event_id,
                )

        # 4. Handle Payment Captured Event
        if event_type in ["payment.captured", "order.paid"]:
            payment.status = PaymentStatus.CAPTURED
            if case:
                case.current_state = CaseState.RECOVERED
                case.residual_amount = 0.0
                case.last_updated_at = current_time

            self.audit_service.log(
                case_id=case_id or "unknown",
                actor="WebhookIngestionService",
                event_type="PAYMENT_CAPTURED_WEBHOOK",
                policy_version="1.0.0",
                observed_payment_state="CAPTURED",
                final_outcome="RECOVERED",
                now=current_time,
            )
            return WebhookProcessingResult(
                status="PROCESSED",
                message=f"Payment {payment_id} transitioned to CAPTURED",
                duplicate_detected=False,
                state_mutated=True,
                event_id=event_id,
            )

        return WebhookProcessingResult(
            status="PROCESSED",
            message=f"Event {event_type} processed",
            duplicate_detected=False,
            state_mutated=False,
            event_id=event_id,
        )
