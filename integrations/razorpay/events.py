import hashlib
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from domain.enums import PaymentStatus, FailureCode
from integrations.razorpay.models import NormalizedPaymentEvent
from integrations.razorpay.errors import InvalidRequestError

class RazorpayEventNormalizer:
    """
    EVENT NORMALIZER.
    Translates authenticated, raw Razorpay webhook payloads into strictly typed,
    provider-agnostic NormalizedPaymentEvent models.
    Converts paise to INR and maps provider failure codes to domain FailureCode enums.
    """
    @staticmethod
    def map_failure_code(raw_code: Optional[str], raw_desc: Optional[str]) -> FailureCode:
        text = f"{raw_code or ''} {raw_desc or ''}".lower()
        if any(w in text for w in ["insufficient", "balance", "low_funds"]):
            return FailureCode.INSUFFICIENT_FUNDS
        if any(w in text for w in ["expired", "validity", "card_expired"]):
            return FailureCode.CARD_EXPIRED
        if any(w in text for w in ["bank", "down", "server", "unavailable"]):
            return FailureCode.BANK_UNAVAILABLE
        if any(w in text for w in ["timeout", "gateway", "network"]):
            return FailureCode.NETWORK_TIMEOUT
        return FailureCode.DO_NOT_HONOR

    @staticmethod
    def map_payment_status(raw_status: str, event_type: str) -> PaymentStatus:
        s = (raw_status or "").lower()
        if event_type in ["payment.captured", "payment_link.paid"] or s in ["captured", "paid"]:
            return PaymentStatus.CAPTURED
        if event_type == "payment.failed" or s == "failed":
            return PaymentStatus.FAILED
        if s == "authorized":
            return PaymentStatus.AUTHORIZED
        if s == "refunded":
            return PaymentStatus.REFUNDED
        return PaymentStatus.FAILED

    @classmethod
    def normalize_webhook(
        cls,
        payload: Dict[str, Any],
        event_id: str,
    ) -> NormalizedPaymentEvent:
        """
        Normalizes a raw Razorpay webhook dictionary.
        Raises InvalidRequestError if required payload entities are missing.
        """
        if not isinstance(payload, dict):
            raise InvalidRequestError("Payload must be a dictionary")

        event_type = payload.get("event")
        if not event_type:
            raise InvalidRequestError("Webhook payload missing 'event' type field")

        created_ts = payload.get("created_at")
        event_dt = (
            datetime.fromtimestamp(created_ts, tz=timezone.utc)
            if isinstance(created_ts, (int, float))
            else datetime.now(timezone.utc)
        )

        inner_payload = payload.get("payload", {})
        payment_entity = inner_payload.get("payment", {}).get("entity", {})
        plink_entity = inner_payload.get("payment_link", {}).get("entity", {})

        # Extract payment id
        payment_id = payment_entity.get("id") or plink_entity.get("payment_id")
        order_id = payment_entity.get("order_id") or plink_entity.get("order_id")

        # Amount in Razorpay is sent in paise (1 INR = 100 paise)
        amount_paise = payment_entity.get("amount") or plink_entity.get("amount") or 0
        amount_inr = round(float(amount_paise) / 100.0, 2)

        raw_status = payment_entity.get("status") or plink_entity.get("status") or ""
        status = cls.map_payment_status(raw_status, event_type)

        raw_err_code = payment_entity.get("error_code")
        raw_err_desc = payment_entity.get("error_description")
        failure_code = cls.map_failure_code(raw_err_code, raw_err_desc) if status == PaymentStatus.FAILED else None

        # Generate cryptographic audit reference of the raw payload
        raw_str = json.dumps(payload, sort_keys=True)
        audit_ref = hashlib.sha256(raw_str.encode("utf-8")).hexdigest()

        return NormalizedPaymentEvent(
            provider="razorpay",
            provider_event_id=event_id,
            event_type=event_type,
            payment_id=payment_id,
            order_id=order_id,
            amount=amount_inr,
            currency=payment_entity.get("currency") or plink_entity.get("currency") or "INR",
            payment_status=status,
            failure_code=failure_code,
            failure_reason=raw_err_desc,
            event_timestamp=event_dt,
            raw_event_reference=audit_ref,
        )
