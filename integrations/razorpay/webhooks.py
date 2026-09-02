import hmac
import hashlib
import json
import logging
from typing import Tuple, Dict, Any, Optional
from integrations.razorpay.errors import WebhookVerificationError

logger = logging.getLogger(__name__)

class RazorpayWebhookVerifier:
    """
    RAZORPAY WEBHOOK AUTHENTICATION & SIGNATURE VERIFICATION.
    Validates HMAC-SHA256 signatures over raw request bodies using constant-time comparison.
    NEVER parses or re-serializes JSON before signature verification.
    """
    def __init__(self, webhook_secret: str):
        if not webhook_secret:
            raise ValueError("Webhook secret must be non-empty for Razorpay webhook verification")
        self._secret = webhook_secret.encode("utf-8")

    def verify_signature(
        self,
        raw_body: bytes,
        signature: Optional[str],
    ) -> bool:
        """
        Verifies raw request body against x-razorpay-signature header.
        Uses constant-time comparison to prevent timing attacks.
        """
        if not signature or not isinstance(signature, str):
            logger.warning("Rejected webhook: missing or invalid signature header")
            return False

        if not raw_body or not isinstance(raw_body, bytes):
            logger.warning("Rejected webhook: empty or non-bytes request body")
            return False

        computed = hmac.new(
            self._secret,
            raw_body,
            hashlib.sha256,
        ).hexdigest()

        is_valid = hmac.compare_digest(computed.lower(), signature.strip().lower())
        if not is_valid:
            logger.warning("Rejected webhook: signature mismatch")
        return is_valid

    def parse_and_validate(
        self,
        raw_body: bytes,
        signature: Optional[str],
        event_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Full verification and parsing pipeline.
        Fails closed with WebhookVerificationError if signature is invalid or JSON is malformed.
        """
        if not self.verify_signature(raw_body, signature):
            raise WebhookVerificationError("Invalid or missing Razorpay webhook signature")

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as err:
            logger.warning(f"Rejected webhook: malformed JSON body - {err}")
            raise WebhookVerificationError(f"Malformed JSON in webhook body: {err}")

        if not isinstance(payload, dict):
            raise WebhookVerificationError("Webhook body must be a JSON object")

        return payload
